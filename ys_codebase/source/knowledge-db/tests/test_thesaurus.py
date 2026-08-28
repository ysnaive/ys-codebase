"""
Unit Tests for knowledge-db ThesaurusEngine.
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.thesaurus import ThesaurusEngine


class TestThesaurus(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_thesaurus_merging_and_query_expansion(self):
        """FT-03: 驗證同義詞庫載入、自訂詞庫無衝突合併與雙向查詢擴展 (EC-05)"""
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

        # 4. 防無窮迴圈與集合防禦 (EC-05)
        cyclic_engine = ThesaurusEngine(custom_groups=[["a", "b"], ["b", "c"], ["c", "a"]])
        expanded_cyclic = cyclic_engine.expand_query(["a"])
        self.assertLessEqual(len(expanded_cyclic), 10)
        self.assertEqual(len(expanded_cyclic), len(set(expanded_cyclic)))  # 確保無重複
