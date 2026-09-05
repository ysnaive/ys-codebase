"""
Unit tests for knowledge-db HybridSearchEngine and EmbeddingService.
Tests cover:
- EmbeddingService (mock vector generation, similarity, caching)
- VectorIndex (search, save/load, corruption handling)
- HybridSearchEngine (RRF fusion math, lexical/vector ranking)
- Rigid 100% Fallback (lexical_only flag, vector unavailable)
- Edge cases (empty query, long content)
"""

import gzip
import os
from pathlib import Path
import sys
import tempfile

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import numpy as np

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.embedding import DEFAULT_EMBEDDING_DIM, EmbeddingService, VectorIndex
from knowledge_db.hybrid import DEFAULT_RRF_K, HybridSearchEngine
from knowledge_db.schema import SymbolKind, UnifiedSymbol


class DummyIndex:
    """Mock InvertedIndex for hybrid unit tests"""

    def __init__(self, symbols=None, hits=None):
        self.symbols = symbols or {}
        self.hits = hits or []

    def search(self, query: str, limit: int = 10, file_types=None):
        return self.hits[:limit]


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

        # 斷言形狀與 L2 正規化
        self.assertEqual(embeddings.shape, (3, DEFAULT_EMBEDDING_DIM))
        for vec in embeddings:
            norm = np.linalg.norm(vec)
            self.assertAlmostEqual(norm, 1.0, places=4)

        # 相似度計算
        query_vec = self.service.embed_query("inverted index")
        sims = self.service.compute_similarity(query_vec, embeddings)
        self.assertEqual(len(sims), 3)

        # VectorIndex 建置與 Top-K
        doc_ids = ["doc_1", "doc_2", "doc_3"]
        v_idx = VectorIndex()
        v_idx.build(doc_ids, embeddings)
        hits = v_idx.search(query_vec, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertIn(hits[0][0], doc_ids)

        # 快取持久化與還原
        cache_file = self.cache_dir / "vectors.bin.gz"
        v_idx.save_binary(cache_file)
        self.assertTrue(cache_file.exists())

        loaded_idx = VectorIndex.load_binary(cache_file)
        self.assertEqual(loaded_idx.doc_ids, doc_ids)
        self.assertEqual(loaded_idx.vectors.shape, embeddings.shape)

    @require(Requirement.LOGIC)
    def test_corrupted_cache(self):
        """ET-03: 本地向量快取損毀時捕獲驗證失敗並安全降級"""
        corrupted_file = self.cache_dir / "bad_vectors.bin.gz"
        with gzip.open(corrupted_file, "wb") as f:
            f.write(b"NOT_A_VALID_PICKLE_DATA")

        # 載入損毀快取不拋出未捕獲例外，優雅退化為空索引
        loaded = VectorIndex.load_binary(corrupted_file)
        self.assertEqual(len(loaded.doc_ids), 0)
        self.assertIsNone(loaded.vectors)

    @require(Requirement.LOGIC)
    def test_long_content(self):
        """ET-02: 512+ tokens 超長內容之安全切片與特徵提煉"""
        long_text = "token " * 1000
        vec = self.service.embed_query(long_text)
        self.assertEqual(vec.shape, (DEFAULT_EMBEDDING_DIM,))
        self.assertAlmostEqual(np.linalg.norm(vec), 1.0, places=4)


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
        # 構造 dummy BM25 檢索結果 (sym_a: rank 1, sym_b: rank 2)
        bm25_hits = [
            {"doc_id": "sym_a", "score": 10.5, "matched_terms": ["index"]},
            {"doc_id": "sym_b", "score": 8.0, "matched_terms": ["engine"]},
        ]
        dummy_index = DummyIndex(symbols=self.symbols, hits=bm25_hits)

        # 構造向量索引 (sym_b 排名高於 sym_a)
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

        # 檢驗 compute_rrf 數值準確性
        lexical_ranks = {"sym_a": 1, "sym_b": 2}
        vector_ranks = {"sym_b": 1, "sym_a": 2}
        rrf_scores = engine.compute_rrf(lexical_ranks, vector_ranks)

        # sym_a: 0.5 / (60 + 1) + 0.5 / (60 + 2)
        expected_a = 0.5 / 61.0 + 0.5 / 62.0
        # sym_b: 0.5 / (60 + 2) + 0.5 / (60 + 1)
        expected_b = 0.5 / 62.0 + 0.5 / 61.0
        self.assertAlmostEqual(rrf_scores["sym_a"], expected_a, places=6)
        self.assertAlmostEqual(rrf_scores["sym_b"], expected_b, places=6)

        results = engine.search("inverted index", limit=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["mode"], "hybrid_rrf")

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

        # 情況 2: vector_index 為空 (is_vector_available 為 False)
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


if __name__ == "__main__":
    import unittest
    unittest.main()
