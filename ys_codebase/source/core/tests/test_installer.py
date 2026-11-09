"""
Official test suite for core.installer.Installer.
"""
import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch

from dev.testing import YSCBTestCase, require, Requirement
from core import uri, vfs
from core.engine import compute_file_sha256, normalize_legacy_provider_url, DEFAULT_PROVIDER_URL
from core.installer import Installer, _notify_server_release_handles, fetch_and_extract_zip
from tests import create_provider_release_zip, load_yscb_host_module
import yscb


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreInstaller(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.installer = Installer()

    def test_status_health_reporting(self):
        """驗證 cmd_status 健全環境回傳 0 且輸出包含 HEALTHY (100% Ready)，異常環境回傳 1 且輸出 Incomplete 與 DEGRADED。"""
        buf_ok = io.StringIO()
        with redirect_stdout(buf_ok):
            res_ok = self.installer.cmd_status()
        self.assertEqual(res_ok, 0)
        self.assertIn("HEALTHY (100% Ready)", buf_ok.getvalue())

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
        """Verify cmd_remove blocks removal when required by other modules, and allows with force."""
        try:
            self.installer.engine.act_register("mock_lib", "1.0.0", "local")
            self.installer.engine.act_register("mock_app", "1.0.0", "local")

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

            res_blocked = self.installer.cmd_remove("mock_lib", force=False)
            self.assertEqual(res_blocked, 1)

            res_forced = self.installer.cmd_remove("mock_lib", force=True)
            self.assertEqual(res_forced, 0)

            self.installer.cmd_remove("mock_app", force=True)
        finally:
            for m in ("mock_lib", "mock_app"):
                self.installer.engine.act_unregister(m)
                if vfs.exists(f"module://{m}"):
                    vfs.rmtree(f"module://{m}", ignore_errors=True)
        self.mark_passed()

    def test_remove_lifecycle_cache_cleaning_and_purge(self):
        """Test module removal cache cleaning and --purge behavior across all five semantic spaces."""
        mod_name = "mock_lifecycle"
        try:
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

            res_std = self.installer.cmd_remove(mod_name, force=True, purge=False)
            self.assertEqual(res_std, 0)
            self.assertFalse(vfs.exists(f"cache://{mod_name}"))
            self.assertTrue(vfs.exists(f"storage://{mod_name}"))
            self.assertTrue(vfs.exists(f"storage.local://{mod_name}"))
            self.assertTrue(vfs.exists(f"config://{mod_name}"))
            self.assertTrue(vfs.exists(f"config.local://{mod_name}"))

            self.installer.engine.act_register(mod_name, "1.0.0", "local")
            vfs.makedirs(f"module://{mod_name}")
            vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0"})
            vfs.makedirs(f"cache://{mod_name}")
            vfs.write_text(f"cache://{mod_name}/temp.cache", "cache_content")

            res_purge = self.installer.cmd_remove(mod_name, force=True, purge=True)
            self.assertEqual(res_purge, 0)
            self.assertFalse(vfs.exists(f"cache://{mod_name}"))
            self.assertFalse(vfs.exists(f"storage://{mod_name}"))
            self.assertFalse(vfs.exists(f"storage.local://{mod_name}"))
            self.assertFalse(vfs.exists(f"config://{mod_name}"))
            self.assertFalse(vfs.exists(f"config.local://{mod_name}"))
        finally:
            self.installer.engine.act_unregister(mod_name)
            self.installer.engine.act_delete(mod_name, clean_mirror=True, purge=True)
            if vfs.exists(f"module://{mod_name}"):
                vfs.rmtree(f"module://{mod_name}", ignore_errors=True)
        self.mark_passed()

    def test_list_installed_modules(self):
        """Verify cmd_list executes successfully."""
        res = self.installer.cmd_list()
        self.assertEqual(res, 0)
        self.mark_passed()

    def test_install_unreleased_module_strict_error(self):
        """Verify unreleased or non-existent module installation is strictly rejected with error."""
        with self.assertRaises(ModuleNotFoundError):
            self.installer.engine._get_module_manifest_from_provider_or_local("non_existent_unreleased_xyz", "local")

        res = self.installer.cmd_install("non_existent_unreleased_xyz")
        self.assertEqual(res, 1)

        _, cfg = self.installer.engine._get_config()
        self.assertNotIn("non_existent_unreleased_xyz", cfg.get("installed_modules", {}))
        self.mark_passed()

    def test_build_package_isolation(self):
        """Verify build packages are isolated and only accessible when explicitly requested."""
        mod_name = "mock_isolated_build_mod"
        try:
            vfs.makedirs(f"module.build://{mod_name}")
            build_zip_path = uri.resolve(f"module.build://{mod_name}/1.0.0.build.zip")
            with zipfile.ZipFile(build_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps({"name": mod_name, "version": "1.0.0.build"}))
                zf.writestr("scripts/cli.py", "print('mock build cli')")

            res_regular = self.installer.cmd_install(mod_name)
            self.assertEqual(res_regular, 1)

            res_build = self.installer.cmd_install(mod_name, version="1.0.0.build")
            self.assertEqual(res_build, 0)

            _, cfg = self.installer.engine._get_config()
            self.assertIn(mod_name, cfg.get("installed_modules", {}))
            self.assertEqual(cfg["installed_modules"][mod_name]["version"], "1.0.0.build")
        finally:
            self.installer.cmd_remove(mod_name, force=True, purge=True)
            for scheme in ("module.build", "module.mirror", "module"):
                if vfs.exists(f"{scheme}://{mod_name}"):
                    vfs.rmtree(f"{scheme}://{mod_name}", ignore_errors=True)
        self.mark_passed()

    def test_optional_dependencies_hint(self):
        """驗證模組宣告 optional 且未安裝時，安裝器提示擴充模組建議與指令。"""
        mod_name = "mock_opt_host"
        try:
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
        finally:
            target_dir = uri.resolve(f"module://{mod_name}")
            if os.path.isdir(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
        self.mark_passed()

    def test_optional_dependencies_already_installed(self):
        """驗證模組宣告 optional 且已安裝時，靜默跳過無提示。"""
        mod_name = "mock_opt_host_installed"
        try:
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
        finally:
            target_dir = uri.resolve(f"module://{mod_name}")
            if os.path.isdir(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
        self.mark_passed()

    def test_update_skips_build_version(self):
        """驗證 cmd_update 自動跳過 @build 開發中版本，防範降級覆蓋。"""
        self.installer.engine.act_register("mock_dev_mod", "1.0.0.build", "local")
        try:
            f_out = io.StringIO()
            with redirect_stdout(f_out):
                res = self.installer.cmd_update("mock_dev_mod")
            out = f_out.getvalue()

            self.assertEqual(res, 0)
            self.assertIn("is a development build", out)
            self.assertIn("skipping update", out)
        finally:
            self.installer.engine.act_unregister("mock_dev_mod")
        self.mark_passed()

    def test_cmd_restore_empty_and_fetch_extract(self):
        """驗證 cmd_restore 無模組需還原時安全返回 0，且 fetch_and_extract_zip 正常解壓。"""
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
            self.assertEqual(vfs.read_text(os.path.join(extract_dest, "test.txt")), "hello yscb")
            self.assertTrue(os.path.isfile(os.path.join(extract_dest, "nested", "foo.json")))
        self.mark_passed()

    def test_cmd_list_remote_and_local(self):
        """驗證 cmd_list 支援 remote 與 local 雙模式查詢及無效 Provider 回傳 1。"""
        buf_local = io.StringIO()
        with redirect_stdout(buf_local):
            ret_loc = self.installer.cmd_list(remote=False)
        self.assertEqual(ret_loc, 0)
        self.assertIn("Module Name", buf_local.getvalue())

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

        buf_remote = io.StringIO()
        with redirect_stdout(buf_remote):
            ret_rem = self.installer.cmd_list(remote=True, provider="/nonexistent/provider")
        self.assertEqual(ret_rem, 1)
        self.assertIn("No remote modules found", buf_remote.getvalue())
        self.mark_passed()

    def test_cmd_update_end_to_end_and_major_lock(self):
        """驗證 cmd_update 端到端升級、Major Lock 跨大版本攔截與增量遷移腳本觸發。"""
        mod_name = "mock_up_mod"
        with tempfile.TemporaryDirectory() as prov_dir:
            mig_code = (
                "import os, json\n"
                "def migrate(ctx):\n"
                "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
                "    p = os.path.join(ctx['storage_dir'], 'up_mig.json')\n"
                "    if os.path.isfile(p):\n"
                "        with open(p, 'r', encoding='utf-8') as f:\n"
                "            arr = json.load(f)\n"
                "    else:\n"
                "        arr = []\n"
                "    arr.append(ctx['target_version'])\n"
                "    with open(p, 'w', encoding='utf-8') as f:\n"
                "        json.dump(arr, f)\n"
                "    return True\n"
            )
            create_provider_release_zip(prov_dir, mod_name, "1.0.0.0")
            create_provider_release_zip(
                prov_dir,
                mod_name,
                "1.2.0.0",
                extra_files={
                    "scripts/migrations/1.1.x.py": mig_code,
                    "scripts/migrations/1.2.x.py": mig_code,
                },
            )
            create_provider_release_zip(prov_dir, mod_name, "2.0.0.0")

            try:
                ret_inst = self.installer.cmd_install(mod_name, version="1.0.0.0", provider=prov_dir)
                self.assertEqual(ret_inst, 0)

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
        mod_name = "mock_branch_mod"
        with tempfile.TemporaryDirectory() as prov_dir:
            for ver_str in ("1.0.0.0", "1.1.0.0"):
                create_provider_release_zip(prov_dir, mod_name, ver_str)

            cfg_path, orig_cfg = self.installer.engine._get_config()
            orig_installed = dict(orig_cfg.get("installed_modules", {}))
            try:
                vfs.makedirs(f"module://{mod_name}", exist_ok=True)
                vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0.0", "entry": "scripts/cli.py"})
                vfs.write_text(f"module://{mod_name}/scripts/cli.py", "VER = '1.0.0.0'\n")

                orig_cfg.setdefault("installed_modules", {})[mod_name] = {"version": "1.1.0.0", "provider": prov_dir}
                self.installer.engine._save_config(cfg_path, orig_cfg)

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc, 0)
                restored_mf = vfs.read_json(f"module://{mod_name}/manifest.json")
                self.assertEqual(restored_mf.get("version"), "1.1.0.0")

                buf_skip = io.StringIO()
                with redirect_stdout(buf_skip):
                    rc_skip = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc_skip, 0)
                self.assertIn(f"Skipping '{mod_name}@1.1.0.0'", buf_skip.getvalue())

                vfs.write_text(f"module://{mod_name}/manifest.json", "{corrupted_json")
                buf_corrupt = io.StringIO()
                with redirect_stdout(buf_corrupt):
                    rc_corrupt = self.installer.cmd_restore(force=False, provider=prov_dir)
                self.assertEqual(rc_corrupt, 0)
                self.assertEqual(vfs.read_json(f"module://{mod_name}/manifest.json").get("version"), "1.1.0.0")

                vfs.write_json(f"module://{mod_name}/manifest.json", {"name": mod_name, "version": "1.0.0.0"})
                with patch("os.path.isfile", side_effect=lambda p: False if str(p).endswith(os.path.join("core", "scripts", "cli.py")) else os.path.exists(p)):
                    with patch("yscb.load_config", return_value=(cfg_path, orig_cfg)):
                        rc_boot = yscb.cmd_restore([])
                        self.assertEqual(rc_boot, 0)
                self.assertEqual(vfs.read_json(f"module://{mod_name}/manifest.json").get("version"), "1.1.0.0")

                self.assertFalse(_notify_server_release_handles(prov_dir))
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
        with tempfile.TemporaryDirectory() as prov_dir:
            for m_name, vers, deps_map in (
                ("batch_lib", ["1.0.0.0", "2.0.0.0"], {}),
                ("batch_mid", ["1.0.0.0"], {"batch_lib": ">=1.0.0.0"}),
                ("batch_top", ["1.5.0.0"], {"batch_mid": ">=1.0.0.0"}),
            ):
                for v in vers:
                    create_provider_release_zip(prov_dir, m_name, v, dependencies=deps_map)

            try:
                buf_err = io.StringIO()
                with redirect_stdout(buf_err):
                    rc_conflict = self.installer.cmd_install(
                        ["batch_lib@1.0.0.0", "batch_lib@2.0.0.0"], provider=prov_dir
                    )
                self.assertEqual(rc_conflict, 1)
                self.assertIn("Conflicting version constraints", buf_err.getvalue())
                _, cfg_after_fail = self.installer.engine._get_config()
                self.assertNotIn("batch_lib", cfg_after_fail.get("installed_modules", {}))

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
        with tempfile.TemporaryDirectory() as prov_dir:
            for m_name, vers, deps_map in (
                ("up_mod_a", ["1.0.0.0", "1.1.0.0"], {}),
                ("up_mod_b", ["1.0.0.0", "1.2.0.0"], {"up_mod_a": ">=1.0.0.0"}),
                ("up_mod_c", ["1.0.0.0"], {"up_mod_b": ">=1.0.0.0"}),
            ):
                for v in vers:
                    create_provider_release_zip(prov_dir, m_name, v, dependencies=deps_map)

            try:
                rc_inst = self.installer.cmd_install(
                    ["up_mod_a@1.0.0.0", "up_mod_b@1.0.0.0", "up_mod_c@1.0.0.0"], provider=prov_dir
                )
                self.assertEqual(rc_inst, 0)

                buf_up_err = io.StringIO()
                with redirect_stdout(buf_up_err):
                    rc_up_err = self.installer.cmd_update(["up_mod_a", "ghost_uninstalled_mod"], provider=prov_dir)
                self.assertEqual(rc_up_err, 1)
                self.assertIn("not currently installed", buf_up_err.getvalue())
                _, cfg_check = self.installer.engine._get_config()
                self.assertEqual(cfg_check["installed_modules"]["up_mod_a"]["version"], "1.0.0.0")

                buf_up_ok = io.StringIO()
                with redirect_stdout(buf_up_ok):
                    rc_up_ok = self.installer.cmd_update(["up_mod_a", "up_mod_b", "up_mod_a"], provider=prov_dir)
                self.assertEqual(rc_up_ok, 0)
                _, cfg_up = self.installer.engine._get_config()
                self.assertEqual(cfg_up["installed_modules"]["up_mod_a"]["version"], "1.1.0.0")
                self.assertEqual(cfg_up["installed_modules"]["up_mod_b"]["version"], "1.2.0.0")

                buf_rm_block = io.StringIO()
                with redirect_stdout(buf_rm_block):
                    rc_rm_block = self.installer.cmd_remove(["up_mod_a", "up_mod_b"], force=False)
                self.assertEqual(rc_rm_block, 1)
                self.assertIn("up_mod_c", buf_rm_block.getvalue())

                buf_rm_core = io.StringIO()
                with redirect_stdout(buf_rm_core):
                    rc_rm_core = self.installer.cmd_remove(["up_mod_c", "core"], force=True)
                self.assertEqual(rc_rm_core, 1)
                self.assertIn("Cannot remove 'core'", buf_rm_core.getvalue())

                with patch.object(self.installer.engine, "act_reload", wraps=self.installer.engine.act_reload) as spy_rm_reload:
                    buf_rm_ok = io.StringIO()
                    with redirect_stdout(buf_rm_ok):
                        rc_rm_ok = self.installer.cmd_remove(["up_mod_a", "up_mod_b", "up_mod_c"], force=False, purge=True)
                    self.assertEqual(rc_rm_ok, 0)
                    self.assertEqual(spy_rm_reload.call_count, 1)

                _, cfg_final = self.installer.engine._get_config()
                for m_gone in ("up_mod_a", "up_mod_b", "up_mod_c"):
                    self.assertNotIn(m_gone, cfg_final.get("installed_modules", {}))
            finally:
                for m_clean in ("up_mod_c", "up_mod_b", "up_mod_a"):
                    self.installer.engine.act_unregister(m_clean)
                    self.installer.engine.act_delete(m_clean, clean_mirror=True, purge=True)
                    if vfs.exists(f"module://{m_clean}"):
                        vfs.rmtree(f"module://{m_clean}")

        self.mark_passed()

    def test_legacy_agent_workflow_provider_url_auto_migration(self):
        """驗證舊倉庫名 ysnaive/agent.workflow 之 legacy provider URL 能於 engine 與 yscb.py 自動正規化至 /releases。"""
        for legacy_url in (
            "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release",
            "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release/",
            "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
            "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/",
        ):
            self.assertEqual(normalize_legacy_provider_url(legacy_url), DEFAULT_PROVIDER_URL)

        custom_url = "https://example.com/custom/releases"
        self.assertEqual(normalize_legacy_provider_url(custom_url), custom_url)

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

        host_mod = load_yscb_host_module("_test_yscb_legacy_url")
        self.assertEqual(
            host_mod._normalize_provider_url(
                "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release"
            ),
            DEFAULT_PROVIDER_URL,
        )

        self.mark_passed()

    def test_transaction_lock_contention_does_not_overwrite_snapshot_or_rollback(self):
        """Verify lock timeout in cmd_update/cmd_install does not overwrite snapshot or trigger rollback."""
        with patch.object(self.installer.engine, "act_lock", side_effect=BlockingIOError("lock held by another process")):
            with patch.object(self.installer.engine, "act_snapshot") as mock_snap, \
                 patch.object(self.installer.engine, "act_restore_snapshot") as mock_restore:
                rc_upd = self.installer.cmd_update("core", provider="local")
                self.assertEqual(rc_upd, 1)
                mock_snap.assert_not_called()
                mock_restore.assert_not_called()

        self.mark_passed()

    def test_rollback_mtime_sorting_and_restore_mirror_before_sha256(self):
        """驗證 cmd_rollback 依 mtime 排序快照、不存在快照回傳 1、事務鎖與 Pip 同步，且 _restore_module_package 先複製至 .mirror 再驗 SHA256。"""
        mod_name = "mock_restore_order_mod"
        ver = "1.0.0.0"
        with tempfile.TemporaryDirectory() as tmp_root:
            rel_root = os.path.join(tmp_root, "release")
            rel_zip_abs = create_provider_release_zip(rel_root, mod_name, ver)
            expected_sha = compute_file_sha256(rel_zip_abs)
            self.assertEqual(len(expected_sha), 64)

            dest_dir = os.path.join(tmp_root, ".modules", mod_name)
            mirror_dir = os.path.join(tmp_root, ".mirror", mod_name)
            mirror_zip_abs = os.path.join(mirror_dir, f"{ver}.zip")

            observed_mirror_exists = []
            orig_verify = self.installer.engine._verify_zip_sha256

            def spy_verify(m_name, v_str, zip_path, prov_arg, ignore_sha256=False):
                observed_mirror_exists.append(os.path.isfile(mirror_zip_abs))
                return orig_verify(m_name, v_str, zip_path, prov_arg, ignore_sha256=ignore_sha256)

            with patch.object(self.installer.engine, "_verify_zip_sha256", side_effect=spy_verify):
                ok = self.installer._restore_module_package(
                    tmp_root, ".", mod_name, ver, rel_root, dest_dir, mirror_dir
                )
            self.assertTrue(ok)
            self.assertEqual(observed_mirror_exists, [True])

            os.remove(mirror_zip_abs)
            with patch.object(self.installer.engine, "_verify_zip_sha256", side_effect=ValueError("SHA256 mismatch")):
                ok_bad = self.installer._restore_module_package(
                    tmp_root, ".", mod_name, ver, rel_root, dest_dir, mirror_dir
                )
            self.assertFalse(ok_bad)
            self.assertFalse(os.path.isfile(mirror_zip_abs))

        # Negative test: nonexistent snapshot returns 1
        self.assertEqual(self.installer.cmd_rollback("nonexistent_snap_id_999"), 1)

        snap_root = uri.resolve("snapshot://")
        snap_lex_high_old = os.path.join(snap_root, "z_older_snap")
        snap_lex_low_new = os.path.join(snap_root, "a_newer_snap")
        try:
            os.makedirs(snap_lex_high_old, exist_ok=True)
            os.makedirs(snap_lex_low_new, exist_ok=True)
            now_ts = time.time()
            os.utime(snap_lex_high_old, (now_ts + 100.0, now_ts + 100.0))
            os.utime(snap_lex_low_new, (now_ts + 200.0, now_ts + 200.0))
            with patch.object(self.installer.engine, "act_restore_snapshot") as mock_restore_snap, \
                 patch.object(self.installer, "sync_pip_dependencies") as mock_sync_pip:
                rc_rb = self.installer.cmd_rollback()
            self.assertEqual(rc_rb, 0)
            mock_restore_snap.assert_called_once_with("a_newer_snap")
            mock_sync_pip.assert_called_once()
        finally:
            for p in (snap_lex_high_old, snap_lex_low_new):
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)

        self.mark_passed()

    def test_remediated_lock_reentrancy_zip_slip_pip_fallback_and_log_rotation(self):
        """
        驗證:
        1. `AtomicEngine.transaction_lock` 跨操作同進程可重入 (`restore` 內嵌 `reload`) 與 `is_transaction_locked`。
        2. `_extract_zip_safely` 阻斷 Zip Slip 路徑穿越 (`../evil.py`)。
        3. `vfs.atomic_swap_directory` 於交換失敗時自動從 `.old` 回滾原目錄。
        4. `core.log._rotate_lines_file` 保留完整檔名後綴 (`.log` vs `.jsonl`) 不發生覆寫衝突。
        5. `PipManager._try_copy_host_pip_to_site_packages` 離線複製宿主 `pip` 套件。
        """
        from pathlib import Path
        from core.platform.lock import is_transaction_locked
        from core.engine import _extract_zip_safely
        from core.log import _rotate_lines_file
        from core.pip_manager import PipManager

        # 1. Cross-operation transaction_lock reentrancy + is_transaction_locked
        host_dir, yscb_dir = uri._get_host_config()
        with self.installer.engine.transaction_lock("restore"):
            self.assertTrue(is_transaction_locked(host_dir, yscb_dir))
            with self.installer.engine.transaction_lock("reload"):
                self.assertTrue(is_transaction_locked(host_dir, yscb_dir))
            self.assertTrue(is_transaction_locked(host_dir, yscb_dir))
        self.assertFalse(is_transaction_locked(host_dir, yscb_dir))

        with tempfile.TemporaryDirectory() as tmp_root:
            # 2. Zip Slip path traversal guard
            bad_zip = os.path.join(tmp_root, "slip.zip")
            extract_dst = os.path.join(tmp_root, "extracted")
            os.makedirs(extract_dst, exist_ok=True)
            with zipfile.ZipFile(bad_zip, "w") as zf:
                zf.writestr("../escaped.txt", "malicious")
            with self.assertRaises(RuntimeError):
                _extract_zip_safely(bad_zip, extract_dst, source_label="slip.zip")
            self.assertFalse(os.path.exists(os.path.join(tmp_root, "escaped.txt")))

            # 3. vfs.atomic_swap_directory rollback on failure
            target_dir = os.path.join(tmp_root, "swap_target")
            staging_dir = os.path.join(tmp_root, "swap_staging")
            os.makedirs(target_dir, exist_ok=True)
            os.makedirs(staging_dir, exist_ok=True)
            with open(os.path.join(target_dir, "keep.txt"), "w", encoding="utf-8") as f:
                f.write("original_data")
            with open(os.path.join(staging_dir, "new.txt"), "w", encoding="utf-8") as f:
                f.write("new_data")

            orig_replace = os.replace
            call_idx = {"n": 0}
            def _fail_second_replace(src, dst):
                call_idx["n"] += 1
                if call_idx["n"] == 2:
                    raise OSError("Simulated swap failure")
                return orig_replace(src, dst)

            with patch("os.replace", side_effect=_fail_second_replace):
                with self.assertRaises(OSError):
                    vfs.atomic_swap_directory(staging_dir, target_dir)
            self.assertTrue(os.path.isfile(os.path.join(target_dir, "keep.txt")))

            # 4. _rotate_lines_file preserves extensions
            log_file = Path(tmp_root) / "core.log"
            jsonl_file = Path(tmp_root) / "core.jsonl"
            log_file.write_text("\n".join(f"line {i}" for i in range(20)) + "\n", encoding="utf-8")
            jsonl_file.write_text("\n".join(f'{{"i": {i}}}' for i in range(20)) + "\n", encoding="utf-8")
            _rotate_lines_file(log_file, 5)
            _rotate_lines_file(jsonl_file, 5, jsonl_only=True)
            self.assertEqual(len(log_file.read_text(encoding="utf-8").splitlines()), 5)
            self.assertEqual(len(jsonl_file.read_text(encoding="utf-8").splitlines()), 5)

            # 5. PipManager._try_copy_host_pip_to_site_packages
            pm = PipManager(yscb_dir=tmp_root)
            fake_site = os.path.join(tmp_root, "fake_site_packages")
            os.makedirs(fake_site, exist_ok=True)
            copied = pm._try_copy_host_pip_to_site_packages(fake_site)
            if copied:
                self.assertTrue(os.path.isfile(os.path.join(fake_site, "pip", "__init__.py")))

        self.mark_passed()

