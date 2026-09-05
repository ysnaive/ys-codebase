"""
Unit Tests for knowledge-db Performance Optimization and Memory Slimming.
"""

import os
from pathlib import Path
import sys
import tempfile
import time

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.bundler import _parse_file_task_worker, SemanticBundler
from knowledge_db.retrieval import BM25Engine, InvertedIndex, Posting, QueryFilter
from knowledge_db.schema import UnifiedSymbol, WeightedToken
from knowledge_db.tokenizer import _is_cjk_ord, _split_identifier_cached, CodeTokenizer


class TestBenchmarkPerfAndMemory(YSCBTestCase):
    """效能與記憶體瘦身驗證測試套件。"""

    @require(Requirement.LOGIC)
    def test_tokenizer_unicode_ranges_and_cjk(self):
        """FT-01: 驗證 Unicode 整數區間比對與極限符號/Emoji 分詞防禦"""
        tok = CodeTokenizer()

        self.assertTrue(tok.is_cjk("中"))
        self.assertTrue(tok.is_cjk("文"))
        self.assertTrue(tok.is_cjk("あ"))
        self.assertTrue(tok.is_cjk("ア"))
        self.assertTrue(tok.is_cjk("한"))
        self.assertFalse(tok.is_cjk("A"))
        self.assertFalse(tok.is_cjk("1"))
        self.assertFalse(tok.is_cjk("_"))
        self.assertFalse(tok.is_cjk(""))

        res = tok.tokenize("Hello 🚀 世界 ⚡ TestController_v2 測試！ 123 😊")
        self.assertIn("hello", res)
        self.assertIn("世", res)
        self.assertIn("界", res)
        self.assertIn("世界", res)
        self.assertIn("test", res)
        self.assertIn("controller", res)
        self.assertIn("testcontroller_v2", res)
        self.assertIn("123", res)

        self.mark_passed()

    @require(Requirement.PERF)
    def test_tokenizer_split_identifier_lru_cache(self):
        """FT-02: 驗證識別碼拆分 LRU 快取命中與等價性 (PERF)"""
        tok = CodeTokenizer()

        r1 = tok.split_identifier("PIDVelocityManager")
        self.assertEqual(r1, ["pid", "velocity", "manager", "pidvelocitymanager"])

        r2 = tok.split_identifier("PIDVelocityManager")
        self.assertEqual(r1, r2)

        t0 = time.perf_counter()
        for _ in range(10000):
            tok.split_identifier("PIDVelocityManager")
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.2, f"10,000 cached split_identifier should take < 200ms, took {elapsed*1000:.2f}ms")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_posting_slots_and_memory_savings(self):
        """FT-03: 驗證 Posting __slots__ 屬性約束與記憶體瘦身"""
        p = Posting(doc_id="doc_1", field_freqs={"name": 2}, space="core", spaces=["core", "unified"])
        self.assertEqual(p.doc_id, "doc_1")
        self.assertEqual(p.field_freqs["name"], 2)
        self.assertEqual(p.space, "core")
        self.assertEqual(p.spaces, ["core", "unified"])

        self.assertFalse(hasattr(p, "__dict__"))
        with self.assertRaises(AttributeError):
            p.arbitrary_attr = "invalid"

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inverted_index_doc_lengths_top_level(self):
        """FT-04: 驗證 InvertedIndex 頂層 doc_lengths 共享池與增量同步"""
        idx = InvertedIndex(space_name="test")
        tok = CodeTokenizer()

        sym1 = UnifiedSymbol(
            id="sym_1",
            name="PIDController",
            kind="class",
            file_path="src/pid.py",
            line_number=10,
            language="python",
            docstring="PID 控制器實現",
        )
        sym2 = UnifiedSymbol(
            id="sym_2",
            name="calculate_velocity",
            kind="function",
            file_path="src/pid.py",
            line_number=50,
            language="python",
            docstring="計算 PID 速度輸出",
        )

        idx.add_symbol(sym1, tok, space="test")
        idx.add_symbol(sym2, tok, space="test")

        self.assertIn("sym_1", idx.doc_lengths)
        self.assertIn("sym_2", idx.doc_lengths)
        self.assertGreater(idx.doc_lengths["sym_1"]["name"], 0)

        sym3 = UnifiedSymbol(
            id="sym_3",
            name="PIDControllerV2",
            kind="class",
            file_path="src/pid.py",
            line_number=10,
            language="python",
        )
        idx.patch_incremental(dirty_file_paths={"src/pid.py"}, new_symbols=[sym3], tokenizer=tok)

        self.assertNotIn("sym_1", idx.doc_lengths)
        self.assertNotIn("sym_2", idx.doc_lengths)
        self.assertIn("sym_3", idx.doc_lengths)
        self.assertEqual(idx.doc_count, 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inverted_index_legacy_cache_migration(self):
        """FT-05: 驗證 InvertedIndex 舊版包含 field_lengths 之快取自動遷移"""
        legacy_data = {
            "space_name": "legacy",
            "doc_count": 1,
            "field_avgdl": {"name": 3.0, "signature": 1.0, "members": 1.0, "docstring": 5.0},
            "field_total_lengths": {"name": 3, "signature": 0, "members": 0, "docstring": 5},
            "symbols": {
                "doc_legacy": {
                    "id": "doc_legacy",
                    "name": "LegacySymbol",
                    "kind": "class",
                    "file_path": "legacy.py",
                    "line_number": 1,
                    "language": "python",
                }
            },
            "index": {
                "legacy": [
                    {
                        "doc_id": "doc_legacy",
                        "field_freqs": {"name": 1},
                        "field_lengths": {"name": 3, "signature": 0, "members": 0, "docstring": 5},
                        "space": "legacy",
                    }
                ]
            },
        }

        idx = InvertedIndex.from_dict(legacy_data)
        self.assertEqual(idx.doc_count, 1)
        self.assertIn("doc_legacy", idx.doc_lengths)
        self.assertEqual(idx.doc_lengths["doc_legacy"]["name"], 3)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_bundler_worker_parsing(self):
        """FT-07: 驗證頂層工作者解析函式與錯誤容錯"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_sample.py"
            test_file.write_text("class SampleWorkerClass:\n    pass\n", encoding="utf-8")

            task = ("test_key", str(test_file.resolve()), "test_sample.py", ["unified"])
            c_key, sym_dicts, err = _parse_file_task_worker(task)

            self.assertEqual(c_key, "test_key")
            self.assertIsNone(err)
            self.assertEqual(len(sym_dicts), 1)
            self.assertEqual(sym_dicts[0]["name"], "SampleWorkerClass")

            task_err = ("err_key", "non_existent.py", "non_existent.py", ["unified"])
            c_key_e, sym_dicts_e, err_e = _parse_file_task_worker(task_err)
            self.assertEqual(c_key_e, "err_key")
            self.assertIsNotNone(err_e)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_bm25_search_scoring_correctness(self):
        """FT-08: 驗證 BM25 檢索使用頂層 doc_lengths 評分之精確度與置頂加權"""
        idx = InvertedIndex(space_name="test")
        tok = CodeTokenizer()

        sym1 = UnifiedSymbol(
            id="sym_1",
            name="PIDController",
            kind="class",
            file_path="src/pid.py",
            line_number=10,
            language="python",
            docstring="PID 反饋控制系統核心實現",
        )
        sym2 = UnifiedSymbol(
            id="sym_2",
            name="UnrelatedHelper",
            kind="class",
            file_path="src/helper.py",
            line_number=1,
            language="python",
            docstring="無關輔助工具",
        )

        idx.add_symbol(sym1, tok, space="test")
        idx.add_symbol(sym2, tok, space="test")
        if idx.doc_count > 0:
            for f in idx.INDEXED_FIELDS:
                idx.field_avgdl[f] = max(1.0, idx.field_total_lengths[f] / idx.doc_count)

        engine = BM25Engine(tokenizer=tok)
        results = engine.search("PIDController", idx)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].symbol.id, "sym_1")
        self.assertGreater(results[0].score, 0.5)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
