import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from core import config
from core import uri


class TestConfigManager(YSCBTestCase):
    """測試 core.config 核心管理器、雙層深層合併、mtime 自愈與 CLI 指令。"""

    def setUp(self):
        super().setUp()
        config.reload()

    def test_config_get_dot_notation(self):
        """FT-01: 驗證 Config SDK 點分隔查詢與巢狀結構解析。"""
        test_data = {
            "paths": {
                "plans": "project://plans",
                "docs": "project://docs"
            },
            "flags": {
                "enabled": True,
                "count": 42
            }
        }
        
        cfg_path = config.get_config_path("test_mod_get", local=False)
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f, indent=2)

        config.reload("test_mod_get")

        self.assertEqual(config.get("test_mod_get", "paths.plans"), "project://plans")
        self.assertEqual(config.get("test_mod_get", "flags.count"), 42)
        self.assertTrue(config.get("test_mod_get", "flags.enabled"))
        self.assertEqual(config.get("test_mod_get", "paths.nonexistent", "fallback"), "fallback")
        self.assertEqual(config.get_all("test_mod_get")["paths"]["docs"], "project://docs")
        self.mark_passed()

    def test_local_overrides_project(self):
        """FT-02: 驗證 Local > Project 雙層深層合併 (Tier 1 優先覆蓋 Tier 2)。"""
        proj_data = {
            "key_a": "proj_a",
            "key_b": "proj_b",
            "nested": {
                "x": 10,
                "y": 20
            }
        }
        local_data = {
            "key_b": "local_b",
            "nested": {
                "y": 99,
                "z": 100
            }
        }

        proj_path = config.get_config_path("test_mod_override", local=False)
        local_path = config.get_config_path("test_mod_override", local=True)
        os.makedirs(os.path.dirname(proj_path), exist_ok=True)

        with open(proj_path, "w", encoding="utf-8") as f:
            json.dump(proj_data, f, indent=2)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(local_data, f, indent=2)

        config.reload("test_mod_override")

        # 斷言：key_a 保留 project，key_b 被 local 覆蓋，nested 遞迴深層合併
        self.assertEqual(config.get("test_mod_override", "key_a"), "proj_a")
        self.assertEqual(config.get("test_mod_override", "key_b"), "local_b")
        self.assertEqual(config.get("test_mod_override", "nested.x"), 10)
        self.assertEqual(config.get("test_mod_override", "nested.y"), 99)
        self.assertEqual(config.get("test_mod_override", "nested.z"), 100)
        self.mark_passed()

    def test_config_set_and_auto_healing(self):
        """FT-03: 驗證 Config SDK 寫入、點分隔巢狀賦值與快取自愈。"""
        mod = "test_mod_set"
        config.set(mod, "database.host", "localhost", local=False)
        config.set(mod, "database.port", 5432, local=False)

        self.assertEqual(config.get(mod, "database.host"), "localhost")
        self.assertEqual(config.get(mod, "database.port"), 5432)

        # 寫入 local 覆蓋
        config.set(mod, "database.host", "127.0.0.1", local=True)
        self.assertEqual(config.get(mod, "database.host"), "127.0.0.1")
        self.assertEqual(config.get(mod, "database.port"), 5432)
        self.mark_passed()

    def test_config_delete(self):
        """驗證鍵值刪除操作。"""
        mod = "test_mod_del"
        config.set(mod, "a.b.c", "target", local=False)
        self.assertEqual(config.get(mod, "a.b.c"), "target")

        deleted = config.delete(mod, "a.b.c", local=False)
        self.assertTrue(deleted)
        self.assertIsNone(config.get(mod, "a.b.c"))
        self.mark_passed()

    def test_config_missing_fallback(self):
        """ET-01: 驗證無設定檔時安全回退預設值。"""
        self.assertIsNone(config.get("nonexistent_mod_12345", "any.key"))
        self.assertEqual(config.get("nonexistent_mod_12345", "any.key", "custom_default"), "custom_default")
        self.assertEqual(config.get_all("nonexistent_mod_12345"), {})
        self.mark_passed()

    def test_config_corrupted_json_isolation(self):
        """ET-02: 驗證損毀 JSON 安全容錯隔離不崩潰。"""
        mod = "test_mod_corrupt"
        proj_path = config.get_config_path(mod, local=False)
        os.makedirs(os.path.dirname(proj_path), exist_ok=True)
        with open(proj_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json corrupted ...")

        config.reload(mod)
        self.assertEqual(config.get(mod, "some.key", "fallback_ok"), "fallback_ok")
        self.mark_passed()

    def test_cli_config_commands(self):
        """FT-07: 驗證 CLI config list/get/set 指令運作。"""
        import importlib.util
        cli_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "cli.py"))
        spec = importlib.util.spec_from_file_location("core_scripts_cli", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)
        cmd_config = cli_mod.cmd_config

        mod = "test_mod_cli"

        # 測試 set
        ret_set = cmd_config(["set", mod, "foo.bar", "hello_world"])
        self.assertEqual(ret_set, 0)
        self.assertEqual(config.get(mod, "foo.bar"), "hello_world")

        # 測試 get
        ret_get = cmd_config(["get", mod, "foo.bar"])
        self.assertEqual(ret_get, 0)

        # 測試 list
        ret_list = cmd_config(["list", f"--mod={mod}"])
        self.assertEqual(ret_list, 0)
        self.mark_passed()

    def test_config_get_raw_and_inspect(self):
        """FT-08: 驗證 get_raw 單層原始讀取與 inspect 來源層級診斷。"""
        mod = "test_mod_inspect"
        config.set(mod, "target.alpha", "from_project", local=False)
        config.set(mod, "target.beta", "from_project", local=False)
        config.set(mod, "target.beta", "from_local", local=True)
        config.set(mod, "target.gamma", "from_local", local=True)

        # 1. 測試 get_raw
        self.assertEqual(config.get_raw(mod, "target.alpha", local=False), "from_project")
        self.assertIsNone(config.get_raw(mod, "target.alpha", local=True))
        self.assertEqual(config.get_raw(mod, "target.beta", local=False), "from_project")
        self.assertEqual(config.get_raw(mod, "target.beta", local=True), "from_local")
        self.assertEqual(config.get_raw(mod, "target.gamma", local=True), "from_local")
        self.assertIsNone(config.get_raw(mod, "target.gamma", local=False))

        # 2. 測試 inspect
        insp_alpha = config.inspect(mod, "target.alpha")
        self.assertEqual(insp_alpha["source"], "project")
        self.assertEqual(insp_alpha["effective"], "from_project")
        self.assertFalse(insp_alpha["is_overridden"])

        insp_beta = config.inspect(mod, "target.beta")
        self.assertEqual(insp_beta["source"], "both")
        self.assertEqual(insp_beta["effective"], "from_local")
        self.assertTrue(insp_beta["is_overridden"])

        insp_gamma = config.inspect(mod, "target.gamma")
        self.assertEqual(insp_gamma["source"], "local")
        self.assertEqual(insp_gamma["effective"], "from_local")
        self.assertFalse(insp_gamma["is_overridden"])

        insp_none = config.inspect(mod, "target.nonexistent")
        self.assertEqual(insp_none["source"], "none")
        self.assertIsNone(insp_none["effective"])
        self.mark_passed()



if __name__ == "__main__":
    unittest.main()
