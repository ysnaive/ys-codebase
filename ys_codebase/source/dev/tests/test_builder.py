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

    def _get_build_tag(self, module_name: str) -> str:
        """動態解算目標模組之 build tag (例如 1.0.1.build)。"""
        m_data = uri.read_json(f"module.source://{module_name}/manifest.json")
        ver = m_data.get("version", "1.0.0.0")
        triplet = ver.rsplit(".", 1)[0] if ver.count(".") == 3 else ver
        return f"{triplet}.build", ver

    def test_clean_build_core(self):
        """Verify dev build of 'core' outputs to <ver>.build.zip and retains tests/."""
        build_tag, _ = self._get_build_tag("core")
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed, f"Build core failed: {msg}")
        zip_uri = f"module.build://core/{build_tag}.zip"
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
        """Verify dev build of 'dev' outputs <ver>.build.zip and package_release excludes tests/."""
        build_tag, ver = self._get_build_tag("dev")
        passed, msg = self.builder.build_module("dev", clean=True)
        self.assertTrue(passed, f"Build dev failed: {msg}")
        self.assertTrue(uri.exists(f"module.build://dev/{build_tag}.zip"))
        
        # Release packager must exclude tests/
        ok_rel, msg_rel = self.builder.package_release("dev", ver)
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        rel_zip_uri = f"module.release://dev/{ver}.zip"
        self.assertTrue(uri.exists(rel_zip_uri))
        
        real_rel_zip = uri.resolve(rel_zip_uri)
        with zipfile.ZipFile(real_rel_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            # Must exclude tests/
            self.assertFalse(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_revision_purge_deletes_old_zip(self):
        """FT-03: Verify 3-Revision sliding window and cross-triplet convergence."""
        # Package 1.0.0.1, 1.0.0.2, 1.0.0.3
        self.builder.package_release("dev", "1.0.0.1")
        self.builder.package_release("dev", "1.0.0.2")
        self.builder.package_release("dev", "1.0.0.3")
        
        zip_1 = uri.resolve("module.release://dev/1.0.0.1.zip")
        zip_2 = uri.resolve("module.release://dev/1.0.0.2.zip")
        zip_3 = uri.resolve("module.release://dev/1.0.0.3.zip")
        self.assertTrue(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))
        
        # Package 1.0.0.4 -> 4th revision in same triplet -> 1.0.0.1 must be purged
        ok4, msg4 = self.builder.package_release("dev", "1.0.0.4")
        self.assertTrue(ok4, f"Package 1.0.0.4 failed: {msg4}")
        zip_4 = uri.resolve("module.release://dev/1.0.0.4.zip")
        self.assertTrue(os.path.isfile(zip_4))
        self.assertFalse(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))
        
        # Package 1.0.1.0 -> cross-triplet upgrade -> legacy 1.0.0 only retains 1.0.0.4
        self.builder.package_release("dev", "1.0.1.0")
        self.assertFalse(os.path.isfile(zip_2))
        self.assertFalse(os.path.isfile(zip_3))
        self.assertTrue(os.path.isfile(zip_4))
        self.assertTrue(os.path.isfile(uri.resolve("module.release://dev/1.0.1.0.zip")))
        
        idx = uri.read_json("module.release://dev/index.json")
        self.assertEqual(idx.get("versions", []), ["1.0.0.4", "1.0.1.0"])
        self.mark_passed()

    def test_builder_generates_and_updates_index_json(self):
        """Verify builder automatically creates and updates build/{module}/index.json (FT-04)."""
        build_tag, _ = self._get_build_tag("core")
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed)
        
        index_uri = "module.build://core/index.json"
        self.assertTrue(uri.exists(index_uri))
        index_data = uri.read_json(index_uri)
        self.assertEqual(index_data.get("name"), "core")
        self.assertIn(build_tag, index_data.get("versions", []))
        self.mark_passed()
