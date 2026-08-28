"""
Official test suite for dev.builder.Builder with Full Zip Single-File packaging.
Uses mock modules to eliminate side-effects and official module coupling.
"""
import os
import zipfile
from dev.testing import YSCBTestCase, require, Requirement
from dev.builder import Builder
from core import uri

@require(Requirement.ENV)
class TestDevBuilder(YSCBTestCase):

    def setUp(self):
        super().setUp()
        self.builder = Builder()

    def test_clean_build_mock_module(self):
        """Verify dev build of mock module outputs to <ver>.build.zip and retains tests/."""
        self.create_mock_source_module("mock_bld_pkg", "1.2.3.4")
        passed, msg = self.builder.build_module("mock_bld_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")
        zip_uri = "module.build://mock_bld_pkg/1.2.3.build.zip"
        self.assertTrue(uri.exists(zip_uri))
        
        # Verify zip contents
        real_zip = uri.resolve(zip_uri)
        with zipfile.ZipFile(real_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            self.assertIn("scripts/cli.py", namelist)
            # Dev build retains tests/
            self.assertTrue(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_package_release_excludes_tests(self):
        """Verify package_release of mock module outputs pure release zip excluding tests/."""
        self.create_mock_source_module("mock_rel_pkg", "2.0.0.1")
        passed, msg = self.builder.build_module("mock_rel_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")
        self.assertTrue(uri.exists("module.build://mock_rel_pkg/2.0.0.build.zip"))
        
        # Release packager must exclude tests/
        ok_rel, msg_rel = self.builder.package_release("mock_rel_pkg", "2.0.0.1")
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        rel_zip_uri = "module.release://mock_rel_pkg/2.0.0.1.zip"
        self.assertTrue(uri.exists(rel_zip_uri))
        
        real_rel_zip = uri.resolve(rel_zip_uri)
        with zipfile.ZipFile(real_rel_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            # Must exclude tests/
            self.assertFalse(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_revision_purge_deletes_old_zip(self):
        """FT-03: Verify 3-Revision sliding window and cross-triplet convergence on mock module."""
        self.create_mock_source_module("mock_purge_pkg", "1.0.0.1")
        # Package 1.0.0.1, 1.0.0.2, 1.0.0.3
        self.builder.package_release("mock_purge_pkg", "1.0.0.1")
        self.builder.package_release("mock_purge_pkg", "1.0.0.2")
        self.builder.package_release("mock_purge_pkg", "1.0.0.3")
        
        zip_1 = uri.resolve("module.release://mock_purge_pkg/1.0.0.1.zip")
        zip_2 = uri.resolve("module.release://mock_purge_pkg/1.0.0.2.zip")
        zip_3 = uri.resolve("module.release://mock_purge_pkg/1.0.0.3.zip")
        self.assertTrue(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))
        
        # Package 1.0.0.4 -> 4th revision in same triplet -> 1.0.0.1 must be purged
        ok4, msg4 = self.builder.package_release("mock_purge_pkg", "1.0.0.4")
        self.assertTrue(ok4, f"Package 1.0.0.4 failed: {msg4}")
        zip_4 = uri.resolve("module.release://mock_purge_pkg/1.0.0.4.zip")
        self.assertTrue(os.path.isfile(zip_4))
        self.assertFalse(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))
        
        # Package 1.0.1.0 -> cross-triplet upgrade -> legacy 1.0.0 only retains 1.0.0.4
        self.builder.package_release("mock_purge_pkg", "1.0.1.0")
        self.assertFalse(os.path.isfile(zip_2))
        self.assertFalse(os.path.isfile(zip_3))
        self.assertTrue(os.path.isfile(zip_4))
        self.assertTrue(os.path.isfile(uri.resolve("module.release://mock_purge_pkg/1.0.1.0.zip")))
        
        idx = uri.read_json("module.release://mock_purge_pkg/index.json")
        self.assertEqual(idx.get("versions", []), ["1.0.0.4", "1.0.1.0"])
        self.mark_passed()

    def test_builder_generates_and_updates_index_json(self):
        """Verify builder automatically creates and updates build/{module}/index.json (FT-04)."""
        self.create_mock_source_module("mock_idx_pkg", "3.1.2.0")
        passed, msg = self.builder.build_module("mock_idx_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")
        
        index_uri = "module.build://mock_idx_pkg/index.json"
        self.assertTrue(uri.exists(index_uri))
        index_data = uri.read_json(index_uri)
        self.assertEqual(index_data.get("name"), "mock_idx_pkg")
        self.assertIn("3.1.2.build", index_data.get("versions", []))
        self.mark_passed()
