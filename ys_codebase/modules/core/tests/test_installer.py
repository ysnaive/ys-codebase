"""
Official test suite for core.installer.Installer.
"""
from dev.testing import YSCBTestCase, require, Requirement
from core.installer import Installer
from core import uri

@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
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
        uri.makedirs("module://mock_app")
        uri.write_json("module://mock_app/manifest.json", {
            "name": "mock_app",
            "version": "1.0.0",
            "dependencies": {"mock_lib": ">=1.0.0"}
        })
        uri.makedirs("module://mock_lib")
        uri.write_json("module://mock_lib/manifest.json", {
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

    def test_remove_lifecycle_cache_cleaning_and_purge(self):
        """FT-04, FT-05, ET-04: Test module removal cache cleaning and --purge behavior."""
        # 1. Setup mock_lifecycle module with storage, config, and cache
        mod_name = "mock_lifecycle"
        self.installer.engine.act_register(mod_name, "1.0.0", "local")
        uri.makedirs(f"module://{mod_name}")
        uri.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0"})
        
        uri.makedirs(f"storage://{mod_name}")
        uri.write_text(f"storage://{mod_name}/data.json", '{"state": 1}')
        uri.makedirs(f"config://{mod_name}")
        uri.write_text(f"config://{mod_name}/config.json", '{"enabled": true}')
        uri.makedirs(f"cache://{mod_name}")
        uri.write_text(f"cache://{mod_name}/temp.cache", "cache_content")

        # Standard remove: cache deleted, storage & config preserved
        res_std = self.installer.cmd_remove(mod_name, force=True, purge=False)
        self.assertEqual(res_std, 0)
        self.assertFalse(uri.exists(f"cache://{mod_name}"))
        self.assertTrue(uri.exists(f"storage://{mod_name}"))
        self.assertTrue(uri.exists(f"config://{mod_name}"))

        # Re-register and populate for purge test
        self.installer.engine.act_register(mod_name, "1.0.0", "local")
        uri.makedirs(f"module://{mod_name}")
        uri.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0"})
        uri.makedirs(f"cache://{mod_name}")
        uri.write_text(f"cache://{mod_name}/temp.cache", "cache_content")

        # Purge remove: cache, storage, config all deleted
        res_purge = self.installer.cmd_remove(mod_name, force=True, purge=True)
        self.assertEqual(res_purge, 0)
        self.assertFalse(uri.exists(f"cache://{mod_name}"))
        self.assertFalse(uri.exists(f"storage://{mod_name}"))
        self.assertFalse(uri.exists(f"config://{mod_name}"))
        self.mark_passed()

    def test_list_installed_modules(self):
        """Verify cmd_list executes successfully."""
        res = self.installer.cmd_list()
        self.assertEqual(res, 0)
        self.mark_passed()

    def test_install_unreleased_module_strict_error(self):
        """FT-09: Verify unreleased or non-existent module installation is strictly rejected with error."""
        # 1. Direct engine call must raise ModuleNotFoundError (Zero Dummy Fallback)
        with self.assertRaises(ModuleNotFoundError):
            self.installer.engine._get_module_manifest_from_provider_or_local("non_existent_unreleased_xyz", "local")

        # 2. CLI install must fail cleanly with return code 1
        res = self.installer.cmd_install("non_existent_unreleased_xyz")
        self.assertEqual(res, 1)

        # 3. yscb.config.json must NOT contain the ghost module
        _, cfg = self.installer.engine._get_config()
        self.assertNotIn("non_existent_unreleased_xyz", cfg.get("installed_modules", {}))
        self.mark_passed()

    def test_build_package_isolation(self):
        """FT-10: Verify build packages are isolated and only accessible when explicitly requested."""
        import zipfile
        import json
        mod_name = "mock_isolated_build_mod"

        # Setup build package in module.build://
        uri.makedirs(f"module.build://{mod_name}")
        build_zip_path = uri.resolve(f"module.build://{mod_name}/1.0.0.build.zip")
        with zipfile.ZipFile(build_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "1.0.0.build"}))
            zf.writestr("scripts/cli.py", "print('mock build cli')")

        # 1. Regular install (no build revision specified) MUST fail because module is not released
        res_regular = self.installer.cmd_install(mod_name)
        self.assertEqual(res_regular, 1)

        # 2. Explicit build install (version="1.0.0.build") MUST succeed
        res_build = self.installer.cmd_install(mod_name, version="1.0.0.build")
        self.assertEqual(res_build, 0)

        # Verify installed version has .build tag
        _, cfg = self.installer.engine._get_config()
        self.assertIn(mod_name, cfg.get("installed_modules", {}))
        self.assertEqual(cfg["installed_modules"][mod_name]["version"], "1.0.0.build")

        # Cleanup
        self.installer.cmd_remove(mod_name, force=True, purge=True)
        self.mark_passed()
