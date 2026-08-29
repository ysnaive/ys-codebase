"""
knowledge-db 詞彙池解耦與 Contributes 初始詞庫單元測試套件
覆蓋 FT-01~FT-04, ET-01~ET-03
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.schema import ThesaurusConfig, WeightedToken
from knowledge_db.thesaurus import ThesaurusEngine
from knowledge_db.space import SpaceManager


class TestThesaurusDecoupling(YSCBTestCase):
    """詞彙池解耦與工廠裝配測試"""

    @require(Requirement.LOGIC)
    def test_thesaurus_engine_pure_container_default(self):
        """FT-01: 驗證 ThesaurusEngine 預設無傳參時為純空容器"""
        engine = ThesaurusEngine()
        # 預設無任何內建詞條
        expanded = engine.expand_query_weighted(["搜尋"])
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].term, "搜尋")
        self.assertEqual(expanded[0].weight, 1.0)
        self.assertEqual(expanded[0].kind, "original")

    @require(Requirement.LOGIC)
    def test_thesaurus_engine_from_config(self):
        """FT-02: 驗證 ThesaurusEngine(config=...) 正確自組態裝配"""
        config = ThesaurusConfig(
            groups=[["搜尋", "search", "query"]],
            aliases={"ngspice": ["spice", "circuit"]},
            related=[["parser", "ast", "lexer"]],
        )
        engine = ThesaurusEngine(config=config)

        # 1. 雙向同義詞 (Tier 2, 0.6)
        res_search = engine.expand_query_weighted(["搜尋"])
        terms_search = {wt.term: wt.weight for wt in res_search}
        self.assertEqual(terms_search["搜尋"], 1.0)
        self.assertEqual(terms_search["search"], 0.6)
        self.assertEqual(terms_search["query"], 0.6)

        # 2. 單向別名 (Tier 2, 0.6)
        res_spice = engine.expand_query_weighted(["ngspice"])
        terms_spice = {wt.term: wt.weight for wt in res_spice}
        self.assertEqual(terms_spice["ngspice"], 1.0)
        self.assertEqual(terms_spice["spice"], 0.6)
        self.assertEqual(terms_spice["circuit"], 0.6)

        # 3. 領域關聯詞 (Tier 3, 0.25)
        res_ast = engine.expand_query_weighted(["parser"])
        terms_ast = {wt.term: wt.weight for wt in res_ast}
        self.assertEqual(terms_ast["parser"], 1.0)
        self.assertEqual(terms_ast["ast"], 0.25)
        self.assertEqual(terms_ast["lexer"], 0.25)

    @require(Requirement.LOGIC)
    def test_space_manager_create_thesaurus_engine(self):
        """FT-03: 驗證 SpaceManager.create_thesaurus_engine() 工廠方法裝配"""
        mock_contrib = {
            "thesaurus": [
                ["狀態", "現狀", "status", "state"]
            ],
            "aliases": {
                "cpp": ["cxx", "hpp"]
            },
            "related": [
                ["retrieval", "bm25", "idf"]
            ]
        }
        sm = SpaceManager(contributes_data=mock_contrib)
        engine = sm.create_thesaurus_engine()
        self.assertIsInstance(engine, ThesaurusEngine)

        # 驗證同義詞
        res_status = engine.expand_query_weighted(["狀態"])
        terms_status = {wt.term: wt.weight for wt in res_status}
        self.assertIn("status", terms_status)
        self.assertEqual(terms_status["status"], 0.6)

        # 驗證別名
        res_cpp = engine.expand_query_weighted(["cpp"])
        terms_cpp = {wt.term: wt.weight for wt in res_cpp}
        self.assertIn("cxx", terms_cpp)
        self.assertEqual(terms_cpp["cxx"], 0.6)

        # 驗證額外疊加 extra_config
        extra = ThesaurusConfig(
            groups=[["自訂詞A", "custom_a"]],
            aliases={"extra_alias": ["tgt1"]},
            related=[["rel_a", "rel_b"]],
        )
        engine_extra = sm.create_thesaurus_engine(extra_config=extra)
        res_extra = engine_extra.expand_query_weighted(["自訂詞a"])
        terms_extra = {wt.term: wt.weight for wt in res_extra}
        self.assertIn("custom_a", terms_extra)

    @require(Requirement.LOGIC)
    def test_six_dimensional_thesaurus_enrichment(self):
        """FT-04: 驗證六大維度初始詞庫宣告（日用語、C/C++、C#、Python、SPICE、資電學系）"""
        # 使用預設 SpaceManager (載入 source/knowledge-db/contributes/knowledge-db.json)
        sm = SpaceManager()
        engine = sm.create_thesaurus_engine()

        # 維度 1: 軟工通用動名詞
        res_build = engine.expand_query_weighted(["建立"])
        terms_build = {wt.term for wt in res_build}
        self.assertTrue({"create", "init", "initialize", "build"}.issubset(terms_build))

        # 維度 2: C / C++ 術語
        res_ptr = engine.expand_query_weighted(["指標"])
        terms_ptr = {wt.term for wt in res_ptr}
        self.assertTrue({"指針", "pointer", "ptr"}.issubset(terms_ptr))

        res_cpp = engine.expand_query_weighted(["cpp"])
        terms_cpp = {wt.term for wt in res_cpp}
        self.assertTrue({"cxx", "hpp"}.issubset(terms_cpp))

        # 維度 3: C# 術語
        res_async = engine.expand_query_weighted(["非同步"])
        terms_async = {wt.term for wt in res_async}
        self.assertTrue({"異步", "async", "await", "task"}.issubset(terms_async))

        # 維度 4: Python 術語
        res_deco = engine.expand_query_weighted(["裝飾器"])
        terms_deco = {wt.term for wt in res_deco}
        self.assertTrue({"裝飾者", "decorator", "wrapper"}.issubset(terms_deco))

        # 維度 5: SPICE 術語
        res_spice = engine.expand_query_weighted(["網表"])
        terms_spice = {wt.term for wt in res_spice}
        self.assertTrue({"netlist", "spice", "cir"}.issubset(terms_spice))

        res_ngspice = engine.expand_query_weighted(["ngspice"])
        terms_ngspice = {wt.term for wt in res_ngspice}
        self.assertTrue({"spice", "circuit", "netlist"}.issubset(terms_ngspice))

        # 維度 6: 資電學系術語
        res_gate = engine.expand_query_weighted(["邏輯閘"])
        terms_gate = {wt.term for wt in res_gate}
        self.assertTrue({"logic_gate", "combinational"}.issubset(terms_gate))

        res_fpga = engine.expand_query_weighted(["fpga"])
        terms_fpga = {wt.term for wt in res_fpga}
        self.assertTrue({"hdl", "verilog", "vhdl", "rtl"}.issubset(terms_fpga))

        # 維度 7: 常用演算法與尋路 (A*, Dijkstra, BFS, DFS, DP)
        res_astar = engine.expand_query_weighted(["astar"])
        terms_astar = {wt.term for wt in res_astar}
        self.assertTrue({"pathfinding", "dijkstra", "heuristic"}.issubset(terms_astar))

        res_pathfinding = engine.expand_query_weighted(["尋路"])
        terms_pathfinding = {wt.term for wt in res_pathfinding}
        self.assertTrue({"astar", "pathfinding", "routing"}.issubset(terms_pathfinding))

        res_dp = engine.expand_query_weighted(["dp"])
        terms_dp = {wt.term for wt in res_dp}
        self.assertTrue({"dynamic_programming", "memoization"}.issubset(terms_dp))

        # 維度 8: 日常工程作業 (重試/回滾, 快取/緩存, 登入/驗證, 鎖定/解鎖)
        res_retry = engine.expand_query_weighted(["重試"])
        terms_retry = {wt.term for wt in res_retry}
        self.assertTrue({"rollback", "revert", "retry"}.issubset(terms_retry))

        res_cache = engine.expand_query_weighted(["快取"])
        terms_cache = {wt.term for wt in res_cache}
        self.assertTrue({"緩存", "cache", "buffer"}.issubset(terms_cache))

    @require(Requirement.LOGIC)
    def test_empty_contributes_safe_fallback(self):
        """ET-01: 驗證無 Contributes 或空字典時安全降級"""
        sm = SpaceManager(contributes_data={})
        engine = sm.create_thesaurus_engine()
        self.assertIsInstance(engine, ThesaurusEngine)
        res = engine.expand_query_weighted(["未知術語xyz"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].term, "未知術語xyz")

    @require(Requirement.LOGIC)
    def test_duplicate_contributes_deduplication(self):
        """ET-02: 驗證重複詞條與大小寫去重"""
        mock_contrib = {
            "thesaurus": [
                ["搜尋", "Search"],
                ["search", "搜尋"],
                ["搜尋", "SEARCH"]
            ]
        }
        sm = SpaceManager(contributes_data=mock_contrib)
        cfg = sm.load_thesaurus_config()
        self.assertEqual(len(cfg.groups), 1)

    @require(Requirement.LOGIC)
    def test_none_parameters_safety(self):
        """ET-03: 驗證 None 傳參安全防禦"""
        engine = ThesaurusEngine(config=None, custom_groups=None, custom_aliases=None, custom_related=None)
        res = engine.expand_query_weighted(["test"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].term, "test")

    @require(Requirement.LOGIC)
    def test_multi_hop_transitive_chaining(self):
        """FT-05: 驗證多跳鏈式傳播 (中文 -> 同義英文 -> 關聯英文 -> 關聯中文)"""
        sm = SpaceManager()
        engine = sm.create_thesaurus_engine()

        # 輸入中文 "尋路" (1.0)
        # Hop 1 (同義): 展開到 astar, pathfinding (0.6)
        # Hop 2 (關聯): 由 astar 關聯到 dijkstra, heuristic (0.25)
        # Hop 3 (同義反查): 由 dijkstra 展開到 最短路徑 (0.25)
        res = engine.expand_query_weighted(["尋路"])
        term_map = {wt.term: wt for wt in res}

        # 1. 驗證 Tier 1 原始詞
        self.assertIn("尋路", term_map)
        self.assertEqual(term_map["尋路"].weight, 1.0)
        self.assertEqual(term_map["尋路"].kind, "original")

        # 2. 驗證 Hop 1 同義詞 (0.6)
        self.assertIn("astar", term_map)
        self.assertEqual(term_map["astar"].weight, 0.6)

        # 3. 驗證 Hop 2 關聯詞 (0.25)
        self.assertIn("dijkstra", term_map)
        self.assertEqual(term_map["dijkstra"].weight, 0.25)
        self.assertEqual(term_map["dijkstra"].kind, "related")

        # 4. 驗證 Hop 3 關聯之中文同義詞 (0.25)
        self.assertIn("最短路徑", term_map)
        self.assertEqual(term_map["最短路徑"].weight, 0.25)
        self.assertEqual(term_map["最短路徑"].kind, "related")
