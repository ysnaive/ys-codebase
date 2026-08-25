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

    def test_remove_reverse_dependency_guard(self):
        """Verify cmd_remove blocks removal when required by other modules, and allows with force (FT-05)."""
        # Register mock_lib and dependent mock_app
        self.installer.engine.act_register("mock_lib", "1.0.0", "local")
        self.installer.engine.act_register("mock_app", "1.0.0", "local")
        
        # Setup mock_app manifest declaring dependency on mock_lib
        uri.makedirs("module.root://mock_app")
        uri.write_json("module.root://mock_app/manifest.json", {
            "name": "mock_app",
            "version": "1.0.0",
            "dependencies": {"mock_lib": ">=1.0.0"}
        })
        uri.makedirs("module.root://mock_lib")
        uri.write_json("module.root://mock_lib/manifest.json", {
            "name": "mock_lib",
            "version": "1.0.0"
        })
        
        # 1. Attempting to remove mock_lib without force should be blocked
        res_blocked = self.installer.cmd_remove("mock_lib", force=False)
        self.assertEqual(res_blocked, 1)
        
        # 2. Attempting with force=True should succeed
        res_forced = self.installer.cmd_remove("mock_lib", force=True)
        self.assertEqual(res_forced, 0)
        
        # Cleanup
        self.installer.cmd_remove("mock_app", force=True)
        self.mark_passed()

    def test_list_installed_modules(self):
        """Verify cmd_list executes successfully."""
        res = self.installer.cmd_list()
        self.assertEqual(res, 0)
        self.mark_passed()
