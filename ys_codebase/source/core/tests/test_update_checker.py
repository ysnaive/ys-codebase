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


if __name__ == "__main__":
    unittest.main()
