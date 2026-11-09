"""
Unit tests for YSCBTestCase sandbox sharing, isolation branching, and YSCB_TEST_SANDBOX propagation.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch
from dev.testing.case import YSCBTestCase, SecurityError
from dev.testing.requirement import require, Requirement, is_network_available
from dev.testing.runner import get_test_category
from dev.testing.sandbox import SandboxProvisioner
from dev.checker import Checker


class TestCaseSandboxLifecycleTest(YSCBTestCase):
    """Test suite validating YSCBTestCase sandbox lifecycle rules."""

    @require(Requirement.LOGIC)
    def test_requirement_isolated_sandbox_flag(self):
        """Verify Requirement.ISOLATED_SANDBOX is defined and combinable."""
        flag = Requirement.ISOLATED_SANDBOX
        self.assertTrue(bool(flag & Requirement.ISOLATED_SANDBOX))
        comb = Requirement.ENV | Requirement.ISOLATED_SANDBOX
        self.assertTrue(bool(comb & Requirement.ENV))
        self.assertTrue(bool(comb & Requirement.ISOLATED_SANDBOX))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_shared_and_isolated_sandbox_dispatch(self):
        """Verify shared vs isolated sandbox behavior and automatic isolated sandbox cleanup in local TestCases."""
        shared_dirs = []
        isolated_dirs = []

        class LocalSharedTestCase(YSCBTestCase):
            def test_method_one(self):
                shared_dirs.append(self.sandbox_dir)
                self.assertTrue(os.path.isdir(self.sandbox_dir))
                self.assertFalse(self._is_isolated_sandbox)
                self.mark_passed()

            def test_method_two(self):
                shared_dirs.append(self.sandbox_dir)
                self.assertTrue(os.path.isdir(self.sandbox_dir))
                self.assertFalse(self._is_isolated_sandbox)
                self.mark_passed()

            @require(Requirement.ISOLATED_SANDBOX)
            def test_method_isolated(self):
                isolated_dirs.append(self.sandbox_dir)
                self.assertTrue(os.path.isdir(self.sandbox_dir))
                self.assertTrue(self._is_isolated_sandbox)
                self.mark_passed()

        class LocalSharedTestCaseB(YSCBTestCase):
            def test_method_b1(self):
                shared_dirs.append(self.sandbox_dir)
                self.assertTrue(os.path.isdir(self.sandbox_dir))
                self.assertFalse(self._is_isolated_sandbox)
                self.mark_passed()

        old_keep = os.environ.get("YSCB_TEST_KEEP_SANDBOX")
        try:
            os.environ["YSCB_TEST_KEEP_SANDBOX"] = "0"
            suite = unittest.TestSuite()
            suite.addTest(LocalSharedTestCase("test_method_one"))
            suite.addTest(LocalSharedTestCase("test_method_two"))
            suite.addTest(LocalSharedTestCase("test_method_isolated"))
            suite.addTest(LocalSharedTestCaseB("test_method_b1"))

            runner = unittest.TextTestRunner(stream=StringIO(), verbosity=0)
            result = runner.run(suite)

            self.assertTrue(result.wasSuccessful())
            self.assertEqual(len(shared_dirs), 3)
            self.assertEqual(shared_dirs[0], shared_dirs[1])
            self.assertEqual(shared_dirs[0], shared_dirs[2])

            self.assertEqual(len(isolated_dirs), 1)
            self.assertNotEqual(isolated_dirs[0], shared_dirs[0])
            self.assertFalse(os.path.exists(isolated_dirs[0]))
        finally:
            if old_keep is not None:
                os.environ["YSCB_TEST_KEEP_SANDBOX"] = old_keep
            else:
                os.environ.pop("YSCB_TEST_KEEP_SANDBOX", None)
            for d in isolated_dirs:
                if os.path.exists(d):
                    SandboxProvisioner.cleanup_sandbox(d, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cleanup_shared_sandbox_safe(self):
        """Verify cleanup_shared_sandbox resets shared sandbox state in RuntimeContext and deletes directory."""
        saved_ctx = YSCBTestCase._get_shared_sandbox_ctx()
        mock_sb = SandboxProvisioner.create_sandbox()
        sb_dir = mock_sb.sandbox_dir
        self.assertTrue(os.path.isdir(sb_dir))

        try:
            YSCBTestCase._set_shared_sandbox_ctx(mock_sb)
            old_harness = os.environ.get("YSCB_TEST_SANDBOX")
            old_keep = os.environ.get("YSCB_TEST_KEEP_SANDBOX")
            try:
                os.environ["YSCB_TEST_SANDBOX"] = "0"
                os.environ["YSCB_TEST_KEEP_SANDBOX"] = "0"
                YSCBTestCase.cleanup_shared_sandbox()
                self.assertIsNone(YSCBTestCase._get_shared_sandbox_ctx())
                self.assertFalse(os.path.exists(sb_dir))
            finally:
                if old_harness is not None:
                    os.environ["YSCB_TEST_SANDBOX"] = old_harness
                else:
                    os.environ.pop("YSCB_TEST_SANDBOX", None)
                if old_keep is not None:
                    os.environ["YSCB_TEST_KEEP_SANDBOX"] = old_keep
                else:
                    os.environ.pop("YSCB_TEST_KEEP_SANDBOX", None)
        finally:
            YSCBTestCase._set_shared_sandbox_ctx(saved_ctx)
            if os.path.exists(sb_dir):
                SandboxProvisioner.cleanup_sandbox(sb_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_taxonomy_flags_and_masks(self):
        """Verify 4-tier taxonomy flags and composite masks."""
        self.assertTrue(bool(Requirement.LOGIC & Requirement.ALL_DEFAULT))
        self.assertTrue(bool(Requirement.ENV & Requirement.ALL_DEFAULT))
        self.assertFalse(bool(Requirement.WORKFLOW & Requirement.ALL_DEFAULT))
        self.assertFalse(bool(Requirement.PERF & Requirement.ALL_DEFAULT))
        self.assertTrue(bool(Requirement.WORKFLOW & Requirement.ALL))
        self.assertTrue(bool(Requirement.PERF & Requirement.ALL))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_is_network_available_and_require_inheritance(self):
        """Verify is_network_available branches and class/method @require inheritance and composition."""
        with patch("urllib.request.urlopen") as mock_open:
            self.assertTrue(is_network_available(timeout=0.5))
            mock_open.assert_called_once()

        with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            self.assertFalse(is_network_available(timeout=0.5))

        @require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
        class LocalClassReqCase(YSCBTestCase):
            def test_inherit_class(self):
                self.mark_passed()

            @require(Requirement.WORKFLOW)
            def test_override_cat(self):
                self.mark_passed()

        @require(Requirement.ENV)
        class LocalCatOnlyCase(YSCBTestCase):
            @require(Requirement.ISOLATED_SANDBOX)
            def test_iso_merges_class_cat(self):
                self.mark_passed()

        self.assertEqual(get_test_category(LocalClassReqCase("test_inherit_class")), "env")
        self.assertEqual(get_test_category(LocalClassReqCase("test_override_cat")), "workflow")
        self.assertEqual(get_test_category(LocalCatOnlyCase("test_iso_merges_class_cat")), "env")

        with patch.object(SandboxProvisioner, "create_sandbox", return_value=self.ctx), \
             patch.object(SandboxProvisioner, "cleanup_sandbox", return_value=True):
            c_inh = LocalClassReqCase("test_inherit_class")
            c_inh.setUp()
            try:
                self.assertTrue(c_inh._is_isolated_sandbox)
                c_inh.mark_passed()
            finally:
                c_inh.tearDown()

            c_merge = LocalCatOnlyCase("test_iso_merges_class_cat")
            c_merge.setUp()
            try:
                self.assertTrue(c_merge._is_isolated_sandbox)
                c_merge.mark_passed()
            finally:
                c_merge.tearDown()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_assertion_helpers_positive_and_negative(self):
        """Verify YSCBTestCase assertion helpers in both positive and negative scenarios."""
        self.assertSuccess(0)
        with self.assertRaises(AssertionError):
            self.assertSuccess(1)

        self.assertFailed(2)
        with self.assertRaises(AssertionError):
            self.assertFailed(0)

        self.assertInOutput("expected_token", "output has expected_token here")
        with self.assertRaises(AssertionError):
            self.assertInOutput("missing_token", "output without token")

        tmp_dir = tempfile.mkdtemp()
        try:
            json_path = os.path.join(tmp_dir, "sample.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"status": "ok", "count": 3}, f)

            self.assertFileExists(json_path)
            with self.assertRaises(AssertionError):
                self.assertFileExists(os.path.join(tmp_dir, "missing.json"))

            self.assertJsonEquals({"status": "ok", "count": 3}, json_path)
            with self.assertRaises(AssertionError):
                self.assertJsonEquals({"status": "mismatch"}, json_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        with patch("time.perf_counter", side_effect=[10.0, 10.2]):
            with self.assertExecutionTime(0.5):
                pass

        with patch("time.perf_counter", side_effect=[10.0, 12.5]):
            with self.assertRaises(AssertionError):
                with self.assertExecutionTime(1.0):
                    pass

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_security_error_when_direct_host_run(self):
        """Verify SecurityError when running outside sandbox or from invalid directory, and CWD ancestor discovery."""
        class GuardCheckCase(YSCBTestCase):
            def test_dummy(self):
                self.mark_passed()

        old_val = os.environ.get("YSCB_TEST_SANDBOX")
        old_sb_dir = os.environ.get("YSCB_SANDBOX_DIR")
        saved_shared_ctx = YSCBTestCase._get_shared_sandbox_ctx()
        orig_cwd = os.getcwd()
        plain_tmp = tempfile.mkdtemp()
        try:
            os.environ.pop("YSCB_TEST_SANDBOX", None)
            dummy = GuardCheckCase("test_dummy")
            with self.assertRaises(SecurityError) as ctx:
                dummy.setUp()
            self.assertIn("Security Guard Blocked", str(ctx.exception))

            os.environ["YSCB_TEST_SANDBOX"] = "1"
            os.environ["YSCB_SANDBOX_DIR"] = os.path.join(plain_tmp, "nonexistent_sb")
            YSCBTestCase._set_shared_sandbox_ctx(None)
            os.chdir(plain_tmp)
            dummy_invalid = GuardCheckCase("test_dummy")
            with self.assertRaises(SecurityError) as ctx2:
                dummy_invalid.setUp()
            self.assertIn("Unable to resolve an authentic virtual sandbox directory", str(ctx2.exception))

            os.environ.pop("YSCB_SANDBOX_DIR", None)
            YSCBTestCase._set_shared_sandbox_ctx(None)
            os.chdir(self.sandbox_host_dir)
            dummy_walk = GuardCheckCase("test_dummy")
            dummy_walk.setUp()
            try:
                self.assertEqual(os.path.abspath(dummy_walk.sandbox_dir), os.path.abspath(self.sandbox_dir))
                dummy_walk.mark_passed()
            finally:
                dummy_walk.tearDown()
        finally:
            os.chdir(orig_cwd)
            YSCBTestCase._set_shared_sandbox_ctx(saved_shared_ctx)
            if old_val is not None:
                os.environ["YSCB_TEST_SANDBOX"] = old_val
            else:
                os.environ.pop("YSCB_TEST_SANDBOX", None)
            if old_sb_dir is not None:
                os.environ["YSCB_SANDBOX_DIR"] = old_sb_dir
            else:
                os.environ.pop("YSCB_SANDBOX_DIR", None)
            shutil.rmtree(plain_tmp, ignore_errors=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_execution_status_classification_in_teardown(self):
        """Verify tearDown classifies Passed, Failed, and UNKNOWN and prints [Sandbox Kept] / [Test Failed]."""
        class StatusDemoCase(YSCBTestCase):
            def test_explicit_passed(self):
                self.mark_passed()

            def test_no_mark_no_error(self):
                pass

            def test_raises_failure(self):
                raise AssertionError("Deliberate failure")

        orig_out = sys.stdout
        old_keep = os.environ.get("YSCB_TEST_KEEP_SANDBOX")

        # 1. Explicit Passed with YSCB_TEST_KEEP_SANDBOX=1 -> PASSED & [Sandbox Kept]
        captured_passed = StringIO()
        try:
            os.environ["YSCB_TEST_KEEP_SANDBOX"] = "1"
            case_passed = StatusDemoCase("test_explicit_passed")
            case_passed.setUp()
            sys.stdout = captured_passed
            case_passed._callTestMethod(getattr(case_passed, "test_explicit_passed"))
            case_passed.tearDown()
        finally:
            sys.stdout = orig_out
            if old_keep is not None:
                os.environ["YSCB_TEST_KEEP_SANDBOX"] = old_keep
            else:
                os.environ.pop("YSCB_TEST_KEEP_SANDBOX", None)
        self.assertEqual(case_passed.execution_status, "PASSED")
        self.assertIn("[Sandbox Kept]", captured_passed.getvalue())

        # 2. No mark passed and no exception -> UNKNOWN (without outputting [Test Failed])
        captured_unknown = StringIO()
        case_unknown = StatusDemoCase("test_no_mark_no_error")
        case_unknown.setUp()
        try:
            sys.stdout = captured_unknown
            case_unknown._callTestMethod(getattr(case_unknown, "test_no_mark_no_error"))
            case_unknown.tearDown()
        finally:
            sys.stdout = orig_out
        self.assertEqual(case_unknown.execution_status, "UNKNOWN")
        self.assertNotIn("[Test Failed]", captured_unknown.getvalue())

        # 3. Raises Failure -> FAILED & [Test Failed]
        captured_failed = StringIO()
        case_failed = StatusDemoCase("test_raises_failure")
        case_failed.setUp()
        try:
            sys.stdout = captured_failed
            with self.assertRaises(AssertionError):
                case_failed._callTestMethod(getattr(case_failed, "test_raises_failure"))
            case_failed.tearDown()
        finally:
            sys.stdout = orig_out
        self.assertEqual(case_failed.execution_status, "FAILED")
        self.assertIn("[Test Failed]", captured_failed.getvalue())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cwd_restoration_in_teardown(self):
        """Verify YSCBTestCase.tearDown restores CWD to self._orig_cwd."""
        class CWDDemoCase(YSCBTestCase):
            def test_drift(self):
                self.mark_passed()

        orig_dir = os.getcwd()
        case = CWDDemoCase("test_drift")
        case.setUp()
        self.assertEqual(case._orig_cwd, orig_dir)

        temp_sub = tempfile.mkdtemp()
        try:
            os.chdir(temp_sub)
            self.assertEqual(os.getcwd(), temp_sub)
            case.tearDown()
            self.assertEqual(os.getcwd(), orig_dir, "Expected tearDown to restore original CWD")
        finally:
            if os.path.exists(temp_sub):
                os.rmdir(temp_sub)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_create_mock_source_module_default_compliance(self):
        """Verify create_mock_source_module generates compliant module passing Checker with zero warnings."""
        mod_name = "mock_compliant_test_mod"
        src_path = self.create_mock_source_module(mod_name)
        try:
            self.assertTrue(os.path.isdir(src_path))
            checker = Checker()
            report = checker.check_module(mod_name)
            self.assertTrue(report.passed, f"Default mock source module failed check: {report.errors}")
            self.assertFalse(report.has_warns, f"Default mock source module produced warnings: {report.warnings}")
        finally:
            if os.path.exists(src_path):
                shutil.rmtree(src_path, ignore_errors=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_teardown_incremental_env_restore_and_run_cli_tree_timeout(self):
        """Verify YSCBTestCase.tearDown restores os.environ without calling clear() and run_cli delegates to run_subprocess_with_tree_timeout."""
        class EnvAndCliCase(YSCBTestCase):
            def test_noop(self):
                self.mark_passed()

        case = EnvAndCliCase("test_noop")
        case.setUp()
        os.environ["YSCB_TEST_TEMP_ADDED_VAR"] = "added"
        with patch.object(os.environ, "clear", side_effect=AssertionError("os.environ.clear() must not be called")):
            case.tearDown()
        self.assertNotIn("YSCB_TEST_TEMP_ADDED_VAR", os.environ)

        with patch("dev.testing.runner.run_subprocess_with_tree_timeout", return_value=(124, "", "[TimeoutError]")) as mock_run:
            rc, out, err = self.run_cli(["status"], timeout=12.5)
            self.assertEqual(rc, 124)
            self.assertEqual(err, "[TimeoutError]")
            mock_run.assert_called_once()
            self.assertEqual(mock_run.call_args.kwargs.get("timeout_sec"), 12.5)

        self.mark_passed()
