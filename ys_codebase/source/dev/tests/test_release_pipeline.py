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
        self.assertTrue(isinstance(passed, bool))
        self.assertTrue(isinstance(errors, list))

    def test_release_force_override_behavior(self):
        """FT-01 & ET-01: 驗證 --force 允許覆蓋在庫最高同版本，無 force 則被 Gate 2/3 阻斷。"""
        # 假設 core@1.0.0.0 已存在於 release
        rel_zip = uri.resolve("module.release://core/1.0.0.0.zip")
        self.assertTrue(os.path.isfile(rel_zip))

        # 1. 無 force: 預期 Gate 2 / Gate 3 阻斷
        passed_no_force, errors_no_force = self.releaser.release_check("core", force=False)
        self.assertFalse(passed_no_force)
        self.assertTrue(any("Gate 2 Failed" in e or "Gate 3 Failed" in e for e in errors_no_force))

        # 2. 有 force: 預期放行（因為版本等於最高版本 1.0.0.0）
        passed_force, errors_force = self.releaser.release_check("core", force=True)
        self.assertTrue(passed_force)
        self.assertEqual(len(errors_force), 0)

        # 3. 實際執行 release_module(force=True)
        ok_rel, msg_rel = self.releaser.release_module("core", force=True)
        self.assertTrue(ok_rel)
        self.assertTrue(os.path.isfile(rel_zip))

    def test_release_git_smart_skip_and_force(self):
        """FT-02 & FT-03: 驗證 release-git 在已發布時自動略過打包或在 force 下覆蓋打包。"""
        # 測試 release_git 智慧略過（已發布且無 force）
        # mock git command to avoid real git operations in unit test
        original_git = self.releaser._run_git_cmd
        try:
            self.releaser._run_git_cmd = lambda args, cwd=None: (0, "", "")
            
            # 版本已在庫，force=False -> 略過打包
            ok, msg = self.releaser.release_git("core", "test commit msg", force=False)
            self.assertTrue(ok)
            self.assertIn("Successfully processed", msg)

            # force=True -> 強制覆蓋打包
            ok_f, msg_f = self.releaser.release_git("core", "test commit msg", force=True)
            self.assertTrue(ok_f)
            self.assertIn("Successfully processed", msg_f)
        finally:
            self.releaser._run_git_cmd = original_git

if __name__ == "__main__":
    unittest.main()
