"""
Official test suite for core.uri semantic URI protocol resolution, @/ syntax, to_uri, and JIT reconciliation.
"""
import io
import os
import tempfile
import threading
import time
from contextlib import redirect_stdout

from dev.testing import YSCBTestCase, require, Requirement
from core import uri, vfs
from core.config import ConfigManager
from core.uri import UndefinedURIError, CyclicURIDependencyError, UndefinedModuleContextError
from tests import load_core_cli_module


@require(Requirement.ENV)
class TestCoreURI(YSCBTestCase):
    def test_protocol_resolution_standards(self):
        """Verify standard protocol resolutions and explicit config/ path."""
        core_cfg = "config://core/config.project.json"
        if not vfs.exists(core_cfg):
            vfs.write_json(core_cfg, {"project_root": "./"}, indent=2)

        canonical_protocols = [
            "project://", "yscb://", "yscb.host://", "module.mirror://", "snapshot://",
            "module://", "config://", "config.local://", "cache://", "storage://", "storage.local://",
            "module.source://", "module.build://", "module.release://"
        ]
        for p in canonical_protocols:
            res = uri.resolve(p, interactive=False)
            self.assertIsInstance(res, str, f"Failed resolving {p}")
            self.assertGreater(len(res), 0, f"Empty resolution for {p}")

        cfg_root = uri.resolve("config://", interactive=False)
        self.assertTrue(cfg_root.endswith("config") and not cfg_root.endswith(".config"), f"config:// must be explicit config/, got {cfg_root}")
        cfg_local_root = uri.resolve("config.local://", interactive=False)
        self.assertTrue(cfg_local_root.replace("\\", "/").endswith("/.config.local"), f"config.local:// must resolve to .config.local, got {cfg_local_root}")
        storage_local_root = uri.resolve("storage.local://", interactive=False)
        self.assertTrue(storage_local_root.replace("\\", "/").endswith("/.storage.local"), f"storage.local:// must resolve to .storage.local, got {storage_local_root}")
        self.mark_passed()

    def test_option_b_canonical_rooting_and_at_syntax(self):
        """Verify explicit module addressing, @/ active context, and root space."""
        res_dev = uri.resolve("storage://dev/release_manifest.json")
        self.assertTrue(res_dev.replace("\\", "/").endswith("storage/dev/release_manifest.json"))
        self.assertNotIn("core/dev", res_dev.replace("\\", "/"))

        with uri.module_scope("agents-workflow"):
            res_at = uri.resolve("storage://@/release_manifest.json")
            self.assertTrue(res_at.replace("\\", "/").endswith("storage/agents-workflow/release_manifest.json"))

            res_cfg_local_at = uri.resolve("config.local://@/config.local.json")
            self.assertTrue(res_cfg_local_at.replace("\\", "/").endswith(".config.local/agents-workflow/config.local.json"))

            res_stg_local_at = uri.resolve("storage.local://@/release_manifest.json")
            self.assertTrue(res_stg_local_at.replace("\\", "/").endswith(".storage.local/agents-workflow/release_manifest.json"))

            res_cache_at = uri.resolve("cache://@/resolved_contents/test.md")
            self.assertTrue(res_cache_at.replace("\\", "/").endswith(".cache/agents-workflow/resolved_contents/test.md"))

        res_storage_root = uri.resolve("storage://")
        self.assertTrue(res_storage_root.replace("\\", "/").endswith("storage"))
        self.mark_passed()

    def test_undefined_module_context_error(self):
        """Verify @/ without active context raises UndefinedModuleContextError."""
        with uri.module_scope(None):
            with self.assertRaises(UndefinedModuleContextError) as ctx:
                uri.resolve("storage://@/file.json")
            self.assertIn("Cannot resolve active module placeholder '@'", str(ctx.exception))
        self.mark_passed()

    def test_security_path_traversal_guard(self):
        """Verify path traversal attempting to escape root is blocked."""
        with uri.module_scope("core"):
            with self.assertRaises(PermissionError):
                uri.resolve("storage://@/../../../../../../etc/passwd")
            with self.assertRaises(PermissionError):
                uri.resolve("storage://../storage_sibling/hack.txt")
            with self.assertRaises(PermissionError):
                uri.resolve("config.local://@/../../../../../../etc/passwd")
            with self.assertRaises(PermissionError):
                uri.resolve("storage.local://../.storage.local_sibling/hack.txt")
        self.mark_passed()

    def test_deprecated_scheme_redirection_warning(self):
        """Verify legacy *.root:// schemes raise ValueError in pure mode."""
        with self.assertRaises(ValueError):
            uri.resolve("storage.root://dev/data.json")
        self.mark_passed()

    def test_yscb_uri_constant_self_locating(self):
        """Verify yscb:// constant self-locating from __file__ and host context injection."""
        yscb_root = uri.resolve_yscb_root()
        self.assertTrue(os.path.isdir(yscb_root), f"yscb_root must be a valid directory: {yscb_root}")

        dummy_host = os.path.normpath(self.sandbox_dir)
        uri.set_host_dir(dummy_host)
        self.assertEqual(uri.get_host_dir(), dummy_host)

        uri.set_host_dir(None)
        self.mark_passed()

    def test_uninitialized_host_raises_file_not_found(self):
        """Verify _get_host_config raises FileNotFoundError on missing yscb.config.json."""
        empty_dir = os.path.join(self.sandbox_dir, "empty_dir_for_test")
        os.makedirs(empty_dir, exist_ok=True)

        with self.assertRaises(FileNotFoundError) as ctx:
            uri._get_host_config(start_dir=empty_dir)
        self.assertIn("yscb.config.json", str(ctx.exception))
        self.mark_passed()

    def test_project_root_undefined_raises_undefined_uri_error(self):
        """Verify project:// without project_root raises UndefinedURIError in non-interactive mode."""
        core_cfg = "config://core/config.project.json"
        saved = None
        if vfs.exists(core_cfg):
            saved = vfs.read_json(core_cfg)
            vfs.remove(core_cfg)

        try:
            with self.assertRaises(UndefinedURIError) as ctx:
                uri.resolve("project://some/file.txt", interactive=False)
            self.assertIn("project", ctx.exception.scheme)
        finally:
            if saved is not None:
                vfs.write_json(core_cfg, saved, indent=2)
        self.mark_passed()

    def test_registered_schemes_summary(self):
        """Verify list_registered_schemes_summary returns full summary list."""
        summary = uri.list_registered_schemes_summary()
        self.assertIsInstance(summary, list)
        self.assertGreaterEqual(len(summary), 8)
        tokens = [s["token"] for s in summary]
        self.assertIn("project", tokens)
        self.assertIn("module", tokens)
        self.assertIn("config", tokens)
        self.mark_passed()

    def test_cyclic_dependency_protection(self):
        """Verify reconcile_undefined_uri raises CyclicURIDependencyError on self-referencing cycle."""
        uri._reconciling_tokens.add("test_cycle")
        try:
            with self.assertRaises(CyclicURIDependencyError):
                uri.reconcile_undefined_uri("test_cycle", "!undefined", interactive=False)
        finally:
            uri._reconciling_tokens.discard("test_cycle")
        self.mark_passed()

    def test_test_sandbox_env_suppresses_jit_interaction(self):
        """Verify YSCB_TEST_SANDBOX=1 environment suppresses JIT prompt and raises UndefinedURIError."""
        orig_env = os.environ.get("YSCB_TEST_SANDBOX")
        os.environ["YSCB_TEST_SANDBOX"] = "1"
        try:
            with self.assertRaises(UndefinedURIError) as ctx:
                uri.reconcile_undefined_uri("mock_undef", "!undefined", interactive=True)
            self.assertEqual(ctx.exception.scheme, "mock_undef")
        finally:
            if orig_env is not None:
                os.environ["YSCB_TEST_SANDBOX"] = orig_env
            else:
                os.environ.pop("YSCB_TEST_SANDBOX", None)
        self.mark_passed()

    def test_yscb_root_injection_and_scope(self):
        """Verify set_yscb_root, get_yscb_root, yscb_scope, and env override."""
        dummy_dir = os.path.join(self.sandbox_dir, "custom_yscb_root")
        os.makedirs(dummy_dir, exist_ok=True)

        orig_yscb = uri.get_yscb_root()
        try:
            uri.set_yscb_root(dummy_dir)
            self.assertEqual(uri.get_yscb_root(), dummy_dir)
            self.assertEqual(uri.resolve_yscb_root(), dummy_dir)

            nested_dir = os.path.join(self.sandbox_dir, "nested_yscb_root")
            os.makedirs(nested_dir, exist_ok=True)
            with uri.yscb_scope(nested_dir):
                self.assertEqual(uri.get_yscb_root(), nested_dir)
                self.assertEqual(uri.resolve_yscb_root(), nested_dir)

            self.assertEqual(uri.get_yscb_root(), dummy_dir)

            with self.assertRaises(RuntimeError):
                with uri.yscb_scope(nested_dir):
                    self.assertEqual(uri.get_yscb_root(), nested_dir)
                    raise RuntimeError("Intentional error inside scope")
            self.assertEqual(uri.get_yscb_root(), dummy_dir)
        finally:
            uri.set_yscb_root(orig_yscb)

        orig_env = os.environ.get("YSCB_ROOT_DIR")
        try:
            os.environ["YSCB_ROOT_DIR"] = dummy_dir
            with uri.yscb_scope(None):
                self.assertEqual(uri.get_yscb_root(), dummy_dir)
                self.assertEqual(uri.resolve_yscb_root(), dummy_dir)
        finally:
            if orig_env is not None:
                os.environ["YSCB_ROOT_DIR"] = orig_env
            else:
                os.environ.pop("YSCB_ROOT_DIR", None)

        self.assertIsInstance(ConfigManager._get_yscb_root(), str)
        self.mark_passed()

    def test_undefined_uri_quick_fix_hints(self):
        """Verify format_undefined_uri_hint and UndefinedURIError Quick fix hints."""
        h_proj = uri.format_undefined_uri_hint("project", "core", "project_root")
        self.assertIn("python yscb.py config set core project_root ./", h_proj)

        h_wf = uri.format_undefined_uri_hint("workflow.plans", "agents-workflow", "paths.plans")
        self.assertEqual(h_wf, "python yscb.py config set agents-workflow paths.plans <path>")

        h_custom = uri.format_undefined_uri_hint("custom.data", "my-mod", "data_dir")
        self.assertEqual(h_custom, "python yscb.py config set my-mod data_dir <path>")

        err = uri.UndefinedURIError("workflow.docs", "agents-workflow", "paths.docs")
        self.assertIn("Semantic URI 'workflow.docs://' is undefined (!undefined).", str(err))
        self.assertIn("Quick fix: python yscb.py config set agents-workflow paths.docs <path>", str(err))
        self.mark_passed()

    def test_invalid_uri_string_raises_value_error(self):
        """驗證非法 URI 字串與未知協議拋出 ValueError。"""
        with self.assertRaises(ValueError):
            uri.resolve("relative/path/not/uri")
        with self.assertRaises(ValueError):
            uri.resolve("unknown_scheme://foo")
        self.mark_passed()

    def test_context_managers_auto_restore_and_exception_safety(self):
        """驗證 module_scope 與 host_scope 上下文管理器自動復原與例外安全性。"""
        orig_mod = uri.get_module_context()
        with uri.module_scope("test_mod"):
            self.assertEqual(uri.get_module_context(), "test_mod")
        self.assertEqual(uri.get_module_context(), orig_mod)

        with self.assertRaises(RuntimeError):
            with uri.module_scope("temp_error_scope"):
                raise RuntimeError("Intentional error")
        self.assertEqual(uri.get_module_context(), orig_mod)
        self.mark_passed()

    def test_module_build_uri_resolution_and_perf(self):
        """驗證 module.build:// 解析至 .build/ 與效能。"""
        bld_root = uri.resolve("module.build://")
        self.assertIn(".build", bld_root)

        bld_core = uri.resolve("module.build://core")
        self.assertIn(os.path.join(".build", "core"), bld_core)

        target = "module.build://test_clean_sub_mod/1.0.0.build"
        res = uri.resolve(target)
        try:
            vfs.makedirs(target, exist_ok=True)
            self.assertTrue(os.path.isdir(res))
        finally:
            if os.path.isdir(res):
                os.removedirs(res)

        start = time.perf_counter()
        for _ in range(50):
            uri.resolve("module.build://core")
        elapsed = (time.perf_counter() - start) / 50
        self.assertLess(elapsed, 0.005)
        self.mark_passed()

    def test_thread_local_scope_isolation_and_subpath_traversal_guard(self):
        """驗證 host_scope / module_scope 跨執行緒 TLS 隔離，以及 URI 子路徑 '..' 逃逸阻斷且不誤傷 sval '..'。"""
        results = {}
        barrier = threading.Barrier(2)
        with tempfile.TemporaryDirectory() as tmp_root:
            host_a = os.path.join(tmp_root, "fake_host_a")
            host_b = os.path.join(tmp_root, "fake_host_b")
            for hd in (host_a, host_b):
                os.makedirs(hd, exist_ok=True)
                with open(os.path.join(hd, "yscb.config.json"), "w", encoding="utf-8") as f:
                    f.write('{"yscb_root": "./ys_codebase"}\n')

            def worker(name: str, host_p: str, mod_p: str):
                with uri.host_scope(host_p, "ys_codebase"):
                    with uri.module_scope(mod_p):
                        barrier.wait(timeout=5.0)
                        results[name] = (
                            uri.get_module_context(),
                            os.path.normpath(uri.resolve("yscb.host://", interactive=False)),
                        )

            t1 = threading.Thread(target=worker, args=("t1", host_a, "mod_a"))
            t2 = threading.Thread(target=worker, args=("t2", host_b, "mod_b"))
            t1.start()
            t2.start()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)

            self.assertEqual(results["t1"], ("mod_a", os.path.normpath(os.path.abspath(host_a))))
            self.assertEqual(results["t2"], ("mod_b", os.path.normpath(os.path.abspath(host_b))))

        proj_root = uri.resolve("project://", interactive=False)
        self.assertTrue(os.path.isabs(proj_root))

        for bad_uri in (
            "project://../../etc/passwd",
            "yscb://../escape",
            "config://core/../../secret",
            "module://core/../../outside",
            "project://C:/Windows/System32",
        ):
            with self.assertRaises(PermissionError, msg=f"Expected PermissionError for {bad_uri}"):
                uri.resolve(bad_uri, interactive=False)

        self.mark_passed()

    def test_to_uri_longest_prefix_and_cli_uri_subcommands(self):
        """驗證 uri.to_uri 最長前綴優先反向推導、重入回退型別、invalidate_uri_cache 與 cli.uri 子命令。"""
        mod_file_abs = uri.resolve("module://core/manifest.json")
        self.assertEqual(uri.to_uri(mod_file_abs), "module://core/manifest.json")

        cfg_file_abs = uri.resolve("config://core/config.project.json")
        self.assertEqual(uri.to_uri(cfg_file_abs), "config://core/config.project.json")

        yscb_root_abs = uri.resolve("yscb://")
        self.assertEqual(uri.to_uri(yscb_root_abs), "yscb://")

        ext_path = "/tmp/unrelated_external_path_xyz/file.txt"
        self.assertEqual(uri.to_uri(ext_path), os.path.normpath(os.path.abspath(ext_path)))

        # Verify reentrancy guard returns list of dicts (not empty dict)
        prev_active = getattr(uri._URI_REENTRANCY, "active", False)
        try:
            uri._URI_REENTRANCY.active = True
            fallback_schemes = uri._get_merged_uri_schemes(yscb_root_abs)
            self.assertIsInstance(fallback_schemes, list)
            self.assertGreater(len(fallback_schemes), 0)
            self.assertIsInstance(fallback_schemes[0], dict)
        finally:
            uri._URI_REENTRANCY.active = prev_active

        uri.invalidate_uri_cache()
        self.assertEqual(uri._SCHEMES_CACHE, {})
        self.assertEqual(uri._TOKEN_MAP_CACHE, {})

        # Verify CLI uri subcommands and error branches
        cli_mod = load_core_cli_module("_test_core_cli_uri")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli_mod.uri(["list"]), 0)
            self.assertEqual(cli_mod.uri(["resolve", "yscb://"]), 0)
            self.assertEqual(cli_mod.uri(["to-uri", yscb_root_abs]), 0)
            self.assertEqual(cli_mod.uri(["check"]), 0)
        out = buf.getvalue()
        self.assertIn("YS-Codebase Registered URI Schemes Catalog", out)
        self.assertIn("yscb://", out)

        # Negative error branches
        self.assertEqual(cli_mod.uri(["resolve"]), 1)
        self.assertEqual(cli_mod.uri(["to-uri"]), 1)
        self.assertEqual(cli_mod.uri(["resolve", "unknown_scheme_xyz://foo"]), 1)
        self.assertEqual(cli_mod.uri(["unknown_sub"]), 1)
        self.mark_passed()
