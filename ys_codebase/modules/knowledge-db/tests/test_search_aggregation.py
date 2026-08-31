"""
knowledge-db 檢索、副檔名過濾與 Top-N 動態聚合回填管線單元測試 (test_search_aggregation.py)
驗證 FT-05, FT-06, FT-07, FT-08
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.retrieval import BM25Engine, InvertedIndex, QueryFilter
from knowledge_db.schema import AggregatedFileResult, LanguageType, SymbolKind, UnifiedSymbol


class TestSearchAggregation(YSCBTestCase):
    """檢索過濾、積分聚合與回填管線測試"""

    def setUp(self):
        super().setUp()
        self.engine = BM25Engine()
        self.index = InvertedIndex(space_name="test")

        # 模擬 3 個不同檔案中的多個 Symbols
        symbols = [
            # File 1: Python file with 3 matching methods
            UnifiedSymbol(
                id="f1_cls",
                name="ParserEngine",
                kind=SymbolKind.CLASS.value,
                file_path="src/engine.py",
                line_number=1,
                end_line=50,
                language=LanguageType.PYTHON.value,
                signature="class ParserEngine",
                docstring="Core parsing and compilation engine",
            ),
            UnifiedSymbol(
                id="f1_m1",
                name="ParserEngine.parse_tokens",
                kind=SymbolKind.METHOD.value,
                file_path="src/engine.py",
                line_number=10,
                end_line=20,
                language=LanguageType.PYTHON.value,
                signature="def parse_tokens(self, text: str)",
                docstring="Parse tokens from text stream",
            ),
            UnifiedSymbol(
                id="f1_m2",
                name="ParserEngine.tokenize_stream",
                kind=SymbolKind.METHOD.value,
                file_path="src/engine.py",
                line_number=25,
                end_line=35,
                language=LanguageType.PYTHON.value,
                signature="def tokenize_stream(self)",
                docstring="Tokenize input stream",
            ),
            # File 2: C++ file with 2 matching functions
            UnifiedSymbol(
                id="f2_fn1",
                name="ParseASTNode",
                kind=SymbolKind.FUNCTION.value,
                file_path="src/native_parser.cpp",
                line_number=5,
                end_line=15,
                language=LanguageType.CPP.value,
                signature="ASTNode* ParseASTNode(const char* src)",
                docstring="Parse AST node from source buffer",
            ),
            UnifiedSymbol(
                id="f2_fn2",
                name="ValidateAST",
                kind=SymbolKind.FUNCTION.value,
                file_path="src/native_parser.cpp",
                line_number=20,
                end_line=30,
                language=LanguageType.CPP.value,
                signature="bool ValidateAST(ASTNode* node)",
                docstring="Validate AST node structure",
            ),
            # File 3: Markdown documentation
            UnifiedSymbol(
                id="f3_doc",
                name="Parser Architecture Guide",
                kind=SymbolKind.DOC_HEADING_1.value,
                file_path="docs/parser_guide.md",
                line_number=1,
                end_line=20,
                language=LanguageType.MARKDOWN.value,
                signature="# Parser Architecture Guide",
                docstring="Detailed documentation on how ParserEngine works",
            ),
        ]
        self.index.build(symbols, space="test")

    @require(Requirement.LOGIC)
    def test_ft_05_ftype_filtering(self):
        """FT-05: --ftype 檔案類型過濾"""
        # 1. 僅搜尋 Python
        flt_py = QueryFilter(ftypes=["py"], limit=10)
        res_py = self.engine.search_aggregated("parse", self.index, filter_cfg=flt_py)
        self.assertTrue(all(r.file_path.endswith(".py") for r in res_py))
        self.assertEqual(len(res_py), 1)

        # 2. 僅搜尋 C++ / H
        flt_cpp = QueryFilter(ftypes=["c|cpp|h"], limit=10)
        res_cpp = self.engine.search_aggregated("parse", self.index, filter_cfg=flt_cpp)
        self.assertTrue(all(r.file_path.endswith(".cpp") for r in res_cpp))
        self.assertEqual(len(res_cpp), 1)

        # 3. 僅搜尋 Markdown
        flt_md = QueryFilter(ftypes=[".md"], limit=10)
        res_md = self.engine.search_aggregated("parser", self.index, filter_cfg=flt_md)
        self.assertTrue(all(r.file_path.endswith(".md") for r in res_md))
        self.assertEqual(len(res_md), 1)

    @require(Requirement.LOGIC)
    def test_ft_06_score_aggregation_and_top3_cap(self):
        """FT-06: 同檔案積分累加 (Max + 0.2*Rest) 與內部 Top-3 限制"""
        flt = QueryFilter(limit=10)
        results = self.engine.search_aggregated("parse token stream", self.index, filter_cfg=flt, alpha=0.2)
        self.assertTrue(len(results) >= 2)

        # 第一個檔案應該是 src/engine.py (3 個命中)
        py_node = next((r for r in results if r.file_path == "src/engine.py"), None)
        self.assertIsNotNone(py_node)
        self.assertLessEqual(len(py_node.items), 3)

        # 驗證分數公式：total_score 應該大於單一 max score
        scores = [item.score for item in py_node.items]
        max_s = max(scores)
        rest_s = sum(scores) - max_s
        expected_score = max_s + 0.2 * rest_s
        self.assertAlmostEqual(py_node.total_score, expected_score, places=4)

    @require(Requirement.LOGIC)
    def test_ft_07_top_n_refill_pipeline(self):
        """FT-07: Top-N 動態聚合回填管線"""
        flt = QueryFilter(limit=2)
        results = self.engine.search_aggregated("parse", self.index, filter_cfg=flt)
        self.assertEqual(len(results), 2)
        file_paths = {r.file_path for r in results}
        self.assertEqual(len(file_paths), 2)

    @require(Requirement.LOGIC)
    def test_ft_08_json_and_model_serialization(self):
        """FT-08: 結構化模型序列化"""
        flt = QueryFilter(limit=5)
        results = self.engine.search_aggregated("parser", self.index, filter_cfg=flt)
        for r in results:
            d = r.to_dict()
            self.assertIn("file_path", d)
            self.assertIn("total_score", d)
            self.assertIn("items", d)
            self.assertIn("language", d)
