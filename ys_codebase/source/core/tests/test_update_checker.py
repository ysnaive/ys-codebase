"""
Unit tests for core.update_checker UpdateChecker.
"""
import unittest
import tempfile
import shutil
import os
import json
import time
from unittest.mock import patch, MagicMock
from core.update_checker import UpdateChecker
from dev.testing.case import YSCBTestCase


class TestUpdateChecker(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.cache_uri = f"cache://core/test_update_check_{int(time.time() * 1000)}.json"
        self.cfg_path = os.path.join(self.temp_dir, "yscb.config.json")
        self.prov_dir = os.path.join(self.temp_dir, "release")
        os.makedirs(self.prov_dir, exist_ok=True)

        # 模擬 yscb.config.json
        self.cfg_data = {
            "yscb_root": "./ys_codebase",
            "default_provider": self.prov_dir,
            "installed_modules": {
                "core": {
                    "version": "1.0.0.0",
                    "provider": self.prov_dir
                }
            }
        }
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(self.cfg_data, f)

        # 建立 Provider 端 index.json
        mod_release_dir = os.path.join(self.prov_dir, "core")
        os.makedirs(mod_release_dir, exist_ok=True)
        with open(os.path.join(mod_release_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "core", "versions": ["1.0.0.0", "1.0.1.0"]}, f)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_update_detection_and_tips(self):
        """FT-04: 驗證正確探測到新版本並生成提示字串。"""
        checker = UpdateChecker(
            cache_uri=self.cache_uri,
            throttle_seconds=10,
            config_path=self.cfg_path
        )
        updates = checker.check_updates(force=True)
        self.assertIn("core", updates)
        self.assertEqual(updates["core"]["latest_version"], "1.0.1.0")
        self.assertTrue(updates["core"]["has_update"])

        tips = checker.get_tips(updates)
        self.assertEqual(len(tips), 1)
        self.assertIn("1.0.1.0", tips[0])
        self.mark_passed()

    def test_throttling_within_window(self):
        """FT-04: 驗證在節流時間內直接返回快取，不重複探測。"""
        checker = UpdateChecker(
            cache_uri=self.cache_uri,
            throttle_seconds=3600,
            config_path=self.cfg_path
        )
        checker.check_updates(force=True)

        # 模擬修改 provider 端為更高版本
        mod_release_dir = os.path.join(self.prov_dir, "core")
        with open(os.path.join(mod_release_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "core", "versions": ["1.0.0.0", "1.0.2.0"]}, f)

        # 未強制且未超時 -> 仍應返回先前的 1.0.1.0 快取
        updates_cached = checker.check_updates(force=False)
        self.assertEqual(updates_cached["core"]["latest_version"], "1.0.1.0")

        # 強制更新 -> 取得 1.0.2.0
        updates_forced = checker.check_updates(force=True)
        self.assertEqual(updates_forced["core"]["latest_version"], "1.0.2.0")
        self.mark_passed()

    def test_network_failure_fallback(self):
        """EC-02: 驗證遠端網路異常或逾時時靜默安全降級，不拋出例外。"""
        checker = UpdateChecker(
            cache_uri=self.cache_uri,
            throttle_seconds=10,
            config_path=self.cfg_path
        )
        with patch("urllib.request.urlopen", side_effect=Exception("Connection timed out")):
            # 不應引發任何例外
            res = checker._fetch_latest_version("dummy_mod", "https://invalid.example.com/release")
            self.assertIsNone(res)
        self.mark_passed()

    def test_host_script_update_detection_and_agent_blocker_tip(self):
        """REV-01: 驗證入口檔 yscb.py __version__ 語意版本比對、特化 AGENT BLOCKER 提示與 self-update 快取清除。"""
        # 在 temp_dir 建立本機 yscb.py (1.1.0.5) 與來源端 yscb.py (1.1.0.6)
        local_yscb = os.path.join(self.temp_dir, "yscb.py")
        with open(local_yscb, "w", encoding="utf-8") as f:
            f.write('__version__: str = "1.1.0.5"\n')

        remote_yscb = os.path.join(self.prov_dir, "yscb.py")
        with open(remote_yscb, "w", encoding="utf-8") as f:
            f.write('__version__: str = "1.1.0.6"\n')

        checker = UpdateChecker(
            cache_uri=self.cache_uri,
            throttle_seconds=10,
            config_path=self.cfg_path,
        )
        updates = checker.check_updates(force=True)
        self.assertIn("yscb.py", updates)
        self.assertEqual(updates["yscb.py"]["current_version"], "1.1.0.5")
        self.assertEqual(updates["yscb.py"]["latest_version"], "1.1.0.6")
        self.assertTrue(updates["yscb.py"]["has_update"])

        tips = checker.get_tips(updates)
        self.assertGreaterEqual(len(tips), 2)
        self.assertIn("[CRITICAL UPDATE]", tips[0])
        self.assertIn("python yscb.py self-update", tips[0])
        self.assertIn("[AGENT BLOCKER]", tips[0])

        # 驗證 invalidate_cache("yscb.py") 僅清除 yscb.py 條目
        checker.invalidate_cache("yscb.py")
        cached_after = checker._load_cache()
        self.assertNotIn("yscb.py", cached_after.get("updates", {}))
        self.assertIn("core", cached_after.get("updates", {}))
        self.mark_passed()

    def test_dispatcher_triggers_update_check_on_any_command(self):
        """REV-01: 驗證 dispatcher.dispatch 在執行任意指令後均會觸發 _maybe_check_and_print_updates。"""
        from core.commands import dispatcher
        from core.commands.registry import CommandsRegistry

        reg = CommandsRegistry()
        reg.register_module("any_mod", {"cmd": {"ping": {"description": "Ping", "server_compatible": False}}})

        with patch("core.commands.dispatcher._load_registry", return_value=reg):
            with patch("core.commands.dispatcher.dispatch_local", return_value=0):
                with patch("core.commands.dispatcher._maybe_auto_spawn_server"):
                    with patch("core.commands.dispatcher._maybe_check_and_print_updates") as mock_chk:
                        rc = dispatcher.dispatch(["any_mod", "ping"])
                        self.assertEqual(rc, 0)
                        mock_chk.assert_called_once()
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
