import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.providers import get_agents_cli_guild
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestCliGuildProvider(YSCBTestCase):
    """測試 CLI 防呆手冊動態產生與過濾邏輯。"""

    def test_filter_and_formatting(self):
        """FT-01: 驗證有定義 pros/cons 正常生成，無定義或皆空之指令自動排除。"""
        fake_commands = {
            "test": {
                "description": "Run module tests",
                "case_pros": ["開發中跑測"],
                "case_cons": ["嚴禁手動先 build", "嚴禁跑 --all"],
                "__provider__": "dev"
            },
            "dummy_plain": {
                "description": "Just a plain tool without pros/cons",
                "case_pros": [],
                "case_cons": [],
                "__provider__": "dev"
            },
            "dummy_none": {
                "description": "No pros or cons",
                "__provider__": "dev"
            }
        }

        with patch("core.contributes.get", return_value=fake_commands):
            output = get_agents_cli_guild()

        # 斷言 test 包含在內
        self.assertIn("`python yscb.py dev test`", output)
        self.assertIn("開發中跑測", output)
        self.assertIn("嚴禁手動先 build", output)

        # 斷言 dummy_plain 與 dummy_none 被過濾排除
        self.assertNotIn("dummy_plain", output)
        self.assertNotIn("dummy_none", output)
        self.mark_passed()

    def test_defensive_string_coercion(self):
        """ET-01: 驗證 case_pros / case_cons 為單一字串時自動防禦轉換為列表。"""
        fake_commands = {
            "install": {
                "description": "Install package",
                "case_pros": "單一字串適用情境",
                "case_cons": "單一字串禁止情境",
                "__provider__": "core"
            }
        }

        with patch("core.contributes.get", return_value=fake_commands):
            output = get_agents_cli_guild()

        self.assertIn("`python yscb.py install`", output)
        self.assertIn("單一字串適用情境", output)
        self.assertIn("單一字串禁止情境", output)
        self.mark_passed()

    def test_empty_fallback(self):
        """驗證全系統無任何防呆指令時回傳安全提示。"""
        with patch("core.contributes.get", return_value={}):
            output = get_agents_cli_guild()

        self.assertIn("目前無已註冊之 CLI 防呆指令", output)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
