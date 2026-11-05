"""
Official test suite for core.installer.Installer.
"""
import os
from dev.testing import YSCBTestCase, require, Requirement
from core.installer import Installer
from core import uri, vfs

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
        vfs.makedirs("module://mock_app")
        vfs.write_json("module://mock_app/manifest.json", {
            "name": "mock_app",
            "version": "1.0.0",
            "dependencies": {"mock_lib": ">=1.0.0"}
        })
        vfs.makedirs("module://mock_lib")
        vfs.write_json("module://mock_lib/manifest.json", {
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
        """FT-04, FT-05, ET-04: Test module removal cache cleaning and --purge behavior across all five semantic spaces."""
        # 1. Setup mock_lifecycle module with storage, storage.local, config, config.local, and cache
        mod_name = "mock_lifecycle"
        self.installer.engine.act_register(mod_name, "1.0.0", "local")
        vfs.makedirs(f"module://{mod_name}")
        vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0"})
        
        vfs.makedirs(f"storage://{mod_name}")
        vfs.write_text(f"storage://{mod_name}/data.json", '{"state": 1}')
        vfs.makedirs(f"storage.local://{mod_name}")
        vfs.write_text(f"storage.local://{mod_name}/local_state.json", '{"local": 1}')
        vfs.makedirs(f"config://{mod_name}")
        vfs.write_text(f"config://{mod_name}/config.json", '{"enabled": true}')
        vfs.makedirs(f"config.local://{mod_name}")
        vfs.write_text(f"config.local://{mod_name}/config.local.json", '{"secret": "xyz"}')
        vfs.makedirs(f"cache://{mod_name}")
        vfs.write_text(f"cache://{mod_name}/temp.cache", "cache_content")

        # Standard remove: cache deleted, storage, storage.local, config & config.local preserved
        res_std = self.installer.cmd_remove(mod_name, force=True, purge=False)
        self.assertEqual(res_std, 0)
        self.assertFalse(vfs.exists(f"cache://{mod_name}"))
        self.assertTrue(vfs.exists(f"storage://{mod_name}"))
        self.assertTrue(vfs.exists(f"storage.local://{mod_name}"))
        self.assertTrue(vfs.exists(f"config://{mod_name}"))
        self.assertTrue(vfs.exists(f"config.local://{mod_name}"))

        # Re-register and populate for purge test
        self.installer.engine.act_register(mod_name, "1.0.0", "local")
        vfs.makedirs(f"module://{mod_name}")
        vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0"})
        vfs.makedirs(f"cache://{mod_name}")
        vfs.write_text(f"cache://{mod_name}/temp.cache", "cache_content")

        # Purge remove: cache, storage, storage.local, config, config.local all deleted
        res_purge = self.installer.cmd_remove(mod_name, force=True, purge=True)
        self.assertEqual(res_purge, 0)
        self.assertFalse(vfs.exists(f"cache://{mod_name}"))
        self.assertFalse(vfs.exists(f"storage://{mod_name}"))
        self.assertFalse(vfs.exists(f"storage.local://{mod_name}"))
        self.assertFalse(vfs.exists(f"config://{mod_name}"))
        self.assertFalse(vfs.exists(f"config.local://{mod_name}"))
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
        vfs.makedirs(f"module.build://{mod_name}")
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
        vfs.makedirs(f"module://{mod_name}")
        vfs.write_json(f"module://{mod_name}/manifest.json", {
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
        vfs.makedirs(f"module://{mod_name}")
        vfs.write_json(f"module://{mod_name}/manifest.json", {
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
            z_100 = os.path.join(mod_prov_dir, "1.0.0.0.zip")
            with zipfile.ZipFile(z_100, "w") as zf:
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
            z_120 = os.path.join(mod_prov_dir, "1.2.0.0.zip")
            with zipfile.ZipFile(z_120, "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "1.2.0.0", "entry": "scripts/cli.py"}))
                zf.writestr("scripts/cli.py", "def main(): return 0\n")
                zf.writestr("scripts/migrations/1.1.x.py", mig_code)
                zf.writestr("scripts/migrations/1.2.x.py", mig_code)

            # 3. 建立 2.0.0.0.zip (跨 Major 版本，應被 Major Lock 攔截)
            z_200 = os.path.join(mod_prov_dir, "2.0.0.0.zip")
            with zipfile.ZipFile(z_200, "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "2.0.0.0", "entry": "scripts/cli.py"}))
                zf.writestr("scripts/cli.py", "def main(): return 0\n")

            from core.engine import compute_file_sha256
            with open(os.path.join(mod_prov_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "name": mod_name,
                        "latest": "2.0.0.0",
                        "versions": ["1.0.0.0", "1.2.0.0", "2.0.0.0"],
                        "releases": {
                            "1.0.0.0": {"sha256": compute_file_sha256(z_100)},
                            "1.2.0.0": {"sha256": compute_file_sha256(z_120)},
                            "2.0.0.0": {"sha256": compute_file_sha256(z_200)},
                        },
                    },
                    f,
                )

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
                if vfs.exists(f"module.mirror://{mod_name}"):
                    vfs.rmtree(f"module.mirror://{mod_name}")

        self.mark_passed()

    def test_cmd_restore_cross_branch_version_mismatch_and_corrupted_manifest(self):
        """驗證跨分支 cmd_restore (含 yscb.py 與 Installer) 在 installed_ver != ver 或 manifest 損毀時自動覆寫還原。"""
        import io
        import json
        import zipfile
        import tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import yscb
        from core.installer import _notify_server_release_handles

        mod_name = "mock_branch_mod"
        with tempfile.TemporaryDirectory() as prov_dir:
            mod_prov_dir = os.path.join(prov_dir, mod_name)
            os.makedirs(mod_prov_dir, exist_ok=True)

            # 準備 1.0.0.0.zip 與 1.1.0.0.zip
            from core.engine import compute_file_sha256
            rels_info = {}
            for ver_str in ("1.0.0.0", "1.1.0.0"):
                zp = os.path.join(mod_prov_dir, f"{ver_str}.zip")
                with zipfile.ZipFile(zp, "w") as zf:
                    zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": ver_str, "entry": "scripts/cli.py"}))
                    zf.writestr("scripts/cli.py", f"VER = '{ver_str}'\ndef main(): return 0\n")
                rels_info[ver_str] = {"sha256": compute_file_sha256(zp)}
            with open(os.path.join(mod_prov_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump({"name": mod_name, "versions": ["1.0.0.0", "1.1.0.0"], "releases": rels_info}, f)

            cfg_path, orig_cfg = self.installer.engine._get_config()
            orig_installed = dict(orig_cfg.get("installed_modules", {}))
            try:
                # 1. 先將 .modules/mock_branch_mod 設為舊版 1.0.0.0，但 yscb.config.json 目標設為 1.1.0.0 (模擬 git checkout 切換分支)
                vfs.makedirs(f"module://{mod_name}", exist_ok=True)
                vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0.0", "entry": "scripts/cli.py"})
                vfs.write_text(f"module://{mod_name}/scripts/cli.py", "VER = '1.0.0.0'\n")

                orig_cfg.setdefault("installed_modules", {})[mod_name] = {"version": "1.1.0.0", "provider": prov_dir}
                self.installer.engine._save_config(cfg_path, orig_cfg)

                # 執行 cmd_restore (不帶 force)，應偵測 installed_ver (1.0.0.0) != ver (1.1.0.0) 並自動覆寫為 1.1.0.0
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc, 0)
                restored_mf = vfs.read_json(f"module://{mod_name}/manifest.json")
                self.assertEqual(restored_mf.get("version"), "1.1.0.0")

                # 2. 當版本已一致 (1.1.0.0 == 1.1.0.0) 時，再次執行 cmd_restore 應 Skipping
                buf_skip = io.StringIO()
                with redirect_stdout(buf_skip):
                    rc_skip = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc_skip, 0)
                self.assertIn(f"Skipping '{mod_name}@1.1.0.0'", buf_skip.getvalue())

                # 3. EC-01: 當 manifest.json 損毀無法解析 JSON 時，視為版本不符並重新覆寫修復
                vfs.write_text(f"module://{mod_name}/manifest.json", "{corrupted_json")
                buf_corrupt = io.StringIO()
                with redirect_stdout(buf_corrupt):
                    rc_corrupt = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc_corrupt, 0)
                self.assertEqual(vfs.read_json(f"module://{mod_name}/manifest.json").get("version"), "1.1.0.0")

                # 4. 驗證 yscb.py 獨立自舉 cmd_restore 的版本比對行為
                vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0.0"})
                with patch("os.path.isfile", side_effect=lambda p: False if str(p).endswith(os.path.join("core", "scripts", "cli.py")) else os.path.exists(p)):
                    with patch("yscb.load_config", return_value=(cfg_path, orig_cfg)):
                        rc_boot = yscb.cmd_restore([])
                        self.assertEqual(rc_boot, 0)
                self.assertEqual(vfs.read_json(f"module://{mod_name}/manifest.json").get("version"), "1.1.0.0")

                # 5. 驗證 _notify_server_release_handles 在無 Server 或假 daemon.json 下安全容錯
                self.assertFalse(_notify_server_release_handles( prov_dir))
                daemon_dir = os.path.join(prov_dir, ".cache", "server")
                os.makedirs(daemon_dir, exist_ok=True)
                with open(os.path.join(daemon_dir, "daemon.json"), "w", encoding="utf-8") as df:
                    json.dump({"pid": 999999, "port": 65530, "token": "tok"}, df)
                self.assertFalse(_notify_server_release_handles(prov_dir))
            finally:
                orig_cfg["installed_modules"] = orig_installed
                self.installer.engine._save_config(cfg_path, orig_cfg)
                if vfs.exists(f"module://{mod_name}"):
                    vfs.rmtree(f"module://{mod_name}")
                if vfs.exists(f"module.mirror://{mod_name}"):
                    vfs.rmtree(f"module.mirror://{mod_name}")

        self.mark_passed()

    def test_batch_install_atomic_transaction_and_conflict_rollback(self):
        """驗證 cmd_install 支援多模組批次原子交易、單次 reload/pip 同步、混合 @ver 與 --version，以及版本衝突時 All-or-Nothing 回滾。"""
        import io
        import json
        import zipfile
        import tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as prov_dir:
            for m_name, vers, deps_map in (
                ("batch_lib", ["1.0.0.0", "2.0.0.0"], {}),
                ("batch_mid", ["1.0.0.0"], {"batch_lib": ">=1.0.0.0"}),
                ("batch_top", ["1.5.0.0"], {"batch_mid": ">=1.0.0.0"}),
            ):
                m_dir = os.path.join(prov_dir, m_name)
                os.makedirs(m_dir, exist_ok=True)
                from core.engine import compute_file_sha256
                rels_map = {}
                for v in vers:
                    zp = os.path.join(m_dir, f"{v}.zip")
                    with zipfile.ZipFile(zp, "w") as zf:
                        zf.writestr(
                            "manifest.json",
                            json.dumps({"name": m_name, "version": v, "dependencies": deps_map, "entry": "scripts/cli.py"}),
                        )
                        zf.writestr("scripts/cli.py", "def dummy(): return 0\n")
                    rels_map[v] = {"sha256": compute_file_sha256(zp)}
                with open(os.path.join(m_dir, "index.json"), "w", encoding="utf-8") as f:
                    json.dump({"name": m_name, "latest": vers[-1], "versions": vers, "releases": rels_map}, f)

            try:
                # 1. 負向測試：批次內對同一模組指定衝突版本 (batch_lib@1.0.0.0 vs batch_lib@2.0.0.0) 應攔截並回滾
                buf_err = io.StringIO()
                with redirect_stdout(buf_err):
                    rc_conflict = self.installer.cmd_install(
                        ["batch_lib@1.0.0.0", "batch_lib@2.0.0.0"], provider=prov_dir
                    )
                self.assertEqual(rc_conflict, 1)
                self.assertIn("Conflicting version constraints", buf_err.getvalue())
                _, cfg_after_fail = self.installer.engine._get_config()
                self.assertNotIn("batch_lib", cfg_after_fail.get("installed_modules", {}))

                # 2. 正向測試：批次安裝多個模組，且驗證 act_reload 與 sync_pip_dependencies 僅各執行 1 次
                with patch.object(self.installer.engine, "act_reload", wraps=self.installer.engine.act_reload) as spy_reload:
                    with patch.object(self.installer, "sync_pip_dependencies", wraps=self.installer.sync_pip_dependencies) as spy_pip:
                        buf_ok = io.StringIO()
                        with redirect_stdout(buf_ok):
                            rc_ok = self.installer.cmd_install(
                                ["batch_lib@1.0.0.0", "batch_top"],
                                version="1.5.0.0",
                                provider=prov_dir,
                            )
                        self.assertEqual(rc_ok, 0)
                        self.assertEqual(spy_reload.call_count, 1)
                        self.assertEqual(spy_pip.call_count, 1)

                _, cfg_ok = self.installer.engine._get_config()
                inst_mods = cfg_ok.get("installed_modules", {})
                self.assertEqual(inst_mods.get("batch_lib", {}).get("version"), "1.0.0.0")
                self.assertEqual(inst_mods.get("batch_mid", {}).get("version"), "1.0.0.0")
                self.assertEqual(inst_mods.get("batch_top", {}).get("version"), "1.5.0.0")
            finally:
                for m_clean in ("batch_top", "batch_mid", "batch_lib"):
                    self.installer.engine.act_unregister(m_clean)
                    self.installer.engine.act_delete(m_clean, clean_mirror=True, purge=True)
                    if vfs.exists(f"module://{m_clean}"):
                        vfs.rmtree(f"module://{m_clean}")

        self.mark_passed()

    def test_batch_update_and_remove_reverse_deps_exemption(self):
        """驗證 cmd_update 支援多模組批次更新與未安裝模組攔截，以及 cmd_remove 支援多模組逆向依賴聯集豁免與外部依賴阻斷。"""
        import io
        import json
        import zipfile
        import tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as prov_dir:
            for m_name, vers, deps_map in (
                ("up_mod_a", ["1.0.0.0", "1.1.0.0"], {}),
                ("up_mod_b", ["1.0.0.0", "1.2.0.0"], {"up_mod_a": ">=1.0.0.0"}),
                ("up_mod_c", ["1.0.0.0"], {"up_mod_b": ">=1.0.0.0"}),
            ):
                m_dir = os.path.join(prov_dir, m_name)
                os.makedirs(m_dir, exist_ok=True)
                from core.engine import compute_file_sha256
                rels_map = {}
                for v in vers:
                    zp = os.path.join(m_dir, f"{v}.zip")
                    with zipfile.ZipFile(zp, "w") as zf:
                        zf.writestr(
                            "manifest.json",
                            json.dumps({"name": m_name, "version": v, "dependencies": deps_map, "entry": "scripts/cli.py"}),
                        )
                        zf.writestr("scripts/cli.py", "def dummy(): return 0\n")
                    rels_map[v] = {"sha256": compute_file_sha256(zp)}
                with open(os.path.join(m_dir, "index.json"), "w", encoding="utf-8") as f:
                    json.dump({"name": m_name, "latest": vers[-1], "versions": vers, "releases": rels_map}, f)

            try:
                rc_inst = self.installer.cmd_install(
                    ["up_mod_a@1.0.0.0", "up_mod_b@1.0.0.0", "up_mod_c@1.0.0.0"], provider=prov_dir
                )
                self.assertEqual(rc_inst, 0)

                # 1. cmd_update 包含未安裝模組時應報錯返回 1 且不執行部分更新
                buf_up_err = io.StringIO()
                with redirect_stdout(buf_up_err):
                    rc_up_err = self.installer.cmd_update(["up_mod_a", "ghost_uninstalled_mod"], provider=prov_dir)
                self.assertEqual(rc_up_err, 1)
                self.assertIn("not currently installed", buf_up_err.getvalue())
                _, cfg_check = self.installer.engine._get_config()
                self.assertEqual(cfg_check["installed_modules"]["up_mod_a"]["version"], "1.0.0.0")

                # 2. cmd_update 批次更新指定模組 (含重複名稱自動去重)
                buf_up_ok = io.StringIO()
                with redirect_stdout(buf_up_ok):
                    rc_up_ok = self.installer.cmd_update(["up_mod_a", "up_mod_b", "up_mod_a"], provider=prov_dir)
                self.assertEqual(rc_up_ok, 0)
                _, cfg_up = self.installer.engine._get_config()
                self.assertEqual(cfg_up["installed_modules"]["up_mod_a"]["version"], "1.1.0.0")
                self.assertEqual(cfg_up["installed_modules"]["up_mod_b"]["version"], "1.2.0.0")

                # 3. cmd_remove 批次移除 up_mod_a 與 up_mod_b 時，因批次外的 up_mod_c 依賴 up_mod_b，無 --force 應阻斷
                buf_rm_block = io.StringIO()
                with redirect_stdout(buf_rm_block):
                    rc_rm_block = self.installer.cmd_remove(["up_mod_a", "up_mod_b"], force=False)
                self.assertEqual(rc_rm_block, 1)
                self.assertIn("up_mod_c", buf_rm_block.getvalue())

                # 4. cmd_remove 批次包含 core 時應拒絕
                buf_rm_core = io.StringIO()
                with redirect_stdout(buf_rm_core):
                    rc_rm_core = self.installer.cmd_remove(["up_mod_c", "core"], force=True)
                self.assertEqual(rc_rm_core, 1)
                self.assertIn("Cannot remove 'core'", buf_rm_core.getvalue())

                # 5. cmd_remove 將 up_mod_a, up_mod_b, up_mod_c 一併列入批次時，逆向依賴聯集豁免生效，無須 --force 即可一次乾淨移除
                with patch.object(self.installer.engine, "act_reload", wraps=self.installer.engine.act_reload) as spy_rm_reload:
                    buf_rm_ok = io.StringIO()
                    with redirect_stdout(buf_rm_ok):
                        rc_rm_ok = self.installer.cmd_remove(["up_mod_a", "up_mod_b", "up_mod_c"], force=False, purge=True)
                    self.assertEqual(rc_rm_ok, 0)
                    self.assertEqual(spy_rm_reload.call_count, 1)

                _, cfg_final = self.installer.engine._get_config()
                for m_Gone in ("up_mod_a", "up_mod_b", "up_mod_c"):
                    self.assertNotIn(m_Gone, cfg_final.get("installed_modules", {}))
            finally:
                for m_clean in ("up_mod_c", "up_mod_b", "up_mod_a"):
                    self.installer.engine.act_unregister(m_clean)
                    self.installer.engine.act_delete(m_clean, clean_mirror=True, purge=True)
                    if vfs.exists(f"module://{m_clean}"):
                        vfs.rmtree(f"module://{m_clean}")

        self.mark_passed()

    def test_legacy_agent_workflow_provider_url_auto_migration(self):
        """驗證舊倉庫名 ysnaive/agent.workflow 之 legacy provider URL 能於 engine 與 yscb.py 自動正規化至 /releases。"""
        import importlib.util
        from pathlib import Path
        from core.engine import normalize_legacy_provider_url, DEFAULT_PROVIDER_URL

        for legacy_url in (
            "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release",
            "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release/",
            "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
            "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/",
        ):
            self.assertEqual(normalize_legacy_provider_url(legacy_url), DEFAULT_PROVIDER_URL)

        # 驗證自訂網址不受影響
        custom_url = "https://example.com/custom/releases"
        self.assertEqual(normalize_legacy_provider_url(custom_url), custom_url)

        # 驗證 engine._get_config() 自動將 yscb.config.json 中之 agent.workflow 舊網址遷移並回寫
        cfg_path, orig_cfg = self.installer.engine._get_config()
        orig_provider = orig_cfg.get("default_provider")
        try:
            orig_cfg["default_provider"] = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release/"
            self.installer.engine._save_config(cfg_path, orig_cfg)
            _, reloaded_cfg = self.installer.engine._get_config()
            self.assertEqual(reloaded_cfg.get("default_provider"), DEFAULT_PROVIDER_URL)
        finally:
            if orig_provider is not None:
                orig_cfg["default_provider"] = orig_provider
            else:
                orig_cfg.pop("default_provider", None)
            self.installer.engine._save_config(cfg_path, orig_cfg)

        # 驗證根目錄 yscb.py 載入之 LEGACY_PROVIDER_URLS 同步包含舊倉庫名
        root_yscb = Path(__file__).resolve().parents[4] / "yscb.py"
        if root_yscb.is_file():
            spec = importlib.util.spec_from_file_location("yscb_entry_test", str(root_yscb))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(
                mod._normalize_provider_url(
                    "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release"
                ),
                DEFAULT_PROVIDER_URL,
            )

        self.mark_passed()

    def test_transaction_lock_contention_does_not_overwrite_snapshot_or_rollback(self):
        """FR-01, EC-01 (AUD-01): Verify lock timeout in cmd_update/cmd_install does not overwrite snapshot or trigger rollback."""
        from unittest.mock import patch
        from core.vfs.os_backend import OSBackend

        with patch.object(self.installer.engine, "act_lock", side_effect=BlockingIOError("lock held by another process")):
            with patch.object(self.installer.engine, "act_snapshot") as mock_snap, \
                 patch.object(self.installer.engine, "act_restore_snapshot") as mock_restore:
                rc_upd = self.installer.cmd_update("core", provider="local")
                self.assertEqual(rc_upd, 1)
                mock_snap.assert_not_called()
                mock_restore.assert_not_called()

        # Verify EC-03 (AUD-05): OSBackend blocks symlink escape outside boundary root
        sb_sub = os.path.join(self.sandbox_dir, "vfs_boundary_box")
        outside_dir = os.path.join(self.sandbox_dir, "vfs_outside_secret")
        os.makedirs(sb_sub, exist_ok=True)
        os.makedirs(outside_dir, exist_ok=True)
        outside_file = os.path.join(outside_dir, "secret.txt")
        with open(outside_file, "w", encoding="utf-8") as f:
            f.write("secret")
        symlink_path = os.path.join(sb_sub, "escape_link.txt")
        try:
            os.symlink(outside_file, symlink_path)
            has_symlink = True
        except OSError:
            has_symlink = False

        if has_symlink:
            guarded_vfs = OSBackend(root_dir=sb_sub)
            with self.assertRaises(PermissionError):
                guarded_vfs.read_text(symlink_path)
            with self.assertRaises(PermissionError):
                guarded_vfs.exists(symlink_path)

        self.mark_passed()




