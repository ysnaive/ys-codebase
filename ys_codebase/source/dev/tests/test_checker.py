"""
Official test suite for dev.checker.Checker.
"""
from dev.testing import YSCBTestCase
from dev.checker import Checker
from core import uri

class TestDevChecker(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.checker = Checker()

    def test_check_core_module_passes(self):
        """Verify checking 'core' module returns True with 0 errors."""
        passed, errors = self.checker.check_module("core")
        self.assertTrue(passed, f"Core check failed with errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.mark_passed()

    def test_check_dev_module_passes(self):
        """Verify checking 'dev' module returns True with 0 errors."""
        passed, errors = self.checker.check_module("dev")
        self.assertTrue(passed, f"Dev check failed with errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.mark_passed()

    def test_check_all_passes(self):
        """Verify check_all succeeds across source/."""
        res = self.checker.check_all()
        for mod, (passed, errors) in res.items():
            self.assertTrue(passed, f"Module '{mod}' failed check: {errors}")
        self.mark_passed()
