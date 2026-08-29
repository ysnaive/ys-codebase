import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.providers import (
    get_agents_cli_guild,
    get_phase_cli_guild,
    get_phase05_cli_guild,
    get_phase06_cli_guild,
    get_phase07_cli_guild,
)
from dev.testing.case import YSCBTestCase


class TestCliGuildProvider(YSCBTestCase):
    """測試 CLI 防呆手冊動態產生、三級權限分級與 Phase JIT 過濾邏輯。"""

    def test_filter_and_formatting(self):
        """FT-01: 驗證有定義 pros/cons 正常生成，支援 tier 標籤 (🟢/🟡/🔴)，無定義之指令自動排除。"""
        fake_commands = {
            "test": {
                "description": "Run module tests",
                "tier": "safe",
                "phases": ["P05", "P06"],
                "case_pros": ["開發中跑測"],
                "case_cons": ["嚴禁手動先 build", "嚴禁跑 --all"],
                "__provider__": "dev",
            },
            "release": {
                "description": "Release package",
                "tier": "gated",
                "phases": ["P07"],
                "case_pros": ["正式打包發布"],
                "case_cons": ["嚴禁未經指示發布"],
                "__provider__": "dev",
            },
            "dummy_plain": {
                "description": "Just a plain tool without pros/cons",
                "case_pros": [],
                "case_cons": [],
                "__provider__": "dev",
            },
        }

        with patch("core.contributes.get", return_value=fake_commands):
            output = get_agents_cli_guild()

        # 斷言三級權限標籤
        self.assertIn("🟢 自主安全", output)
        self.assertIn("🔴 授權守門", output)
        self.assertIn("`python yscb.py dev test`", output)
        self.assertIn("`python yscb.py dev release`", output)
        self.assertIn("開發中跑測", output)
        self.assertIn("嚴禁手動先 build", output)

        # 斷言 dummy_plain 被過濾排除
        self.assertNotIn("dummy_plain", output)
        self.mark_passed()

    def test_phase_aware_jit_filtering(self):
        """FT-02: 驗證 get_phase_cli_guild 能精準依據 Phase 過濾推薦指令與守門紅線。"""
        fake_commands = {
            "test": {
                "description": "Run module tests",
                "tier": "safe",
                "phases": ["P05", "P06"],
                "case_pros": ["沙盒自動化跑測"],
                "case_cons": ["嚴禁日常跑 --all"],
                "__provider__": "dev",
            },
            "check": {
                "description": "Static code check",
                "tier": "safe",
                "phases": ["P05"],
                "case_pros": ["代碼靜態預檢"],
                "__provider__": "dev",
            },
            "release": {
                "description": "Release package",
                "tier": "gated",
                "phases": ["P07"],
                "case_pros": ["正式發布"],
                "case_cons": ["嚴禁未經指示發布"],
                "__provider__": "dev",
            },
        }

        with patch("core.contributes.get", return_value=fake_commands):
            # Phase 5 JIT
            p5_output = get_phase05_cli_guild()
            self.assertIn("python yscb.py dev check", p5_output)
            self.assertIn("python yscb.py dev test", p5_output)
            self.assertIn("🚨 嚴禁執行 `python yscb.py dev release`", p5_output)

            # Phase 6 JIT
            p6_output = get_phase06_cli_guild()
            self.assertIn("python yscb.py dev test", p6_output)
            self.assertNotIn("python yscb.py dev check", p6_output)
            self.assertIn("🚨 嚴禁執行 `python yscb.py dev release`", p6_output)

            # Phase 7 JIT
            p7_output = get_phase07_cli_guild()
            self.assertIn("python yscb.py dev release", p7_output)

        self.mark_passed()

    def test_defensive_string_coercion(self):
        """ET-01: 驗證 case_pros / case_cons 為單一字串時自動防禦轉換為列表，tier 缺失時 fallback 為 conditional。"""
        fake_commands = {
            "install": {
                "description": "Install package",
                "case_pros": "單一字串適用情境",
                "case_cons": "單一字串禁止情境",
                "__provider__": "core",
            }
        }

        with patch("core.contributes.get", return_value=fake_commands):
            output = get_agents_cli_guild()

        self.assertIn("🟡 階段條件", output)
        self.assertIn("`python yscb.py install`", output)
        self.assertIn("單一字串適用情境", output)
        self.assertIn("單一字串禁止情境", output)
        self.mark_passed()

    def test_empty_fallback(self):
        """ET-02: 驗證全系統無任何防呆指令時回傳安全提示。"""
        with patch("core.contributes.get", return_value={}):
            output = get_agents_cli_guild()
            p_output = get_phase_cli_guild(phase="P05")

        self.assertIn("目前無已註冊之 CLI 防呆指令", output)
        self.assertEqual(p_output, "")
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
