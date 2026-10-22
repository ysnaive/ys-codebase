"""
Unit tests for modules Git decoupling, restore pipeline, and JIT module synchronization.
Covers FT-01 ~ FT-05, ET-01 ~ ET-02, and PT-01.
"""

import unittest
import tempfile
import os
import shutil
import json
import zipfile
import time
from core import uri
from dev.testing.case import YSCBTestCase
import sys
import importlib.util

# Robustly load yscb host bootstrapper module
_host_d, _ = uri._get_host_config()
_yscb_p = os.path.join(_host_d, "yscb.py")
if not os.path.isfile(_yscb_p):
    _yscb_p = os.path.abspath("yscb.py")
if os.path.isfile(_yscb_p):
    spec = importlib.util.spec_from_file_location("yscb_host", _yscb_p)
    yscb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yscb)
else:
    import yscb


class TestRestoreAndJitModules(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.test_root = tempfile.mkdtemp(prefix="test_jit_modules_")
        self.host_dir = os.path.join(self.test_root, "host")
        self.engine_dir = os.path.join(self.host_dir, "engine")
        os.makedirs(self.host_dir, exist_ok=True)
        os.makedirs(self.engine_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)
        super().tearDown()

    def test_ft_01_gitignore_soft_merge_and_topology_coexistence(self):
        """FT-01: Verify _generate_internal_gitignore performs soft merge and preserves user rules."""
        # 1. New file creation
        gi_path = os.path.join(self.engine_dir, ".gitignore")
        yscb._generate_internal_gitignore(self.engine_dir)
        self.assertTrue(os.path.isfile(gi_path))
        with open(gi_path, "r", encoding="utf-8") as f:
            c1 = f.read()
        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, c1)
        self.assertIn("/.modules/", c1)
        self.assertIn(yscb.INTERNAL_IGNORE_END, c1)

        # 2. Soft merge when yscb:// == project:// (custom user rules + agents-workflow block)
        custom_header = "# Custom User Rules\n*.log\nnode_modules/\n.env\n\n"
        aw_block = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===\n/.agents/temp/\n# === YSCB AGENTS_WORKFLOW IGNORE END ===\n"
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(custom_header + c1 + "\n" + aw_block)

        # Call again
        yscb._generate_internal_gitignore(self.engine_dir)
        with open(gi_path, "r", encoding="utf-8") as f:
            c2 = f.read()

        self.assertIn("# Custom User Rules", c2)
        self.assertIn("node_modules/", c2)
        self.assertIn(".env", c2)
        self.assertIn(aw_block, c2)
        self.assertIn(yscb.INTERNAL_IGNORE_BEGIN, c2)
        self.assertIn("/.modules/", c2)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_BEGIN), 1)
        self.assertEqual(c2.count(yscb.INTERNAL_IGNORE_END), 1)
        self.mark_passed()

    def test_ft_02_semantic_uri_resolution_to_dot_modules(self):
        """FT-02: Verify module:// resolves to yscb://.modules/."""
        mod_root = uri.resolve("module://")
        self.assertTrue(mod_root.endswith(".modules") or mod_root.endswith(f".modules{os.sep}"))

        core_mod = uri.resolve("module://core")
        self.assertTrue(core_mod.endswith(os.path.join(".modules", "core")) or core_mod.endswith(os.path.join(".modules", "core") + os.sep))
        self.mark_passed()

    def test_ft_03_and_04_restore_and_dirty_detection(self):
        """FT-03 & FT-04: Verify _is_modules_dirty and cmd_restore cycle."""
        provider_dir = os.path.join(self.test_root, "provider")
        os.makedirs(provider_dir, exist_ok=True)

        # Create a mock module zip
        mock_mod_name = "testmod"
        mock_ver = "1.0.0"
        pkg_dir = os.path.join(self.test_root, "src_pkg")
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

        # Configure workspace
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
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        # Verify dirty detection before restore
        is_dirty, dirty_mods = yscb._is_modules_dirty(self.host_dir, "engine", installed)
        self.assertTrue(is_dirty)
        self.assertIn(mock_mod_name, dirty_mods)

        # Execute restore
        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 0)
        finally:
            os.chdir(orig_cwd)

        # Verify materialized in .modules
        mat_mf = os.path.join(self.engine_dir, ".modules", mock_mod_name, "manifest.json")
        self.assertTrue(os.path.isfile(mat_mf))
        with open(mat_mf, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["version"], mock_ver)

        # Verify Clean state
        is_dirty_after, _ = yscb._is_modules_dirty(self.host_dir, "engine", installed)
        self.assertFalse(is_dirty_after)
        self.mark_passed()

    def test_et_01_empty_installed_modules_restore(self):
        """ET-01: Verify cmd_restore handles empty installed_modules safely without crashing."""
        cfg_data = {
            "yscb_root": "engine",
            "installed_modules": {}
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 0)
        finally:
            os.chdir(orig_cwd)
        self.mark_passed()

    def test_et_02_corrupted_provider_restore_handling(self):
        """ET-02: Verify restore handles unresolvable provider gracefully."""
        cfg_data = {
            "yscb_root": "engine",
            "installed_modules": {
                "nonexistent": {
                    "version": "9.9.9",
                    "provider": "/invalid/nonexistent/path"
                }
            }
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        orig_cwd = os.getcwd()
        try:
            os.chdir(self.host_dir)
            ret = yscb.cmd_restore([])
            self.assertEqual(ret, 1)
        finally:
            os.chdir(orig_cwd)
        self.mark_passed()

    def test_pt_01_clean_state_jit_sniff_latency(self):
        """PT-01: Benchmark _is_modules_dirty executes in <2ms under clean state."""
        mod_dir = os.path.join(self.engine_dir, ".modules", "mod_perf")
        os.makedirs(mod_dir, exist_ok=True)
        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "mod_perf", "version": "1.0.0"}, f)

        installed = {"mod_perf": {"version": "1.0.0"}}
        
        # Warmup
        yscb._is_modules_dirty(self.host_dir, "engine", installed)

        # 100 runs benchmark
        t0 = time.perf_counter()
        for _ in range(100):
            dirty, _ = yscb._is_modules_dirty(self.host_dir, "engine", installed)
            self.assertFalse(dirty)
        elapsed_avg_ms = ((time.perf_counter() - t0) / 100) * 1000

        self.assertLess(elapsed_avg_ms, 2.0, f"Average JIT sniff took {elapsed_avg_ms:.3f}ms, exceeding 2ms threshold")
        self.mark_passed()

    def test_rev_02_auto_bootstrap_core_and_restore_on_fresh_clone(self):
        """REV-02: 當 yscb.py 與 yscb.config.json 存在但 .modules 尚未下載 (含 core) 時，自適應重下載 core 後觸發 restore 重建運行環境。"""
        from unittest.mock import patch

        provider_dir = os.path.join(self.test_root, "provider")
        os.makedirs(provider_dir, exist_ok=True)

        # 建立 mock core 與 mock appmod 兩個 zip 包於 provider_dir
        for m_name, m_ver in [("core", "1.1.0.6"), ("appmod", "1.0.0.0")]:
            pkg_dir = os.path.join(self.test_root, f"pkg_{m_name}")
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

        installed = {
            "core": {"version": "1.1.0.6", "provider": provider_dir},
            "appmod": {"version": "1.0.0.0", "provider": provider_dir},
        }
        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": installed,
        }
        with open(os.path.join(self.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2)

        # 確認初始狀態下 .modules 完全不存在（模擬剛 clone 到新設備）
        self.assertFalse(os.path.exists(os.path.join(self.engine_dir, ".modules", "core")))
        self.assertFalse(os.path.exists(os.path.join(self.engine_dir, ".modules", "appmod")))

        # 當呼叫 _auto_bootstrap_and_restore_if_needed 時，應先透過純標準庫下載解壓 core，再觸發 restore 還原其餘模組
        def fake_dispatch_restore(mod_name, args):
            self.assertEqual(mod_name, "core")
            self.assertEqual(args, ["restore"])
            # 驗證觸發 restore 時 core 已經被成功自舉解壓至 .modules/core
            self.assertTrue(yscb._is_core_healthy(os.path.join(self.engine_dir, ".modules", "core"))[0])
            # 模擬無 core/scripts/cli.py 時（或攔截遞迴 dispatch_module）直接走完 cmd_restore 內迴圈
            yscb._bootstrap_package_from_provider(
                self.host_dir, "engine", "appmod", "1.0.0.0", provider_dir,
                os.path.join(self.engine_dir, ".modules", "appmod"),
                os.path.join(self.engine_dir, ".mirror", "appmod"),
            )
            return 0

        orig_cwd = os.getcwd()
        orig_host_env = os.environ.get("YSCB_HOST_DIR")
        try:
            os.chdir(self.host_dir)
            with patch.object(yscb, "dispatch_module", side_effect=fake_dispatch_restore) as mock_disp:
                ok = yscb._auto_bootstrap_and_restore_if_needed(self.host_dir, "engine", cfg_data, "status")
                self.assertTrue(ok)
                mock_disp.assert_called_once_with("core", ["restore"])
        finally:
            os.chdir(orig_cwd)
            if orig_host_env is None:
                os.environ.pop("YSCB_HOST_DIR", None)
            else:
                os.environ["YSCB_HOST_DIR"] = orig_host_env

        # 驗證 core 與 appmod 皆已物化完成且狀態為 clean
        self.assertTrue(os.path.isfile(os.path.join(self.engine_dir, ".modules", "core", "manifest.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.engine_dir, ".modules", "appmod", "manifest.json")))
        is_dirty_after, _ = yscb._is_modules_dirty(self.host_dir, "engine", installed)
        self.assertFalse(is_dirty_after)
        self.mark_passed()

    def test_rev_02_missing_source_no_uncontrolled_fallback(self):
        """REV-02: 當組態指定之 version/provider 來源已遺失時，禁止跨版本猜測 fallback，應阻斷並輸出手動修復建議措施。"""
        import io
        from contextlib import redirect_stdout

        provider_dir = os.path.join(self.test_root, "provider_missing")
        os.makedirs(os.path.join(provider_dir, "core"), exist_ok=True)
        # 故意在 provider 放一個不同版本 1.9.9.9.zip，但組態要求 1.1.0.6 -> 嚴禁自動 fallback 去抓 1.9.9.9！
        pkg_dir = os.path.join(self.test_root, "pkg_other_core")
        os.makedirs(os.path.join(pkg_dir, "scripts"), exist_ok=True)
        with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "core", "version": "1.9.9.9", "entry": "scripts/cli.py"}, f)
        with open(os.path.join(pkg_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write("def status(cmd_bags): return 0\n")
        zip_other = os.path.join(provider_dir, "core", "1.9.9.9.zip")
        with zipfile.ZipFile(zip_other, "w") as zf:
            for root, _, files in os.walk(pkg_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    zf.write(full_p, os.path.relpath(full_p, pkg_dir))
        with open(os.path.join(provider_dir, "core", "index.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "core", "versions": ["1.9.9.9"]}, f)

        cfg_data = {
            "yscb_root": "engine",
            "default_provider": provider_dir,
            "installed_modules": {
                "core": {"version": "1.1.0.6", "provider": provider_dir}
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = yscb._auto_bootstrap_and_restore_if_needed(self.host_dir, "engine", cfg_data, "status")

        self.assertFalse(ok)
        out = buf.getvalue()
        self.assertIn("'core' 模組 (v1.1.0.6) 來源", out)
        self.assertIn("已遺失或無法存取，需手動修復", out)
        self.assertIn("建議措施為:", out)
        self.assertIn("python yscb.py init --fix", out)
        self.assertIn("python yscb.py restore --force --provider", out)
        self.mark_passed()

    def test_rev_03_discover_latest_core_no_fake_fallback(self):
        """REV-03: 驗證 _discover_latest_core 於遠端失敗或本地損毀時回傳 (None, None)，嚴禁偽造 1.1.0.1 或 1.0.0.0。"""
        from unittest.mock import patch

        # 1. 遠端失敗時不得回傳 ("1.1.0.1", ...)
        with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            ver, src = yscb._discover_latest_core("https://invalid.example.com/release")
            self.assertIsNone(ver)
            self.assertIsNone(src)

        # 2. 本地目錄 manifest.json 損毀或無 version 欄位時不得偽造 "1.0.0.0"
        broken_prov = os.path.join(self.test_root, "broken_prov")
        os.makedirs(os.path.join(broken_prov, "core"), exist_ok=True)
        with open(os.path.join(broken_prov, "core", "manifest.json"), "w", encoding="utf-8") as f:
            f.write("{invalid json")
        ver2, src2 = yscb._discover_latest_core(broken_prov)
        self.assertIsNone(ver2)
        self.assertIsNone(src2)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
