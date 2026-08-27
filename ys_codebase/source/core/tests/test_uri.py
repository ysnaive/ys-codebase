"""
Official test suite for core.uri VFS, semantic URI protocol resolution, Option B @/ syntax, and JIT reconciliation.
"""
import os
import json
import warnings
from dev.testing import YSCBTestCase
from core import uri
from core.uri import ExecutionContext, UndefinedURIError, CyclicURIDependencyError, UndefinedModuleContextError

class TestCoreURI(YSCBTestCase):
    def test_protocol_resolution_standards(self):
        """Verify standard protocol resolutions and explicit config/ path (Option B)."""
        # Ensure core config has project_root for project:// resolution
        core_cfg = "config://core/config.project.json"
        if not uri.exists(core_cfg):
            uri.write_json(core_cfg, {"project_root": "./"}, indent=2)
            
        canonical_protocols = [
            "project://", "yscb://", "yscb.host://", "module.mirror://", "snapshot://",
            "module://", "config://", "cache://", "storage://",
            "module.source://", "module.build://", "module.release://"
        ]
        for p in canonical_protocols:
            res = uri.resolve(p, interactive=False)
            self.assertTrue(isinstance(res, str) and len(res) > 0, f"Failed resolving {p}")
            
        # Verify explicit config/ directory (not .config)
        cfg_root = uri.resolve("config://", interactive=False)
        self.assertTrue(cfg_root.endswith("config") and not cfg_root.endswith(".config"), f"config:// must be explicit config/, got {cfg_root}")
        self.mark_passed()

    def test_option_b_canonical_rooting_and_at_syntax(self):
        """FT-02, FT-03: Verify Option B explicit module, @/ active context, and root space."""
        # 1. Explicit cross-module addressing (Zero Ambiguity)
        res_dev = uri.resolve("storage://dev/release_manifest.json")
        self.assertTrue(res_dev.replace("\\", "/").endswith("storage/dev/release_manifest.json"))
        self.assertNotIn("core/dev", res_dev.replace("\\", "/"))

        # 2. Active module context self-introspection (@/)
        with uri.module_scope("agents-workflow"):
            res_at = uri.resolve("storage://@/release_manifest.json")
            self.assertTrue(res_at.replace("\\", "/").endswith("storage/agents-workflow/release_manifest.json"))

            res_cache_at = uri.resolve("cache://@/resolved_contents/test.md")
            self.assertTrue(res_cache_at.replace("\\", "/").endswith(".cache/agents-workflow/resolved_contents/test.md"))

        # 3. Root space resolution
        res_storage_root = uri.resolve("storage://")
        self.assertTrue(res_storage_root.replace("\\", "/").endswith("storage"))
        self.mark_passed()

    def test_undefined_module_context_error(self):
        """ET-01, EC-01: Verify @/ without active context raises UndefinedModuleContextError."""
        # Force clear active module context
        with uri.module_scope(None):
            with self.assertRaises(UndefinedModuleContextError) as ctx:
                uri.resolve("storage://@/file.json")
            self.assertIn("Cannot resolve active module placeholder '@'", str(ctx.exception))
        self.mark_passed()

    def test_security_path_traversal_guard(self):
        """ET-02, EC-02: Verify path traversal attempting to escape root is blocked."""
        with uri.module_scope("core"):
            with self.assertRaises(PermissionError):
                uri.resolve("storage://@/../../../../../../etc/passwd")
        self.mark_passed()

    def test_deprecated_scheme_redirection_warning(self):
        """ET-03, EC-03: Verify legacy *.root:// schemes raise ValueError in pure mode."""
        with self.assertRaises(ValueError):
            uri.resolve("storage.root://dev/data.json")
        self.mark_passed()

    def test_yscb_uri_constant_self_locating(self):
        """Verify yscb:// constant self-locating from __file__ and host context injection."""
        yscb_root = uri._get_yscb_root()
        self.assertTrue(os.path.isdir(yscb_root), f"yscb_root must be a valid directory: {yscb_root}")
        
        # Test set_host_dir / get_host_dir
        dummy_host = os.path.normpath(self.sandbox_dir)
        uri.set_host_dir(dummy_host)
        self.assertEqual(uri.get_host_dir(), dummy_host)
        
        # Reset host dir
        uri.set_host_dir(None)
        self.mark_passed()

    def test_uninitialized_host_raises_file_not_found(self):
        """Verify _get_host_config raises FileNotFoundError on missing yscb.config.json (Zero Speculation)."""
        empty_dir = os.path.join(self.sandbox_dir, "empty_dir_for_test")
        os.makedirs(empty_dir, exist_ok=True)
        
        with self.assertRaises(FileNotFoundError) as ctx:
            uri._get_host_config(start_dir=empty_dir)
        self.assertIn("yscb.config.json", str(ctx.exception))
        self.mark_passed()

    def test_project_root_undefined_raises_undefined_uri_error(self):
        """FT-08, ET-03: Verify project:// without project_root raises UndefinedURIError in non-interactive mode."""
        core_cfg = "config://core/config.project.json"
        saved = None
        if uri.exists(core_cfg):
            saved = uri.read_json(core_cfg)
            uri.remove(core_cfg)
            
        try:
            with self.assertRaises(UndefinedURIError) as ctx:
                uri.resolve("project://some/file.txt", interactive=False)
            self.assertIn("project", ctx.exception.scheme)
        finally:
            if saved is not None:
                uri.write_json(core_cfg, saved, indent=2)
        self.mark_passed()

    def test_registered_schemes_summary(self):
        """FT-07: Verify list_registered_schemes_summary returns full summary list."""
        summary = uri.list_registered_schemes_summary()
        self.assertTrue(isinstance(summary, list))
        self.assertTrue(len(summary) >= 8)
        tokens = [s["token"] for s in summary]
        self.assertIn("project", tokens)
        self.assertIn("module", tokens)
        self.assertIn("config", tokens)
        self.mark_passed()

    def test_cyclic_dependency_protection(self):
        """ET-01: Verify reconcile_undefined_uri raises CyclicURIDependencyError on self-referencing cycle."""
        uri._reconciling_tokens.add("test_cycle")
        try:
            with self.assertRaises(CyclicURIDependencyError):
                uri.reconcile_undefined_uri("test_cycle", "!undefined", interactive=False)
        finally:
            uri._reconciling_tokens.discard("test_cycle")
        self.mark_passed()

    def test_vfs_atomic_io(self):
        """Verify atomic text and json I/O with tmp replacement in sandbox."""
        test_f = f"{self.sandbox_uri}/test_vfs_atomic.txt"
        test_j = f"{self.sandbox_uri}/test_vfs_atomic.json"
        
        uri.write_text(test_f, "Hello VFS World")
        self.assertTrue(uri.exists(test_f))
        self.assertEqual(uri.read_text(test_f), "Hello VFS World")
        
        data = {"key": "value", "count": 100}
        uri.write_json(test_j, data)
        self.assertTrue(uri.exists(test_j))
        self.assertEqual(uri.read_json(test_j), data)
        
        uri.remove(test_f)
        uri.remove(test_j)
        self.assertFalse(uri.exists(test_f))
        self.assertFalse(uri.exists(test_j))
        self.mark_passed()

    def test_vfs_directory_operations(self):
        """Verify makedirs, listdir, rmtree, copy, move in sandbox."""
        d_uri = f"{self.sandbox_uri}/vfs_test_dir/subdir"
        uri.makedirs(d_uri)
        self.assertTrue(uri.is_dir(d_uri))
        
        f1 = f"{d_uri}/f1.txt"
        uri.write_text(f1, "file1")
        self.assertTrue(uri.is_file(f1))
        self.assertIn("f1.txt", uri.listdir(d_uri))
        
        # Test copy file
        f2 = f"{d_uri}/f2.txt"
        uri.copy(f1, f2)
        self.assertTrue(uri.exists(f2))
        self.assertEqual(uri.read_text(f2), "file1")
        
        # Test move file
        f3 = f"{self.sandbox_uri}/vfs_test_dir/f3.txt"
        uri.move(f2, f3)
        self.assertFalse(uri.exists(f2))
        self.assertTrue(uri.exists(f3))
        
        # Test rmtree
        uri.rmtree(f"{self.sandbox_uri}/vfs_test_dir")
        self.assertFalse(uri.exists(f"{self.sandbox_uri}/vfs_test_dir"))
        self.mark_passed()

    def test_test_sandbox_env_suppresses_jit_interaction(self):
        """FT-04: Verify YSCB_TEST_SANDBOX=1 environment suppresses JIT prompt and raises UndefinedURIError."""
        orig_env = os.environ.get("YSCB_TEST_SANDBOX")
        os.environ["YSCB_TEST_SANDBOX"] = "1"
        try:
            with self.assertRaises(UndefinedURIError) as ctx:
                # Even with interactive=True, YSCB_TEST_SANDBOX=1 must immediately suppress prompt
                uri.reconcile_undefined_uri("mock_undef", "!undefined", interactive=True)
            self.assertEqual(ctx.exception.scheme, "mock_undef")
        finally:
            if orig_env is not None:
                os.environ["YSCB_TEST_SANDBOX"] = orig_env
            else:
                os.environ.pop("YSCB_TEST_SANDBOX", None)
        self.mark_passed()
