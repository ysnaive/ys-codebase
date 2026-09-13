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
        """FT-01: 驗證 DEFAULT_PROVIDER_URL 為官方庫且 _resolve_self_update_target_url 正確錨定 repo 根目錄。"""
        self.assertIn("ysnaive/ys-codebase", yscb.DEFAULT_PROVIDER_URL)

        # 1. 官方 release URL -> repo 根目錄 yscb.py
        target = yscb._resolve_self_update_target_url("https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release")
        self.assertEqual(target, "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py")

        # 2. 任意含 /release 的 Provider URL
        target2 = yscb._resolve_self_update_target_url("https://example.com/repo/release")
        self.assertEqual(target2, "https://example.com/repo/yscb.py")

        # 3. 顯式指定 --url 覆寫
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
        """FT-04: 驗證遠端 Provider index.json 成功解析最新版本，異常時安全兜底。"""
        # 1. 模擬遠端正常返回 index.json
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "name": "core",
            "versions": ["1.0.0.0", "1.1.0.0", "1.1.0.1", "1.2.0.0.build"]
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ver, url = yscb._discover_latest_core("https://remote.test/release")
            self.assertEqual(ver, "1.1.0.1")
            self.assertEqual(url, "https://remote.test/release/core/1.1.0.1.zip")

        # 2. 模擬遠端連線異常時兜底
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            ver_fallback, url_fallback = yscb._discover_latest_core("https://remote.test/release")
            self.assertEqual(ver_fallback, "1.1.0.1")
            self.assertEqual(url_fallback, "https://remote.test/release/core/1.1.0.1.zip")

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

