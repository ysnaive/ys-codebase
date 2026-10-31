"""
Unit and integration tests for dev.releaser Releaser Toolchain.
Uses mock modules to eliminate official module coupling and side-effects.
"""
import os
import sys
import json
import zipfile
from core import uri, vfs
from core import semver
from dev.releaser import Releaser, CyclicDependencyError
from dev.builder import Builder
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestReleasePipeline(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.releaser = Releaser()
        self.builder = Builder()

    def tearDown(self):
        for scheme in ("module.source://", "module.build://", "module.release://"):
            if vfs.exists(scheme):
                root = uri.resolve(scheme)
                if os.path.isdir(root):
                    for item in os.listdir(root):
                        if item.startswith("mock_"):
                            p = os.path.join(root, item)
                            if os.path.isdir(p):
                                import shutil
                                shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_release_check_gates(self):
        """FT-02: Real 3-Gate verification asserting concrete pass and fail conditions."""
        # 1. New module with compliant files passes all 3 gates
        self.create_mock_source_module("mock_gate_clean", "1.0.0.0")
        passed, errors = self.releaser.release_check("mock_gate_clean")
        self.assertTrue(passed, f"Expected clean module to pass all 3 gates: {errors}")
        self.assertEqual(len(errors), 0)

        # 2. Gate 1 failure: Bad manifest triggers Gate 1
        self.create_mock_source_module("mock_gate_bad", "1.0.0.0", files={"manifest.json": "{bad_json"})
        passed_g1, errors_g1 = self.releaser.release_check("mock_gate_bad")
        self.assertFalse(passed_g1)
        self.assertTrue(any("Gate 1 Failed" in e or "Invalid version" in e for e in errors_g1))

        # 3. Gate 2 & Gate 3: Release version already in repository
        self.create_mock_source_module("mock_gate_rel", "1.0.0.0")
        self.builder.package_release("mock_gate_rel", "1.0.0.0")
        passed_dup, errors_dup = self.releaser.release_check("mock_gate_rel", force=False)
        self.assertFalse(passed_dup)
        self.assertTrue(any("Gate 2 Failed" in e for e in errors_dup))
        self.assertTrue(any("Gate 3 Failed" in e for e in errors_dup))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_release_gate3_cross_triplet_rollback_blocking(self):
        """EC-02: Target version < global_highest is blocked even with force=True."""
        self.create_mock_source_module("mock_rollback_pkg", "1.0.0.5")
        rel_dir = uri.resolve("module.release://mock_rollback_pkg")
        os.makedirs(rel_dir, exist_ok=True)
        # Populate global_highest as 1.1.0.0
        with open(os.path.join(rel_dir, "1.1.0.0.zip"), "w") as f:
            f.write("mock")

        # Without force: blocked
        p1, err1 = self.releaser.release_check("mock_rollback_pkg", force=False)
        self.assertFalse(p1)
        self.assertTrue(any("Gate 3 Failed" in e for e in err1))

        # With force=True: still blocked because 1.0.0.5 < 1.1.0.0 (cross-triplet rollback)
        p2, err2 = self.releaser.release_check("mock_rollback_pkg", force=True)
        self.assertFalse(p2)
        self.assertTrue(any("Version rollback is forbidden even with --force" in e for e in err2))
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
    def test_release_all_kahn_dag_and_failure_propagation(self):
        """FT-02 & EC-04: release_all alphabetical Kahn DAG order and upstream failure skipping."""
        # Setup mod_b depending on mod_a, and mod_c independent
        self.create_mock_source_module("mock_dag_a", "1.0.0.0")
        self.create_mock_source_module("mock_dag_b", "1.0.0.0", deps={"mock_dag_a": ">=1.0.0.0"})
        self.create_mock_source_module("mock_dag_c", "1.0.0.0")

        # Case 1: All pass -> topological order should release a and c first, then b
        call_order = []
        orig_release_module = self.releaser.release_module
        def fake_release_module(name, force=False, _skip_check=False):
            call_order.append(name)
            return True, f"Released {name}"

        self.releaser.release_module = fake_release_module
        try:
            results = self.releaser.release_all(force=True)
            self.assertTrue(all(ok for ok, _ in results.values()))
            # a must precede b
            self.assertIn("mock_dag_a", call_order)
            self.assertIn("mock_dag_b", call_order)
            self.assertLess(call_order.index("mock_dag_a"), call_order.index("mock_dag_b"))
            # Initial alphabetical stability: between a and c (both degree 0), a is released before c
            self.assertLess(call_order.index("mock_dag_a"), call_order.index("mock_dag_c"))
        finally:
            self.releaser.release_module = orig_release_module

        # Case 2: Upstream failure -> mod_b is skipped because mod_a failed
        call_order2 = []
        def fake_release_module_fail(name, force=False, _skip_check=False):
            call_order2.append(name)
            if name == "mock_dag_a":
                return False, "Gate 1 Check Failed"
            return True, f"Released {name}"

        self.releaser.release_module = fake_release_module_fail
        try:
            results2 = self.releaser.release_all(force=True)
            self.assertFalse(results2["mock_dag_a"][0])
            self.assertFalse(results2["mock_dag_b"][0])
            self.assertIn("Skipped because dependency 'mock_dag_a' failed release", results2["mock_dag_b"][1])
            self.assertNotIn("mock_dag_b", call_order2)
        finally:
            self.releaser.release_module = orig_release_module

        # Case 3: Circular dependency throws CyclicDependencyError
        self.create_mock_source_module("mock_cycle_x", "1.0.0.0", deps={"mock_cycle_y": ">=1.0.0.0"})
        self.create_mock_source_module("mock_cycle_y", "1.0.0.0", deps={"mock_cycle_x": ">=1.0.0.0"})
        with self.assertRaises(CyclicDependencyError):
            self.releaser.release_all(force=True)
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

    @require(Requirement.WORKFLOW)
    def test_release_git_fatal_commit_error_handling(self):
        """EC-03: Fatal git commit error aborts tagging and returns failure."""
        self.create_mock_source_module("mock_git_err_mod", "1.0.0.0")
        original_git = self.releaser._run_git_cmd
        class MockTester:
            def run(self, argv):
                return 0
        self.releaser.tester = MockTester()
        tag_called = False
        def fake_git(args, cwd=None):
            nonlocal tag_called
            if args[0] == "rev-parse":
                return 0, "", ""
            if args[0] == "add":
                return 0, "", ""
            if args[0] == "commit":
                return 1, "", "fatal: unable to auto-detect email address"
            if args[0] == "tag":
                tag_called = True
                return 0, "", ""
            return 0, "", ""

        try:
            self.releaser._run_git_cmd = fake_git
            ok, msg = self.releaser.release_git("mock_git_err_mod", "commit msg", force=True)
            self.assertFalse(ok)
            self.assertIn("Git commit failed", msg)
            self.assertFalse(tag_called, "Git tag should NOT be called if commit suffered a fatal error!")
        finally:
            self.releaser._run_git_cmd = original_git
            self.releaser.tester = None
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_bump_and_release_check_commands(self):
        """DT-05: Verify scripts/cli.py bump_major/minor/patch/revision and default release_check."""
        import importlib.util
        from core.commands import CmdBags, CmdOption

        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_test", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        self.create_mock_source_module("mock_bump_mod", "1.0.0.0")

        # 1. bump_revision: 1.0.0.0 -> 1.0.0.1
        self.assertEqual(cli_mod.bump_revision(CmdBags(raw_cmd="dev bump-revision", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.0.0.1")

        # 2. bump_patch: 1.0.0.1 -> 1.0.1.0
        self.assertEqual(cli_mod.bump_patch(CmdBags(raw_cmd="dev bump-patch", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.0.1.0")

        # 3. bump_minor: 1.0.1.0 -> 1.1.0.0
        self.assertEqual(cli_mod.bump_minor(CmdBags(raw_cmd="dev bump-minor", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.1.0.0")

        # 4. bump_major: 1.1.0.0 -> 2.0.0.0
        self.assertEqual(cli_mod.bump_major(CmdBags(raw_cmd="dev bump-major", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "2.0.0.0")

        # 5. release_check single module and default all-modules (empty args)
        self.assertEqual(cli_mod.release_check(CmdBags(raw_cmd="dev release-check", args=["mock_bump_mod"])), 0)
        self.assertEqual(cli_mod.release_check(CmdBags(raw_cmd="dev release-check", args=[], options={"force": CmdOption("force", True)})), 0)
        self.mark_passed()
