"""
Unit and integration tests for dev.releaser Release Pipeline.
"""
import os
import sys
import json
import unittest
from core import uri
from core import semver
from dev.releaser import ReleasePipeline
from dev.builder import Builder

class TestReleasePipeline(unittest.TestCase):
    def setUp(self):
        self.releaser = ReleasePipeline()
        self.builder = Builder()

    def test_smart_git_tag_matrix_rules(self):
        # Major and minor should tag by default
        self.assertTrue(self.releaser.should_create_git_tag("major"))
        self.assertTrue(self.releaser.should_create_git_tag("minor"))
        # Patch and revision should not tag by default
        self.assertFalse(self.releaser.should_create_git_tag("patch"))
        self.assertFalse(self.releaser.should_create_git_tag("revision"))
        # Overrides
        self.assertTrue(self.releaser.should_create_git_tag("patch", explicit_tag=True))
        self.assertFalse(self.releaser.should_create_git_tag("major", explicit_tag=False))

    def test_builder_dev_build_and_release_package(self):
        # Test dev build outputs X.Y.Z.build.zip containing tests
        ok, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(ok)
        
        build_zip = uri.resolve("module.build.root://core/1.0.0.build.zip")
        self.assertTrue(os.path.isfile(build_zip))
        
        # Test release packaging outputs clean package (.zip)
        ok_rel, msg_rel = self.builder.package_release("core", "1.0.0.0")
        self.assertTrue(ok_rel)
        rel_zip = uri.resolve("release.root://core/1.0.0.0.zip")
        self.assertTrue(os.path.isfile(rel_zip))
        # Ensure tests/ is excluded in release zip
        import zipfile
        with zipfile.ZipFile(rel_zip, "r") as zf:
            self.assertFalse(any(f.startswith("tests/") for f in zf.namelist()))

    def test_preflight_check_without_git_dirty_restriction(self):
        """FT-01: Verifies that preflight_check passes even if git status is dirty or in non-git env."""
        # preflight_check for 'core' with a new version like '9.9.9.0'
        passed, errors = self.releaser.preflight_check("core", "9.9.9.0", skip_test=True)
        self.assertTrue(passed, f"Preflight check unexpectedly failed with errors: {errors}")
        self.assertEqual(len(errors), 0)

if __name__ == "__main__":
    unittest.main()
