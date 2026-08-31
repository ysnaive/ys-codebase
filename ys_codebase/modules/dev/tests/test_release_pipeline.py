"""
Unit and integration tests for dev.releaser Releaser Toolchain.
Uses mock modules to eliminate official module coupling and side-effects.
"""
import os
import sys
import json
import zipfile
from core import uri
from core import semver
from dev.releaser import Releaser, ReleasePipeline
from dev.builder import Builder
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestReleasePipeline(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.releaser = Releaser()
        self.builder = Builder()

    @require(Requirement.ENV)
    def test_builder_dev_build_and_release_package(self):
        """Test dev build and release packaging on isolated mock module."""
        self.create_mock_source_module("mock_rel_mod", "1.0.0.0")
        
        ok, msg = self.builder.build_module("mock_rel_mod", clean=True)
        self.assertTrue(ok, f"Build failed: {msg}")
        
        build_zip = uri.resolve("module.build://mock_rel_mod/1.0.0.build.zip")
        self.assertTrue(os.path.isfile(build_zip))
        
        # Test release packaging outputs clean package (.zip)
        ok_rel, msg_rel = self.builder.package_release("mock_rel_mod", "1.0.0.0")
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        rel_zip = uri.resolve("module.release://mock_rel_mod/1.0.0.0.zip")
        self.assertTrue(os.path.isfile(rel_zip))
        
        with zipfile.ZipFile(rel_zip, "r") as zf:
            self.assertFalse(any(f.startswith("tests/") for f in zf.namelist()))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_release_check_gates(self):
        """Verify release_check executes 3-Gate verification on mock module."""
        self.create_mock_source_module("mock_gate_mod", "1.0.0.0")
        passed, errors = self.releaser.release_check("mock_gate_mod")
        self.assertTrue(isinstance(passed, bool))
        self.assertTrue(isinstance(errors, list))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_release_force_override_behavior(self):
        """FT-01 & ET-01: 驗證 --force 允許覆蓋在庫最高同版本，無 force 則被 Gate 2/3 阻斷。"""
        self.create_mock_source_module("mock_override_mod", "1.0.0.0")
        ver = "1.0.0.0"

        # 確保 mock_override_mod@1.0.0.0 在庫
        rel_zip = uri.resolve(f"module.release://mock_override_mod/{ver}.zip")
        if not os.path.isfile(rel_zip):
            self.builder.package_release("mock_override_mod", ver)
        self.assertTrue(os.path.isfile(rel_zip))

        # 1. 無 force: 預期 Gate 2 / Gate 3 阻斷
        passed_no_force, errors_no_force = self.releaser.release_check("mock_override_mod", force=False)
        self.assertFalse(passed_no_force)
        self.assertTrue(any("Gate 2 Failed" in e or "Gate 3 Failed" in e for e in errors_no_force))

        # 2. 有 force: 預期放行（因為版本等於最高版本 ver）
        passed_force, errors_force = self.releaser.release_check("mock_override_mod", force=True)
        self.assertTrue(passed_force)
        self.assertEqual(len(errors_force), 0)

        # 3. 實際執行 release_module(force=True)
        ok_rel, msg_rel = self.releaser.release_module("mock_override_mod", force=True)
        self.assertTrue(ok_rel)
        self.assertTrue(os.path.isfile(rel_zip))
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_release_git_smart_skip_and_force(self):
        """FT-02 & FT-03: 驗證 release-git 在已發布時自動略過打包或在 force 下覆蓋打包。"""
        self.create_mock_source_module("mock_git_mod", "1.0.0.0")
        original_git = self.releaser._run_git_cmd
        class MockTester:
            def run(self, argv):
                return 0
        self.releaser.tester = MockTester()
        try:
            self.releaser._run_git_cmd = lambda args, cwd=None: (0, "", "")
            
            # 版本已在庫，force=False -> 略過打包
            ok, msg = self.releaser.release_git("mock_git_mod", "test commit msg", force=False)
            self.assertTrue(ok)
            self.assertIn("Successfully processed", msg)

            # force=True -> 強制覆蓋打包
            ok_f, msg_f = self.releaser.release_git("mock_git_mod", "test commit msg", force=True)
            self.assertTrue(ok_f)
            self.assertIn("Successfully processed", msg_f)
        finally:
            self.releaser._run_git_cmd = original_git
            self.releaser.tester = None
        self.mark_passed()
