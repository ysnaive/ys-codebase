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

        runner = unittest.TextTestRunner(verbosity=0)
        result = runner.run(suite)

        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(_shared_dirs_recorded), 2)
        # Shared methods must have identical sandbox_dir
        self.assertEqual(_shared_dirs_recorded[0], _shared_dirs_recorded[1])
        
        self.assertEqual(len(_isolated_dirs_recorded), 1)
        # Isolated method must have a different sandbox_dir
        self.assertNotEqual(_isolated_dirs_recorded[0], _shared_dirs_recorded[0])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ysc_test_sandbox_env_set_in_setup(self):
        """FT-03: Verify YSCB_TEST_SANDBOX=1 is set in setUp."""
        self.assertEqual(os.environ.get("YSCB_TEST_SANDBOX"), "1")
        self.mark_passed()
