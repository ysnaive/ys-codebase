"""
Unit and Integration Tests for knowledge-db InvertedIndex, BM25Engine, Tokenizer, HybridSearchEngine, and Aggregation.
Unified Suite consolidating retrieval, search aggregation, tokenizer, embedding, and hybrid search tests.
"""

import gzip
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import numpy as np

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.embedding import EmbeddingService, VectorIndex
from knowledge_db.exceptions import KnowledgeDBError, SchemaValidationError
from knowledge_db.hybrid import HybridSearchEngine
from knowledge_db.retrieval import (
    BM25Engine,
    CodeSnippet,
    InvertedIndex,
    Posting,
    QueryFilter,
    SearchResult,
    SnippetExtractor,
)
from knowledge_db.schema import (
    LanguageType,
    MemberInfo,
    SymbolKind,
    UnifiedSymbol,
)
from knowledge_db.tokenizer import MultilingualTokenizer
from tests import write_text_and_advance_mtime


class DummyIndex:
    """Mock InvertedIndex & BM25Engine for hybrid unit tests"""

    def __init__(self, symbols=None, hits=None):
        self.symbols = symbols or {}
        self.hits = hits or []

    def search(self, query: str = "", index: object = None, filter_cfg: object = None):
        limit = getattr(filter_cfg, "limit", 10) if filter_cfg else 10
        ftypes = getattr(filter_cfg, "ftypes", None) if filter_cfg else None
        spaces = getattr(filter_cfg, "spaces", None) if filter_cfg else None
        kinds = getattr(filter_cfg, "kinds", None) if filter_cfg else None
        languages = getattr(filter_cfg, "languages", None) if filter_cfg else None

        norm_ftypes = (
            {f.strip().lstrip(".").lower() for f in ftypes} if ftypes else None
        )
        out = []
        for h in self.hits:
            sym = self.symbols.get(h["doc_id"])
            if not sym:
                continue
            if norm_ftypes:
                ext = (
                    Path(sym.file_path).suffix.lstrip(".").lower()
                    if sym.file_path
                    else ""
                )
                if ext not in norm_ftypes:
                    continue
            if spaces and not any(s in spaces for s in getattr(sym, "spaces", [])):
                continue
            if kinds and sym.kind not in kinds:
                continue
            if languages and sym.language not in languages:
                continue
            sym_spaces = getattr(sym, "spaces", None) or ["default"]
            out.append(
                SearchResult(
                    symbol=sym,
                    score=h["score"],
                    space=sym_spaces[0],
                    matched_terms=h.get("matched_terms", []),
                )
            )
        return out[:limit]


class TestRetrieval(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tokenizer = MultilingualTokenizer()

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
                MemberInfo(
                    "Calculate",
                    "method",
                    "float Calculate(float target, float current)",
                    "計算控制輸出",
                )
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
                MemberInfo(
                    "SetVelocity", "method", "void SetVelocity(int rpm)", "設定馬達轉速"
                )
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
        """驗證倒排索引建立、平均長度計算與 IDF 平滑計算"""
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

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_bm25_multi_field_scoring_and_boost(self):
        """驗證多欄位加權評分與 Exact Match 2.0x 置頂加權"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        engine = BM25Engine(tokenizer=self.tokenizer)

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

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_query_filtering_and_top_k(self):
        """驗證 QueryFilter 語言、類型過濾與 limit 限制"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)
        engine = BM25Engine(tokenizer=self.tokenizer)

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

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inverted_index_serialization(self):
        """驗證 InvertedIndex 序列化與反序列化無損一致"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        d = index.to_dict()
        self.assertEqual(d["space_name"], "test_space")
        self.assertEqual(d["doc_count"], 3)

        restored = InvertedIndex.from_dict(d)
        self.assertEqual(restored.space_name, index.space_name)
        self.assertEqual(restored.doc_count, index.doc_count)
        self.assertEqual(len(restored.index), len(index.index))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_edge_cases_empty_and_special_chars(self):
        """驗證空 Query、未命中詞條與特殊字元檢索安全防禦"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)
        engine = BM25Engine(tokenizer=self.tokenizer)

        # 空 Query
        self.assertEqual(engine.search("", index), [])
        self.assertEqual(engine.search("   ", index), [])

        # 未命中詞
        self.assertEqual(engine.search("quantum_flux_nonexistent_xyz", index), [])

        # 特殊正則字元防禦
        self.assertEqual(engine.search(".*+?^${}()|[]\\", index), [])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_symbol_pool_normalization_and_binary_gzip_io(self):
        """驗證 InvertedIndex 符號池去重與二進位 Gzip 讀寫無損還原"""
        index = InvertedIndex(space_name="test_space")
        index.build(self.symbols, tokenizer=self.tokenizer)

        # 1. 驗證符號池去重
        self.assertEqual(len(index.symbols), 3)
        self.assertIn("sym_01_pid", index.symbols)
        self.assertEqual(index.get_symbol("sym_01_pid").name, "PIDController")

        # 驗證 Posting 字典不內嵌 symbol
        first_term = list(index.index.keys())[0]
        first_posting = index.index[first_term][0]
        p_dict = first_posting.to_dict()
        self.assertNotIn("symbol", p_dict)
        self.assertIn("doc_id", p_dict)

        # 2. 驗證二進位 Gzip 儲存與還原
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_path = Path(temp_dir) / "test.index.bin.gz"
            index.save_binary(bin_path)

            self.assertTrue(bin_path.exists())
            self.assertGreater(bin_path.stat().st_size, 0)

            # 讀取還原
            restored = InvertedIndex.load_binary(bin_path)
            self.assertEqual(restored.space_name, "test_space")
            self.assertEqual(restored.doc_count, 3)
            self.assertEqual(len(restored.symbols), 3)
            self.assertEqual(len(restored.index), len(index.index))

            # 驗證還原後搜尋能力一致
            engine = BM25Engine(tokenizer=self.tokenizer)
            res = engine.search("PIDController", restored)
            self.assertGreaterEqual(len(res), 1)
            self.assertEqual(res[0].symbol.name, "PIDController")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_corrupted_binary_cache_fallback(self):
        """驗證損毀之二進位檔案讀取與非字典結構拋出明確異常"""
        with tempfile.TemporaryDirectory() as temp_dir:
            corrupt_path = Path(temp_dir) / "corrupt.index.bin.gz"
            corrupt_path.write_bytes(b"not a valid gzip or pickle data 123456789")

            with self.assertRaises((OSError, EOFError, SchemaValidationError)):
                InvertedIndex.load_binary(corrupt_path)

        with self.assertRaises(SchemaValidationError):
            InvertedIndex.from_dict("not_a_dict")  # type: ignore[arg-type]

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_snippet_extractor_and_code_snippet(self):
        """驗證 SnippetExtractor 安全讀取、截斷與編碼容錯"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            code_file = temp_path / "sample.py"
            code_file.write_text(
                "def line_1():\n"
                "    pass\n"
                "\n"
                "def target_func(a, b):\n"
                "    '''Calculate sum'''\n"
                "    c = a + b\n"
                "    return c\n"
                "\n"
                "def line_9():\n"
                "    return True\n",
                encoding="utf-8",
            )

            extractor = SnippetExtractor(workspace_root=temp_path, max_lines=6)

            # 1. 正常提取
            snip = extractor.extract(
                file_path="sample.py",
                line_number=4,
                context_before=1,
                context_after=3,
                docstring="Calculate sum",
            )
            self.assertIsInstance(snip, CodeSnippet)
            self.assertIsNone(snip.error)
            self.assertEqual(snip.target_line, 4)
            self.assertEqual(snip.docstring_summary, "Calculate sum")
            self.assertGreater(len(snip.lines), 0)
            formatted = snip.format_text()
            self.assertIn("target_func", formatted)
            self.assertIn(">", formatted)

            # 2. 序列化測試
            s_dict = snip.to_dict()
            self.assertEqual(s_dict["target_line"], 4)
            self.assertIn("raw_code", s_dict)
            self.assertIn("target_func", s_dict["raw_code"])

            # 3. 檔案不存在測試
            snip_missing = extractor.extract("non_existent.py", line_number=10)
            self.assertIsNotNone(snip_missing.error)
            self.assertEqual(snip_missing.error, "File not found")
            self.assertIn("[Snippet Unavailable", snip_missing.format_text())

            # 4. 行號超界測試
            snip_oob = extractor.extract("sample.py", line_number=999)
            self.assertIsNone(snip_oob.error)
            self.assertLessEqual(snip_oob.end_line, 10)

            # 5. 超出行數截斷
            snip_trunc = extractor.extract(
                "sample.py", line_number=1, context_before=0, context_after=9
            )
            self.assertTrue(snip_trunc.is_truncated)
            self.assertLessEqual(len(snip_trunc.lines), 6)

            # 6. 二進位/非 UTF-8 容錯與行數斷言
            bin_file = temp_path / "binary.dat"
            bin_file.write_bytes(b"\xff\xfe\x00\x12\x34\x56\x78\x90")
            snip_bin = extractor.extract("binary.dat", line_number=1)
            self.assertIsNone(snip_bin.error)
            self.assertGreaterEqual(len(snip_bin.lines), 1)

        self.mark_passed()


class TestSearchAggregation(YSCBTestCase):
    """檢索過濾、積分聚合與回填管線測試"""

    def setUp(self):
        super().setUp()
        self.engine = BM25Engine()
        self.index = InvertedIndex(space_name="test")

        symbols = [
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
            UnifiedSymbol(
                id="f2_fn1",
                name="ParseASTNode",
                kind=SymbolKind.FUNCTION.value,
                file_path="src/native_parser.cpp",
                line_number=5,
                end_line=15,
                language=LanguageType.CPP.value,
                signature="ASTNode* ParseASTNode(const char* src)",
                docstring="Parse AST node from token source buffer",
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
    def test_ftype_filtering(self):
        """驗證 --ftype 檔案類型過濾"""
        flt_py = QueryFilter(ftypes=["py"], limit=10)
        res_py = self.engine.search_aggregated("parse", self.index, filter_cfg=flt_py)
        self.assertTrue(all(r.file_path.endswith(".py") for r in res_py))
        self.assertEqual(len(res_py), 1)

        flt_cpp = QueryFilter(ftypes=["c|cpp|h"], limit=10)
        res_cpp = self.engine.search_aggregated(
            "parse", self.index, filter_cfg=flt_cpp
        )
        self.assertTrue(all(r.file_path.endswith(".cpp") for r in res_cpp))
        self.assertEqual(len(res_cpp), 1)

        flt_md = QueryFilter(ftypes=[".md"], limit=10)
        res_md = self.engine.search_aggregated("parser", self.index, filter_cfg=flt_md)
        self.assertTrue(all(r.file_path.endswith(".md") for r in res_md))
        self.assertEqual(len(res_md), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_score_aggregation_and_top3_cap(self):
        """驗證同檔案積分累加 (Max + 0.2*Rest) 與內部 Top-3 限制"""
        flt = QueryFilter(limit=10)
        results = self.engine.search_aggregated(
            "parse token stream", self.index, filter_cfg=flt, alpha=0.2
        )
        self.assertGreaterEqual(len(results), 2)

        py_node = next((r for r in results if r.file_path == "src/engine.py"), None)
        self.assertIsNotNone(py_node)
        self.assertLessEqual(len(py_node.items), 3)

        scores = [item.score for item in py_node.items]
        max_s = max(scores)
        rest_s = sum(scores) - max_s
        expected_score = max_s + 0.2 * rest_s
        self.assertAlmostEqual(py_node.total_score, expected_score, places=4)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_top_n_refill_pipeline(self):
        """驗證 Top-N 動態聚合回填管線"""
        flt = QueryFilter(limit=2)
        results = self.engine.search_aggregated("parse", self.index, filter_cfg=flt)
        self.assertEqual(len(results), 2)
        file_paths = {r.file_path for r in results}
        self.assertEqual(len(file_paths), 2)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_json_and_model_serialization(self):
        """驗證結構化模型序列化"""
        flt = QueryFilter(limit=5)
        results = self.engine.search_aggregated("parser", self.index, filter_cfg=flt)
        for r in results:
            d = r.to_dict()
            self.assertIn("file_path", d)
            self.assertIn("total_score", d)
            self.assertIn("items", d)
            self.assertIn("language", d)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_compound_token_coverage_filter_in_aggregated(self):
        """驗證 >= 3 sub-tokens 複合字查詢於 search_aggregated 強制過濾覆蓋率 < 50% 之單一子詞噪音"""
        flt = QueryFilter(limit=10)
        noise_results = self.engine.search_aggregated(
            "parse unknownalpha unknownbeta", self.index, filter_cfg=flt
        )
        self.assertEqual(
            noise_results,
            [],
            "僅命中 1/3 子詞 (< 50%) 之候選符號應於 search_aggregated 被強制過濾",
        )

        valid_results = self.engine.search_aggregated(
            "parse token stream", self.index, filter_cfg=flt
        )
        hit_files = {r.file_path for r in valid_results}
        self.assertIn("src/engine.py", hit_files)
        self.assertIn("src/native_parser.cpp", hit_files)
        self.assertNotIn("docs/parser_guide.md", hit_files)

        self.mark_passed()


class TestTokenizer(YSCBTestCase):
    """代碼分詞器 (CamelCase / snake_case / CJK 滑動窗口) 測試。"""

    @require(Requirement.LOGIC)
    def test_code_identifier_tokenization(self):
        tok = MultilingualTokenizer()

        res1 = tok.tokenize("PIDController")
        self.assertIn("pid", res1)
        self.assertIn("controller", res1)
        self.assertIn("pidcontroller", res1)

        res2 = tok.tokenize("getHTTPResponse")
        self.assertIn("get", res2)
        self.assertIn("http", res2)
        self.assertIn("response", res2)

        res3 = tok.tokenize("user_profile_manager_v5")
        self.assertIn("user", res3)
        self.assertIn("profile", res3)
        self.assertIn("manager", res3)
        self.assertIn("v5", res3)

        res4 = tok.tokenize("def calculate_pid_velocity(target_rpm: float) -> bool:")
        self.assertIn("calculate", res4)
        self.assertIn("pid", res4)
        self.assertIn("velocity", res4)
        self.assertIn("target", res4)
        self.assertIn("rpm", res4)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cjk_and_stopword_tokenization(self):
        tok = MultilingualTokenizer()

        res1 = tok.tokenize("狀態機更新頻率")
        self.assertIn("狀", res1)
        self.assertIn("態", res1)
        self.assertIn("機", res1)
        self.assertIn("狀態", res1)
        self.assertIn("態機", res1)
        self.assertIn("更新", res1)
        self.assertIn("頻率", res1)

        res2 = tok.tokenize("在 SpaceManager 中建立 UnifiedSymbol 實例")
        self.assertIn("spacemanager", res2)
        self.assertIn("unifiedsymbol", res2)
        self.assertIn("建", res2)
        self.assertIn("立", res2)
        self.assertIn("建立", res2)
        self.assertNotIn("在", res2)

        self.assertEqual(tok.tokenize(""), [])
        self.assertEqual(tok.tokenize("   "), [])
        self.assertEqual(tok.tokenize("!@#$%^&*()_+=-`~[]{}|;':\",.<>?/"), [])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_multilingual_tokenizer_advanced(self):
        """驗證 MultilingualTokenizer 中英混排無縫切分、tokenize_unique 與 keep_original_identifier=False"""
        tok = MultilingualTokenizer()

        res1 = tok.tokenize("解析InvertedIndex倒排索引")
        self.assertIn("inverted", res1)
        self.assertIn("index", res1)
        self.assertIn("invertedindex", res1)
        self.assertIn("解析", res1)
        self.assertIn("倒排", res1)
        self.assertIn("索引", res1)

        parts = tok._split_identifier("TreeSitterDriver.extract_imports")
        self.assertIn("tree", parts)
        self.assertIn("imports", parts)

        # 驗證 tokenize_unique 保序去重
        dup_tokens = tok.tokenize("PIDController PIDController pid")
        uniq_tokens = tok.tokenize_unique("PIDController PIDController pid")
        self.assertGreater(len(dup_tokens), len(uniq_tokens))
        self.assertEqual(len(uniq_tokens), len(set(uniq_tokens)))
        self.assertEqual(uniq_tokens[0], "pid")

        # 驗證 keep_original_identifier=False 不保留完整複合詞
        tok_no_orig = MultilingualTokenizer(keep_original_identifier=False)
        no_orig_res = tok_no_orig.tokenize("PIDController")
        self.assertIn("pid", no_orig_res)
        self.assertIn("controller", no_orig_res)
        self.assertNotIn("pidcontroller", no_orig_res)

        self.mark_passed()


class TestEmbeddingServiceAndVectorIndex(YSCBTestCase):
    """驗證 EmbeddingService 與 VectorIndex"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.service = EmbeddingService(cache_dir=self.cache_dir, mock_mode=True)

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_embedding(self):
        """驗證向量生成、餘弦相似度與二進位快取持久化"""
        self.assertTrue(self.service.is_available)
        texts = ["hello world", "inverted index search", "中文倒排索引檢索"]
        embeddings = self.service.embed_texts(texts)

        self.assertEqual(embeddings.shape, (3, self.service.dimension))
        for vec in embeddings:
            norm = np.linalg.norm(vec)
            self.assertAlmostEqual(norm, 1.0, places=4)

        query_vec = self.service.embed_query("inverted index")

        doc_ids = ["doc_1", "doc_2", "doc_3"]
        v_idx = VectorIndex()
        v_idx.build(doc_ids, embeddings)
        hits = v_idx.search(query_vec, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertIn(hits[0][0], doc_ids)

        cache_file = self.cache_dir / "vectors.bin.gz"
        v_idx.save_binary(cache_file)
        self.assertTrue(cache_file.exists())

        loaded_idx = VectorIndex.load_binary(cache_file)
        self.assertEqual(loaded_idx.doc_ids, doc_ids)
        self.assertEqual(loaded_idx.vectors.shape, embeddings.shape)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_corrupted_cache(self):
        """本地向量快取損毀時捕獲驗證失敗並安全降級"""
        corrupted_file = self.cache_dir / "bad_vectors.bin.gz"
        with gzip.open(corrupted_file, "wb") as f:
            f.write(b"NOT_A_VALID_PICKLE_DATA")

        loaded = VectorIndex.load_binary(corrupted_file)
        self.assertEqual(len(loaded.doc_ids), 0)
        self.assertIsNone(loaded.vectors)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_long_content(self):
        """512+ tokens 超長內容之安全切片與特徵提煉"""
        long_text = "token " * 1000
        vec = self.service.embed_query(long_text)
        self.assertEqual(vec.shape, (self.service.dimension,))
        self.assertAlmostEqual(np.linalg.norm(vec), 1.0, places=4)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_batching_and_thread_capping(self):
        """驗證 EmbeddingService 於 mock_mode=False 下之真实 batch_size=32 切分 ([32, 32, 6]) 與 L2 正規化"""
        real_cache = self.cache_dir / "real_batch_cache"
        model_dir = real_cache / "models--BAAI--bge-small-zh-v1.5"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.onnx").write_bytes(b"FAKE_ONNX_WEIGHTS")

        svc = EmbeddingService(
            cache_dir=real_cache,
            mock_mode=False,
            max_threads=2,
            enable_vector_search=False,
        )
        self.assertTrue(svc.is_model_downloaded())

        recorded_chunk_sizes = []

        class _FakeModel:
            embedding_size = 512

            def embed(self, chunk, batch_size=32):
                recorded_chunk_sizes.append(len(chunk))
                for idx in range(len(chunk)):
                    vec = np.ones(512, dtype=np.float32) * float(idx + 1)
                    yield vec

        svc._model = _FakeModel()
        svc._dimension = 512
        svc._is_available = True
        svc._init_attempted = True

        texts = [f"test text {i}" for i in range(70)]
        with patch("knowledge_db.embedding.time.sleep"):
            embeddings = svc.embed_texts(texts, batch_size=32)

        self.assertEqual(recorded_chunk_sizes, [32, 32, 6])
        self.assertEqual(embeddings.shape, (70, 512))
        norms = np.linalg.norm(embeddings, axis=1)
        np.testing.assert_allclose(norms, np.ones(70, dtype=np.float32), rtol=1e-5)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dynamic_dimension_without_constant(self):
        """驗證 DEFAULT_EMBEDDING_DIM 徹底淘汰，dimension 動態解析為 512 (SSOT)"""
        import knowledge_db.embedding as emb_mod

        self.assertFalse(hasattr(emb_mod, "DEFAULT_EMBEDDING_DIM"))
        self.assertEqual(self.service.dimension, 512)
        minilm_svc = EmbeddingService(
            model_name="sentence-transformers/all-MiniLM-L6-v2", mock_mode=True
        )
        self.assertEqual(minilm_svc.dimension, 384)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_embedding_last_error_capture(self):
        """驗證真實觸發 _init_model() 時捕獲載入異常寫入 last_error，且模型權重移除後自動重置 _init_attempted"""
        err_cache = self.cache_dir / "err_model_cache"
        model_dir = err_cache / "models--BAAI--bge-small-zh-v1.5"
        model_dir.mkdir(parents=True, exist_ok=True)
        fake_onnx = model_dir / "model.onnx"
        fake_onnx.write_bytes(b"CORRUPT_ONNX_HEADER")

        class _BrokenTextEmbedding:
            @staticmethod
            def list_supported_models():
                return [{"model": "BAAI/bge-small-zh-v1.5"}]

            def __init__(self, *args, **kwargs):
                raise RuntimeError("Fake FastEmbed missing DLL (WinError 1114)")

        fake_fastembed = SimpleNamespace(TextEmbedding=_BrokenTextEmbedding)
        failing_svc = EmbeddingService(
            cache_dir=err_cache,
            mock_mode=False,
            enable_vector_search=False,
        )
        with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
            self.assertFalse(failing_svc.is_available)

        self.assertTrue(failing_svc._init_attempted)
        self.assertIsNotNone(failing_svc.last_error)
        self.assertEqual(failing_svc.last_error["error_type"], "RuntimeError")
        self.assertIn("WinError 1114", failing_svc.last_error["message"])

        # 驗證當權重先載入成功、後續磁碟權重檔被刪除時，is_available 重置 _init_attempted 並更新為 ModelNotFoundLocally
        failing_svc._is_available = True
        failing_svc._verified_onnx_path = fake_onnx
        fake_onnx.unlink()
        self.assertFalse(failing_svc.is_available)
        self.assertEqual(failing_svc.last_error["error_type"], "ModelNotFoundLocally")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_model_download_and_embed_texts_probe(self):
        """驗證 download_model 成功與失敗拋出 KnowledgeDBError，以及 embed_texts_probe 三種回傳模式"""
        dl_cache = self.cache_dir / "dl_cache"

        class _MockTextEmbedding:
            embedding_size = 512

            def __init__(self, model_name="", cache_dir="", **kwargs):
                p = Path(cache_dir) / "models--BAAI--bge-small-zh-v1.5"
                p.mkdir(parents=True, exist_ok=True)
                (p / "model.onnx").write_bytes(b"DOWNLOADED_ONNX")

            def embed(self, texts, batch_size=32):
                for _ in texts:
                    yield np.ones(512, dtype=np.float32)

        fake_fastembed = SimpleNamespace(TextEmbedding=_MockTextEmbedding)
        svc = EmbeddingService(
            cache_dir=dl_cache, mock_mode=False, enable_vector_search=False
        )
        with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
            self.assertTrue(svc.download_model(force=True))
            self.assertTrue(svc.is_available)
            self.assertEqual(svc.dimension, 512)

        # 驗證 download_model 失敗時拋出 KnowledgeDBError 並記錄 last_error
        class _FailingDownloadEmbedding:
            def __init__(self, *args, **kwargs):
                raise OSError("Network unreachable during model download")

        svc_fail = EmbeddingService(
            cache_dir=self.cache_dir / "dl_fail",
            mock_mode=False,
            enable_vector_search=False,
        )
        with patch.dict(
            sys.modules,
            {"fastembed": SimpleNamespace(TextEmbedding=_FailingDownloadEmbedding)},
        ):
            with self.assertRaises(KnowledgeDBError):
                svc_fail.download_model(force=True)
        self.assertIsNotNone(svc_fail.last_error)
        self.assertEqual(svc_fail.last_error["error_type"], "OSError")

        # 驗證 embed_texts_probe 空輸入、指定 total_count 與未指定 total_count
        empty_vecs, empty_est = self.service.embed_texts_probe([], total_count=20)
        self.assertEqual(empty_vecs.shape, (0, 512))
        self.assertEqual(empty_est, 0.0)

        empty_vecs3, e_elapsed, e_unit = self.service.embed_texts_probe([])
        self.assertEqual(empty_vecs3.shape, (0, 512))
        self.assertEqual(e_elapsed, 0.0)
        self.assertEqual(e_unit, 0.0)

        sample_texts = [f"probe item {i}" for i in range(12)]
        p_vecs, est_total = self.service.embed_texts_probe(
            sample_texts, probe_size=5, total_count=50
        )
        self.assertEqual(p_vecs.shape, (5, 512))
        self.assertGreaterEqual(est_total, 0.0)

        p_vecs2, elapsed, unit_sec = self.service.embed_texts_probe(
            sample_texts, probe_size=4
        )
        self.assertEqual(p_vecs2.shape, (4, 512))
        self.assertGreaterEqual(elapsed, 0.0)
        self.assertGreaterEqual(unit_sec, 0.0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_model_name_normalization(self):
        """驗證 normalize_model_name 自動補齊前綴與容錯"""
        self.assertEqual(
            EmbeddingService.normalize_model_name("bge-small-zh-v1.5"),
            "BAAI/bge-small-zh-v1.5",
        )
        self.assertEqual(
            EmbeddingService.normalize_model_name("all-MiniLM-L6-v2"),
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        self.assertEqual(
            EmbeddingService.normalize_model_name("BAAI/bge-small-zh-v1.5"),
            "BAAI/bge-small-zh-v1.5",
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_vector_index_dimension_compatibility(self):
        """驗證 VectorIndex.is_compatible_with 維度動態相容檢核"""
        idx = VectorIndex(model_name="BAAI/bge-small-zh-v1.5", dim=512)
        idx.build(["doc_1"], np.ones((1, 512), dtype=np.float32))
        self.assertTrue(idx.is_compatible_with("BAAI/bge-small-zh-v1.5", 512))
        self.assertFalse(idx.is_compatible_with("BAAI/bge-small-zh-v1.5", 384))
        self.assertFalse(
            idx.is_compatible_with("sentence-transformers/all-MiniLM-L6-v2", 512)
        )
        self.mark_passed()


class TestHybridSearchEngine(YSCBTestCase):
    """驗證 HybridSearchEngine 與剛性降級"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.service = EmbeddingService(cache_dir=self.cache_dir, mock_mode=True)

        self.sym_a = UnifiedSymbol(
            id="sym_a",
            name="InvertedIndex",
            kind=SymbolKind.CLASS,
            file_path="src/retrieval.py",
            line_number=10,
            language="python",
            signature="class InvertedIndex",
            docstring="倒排索引資料結構",
        )
        self.sym_b = UnifiedSymbol(
            id="sym_b",
            name="BM25Engine",
            kind=SymbolKind.CLASS,
            file_path="src/engine.py",
            line_number=20,
            language="python",
            signature="class BM25Engine",
            docstring="BM25 檢索引擎",
        )
        self.sym_c = UnifiedSymbol(
            id="sym_c",
            name="Tokenizer",
            kind=SymbolKind.CLASS,
            file_path="src/tok.py",
            line_number=30,
            language="python",
            signature="class Tokenizer",
            docstring="分詞器",
        )

        self.symbols = {"sym_a": self.sym_a, "sym_b": self.sym_b, "sym_c": self.sym_c}

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_rrf_fusion(self):
        """驗證 HybridSearchEngine RRF 融合排序邏輯與權重計算"""
        bm25_hits = [
            {"doc_id": "sym_a", "score": 10.5, "matched_terms": ["index"]},
            {"doc_id": "sym_b", "score": 8.0, "matched_terms": ["engine"]},
        ]
        dummy_index = DummyIndex(symbols=self.symbols, hits=bm25_hits)

        vec_index = VectorIndex()
        vecs = self.service.embed_texts(["index", "engine"])
        vec_index.build(["sym_b", "sym_a"], vecs)

        engine = HybridSearchEngine(
            inverted_index=dummy_index,
            vector_index=vec_index,
            embedding_service=self.service,
            bm25_engine=dummy_index,
            rrf_k=60,
            weight_lexical=0.5,
            weight_vector=0.5,
        )

        lexical_ranks = {"sym_a": 1, "sym_b": 2}
        vector_ranks = {"sym_b": 1, "sym_a": 2}
        rrf_scores = engine.compute_rrf(lexical_ranks, vector_ranks)

        expected_a = 0.5 / 61.0 + 0.5 / 62.0
        expected_b = 0.5 / 62.0 + 0.5 / 61.0
        self.assertAlmostEqual(rrf_scores["sym_a"], expected_a, places=6)
        self.assertAlmostEqual(rrf_scores["sym_b"], expected_b, places=6)

        results = engine.search("inverted index", limit=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["mode"], "hybrid_rrf")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_fallback(self):
        """驗證雙軌剛性降級守門：lexical_only=True 或向量未就緒時退化純 BM25"""
        bm25_hits = [
            {"doc_id": "sym_a", "score": 10.5, "matched_terms": ["index"]},
        ]
        dummy_index = DummyIndex(symbols=self.symbols, hits=bm25_hits)

        # 情況 1: lexical_only=True
        engine = HybridSearchEngine(
            inverted_index=dummy_index,
            vector_index=VectorIndex(),
            embedding_service=self.service,
            bm25_engine=dummy_index,
        )
        res_lexical = engine.search("index", lexical_only=True)
        self.assertEqual(len(res_lexical), 1)
        self.assertEqual(res_lexical[0]["mode"], "lexical_bm25")
        self.assertEqual(res_lexical[0]["symbol"].name, "InvertedIndex")

        # 情況 2: vector_index 為空
        res_no_vec = engine.search("index", lexical_only=False)
        self.assertEqual(len(res_no_vec), 1)
        self.assertEqual(res_no_vec[0]["mode"], "lexical_bm25")

        # 情況 3: embedding_service 為 None
        engine_no_svc = HybridSearchEngine(
            inverted_index=dummy_index,
            vector_index=None,
            embedding_service=None,
            bm25_engine=dummy_index,
        )
        self.assertFalse(engine_no_svc.is_vector_available)
        res_no_svc = engine_no_svc.search("index", lexical_only=False)
        self.assertEqual(len(res_no_svc), 1)
        self.assertEqual(res_no_svc[0]["mode"], "lexical_bm25")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_empty_query(self):
        """驗證空字串、純空白與無效輸入安全防護"""
        dummy_empty = DummyIndex(symbols=self.symbols, hits=[])
        engine = HybridSearchEngine(
            inverted_index=dummy_empty,
            vector_index=VectorIndex(),
            embedding_service=self.service,
            bm25_engine=dummy_empty,
        )
        self.assertEqual(engine.search(""), [])
        self.assertEqual(engine.search("   "), [])
        self.assertEqual(engine.search(None), [])  # type: ignore[arg-type]

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hybrid_search_multi_extension_filtering(self):
        """驗證真實 InvertedIndex + BM25Engine + VectorIndex 下多副檔名清單、逗號與直線分隔過濾"""
        tok = MultilingualTokenizer()
        real_idx = InvertedIndex(space_name="unified")

        sym_py = UnifiedSymbol(
            id="sym_py",
            name="IndexProcessor",
            kind=SymbolKind.CLASS.value,
            file_path="src/processor.py",
            line_number=1,
            language="python",
            docstring="Shared index processor unit",
        )
        sym_cs = UnifiedSymbol(
            id="sym_cs",
            name="IndexProcessorCs",
            kind=SymbolKind.CLASS.value,
            file_path="src/Processor.cs",
            line_number=1,
            language="c_sharp",
            docstring="Shared index processor unit",
        )
        sym_md = UnifiedSymbol(
            id="sym_md",
            name="IndexProcessorDoc",
            kind=SymbolKind.DOC_HEADING_1.value,
            file_path="docs/processor.md",
            line_number=1,
            language="markdown",
            docstring="Shared index processor unit",
        )
        real_idx.build([sym_py, sym_cs, sym_md], tokenizer=tok)

        bm25 = BM25Engine(tokenizer=tok)
        vec_idx = VectorIndex(model_name="mock-model", dim=self.service.dimension)
        vecs = self.service.embed_texts(
            [
                "IndexProcessor processor",
                "IndexProcessorCs processor",
                "IndexProcessorDoc processor",
            ]
        )
        vec_idx.build(["sym_py", "sym_cs", "sym_md"], vecs)

        engine = HybridSearchEngine(
            inverted_index=real_idx,
            vector_index=vec_idx,
            embedding_service=self.service,
            bm25_engine=bm25,
        )

        # 1. 清單形式 ["py", "cs"]
        hits_list = engine.search(
            "processor", file_types=["py", "cs"], lexical_only=False
        )
        self.assertEqual({h["symbol"].id for h in hits_list}, {"sym_py", "sym_cs"})

        # 2. 逗號分隔字串 "py,cs"
        hits_comma = engine.search(
            "processor", file_types="py,cs", lexical_only=False  # type: ignore[arg-type]
        )
        self.assertEqual({h["symbol"].id for h in hits_comma}, {"sym_py", "sym_cs"})

        # 3. 直線分隔字串 "py|md"
        hits_pipe = engine.search(
            "processor", file_types="py|md", lexical_only=False  # type: ignore[arg-type]
        )
        self.assertEqual({h["symbol"].id for h in hits_pipe}, {"sym_py", "sym_md"})

        # 4. 不存在之副檔名 "cpp"
        hits_none = engine.search(
            "processor", file_types="cpp", lexical_only=False  # type: ignore[arg-type]
        )
        self.assertEqual(len(hits_none), 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_posting_slots_and_memory_savings(self):
        """驗證 Posting __slots__、SparseFieldFreqs 稀疏化與 InvertedIndex 0..n doc_idx 映射"""
        p = Posting(
            doc_id="doc_1",
            field_freqs={"name": 2, "signature": 0, "docstring": 0},
            space="core",
            spaces=["core", "unified"],
        )
        self.assertEqual(p.doc_id, "doc_1")
        self.assertEqual(p.field_freqs["name"], 2)
        self.assertEqual(p.field_freqs["signature"], 0)
        self.assertEqual(p.field_freqs.get("members", 0), 0)
        self.assertEqual(list(p.field_freqs.keys()), ["name"])
        self.assertEqual(p.space, "core")
        self.assertEqual(p.spaces, ["core", "unified"])

        self.assertFalse(hasattr(p, "__dict__"))
        with self.assertRaises(AttributeError):
            p.arbitrary_attr = "invalid"

        # 驗證 InvertedIndex 0..n 整數文檔碼映射與增量刪除之 free_doc_indices 回收
        idx = InvertedIndex(space_name="core")
        tok = MultilingualTokenizer()
        s1 = UnifiedSymbol(
            id="sym_a",
            name="Alpha",
            kind="class",
            file_path="a.py",
            line_number=1,
            language="python",
        )
        s2 = UnifiedSymbol(
            id="sym_b",
            name="Beta",
            kind="class",
            file_path="b.py",
            line_number=1,
            language="python",
        )
        idx.build([s1, s2], tokenizer=tok, space="core")
        self.assertEqual(idx._doc_id_table, ["sym_a", "sym_b"])
        p_alpha = idx.index["alpha"][0]
        self.assertEqual(p_alpha.doc_idx, 0)
        self.assertIsNone(p_alpha._doc_id)
        self.assertEqual(p_alpha.doc_id, "sym_a")

        # 增量替換 a.py -> 釋放 idx 0 並由新符號重用，且 b.py 之 doc_idx=1 不偏移
        s1_new = UnifiedSymbol(
            id="sym_a2",
            name="AlphaV2",
            kind="class",
            file_path="a.py",
            line_number=1,
            language="python",
        )
        idx.patch_incremental(
            dirty_file_paths={"a.py"}, new_symbols=[s1_new], tokenizer=tok
        )
        self.assertEqual(idx._doc_id_table[0], "sym_a2")
        self.assertEqual(idx._doc_id_table[1], "sym_b")
        self.assertEqual(idx.index["beta"][0].doc_id, "sym_b")
        self.assertEqual(idx.index["alphav2"][0].doc_idx, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inverted_index_doc_lengths_top_level(self):
        """驗證 InvertedIndex 頂層 doc_lengths 共享池與增量同步"""
        idx = InvertedIndex(space_name="test")
        tok = MultilingualTokenizer()

        sym1 = UnifiedSymbol(
            id="sym_1",
            name="PIDController",
            kind="class",
            file_path="src/pid.py",
            line_number=10,
            language="python",
            docstring="PID 控制器實現",
        )
        idx.add_symbol(sym1, tok, space="test")
        self.assertIn("sym_1", idx.doc_lengths)
        self.assertGreater(idx.doc_lengths["sym_1"]["name"], 0)

        sym3 = UnifiedSymbol(
            id="sym_3",
            name="PIDControllerV2",
            kind="class",
            file_path="src/pid.py",
            line_number=10,
            language="python",
        )
        idx.patch_incremental(
            dirty_file_paths={"src/pid.py"}, new_symbols=[sym3], tokenizer=tok
        )
        self.assertNotIn("sym_1", idx.doc_lengths)
        self.assertIn("sym_3", idx.doc_lengths)
        self.assertEqual(idx.doc_count, 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_space_weights_in_bm25_and_hybrid_search(self):
        """驗證 BM25Engine 與 HybridSearchEngine 空間權重乘算 (docs 1.2 > default 1.0 > plans 0.85)"""
        tok = MultilingualTokenizer()
        idx = InvertedIndex(space_name="unified")

        sym_docs = UnifiedSymbol(
            id="doc_arch",
            name="PrecisionGuide",
            kind=SymbolKind.DOC_HEADING_1.value,
            file_path="docs/precision.md",
            line_number=1,
            language="markdown",
            signature="# PrecisionGuide",
            docstring="系統精準度設計指南",
            metadata={"spaces": ["docs"]},
        )
        sym_plans = UnifiedSymbol(
            id="plan_arch",
            name="PrecisionGuide",
            kind=SymbolKind.DOC_HEADING_1.value,
            file_path="plans/architecture/precision.md",
            line_number=1,
            language="markdown",
            signature="# PrecisionGuide",
            docstring="系統精準度設計指南",
            metadata={"spaces": ["plans"]},
        )
        idx.build([sym_plans, sym_docs], tokenizer=tok)

        bm25 = BM25Engine(tokenizer=tok)
        weights = {"docs": 1.2, "plans": 0.85}

        # 1. BM25 空間權重乘算驗證
        flt_unweighted = QueryFilter(limit=10)
        res_unweighted = {
            r.symbol.id: r.score
            for r in bm25.search("PrecisionGuide", idx, filter_cfg=flt_unweighted)
        }
        self.assertAlmostEqual(
            res_unweighted["doc_arch"], res_unweighted["plan_arch"], places=4
        )

        flt_weighted = QueryFilter(limit=10, space_weights=weights)
        res_weighted = bm25.search("PrecisionGuide", idx, filter_cfg=flt_weighted)
        self.assertEqual(len(res_weighted), 2)
        self.assertEqual(res_weighted[0].symbol.id, "doc_arch")
        self.assertEqual(res_weighted[1].symbol.id, "plan_arch")
        self.assertAlmostEqual(
            res_weighted[0].score / res_weighted[1].score, 1.2 / 0.85, places=4
        )

        # 2. HybridSearchEngine RRF 空間權重乘算驗證
        vec_idx = VectorIndex()
        vecs = self.service.embed_texts(["PrecisionGuide", "PrecisionGuide"])
        vec_idx.build(["plan_arch", "doc_arch"], vecs)

        hybrid = HybridSearchEngine(
            inverted_index=idx,
            vector_index=vec_idx,
            embedding_service=self.service,
            bm25_engine=bm25,
            space_weights=weights,
        )
        h_res = hybrid.search("PrecisionGuide", limit=5, lexical_only=False)
        self.assertEqual(len(h_res), 2)
        self.assertEqual(h_res[0]["symbol"].id, "doc_arch")
        self.assertEqual(h_res[1]["symbol"].id, "plan_arch")
        self.assertGreater(h_res[0]["score"], h_res[1]["score"])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_bm25_prefilter_before_scoring(self):
        """驗證 BM25Engine._score_candidate_documents 於計分迴圈前即依 space/language/kind/ftype 過濾候選文件"""
        tok = MultilingualTokenizer()
        idx = InvertedIndex(space_name="code")

        sym_py = UnifiedSymbol(
            id="sym_py_fn",
            name="compute_metric",
            kind="function",
            file_path="src/metrics.py",
            line_number=10,
            language="python",
            signature="def compute_metric()",
            docstring="compute metric value",
            metadata={"spaces": ["code"]},
        )
        sym_cs = UnifiedSymbol(
            id="sym_cs_cls",
            name="compute_metric",
            kind="class",
            file_path="src/Metrics.cs",
            line_number=20,
            language="c_sharp",
            signature="class compute_metric",
            docstring="compute metric value",
            metadata={"spaces": ["other_space"]},
        )
        idx.build([sym_py, sym_cs], tokenizer=tok)

        # 注入毒丸值：若 sym_cs_cls 未在計分前被預先過濾，讀取 doc_lengths["sym_cs_cls"].get(...) 將拋出 AttributeError
        idx.doc_lengths["sym_cs_cls"] = 0  # type: ignore[assignment]

        bm25 = BM25Engine(tokenizer=tok)
        flt = QueryFilter(
            spaces=["code"],
            languages=["python"],
            kinds=["function"],
            ftypes=["py"],
            limit=10,
        )
        results = bm25.search("compute_metric", idx, filter_cfg=flt)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].symbol.id, "sym_py_fn")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_snippet_extractor_mtime_ns_cache_invalidation(self):
        """驗證 knowledge_db SnippetExtractor 基於 mtime_ns 快取檔案行並在檔案更新後自動讀取新內容"""
        sample_file = self.cache_dir / "snippet_target.py"
        sample_file.write_text("alpha = 1\nbeta = 2\ngamma = 3\n", encoding="utf-8")

        extractor = SnippetExtractor(workspace_root=self.cache_dir)
        s1 = extractor.extract(
            sample_file, line_number=2, end_line=2, context_before=0, context_after=0
        )
        self.assertEqual(s1.lines[0], (2, "beta = 2"))
        self.assertEqual(len(extractor._file_lines_cache), 1)

        write_text_and_advance_mtime(sample_file, "alpha = 1\nbeta = 999\ngamma = 3\n")

        s2 = extractor.extract(
            sample_file, line_number=2, end_line=2, context_before=0, context_after=0
        )
        self.assertEqual(s2.lines[0], (2, "beta = 999"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hybrid_dot_directory_extension_and_pre_aggregated_index(self):
        """驗證含隱藏點目錄但無副檔名路徑之 file_types 過濾精確度，以及 InvertedIndex.build(pre_aggregated=True) 快徑。"""
        sym_dotdir_no_ext = UnifiedSymbol(
            id="sym_makefile",
            name="build_target",
            kind=SymbolKind.FUNCTION,
            file_path=".agents/skills/Makefile",
            line_number=1,
            language="python",
        )
        sym_py = UnifiedSymbol(
            id="sym_py_ok",
            name="build_target",
            kind=SymbolKind.FUNCTION,
            file_path=".agents/skills/runner.py",
            line_number=1,
            language="python",
        )
        symbols = {"sym_makefile": sym_dotdir_no_ext, "sym_py_ok": sym_py}
        dummy_idx = DummyIndex(
            symbols=symbols,
            hits=[
                {"doc_id": "sym_makefile", "score": 1.0},
                {"doc_id": "sym_py_ok", "score": 1.0},
            ],
        )
        vec_idx = VectorIndex(model_name="mock-model", dim=self.service.dimension)
        vecs = self.service.embed_texts(
            ["build_target makefile", "build_target runner"]
        )
        vec_idx.build(["sym_makefile", "sym_py_ok"], vecs)
        engine = HybridSearchEngine(
            inverted_index=dummy_idx,
            vector_index=vec_idx,
            embedding_service=self.service,
            bm25_engine=dummy_idx,
        )
        # 過濾 file_types=["skills/makefile"] 不應誤將 .agents/skills/Makefile 當成副檔名匹配
        res_fake_ext = engine.search(
            "build_target", file_types=["skills/makefile"], lexical_only=False
        )
        self.assertEqual(len(res_fake_ext), 0)

        res_py = engine.search("build_target", file_types=["py"], lexical_only=False)
        self.assertEqual(len(res_py), 1)
        self.assertEqual(res_py[0]["symbol"].id, "sym_py_ok")

        # 驗證 pre_aggregated=True 直接建立索引而不重複呼叫 aggregate_partial_symbols
        idx = InvertedIndex(space_name="unified")
        tok = MultilingualTokenizer()
        idx.build([sym_py], tokenizer=tok, pre_aggregated=True)
        self.assertEqual(idx.doc_count, 1)
        self.assertIn("sym_py_ok", idx.symbols)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
