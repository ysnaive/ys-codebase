"""
Official test suite for core.uri VFS and semantic URI protocol resolution.
"""
import os
import json
from dev.testing import YSCBTestCase
from core import uri
from core.uri import ExecutionContext

class TestCoreURI(YSCBTestCase):
    def test_protocol_resolution_standards(self):
        """Verify standard protocol resolutions and explicit config/ path."""
        # Ensure core config has project_root for project:// resolution
        core_cfg = "config.root://core/config.project.json"
        if not uri.exists(core_cfg):
            uri.write_json(core_cfg, {"project_root": "./"}, indent=2)
            
        protocols = [
            "project://", "yscb://", "mirror://", "temp://", "snapshot://",
            "module.root://", "module://", "config.root://", "config://",
            "cache.root://", "cache://", "module.source.root://", "module.source://",
            "module.build.root://", "module.build://"
        ]
        for p in protocols:
            res = uri.resolve(p)
            self.assertTrue(isinstance(res, str) and len(res) > 0, f"Failed resolving {p}")
            
        # Verify explicit config/ directory (not .config)
        cfg_root = uri.resolve("config.root://")
        self.assertTrue(cfg_root.endswith("config") and not cfg_root.endswith(".config"), f"config.root:// must be explicit config/, got {cfg_root}")
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
        """Verify _get_host_config (and legacy _find_host_config alias) raises FileNotFoundError on missing yscb.config.json (Zero Speculation)."""
        empty_dir = os.path.join(self.sandbox_dir, "empty_dir_for_test")
        os.makedirs(empty_dir, exist_ok=True)
        
        # When looking strictly at a directory with no yscb.config.json anywhere
        with self.assertRaises(FileNotFoundError) as ctx:
            uri._get_host_config(start_dir=empty_dir)
        self.assertIn("yscb.config.json", str(ctx.exception))

        # Test backward-compatibility alias
        with self.assertRaises(FileNotFoundError):
            uri._find_host_config(start_dir=empty_dir)
        self.mark_passed()

    def test_project_root_undefined_raises_value_error(self):
        """Verify project:// without project_root raises ValueError (Zero Fallback)."""
        core_cfg = "config.root://core/config.project.json"
        saved = None
        if uri.exists(core_cfg):
            saved = uri.read_json(core_cfg)
            uri.remove(core_cfg)
            
        try:
            with self.assertRaises(ValueError) as ctx:
                uri.resolve("project://some/file.txt")
            self.assertIn("'project://' is undefined", str(ctx.exception))
        finally:
            if saved is not None:
                uri.write_json(core_cfg, saved, indent=2)
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
        
        f1 = f"{d_uri}/sample.txt"
        uri.write_text(f1, "Sample Data")
        self.assertTrue(uri.is_file(f1))
        
        entries = uri.listdir(f"{self.sandbox_uri}/vfs_test_dir")
        self.assertIn("subdir", entries)
        
        dst_copy = f"{self.sandbox_uri}/vfs_test_copy"
        uri.copy(f"{self.sandbox_uri}/vfs_test_dir", dst_copy)
        self.assertTrue(uri.exists(f"{dst_copy}/subdir/sample.txt"))
        
        uri.rmtree(f"{self.sandbox_uri}/vfs_test_dir")
        uri.rmtree(dst_copy)
        self.assertFalse(uri.exists(f"{self.sandbox_uri}/vfs_test_dir"))
        self.assertFalse(uri.exists(dst_copy))
        self.mark_passed()

    def test_unsupported_scheme_raises_value_error(self):
        """Verify unsupported schemes throw ValueError."""
        with self.assertRaises(ValueError):
            uri.resolve("invalid_proto://path/to/file")
        self.mark_passed()
