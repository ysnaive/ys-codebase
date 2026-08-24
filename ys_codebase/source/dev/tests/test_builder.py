"""
Official test suite for dev.builder.Builder.
"""
from dev.testing import YSCBTestCase
from dev.builder import Builder
from core import uri

class TestDevBuilder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.builder = Builder()

    def test_clean_build_core(self):
        """Verify clean build of 'core' outputs to versioned build directory."""
        passed, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(passed, f"Build core failed: {msg}")
        self.assertTrue(uri.exists("module.build.root://core/1.0.0/manifest.json"))
        self.assertTrue(uri.exists("module.build.root://core/1.0.0/scripts/cli.py"))
        # Verify tests/ is excluded
        self.assertFalse(uri.exists("module.build.root://core/1.0.0/tests"))
        self.assertFalse(uri.exists("module.build.root://core/1.0.0/.yscbignore"))
        self.mark_passed()

    def test_clean_build_dev(self):
        """Verify clean build of 'dev' excludes tests/ and .yscbignore."""
        passed, msg = self.builder.build_module("dev", clean=True)
        self.assertTrue(passed, f"Build dev failed: {msg}")
        self.assertTrue(uri.exists("module.build.root://dev/1.0.0/manifest.json"))
        self.assertFalse(uri.exists("module.build.root://dev/1.0.0/tests"))
        self.assertFalse(uri.exists("module.build.root://dev/1.0.0/.yscbignore"))
        self.mark_passed()
