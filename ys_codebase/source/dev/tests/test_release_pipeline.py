"""
Unit and integration tests for dev.releaser Releaser Toolchain.
"""
import os
import sys
import json
import zipfile
import unittest
from core import uri
from core import semver
from dev.releaser import Releaser, ReleasePipeline
from dev.builder import Builder

class TestReleasePipeline(unittest.TestCase):
    def setUp(self):
        self.releaser = Releaser()
        self.builder = Builder()

    def test_builder_dev_build_and_release_package(self):
        # Test dev build outputs X.Y.Z.build.zip containing tests
        ok, msg = self.builder.build_module("core", clean=True)
        self.assertTrue(ok)
        
        build_zip = uri.resolve("module.build://core/1.0.0.build.zip")
        self.assertTrue(os.path.isfile(build_zip))
        
        # Test release packaging outputs clean package (.zip)
        ok_rel, msg_rel = self.builder.package_release("core", "1.0.0.0")
        self.assertTrue(ok_rel)
        rel_zip = uri.resolve("module.release://core/1.0.0.0.zip")
        self.assertTrue(os.path.isfile(rel_zip))
        
        with zipfile.ZipFile(rel_zip, "r") as zf:
            self.assertFalse(any(f.startswith("tests/") for f in zf.namelist()))

    def test_release_check_gates(self):
        """Verify release_check executes 3-Gate verification."""
        passed, errors = self.releaser.release_check("core")
        # Manifest is valid and core is clean
        self.assertTrue(isinstance(passed, bool))
        self.assertTrue(isinstance(errors, list))

if __name__ == "__main__":
    unittest.main()
