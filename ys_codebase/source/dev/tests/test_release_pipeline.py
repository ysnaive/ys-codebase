"""
Unit and integration tests for dev.releaser Releaser Toolchain.
Uses mock modules to eliminate official module coupling and side-effects.
"""
import importlib.util
import io
import os
import shutil
from unittest.mock import patch
from core import uri, vfs
from core.commands import CmdBags, CmdOption
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
                                shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_release_check_gates(self):
        """Verify 3-Gate release_check across compliant module, Gate 1 failure, and Gate 2/3 version conflict."""
        # 1. New module with compliant files passes all 3 gates
        self.create_mock_source_module("mock_gate_clean", "1.0.0.0")
        passed, errors = self.releaser.release_check("mock_gate_clean")
        self.assertTrue(passed, f"Expected clean module to pass all 3 gates: {errors}")
        self.assertEqual(len(errors), 0)

        # 2a. Gate 1 failure: Missing 'core' dependency in manifest.json blocks release_check
        self.create_mock_source_module(
            "mock_gate_no_core",
            "1.0.0.0",
            files={
                "manifest.json": '{"name": "mock_gate_no_core", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": []}'
            },
        )
        passed_nc, errors_nc = self.releaser.release_check("mock_gate_no_core")
        self.assertFalse(passed_nc)
        self.assertTrue(any("Gate 1 Failed" in e and "must explicitly declare 'core'" in e for e in errors_nc))

        # 2b. Gate 1 failure: Malformed manifest.json triggers Gate 1
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
        """Verify target version < global_highest is blocked even with force=True."""
        self.create_mock_source_module("mock_rollback_pkg", "1.0.0.5")
        rel_dir = uri.resolve("module.release://mock_rollback_pkg")
        os.makedirs(rel_dir, exist_ok=True)
        with open(os.path.join(rel_dir, "1.1.0.0.zip"), "w", encoding="utf-8") as f:
            f.write("mock")

        p1, err1 = self.releaser.release_check("mock_rollback_pkg", force=False)
        self.assertFalse(p1)
        self.assertTrue(any("Gate 3 Failed" in e for e in err1))

        p2, err2 = self.releaser.release_check("mock_rollback_pkg", force=True)
        self.assertFalse(p2)
        self.assertTrue(any("Version rollback is forbidden even with --force" in e for e in err2))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_release_force_override_behavior(self):
        """Verify --force allows overwriting the highest existing version while force=False is blocked by Gate 2/3."""
        self.create_mock_source_module("mock_override_mod", "1.0.0.0")
        ver = "1.0.0.0"

        rel_zip = uri.resolve(f"module.release://mock_override_mod/{ver}.zip")
        if not os.path.isfile(rel_zip):
            self.builder.package_release("mock_override_mod", ver)
        self.assertTrue(os.path.isfile(rel_zip))

        passed_no_force, errors_no_force = self.releaser.release_check("mock_override_mod", force=False)
        self.assertFalse(passed_no_force)
        self.assertTrue(any("Gate 2 Failed" in e or "Gate 3 Failed" in e for e in errors_no_force))

        passed_force, errors_force = self.releaser.release_check("mock_override_mod", force=True)
        self.assertTrue(passed_force)
        self.assertEqual(len(errors_force), 0)

        ok_rel, _ = self.releaser.release_module("mock_override_mod", force=True)
        self.assertTrue(ok_rel)
        self.assertTrue(os.path.isfile(rel_zip))
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_release_all_kahn_dag_and_failure_propagation(self):
        """Verify release_all alphabetical Kahn DAG order and upstream failure skipping."""
        self.create_mock_source_module("mock_dag_a", "1.0.0.0")
        self.create_mock_source_module("mock_dag_b", "1.0.0.0", deps={"mock_dag_a": ">=1.0.0.0"})
        self.create_mock_source_module("mock_dag_c", "1.0.0.0")

        call_order = []
        orig_release_module = self.releaser.release_module

        def fake_release_module(name, force=False, _skip_check=False):
            call_order.append(name)
            return True, f"Released {name}"

        self.releaser.release_module = fake_release_module
        try:
            results = self.releaser.release_all(force=True)
            self.assertTrue(all(ok for ok, _ in results.values()))
            self.assertIn("mock_dag_a", call_order)
            self.assertIn("mock_dag_b", call_order)
            self.assertLess(call_order.index("mock_dag_a"), call_order.index("mock_dag_b"))
            self.assertLess(call_order.index("mock_dag_a"), call_order.index("mock_dag_c"))
        finally:
            self.releaser.release_module = orig_release_module

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

        self.create_mock_source_module("mock_cycle_x", "1.0.0.0", deps={"mock_cycle_y": ">=1.0.0.0"})
        self.create_mock_source_module("mock_cycle_y", "1.0.0.0", deps={"mock_cycle_x": ">=1.0.0.0"})
        with self.assertRaises(CyclicDependencyError):
            self.releaser.release_all(force=True)
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_release_git_smart_skip_and_force(self):
        """Verify 3-step release-git state machine: initial package -> smart skip when already released -> force repackage."""
        self.create_mock_source_module("mock_git_mod", "1.0.0.0")
        original_git = self.releaser._run_git_cmd
        orig_release_module = self.releaser.release_module

        class MockTester:
            def run(self, argv):
                return 0

        self.releaser.tester = MockTester()
        release_calls = []
        git_tag_calls = []

        def spy_release_module(module_name, force=False, _skip_check=False, release_meta=None):
            release_calls.append((module_name, force, _skip_check))
            return orig_release_module(module_name, force=force, _skip_check=_skip_check, release_meta=release_meta)

        def spy_git_cmd(args, cwd=None, timeout=30.0):
            if args and args[0] == "tag":
                git_tag_calls.append(list(args))
            return 0, "", ""

        try:
            self.releaser.release_module = spy_release_module
            self.releaser._run_git_cmd = spy_git_cmd

            # Call 1: Not yet released, force=False -> calls release_module and tags without -f
            self.assertFalse(vfs.exists("module.release://mock_git_mod/1.0.0.0.zip"))
            ok1, msg1 = self.releaser.release_git("mock_git_mod", "initial release", force=False)
            self.assertTrue(ok1, f"Call 1 failed: {msg1}")
            self.assertIn("Successfully processed", msg1)
            self.assertEqual(len(release_calls), 1)
            self.assertEqual(release_calls[0], ("mock_git_mod", False, True))
            self.assertTrue(vfs.exists("module.release://mock_git_mod/1.0.0.0.zip"))
            self.assertEqual(git_tag_calls[-1], ["tag", "-a", "mock_git_mod/v1.0.0.0", "-m", "initial release"])

            # Call 2: Already released, force=False -> skips release_module, prints skip message, tags without -f
            buf_skip = io.StringIO()
            with patch("sys.stdout", buf_skip):
                ok2, msg2 = self.releaser.release_git("mock_git_mod", "smart skip commit", force=False)
            self.assertTrue(ok2, f"Call 2 failed: {msg2}")
            self.assertEqual(len(release_calls), 1, "release_module must be skipped when already released and force=False")
            self.assertIn("Skipping packaging step", buf_skip.getvalue())
            self.assertEqual(git_tag_calls[-1], ["tag", "-a", "mock_git_mod/v1.0.0.0", "-m", "smart skip commit"])

            # Call 3: Already released, force=True -> re-invokes release_module(force=True) and tags with -f
            ok3, msg3 = self.releaser.release_git("mock_git_mod", "force overwrite commit", force=True)
            self.assertTrue(ok3, f"Call 3 failed: {msg3}")
            self.assertEqual(len(release_calls), 2)
            self.assertEqual(release_calls[1], ("mock_git_mod", True, True))
            self.assertEqual(git_tag_calls[-1], ["tag", "-f", "-a", "mock_git_mod/v1.0.0.0", "-m", "force overwrite commit"])
        finally:
            self.releaser.release_module = orig_release_module
            self.releaser._run_git_cmd = original_git
            self.releaser.tester = None
        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_release_git_fatal_commit_error_handling(self):
        """Verify fatal git commit error aborts tagging and returns failure."""
        self.create_mock_source_module("mock_git_err_mod", "1.0.0.0")
        original_git = self.releaser._run_git_cmd

        class MockTester:
            def run(self, argv):
                return 0

        self.releaser.tester = MockTester()
        tag_called = False

        def fake_git(args, cwd=None, timeout=30.0):
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

    @require(Requirement.WORKFLOW)
    def test_release_git_step_failures_and_non_git_branches(self):
        """Verify release_git guardrails across empty msg, missing manifest, Step 1/2 failures, non-git repo, and clean tree."""
        ok_empty, msg_empty = self.releaser.release_git("mock_git_ step_mod", "   ")
        self.assertFalse(ok_empty)
        self.assertIn("Commit message cannot be empty", msg_empty)

        ok_no_mf, msg_no_mf = self.releaser.release_git("mock_nonexistent_git_mod", "valid msg")
        self.assertFalse(ok_no_mf)
        self.assertIn("manifest.json not found", msg_no_mf)

        self.create_mock_source_module("mock_git_step_mod", "1.0.0.0")
        original_git = self.releaser._run_git_cmd
        try:
            # Step 1: E2E test failure
            class FailingTester:
                def run(self, argv):
                    return 1

            self.releaser.tester = FailingTester()
            ok_s1, msg_s1 = self.releaser.release_git("mock_git_step_mod", "msg")
            self.assertFalse(ok_s1)
            self.assertIn("Step 1 Failed", msg_s1)

            # Step 2: Release check failure (missing core dependency)
            class PassingTester:
                def run(self, argv):
                    return 0

            self.releaser.tester = PassingTester()
            self.create_mock_source_module(
                "mock_git_step2_bad",
                "1.0.0.0",
                files={
                    "manifest.json": '{"name": "mock_git_step2_bad", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": []}'
                },
            )
            ok_s2, msg_s2 = self.releaser.release_git("mock_git_step2_bad", "msg")
            self.assertFalse(ok_s2)
            self.assertIn("Step 2 Failed", msg_s2)

            # Step 4a: Not a Git repository -> returns True with warning
            self.releaser._run_git_cmd = lambda args, cwd=None, timeout=30.0: (128, "", "not a git repo") if args[0] == "rev-parse" else (0, "", "")
            ok_nogit, msg_nogit = self.releaser.release_git("mock_git_step_mod", "msg", force=True)
            self.assertTrue(ok_nogit)
            self.assertIn("Not a Git repository, skipped commit & tag", msg_nogit)

            # Step 4b: Git commit returns 1 with 'nothing to commit, working tree clean' -> proceeds to tag and succeeds
            def clean_tree_git(args, cwd=None, timeout=30.0):
                if args[0] == "commit":
                    return 1, "nothing to commit, working tree clean", ""
                return 0, "", ""

            self.releaser._run_git_cmd = clean_tree_git
            ok_clean, msg_clean = self.releaser.release_git("mock_git_step_mod", "msg", force=True)
            self.assertTrue(ok_clean)
            self.assertIn("Successfully processed", msg_clean)

            # Step 4c: Git add failure & Git tag failure
            self.releaser._run_git_cmd = lambda args, cwd=None, timeout=30.0: (1, "", "index lock error") if args[0] == "add" else (0, "", "")
            ok_add, msg_add = self.releaser.release_git("mock_git_step_mod", "msg", force=True)
            self.assertFalse(ok_add)
            self.assertIn("Git add failed", msg_add)

            self.releaser._run_git_cmd = lambda args, cwd=None, timeout=30.0: (1, "", "tag already exists") if args[0] == "tag" else (0, "", "")
            ok_tag, msg_tag = self.releaser.release_git("mock_git_step_mod", "msg", force=False)
            self.assertFalse(ok_tag)
            self.assertIn("Git tag failed", msg_tag)
        finally:
            self.releaser._run_git_cmd = original_git
            self.releaser.tester = None
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_bump_and_release_check_commands(self):
        """Verify scripts/cli.py bump commands sync __version__ in __init__.py and release/release_git/index_patch CLI paths."""
        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_test", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        self.create_mock_source_module(
            "mock_bump_mod",
            "1.0.0.0",
            files={
                "mock_bump_mod/__init__.py": '"""Pkg."""\n__version__ = "1.0.0.0"\n',
                "sub_pkg/__init__.py": "'''Subpkg.'''\n__version__: str = '1.0.0.0'\n",
            },
        )

        # Missing args / nonexistent module guards for _handle_bump
        self.assertEqual(cli_mod.bump_revision(CmdBags(raw_cmd="dev bump-revision", args=[])), 1)
        self.assertEqual(cli_mod.bump_revision(CmdBags(raw_cmd="dev bump-revision", args=["mock_no_such_mod"])), 1)

        # 1. bump_revision: 1.0.0.0 -> 1.0.0.1
        self.assertEqual(cli_mod.bump_revision(CmdBags(raw_cmd="dev bump-revision", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.0.0.1")
        self.assertIn('__version__ = "1.0.0.1"', vfs.read_text("module.source://mock_bump_mod/mock_bump_mod/__init__.py"))
        self.assertIn("__version__: str = '1.0.0.1'", vfs.read_text("module.source://mock_bump_mod/sub_pkg/__init__.py"))

        # 2. bump_patch: 1.0.0.1 -> 1.0.1.0
        self.assertEqual(cli_mod.bump_patch(CmdBags(raw_cmd="dev bump-patch", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.0.1.0")
        self.assertIn('__version__ = "1.0.1.0"', vfs.read_text("module.source://mock_bump_mod/mock_bump_mod/__init__.py"))

        # 3. bump_minor: 1.0.1.0 -> 1.1.0.0
        self.assertEqual(cli_mod.bump_minor(CmdBags(raw_cmd="dev bump-minor", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "1.1.0.0")
        self.assertIn('__version__ = "1.1.0.0"', vfs.read_text("module.source://mock_bump_mod/mock_bump_mod/__init__.py"))

        # 4. bump_major: 1.1.0.0 -> 2.0.0.0
        self.assertEqual(cli_mod.bump_major(CmdBags(raw_cmd="dev bump-major", args=["mock_bump_mod"])), 0)
        self.assertEqual(vfs.read_json("module.source://mock_bump_mod/manifest.json")["version"], "2.0.0.0")
        self.assertIn('__version__ = "2.0.0.0"', vfs.read_text("module.source://mock_bump_mod/mock_bump_mod/__init__.py"))
        self.assertIn("__version__: str = '2.0.0.0'", vfs.read_text("module.source://mock_bump_mod/sub_pkg/__init__.py"))

        # 5. release_check single module and default all-modules
        self.assertEqual(cli_mod.release_check(CmdBags(raw_cmd="dev release-check", args=["mock_bump_mod"])), 0)
        self.assertEqual(
            cli_mod.release_check(CmdBags(raw_cmd="dev release-check", args=[], options={"force": CmdOption("force", True)})),
            0,
        )

        # 6. cli.release positive and negative branches
        self.assertEqual(cli_mod.release(["mock_bump_mod"]), 0)
        self.assertEqual(cli_mod.release(["mock_bump_mod"]), 1)
        self.assertEqual(cli_mod.release(["mock_bump_mod", "--force"]), 0)

        # 7. cli.release_git argument validation and dispatch
        self.assertEqual(cli_mod.release_git([]), 1)
        self.assertEqual(cli_mod.release_git(["mock_bump_mod"]), 1)
        with patch.object(Releaser, "release_git", return_value=(True, "mock release-git ok")) as mock_rg:
            self.assertEqual(cli_mod.release_git(["mock_bump_mod", "-m", "release commit", "--force"]), 0)
            mock_rg.assert_called_once()
        with patch.object(Releaser, "release_git", return_value=(False, "mock release-git failed")):
            self.assertEqual(cli_mod.release_git(["mock_bump_mod", "positional commit msg"]), 1)

        # 8. cli.index_patch argument validation
        self.assertEqual(cli_mod.index_patch([]), 1)
        self.assertEqual(cli_mod.index_patch(["mock_bump_mod"]), 1)
        self.assertEqual(cli_mod.index_patch(["mock_bump_mod", "--ver=2.0.0.0", "--dep=:missing_mod"]), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_release_check_with_index_json_ssot_without_local_zip(self):
        """Verify Gate 2 and Gate 3 enforce version immutability and monotonicity from index.json ledger without local .zip files."""
        self.create_mock_source_module("mock_ssot_mod", "1.0.0.1")
        rel_dir = uri.resolve("module.release://mock_ssot_mod")
        os.makedirs(rel_dir, exist_ok=True)
        vfs.write_json(
            "module.release://mock_ssot_mod/index.json",
            {
                "name": "mock_ssot_mod",
                "versions": ["1.0.0.2"],
                "releases": {
                    "1.0.0.1": {"status": "pruned", "dependencies": {}},
                    "1.0.0.2": {"status": "active", "dependencies": {}},
                },
            },
            indent=2,
        )

        passed_old, errors_old = self.releaser.release_check("mock_ssot_mod", force=False)
        self.assertFalse(passed_old)
        self.assertTrue(any("Gate 2 Failed" in e for e in errors_old))
        self.assertTrue(any("Gate 3 Failed" in e for e in errors_old))

        self.create_mock_source_module("mock_ssot_mod", "1.0.0.3")
        with patch("core.events.broadcast") as mock_broadcast:
            ok_rel, _ = self.releaser.release_module("mock_ssot_mod", force=False)
            self.assertTrue(ok_rel)
            called_events = [c.args[0] for c in mock_broadcast.call_args_list if c.args]
            self.assertIn("on_module_released", called_events)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dual_track_release_meta_index_patch_and_manifest_validation(self):
        """Verify dual-track release_meta writing, dev index-patch dependency patching, and Checker release metadata validation."""
        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_patch_test", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        self.create_mock_source_module("mock_meta_mod", "1.0.0.0")
        rc_rel = cli_mod.release(
            ["mock_meta_mod", "--type=bugfix", "--urgency=critical", "--summary=Fix critical init race"]
        )
        self.assertEqual(rc_rel, 0)
        src_mf = vfs.read_json("module.source://mock_meta_mod/manifest.json")
        self.assertEqual(
            src_mf.get("release"),
            {"type": "bugfix", "urgency": "critical", "summary": "Fix critical init race"},
        )
        idx_1 = vfs.read_json("module.release://mock_meta_mod/index.json")
        self.assertEqual(idx_1["releases"]["1.0.0.0"]["type"], "bugfix")
        self.assertEqual(idx_1["releases"]["1.0.0.0"]["urgency"], "critical")
        self.assertEqual(idx_1["releases"]["1.0.0.0"]["summary"], "Fix critical init race")

        rc_patch = cli_mod.index_patch(
            [
                "mock_meta_mod",
                "--ver=1.0.0.0",
                "--dep=core:>=1.1.0,<1.4.0",
                "--dep=server:>=1.0.0",
            ]
        )
        self.assertEqual(rc_patch, 0)
        idx_2 = vfs.read_json("module.release://mock_meta_mod/index.json")
        self.assertEqual(
            idx_2["releases"]["1.0.0.0"]["dependencies"],
            {"core": ">=1.1.0,<1.4.0", "server": ">=1.0.0"},
        )

        self.create_mock_source_module("mock_meta_mod", "1.0.0.1")
        ok_next, _ = self.releaser.release_module("mock_meta_mod", force=False)
        self.assertTrue(ok_next)
        idx_3 = vfs.read_json("module.release://mock_meta_mod/index.json")
        self.assertEqual(
            idx_3["releases"]["1.0.0.0"]["dependencies"],
            {"core": ">=1.1.0,<1.4.0", "server": ">=1.0.0"},
        )

        self.assertEqual(cli_mod.index_patch(["mock_meta_mod", "--ver=1.0.0.0", "--dep=invalid_no_colon"]), 1)
        bad_mf = vfs.read_json("module.source://mock_meta_mod/manifest.json")
        bad_mf["release"] = {"type": ""}
        vfs.write_json("module.source://mock_meta_mod/manifest.json", bad_mf, indent=2)
        chk_rep = self.releaser.checker.check_module("mock_meta_mod")
        self.assertFalse(chk_rep.passed)
        self.assertTrue(any("release.type" in e for e in chk_rep.errors))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_patch_release_index_status_sync_and_guards(self):
        """Verify patch_release_index input guards and top-level versions synchronization when toggling status."""
        ok_m, msg_m = self.releaser.patch_release_index("", "1.0.0.0")
        self.assertFalse(ok_m)
        self.assertIn("Module name cannot be empty", msg_m)

        ok_v, msg_v = self.releaser.patch_release_index("mock_patch_sync", "")
        self.assertFalse(ok_v)
        self.assertIn("Target version (--ver) is required", msg_v)

        ok_sv, msg_sv = self.releaser.patch_release_index("mock_patch_sync", "not_a_semver")
        self.assertFalse(ok_sv)
        self.assertIn("Invalid SemVer version", msg_sv)

        ok_st, msg_st = self.releaser.patch_release_index("mock_patch_sync", "1.0.0.0", status="invalid_status")
        self.assertFalse(ok_st)
        self.assertIn("Invalid status", msg_st)

        ok_nf, msg_nf = self.releaser.patch_release_index("mock_patch_sync", "1.0.0.0")
        self.assertFalse(ok_nf)
        self.assertIn("Release index not found", msg_nf)

        self.create_mock_source_module("mock_patch_sync", "1.0.0.0")
        self.builder.package_release("mock_patch_sync", "1.0.0.0")

        ok_prune, _ = self.releaser.patch_release_index("mock_patch_sync", "1.0.0.0", status="pruned")
        self.assertTrue(ok_prune)
        idx_pruned = vfs.read_json("module.release://mock_patch_sync/index.json")
        self.assertNotIn("1.0.0.0", idx_pruned["versions"])
        self.assertEqual(idx_pruned["releases"]["1.0.0.0"]["status"], "pruned")

        ok_act, _ = self.releaser.patch_release_index(
            "mock_patch_sync",
            "1.0.0.0",
            status="active",
            release_type="feature",
            urgency="high",
            summary="Restored active version",
        )
        self.assertTrue(ok_act)
        idx_active = vfs.read_json("module.release://mock_patch_sync/index.json")
        self.assertIn("1.0.0.0", idx_active["versions"])
        self.assertEqual(idx_active["releases"]["1.0.0.0"]["status"], "active")
        self.assertEqual(idx_active["releases"]["1.0.0.0"]["type"], "feature")
        self.assertEqual(idx_active["releases"]["1.0.0.0"]["urgency"], "high")
        self.assertEqual(idx_active["releases"]["1.0.0.0"]["summary"], "Restored active version")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_release_module_preflight_failure_rolls_back_manifest(self):
        """Verify release_module validates pre-flight checks before mutating manifest.json and restores manifest.json if packaging fails."""
        mod_name = "mock_atomic_rel"
        self.create_mock_source_module(mod_name, "1.0.0.0")
        mf_uri = f"module.source://{mod_name}/manifest.json"
        orig_raw = vfs.read_text(mf_uri)

        with patch.object(self.releaser, "release_check", return_value=(False, ["Simulated pre-flight check failure"])):
            ok, msg = self.releaser.release_module(
                mod_name,
                release_meta={
                    "type": "bugfix",
                    "urgency": "high",
                    "summary": "Should not persist on failure",
                },
            )
        self.assertFalse(ok)
        self.assertIn("Release pre-flight check failed", msg)
        self.assertEqual(vfs.read_text(mf_uri), orig_raw)
        self.mark_passed()
