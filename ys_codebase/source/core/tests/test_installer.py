"""
Official test suite for core.installer.Installer.
"""
from dev.testing import YSCBTestCase
from core.installer import Installer
from core import uri

class TestCoreInstaller(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.installer = Installer()

    def test_status_health_reporting(self):
        """Verify cmd_status produces diagnostic health report without crashing."""
        res = self.installer.cmd_status()
        self.assertIn(res, (0, 1))
        self.mark_passed()

    def test_remove_core_infrastructure_guard(self):
        """Verify core module is protected from removal."""
        res = self.installer.cmd_remove("core")
        self.assertEqual(res, 1)
        self.mark_passed()

    def test_list_installed_modules(self):
        """Verify cmd_list executes successfully."""
        res = self.installer.cmd_list()
        self.assertEqual(res, 0)
        self.mark_passed()
