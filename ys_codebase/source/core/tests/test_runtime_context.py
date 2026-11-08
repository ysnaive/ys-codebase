"""
Tests for `core.context` (`RuntimeContext`, `RuntimeScope`, `bind_runtime_context`),
`core.loader` (`load_module_from_path`, `get_cached_module`, `clear_loaded_modules`),
and static AST guardrails for `module:core` (A2, B3, B4, B5, C8, C9, D10).
"""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import sys
import tempfile
import unittest

import core
from core import config, contributes, gitignore, guard, loader, locale, symbols, uri, validator
from core.commands import bags, dispatcher
from core.commands.registry import ArgSpec, CommandSpec, ModuleSpec, OptionSpec
from core.context import (
    ExecutionContext,
    RuntimeContext,
    RuntimeScope,
    bind_runtime_context,
    get_env,
    get_env_snapshot,
    get_runtime_context,
    get_virtual_cwd,
    reset_runtime_context,
)
from core.log import LogExecutionScope
from core.platform import process as platform_process
from core.platform import venv as platform_venv
from core.space import registry as space_registry
from core.space import scanner as space_scanner
from core.space import watcher as space_watcher
from core.space.scanner import FileFingerprint, ScanDiffDetail, ScanDiffResult, SnapshotState
from core.space.schema import SpaceConfig
from dev.testing import Requirement, YSCBTestCase, require


@require(Requirement.LOGIC)
class TestCoreRuntimeContextAndLoader(YSCBTestCase):
    """Comprehensive verification for `sub_02_core_runtime_context_and_namespace_loader`."""

    def tearDown(self) -> None:
        loader.clear_loaded_modules("_yscb_mod_test_")
        super().tearDown()

    def test_ft01_runtime_context_isolation_and_concurrent_thread_scopes(self) -> None:
        """
        FT-01: Verify `RuntimeContext` & `bind_runtime_context` isolate `virtual_cwd`, `env`,
        `host_dir`, `yscb_dir`, and `module_name` across concurrent threads without mutating
        `os.environ` or calling `os.chdir()`, and `reset_all_caches()` clears all caches in-place.
        """
        ctx = get_runtime_context()
        self.assertIsInstance(ctx, RuntimeContext)

        # Verify `reset_all_caches()` preserves dict/list object identities
        uri_cache_ref = ctx.uri_schemes_cache
        config_cache_ref = ctx.config_cache
        symbols_cache_ref = ctx.symbols_callable_cache
        ctx.config_cache["dummy_key"] = {"val": 1}
        ctx.symbols_callable_cache["dummy_sym"] = lambda: None
        reset_runtime_context()
        self.assertIs(ctx.uri_schemes_cache, uri_cache_ref)
        self.assertIs(ctx.config_cache, config_cache_ref)
        self.assertIs(ctx.symbols_callable_cache, symbols_cache_ref)
        self.assertEqual(len(ctx.config_cache), 0)
        self.assertEqual(len(ctx.symbols_callable_cache), 0)

        # Concurrent 4-thread isolation verification
        def _worker(idx: int) -> tuple[str, str | None, str | None, str, str]:
            fake_cwd = f"/tmp/virtual_workspace_{idx}"
            fake_host = f"/tmp/virtual_host_{idx}"
            with bind_runtime_context(
                virtual_cwd=fake_cwd,
                env={"YSCB_TEST_ISOLATION_VAR": f"val_{idx}", "PATH": None},
                host_dir=fake_host,
                yscb_dir="ys_codebase",
                module_name=f"mod_{idx}",
            ):
                snap = get_env_snapshot()
                self.assertNotIn("PATH", snap)
                self.assertEqual(snap.get("YSCB_TEST_ISOLATION_VAR"), f"val_{idx}")
                return (
                    get_virtual_cwd(),
                    get_env("YSCB_TEST_ISOLATION_VAR"),
                    uri.get_module_context(),
                    uri.get_host_dir(),
                    uri.get_yscb_root(),
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_worker, range(8)))

        for idx, (vcwd, env_val, mod_ctx, host_dir, yscb_dir) in enumerate(results):
            self.assertTrue(vcwd.endswith(f"virtual_workspace_{idx}"))
            self.assertEqual(env_val, f"val_{idx}")
            self.assertEqual(mod_ctx, f"mod_{idx}")
            self.assertTrue(host_dir.endswith(f"virtual_host_{idx}"))
            self.assertTrue(yscb_dir.endswith("ys_codebase"))

        # Outside the context, `YSCB_TEST_ISOLATION_VAR` must not exist in `os.environ`
        self.assertIsNone(get_env("YSCB_TEST_ISOLATION_VAR"))
        self.mark_passed()

    def test_ft02_et01_et02_loader_namespace_fingerprint_and_atomic_rollback(self) -> None:
        """
        FT-02, ET-01, ET-02: Verify `core.loader.load_module_from_path`:
        1. Rejects module keys without `_yscb_mod_` prefix (`ET-02`).
        2. Caches by `(mtime_ns, size)` fingerprint and reloads when modified (`FT-02`).
        3. Rolls back `sys.modules[module_key]` atomically when `exec_module` raises (`ET-01`).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            mod_file = Path(tmp_dir) / "sample_mod.py"
            mod_file.write_text("VALUE = 10\n", encoding="utf-8")

            # ET-02: Reject non-prefixed module key
            with self.assertRaises(ValueError):
                loader.load_module_from_path("bad_prefix_key", mod_file)

            key = "_yscb_mod_test_sample"
            mod1 = loader.load_module_from_path(key, mod_file)
            self.assertEqual(getattr(mod1, "VALUE", None), 10)
            self.assertIs(loader.get_cached_module(key), mod1)
            self.assertIs(sys.modules.get(key), mod1)

            # Cache hit with identical fingerprint
            mod2 = loader.load_module_from_path(key, mod_file)
            self.assertIs(mod1, mod2)

            # Modify file content (changes size & mtime_ns) -> triggers reload
            mod_file.write_text("VALUE = 9999\nEXTRA = 'reloaded'\n", encoding="utf-8")
            mod3 = loader.load_module_from_path(key, mod_file)
            self.assertIsNot(mod3, mod1)
            self.assertEqual(getattr(mod3, "VALUE", None), 9999)

            # ET-01: Atomic rollback when newly loaded module raises during exec_module
            broken_file = Path(tmp_dir) / "broken_mod.py"
            broken_file.write_text("PARTIAL = 1\nraise RuntimeError('boom in import')\n", encoding="utf-8")
            broken_key = "_yscb_mod_test_broken"

            with self.assertRaises(RuntimeError):
                loader.load_module_from_path(broken_key, broken_file)

            self.assertNotIn(broken_key, sys.modules)
            self.assertIsNone(loader.get_cached_module(broken_key))

            # ET-01b: If a previous valid version was in sys.modules, failed reload restores prior module
            mod_file.write_text("raise RuntimeError('reload failure')\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                loader.load_module_from_path(key, mod_file, reload_if_changed=True)
            self.assertIs(sys.modules.get(key), mod3)
            self.assertIs(loader.get_cached_module(key), mod3)

            # Alias cleanup on clear_loaded_modules
            alias_key = "_yscb_alias_test_demo_mod"
            mod_file.write_text("VALUE = 300\n", encoding="utf-8")
            st = os.stat(mod_file)
            os.utime(mod_file, ns=(st.st_atime_ns, st.st_mtime_ns + 4_000_000_000))
            mod4 = loader.load_module_from_path(
                key, mod_file, alias_keys=(alias_key,), reload_if_changed=True
            )
            self.assertIs(sys.modules.get(alias_key), mod4)
            loader.clear_loaded_modules(prefix=key)
            self.assertNotIn(key, sys.modules)
            self.assertNotIn(alias_key, sys.modules)
        self.mark_passed()

    def test_ft03_et04_et05_ast_guardrails_pep562_and_frozen_dataclasses(self) -> None:
        """
        FT-03, ET-04, ET-05:
        1. AST scan across all non-test `.py` files in `ys_codebase/source/core/` for A2, B3, B4, B5, C8, C9, D10.
        2. PEP 562 module-level `__getattr__` backward-compatibility (`ET-04`).
        3. `@dataclass(frozen=True)` immutability across all 12 core dataclasses (`ET-05`).
        """
        core_pkg_root = Path(core.__file__).resolve().parent
        core_module_root = core_pkg_root.parent

        py_files = [
            p
            for p in core_module_root.rglob("*.py")
            if "tests" not in p.parts
        ]
        self.assertGreater(len(py_files), 20)

        global_violations: list[str] = []
        input_violations: list[str] = []
        sys_exit_violations: list[str] = []
        getcwd_violations: list[str] = []
        loader_violations: list[str] = []
        unfrozen_dataclass_violations: list[str] = []
        top_level_mutable_violations: list[str] = []

        for py_file in py_files:
            rel_path = py_file.relative_to(core_module_root).as_posix()
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel_path)

            # Check top-level statements for mutable literals (`list`, `dict`, `set`)
            for stmt in tree.body:
                target_Value = None
                if isinstance(stmt, ast.Assign):
                    target_Value = stmt.value
                elif isinstance(stmt, ast.AnnAssign):
                    target_Value = stmt.value
                if isinstance(target_Value, (ast.List, ast.Dict, ast.Set)):
                    top_level_mutable_violations.append(f"{rel_path}:{stmt.lineno}")

            for node in ast.walk(tree):
                # C8: No `global` statements
                if isinstance(node, ast.Global):
                    global_violations.append(f"{rel_path}:{node.lineno} ({','.join(node.names)})")

                # C9: Every `@dataclass` in `core/` must specify `frozen=True`
                if isinstance(node, ast.ClassDef):
                    for dec in node.decorator_list:
                        is_dc = False
                        is_frozen = False
                        if isinstance(dec, ast.Name) and dec.id == "dataclass":
                            is_dc = True
                        elif isinstance(dec, ast.Call):
                            func = dec.func
                            if (isinstance(func, ast.Name) and func.id == "dataclass") or (
                                isinstance(func, ast.Attribute) and func.attr == "dataclass"
                            ):
                                is_dc = True
                                for kw in dec.keywords:
                                    if (
                                        kw.arg == "frozen"
                                        and isinstance(kw.value, ast.Constant)
                                        and kw.value.value is True
                                    ):
                                        is_frozen = True
                        if is_dc and not is_frozen:
                            unfrozen_dataclass_violations.append(f"{rel_path}:{node.lineno}:{node.name}")

                if isinstance(node, ast.Call):
                    # A2: No `input()` calls
                    if isinstance(node.func, ast.Name) and node.func.id == "input":
                        input_violations.append(f"{rel_path}:{node.lineno}")

                    # B3: No `sys.exit()` outside `__main__` blocks or `scripts/`
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "sys"
                        and node.func.attr == "exit"
                    ):
                        if not rel_path.startswith("scripts/") and rel_path not in {
                            "core/cli.py",
                            "core/platform/daemon_probe.py",
                        }:
                            sys_exit_violations.append(f"{rel_path}:{node.lineno}")

                    # B4: No `os.getcwd()` or `Path.cwd()` outside `core/context.py`
                    if rel_path != "core/context.py":
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr == "getcwd"
                        ):
                            getcwd_violations.append(f"{rel_path}:{node.lineno}")
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "Path"
                            and node.func.attr == "cwd"
                        ):
                            getcwd_violations.append(f"{rel_path}:{node.lineno}")

                    # D10: No `spec_from_file_location` outside `core/loader.py`
                    if rel_path != "core/loader.py":
                        if (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "spec_from_file_location"
                        ) or (
                            isinstance(node.func, ast.Name)
                            and node.func.id == "spec_from_file_location"
                        ):
                            loader_violations.append(f"{rel_path}:{node.lineno}")

        self.assertEqual(global_violations, [], f"C8 global violations: {global_violations}")
        self.assertEqual(
            top_level_mutable_violations,
            [],
            f"C8 top-level mutable literal violations: {top_level_mutable_violations}",
        )
        self.assertEqual(
            unfrozen_dataclass_violations,
            [],
            f"C9 unfrozen dataclass violations: {unfrozen_dataclass_violations}",
        )
        self.assertEqual(input_violations, [], f"A2 input() violations: {input_violations}")
        self.assertEqual(sys_exit_violations, [], f"B3 sys.exit() violations: {sys_exit_violations}")
        self.assertEqual(getcwd_violations, [], f"B4 getcwd/cwd violations: {getcwd_violations}")
        self.assertEqual(loader_violations, [], f"D10 loader violations: {loader_violations}")

        # ET-04: Verify PEP 562 `__getattr__` proxy identity with `RuntimeContext`
        ctx = get_runtime_context()
        from core.symbols import _RESOLVED_CALLABLE_CACHE

        self.assertIs(_RESOLVED_CALLABLE_CACHE, ctx.symbols_callable_cache)
        self.assertIs(uri._SCHEMES_CACHE, ctx.uri_schemes_cache)
        self.assertIs(uri._TOKEN_MAP_CACHE, ctx.uri_token_map_cache)
        self.assertIs(config.ConfigManager._cache, ctx.config_cache)
        self.assertIs(contributes._MERGED_MEMORY_CACHE, ctx.contributes_merged_cache)
        self.assertIs(locale._LOCALE_FILE_CACHE, ctx.locale_file_cache)
        self.assertIs(gitignore._CUSTOM_ROOT_DYNAMIC_STORE, ctx.gitignore_custom_root_store)
        self.assertIs(validator._SIGNATURE_PARSE_CACHE, ctx.validator_signature_cache)
        self.assertIs(dispatcher._MODULE_CACHE, ctx.dispatcher_module_cache)
        self.assertIs(platform_venv._ACTIVE_TEST_SOURCE_PATHS, ctx.venv_active_test_source_paths)
        self.assertIs(space_registry._DEFAULT_REGISTRIES, ctx.space_default_registries)
        self.assertIs(space_scanner._DEFAULT_SCANNERS, ctx.space_default_scanners)
        self.assertIs(space_watcher._SUBSCRIBERS, ctx.space_subscribers)
        self.assertIsNone(platform_process._CAN_SPAWN_DAEMON_CACHE)

        # ET-05: Verify `FrozenInstanceError` on all frozen dataclasses
        exec_ctx = ExecutionContext(module_name="core", args=None)
        self.assertIsNone(exec_ctx.args)
        with self.assertRaises(FrozenInstanceError):
            exec_ctx.module_name = "mutated"  # type: ignore[misc]

        rt_scope = RuntimeScope(virtual_cwd="/tmp")
        with self.assertRaises(FrozenInstanceError):
            rt_scope.virtual_cwd = "/other"  # type: ignore[misc]

        log_scope = LogExecutionScope(component="core")
        with self.assertRaises(FrozenInstanceError):
            log_scope.component = "other"  # type: ignore[misc]

        arg_spec = ArgSpec(name="target")
        with self.assertRaises(FrozenInstanceError):
            arg_spec.name = "other"  # type: ignore[misc]

        opt_spec = OptionSpec(canonical_name="--flag")
        with self.assertRaises(FrozenInstanceError):
            opt_spec.canonical_name = "--other"  # type: ignore[misc]

        cmd_spec = CommandSpec(name="test")
        with self.assertRaises(FrozenInstanceError):
            cmd_spec.name = "other"  # type: ignore[misc]

        mod_spec = ModuleSpec(module_name="core")
        with self.assertRaises(FrozenInstanceError):
            mod_spec.module_name = "other"  # type: ignore[misc]

        space_cfg = SpaceConfig(qualified_name="core/test", owner="core", short_name="test")
        with self.assertRaises(FrozenInstanceError):
            space_cfg.short_name = "other"  # type: ignore[misc]

        fp = FileFingerprint(rel_path="a.py", mtime_ns=1, ctime_ns=1, size=1, content_hash="abc")
        with self.assertRaises(FrozenInstanceError):
            fp.size = 2  # type: ignore[misc]

        diff_detail = ScanDiffDetail(added={"a.py"})
        with self.assertRaises(FrozenInstanceError):
            diff_detail.added = set()  # type: ignore[misc]

        diff_res = ScanDiffResult(added_count=1, from_generation=0, to_generation=1)
        with self.assertRaises(FrozenInstanceError):
            diff_res.to_generation = 2  # type: ignore[misc]

        snap_state = SnapshotState(head_generation=1, merkle_root="abc")
        with self.assertRaises(FrozenInstanceError):
            snap_state.head_generation = 2  # type: ignore[misc]

        # Verify all frozen dataclasses with container fields are hashable and SpaceConfig normalizes tuples
        for obj in (
            exec_ctx,
            rt_scope,
            log_scope,
            arg_spec,
            opt_spec,
            cmd_spec,
            mod_spec,
            space_cfg,
            fp,
            diff_detail,
            diff_res,
            snap_state,
            bags.CmdOption(name="opt", params=["a", "b"]),
            bags.CmdBags(command="run", args=["x"]),
        ):
            self.assertIsInstance(hash(obj), int)

        space_cfg_lists = SpaceConfig(
            qualified_name="core/list_norm",
            owner="core",
            short_name="list_norm",
            unresolved_presets=["p1"],  # type: ignore[arg-type]
            unresolved_compose=["c1"],  # type: ignore[arg-type]
            uri_warnings=["w1"],  # type: ignore[arg-type]
        )
        self.assertIsInstance(space_cfg_lists.unresolved_presets, tuple)
        self.assertIsInstance(space_cfg_lists.unresolved_compose, tuple)
        self.assertIsInstance(space_cfg_lists.uri_warnings, tuple)
        self.assertIsInstance(hash(space_cfg_lists), int)

        # Verify metaclass property setters on ConfigManager and ContributesValidator
        config.ConfigManager._cache = {"custom_mod": {"k": "v"}}
        self.assertEqual(ctx.config_cache.get("custom_mod"), {"k": "v"})
        config.ConfigManager._cache = {}
        validator.ContributesValidator._SIGNATURE_PARSE_CACHE = {"str": {"type": "str"}}
        self.assertIn("str", ctx.validator_signature_cache)
        validator.ContributesValidator._SIGNATURE_PARSE_CACHE = {}

        # Verify RuntimeScope priority over uri_tls and empty virtual_cwd filtering
        uri.set_host_dir("/tmp/stale_tls_host")
        try:
            with bind_runtime_context(host_dir="/tmp/scoped_host", virtual_cwd="   "):
                self.assertEqual(
                    uri.get_host_dir(), os.path.normpath(os.path.abspath("/tmp/scoped_host"))
                )
        finally:
            reset_runtime_context()
        self.assertIsNone(getattr(ctx.uri_tls, "active_host_dir", None))
        self.mark_passed()

    def test_ft04_et03_uri_reconcile_undefined_and_guard_system_exit(self) -> None:
        """
        FT-04 & ET-03:
        1. `uri.reconcile_undefined_uri` raises `UndefinedURIError` without calling `input()` or `sys.exit()`,
           and raises `CyclicURIDependencyError` on reentrant token reconciliation (`ET-03`).
        2. `guard.guard_dispatch` raises `SystemExit(126)` when blocked (`FT-04`).
        """
        with self.assertRaises(uri.UndefinedURIError):
            uri.reconcile_undefined_uri("nonexistent_token_xyz", "nonexistent_token_xyz://foo")

        # ET-03: Reentrant token reconciliation raises `CyclicURIDependencyError`
        reconciling = uri._get_reconciling_tokens() if hasattr(uri, "_get_reconciling_tokens") else None
        if reconciling is not None:
            reconciling.add("cyclic_token_abc")
            try:
                with self.assertRaises(uri.CyclicURIDependencyError):
                    uri.reconcile_undefined_uri("cyclic_token_abc", "cyclic_token_abc://bar")
            finally:
                reconciling.discard("cyclic_token_abc")

        # FT-04: `guard_dispatch` raises `SystemExit(126)` when unauthorized direct execution is detected
        with bind_runtime_context(
            env={
                "YSCB_TESTING": "0",
                "YSCB_HOST_DISPATCH_TOKEN": None,
                "YSCB_HOST_DIR": None,
            }
        ):
            with self.assertRaises(SystemExit) as cm:
                guard.guard_dispatch("core")
            self.assertEqual(cm.exception.code, 126)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
