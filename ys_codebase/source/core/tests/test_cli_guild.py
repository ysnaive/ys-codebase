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
        fake_manifests = {
            "module://dev/manifest.json": {
                "contributes": {
                    "core": {
                        "commands": {
                            "test": {
                                "description": "Run module tests",
                                "case_pros": ["開發中跑測"],
                                "case_cons": ["嚴禁手動先 build", "嚴禁跑 --all"]
                            },
                            "dummy_plain": {
                                "description": "Just a plain tool without pros/cons",
                                "case_pros": [],
                                "case_cons": []
                            },
                            "dummy_none": {
                                "description": "No pros or cons"
                            }
                        }
                    }
                }
            }
        }

        with patch("core.uri.exists", side_effect=lambda u: u in fake_manifests or u == "module://"):
            with patch("core.uri.listdir", return_value=["dev"]):
                with patch("core.uri.read_json", side_effect=lambda u: fake_manifests.get(u, {})):
                    output = get_agents_cli_guild()

        # 斷言 test 包含在內
        self.assertIn("`dev test`", output)
        self.assertIn("Run module tests", output)
        self.assertIn("• 開發中跑測", output)
        self.assertIn("• 嚴禁手動先 build", output)

        # 斷言 dummy_plain 與 dummy_none 被過濾排除
        self.assertNotIn("dummy_plain", output)
        self.assertNotIn("dummy_none", output)
        self.assertNotIn("Just a plain tool", output)

    def test_defensive_string_coercion(self):
        """ET-01: 驗證 case_pros / case_cons 為單一字串時自動防禦轉換為列表。"""
        fake_manifests = {
            "module://core/manifest.json": {
                "contributes": {
                    "core": {
                        "commands": {
                            "install": {
                                "description": "Install package",
                                "case_pros": "單一字串適用情境",
                                "case_cons": "單一字串禁止情境"
                            }
                        }
                    }
                }
            }
        }

        with patch("core.uri.exists", side_effect=lambda u: u in fake_manifests or u == "module://"):
            with patch("core.uri.listdir", return_value=["core"]):
                with patch("core.uri.read_json", side_effect=lambda u: fake_manifests.get(u, {})):
                    output = get_agents_cli_guild()

        self.assertIn("`install`", output)
        self.assertIn("• 單一字串適用情境", output)
        self.assertIn("• 單一字串禁止情境", output)

    def test_empty_fallback(self):
        """驗證全系統無任何防呆指令時回傳安全提示。"""
        with patch("core.uri.exists", return_value=False):
            output = get_agents_cli_guild()

        self.assertIn("目前全系統模組尚未定義具備防呆情境之 CLI 指令", output)


if __name__ == "__main__":
    unittest.main()
