"""
Unit Tests for knowledge-db Three-Tier Weighted Thesaurus & Retrieval Engine.
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.schema import (
    SymbolKind,
    ThesaurusConfig,
    UnifiedSymbol,
    WeightedToken,
)
from knowledge_db.thesaurus import ThesaurusEngine
from knowledge_db.tokenizer import CodeTokenizer
from knowledge_db.retrieval import BM25Engine, InvertedIndex
from knowledge_db.space import SpaceManager


class TestThesaurusWeighted(YSCBTestCase):
    """三階加權語意同義詞/別名/關聯詞擴展與 BM25 檢索引擎測試。"""

    @require(Requirement.LOGIC)
    def test_weighted_token_and_config(self):
        """FT-01: 驗證 WeightedToken 與 ThesaurusConfig 序列化/反序列化。"""
        wt = WeightedToken(term="search", weight=0.6, kind="synonym")
        d = wt.to_dict()
        self.assertEqual(d["term"], "search")
        self.assertEqual(d["weight"], 0.6)
        self.assertEqual(d["kind"], "synonym")

        cfg = ThesaurusConfig.from_dict({
            "thesaurus": [["搜尋", "search"]],
            "aliases": {"spice": ["circuit", "netlist"]},
            "related": [["parser", "ast", "lexer"]],
            "origin": "test_module",
        })
        self.assertEqual(cfg.origin, "test_module")
        self.assertEqual(cfg.thesaurus, [["搜尋", "search"]])
        self.assertEqual(cfg.aliases["spice"], ["circuit", "netlist"])
        self.assertEqual(cfg.related, [["parser", "ast", "lexer"]])

        cfg_dict = cfg.to_dict()
        self.assertIn("aliases", cfg_dict)
        self.assertIn("related", cfg_dict)
        self.assertEqual(cfg_dict["aliases"]["spice"], ["circuit", "netlist"])

    @require(Requirement.LOGIC)
    def test_directed_aliases(self):
        """FT-02: 驗證單向別名 add_alias 展開正確性 (A => B 有效且 B 不反向展開 A)。"""
        engine = ThesaurusEngine(
            custom_groups=[],
            custom_aliases={"ngspice": ["spice", "circuit"]},
        )
        # 1. 查詢來源詞 ngspice -> 展開 ngspice(1.0), spice(0.6), circuit(0.6)
        expanded = engine.expand_query_weighted(["ngspice"])
        terms = [t.term for t in expanded]
        self.assertIn("ngspice", terms)
        self.assertIn("spice", terms)
        self.assertIn("circuit", terms)
        for t in expanded:
            if t.term == "ngspice":
                self.assertEqual(t.weight, 1.0)
                self.assertEqual(t.kind, "original")
            elif t.term in ("spice", "circuit"):
                self.assertEqual(t.weight, 0.6)
                self.assertEqual(t.kind, "alias")

        # 2. 查詢目標詞 spice -> 不應反向展開 ngspice
        expanded_reverse = engine.expand_query_weighted(["spice"])
        reverse_terms = [t.term for t in expanded_reverse]
        self.assertIn("spice", reverse_terms)
        self.assertNotIn("ngspice", reverse_terms)

    @require(Requirement.LOGIC)
    def test_related_terms_expansion(self):
        """FT-03: 驗證領域關聯詞 add_related_group 雙向關聯展開 (權重 0.25, kind='related')。"""
        engine = ThesaurusEngine(
            custom_groups=[],
            custom_related=[["parser", "ast", "lexer"]],
        )
        expanded = engine.expand_query_weighted(["parser"])
        term_map = {t.term: t for t in expanded}
        self.assertIn("parser", term_map)
        self.assertIn("ast", term_map)
        self.assertIn("lexer", term_map)

        self.assertEqual(term_map["parser"].weight, 1.0)
        self.assertEqual(term_map["parser"].kind, "original")
        self.assertEqual(term_map["ast"].weight, 0.25)
        self.assertEqual(term_map["ast"].kind, "related")
        self.assertEqual(term_map["lexer"].weight, 0.25)
        self.assertEqual(term_map["lexer"].kind, "related")

    @require(Requirement.LOGIC)
    def test_expand_query_weighted_tiers(self):
        """FT-04: 驗證三階加權展開之順序與層級權重。"""
        engine = ThesaurusEngine(
            custom_groups=[["find", "lookup"]],
            custom_aliases={"find": ["search_engine"]},
            custom_related=[["find", "index", "scan"]],
        )
        tokens = ["find"]
        expanded = engine.expand_query_weighted(tokens)
        
        # 檢查各層級是否存在
        kinds = [t.kind for t in expanded]
        self.assertEqual(kinds[0], "original")
        self.assertEqual(expanded[0].term, "find")
        self.assertEqual(expanded[0].weight, 1.0)

        # 檢查 backward-compatible expand_query
        raw_list = engine.expand_query(["find"])
        self.assertIn("find", raw_list)
        self.assertIn("lookup", raw_list)
        self.assertIn("search_engine", raw_list)
        self.assertIn("index", raw_list)
        self.assertIn("scan", raw_list)

    @require(Requirement.LOGIC)
    def test_bm25_weighted_scoring_ranking(self):
        """FT-05: 驗證 BM25 加權計分：原始詞精確匹配得分 > 同義詞/別名匹配 > 關聯詞匹配。"""
        thesaurus = ThesaurusEngine(
            custom_groups=[["search", "lookup"]],
            custom_aliases={"search": ["query_alias"]},
            custom_related=[["search", "index_related"]],
        )
        bm25 = BM25Engine(thesaurus=thesaurus)
        index = InvertedIndex()

        # 建立 3 個符號
        # Doc 1: 包含原始詞 "search"
        sym1 = UnifiedSymbol(
            id="sym1",
            name="SearchService",
            kind=SymbolKind.CLASS.value,
            language="python",
            file_path="/app/search.py",
            line_number=1,
            end_line=10,
            signature="class SearchService:",
            docstring="Service to search items in repository",
        )
        # Doc 2: 包含同義詞 "lookup"
        sym2 = UnifiedSymbol(
            id="sym2",
            name="LookupService",
            kind=SymbolKind.CLASS.value,
            language="python",
            file_path="/app/lookup.py",
            line_number=1,
            end_line=10,
            signature="class LookupService:",
            docstring="Service to lookup items in repository",
        )
        # Doc 3: 包含關聯詞 "index_related"
        sym3 = UnifiedSymbol(
            id="sym3",
            name="IndexRelatedService",
            kind=SymbolKind.CLASS.value,
            language="python",
            file_path="/app/index_related.py",
            line_number=1,
            end_line=10,
            signature="class IndexRelatedService:",
            docstring="Service to index_related items in repository",
        )

        tok = CodeTokenizer()
        index.add_symbol(sym1, tokenizer=tok, space="app")
        index.add_symbol(sym2, tokenizer=tok, space="app")
        index.add_symbol(sym3, tokenizer=tok, space="app")

        # 執行檢索 "search"
        results = bm25.search("search", index)
        self.assertEqual(len(results), 3)

        # 驗證排名：SearchService (Doc 1) 得分最高，其次 LookupService (Doc 2)，最後 IndexRelatedService (Doc 3)
        self.assertEqual(results[0].symbol.name, "SearchService")
        self.assertEqual(results[1].symbol.name, "LookupService")
        self.assertEqual(results[2].symbol.name, "IndexRelatedService")
        self.assertGreater(results[0].score, results[1].score)
        self.assertGreater(results[1].score, results[2].score)

    @require(Requirement.LOGIC)
    def test_space_manager_thesaurus_loading(self):
        """FT-06: 驗證 SpaceManager.load_thesaurus_config 正確聚合同義詞、別名與關聯詞。"""
        sm = SpaceManager()
        cfg = sm.load_thesaurus_config()
        self.assertIsInstance(cfg, ThesaurusConfig)
        self.assertIsInstance(cfg.groups, list)
        self.assertIsInstance(cfg.aliases, dict)
        self.assertIsInstance(cfg.related, list)

        # load_thesaurus 向後相容
        groups = sm.load_thesaurus()
        self.assertIsInstance(groups, list)

    @require(Requirement.LOGIC)
    def test_cycle_and_infinite_loop_prevention(self):
        """ET-01: 驗證同義詞/別名循環 (A=>B=>A) 之單步展開與防無窮迴圈機制。"""
        engine = ThesaurusEngine(
            custom_groups=[["a", "b"], ["b", "c"], ["c", "a"]],
            custom_aliases={"a": ["b"], "b": ["a"]},
            custom_related=[["a", "b", "c"]],
        )
        expanded = engine.expand_query_weighted(["a"])
        terms = [t.term for t in expanded]
        # 詞條應完全去重
        self.assertEqual(len(terms), len(set(terms)))
        self.assertLessEqual(len(terms), 10)

    @require(Requirement.LOGIC)
    def test_max_weight_conflict_retention(self):
        """ET-02: 驗證多重路徑衝突時之最高權重保留 (Max-Weight Retention, 1.0 > 0.6 > 0.25)。"""
        # "parser" 是原始查詢詞 (1.0)，同時由 "compiler" 展開為關聯詞 (0.25) 與 "parse" 展開為同義詞 (0.6)
        engine = ThesaurusEngine(
            custom_groups=[["parse", "parser"]],
            custom_related=[["compiler", "parser"]],
        )
        # 輸入同時包含 "parser" 與 "compiler"
        expanded = engine.expand_query_weighted(["parser", "compiler"])
        term_map = {t.term: t for t in expanded}
        # "parser" 必須保持 1.0 (original)
        self.assertEqual(term_map["parser"].weight, 1.0)
        self.assertEqual(term_map["parser"].kind, "original")

    @require(Requirement.LOGIC)
    def test_malformed_and_empty_inputs(self):
        """ET-03: 驗證空值、純空白字元與畸形字串之邊界安全防護。"""
        engine = ThesaurusEngine(
            custom_groups=[["", "   ", None], ["ValidA", "ValidB"]],
            custom_aliases={" ": ["x"], "": ["y"], "valid_src": ["", "valid_tgt"]},
            custom_related=[["", "   "]],
        )
        # 空值與空白輸入
        self.assertEqual(engine.expand_query_weighted([]), [])
        self.assertEqual(engine.expand_query_weighted(["", "   "]), [])

        expanded = engine.expand_query_weighted(["valida"])
        terms = [t.term for t in expanded]
        self.assertIn("valida", terms)
        self.assertIn("validb", terms)

    @require(Requirement.LOGIC)
    def test_max_expanded_tier_prioritization(self):
        """ET-04: 驗證 max_expanded 數量截斷時優先保留高權重詞條。"""
        engine = ThesaurusEngine(
            custom_groups=[["query", "syn1", "syn2", "syn3"]],
            custom_aliases={"query": ["alias1", "alias2"]},
            custom_related=[["query", "rel1", "rel2", "rel3", "rel4"]],
        )
        # 限制 max_expanded = 4
        # 應包含: query (1.0), syn1 (0.6), syn2 (0.6), syn3 (0.6)
        # 不應溢出至更低優先順序的 rel 關聯詞
        expanded = engine.expand_query_weighted(["query"], max_expanded=4)
        self.assertEqual(len(expanded), 4)
        self.assertEqual(expanded[0].term, "query")
        self.assertEqual(expanded[0].weight, 1.0)
        for t in expanded[1:]:
            self.assertEqual(t.weight, 0.6)
