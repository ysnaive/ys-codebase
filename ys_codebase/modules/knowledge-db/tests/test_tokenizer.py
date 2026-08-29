"""
Unit Tests for knowledge-db CodeTokenizer.
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.tokenizer import CodeTokenizer


class TestTokenizer(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_code_identifier_tokenization(self):
        """FT-01: 驗證代碼標識符駝峰、底線、縮寫切分與保留原始詞"""
        tok = CodeTokenizer()

        # 1. 駝峰切分 (camelCase & PascalCase)
        res1 = tok.tokenize("PIDController")
        self.assertIn("pid", res1)
        self.assertIn("controller", res1)
        self.assertIn("pidcontroller", res1)

        res2 = tok.tokenize("getHTTPResponse")
        self.assertIn("get", res2)
        self.assertIn("http", res2)
        self.assertIn("response", res2)

        # 2. 底線切分 (snake_case)
        res3 = tok.tokenize("user_profile_manager_v5")
        self.assertIn("user", res3)
        self.assertIn("profile", res3)
        self.assertIn("manager", res3)
        self.assertIn("v5", res3)

        # 3. 複合代碼簽名
        res4 = tok.tokenize("def calculate_pid_velocity(target_rpm: float) -> bool:")
        self.assertIn("calculate", res4)
        self.assertIn("pid", res4)
        self.assertIn("velocity", res4)
        self.assertIn("target", res4)
        self.assertIn("rpm", res4)

    @require(Requirement.LOGIC)
    def test_cjk_and_stopword_tokenization(self):
        """FT-02: 驗證 CJK 1-gram/2-gram 滑動窗口與停用詞過濾 (EC-01)"""
        tok = CodeTokenizer()

        # 1. 中文字元 1-gram 與 2-gram
        res1 = tok.tokenize("狀態機更新頻率")
        self.assertIn("狀", res1)
        self.assertIn("態", res1)
        self.assertIn("機", res1)
        self.assertIn("狀態", res1)
        self.assertIn("態機", res1)
        self.assertIn("更新", res1)
        self.assertIn("頻率", res1)

        # 2. 中英文混排
        res2 = tok.tokenize("在 SpaceManager 中建立 UnifiedSymbol 實例")
        self.assertIn("spacemanager", res2)
        self.assertIn("unifiedsymbol", res2)
        self.assertIn("建", res2)
        self.assertIn("立", res2)
        self.assertIn("建立", res2)
        # 停用詞 "在" 與 "中" 應被過濾
        self.assertNotIn("在", res2)

        # 3. 空字串與純標點防禦 (EC-01)
        self.assertEqual(tok.tokenize(""), [])
        self.assertEqual(tok.tokenize("   "), [])
        self.assertEqual(tok.tokenize("!@#$%^&*()_+=-`~[]{}|;':\",.<>?/"), [])
