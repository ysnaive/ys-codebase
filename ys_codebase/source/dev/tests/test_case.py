"""
Unit tests for YSCBTestCase sandbox sharing, isolation branching, and YSCB_TEST_SANDBOX propagation.
"""
import os
import tempfile
import unittest
from dev.testing.case import YSCBTestCase, SecurityError
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner
from dev.checker import Checker


class TestCaseSandboxLifecycleTest(YSCBTestCase):
    """Test suite validating YSCBTestCase sandbox lifecycle rules."""

    @require(Requirement.LOGIC)
    def test_requirement_isolated_sandbox_flag(self):
        """FT-01: Verify Requirement.ISOLATED_SANDBOX is defined and combinable."""
        flag = Requirement.ISOLATED_SANDBOX
        self.assertTrue(bool(flag & Requirement.ISOLATED_SANDBOX))
        comb = Requirement.LOGIC | Requirement.ISOLATED_SANDBOX
        self.assertTrue(bool(comb & Requirement.LOGIC))
        self.assertTrue(bool(comb & Requirement.ISOLATED_SANDBOX))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_shared_and_isolated_sandbox_dispatch(self):
        """FT-02, FT-03, ET-01: Verify shared vs isolated sandbox behavior in local TestCases."""
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

        suite = unittest.TestSuite()
        suite.addTest(LocalSharedTestCase("test_method_one"))
        suite.addTest(LocalSharedTestCase("test_method_two"))
        suite.addTest(LocalSharedTestCase("test_method_isolated"))
        suite.addTest(LocalSharedTestCaseB("test_method_b1"))

        runner = unittest.TextTestRunner(verbosity=0)
        result = runner.run(suite)

        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(shared_dirs), 3)
        # Shared methods across different classes must have identical session-level sandbox_dir
        self.assertEqual(shared_dirs[0], shared_dirs[1])
        self.assertEqual(shared_dirs[0], shared_dirs[2])
        
        self.assertEqual(len(isolated_dirs), 1)
        # Isolated method must have a different sandbox_dir
        self.assertNotEqual(isolated_dirs[0], shared_dirs[0])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cleanup_shared_sandbox_safe(self):
        """FT-03: Verify cleanup_shared_sandbox resets _shared_sandbox_ctx and deletes directory."""
        saved_ctx = YSCBTestCase._shared_sandbox_ctx
        mock_sb = SandboxProvisioner.create_sandbox()
        sb_dir = mock_sb.sandbox_dir
        self.assertTrue(os.path.isdir(sb_dir))

        try:
            YSCBTestCase._shared_sandbox_ctx = mock_sb
            # Temporarily simulate non-harness managed mode to allow cleanup
            old_harness = os.environ.get("YSCB_TEST_SANDBOX")
            old_keep = os.environ.get("YSCB_TEST_KEEP_SANDBOX")
            try:
                os.environ["YSCB_TEST_SANDBOX"] = "0"
                os.environ["YSCB_TEST_KEEP_SANDBOX"] = "0"
                YSCBTestCase.cleanup_shared_sandbox()
                self.assertIsNone(YSCBTestCase._shared_sandbox_ctx)
                self.assertFalse(os.path.exists(sb_dir))
            finally:
                if old_harness is not None:
                    os.environ["YSCB_TEST_SANDBOX"] = old_harness
                if old_keep is not None:
                    os.environ["YSCB_TEST_KEEP_SANDBOX"] = old_keep
        finally:
            YSCBTestCase._shared_sandbox_ctx = saved_ctx
            if os.path.exists(sb_dir):
                SandboxProvisioner.cleanup_sandbox(sb_dir, force=True)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_taxonomy_flags_and_masks(self):
        """FT-01: Verify 4-tier taxonomy flags, aliases, and composite masks."""
        self.assertTrue(bool(Requirement.LOGIC & Requirement.ALL_DEFAULT))
        self.assertTrue(bool(Requirement.ENV & Requirement.ALL_DEFAULT))
        self.assertFalse(bool(Requirement.WORKFLOW & Requirement.ALL_DEFAULT))
        self.assertFalse(bool(Requirement.PERF & Requirement.ALL_DEFAULT))
        self.assertTrue(bool(Requirement.WORKFLOW & Requirement.ALL))
        self.assertTrue(bool(Requirement.PERF & Requirement.ALL))
        self.assertEqual(Requirement.PERFORMANCE, Requirement.PERF)
        self.assertEqual(Requirement.HOST_CLI, Requirement.ENV)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_security_error_when_direct_host_run(self):
        """FT-05 & ET-02: Verify SecurityError is raised if running YSCBTestCase directly outside sandbox."""
        class GuardCheckCase(YSCBTestCase):
            def test_dummy(self):
                self.mark_passed()

        old_val = os.environ.get("YSCB_TEST_SANDBOX")
        try:
            if "YSCB_TEST_SANDBOX" in os.environ:
                del os.environ["YSCB_TEST_SANDBOX"]
            
            dummy = GuardCheckCase("test_dummy")
            with self.assertRaises(SecurityError) as ctx:
                dummy.setUp()
            self.assertIn("Security Guard Blocked", str(ctx.exception))
        finally:
            if old_val is not None:
                os.environ["YSCB_TEST_SANDBOX"] = old_val
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_execution_status_classification_in_teardown(self):
        """Verify tearDown classifies: Passed, Failed, and uncalled mark_passed without exception as UNKNOWN."""
        from io import StringIO
        import sys

        class StatusDemoCase(YSCBTestCase):
            def test_explicit_passed(self):
                self.mark_passed()

            def test_no_mark_no_error(self):
                pass  # no mark_passed and no exception -> should be UNKNOWN

            def test_raises_failure(self):
                raise AssertionError("Deliberate failure")

        # 1. Explicit Passed
        case_passed = StatusDemoCase("test_explicit_passed")
        case_passed.setUp()
        case_passed._callTestMethod(getattr(case_passed, "test_explicit_passed"))
        case_passed.tearDown()
        self.assertEqual(case_passed.execution_status, "PASSED")

        # 2. No mark passed and no exception -> UNKNOWN (without outputting [Test Failed])
        captured_out = StringIO()
        orig_out = sys.stdout
        case_unknown = StatusDemoCase("test_no_mark_no_error")
        case_unknown.setUp()
        try:
            sys.stdout = captured_out
            case_unknown._callTestMethod(getattr(case_unknown, "test_no_mark_no_error"))
            case_unknown.tearDown()
        finally:
            sys.stdout = orig_out
        self.assertEqual(case_unknown.execution_status, "UNKNOWN")
        self.assertNotIn("[Test Failed]", captured_out.getvalue())

        # 3. Raises Failure -> FAILED
        case_failed = StatusDemoCase("test_raises_failure")
        case_failed.setUp()
        with self.assertRaises(AssertionError):
            case_failed._callTestMethod(getattr(case_failed, "test_raises_failure"))
        case_failed.tearDown()
        self.assertEqual(case_failed.execution_status, "FAILED")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cwd_restoration_in_teardown(self):
        """FT-06: Verify YSCBTestCase.tearDown restores CWD to self._orig_cwd."""
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
        """FT-05: Verify create_mock_source_module generates 100% compliant module passing Checker."""
        import shutil
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
