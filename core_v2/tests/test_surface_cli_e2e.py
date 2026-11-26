"""Live end-to-end verification for core.surface.cli, core.surface.bootstrap, and core_v2/yscb.py."""

from __future__ import annotations

from abc import ABC

from dataclasses import dataclass, field
from enum import Enum
import gc
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec
import io
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import threading
import time
from types import ModuleType
from typing import Annotated, Generic, Literal, Mapping, Optional, Sequence, TypeVar
import zipfile

from core.execution.daemon import DaemonRunState, query_daemon_control
from core.execution.rpc import FrameKind, probe_daemon_endpoint
from core.execution.runtime import (
    CallPropagationContext,
    ClientRoutingPolicy,
    DispatchMode,
    InvokeRequest,
    SecurityTier,
    TaskContext,
    TaskExposure,
    TaskOutcome,
    build_workspace_module_services_factory,
)
from core.filesystem.space import SpaceDiffBatch, SpaceSpec
from core.metadata.config import ConfigStore
from core.metadata.contributes import (
    bind_locale_getter_dialect,
    discover_installed_manifests_map,
    is_control_plane_reserved_path,
    lookup_cold_workspace_dialect,
    lookup_cold_workspace_dialect_state,
)
from core.packaging.env import EnvGarbageCollector, EnvSpec, ImmutableVenvPool
from core.packaging.installer import ProviderClient
from core.foundation import (
    SemVer4,
    DataclassCodec,
    EnvHash,
    ErrorCode,
    EventId,
    HostPath,
    ModuleId,
    ProfilerSession,
    ProgressEvent,
    SemanticUri,
    SpaceId,
    TaskId,
    YscbError,
)
from core.surface.bootstrap import (
    ClearDynamicSpaceInput,
    ConfigGetInput,
    ConfigSetInput,
    CoreSystemModule,
    SetDynamicSpaceInput,
    SpaceAckCursorInput,
    SpaceScanInput,
    SystemResultView,
    WorkspaceKernel,
    WorkspaceKernelFactory,
)
from core.surface.cli import (
    ApprovalTokenStore,
    CallerMode,
    CliOptionSpec,
    HelpRenderer,
    render_task_help,
    IndexedTaskEntry,
    ModuleTasksIndex,
    WorkspaceTasksIndexCache,
    build_cli_command_tree,
    compile_tasks_index,
    detect_caller_environment,
    extract_global_flags,
    main as cli_main,
    resolve_cli_invocation,
)
from core.surface.sdk import (
    Arg,
    ExitCodeProvider,
    HumanRenderable,
    MigrationRequest,
    Module,
    ModuleEnv,
    Option,
    TaskGroup,
    on_migrate,
    task,
)
from core.surface.sdk.advanced import (
    InMemoryModule,
    YscbClient,
    format_output,
)
from tests import CORE_SRC_ROOT, CORE_V2_ROOT
from tests._harness import check, log, stop_daemon_cleanly


class _ZeroImportGuardFinder(MetaPathFinder):
    """MetaPathFinder asserting cold CLI paths never import business modules."""

    def __init__(self, forbidden_prefixes: tuple[str, ...]) -> None:
        self.forbidden_prefixes = forbidden_prefixes
        self.violations: list[str] = []

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]] = None,
        target: Optional[ModuleType] = None,
    ) -> Optional[ModuleSpec]:
        _ = (path, target)
        if fullname.startswith(self.forbidden_prefixes):
            self.violations.append(fullname)
            raise AssertionError(f"Zero-import cold CLI path attempted forbidden import: {fullname}")
        return None


class _MockTtyInput:
    """Simulated TTY input stream asserting readline() is never invoked in non-human modes."""

    def __init__(self, lines: tuple[str, ...] = (), *, is_tty: bool = True, forbid_read: bool = False) -> None:
        self._lines = list(lines)
        self._is_tty = is_tty
        self._forbid_read = forbid_read
        self.read_calls = 0

    def isatty(self) -> bool:
        return self._is_tty

    def readline(self) -> str:
        self.read_calls += 1
        if self._forbid_read:
            raise AssertionError("Interactive readline() must never be called in AGENT/NON_TTY/CI mode!")
        return self._lines.pop(0) if self._lines else ""


class _MockTtyOutput:
    """In-memory output stream with configurable isatty()."""

    def __init__(self, *, is_tty: bool = True) -> None:
        self._buf = io.StringIO()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, s: str) -> int:
        return self._buf.write(s)

    def flush(self) -> None:
        self._buf.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()


@dataclass(frozen=True, slots=True)
class _SampleDeployInput:
    target: Annotated[Literal["staging", "prod"], Arg(name="target", summary="Target slot")] = "staging"
    mode: Annotated[
        str,
        Option(short="m", summary="Execution strategy", group="strategy"),
    ] = "fast"
    safe_plan: Annotated[
        bool,
        Option(summary="Dry-run conservative strategy", group="strategy"),
    ] = False
    meta: Annotated[
        dict[str, str],
        Option(summary="Metadata dictionary"),
    ] = field(default_factory=lambda: {"env": "default"})
    exit_status: Annotated[
        int,
        Option(summary="Custom exit status code"),
    ] = 0
    tags: Annotated[tuple[str, ...], Option(short="t", summary="Optional labels")] = ()


@dataclass(frozen=True, slots=True)
class _SampleDictDefaultInput:
    label: Annotated[str, Arg(name="label", summary="Positional label with default")] = "auto-label"


@dataclass(frozen=True, slots=True)
class _SampleCustomExitOutput(HumanRenderable, ExitCodeProvider):
    text: str
    code: int

    def render_text(self) -> str:
        return self.text

    def exit_code(self) -> int:
        return self.code


class _PlanSubGroup(TaskGroup):
    @task(
        cli="plan",
        name="alpha.plan.default",
        summary="Show active plan status summary",
        usage_pros=("快速檢視當前工作區計畫狀態",),
        usage_cons=("不接受未知子命令參數",),
    )
    def plan_default(self, ctx: TaskContext) -> str:
        _ = self
        return ctx.locale.translate("plan.greeting", caller_module=ModuleId("alpha"))

    @task(cli=("plan", "verify"), name="alpha.plan.verify", summary="Verify plan structure")
    def plan_verify(self, req: _SampleDictDefaultInput, ctx: TaskContext) -> dict[str, str]:
        _ = (self, ctx)
        return {"status": "plan-verify-ok", "label": req.label}


class _SampleCliModule(Module):
    id = "alpha"
    aliases = ("al",)
    description = "Alpha sample module for zero-import CLI verification"
    groups = (_PlanSubGroup,)

    @task(
        cli="deploy",
        name="deploy",
        aliases=("dp",),
        summary="Deploy alpha artifact with mutually exclusive strategy group",
        usage_pros=("支援單次確認碼安全部署",),
        usage_cons=("禁止靜態 -y 繞過授權",),
        security=SecurityTier.GATED,
        dispatch_mode=DispatchMode.HYBRID,
    )
    def deploy(self, req: _SampleDeployInput, ctx: TaskContext) -> _SampleCustomExitOutput:
        _ = self
        ctx.report_progress(ProgressEvent(phase="deploy", completed=50, total=100, message="deploying-step"))
        return _SampleCustomExitOutput(
            text=f"deployed:{req.target}:{req.mode}:{req.safe_plan}",
            code=req.exit_status,
        )

    @task(
        cli="nuke",
        name="nuke",
        summary="Permanently wipe alpha state",
        security=SecurityTier.CRITICAL,
        dispatch_mode=DispatchMode.COLD_ONLY,
    )
    def nuke(self, ctx: TaskContext) -> str:
        _ = (self, ctx)
        return "nuked"

    @task(
        cli="repl",
        name="repl",
        summary="Launch interactive human REPL",
        security=SecurityTier.SAFE,
        dispatch_mode=DispatchMode.COLD_ONLY,
        interactive_tty=True,
    )
    def repl(self, ctx: TaskContext) -> str:
        _ = (self, ctx)
        return "repl-session-ok"

    @on_migrate()
    def migrate_state(self, req: MigrationRequest, ctx: TaskContext) -> None:
        _ = (self, req, ctx)


def _init_minimal_workspace(ws_dir: Path) -> tuple[HostPath, HostPath]:
    host_dir = ws_dir / "host"
    yscb_root = host_dir / ".yscb"
    (yscb_root / ".modules" / "core").mkdir(parents=True, exist_ok=True)
    (yscb_root / ".cache").mkdir(parents=True, exist_ok=True)
    (yscb_root / "config" / "core").mkdir(parents=True, exist_ok=True)
    host_cfg = {
        "yscb_root": ".yscb",
        "default_provider": str(ws_dir / "provider"),
        "installed_modules": {
            "core": {
                "version": "2.0.0.0",
                "provider": str(ws_dir / "provider"),
                "installed_at": "2026-11-22T00:00:00Z",
            }
        },
    }
    (host_dir / "yscb.config.json").write_text(json.dumps(host_cfg, indent=2), encoding="utf-8")
    (yscb_root / ".modules" / "core" / "manifest.json").write_text(
        json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core"}),
        encoding="utf-8",
    )
    (yscb_root / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": "./"}, indent=2),
        encoding="utf-8",
    )
    return (HostPath(host_dir), HostPath(yscb_root))


def _verify_zero_import_help_and_parser(tmp_root: Path) -> None:
    log("[SURFACE-CLI] Verifying zero-import cold --help, sys.meta_path guard, 1.x HelpRenderer, DN-13 & Option.group...")
    host_hp, root_hp = _init_minimal_workspace(tmp_root / "ws_zero_import")
    alpha_idx = compile_tasks_index(_SampleCliModule)
    alpha_dir = root_hp.path / ".modules" / "alpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    (alpha_dir / "manifest.json").write_text(
        json.dumps({"id": "alpha", "version": "1.0.0.0", "description": "Alpha"}),
        encoding="utf-8",
    )
    (alpha_dir / "tasks.index.json").write_text(
        json.dumps(alpha_idx.to_json_dict(), indent=2),
        encoding="utf-8",
    )
    (alpha_dir / "module_entry.py").write_text(
        "import alpha_poison_dep\ndef create_module():\n    _ = alpha_poison_dep\n"
        "    raise RuntimeError('POISON_MODULE_ENTRY_IMPORTED')\n"
        "raise RuntimeError('TOP_LEVEL_IMPORT_FORBIDDEN_ON_COLD_HELP')\n",
        encoding="utf-8",
    )

    guard_finder = _ZeroImportGuardFinder(("alpha_poison_dep", "module_entry", "alpha"))
    sys.meta_path.insert(0, guard_finder)
    try:
        out_tty = _MockTtyOutput(is_tty=True)
        err_tty = _MockTtyOutput(is_tty=True)
        rc_root_help = cli_main(
            ["--help"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_tty,
            stderr_stream=err_tty,
            install_signal_guard=False,
        )
        check(rc_root_help == 0, f"Expected 0 on root --help, got {rc_root_help}")
        check("alpha (al)" in out_tty.getvalue(), "Root help missing installed module + alias")
        check((root_hp.path / ".cache" / "tasks.index.json").is_file(), "Expected .cache/tasks.index.json cache")

        out_mod_help = _MockTtyOutput(is_tty=True)
        rc_mod_help = cli_main(
            ["alpha", "-h"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_mod_help,
            stderr_stream=err_tty,
            install_signal_guard=False,
        )
        check(rc_mod_help == 0 and "deploy" in out_mod_help.getvalue())

        out_json_help = _MockTtyOutput(is_tty=True)
        rc_json_help = cli_main(
            ["alpha", "--help", "--json"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_json_help,
            stderr_stream=err_tty,
            install_signal_guard=False,
        )
        check(rc_json_help == 0)
        help_json_doc = json.loads(out_json_help.getvalue())
        check(help_json_doc["ok"] is True and "deploy" in help_json_doc["value"]["help"])

        out_leaf = _MockTtyOutput(is_tty=True)
        rc_leaf_help = cli_main(
            ["al", "dp", "-h"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_leaf,
            stderr_stream=err_tty,
            install_signal_guard=False,
        )
        leaf_txt = out_leaf.getvalue()
        check(rc_leaf_help == 0)
        check("Security : [GATED]" in leaf_txt, "Help missing Security badge")
        check("Dispatch : [HYBRID]" in leaf_txt, "Help missing Dispatch badge")
        check("[Group: strategy (Mutually Exclusive)]" in leaf_txt, "Help missing Option.group header")
        check("RECOMMENDED USAGE (Pros):" in leaf_txt, "Help missing Pros section")
        check("RESTRICTIONS & GATES (Cons):" in leaf_txt, "Help missing Cons section")

        out_agent = _MockTtyOutput(is_tty=True)
        _ = cli_main(
            ["alpha", "deploy", "-h"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_agent,
            stderr_stream=err_tty,
            install_signal_guard=False,
        )
        check(" : " in out_agent.getvalue(), "Compact AGENT HelpRenderer mode expected")

        for bad_args in (["alpha", "plan", "verfy"], ["alpha", "plan", "verfy", "--help"]):
            err_typo = _MockTtyOutput(is_tty=True)
            rc_typo = cli_main(
                bad_args,
                host_dir=host_hp,
                yscb_root=root_hp,
                env={"YSCB_TEST_SANDBOX": "1"},
                stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
                stdout_stream=_MockTtyOutput(is_tty=True),
                stderr_stream=err_typo,
                install_signal_guard=False,
            )
            check(rc_typo == 2, f"Expected exit code 2 on unknown subcommand {bad_args}, got {rc_typo}")
            check("Did you mean 'verify'?" in err_typo.getvalue(), f"Expected fuzzy suggestion for {bad_args}")

        err_dd = _MockTtyOutput(is_tty=True)
        out_dd = _MockTtyOutput(is_tty=True)
        rc_dd = cli_main(
            ["unknowncmd", "--", "--json"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=out_dd,
            stderr_stream=err_dd,
            install_signal_guard=False,
        )
        check(rc_dd == 2 and out_dd.getvalue() == "" and "Unknown command" in err_dd.getvalue())

        err_grp = _MockTtyOutput(is_tty=True)
        rc_grp = cli_main(
            ["alpha", "deploy", "prod", "--mode", "fast", "--safe-plan"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=_MockTtyOutput(is_tty=True),
            stderr_stream=err_grp,
            install_signal_guard=False,
        )
        check(rc_grp == 2 and "strategy" in err_grp.getvalue())

        rc_cold_gate = cli_main(
            ["alpha", "deploy", "prod", "--json"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
            stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
            stdout_stream=_MockTtyOutput(is_tty=True),
            stderr_stream=_MockTtyOutput(is_tty=True),
            install_signal_guard=False,
        )
        check(rc_cold_gate == 4, "ApprovalGate rejection must succeed with zero business module import")
        check(not guard_finder.violations, f"Unexpected module imports on cold CLI paths: {guard_finder.violations}")
    finally:
        if guard_finder in sys.meta_path:
            sys.meta_path.remove(guard_finder)

    cache = WorkspaceTasksIndexCache(root_hp)
    tree = build_cli_command_tree(cache.load_all())
    check("alpha" in tree.children and HelpRenderer(CallerMode.NON_TTY).compact_mode)


def _verify_caller_mode_and_security_matrix(tmp_root: Path) -> None:
    log("[SURFACE-CLI] Verifying 5-layer CallerMode, AI Dialect -> LocaleCatalog, 4x3 matrix & --json purity...")
    host_hp, root_hp = _init_minimal_workspace(tmp_root / "ws_security")
    _ = _package_core_release_zip(tmp_root / "ws_security" / "provider", "2.0.1.0", status="active")

    alpha_loc_dir = root_hp.path / ".modules" / "alpha" / "locales"
    alpha_loc_dir.mkdir(parents=True, exist_ok=True)
    (alpha_loc_dir / "nouns-claude.json").write_text(
        json.dumps({"plan.greeting": "claude-dialect-plan-ok"}),
        encoding="utf-8",
    )
    (alpha_loc_dir / "en.json").write_text(
        json.dumps({"plan.greeting": "human-en-plan-ok"}),
        encoding="utf-8",
    )

    pty_in = _MockTtyInput(is_tty=True, forbid_read=True)
    pty_out = _MockTtyOutput(is_tty=True)

    ag_env = detect_caller_environment(
        env={"ANTIGRAVITY_AGENT": "1"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(ag_env.mode == CallerMode.AGENT and ag_env.dialect == "nouns-antigravity")

    cc_env = detect_caller_environment(
        env={"claudecode": "1"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(cc_env.mode == CallerMode.AGENT and cc_env.dialect == "nouns-claude")

    falsy_agent_env = detect_caller_environment(
        env={"CLAUDECODE": "0", "GITHUB_ACTIONS": "false"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        falsy_agent_env.mode == CallerMode.HUMAN_TTY and falsy_agent_env.dialect is None,
        f"Falsy CI/AGENT env tokens must not trigger AGENT/CI: {falsy_agent_env}",
    )

    custom_env = detect_caller_environment(
        env={"CUSTOM_BOT_ID": "9"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
        extra_agent_env_prefixes=("custom_bot_",),
    )
    check(custom_env.mode == CallerMode.AGENT)

    spoof_env = detect_caller_environment(
        env={"YSCB_CALLER_MODE": "human"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=_MockTtyOutput(is_tty=False),
    )
    check(spoof_env.mode == CallerMode.NON_TTY, "Non-TTY must never allow YSCB_CALLER_MODE=human spoofing")

    ci_agent_env = detect_caller_environment(
        env={"GITHUB_ACTIONS": "true", "CLAUDECODE": "1"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        ci_agent_env.mode == CallerMode.AGENT and ci_agent_env.dialect == "nouns-claude",
        f"Layer 2 AGENT must beat Layer 3 CI: {ci_agent_env}",
    )

    ci_agy_env = detect_caller_environment(
        env={"CI": "true", "ANTIGRAVITY_AGENT": "1"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        ci_agy_env.mode == CallerMode.AGENT and ci_agy_env.dialect == "nouns-antigravity",
        f"Containerized CI=true + ANTIGRAVITY_AGENT=1 must resolve to AGENT: {ci_agy_env}",
    )

    ci_explicit_env = detect_caller_environment(
        env={"CI": "true", "ANTIGRAVITY_AGENT": "1", "YSCB_CALLER_MODE": "ci"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        ci_explicit_env.mode == CallerMode.CI_PIPELINE and ci_explicit_env.dialect is None,
        f"Explicit YSCB_CALLER_MODE=ci must override AGENT env: {ci_explicit_env}",
    )

    pty_agent_downgrade = detect_caller_environment(
        env={"CLAUDECODE": "1", "YSCB_CALLER_MODE": "human"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        pty_agent_downgrade.mode == CallerMode.AGENT and pty_agent_downgrade.dialect == "nouns-claude",
        f"Agent under PTY must not self-downgrade via YSCB_CALLER_MODE=human: {pty_agent_downgrade}",
    )

    pty_ci_downgrade = detect_caller_environment(
        env={"CI": "true", "YSCB_CALLER_MODE": "human"},
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        pty_ci_downgrade.mode == CallerMode.CI_PIPELINE and pty_ci_downgrade.dialect is None,
        f"CI under PTY must not self-downgrade via YSCB_CALLER_MODE=human: {pty_ci_downgrade}",
    )

    human_cfg_env = detect_caller_environment(
        env={
            "CLAUDE_CODE_USE_VERTEX": "1",
            "CODEX_HOME": "/tmp/codex-home",
            "AIDER_MODEL": "sonnet",
            "ANTIGRAVITY_THEME": "dark",
            "AGY_COLOR": "1",
        },
        stdin_stream=pty_in,
        stdout_stream=pty_out,
    )
    check(
        human_cfg_env.mode == CallerMode.HUMAN_TTY and human_cfg_env.dialect is None,
        f"Human developer config env keys must not false-positive as AGENT: {human_cfg_env}",
    )

    for sess_key, exp_dial in (
        ("CLAUDE_CODE_SESSION_ID", "nouns-claude"),
        ("CODEX_THREAD_ID", "nouns-codex"),
        ("AIDER_SESSION", None),
        ("ANTIGRAVITY_CONVERSATION_ID", "nouns-antigravity"),
        ("AGY_SESSION", "nouns-antigravity"),
    ):
        sess_res = detect_caller_environment(
            env={sess_key: "sess-1"},
            stdin_stream=pty_in,
            stdout_stream=pty_out,
        )
        check(
            sess_res.mode == CallerMode.AGENT and sess_res.dialect == exp_dial,
            f"Active agent session key {sess_key} must resolve to AGENT/{exp_dial}: {sess_res}",
        )

    alpha_mod = _SampleCliModule()
    alpha_idx = compile_tasks_index(alpha_mod)

    def _mem_kernel_factory(h_dir: HostPath, y_root: HostPath, force_cold: bool):
        return WorkspaceKernelFactory.create(
            h_dir,
            y_root,
            force_cold=force_cold,
            extra_modules=(alpha_mod,),
        )

    builtins = (*WorkspaceKernelFactory.builtin_cli_indices(), alpha_idx)

    out_dn13 = _MockTtyOutput(is_tty=True)
    rc_dn13 = cli_main(
        ["alpha", "plan", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "CLAUDECODE": "1"},
        stdin_stream=pty_in,
        stdout_stream=out_dn13,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_dn13 == 0 and "claude-dialect-plan-ok" in out_dn13.getvalue(), f"Dialect locale missing: {out_dn13.getvalue()}")
    check(pty_in.read_calls == 0)

    out_comma_loc = _MockTtyOutput(is_tty=True)
    rc_comma_loc = cli_main(
        ["alpha", "plan", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_LOCALE": "fr,en"},
        stdin_stream=pty_in,
        stdout_stream=out_comma_loc,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_comma_loc == 0 and "human-en-plan-ok" in out_comma_loc.getvalue(), f"Comma YSCB_LOCALE chain failed: {out_comma_loc.getvalue()}")

    out_gen_json = _MockTtyOutput(is_tty=True)
    rc_gen_json = cli_main(
        ["alpha", "plan", "verify", "--json", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=pty_in,
        stdout_stream=out_gen_json,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_gen_json == 0, f"Generic dict[str, str] --json failed: {out_gen_json.getvalue()}")
    gen_doc = json.loads(out_gen_json.getvalue())
    check(gen_doc["ok"] is True and gen_doc["value"] == {"status": "plan-verify-ok", "label": "auto-label"})

    rc_static_y = cli_main(
        ["alpha", "deploy", "prod", "-y", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_static_y == 2, "Static -y must be rejected")

    json_gate_out = _MockTtyOutput(is_tty=True)
    rc_gate1 = cli_main(
        ["alpha", "deploy", "prod", "--exit-status", "7", "--json", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
        stdin_stream=pty_in,
        stdout_stream=json_gate_out,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_gate1 == 4 and pty_in.read_calls == 0)
    gate_doc = json.loads(json_gate_out.getvalue())
    tok = str(gate_doc["error"]["message"]).split("--approve=", 1)[1].split()[0].strip("().")

    rc_mismatch = cli_main(
        ["alpha", "deploy", "staging", "--exit-status", "7", f"--approve={tok}", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_mismatch == 4, "Modified arguments must fail args_hash check")

    json_ok_out = _MockTtyOutput(is_tty=True)
    prog_err = _MockTtyOutput(is_tty=True)
    rc_approved = cli_main(
        ["alpha", "deploy", "prod", "--exit-status", "7", f"--approve={tok}", "--json", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_OFFLINE": "0", "YSCB_NO_UPDATE_CHECK": "0", "ANTIGRAVITY_SESSION": "1"},
        stdin_stream=pty_in,
        stdout_stream=json_ok_out,
        stderr_stream=prog_err,
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_approved == 7, f"Expected custom ExitCodeProvider 7 under --json, got {rc_approved}")
    pure_json = json.loads(json_ok_out.getvalue())
    check(pure_json["ok"] is True and pure_json["value"]["text"] == "deployed:prod:fast:False")
    check("deploying-step" in prog_err.getvalue() and "deploying-step" not in json_ok_out.getvalue())
    check("[Update Available]" not in prog_err.getvalue(), "--json must suppress 12h update check notice")
    perf_files = list((root_hp.path / ".cache" / "logs" / "perf").glob("*.jsonl"))
    daily_files = list((root_hp.path / ".cache" / "logs" / "daily").glob("*.jsonl"))
    check(len(perf_files) == 1, f"Expected CLI perf flight log under .cache/logs/perf/, got {perf_files}")
    check(len(daily_files) == 1, f"Expected CLI daily flight log under .cache/logs/daily/, got {daily_files}")
    daily_rows = [json.loads(ln) for ln in daily_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    check(
        any(r.get("kind") == "IN" and r.get("task_id") == "alpha.deploy" for r in daily_rows)
        and any(r.get("kind") == "OUT" and r.get("task_id") == "alpha.deploy" for r in daily_rows),
        f"Expected [IN] and [OUT] daily flight log records for alpha.deploy: {daily_rows}",
    )

    human_upd_err = _MockTtyOutput(is_tty=True)
    _ = cli_main(
        ["alpha", "plan", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_OFFLINE": "0", "YSCB_NO_UPDATE_CHECK": "0", "CLAUDECODE": "1"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=human_upd_err,
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check("[Update Available] core (2.0.0.0 -> 2.0.1.0)" in human_upd_err.getvalue(), f"Expected update notice on stderr: {human_upd_err.getvalue()}")

    rc_replay = cli_main(
        ["alpha", "deploy", "prod", "--exit-status", "7", f"--approve={tok}", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_replay == 4, "Replayed --approve token must fail (burn-on-use)")

    rc_ci_block = cli_main(
        ["alpha", "deploy", "prod", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "CI": "true"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_ci_block == 4, "CI_PIPELINE must block GATED task by default")

    rc_ci_ok = cli_main(
        ["alpha", "deploy", "prod", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "CI": "true", "YSCB_CI_APPROVE_GATED": "1"},
        stdin_stream=pty_in,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_ci_ok == 0, "CI_PIPELINE with YSCB_CI_APPROVE_GATED=1 must allow GATED task")

    gated_tty_err = _MockTtyOutput(is_tty=True)
    rc_gated_tty = cli_main(
        ["alpha", "deploy", "prod", "--exit-status", "5", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(lines=("y\n",), is_tty=True),
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=gated_tty_err,
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_gated_tty == 5 and "[GATED]" in gated_tty_err.getvalue())

    core_cfg_file = root_hp.path / "config" / "core" / "config.project.json"
    prev_core_cfg = core_cfg_file.read_text(encoding="utf-8")
    core_cfg_file.write_text(
        json.dumps({"project_root": "./", "security": {"allow_noninteractive_approve": False}}),
        encoding="utf-8",
    )
    try:
        err_ni = _MockTtyOutput(is_tty=True)
        rc_ni_blocked = cli_main(
            ["alpha", "deploy", "prod", "--cold"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env={"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
            stdin_stream=pty_in,
            stdout_stream=_MockTtyOutput(is_tty=True),
            stderr_stream=err_ni,
            kernel_factory=_mem_kernel_factory,
            builtin_indices=builtins,
            install_signal_guard=False,
        )
        check(
            rc_ni_blocked == 4 and "--approve=" not in err_ni.getvalue(),
            f"allow_noninteractive_approve=False must reject without issuing token: {err_ni.getvalue()}",
        )
    finally:
        core_cfg_file.write_text(prev_core_cfg, encoding="utf-8")

    store = ApprovalTokenStore(HostPath(root_hp.path / ".cache"), ttl_sec=5.0)
    exp_rec = store.issue_token(TaskId("alpha.deploy"), {"target": "prod"}, now_epoch=100.0)
    expired_caught = False
    try:
        _ = store.consume_token(exp_rec.token, TaskId("alpha.deploy"), {"target": "prod"}, now_epoch=110.0)
    except YscbError as exc:
        expired_caught = exc.detail.code == ErrorCode.SECURITY_GATED
    check(expired_caught, "Expired approval token must be rejected")

    for blocked_env in (
        {"YSCB_TEST_SANDBOX": "1", "ANTIGRAVITY_SESSION": "1"},
        {"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "non_tty"},
        {"YSCB_TEST_SANDBOX": "1", "CI": "true"},
    ):
        rc_crit = cli_main(
            ["alpha", "nuke", "--cold"],
            host_dir=host_hp,
            yscb_root=root_hp,
            env=blocked_env,
            stdin_stream=pty_in,
            stdout_stream=_MockTtyOutput(is_tty=True),
            stderr_stream=_MockTtyOutput(is_tty=True),
            kernel_factory=_mem_kernel_factory,
            builtin_indices=builtins,
            install_signal_guard=False,
        )
        check(rc_crit == 4, f"CRITICAL task must be hard-blocked in {blocked_env}")

    human_cancel = _MockTtyInput(lines=("",), is_tty=True)
    rc_crit_cancel = cli_main(
        ["alpha", "nuke", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=human_cancel,
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_crit_cancel == 4, "Empty Enter at CRITICAL prompt must cancel")

    human_ok = _MockTtyInput(lines=("CONFIRM\n",), is_tty=True)
    out_crit_ok = _MockTtyOutput(is_tty=True)
    err_crit_ok = _MockTtyOutput(is_tty=True)
    rc_crit_ok = cli_main(
        ["alpha", "nuke", "--json", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=human_ok,
        stdout_stream=out_crit_ok,
        stderr_stream=err_crit_ok,
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_crit_ok == 0 and json.loads(out_crit_ok.getvalue())["value"] == "nuked")
    check("[CRITICAL WARNING]" in err_crit_ok.getvalue(), "HUMAN_TTY --json must still write prompt to stderr")

    for repl_env, repl_args in (
        ({"YSCB_TEST_SANDBOX": "1", "CLAUDECODE": "1"}, ["alpha", "repl", "--json", "--cold"]),
        ({"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "non_tty"}, ["alpha", "repl", "--json", "--cold"]),
        ({"YSCB_TEST_SANDBOX": "1", "CI": "true"}, ["alpha", "repl", "--json", "--cold"]),
        ({"YSCB_TEST_SANDBOX": "1"}, ["alpha", "repl", "--json", "--cold"]),
    ):
        repl_out = _MockTtyOutput(is_tty=True)
        rc_repl_blocked = cli_main(
            repl_args,
            host_dir=host_hp,
            yscb_root=root_hp,
            env=repl_env,
            stdin_stream=pty_in,
            stdout_stream=repl_out,
            stderr_stream=_MockTtyOutput(is_tty=True),
            kernel_factory=_mem_kernel_factory,
            builtin_indices=builtins,
            install_signal_guard=False,
        )
        check(rc_repl_blocked != 0 and pty_in.read_calls == 0)
        repl_err_doc = json.loads(repl_out.getvalue())
        check(
            repl_err_doc["ok"] is False and repl_err_doc["error"]["code"] == ErrorCode.TTY_REQUIRED.value,
            f"Expected TTY_REQUIRED for interactive_tty under {repl_env} {repl_args}, got {repl_err_doc}",
        )

    repl_human_out = _MockTtyOutput(is_tty=True)
    rc_repl_human = cli_main(
        ["alpha", "repl", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True),
        stdout_stream=repl_human_out,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=_mem_kernel_factory,
        builtin_indices=builtins,
        install_signal_guard=False,
    )
    check(rc_repl_human == 0 and "repl-session-ok" in repl_human_out.getvalue())


def _package_core_release_zip(provider_root: Path, version: str, *, status: str = "active") -> str:
    core_prov_dir = provider_root / "core"
    core_prov_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{version}.zip"
    zip_path = core_prov_dir / archive_name
    core_idx_dict = compile_tasks_index(CoreSystemModule).to_json_dict()
    mf_dict = {
        "id": "core",
        "version": version,
        "description": "YS-Codebase Core Microkernel",
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(mf_dict, indent=2))
        zf.writestr("tasks.index.json", json.dumps(core_idx_dict, indent=2))
        zf.writestr(
            "configurable/config.project.json.tmpl",
            json.dumps({"project_root": "./", "locale": ["zh", "en"], "idle_timeout_sec": 300.0}, indent=2),
        )
        src_core_pkg = CORE_SRC_ROOT / "core"
        for py_f in sorted(src_core_pkg.rglob("*.py")):
            if "__pycache__" in py_f.parts:
                continue
            rel = py_f.relative_to(CORE_SRC_ROOT).as_posix()
            zf.write(py_f, rel)

    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (core_prov_dir / f"{archive_name}.sha256").write_text(f"{sha}  {archive_name}\n", encoding="utf-8")

    idx_path = core_prov_dir / "index.json"
    existing_idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.is_file() else {"module_id": "core", "versions": [], "releases": {}}
    if version not in existing_idx["versions"]:
        existing_idx["versions"].append(version)
    existing_idx["releases"][version] = {
        "version": version,
        "status": status,
        "urgency": "recommended",
        "yanked": False,
        "sha256": sha,
        "filename": archive_name,
        "summary": f"Core release {version}",
    }
    idx_path.write_text(json.dumps(existing_idx, indent=2), encoding="utf-8")
    return sha


def _package_demo_module_zip(
    provider_root: Path,
    version: str,
    *,
    fail_migration: bool = False,
) -> None:
    mod_prov_dir = provider_root / "demo"
    mod_prov_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{version}.zip"
    zip_path = mod_prov_dir / archive_name

    mf_dict = {
        "id": "demo",
        "version": version,
        "description": f"Demo business module v{version}",
        "dependencies": {"core": ">=2.0.0"},
    }
    cfg_schema = {
        "type": "object",
        "properties": {
            "greeting": {"type": "string", "default": "hello"},
        },
        "additionalProperties": False,
    }
    core_contrib = {
        "locales": {
            "definition": "locales/definition.json",
            "en": "locales/en.json",
            "nouns-claude": "locales/nouns-claude.json",
        }
    }
    tasks_idx = {
        "schema_version": 2,
        "module_id": "demo",
        "module_aliases": ["dm"],
        "description": f"Demo business module v{version}",
        "tasks": [
            {
                "task_id": "demo.info",
                "command_path": ["info"],
                "aliases": [],
                "summary": "Inspect demo state",
                "usage_pros": [],
                "usage_cons": [],
                "exposure": "cli_and_sdk",
                "security_tier": "safe",
                "dispatch_mode": "hybrid",
                "interactive_tty": False,
                "args": [],
                "options": [],
                "subscriptions": [],
                "periodic": None,
                "custom_render": False,
                "custom_exit_code": False,
            },
            {
                "task_id": "demo.banner",
                "command_path": ["banner"],
                "aliases": [],
                "summary": "Render custom banner",
                "usage_pros": [],
                "usage_cons": [],
                "exposure": "cli_and_sdk",
                "security_tier": "safe",
                "dispatch_mode": "hybrid",
                "interactive_tty": False,
                "args": [],
                "options": [],
                "subscriptions": [],
                "periodic": None,
                "custom_render": True,
                "custom_exit_code": True,
            },
            {
                "task_id": "demo.reg_sp",
                "command_path": [],
                "aliases": [],
                "summary": "Register dynamic space",
                "usage_pros": [],
                "usage_cons": [],
                "exposure": "sdk_only",
                "security_tier": "safe",
                "dispatch_mode": "hybrid",
                "interactive_tty": False,
                "args": [],
                "options": [],
                "subscriptions": [],
                "periodic": None,
            },
            {
                "task_id": "demo.yscb_on_migrate",
                "command_path": [],
                "aliases": [],
                "summary": "",
                "usage_pros": [],
                "usage_cons": [],
                "exposure": "internal_trigger",
                "security_tier": "safe",
                "dispatch_mode": "hybrid",
                "interactive_tty": False,
                "args": [],
                "options": [],
                "subscriptions": [],
                "periodic": None,
            },
        ],
    }

    fail_flag_lit = "1" if fail_migration else "0"
    base_tpl = (
        "from dataclasses import dataclass\n"
        "from core.surface.sdk import ExitCodeProvider, HumanRenderable, MigrationRequest, Module, SemanticUri, SpaceId, SpaceSpec, TaskContext, on_migrate, task\n"
        "from core.surface.sdk.advanced import ModuleId\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class DemoBannerOut(HumanRenderable, ExitCodeProvider):\n"
        "    headline: str\n"
        "    status_code: int\n"
        "    def render_text(self) -> str:\n"
        "        return f'BANNER::{self.headline}'\n"
        "    def exit_code(self) -> int:\n"
        "        return self.status_code\n\n"
        "class DemoModule(Module):\n"
        "    id = 'demo'\n"
        "    aliases = ('dm',)\n"
        "    description = 'Demo module __VER__'\n\n"
        "    @task(cli='info', name='info', summary='Inspect demo state')\n"
        "    def info(self, ctx: TaskContext) -> dict[str, str]:\n"
        "        _ = self\n"
        "        uri = SemanticUri('storage.local', '@/mig.json')\n"
        "        mig = 'none'\n"
        "        if ctx.vfs.exists(uri):\n"
        "            doc = ctx.vfs.read_json(uri)\n"
        "            if isinstance(doc, dict):\n"
        "                mig = str(doc.get('from')) + '->' + str(doc.get('to'))\n"
        "        greet = ctx.locale.translate('demo.msg', caller_module=ModuleId('demo'))\n"
        "        return {'version': '__VER__', 'migrated': mig, 'msg': greet}\n\n"
        "    @task(cli='banner', name='banner', summary='Render custom banner')\n"
        "    def banner(self, ctx: TaskContext) -> DemoBannerOut:\n"
        "        _ = (self, ctx)\n"
        "        return DemoBannerOut(headline='v__VER__', status_code=9)\n\n"
        "    @task(name='reg_sp', summary='Register dynamic space')\n"
        "    def reg_sp(self, ctx: TaskContext) -> bool:\n"
        "        _ = self\n"
        "        sp = SpaceSpec(space_id=SpaceId('demo', 'dyn_docs'), entries=(SemanticUri('project', ''),), include=('*.py',))\n"
        "        out = ctx.call('core.space.set_dynamic', {'owner': 'demo', 'name': 'dyn_docs', 'spec': sp}, output_type=bool)\n"
        "        return bool(out.ok and out.value is True)\n\n"
        "    @on_migrate()\n"
        "    def handle_migrate(self, req: MigrationRequest, ctx: TaskContext) -> None:\n"
        "        _ = self\n"
        "        if '__FAIL__' == '1':\n"
        "            raise RuntimeError('SIMULATED_MIGRATION_CRASH')\n"
        "        uri = SemanticUri('storage.local', '@/mig.json')\n"
        "        ctx.vfs.write_json(uri, {'from': str(req.old_version), 'to': str(req.new_version)})\n\n"
        "def create_module():\n"
        "    return DemoModule().to_yscb_module()\n"
    )
    entry_code = base_tpl.replace("__VER__", version).replace("__FAIL__", fail_flag_lit)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(mf_dict, indent=2))
        zf.writestr("config.schema.json", json.dumps(cfg_schema, indent=2))
        zf.writestr("contributes/core.json", json.dumps(core_contrib, indent=2))
        zf.writestr("locales/definition.json", json.dumps({"demo.msg": "baseline-en"}))
        zf.writestr("locales/en.json", json.dumps({"demo.msg": "en-msg"}))
        zf.writestr("locales/nouns-claude.json", json.dumps({"demo.msg": "claude-msg"}))
        zf.writestr("tasks.index.json", json.dumps(tasks_idx, indent=2))
        zf.writestr("module_entry.py", entry_code)
        zf.writestr("configurable/config.project.json.tmpl", json.dumps({"greeting": "hello"}, indent=2))

    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    idx_path = mod_prov_dir / "index.json"
    existing_idx = (
        json.loads(idx_path.read_text(encoding="utf-8"))
        if idx_path.is_file()
        else {"module_id": "demo", "versions": [], "releases": {}}
    )
    if version not in existing_idx["versions"]:
        existing_idx["versions"].append(version)
    existing_idx["releases"][version] = {
        "version": version,
        "status": "active",
        "urgency": "recommended",
        "yanked": False,
        "sha256": sha,
        "filename": archive_name,
        "summary": f"Demo release {version}",
    }
    idx_path.write_text(json.dumps(existing_idx, indent=2), encoding="utf-8")


def _build_sanitized_subproc_env(
    *,
    caller_mode: Optional[str] = "agent",
    extra_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    env = dict(os.environ)
    ci_exact_keys = frozenset(
        {
            "CI",
            "GITHUB_ACTIONS",
            "GITLAB_CI",
            "TF_BUILD",
            "BUILDKITE",
            "CIRCLECI",
            "TRAVIS",
            "JENKINS_URL",
            "BITBUCKET_BUILD_NUMBER",
        }
    )
    for k in list(env.keys()):
        up_k = k.upper()
        if up_k in ci_exact_keys or up_k.startswith(
            (
                "ANTIGRAVITY_",
                "AGY_",
                "CLAUDECODE",
                "CLAUDE_CODE_",
                "CODEX_",
                "GEMINI_CLI",
                "CURSOR_",
                "WINDSURF_",
                "AIDER_",
                "OPENCODE",
                "YSCB_",
                "_YSCB_",
            )
        ):
            env.pop(k, None)
    env["YSCB_OFFLINE"] = "0"
    env["YSCB_NO_UPDATE_CHECK"] = "1"
    if caller_mode is not None:
        env["YSCB_CALLER_MODE"] = caller_mode
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env is not None:
        env.update(extra_env)
    return env


def _terminate_and_close_subproc(proc: subprocess.Popen[str]) -> None:
    try:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)
    except (OSError, subprocess.SubprocessError):
        pass
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _readline_subproc_with_timeout(proc: subprocess.Popen[str], timeout_sec: float = 15.0) -> str:
    if proc.stdout is None:
        return ""
    out_box: list[str] = []
    err_box: list[BaseException] = []

    def _reader() -> None:
        try:
            if proc.stdout is not None:
                out_box.append(proc.stdout.readline())
        except BaseException as exc:
            err_box.append(exc)

    thr = threading.Thread(target=_reader, daemon=True)
    thr.start()
    thr.join(timeout=timeout_sec)
    if thr.is_alive():
        proc.kill()
        proc.wait(timeout=5.0)
        raise AssertionError(f"Timed out after {timeout_sec}s waiting for foreground daemon ready line")
    if err_box:
        raise err_box[0]
    return out_box[0] if out_box else ""


def _run_yscb_subproc(
    host_dir: Path,
    args: list[str],
    *,
    extra_env: Optional[dict[str, str]] = None,
    stdin_text: str = "",
    script_override: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    script_src = CORE_V2_ROOT / "yscb.py"
    if script_override is not None:
        exec_script = script_override
    else:
        local_script = host_dir / "yscb.py"
        if not local_script.is_file():
            shutil.copy2(script_src, local_script)
        exec_script = local_script

    env = _build_sanitized_subproc_env(caller_mode="agent", extra_env=extra_env)
    win_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-W", "error::ResourceWarning", str(exec_script), *args],
        cwd=str(host_dir),
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
        creationflags=win_flags,
    )


def _run_gated_cli_two_step(host_dir: Path, cmd_args: list[str]) -> dict[str, object]:
    cp1 = _run_yscb_subproc(host_dir, [*cmd_args, "--json"])
    check(cp1.returncode == 4, f"Expected GATED exit 4 on step 1 for {cmd_args}, got {cp1.returncode}: {cp1.stderr}")
    doc1 = json.loads(cp1.stdout)
    msg = str(doc1["error"]["message"])
    tok = msg.split("--approve=", 1)[1].split()[0].strip("().")
    cp2 = _run_yscb_subproc(host_dir, [*cmd_args, f"--approve={tok}", "--json"])
    check(cp2.returncode == 0, f"Expected exit 0 on step 2 for {cmd_args}, got {cp2.returncode}: {cp2.stdout} / {cp2.stderr}")
    out_doc = json.loads(cp2.stdout)
    check(isinstance(out_doc, dict) and out_doc.get("ok") is True)
    return out_doc


def _run_gated_cli_two_step_expect_fail(
    host_dir: Path,
    cmd_args: list[str],
    *,
    expected_rc: int,
    expected_code: str,
) -> dict[str, object]:
    cp1 = _run_yscb_subproc(host_dir, [*cmd_args, "--json"])
    check(cp1.returncode == 4, f"Expected GATED exit 4 on step 1 for {cmd_args}, got {cp1.returncode}: {cp1.stderr}")
    doc1 = json.loads(cp1.stdout)
    msg = str(doc1["error"]["message"])
    tok = msg.split("--approve=", 1)[1].split()[0].strip("().")
    cp2 = _run_yscb_subproc(host_dir, [*cmd_args, f"--approve={tok}", "--json"])
    check(
        cp2.returncode == expected_rc,
        f"Expected exit {expected_rc} on step 2 for {cmd_args}, got {cp2.returncode}: {cp2.stdout} / {cp2.stderr}",
    )
    out_doc = json.loads(cp2.stdout)
    check(isinstance(out_doc, dict) and out_doc.get("ok") is False and out_doc["error"]["code"] == expected_code)
    return out_doc


def _verify_yscb_e2e_lifecycle(tmp_root: Path) -> None:
    log("[SURFACE-CLI] Verifying yscb.py init -> pruned core restore -> install -> daemon -> @on_migrate -> rollback E2E...")
    e2e_root = tmp_root / "e2e_full"
    prov_dir = e2e_root / "provider"
    host_dir = e2e_root / "project"
    host_dir.mkdir(parents=True, exist_ok=True)

    _ = _package_core_release_zip(prov_dir, "2.0.0.0", status="pruned")
    _ = _package_core_release_zip(prov_dir, "2.0.0.1", status="active")
    _package_demo_module_zip(prov_dir, "1.0.0.0")
    _package_demo_module_zip(prov_dir, "1.1.0.0")

    cp_help_init = _run_yscb_subproc(host_dir, ["--help", "init"])
    check(cp_help_init.returncode == 0 and "yscb init" in cp_help_init.stdout)
    cp_help_init_json = _run_yscb_subproc(host_dir, ["init", "--help", "--json"])
    check(cp_help_init_json.returncode == 0)
    decoded_help_outcome = DataclassCodec.decode(TaskOutcome, json.loads(cp_help_init_json.stdout))
    check(isinstance(decoded_help_outcome, TaskOutcome) and decoded_help_outcome.ok)

    cp_init = _run_yscb_subproc(host_dir, ["init", f"--provider={prov_dir}"])
    check(cp_init.returncode == 0, f"yscb init failed: {cp_init.stderr}")
    yscb_root = host_dir / ".yscb"
    check((yscb_root / ".modules" / "core" / "manifest.json").is_file())
    check(not (yscb_root / ".modules" / "core" / "configurable").exists(), "*.tmpl dir must be stripped")
    check((yscb_root / "config" / "core" / "config.project.json").is_file(), "core default config.project.json must be materialized")

    shutil.rmtree(yscb_root / ".modules" / "core")
    cfg_doc = json.loads((host_dir / "yscb.config.json").read_text(encoding="utf-8"))
    cfg_doc["installed_modules"]["core"]["version"] = "2.0.0.0"
    (host_dir / "yscb.config.json").write_text(json.dumps(cfg_doc, indent=2), encoding="utf-8")

    cp_status = _run_yscb_subproc(host_dir, ["status", "--json", "--cold"])
    check(cp_status.returncode == 0, f"Deterministic core auto-restore failed: out={cp_status.stdout} err={cp_status.stderr}")
    restored_cfg = json.loads((host_dir / "yscb.config.json").read_text(encoding="utf-8"))
    check(
        restored_cfg["installed_modules"]["core"]["version"] == "2.0.0.1",
        "Expected pruned 2.0.0.0 to deterministically advance to same-triplet active 2.0.0.1",
    )

    broken_host = e2e_root / "broken_host"
    broken_host.mkdir(parents=True, exist_ok=True)
    (broken_host / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": ".yscb",
                "default_provider": str(e2e_root / "nonexistent_provider"),
                "installed_modules": {
                    "core": {"version": "2.0.0.0", "provider": str(e2e_root / "nonexistent_provider")}
                },
            }
        ),
        encoding="utf-8",
    )
    cp_broken = _run_yscb_subproc(broken_host, ["status"])
    check(cp_broken.returncode != 0 and "init --fix" in cp_broken.stderr, "Must refuse blind fallback on missing provider")

    upd_src = e2e_root / "remote_launcher" / "yscb.py"
    upd_src.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CORE_V2_ROOT / "yscb.py", upd_src)
    upd_sha = hashlib.sha256(upd_src.read_bytes()).hexdigest()
    (e2e_root / "remote_launcher" / "yscb.py.sha256").write_text(f"{upd_sha}  yscb.py\n", encoding="utf-8")
    local_launcher = host_dir / "yscb.py"
    if not local_launcher.is_file():
        shutil.copy2(CORE_V2_ROOT / "yscb.py", local_launcher)
    if os.name != "nt":
        os.chmod(local_launcher, 0o755)
    cp_self_upd = _run_yscb_subproc(host_dir, ["self-update", "--allow-bootstrap-mutation", f"--url={upd_src}"])
    check(cp_self_upd.returncode == 0, f"self-update failed: {cp_self_upd.stderr}")
    if os.name != "nt":
        check((stat.S_IMODE(os.lstat(local_launcher).st_mode) & stat.S_IXUSR) != 0, "self-update must preserve POSIX +x bit")

    _ = _run_gated_cli_two_step(host_dir, ["install", "demo@1.0.0.0", "--cold"])
    cp_demo_v1 = _run_yscb_subproc(host_dir, ["dm", "info", "--json", "--cold"])
    check(cp_demo_v1.returncode == 0, f"demo info failed: out={cp_demo_v1.stdout} err={cp_demo_v1.stderr}")
    v1_val = json.loads(cp_demo_v1.stdout)["value"]
    check(v1_val == {"version": "1.0.0.0", "migrated": "none", "msg": "en-msg"}, f"Unexpected v1 info: {v1_val}")

    cp_banner_txt = _run_yscb_subproc(host_dir, ["demo", "banner", "--cold"])
    check(cp_banner_txt.returncode == 9 and "BANNER::v1.0.0.0" in cp_banner_txt.stdout, f"Installed module HumanRenderable/ExitCodeProvider failed: rc={cp_banner_txt.returncode}, out={cp_banner_txt.stdout}")

    cp_banner_json = _run_yscb_subproc(host_dir, ["demo", "banner", "--json", "--cold"])
    check(cp_banner_json.returncode == 9 and json.loads(cp_banner_json.stdout)["value"]["headline"] == "v1.0.0.0")

    cp_clist = _run_yscb_subproc(host_dir, ["contributes", "list", "core", "--json", "--cold"])
    check(cp_clist.returncode == 0 and set(json.loads(cp_clist.stdout)["value"]["data"]["core"]) == {"locales", "spaces", "uri_schemes"})
    cp_ccheck_ok = _run_yscb_subproc(host_dir, ["contributes", "check", "--json", "--cold"])
    check(cp_ccheck_ok.returncode == 0 and json.loads(cp_ccheck_ok.stdout)["value"]["data"]["ok"] is True)
    cp_cinsp = _run_yscb_subproc(host_dir, ["contributes", "inspect", "core", "--provenance", "--json", "--cold"])
    check(cp_cinsp.returncode == 0 and "provenance" in json.loads(cp_cinsp.stdout)["value"]["data"])

    bad_contrib = yscb_root / "config" / "core" / "contribute.json"
    bad_contrib.write_text(json.dumps({"unknown_point": 123}), encoding="utf-8")
    try:
        cp_ccheck_fail = _run_yscb_subproc(host_dir, ["contributes", "check", "--json", "--cold"])
        check(cp_ccheck_fail.returncode == 1, f"Expected non-zero exit code 1 on failing contributes check, got {cp_ccheck_fail.returncode}")
    finally:
        bad_contrib.unlink()

    ext_launcher = e2e_root / "external_bin" / "yscb.py"
    ext_launcher.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CORE_V2_ROOT / "yscb.py", ext_launcher)

    try:
        cp_dstart = _run_yscb_subproc(
            host_dir,
            [f"--host-dir={host_dir}", "daemon", "start", "-d", "--json"],
            extra_env={"_YSCB_TEST_SANDBOX": "0", "CLAUDECODE": "1"},
            script_override=ext_launcher,
        )
        check(
            cp_dstart.returncode == 0,
            f"daemon start -d via external launcher failed: rc={cp_dstart.returncode} out={cp_dstart.stdout} err={cp_dstart.stderr}",
        )
        cp_dstat = _run_yscb_subproc(host_dir, ["daemon", "status", "--json"])
        dstat_val = json.loads(cp_dstat.stdout)["value"]
        check(dstat_val["data"]["online"] is True, f"Expected daemon online: {dstat_val}")
        rem_ttl = dstat_val["data"]["status"]["status"]["idle_ttl_remaining_sec"]
        check(isinstance(rem_ttl, (int, float)) and rem_ttl > 0.0, f"Background daemon must have active Idle TTL > 0, got {rem_ttl}")

        cp_hot_claude = _run_yscb_subproc(
            host_dir,
            ["demo", "info", "--json"],
            extra_env={"YSCB_CALLER_MODE": "", "CLAUDECODE": "1"},
        )
        hot_claude_doc = json.loads(cp_hot_claude.stdout)
        check(
            hot_claude_doc["ok"] is True
            and hot_claude_doc["executed_hot"] is True
            and hot_claude_doc["value"]["msg"] == "claude-msg",
            f"Expected hot daemon execution to honor caller CLAUDECODE dialect: {hot_claude_doc}",
        )

        cp_hot_en = _run_yscb_subproc(host_dir, ["demo", "info", "--json"])
        hot_en_doc = json.loads(cp_hot_en.stdout)
        check(
            hot_en_doc["ok"] is True
            and hot_en_doc["executed_hot"] is True
            and hot_en_doc["value"]["msg"] == "en-msg",
            f"Expected subsequent non-Claude hot call to resolve en-msg: {hot_en_doc}",
        )

        alt_proj = host_dir / "subproject"
        alt_proj.mkdir(parents=True, exist_ok=True)
        cp_cfg_set_pr = _run_yscb_subproc(host_dir, ["config", "set", "core", "project_root", '"subproject"', "--json"])
        check(
            cp_cfg_set_pr.returncode == 0,
            f"config set core project_root failed: rc={cp_cfg_set_pr.returncode} out={cp_cfg_set_pr.stdout} err={cp_cfg_set_pr.stderr}",
        )
        cp_uri_proj = _run_yscb_subproc(host_dir, ["uri", "resolve", "project://", "--json"])
        check(Path(json.loads(cp_uri_proj.stdout)["value"]["data"]["path"]).resolve() == alt_proj.resolve(), "UriMountTable must hot-reload after config set core project_root")
        check(_run_yscb_subproc(host_dir, ["config", "unset", "core", "project_root", "--json"]).returncode == 0)

        cp_undef_proj = _run_yscb_subproc(host_dir, ["uri", "resolve", "project://", "--json"])
        check(cp_undef_proj.returncode != 0 and json.loads(cp_undef_proj.stdout)["error"]["code"] == ErrorCode.URI_UNDEFINED.value, f"Expected URI_UNDEFINED after unsetting project_root: {cp_undef_proj.stdout}")
        cp_uri_chk_fail = _run_yscb_subproc(host_dir, ["uri", "check", "--json"])
        check(cp_uri_chk_fail.returncode == 1, f"Expected uri check exit code 1 when project:// is undefined, got {cp_uri_chk_fail.returncode}")
        check(_run_yscb_subproc(host_dir, ["config", "set", "core", "project_root", '"./"', "--json"]).returncode == 0)

        cp_bad_cfg = _run_yscb_subproc(host_dir, ["config", "set", "demo", "greeting", "123", "--json"])
        check(
            cp_bad_cfg.returncode != 0
            and json.loads(cp_bad_cfg.stdout)["error"]["code"] == ErrorCode.CONFIG_INVALID.value,
            f"Expected config.schema.json to reject integer greeting: {cp_bad_cfg.stdout}",
        )

        check(_run_yscb_subproc(host_dir, ["config", "set", "demo", "greeting", '"hi"', "--json"]).returncode == 0)
        cp_cget = _run_yscb_subproc(host_dir, ["config", "get", "demo", "greeting", "--json"])
        check(json.loads(cp_cget.stdout)["value"]["data"]["value"] == "hi")
        check(_run_yscb_subproc(host_dir, ["uri", "check", "--json"]).returncode == 0)
        check(_run_yscb_subproc(host_dir, ["gitignore", "sync", "--json"]).returncode == 0)
        check((host_dir / ".gitignore").is_file(), "Expected project://.gitignore materialized")
        check(_run_yscb_subproc(host_dir, ["fs", "scan", "core/workspace", "--json"]).returncode == 0)

        _ = _run_gated_cli_two_step(host_dir, ["update", "demo"])
        cp_demo_v2 = _run_yscb_subproc(host_dir, ["demo", "info", "--json"])
        v2_doc = json.loads(cp_demo_v2.stdout)
        check(v2_doc["executed_hot"] is True, f"Expected online daemon to resume and execute hot after demo update: {v2_doc}")
        check(
            v2_doc["value"] == {"version": "1.1.0.0", "migrated": "1.0.0.0->1.1.0.0", "msg": "en-msg"},
            f"Expected @on_migrate 1.0.0.0->1.1.0.0, got {v2_doc['value']}",
        )

        _package_demo_module_zip(prov_dir, "1.2.0.0", fail_migration=True)
        cp_u1 = _run_yscb_subproc(host_dir, ["update", "demo", "--json"])
        tok_fail = str(json.loads(cp_u1.stdout)["error"]["message"]).split("--approve=", 1)[1].split()[0].strip("().")
        cp_u2 = _run_yscb_subproc(host_dir, ["update", "demo", f"--approve={tok_fail}", "--json"])
        check(cp_u2.returncode != 0, "Expected broken @on_migrate upgrade to fail")

        cp_after_rb = _run_yscb_subproc(host_dir, ["demo", "info", "--json"])
        after_rb_doc = json.loads(cp_after_rb.stdout)
        check(
            after_rb_doc["executed_hot"] is True
            and after_rb_doc["value"]["version"] == "1.1.0.0"
            and after_rb_doc["value"]["migrated"] == "1.0.0.0->1.1.0.0",
            f"Expected exact pre-transaction rollback to 1.1.0.0 and hot daemon sync after failed migration, got {after_rb_doc}",
        )
        cp_cget_after_rb = _run_yscb_subproc(host_dir, ["config", "get", "demo", "greeting", "--json"])
        check(
            json.loads(cp_cget_after_rb.stdout)["value"]["data"]["value"] == "hi",
            "Migration rollback within 60s coalesce window must preserve prior committed config/storage state",
        )

        with YscbClient.connect(HostPath(yscb_root)) as sdk_client:
            sdk_core_hot = sdk_client.call("core.status")
            check(sdk_core_hot.ok and sdk_core_hot.executed_hot, f"Expected YscbClient.connect to dispatch core.status hot: {sdk_core_hot}")
            sdk_info = sdk_client.call("demo.info", output_type=dict[str, str])
            check(
                sdk_info.ok
                and sdk_info.executed_hot
                and sdk_info.value is not None
                and sdk_info.value["version"] == "1.1.0.0"
                and sdk_info.value["msg"] == "en-msg",
                f"Expected shared background daemon to remain caller-neutral ('en-msg'), got {sdk_info}",
            )
            sdk_dyn = sdk_client.call("demo.reg_sp", output_type=bool)
            check(sdk_dyn.ok and sdk_dyn.value is True)

        standalone_hot_code = (
            "import json, sys\n"
            "from core.surface.sdk import HostPath\n"
        "from core.surface.sdk.advanced import YscbClient\n"
            "assert 'core.surface.bootstrap' not in sys.modules\n"
            "ws = HostPath(sys.argv[1])\n"
            "with YscbClient.connect(ws) as c:\n"
            "    hot_r = c.call('core.status')\n"
            "    cold_r = c.call('core.status', force_cold=True)\n"
            "sys.stdout.write(json.dumps({'hot_ok': hot_r.ok, 'hot_exec': hot_r.executed_hot, 'cold_ok': cold_r.ok, 'cold_code': cold_r.error.code.value if cold_r.error else ''}))\n"
        )
        cp_standalone_sdk = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-W",
                "error::ResourceWarning",
                "-c",
                standalone_hot_code,
                str(yscb_root),
            ],
            cwd=str(host_dir),
            env=_build_sanitized_subproc_env(
                caller_mode="agent",
                extra_env={"PYTHONPATH": str(CORE_SRC_ROOT)},
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15.0,
            check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        check(cp_standalone_sdk.returncode == 0, f"Standalone SDK subprocess failed: {cp_standalone_sdk.stderr}")
        st_sdk_doc = json.loads(cp_standalone_sdk.stdout)
        check(
            st_sdk_doc["hot_ok"] is True
            and st_sdk_doc["hot_exec"] is True
            and st_sdk_doc["cold_ok"] is False
            and st_sdk_doc["cold_code"] == ErrorCode.CONFIG_INVALID.value,
            f"Expected standalone SDK without bootstrap import to route hot RPC and return CONFIG_INVALID (never SECURITY_GATED) on cold core.*: {st_sdk_doc}",
        )

        cp_hot_spaces_before = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json"])
        hot_sp_list = json.loads(cp_hot_spaces_before.stdout)["value"]["data"]["spaces"]
        check(
            any(sp["space_id"] == "demo/dyn_docs" for sp in hot_sp_list),
            f"Expected online daemon to reflect demo/dyn_docs space: {hot_sp_list}",
        )

        cp_dreload = _run_yscb_subproc(host_dir, ["daemon", "reload", "--json"])
        check(cp_dreload.returncode == 0 and json.loads(cp_dreload.stdout)["value"]["data"]["reloaded"] is True)

        # Verify online daemon core handoff via 'daemon reload core' spawns a fresh successor boot_id
        ep_json_path = yscb_root / ".cache" / "daemon" / "daemon.json"
        pre_ho_boot = str(json.loads(ep_json_path.read_text(encoding="utf-8"))["boot_id"])
        cp_dreload_core = _run_yscb_subproc(host_dir, ["daemon", "reload", "core", "--json"])
        check(
            cp_dreload_core.returncode == 0 and json.loads(cp_dreload_core.stdout)["value"]["data"]["handoff"] is True,
            f"Expected daemon reload core to initiate core handoff: {cp_dreload_core.stdout}",
        )
        ho_deadline = time.monotonic() + 8.0
        post_ho_boot = ""
        while time.monotonic() < ho_deadline:
            cp_st_post = _run_yscb_subproc(host_dir, ["daemon", "status", "--json"])
            if cp_st_post.returncode == 0 and ep_json_path.is_file():
                post_data = json.loads(cp_st_post.stdout)["value"]["data"]
                if post_data.get("online") is True:
                    try:
                        cand_boot = str(json.loads(ep_json_path.read_text(encoding="utf-8"))["boot_id"])
                    except (OSError, ValueError, KeyError):
                        cand_boot = ""
                    if cand_boot and cand_boot != pre_ho_boot:
                        post_ho_boot = cand_boot
                        break
            time.sleep(0.05)
        check(
            bool(post_ho_boot) and post_ho_boot != pre_ho_boot,
            f"Expected online daemon core handoff to transition to a new boot_id (was {pre_ho_boot!r}, got {post_ho_boot!r})",
        )

        _ = _run_gated_cli_two_step(host_dir, ["remove", "demo"])
        cp_hot_spaces_after = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json"])
        hot_sp_after = json.loads(cp_hot_spaces_after.stdout)["value"]["data"]["spaces"]
        check(
            hot_sp_after == [],
            f"Expected online warm daemon SpaceRegistry to clear removed module dynamic spaces immediately, got {hot_sp_after}",
        )

        _ = _run_gated_cli_two_step(host_dir, ["install", "demo@1.1.0.0"])
        cp_hot_reinst = _run_yscb_subproc(host_dir, ["demo", "info", "--json"])
        reinst_doc = json.loads(cp_hot_reinst.stdout)
        check(
            reinst_doc["ok"] is True and reinst_doc["executed_hot"] is True and reinst_doc["value"]["version"] == "1.1.0.0",
            f"Expected freshly installed module to be immediately visible on warm daemon without --cold: {reinst_doc}",
        )

        with YscbClient.connect(HostPath(yscb_root)) as cold_sp_client:
            cold_dyn_out = cold_sp_client.call("demo.reg_sp", output_type=bool, force_cold=True)
            check(
                cold_dyn_out.ok and not cold_dyn_out.executed_hot and cold_dyn_out.value is True,
                f"Expected cold SDK demo.reg_sp to succeed: {cold_dyn_out}",
            )
        cp_hot_spaces_notified = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json"])
        notified_doc = json.loads(cp_hot_spaces_notified.stdout)
        check(
            notified_doc["executed_hot"] is True
            and any(sp["space_id"] == "demo/dyn_docs" for sp in notified_doc["value"]["data"]["spaces"]),
            f"Expected cold dynamic space mutation to immediately notify online warm daemon via RPC: {notified_doc}",
        )
        cold_clr_k = WorkspaceKernelFactory.create(HostPath(host_dir), HostPath(yscb_root), force_cold=True)
        try:
            check(cold_clr_k.clear_dynamic_spaces(ModuleId("demo")) == 1)
        finally:
            cold_clr_k.close()
        cp_hot_spaces_cleared = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json"])
        cleared_doc = json.loads(cp_hot_spaces_cleared.stdout)
        check(
            cleared_doc["executed_hot"] is True and cleared_doc["value"]["data"]["spaces"] == [],
            f"Expected cold clear_dynamic_spaces to immediately notify online warm daemon via RPC: {cleared_doc}",
        )
    finally:
        try:
            _ = _run_yscb_subproc(host_dir, ["daemon", "stop", "--force", "--json"])
        except OSError:
            pass
        stop_daemon_cleanly(HostPath(yscb_root))

    host_hp = HostPath(host_dir)
    root_hp = HostPath(yscb_root)
    rogue_mod = InMemoryModule("rogue")

    def _rogue_hijack(ctx: TaskContext) -> bool:
        sp = SpaceSpec(space_id=SpaceId("demo", "hijacked"), entries=(SemanticUri("project", ""),), include=("*.py",))
        out = ctx.call(
            "core.space.set_dynamic",
            SetDynamicSpaceInput(owner=ModuleId("demo"), name="hijacked", spec=sp),
            output_type=bool,
        )
        if not out.ok and out.error is not None:
            raise YscbError(out.error.code, out.error.message)
        return bool(out.value)

    def _rogue_own(ctx: TaskContext) -> int:
        sp = SpaceSpec(space_id=SpaceId("rogue", "temp_sp"), entries=(SemanticUri("project", ""),), include=("*.py",))
        out_set = ctx.call(
            "core.space.set_dynamic",
            SetDynamicSpaceInput(owner=ModuleId("rogue"), name="temp_sp", spec=sp),
            output_type=bool,
        )
        check(out_set.ok and out_set.value is True)
        scan_out = ctx.call(
            "core.space.scan",
            SpaceScanInput(space_id="rogue/temp_sp", force=False),
            output_type=tuple[SpaceDiffBatch, ...],
        )
        check(scan_out.ok and scan_out.value is not None and len(scan_out.value) == 1 and str(scan_out.value[0].space_id) == "rogue/temp_sp")
        out_clr = ctx.call(
            "core.space.clear_dynamic",
            ClearDynamicSpaceInput(owner=ModuleId("rogue"), name="temp_sp"),
            output_type=int,
        )
        check(out_clr.ok)
        return int(out_clr.value or 0)

    rogue_mod.add_task("hijack", _rogue_hijack)
    rogue_mod.add_task("own_space", _rogue_own)

    foreign_host_hp, foreign_root_hp = _init_minimal_workspace(e2e_root / "foreign_ws")
    spoof_demo = InMemoryModule("demo")

    def _spoof_cross_ws(ctx: TaskContext) -> bool:
        sp = SpaceSpec(space_id=SpaceId("demo", "spoofed"), entries=(SemanticUri("project", ""),), include=("*.py",))
        out = ctx.call(
            "core.space.set_dynamic",
            SetDynamicSpaceInput(owner=ModuleId("demo"), name="spoofed", spec=sp),
            output_type=bool,
            target_workspace=root_hp,
            routing_policy=None,
        )
        if not out.ok and out.error is not None:
            raise YscbError(out.error.code, out.error.message)
        return bool(out.value)

    spoof_demo.add_task("cross_hijack", _spoof_cross_ws)

    def _call_peer_info(ctx: TaskContext) -> dict[str, str]:
        out = ctx.call(
            "demo.info",
            {},
            output_type=dict[str, str],
            target_workspace=root_hp,
            routing_policy=None,
        )
        if not out.ok or out.value is None:
            raise RuntimeError(f"Cross-workspace cold discovery failed: {out.error}")
        return out.value

    spoof_demo.add_task("peer_info", _call_peer_info)

    kernel = WorkspaceKernelFactory.create(host_hp, root_hp, force_cold=True, extra_modules=(rogue_mod,))
    try:
        top_sp = SpaceSpec(space_id=SpaceId("demo", "top_hijack"), entries=(SemanticUri("project", ""),), include=("*.py",))
        top_out = kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("core.space.set_dynamic"),
                raw_input={
                    "owner": "demo",
                    "name": "top_hijack",
                    "spec": {
                        "space_id": "demo/top_hijack",
                        "entries": ["project://"],
                        "include": ["*.py"],
                        "exclude": [],
                        "presets": [],
                        "compose": [],
                        "watch": False,
                        "hash_policy": "adaptive",
                        "description": "",
                    },
                },
                workspace_root=root_hp,
                caller_cwd=host_hp,
            )
        )
        check(
            not top_out.ok and top_out.error is not None and top_out.error.code == ErrorCode.ACCESS_DENIED,
            f"Top-level unauthenticated dynamic space mutation must fail with ACCESS_DENIED: {top_out}",
        )
        _ = top_sp

        hijack_out = kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("rogue.hijack"),
                raw_input={},
                workspace_root=root_hp,
                caller_cwd=host_hp,
            )
        )
        check(
            not hijack_out.ok and hijack_out.error is not None and hijack_out.error.code == ErrorCode.ACCESS_DENIED,
            f"Expected ACCESS_DENIED on cross-module dynamic space hijack, got {hijack_out}",
        )

        own_out = kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("rogue.own_space"),
                raw_input={},
                workspace_root=root_hp,
                caller_cwd=host_hp,
            )
        )
        check(own_out.ok and own_out.value == 1, f"Expected rogue module to manage & scan its own dynamic space: {own_out}")

        try:
            _ = kernel.set_dynamic_space(
                ModuleId("rogue"),
                "steal_victim",
                SpaceSpec(
                    space_id=SpaceId("rogue", "steal_victim"),
                    entries=(SemanticUri("storage.local", "demo"),),
                ),
            )
        except YscbError as exc_steal:
            check(exc_steal.detail.code == ErrorCode.ACCESS_DENIED, f"Expected ACCESS_DENIED on cross-module storage.local entry, got {exc_steal}")
        else:
            raise AssertionError("Non-core module must not reference foreign storage.local:// in SpaceSpec.entries")

        try:
            _ = kernel.set_dynamic_space(
                ModuleId("rogue"),
                "readonly",
                SpaceSpec(
                    space_id=SpaceId("rogue", "readonly"),
                    entries=(SemanticUri("config", "rogue"),),
                ),
            )
        except YscbError as exc_ro_cfg:
            check(exc_ro_cfg.detail.code == ErrorCode.ACCESS_DENIED, f"Expected ACCESS_DENIED locking config:// in non-core readonly space: {exc_ro_cfg}")
        else:
            raise AssertionError("Non-core readonly space must not lock config://")

        try:
            _ = kernel.set_dynamic_space(
                ModuleId("rogue"),
                "mismatch_name",
                SpaceSpec(
                    space_id=SpaceId("rogue", "other_name"),
                    entries=(SemanticUri("project", ""),),
                ),
            )
        except YscbError as exc_mm:
            check(exc_mm.detail.code == ErrorCode.CONFIG_INVALID, f"Expected CONFIG_INVALID on space_id mismatch, got {exc_mm}")
        else:
            raise AssertionError("Expected YscbError(CONFIG_INVALID) on dynamic space_id mismatch")

        reg_demo_out = kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("demo.reg_sp"),
                raw_input={},
                workspace_root=root_hp,
                caller_cwd=host_hp,
            )
        )
        check(reg_demo_out.ok and reg_demo_out.value is True)
        check(any(str(s.space_id) == "demo/dyn_docs" for s in kernel.space_registry.list_spaces(owner="demo")))
        check(kernel.clear_dynamic_spaces(ModuleId("demo")) == 1)
        check(kernel.space_registry.list_spaces(owner="demo") == ())
    finally:
        kernel.close()

    foreign_kernel = WorkspaceKernelFactory.create(
        foreign_host_hp,
        foreign_root_hp,
        force_cold=True,
        extra_modules=(spoof_demo,),
    )
    try:
        peer_info_out = foreign_kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("demo.peer_info"),
                raw_input={},
                workspace_root=foreign_root_hp,
                caller_cwd=foreign_host_hp,
            )
        )
        check(
            peer_info_out.ok and isinstance(peer_info_out.value, dict) and peer_info_out.value.get("version") == "1.1.0.0",
            f"Expected cold peer workspace discovery and child kernel execution to succeed, got {peer_info_out}",
        )

        cross_ws_out = foreign_kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("demo.cross_hijack"),
                raw_input={},
                workspace_root=foreign_root_hp,
                caller_cwd=foreign_host_hp,
            )
        )
        check(
            not cross_ws_out.ok and cross_ws_out.error is not None and cross_ws_out.error.code == ErrorCode.ACCESS_DENIED,
            f"Expected exact ACCESS_DENIED on cross-workspace dynamic space hijack, got {cross_ws_out}",
        )
    finally:
        foreign_kernel.close()

    outside_file = e2e_root / "outside_unmanaged.txt"
    outside_file.write_text("outside", encoding="utf-8")
    cp_lock_out = _run_yscb_subproc(host_dir, ["file-lock", "lock", str(outside_file), "--json", "--cold"])
    check(
        cp_lock_out.returncode == 4
        and json.loads(cp_lock_out.stdout)["error"]["code"] == ErrorCode.ACCESS_DENIED.value,
        f"file-lock lock outside workspace must fail with ACCESS_DENIED: {cp_lock_out.stdout}",
    )

    sym_supported = True
    sym_target = host_dir / "real_doc.py"
    sym_target.write_text("x = 1\n", encoding="utf-8")
    sym_link = host_dir / "sym_doc.py"
    try:
        os.symlink(sym_target, sym_link)
    except OSError:
        sym_supported = False
    if sym_supported:
        try:
            cp_match_sym = _run_yscb_subproc(host_dir, ["fs", "match", "core/workspace", str(sym_link), "--json", "--cold"])
            check(cp_match_sym.returncode == 0, f"fs match symlink failed: {cp_match_sym.stderr}")
            match_doc = json.loads(cp_match_sym.stdout)["value"]["data"]
            check(
                match_doc["matched"] is False and match_doc["reason"] == "symlink_rejected",
                f"Expected fs match symlink_rejected, got {match_doc}",
            )
            cp_uri_sym = _run_yscb_subproc(host_dir, ["uri", "to-uri", str(sym_link), "--json", "--cold"])
            check(
                cp_uri_sym.returncode == 4
                and json.loads(cp_uri_sym.stdout)["error"]["code"] == ErrorCode.SECURITY_GATED.value,
                f"Expected SECURITY_GATED on uri to-uri symlink, got {cp_uri_sym.stdout}",
            )
        finally:
            sym_link.unlink(missing_ok=True)

    dep_app_dir = prov_dir / "app"
    dep_app_dir.mkdir(parents=True, exist_ok=True)
    app_zip = dep_app_dir / "1.0.0.0.zip"
    with zipfile.ZipFile(app_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"id": "app", "version": "1.0.0.0", "description": "Dependent app", "dependencies": {"demo": ">=1.1.0.0"}}),
        )
        zf.writestr("module_entry.py", "from core.surface.sdk import Module\nclass AppMod(Module):\n    id = 'app'\n    description = 'app'\ndef create_module():\n    return AppMod().to_yscb_module()\n")
    app_sha = hashlib.sha256(app_zip.read_bytes()).hexdigest()
    (dep_app_dir / "index.json").write_text(
        json.dumps(
            {
                "module_id": "app",
                "versions": ["1.0.0.0"],
                "releases": {
                    "1.0.0.0": {"version": "1.0.0.0", "status": "active", "yanked": False, "sha256": app_sha, "filename": "1.0.0.0.zip"}
                },
            }
        ),
        encoding="utf-8",
    )
    _ = _run_gated_cli_two_step(host_dir, ["install", "app@1.0.0.0", "--cold"])
    cp_help_no_empty_app = _run_yscb_subproc(host_dir, ["--help"])
    check(
        cp_help_no_empty_app.returncode == 0
        and "demo" in cp_help_no_empty_app.stdout
        and "  app " not in cp_help_no_empty_app.stdout,
        f"Non-CLI module 'app' must not register an empty top-level command group in --help: {cp_help_no_empty_app.stdout}",
    )
    with YscbClient(HostPath(yscb_root)) as cold_sdk:
        cold_core_stat = cold_sdk.call("core.status", force_cold=True)
        check(cold_core_stat.ok and not cold_core_stat.executed_hot, f"Cold YscbClient core.status failed: {cold_core_stat}")
        cold_sdk_info = cold_sdk.call("demo.info", output_type=dict[str, str], force_cold=True)
        check(
            cold_sdk_info.ok
            and not cold_sdk_info.executed_hot
            and cold_sdk_info.value is not None
            and cold_sdk_info.value.get("version") == "1.1.0.0"
            and cold_sdk_info.value.get("msg") == "en-msg",
            f"Cold YscbClient on installed disk module must succeed with workspace services: {cold_sdk_info}",
        )
        cold_sdk_dyn = cold_sdk.call("demo.reg_sp", output_type=bool, force_cold=True)
        check(cold_sdk_dyn.ok and cold_sdk_dyn.value is True, f"Cold YscbClient nested core.space.set_dynamic failed: {cold_sdk_dyn}")
    cp_rm_blocked1 = _run_yscb_subproc(host_dir, ["remove", "demo", "--cold", "--json"])
    tok_rm_blocked = str(json.loads(cp_rm_blocked1.stdout)["error"]["message"]).split("--approve=", 1)[1].split()[0].strip("().")
    cp_rm_blocked2 = _run_yscb_subproc(host_dir, ["remove", "demo", f"--approve={tok_rm_blocked}", "--cold", "--json"])
    check(
        cp_rm_blocked2.returncode != 0
        and json.loads(cp_rm_blocked2.stdout)["error"]["code"] == ErrorCode.DEPENDENCY_CONFLICT.value,
        f"Expected DEPENDENCY_CONFLICT removing demo while app depends on it: {cp_rm_blocked2.stdout}",
    )
    cp_sp_preserved = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json", "--cold"])
    preserved_sp = json.loads(cp_sp_preserved.stdout)["value"]["data"]["spaces"]
    check(
        any(sp["space_id"] == "demo/dyn_docs" for sp in preserved_sp),
        f"Rejected remove must preserve demo dynamic spaces in state.db, got {preserved_sp}",
    )
    _ = _run_gated_cli_two_step(host_dir, ["remove", "app", "--cold"])

    _ = _run_gated_cli_two_step(host_dir, ["remove", "demo", "--cold"])
    cp_spaces_after_rm = _run_yscb_subproc(host_dir, ["fs", "spaces", "--owner", "demo", "--json", "--cold"])
    check(cp_spaces_after_rm.returncode == 0)
    rem_spaces = json.loads(cp_spaces_after_rm.stdout)["value"]["data"]["spaces"]
    check(rem_spaces == [], f"Expected demo dynamic spaces cleared on remove, got {rem_spaces}")

    rb_in = _MockTtyInput(lines=("CONFIRM\n",), is_tty=True)
    rb_out = _MockTtyOutput(is_tty=True)
    rb_err = _MockTtyOutput(is_tty=True)
    rc_manual_rb = cli_main(
        ["rollback", "--json", "--cold"],
        host_dir=host_hp,
        yscb_root=root_hp,
        env={"_YSCB_TEST_SANDBOX": "1"},
        stdin_stream=rb_in,
        stdout_stream=rb_out,
        stderr_stream=rb_err,
        install_signal_guard=False,
    )
    check(rc_manual_rb == 0, f"Expected CRITICAL rollback to succeed under HUMAN_TTY CONFIRM, got {rc_manual_rb}")
    check("[CRITICAL WARNING]" in rb_err.getvalue(), "Expected CRITICAL prompt on stderr during rollback --json")


class _BootstrapRedirectHandler(BaseHTTPRequestHandler):
    path: str = ""

    def do_GET(self) -> None:
        if self.path.startswith("/ssrf_v6_meta"):
            self.send_response(302)
            self.send_header("Location", "https://[::ffff:169.254.169.254]/core/index.json")
            self.end_headers()
            return
        if self.path.startswith("/ssrf_v6_priv"):
            self.send_response(302)
            self.send_header("Location", "https://[::ffff:10.0.0.1]/core/index.json")
            self.end_headers()
            return
        if self.path.startswith("/ssrf"):
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.1/core/index.json")
            self.end_headers()
            return
        if self.path.startswith("/loop"):
            step_s = self.path.split("step=", 1)[1] if "step=" in self.path else "0"
            nxt = int(step_s) + 1
            self.send_response(302)
            self.send_header("Location", f"/loop/core/index.json?step={nxt}")
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:9/core/index.json")
        self.end_headers()

    def log_message(self, fmt_str: str, *args: object) -> None:
        _ = (self, fmt_str, args)


def _verify_yscb_bootstrapper_security_and_mirror_fallback(tmp_root: Path) -> None:
    sec_root = tmp_root / "yscb_sec"
    sec_root.mkdir(parents=True, exist_ok=True)

    trav_prov = sec_root / "trav_provider"
    (trav_prov / "core").mkdir(parents=True, exist_ok=True)
    (trav_prov / "core" / "index.json").write_text(
        json.dumps(
            {
                "module_id": "core",
                "versions": ["2.0.0.0"],
                "releases": {
                    "2.0.0.0": {
                        "version": "2.0.0.0",
                        "status": "active",
                        "yanked": False,
                        "filename": "../evil.zip",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    trav_host = sec_root / "trav_host"
    trav_host.mkdir(parents=True, exist_ok=True)
    cp_trav = _run_yscb_subproc(trav_host, ["init", f"--provider={trav_prov}", "--ignore-sha256"])
    check(cp_trav.returncode != 0, "yscb init must reject '../evil.zip' archive traversal in core/index.json")

    bomb_prov = sec_root / "bomb_provider"
    (bomb_prov / "core").mkdir(parents=True, exist_ok=True)
    bomb_zip = bomb_prov / "core" / "2.0.0.0.zip"
    with zipfile.ZipFile(bomb_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core"}))
        zf.writestr("zeroes.bin", b"\x00" * (2 * 1024 * 1024))
    bomb_sha = hashlib.sha256(bomb_zip.read_bytes()).hexdigest()
    (bomb_prov / "core" / "index.json").write_text(
        json.dumps(
            {
                "module_id": "core",
                "versions": ["2.0.0.0"],
                "releases": {
                    "2.0.0.0": {
                        "version": "2.0.0.0",
                        "status": "active",
                        "yanked": False,
                        "sha256": bomb_sha,
                        "filename": "2.0.0.0.zip",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bomb_host = sec_root / "bomb_host"
    bomb_host.mkdir(parents=True, exist_ok=True)
    cp_bomb = _run_yscb_subproc(bomb_host, ["init", f"--provider={bomb_prov}"])
    check(cp_bomb.returncode != 0 and "ratio" in cp_bomb.stderr.lower(), f"Expected 200:1 Zip bomb rejection, got {cp_bomb.stderr}")

    good_prov = sec_root / "good_provider"
    _ = _package_core_release_zip(good_prov, "2.0.0.0", status="active")
    fb_host = sec_root / "fb_host"
    fb_host.mkdir(parents=True, exist_ok=True)
    cp_init_json = _run_yscb_subproc(fb_host, ["init", "--provider=../good_provider", "--json"])
    check(cp_init_json.returncode == 0, f"yscb init --json with ../good_provider failed: {cp_init_json.stdout} {cp_init_json.stderr}")
    init_json_doc = json.loads(cp_init_json.stdout)
    check(
        init_json_doc.get("ok") is True
        and isinstance(init_json_doc.get("value"), dict)
        and init_json_doc["value"].get("core_version") == "2.0.0.0",
        f"Expected structured JSON output from yscb init --json: {init_json_doc}",
    )
    check(
        (fb_host / ".yscb" / ".mirror" / "core" / "2.0.0.0.zip.sha256").is_file(),
        "Mirror must persist verified 2.0.0.0.zip.sha256 sidecar",
    )

    uninit_host = sec_root / "uninit_json_host"
    uninit_host.mkdir(parents=True, exist_ok=True)
    cp_uninit_json = _run_yscb_subproc(uninit_host, ["status", "--json"])
    check(cp_uninit_json.returncode == 1, f"Expected exit 1 on uninitialized status --json: {cp_uninit_json.stdout}")
    uninit_doc = json.loads(cp_uninit_json.stdout)
    check(uninit_doc.get("ok") is False and isinstance(uninit_doc.get("error"), dict), f"Expected JSON error envelope: {uninit_doc}")

    shutil.rmtree(good_prov)
    shutil.rmtree(fb_host / ".yscb" / ".modules" / "core")
    cp_fb = _run_yscb_subproc(fb_host, ["status", "--json", "--cold"])
    check(
        cp_fb.returncode == 0 and (fb_host / ".yscb" / ".modules" / "core" / "manifest.json").is_file(),
        f"Expected automatic fallback to verified local .mirror/core/ when primary provider is missing: {cp_fb.stderr}",
    )

    srv = HTTPServer(("127.0.0.1", 0), _BootstrapRedirectHandler)
    srv_port = srv.server_address[1]
    srv_thr = threading.Thread(target=srv.serve_forever, daemon=True)
    srv_started = False
    try:
        srv_thr.start()
        srv_started = True
        redir_host = sec_root / "redir_host"
        redir_host.mkdir(parents=True, exist_ok=True)
        cp_nonloop_http = _run_yscb_subproc(
            redir_host,
            ["init", "--provider=http://192.0.2.1:8080", "--json"],
        )
        check(cp_nonloop_http.returncode != 0, "Plain HTTP to non-loopback host must be rejected")
        cp_v6_map_loop = _run_yscb_subproc(
            redir_host,
            ["init", f"--provider=http://[::ffff:127.0.0.1]:{srv_port}", "--json"],
        )
        check(cp_v6_map_loop.returncode != 0, "Plain HTTP to IPv4-mapped loopback [::ffff:127.0.0.1] must be rejected")

        cp_loop_lim = _run_yscb_subproc(
            redir_host,
            ["init", f"--provider=http://127.0.0.1:{srv_port}/loop", "--json"],
            extra_env={"_YSCB_ALLOW_LOOPBACK_HTTP": "1"},
        )
        check(cp_loop_lim.returncode != 0, "Redirect loop exceeding 5 hops must be rejected")
        loop_err_msg = str(json.loads(cp_loop_lim.stdout)["error"]["message"]).lower()
        check("redirects" in loop_err_msg, f"Expected max redirects rejection message, got {loop_err_msg}")

        cp_ssrf = _run_yscb_subproc(
            redir_host,
            ["init", f"--provider=http://127.0.0.1:{srv_port}/ssrf", "--json"],
            extra_env={"_YSCB_ALLOW_LOOPBACK_HTTP": "1"},
        )
        check(cp_ssrf.returncode != 0, "Redirect from loopback HTTP to non-loopback private IP must be rejected")
        ssrf_err_msg = str(json.loads(cp_ssrf.stdout)["error"]["message"]).lower()
        check("10.0.0.1" in ssrf_err_msg or "insecure" in ssrf_err_msg, f"Expected non-loopback HTTP rejection, got {ssrf_err_msg}")

        for v6_path in ("/ssrf_v6_meta", "/ssrf_v6_priv"):
            cp_v6 = _run_yscb_subproc(
                redir_host,
                ["init", f"--provider=http://127.0.0.1:{srv_port}{v6_path}", "--json"],
                extra_env={"_YSCB_ALLOW_LOOPBACK_HTTP": "1"},
            )
            check(cp_v6.returncode != 0, f"IPv4-mapped IPv6 redirect {v6_path} must be rejected")
            v6_msg = str(json.loads(cp_v6.stdout)["error"]["message"]).lower()
            check("disallowed host" in v6_msg or "tier=" in v6_msg, f"Expected SSRF tier rejection for {v6_path}, got {v6_msg}")
    finally:
        if srv_started:
            srv.shutdown()
        srv.server_close()
        if srv_started:
            srv_thr.join(timeout=5.0)
            check(not srv_thr.is_alive(), "Redirect test HTTPServer thread failed to terminate")

    # Empty/missing launcher flags & '--approve --json' non-swallowing JSON purity
    for bad_launcher_argv in (
        ["--host-dir=", "status", "--json"],
        ["--host-dir", "--json"],
        ["init", "--provider=", "--json"],
        ["init", "--provider", "--json"],
        ["init", "--yscb-root=", "--json"],
        ["self-update", "--url=", "--json"],
        ["self-update", "--sha256=", "--json"],
    ):
        cp_bad_fl = _run_yscb_subproc(fb_host, bad_launcher_argv)
        check(cp_bad_fl.returncode == 2, f"Expected exit code 2 for {bad_launcher_argv}, got {cp_bad_fl.returncode}: {cp_bad_fl.stdout}")
        fl_doc = json.loads(cp_bad_fl.stdout)
        check(fl_doc.get("ok") is False and fl_doc["error"]["code"] == "codec_validation_failed", f"Expected codec_validation_failed JSON for {bad_launcher_argv}: {fl_doc}")

    cp_app_swallow = _run_yscb_subproc(fb_host, ["install", "demo", "--approve", "--json"])
    check(cp_app_swallow.returncode == 2, f"Expected exit code 2 on '--approve --json', got {cp_app_swallow.returncode}")
    app_sw_doc = json.loads(cp_app_swallow.stdout)
    check(app_sw_doc.get("ok") is False and app_sw_doc["error"]["code"] == ErrorCode.CODEC_VALIDATION_FAILED.value)

    # Zero-import int64 overflow & NaN/Inf scalar pre-validation + ApprovalTokenStore 0o600 / expiry / cross-task replay
    tok_dir = sec_root / "tok_store_check"
    tok_dir.mkdir(parents=True, exist_ok=True)
    tok_store = ApprovalTokenStore(HostPath(tok_dir))
    issued_rec = tok_store.issue_token(TaskId("core.install"), {"specs": ["demo"]}, summary="Install demo", now_epoch=1000.0)
    if os.name != "nt":
        tok_mode = stat.S_IMODE((tok_dir / "core" / "pending_approvals.json").stat().st_mode)
        check(tok_mode == 0o600, f"Expected pending_approvals.json mode 0o600, got {oct(tok_mode)}")
    try:
        _ = tok_store.consume_token(issued_rec.token, TaskId("core.remove"), {"specs": ["demo"]}, now_epoch=1005.0)
    except YscbError as exc_rep:
        check(exc_rep.detail.code == ErrorCode.SECURITY_GATED)
    else:
        raise AssertionError("Cross-task token replay must be rejected")
    issued_exp = tok_store.issue_token(TaskId("core.install"), {"specs": ["demo"]}, summary="Install demo", now_epoch=1000.0)
    try:
        _ = tok_store.consume_token(issued_exp.token, TaskId("core.install"), {"specs": ["demo"]}, now_epoch=1305.0)
    except YscbError as exc_exp:
        check(exc_exp.detail.code == ErrorCode.SECURITY_GATED and "expired" in exc_exp.detail.message.lower())
    else:
        raise AssertionError("Expired approval token (>300s) must be rejected")

    cp_unk_opt = _run_yscb_subproc(fb_host, ["env", "gc", "--grace-sec", "10", "--json", "--cold"])
    check(cp_unk_opt.returncode == 2 and json.loads(cp_unk_opt.stdout)["error"]["code"] == ErrorCode.CODEC_VALIDATION_FAILED.value)

    # Anti-downgrade guard when local .mirror lags behind pinned yscb.config.json (not marked pruned) & .build pin guard
    lag_host = sec_root / "lag_mirror_host"
    shutil.copytree(fb_host, lag_host)
    lag_cfg_path = lag_host / "yscb.config.json"
    lag_cfg = json.loads(lag_cfg_path.read_text(encoding="utf-8"))
    lag_cfg["installed_modules"]["core"]["version"] = "2.0.0.5"
    lag_cfg_path.write_text(json.dumps(lag_cfg, indent=2), encoding="utf-8")
    shutil.rmtree(lag_host / ".yscb" / ".modules" / "core")
    cp_lag = _run_yscb_subproc(lag_host, ["status", "--json", "--cold"], extra_env={"YSCB_OFFLINE": "1"})
    check(cp_lag.returncode != 0, "Lagging local mirror (2.0.0.0 < 2.0.0.5 non-pruned) must NOT silently downgrade core")
    check(
        json.loads(lag_cfg_path.read_text(encoding="utf-8"))["installed_modules"]["core"]["version"] == "2.0.0.5",
        "Failed restore must not overwrite yscb.config.json with older mirror version",
    )

    lag_cfg["installed_modules"]["core"]["version"] = "2.0.0.0.build"
    lag_cfg_path.write_text(json.dumps(lag_cfg, indent=2), encoding="utf-8")
    cp_bld_pin = _run_yscb_subproc(lag_host, ["status", "--json", "--cold"], extra_env={"YSCB_OFFLINE": "1"})
    check(cp_bld_pin.returncode != 0, ".build pinned core version must refuse release fallback")

    # Zip slip ('../escape.py') & symlink entry rejection in yscb.py bootstrapper
    zipslip_prov = sec_root / "zipslip_prov"
    (zipslip_prov / "core").mkdir(parents=True, exist_ok=True)
    zs_zip = zipslip_prov / "core" / "2.0.0.0.zip"
    with zipfile.ZipFile(zs_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core"}))
        zf.writestr("../escape.py", "evil = 1\n")
    zs_sha = hashlib.sha256(zs_zip.read_bytes()).hexdigest()
    (zipslip_prov / "core" / "index.json").write_text(
        json.dumps({"module_id": "core", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"version": "2.0.0.0", "status": "active", "yanked": False, "sha256": zs_sha, "filename": "2.0.0.0.zip"}}}),
        encoding="utf-8",
    )
    zs_host = sec_root / "zs_host"
    zs_host.mkdir(parents=True, exist_ok=True)
    cp_zs = _run_yscb_subproc(zs_host, ["init", f"--provider={zipslip_prov}", "--json"])
    check(cp_zs.returncode != 0 and not (sec_root / "escape.py").exists(), "Zip slip in yscb.py init must be rejected")

    zsym_prov = sec_root / "zsym_prov"
    (zsym_prov / "core").mkdir(parents=True, exist_ok=True)
    zsym_zip = zsym_prov / "core" / "2.0.0.0.zip"
    with zipfile.ZipFile(zsym_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core"}))
        sym_zi = zipfile.ZipInfo("evil_link.py")
        sym_zi.create_system = 3
        sym_zi.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(sym_zi, "/etc/passwd")
    zsym_sha = hashlib.sha256(zsym_zip.read_bytes()).hexdigest()
    (zsym_prov / "core" / "index.json").write_text(
        json.dumps({"module_id": "core", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"version": "2.0.0.0", "status": "active", "yanked": False, "sha256": zsym_sha, "filename": "2.0.0.0.zip"}}}),
        encoding="utf-8",
    )
    zsym_host = sec_root / "zsym_host"
    zsym_host.mkdir(parents=True, exist_ok=True)
    cp_zsym = _run_yscb_subproc(zsym_host, ["init", f"--provider={zsym_prov}", "--json"])
    check(cp_zsym.returncode != 0, "Symlink entry in core Zip must be rejected by yscb.py")

    # Concurrent yscb.py deterministic core auto-restore storm (4 parallel processes on missing .modules/core)
    conc_prov = sec_root / "conc_provider"
    _ = _package_core_release_zip(conc_prov, "2.0.0.0", status="active")
    conc_host = sec_root / "conc_host"
    conc_host.mkdir(parents=True, exist_ok=True)
    check(_run_yscb_subproc(conc_host, ["init", f"--provider={conc_prov}", "--json"]).returncode == 0)
    shutil.rmtree(conc_host / ".yscb" / ".modules" / "core")
    win_flags_e2e = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    conc_env = _build_sanitized_subproc_env(caller_mode="agent", extra_env={"YSCB_TEST_SANDBOX": "1"})
    conc_procs = [
        subprocess.Popen(
            [sys.executable, "-X", "utf8", "-B", str(CORE_V2_ROOT / "yscb.py"), f"--host-dir={conc_host}", "status", "--json", "--cold"],
            cwd=str(conc_host),
            env=conc_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=win_flags_e2e,
        )
        for _ in range(4)
    ]
    conc_outs: list[tuple[int, str, str]] = []
    try:
        for p_conc in conc_procs:
            out_s, err_s = p_conc.communicate(timeout=30.0)
            conc_outs.append((p_conc.returncode, out_s, err_s))
    finally:
        for p_conc in conc_procs:
            _terminate_and_close_subproc(p_conc)
    for rc_c, out_c, err_c in conc_outs:
        check(rc_c == 0 and json.loads(out_c).get("ok") is True, f"Concurrent core auto-restore failed (rc={rc_c}): {out_c} {err_c}")

    # Foreground 'daemon start --console --json' ready emission + 'daemon stop' clean exit 0,
    # relative './releases' provider across init/install/list --remote, dynamic Module.aliases synthesis,
    # SemVer4 '2.0.0' == '2.0.0.0' parity, and negative numeric positional CLI args
    rel_ws = sec_root / "rel_prov_ws"
    rel_releases = rel_ws / "releases"
    _ = _package_core_release_zip(rel_releases, "2.0.0.0", status="active")
    _package_demo_module_zip(rel_releases, "1.0.0.0")

    # Package a module WITHOUT pre-bundled tasks.index.json and with negative-int positional Arg + aliases
    calc_mod_dir = rel_releases / "calcmod"
    calc_mod_dir.mkdir(parents=True, exist_ok=True)
    calc_zip = calc_mod_dir / "1.0.0.0.zip"
    calc_entry = (
        "from dataclasses import dataclass\n"
        "from typing import Annotated\n"
        "from core.surface.sdk import Arg, Module, TaskContext, task\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class AddIn:\n"
        "    delta: Annotated[int, Arg(summary='Signed integer delta')]\n"
        "    scale: Annotated[float, Arg(summary='Signed float scale')] = 1.0\n\n"
        "class CalcModule(Module):\n"
        "    id = 'calcmod'\n"
        "    aliases = ('cm',)\n"
        "    description = 'Signed arithmetic module'\n\n"
        "    @task(cli='shift', name='shift', summary='Compute shifted value')\n"
        "    def shift(self, req: AddIn, ctx: TaskContext) -> float:\n"
        "        _ = (self, ctx)\n"
        "        return float(req.delta) * req.scale\n\n"
        "def create_module():\n"
        "    return CalcModule().to_yscb_module()\n"
    )
    with zipfile.ZipFile(calc_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"id": "calcmod", "version": "1.0.0.0", "description": "Calc manifest"}))
        zf.writestr("module_entry.py", calc_entry)
    calc_sha = hashlib.sha256(calc_zip.read_bytes()).hexdigest()
    (calc_mod_dir / "index.json").write_text(
        json.dumps(
            {
                "module_id": "calcmod",
                "versions": ["1.0.0.0"],
                "releases": {"1.0.0.0": {"version": "1.0.0.0", "status": "active", "yanked": False, "sha256": calc_sha, "filename": "1.0.0.0.zip"}},
            }
        ),
        encoding="utf-8",
    )

    cp_rel_init = _run_yscb_subproc(rel_ws, ["init", "--provider=./releases", "--json"])
    check(cp_rel_init.returncode == 0, f"init --provider=./releases failed: {cp_rel_init.stdout} {cp_rel_init.stderr}")
    _ = _run_gated_cli_two_step(rel_ws, ["install", "calcmod", "--cold"])
    cp_list_rem = _run_yscb_subproc(rel_ws, ["list", "--remote", "--json", "--cold"])
    check(cp_list_rem.returncode == 0, f"list --remote with ./releases failed: {cp_list_rem.stdout} {cp_list_rem.stderr}")
    rem_mods = {m["module_id"]: m for m in json.loads(cp_list_rem.stdout)["value"]["data"]["modules"]}
    check("1.0.0.0" in rem_mods["calcmod"].get("remote_versions", []), f"Expected remote_versions from ./releases: {rem_mods}")

    # Verify synthesized tasks.index.json preserved Module.aliases ('cm') AND supports negative positional numbers (-5, -2.5)
    cp_neg_alias = _run_yscb_subproc(rel_ws, ["cm", "shift", "-5", "-2.5", "--json", "--cold"])
    check(cp_neg_alias.returncode == 0, f"Expected alias 'cm' + negative positionals (-5, -2.5) to succeed: {cp_neg_alias.stdout} {cp_neg_alias.stderr}")
    check(json.loads(cp_neg_alias.stdout)["value"] == 12.5, f"Unexpected shift result: {cp_neg_alias.stdout}")

    cp_int64_ovf = _run_yscb_subproc(rel_ws, ["cm", "shift", "99999999999999999999999999", "1.0", "--json", "--cold"])
    check(cp_int64_ovf.returncode == 2, f"Expected int64 overflow exit 2: {cp_int64_ovf.stdout}")
    ovf_doc = json.loads(cp_int64_ovf.stdout)
    check(
        ovf_doc["error"]["code"] == ErrorCode.CODEC_VALIDATION_FAILED.value
        and "64-bit signed range" in ovf_doc["error"]["message"],
        f"Expected genuine 64-bit signed range rejection: {ovf_doc}",
    )
    for nonfin_lit in ("nan", "inf", "-inf"):
        cp_nonfin = _run_yscb_subproc(rel_ws, ["cm", "shift", "--json", "--cold", "--", "1", nonfin_lit])
        check(cp_nonfin.returncode == 2, f"Expected non-finite float rejection for {nonfin_lit}: {cp_nonfin.stdout}")
        nf_doc = json.loads(cp_nonfin.stdout)
        check(
            nf_doc["error"]["code"] == ErrorCode.CODEC_VALIDATION_FAILED.value
            and "non-finite float" in nf_doc["error"]["message"].lower(),
            f"Expected genuine non-finite float error for {nonfin_lit}: {nf_doc}",
        )

    # Verify 3-segment '2.0.0' pin in yscb.config.json matches installed '2.0.0.0' without redundant re-deploy
    rel_cfg_file = rel_ws / "yscb.config.json"
    rel_cfg_doc = json.loads(rel_cfg_file.read_text(encoding="utf-8"))
    rel_cfg_doc["installed_modules"]["core"]["version"] = "v2.0.0"
    rel_cfg_file.write_text(json.dumps(rel_cfg_doc, indent=2), encoding="utf-8")
    cp_v3_status = _run_yscb_subproc(rel_ws, ["status", "--json", "--cold"], extra_env={"YSCB_OFFLINE": "1"})
    check(cp_v3_status.returncode == 0, f"v2.0.0 pin must match installed 2.0.0.0 core: {cp_v3_status.stdout} {cp_v3_status.stderr}")

    # Foreground daemon start --console --json ready callback + daemon stop clean exit 0
    fg_proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-B", str(CORE_V2_ROOT / "yscb.py"), f"--host-dir={rel_ws}", "daemon", "start", "--console", "--json"],
        cwd=str(rel_ws),
        env=_build_sanitized_subproc_env(caller_mode="agent"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=win_flags_e2e,
    )
    try:
        ready_line = _readline_subproc_with_timeout(fg_proc, timeout_sec=15.0)
        check(bool(ready_line.strip()), "Expected immediate JSON ready line from daemon start --console --json")
        ready_doc = json.loads(ready_line)
        check(
            ready_doc.get("ok") is True and ready_doc["value"]["data"].get("started") is True,
            f"Unexpected foreground daemon ready JSON: {ready_doc}",
        )
        cp_contend = _run_yscb_subproc(rel_ws, ["daemon", "start", "--console", "--json"])
        check(cp_contend.returncode == 0, f"Expected contended daemon start --console to exit 0: {cp_contend.stdout}")
        contend_doc = json.loads(cp_contend.stdout)
        check(
            contend_doc["value"]["data"].get("already_running") is True
            and "title" not in contend_doc["value"]
            and contend_doc["value"].get("summary") is not None,
            f"Unexpected contended foreground daemon JSON: {contend_doc}",
        )
        cp_stop_fg = _run_yscb_subproc(rel_ws, ["daemon", "stop", "--json"])
        check(cp_stop_fg.returncode == 0, f"daemon stop failed: {cp_stop_fg.stdout} {cp_stop_fg.stderr}")
        rem_out, rem_err = fg_proc.communicate(timeout=15.0)
        check(fg_proc.returncode == 0 and not rem_out.strip(), f"Foreground daemon must exit 0 without trailing duplicate JSON (rc={fg_proc.returncode}, rem={rem_out!r}, err={rem_err!r})")
    finally:
        _terminate_and_close_subproc(fg_proc)




def _verify_hot_sdk_sync_and_boundary_hardening(sec_root: Path) -> None:
    """Verify hot YscbClient post-install daemon resume, default mod_<id> Tier 1 venv, and boundary guards."""
    # 1. CLI command-tree core protection & canonical priority over aliases + strict index validation
    core_idx = WorkspaceKernelFactory.builtin_cli_indices()[0]
    spoof_install_idx = ModuleTasksIndex(
        module_id=ModuleId("install"),
        module_aliases=("status",),
        description="Attempted hijack of core install",
        tasks=(
            IndexedTaskEntry(
                task_id=TaskId("install.run"),
                command_path=("sub",),
                aliases=(),
                summary="Hijack",
                usage_pros=(),
                usage_cons=(),
                exposure=TaskExposure.CLI_AND_SDK,
                security_tier=SecurityTier.SAFE,
                dispatch_mode=DispatchMode.HYBRID,
                interactive_tty=False,
            ),
        ),
    )
    mod_alpha_idx = ModuleTasksIndex(
        module_id=ModuleId("alpha"),
        module_aliases=("beta", "st"),
        description="Alpha module",
        tasks=(
            IndexedTaskEntry(
                task_id=TaskId("alpha.ping"),
                command_path=("ping",),
                aliases=(),
                summary="Alpha ping",
                usage_pros=(),
                usage_cons=(),
                exposure=TaskExposure.CLI_AND_SDK,
                security_tier=SecurityTier.SAFE,
                dispatch_mode=DispatchMode.HYBRID,
                interactive_tty=False,
            ),
        ),
    )
    mod_beta_idx = ModuleTasksIndex(
        module_id=ModuleId("beta"),
        module_aliases=(),
        description="Canonical beta module",
        tasks=(
            IndexedTaskEntry(
                task_id=TaskId("beta.ping"),
                command_path=("ping",),
                aliases=(),
                summary="Beta ping",
                usage_pros=(),
                usage_cons=(),
                exposure=TaskExposure.CLI_AND_SDK,
                security_tier=SecurityTier.SAFE,
                dispatch_mode=DispatchMode.HYBRID,
                interactive_tty=False,
            ),
        ),
    )
    tree = build_cli_command_tree((spoof_install_idx, mod_alpha_idx, mod_beta_idx, core_idx))
    check(
        tree.children["install"].owner_module == ModuleId("core") and "sub" not in tree.children["install"].children,
        "External module named 'install' must never overwrite or attach children under core 'install'",
    )
    beta_res = resolve_cli_invocation(
        extract_global_flags(("beta", "ping")),
        (spoof_install_idx, mod_alpha_idx, mod_beta_idx, core_idx),
    )
    check(
        beta_res.task_entry is not None and beta_res.task_entry.task_id == TaskId("beta.ping"),
        f"Canonical module 'beta' must win over earlier alias 'beta' on 'alpha': {beta_res}",
    )
    check("beta" not in tree.children["alpha"].aliases, f"Shadowed alias 'beta' must be pruned from node.aliases: {tree.children['alpha'].aliases}")

    for bad_idx_doc in (
        {
            "schema_version": 2,
            "module_id": "badm",
            "tasks": [
                {
                    "task_id": "badm.t",
                    "command_path": ["  "],
                    "exposure": "cli_and_sdk",
                    "security_tier": "safe",
                    "dispatch_mode": "hybrid",
                }
            ],
        },
        {
            "schema_version": 2,
            "module_id": "badm",
            "tasks": [
                {
                    "task_id": "badm.t",
                    "command_path": ["ok"],
                    "exposure": "cli_and_sdk",
                    "security_tier": "safe",
                    "dispatch_mode": "hybrid",
                    "periodic": {"interval_config_key": "k"},
                }
            ],
        },
    ):
        try:
            _ = ModuleTasksIndex.from_json_dict(bad_idx_doc)
        except YscbError as exc_idx:
            check(exc_idx.detail.code == ErrorCode.CONFIG_INVALID)
        else:
            raise AssertionError(f"Expected CONFIG_INVALID for malformed tasks.index.json: {bad_idx_doc}")

    # 2. Project bare space owner ('# [project]'), wildcard gitignore carve-out, and foreign storage:// readonly denial
    hard_ws = sec_root / "hardening_ws"
    hard_prov = hard_ws / "releases"
    _ = _package_core_release_zip(hard_prov, "2.0.0.0", status="active")
    _package_demo_module_zip(hard_prov, "1.0.0.0")
    check(_run_yscb_subproc(hard_ws, ["init", "--provider=./releases", "--json"]).returncode == 0)

    hard_host_hp = HostPath(hard_ws)
    hard_root_hp = HostPath(hard_ws / ".yscb")
    proj_spaces_file = hard_ws / ".yscb" / "config" / "core" / "contribute.json"
    proj_spaces_file.parent.mkdir(parents=True, exist_ok=True)
    proj_spaces_file.write_text(
        json.dumps(
            {
                "spaces": {
                    "gitignore": {
                        "entries": ["project://"],
                        "include": [
                            "custom_out/",
                            "[.]yscb/**",
                            "./.yscb/secret",
                            "**/.git/**",
                            "[y]scb.py",
                        ],
                        "exclude": ["*.local.json"],
                    },
                    "core/forged_space": {
                        "entries": ["project://"],
                        "include": ["*.py"],
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    hk = WorkspaceKernelFactory.create(hard_host_hp, hard_root_hp, force_cold=True)
    try:
        gi_res = hk.gitignore_materializer.sync()
        check("project" in gi_res.groups, f"Bare project gitignore space must compile under 'project', got {dict(gi_res.groups)}")
        proj_pats = gi_res.groups["project"]
        check("custom_out/" in proj_pats, f"Expected 'custom_out/' in project gitignore group: {proj_pats}")
        for forbidden_pat in ("[.]yscb/**", "./.yscb/secret", "**/.git/**", "[y]scb.py", "!*.local.json"):
            check(forbidden_pat not in proj_pats, f"Control-plane wildcard/exemption {forbidden_pat!r} must be rejected: {proj_pats}")
        try:
            _ = hk.space_registry.get_space("core/forged_space")
        except YscbError as exc_fg:
            check(exc_fg.detail.code == ErrorCode.SPACE_NOT_FOUND)
        else:
            raise AssertionError("Project donor must not forge 'core/*' spaces")

        try:
            _ = hk.set_dynamic_space(
                ModuleId("rogue"),
                "readonly",
                SpaceSpec(
                    space_id=SpaceId("rogue", "readonly"),
                    entries=(SemanticUri("storage", "victim"),),
                ),
            )
        except YscbError as exc_st_ro:
            check(exc_st_ro.detail.code == ErrorCode.ACCESS_DENIED, f"Expected ACCESS_DENIED locking foreign storage:// in readonly: {exc_st_ro}")
        else:
            raise AssertionError("Module readonly space must not lock foreign storage://<other>")
    finally:
        hk.close()

    # 3. Corrupt .modules/core/tasks.index.json zero-import fallback & self-heal
    corrupt_core_idx = hard_ws / ".yscb" / ".modules" / "core" / "tasks.index.json"
    corrupt_core_idx.write_text("{corrupt_json", encoding="utf-8")
    cp_heal = _run_yscb_subproc(hard_ws, ["status", "--json", "--cold"])
    check(cp_heal.returncode == 0 and json.loads(cp_heal.stdout).get("ok") is True, f"CLI must survive corrupt core tasks.index.json: {cp_heal.stdout} {cp_heal.stderr}")
    healed_doc = json.loads(corrupt_core_idx.read_text(encoding="utf-8"))
    check(healed_doc.get("module_id") == "core", f"Expected WorkspaceKernel to heal corrupt core tasks.index.json: {healed_doc}")

    # 4. Online WorkspaceDaemon + long-lived YscbClient.connect(...) running core.install then immediate hot RPC call
    win_flags_hd = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    fg_daemon = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-B", str(CORE_V2_ROOT / "yscb.py"), f"--host-dir={hard_ws}", "daemon", "start", "--console", "--json"],
        cwd=str(hard_ws),
        env=_build_sanitized_subproc_env(caller_mode="agent"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=win_flags_hd,
    )
    try:
        r_line = _readline_subproc_with_timeout(fg_daemon, timeout_sec=15.0)
        check(bool(r_line.strip()) and json.loads(r_line).get("ok") is True, f"Daemon failed to start: {r_line}")
        with YscbClient.connect(hard_root_hp) as live_client:
            inst_out = live_client.call(
                "core.install",
                {"specs": ["demo"], "provider": None, "force": False, "offline": False, "ignore_sha256": False},
                approval_scope=frozenset({TaskId("core.install")}),
            )
            check(inst_out.ok, f"YscbClient.connect core.install failed: {inst_out}")
            hot_demo = live_client.call("demo.info")
            check(
                hot_demo.ok and hot_demo.executed_hot is True,
                f"Expected immediate hot RPC execution on newly installed module without closing YscbClient: {hot_demo}",
            )
        _ = _run_yscb_subproc(hard_ws, ["daemon", "stop", "--json"])
        fg_daemon.communicate(timeout=15.0)
    finally:
        _terminate_and_close_subproc(fg_daemon)

    # 5. Standalone YscbClient default venv_group=None ('mod_<id>') Tier 1 resolution (POSIX wrapper shim)
    if os.name != "nt":
        t1_ws = sec_root / "t1_default_group_ws"
        t1_mod_dir = t1_ws / ".modules" / "defgrp"
        t1_mod_dir.mkdir(parents=True, exist_ok=True)
        (t1_mod_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "defgrp",
                    "version": "1.0.0.0",
                    "description": "Default group Tier 1 module",
                    "pip_dependencies": {"sample-pkg": ">=1.0"},
                }
            ),
            encoding="utf-8",
        )
        (t1_mod_dir / "module_entry.py").write_text(
            "from core.surface.sdk import Module, TaskContext, task\n"
            "class DefGrpMod(Module):\n"
            "    id = 'defgrp'\n"
            "    @task\n"
            "    def ping(self, ctx: TaskContext) -> str:\n"
            "        _ = ctx\n"
            "        return 'tier1_default_mod_group_ok'\n"
            "def create_module():\n"
            "    return DefGrpMod().to_yscb_module()\n",
            encoding="utf-8",
        )
        (t1_mod_dir / "tasks.index.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "module_id": "defgrp",
                    "module_aliases": [],
                    "description": "Default group Tier 1 module",
                    "tasks": [
                        {
                            "task_id": "defgrp.ping",
                            "command_path": [],
                            "aliases": [],
                            "summary": "Ping",
                            "usage_pros": [],
                            "usage_cons": [],
                            "exposure": "sdk_only",
                            "security_tier": "safe",
                            "dispatch_mode": "hybrid",
                            "interactive_tty": False,
                            "args": [],
                            "options": [],
                            "subscriptions": [],
                            "periodic": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
        mach_low = platform.machine().lower()
        plat_tag = f"{sys.platform}_{mach_low}"
        specs = ["sample-pkg>=1.0"]
        h_payload = {
            "canonical_pip_specs": specs,
            "machine": mach_low,
            "platform": sys.platform,
            "py_tag": py_tag,
        }
        dig16 = hashlib.sha256(
            json.dumps(h_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()[:16]
        venv_dir = t1_ws / ".venv" / f"defgrp_{py_tag}_{dig16}"
        (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
        py_shim = venv_dir / "bin" / "python"
        os.symlink(sys.executable, py_shim)
        (venv_dir / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
        (venv_dir / ".yscb_env_meta.json").write_text(
            json.dumps(
                {
                    "complete": True,
                    "env_hash": dig16,
                    "group": "defgrp",
                    "py_tag": py_tag,
                    "platform_tag": plat_tag,
                    "pip_specs": specs,
                }
            ),
            encoding="utf-8",
        )
        with YscbClient(HostPath(t1_ws)) as t1_cli:
            t1_res = t1_cli.call("defgrp.ping", output_type=str)
            check(
                t1_res.ok and t1_res.value == "tier1_default_mod_group_ok",
                f"Expected standalone YscbClient to resolve default Tier 1 venv matching ImmutableVenvPool: {t1_res}",
            )


def _verify_uri_scheme_provenance_and_bootstrap_edges(sec_root: Path) -> None:
    """Verify contributed uri_schemes provenance, module storage readonly, packager .gitignore, init --fix, and CLI flag guards."""
    # 1. Reserved global CLI flag rejection & subcommand group alias collision vs DN-13 group-default task
    for bad_opt_fn in (
        lambda: Option(short="h"),
        lambda: Option(long_name="json"),
        lambda: Option(long_name="--host-dir"),
        lambda: Option(long_name="approve"),
    ):
        try:
            _ = bad_opt_fn()
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError on reserved global CLI flag in Option")

    @dataclass(frozen=True, slots=True)
    class ReservedFlagDto:
        json: bool = False

    try:
        class _BadCliFlagMod(Module):
            id = "badfl"

            @task(cli="run")
            def run(self, req: ReservedFlagDto, ctx: TaskContext) -> str:
                _ = (req, ctx)
                return "bad"
    except ValueError:
        pass
    else:
        raise AssertionError("CLI task DTO colliding with --json must raise ValueError")

    class _ValidSdkFlagAndGroupDefaultMod(Module):
        id = "okfl"

        @task
        def sdk_only_json(self, req: ReservedFlagDto, ctx: TaskContext) -> bool:
            _ = ctx
            return req.json

        @task(cli="cfg")
        def cfg_default(self, ctx: TaskContext) -> str:
            _ = ctx
            return "root"

        @task(cli=("cfg", "show"))
        def cfg_show(self, ctx: TaskContext) -> str:
            _ = ctx
            return "show"

    check(len(compile_tasks_index(_ValidSdkFlagAndGroupDefaultMod).tasks) == 3)

    try:
        class _AliasHitsGroupMod(Module):
            id = "badalias"

            @task(cli=("grp", "leaf"))
            def leaf(self, ctx: TaskContext) -> str:
                _ = ctx
                return "leaf"

            @task(cli="other", aliases=("grp",))
            def other(self, ctx: TaskContext) -> str:
                _ = ctx
                return "other"
    except ValueError:
        pass
    else:
        raise AssertionError("CLI alias colliding with subcommand group segment must raise ValueError")

    # 2. Packager preserves .gitignore and .gitignore.tmpl while excluding .git directory
    pkg_ws_root = sec_root / "pkg_gitignore_ws" / ".yscb"
    pkg_src = pkg_ws_root / "source" / "gitkeep"
    (pkg_src / ".git").mkdir(parents=True, exist_ok=True)
    (pkg_src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (pkg_src / "templates").mkdir(parents=True, exist_ok=True)
    (pkg_src / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (pkg_src / "templates" / ".gitignore.tmpl").write_text("dist/\n", encoding="utf-8")
    (pkg_src / "manifest.json").write_text(
        json.dumps({"id": "gitkeep", "version": "1.0.0.0", "description": "Gitignore keep test"}),
        encoding="utf-8",
    )
    (pkg_src / "module_entry.py").write_text(
        "from core.surface.sdk.advanced import InMemoryModule\n"
        "def create_module():\n"
        "    return InMemoryModule('gitkeep').to_yscb_module()\n",
        encoding="utf-8",
    )
    pkg_out_zip = sec_root / "pkg_gitignore_out" / "gitkeep.build.zip"
    built_zip = ProviderClient(yscb_root=HostPath(pkg_ws_root), default_provider=str(pkg_ws_root), offline=True).fetch_package_zip(
        ModuleId("gitkeep"),
        SemVer4(1, 0, 0, 0, is_build=True),
        HostPath(pkg_out_zip),
    )
    with zipfile.ZipFile(str(built_zip), "r") as zf_chk:
        names_set = set(zf_chk.namelist())
    check(".gitignore" in names_set and "templates/.gitignore.tmpl" in names_set, f"Expected .gitignore files preserved: {names_set}")
    check(not any(n == ".git" or n.startswith(".git/") for n in names_set), f".git directory must be excluded: {names_set}")

    # 3. Module own storage:// readonly positive lock + CLI/SDK file-lock control-plane denial + uri_schemes provenance
    edge_ws = sec_root / "edge_ws"
    edge_prov = edge_ws / "releases"
    _ = _package_core_release_zip(edge_prov, "2.0.0.0", status="active")
    _package_demo_module_zip(edge_prov, "1.0.0.0")
    check(_run_yscb_subproc(edge_ws, ["init", "--provider=./releases", "--json"]).returncode == 0)
    _ = _run_gated_cli_two_step(edge_ws, ["install", "demo", "--cold"])

    (edge_ws / "docs").mkdir(parents=True, exist_ok=True)
    demo_store_file = edge_ws / ".yscb" / "storage" / "demo" / "pinned.json"
    demo_store_file.parent.mkdir(parents=True, exist_ok=True)
    demo_store_file.write_text('{"ok": true}\n', encoding="utf-8")

    (edge_ws / ".yscb" / "config" / "core" / "contribute.json").write_text(
        json.dumps(
            {
                "uri_schemes": {
                    "docs_ok": {"token": "docs_ok", "target_uri": "project://docs", "description": "Valid project docs"},
                    "bad_tok": {"token": "mismatch", "target_uri": "project://docs"},
                    "bad_kern": {"token": "bad_kern", "target_uri": "module://core"},
                    "bad_stor": {"token": "bad_stor", "target_uri": "storage://demo"},
                    "bad_core_cfg": {"token": "bad_core_cfg", "config_binding": "core.project_root"},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ek = WorkspaceKernelFactory.create(HostPath(edge_ws), HostPath(edge_ws / ".yscb"), force_cold=True)
    try:
        mounted_schemes = {entry.scheme for entry in ek.mount_table.check_health()}
        check("docs_ok" in mounted_schemes, f"Expected valid project uri_scheme 'docs_ok' mounted: {mounted_schemes}")
        for rej_sch in ("bad_tok", "bad_kern", "bad_stor", "bad_core_cfg"):
            check(rej_sch not in mounted_schemes, f"Unsafe contributed uri_scheme {rej_sch!r} must be rejected: {mounted_schemes}")

        _ = ek.set_dynamic_space(
            ModuleId("demo"),
            "readonly",
            SpaceSpec(space_id=SpaceId("demo", "readonly"), entries=(SemanticUri("storage", "demo"),)),
        )
        demo_file_hp = HostPath(demo_store_file)
        check(
            ek.readonly_policy.is_protected(demo_file_hp) and ek.readonly_policy.is_os_readonly(demo_file_hp),
            "Module <owner>/readonly must protect its own storage://<owner> subtree",
        )
    finally:
        ek.close()

    class _RogueLockCallerMod(Module):
        id = "roguelk"

        @task
        def try_lock_foreign(self, ctx: TaskContext) -> str:
            out = ctx.call(
                "core.file_lock.lock",
                {"path": "storage://demo/pinned.json"},
            )
            if out.ok:
                return "unexpected_ok"
            return out.error.code.value if out.error is not None else "unknown"

    rk = WorkspaceKernelFactory.create(
        HostPath(edge_ws),
        HostPath(edge_ws / ".yscb"),
        force_cold=True,
        extra_modules=(_RogueLockCallerMod(),),
    )
    try:
        rogue_out = rk.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("roguelk.try_lock_foreign"),
                raw_input={},
                workspace_root=HostPath(edge_ws / ".yscb"),
                caller_cwd=HostPath(edge_ws),
            )
        )
        check(
            rogue_out.ok and rogue_out.value == ErrorCode.ACCESS_DENIED.value,
            f"Non-core module SDK call must not lock foreign storage:// subtree: {rogue_out}",
        )
    finally:
        rk.close()

    cp_fl_list = _run_yscb_subproc(edge_ws, ["file-lock", "status", "--json", "--cold"])
    check(cp_fl_list.returncode == 0, f"file-lock status failed: {cp_fl_list.stdout} {cp_fl_list.stderr}")
    fl_entries = [e for e in json.loads(cp_fl_list.stdout)["value"]["data"]["files"] if Path(e["path"]).resolve() == demo_store_file.resolve()]
    check(len(fl_entries) == 1 and fl_entries[0]["space"] == "demo/readonly", f"Expected single deduplicated demo/readonly entry: {fl_entries}")

    for cp_prot_target in (
        edge_ws / "yscb.config.json",
        edge_ws / ".yscb" / ".modules" / "core" / "manifest.json",
    ):
        cp_deny_lk = _run_yscb_subproc(edge_ws, ["file-lock", "lock", str(cp_prot_target), "--json", "--cold"])
        check(
            cp_deny_lk.returncode == 4 and json.loads(cp_deny_lk.stdout)["error"]["code"] == ErrorCode.ACCESS_DENIED.value,
            f"file-lock lock must reject control-plane path {cp_prot_target}: {cp_deny_lk.stdout}",
        )

    # 4. yscb.py init --fix corrupt JSON recovery, core provider preservation, id!='core' guard, and YSCB_OFFLINE=1
    fix_ws = sec_root / "fix_corrupt_ws"
    shutil.copytree(edge_ws, fix_ws)
    copied_ro_pin = fix_ws / ".yscb" / "storage" / "demo" / "pinned.json"
    if copied_ro_pin.exists():
        os.chmod(copied_ro_pin, 0o644)
    orig_cfg = json.loads((fix_ws / "yscb.config.json").read_text(encoding="utf-8"))
    orig_cfg.pop("default_provider", None)
    orig_cfg["installed_modules"]["core"]["provider"] = "./releases"
    (fix_ws / "yscb.config.json").write_text(json.dumps(orig_cfg, indent=2), encoding="utf-8")
    cp_pres_prov = _run_yscb_subproc(fix_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"])
    check(cp_pres_prov.returncode == 0, f"init --fix with installed_modules.core.provider failed: {cp_pres_prov.stdout}")
    check(
        json.loads((fix_ws / "yscb.config.json").read_text(encoding="utf-8"))["default_provider"] == "./releases",
        "init --fix must preserve installed_modules.core.provider when top-level default_provider is absent",
    )

    (fix_ws / "yscb.config.json").write_text("{corrupt_host_cfg", encoding="utf-8")
    (fix_ws / "yscb.config.local.json").write_text("[1, 2, 3]", encoding="utf-8")
    cp_no_fix = _run_yscb_subproc(fix_ws, ["init", "--json"])
    check(cp_no_fix.returncode == 1 and json.loads(cp_no_fix.stdout)["error"]["code"] == "config_invalid")
    cp_with_fix = _run_yscb_subproc(fix_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--provider=./releases", "--json"])
    check(cp_with_fix.returncode == 0, f"init --fix must repair corrupt yscb.config.json: {cp_with_fix.stdout} {cp_with_fix.stderr}")

    cp_off_su = _run_yscb_subproc(fix_ws, ["self-update", "--allow-bootstrap-mutation", "--json"], extra_env={"YSCB_OFFLINE": "1"})
    check(
        cp_off_su.returncode == 1 and json.loads(cp_off_su.stdout)["error"]["code"] == "transport_lost",
        f"self-update must respect YSCB_OFFLINE=1 for remote URLs: {cp_off_su.stdout}",
    )
    cp_off_init_rem = _run_yscb_subproc(
        fix_ws,
        ["init", "--fix", "--allow-bootstrap-mutation", "--provider=https://example.com/releases", "--json"],
        extra_env={"YSCB_OFFLINE": "1"},
    )
    check(
        cp_off_init_rem.returncode == 1 and json.loads(cp_off_init_rem.stdout)["error"]["code"] == "transport_lost",
        f"init --provider=https://... must respect YSCB_OFFLINE=1: {cp_off_init_rem.stdout}",
    )

    spoof_prov = sec_root / "spoof_core_prov"
    (spoof_prov / "core").mkdir(parents=True, exist_ok=True)
    sp_zip = spoof_prov / "core" / "9.9.9.9.zip"
    with zipfile.ZipFile(sp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf_sp:
        zf_sp.writestr("manifest.json", json.dumps({"id": "impostor", "version": "9.9.9.9", "description": "Fake core"}))
        zf_sp.writestr("core/__init__.py", "# fake\n")
    sp_sha = hashlib.sha256(sp_zip.read_bytes()).hexdigest()
    (spoof_prov / "core" / "index.json").write_text(
        json.dumps({"module_id": "core", "versions": ["9.9.9.9"], "releases": {"9.9.9.9": {"version": "9.9.9.9", "status": "active", "yanked": False, "sha256": sp_sha, "filename": "9.9.9.9.zip"}}}),
        encoding="utf-8",
    )
    cp_spoof = _run_yscb_subproc(fix_ws, ["init", "--fix", "--allow-bootstrap-mutation", f"--provider={spoof_prov}", "--json"])
    check(cp_spoof.returncode != 0, "Core archive with manifest id != 'core' must be rejected")
    check(
        json.loads((fix_ws / ".yscb" / ".modules" / "core" / "manifest.json").read_text(encoding="utf-8"))["id"] == "core",
        "Rejected core archive must leave existing .modules/core intact",
    )

    # 5. Yanked primary core release must NOT silently fallback to stale .mirror/core, and symlinked .modules/core heals via init --fix
    yank_prov = sec_root / "yank_core_prov"
    _ = _package_core_release_zip(yank_prov, "2.0.0.0", status="active")
    yank_ws = sec_root / "yank_ws"
    yank_ws.mkdir(parents=True, exist_ok=True)
    check(_run_yscb_subproc(yank_ws, ["init", f"--provider={yank_prov}", "--json"]).returncode == 0)
    yank_idx_p = yank_prov / "core" / "index.json"
    yank_idx_doc = json.loads(yank_idx_p.read_text(encoding="utf-8"))
    yank_idx_doc["releases"]["2.0.0.0"]["yanked"] = True
    yank_idx_p.write_text(json.dumps(yank_idx_doc, indent=2), encoding="utf-8")
    shutil.rmtree(yank_ws / ".yscb" / ".modules" / "core")
    cp_yank_restore = _run_yscb_subproc(yank_ws, ["status", "--json", "--cold"])
    check(cp_yank_restore.returncode != 0, "Yanked primary core release must not fallback to stale local .mirror/core")

    yank_idx_doc["releases"]["2.0.0.0"]["yanked"] = False
    yank_idx_p.write_text(json.dumps(yank_idx_doc, indent=2), encoding="utf-8")
    if os.name != "nt":
        os.symlink(sec_root, yank_ws / ".yscb" / ".modules" / "core")
        cp_sym_fix = _run_yscb_subproc(yank_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"])
        check(
            cp_sym_fix.returncode == 0 and not (yank_ws / ".yscb" / ".modules" / "core").is_symlink(),
            f"init --fix must replace broken symlink at .modules/core cleanly: {cp_sym_fix.stdout} {cp_sym_fix.stderr}",
        )

    # 6. CLI file-lock unlock boundary (positive emergency unlock on module storage vs control-plane denial) + TEARDOWN_ERROR JSON purity + generic config_type + bool Literal choices
    cp_ulk_step1 = _run_yscb_subproc(
        edge_ws,
        ["file-lock", "unlock", str(edge_ws / "yscb.config.json"), "--json", "--cold"],
    )
    check(cp_ulk_step1.returncode == 4)
    ulk_rem = str(json.loads(cp_ulk_step1.stdout)["error"]["remediation"])
    ulk_tok = ulk_rem.split("--approve=", 1)[1].strip().split()[0]
    cp_deny_ulk = _run_yscb_subproc(
        edge_ws,
        ["file-lock", "unlock", str(edge_ws / "yscb.config.json"), f"--approve={ulk_tok}", "--json", "--cold"],
    )
    check(
        cp_deny_ulk.returncode == 4 and json.loads(cp_deny_ulk.stdout)["error"]["code"] == ErrorCode.ACCESS_DENIED.value,
        f"file-lock unlock must reject control-plane yscb.config.json: {cp_deny_ulk.stdout}",
    )
    ulk_ok_doc = _run_gated_cli_two_step(edge_ws, ["file-lock", "unlock", str(demo_store_file), "--cold"])
    check(ulk_ok_doc.get("ok") is True, f"Operator emergency unlock on storage://demo must succeed: {ulk_ok_doc}")

    t_box = TypeVar("t_box")

    @dataclass(frozen=True, slots=True)
    class _GenBox(Generic[t_box]):
        item: t_box

    class _MutableLeaf:
        pass

    @dataclass
    class _UnfrozenDc:
        val: int = 1

    @dataclass(frozen=True, slots=True)
    class _BadGenCfg:
        wrapped: _GenBox[_UnfrozenDc]

    try:
        class _BadGenCfgMod(Module):
            id = "badgencfg"
            config_type = _BadGenCfg
    except ValueError:
        pass
    else:
        raise AssertionError("Parameterized generic dataclass containing unfrozen dataclass must raise ValueError")
    _ = _MutableLeaf

    @dataclass(frozen=True, slots=True)
    class _StrictTrueDto:
        must_true: Annotated[Literal[True], Option(summary="Must be true")] = True

    class _BoolChoiceTearMod(Module):
        id = "bctear"

        def on_init(self, env) -> None:
            def _boom() -> None:
                raise RuntimeError("simulated closer failure")
            env.register_closer(_boom)

        @task(cli="act")
        def act(self, req: _StrictTrueDto, ctx: TaskContext) -> str:
            _ = ctx
            return f"ok:{req.must_true}"

    bc_idx = compile_tasks_index(_BoolChoiceTearMod)
    try:
        _ = resolve_cli_invocation(extract_global_flags(("bctear", "act", "--no-must-true")), (bc_idx,))
    except YscbError as exc_bc:
        check(exc_bc.detail.code == ErrorCode.CODEC_VALIDATION_FAILED and "InvalidChoice" in exc_bc.detail.message)
    else:
        raise AssertionError("Literal[True] bool option must reject --no-must-true")

    class _FailingCloseSession:
        def __init__(self, inner) -> None:
            self._inner = inner

        @property
        def dispatcher(self):
            return self._inner.dispatcher

        @property
        def config_store(self):
            return self._inner.config_store

        def apply_caller_dialect(self, dialect, raw_env_locale=None) -> None:
            self._inner.apply_caller_dialect(dialect, raw_env_locale)

        def resolve_task_output_type(self, task_id):
            return self._inner.resolve_task_output_type(task_id)

        def decode_task_output(self, task_id, raw_value):
            return self._inner.decode_task_output(task_id, raw_value)

        def format_tier1_task_output(self, task_id, raw_value):
            return self._inner.format_tier1_task_output(task_id, raw_value)

        def has_deferred_daemon(self) -> bool:
            return False

        def run_deferred_daemon(self, *, on_ready=None):
            return self._inner.run_deferred_daemon(on_ready=on_ready)

        def consume_post_close_exit_code(self):
            return None

        def close(self) -> None:
            self._inner.close()
            raise YscbError(ErrorCode.TEARDOWN_ERROR, "simulated session close failure")

    tear_out = io.StringIO()
    tear_err = io.StringIO()
    tear_rc = cli_main(
        ["bctear", "act", "--json", "--cold"],
        host_dir=HostPath(edge_ws),
        yscb_root=HostPath(edge_ws / ".yscb"),
        stdout_stream=tear_out,
        stderr_stream=tear_err,
        kernel_factory=lambda h, r, fc: _FailingCloseSession(
            WorkspaceKernelFactory.create(h, r, force_cold=fc, extra_modules=(_BoolChoiceTearMod(),))
        ),
        builtin_indices=(*WorkspaceKernelFactory.builtin_cli_indices(), bc_idx),
        install_signal_guard=False,
    )
    tear_json = json.loads(tear_out.getvalue())
    check(
        tear_rc != 0 and tear_json.get("ok") is False and tear_json["error"]["code"] == ErrorCode.TEARDOWN_ERROR.value,
        f"Expected single clean TEARDOWN_ERROR JSON outcome when session.close() fails: rc={tear_rc}, out={tear_out.getvalue()!r}",
    )

    # 7. Cross-process cold readonly unlock persistence + caller_mode case-folding guard + --no-flag collision + optional variadic None
    tty_in = _MockTtyInput(is_tty=True)
    tty_out = io.StringIO()
    spoof_env_res = detect_caller_environment(
        env={"CLAUDECODE": "1", "claudecode": "0", "YSCB_CALLER_MODE": "agent", "yscb_caller_mode": "human"},
        stdin_stream=tty_in,
        stdout_stream=tty_out,
    )
    check(
        spoof_env_res.mode == CallerMode.AGENT and spoof_env_res.dialect == "nouns-claude",
        f"Expected authoritative uppercase env to defeat trailing lowercase falsy override: {spoof_env_res}",
    )

    @dataclass(frozen=True, slots=True)
    class _NegFlagCollisionDto:
        cache: bool = True
        no_cache: bool = False

    try:
        class _BadNegFlagMod(Module):
            id = "badneg"

            @task(cli="go")
            def go(self, req: _NegFlagCollisionDto, ctx: TaskContext) -> str:
                _ = (req, ctx)
                return "x"
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError on --cache / --no-cache option collision")

    @dataclass(frozen=True, slots=True)
    class _OptVarArgDto:
        items: Annotated[Optional[tuple[str, ...]], Arg(summary="Optional items")] = None
        ratio: Annotated[Literal[0.5, 1.0], Option(summary="Float choice")] = 1.0

    class _OptVarMod(Module):
        id = "optvar"

        @task(cli="check")
        def check_items(self, req: _OptVarArgDto, ctx: TaskContext) -> str:
            _ = ctx
            return f"{req.items!r}:{req.ratio}"

    ov_idx = compile_tasks_index(_OptVarMod)
    ov_res_none = resolve_cli_invocation(extract_global_flags(("optvar", "check", "--ratio=1")), (ov_idx,))
    check(
        ov_res_none.normalized_input == {"items": None, "ratio": 1.0},
        f"Expected Optional variadic Arg=None and numeric float Literal 1 == 1.0: {ov_res_none.normalized_input}",
    )

    ek_lock = WorkspaceKernelFactory.create(HostPath(edge_ws), HostPath(edge_ws / ".yscb"), force_cold=True)
    try:
        _ = ek_lock.set_dynamic_space(
            ModuleId("demo"),
            "readonly",
            SpaceSpec(space_id=SpaceId("demo", "readonly"), entries=(SemanticUri("storage", "demo"),)),
        )
        _ = ek_lock.sync_gitignore_and_readonly()
        check(ek_lock.readonly_policy.is_os_readonly(HostPath(demo_store_file)) is True)
    finally:
        ek_lock.close()

    ek_unlock_cold = WorkspaceKernelFactory.create(HostPath(edge_ws), HostPath(edge_ws / ".yscb"), force_cold=True)
    try:
        _ = ek_unlock_cold.clear_dynamic_spaces(ModuleId("demo"))
        check(
            ek_unlock_cold.readonly_policy.is_os_readonly(HostPath(demo_store_file)) is False,
            "Brand-new cold WorkspaceKernel must auto-unlock previously managed OS readonly file on space removal",
        )
    finally:
        ek_unlock_cold.close()

    bad_root_ws = sec_root / "bad_root_type_ws"
    shutil.copytree(edge_ws, bad_root_ws)
    br_cfg_p = bad_root_ws / "yscb.config.json"
    br_doc = json.loads(br_cfg_p.read_text(encoding="utf-8"))
    br_doc["yscb_root"] = True
    br_cfg_p.write_text(json.dumps(br_doc, indent=2), encoding="utf-8")
    cp_br = _run_yscb_subproc(bad_root_ws, ["status", "--json", "--cold"])
    check(
        cp_br.returncode == 1 and json.loads(cp_br.stdout)["error"]["code"] == "config_invalid",
        f"Non-string yscb_root must fail with config_invalid: {cp_br.stdout}",
    )

    # Trailing empty '@' in package spec must fail with codec_validation_failed (exit code 2)
    out_empty_at = _run_gated_cli_two_step_expect_fail(edge_ws, ["install", "demo@"], expected_rc=2, expected_code="codec_validation_failed")
    check(out_empty_at["ok"] is False)

    # env check on nonexistent module must fail with task_not_found (exit code 3) even when other modules exist
    cp_env_missing = _run_yscb_subproc(edge_ws, ["env", "check", "nonexistent_mod", "--json", "--cold"])
    check(
        cp_env_missing.returncode == 3 and json.loads(cp_env_missing.stdout)["error"]["code"] == "task_not_found",
        f"env check on missing module must return task_not_found: {cp_env_missing.returncode} / {cp_env_missing.stdout}",
    )

    # Foreground daemon console mode via SDK YscbClient must be rejected with EXPOSURE_DENIED
    sdk_edge_cli = YscbClient(HostPath(edge_ws / ".yscb"))
    try:
        fg_out = sdk_edge_cli.call("core.daemon.start", {"console": True, "detach": False})
        check(
            not fg_out.ok and fg_out.error is not None and fg_out.error.code == ErrorCode.EXPOSURE_DENIED,
            f"SDK call to foreground daemon console must fail with EXPOSURE_DENIED: {fg_out}",
        )
    finally:
        sdk_edge_cli.close()

    # Lazy YscbClient workspace binding: construct client BEFORE workspace initialization, then init & verify real disk VFS
    lazy_host = sec_root / "lazy_sdk_host"
    lazy_yscb = lazy_host / ".yscb"
    lazy_yscb.mkdir(parents=True, exist_ok=True)

    class _LazyDiskProbeMod(Module):
        id = "lazydisk"

        @task
        def write_probe(self, ctx: TaskContext) -> str:
            ctx.vfs.write_text(SemanticUri("storage", "lazydisk/hello.txt"), "persisted_ok")
            return ctx.vfs.read_text(SemanticUri("storage", "lazydisk/hello.txt"))

    pre_init_client = YscbClient.local(HostPath(lazy_yscb), _LazyDiskProbeMod())
    try:
        (lazy_host / "yscb.config.json").write_text(
            json.dumps({"yscb_root": ".yscb", "default_provider": "https://releases.ys-codebase.invalid", "installed_modules": {}}, indent=2),
            encoding="utf-8",
        )
        probe_out = pre_init_client.call("lazydisk.write_probe", output_type=str, force_cold=True)
        check(probe_out.ok and probe_out.value == "persisted_ok", f"Lazy SDK probe failed: {probe_out}")
        check(
            (lazy_yscb / "storage" / "lazydisk" / "hello.txt").read_text(encoding="utf-8") == "persisted_ok",
            "Lazy YscbClient must bind to initialized workspace disk VFS rather than staying on MemoryVfsProvider",
        )
    finally:
        pre_init_client.close()

    # Symlinked .cache directory in cli.main must return clean single JSON security_gated without raw traceback
    sym_cache_ws = sec_root / "sym_cache_cli_ws"
    shutil.copytree(edge_ws, sym_cache_ws)
    real_cache_dir = sym_cache_ws / ".yscb" / ".cache"
    outside_cache_dir = sec_root / "outside_cache_target"
    outside_cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(real_cache_dir)
    created_sym_cache = True
    try:
        os.symlink(str(outside_cache_dir), str(real_cache_dir), target_is_directory=True)
    except OSError:
        created_sym_cache = False
    if created_sym_cache:
        out_buf_sc = io.StringIO()
        err_buf_sc = io.StringIO()
        rc_sc = cli_main(
            ["status", "--json", "--cold"],
            host_dir=HostPath(sym_cache_ws),
            yscb_root=HostPath(sym_cache_ws / ".yscb"),
            stdout_stream=out_buf_sc,
            stderr_stream=err_buf_sc,
            install_signal_guard=False,
        )
        doc_sc = json.loads(out_buf_sc.getvalue())
        check(
            rc_sc == 4 and doc_sc["ok"] is False and doc_sc["error"]["code"] == "security_gated",
            f"Symlinked .cache must return structured JSON security_gated: {rc_sc} / {doc_sc}",
        )

    # Control-plane root .cache/tasks.index.json and config/<mod>/ must be rejected by file-lock
    cp_lk_idx = _run_yscb_subproc(
        edge_ws,
        ["file-lock", "lock", str(edge_ws / ".yscb" / ".cache" / "tasks.index.json"), "--json", "--cold"],
    )
    check(
        cp_lk_idx.returncode == 4 and json.loads(cp_lk_idx.stdout)["error"]["code"] == "access_denied",
        f"file-lock must reject root .cache/tasks.index.json: {cp_lk_idx.stdout}",
    )
    demo_cfg_dir = edge_ws / ".yscb" / "config" / "demo"
    demo_cfg_dir.mkdir(parents=True, exist_ok=True)
    demo_cfg_f = demo_cfg_dir / "config.project.json"
    demo_cfg_f.write_text("{}", encoding="utf-8")
    cp_lk_cfg = _run_yscb_subproc(edge_ws, ["file-lock", "lock", str(demo_cfg_f), "--json", "--cold"])
    check(
        cp_lk_cfg.returncode == 4 and json.loads(cp_lk_cfg.stdout)["error"]["code"] == "access_denied",
        f"file-lock must reject config/<mod>/config.project.json: {cp_lk_cfg.stdout}",
    )

    # Concurrent in-flight YscbClient.local task must NOT be drained/unloaded by read-only cold core.status
    hold_entered = threading.Event()
    hold_release = threading.Event()
    close_events: list[str] = []

    class _InFlightProbeMod(Module):
        id = "statefulprobe"

        def on_init(self, env: ModuleEnv) -> None:
            _ = env

        def on_close(self) -> None:
            close_events.append("closed")

        @task
        def hold_open(self, ctx: TaskContext) -> str:
            _ = ctx
            hold_entered.set()
            hold_release.wait(timeout=8.0)
            return "done"

    st_cli = YscbClient.local(HostPath(edge_ws / ".yscb"), _InFlightProbeMod())
    t_hold: Optional[threading.Thread] = None
    try:
        bg_out: list[TaskOutcome[str]] = []
        t_hold = threading.Thread(
            target=lambda: bg_out.append(st_cli.call("statefulprobe.hold_open", output_type=str, force_cold=True))
        )
        t_hold.start()
        check(hold_entered.wait(timeout=5.0), "hold_open failed to enter")
        t0_st = time.monotonic()
        r_core_st = st_cli.call("core.status", force_cold=True)
        elapsed_st = time.monotonic() - t0_st
        check(
            r_core_st.ok and t_hold.is_alive() and elapsed_st < 6.0 and not close_events,
            f"core.status must not drain/unload active module: {elapsed_st}s / alive={t_hold.is_alive()} / {close_events}",
        )
        hold_release.set()
        t_hold.join(timeout=5.0)
        check(len(bg_out) == 1 and bg_out[0].ok and bg_out[0].value == "done")
    finally:
        hold_release.set()
        if t_hold is not None:
            t_hold.join(timeout=5.0)
        st_cli.close()

    # Online daemon must be stopped cleanly by yscb init --fix without NameError or split-brain
    try:
        cp_d_start = _run_yscb_subproc(edge_ws, ["daemon", "start", "--detach", "--json"])
        check(cp_d_start.returncode == 0 and json.loads(cp_d_start.stdout)["ok"] is True, f"daemon start failed: {cp_d_start.stdout}")
        cp_d_stat1 = _run_yscb_subproc(edge_ws, ["daemon", "status", "--json"])
        check(json.loads(cp_d_stat1.stdout)["value"]["data"]["online"] is True, "Expected online daemon before init --fix")
        cp_fix_live = _run_yscb_subproc(edge_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"])
        check(cp_fix_live.returncode == 0 and json.loads(cp_fix_live.stdout)["ok"] is True, f"init --fix failed: {cp_fix_live.stdout}")
        deadline_stop = time.monotonic() + (10.0 if os.name == "nt" else 5.0)
        stopped_after_fix = False
        while time.monotonic() < deadline_stop:
            cp_d_stat2 = _run_yscb_subproc(edge_ws, ["daemon", "status", "--json"])
            if json.loads(cp_d_stat2.stdout)["value"]["data"]["online"] is False:
                stopped_after_fix = True
                break
            time.sleep(0.05)
        check(stopped_after_fix, "yscb init --fix must stop online daemon cleanly via isolated subprocess")
    finally:
        stop_daemon_cleanly(HostPath(edge_ws / ".yscb"))


@dataclass(frozen=True, slots=True)
class _SampleWorkerCfg:
    greeting: str = "initial"


@dataclass(frozen=True, slots=True)
class _LiteralBoolOptIn:
    only_true: Annotated[Literal[True], Option(summary="Must be True")] = True


def _verify_surface_convergence_regressions(sec_root: Path) -> None:
    """Verify worker config reload, transitive SDK disk sync, module-root cli=(), index skip-cache, and pinned init."""
    reg_ws = sec_root / "conv_reg_ws"
    reg_prov = reg_ws / "releases"
    _ = _package_core_release_zip(reg_prov, "2.0.0.0", status="active")
    _ = _package_core_release_zip(reg_prov, "3.0.0.0", status="active")
    reg_ws.mkdir(parents=True, exist_ok=True)

    pre_init_cli = YscbClient.local(HostPath(reg_ws / ".yscb"))
    try:
        pinned_cfg = {
            "yscb_root": ".yscb",
            "default_provider": "./releases",
            "installed_modules": {
                "core": {
                    "version": "2.0.0.0",
                    "provider": "./releases",
                    "installed_at": "2026-11-23T00:00:00Z",
                }
            },
        }
        (reg_ws / "yscb.config.json").write_text(json.dumps(pinned_cfg, indent=2), encoding="utf-8")
        cp_clone_init = _run_yscb_subproc(reg_ws, ["init", "--json"])
        check(
            cp_clone_init.returncode == 0
            and json.loads(cp_clone_init.stdout)["value"]["core_version"] == "2.0.0.0",
            f"Bare yscb init on cloned config must honor pinned 2.0.0.0 instead of jumping to 3.0.0.0: {cp_clone_init.stdout}",
        )
        check(
            json.loads((reg_ws / "yscb.config.json").read_text(encoding="utf-8"))["installed_modules"]["core"]["version"] == "2.0.0.0",
            "Pinned version in yscb.config.json must remain 2.0.0.0",
        )
        st_after_init = pre_init_cli.call("core.status", force_cold=True)
        check(st_after_init.ok, f"YscbClient constructed before init must bind cleanly after init: {st_after_init}")
        mirror_idx_doc = json.loads((reg_ws / ".yscb" / ".mirror" / "core" / "index.json").read_text(encoding="utf-8"))
        check(
            mirror_idx_doc.get("versions") == ["2.0.0.0"] and "3.0.0.0" not in mirror_idx_doc.get("releases", {}),
            f"Local mirror index must only advertise locally cached core archives: {mirror_idx_doc}",
        )
        remote_pinned_cfg = json.loads((reg_ws / "yscb.config.json").read_text(encoding="utf-8"))
        remote_pinned_cfg["default_provider"] = "http://127.0.0.1:9/offline-test"
        remote_pinned_cfg["installed_modules"]["core"]["provider"] = "http://127.0.0.1:9/offline-test"
        (reg_ws / "yscb.config.json").write_text(json.dumps(remote_pinned_cfg, indent=2), encoding="utf-8")
        cp_offline_fix = _run_yscb_subproc(
            reg_ws,
            ["init", "--fix", "--allow-bootstrap-mutation", "--json"],
            extra_env={"YSCB_OFFLINE": "1"},
        )
        check(
            cp_offline_fix.returncode == 0
            and json.loads(cp_offline_fix.stdout)["value"]["core_version"] == "2.0.0.0",
            f"Offline init --fix must resolve cached 2.0.0.0 from .mirror instead of failing on uncached 3.0.0.0: {cp_offline_fix.stdout} {cp_offline_fix.stderr}",
        )
        # Verify offline deterministic auto-restore honors local directory provider when .mirror only has older 2.0.0.0
        local_3_cfg = json.loads((reg_ws / "yscb.config.json").read_text(encoding="utf-8"))
        local_3_cfg["default_provider"] = "./releases"
        local_3_cfg["installed_modules"]["core"]["provider"] = "./releases"
        local_3_cfg["installed_modules"]["core"]["version"] = "3.0.0.0"
        (reg_ws / "yscb.config.json").write_text(json.dumps(local_3_cfg, indent=2), encoding="utf-8")
        shutil.rmtree(reg_ws / ".yscb" / ".modules" / "core")
        cp_local_offline_restore = _run_yscb_subproc(
            reg_ws,
            ["--help", "--json"],
            extra_env={"YSCB_OFFLINE": "1"},
        )
        check(
            cp_local_offline_restore.returncode == 0
            and json.loads((reg_ws / ".yscb" / ".modules" / "core" / "manifest.json").read_text(encoding="utf-8"))["version"] == "3.0.0.0",
            f"Offline deterministic auto-restore must use local filesystem provider ./releases instead of failing on stale .mirror: {cp_local_offline_restore.stdout} {cp_local_offline_restore.stderr}",
        )
        # Verify offline fallback to .mirror when local directory provider is temporarily unavailable
        local_missing_cfg = json.loads((reg_ws / "yscb.config.json").read_text(encoding="utf-8"))
        local_missing_cfg["default_provider"] = "./missing_usb_drive"
        local_missing_cfg["installed_modules"]["core"]["provider"] = "./missing_usb_drive"
        (reg_ws / "yscb.config.json").write_text(json.dumps(local_missing_cfg, indent=2), encoding="utf-8")
        shutil.rmtree(reg_ws / ".yscb" / ".modules" / "core")
        cp_usb_fallback = _run_yscb_subproc(
            reg_ws,
            ["--help", "--json"],
            extra_env={"YSCB_OFFLINE": "1"},
        )
        check(
            cp_usb_fallback.returncode == 0
            and (reg_ws / ".yscb" / ".modules" / "core" / "manifest.json").is_file(),
            f"Unreachable local provider under YSCB_OFFLINE=1 must fall back to cached .mirror: {cp_usb_fallback.stdout} {cp_usb_fallback.stderr}",
        )

        # Verify explicit non-AGENT modes never leak dialect while AGENT env resists human downgrade and beats CI
        for probe_env, exp_mode, exp_dial in (
            ({"CLAUDECODE": "1", "YSCB_CALLER_MODE": "human"}, CallerMode.AGENT, "nouns-claude"),
            ({"CLAUDECODE": "1", "YSCB_CALLER_MODE": "non_tty"}, CallerMode.NON_TTY, None),
            ({"CLAUDECODE": "1", "YSCB_CALLER_MODE": "ci"}, CallerMode.CI_PIPELINE, None),
            ({"ANTIGRAVITY_AGENT": "1", "GITHUB_ACTIONS": "true"}, CallerMode.AGENT, "nouns-antigravity"),
        ):
            det_env = detect_caller_environment(
                env=probe_env,
                stdin_stream=_MockTtyInput(is_tty=True),
                stdout_stream=_MockTtyOutput(is_tty=True),
            )
            check(
                det_env.mode == exp_mode and det_env.dialect == exp_dial,
                f"Expected mode={exp_mode} and dialect={exp_dial} for {probe_env}, got {det_env}",
            )

        cp_upgrade_fix = _run_yscb_subproc(reg_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--provider=./releases", "--json"])
        check(
            cp_upgrade_fix.returncode == 0
            and json.loads(cp_upgrade_fix.stdout)["value"]["core_version"] == "3.0.0.0",
            f"Expected init --fix --provider=./releases to install 3.0.0.0: {cp_upgrade_fix.stdout}",
        )
        merged_mirror_doc = json.loads((reg_ws / ".yscb" / ".mirror" / "core" / "index.json").read_text(encoding="utf-8"))
        check(
            merged_mirror_doc.get("versions") == ["2.0.0.0", "3.0.0.0"]
            and set(merged_mirror_doc.get("releases", {}).keys()) == {"2.0.0.0", "3.0.0.0"},
            f"Upgrading core must preserve previously cached 2.0.0.0 in .mirror/core/index.json: {merged_mirror_doc}",
        )
        (reg_ws / "yscb.config.local.json").write_text(json.dumps({"default_provider": None}), encoding="utf-8")
        shutil.rmtree(reg_ws / ".yscb" / ".modules" / "core")
        cp_null_local = _run_yscb_subproc(reg_ws, ["--help", "--json"])
        check(
            cp_null_local.returncode == 0 and (reg_ws / ".yscb" / ".modules" / "core" / "manifest.json").is_file(),
            f"Null default_provider in yscb.config.local.json must fall back to base provider during core auto-restore instead of stringifying 'None': {cp_null_local.stdout} {cp_null_local.stderr}",
        )
        (reg_ws / "yscb.config.local.json").write_text(json.dumps({"default_provider": True}), encoding="utf-8")
        cp_bool_local = _run_yscb_subproc(reg_ws, ["--help", "--json"])
        check(
            cp_bool_local.returncode == 1
            and json.loads(cp_bool_local.stdout)["error"]["code"] == ErrorCode.CONFIG_INVALID.value,
            f"Boolean default_provider in yscb.config.local.json must fail with config_invalid: {cp_bool_local.stdout}",
        )
        (reg_ws / "yscb.config.local.json").unlink()

        for raw_nonfin in ("Infinity", "-Infinity", "NaN"):
            cp_nf_cfg = _run_yscb_subproc(reg_ws, ["config", "set", "--json", "--cold", "--", "demo", "label", raw_nonfin])
            check(cp_nf_cfg.returncode == 0, f"config set {raw_nonfin} should store string: {cp_nf_cfg.stdout} {cp_nf_cfg.stderr}")
            nf_val = json.loads(cp_nf_cfg.stdout)["value"]["data"]["value"]
            check(nf_val == raw_nonfin, f"Expected string {raw_nonfin!r}, got {nf_val!r}")
    finally:
        pre_init_cli.close()

    host_hp = HostPath(reg_ws)
    root_hp = HostPath(reg_ws / ".yscb")
    worker_fac = build_workspace_module_services_factory(host_hp, root_hp, config_store=None)
    demo_mid = ModuleId("demo")
    cfg_proj = root_hp.path / "config" / "demo" / "config.project.json"
    cfg_proj.parent.mkdir(parents=True, exist_ok=True)
    cfg_proj.write_text(json.dumps({"greeting": "alpha1"}), encoding="utf-8")
    svc_t1 = worker_fac(demo_mid)
    loaded_1 = svc_t1.config_loader(_SampleWorkerCfg)
    check(isinstance(loaded_1, _SampleWorkerCfg) and loaded_1.greeting == "alpha1")
    cfg_proj.write_text(json.dumps({"greeting": "bravo2"}), encoding="utf-8")
    svc_t2 = worker_fac(demo_mid)
    loaded_2 = svc_t2.config_loader(_SampleWorkerCfg)
    check(
        isinstance(loaded_2, _SampleWorkerCfg) and loaded_2.greeting == "bravo2",
        f"Tier 1 worker service factory must reload updated disk config on next turn, got {loaded_2!r}",
    )

    class _NestedMutatorMod(Module):
        id = "nestedmut"
        config_type = _SampleWorkerCfg

        @task
        def mutate_and_done(self, ctx: TaskContext) -> str:
            res = ctx.call(
                "core.config.set",
                {"module": "nestedmut", "key": "greeting", "value": '"updated_via_nested"', "local": False},
            )
            check(res.ok, f"Nested core.config.set failed: {res}")
            return "mutated"

        @task
        def read_greeting(self, ctx: TaskContext) -> str:
            return ctx.load_config(_SampleWorkerCfg).greeting

    with YscbClient.local(root_hp, _NestedMutatorMod()) as nest_cli:
        check(nest_cli.call("nestedmut.read_greeting", output_type=str, force_cold=True).value == "initial")
        check(nest_cli.call("nestedmut.mutate_and_done", output_type=str, force_cold=True).ok)
        after_nest = nest_cli.call("nestedmut.read_greeting", output_type=str, force_cold=True)
        check(
            after_nest.ok and after_nest.value == "updated_via_nested",
            f"Expected transitive nested core.config.set to refresh SDK config view: {after_nest}",
        )

    class _RootDefaultMod(Module):
        id = "quickplan"
        aliases = ("qp",)
        description = "Quick plan module with root default task"

        @task(cli=(), name="overview", summary="Show quickplan overview")
        def overview(self, req: _LiteralBoolOptIn, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return f"overview:{req.only_true}"

        @task(cli="verify", name="verify", summary="Verify plan")
        def verify(self, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return "verified"

    qp_idx = compile_tasks_index(_RootDefaultMod)
    qp_tree = build_cli_command_tree((*WorkspaceKernelFactory.builtin_cli_indices(), qp_idx))
    qp_help = HelpRenderer(CallerMode.HUMAN_TTY).render_node(qp_tree.children["quickplan"])
    check("--no-only-true" not in qp_help and "--only-true" in qp_help, f"Literal[True] must omit --no-only-true: {qp_help}")
    qp_root_res = resolve_cli_invocation(extract_global_flags(("qp",)), (qp_idx,))
    check(
        qp_root_res.task_entry is not None and qp_root_res.task_entry.task_id == TaskId("quickplan.overview"),
        f"Alias 'qp' with no subcommand must dispatch to cli=() default task: {qp_root_res}",
    )
    try:
        _ = resolve_cli_invocation(extract_global_flags(("quickplan", "verfy")), (qp_idx,))
    except YscbError as exc_qp_typo:
        check(exc_qp_typo.detail.code == ErrorCode.CODEC_VALIDATION_FAILED and "Did you mean 'verify'?" in exc_qp_typo.detail.message)
    else:
        raise AssertionError("Unknown subcommand under cli=() module without positional args must be rejected per DN-13")

    try:
        @dataclass(frozen=True, slots=True)
        class _BadMultiUnionDto:
            amount: int | float = 1

        class _BadUnionCliMod(Module):
            id = "badunion"

            @task(cli="run")
            def run(self, req: _BadMultiUnionDto, ctx: TaskContext) -> None:
                _ = (self, req, ctx)
    except ValueError as exc_u:
        check("Union" in str(exc_u), f"Expected multi-type Union CLI rejection: {exc_u}")
    else:
        raise AssertionError("Multi-type Union in CLI DTO must be rejected at definition time")

    corrupt_mod_dir = root_hp.path / ".modules" / "brokenidx"
    corrupt_mod_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_mod_dir / "tasks.index.json").write_text("{corrupt", encoding="utf-8")
    idx_cache = WorkspaceTasksIndexCache(root_hp, builtin_indices=WorkspaceKernelFactory.builtin_cli_indices())
    _ = idx_cache.load_all(force_rebuild=True)
    cache_file = root_hp.path / ".cache" / "tasks.index.json"
    cache_doc = json.loads(cache_file.read_text(encoding="utf-8"))
    check("brokenidx" in cache_doc.get("skipped_modules", []), f"Expected brokenidx in skipped_modules: {cache_doc}")
    mtime_before = cache_file.stat().st_mtime_ns
    time.sleep(0.02)
    _ = idx_cache.load_all(force_rebuild=False)
    mtime_after = cache_file.stat().st_mtime_ns
    check(mtime_before == mtime_after, "Second load_all() with unchanged corrupt module must hit cache without rewriting")

    # 7. Abstract TaskGroup(ABC) rejection, Option.long_name '=' rejection, explicit builtin_indices, and CWD core hijack immunity
    class _AbstractBaseGrp(TaskGroup, ABC):
        pass

    try:
        class _BadAbsGrpMod(Module):
            id = "badabsgrp"
            groups = (_AbstractBaseGrp,)
    except ValueError as exc_abs:
        check("concrete TaskGroup" in str(exc_abs), f"Expected concrete TaskGroup error: {exc_abs}")
    else:
        raise AssertionError("Abstract TaskGroup(ABC) without @abstractmethod must be rejected in Module.groups")

    try:
        _ = Option(long_name="bad=name")
    except ValueError as exc_eq:
        check("=" in str(exc_eq))
    else:
        raise AssertionError("Option(long_name='bad=name') must be rejected")

    uninit_no_core = sec_root / "explicit_builtins_ws"
    (uninit_no_core / ".yscb").mkdir(parents=True, exist_ok=True)
    out_eb = _MockTtyOutput(is_tty=True)
    rc_eb = cli_main(
        ["quickplan", "--help"],
        host_dir=HostPath(uninit_no_core),
        yscb_root=HostPath(uninit_no_core / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
        stdout_stream=out_eb,
        stderr_stream=_MockTtyOutput(is_tty=True),
        builtin_indices=(qp_idx,),
        install_signal_guard=False,
    )
    check(rc_eb == 0 and "Show quickplan overview" in out_eb.getvalue(), "Explicit non-core builtin_indices must not be wiped")

    file_uri_ws = sec_root / "file_uri_loopback_ws"
    file_uri_ws.mkdir(parents=True, exist_ok=True)
    file_loop_uri = reg_prov.resolve().as_uri().replace("file:///", "file://127.0.0.1/")
    cp_f_init = _run_yscb_subproc(file_uri_ws, ["init", f"--provider={file_loop_uri}", "--json"])
    check(cp_f_init.returncode == 0, f"file://127.0.0.1/... provider must be accepted by yscb.py: {cp_f_init.stdout} {cp_f_init.stderr}")

    poison_cwd = sec_root / "poison_cwd_dir"
    (poison_cwd / "core").mkdir(parents=True, exist_ok=True)
    (poison_cwd / "core" / "__init__.py").write_text("raise RuntimeError('CWD_CORE_HIJACKED')\n", encoding="utf-8")
    try:
        cp_d_p = _run_yscb_subproc(file_uri_ws, ["daemon", "start", "--detach", "--json"])
        check(
            cp_d_p.returncode == 0,
            f"daemon start --detach failed: rc={cp_d_p.returncode} out={cp_d_p.stdout} err={cp_d_p.stderr}",
        )
        cp_fix_poison = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-W",
                "error::ResourceWarning",
                str(CORE_V2_ROOT / "yscb.py"),
                f"--host-dir={file_uri_ws}",
                "init",
                "--fix",
                "--allow-bootstrap-mutation",
                "--json",
            ],
            cwd=str(poison_cwd),
            env=_build_sanitized_subproc_env(caller_mode="agent"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        check(cp_fix_poison.returncode == 0, f"init --fix from CWD containing ./core must succeed: {cp_fix_poison.stdout} {cp_fix_poison.stderr}")
        cp_d_after_p = _run_yscb_subproc(file_uri_ws, ["daemon", "status", "--json"])
        check(
            json.loads(cp_d_after_p.stdout)["value"]["data"]["online"] is False,
            "Online daemon must be stopped cleanly even when caller CWD contains a shadowing ./core package",
        )
    finally:
        stop_daemon_cleanly(HostPath(file_uri_ws / ".yscb"))


def run_surface_cli_e2e_suite(tmp_root: Path) -> None:
    """Run all Wave 1.2c CLI, Composition Root, and yscb.py end-to-end checks."""
    suite_dir = tmp_root / "surface_cli_e2e"
    suite_dir.mkdir(parents=True, exist_ok=True)
    _verify_zero_import_help_and_parser(suite_dir)
    _verify_caller_mode_and_security_matrix(suite_dir)
    _verify_yscb_e2e_lifecycle(suite_dir)
    log("[SURFACE-CLI] Verifying yscb.py bootstrapper security and mirror fallback...")
    _verify_yscb_bootstrapper_security_and_mirror_fallback(suite_dir)
    log("[SURFACE-CLI] Verifying hot SDK sync and boundary hardening...")
    _verify_hot_sdk_sync_and_boundary_hardening(suite_dir)
    log("[SURFACE-CLI] Verifying URI scheme provenance and bootstrap edges...")
    _verify_uri_scheme_provenance_and_bootstrap_edges(suite_dir)
    log("[SURFACE-CLI] Verifying surface convergence regressions and Wave 1.2 hardening...")
    _verify_surface_convergence_regressions(suite_dir)
    # Verify option arguments equal to reserved global flags (--json, -h) are preserved as literal values end-to-end
    @dataclass(frozen=True, slots=True)
    class _QueryFilterIn:
        target: Annotated[str, Arg(summary="Target path")]
        query: Annotated[str, Option(short="q", summary="Query string")] = ""

    class _FlagValMod(Module):
        id = "flagval"

        @task(cli="find", name="find", summary="Find matching token")
        def find(self, req: _QueryFilterIn, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return f"q={req.query}|t={req.target}"

    fv_idx = compile_tasks_index(_FlagValMod)
    fv_ws = suite_dir / "flag_val_ws"
    (fv_ws / ".yscb").mkdir(parents=True, exist_ok=True)
    fv_out_1 = _MockTtyOutput(is_tty=True)
    fv_err_1 = _MockTtyOutput(is_tty=True)
    rc_fv_1 = cli_main(
        ["flagval", "find", "--query", "--json", "src/app.py"],
        host_dir=HostPath(fv_ws),
        yscb_root=HostPath(fv_ws / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
        stdout_stream=fv_out_1,
        stderr_stream=fv_err_1,
        kernel_factory=lambda h, y, _fc: WorkspaceKernelFactory.create(
            h,
            y,
            is_daemon_host=False,
            force_cold=True,
            extra_modules=(_FlagValMod().to_yscb_module(),),
        ),
        builtin_indices=(fv_idx,),
        install_signal_guard=False,
    )
    check(
        rc_fv_1 == 0 and fv_out_1.getvalue().strip() == "q=--json|t=src/app.py",
        f"Expected --query --json to bind literal --json in human mode: rc={rc_fv_1}, out={fv_out_1.getvalue()!r}, err={fv_err_1.getvalue()!r}",
    )

    fv_out_2 = _MockTtyOutput(is_tty=True)
    rc_fv_2 = cli_main(
        ["flagval", "find", "-q", "-h", "src/app.py", "--json"],
        host_dir=HostPath(fv_ws),
        yscb_root=HostPath(fv_ws / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
        stdout_stream=fv_out_2,
        stderr_stream=_MockTtyOutput(is_tty=True),
        kernel_factory=lambda h, y, _fc: WorkspaceKernelFactory.create(
            h,
            y,
            is_daemon_host=False,
            force_cold=True,
            extra_modules=(_FlagValMod().to_yscb_module(),),
        ),
        builtin_indices=(fv_idx,),
        install_signal_guard=False,
    )
    check(
        rc_fv_2 == 0 and json.loads(fv_out_2.getvalue()).get("value") == "q=-h|t=src/app.py",
        f"Expected -q -h ... --json to execute task instead of --help: rc={rc_fv_2}, out={fv_out_2.getvalue()!r}",
    )

    # Verify Ctrl+C during interactive security gate prompt returns 130 & structured JSON, single-valued bool Literal[True]/Literal[False] stays required, and TaskGroup cli=() + cli="group" succeeds
    class _SigintTtyInput:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            raise KeyboardInterrupt()

    @dataclass(frozen=True, slots=True)
    class _SingleBoolIn:
        ack: Annotated[Literal[True], Option(short="a", summary="Explicit confirmation")]
        veto: Annotated[Literal[False], Option(short="v", summary="Explicit veto")]

    class _ReusableGroup(TaskGroup):
        @task(cli=(), summary="Default group action")
        def root_act(self, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return "root-ok"

        @task(cli="group", security=SecurityTier.GATED, summary="Subcommand literally named group")
        def sub_group(self, req: _SingleBoolIn, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return f"ack={req.ack}|veto={req.veto}"

    class _UsersMod(Module):
        id = "users"
        groups = (_ReusableGroup,)

    users_idx = compile_tasks_index(_UsersMod)
    users_tree = build_cli_command_tree((users_idx,))
    sub_node = users_tree.children["users"].children["group"]
    help_txt = HelpRenderer(CallerMode.AGENT).render_node(sub_node)
    check(
        "(required)" in help_txt and "(default: false)" not in help_txt,
        f"Single-valued Literal[True]/Literal[False] options without default must render as required: {help_txt!r}",
    )

    # Missing required Literal[True] option must fail static CLI validation before security gate
    miss_ack_err = _MockTtyOutput(is_tty=True)
    rc_miss_ack = cli_main(
        ["users", "group", "--no-veto"],
        host_dir=HostPath(fv_ws),
        yscb_root=HostPath(fv_ws / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=miss_ack_err,
        kernel_factory=lambda h, y, _fc: WorkspaceKernelFactory.create(
            h, y, is_daemon_host=False, force_cold=True, extra_modules=(_UsersMod().to_yscb_module(),)
        ),
        builtin_indices=(users_idx,),
        install_signal_guard=False,
    )
    check(
        rc_miss_ack == 2 and "Missing required option '--ack'" in miss_ack_err.getvalue(),
        f"Expected exit code 2 for missing required --ack: rc={rc_miss_ack}, err={miss_ack_err.getvalue()!r}",
    )

    miss_veto_err = _MockTtyOutput(is_tty=True)
    rc_miss_veto = cli_main(
        ["users", "group", "--ack"],
        host_dir=HostPath(fv_ws),
        yscb_root=HostPath(fv_ws / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_MockTtyInput(is_tty=True, forbid_read=True),
        stdout_stream=_MockTtyOutput(is_tty=True),
        stderr_stream=miss_veto_err,
        kernel_factory=lambda h, y, _fc: WorkspaceKernelFactory.create(
            h, y, is_daemon_host=False, force_cold=True, extra_modules=(_UsersMod().to_yscb_module(),)
        ),
        builtin_indices=(users_idx,),
        install_signal_guard=False,
    )
    check(
        rc_miss_veto == 2 and "Missing required option '--no-veto'" in miss_veto_err.getvalue(),
        f"Expected exit code 2 with '--no-veto' hint for missing Literal[False]: rc={rc_miss_veto}, err={miss_veto_err.getvalue()!r}",
    )

    # Ctrl+C during interactive security gate prompt returns exit code 130 and single TASK_CANCELLED JSON in --json mode
    sigint_json_out = _MockTtyOutput(is_tty=True)
    sigint_json_err = _MockTtyOutput(is_tty=True)
    rc_sigint_json = cli_main(
        ["users", "group", "--ack", "-v", "--json"],
        host_dir=HostPath(fv_ws),
        yscb_root=HostPath(fv_ws / ".yscb"),
        env={"YSCB_TEST_SANDBOX": "1"},
        stdin_stream=_SigintTtyInput(),
        stdout_stream=sigint_json_out,
        stderr_stream=sigint_json_err,
        kernel_factory=lambda h, y, _fc: WorkspaceKernelFactory.create(
            h, y, is_daemon_host=False, force_cold=True, extra_modules=(_UsersMod().to_yscb_module(),)
        ),
        builtin_indices=(users_idx,),
        install_signal_guard=False,
    )
    sigint_doc = json.loads(sigint_json_out.getvalue())
    check(
        rc_sigint_json == 130 and sigint_doc.get("ok") is False and sigint_doc["error"]["code"] == ErrorCode.TASK_CANCELLED.value,
        f"Expected exit 130 + TASK_CANCELLED JSON on security gate SIGINT: rc={rc_sigint_json}, out={sigint_json_out.getvalue()!r}",
    )
    # Cold dynamic space mutation on 'core' refreshes online daemon SpaceRegistry without triggering core handoff
    dyn_hot_kernel = WorkspaceKernelFactory.create(HostPath(fv_ws), HostPath(fv_ws / ".yscb"), is_daemon_host=True)
    dyn_daemon = dyn_hot_kernel.build_daemon(watcher_debounce_sec=0.2, self_restart_argv=None)
    dyn_ready = threading.Event()
    dyn_th = threading.Thread(
        target=lambda: dyn_daemon.run_forever(ready_callback=dyn_ready.set),
        name="test-dyn-space-no-handoff",
        daemon=True,
    )
    dyn_th.start()
    try:
        check(dyn_ready.wait(timeout=5.0), "Hot daemon for dynamic space test failed to reach ready state")
        boot_before = dyn_daemon.snapshot_status().boot_id
        cold_sp_kernel = WorkspaceKernelFactory.create(
            HostPath(fv_ws),
            HostPath(fv_ws / ".yscb"),
            is_daemon_host=False,
            force_cold=True,
        )
        try:
            extra_dir = fv_ws / "extra_tracked"
            extra_dir.mkdir(parents=True, exist_ok=True)
            (extra_dir / "note.txt").write_text("tracked", encoding="utf-8")
            mut_ok = cold_sp_kernel.set_dynamic_space(
                ModuleId("core"),
                "cold_dyn",
                SpaceSpec(
                    space_id=SpaceId("core", "cold_dyn"),
                    entries=(SemanticUri("project", "extra_tracked"),),
                    watch=True,
                ),
            )
            check(mut_ok is True, "Expected set_dynamic_space to report mutation")
        finally:
            cold_sp_kernel.close()
        snap_after = dyn_daemon.snapshot_status()
        check(
            snap_after.boot_id == boot_before and snap_after.state == DaemonRunState.READY,
            f"Cold core dynamic space mutation must refresh online daemon in place without core handoff: {snap_after}",
        )
        hot_space_ids = {str(s.space_id) for s in dyn_hot_kernel.space_registry.list_spaces(owner="core")}
        check(
            "core/cold_dyn" in hot_space_ids,
            f"Expected online daemon SpaceRegistry to observe core/cold_dyn: {hot_space_ids}",
        )
    finally:
        dyn_daemon.request_shutdown(force=True)
        dyn_th.join(timeout=5.0)
        dyn_hot_kernel.close()

    # Managed child WorkspaceKernel refreshes peer workspace config mutations without stale self-short-circuit
    peer_parent_host, peer_parent_root = _init_minimal_workspace(suite_dir / "peer_parent_ws")
    _peer_child_host, peer_child_root = _init_minimal_workspace(suite_dir / "peer_child_ws")
    with YscbClient(peer_child_root) as init_cfg_client:
        init_set = init_cfg_client.call(
            "core.config.set",
            ConfigSetInput(module="core", key="peer_marker", value='"alpha"'),
            force_cold=True,
        )
        check(init_set.ok, f"Initial cold core.config.set failed: {init_set.error}")
    peer_bridge = InMemoryModule("peerbridge")

    def _read_peer_marker(ctx: TaskContext) -> object:
        res = ctx.call(
            "core.config.get",
            ConfigGetInput(module="core", key="peer_marker"),
            output_type=SystemResultView,
            target_workspace=peer_child_root,
            routing_policy=None,
        )
        check(res.ok and res.value is not None, f"Cross-workspace core.config.get failed: {res.error}")
        return res.value.data.get("value") if res.value is not None else None

    peer_bridge.add_task("read_marker", _read_peer_marker)
    parent_k = WorkspaceKernelFactory.create(
        peer_parent_host,
        peer_parent_root,
        is_daemon_host=False,
        force_cold=True,
        extra_modules=(peer_bridge,),
    )
    try:
        first_m = parent_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("peerbridge.read_marker"),
                raw_input={},
                workspace_root=peer_parent_root,
                caller_cwd=peer_parent_host,
            )
        )
        check(first_m.ok and first_m.value == "alpha", f"Expected initial peer_marker 'alpha', got {first_m}")
        with YscbClient(peer_child_root) as mut_cfg_client:
            mut_set = mut_cfg_client.call(
                "core.config.set",
                ConfigSetInput(module="core", key="peer_marker", value='"beta"'),
                force_cold=True,
            )
            check(mut_set.ok, f"Second cold core.config.set failed: {mut_set.error}")
        second_m = parent_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("peerbridge.read_marker"),
                raw_input={},
                workspace_root=peer_parent_root,
                caller_cwd=peer_parent_host,
            )
        )
        check(
            second_m.ok and second_m.value == "beta",
            f"Managed child WorkspaceKernel must detect peer config fingerprint change and reload ('beta'): {second_m}",
        )
    finally:
        parent_k.close()

    # Cold YscbClient call to core.space.on_dynamic_mutated succeeds through _LazySdkKernelPort
    with YscbClient(peer_child_root) as lazy_sdk_client:
        dyn_mut_res = lazy_sdk_client.call(
            "core.space.on_dynamic_mutated",
            output_type=tuple[str, ...],
            force_cold=True,
        )
        check(
            dyn_mut_res.ok and dyn_mut_res.value == (),
            f"Expected cold SDK core.space.on_dynamic_mutated to succeed via _LazySdkKernelPort: {dyn_mut_res}",
        )

    # Foreground deferred daemon exiting during warmup before READY reports DAEMON_UNAVAILABLE (exit 1), never 'already running'
    preready_host, preready_root = _init_minimal_workspace(suite_dir / "preready_exit_ws")
    early_mod_dir = preready_root.path / ".modules" / "earlystop"
    early_mod_dir.mkdir(parents=True, exist_ok=True)
    (early_mod_dir / "manifest.json").write_text(
        json.dumps({"id": "earlystop", "version": "1.0.0.0", "description": "Early stop", "eager_warmup": True}),
        encoding="utf-8",
    )
    (early_mod_dir / "module_entry.py").write_text(
        "import signal\n"
        "from core.surface.sdk import Module, ModuleEnv\n"
        "class EarlyStopMod(Module):\n"
        "    id = 'earlystop'\n"
        "    description = 'Early stop'\n"
        "    def on_init(self, env: ModuleEnv) -> None:\n"
        "        _ = env\n"
        "        signal.raise_signal(signal.SIGTERM)\n"
        "def create_module():\n"
        "    return EarlyStopMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    fg_sub_code = (
        "import sys, core.surface.bootstrap; "
        "from core.foundation import HostPath; "
        "from core.surface.cli import main; "
        "raise SystemExit(main(['daemon', 'start', '--console', '--json'], host_dir=HostPath(sys.argv[1]), yscb_root=HostPath(sys.argv[2])))"
    )
    cp_fg_preready = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            "-W",
            "error::ResourceWarning",
            "-c",
            fg_sub_code,
            str(preready_host),
            str(preready_root),
        ],
        cwd=str(preready_host),
        env=_build_sanitized_subproc_env(
            caller_mode="agent",
            extra_env={"PYTHONPATH": str(CORE_SRC_ROOT), "YSCB_TEST_SANDBOX": "1"},
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15.0,
        check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    check(
        bool(cp_fg_preready.stdout.strip()),
        f"Foreground daemon pre-ready exit produced empty stdout: rc={cp_fg_preready.returncode}, err={cp_fg_preready.stderr!r}",
    )
    fg_doc = json.loads(cp_fg_preready.stdout)
    check(
        cp_fg_preready.returncode == 1
        and fg_doc.get("ok") is False
        and isinstance(fg_doc.get("error"), dict)
        and fg_doc["error"].get("code") == ErrorCode.DAEMON_UNAVAILABLE.value,
        f"Foreground daemon exiting before READY must return exit 1 + DAEMON_UNAVAILABLE, got rc={cp_fg_preready.returncode}, out={cp_fg_preready.stdout!r}, err={cp_fg_preready.stderr!r}",
    )

    # Cross-workspace managed child hits online peer daemon for DAEMON_ONLY tasks and detects .config.local mutations
    hot_peer_host, hot_peer_root = _init_minimal_workspace(suite_dir / "hot_peer_ws")
    hot_peer_mod_dir = hot_peer_root.path / ".modules" / "hotonly"
    hot_peer_mod_dir.mkdir(parents=True, exist_ok=True)
    (hot_peer_mod_dir / "manifest.json").write_text(
        json.dumps({"id": "hotonly", "version": "1.0.0.0", "description": "Hot peer module"}),
        encoding="utf-8",
    )
    (hot_peer_mod_dir / "module_entry.py").write_text(
        "from core.surface.sdk import DispatchMode, Module, TaskContext, task\n"
        "class HotOnlyMod(Module):\n"
        "    id = 'hotonly'\n"
        "    description = 'Hot peer module'\n"
        "    @task(cli='ping', name='ping', summary='Daemon-only ping', dispatch_mode=DispatchMode.DAEMON_ONLY)\n"
        "    def ping(self, ctx: TaskContext) -> str:\n"
        "        _ = self\n"
        "        return 'hot-peer-ok' if ctx.workspace_root else 'missing'\n"
        "def create_module():\n"
        "    return HotOnlyMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    peer_daemon_sub = (
        "import sys, core.surface.bootstrap; "
        "from core.foundation import HostPath; "
        "from core.surface.cli import main; "
        "raise SystemExit(main(['daemon', 'start', '--console', '--json'], host_dir=HostPath(sys.argv[1]), yscb_root=HostPath(sys.argv[2])))"
    )
    peer_d_proc = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            "-c",
            peer_daemon_sub,
            str(hot_peer_host),
            str(hot_peer_root),
        ],
        cwd=str(hot_peer_host),
        env=_build_sanitized_subproc_env(
            caller_mode="agent",
            extra_env={"PYTHONPATH": str(CORE_SRC_ROOT), "YSCB_TEST_SANDBOX": "1"},
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    try:
        peer_ready_line = _readline_subproc_with_timeout(peer_d_proc, timeout_sec=15.0)
        check(bool(peer_ready_line.strip()), "Peer daemon did not emit ready line")
        caller_host, caller_root = _init_minimal_workspace(suite_dir / "caller_for_hot_peer_ws")
        caller_bridge = InMemoryModule("callerbridge")

        def _call_peer_hotonly(ctx: TaskContext) -> str:
            r_hot = ctx.call(
                "hotonly.ping",
                {},
                output_type=str,
                target_workspace=hot_peer_root,
                routing_policy=None,
            )
            check(r_hot.ok and r_hot.executed_hot, f"Expected cross-workspace DAEMON_ONLY task to execute hot: {r_hot}")
            return r_hot.value or ""

        caller_bridge.add_task("call_hot", _call_peer_hotonly)
        caller_k = WorkspaceKernelFactory.create(
            caller_host,
            caller_root,
            is_daemon_host=False,
            force_cold=True,
            extra_modules=(caller_bridge,),
        )
        try:
            hot_out = caller_k.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("callerbridge.call_hot"),
                    raw_input={},
                    workspace_root=caller_root,
                    caller_cwd=caller_host,
                )
            )
            check(hot_out.ok and hot_out.value == "hot-peer-ok", f"Cross-workspace hot call failed: {hot_out}")
        finally:
            caller_k.close()
    finally:
        stop_daemon_cleanly(hot_peer_root)
        _terminate_and_close_subproc(peer_d_proc)

    # Flat workspace topology ('yscb_root': '.') permits file-lock on project files while protecting control-plane files
    flat_ws = suite_dir / "flat_topology_ws"
    flat_ws.mkdir(parents=True, exist_ok=True)
    (flat_ws / "yscb.config.json").write_text(
        json.dumps({"schema_version": 2, "yscb_root": ".", "installed_modules": {}}),
        encoding="utf-8",
    )
    (flat_ws / "docs").mkdir(parents=True, exist_ok=True)
    flat_doc_file = flat_ws / "docs" / "guide.md"
    flat_doc_file.write_text("# Guide\n", encoding="utf-8")
    flat_hp = HostPath(flat_ws)
    flat_lk_out = _MockTtyOutput(is_tty=True)
    rc_flat_lk = cli_main(
        ["file-lock", "lock", str(flat_doc_file), "--json", "--cold"],
        host_dir=flat_hp,
        yscb_root=flat_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=flat_lk_out,
        stderr_stream=_MockTtyOutput(is_tty=False),
        install_signal_guard=False,
    )
    check(rc_flat_lk == 0, f"Flat workspace file-lock on project file must succeed: {flat_lk_out.getvalue()}")
    flat_unlk_s1 = _MockTtyOutput(is_tty=True)
    _ = cli_main(
        ["file-lock", "unlock", str(flat_doc_file), "--json", "--cold"],
        host_dir=flat_hp,
        yscb_root=flat_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=flat_unlk_s1,
        stderr_stream=_MockTtyOutput(is_tty=False),
        install_signal_guard=False,
    )
    unlk_tok = str(json.loads(flat_unlk_s1.getvalue())["error"]["message"]).split("--approve=", 1)[1].split()[0].strip("().")
    flat_unlk_out = _MockTtyOutput(is_tty=True)
    rc_flat_unlk = cli_main(
        ["file-lock", "unlock", str(flat_doc_file), f"--approve={unlk_tok}", "--json", "--cold"],
        host_dir=flat_hp,
        yscb_root=flat_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=flat_unlk_out,
        stderr_stream=_MockTtyOutput(is_tty=False),
        install_signal_guard=False,
    )
    check(rc_flat_unlk == 0, f"Flat workspace file-lock unlock must succeed: {flat_unlk_out.getvalue()}")
    flat_deny_out = _MockTtyOutput(is_tty=True)
    rc_flat_deny = cli_main(
        ["file-lock", "lock", str(flat_ws / "yscb.config.json"), "--json", "--cold"],
        host_dir=flat_hp,
        yscb_root=flat_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=flat_deny_out,
        stderr_stream=_MockTtyOutput(is_tty=False),
        install_signal_guard=False,
    )
    check(
        rc_flat_deny == 4 and json.loads(flat_deny_out.getvalue())["error"]["code"] == ErrorCode.ACCESS_DENIED.value,
        f"Flat workspace file-lock on yscb.config.json must still fail with ACCESS_DENIED: {flat_deny_out.getvalue()}",
    )

    # Verify 'yscb init --fix' repairs corrupt/invalid yscb.config.local.json so subsequent commands succeed
    fix_local_prov = suite_dir / "fix_local_prov"
    _ = _package_core_release_zip(fix_local_prov, "2.0.0.0", status="active")
    fix_local_ws = suite_dir / "fix_local_ws"
    fix_local_ws.mkdir(parents=True, exist_ok=True)
    check(_run_yscb_subproc(fix_local_ws, ["init", f"--provider={fix_local_prov}", "--json"]).returncode == 0)
    (fix_local_ws / "yscb.config.local.json").write_text("[1, 2, 3]", encoding="utf-8")
    cp_broken_loc = _run_yscb_subproc(fix_local_ws, ["status", "--json", "--cold"])
    check(
        cp_broken_loc.returncode == 1 and "yscb.config.local.json" in json.loads(cp_broken_loc.stdout)["error"]["message"],
        f"Expected error message naming yscb.config.local.json: {cp_broken_loc.stdout}",
    )
    check(_run_yscb_subproc(fix_local_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"]).returncode == 0, "init --fix must repair corrupt yscb.config.local.json")
    cp_after_loc_fix = _run_yscb_subproc(fix_local_ws, ["status", "--json", "--cold"])
    check(cp_after_loc_fix.returncode == 0, f"status after init --fix must succeed without infinite loop: {cp_after_loc_fix.stdout}")

    (fix_local_ws / "yscb.config.local.json").write_text(
        json.dumps({"yscb_root": "../escape", "default_provider": True}),
        encoding="utf-8",
    )
    check(_run_yscb_subproc(fix_local_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"]).returncode == 0, "init --fix must sanitize invalid local yscb_root/default_provider")
    check(_run_yscb_subproc(fix_local_ws, ["status", "--json", "--cold"]).returncode == 0, "status after sanitizing local config must succeed")

    # Verify EnvHash human formatting renders plain value without JSON quotes
    eh_txt, eh_rc = format_output(EnvHash("a" * 64))
    check(eh_txt == "a" * 64 and eh_rc == 0, f"Expected unquoted EnvHash text, got {eh_txt!r}")

    # Verify self-update with malformed port URL returns structured JSON failure instead of uncaught ValueError
    cp_bad_port_su = _run_yscb_subproc(
        fix_local_ws,
        ["self-update", "--allow-bootstrap-mutation", "--url=https://example.com:99999/yscb.py", "--json"],
    )
    check(
        cp_bad_port_su.returncode == 1 and json.loads(cp_bad_port_su.stdout).get("ok") is False,
        f"Expected JSON error on malformed self-update port URL: {cp_bad_port_su.returncode} / {cp_bad_port_su.stdout}",
    )

    # Verify cold dynamic space mutation while online daemon is running does NOT self-deadlock on _SPACE_MUTATION_LOCK
    # AND _LazySdkKernelPort materialization does NOT hijack cross-workspace DAEMON_ONLY dispatch
    dyn_sync_host, dyn_sync_root = _init_minimal_workspace(suite_dir / "cold_dyn_space_sync_ws")
    dyn_mod_dir = dyn_sync_root.path / ".modules" / "hotdyn"
    dyn_mod_dir.mkdir(parents=True, exist_ok=True)
    (dyn_mod_dir / "manifest.json").write_text(
        json.dumps({"id": "hotdyn", "version": "1.0.0.0", "description": "Hot dynamic space observer"}),
        encoding="utf-8",
    )
    (dyn_mod_dir / "module_entry.py").write_text(
        "from core.surface.sdk import DispatchMode, Module, SPACE_REGISTRY_CHANGED_EVENT, SpaceUpdatedEventPayload, TaskContext, on_event, task\n"
        "_SPACE_EV = SPACE_REGISTRY_CHANGED_EVENT\n"
        "def _first_space_ev(items: tuple[SpaceUpdatedEventPayload, ...]):\n"
        "    return items[0] if items else None\n"
        "class HotDynMod(Module):\n"
        "    id = 'hotdyn'\n"
        "    description = 'Hot dynamic space observer'\n"
        "    def __init__(self) -> None:\n"
        "        self.seen: list[str] = []\n"
        "    @on_event(_SPACE_EV, mapper=_first_space_ev)\n"
        "    @task(name='on_space', summary='Record dynamic space change')\n"
        "    def on_space(self, req: SpaceUpdatedEventPayload, ctx: TaskContext) -> None:\n"
        "        _ = ctx\n"
        "        self.seen.extend(req.spaces)\n"
        "    @task(cli='spaces', name='spaces', summary='List seen spaces', dispatch_mode=DispatchMode.DAEMON_ONLY)\n"
        "    def spaces(self, ctx: TaskContext) -> list[str]:\n"
        "        _ = ctx\n"
        "        return list(self.seen)\n"
        "def create_module():\n"
        "    return HotDynMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    dyn_d_proc = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            "-c",
            peer_daemon_sub,
            str(dyn_sync_host),
            str(dyn_sync_root),
        ],
        cwd=str(dyn_sync_host),
        env=_build_sanitized_subproc_env(
            caller_mode="agent",
            extra_env={"PYTHONPATH": str(CORE_SRC_ROOT), "YSCB_TEST_SANDBOX": "1"},
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    try:
        check(bool(_readline_subproc_with_timeout(dyn_d_proc, timeout_sec=15.0).strip()), "HotDyn daemon did not start")
        sdk_dyn_cli = YscbClient(dyn_sync_root)
        try:
            st_out = sdk_dyn_cli.call("core.daemon.status", {})
            check(st_out.ok, f"Expected core.daemon.status via SDK to succeed: {st_out}")

            peer_caller_h, peer_caller_r = _init_minimal_workspace(suite_dir / "peer_caller_not_hijacked_ws")
            peer_caller_mod = InMemoryModule("peercheck")

            def _invoke_hotdyn_spaces(ctx: TaskContext) -> list[str]:
                res_hd = ctx.call(
                    "hotdyn.spaces",
                    {},
                    output_type=list[str],
                    target_workspace=dyn_sync_root,
                    routing_policy=None,
                )
                check(res_hd.ok and res_hd.executed_hot, f"Expected cross-workspace DAEMON_ONLY hot execution: {res_hd}")
                return list(res_hd.value or ())

            peer_caller_mod.add_task("query", _invoke_hotdyn_spaces)
            peer_caller_k = WorkspaceKernelFactory.create(
                peer_caller_h,
                peer_caller_r,
                is_daemon_host=False,
                force_cold=True,
                extra_modules=(peer_caller_mod,),
            )
            try:
                mut_mod = InMemoryModule("dynmut")

                def _do_cold_dyn_set(ctx: TaskContext) -> bool:
                    spec_obj = SpaceSpec(
                        space_id=SpaceId("dynmut", "live"),
                        entries=(SemanticUri("storage", "dynmut"),),
                    )
                    out_set = ctx.call(
                        "core.space.set_dynamic",
                        DataclassCodec.encode_object(
                            SetDynamicSpaceInput(owner=ModuleId("dynmut"), name="live", spec=spec_obj)
                        ),
                        output_type=bool,
                        routing_policy=ClientRoutingPolicy.FORCE_COLD,
                    )
                    check(out_set.ok and out_set.value is True, f"Cold set_dynamic failed: {out_set}")
                    return True

                mut_mod.add_task("mutate", _do_cold_dyn_set)
                cold_mut_k = WorkspaceKernelFactory.create(
                    dyn_sync_host,
                    dyn_sync_root,
                    is_daemon_host=False,
                    force_cold=True,
                    extra_modules=(mut_mod,),
                )
                try:
                    t_start = time.monotonic()
                    m_out = cold_mut_k.dispatcher.invoke(
                        InvokeRequest(
                            task_id=TaskId("dynmut.mutate"),
                            raw_input={},
                            workspace_root=dyn_sync_root,
                            caller_cwd=dyn_sync_host,
                            routing_policy=ClientRoutingPolicy.FORCE_COLD,
                        )
                    )
                    elapsed_dyn = time.monotonic() - t_start
                    max_dyn_sec = 4.5 if os.name == "nt" else 1.8
                    check(m_out.ok and elapsed_dyn < max_dyn_sec, f"Cold set_dynamic self-deadlocked ({elapsed_dyn:.2f}s): {m_out}")
                finally:
                    cold_mut_k.close()

                q_out = peer_caller_k.dispatcher.invoke(
                    InvokeRequest(
                        task_id=TaskId("peercheck.query"),
                        raw_input={},
                        workspace_root=peer_caller_r,
                        caller_cwd=peer_caller_h,
                    )
                )
                poll_dl = time.monotonic() + (5.0 if os.name == "nt" else 2.0)
                while q_out.ok and q_out.value != ["dynmut/live"] and time.monotonic() < poll_dl:
                    time.sleep(0.05)
                    q_out = peer_caller_k.dispatcher.invoke(
                        InvokeRequest(
                            task_id=TaskId("peercheck.query"),
                            raw_input={},
                            workspace_root=peer_caller_r,
                            caller_cwd=peer_caller_h,
                        )
                    )
                check(
                    q_out.ok and q_out.value == ["dynmut/live"],
                    f"Online daemon did not receive deferred cold dynamic space sync or was hijacked: {q_out}",
                )
            finally:
                peer_caller_k.close()
        finally:
            sdk_dyn_cli.close()
    finally:
        stop_daemon_cleanly(dyn_sync_root)
        _terminate_and_close_subproc(dyn_d_proc)

    # Verify flat workspace narrowing project_root auto-unlocks former project readonly file & CLI unlock works,
    # while project_root='!undefined' still blocks non-core modules and host_dir.parent config_binding is rejected
    narrow_ws = suite_dir / "flat_narrow_proj_ws"
    narrow_ws.mkdir(parents=True, exist_ok=True)
    (narrow_ws / "yscb.config.json").write_text(
        json.dumps({"yscb_root": ".", "default_provider": "./prov", "installed_modules": {}}),
        encoding="utf-8",
    )
    (narrow_ws / "docs").mkdir(parents=True, exist_ok=True)
    (narrow_ws / "app").mkdir(parents=True, exist_ok=True)
    narrow_doc = narrow_ws / "docs" / "legacy.md"
    narrow_doc.write_text("# Legacy\n", encoding="utf-8")
    narrow_hp = HostPath(narrow_ws)
    nk1 = WorkspaceKernelFactory.create(narrow_hp, narrow_hp, force_cold=True)
    try:
        _ = nk1.set_dynamic_space(
            ModuleId("core"),
            "readonly",
            SpaceSpec(space_id=SpaceId("core", "readonly"), entries=(SemanticUri("yscb.host", "docs"),)),
        )
        check(nk1.readonly_policy.is_os_readonly(HostPath(narrow_doc)) is True, "Expected core/readonly to lock legacy.md")
    finally:
        nk1.close()

    (narrow_ws / "config" / "core").mkdir(parents=True, exist_ok=True)
    (narrow_ws / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": "!undefined"}),
        encoding="utf-8",
    )
    nk2 = WorkspaceKernelFactory.create(narrow_hp, narrow_hp, force_cold=True)
    try:
        check(
            nk2.is_reserved_control_plane_path(HostPath(narrow_doc), owner="rogue", allow_any_module_storage=False) is True,
            "Flat workspace with project_root='!undefined' must reject non-core module access to host subtrees",
        )
        _ = nk2.clear_dynamic_spaces(ModuleId("core"))
        check(
            nk2.readonly_policy.is_os_readonly(HostPath(narrow_doc)) is False,
            "Cross-process core/readonly removal must symmetrically unlock previously managed file",
        )
    finally:
        nk2.close()

    # Verify non-core config_binding to host_dir.parent in separated workspace is rejected
    sep_parent = suite_dir / "sep_escape_container"
    sep_host = sep_parent / "ctrl_host"
    sep_yscb = sep_parent / "var_yscb"
    sep_proj = sep_parent / "app_proj"
    sep_host.mkdir(parents=True, exist_ok=True)
    sep_yscb.mkdir(parents=True, exist_ok=True)
    sep_proj.mkdir(parents=True, exist_ok=True)
    (sep_host / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": str(sep_yscb),
                "default_provider": "./prov",
                "installed_modules": {
                    "escmod": {"version": "1.0.0.0", "provider": "./prov", "installed_at": "2026-11-23T00:00:00Z"}
                },
            }
        ),
        encoding="utf-8",
    )
    (sep_yscb / "config" / "core").mkdir(parents=True, exist_ok=True)
    (sep_yscb / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": str(sep_proj)}),
        encoding="utf-8",
    )
    (sep_yscb / "config" / "escmod").mkdir(parents=True, exist_ok=True)
    (sep_yscb / "config" / "escmod" / "config.project.json").write_text(
        json.dumps({"bind_dir": str(sep_parent)}),
        encoding="utf-8",
    )
    esc_mod_dir = sep_yscb / ".modules" / "escmod"
    (esc_mod_dir / "contributes").mkdir(parents=True, exist_ok=True)
    (esc_mod_dir / "manifest.json").write_text(
        json.dumps({"id": "escmod", "version": "1.0.0.0", "description": "Escape probe"}),
        encoding="utf-8",
    )
    (esc_mod_dir / "config.schema.json").write_text(
        json.dumps({"type": "object", "properties": {"bind_dir": {"type": "string"}}}),
        encoding="utf-8",
    )
    (esc_mod_dir / "contributes" / "core.json").write_text(
        json.dumps({"uri_schemes": {"esc.parent": {"token": "esc.parent", "config_binding": "escmod.bind_dir"}}}),
        encoding="utf-8",
    )
    (esc_mod_dir / "module_entry.py").write_text(
        "from core.surface.sdk import Module\n"
        "class EscMod(Module):\n"
        "    id = 'escmod'\n"
        "    description = 'Escape probe'\n"
        "def create_module():\n"
        "    return EscMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    sep_k = WorkspaceKernelFactory.create(HostPath(sep_host), HostPath(sep_yscb), force_cold=True)
    try:
        sep_schemes = {entry.scheme for entry in sep_k.mount_table.check_health()}
        check("esc.parent" not in sep_schemes, f"Non-core config_binding to host_dir.parent must be rejected: {sep_schemes}")
    finally:
        sep_k.close()

    # Verify configurable template stripping rejects trailing dot/space ('foo..tmpl') in yscb.py init
    bad_tmpl_prov = suite_dir / "bad_tmpl_prov"
    (bad_tmpl_prov / "core").mkdir(parents=True, exist_ok=True)
    bad_tmpl_zip = bad_tmpl_prov / "core" / "2.0.0.0.zip"
    with zipfile.ZipFile(bad_tmpl_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core"}))
        zf.writestr("core/__init__.py", "")
        zf.writestr("configurable/bad..tmpl", "{}")
    bad_tmpl_sha = hashlib.sha256(bad_tmpl_zip.read_bytes()).hexdigest()
    (bad_tmpl_prov / "core" / "index.json").write_text(
        json.dumps({"module_id": "core", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"version": "2.0.0.0", "status": "active", "yanked": False, "sha256": bad_tmpl_sha, "filename": "2.0.0.0.zip"}}}),
        encoding="utf-8",
    )
    bad_tmpl_ws = suite_dir / "bad_tmpl_ws"
    bad_tmpl_ws.mkdir(parents=True, exist_ok=True)
    cp_bad_tmpl = _run_yscb_subproc(bad_tmpl_ws, ["init", f"--provider={bad_tmpl_prov}", "--json"])
    check(cp_bad_tmpl.returncode != 0, f"Expected bad..tmpl configurable template to be rejected: {cp_bad_tmpl.stdout}")

    # Verify yscb init --fix heals corrupt yscb.config.json + unknown/null/broken yscb.config.local.json
    # and ConfigStore.load_host_config() succeeds cleanly afterward
    fix_heal_prov = suite_dir / "fix_heal_prov"
    _ = _package_core_release_zip(fix_heal_prov, "2.0.0.0", status="active")
    fix_heal_ws = suite_dir / "fix_heal_ws"
    fix_heal_ws.mkdir(parents=True, exist_ok=True)
    (fix_heal_ws / "yscb.config.json").write_text(
        json.dumps(
            {
                "schema_version": "corrupt",
                "unknown_extra_key": 123,
                "yscb_root": ".yscb",
                "default_provider": "http://198.51.100.10/insecure",
                "installed_modules": {"broken_mod": 99},
            }
        ),
        encoding="utf-8",
    )
    (fix_heal_ws / "yscb.config.local.json").write_text(
        json.dumps(
            {
                "extra_local_key": True,
                "default_provider": "http://198.51.100.20/insecure",
            }
        ),
        encoding="utf-8",
    )
    cp_fix_heal = _run_yscb_subproc(fix_heal_ws, ["init", "--fix", "--allow-bootstrap-mutation", f"--provider={fix_heal_prov}", "--json"])
    check(cp_fix_heal.returncode == 0, f"Expected yscb init --fix to heal corrupt host & local config: {cp_fix_heal.stdout} {cp_fix_heal.stderr}")
    healed_store = ConfigStore(host_dir=HostPath(fix_heal_ws), yscb_root=HostPath(fix_heal_ws / ".yscb"))
    healed_cfg = healed_store.load_host_config()
    check("core" in [m.value for m in healed_cfg.installed_modules.keys()], "Expected healed HostConfig to decode cleanly")

    # Verify --host-dir pointing to an existing regular file fails with exit_code=4 (security_gated)
    host_as_file = suite_dir / "not_a_dir.txt"
    host_as_file.write_text("regular file", encoding="utf-8")
    cp_file_host = _run_yscb_subproc(suite_dir, [f"--host-dir={host_as_file}", "init", "--json"])
    check(
        cp_file_host.returncode == 4
        and json.loads(cp_file_host.stdout)["error"]["code"] == "security_gated",
        f"Expected --host-dir=<regular_file> to fail with security_gated (4): {cp_file_host.stdout}",
    )

    # Verify non-core module can mount custom URI scheme onto storage://{module} even when project_root='!undefined'
    own_data_ws = suite_dir / "own_data_mount_ws"
    own_data_ws.mkdir(parents=True, exist_ok=True)
    own_data_root = own_data_ws / ".yscb"
    own_data_root.mkdir(parents=True, exist_ok=True)
    (own_data_ws / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": ".yscb",
                "default_provider": "./prov",
                "installed_modules": {
                    "datamod": {"version": "1.0.0.0", "provider": "./prov", "installed_at": "2026-11-23T00:00:00Z"}
                },
            }
        ),
        encoding="utf-8",
    )
    (own_data_root / "config" / "core").mkdir(parents=True, exist_ok=True)
    (own_data_root / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": "!undefined"}),
        encoding="utf-8",
    )
    dm_dir = own_data_root / ".modules" / "datamod"
    (dm_dir / "contributes").mkdir(parents=True, exist_ok=True)
    (dm_dir / "manifest.json").write_text(
        json.dumps({"id": "datamod", "version": "1.0.0.0", "description": "Data mount probe"}),
        encoding="utf-8",
    )
    (dm_dir / "contributes" / "core.json").write_text(
        json.dumps({"uri_schemes": {"datamod.store": {"token": "datamod.store", "target_uri": "storage://@/items"}}}),
        encoding="utf-8",
    )
    (dm_dir / "module_entry.py").write_text(
        "from core.surface.sdk import Module\n"
        "class DataMod(Module):\n"
        "    id = 'datamod'\n"
        "    description = 'Data mount probe'\n"
        "def create_module():\n"
        "    return DataMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    dm_k = WorkspaceKernelFactory.create(HostPath(own_data_ws), HostPath(own_data_root), force_cold=True)
    try:
        dm_schemes = {entry.scheme for entry in dm_k.mount_table.check_health()}
        check("datamod.store" in dm_schemes, f"Expected module-owned storage:// URI scheme allowed under project_root='!undefined': {dm_schemes}")
    finally:
        dm_k.close()

    # Verify CliOptionSpec rejects invalid type_name or non-numeric int choices on tasks.index.json load
    for bad_opt_doc in (
        {"field": "x", "long_name": "x", "short": None, "type": "unknown_tp", "required": False},
        {"field": "x", "long_name": "x", "short": None, "type": "int", "required": False, "choices": ["abc"]},
    ):
        try:
            _ = CliOptionSpec.from_json_dict(bad_opt_doc)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected CliOptionSpec.from_json_dict to reject {bad_opt_doc}")

    # Verify Sequence[str] variadic CLI Arg, Mapping[str, str] SDK task input, render_task_help module prefix,
    # and cross-workspace file-lock isolation against foreign module storage
    @dataclass(frozen=True, slots=True)
    class _SeqCliInput:
        items: Annotated[Sequence[str], Arg(summary="Variadic sequence items")]
        tags: Annotated[Optional[Mapping[str, str]], Option(summary="Tag mapping")] = None

    class _SeqCliMod(Module):
        id = "seqmod"
        description = "Sequence CLI probe"

        @task(cli=("collect",), summary="Collect sequence items")
        def collect(self, req: _SeqCliInput, ctx: TaskContext) -> list[str]:
            _ = (self, ctx, req.tags)
            return list(req.items)

        @task(name="map_echo")
        def map_echo(self, req: Mapping[str, str], ctx: TaskContext) -> dict[str, str]:
            _ = (self, ctx)
            return dict(req)

    seq_idx = compile_tasks_index(_SeqCliMod)
    collect_entry = next(t for t in seq_idx.tasks if t.command_path == ("collect",))
    check(
        len(collect_entry.args) == 1 and collect_entry.args[0].is_variadic and collect_entry.args[0].type_name == "list[str]",
        f"Expected Sequence[str] Arg to compile as variadic list[str], got {collect_entry.args}",
    )
    check(
        any(o.field == "tags" and o.type_name == "dict" for o in collect_entry.options),
        f"Expected Mapping[str, str] Option to compile as dict, got {collect_entry.options}",
    )
    rendered_leaf = render_task_help(collect_entry)
    check(
        "Usage: yscb seqmod collect" in rendered_leaf,
        f"Expected render_task_help to include non-core module prefix 'seqmod': {rendered_leaf}",
    )

    victim_store_file = own_data_root / "storage" / "datamod" / "secret.json"
    victim_store_file.parent.mkdir(parents=True, exist_ok=True)
    victim_store_file.write_text('{"k": 1}\n', encoding="utf-8")
    atk_host_hp, atk_root_hp = _init_minimal_workspace(suite_dir / "xws_atk_ws")
    xws_attacker = InMemoryModule("attacker")

    def _xws_lock_attack(ctx: TaskContext) -> bool:
        out_lk = ctx.call(
            "core.file_lock.lock",
            {"paths": [str(victim_store_file)]},
            target_workspace=HostPath(own_data_root),
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
        )
        check(not out_lk.ok and out_lk.error is not None and out_lk.error.code == ErrorCode.SECURITY_GATED)
        out_st = ctx.call(
            "core.file_lock.status",
            {"path": str(victim_store_file)},
            target_workspace=HostPath(own_data_root),
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
        )
        if not out_st.ok and out_st.error is not None:
            raise YscbError(out_st.error.code, out_st.error.message)
        return True

    xws_attacker.add_task("attack_lock", _xws_lock_attack)
    fk_attack = WorkspaceKernelFactory.create(
        atk_host_hp,
        atk_root_hp,
        force_cold=True,
        extra_modules=(xws_attacker,),
    )
    try:
        atk_out = fk_attack.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("attacker.attack_lock"),
                raw_input={},
                workspace_root=atk_root_hp,
                caller_cwd=atk_host_hp,
            )
        )
        check(
            not atk_out.ok and atk_out.error is not None and atk_out.error.code == ErrorCode.ACCESS_DENIED,
            f"Expected cross-workspace core.file_lock.lock on victim module storage to fail with ACCESS_DENIED: {atk_out}",
        )
    finally:
        fk_attack.close()

    # Bootstrap CLI flag routing, double-dash handling, NaN rejection, SemVer4 health check, and symlinked .cache/daemon protection
    boot_chk_ws = suite_dir / "boot_hardening_ws"
    boot_prov = boot_chk_ws / "releases"
    _ = _package_core_release_zip(boot_prov, "2.0.0.0", status="active")
    boot_chk_ws.mkdir(parents=True, exist_ok=True)
    cp_bad_pre = _run_yscb_subproc(boot_chk_ws, ["--bogus-flag", "init", "--json"])
    check(
        cp_bad_pre.returncode == 2 and json.loads(cp_bad_pre.stdout)["error"]["code"] == "codec_validation_failed",
        f"Expected --bogus-flag init to fail with exit 2 codec_validation_failed: {cp_bad_pre.returncode} {cp_bad_pre.stdout}",
    )
    cp_dd_extra = _run_yscb_subproc(boot_chk_ws, ["init", "--provider", "./releases", "--json", "--", "unexpected"])
    check(
        cp_dd_extra.returncode == 2 and json.loads(cp_dd_extra.stdout)["error"]["code"] == "codec_validation_failed",
        f"Expected positional after -- in init to fail with exit 2: {cp_dd_extra.returncode} {cp_dd_extra.stdout}",
    )
    cp_dd_clean = _run_yscb_subproc(boot_chk_ws, ["init", "--provider", "./releases", "--json", "--"])
    check(cp_dd_clean.returncode == 0 and json.loads(cp_dd_clean.stdout)["ok"] is True, f"init -- failed: {cp_dd_clean.stdout}")

    # Malformed config.project.json schema repaired by init --fix
    core_proj_f = boot_chk_ws / ".yscb" / "config" / "core" / "config.project.json"
    core_proj_f.write_text('{"unrelated": 1}\n', encoding="utf-8")
    cp_fix_proj = _run_yscb_subproc(boot_chk_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--json"])
    check(cp_fix_proj.returncode == 0, f"init --fix failed: {cp_fix_proj.stdout}")
    check(
        json.loads(core_proj_f.read_text(encoding="utf-8")).get("project_root") == "./",
        "Expected init --fix to repair config.project.json missing project_root",
    )

    # Non-standard NaN in yscb.config.json must be rejected cleanly
    (boot_chk_ws / "yscb.config.json").write_text('{"yscb_root": ".yscb", "nan_field": NaN}\n', encoding="utf-8")
    cp_nan_cfg = _run_yscb_subproc(boot_chk_ws, ["status", "--json", "--cold"])
    check(
        cp_nan_cfg.returncode == 1 and json.loads(cp_nan_cfg.stdout)["error"]["code"] == "config_invalid",
        f"Expected NaN in yscb.config.json to fail with config_invalid: {cp_nan_cfg.returncode} {cp_nan_cfg.stdout}",
    )
    _ = _run_yscb_subproc(boot_chk_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--provider", "./releases", "--json"])

    # Invalid non-SemVer4 version string matching between config and manifest must NOT pass _is_installed_core_healthy
    bad_ver_cfg = json.loads((boot_chk_ws / "yscb.config.json").read_text(encoding="utf-8"))
    bad_ver_cfg["installed_modules"]["core"]["version"] = "not-a-semver"
    (boot_chk_ws / "yscb.config.json").write_text(json.dumps(bad_ver_cfg, indent=2), encoding="utf-8")
    core_mf_p = boot_chk_ws / ".yscb" / ".modules" / "core" / "manifest.json"
    orig_mf_txt = core_mf_p.read_text(encoding="utf-8")
    bad_mf_doc = json.loads(orig_mf_txt)
    bad_mf_doc["version"] = "not-a-semver"
    core_mf_p.write_text(json.dumps(bad_mf_doc, indent=2), encoding="utf-8")
    cp_bad_sv = _run_yscb_subproc(boot_chk_ws, ["status", "--json", "--cold"])
    check(cp_bad_sv.returncode != 0, "Expected non-SemVer4 core version to fail health check")
    core_mf_p.write_text(orig_mf_txt, encoding="utf-8")
    _ = _run_yscb_subproc(boot_chk_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--provider", "./releases", "--json"])

    # Symlinked .cache/daemon must NOT unlink external daemon.json during init --fix
    ext_daemon_dir = suite_dir / "ext_daemon_target"
    ext_daemon_dir.mkdir(parents=True, exist_ok=True)
    ext_ep_file = ext_daemon_dir / "daemon.json"
    ext_ep_file.write_text('{"pid": 99999999, "port": 1}\n', encoding="utf-8")
    ws_daemon_dir = boot_chk_ws / ".yscb" / ".cache" / "daemon"
    if ws_daemon_dir.exists():
        shutil.rmtree(ws_daemon_dir)
    ws_daemon_dir.parent.mkdir(parents=True, exist_ok=True)
    symlink_supported = True
    try:
        os.symlink(ext_daemon_dir, ws_daemon_dir, target_is_directory=True)
    except OSError:
        symlink_supported = False
    if symlink_supported:
        try:
            cp_sym_ep = _run_yscb_subproc(boot_chk_ws, ["init", "--fix", "--allow-bootstrap-mutation", "--provider", "./releases", "--json"])
            check(cp_sym_ep.returncode != 0, "Expected init --fix to abort when .cache/daemon is a symlink")
            check(ext_ep_file.is_file(), "External daemon.json through symlinked .cache/daemon must NEVER be unlinked")
        finally:
            ws_daemon_dir.unlink(missing_ok=True)

    # Retired mount table unlocks OS read-only file when external project_root is repointed
    ext_proj_a = suite_dir / "ext_proj_a"
    ext_proj_b = suite_dir / "ext_proj_b"
    ext_proj_a.mkdir(parents=True, exist_ok=True)
    ext_proj_b.mkdir(parents=True, exist_ok=True)
    ext_ro_file = ext_proj_a / "locked_asset.txt"
    ext_ro_file.write_text("asset", encoding="utf-8")
    mt_host_hp, mt_root_hp = _init_minimal_workspace(suite_dir / "retired_mt_ws")
    (mt_root_hp.path / "config" / "core").mkdir(parents=True, exist_ok=True)
    (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": str(ext_proj_a)}),
        encoding="utf-8",
    )
    fk_mt = WorkspaceKernelFactory.create(mt_host_hp, mt_root_hp, force_cold=True)
    try:
        _ = fk_mt.set_dynamic_space(
            ModuleId("core"),
            "readonly",
            SpaceSpec(space_id=SpaceId("core", "readonly"), entries=(SemanticUri.parse("project://locked_asset.txt"),)),
        )
        check(fk_mt.readonly_policy.is_os_readonly(HostPath(ext_ro_file)), "Expected external project file to be locked read-only")
        (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
            json.dumps({"project_root": str(ext_proj_b)}),
            encoding="utf-8",
        )
        _ = fk_mt.clear_dynamic_spaces(ModuleId("core"), "readonly", sync=False)
        _ = fk_mt.reload_config_only(())
        _ = fk_mt.sync_gitignore_and_readonly()
        check(
            not fk_mt.readonly_policy.is_os_readonly(HostPath(ext_ro_file)),
            "Expected retired mount table to unlock read-only file in former external project_root",
        )
    finally:
        fk_mt.close()

    # Cross-process persisted managed_roots unlock + .yscb/subproj !undefined unlock
    ext_ro_xproc = ext_proj_a / "xproc_locked.txt"
    ext_ro_xproc.write_text("xproc", encoding="utf-8")
    (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": str(ext_proj_a)}),
        encoding="utf-8",
    )
    fk_mt1 = WorkspaceKernelFactory.create(mt_host_hp, mt_root_hp, force_cold=True)
    try:
        _ = fk_mt1.set_dynamic_space(
            ModuleId("core"),
            "readonly",
            SpaceSpec(space_id=SpaceId("core", "readonly"), entries=(SemanticUri.parse("project://xproc_locked.txt"),)),
        )
        check(fk_mt1.readonly_policy.is_os_readonly(HostPath(ext_ro_xproc)), "Expected xproc file locked")
    finally:
        fk_mt1.close()

    (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": str(ext_proj_b)}),
        encoding="utf-8",
    )
    fk_mt2 = WorkspaceKernelFactory.create(mt_host_hp, mt_root_hp, force_cold=True)
    try:
        _ = fk_mt2.clear_dynamic_spaces(ModuleId("core"), "readonly", sync=False)
        _ = fk_mt2.sync_gitignore_and_readonly()
        check(
            not fk_mt2.readonly_policy.is_os_readonly(HostPath(ext_ro_xproc)),
            "Expected persisted managed_roots to unlock former external project_root file across fresh kernel instances",
        )
    finally:
        fk_mt2.close()

    subproj_dir = mt_root_hp.path / "subproj"
    subproj_dir.mkdir(parents=True, exist_ok=True)
    subproj_ro = subproj_dir / "doc.txt"
    subproj_ro.write_text("doc", encoding="utf-8")
    (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
        json.dumps({"project_root": str(subproj_dir)}),
        encoding="utf-8",
    )
    fk_mt3 = WorkspaceKernelFactory.create(mt_host_hp, mt_root_hp, force_cold=True)
    try:
        _ = fk_mt3.set_dynamic_space(
            ModuleId("submod"),
            "readonly",
            SpaceSpec(space_id=SpaceId("submod", "readonly"), entries=(SemanticUri.parse("project://doc.txt"),)),
        )
        check(fk_mt3.readonly_policy.is_os_readonly(HostPath(subproj_ro)), "Expected .yscb/subproj file locked")
        (mt_root_hp.path / "config" / "core" / "config.project.json").write_text(
            json.dumps({"project_root": "!undefined"}),
            encoding="utf-8",
        )
        _ = fk_mt3.clear_dynamic_spaces(ModuleId("submod"), "readonly", sync=False)
        _ = fk_mt3.reload_config_only(())
        _ = fk_mt3.sync_gitignore_and_readonly()
        check(
            not fk_mt3.readonly_policy.is_os_readonly(HostPath(subproj_ro)),
            "Expected .yscb/subproj read-only file to unlock cleanly when project_root becomes !undefined",
        )
    finally:
        fk_mt3.close()

    # CLI non-str/constrained option followed by --help, missing-arg --json purity, and -- terminator non-swallowing
    cp_opt_help = _run_yscb_subproc(boot_chk_ws, ["config", "set", "--scope", "--help", "--json", "--cold"])
    check(
        cp_opt_help.returncode == 0 and "help" in json.loads(cp_opt_help.stdout)["value"],
        f"Expected 'config set --scope --help' to render help instead of swallowing --help: {cp_opt_help.returncode} {cp_opt_help.stdout}",
    )
    cp_opt_json = _run_yscb_subproc(boot_chk_ws, ["install", "--provider", "--json", "--cold"])
    check(
        cp_opt_json.returncode == 2 and json.loads(cp_opt_json.stdout)["error"]["code"] == "codec_validation_failed",
        f"Expected 'install --provider --json' to preserve JSON output on parse error: {cp_opt_json.returncode} {cp_opt_json.stdout} {cp_opt_json.stderr}",
    )
    cp_opt_dd = _run_yscb_subproc(boot_chk_ws, ["install", "--provider", "--", "demo", "--json", "--cold"])
    check(
        cp_opt_dd.returncode == 2,
        f"Expected 'install --provider -- demo' to reject missing --provider value: {cp_opt_dd.returncode}",
    )

    # Deep relative --yscb-root (>= 6 levels) discovered by YscbClient
    deep_ws = suite_dir / "deep_anc_ws"
    deep_ws.mkdir(parents=True, exist_ok=True)
    cp_deep_init = _run_yscb_subproc(
        deep_ws,
        ["init", "--provider", str(boot_prov), "--yscb-root=l1/l2/l3/l4/l5/.yscb", "--json"],
    )
    check(cp_deep_init.returncode == 0, f"Deep yscb_root init failed: {cp_deep_init.stdout}")
    deep_root_hp = HostPath(deep_ws / "l1" / "l2" / "l3" / "l4" / "l5" / ".yscb")
    deep_cli = YscbClient.local(deep_root_hp)
    try:
        deep_st = deep_cli.call("core.status", force_cold=True)
        check(
            deep_st.ok and isinstance(deep_st.value, dict) and deep_st.value.get("data", {}).get("host_dir") == str(HostPath(deep_ws)),
            f"Expected YscbClient to discover host_dir across 6 ancestor levels: {deep_st}",
        )
    finally:
        deep_cli.close()

    # Security error vs transport_lost classification on self-update
    cp_su_sec = _run_yscb_subproc(boot_chk_ws, ["self-update", "--allow-bootstrap-mutation", "--url=http://192.0.2.1:8080/yscb.py", "--json"])
    check(
        cp_su_sec.returncode == 4 and json.loads(cp_su_sec.stdout)["error"]["code"] == "security_gated",
        f"Expected non-loopback HTTP self-update to return security_gated (4): {cp_su_sec.returncode} {cp_su_sec.stdout}",
    )
    cp_su_net = _run_yscb_subproc(boot_chk_ws, ["self-update", "--allow-bootstrap-mutation", "--url=http://127.0.0.1:9/yscb.py", "--json"])
    check(
        cp_su_net.returncode == 1 and json.loads(cp_su_net.stdout)["error"]["code"] == "transport_lost",
        f"Expected unreachable loopback self-update to return transport_lost (1): {cp_su_net.returncode} {cp_su_net.stdout}",
    )

    # Reserved global flag & duplicate option rejection in CliOptionSpec / IndexedTaskEntry deserialization
    for bad_long, bad_short in (("help", None), ("json", None), ("cold", None), ("approve", None), ("host-dir", None), ("ok", "h")):
        try:
            _ = CliOptionSpec(field="bad", long_name=bad_long, short=bad_short, type_name="str", required=False)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected CliOptionSpec to reject reserved flag long={bad_long!r} short={bad_short!r}")

    try:
        _ = IndexedTaskEntry(
            task_id=TaskId("demo.dup"),
            command_path=("dup",),
            aliases=(),
            summary="dup",
            usage_pros=(),
            usage_cons=(),
            exposure=TaskExposure.CLI_AND_SDK,
            security_tier=SecurityTier.SAFE,
            dispatch_mode=DispatchMode.HYBRID,
            interactive_tty=False,
            options=(
                CliOptionSpec(field="a", long_name="flag", short=None, type_name="bool", required=False),
                CliOptionSpec(field="b", long_name="no-flag", short=None, type_name="str", required=False),
            ),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected IndexedTaskEntry to reject --no-flag collision with boolean --flag")

    # Fast-idempotency init path returns security_gated (4) when yscb_root traverses parent directory
    sec_idem_ws = suite_dir / "sec_idem_ws"
    sec_idem_ws.mkdir(parents=True, exist_ok=True)
    (sec_idem_ws / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": "../escaped_root",
                "default_provider": str(boot_prov),
                "installed_modules": {
                    "core": {"version": "2.0.0.0", "provider": str(boot_prov), "installed_at": "2026-11-22T00:00:00Z"}
                },
            }
        ),
        encoding="utf-8",
    )
    cp_sec_idem = _run_yscb_subproc(sec_idem_ws, ["init", "--json"])
    check(
        cp_sec_idem.returncode == 4 and json.loads(cp_sec_idem.stdout)["error"]["code"] == "security_gated",
        f"Expected parent-traversing yscb_root on init idempotency check to return security_gated (4): {cp_sec_idem.returncode} {cp_sec_idem.stdout}",
    )

    # YscbClient SDK core.install & core.update with @on_migrate (shared installer.lock lease, zero self-deadlock)
    sdk_mig_ws = suite_dir / "sdk_mig_ws"
    sdk_mig_prov = sdk_mig_ws / "releases"
    _ = _package_core_release_zip(sdk_mig_prov, "2.0.0.0", status="active")
    _package_demo_module_zip(sdk_mig_prov, "1.0.0.0")
    sdk_mig_ws.mkdir(parents=True, exist_ok=True)
    cp_sdk_mig_init = _run_yscb_subproc(sdk_mig_ws, ["init", "--provider", str(sdk_mig_prov), "--json"])
    check(cp_sdk_mig_init.returncode == 0, f"sdk_mig_ws init failed: {cp_sdk_mig_init.stdout}")
    sdk_mig_root = HostPath(sdk_mig_ws / ".yscb")
    sdk_mig_cli = YscbClient.local(sdk_mig_root)
    try:
        inst_res = sdk_mig_cli.call(
            "core.install",
            {"specs": ["demo"], "provider": str(sdk_mig_prov)},
            force_cold=True,
            approval_scope=frozenset({TaskId("core.install")}),
        )
        check(inst_res.ok, f"YscbClient core.install demo 1.0.0.0 failed: {inst_res}")
        _package_demo_module_zip(sdk_mig_prov, "1.1.0.0")
        upd_res = sdk_mig_cli.call(
            "core.update",
            {"modules": ["demo"], "provider": str(sdk_mig_prov)},
            force_cold=True,
            approval_scope=frozenset({TaskId("core.update")}),
        )
        check(upd_res.ok, f"YscbClient core.update demo 1.1.0.0 with @on_migrate deadlocked or failed: {upd_res}")
        info_res = sdk_mig_cli.call("demo.info", force_cold=True)
        check(
            info_res.ok and isinstance(info_res.value, dict) and info_res.value.get("migrated") == "1.0.0.0->1.1.0.0",
            f"Expected demo @on_migrate to run during YscbClient core.update: {info_res}",
        )
    finally:
        sdk_mig_cli.close()

    # Worker service factory parity: @ placeholder uri_schemes, ReadonlyPolicy, project contributes fp & hot lazy on_init locale isolation
    wk_par_ws = suite_dir / "wk_parity_ws"
    wk_par_ws.mkdir(parents=True, exist_ok=True)
    cp_wk_init = _run_yscb_subproc(wk_par_ws, ["init", "--provider", str(boot_prov), "--json"])
    check(cp_wk_init.returncode == 0, f"wk_parity_ws init failed: {cp_wk_init.stdout}")
    wk_host_hp = HostPath(wk_par_ws)
    wk_root_hp = HostPath(wk_par_ws / ".yscb")
    wmod_dir = wk_root_hp.path / ".modules" / "wmod"
    (wmod_dir / "contributes").mkdir(parents=True, exist_ok=True)
    (wmod_dir / "locales").mkdir(parents=True, exist_ok=True)
    (wmod_dir / "manifest.json").write_text(
        json.dumps({"id": "wmod", "version": "1.0.0.0", "description": "Worker parity mod", "dependencies": {"core": ">=2.0.0"}}),
        encoding="utf-8",
    )
    (wmod_dir / "module_entry.py").write_text("pass\n", encoding="utf-8")
    (wmod_dir / "contributes" / "core.json").write_text(
        json.dumps(
            {
                "uri_schemes": {
                    "wdata": {"target_uri": "storage.local://@/sub", "description": "Valid module placeholder scheme"},
                    "wbad": {"target_uri": "yscb://.modules", "description": "Forbidden control-plane scheme"},
                },
                "spaces": {
                    "readonly": {"entries": ["project://locked_dir"], "include": ["*.lock"]},
                },
                "locales": {"en": "locales/en.json", "zh-tw": "locales/zh-tw.json"},
            }
        ),
        encoding="utf-8",
    )
    (wmod_dir / "locales" / "en.json").write_text(json.dumps({"wmod.hi": "Hello EN"}), encoding="utf-8")
    (wmod_dir / "locales" / "zh-tw.json").write_text(json.dumps({"wmod.hi": "Hello ZHTW"}), encoding="utf-8")
    (wk_par_ws / "locked_dir").mkdir(parents=True, exist_ok=True)

    wk_svc_fac = build_workspace_module_services_factory(wk_host_hp, wk_root_hp)
    wmod_svc = wk_svc_fac(ModuleId("wmod"))
    wmod_svc.vfs.write_text(SemanticUri.parse("wdata://note.txt"), "ok-placeholder")
    check(
        (wk_root_hp.path / ".storage.local" / "wmod" / "sub" / "note.txt").read_text(encoding="utf-8") == "ok-placeholder",
        "Expected Tier 1 worker service factory to bind '@' placeholder in contributed uri_schemes",
    )
    try:
        _ = wmod_svc.vfs.read_bytes(SemanticUri.parse("wbad://manifest.json"))
    except YscbError as exc_wbad:
        check(exc_wbad.detail.code in (ErrorCode.URI_UNDEFINED, ErrorCode.ACCESS_DENIED), f"Unexpected code: {exc_wbad}")
    else:
        raise AssertionError("Expected forbidden contributed target_uri yscb:// to be rejected in worker services")

    try:
        wmod_svc.vfs.write_text(SemanticUri.parse("project://locked_dir/uncreated.lock"), "blocked")
    except YscbError as exc_wro:
        check(exc_wro.detail.code == ErrorCode.READONLY_VIOLATION, f"Expected READONLY_PROTECTED, got {exc_wro}")
    else:
        raise AssertionError("Expected worker ReadonlyPolicy to block writes to uncreated file in <mod>/readonly space")

    proj_contrib_dir = wk_root_hp.path / "config" / "core"
    proj_contrib_dir.mkdir(parents=True, exist_ok=True)
    (proj_contrib_dir / "contribute.json").write_text(
        json.dumps({"uri_schemes": {"pdocs": {"target_uri": "project://docs"}}}),
        encoding="utf-8",
    )
    wmod_svc_after = wk_svc_fac(ModuleId("wmod"))
    wmod_svc_after.vfs.write_text(SemanticUri.parse("pdocs://readme.txt"), "from-proj-contrib")
    check((wk_par_ws / "docs" / "readme.txt").read_text(encoding="utf-8") == "from-proj-contrib")

    # Hot container lazy on_init(env) locale isolation from first caller's YSCB_LOCALE
    seen_init_locales: list[str] = []

    class _HotLazyLocMod(Module):
        id = "wmod"

        def on_init(self, env: ModuleEnv) -> None:
            _ = self
            seen_init_locales.append(env.locale.translate("wmod.hi", caller_module=ModuleId("wmod")))

        @task
        def ping(self, ctx: TaskContext) -> str:
            _ = self
            return ctx.locale.translate("wmod.hi", caller_module=ModuleId("wmod"))

    hot_k = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        is_daemon_host=True,
        force_cold=False,
        extra_modules=(_HotLazyLocMod().to_yscb_module(),),
    )
    try:
        hot_k.dispatcher.warmup_daemon_container()
        hot_out1 = hot_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("wmod.ping"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
                caller_env={"YSCB_LOCALE": "zh-tw"},
            )
        )
        check(hot_out1.ok and hot_out1.value == "Hello ZHTW", f"Expected per-step zh-tw locale, got {hot_out1}")
        check(
            seen_init_locales == ["Hello EN"],
            f"Expected hot container lazy on_init(env) to use workspace default locale 'Hello EN', got {seen_init_locales}",
        )
    finally:
        hot_k.close()

    # Verify core.file_lock.status (path=None) hides foreign module storage:// files from non-core callers
    fl_iso_kernel = WorkspaceKernelFactory.create(wk_host_hp, wk_root_hp, force_cold=True)
    try:
        sec_other = wk_root_hp.path / "storage" / "victim" / "secret.txt"
        sec_other.parent.mkdir(parents=True, exist_ok=True)
        sec_other.write_text("top-secret", encoding="utf-8")
        _ = fl_iso_kernel.set_dynamic_space(
            ModuleId("victim"),
            "readonly",
            SpaceSpec(space_id=SpaceId("victim", "readonly"), entries=(SemanticUri.parse("storage://victim"),)),
        )

        class _PeekLockMod(Module):
            id = "peeker"

            @task
            def peek_all(self, ctx: TaskContext) -> object:
                _ = self
                res_p = ctx.call(TaskId("core.file_lock.status"), {})
                return res_p.value

        peek_kernel = WorkspaceKernelFactory.create(
            wk_host_hp,
            wk_root_hp,
            force_cold=True,
            extra_modules=(_PeekLockMod().to_yscb_module(),),
        )
        try:
            out_peek = peek_kernel.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("peeker.peek_all"),
                    raw_input={},
                    workspace_root=wk_root_hp,
                    caller_cwd=wk_host_hp,
                    routing_policy=ClientRoutingPolicy.FORCE_COLD,
                )
            )
            check(out_peek.ok and isinstance(out_peek.value, dict), f"peek_all failed: {out_peek}")
            peek_files = out_peek.value.get("data", {}).get("files", [])
            check(
                all("victim" not in str(item.get("path", "")) for item in peek_files if isinstance(item, dict)),
                f"Expected foreign storage://victim readonly files hidden from peeker module: {peek_files}",
            )
        finally:
            peek_kernel.close()
    finally:
        fl_iso_kernel.close()

    # Verify nested non-core caller cannot hijack core.project_root, read/write foreign module config, or wipe foreign fs.clean
    sec_cfg_dir = wk_root_hp.path / ".config.local" / "victim"
    sec_cfg_dir.mkdir(parents=True, exist_ok=True)
    (sec_cfg_dir / "config.local.json").write_text(json.dumps({"api_token": "secret-token-xyz"}), encoding="utf-8")

    class _SandboxProbeMod(Module):
        id = "sbprobe"

        @task
        def run_checks(self, ctx: TaskContext) -> str:
            _ = self
            r_hijack = ctx.call(
                TaskId("core.config.set"),
                {"module": "core", "key": "project_root", "value": '"/tmp"', "local": False},
            )
            check(
                not r_hijack.ok and r_hijack.error is not None and r_hijack.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module mutates core.project_root: {r_hijack}",
            )
            r_foreign_set = ctx.call(
                TaskId("core.config.set"),
                {"module": "victim", "key": "api_token", "value": '"pwned"', "local": True},
            )
            check(
                not r_foreign_set.ok and r_foreign_set.error is not None and r_foreign_set.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module mutates sibling config: {r_foreign_set}",
            )
            r_foreign_get = ctx.call(
                TaskId("core.config.get"),
                {"module": "victim", "key": "api_token"},
            )
            check(
                not r_foreign_get.ok and r_foreign_get.error is not None and r_foreign_get.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module reads sibling .config.local secret: {r_foreign_get}",
            )
            r_list_all = ctx.call(TaskId("core.config.list"), {})
            check(
                not r_list_all.ok and r_list_all.error is not None and r_list_all.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module dumps all module configs: {r_list_all}",
            )
            r_clean_all = ctx.call(TaskId("core.fs.clean"), {})
            check(
                not r_clean_all.ok and r_clean_all.error is not None and r_clean_all.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module cleans all workspace spaces: {r_clean_all}",
            )
            r_clean_foreign = ctx.call(TaskId("core.fs.clean"), {"space_id": "core/readonly"})
            check(
                not r_clean_foreign.ok and r_clean_foreign.error is not None and r_clean_foreign.error.code == ErrorCode.ACCESS_DENIED,
                f"Expected ACCESS_DENIED when non-core module cleans foreign space: {r_clean_foreign}",
            )
            r_own_set = ctx.call(
                TaskId("core.config.set"),
                {"module": "sbprobe", "key": "note", "value": '"allowed"', "local": True},
            )
            check(r_own_set.ok, f"Expected own-module config.set to remain allowed: {r_own_set}")
            r_own_get = ctx.call(
                TaskId("core.config.get"),
                {"module": "sbprobe", "key": "note"},
            )
            check(r_own_get.ok, f"Expected own-module config.get to succeed: {r_own_get}")
            r_own_clean = ctx.call(
                TaskId("core.fs.clean"),
                {"space_id": "sbprobe/cache", "consumer": "sbprobe"},
            )
            check(r_own_clean.ok, f"Expected own-module fs.clean to succeed: {r_own_clean}")
            return "sandbox-ok"

    sb_kernel = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        force_cold=True,
        extra_modules=(_SandboxProbeMod().to_yscb_module(),),
    )
    try:
        _ = sb_kernel.set_dynamic_space(
            ModuleId("sbprobe"),
            "cache",
            SpaceSpec(space_id=SpaceId("sbprobe", "cache"), entries=(SemanticUri.parse("storage.local://sbprobe"),)),
        )
        sb_out = sb_kernel.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("sbprobe.run_checks"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(sb_out.ok and sb_out.value == "sandbox-ok", f"Sandbox probe failed: {sb_out}")
    finally:
        sb_kernel.close()

    # Verify cold WorkspaceKernel(dialect=...) preserves dialect when caller_env overrides YSCB_LOCALE, while daemon stays neutral
    (wmod_dir / "contributes" / "core.json").write_text(
        json.dumps(
            {
                "locales": {
                    "en": "locales/en.json",
                    "zh-tw": "locales/zh-tw.json",
                    "nouns-claude": "locales/nouns-claude.json",
                }
            }
        ),
        encoding="utf-8",
    )
    (wmod_dir / "locales" / "en.json").write_text(
        json.dumps({"wmod.banner": "{wmod.agent_noun}: EN"}),
        encoding="utf-8",
    )
    (wmod_dir / "locales" / "zh-tw.json").write_text(
        json.dumps({"wmod.banner": "{wmod.agent_noun}: ZHTW", "wmod.agent_noun": "GenericAgent"}),
        encoding="utf-8",
    )
    (wmod_dir / "locales" / "nouns-claude.json").write_text(
        json.dumps({"wmod.agent_noun": "ClaudeSubagent"}),
        encoding="utf-8",
    )

    class _DialectCheckMod(Module):
        id = "wmod"

        @task
        def banner(self, ctx: TaskContext) -> str:
            _ = self
            return ctx.locale.translate("wmod.banner", caller_module=ModuleId("wmod"))

    cold_dial_k = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        is_daemon_host=False,
        force_cold=True,
        dialect="nouns-claude",
        extra_modules=(_DialectCheckMod().to_yscb_module(),),
    )
    try:
        cold_dial_out = cold_dial_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("wmod.banner"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
                caller_env={"YSCB_LOCALE": "zh-tw"},
            )
        )
        check(
            cold_dial_out.ok and cold_dial_out.value == "ClaudeSubagent: ZHTW",
            f"Expected cold WorkspaceKernel(dialect='claude') + YSCB_LOCALE='zh-tw' to preserve dialect noun: {cold_dial_out}",
        )
    finally:
        cold_dial_k.close()

    hot_dial_k = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        is_daemon_host=True,
        force_cold=False,
        dialect="nouns-claude",
        extra_modules=(_DialectCheckMod().to_yscb_module(),),
    )
    try:
        hot_dial_k.dispatcher.warmup_daemon_container()
        hot_dial_out = hot_dial_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("wmod.banner"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
                caller_env={"YSCB_LOCALE": "zh-tw"},
            )
        )
        check(
            hot_dial_out.ok and hot_dial_out.value == "GenericAgent: ZHTW",
            f"Expected daemon WorkspaceKernel to remain dialect-neutral even with YSCB_LOCALE='zh-tw': {hot_dial_out}",
        )
    finally:
        hot_dial_k.close()

    # Verify Tier 0 disk module writing stdout noise and raising SystemExit on import does not crash CLI or pollute JSON stdout
    badexit_dir = wk_root_hp.path / ".modules" / "badexit"
    badexit_dir.mkdir(parents=True, exist_ok=True)
    (badexit_dir / "manifest.json").write_text(
        json.dumps({"id": "badexit", "version": "1.0.0.0", "description": "Bad exit Tier 0 module"}),
        encoding="utf-8",
    )
    (badexit_dir / "module_entry.py").write_text(
        "import sys\nsys.stdout.write('IMPORT_STDOUT_POLLUTION\\n')\nraise SystemExit(7)\n",
        encoding="utf-8",
    )
    clean_json_out = _MockTtyOutput(is_tty=False)
    rc_badexit_cli = cli_main(
        ["uri", "list", "--json", "--cold"],
        host_dir=wk_host_hp,
        yscb_root=wk_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False, forbid_read=True),
        stdout_stream=clean_json_out,
        stderr_stream=_MockTtyOutput(is_tty=False),
        install_signal_guard=False,
    )
    parsed_clean_doc = json.loads(clean_json_out.getvalue())
    check(
        rc_badexit_cli == 0 and parsed_clean_doc.get("ok") is True and "IMPORT_STDOUT_POLLUTION" not in clean_json_out.getvalue(),
        f"Expected broken SystemExit Tier 0 module not to crash CLI or pollute JSON stdout: {clean_json_out.getvalue()!r}",
    )

    # Verify weakref GC cleanup on _LocaleGetterDialectRegistry, .cache/wheels protection, bare dict CLI option, Enum format_output, and custom locale fingerprint
    def _bind_ephemeral_dialect() -> None:
        def _ephemeral_getter() -> object:
            return object()

        bind_locale_getter_dialect(_ephemeral_getter, wk_root_hp, "nouns-ephemeral", is_daemon_host=False, register_cold_root=True)
        check(lookup_cold_workspace_dialect(wk_root_hp) == "nouns-ephemeral")

    _bind_ephemeral_dialect()
    gc.collect()
    check(lookup_cold_workspace_dialect(wk_root_hp) is None, "Expected GC'd getter dialect to auto-purge from cold workspace stack")

    wheel_cand = HostPath(wk_root_hp.path / ".cache" / "wheels" / "demo-1.0.whl")
    proj_store_cand = HostPath(wk_root_hp.path / "storage" / "project" / "data.json")
    check(
        is_control_plane_reserved_path(
            wheel_cand,
            yscb_root=wk_root_hp,
            host_dir=wk_host_hp,
            project_root=wk_host_hp,
            allow_any_module_storage=True,
        ),
        "Expected .cache/wheels/*.whl to remain reserved even under allow_any_module_storage=True",
    )
    check(
        is_control_plane_reserved_path(
            proj_store_cand,
            yscb_root=wk_root_hp,
            host_dir=wk_host_hp,
            project_root=wk_host_hp,
            allow_any_module_storage=True,
        ),
        "Expected storage/project/* to remain reserved even under allow_any_module_storage=True",
    )

    class _SampleOutState(Enum):
        READY = "ready-state"

    enum_txt, enum_rc = format_output(_SampleOutState.READY)
    check(enum_txt == "ready-state" and enum_rc == 0, f"Expected Enum format_output to render value 'ready-state', got {enum_txt!r}")

    @dataclass(frozen=True, slots=True)
    class _BareDictCliDto:
        note: Annotated[str, Option(summary="Arbitrary note")] = ""
        meta: Annotated[dict, Option(summary="Bare dict payload")] = field(default_factory=dict)

    class _BareDictCliMod(Module):
        id = "baredict"

        @task(cli="send", name="send", summary="Send bare dict")
        def send(self, req: _BareDictCliDto, ctx: TaskContext) -> str:
            _ = (self, ctx)
            return json.dumps(req.meta, sort_keys=True)

    bd_idx = compile_tasks_index(_BareDictCliMod)
    bd_inv = resolve_cli_invocation(
        extract_global_flags(("baredict", "send", "--meta", '{"k": 7}')),
        (bd_idx,),
    )
    check(bd_inv.normalized_input.get("meta") == {"k": 7}, f"Expected bare dict CLI option to parse JSON object: {bd_inv}")

    # Verify '--note --json --unknown-flag' emits human error to stderr rather than false-positive JSON stdout
    (wk_root_hp.path / ".modules" / "baredict").mkdir(parents=True, exist_ok=True)
    (wk_root_hp.path / ".modules" / "baredict" / "manifest.json").write_text(
        json.dumps({"id": "baredict", "version": "1.0.0.0", "description": "Bare dict CLI mod"}),
        encoding="utf-8",
    )
    (wk_root_hp.path / ".modules" / "baredict" / "tasks.index.json").write_text(
        json.dumps(bd_idx.to_json_dict()),
        encoding="utf-8",
    )
    opt_val_out = _MockTtyOutput(is_tty=True)
    opt_val_err = _MockTtyOutput(is_tty=True)
    rc_opt_val = cli_main(
        ["baredict", "send", "--note=--json", "--unknown-flag"],
        host_dir=wk_host_hp,
        yscb_root=wk_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "human_tty"},
        stdin_stream=_MockTtyInput(is_tty=True),
        stdout_stream=opt_val_out,
        stderr_stream=opt_val_err,
        builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
        install_signal_guard=False,
    )
    check(
        rc_opt_val != 0 and opt_val_out.getvalue() == "" and "Error [" in opt_val_err.getvalue(),
        f"Expected human error on stderr when '--json' is an option value: out={opt_val_out.getvalue()!r} err={opt_val_err.getvalue()!r}",
    )

    # Verify custom core.locales relative path (i18n/en.json) invalidates service factory fingerprint on edit
    (wmod_dir / "i18n").mkdir(parents=True, exist_ok=True)
    (wmod_dir / "i18n" / "en.json").write_text(json.dumps({"wmod.custom": "v1"}), encoding="utf-8")
    (wmod_dir / "contributes" / "core.json").write_text(
        json.dumps({"locales": {"en": "i18n/en.json"}}),
        encoding="utf-8",
    )
    i18n_fac = build_workspace_module_services_factory(wk_host_hp, wk_root_hp)
    check(i18n_fac(ModuleId("wmod")).locale.translate("wmod.custom", caller_module=ModuleId("wmod")) == "v1")
    (wmod_dir / "i18n" / "en.json").write_text(json.dumps({"wmod.custom": "v2-updated"}), encoding="utf-8")
    check(
        i18n_fac(ModuleId("wmod")).locale.translate("wmod.custom", caller_module=ModuleId("wmod")) == "v2-updated",
        "Expected custom core.locales path i18n/en.json edit to invalidate surface fingerprint",
    )

    # Verify non-core module cannot invoke control-plane mutations or lock project:// files
    proj_victim_f = wk_par_ws / "docs" / "proj_target.txt"
    proj_victim_f.parent.mkdir(parents=True, exist_ok=True)
    proj_victim_f.write_text("data", encoding="utf-8")

    class _CtrlGuardMod(Module):
        id = "ctrlguard"

        @task
        def verify_denied(self, ctx: TaskContext) -> str:
            _ = self
            for bad_tid, bad_in in (
                ("core.daemon.stop", {"force": True}),
                ("core.reload", {}),
                ("core.file_lock.sync", {}),
                ("core.gitignore.sync", {}),
                ("core.file_lock.lock", {"path": str(proj_victim_f)}),
            ):
                r_bad = ctx.call(TaskId(bad_tid), bad_in)
                check(
                    not r_bad.ok and r_bad.error is not None and r_bad.error.code == ErrorCode.ACCESS_DENIED,
                    f"Expected ACCESS_DENIED for non-core nested {bad_tid}, got {r_bad}",
                )
            return "ctrl-denied-ok"

    cg_k = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        force_cold=True,
        extra_modules=(_CtrlGuardMod().to_yscb_module(),),
    )
    try:
        cg_out = cg_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("ctrlguard.verify_denied"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                allow_conditional=True,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(cg_out.ok and cg_out.value == "ctrl-denied-ok", f"Control-plane guard verification failed: {cg_out}")
    finally:
        cg_k.close()

    # Verify cold Tier 1 dialect isolation across multi-kernel same-workspace coexistence and cross-workspace managed child kernels
    _peer_dial_host_hp, peer_dial_root_hp = _init_minimal_workspace(suite_dir / "peer_dial_ws")

    wheel_house_dir = wk_par_ws.parent / "dial_wheels"
    wheel_house_dir.mkdir(parents=True, exist_ok=True)
    whl_path = wheel_house_dir / "dummy_dial_pkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(whl_path, "w", compression=zipfile.ZIP_DEFLATED) as wf:
        wf.writestr("dummy_dial_pkg/__init__.py", "MARKER = 1\n")
        wf.writestr(
            "dummy_dial_pkg-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: dummy-dial-pkg\nVersion: 1.0.0\n",
        )
        wf.writestr(
            "dummy_dial_pkg-1.0.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wf.writestr("dummy_dial_pkg-1.0.0.dist-info/RECORD", "")
    wheel_house_hp = HostPath(wheel_house_dir)

    def _provision_tier1_dialect_mod(target_root_hp: HostPath) -> None:
        t1_dir = target_root_hp.path / ".modules" / "t1dial"
        (t1_dir / "contributes").mkdir(parents=True, exist_ok=True)
        (t1_dir / "locales").mkdir(parents=True, exist_ok=True)
        (t1_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "t1dial",
                    "version": "1.0.0.0",
                    "description": "Tier 1 dialect probe",
                    "venv_group": "t1dial_grp",
                    "pip_dependencies": {"dummy-dial-pkg": "==1.0.0"},
                }
            ),
            encoding="utf-8",
        )
        (t1_dir / "contributes" / "core.json").write_text(
            json.dumps(
                {
                    "locales": {
                        "definition": "locales/definition.json",
                        "en": "locales/en.json",
                        "zh-tw": "locales/zh-TW.json",
                        "nouns-claude": "locales/nouns-claude.json",
                    }
                }
            ),
            encoding="utf-8",
        )
        (t1_dir / "locales" / "definition.json").write_text(
            json.dumps({"t1dial.agent": "GenericAgent", "t1dial.greeting": "EN"}),
            encoding="utf-8",
        )
        (t1_dir / "locales" / "en.json").write_text(
            json.dumps({"t1dial.agent": "GenericAgent", "t1dial.greeting": "EN"}),
            encoding="utf-8",
        )
        (t1_dir / "locales" / "zh-TW.json").write_text(
            json.dumps({"t1dial.greeting": "ZHTW"}),
            encoding="utf-8",
        )
        (t1_dir / "locales" / "nouns-claude.json").write_text(
            json.dumps({"t1dial.agent": "ClaudeSubagent"}),
            encoding="utf-8",
        )
        (t1_dir / "module_entry.py").write_text(
            "from core.surface.sdk import Module, TaskContext, task\n"
        "from core.surface.sdk.advanced import ModuleId\n\n"
            "class T1DialMod(Module):\n"
            "    id = 't1dial'\n"
            "    @task(cli='probe', name='probe', summary='Probe Tier 1 dialect')\n"
            "    def probe(self, ctx: TaskContext) -> str:\n"
            "        a = ctx.locale.translate('t1dial.agent', caller_module=ModuleId('t1dial'))\n"
            "        g = ctx.locale.translate('t1dial.greeting', caller_module=ModuleId('t1dial'))\n"
            "        return f'{a}:{g}'\n\n"
            "def create_module():\n"
            "    return T1DialMod().to_yscb_module()\n",
            encoding="utf-8",
        )
        pool = ImmutableVenvPool(yscb_root=target_root_hp, cache_dir=HostPath(target_root_hp.path / ".cache"))
        mfs_map = discover_installed_manifests_map(target_root_hp)
        grp_specs = ImmutableVenvPool.resolve_group_specs(tuple(mfs_map.values()))
        pool.ensure_env(grp_specs[ModuleId("t1dial")], offline=True, wheel_cache_dir=wheel_house_hp)

    _provision_tier1_dialect_mod(wk_root_hp)
    _provision_tier1_dialect_mod(peer_dial_root_hp)

    class _CrossDialCallerMod(Module):
        id = "xdialcaller"

        @task
        def call_peer_t1(self, ctx: TaskContext) -> str:
            _ = self
            r_peer = ctx.call(TaskId("t1dial.probe"), {}, target_workspace=peer_dial_root_hp)
            check(r_peer.ok and isinstance(r_peer.value, str), f"Expected peer t1dial.probe ok, got {r_peer}")
            return str(r_peer.value)

    k1_claude = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        force_cold=True,
        dialect="nouns-claude",
        extra_modules=(_CrossDialCallerMod().to_yscb_module(),),
    )
    try:
        check(lookup_cold_workspace_dialect(wk_root_hp) == "nouns-claude")
        k2_plain = WorkspaceKernelFactory.create(
            wk_host_hp,
            wk_root_hp,
            force_cold=True,
            dialect=None,
        )
        try:
            check(
                lookup_cold_workspace_dialect(wk_root_hp) is None,
                "Expected K2(dialect=None) to mask K1(dialect='nouns-claude') on cold workspace stack",
            )
            k2_t1_out = k2_plain.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("t1dial.probe"),
                    raw_input={},
                    workspace_root=wk_root_hp,
                    caller_cwd=wk_host_hp,
                    routing_policy=ClientRoutingPolicy.FORCE_COLD,
                )
            )
            check(
                k2_t1_out.ok and k2_t1_out.value == "GenericAgent:EN",
                f"Expected K2(dialect=None) cold Tier 1 worker not to leak K1 dialect: {k2_t1_out}",
            )
            k1_t1_out = k1_claude.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("t1dial.probe"),
                    raw_input={},
                    workspace_root=wk_root_hp,
                    caller_cwd=wk_host_hp,
                    routing_policy=ClientRoutingPolicy.FORCE_COLD,
                )
            )
            check(
                k1_t1_out.ok and k1_t1_out.value == "ClaudeSubagent:EN",
                f"Expected K1(dialect='nouns-claude') cold Tier 1 worker to preserve its own dialect: {k1_t1_out}",
            )
        finally:
            k2_plain.close()

        check(
            lookup_cold_workspace_dialect(wk_root_hp) == "nouns-claude",
            "Expected K1 dialect to restore on cold workspace stack after K2 closes",
        )

        peer_claude_out = k1_claude.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("xdialcaller.call_peer_t1"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(
            peer_claude_out.ok and peer_claude_out.value == "ClaudeSubagent:EN",
            f"Expected managed child cold Tier 1 worker to inherit parent cold dialect: {peer_claude_out}",
        )
        check(
            lookup_cold_workspace_dialect(peer_dial_root_hp) is None,
            "Managed child kernel must not pollute peer workspace cold dialect stack",
        )

        k1_claude.apply_caller_dialect(None, "zh-tw")
        peer_updated_out = k1_claude.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("xdialcaller.call_peer_t1"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(
            peer_updated_out.ok and peer_updated_out.value == "GenericAgent:ZHTW",
            f"Expected cached managed child cold Tier 1 worker to sync updated parent dialect/locale: {peer_updated_out}",
        )
        check(lookup_cold_workspace_dialect(peer_dial_root_hp) is None)
    finally:
        k1_claude.close()

    # Verify space-separated '--note --json --unknown-flag' also emits human error to stderr
    opt_val_sp_out = _MockTtyOutput(is_tty=True)
    opt_val_sp_err = _MockTtyOutput(is_tty=True)
    rc_opt_val_sp = cli_main(
        ["baredict", "send", "--note", "--json", "--unknown-flag"],
        host_dir=wk_host_hp,
        yscb_root=wk_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "human_tty"},
        stdin_stream=_MockTtyInput(is_tty=True),
        stdout_stream=opt_val_sp_out,
        stderr_stream=opt_val_sp_err,
        builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
        install_signal_guard=False,
    )
    check(
        rc_opt_val_sp != 0 and opt_val_sp_out.getvalue() == "" and "Error [" in opt_val_sp_err.getvalue(),
        f"Expected human error on stderr for space-separated '--note --json --unknown-flag': out={opt_val_sp_out.getvalue()!r} err={opt_val_sp_err.getvalue()!r}",
    )

    # Verify non-regular lock file at .cache/locks/bootstrap.lock is rejected as security_gated (exit 4)
    bad_lock_ws = suite_dir / "bad_lock_kind_ws"
    bad_lock_dir = bad_lock_ws / ".yscb" / ".cache" / "locks" / "bootstrap.lock"
    bad_lock_dir.mkdir(parents=True, exist_ok=True)
    cp_bad_lock = _run_yscb_subproc(
        bad_lock_ws,
        ["init", "--provider", str(boot_prov), "--json"],
    )
    bad_lock_doc = json.loads(cp_bad_lock.stdout)
    check(
        cp_bad_lock.returncode == 4
        and bad_lock_doc.get("ok") is False
        and bad_lock_doc.get("error", {}).get("code") == "security_gated",
        f"Expected security_gated (exit 4) for non-regular bootstrap.lock: rc={cp_bad_lock.returncode} out={cp_bad_lock.stdout!r}",
    )

    # Verify mid-Cold-Turn Tier 1 source edit retires previous OneShotVenvHost gracefully (running on_init closer) and loads updated code
    closer_marker = wk_par_ws / "t1_closer_ran.txt"
    t1_entry_path = wk_root_hp.path / ".modules" / "t1dial" / "module_entry.py"
    t1_entry_path.write_text(
        "from pathlib import Path\n"
        "from core.surface.sdk import Module, ModuleEnv, TaskContext, task\n\n"
        "class T1DialMod(Module):\n"
        "    id = 't1dial'\n"
        "    def on_init(self, env: ModuleEnv) -> None:\n"
        f"        marker = Path({str(closer_marker)!r})\n"
        "        env.register_closer(lambda: marker.write_text('closed-v1', encoding='utf-8'))\n"
        "    @task(cli='probe', name='probe', summary='Probe Tier 1 dialect')\n"
        "    def probe(self, ctx: TaskContext) -> str:\n"
        "        _ = ctx\n"
        "        return 'v1-live'\n\n"
        "def create_module():\n"
        "    return T1DialMod().to_yscb_module()\n",
        encoding="utf-8",
    )

    class _MidTurnTier1ReloadMod(Module):
        id = "midt1rel"

        @task
        def run_sequence(self, ctx: TaskContext) -> str:
            _ = self
            first = ctx.call(TaskId("t1dial.probe"), {})
            check(first.ok and first.value == "v1-live", f"Expected v1-live first, got {first}")
            check(not closer_marker.exists(), "Expected on_init closer not yet run while v1 worker active")
            t1_entry_path.write_text(
                "from core.surface.sdk import Module, TaskContext, task\n\n"
                "class T1DialMod(Module):\n"
                "    id = 't1dial'\n"
                "    @task(cli='probe', name='probe', summary='Probe Tier 1 dialect')\n"
                "    def probe(self, ctx: TaskContext) -> str:\n"
                "        _ = ctx\n"
                "        return 'v2-live'\n\n"
                "def create_module():\n"
                "    return T1DialMod().to_yscb_module()\n",
                encoding="utf-8",
            )
            second = ctx.call(TaskId("t1dial.probe"), {})
            check(second.ok and second.value == "v2-live", f"Expected v2-live after mid-turn edit, got {second}")
            check(
                closer_marker.is_file() and closer_marker.read_text(encoding="utf-8") == "closed-v1",
                "Expected stale Cold Tier 1 worker to shut down gracefully and run on_init closer before v2 step",
            )
            return f"{first.value}->{second.value}"

    mt_k = WorkspaceKernelFactory.create(
        wk_host_hp,
        wk_root_hp,
        force_cold=True,
        extra_modules=(_MidTurnTier1ReloadMod().to_yscb_module(),),
    )
    try:
        mt_out = mt_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("midt1rel.run_sequence"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            )
        )
        check(mt_out.ok and mt_out.value == "v1-live->v2-live", f"Mid-turn Tier 1 reload check failed: {mt_out}")
    finally:
        mt_k.close()

    # Verify post-close cold WorkspaceKernel rejects invoke and emit_background_event with DAEMON_UNAVAILABLE
    closed_cold_k = WorkspaceKernelFactory.create(wk_host_hp, wk_root_hp, force_cold=True)
    closed_cold_k.close()
    post_close_inv = closed_cold_k.dispatcher.invoke(
        InvokeRequest(
            task_id=TaskId("core.status"),
            raw_input={},
            workspace_root=wk_root_hp,
            caller_cwd=wk_host_hp,
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
        )
    )
    check(
        not post_close_inv.ok
        and post_close_inv.error is not None
        and post_close_inv.error.code == ErrorCode.DAEMON_UNAVAILABLE,
        f"Expected closed cold WorkspaceKernel invoke to fail with DAEMON_UNAVAILABLE, got {post_close_inv}",
    )
    post_close_ev = closed_cold_k.dispatcher.emit_background_event(
        EventId("core.test_post_close"),
        {},
    )
    check(
        post_close_ev.primary_result is not None
        and not post_close_ev.primary_result.ok
        and post_close_ev.primary_result.error is not None
        and post_close_ev.primary_result.error.code == ErrorCode.DAEMON_UNAVAILABLE,
        f"Expected closed cold WorkspaceKernel emit_background_event to fail with DAEMON_UNAVAILABLE, got {post_close_ev}",
    )

    # Verify Tier 0 on_init closer stdout noise is suppressed during Cold CLI --json exit
    noisy_closer_ws = suite_dir / "noisy_closer_ws"
    noisy_closer_ws.mkdir(parents=True, exist_ok=True)
    cp_nc_init = _run_yscb_subproc(noisy_closer_ws, ["init", "--provider", str(boot_prov), "--json"])
    check(cp_nc_init.returncode == 0, f"Expected noisy_closer_ws init to succeed: {cp_nc_init.stderr}")
    nc_host_hp = HostPath(noisy_closer_ws)
    nc_root_hp = HostPath(noisy_closer_ws / ".yscb")
    nc_mod_dir = nc_root_hp.path / ".modules" / "noisyt0"
    nc_mod_dir.mkdir(parents=True, exist_ok=True)
    (nc_mod_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "noisyt0",
                "version": "1.0.0.0",
                "description": "Noisy Tier 0 closer module",
                "dependencies": {"core": ">=2.0.0"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (nc_mod_dir / "tasks.index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module_id": "noisyt0",
                "module_aliases": [],
                "description": "Noisy Tier 0 closer module",
                "tasks": [
                    {
                        "task_id": "noisyt0.ping",
                        "command_path": ["ping"],
                        "aliases": [],
                        "summary": "Ping noisy Tier 0 module",
                        "usage_pros": [],
                        "usage_cons": [],
                        "exposure": "cli_and_sdk",
                        "security_tier": "safe",
                        "dispatch_mode": "hybrid",
                        "interactive_tty": False,
                        "args": [],
                        "options": [],
                        "subscriptions": [],
                        "periodic": None,
                        "custom_render": False,
                        "custom_exit_code": False,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (nc_mod_dir / "module_entry.py").write_text(
        "import sys\n"
        "from core.surface.sdk import Module, ModuleEnv, TaskContext, task\n\n"
        "class NoisyT0Mod(Module):\n"
        "    id = 'noisyt0'\n"
        "    def on_init(self, env: ModuleEnv) -> None:\n"
        "        env.register_closer(lambda: sys.stdout.write('NOISY_CLOSER_STDOUT_LEAK\\n') or sys.stdout.flush())\n"
        "    @task(cli='ping', name='ping', summary='Ping noisy Tier 0 module')\n"
        "    def ping(self, ctx: TaskContext) -> dict[str, str]:\n"
        "        _ = ctx\n"
        "        return {'pong': 'clean'}\n\n"
        "def create_module():\n"
        "    return NoisyT0Mod().to_yscb_module()\n",
        encoding="utf-8",
    )
    nc_cfg = json.loads((nc_host_hp.path / "yscb.config.json").read_text(encoding="utf-8"))
    nc_cfg["installed_modules"]["noisyt0"] = {"version": "1.0.0.0", "provider": "local"}
    (nc_host_hp.path / "yscb.config.json").write_text(json.dumps(nc_cfg, indent=2), encoding="utf-8")
    cp_nc = _run_yscb_subproc(nc_host_hp.path, ["noisyt0", "ping", "--cold", "--json"])
    check(
        cp_nc.returncode == 0 and "NOISY_CLOSER_STDOUT_LEAK" not in cp_nc.stdout,
        f"Expected Cold CLI --json stdout to remain uncorrupted by Tier 0 closer stdout write: {cp_nc.stdout!r} / {cp_nc.stderr!r}",
    )
    nc_doc = json.loads(cp_nc.stdout)
    check(nc_doc.get("ok") is True and nc_doc.get("value") == {"pong": "clean"}, f"Unexpected noisy closer JSON doc: {nc_doc}")

    # Verify post-close WorkspaceKernel methods do not resurrect cold dialect state and reject mutating/daemon calls
    closed_Cold_check_ws = suite_dir / "closed_kernel_guards_ws"
    ck_host_hp, ck_root_hp = _init_minimal_workspace(closed_Cold_check_ws)
    ck_kernel = WorkspaceKernelFactory.create(ck_host_hp, ck_root_hp, force_cold=True, dialect="nouns-claude")
    check(lookup_cold_workspace_dialect_state(ck_root_hp).has_active_kernel is True)
    ck_kernel.close()
    check(lookup_cold_workspace_dialect_state(ck_root_hp).has_active_kernel is False)
    ck_kernel.apply_caller_dialect("nouns-codex", "zh-tw")
    check(
        lookup_cold_workspace_dialect_state(ck_root_hp).has_active_kernel is False,
        "Post-close apply_caller_dialect must not resurrect cold workspace dialect registration",
    )
    for closed_fn in (
        lambda: ck_kernel.reload_config_only(),
        lambda: ck_kernel.reload_workspace_metadata(),
        lambda: ck_kernel.refresh_dynamic_spaces_only(),
        lambda: ck_kernel.set_dynamic_space(
            ModuleId("core"),
            "late_sp",
            SpaceSpec(space_id=SpaceId("core", "late_sp"), entries=(SemanticUri("project", ""),)),
        ),
        lambda: ck_kernel.build_daemon(),
        lambda: ck_kernel.spawn_or_run_daemon(console=False, detach=True),
    ):
        got_unavail = False
        try:
            _ = closed_fn()
        except YscbError as exc:
            got_unavail = exc.detail.code == ErrorCode.DAEMON_UNAVAILABLE
        check(got_unavail, "Expected post-close WorkspaceKernel method to raise YscbError(DAEMON_UNAVAILABLE)")

    # Verify Tier 1 raw OS fd 1 writes during import/render/exit_code do not corrupt index compilation or CLI presentation
    t1_fd1_dir = wk_root_hp.path / ".modules" / "t1fd1"
    t1_fd1_dir.mkdir(parents=True, exist_ok=True)
    (t1_fd1_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "t1fd1",
                "version": "1.0.0.0",
                "description": "Tier 1 raw fd1 noise probe",
                "venv_group": "t1dial_grp",
                "pip_dependencies": {"dummy-dial-pkg": "==1.0.0"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (t1_fd1_dir / "module_entry.py").write_text(
        "from dataclasses import dataclass\n"
        "import os\n"
        "from core.surface.sdk import ExitCodeProvider, HumanRenderable, Module, TaskContext, task\n"
        "os.write(1, b'RAW_FD1_IMPORT_NOISE\\n')\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class NoisyT1Out(HumanRenderable, ExitCodeProvider):\n"
        "    tag: str\n"
        "    code: int\n"
        "    def render_text(self) -> str:\n"
        "        os.write(1, b'RAW_FD1_RENDER_NOISE\\n')\n"
        "        return f'CLEAN_T1::{self.tag}'\n"
        "    def exit_code(self) -> int:\n"
        "        os.write(1, b'RAW_FD1_EXIT_NOISE\\n')\n"
        "        return self.code\n\n"
        "class T1Fd1Mod(Module):\n"
        "    id = 't1fd1'\n"
        "    @task(cli='run', name='run', summary='Run noisy Tier 1 task')\n"
        "    def run(self, ctx: TaskContext) -> NoisyT1Out:\n"
        "        _ = ctx\n"
        "        return NoisyT1Out(tag='ok', code=7)\n\n"
        "def create_module():\n"
        "    return T1Fd1Mod().to_yscb_module()\n",
        encoding="utf-8",
    )
    t1_pool = ImmutableVenvPool(yscb_root=wk_root_hp, cache_dir=HostPath(wk_root_hp.path / ".cache"))
    t1_mfs_map = discover_installed_manifests_map(wk_root_hp)
    t1_grp_specs = ImmutableVenvPool.resolve_group_specs(tuple(t1_mfs_map.values()))
    t1_pool.ensure_env(t1_grp_specs[ModuleId("t1fd1")], offline=True, wheel_cache_dir=wheel_house_hp)

    fd1_k = WorkspaceKernelFactory.create(wk_host_hp, wk_root_hp, force_cold=True)
    try:
        fd1_k.ensure_installed_tasks_indices((ModuleId("t1fd1"),))
        check((t1_fd1_dir / "tasks.index.json").is_file(), "Expected Tier 1 tasks.index.json compiled despite raw fd 1 noise")
        fd1_k.rebuild_tasks_index_cache()
    finally:
        fd1_k.close()

    fd1_json_out = _MockTtyOutput(is_tty=False)
    fd1_json_err = _MockTtyOutput(is_tty=False)
    rc_fd1_json = cli_main(
        ["t1fd1", "run", "--cold", "--json"],
        host_dir=wk_host_hp,
        yscb_root=wk_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False),
        stdout_stream=fd1_json_out,
        stderr_stream=fd1_json_err,
        builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
        install_signal_guard=False,
    )
    fd1_doc = json.loads(fd1_json_out.getvalue())
    check(
        rc_fd1_json == 7 and fd1_doc.get("ok") is True and fd1_doc.get("value", {}).get("tag") == "ok",
        f"Expected Tier 1 ExitCodeProvider exit code 7 in --json mode despite raw fd 1 writes, got rc={rc_fd1_json}, doc={fd1_doc}",
    )

    fd1_hum_out = _MockTtyOutput(is_tty=False)
    fd1_hum_err = _MockTtyOutput(is_tty=False)
    rc_fd1_hum = cli_main(
        ["t1fd1", "run", "--cold"],
        host_dir=wk_host_hp,
        yscb_root=wk_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False),
        stdout_stream=fd1_hum_out,
        stderr_stream=fd1_hum_err,
        builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
        install_signal_guard=False,
    )
    check(
        rc_fd1_hum == 7 and "CLEAN_T1::ok" in fd1_hum_out.getvalue() and "RAW_FD1_" not in fd1_hum_out.getvalue(),
        f"Expected Tier 1 human render & exit code 7 without fd 1 noise: rc={rc_fd1_hum} out={fd1_hum_out.getvalue()!r}",
    )

    _verify_bootstrap_gate_ack_cursor_and_env_lease(wk_host_hp, wk_root_hp, t1_pool, t1_grp_specs[ModuleId("t1fd1")])
    _verify_observability_profiler_and_fast_daemon_boot(suite_dir, boot_prov, wheel_house_hp)
    _verify_ctx_spaces_tier0_and_tier1_e2e(suite_dir, boot_prov, wheel_house_hp)
    log("[SURFACE-CLI] All CLI, Bootstrap, and yscb.py E2E checks passed.")


def _verify_bootstrap_gate_ack_cursor_and_env_lease(
    wk_host_hp: HostPath,
    wk_root_hp: HostPath,
    t1_pool: ImmutableVenvPool,
    t1_spec: EnvSpec,
) -> None:
    gate_base = wk_host_hp.path.parent / "boot_mut_ack_lease_e2e"
    gate_prov = gate_base / "releases"
    _ = _package_core_release_zip(gate_prov, "2.0.0.0", status="active")
    gate_ws = gate_base / "fresh_ws"
    gate_ws.mkdir(parents=True, exist_ok=True)
    cp_fresh_init = _run_yscb_subproc(gate_ws, ["init", f"--provider={gate_prov}", "--json"])
    check(
        cp_fresh_init.returncode == 0 and json.loads(cp_fresh_init.stdout).get("ok") is True,
        f"Fresh empty workspace init must remain allowed without mutation flag: {cp_fresh_init.stdout} {cp_fresh_init.stderr}",
    )
    for label, xenv in (
        ("agent_explicit", {"YSCB_CALLER_MODE": "agent"}),
        ("agent_env", {"YSCB_CALLER_MODE": "", "CLAUDECODE": "1"}),
        ("ci", {"YSCB_CALLER_MODE": "", "CI": "true"}),
        ("non_tty", {"YSCB_CALLER_MODE": ""}),
    ):
        for cmd in (
            ["init", "--fix", "--json"],
            ["init", f"--provider={gate_prov}", "--json"],
            ["init", "--yscb-root=.alt_yscb", "--json"],
            ["init", "--ignore-sha256", "--json"],
            ["self-update", "--json"],
        ):
            cp_blk = _run_yscb_subproc(gate_ws, cmd, extra_env=xenv)
            blk_doc = json.loads(cp_blk.stdout)
            check(
                cp_blk.returncode == 4
                and blk_doc.get("ok") is False
                and blk_doc.get("error", {}).get("code") == "security_gated"
                and "--allow-bootstrap-mutation" in str(blk_doc.get("error", {}).get("remediation", "")),
                f"Expected security_gated (4) for {cmd} under {label}: rc={cp_blk.returncode} doc={blk_doc}",
            )
    cp_idemp_init = _run_yscb_subproc(gate_ws, ["init", "--json"])
    check(
        cp_idemp_init.returncode == 0 and json.loads(cp_idemp_init.stdout).get("ok") is True,
        f"Idempotent init without override flags must remain allowed: {cp_idemp_init.stdout}",
    )

    ack_host_hp, ack_root_hp = _init_minimal_workspace(gate_base / "ack_cursor_ws")
    probe_f = ack_host_hp.path / "hello.txt"
    probe_f.write_text("v1\n", encoding="utf-8")
    ack_mod = InMemoryModule("ackmod")

    def _ack_as_mod(req: dict[str, object], ctx: TaskContext) -> dict[str, object]:
        res = ctx.call(
            "core.space.ack_cursor",
            req,
            routing_policy=ClientRoutingPolicy.FORCE_COLD,
        )
        if not res.ok and res.error is not None:
            return {"ok": False, "code": res.error.code.value}
        val = res.value if isinstance(res.value, Mapping) else {}
        data = val.get("data") if isinstance(val.get("data"), Mapping) else {}
        return {"ok": True, "acked": data.get("acked")}

    ack_mod.add_task("try_ack", _ack_as_mod)
    ack_k = WorkspaceKernelFactory.create(ack_host_hp, ack_root_hp, force_cold=True, extra_modules=(ack_mod,))
    try:
        sp_ws = SpaceId("core", "ack_probe")
        ack_k.set_dynamic_space(
            ModuleId("core"),
            "ack_probe",
            SpaceSpec(space_id=sp_ws, entries=(SemanticUri("project", ""),)),
        )
        _ = ack_k.space_scanner.scan(sp_ws)
        b1 = ack_k.space_scanner.diff(sp_ws, "idx_c1")
        check(b1.has_changes and b1.to_gen.value >= 1, f"Expected initial space diff batch: {b1}")
        for bad_consumer in ("idx_c1", "ackmod2", "knowledge-db"):
            hijack_out = ack_k.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("ackmod.try_ack"),
                    raw_input=DataclassCodec.encode_object(
                        SpaceAckCursorInput(
                            space=str(sp_ws),
                            consumer=bad_consumer,
                            from_gen=b1.from_gen.value,
                            to_gen=b1.to_gen.value,
                            config_hash=b1.config_hash,
                            merkle_root=b1.merkle_root,
                        )
                    ),
                    workspace_root=ack_root_hp,
                    caller_cwd=ack_host_hp,
                )
            )
            check(
                hijack_out.ok
                and isinstance(hijack_out.value, Mapping)
                and hijack_out.value.get("ok") is False
                and hijack_out.value.get("code") == ErrorCode.ACCESS_DENIED.value,
                f"Non-core module must not ack foreign consumer '{bad_consumer}': {hijack_out}",
            )
        for own_consumer in ("ackmod", "ackmod:sub"):
            b_own = ack_k.space_scanner.diff(sp_ws, own_consumer)
            own_out = ack_k.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("ackmod.try_ack"),
                    raw_input=DataclassCodec.encode_object(
                        SpaceAckCursorInput(
                            space=str(sp_ws),
                            consumer=own_consumer,
                            from_gen=b_own.from_gen.value,
                            to_gen=b_own.to_gen.value,
                            config_hash=b_own.config_hash,
                            merkle_root=b_own.merkle_root,
                        )
                    ),
                    workspace_root=ack_root_hp,
                    caller_cwd=ack_host_hp,
                )
            )
            check(
                own_out.ok and isinstance(own_out.value, Mapping) and own_out.value.get("acked") is True,
                f"Module must be allowed to ack its own consumer '{own_consumer}': {own_out}",
            )
        ack1 = ack_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("core.space.ack_cursor"),
                raw_input=DataclassCodec.encode_object(
                    SpaceAckCursorInput(
                        space=str(sp_ws),
                        consumer="idx_c1",
                        from_gen=b1.from_gen.value,
                        to_gen=b1.to_gen.value,
                        config_hash=b1.config_hash,
                        merkle_root=b1.merkle_root,
                    )
                ),
                workspace_root=ack_root_hp,
                caller_cwd=ack_host_hp,
            )
        )
        check(ack1.ok and isinstance(ack1.value, dict) and ack1.value.get("data", {}).get("acked") is True, f"CAS ack1 failed: {ack1}")
        b_empty = ack_k.space_scanner.diff(sp_ws, "idx_c1")
        check(not b_empty.has_changes and b_empty.from_gen == b1.to_gen == b_empty.to_gen, f"Expected empty diff after ack: {b_empty}")

        stale_ack = ack_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("core.space.ack_cursor"),
                raw_input=DataclassCodec.encode_object(
                    SpaceAckCursorInput(
                        space=str(sp_ws),
                        consumer="idx_c1",
                        from_gen=b1.from_gen.value,
                        to_gen=b1.to_gen.value,
                        config_hash=b1.config_hash,
                        merkle_root=b1.merkle_root,
                    )
                ),
                workspace_root=ack_root_hp,
                caller_cwd=ack_host_hp,
            )
        )
        check(stale_ack.ok and isinstance(stale_ack.value, dict) and stale_ack.value.get("data", {}).get("acked") is False, f"Stale ack must return acked=False: {stale_ack}")

        probe_f.write_text("v2-updated\n", encoding="utf-8")
        _ = ack_k.space_scanner.scan(sp_ws, force=True)
        b2 = ack_k.space_scanner.diff(sp_ws, "idx_c1")
        check(b2.has_changes and b2.to_gen.value > b1.to_gen.value, f"Expected new diff after file edit: {b2}")

        for bad_cfg, bad_mrk in (("wrong_cfg", b2.merkle_root), (b2.config_hash, "wrong_merkle")):
            bad_cas = ack_k.dispatcher.invoke(
                InvokeRequest(
                    task_id=TaskId("core.space.ack_cursor"),
                    raw_input=DataclassCodec.encode_object(
                        SpaceAckCursorInput(
                            space=str(sp_ws),
                            consumer="idx_c1",
                            from_gen=b2.from_gen.value,
                            to_gen=b2.to_gen.value,
                            config_hash=bad_cfg,
                            merkle_root=bad_mrk,
                        )
                    ),
                    workspace_root=ack_root_hp,
                    caller_cwd=ack_host_hp,
                )
            )
            check(bad_cas.ok and isinstance(bad_cas.value, dict) and bad_cas.value.get("data", {}).get("acked") is False, f"Mismatched CAS must return acked=False: {bad_cas}")
    finally:
        ack_k.close()

    ack_cli_out = _MockTtyOutput(is_tty=False)
    rc_ack_cli = cli_main(
        [
            "fs",
            "ack-cursor",
            "--space=core/ack_probe",
            "--consumer=idx_c1",
            f"--from-gen={b2.from_gen.value}",
            f"--to-gen={b2.to_gen.value}",
            f"--config-hash={b2.config_hash}",
            f"--merkle-root={b2.merkle_root}",
            "--cold",
            "--json",
        ],
        host_dir=ack_host_hp,
        yscb_root=ack_root_hp,
        env={"YSCB_TEST_SANDBOX": "1", "YSCB_CALLER_MODE": "agent"},
        stdin_stream=_MockTtyInput(is_tty=False),
        stdout_stream=ack_cli_out,
        stderr_stream=_MockTtyOutput(is_tty=False),
        builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
        install_signal_guard=False,
    )
    ack_cli_doc = json.loads(ack_cli_out.getvalue())
    check(
        rc_ack_cli == 0 and ack_cli_doc.get("ok") is True and ack_cli_doc.get("value", {}).get("data", {}).get("acked") is True,
        f"CLI fs ack-cursor failed: rc={rc_ack_cli} doc={ack_cli_doc}",
    )

    (wk_root_hp.path / ".modules" / "t1dial" / "module_entry.py").write_text(
        "from core.surface.sdk import Module, TaskContext, task\n"
        "from core.surface.sdk.advanced import ModuleId\n\n"
        "class T1DialMod(Module):\n"
        "    id = 't1dial'\n"
        "    @task(cli='probe', name='probe', summary='Probe Tier 1 dialect')\n"
        "    def probe(self, ctx: TaskContext) -> str:\n"
        "        a = ctx.locale.translate('t1dial.agent', caller_module=ModuleId('t1dial'))\n"
        "        g = ctx.locale.translate('t1dial.greeting', caller_module=ModuleId('t1dial'))\n"
        "        return f'{a}:{g}'\n\n"
        "def create_module():\n"
        "    return T1DialMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    sdk_t1_dial_code = (
        "import sys\n"
        "from core.foundation import HostPath\n"
        "from core.surface.sdk.advanced import YscbClient\n"
        "with YscbClient(HostPath(sys.argv[1])) as cli:\n"
        "    out = cli.call('t1dial.probe', force_cold=True)\n"
        "    sys.stdout.write(str(out.value if out.ok else out.error))\n"
    )
    for label, xenv, expected_agent in (
        (
            "broad_non_session_keys",
            {
                "CLAUDE_CODE_USE_VERTEX": "1",
                "CODEX_HOME": "/tmp/cx",
                "CURSOR_TRACE_ID": "1",
                "GEMINI_API_KEY": "sk-test",
                "ANTIGRAVITY_HOME": "/tmp/agy",
            },
            "GenericAgent:",
        ),
        ("explicit_ci_suppresses_agent", {"YSCB_CALLER_MODE": "ci", "CLAUDECODE": "1"}, "GenericAgent:"),
        ("active_claude_session", {"CLAUDECODE": "1"}, "ClaudeSubagent:"),
    ):
        sub_env = _build_sanitized_subproc_env(caller_mode=None, extra_env={"PYTHONPATH": str(CORE_SRC_ROOT), **xenv})
        cp_t1d = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-W", "error::ResourceWarning", "-c", sdk_t1_dial_code, str(wk_root_hp)],
            cwd=str(wk_host_hp),
            env=sub_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        check(
            cp_t1d.returncode == 0 and cp_t1d.stdout.startswith(expected_agent),
            f"Standalone cold Tier 1 worker dialect mismatch for {label}: rc={cp_t1d.returncode} out={cp_t1d.stdout!r} err={cp_t1d.stderr!r}",
        )

    t1_env_dir = t1_pool.get_env_dir(t1_spec)
    hot_k = WorkspaceKernelFactory.create(wk_host_hp, wk_root_hp, is_daemon_host=True, force_cold=False)
    try:
        hot_out = hot_k.dispatcher.invoke(
            InvokeRequest(
                task_id=TaskId("t1fd1.run"),
                raw_input={},
                workspace_root=wk_root_hp,
                caller_cwd=wk_host_hp,
            )
        )
        check(hot_out.ok, f"Hot Tier 1 invoke failed: {hot_out}")
        gc_live = hot_k.env_gc.collect(active_specs=(), force_all=True)
        check(
            t1_env_dir in gc_live.skipped_locked_dirs and t1_env_dir not in gc_live.removed_dirs and t1_env_dir.path.is_dir(),
            f"Active HotWorkerPool shared env lease must protect venv from EnvGarbageCollector: {gc_live}",
        )
    finally:
        hot_k.close()
    gc_post = EnvGarbageCollector(t1_pool).collect(active_specs=(), force_all=True)
    check(
        t1_env_dir in gc_post.removed_dirs and not t1_env_dir.path.exists(),
        f"EnvGarbageCollector must reclaim venv after kernel closes and releases shared lease: {gc_post}",
    )


def _collect_profiler_tree_names(node: Mapping[str, object]) -> set[str]:
    names: set[str] = set()
    raw_name = node.get("name")
    if isinstance(raw_name, str) and raw_name:
        names.add(raw_name)
    raw_children = node.get("children")
    if isinstance(raw_children, list):
        for ch in raw_children:
            if isinstance(ch, Mapping):
                names.update(_collect_profiler_tree_names(ch))
    return names


def _verify_cli_profile_flags_and_pre_dispatch_redaction(obs_base: Path, prov_dir: Path) -> None:
    empty_ws = obs_base / "uninit_empty_ws"
    empty_ws.mkdir(parents=True, exist_ok=True)
    for empty_argv in (["--profile", "--help"], ["--profile"]):
        cp_empty = _run_yscb_subproc(
            empty_ws,
            empty_argv,
            script_override=CORE_V2_ROOT / "yscb.py",
        )
        check(
            cp_empty.returncode == 0 and list(empty_ws.iterdir()) == [],
            f"Uninitialized workspace {empty_argv} must exit 0 with 0 disk writes: rc={cp_empty.returncode} files={list(empty_ws.iterdir())} err={cp_empty.stderr!r}",
        )

    ws_prof = obs_base / "cli_prof_ws"
    ws_prof.mkdir(parents=True, exist_ok=True)
    cp_init = _run_yscb_subproc(ws_prof, ["init", f"--provider={prov_dir}", "--json"])
    check(cp_init.returncode == 0, f"cli_prof_ws init failed: {cp_init.stdout} {cp_init.stderr}")
    logs_dir = ws_prof / ".yscb" / ".cache" / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)

    for help_argv in (["--help"], ["--profile", "--help"], ["status", "--profile", "-h"]):
        cp_h = _run_yscb_subproc(ws_prof, help_argv)
        check(cp_h.returncode == 0, f"Help command {help_argv} failed: {cp_h.stderr}")
    check(not logs_dir.exists(), f"Cold --help must produce 0 flight-log writes, found {logs_dir}")

    cp_prof = _run_yscb_subproc(ws_prof, ["status", "--profile", "--json", "--cold"])
    check(cp_prof.returncode == 0, f"status --profile --json --cold failed: {cp_prof.stdout} {cp_prof.stderr}")
    prof_doc = json.loads(cp_prof.stdout)
    check(prof_doc.get("ok") is True, f"Expected pure JSON stdout on --profile --json: {prof_doc}")
    check(
        "Bootstrap" in cp_prof.stderr and "Launcher" in cp_prof.stderr and "Total ms" in cp_prof.stderr and "Self ms" in cp_prof.stderr and "core.status" in cp_prof.stderr,
        f"Expected ImTK profiler waterfall tree on stderr: {cp_prof.stderr!r}",
    )

    cp_pmem = _run_yscb_subproc(ws_prof, ["status", "--profile-mem", "--json", "--cold"])
    check(cp_pmem.returncode == 0, f"status --profile-mem --json --cold failed: {cp_pmem.stdout} {cp_pmem.stderr}")
    pmem_doc = json.loads(cp_pmem.stdout)
    check(pmem_doc.get("ok") is True, f"Expected pure JSON stdout on --profile-mem --json: {pmem_doc}")
    check(
        "Alloc KB" in cp_pmem.stderr and "Bootstrap" in cp_pmem.stderr and "Launcher" in cp_pmem.stderr,
        f"Expected Alloc KB column in --profile-mem stderr output: {cp_pmem.stderr!r}",
    )

    cp_env_mem = _run_yscb_subproc(
        ws_prof,
        ["status", "--json", "--cold"],
        extra_env={"YSCB_PROFILE_MEM": "1"},
    )
    check(cp_env_mem.returncode == 0 and json.loads(cp_env_mem.stdout).get("ok") is True)
    check("Total ms" not in cp_env_mem.stderr, f"YSCB_PROFILE_MEM=1 alone must not print tree to stderr: {cp_env_mem.stderr!r}")

    perf_files = sorted((logs_dir / "perf").glob("*.jsonl"))
    check(len(perf_files) == 1, f"Expected perf flight log file, got {perf_files}")
    perf_rows = [json.loads(ln) for ln in perf_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    check(
        sum(1 for r in perf_rows if r.get("task_id") == "core.status" and r.get("mem_tracked") is True) >= 2,
        f"Expected --profile-mem and YSCB_PROFILE_MEM=1 traces with mem_tracked=True: {perf_rows}",
    )

    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    cp_sec_fail = _run_yscb_subproc(ws_prof, ["remove", "demo", "--approve=secret_tok_999", "--json", "--cold"])
    check(cp_sec_fail.returncode == 4, f"Expected security gate failure (4), got {cp_sec_fail.returncode}")
    cp_parse_fail = _run_yscb_subproc(
        ws_prof,
        ["config", "set", "core", "api_token", "supersecretvalue123", "--unknown-flag", "--json", "--cold"],
    )
    check(cp_parse_fail.returncode == 2, f"Expected parse failure (2), got {cp_parse_fail.returncode}")

    red_daily_files = sorted((logs_dir / "daily").glob("*.jsonl"))
    red_perf_files = sorted((logs_dir / "perf").glob("*.jsonl"))
    check(len(red_daily_files) == 1 and len(red_perf_files) == 1, "Expected daily and perf logs on pre-dispatch errors")
    red_daily_txt = red_daily_files[0].read_text(encoding="utf-8")
    red_perf_txt = red_perf_files[0].read_text(encoding="utf-8")
    for raw_secret in ("secret_tok_999", "supersecretvalue123"):
        check(raw_secret not in red_daily_txt, f"Raw secret {raw_secret!r} leaked into daily log!")
        check(raw_secret not in red_perf_txt, f"Raw secret {raw_secret!r} leaked into perf log!")
    check("[REDACTED]" in red_perf_txt, f"Expected [REDACTED] marker in perf log: {red_perf_txt}")
    red_daily_rows = [json.loads(ln) for ln in red_daily_txt.splitlines() if ln.strip()]
    red_perf_rows = [json.loads(ln) for ln in red_perf_txt.splitlines() if ln.strip()]
    check(
        len(red_perf_rows) == 2 and all(r.get("ok") is False for r in red_perf_rows),
        f"Expected strictly 2 failed perf records for 2 pre-dispatch failures: {red_perf_rows}",
    )
    check(
        sum(1 for r in red_daily_rows if r.get("kind") == "IN") == 2
        and sum(1 for r in red_daily_rows if r.get("kind") == "OUT" and r.get("ok") is False) == 2,
        f"Expected strictly 2 IN and 2 failed OUT daily records: {red_daily_rows}",
    )


def _setup_t1obs_workspace(obs_base: Path, prov_dir: Path, wheel_house_hp: HostPath) -> tuple[Path, Path]:
    ws_obs = obs_base / "three_proc_obs_ws"
    ws_obs.mkdir(parents=True, exist_ok=True)
    cp_init = _run_yscb_subproc(ws_obs, ["init", f"--provider={prov_dir}", "--json"])
    check(cp_init.returncode == 0, f"three_proc_obs_ws init failed: {cp_init.stdout} {cp_init.stderr}")
    obs_root = ws_obs / ".yscb"
    t1_dir = obs_root / ".modules" / "t1obs"
    t1_dir.mkdir(parents=True, exist_ok=True)
    (t1_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "t1obs",
                "version": "1.0.0.0",
                "description": "Tier 1 observability probe module",
                "venv_group": "obs_t1_grp",
                "pip_dependencies": {"dummy-dial-pkg": "==1.0.0"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (t1_dir / "module_entry.py").write_text(
        "from core.surface.sdk import Module, TaskContext, task\n\n"
        "class T1ObsMod(Module):\n"
        "    id = 't1obs'\n"
        "    @task(cli=('trace-work',), name='trace_work', summary='Emit Tier 1 spans and warning alert')\n"
        "    def trace_work(self, ctx: TaskContext) -> dict[str, str]:\n"
        "        with ctx.profiler.scope('WorkerPhase'):\n"
        "            ctx.logger.info('t1_info_event', fields={'step': 1})\n"
        "            with ctx.profiler.scope_relative('InnerCalc'):\n"
        "                ctx.logger.warning('t1_warn_alert', fields={'code': 'W42'})\n"
        "        return {'status': 'traced'}\n\n"
        "def create_module():\n"
        "    return T1ObsMod().to_yscb_module()\n",
        encoding="utf-8",
    )
    host_cfg_p = ws_obs / "yscb.config.json"
    host_cfg = json.loads(host_cfg_p.read_text(encoding="utf-8"))
    host_cfg["installed_modules"]["t1obs"] = {
        "version": "1.0.0.0",
        "provider": "local",
        "installed_at": "2026-11-25T00:00:00Z",
    }
    host_cfg_p.write_text(json.dumps(host_cfg, indent=2), encoding="utf-8")

    obs_host_hp = HostPath(ws_obs)
    obs_root_hp = HostPath(obs_root)
    obs_pool = ImmutableVenvPool(yscb_root=obs_root_hp, cache_dir=HostPath(obs_root / ".cache"))
    mfs_map = discover_installed_manifests_map(obs_root_hp)
    grp_specs = ImmutableVenvPool.resolve_group_specs(tuple(mfs_map.values()))
    obs_pool.ensure_env(grp_specs[ModuleId("t1obs")], offline=True, wheel_cache_dir=wheel_house_hp)
    idx_k = WorkspaceKernelFactory.create(obs_host_hp, obs_root_hp, force_cold=True)
    try:
        idx_k.ensure_installed_tasks_indices((ModuleId("t1obs"),))
        idx_k.rebuild_tasks_index_cache()
    finally:
        idx_k.close()
    return (ws_obs, obs_root)


def _verify_single_kernel_fast_daemon_boot(ws_obs: Path, obs_root: Path) -> None:
    obs_host_hp = HostPath(ws_obs)
    obs_root_hp = HostPath(obs_root)
    cache_hp = HostPath(obs_root / ".cache")
    logs_dir = obs_root / ".cache" / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)

    init_modes: list[bool] = []
    init_lock = threading.Lock()
    orig_init = WorkspaceKernel.__init__

    def _counting_init(self: WorkspaceKernel, *args: object, **kwargs: object) -> None:
        with init_lock:
            init_modes.append(bool(kwargs.get("is_daemon_host", False)))
        orig_init(self, *args, **kwargs)

    stop_done = threading.Event()
    sup_out = _MockTtyOutput(is_tty=False)
    sup_err = _MockTtyOutput(is_tty=False)

    def _stop_when_ready() -> None:
        dl = time.monotonic() + 15.0
        while time.monotonic() < dl:
            if probe_daemon_endpoint(cache_hp, obs_root_hp) is not None and bool(sup_out.getvalue()):
                _ = query_daemon_control(cache_hp, obs_root_hp, FrameKind.CONTROL_STOP, {"force": False}, timeout_ms=5000)
                stop_done.set()
                return
            time.sleep(0.05)

    WorkspaceKernel.__init__ = _counting_init
    stopper = threading.Thread(target=_stop_when_ready, daemon=True)
    stopper.start()
    try:
        rc_sup = cli_main(
            ["daemon", "start", "--supervisor", "--json"],
            host_dir=obs_host_hp,
            yscb_root=obs_root_hp,
            env={"YSCB_CALLER_MODE": "agent", "YSCB_OFFLINE": "1", "YSCB_NO_UPDATE_CHECK": "1"},
            stdin_stream=_MockTtyInput(is_tty=False),
            stdout_stream=sup_out,
            stderr_stream=sup_err,
            builtin_indices=WorkspaceKernelFactory.builtin_cli_indices(),
            install_signal_guard=False,
        )
    finally:
        WorkspaceKernel.__init__ = orig_init
        stopper.join(timeout=5.0)
        stop_daemon_cleanly(obs_root_hp)

    check(stop_done.is_set(), "Timed out waiting for fast foreground daemon to become ready")
    check(rc_sup == 0, f"Expected fast supervisor boot exit 0, got {rc_sup}: out={sup_out.getvalue()!r} err={sup_err.getvalue()!r}")
    check(
        init_modes == [True],
        f"Foreground daemon start must instantiate WorkspaceKernel EXACTLY ONCE (is_daemon_host=True), got {init_modes}",
    )
    sig_cache_p = obs_root / ".cache" / "daemon" / "core_sig_cache.json"
    check(sig_cache_p.is_file(), f"Expected core_sig_cache.json persisted at {sig_cache_p}")
    sig_doc = json.loads(sig_cache_p.read_text(encoding="utf-8"))
    check(isinstance(sig_doc, dict) and bool(sig_doc), f"Expected non-empty core_sig_cache.json, got {sig_doc}")


def _verify_three_process_observability_e2e(ws_obs: Path, obs_root: Path) -> None:
    logs_dir = obs_root / ".cache" / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    try:
        cp_start = _run_yscb_subproc(ws_obs, ["daemon", "start", "-d", "--json"])
        check(
            cp_start.returncode == 0 and json.loads(cp_start.stdout).get("value", {}).get("data", {}).get("online") is True,
            f"Background daemon start failed: rc={cp_start.returncode} out={cp_start.stdout!r} err={cp_start.stderr!r}",
        )
        ep_doc = json.loads((obs_root / ".cache" / "daemon" / "daemon.json").read_text(encoding="utf-8"))
        live_boot_id = str(ep_doc["boot_id"])
        check(bool(live_boot_id), f"Expected non-empty daemon boot_id in {ep_doc}")

        cp_t1 = _run_yscb_subproc(ws_obs, ["t1obs", "trace-work", "--profile", "--json"])
        check(cp_t1.returncode == 0, f"t1obs trace-work failed: rc={cp_t1.returncode} out={cp_t1.stdout!r} err={cp_t1.stderr!r}")
        t1_doc = json.loads(cp_t1.stdout)
        check(
            t1_doc.get("ok") is True and t1_doc.get("executed_hot") is True and t1_doc.get("value") == {"status": "traced"},
            f"Expected pure hot JSON outcome for t1obs.trace_work: {t1_doc}",
        )
        check(
            "Bootstrap" in cp_t1.stderr and "Launcher" in cp_t1.stderr and "WorkerPhase" in cp_t1.stderr and "InnerCalc" in cp_t1.stderr,
            f"Expected merged 3-process ImTK tree on stderr: {cp_t1.stderr!r}",
        )

        # Verify YscbClient -> Hot Daemon single-owner write matrix (no duplicate daily/perf writes)
        with YscbClient.connect(HostPath(obs_root)) as sdk_hot_cli:
            sdk_hot_out = sdk_hot_cli.call("t1obs.trace_work")
            check(
                sdk_hot_out.ok and sdk_hot_out.executed_hot and sdk_hot_out.value == {"status": "traced"},
                f"Expected hot YscbClient call ok: {sdk_hot_out}",
            )

        # Verify nested active profiler mounts remote daemon subtree inside active scope without double-counting
        nested_prof = ProfilerSession("NestedRpcRoot", track_memory=False)
        nested_k = WorkspaceKernelFactory.create(HostPath(ws_obs), HostPath(obs_root), force_cold=False)
        try:
            with nested_prof.scope("OuterParent"):
                nested_out = nested_k.dispatcher.invoke(
                    InvokeRequest(
                        task_id=TaskId("t1obs.trace_work"),
                        raw_input={},
                        workspace_root=HostPath(obs_root),
                        caller_cwd=HostPath(ws_obs),
                        routing_policy=ClientRoutingPolicy.AUTO_NO_SPAWN,
                        external_flight_owner=True,
                        active_profiler=nested_prof,
                    )
                )
            check(nested_out.ok and nested_out.executed_hot, f"Expected nested hot RPC ok: {nested_out}")
        finally:
            nested_k.close()
        nested_snap = nested_prof.snapshot()
        top_names = {c.name for c in nested_snap.children}
        check(
            top_names == {"OuterParent"},
            f"Nested RPC subtree must mount under OuterParent rather than leaking Root/Runtime/RpcCall: {top_names}",
        )
        outer_node = nested_snap.children[0]
        outer_names = _collect_profiler_tree_names(DataclassCodec.encode_object(outer_node))
        check(
            {"Runtime", "RpcCall", "WorkerPhase", "InnerCalc"}.issubset(outer_names),
            f"Expected nested RPC daemon+worker spans inside OuterParent: {sorted(outer_names)}",
        )
        check(
            nested_snap.total_ms <= outer_node.total_ms + 1.0,
            f"Nested RPC merge must not double-count wall time: root={nested_snap.total_ms} outer={outer_node.total_ms}",
        )

        cp_stop = _run_yscb_subproc(ws_obs, ["daemon", "stop", "--json"])
        check(cp_stop.returncode == 0, f"daemon stop failed: {cp_stop.stdout} {cp_stop.stderr}")
    finally:
        stop_daemon_cleanly(HostPath(obs_root))

    daily_files = sorted((logs_dir / "daily").glob("*.jsonl"))
    perf_files = sorted((logs_dir / "perf").glob("*.jsonl"))
    daemon_files = sorted((logs_dir / "daemon").glob("daemon_*.jsonl"))
    mod_log_p = logs_dir / "modules" / "t1obs.jsonl"
    check(len(daily_files) == 1 and len(perf_files) == 1, f"Missing daily/perf logs: {daily_files} / {perf_files}")
    check(len(daemon_files) >= 1 and mod_log_p.is_file(), f"Missing daemon/module logs: {daemon_files} / {mod_log_p}")

    daily_rows = [json.loads(ln) for ln in daily_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    perf_rows = [json.loads(ln) for ln in perf_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    daemon_rows = [json.loads(ln) for df in daemon_files for ln in df.read_text(encoding="utf-8").splitlines() if ln.strip()]
    mod_rows = [json.loads(ln) for ln in mod_log_p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    t1_perf = [r for r in perf_rows if r.get("task_id") == "t1obs.trace_work"]
    check(
        len(t1_perf) == 2,
        f"Expected strictly 2 perf traces (1 CLI hot + 1 YscbClient hot, 0 daemon duplicates), got {len(t1_perf)}: {t1_perf}",
    )
    cli_t1_perf = [r for r in t1_perf if r.get("caller_mode") != "sdk"]
    sdk_t1_perf = [r for r in t1_perf if r.get("caller_mode") == "sdk"]
    check(len(cli_t1_perf) == 1 and len(sdk_t1_perf) == 1, f"Expected 1 CLI + 1 SDK perf trace: {t1_perf}")
    trace_id = str(cli_t1_perf[0]["trace_id"])
    sdk_trace_id = str(sdk_t1_perf[0]["trace_id"])
    check(bool(trace_id) and cli_t1_perf[0].get("daemon_boot_id") == live_boot_id and cli_t1_perf[0].get("executed_hot") is True)
    sdk_tr_daily = [r for r in daily_rows if r.get("trace_id") == sdk_trace_id]
    check(
        sum(1 for r in sdk_tr_daily if r.get("kind") == "IN") == 1
        and sum(1 for r in sdk_tr_daily if r.get("kind") == "OUT" and r.get("ok") is True) == 1,
        f"YscbClient->Hot Daemon must emit strictly 1 IN and 1 OUT in daily/ for trace_id={sdk_trace_id}: {sdk_tr_daily}",
    )
    tree_names = _collect_profiler_tree_names(cli_t1_perf[0]["profiler_tree"])
    check(
        {"Bootstrap", "Launcher", "WorkerPhase", "InnerCalc"}.issubset(tree_names),
        f"Expected CLI + Daemon + Tier 1 spans merged into single perf profiler_tree, got {sorted(tree_names)}",
    )
    check(
        any(r.get("task_id") == "daemon.boot" and r.get("daemon_boot_id") == live_boot_id and r.get("ok") is True for r in perf_rows),
        f"Expected daemon.boot trace in perf log for boot_id={live_boot_id}",
    )

    tr_daily = [r for r in daily_rows if r.get("trace_id") == trace_id]
    check(
        sum(1 for r in tr_daily if r.get("kind") == "IN") == 1
        and sum(1 for r in tr_daily if r.get("kind") == "OUT" and r.get("ok") is True) == 1,
        f"Single-owner matrix must emit strictly 1 IN and 1 OUT in daily/ for trace_id={trace_id}: {tr_daily}",
    )
    check(
        any(
            r.get("kind") == "ALERT"
            and r.get("daemon_boot_id") == live_boot_id
            and "t1_warn_alert" in str(r.get("message", ""))
            for r in tr_daily
        ),
        f"Expected Tier 1 WARNING to bubble as ALERT into daily/ with matching trace_id & daemon_boot_id: {tr_daily}",
    )
    check(
        any(r.get("event") == "ready" and r.get("daemon_boot_id") == live_boot_id for r in daemon_rows)
        and any(r.get("event") == "rpc_done" and r.get("trace_id") == trace_id and r.get("daemon_boot_id") == live_boot_id for r in daemon_rows),
        f"Expected daemon lifecycle + rpc_done for trace_id={trace_id}: {daemon_rows}",
    )
    check(
        any(r.get("trace_id") == trace_id and r.get("daemon_boot_id") == live_boot_id and "t1_info_event" in json.dumps(r) for r in mod_rows)
        and any(r.get("trace_id") == trace_id and r.get("daemon_boot_id") == live_boot_id and "t1_warn_alert" in json.dumps(r) for r in mod_rows),
        f"Expected modules/t1obs.jsonl stamped with matching trace_id & daemon_boot_id: {mod_rows}",
    )


def _verify_lazy_proxy_gates_and_sandbox_env_overrides(ws_obs: Path, obs_root: Path) -> None:
    lazy_cases: tuple[tuple[str, InvokeRequest, ErrorCode], ...] = (
        (
            "allow_conditional=False",
            InvokeRequest(
                task_id=TaskId("core.daemon.start"),
                raw_input={"supervisor": True},
                workspace_root=HostPath(obs_root),
                caller_cwd=HostPath(ws_obs),
                allow_conditional=False,
            ),
            ErrorCode.SECURITY_GATED,
        ),
        (
            "DaemonStartInput schema validation",
            InvokeRequest(
                task_id=TaskId("core.daemon.start"),
                raw_input={"supervisor": True, "unexpected_key": 1},
                workspace_root=HostPath(obs_root),
                caller_cwd=HostPath(ws_obs),
                allow_conditional=True,
            ),
            ErrorCode.CODEC_VALIDATION_FAILED,
        ),
        (
            "in_event_chain=True",
            InvokeRequest(
                task_id=TaskId("core.daemon.start"),
                raw_input={"supervisor": True},
                workspace_root=HostPath(obs_root),
                caller_cwd=HostPath(ws_obs),
                allow_conditional=True,
                propagation=CallPropagationContext(in_event_chain=True),
            ),
            ErrorCode.SECURITY_GATED,
        ),
        (
            "from_hot_container=True",
            InvokeRequest(
                task_id=TaskId("core.daemon.start"),
                raw_input={"supervisor": True},
                workspace_root=HostPath(obs_root),
                caller_cwd=HostPath(ws_obs),
                allow_conditional=True,
                propagation=CallPropagationContext(from_hot_container=True),
            ),
            ErrorCode.COLD_DISPATCH_FORBIDDEN,
        ),
        (
            "STRICT_HOT COLD_ONLY",
            InvokeRequest(
                task_id=TaskId("core.daemon.start"),
                raw_input={"supervisor": True},
                workspace_root=HostPath(obs_root),
                caller_cwd=HostPath(ws_obs),
                allow_conditional=True,
                routing_policy=ClientRoutingPolicy.STRICT_HOT,
            ),
            ErrorCode.COLD_DISPATCH_FORBIDDEN,
        ),
    )
    for case_label, req_case, expected_code in lazy_cases:
        lazy_sess = WorkspaceKernelFactory.open_cli_session(HostPath(ws_obs), HostPath(obs_root), force_cold=True)
        try:
            disp_proxy = lazy_sess.dispatcher
            check(
                type(disp_proxy).__name__ == "_LazyCliDispatcherProxy",
                f"Expected unmaterialized _LazyCliDispatcherProxy for {case_label}, got {type(disp_proxy).__name__}",
            )
            case_out = disp_proxy.invoke(req_case)
            check(
                not case_out.ok and case_out.error is not None and case_out.error.code == expected_code,
                f"Lazy daemon fast path must not bypass {case_label} gate (expected {expected_code}): {case_out}",
            )
        finally:
            lazy_sess.close()

    logs_dir = obs_root / ".cache" / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    sdk_probe_code = (
        "import sys\n"
        "from core.foundation import HostPath\n"
        "from core.surface.sdk.advanced import YscbClient\n"
        "with YscbClient(HostPath(sys.argv[1])) as cli:\n"
        "    out = cli.call('t1obs.trace_work', force_cold=True)\n"
        "    if not out.ok:\n"
        "        raise SystemExit(str(out))\n"
    )
    legacy_sbx_env = _build_sanitized_subproc_env(
        caller_mode=None,
        extra_env={"PYTHONPATH": str(CORE_SRC_ROOT), "YSCB_TEST_SANDBOX": "1"},
    )
    legacy_sbx_env.pop("_YSCB_TEST_SANDBOX", None)
    legacy_sbx_env.pop("_YSCB_FORCE_FLIGHT_LOGS", None)
    cp_sbx = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-W", "error::ResourceWarning", "-c", sdk_probe_code, str(obs_root)],
        cwd=str(ws_obs),
        env=legacy_sbx_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    check(cp_sbx.returncode == 0, f"Legacy sandbox SDK probe failed: rc={cp_sbx.returncode} err={cp_sbx.stderr!r}")
    check(
        not (logs_dir / "daily").exists() and not (logs_dir / "perf").exists(),
        f"Legacy YSCB_TEST_SANDBOX=1 must suppress SDK/Kernel daily/perf flight logs: {list(logs_dir.rglob('*')) if logs_dir.exists() else []}",
    )

    force_env = _build_sanitized_subproc_env(
        caller_mode=None,
        extra_env={
            "PYTHONPATH": str(CORE_SRC_ROOT),
            "_YSCB_TEST_SANDBOX": "1",
            "_YSCB_FORCE_FLIGHT_LOGS": "1",
        },
    )
    cp_force = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-W", "error::ResourceWarning", "-c", sdk_probe_code, str(obs_root)],
        cwd=str(ws_obs),
        env=force_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    check(cp_force.returncode == 0, f"Force-flight-logs SDK probe failed: rc={cp_force.returncode} err={cp_force.stderr!r}")
    check(
        bool(list((logs_dir / "daily").glob("*.jsonl"))) and bool(list((logs_dir / "perf").glob("*.jsonl"))),
        f"_YSCB_FORCE_FLIGHT_LOGS=1 must override _YSCB_TEST_SANDBOX=1 for SDK/Kernel flight logs",
    )


def _verify_observability_profiler_and_fast_daemon_boot(
    suite_dir: Path,
    prov_dir: Path,
    wheel_house_hp: HostPath,
) -> None:
    obs_base = suite_dir / "obs_profiler_e2e"
    obs_base.mkdir(parents=True, exist_ok=True)
    _verify_cli_profile_flags_and_pre_dispatch_redaction(obs_base, prov_dir)
    ws_obs, obs_root = _setup_t1obs_workspace(obs_base, prov_dir, wheel_house_hp)
    _verify_single_kernel_fast_daemon_boot(ws_obs, obs_root)
    _verify_three_process_observability_e2e(ws_obs, obs_root)
    _verify_lazy_proxy_gates_and_sandbox_env_overrides(ws_obs, obs_root)


def _verify_ctx_spaces_tier0_and_tier1_e2e(
    suite_dir: Path,
    prov_dir: Path,
    wheel_house_hp: HostPath,
) -> None:
    sp_ws = suite_dir / "ctx_spaces_tier0_tier1_ws"
    sp_ws.mkdir(parents=True, exist_ok=True)
    cp_init = _run_yscb_subproc(sp_ws, ["init", f"--provider={prov_dir}", "--json"])
    check(cp_init.returncode == 0, f"ctx_spaces ws init failed: {cp_init.stdout} {cp_init.stderr}")
    (sp_ws / "docs").mkdir(parents=True, exist_ok=True)
    (sp_ws / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (sp_ws / "docs" / "skip.txt").write_text("skip\n", encoding="utf-8")
    sp_root = sp_ws / ".yscb"

    def _build_mod_src(mod_id: str) -> str:
        return (
            "from core.surface.sdk import (\n"
            "    ErrorCode, Module, SPACE_UPDATED_EVENT, SemanticUri, SpaceId, SpaceSpec,\n"
            "    SpaceUpdatedEventPayload, TaskContext, YscbError, on_event, task,\n"
            ")\n\n"
            "class SpaceProbeMod(Module):\n"
            f"    id = {mod_id!r}\n"
            "    def __init__(self) -> None:\n"
            "        self.ev_hits: int = 0\n"
            "    @on_event(SPACE_UPDATED_EVENT)\n"
            "    def on_space_ev(self, ctx: TaskContext) -> None:\n"
            "        prev = int(ctx.vfs.read_text('cache://@/ev_hits.txt')) if ctx.vfs.exists('cache://@/ev_hits.txt') else 0\n"
            "        ctx.vfs.write_text('cache://@/ev_hits.txt', str(prev + 1))\n"
            "    @task(cli=('probe',), name='probe', summary='Exercise ctx.spaces and resolve_uri')\n"
            "    def probe(self, ctx: TaskContext) -> dict[str, object]:\n"
            "        resolved = ctx.resolve_uri('./docs/guide.md')\n"
            "        sid = SpaceId(ctx.module_id.value, 'docs')\n"
            "        spec = SpaceSpec(space_id=sid, entries=(SemanticUri('project', 'docs'),), include=('*.md',))\n"
            "        changed = ctx.spaces.set_dynamic('docs', spec)\n"
            "        listed = ctx.spaces.list_spaces(owner=ctx.module_id.value)\n"
            "        files = ctx.spaces.list_files(sid, pattern='*.md')\n"
            "        scanned = ctx.spaces.scan(sid)\n"
            "        st = ctx.spaces.status(sid)\n"
            "        diff1 = ctx.spaces.diff(sid)\n"
            "        acked = ctx.spaces.ack_cursor(diff1)\n"
            "        diff2 = ctx.spaces.diff(sid)\n"
            "        missing_code = ''\n"
            "        try:\n"
            "            ctx.spaces.status('noowner/nospace')\n"
            "        except YscbError as exc:\n"
            "            missing_code = exc.detail.code.value\n"
            "        bad_owner_code = ''\n"
            "        try:\n"
            "            ctx.spaces.set_dynamic('bad', SpaceSpec(SpaceId('other', 'bad'), entries=(SemanticUri('project', 'docs'),)))\n"
            "        except YscbError as exc:\n"
            "            bad_owner_code = exc.detail.code.value\n"
            "        cleared = ctx.spaces.clear_dynamic('docs')\n"
            "        return {\n"
            "            'mod': ctx.module_id.value,\n"
            "            'resolved': str(resolved),\n"
            "            'changed': changed,\n"
            "            'listed': [str(s.space_id) for s in listed],\n"
            "            'files': [str(f.rel_path) for f in files],\n"
            "            'scan_cnt': len(scanned),\n"
            "            'gen': st.generation.value,\n"
            "            'diff1_changes': diff1.has_changes,\n"
            "            'acked': acked,\n"
            "            'diff2_changes': diff2.has_changes,\n"
            "            'missing_code': missing_code,\n"
            "            'bad_owner_code': bad_owner_code,\n"
            "            'cleared': cleared,\n"
            "            'ev_type': SpaceUpdatedEventPayload.__name__,\n"
            "        }\n"
            "    @task(name='ev_count', summary='Return SPACE_UPDATED_EVENT hits')\n"
            "    def ev_count(self, ctx: TaskContext) -> int:\n"
            "        return int(ctx.vfs.read_text('cache://@/ev_hits.txt')) if ctx.vfs.exists('cache://@/ev_hits.txt') else 0\n"
        )

    host_cfg_p = sp_ws / "yscb.config.json"
    host_cfg = json.loads(host_cfg_p.read_text(encoding="utf-8"))
    for mod_id, is_t1 in (("sp_t0", False), ("sp_t1", True)):
        mdir = sp_root / ".modules" / mod_id
        mdir.mkdir(parents=True, exist_ok=True)
        mf_doc: dict[str, object] = {
            "id": mod_id,
            "version": "1.0.0.0",
            "description": f"SpaceClient probe {mod_id}",
        }
        if is_t1:
            mf_doc["venv_group"] = "sp_t1_grp"
            mf_doc["pip_dependencies"] = {"dummy-dial-pkg": "==1.0.0"}
        (mdir / "manifest.json").write_text(json.dumps(mf_doc, indent=2), encoding="utf-8")
        (mdir / "module_entry.py").write_text(_build_mod_src(mod_id), encoding="utf-8")
        host_cfg["installed_modules"][mod_id] = {
            "version": "1.0.0.0",
            "provider": "local",
            "installed_at": "2026-11-25T00:00:00Z",
        }
    host_cfg_p.write_text(json.dumps(host_cfg, indent=2), encoding="utf-8")

    sp_host_hp = HostPath(sp_ws)
    sp_root_hp = HostPath(sp_root)
    sp_pool = ImmutableVenvPool(yscb_root=sp_root_hp, cache_dir=HostPath(sp_root / ".cache"))
    sp_mfs = discover_installed_manifests_map(sp_root_hp)
    sp_grp_specs = ImmutableVenvPool.resolve_group_specs(tuple(sp_mfs.values()))
    sp_pool.ensure_env(sp_grp_specs[ModuleId("sp_t1")], offline=True, wheel_cache_dir=wheel_house_hp)
    idx_k = WorkspaceKernelFactory.create(sp_host_hp, sp_root_hp, force_cold=True)
    try:
        idx_k.ensure_installed_tasks_indices((ModuleId("sp_t0"), ModuleId("sp_t1")))
        idx_k.rebuild_tasks_index_cache()
    finally:
        idx_k.close()

    with YscbClient(sp_root_hp) as client:
        for mod_id in ("sp_t0", "sp_t1"):
            out = client.call(f"{mod_id}.probe", cwd=sp_host_hp, force_cold=True)
            check(out.ok and isinstance(out.value, dict), f"ctx.spaces E2E failed for {mod_id}: {out}")
            v = out.value
            check(
                v["mod"] == mod_id
                and v["resolved"] == "project://docs/guide.md"
                and v["changed"] is True
                and f"{mod_id}/docs" in v["listed"]
                and list(v["files"]) == ["docs/guide.md"]
                and v["scan_cnt"] == 1
                and int(v["gen"]) >= 1
                and v["diff1_changes"] is True
                and v["acked"] is True
                and v["diff2_changes"] is False
                and v["missing_code"] == ErrorCode.SPACE_NOT_FOUND.value
                and v["bad_owner_code"] == ErrorCode.CONFIG_INVALID.value
                and v["cleared"] == 1,
                f"Unexpected ctx.spaces E2E result for {mod_id}: {v}",
            )
        ev_t0 = client.call("sp_t0.ev_count", force_cold=True)
        check(ev_t0.ok and isinstance(ev_t0.value, int) and ev_t0.value >= 1, f"Expected SPACE_UPDATED_EVENT hit: {ev_t0}")


__all__ = ("run_surface_cli_e2e_suite",)
