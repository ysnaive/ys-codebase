"""
Unit and Integration Tests for knowledge-db InvertedIndex, BM25Engine, Tokenizer, HybridSearchEngine, and Aggregation.
Unified Suite consolidating test_retrieval.py, test_search_aggregation.py, test_tokenizer.py, and test_hybrid.py.
"""

import gzip
import os
from pathlib import Path
import sys
import tempfile
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import numpy as np

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.embedding import DEFAULT_EMBEDDING_DIM, EmbeddingService, VectorIndex
from knowledge_db.hybrid import DEFAULT_RRF_K, HybridSearchEngine
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
    AggregatedFileResult,
    LanguageType,
    MemberInfo,
    SymbolKind,
    UnifiedSymbol,
)
from knowledge_db.tokenizer import CodeTokenizer, MultilingualTokenizer


class DummyIndex:
    """Mock InvertedIndex for hybrid unit tests"""

    def __init__(self, symbols=None, hits=None):
        self.symbols = symbols or {}
        self.hits = hits or []

    def search(self, query: str, limit: int = 10, file_types=None):
        return self.hits[:limit]


class TestRetrieval(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tokenizer = CodeTokenizer()
        self.thesaurus = None

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

        self.mark_passed()

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

        self.mark_passed()

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

        self.mark_passed()

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

        self.mark_passed()

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

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_symbol_pool_normalization_and_binary_gzip_io(self):
        """FT-01, FT-02: 驗證 InvertedIndex 符號池去重與二進位 Gzip 讀寫無損還原"""
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
            engine = BM25Engine(tokenizer=self.tokenizer, thesaurus=self.thesaurus)
            res = engine.search("PIDController", restored)
            self.assertGreaterEqual(len(res), 1)
            self.assertEqual(res[0].symbol.name, "PIDController")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_corrupted_binary_cache_fallback(self):
        """ET-01: 驗證損毀之二進位檔案讀取拋錯 (EC-01)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            corrupt_path = Path(temp_dir) / "corrupt.index.bin.gz"
            corrupt_path.write_bytes(b"not a valid gzip or pickle data 123456789")

            with self.assertRaises(Exception):
                InvertedIndex.load_binary(corrupt_path)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_snippet_extractor_and_code_snippet(self):
        """FT-01, FT-02, ET-01~04: 驗證 SnippetExtractor 安全讀取、截斷與編碼容錯"""
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

            # 1. 正常提取 (FT-01)
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

            # 2. 序列化測試 (FR-05)
            s_dict = snip.to_dict()
            self.assertEqual(s_dict["target_line"], 4)
            self.assertIn("raw_code", s_dict)
            self.assertIn("target_func", s_dict["raw_code"])

            # 3. 檔案不存在測試 (ET-01, EC-01)
            snip_missing = extractor.extract("non_existent.py", line_number=10)
            self.assertIsNotNone(snip_missing.error)
            self.assertEqual(snip_missing.error, "File not found")
            self.assertIn("[Snippet Unavailable", snip_missing.format_text())

            # 4. 行號超界測試 (ET-02, EC-02)
            snip_oob = extractor.extract("sample.py", line_number=999)
            self.assertIsNone(snip_oob.error)
            self.assertLessEqual(snip_oob.end_line, 10)

            # 5. 超出行數截斷 (ET-03, EC-03)
            snip_trunc = extractor.extract("sample.py", line_number=1, context_before=0, context_after=9)
            self.assertTrue(snip_trunc.is_truncated)
            self.assertLessEqual(len(snip_trunc.lines), 6)

            # 6. 二進位/非 UTF-8 容錯 (ET-04, EC-04)
            bin_file = temp_path / "binary.dat"
            bin_file.write_bytes(b"\xff\xfe\x00\x12\x34\x56\x78\x90")
            snip_bin = extractor.extract("binary.dat", line_number=1)
            self.assertIsNone(snip_bin.error)

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
        flt_py = QueryFilter(ftypes=["py"], limit=10)
        res_py = self.engine.search_aggregated("parse", self.index, filter_cfg=flt_py)
        self.assertTrue(all(r.file_path.endswith(".py") for r in res_py))
        self.assertEqual(len(res_py), 1)

        flt_cpp = QueryFilter(ftypes=["c|cpp|h"], limit=10)
        res_cpp = self.engine.search_aggregated("parse", self.index, filter_cfg=flt_cpp)
        self.assertTrue(all(r.file_path.endswith(".cpp") for r in res_cpp))
        self.assertEqual(len(res_cpp), 1)

        flt_md = QueryFilter(ftypes=[".md"], limit=10)
        res_md = self.engine.search_aggregated("parser", self.index, filter_cfg=flt_md)
        self.assertTrue(all(r.file_path.endswith(".md") for r in res_md))
        self.assertEqual(len(res_md), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_06_score_aggregation_and_top3_cap(self):
        """FT-06: 同檔案積分累加 (Max + 0.2*Rest) 與內部 Top-3 限制"""
        flt = QueryFilter(limit=10)
        results = self.engine.search_aggregated("parse token stream", self.index, filter_cfg=flt, alpha=0.2)
        self.assertTrue(len(results) >= 2)

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
    def test_ft_07_top_n_refill_pipeline(self):
        """FT-07: Top-N 動態聚合回填管線"""
        flt = QueryFilter(limit=2)
        results = self.engine.search_aggregated("parse", self.index, filter_cfg=flt)
        self.assertEqual(len(results), 2)
        file_paths = {r.file_path for r in results}
        self.assertEqual(len(file_paths), 2)

        self.mark_passed()

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

        self.mark_passed()


class TestTokenizer(YSCBTestCase):
    """代碼分詞器 (CamelCase / snake_case / CJK 滑動窗口) 測試。"""

    @require(Requirement.LOGIC)
    def test_code_identifier_tokenization(self):
        tok = CodeTokenizer()

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
        tok = CodeTokenizer()

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
        """FT-01: 驗證 MultilingualTokenizer 中英混排無縫切分與向後相容性。"""
        tok = MultilingualTokenizer()

        res1 = tok.tokenize("解析InvertedIndex倒排索引")
        self.assertIn("inverted", res1)
        self.assertIn("index", res1)
        self.assertIn("invertedindex", res1)
        self.assertIn("解析", res1)
        self.assertIn("倒排", res1)
        self.assertIn("索引", res1)

        self.assertIs(CodeTokenizer, MultilingualTokenizer)
        self.assertTrue(tok.is_cjk("中"))
        self.assertFalse(tok.is_cjk("A"))

        parts = tok.split_identifier("TreeSitterDriver.extract_imports")
        self.assertIn("treesitterdriver", parts)
        self.assertIn("imports", parts)

        self.mark_passed()


class TestEmbeddingServiceAndVectorIndex(YSCBTestCase):
    """FT-02: 驗證 EmbeddingService 與 VectorIndex"""

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
        """FT-02: 驗證向量生成、餘弦相似度與二進位快取持久化"""
        self.assertTrue(self.service.is_available)
        texts = ["hello world", "inverted index search", "中文倒排索引檢索"]
        embeddings = self.service.embed_texts(texts)

        self.assertEqual(embeddings.shape, (3, DEFAULT_EMBEDDING_DIM))
        for vec in embeddings:
            norm = np.linalg.norm(vec)
            self.assertAlmostEqual(norm, 1.0, places=4)

        query_vec = self.service.embed_query("inverted index")
        sims = self.service.compute_similarity(query_vec, embeddings)
        self.assertEqual(len(sims), 3)

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
        """ET-03: 本地向量快取損毀時捕獲驗證失敗並安全降級"""
        corrupted_file = self.cache_dir / "bad_vectors.bin.gz"
        with gzip.open(corrupted_file, "wb") as f:
            f.write(b"NOT_A_VALID_PICKLE_DATA")

        loaded = VectorIndex.load_binary(corrupted_file)
        self.assertEqual(len(loaded.doc_ids), 0)
        self.assertIsNone(loaded.vectors)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_long_content(self):
        """ET-02: 512+ tokens 超長內容之安全切片與特徵提煉"""
        long_text = "token " * 1000
        vec = self.service.embed_query(long_text)
        self.assertEqual(vec.shape, (DEFAULT_EMBEDDING_DIM,))
        self.assertAlmostEqual(np.linalg.norm(vec), 1.0, places=4)

        self.mark_passed()


class TestHybridSearchEngine(YSCBTestCase):
    """FT-03 & FT-04: 驗證 HybridSearchEngine 與剛性降級"""

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
        """FT-03: 驗證 HybridSearchEngine RRF 融合排序邏輯與權重計算"""
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
        """FT-04: 驗證雙軌剛性降級守門：lexical_only=True 或向量未就緒時退化純 BM25"""
        bm25_hits = [
            {"doc_id": "sym_a", "score": 10.5, "matched_terms": ["index"]},
        ]
        dummy_index = DummyIndex(symbols=self.symbols, hits=bm25_hits)

        # 情況 1: lexical_only=True
        engine = HybridSearchEngine(
            inverted_index=dummy_index,
            vector_index=VectorIndex(),
            embedding_service=self.service,
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
        )
        self.assertFalse(engine_no_svc.is_vector_available)
        res_no_svc = engine_no_svc.search("index", lexical_only=False)
        self.assertEqual(len(res_no_svc), 1)
        self.assertEqual(res_no_svc[0]["mode"], "lexical_bm25")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_empty_query(self):
        """ET-01: 驗證空字串、純空白與無效輸入安全防護"""
        engine = HybridSearchEngine(
            inverted_index=DummyIndex(symbols=self.symbols, hits=[]),
            vector_index=VectorIndex(),
            embedding_service=self.service,
        )
        self.assertEqual(engine.search(""), [])
        self.assertEqual(engine.search("   "), [])
        self.assertEqual(engine.search(None), [])

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
