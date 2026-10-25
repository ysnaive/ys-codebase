"""
Test suite for Host distribution lifecycle, self-update, init --fix self-healing, and gitignore management.
Covers FT-01 ~ FT-08.
"""
import ast
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile

from dev.testing.case import YSCBTestCase
from core.installer import generate_internal_gitignore, INTERNAL_IGNORE_PATTERNS
from core.update_checker import UpdateChecker
from core import uri

# Import host functions from yscb.py
import yscb


class TestDistributionLifecycle(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_resolve_self_update_url(self):
        """FT-01: 驗證 DEFAULT_PROVIDER_URL 與 DEFAULT_SELF_UPDATE_URL 職責分離且優先權正確。"""
        self.assertEqual(yscb.DEFAULT_PROVIDER_URL, "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release")
        self.assertEqual(yscb.DEFAULT_SELF_UPDATE_URL, "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py")

        # 1. 預設返回官方自更新 URL（不因 provider 變更而改變）
        target = yscb._resolve_self_update_target_url()
        self.assertEqual(target, yscb.DEFAULT_SELF_UPDATE_URL)

        target2 = yscb._resolve_self_update_target_url("https://example.com/repo/release")
        self.assertEqual(target2, yscb.DEFAULT_SELF_UPDATE_URL)

        # 2. 顯式指定 custom_url 覆寫
        target3 = yscb._resolve_self_update_target_url("https://ignored.com/release", custom_url="https://custom.com/test_yscb.py")
        self.assertEqual(target3, "https://custom.com/test_yscb.py")

        self.mark_passed()

    def test_cmd_self_update_atomic_replacement(self):
        """FT-02: 驗證 cmd_self_update 語法驗證防護與原子備份替換流程。"""
        dummy_script = os.path.join(self.temp_dir, "yscb.py")
        with open(dummy_script, "w", encoding="utf-8") as f:
            f.write("# Original v1.0\nprint('v1.0')\n")

        # 1. 語法錯誤腳本應被 ast.parse 攔截，原檔案不受破壞
        invalid_script = os.path.join(self.temp_dir, "invalid.py")
        with open(invalid_script, "w", encoding="utf-8") as f:
            f.write("def broken( syntax error here !!!")

        with patch.object(yscb, "__file__", dummy_script):
            ret_fail = yscb.cmd_self_update([f"--url={invalid_script}"])
            self.assertEqual(ret_fail, 1)

            # 原檔案內容未受損
            with open(dummy_script, "r", encoding="utf-8") as f:
                self.assertIn("v1.0", f.read())

            # 2. 合法腳本更新成功，並產生 .bak 備份
            valid_script = os.path.join(self.temp_dir, "valid.py")
            with open(valid_script, "w", encoding="utf-8") as f:
                f.write("# Updated v2.0\nprint('v2.0')\n")

            ret_ok = yscb.cmd_self_update([f"--url={valid_script}"])
            self.assertEqual(ret_ok, 0)

            # 原檔案被替換為 v2.0
            with open(dummy_script, "r", encoding="utf-8") as f:
                self.assertIn("v2.0", f.read())

            # 產生 .bak 備份
            bak_path = dummy_script + ".bak"
            self.assertTrue(os.path.isfile(bak_path))
            with open(bak_path, "r", encoding="utf-8") as f:
                self.assertIn("v1.0", f.read())

        self.mark_passed()

    def test_discover_latest_core_local(self):
        """FT-03: 驗證本地 Provider 包含多版本時正確解析最高 semver 且排除 build 版本。"""
        prov_dir = os.path.join(self.temp_dir, "mock_provider", "core")
        os.makedirs(prov_dir, exist_ok=True)

        # 建立多個 zip 檔案
        for ver in ["1.0.0.0", "1.1.0.0", "1.1.0.1", "1.2.0.0.build"]:
            zip_p = os.path.join(prov_dir, f"{ver}.zip")
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("manifest.json", json.dumps({"name": "core", "version": ver}))

        best_ver, best_path = yscb._discover_latest_core(os.path.join(self.temp_dir, "mock_provider"))
        self.assertEqual(best_ver, "1.1.0.1")
        self.assertTrue(best_path.endswith("1.1.0.1.zip"))
        self.mark_passed()

    def test_discover_latest_core_remote(self):
        """FT-04: 驗證遠端 Provider index.json 成功解析最新版本，異常時不偽造 fallback。"""
        # 1. 模擬遠端正常返回 index.json
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "name": "core",
            "versions": ["1.0.0.0", "1.1.0.0", "1.1.0.1", "1.2.0.0.build"]
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ver, url = yscb._discover_latest_core("https://remote.test/release")
            self.assertEqual(ver, "1.1.0.1")
            self.assertEqual(url, "https://remote.test/release/core/1.1.0.1.zip")

        # 2. 模擬遠端連線異常時回傳 (None, None)，嚴禁硬編碼 "1.1.0.1" fallback
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            ver_fallback, url_fallback = yscb._discover_latest_core("https://remote.test/release")
            self.assertIsNone(ver_fallback)
            self.assertIsNone(url_fallback)

        self.mark_passed()

    def test_cmd_init_default_yscb_root(self):
        """FT-05: 驗證全新 cmd_init 未指定 yscb_root 時預設為 .yscb 且動態解析版本。"""
        # 建立本地 mock provider
        prov_dir = os.path.join(self.temp_dir, "prov", "core")
        os.makedirs(prov_dir, exist_ok=True)
        zip_p = os.path.join(prov_dir, "1.1.0.1.zip")
        with zipfile.ZipFile(zip_p, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "core", "version": "1.1.0.1"}))
            zf.writestr("scripts/cli.py", "# mock core cli\ndef main(): pass\n")

        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret = yscb.cmd_init([f"--provider={os.path.join(self.temp_dir, 'prov')}"])
            self.assertEqual(ret, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        # 驗證 yscb.config.json 存在且預設為 .yscb
        cfg_file = os.path.join(self.temp_dir, "yscb.config.json")
        self.assertTrue(os.path.isfile(cfg_file))
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("yscb_root"), ".yscb")
        self.assertEqual(cfg.get("installed_modules", {}).get("core", {}).get("version"), "1.1.0.1")

        # 驗證解壓至 .yscb/.modules/core
        core_installed = os.path.join(self.temp_dir, ".yscb", ".modules", "core", "manifest.json")
        self.assertTrue(os.path.isfile(core_installed))

        self.mark_passed()

    def test_cmd_init_fix_heals_and_reloads(self):
        """FT-06: 驗證 cmd_init --fix 在 core 缺失或指定 --fix 時自癒修復並連鎖 reload。"""
        prov_dir = os.path.join(self.temp_dir, "prov", "core")
        os.makedirs(prov_dir, exist_ok=True)
        zip_p = os.path.join(prov_dir, "1.1.0.1.zip")
        with zipfile.ZipFile(zip_p, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "core", "version": "1.1.0.1"}))
            zf.writestr("scripts/cli.py", "# mock core\n")

        # 預先建立 yscb.config.json，但故意不建立 .modules/core (模擬損毀)
        cfg_file = os.path.join(self.temp_dir, "yscb.config.json")
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({
                "yscb_root": ".yscb",
                "default_provider": os.path.join(self.temp_dir, "prov"),
                "installed_modules": {}
            }, f)

        # 1. 執行 init --fix 觸發自癒
        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret = yscb.cmd_init(["--fix"])
            self.assertEqual(ret, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        # 驗證 core 模組已被還原
        core_manifest = os.path.join(self.temp_dir, ".yscb", ".modules", "core", "manifest.json")
        self.assertTrue(os.path.isfile(core_manifest))

        # 2. core 完好且未傳入 --fix 時應阻止覆蓋
        ret_block = yscb.cmd_init([])
        self.assertEqual(ret_block, 1)

        # 3. core 完好且傳入 --fix 時，提示已就緒無需修復，不觸發 reload
        with patch("yscb.dispatch_module") as mock_dispatch:
            ret_noop = yscb.cmd_init(["--fix"])
            self.assertEqual(ret_noop, 0)
            mock_dispatch.assert_not_called()

        # 4. core 完好但傳入 --fix --force 時強制修復並連鎖 reload
        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret_force = yscb.cmd_init(["--fix", "--force"])
            self.assertEqual(ret_force, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        self.mark_passed()

    def test_internal_gitignore_includes_bak(self):
        """FT-07: 驗證 generate_internal_gitignore 包含 yscb.py.bak 與 *.bak 且具備冪等性。"""
        self.assertIn("yscb.py.bak", INTERNAL_IGNORE_PATTERNS)
        self.assertIn("*.bak", INTERNAL_IGNORE_PATTERNS)

        gi_file = os.path.join(self.temp_dir, ".gitignore")
        with open(gi_file, "w", encoding="utf-8") as f:
            f.write("# User custom rule\nmy_secret.txt\n")

        generate_internal_gitignore(self.temp_dir)
        with open(gi_file, "r", encoding="utf-8") as f:
            content1 = f.read()

        self.assertIn("my_secret.txt", content1)
        self.assertIn("yscb.py.bak", content1)
        self.assertIn("*.bak", content1)

        # 冪等性驗證
        generate_internal_gitignore(self.temp_dir)
        with open(gi_file, "r", encoding="utf-8") as f:
            content2 = f.read()
        self.assertEqual(content1, content2)

        self.mark_passed()

    def test_update_checker_invalidation(self):
        """FT-08: 驗證 UpdateChecker.invalidate_cache 支援局部與全量清除。"""
        cache_uri = f"cache://core/test_invalidation_{os.getpid()}.json"
        checker = UpdateChecker(cache_uri=cache_uri)

        # 模擬已有的快取數據
        data = {
            "last_checked_at": 1000.0,
            "updates": {
                "core": {"latest_version": "1.1.0.1"},
                "dev": {"latest_version": "1.1.0.0"}
            }
        }
        uri.makedirs("cache://core", exist_ok=True)
        uri.write_json(cache_uri, data)

        # 1. 局部清除 core
        checker.invalidate_cache("core")
        cached1 = checker._load_cache()
        self.assertNotIn("core", cached1.get("updates", {}))
        self.assertIn("dev", cached1.get("updates", {}))

        # 2. 全量清除
        checker.invalidate_cache(None)
        cached2 = checker._load_cache()
        self.assertEqual(cached2.get("updates", {}), {})
        self.assertEqual(cached2.get("last_checked_at"), 0.0)

        self.mark_passed()

    def test_init_and_self_update_help(self):
        """FT-09: 驗證自舉指令 init 與 self-update 支援 -h/--help 獨立幫助渲染（不經 core 轉發）。"""
        import io
        from contextlib import redirect_stdout

        # 1. yscb.py init -h / --help
        f1 = io.StringIO()
        with redirect_stdout(f1):
            ret1 = yscb.cmd_init(["-h"])
        self.assertEqual(ret1, 0)
        self.assertIn("Command: python yscb.py init", f1.getvalue())
        self.assertIn("--fix", f1.getvalue())

        # 2. yscb.py self-update -h / --help
        f2 = io.StringIO()
        with redirect_stdout(f2):
            ret2 = yscb.cmd_self_update(["--help"])
        self.assertEqual(ret2, 0)
        self.assertIn("Command: python yscb.py self-update", f2.getvalue())

        # 3. 驗證 core 前綴不包含 init 與 self-update (非 core 模組命令)
        ret3 = yscb.main(["core", "init", "--help"])
        self.assertEqual(ret3, 1)

        ret4 = yscb.main(["core", "self-update", "--help"])
        self.assertEqual(ret4, 1)

        self.mark_passed()

    def test_restore_and_dirty_detection_cycle(self):
        """FT-03 & FT-04: 驗證 _is_modules_dirty 與 cmd_restore 週期。"""
        provider_dir = os.path.join(self.temp_dir, "provider")
        os.makedirs(provider_dir, exist_ok=True)

        mock_mod_name = "testmod"
        mock_ver = "1.0.0"
        pkg_dir = os.path.join(self.temp_dir, "src_pkg")
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": mock_mod_name, "version": mock_ver}, f)
        os.makedirs(os.path.join(pkg_dir, "scripts"), exist_ok=True)
        with open(os.path.join(pkg_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        mod_prov_dir = os.path.join(provider_dir, mock_mod_name)
        os.makedirs(mod_prov_dir, exist_ok=True)
        zip_p = os.path.join(mod_prov_dir, f"{mock_ver}.zip")
        with zipfile.ZipFile(zip_p, "w") as zf:
            for root, _, files in os.walk(pkg_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    arcname = os.path.relpath(full_p, pkg_dir)
                    zf.write(full_p, arcname)

        host_dir = os.path.join(self.temp_dir, "host")
        engine_dir = os.path.join(host_dir, "engine")
        os.makedirs(host_dir, exist_ok=True)
        os.makedirs(engine_dir, exist_ok=True)

        installed = {
            mock_mod_name: {
                "version": mock_ver,
                "provider": provider_dir
            }
        }
        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": installed
        }
        with open(os.path.join(host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        is_dirty, dirty_mods = yscb._is_modules_dirty(host_dir, "engine", installed)
        self.assertTrue(is_dirty)
        self.assertIn(mock_mod_name, dirty_mods)

        orig_cwd = os.getcwd()
        try:
            os.chdir(host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 0)
        finally:
            os.chdir(orig_cwd)

        mat_mf = os.path.join(engine_dir, ".modules", mock_mod_name, "manifest.json")
        self.assertTrue(os.path.isfile(mat_mf))

        is_dirty_after, _ = yscb._is_modules_dirty(host_dir, "engine", installed)
        self.assertFalse(is_dirty_after)
        self.mark_passed()

    def test_rev_02_auto_bootstrap_core_and_restore_on_fresh_clone(self):
        """REV-02: 當 yscb.py 與 yscb.config.json 存在但 .modules 尚未下載時，自適應重下載 core 後觸發 restore。"""
        provider_dir = os.path.join(self.temp_dir, "provider_clone")
        os.makedirs(provider_dir, exist_ok=True)

        for m_name, m_ver in [("core", "1.1.0.6"), ("appmod", "1.0.0.0")]:
            pkg_dir = os.path.join(self.temp_dir, f"pkg_{m_name}")
            os.makedirs(os.path.join(pkg_dir, "scripts"), exist_ok=True)
            with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": m_name, "version": m_ver, "entry": "scripts/cli.py"}, f)
            with open(os.path.join(pkg_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write("def status(cmd_bags): return 0\n")

            mod_prov_dir = os.path.join(provider_dir, m_name)
            os.makedirs(mod_prov_dir, exist_ok=True)
            zip_p = os.path.join(mod_prov_dir, f"{m_ver}.zip")
            with zipfile.ZipFile(zip_p, "w") as zf:
                for root, _, files in os.walk(pkg_dir):
                    for file in files:
                        full_p = os.path.join(root, file)
                        zf.write(full_p, os.path.relpath(full_p, pkg_dir))
            with open(os.path.join(mod_prov_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump({"name": m_name, "versions": [m_ver]}, f)

        host_dir = os.path.join(self.temp_dir, "host_fresh")
        engine_dir = os.path.join(host_dir, "engine")
        os.makedirs(host_dir, exist_ok=True)
        os.makedirs(engine_dir, exist_ok=True)

        installed = {
            "core": {"version": "1.1.0.6", "provider": provider_dir},
            "appmod": {"version": "1.0.0.0", "provider": provider_dir},
        }
        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": installed,
        }
        with open(os.path.join(host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        def fake_dispatch_restore(mod_name, args):
            self.assertEqual(mod_name, "core")
            self.assertEqual(args, ["restore"])
            yscb._bootstrap_package_from_provider(
                host_dir, "engine", "appmod", "1.0.0.0", provider_dir,
                os.path.join(engine_dir, ".modules", "appmod"),
                os.path.join(engine_dir, ".mirror", "appmod"),
            )
            return 0

        orig_cwd = os.getcwd()
        try:
            os.chdir(host_dir)
            with patch.object(yscb, "dispatch_module", side_effect=fake_dispatch_restore):
                ok = yscb._auto_bootstrap_and_restore_if_needed(host_dir, "engine", cfg_data, "status")
                self.assertTrue(ok)
        finally:
            os.chdir(orig_cwd)

        self.assertTrue(os.path.isfile(os.path.join(engine_dir, ".modules", "core", "manifest.json")))
        self.assertTrue(os.path.isfile(os.path.join(engine_dir, ".modules", "appmod", "manifest.json")))
        self.mark_passed()

    def test_rev_02_missing_source_no_uncontrolled_fallback(self):
        """REV-02: 當組態指定之 version/provider 來源已遺失時，禁止跨版本猜測 fallback，應阻斷並輸出手動修復建議。"""
        import io
        from contextlib import redirect_stdout

        provider_dir = os.path.join(self.temp_dir, "provider_missing")
        os.makedirs(os.path.join(provider_dir, "core"), exist_ok=True)
        host_dir = os.path.join(self.temp_dir, "host_missing")
        engine_dir = os.path.join(host_dir, "engine")
        os.makedirs(host_dir, exist_ok=True)
        os.makedirs(engine_dir, exist_ok=True)

        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": {
                "core": {"version": "1.1.0.6", "provider": provider_dir}
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = yscb._auto_bootstrap_and_restore_if_needed(host_dir, "engine", cfg_data, "status")

        self.assertFalse(ok)
        out = buf.getvalue()
        self.assertIn("'core' 模組 (v1.1.0.6) 來源", out)
        self.mark_passed()


    def test_restore_prioritizes_dot_build_and_jit_lifecycle(self):
        """FT-04, FT-05: 驗證 _restore_module_package 優先取用 .build/ 產物，且 Fresh Clone 與 Dirty 狀態精準判讀。"""
        mock_yscb = os.path.join(self.temp_dir, "host_yscb")
        dot_bld = os.path.join(mock_yscb, ".build", "test_mod")
        dest_dir = os.path.join(mock_yscb, ".modules", "test_mod")
        mirror_dir = os.path.join(mock_yscb, ".mirror", "test_mod")

        os.makedirs(dot_bld, exist_ok=True)
        dot_zip = os.path.join(dot_bld, "1.0.0.build.zip")
        with zipfile.ZipFile(dot_zip, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "test_mod", "version": "1.0.0.build"}))
            zf.writestr("marker.txt", "from_dot_build")

        ok = yscb._restore_module_package(
            module_name="test_mod",
            version="1.0.0.build",
            provider_arg="none",
            base_dir=self.temp_dir,
            yscb_root="host_yscb",
            dest_dir=dest_dir,
            mirror_dir=mirror_dir
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "marker.txt")))
        with open(os.path.join(dest_dir, "marker.txt"), "r", encoding="utf-8") as f:
            content = f.read().strip()
        self.assertEqual(content, "from_dot_build")
        self.mark_passed()


