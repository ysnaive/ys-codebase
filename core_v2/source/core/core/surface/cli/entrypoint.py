"""Unified CLI entrypoint orchestrating zero-import routing, 4x3 security gates, dual-track output, profiling, 3+1 flight logs, and 12h update checks."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
import re
import signal
import sys
import threading
import time
from typing import Callable, ClassVar, Final, Mapping, Optional, Protocol, Sequence
import uuid

from core.execution.rpc import read_daemon_endpoint_file
from core.execution.runtime import (
    CORE_MODULE_ID,
    CallPropagationContext,
    CallerSurface,
    ClientRoutingPolicy,
    DEFAULT_CACHE_DIRNAME,
    InvokeRequest,
    RuntimeDispatcher,
    TaskOutcome,
    sanitize_caller_env,
)
from core.filesystem.fs import has_symlink_raw_path, is_symlink_or_reparse, resolve_contained_subpath
from core.foundation import (
    CancellationToken,
    DailyEventRecord,
    DataclassCodec,
    ErrorCode,
    ErrorDetail,
    ExecutionTraceRecord,
    FlightLogConfig,
    FlightLogRouter,
    HostPath,
    JsonObject,
    JsonValue,
    LogLevel,
    MemoryTrackingGuard,
    ProfilerNodeSnapshot,
    ProfilerSession,
    SignalWakeupGuard,
    TEST_SANDBOX_ENV_KEY,
    TaskId,
    YscbError,
    guard_standard_streams,
    read_process_rss_kb,
    redact_cli_args,
    redact_sensitive_value,
    render_profiler_tree,
    require_pure_bool,
    require_pure_int,
    safe_exception_summary,
)
from core.metadata.config import ConfigStore, parse_locale_chain_tokens
from core.packaging.installer import ProviderClient, UpdateCheckReport, UpdateChecker
from core.surface.cli.approval import ApprovalTokenStore, evaluate_security_gate
from core.surface.cli.caller_mode import (
    CallerEnvironment,
    CallerMode,
    CliInputStream,
    CliOutputStream,
    detect_caller_environment,
)
from core.surface.cli.help_renderer import HelpRenderer
from core.surface.cli.index import IndexedTaskEntry, ModuleTasksIndex, WorkspaceTasksIndexCache
from core.surface.cli.parser import CliRouteKind, extract_contextual_global_flags, resolve_cli_invocation
from core.surface.sdk import ExitCodeProvider
from core.surface.sdk.advanced import format_output

CLI_DEFAULT_PROVIDER_URL: Final[str] = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases"
CLI_DEFAULT_SELF_UPDATE_URL: Final[str] = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py"
_TRUTHY_ENV_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


class CliKernelSession(Protocol):
    """Port abstracting WorkspaceKernel lifecycle so core.surface.cli never reverse-imports bootstrap."""

    @property
    def dispatcher(self) -> RuntimeDispatcher: ...

    @property
    def config_store(self) -> Optional[ConfigStore]: ...

    def apply_caller_dialect(self, dialect: Optional[str], raw_env_locale: Optional[str] = None) -> None: ...

    def resolve_task_output_type(self, task_id: TaskId) -> Optional[object]: ...

    def resolve_task_presentation(
        self,
        task_entry: IndexedTaskEntry,
        raw_value: JsonValue,
        *,
        render_human: bool,
    ) -> tuple[Optional[str], Optional[int]]: ...

    def has_deferred_daemon(self) -> bool: ...

    def run_deferred_daemon(self, *, on_ready: Optional[Callable[[], None]] = None) -> tuple[bool, int]: ...

    def consume_post_close_exit_code(self) -> Optional[int]: ...

    def close(self) -> None: ...


CliKernelFactoryFn = Callable[[HostPath, HostPath, bool], CliKernelSession]


class _CliKernelRegistry:
    """Thread-safe holder for default CliKernelFactoryFn and built-in ModuleTasksIndex entries."""

    _LOCK: ClassVar[threading.Lock] = threading.Lock()
    _FACTORY: ClassVar[Optional[CliKernelFactoryFn]] = None
    _BUILTIN_INDICES_FN: ClassVar[Optional[Callable[[], Sequence[ModuleTasksIndex]]]] = None

    @classmethod
    def register(
        cls,
        factory: Optional[CliKernelFactoryFn],
        *,
        builtin_indices_fn: Optional[Callable[[], Sequence[ModuleTasksIndex]]] = None,
    ) -> None:
        with cls._LOCK:
            cls._FACTORY = factory
            if builtin_indices_fn is not None or factory is None:
                cls._BUILTIN_INDICES_FN = builtin_indices_fn

    @classmethod
    def get_factory(cls) -> Optional[CliKernelFactoryFn]:
        with cls._LOCK:
            return cls._FACTORY

    @classmethod
    def get_builtin_indices(cls) -> tuple[ModuleTasksIndex, ...]:
        with cls._LOCK:
            fn = cls._BUILTIN_INDICES_FN
        if fn is None:
            return ()
        return tuple(fn())


def register_cli_kernel_factory(
    factory: Optional[CliKernelFactoryFn],
    *,
    builtin_indices_fn: Optional[Callable[[], Sequence[ModuleTasksIndex]]] = None,
) -> None:
    """Register or clear the Composition Root factory backing CLI task execution."""
    _CliKernelRegistry.register(factory, builtin_indices_fn=builtin_indices_fn)


def _lookup_env_case_insensitive(env_map: Mapping[str, str], key: str) -> str:
    direct = env_map.get(key)
    if direct is not None:
        return direct.strip()
    upper_target = key.upper()
    for k, v in env_map.items():
        if k.upper() == upper_target:
            return v.strip()
    return ""


class _CliSecurityPolicySnapshot:
    __slots__ = ("agent_env_prefixes", "allow_noninteractive_approve", "ci_approve_gated")

    def __init__(
        self,
        agent_env_prefixes: tuple[str, ...] = (),
        allow_noninteractive_approve: bool = True,
        ci_approve_gated: bool = False,
    ) -> None:
        self.agent_env_prefixes = agent_env_prefixes
        self.allow_noninteractive_approve = allow_noninteractive_approve
        self.ci_approve_gated = ci_approve_gated


def _load_cli_security_policy(
    host_dir: HostPath,
    yscb_root: HostPath,
    env_map: Mapping[str, str],
) -> _CliSecurityPolicySnapshot:
    env_ci_approve = _lookup_env_case_insensitive(env_map, "YSCB_CI_APPROVE_GATED").lower() in _TRUTHY_ENV_VALUES
    try:
        store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
        raw_pfxs = store.get_module_value(CORE_MODULE_ID, "security.agent_env_prefixes", default=[])
        raw_allow = store.get_module_value(CORE_MODULE_ID, "security.allow_noninteractive_approve", default=True)
        raw_ci = store.get_module_value(CORE_MODULE_ID, "security.ci_approve_gated", default=False)
    except (OSError, ValueError, YscbError):
        return _CliSecurityPolicySnapshot((), True, env_ci_approve)

    pfxs: tuple[str, ...] = ()
    if isinstance(raw_pfxs, list):
        pfxs = tuple(x.strip() for x in raw_pfxs if type(x) is str and x.strip())
    allow_ni = raw_allow if type(raw_allow) is bool else True
    ci_ok = env_ci_approve or (raw_ci is True)
    return _CliSecurityPolicySnapshot(pfxs, allow_ni, ci_ok)


def _map_error_exit_code(code: ErrorCode) -> int:
    if code == ErrorCode.TASK_CANCELLED:
        return 130
    if code == ErrorCode.CODEC_VALIDATION_FAILED:
        return 2
    if code in (ErrorCode.SECURITY_GATED, ErrorCode.ACCESS_DENIED, ErrorCode.TTY_REQUIRED):
        return 4
    if code == ErrorCode.TASK_NOT_FOUND:
        return 3
    if code == ErrorCode.TASK_TIMEOUT:
        return 124
    return 1


def _write_json_outcome(stdout_stream: CliOutputStream, outcome: TaskOutcome[object]) -> None:
    encoded = DataclassCodec.encode_object(outcome)
    stdout_stream.write(json.dumps(encoded, ensure_ascii=False) + "\n")
    stdout_stream.flush()


def _fallback_decode_output(
    session: CliKernelSession,
    task_entry: IndexedTaskEntry,
    raw_value: JsonValue,
    *,
    render_human: bool,
) -> tuple[Optional[str], Optional[int]]:
    try:
        resolved_txt, resolved_code = session.resolve_task_presentation(
            task_entry,
            raw_value,
            render_human=render_human,
        )
        if resolved_txt is not None or resolved_code is not None:
            return (resolved_txt, resolved_code)
    except (AttributeError, TypeError, ValueError, YscbError):
        pass

    if not render_human and not task_entry.custom_exit_code:
        return (None, 0)
    out_tp = session.resolve_task_output_type(task_entry.task_id)
    if out_tp is not None:
        try:
            typed_val = DataclassCodec.decode(out_tp, raw_value)
            if not render_human:
                code_only = (
                    require_pure_int(typed_val.exit_code(), "ExitCodeProvider.exit_code()", min_val=None, max_val=None)
                    if isinstance(typed_val, ExitCodeProvider)
                    else 0
                )
                return (None, code_only)
            txt, code = format_output(typed_val)
            return (txt, code if isinstance(typed_val, ExitCodeProvider) else 0)
        except (TypeError, ValueError, YscbError):
            pass
    return (None, None)


def _render_human_outcome(
    outcome: TaskOutcome[JsonValue],
    task_entry: IndexedTaskEntry,
    session: CliKernelSession,
    stdout_stream: CliOutputStream,
    stderr_stream: CliOutputStream,
) -> int:
    if not outcome.ok:
        err = outcome.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, "Task execution failed.")
        stderr_stream.write(f"Error [{err.code.value}]: {err.message}\n")
        if err.remediation:
            stderr_stream.write(f"Hint: {err.remediation}\n")
        stderr_stream.flush()
        return _map_error_exit_code(err.code)

    custom_txt, custom_code = _fallback_decode_output(
        session,
        task_entry,
        outcome.value,
        render_human=True,
    )
    if custom_txt is not None or custom_code is not None:
        if custom_txt:
            stdout_stream.write(custom_txt if custom_txt.endswith("\n") else f"{custom_txt}\n")
            stdout_stream.flush()
        return custom_code if custom_code is not None else 0

    if task_entry.void_output and outcome.value == {}:
        return 0

    txt, exit_code = format_output(outcome.value)
    if txt:
        stdout_stream.write(txt if txt.endswith("\n") else f"{txt}\n")
        stdout_stream.flush()
    return exit_code


def _now_utc_and_epoch_ms() -> tuple[str, int]:
    now_dt = datetime.now(timezone.utc)
    return (now_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), max(0, int(now_dt.timestamp() * 1000.0)))


def _is_initialized_workspace(host_dir: HostPath, yscb_root: HostPath) -> bool:
    raw_host = str(host_dir)
    raw_root = str(yscb_root)
    if not os.path.isdir(raw_host) or is_symlink_or_reparse(raw_host) or has_symlink_raw_path(raw_host):
        return False
    if not os.path.isdir(raw_root) or is_symlink_or_reparse(raw_root) or has_symlink_raw_path(raw_root):
        return False
    cfg_path = os.path.join(raw_host, "yscb.config.json")
    return os.path.isfile(cfg_path) and not is_symlink_or_reparse(cfg_path)


def _load_cli_flight_log_config(host_dir: HostPath, yscb_root: HostPath) -> FlightLogConfig:
    try:
        store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
        raw_obs = store.get_module_value(CORE_MODULE_ID, "observability", default=None)
    except (OSError, ValueError, YscbError):
        return FlightLogConfig()
    if isinstance(raw_obs, Mapping):
        try:
            return DataclassCodec.decode(FlightLogConfig, raw_obs)
        except (ValueError, TypeError, KeyError, YscbError):
            return FlightLogConfig()
    return FlightLogConfig()


def _open_cli_flight_router(
    host_dir: HostPath,
    yscb_root: HostPath,
    env_map: Mapping[str, str],
    *,
    config: FlightLogConfig,
) -> Optional[FlightLogRouter]:
    if not _is_initialized_workspace(host_dir, yscb_root):
        return None
    try:
        logs_root = resolve_contained_subpath(yscb_root, DEFAULT_CACHE_DIRNAME, "logs")
        return FlightLogRouter(logs_root, config=config, env=env_map)
    except (OSError, ValueError, YscbError):
        return None


def _read_live_daemon_boot_id(yscb_root: HostPath) -> str:
    try:
        cache_dir = resolve_contained_subpath(yscb_root, DEFAULT_CACHE_DIRNAME)
        ep = read_daemon_endpoint_file(cache_dir, yscb_root)
        return ep.boot_id if ep is not None else ""
    except (OSError, ValueError, YscbError):
        return ""


_INLINE_APPROVE_FLAG_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(--approve(?:=|\s+))(\S+)")
_INLINE_QUOTED_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(\btoken\s+['\"])([^'\"]+)(['\"])")


def _scrub_log_text(text: str, *, raw_approve_token: Optional[str] = None) -> str:
    redacted = redact_sensitive_value(text)
    out = redacted if isinstance(redacted, str) else text
    out = _INLINE_APPROVE_FLAG_RE.sub(r"\1[REDACTED]", out)
    out = _INLINE_QUOTED_TOKEN_RE.sub(r"\1[REDACTED]\3", out)
    if isinstance(raw_approve_token, str):
        for cand in dict.fromkeys((raw_approve_token, raw_approve_token.strip(), raw_approve_token.strip().lower())):
            if cand:
                out = out.replace(cand, "[REDACTED]")
    return out


def _redacted_error_detail_dict(
    err: Optional[ErrorDetail],
    *,
    raw_approve_token: Optional[str] = None,
) -> Optional[JsonObject]:
    if err is None:
        return None
    raw = DataclassCodec.encode_object(err)
    redacted = redact_sensitive_value(raw)
    if not isinstance(redacted, Mapping):
        return None
    cleaned: dict[str, JsonValue] = dict(redacted)
    for txt_key in ("message", "remediation"):
        val = cleaned.get(txt_key)
        if isinstance(val, str) and val:
            cleaned[txt_key] = _scrub_log_text(val, raw_approve_token=raw_approve_token)
    return cleaned


def _collect_dispatched_tasks_from_tree(
    primary_task_id: str,
    snap: Optional[ProfilerNodeSnapshot],
) -> tuple[str, ...]:
    seen: list[str] = [primary_task_id]
    if snap is None:
        return tuple(seen)
    stack: list[tuple[Optional[str], ProfilerNodeSnapshot]] = [(None, snap)]
    while stack:
        parent_name, node = stack.pop()
        if parent_name in ("Task", "WorkerStep") and "." in node.name and node.name not in seen:
            seen.append(node.name)
        for child in reversed(node.children):
            stack.append((node.name, child))
    return tuple(seen)


def _record_pre_dispatch_failure(
    host_dir: HostPath,
    yscb_root: HostPath,
    env_map: Mapping[str, str],
    *,
    task_id_str: str,
    argv_tuple: tuple[str, ...],
    caller_mode_str: str,
    caller_cwd: HostPath,
    exit_code: int,
    cli_entry_ns: int,
    err_det: ErrorDetail,
    raw_approve_token: Optional[str] = None,
) -> None:
    fl_cfg = _load_cli_flight_log_config(host_dir, yscb_root)
    router = _open_cli_flight_router(host_dir, yscb_root, env_map, config=fl_cfg)
    if router is None:
        return
    try:
        if not router.enabled:
            return
        trace_id = uuid.uuid4().hex
        ts_utc, epoch_ms = _now_utc_and_epoch_ms()
        dur_ms = round(max(0.0, (time.perf_counter_ns() - cli_entry_ns) / 1_000_000.0), 4)
        mod_name = task_id_str.split(".", 1)[0] if "." in task_id_str else "core"
        pid = os.getpid()
        router.record_daily(
            DailyEventRecord(
                ts_utc=ts_utc,
                epoch_ms=epoch_ms,
                kind="IN",
                trace_id=trace_id,
                daemon_boot_id="",
                pid=pid,
                exec_mode="cold",
                module=mod_name,
                task_id=task_id_str,
                level=LogLevel.INFO,
                message=f"cli_start:{task_id_str}",
            )
        )
        router.record_daily(
            DailyEventRecord(
                ts_utc=ts_utc,
                epoch_ms=epoch_ms,
                kind="OUT",
                trace_id=trace_id,
                daemon_boot_id="",
                pid=pid,
                exec_mode="cold",
                module=mod_name,
                task_id=task_id_str,
                level=LogLevel.ERROR,
                ok=False,
                duration_ms=dur_ms,
                exit_code=exit_code,
                message=_scrub_log_text(err_det.message, raw_approve_token=raw_approve_token),
            )
        )
        router.record_perf(
            ExecutionTraceRecord(
                ts_utc=ts_utc,
                epoch_ms=epoch_ms,
                trace_id=trace_id,
                daemon_boot_id="",
                pid=pid,
                task_id=task_id_str,
                args=redact_cli_args(argv_tuple),
                caller_mode=caller_mode_str,
                caller_cwd=str(caller_cwd),
                executed_hot=False,
                exit_code=exit_code,
                ok=False,
                duration_ms=dur_ms,
                rss_kb=read_process_rss_kb(),
                rss_delta_kb=0,
                mem_tracked=False,
                dispatched_tasks=(task_id_str,),
                profiler_tree=None,
                error_code=err_det.code.value,
                error_detail=_redacted_error_detail_dict(err_det, raw_approve_token=raw_approve_token),
                runtime_snapshot={"caller_mode": caller_mode_str, "phase": "pre_dispatch", "exit_code": exit_code},
            )
        )
    finally:
        router.close()


def _maybe_emit_update_notice(
    host_dir: HostPath,
    yscb_root: HostPath,
    env_map: Mapping[str, str],
    stderr_stream: CliOutputStream,
    *,
    suppress: bool,
) -> None:
    if suppress or _lookup_env_case_insensitive(env_map, TEST_SANDBOX_ENV_KEY).lower() in _TRUTHY_ENV_VALUES:
        return
    if _lookup_env_case_insensitive(env_map, "YSCB_OFFLINE").lower() in _TRUTHY_ENV_VALUES:
        return
    if _lookup_env_case_insensitive(env_map, "YSCB_NO_UPDATE_CHECK").lower() in _TRUTHY_ENV_VALUES:
        return
    try:
        cfg_store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
        host_cfg = cfg_store.load_host_config()
        prov_url = host_cfg.default_provider.strip() or CLI_DEFAULT_PROVIDER_URL
        provider = ProviderClient(yscb_root=yscb_root, default_provider=prov_url, host_dir=host_dir)
        checker = UpdateChecker(
            host_dir=host_dir,
            yscb_root=yscb_root,
            config_store=cfg_store,
            provider=provider,
            self_update_url=CLI_DEFAULT_SELF_UPDATE_URL,
        )
        report: UpdateCheckReport = checker.check_if_due(force=False, offline=False)
        if report.candidates:
            mods_str = ", ".join(
                f"{c.module_id.value} ({c.current_version} -> {c.latest_version})"
                for c in report.candidates
            )
            stderr_stream.write(f"[Update Available] {mods_str}. Run 'yscb update' to upgrade.\n")
            stderr_stream.flush()
        if report.yscb_host_drift:
            stderr_stream.write("[Launcher Update] Newer yscb.py detected. Run 'yscb self-update' to sync.\n")
            stderr_stream.flush()
    except (OSError, ValueError, YscbError):
        pass


def main(
    argv: Sequence[str],
    *,
    host_dir: HostPath,
    yscb_root: HostPath,
    caller_cwd: Optional[HostPath] = None,
    env: Optional[Mapping[str, str]] = None,
    stdin_stream: Optional[CliInputStream] = None,
    stdout_stream: Optional[CliOutputStream] = None,
    stderr_stream: Optional[CliOutputStream] = None,
    kernel_factory: Optional[CliKernelFactoryFn] = None,
    builtin_indices: Optional[Sequence[ModuleTasksIndex]] = None,
    install_signal_guard: bool = True,
    boot_start_ns: Optional[int] = None,
) -> int:
    """Execute the complete zero-import CLI routing, 4x3 security gate, dispatch, and exit pipeline."""
    cli_entry_ns = time.perf_counter_ns()
    if not isinstance(host_dir, HostPath) or not isinstance(yscb_root, HostPath):
        raise TypeError("cli.main requires explicit HostPath host_dir and yscb_root")
    require_pure_bool(install_signal_guard, "install_signal_guard")
    if boot_start_ns is not None:
        require_pure_int(boot_start_ns, "boot_start_ns", min_val=0)
    if stdout_stream is None and isinstance(sys.stdout, io.TextIOWrapper):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    if stderr_stream is None and isinstance(sys.stderr, io.TextIOWrapper):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    eff_cwd = caller_cwd if caller_cwd is not None else host_dir
    env_map: Mapping[str, str] = dict(env) if env is not None else dict(os.environ)
    eff_in: CliInputStream = stdin_stream if stdin_stream is not None else sys.stdin
    eff_out: CliOutputStream = stdout_stream if stdout_stream is not None else sys.stdout
    eff_err: CliOutputStream = stderr_stream if stderr_stream is not None else sys.stderr
    argv_tup = tuple(str(a) for a in argv)

    sec_policy = _load_cli_security_policy(host_dir, yscb_root, env_map)
    caller_env: CallerEnvironment = detect_caller_environment(
        env=env_map,
        stdin_stream=eff_in,
        stdout_stream=eff_out,
        extra_agent_env_prefixes=sec_policy.agent_env_prefixes,
    )

    dd_stop = argv_tup.index("--") if "--" in argv_tup else len(argv_tup)
    json_mode_requested = "--json" in argv_tup[:dd_stop]
    try:
        if builtin_indices is not None:
            indices = WorkspaceTasksIndexCache(
                yscb_root,
                builtin_indices=tuple(builtin_indices),
            ).load_all()
        else:
            indices = WorkspaceTasksIndexCache(yscb_root, builtin_indices=()).load_all()
            if not any(m.module_id == CORE_MODULE_ID for m in indices):
                fallback_builtins = _CliKernelRegistry.get_builtin_indices()
                if fallback_builtins:
                    indices = WorkspaceTasksIndexCache(
                        yscb_root,
                        builtin_indices=fallback_builtins,
                    ).load_all()
        flags = extract_contextual_global_flags(argv_tup, indices)
        rem_dd = flags.remaining_args.index("--") if "--" in flags.remaining_args else len(flags.remaining_args)
        pre_dd_rem = flags.remaining_args[:rem_dd]
        json_mode_requested = flags.json_output or (bool(pre_dd_rem) and pre_dd_rem[-1] == "--json")
        route = resolve_cli_invocation(flags, indices)
        json_mode_requested = flags.json_output
    except YscbError as exc:
        err_det = exc.detail
        code = _map_error_exit_code(err_det.code)
        if json_mode_requested:
            _write_json_outcome(eff_out, TaskOutcome(ok=False, error=err_det))
        else:
            eff_err.write(f"Error [{err_det.code.value}]: {err_det.message}\n")
            if err_det.remediation:
                eff_err.write(f"Hint: {err_det.remediation}\n")
            eff_err.flush()
        _record_pre_dispatch_failure(
            host_dir,
            yscb_root,
            env_map,
            task_id_str=err_det.source_task or "cli.parse",
            argv_tuple=argv_tup,
            caller_mode_str=caller_env.mode.value,
            caller_cwd=eff_cwd,
            exit_code=code,
            cli_entry_ns=cli_entry_ns,
            err_det=err_det,
        )
        return code

    if route.kind == CliRouteKind.HELP or route.task_entry is None:
        help_txt = HelpRenderer(caller_env.mode).render_node(route.node)
        if flags.json_output:
            _write_json_outcome(
                eff_out,
                TaskOutcome(
                    ok=True,
                    value={
                        "help": help_txt,
                        "command_path": list(route.node.canonical_path),
                    },
                ),
            )
        else:
            eff_out.write(help_txt)
            eff_out.flush()
        return 0

    task_entry = route.task_entry
    eff_factory = kernel_factory if kernel_factory is not None else _CliKernelRegistry.get_factory()

    try:
        if task_entry.interactive_tty and (caller_env.mode != CallerMode.HUMAN_TTY or flags.json_output):
            raise YscbError(
                ErrorCode.TTY_REQUIRED,
                f"Task '{task_entry.task_id}' requires an interactive human terminal without '--json'.",
                remediation=f"Run '{' '.join(route.node.canonical_path)}' directly in an interactive terminal without --json.",
                source_task=task_entry.task_id.value,
            )
        if eff_factory is None:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                "No CLI kernel factory is registered; import core.surface.bootstrap or pass kernel_factory.",
                remediation="Import 'core.surface.bootstrap' before invoking core.surface.cli.main(), or pass an explicit kernel_factory.",
                source_task=task_entry.task_id.value,
            )
        cache_dir = resolve_contained_subpath(yscb_root, DEFAULT_CACHE_DIRNAME)
        token_store = ApprovalTokenStore(cache_dir)
        gate_res = evaluate_security_gate(
            task_id=task_entry.task_id,
            security_tier=task_entry.security_tier,
            caller_mode=caller_env.mode,
            normalized_input=route.normalized_input,
            summary=task_entry.summary,
            token_store=token_store,
            approve_token=flags.approve_token,
            allow_noninteractive_approve=sec_policy.allow_noninteractive_approve,
            ci_approve_gated=sec_policy.ci_approve_gated,
            stdin_stream=eff_in,
            stderr_stream=eff_err,
        )
    except KeyboardInterrupt:
        gate_cancel_err = ErrorDetail(
            ErrorCode.TASK_CANCELLED,
            "Interrupted by SIGINT.",
            source_task=task_entry.task_id.value,
        )
        if flags.json_output or json_mode_requested:
            _write_json_outcome(eff_out, TaskOutcome(ok=False, error=gate_cancel_err))
        else:
            eff_err.write("Interrupted.\n")
            eff_err.flush()
        _record_pre_dispatch_failure(
            host_dir,
            yscb_root,
            env_map,
            task_id_str=task_entry.task_id.value,
            argv_tuple=argv_tup,
            caller_mode_str=caller_env.mode.value,
            caller_cwd=eff_cwd,
            exit_code=130,
            cli_entry_ns=cli_entry_ns,
            err_det=gate_cancel_err,
        )
        return 130
    except YscbError as exc:
        err_det = exc.detail
        code = _map_error_exit_code(err_det.code)
        if flags.json_output or json_mode_requested:
            _write_json_outcome(eff_out, TaskOutcome(ok=False, error=err_det))
        else:
            eff_err.write(f"Error [{err_det.code.value}]: {err_det.message}\n")
            if err_det.remediation:
                eff_err.write(f"Hint: {err_det.remediation}\n")
            eff_err.flush()
        _record_pre_dispatch_failure(
            host_dir,
            yscb_root,
            env_map,
            task_id_str=task_entry.task_id.value,
            argv_tuple=argv_tup,
            caller_mode_str=caller_env.mode.value,
            caller_cwd=eff_cwd,
            exit_code=code,
            cli_entry_ns=cli_entry_ns,
            err_det=err_det,
            raw_approve_token=flags.approve_token,
        )
        return code

    cancel_token = CancellationToken()

    def _on_progress(prog: JsonObject) -> None:
        phase = prog.get("phase")
        comp = prog.get("completed")
        tot = prog.get("total")
        msg = prog.get("message")
        parts: list[str] = ["[progress]"]
        if type(phase) is str and phase:
            parts.append(phase)
        if type(comp) is int and type(tot) is int and tot > 0:
            parts.append(f"({comp}/{tot})")
        if type(msg) is str and msg:
            parts.append(msg)
        if len(parts) > 1:
            eff_err.write(" ".join(parts) + "\n")
            eff_err.flush()

    eff_profile_mem = bool(
        flags.profile_mem
        or _lookup_env_case_insensitive(env_map, "YSCB_PROFILE_MEM").lower() in _TRUTHY_ENV_VALUES
    )
    show_profile_stderr = bool(flags.profile or flags.profile_mem)
    trace_id = uuid.uuid4().hex
    flight_cfg = _load_cli_flight_log_config(host_dir, yscb_root)
    flight_router = _open_cli_flight_router(host_dir, yscb_root, env_map, config=flight_cfg)
    root_profiler = ProfilerSession(root_name=task_entry.task_id.value, track_memory=eff_profile_mem)
    if boot_start_ns is not None:
        launcher_ms = round(max(0.0, (cli_entry_ns - boot_start_ns) / 1_000_000.0), 4)
        root_profiler.merge_subtree(
            ProfilerNodeSnapshot(
                name="Launcher",
                self_ms=launcher_ms,
                total_ms=launcher_ms,
                calls=1,
            ),
            mount_path="Bootstrap",
        )
    rss_before = read_process_rss_kb()
    initial_boot_id = _read_live_daemon_boot_id(yscb_root) if not flags.force_cold else ""
    if flight_router is not None and flight_router.enabled:
        in_ts, in_ms = _now_utc_and_epoch_ms()
        flight_router.record_daily(
            DailyEventRecord(
                ts_utc=in_ts,
                epoch_ms=in_ms,
                kind="IN",
                trace_id=trace_id,
                daemon_boot_id=initial_boot_id,
                pid=os.getpid(),
                exec_mode="hot" if (not flags.force_cold and bool(initial_boot_id)) else "cold",
                module=task_entry.task_id.module_id.value,
                task_id=task_entry.task_id.value,
                level=LogLevel.INFO,
                message=f"cli_start:{task_entry.task_id.value}",
            )
        )

    outcome: TaskOutcome[JsonValue] = TaskOutcome(
        ok=False,
        error=ErrorDetail(ErrorCode.BUSINESS_FAILURE, "Invocation aborted.", source_task=task_entry.task_id.value),
    )
    exit_code = 1
    post_close_rc: Optional[int] = None
    session: Optional[CliKernelSession] = None
    session_closed = False
    emitted_ready = False
    try:
        with MemoryTrackingGuard(eff_profile_mem):
            with root_profiler.scope("Bootstrap/OpenSession"):
                session = eff_factory(host_dir, yscb_root, flags.force_cold)
            sanitized_env = dict(sanitize_caller_env(env_map))
            raw_user_loc = _lookup_env_case_insensitive(env_map, "YSCB_LOCALE") or sanitized_env.get("YSCB_LOCALE", "")
            try:
                session.apply_caller_dialect(caller_env.dialect, raw_user_loc)
            except TypeError:
                session.apply_caller_dialect(caller_env.dialect)
            except AttributeError:
                pass
            cfg_for_loc = (
                session.config_store
                if session.config_store is not None
                else ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
            )
            eff_chain = parse_locale_chain_tokens(
                raw_user_loc if raw_user_loc else None,
                cfg_for_loc,
                dialect=caller_env.dialect,
            )
            sanitized_env["YSCB_LOCALE"] = ",".join(eff_chain)

            req = InvokeRequest(
                task_id=task_entry.task_id,
                raw_input=route.normalized_input,
                workspace_root=yscb_root,
                caller_cwd=eff_cwd,
                caller_env=sanitized_env,
                caller_surface=CallerSurface.CLI,
                routing_policy=(
                    ClientRoutingPolicy.FORCE_COLD if flags.force_cold else ClientRoutingPolicy.AUTO_SPAWN
                ),
                approval_scope=gate_res.approval_scope,
                allow_conditional=True,
                propagation=CallPropagationContext(
                    call_tree_id=trace_id,
                    profile_mem=eff_profile_mem,
                ),
                profile_mem=eff_profile_mem,
                external_flight_owner=True,
                active_profiler=root_profiler,
            )
            with guard_standard_streams(allow_interactive_tty=task_entry.interactive_tty):
                if install_signal_guard and threading.current_thread() is threading.main_thread():
                    sig_guard = SignalWakeupGuard((int(signal.SIGINT),), lambda: cancel_token.cancel(reason="SIGINT"))
                    sig_guard.install()
                    try:
                        outcome = session.dispatcher.invoke(
                            req,
                            cancel_token=cancel_token,
                            on_progress=_on_progress,
                        )
                    finally:
                        sig_guard.close()
                else:
                    outcome = session.dispatcher.invoke(
                        req,
                        cancel_token=cancel_token,
                        on_progress=_on_progress,
                    )

        try:
            deferred_daemon = outcome.ok and session.has_deferred_daemon()
        except AttributeError:
            deferred_daemon = False

        if deferred_daemon:
            if flags.json_output:
                _unused_txt, custom_exit = _fallback_decode_output(
                    session,
                    task_entry,
                    outcome.value,
                    render_human=False,
                )
                exit_code = custom_exit if custom_exit is not None else 0
                pre_human_txt = ""
            else:
                custom_txt, custom_exit = _fallback_decode_output(
                    session,
                    task_entry,
                    outcome.value,
                    render_human=True,
                )
                if custom_txt is not None or custom_exit is not None:
                    pre_human_txt = custom_txt or ""
                    exit_code = custom_exit if custom_exit is not None else 0
                elif task_entry.void_output and outcome.value == {}:
                    pre_human_txt = ""
                    exit_code = 0
                else:
                    pre_human_txt, exit_code = format_output(outcome.value)

            session.close()
            session_closed = True

            def _emit_daemon_ready() -> None:
                nonlocal emitted_ready
                emitted_ready = True
                if flags.json_output:
                    _write_json_outcome(eff_out, outcome)
                elif pre_human_txt:
                    eff_out.write(pre_human_txt if pre_human_txt.endswith("\n") else f"{pre_human_txt}\n")
                    eff_out.flush()

            acquired_lock, daemon_rc = session.run_deferred_daemon(on_ready=_emit_daemon_ready)
            post_close_rc = daemon_rc
            if not emitted_ready:
                if not acquired_lock and daemon_rc == 0:
                    contended_val = outcome.value
                    if isinstance(contended_val, Mapping):
                        inner_data = contended_val.get("data")
                        if isinstance(inner_data, Mapping):
                            patched_data = dict(inner_data)
                            patched_data["already_running"] = True
                            patched_data["started"] = False
                            patched_val = dict(contended_val)
                            patched_val["data"] = patched_data
                            patched_val["summary"] = "Daemon is already running."
                            outcome = TaskOutcome(
                                ok=True,
                                value=patched_val,
                                event_diagnostics=outcome.event_diagnostics,
                                teardown_diagnostics=outcome.teardown_diagnostics,
                                coalesced=outcome.coalesced,
                                executed_hot=outcome.executed_hot,
                            )
                    if flags.json_output:
                        _write_json_outcome(eff_out, outcome)
                    else:
                        eff_out.write("Daemon is already running.\n")
                        eff_out.flush()
                else:
                    fail_rc = daemon_rc if daemon_rc != 0 else 1
                    post_close_rc = fail_rc
                    exit_code = fail_rc
                    boot_err = ErrorDetail(
                        ErrorCode.DAEMON_UNAVAILABLE,
                        f"Foreground daemon exited before ready (code={fail_rc}).",
                        source_task=task_entry.task_id.value,
                    )
                    outcome = TaskOutcome(
                        ok=False,
                        error=boot_err,
                        event_diagnostics=outcome.event_diagnostics,
                        teardown_diagnostics=outcome.teardown_diagnostics,
                        coalesced=outcome.coalesced,
                        executed_hot=outcome.executed_hot,
                    )
                    if flags.json_output:
                        _write_json_outcome(eff_out, outcome)
                    else:
                        eff_err.write(f"Error [{boot_err.code.value}]: {boot_err.message}\n")
                        eff_err.flush()
        else:
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            if flags.json_output:
                if outcome.ok:
                    _unused_txt, custom_exit = _fallback_decode_output(
                        session,
                        task_entry,
                        outcome.value,
                        render_human=False,
                    )
                    exit_code = custom_exit if custom_exit is not None else 0
                else:
                    exit_code = (
                        130
                        if cancel_token.is_cancelled
                        else _map_error_exit_code(
                            outcome.error.code if outcome.error is not None else ErrorCode.BUSINESS_FAILURE
                        )
                    )
            else:
                exit_code = _render_human_outcome(outcome, task_entry, session, buf_out, buf_err)
                if not outcome.ok and cancel_token.is_cancelled:
                    exit_code = 130

            try:
                session.close()
                session_closed = True
                try:
                    post_close_rc = session.consume_post_close_exit_code()
                except AttributeError:
                    post_close_rc = None
            except BaseException as close_exc:
                session_closed = True
                if outcome.ok or not isinstance(close_exc, Exception):
                    raise

            if flags.json_output:
                _write_json_outcome(eff_out, outcome)
            else:
                out_str = buf_out.getvalue()
                err_str = buf_err.getvalue()
                if out_str:
                    eff_out.write(out_str)
                    eff_out.flush()
                if err_str:
                    eff_err.write(err_str)
                    eff_err.flush()
    except KeyboardInterrupt:
        exit_code = 130
        cancel_err = ErrorDetail(
            ErrorCode.TASK_CANCELLED,
            "Interrupted by SIGINT.",
            source_task=task_entry.task_id.value,
        )
        outcome = TaskOutcome(ok=False, error=cancel_err)
        if (flags.json_output or json_mode_requested) and not emitted_ready:
            _write_json_outcome(eff_out, outcome)
        else:
            eff_err.write("Interrupted.\n")
            eff_err.flush()
    except Exception as exc:
        err_det = (
            exc.detail
            if isinstance(exc, YscbError)
            else ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc), source_task=task_entry.task_id.value)
        )
        exit_code = _map_error_exit_code(err_det.code)
        outcome = TaskOutcome(ok=False, error=err_det)
        if (flags.json_output or json_mode_requested) and not emitted_ready:
            _write_json_outcome(eff_out, outcome)
        else:
            eff_err.write(f"Error [{err_det.code.value}]: {err_det.message}\n")
            if err_det.remediation:
                eff_err.write(f"Hint: {err_det.remediation}\n")
            eff_err.flush()
    finally:
        if session is not None and not session_closed:
            try:
                session.close()
            except (YscbError, OSError):
                pass
            finally:
                if post_close_rc is None:
                    try:
                        post_close_rc = session.consume_post_close_exit_code()
                    except AttributeError:
                        post_close_rc = None

        if post_close_rc is not None and outcome.ok:
            exit_code = int(post_close_rc)

        snap = root_profiler.snapshot()
        duration_ms = round(max(0.0, (time.perf_counter_ns() - cli_entry_ns) / 1_000_000.0), 4)
        rss_after = read_process_rss_kb()
        eff_boot_id = (_read_live_daemon_boot_id(yscb_root) or initial_boot_id) if outcome.executed_hot else ""
        exec_mode_out = "hot" if outcome.executed_hot else "cold"
        dispatched_tasks = _collect_dispatched_tasks_from_tree(task_entry.task_id.value, snap)
        err_obj = outcome.error if not outcome.ok else None
        err_code = err_obj.code.value if err_obj is not None else ""
        attach_diag = (not outcome.ok) or (duration_ms >= flight_cfg.slow_threshold_ms)
        try:
            if flight_router is not None and flight_router.enabled:
                out_ts, out_ms = _now_utc_and_epoch_ms()
                flight_router.record_daily(
                    DailyEventRecord(
                        ts_utc=out_ts,
                        epoch_ms=out_ms,
                        kind="OUT",
                        trace_id=trace_id,
                        daemon_boot_id=eff_boot_id,
                        pid=os.getpid(),
                        exec_mode=exec_mode_out,
                        module=task_entry.task_id.module_id.value,
                        task_id=task_entry.task_id.value,
                        level=LogLevel.INFO if outcome.ok else LogLevel.ERROR,
                        ok=outcome.ok,
                        duration_ms=duration_ms,
                        exit_code=exit_code,
                        message=(
                            _scrub_log_text(err_obj.message, raw_approve_token=flags.approve_token)
                            if err_obj is not None
                            else f"cli_done:{task_entry.task_id.value}"
                        ),
                    )
                )
                flight_router.record_perf(
                    ExecutionTraceRecord(
                        ts_utc=out_ts,
                        epoch_ms=out_ms,
                        trace_id=trace_id,
                        daemon_boot_id=eff_boot_id,
                        pid=os.getpid(),
                        task_id=task_entry.task_id.value,
                        args=redact_cli_args(argv_tup),
                        caller_mode=caller_env.mode.value,
                        caller_cwd=str(eff_cwd),
                        executed_hot=outcome.executed_hot,
                        exit_code=exit_code,
                        ok=outcome.ok,
                        duration_ms=duration_ms,
                        rss_kb=rss_after,
                        rss_delta_kb=rss_after - rss_before,
                        mem_tracked=eff_profile_mem,
                        dispatched_tasks=dispatched_tasks,
                        profiler_tree=snap,
                        error_code=err_code,
                        error_detail=(
                            _redacted_error_detail_dict(err_obj, raw_approve_token=flags.approve_token)
                            if attach_diag
                            else None
                        ),
                        runtime_snapshot=(
                            {
                                "caller_mode": caller_env.mode.value,
                                "executed_hot": outcome.executed_hot,
                                "exit_code": exit_code,
                            }
                            if attach_diag
                            else None
                        ),
                    )
                )
        finally:
            if flight_router is not None:
                flight_router.close()
        if show_profile_stderr:
            eff_err.write(render_profiler_tree(snap, include_mem=eff_profile_mem) + "\n")
            eff_err.flush()

    offline_cli_requested = bool(route.normalized_input.get("offline")) or any(
        tok == "--offline"
        or (tok.lower().startswith("--offline=") and tok.split("=", 1)[1].strip().lower() in {"1", "true", "yes", "on"})
        for tok in argv_tup[:dd_stop]
    )
    _maybe_emit_update_notice(
        host_dir,
        yscb_root,
        env_map,
        eff_err,
        suppress=(
            flags.json_output
            or offline_cli_requested
            or cancel_token.is_cancelled
            or exit_code == 130
            or emitted_ready
        ),
    )
    return exit_code
