"""
Unit Tests for Server Module Configuration & Console Override Logic.
Covers FT-01 ~ FT-05 and edge cases (EC-01 ~ EC-02).
"""

import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
_cli_path = os.path.join(_pkg_root, "scripts", "cli.py")

_spec = importlib.util.spec_from_file_location("server_cli", _cli_path)
_server_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server_cli)

_resolve_enable_console = _server_cli._resolve_enable_console
_handle_start = _server_cli._handle_start

from dev.testing.case import YSCBTestCase
from server.config import ServerConfig, _parse_bool, DEFAULT_ENABLE_CONSOLE, DEFAULT_IDLE_TIMEOUT_SEC


class TestServerConfig(YSCBTestCase):
    """Server 組態與 Console 啟動模式測試套件"""

    def test_default_config(self):
        """FT-01: 驗證 ServerConfig 預設值為 enable_console=False 與 TTL=900.0"""
        cfg = ServerConfig()
        self.assertFalse(cfg.enable_console)
        self.assertEqual(cfg.idle_timeout_sec, 900.0)

        # 自 load() 預設無設定時載入
        with patch("core.config.get_all", return_value={}):
            loaded = ServerConfig.load()
            self.assertFalse(loaded.enable_console)
            self.assertEqual(loaded.idle_timeout_sec, 900.0)

        self.mark_passed()

    def test_config_override_and_type_defense(self):
        """FT-02: 驗證 ServerConfig 支援字典覆蓋與寬鬆布林轉型 (EC-02)"""
        # 1. 字典直接覆蓋
        cfg1 = ServerConfig.load(override_dict={"enable_console": True, "idle_timeout_sec": 300.0})
        self.assertTrue(cfg1.enable_console)
        self.assertEqual(cfg1.idle_timeout_sec, 300.0)

        # 2. 字串防禦轉型 ("true", "1", "yes", "on")
        for truthy in ("true", "True", "1", "yes", "on"):
            cfg_t = ServerConfig.load(override_dict={"enable_console": truthy})
            self.assertTrue(cfg_t.enable_console)

        # 3. 偽值轉型 ("false", "0", "no", "off")
        for falsy in ("false", "False", "0", "no", "off"):
            cfg_f = ServerConfig.load(override_dict={"enable_console": falsy})
            self.assertFalse(cfg_f.enable_console)

        # 4. 非法型別或 None 回退預設值 False
        cfg_none = ServerConfig.load(override_dict={"enable_console": None})
        self.assertFalse(cfg_none.enable_console)

        cfg_invalid = ServerConfig.load(override_dict={"enable_console": [1, 2, 3]})
        self.assertFalse(cfg_invalid.enable_console)

        # 5. core.config 整合讀取
        with patch("core.config.get_all", return_value={"enable_console": True, "idle_timeout_sec": 60.0}):
            cfg_core = ServerConfig.load()
            self.assertTrue(cfg_core.enable_console)
            self.assertEqual(cfg_core.idle_timeout_sec, 60.0)

        self.mark_passed()

    def test_cli_console_override(self):
        """FT-03: 驗證 CLI --console 具備最高優先權 (強制前台 Console，覆蓋 config False)"""
        # config 為 False，CLI --console 為 True
        res = _resolve_enable_console(console_arg=True, daemon_arg=None, config_val=False)
        self.assertTrue(res)

        # config 為 True，CLI --console 為 True
        res2 = _resolve_enable_console(console_arg=True, daemon_arg=None, config_val=True)
        self.assertTrue(res2)

        self.mark_passed()

    def test_cli_daemon_override(self):
        """FT-04: 驗證 CLI --daemon 具備優先權 (強制背景脫鉤，覆蓋 config True)"""
        # config 為 True，CLI --daemon 為 True
        res = _resolve_enable_console(console_arg=None, daemon_arg=True, config_val=True)
        self.assertFalse(res)

        # config 為 False，CLI --daemon 為 True
        res2 = _resolve_enable_console(console_arg=None, daemon_arg=True, config_val=False)
        self.assertFalse(res2)

        self.mark_passed()

    def test_config_fallback_when_no_cli_args(self):
        """FT-05: 驗證無 CLI 參數時 (None, None)，精確回退至 config 設定值"""
        self.assertFalse(_resolve_enable_console(console_arg=None, daemon_arg=None, config_val=False))
        self.assertTrue(_resolve_enable_console(console_arg=None, daemon_arg=None, config_val=True))

        self.mark_passed()

    def test_cli_mutually_exclusive_args(self):
        """EC-01: 驗證同時傳入 --console 與 --daemon 觸發互斥例外"""
        with self.assertRaises(SystemExit):
            # argparse parse_args 於衝突時拋出 SystemExit(2)
            _handle_start(["--console", "--daemon"], "/dummy/root")

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
