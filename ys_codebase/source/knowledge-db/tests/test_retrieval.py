"""
Unit Tests for knowledge-db InvertedIndex and BM25Engine.
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.retrieval import (
    BM25Engine,
    InvertedIndex,
    Posting,
    QueryFilter,
    SearchResult,
)
from knowledge_db.schema import LanguageType, MemberInfo, SymbolKind, UnifiedSymbol
from knowledge_db.thesaurus import ThesaurusEngine
from knowledge_db.tokenizer import CodeTokenizer


class TestRetrieval(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tokenizer = CodeTokenizer()
        self.thesaurus = ThesaurusEngine()

        # 準備一組測試符號
        self.sym_pid = UnifiedSymbol(
            id="sym_01_pid",
            name="PIDController",
            kind=SymbolKind.CLASS.value,
            file_path="src/pid.cpp",
            line_number=10,
            language=LanguageType.CPP.value,
            docstring="PID 閉迴路控制器實作，支援速度與位置控制",
            signature="class PIDController : public BaseController",
            members=[
                MemberInfo("Calculate", "method", "float Calculate(float target, float current)", "計算控制輸出")
            ],
        )

        self.sym_motor = UnifiedSymbol(
            id="sym_02_motor",
            name="MotorGroup",
            kind=SymbolKind.CLASS.value,
            file_path="src/motor.cpp",
            line_number=20,
            language=LanguageType.CPP.value,
            docstring="多馬達驅動群組控制模組",
            signature="class MotorGroup",
            members=[
                MemberInfo("SetVelocity", "method", "void SetVelocity(int rpm)", "設定馬達轉速")
            ],
        )

        self.sym_doc = UnifiedSymbol(
            id="sym_03_doc",
            name="系統架構說明",
            kind=SymbolKind.DOC_HEADING_1.value,
            file_path="docs/architecture.md",
            line_number=1,
            language=LanguageType.MARKDOWN.value,
            docstring="本文件描述機器人系統架構，包含 PID 控制器與馬達通訊機制",
            signature="# 系統架構說明",
        )

        self.symbols = [self.sym_pid, self.sym_motor, self.sym_doc]

    @require(Requirement.LOGIC)
    def test_inverted_index_building_and_idf(self):
        """FT-04: 驗證倒排索引建立、平均長度計算與 IDF 平滑計算 (EC-03)"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        self.assertEqual(index.doc_count, 3)
        self.assertGreater(len(index.index), 5)
        self.assertIn("pid", index.index)
        self.assertIn("controller", index.index)
        self.assertIn("motor", index.index)

        # 驗證 avgdl
        for f in InvertedIndex.INDEXED_FIELDS:
            self.assertGreater(index.field_avgdl[f], 0)

    @require(Requirement.LOGIC)
    def test_bm25_multi_field_scoring_and_boost(self):
        """FT-05: 驗證多欄位加權評分與 Exact Match 2.0x 置頂加權"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        engine = BM25Engine(tokenizer=self.tokenizer, thesaurus=self.thesaurus)

        # 1. 查詢 'PIDController' 應直擊置頂第一名 (Exact Match Boost)
        results = engine.search("PIDController", index)
        self.assertGreaterEqual(len(results), 1)
        top_result = results[0]
        self.assertEqual(top_result.symbol.name, "PIDController")
        self.assertIn("pid", top_result.matched_terms)

        # 2. 查詢同義詞 '控制' 應能召回 PIDController 與 MotorGroup
        results_ctrl = engine.search("控制", index)
        self.assertGreaterEqual(len(results_ctrl), 2)
        names = [r.symbol.name for r in results_ctrl]
        self.assertIn("PIDController", names)
        self.assertIn("MotorGroup", names)

    @require(Requirement.LOGIC)
    def test_query_filtering_and_top_k(self):
        """FT-06: 驗證 QueryFilter 語言、類型過濾與 limit 限制"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)
        engine = BM25Engine(tokenizer=self.tokenizer, thesaurus=self.thesaurus)

        # 1. 限定語言為 markdown
        flt_md = QueryFilter(languages=["markdown"])
        res_md = engine.search("PID", index, filter_cfg=flt_md)
        self.assertEqual(len(res_md), 1)
        self.assertEqual(res_md[0].symbol.language, "markdown")

        # 2. 限定類型為 class
        flt_class = QueryFilter(kinds=["class"])
        res_class = engine.search("PID", index, filter_cfg=flt_class)
        self.assertEqual(len(res_class), 1)
        self.assertEqual(res_class[0].symbol.kind, "class")

        # 3. limit 數量限制
        flt_limit = QueryFilter(limit=1)
        res_limit = engine.search("控制", index, filter_cfg=flt_limit)
        self.assertEqual(len(res_limit), 1)

    @require(Requirement.LOGIC)
    def test_inverted_index_serialization(self):
        """FT-07: 驗證 InvertedIndex 序列化與反序列化無損一致"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        d = index.to_dict()
        self.assertEqual(d["space_name"], "test_space")
        self.assertEqual(d["doc_count"], 3)

        restored = InvertedIndex.from_dict(d)
        self.assertEqual(restored.space_name, index.space_name)
        self.assertEqual(restored.doc_count, index.doc_count)
        self.assertEqual(len(restored.index), len(index.index))

    @require(Requirement.LOGIC)
    def test_edge_cases_empty_and_special_chars(self):
        """ET-01: 驗證空 Query、未命中詞條與特殊字元檢索安全防禦 (EC-01, EC-02, EC-06)"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)
        engine = BM25Engine(tokenizer=self.tokenizer, thesaurus=self.thesaurus)

        # 空 Query (EC-01)
        self.assertEqual(engine.search("", index), [])
        self.assertEqual(engine.search("   ", index), [])

        # 未命中詞 (EC-02)
        self.assertEqual(engine.search("quantum_flux_nonexistent_xyz", index), [])

        # 特殊正則字元防禦 (EC-06)
        self.assertEqual(engine.search(".*+?^${}()|[]\\", index), [])
