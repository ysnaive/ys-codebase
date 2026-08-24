"""
Official test suite for core.uri VFS and semantic URI protocol resolution.
"""
import os
import json
from dev.testing import YSCBTestCase
from core import uri

class TestCoreURI(YSCBTestCase):
    def test_protocol_resolution_standards(self):
        """Verify standard protocol resolutions without throwing."""
        protocols = [
            "project://", "yscb://", "mirror://", "temp://", "snapshot://",
            "module.root://", "module://", "config.root://", "config://",
            "cache.root://", "cache://", "module.source.root://", "module.source://",
            "module.build.root://", "module.build://"
        ]
        for p in protocols:
            res = uri.resolve(p)
            self.assertTrue(isinstance(res, str) and len(res) > 0, f"Failed resolving {p}")
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
