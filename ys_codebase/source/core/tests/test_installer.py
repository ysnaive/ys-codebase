"""
Official test suite for core.installer.Installer.
"""
import os
from dev.testing import YSCBTestCase, require, Requirement
from core.installer import Installer
from core import uri

@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreInstaller(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.installer = Installer()

    def test_status_health_reporting(self):
        """T-01 實質化：驗證 cmd_status 健全環境回傳 0 且輸出包含 HEALTHY (100% Ready)，異常環境回傳 1 且輸出 Incomplete 與 DEGRADED。"""
        import io
        from contextlib import redirect_stdout

        # 1. 健全狀態測試
        buf_ok = io.StringIO()
        with redirect_stdout(buf_ok):
            res_ok = self.installer.cmd_status()
        self.assertEqual(res_ok, 0)
        self.assertIn("HEALTHY (100% Ready)", buf_ok.getvalue())

        # 2. 偽造缺少 scripts/cli.py 的殘破模組，驗證降級回傳 1
        cfg_path, cfg = self.installer.engine._get_config()
        orig_installed = dict(cfg.get("installed_modules", {}))
        cfg.setdefault("installed_modules", {})["broken_mod"] = {"version": "0.0.1"}
        self.installer.engine._save_config(cfg_path, cfg)
        try:
            buf_bad = io.StringIO()
            with redirect_stdout(buf_bad):
                res_bad = self.installer.cmd_status()
            self.assertEqual(res_bad, 1)
            bad_out = buf_bad.getvalue()
            self.assertIn("Incomplete", bad_out)
            self.assertIn("DEGRADED", bad_out)
        finally:
            cfg["installed_modules"] = orig_installed
            self.installer.engine._save_config(cfg_path, cfg)

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

    def test_optional_dependencies_hint(self):
        """FT-01: 驗證模組宣告 optional 且未安裝時，安裝器提示擴充模組建議與指令"""
        import io
        import shutil
        from contextlib import redirect_stdout

        mod_name = "mock_opt_host"
        uri.makedirs(f"module://{mod_name}")
        uri.write_json(f"module://{mod_name}/manifest.json", {
            "name": mod_name,
            "version": "1.0.0",
            "dependencies": {"core": ">=1.0.0"},
            "optional": {
                "mock_uninstalled_ext": {
                    "version": ">=1.0.0",
                    "hint": "提供額外擴充能力"
                }
            }
        })

        f_out = io.StringIO()
        with redirect_stdout(f_out):
            self.installer._check_optional_dependencies(mod_name)
        out = f_out.getvalue()
        self.assertIn("偵測到可用的擴充模組", out)
        self.assertIn("mock_uninstalled_ext (>=1.0.0)", out)
        self.assertIn("python yscb.py install mock_uninstalled_ext", out)

        # Cleanup
        target_dir = uri.resolve(f"module://{mod_name}")
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        self.mark_passed()

    def test_optional_dependencies_already_installed(self):
        """FT-02: 驗證模組宣告 optional 且已安裝時，靜默跳過無提示"""
        import io
        import shutil
        from contextlib import redirect_stdout

        mod_name = "mock_opt_host_installed"
        uri.makedirs(f"module://{mod_name}")
        uri.write_json(f"module://{mod_name}/manifest.json", {
            "name": mod_name,
            "version": "1.0.0",
            "dependencies": {"core": ">=1.0.0"},
            "optional": {
                "core": {
                    "version": ">=1.0.0",
                    "hint": "核心模組"
                }
            }
        })

        f_out = io.StringIO()
        with redirect_stdout(f_out):
            self.installer._check_optional_dependencies(mod_name)
        out = f_out.getvalue()
        self.assertNotIn("偵測到可用的擴充模組", out)

        # Cleanup
        target_dir = uri.resolve(f"module://{mod_name}")
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        self.mark_passed()

    def test_update_skips_build_version(self):
        """TASK-06: 驗證 cmd_update 自動跳過 @build 開發中版本，防範降級覆蓋。"""
        import io
        from contextlib import redirect_stdout

        self.installer.engine.act_register("mock_dev_mod", "1.0.0.build", "local")

        f_out = io.StringIO()
        with redirect_stdout(f_out):
            res = self.installer.cmd_update("mock_dev_mod")
        out = f_out.getvalue()

        self.assertEqual(res, 0)
        self.assertIn("is a development build", out)
        self.assertIn("skipping update", out)

        # Cleanup
        self.installer.engine.act_unregister("mock_dev_mod")
        self.mark_passed()

    def test_cmd_restore_empty_and_fetch_extract(self):
        """FT-01: 驗證 cmd_restore 無模組需還原時安全返回 0，且 fetch_and_extract_zip 正常解壓。"""
        import tempfile
        import zipfile
        from core.installer import fetch_and_extract_zip
        res = self.installer.cmd_restore()
        self.assertEqual(res, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_p = os.path.join(tmp_dir, "test.zip")
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("test.txt", "hello yscb")
                zf.writestr("nested/foo.json", '{"key": "value"}')

            extract_dest = os.path.join(tmp_dir, "extracted")
            fetch_and_extract_zip(zip_p, extract_dest)

            self.assertTrue(os.path.isfile(os.path.join(extract_dest, "test.txt")))
            self.assertEqual(open(os.path.join(extract_dest, "test.txt")).read(), "hello yscb")
            self.assertTrue(os.path.isfile(os.path.join(extract_dest, "nested", "foo.json")))
        self.mark_passed()

    def test_cmd_list_remote_and_local(self):
        """C-04 / FT-04 / ET-04: 驗證 cmd_list 支援 remote 與 local 雙模式查詢及無效 Provider 回傳 1。"""
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout

        buf_local = io.StringIO()
        with redirect_stdout(buf_local):
            ret_loc = self.installer.cmd_list(remote=False)
        self.assertEqual(ret_loc, 0)
        self.assertIn("Module Name", buf_local.getvalue())

        # Valid local mock provider for --remote (FT-04)
        with tempfile.TemporaryDirectory() as prov_dir:
            core_dir = os.path.join(prov_dir, "core")
            extra_dir = os.path.join(prov_dir, "mock_remote_pkg")
            os.makedirs(core_dir, exist_ok=True)
            os.makedirs(extra_dir, exist_ok=True)
            with open(os.path.join(core_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "core", "latest": "1.0.9.9", "versions": ["1.0.9.9"]}, f)
            with open(os.path.join(extra_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "mock_remote_pkg", "latest": "2.1.0.0", "versions": ["2.1.0.0"]}, f)

            buf_valid_rem = io.StringIO()
            with redirect_stdout(buf_valid_rem):
                ret_valid_rem = self.installer.cmd_list(remote=True, provider=prov_dir)
            self.assertEqual(ret_valid_rem, 0)
            rem_out = buf_valid_rem.getvalue()
            self.assertIn("Installed (v", rem_out)
            self.assertIn("mock_remote_pkg", rem_out)
            self.assertIn("Available", rem_out)

        # Remote list with nonexistent provider returns 1 (ET-04)
        buf_remote = io.StringIO()
        with redirect_stdout(buf_remote):
            ret_rem = self.installer.cmd_list(remote=True, provider="/nonexistent/provider")
        self.assertEqual(ret_rem, 1)
        self.assertIn("No remote modules found", buf_remote.getvalue())
        self.mark_passed()

    def test_cmd_update_end_to_end_and_major_lock(self):
        """T-06 補盲: 驗證 cmd_update 端到端升級、Major Lock 跨大版本攔截與增量遷移腳本觸發。"""
        import io
        import json
        import zipfile
        import tempfile
        from contextlib import redirect_stdout

        mod_name = "mock_up_mod"
        with tempfile.TemporaryDirectory() as prov_dir:
            mod_prov_dir = os.path.join(prov_dir, mod_name)
            os.makedirs(mod_prov_dir, exist_ok=True)

            # 1. 建立 1.0.0.0.zip
            with zipfile.ZipFile(os.path.join(mod_prov_dir, "1.0.0.0.zip"), "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "1.0.0.0", "entry": "scripts/cli.py"}))
                zf.writestr("scripts/cli.py", "def main(): return 0\n")

            # 2. 建立 1.2.0.0.zip (含 1.1.x.py 與 1.2.x.py 遷移腳本)
            mig_code = (
                "import os, json\n"
                "def migrate(ctx):\n"
                "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
                "    p = os.path.join(ctx['storage_dir'], 'up_mig.json')\n"
                "    arr = json.load(open(p)) if os.path.isfile(p) else []\n"
                "    arr.append(ctx['target_version'])\n"
                "    json.dump(arr, open(p, 'w'))\n"
                "    return True\n"
            )
            with zipfile.ZipFile(os.path.join(mod_prov_dir, "1.2.0.0.zip"), "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "1.2.0.0", "entry": "scripts/cli.py"}))
                zf.writestr("scripts/cli.py", "def main(): return 0\n")
                zf.writestr("scripts/migrations/1.1.x.py", mig_code)
                zf.writestr("scripts/migrations/1.2.x.py", mig_code)

            # 3. 建立 2.0.0.0.zip (跨 Major 版本，應被 Major Lock 攔截)
            with zipfile.ZipFile(os.path.join(mod_prov_dir, "2.0.0.0.zip"), "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "2.0.0.0", "entry": "scripts/cli.py"}))
                zf.writestr("scripts/cli.py", "def main(): return 0\n")

            with open(os.path.join(mod_prov_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump({"name": mod_name, "latest": "2.0.0.0", "versions": ["1.0.0.0", "1.2.0.0", "2.0.0.0"]}, f)

            try:
                # 先安裝 1.0.0.0
                ret_inst = self.installer.cmd_install(mod_name, version="1.0.0.0", provider=prov_dir)
                self.assertEqual(ret_inst, 0)

                # 執行 cmd_update：應升級至 1.2.0.0（受 Major Lock 保護不升上 2.0.0.0）並觸發 1.1.x / 1.2.x 遷移
                buf_up = io.StringIO()
                with redirect_stdout(buf_up):
                    ret_up = self.installer.cmd_update(mod_name, provider=prov_dir)
                self.assertEqual(ret_up, 0)

                _, cfg = self.installer.engine._get_config()
                self.assertEqual(cfg["installed_modules"][mod_name]["version"], "1.2.0.0")

                mig_trace_p = os.path.join(uri.resolve(f"storage://{mod_name}"), "up_mig.json")
                self.assertTrue(os.path.isfile(mig_trace_p))
                with open(mig_trace_p, "r", encoding="utf-8") as f:
                    mig_runs = json.load(f)
                self.assertEqual(len(mig_runs), 2)
            finally:
                self.installer.cmd_remove(mod_name, force=True, purge=True)
                if uri.exists(f"module.mirror://{mod_name}"):
                    uri.rmtree(f"module.mirror://{mod_name}")

        self.mark_passed()

