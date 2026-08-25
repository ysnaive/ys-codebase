"""
Official test suite for dev.builder.Builder with Full Zip Single-File packaging.
"""
import os
import zipfile
from dev.testing import YSCBTestCase
from dev.builder import Builder
from core import uri

class TestDevBuilder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.builder = Builder()

    def test_clean_build_core(self):
        """Verify dev build of 'core' outputs to 1.0.0.build.zip and retains tests/."""
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed, f"Build core failed: {msg}")
        zip_uri = "module.build.root://core/1.0.0.build.zip"
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

    def test_clean_build_dev(self):
        """Verify dev build of 'dev' outputs 1.0.0.build.zip and package_release excludes tests/."""
        passed, msg = self.builder.build_module("dev", clean=True)
        self.assertTrue(passed, f"Build dev failed: {msg}")
        self.assertTrue(uri.exists("module.build.root://dev/1.0.0.build.zip"))
        
        # Release packager must exclude tests/
        ok_rel, msg_rel = self.builder.package_release("dev", "1.0.0.0")
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        rel_zip_uri = "release.root://dev/1.0.0.0.zip"
        self.assertTrue(uri.exists(rel_zip_uri))
        
        real_rel_zip = uri.resolve(rel_zip_uri)
        with zipfile.ZipFile(real_rel_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            # Must exclude tests/
            self.assertFalse(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_revision_purge_deletes_old_zip(self):
        """FT-03: Verify releasing same X.Y.Z new revision purges older .zip file."""
        # Package 1.0.0.1
        ok1, msg1 = self.builder.package_release("dev", "1.0.0.1")
        self.assertTrue(ok1, f"Package 1.0.0.1 failed: {msg1}")
        zip_1 = uri.resolve("release.root://dev/1.0.0.1.zip")
        self.assertTrue(os.path.isfile(zip_1))
        
        # Package 1.0.0.2 -> must purge 1.0.0.1.zip
        ok2, msg2 = self.builder.package_release("dev", "1.0.0.2")
        self.assertTrue(ok2, f"Package 1.0.0.2 failed: {msg2}")
        zip_2 = uri.resolve("release.root://dev/1.0.0.2.zip")
        self.assertTrue(os.path.isfile(zip_2))
        self.assertFalse(os.path.isfile(zip_1))
        
        idx = uri.read_json("release.root://dev/index.json")
        self.assertIn("1.0.0.2", idx.get("versions", []))
        self.assertNotIn("1.0.0.1", idx.get("versions", []))
        self.mark_passed()

    def test_builder_generates_and_updates_index_json(self):
        """Verify builder automatically creates and updates build/{module}/index.json (FT-04)."""
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed)
        
        index_uri = "module.build.root://core/index.json"
        self.assertTrue(uri.exists(index_uri))
        index_data = uri.read_json(index_uri)
        self.assertEqual(index_data.get("name"), "core")
        self.assertIn("1.0.0.build", index_data.get("versions", []))
        self.mark_passed()
