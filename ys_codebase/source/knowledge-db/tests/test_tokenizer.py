"""
Unit Tests for knowledge-db CodeTokenizer and ThesaurusEngine.
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
from knowledge_db.thesaurus import ThesaurusEngine


class TestTokenizer(YSCBTestCase):
    """代碼分詞器 (CamelCase / snake_case / CJK 滑動窗口) 測試。"""

    @require(Requirement.LOGIC)
    def test_code_identifier_tokenization(self):
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

    @require(Requirement.LOGIC)
    def test_thesaurus_merging_and_query_expansion(self):
        """驗證軟工同義詞庫載入、自訂詞庫無衝突合併與雙向查詢擴展 (EC-05)。"""
        # 1. 內建通用詞庫測試
        engine = ThesaurusEngine()
        syns_create = engine.get_synonyms("建立")
        self.assertIn("create", syns_create)
        self.assertIn("init", syns_create)

        syns_search = engine.get_synonyms("search")
        self.assertIn("搜尋", syns_search)
        self.assertIn("query", syns_search)

        # 2. 自訂詞庫合併
        custom_groups = [
            ["自駕", "autonomous", "auto_pilot"],
            ["底盤", "chassis", "drivetrain"],
        ]
        engine_with_custom = ThesaurusEngine(custom_groups=custom_groups)
        syns_auto = engine_with_custom.get_synonyms("自駕")
        self.assertIn("autonomous", syns_auto)
        self.assertIn("auto_pilot", syns_auto)

        # 3. 查詢詞端雙向擴展
        query_tokens = ["搜尋", "底盤"]
        expanded = engine_with_custom.expand_query(query_tokens)
        self.assertIn("搜尋", expanded)
        self.assertIn("search", expanded)
        self.assertIn("query", expanded)
        self.assertIn("底盤", expanded)
        self.assertIn("chassis", expanded)
        self.assertIn("drivetrain", expanded)

        # 4. 防無窮迴圈與集合防禦
        cyclic_engine = ThesaurusEngine(custom_groups=[["a", "b"], ["b", "c"], ["c", "a"]])
        expanded_cyclic = cyclic_engine.expand_query(["a"])
        self.assertLessEqual(len(expanded_cyclic), 10)
        self.assertEqual(len(expanded_cyclic), len(set(expanded_cyclic)))
