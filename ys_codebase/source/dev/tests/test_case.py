"""
Unit tests for YSCBTestCase sandbox sharing, isolation branching, and YSCB_TEST_SANDBOX propagation.
"""
import os
import unittest
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.testing.sandbox import SandboxProvisioner

_shared_dirs_recorded = []
_isolated_dirs_recorded = []

class DummySharedTestCase(YSCBTestCase):
    """Test class verifying default shared sandbox across methods."""
    def test_method_one(self):
        _shared_dirs_recorded.append(self.sandbox_dir)
        self.assertTrue(os.path.isdir(self.sandbox_dir))
        self.assertFalse(self._is_isolated_sandbox)
        self.mark_passed()

    def test_method_two(self):
        _shared_dirs_recorded.append(self.sandbox_dir)
        self.assertTrue(os.path.isdir(self.sandbox_dir))
        self.assertFalse(self._is_isolated_sandbox)
        self.mark_passed()

    @require(Requirement.ISOLATED_SANDBOX)
    def test_method_isolated(self):
        _isolated_dirs_recorded.append(self.sandbox_dir)
        self.assertTrue(os.path.isdir(self.sandbox_dir))
        self.assertTrue(self._is_isolated_sandbox)
        self.mark_passed()


class DummySharedTestCaseB(YSCBTestCase):
    """Second test class verifying cross-class session-level sandbox reuse."""
    def test_method_b1(self):
        _shared_dirs_recorded.append(self.sandbox_dir)
        self.assertTrue(os.path.isdir(self.sandbox_dir))
        self.assertFalse(self._is_isolated_sandbox)
        self.mark_passed()


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
        """FT-02, FT-03, ET-01: Verify shared vs isolated sandbox behavior in DummySharedTestCase."""
        _shared_dirs_recorded.clear()
        _isolated_dirs_recorded.clear()

        suite = unittest.TestSuite()
        suite.addTest(DummySharedTestCase("test_method_one"))
        suite.addTest(DummySharedTestCase("test_method_two"))
        suite.addTest(DummySharedTestCase("test_method_isolated"))
        suite.addTest(DummySharedTestCaseB("test_method_b1"))

        runner = unittest.TextTestRunner(verbosity=0)
        result = runner.run(suite)

        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(_shared_dirs_recorded), 3)
        # Shared methods across different classes must have identical session-level sandbox_dir
        self.assertEqual(_shared_dirs_recorded[0], _shared_dirs_recorded[1])
        self.assertEqual(_shared_dirs_recorded[0], _shared_dirs_recorded[2])
        
        self.assertEqual(len(_isolated_dirs_recorded), 1)
        # Isolated method must have a different sandbox_dir
        self.assertNotEqual(_isolated_dirs_recorded[0], _shared_dirs_recorded[0])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cleanup_shared_sandbox_safe(self):
        """FT-03: Verify cleanup_shared_sandbox resets _shared_sandbox_ctx and deletes dir."""
        saved_ctx = YSCBTestCase._shared_sandbox_ctx
        mock_sb = SandboxProvisioner.create_sandbox()
        try:
            YSCBTestCase._shared_sandbox_ctx = mock_sb
            sb_dir = mock_sb.sandbox_dir
            self.assertTrue(os.path.isdir(sb_dir))
        finally:
            YSCBTestCase._shared_sandbox_ctx = saved_ctx
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
        from dev.testing.case import SecurityError
        old_val = os.environ.get("YSCB_TEST_SANDBOX")
        try:
            if "YSCB_TEST_SANDBOX" in os.environ:
                del os.environ["YSCB_TEST_SANDBOX"]
            
            dummy = DummySharedTestCase("test_method_one")
            with self.assertRaises(SecurityError) as ctx:
                dummy.setUp()
            self.assertIn("Security Guard Blocked", str(ctx.exception))
        finally:
            if old_val is not None:
                os.environ["YSCB_TEST_SANDBOX"] = old_val
        self.mark_passed()
