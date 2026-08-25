"""
Official test suite for dev.builder.Builder.
"""
import os
from dev.testing import YSCBTestCase
from dev.builder import Builder
from core import uri

class TestDevBuilder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.builder = Builder()

    def test_clean_build_core(self):
        """Verify dev build of 'core' outputs to 1.0.0.build directory and retains tests/."""
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed, f"Build core failed: {msg}")
        self.assertTrue(uri.exists("module.build.root://core/1.0.0.build/manifest.json"))
        self.assertTrue(uri.exists("module.build.root://core/1.0.0.build/scripts/cli.py"))
        # Dev build retains tests/ for blackbox testing
        self.assertTrue(uri.exists("module.build.root://core/1.0.0.build/tests"))
        self.mark_passed()

    def test_clean_build_dev(self):
        """Verify dev build of 'dev' outputs 1.0.0.build and package_release excludes tests/."""
        passed, msg = self.builder.build_module("dev", clean=True)
        self.assertTrue(passed, f"Build dev failed: {msg}")
        self.assertTrue(uri.exists("module.build.root://dev/1.0.0.build/manifest.json"))
        
        # Release packager must exclude tests/
        ok_rel, msg_rel = self.builder.package_release("dev", "1.0.0.0")
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        self.assertTrue(uri.exists("release.root://dev/1.0.0.0/manifest.json"))
        self.assertFalse(uri.exists("release.root://dev/1.0.0.0/tests"))
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
