"""
Test suite for Host distribution lifecycle, self-update, init --fix self-healing, and gitignore management.
"""
import io
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from core.commands import dispatcher
from core.engine import AtomicEngine
from core.installer import Installer, generate_internal_gitignore, INTERNAL_IGNORE_PATTERNS
from core.update_checker import UpdateChecker
from core import uri, vfs
from tests import create_provider_release_zip
import yscb


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
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
        """驗證 DEFAULT_PROVIDER_URL 與 DEFAULT_SELF_UPDATE_URL 職責分離且優先權正確。"""
        self.assertEqual(yscb.DEFAULT_PROVIDER_URL, "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases")
        self.assertEqual(yscb.DEFAULT_SELF_UPDATE_URL, "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py")

        target = yscb._resolve_self_update_target_url()
        self.assertEqual(target, yscb.DEFAULT_SELF_UPDATE_URL)

        target2 = yscb._resolve_self_update_target_url("https://example.com/repo/release")
        self.assertEqual(target2, yscb.DEFAULT_SELF_UPDATE_URL)

        target3 = yscb._resolve_self_update_target_url("https://ignored.com/release", custom_url="https://custom.com/test_yscb.py")
        self.assertEqual(target3, "https://custom.com/test_yscb.py")

        self.mark_passed()

    def test_cmd_self_update_atomic_replacement(self):
        """驗證 cmd_self_update 語法驗證防護與原子備份替換流程。"""
        dummy_script = os.path.join(self.temp_dir, "yscb.py")
        with open(dummy_script, "w", encoding="utf-8") as f:
            f.write("# Original v1.0\nprint('v1.0')\n")

        invalid_script = os.path.join(self.temp_dir, "invalid.py")
        with open(invalid_script, "w", encoding="utf-8") as f:
            f.write("def broken( syntax error here !!!")

        with patch.object(yscb, "__file__", dummy_script):
            ret_fail = yscb.cmd_self_update([f"--url={invalid_script}"])
            self.assertEqual(ret_fail, 1)

            with open(dummy_script, "r", encoding="utf-8") as f:
                self.assertIn("v1.0", f.read())

            valid_script = os.path.join(self.temp_dir, "valid.py")
            with open(valid_script, "w", encoding="utf-8") as f:
                f.write("# Updated v2.0\n__version__ = '2.0.0.0'\ndef main():\n    print('v2.0')\n    return 0\n")

            ret_ok = yscb.cmd_self_update([f"--url={valid_script}"])
            self.assertEqual(ret_ok, 0)

            with open(dummy_script, "r", encoding="utf-8") as f:
                self.assertIn("v2.0", f.read())

            bak_path = dummy_script + ".bak"
            self.assertTrue(os.path.isfile(bak_path))
            with open(bak_path, "r", encoding="utf-8") as f:
                self.assertIn("v1.0", f.read())

            no_entry_script = os.path.join(self.temp_dir, "no_entry.py")
            with open(no_entry_script, "w", encoding="utf-8") as f:
                f.write("x = 42\n")
            self.assertEqual(yscb.cmd_self_update([f"--url={no_entry_script}"]), 1)

            self.assertEqual(yscb.cmd_self_update([f"--url={valid_script}", f"--sha256={'a' * 64}"]), 1)
            expected_valid_sha = yscb._compute_file_sha256(valid_script)
            self.assertEqual(yscb.cmd_self_update([f"--url={valid_script}", f"--sha256={expected_valid_sha}"]), 0)

            with open(valid_script + ".sha256", "w", encoding="utf-8") as f:
                f.write(f"{'b' * 64}  yscb.py\n")
            self.assertEqual(yscb.cmd_self_update([f"--url={valid_script}"]), 1)
            self.assertEqual(yscb.cmd_self_update([f"--url={valid_script}", "--ignore-sha256"]), 0)

        self.mark_passed()

    def test_discover_latest_core_local(self):
        """驗證本地 Provider 包含多版本時正確解析最高 semver 且排除 build 版本。"""
        prov_root = os.path.join(self.temp_dir, "mock_provider")
        for ver in ["1.0.0.0", "1.1.0.0", "1.1.0.1", "1.2.0.0.build"]:
            create_provider_release_zip(prov_root, "core", ver, write_index=False)

        best_ver, best_path = yscb._discover_latest_core(prov_root)
        self.assertEqual(best_ver, "1.1.0.1")
        self.assertTrue(best_path.endswith("1.1.0.1.zip"))
        self.mark_passed()

    def test_discover_latest_core_remote(self):
        """驗證遠端 Provider index.json 成功解析最新版本，異常時不偽造 fallback。"""
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

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            ver_fallback, url_fallback = yscb._discover_latest_core("https://remote.test/release")
            self.assertIsNone(ver_fallback)
            self.assertIsNone(url_fallback)

        self.mark_passed()

    def test_cmd_init_default_yscb_root(self):
        """驗證全新 cmd_init 未指定 yscb_root 時預設為 .yscb 且動態解析版本。"""
        prov_root = os.path.join(self.temp_dir, "prov")
        create_provider_release_zip(prov_root, "core", "1.1.0.1")

        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret = yscb.cmd_init([f"--provider={prov_root}"])
            self.assertEqual(ret, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        cfg_file = os.path.join(self.temp_dir, "yscb.config.json")
        self.assertTrue(os.path.isfile(cfg_file))
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("yscb_root"), ".yscb")
        self.assertEqual(cfg.get("installed_modules", {}).get("core", {}).get("version"), "1.1.0.1")

        core_installed = os.path.join(self.temp_dir, ".yscb", ".modules", "core", "manifest.json")
        self.assertTrue(os.path.isfile(core_installed))

        self.mark_passed()

    def test_cmd_init_fix_heals_and_reloads(self):
        """驗證 cmd_init --fix 在 core 缺失或指定 --fix 時自癒修復並連鎖 reload。"""
        prov_root = os.path.join(self.temp_dir, "prov")
        create_provider_release_zip(prov_root, "core", "1.1.0.1")

        cfg_file = os.path.join(self.temp_dir, "yscb.config.json")
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({
                "yscb_root": ".yscb",
                "default_provider": prov_root,
                "installed_modules": {}
            }, f)

        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret = yscb.cmd_init(["--fix"])
            self.assertEqual(ret, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        core_manifest = os.path.join(self.temp_dir, ".yscb", ".modules", "core", "manifest.json")
        self.assertTrue(os.path.isfile(core_manifest))

        ret_block = yscb.cmd_init([])
        self.assertEqual(ret_block, 1)

        with patch("yscb.dispatch_module") as mock_dispatch:
            ret_noop = yscb.cmd_init(["--fix"])
            self.assertEqual(ret_noop, 0)
            mock_dispatch.assert_not_called()

        with patch("yscb.dispatch_module", return_value=0) as mock_dispatch:
            ret_force = yscb.cmd_init(["--fix", "--force"])
            self.assertEqual(ret_force, 0)
            mock_dispatch.assert_called_once_with("core", ["reload"])

        self.mark_passed()

    def test_internal_gitignore_includes_bak(self):
        """驗證 generate_internal_gitignore 包含 yscb.py.bak 與 *.bak 且具備冪等性。"""
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

        generate_internal_gitignore(self.temp_dir)
        with open(gi_file, "r", encoding="utf-8") as f:
            content2 = f.read()
        self.assertEqual(content1, content2)

        self.mark_passed()

    def test_update_checker_invalidation(self):
        """驗證 UpdateChecker.invalidate_cache 支援局部與全量清除。"""
        cache_uri = f"cache://core/test_invalidation_{os.getpid()}.json"
        checker = UpdateChecker(cache_uri=cache_uri)

        data = {
            "last_checked_at": 1000.0,
            "updates": {
                "core": {"latest_version": "1.1.0.1"},
                "dev": {"latest_version": "1.1.0.0"}
            }
        }
        try:
            vfs.makedirs("cache://core", exist_ok=True)
            vfs.write_json(cache_uri, data)

            checker.invalidate_cache("core")
            cached1 = checker._load_cache()
            self.assertNotIn("core", cached1.get("updates", {}))
            self.assertIn("dev", cached1.get("updates", {}))

            checker.invalidate_cache(None)
            cached2 = checker._load_cache()
            self.assertEqual(cached2.get("updates", {}), {})
            self.assertEqual(cached2.get("last_checked_at"), 0.0)
        finally:
            vfs.remove(cache_uri, missing_ok=True)

        self.mark_passed()

    def test_init_and_self_update_help(self):
        """驗證自舉指令 init 與 self-update 支援 -h/--help 獨立幫助渲染（不經 core 轉發）。"""
        f1 = io.StringIO()
        with redirect_stdout(f1):
            ret1 = yscb.cmd_init(["-h"])
        self.assertEqual(ret1, 0)
        self.assertIn("Command: python yscb.py init", f1.getvalue())
        self.assertIn("--fix", f1.getvalue())

        f2 = io.StringIO()
        with redirect_stdout(f2):
            ret2 = yscb.cmd_self_update(["--help"])
        self.assertEqual(ret2, 0)
        self.assertIn("Command: python yscb.py self-update", f2.getvalue())

        ret3 = yscb.main(["core", "init", "--help"])
        self.assertEqual(ret3, 1)

        ret4 = yscb.main(["core", "self-update", "--help"])
        self.assertEqual(ret4, 1)

        self.mark_passed()

    def test_restore_and_dirty_detection_cycle(self):
        """驗證 _is_modules_dirty 與 cmd_restore 週期。"""
        provider_dir = os.path.join(self.temp_dir, "provider")
        mock_mod_name = "testmod"
        mock_ver = "1.0.0"
        create_provider_release_zip(provider_dir, mock_mod_name, mock_ver)

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

    def test_auto_bootstrap_core_and_restore_on_fresh_clone(self):
        """驗證當 yscb.py 與 yscb.config.json 存在但 .modules 尚未下載時，自適應重下載 core 後觸發 restore。"""
        provider_dir = os.path.join(self.temp_dir, "provider_clone")
        for m_name, m_ver in [("core", "1.1.0.6"), ("appmod", "1.0.0.0")]:
            create_provider_release_zip(
                provider_dir,
                m_name,
                m_ver,
                extra_files={"scripts/cli.py": "def status(cmd_bags): return 0\n"},
            )

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

    def test_missing_source_no_uncontrolled_fallback(self):
        """驗證當組態指定之 version/provider 來源已遺失時，禁止跨版本猜測 fallback，應阻斷並輸出手動修復建議。"""
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
        """驗證 _restore_module_package 優先取用 .build/ 產物，且 Fresh Clone 與 Dirty 狀態精準判讀。"""
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

    def test_lifecycle_mutation_commands_skip_auto_spawn_server(self):
        """驗證執行 core 生命週期變異指令 (如 update/install/reload) 時不觸發 _maybe_auto_spawn_server。"""
        self.assertIn("update", dispatcher._LIFECYCLE_MUTATION_COMMANDS)
        self.assertIn("install", dispatcher._LIFECYCLE_MUTATION_COMMANDS)
        self.assertIn("reload", dispatcher._LIFECYCLE_MUTATION_COMMANDS)
        self.assertIn("restore", dispatcher._LIFECYCLE_MUTATION_COMMANDS)

        with patch.object(dispatcher, "_maybe_auto_spawn_server") as mock_spawn, \
             patch.object(dispatcher, "dispatch_local", return_value=0), \
             patch.object(dispatcher, "_maybe_check_and_print_updates"):
            rc = dispatcher.dispatch(["update"])
            self.assertEqual(rc, 0)
            mock_spawn.assert_not_called()

        self.mark_passed()

    def test_legacy_provider_url_auto_migration_and_pruned_same_triplet_fallback(self):
        """驗證舊版 main 分支 Provider URL 自動無感遷移至 releases，且 pruned 版本於無 mirror 時自動退回同三元組最高 active 版本。"""
        provider_dir = os.path.join(self.temp_dir, "provider_window")
        rel_root = os.path.join(provider_dir, "release")
        zip_4 = create_provider_release_zip(rel_root, "appmod", "1.0.0.4", write_index=False)

        mod_rel_dir = os.path.join(rel_root, "appmod")
        with open(os.path.join(mod_rel_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "appmod",
                    "versions": ["1.0.0.2", "1.0.0.3", "1.0.0.4"],
                    "releases": {
                        "1.0.0.1": {"status": "pruned", "dependencies": {}},
                        "1.0.0.4": {
                            "status": "active",
                            "dependencies": {},
                            "sha256": yscb._compute_file_sha256(zip_4),
                        },
                    },
                },
                f,
            )

        host_dir = os.path.join(self.temp_dir, "host_pruned")
        os.makedirs(host_dir, exist_ok=True)
        cfg_file = os.path.join(host_dir, "yscb.config.json")
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "yscb_root": ".yscb",
                    "default_provider": "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
                    "installed_modules": {
                        "appmod": {"version": "1.0.0.1", "provider": provider_dir},
                    },
                },
                f,
            )

        _, loaded_cfg = yscb.load_config(host_dir)
        self.assertEqual(loaded_cfg["default_provider"], yscb.DEFAULT_PROVIDER_URL)

        dest_dir = os.path.join(host_dir, ".yscb", ".modules", "appmod")
        mirror_dir = os.path.join(host_dir, ".yscb", ".mirror", "appmod")
        ok = yscb._bootstrap_package_from_provider(
            host_dir, ".yscb", "appmod", "1.0.0.1", provider_dir, dest_dir, mirror_dir
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "manifest.json")))
        with open(os.path.join(dest_dir, "manifest.json"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], "1.0.0.4")
        with open(cfg_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["installed_modules"]["appmod"]["version"], "1.0.0.4")

        dest_cross = os.path.join(host_dir, ".yscb", ".modules", "appmod_cross")
        mirror_cross = os.path.join(host_dir, ".yscb", ".mirror", "appmod_cross")
        ok_cross = yscb._bootstrap_package_from_provider(
            host_dir, ".yscb", "appmod", "0.9.0.1", provider_dir, dest_cross, mirror_cross
        )
        self.assertFalse(ok_cross)

        inst = Installer()
        dest_inst = os.path.join(host_dir, ".yscb", ".modules", "appmod_inst")
        mirror_inst = os.path.join(host_dir, ".yscb", ".mirror", "appmod_inst")
        self.assertFalse(
            inst._restore_module_package(host_dir, ".yscb", "appmod", "0.9.0.1", provider_dir, dest_inst, mirror_inst)
        )
        self.assertTrue(
            inst._restore_module_package(host_dir, ".yscb", "appmod", "1.0.0.1", provider_dir, dest_inst, mirror_inst)
        )
        with open(os.path.join(dest_inst, "manifest.json"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], "1.0.0.4")

        self.mark_passed()

    def test_exact_version_local_source_dynamic_packaging(self):
        """驗證本地無 .zip 但 source/<mod>/manifest.json 版本嚴格相等時動態打包（排除 tests/），版本不符則拒絕。"""
        ws_dir = os.path.join(self.temp_dir, "ws_source_pkg")
        src_mod = os.path.join(ws_dir, "ys_codebase", "source", "mymod")
        rel_mod = os.path.join(ws_dir, "ys_codebase", "release", "mymod")
        os.makedirs(os.path.join(src_mod, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(src_mod, "tests"), exist_ok=True)
        os.makedirs(rel_mod, exist_ok=True)

        with open(os.path.join(src_mod, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "mymod", "version": "1.2.0.0", "entry": "scripts/cli.py"}, f)
        with open(os.path.join(src_mod, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write("def main(): return 0\n")
        with open(os.path.join(src_mod, "tests", "test_dummy.py"), "w", encoding="utf-8") as f:
            f.write("pass\n")
        with open(os.path.join(rel_mod, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "mymod", "versions": ["1.2.0.0"]}, f)

        dest_dir = os.path.join(ws_dir, "ys_codebase", ".modules", "mymod")
        mirror_dir = os.path.join(ws_dir, "ys_codebase", ".mirror", "mymod")

        ok_mismatch = yscb._bootstrap_package_from_provider(
            ws_dir, "ys_codebase", "mymod", "1.1.0.0", rel_mod, dest_dir, mirror_dir
        )
        self.assertFalse(ok_mismatch)

        ok_match = yscb._bootstrap_package_from_provider(
            ws_dir, "ys_codebase", "mymod", "1.2.0.0", rel_mod, dest_dir, mirror_dir
        )
        self.assertTrue(ok_match)
        self.assertTrue(os.path.isfile(os.path.join(mirror_dir, "1.2.0.0.zip")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "manifest.json")))
        self.assertFalse(os.path.exists(os.path.join(dest_dir, "tests")))

        inst = Installer()
        dest_core_inst = os.path.join(ws_dir, "ys_codebase", ".modules", "mymod_inst")
        mirror_core_inst = os.path.join(ws_dir, "ys_codebase", ".mirror", "mymod_inst")
        if os.path.isfile(os.path.join(rel_mod, "1.2.0.0.zip")):
            os.remove(os.path.join(rel_mod, "1.2.0.0.zip"))
        self.assertFalse(
            inst._restore_module_package(ws_dir, "ys_codebase", "mymod", "1.1.0.0", rel_mod, dest_core_inst, mirror_core_inst)
        )
        self.assertTrue(
            inst._restore_module_package(ws_dir, "ys_codebase", "mymod", "1.2.0.0", rel_mod, dest_core_inst, mirror_core_inst)
        )
        self.assertTrue(os.path.isfile(os.path.join(mirror_core_inst, "1.2.0.0.zip")))
        self.assertFalse(os.path.exists(os.path.join(dest_core_inst, "tests")))

        dest_bld_inst = os.path.join(ws_dir, "ys_codebase", ".modules", "mymod_bld")
        mirror_bld_inst = os.path.join(ws_dir, "ys_codebase", ".mirror", "mymod_bld")
        self.assertFalse(
            inst._restore_module_package(ws_dir, "ys_codebase", "mymod", "1.1.0.build", rel_mod, dest_bld_inst, mirror_bld_inst)
        )
        self.assertTrue(
            inst._restore_module_package(ws_dir, "ys_codebase", "mymod", "1.2.0.build", rel_mod, dest_bld_inst, mirror_bld_inst)
        )
        self.assertTrue(os.path.isfile(os.path.join(mirror_bld_inst, "1.2.0.build.zip")))
        self.assertFalse(os.path.isfile(os.path.join(rel_mod, "1.2.0.build.zip")))

        self.mark_passed()

    def test_release_index_dependency_override_core_compat_and_offline_mirror_reload(self):
        """驗證 index.json['releases'] 依賴覆寫優先級、act_solve_deps 對 core 依賴檢核，以及 mirror:// 離線 reload 覆寫。"""
        engine = AtomicEngine()
        prov_dir = os.path.join(self.temp_dir, "prov_compat")
        create_provider_release_zip(
            prov_dir,
            "compat_mod",
            "1.0.0.0",
            dependencies={"core": ">=1.0.0"},
            release_meta={
                "status": "active",
                "dependencies": {"core": ">=1.0.0,<50.0.0"},
                "type": "bugfix",
                "urgency": "recommended",
                "summary": "相容修補版",
            },
            entry="cli.py",
        )
        create_provider_release_zip(
            prov_dir,
            "compat_mod",
            "1.1.0.0",
            dependencies={"core": ">=1.0.0"},
            release_meta={
                "status": "active",
                "dependencies": {"core": ">=99.0.0"},
            },
            entry="cli.py",
        )

        solved = engine.act_solve_deps("compat_mod", None, prov_dir)
        self.assertEqual(solved, [("compat_mod", "1.0.0.0")])

        with self.assertRaises(RuntimeError) as ctx:
            engine.act_solve_deps("compat_mod", "==1.1.0.0", prov_dir)
        self.assertIn("required core version '>=99.0.0' is not satisfied", str(ctx.exception))

        engine.act_download("compat_mod", "1.0.0.0", prov_dir)
        self.assertTrue(vfs.is_file("module.mirror://compat_mod/index.json"))

        modules_root = uri.resolve("module://")
        try:
            engine._reload_materialize_single_module("compat_mod", "1.0.0.0", modules_root)
            mat_mf = vfs.read_json("module://compat_mod/manifest.json")
            self.assertEqual(mat_mf.get("dependencies"), {"core": ">=1.0.0,<50.0.0"})
            self.assertEqual(mat_mf.get("release", {}).get("type"), "bugfix")
        finally:
            vfs.rmtree("module://compat_mod", ignore_errors=True)
            vfs.rmtree("module.mirror://compat_mod", ignore_errors=True)

        self.mark_passed()
