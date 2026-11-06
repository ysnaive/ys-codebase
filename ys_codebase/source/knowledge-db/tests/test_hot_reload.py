"""
Unit and Integration Tests for Knowledge-DB JIT Cursor Consumption, Incremental Hot Reload, and Hot Healing.
"""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from file_space import FileSpaceConfig
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.retrieval import InvertedIndex
from knowledge_db.schema import UnifiedSymbol
from knowledge_db.tokenizer import MultilingualTokenizer
from tests import write_text_and_advance_mtime


class TestJITHotHealing(YSCBTestCase):
    """JIT 快照檢驗與熱自愈機制測試"""

    @require(Requirement.LOGIC)
    def test_multi_space_union_indexing_and_space_tags(self):
        """驗證 KnowledgeEngine 跨空間重疊檔案之單次解析共享與多空間標籤保留"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file_a = src_dir / "common.py"
            file_a.write_text(
                "class CommonHelper:\n    '''共用輔助工具類別'''\n    def execute(self): pass",
                encoding="utf-8",
            )

            sp_a = FileSpaceConfig(name="space_a", include=[str(src_dir)])
            sp_b = FileSpaceConfig(name="space_b", include=[str(src_dir)])

            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={
                    "spaces": {"space_a": sp_a.to_dict(), "space_b": sp_b.to_dict()},
                    "space_weights": {"space_a": 1.0, "space_b": 1.2},
                },
            )

            idx = engine.build_unified_index(force=True)
            sym = next(s for s in idx.symbols.values() if s.name == "CommonHelper")
            self.assertEqual(sorted(sym.spaces), ["space_a", "space_b"])

            res_a = engine.search("CommonHelper", space="space_a", auto_rebuild=False)
            self.assertEqual(len(res_a), 1)
            self.assertEqual(sorted(res_a[0].spaces), ["space_a", "space_b"])

            res_b = engine.search("CommonHelper", space="space_b", auto_rebuild=False)
            self.assertEqual(len(res_b), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_single_parse_symbol_sharing_zero_reparse(self):
        """驗證 Single-Parse Symbol Sharing：當 ast_engine 已同步最新快照時，knowledge-db 直接消費快照而不重複解析檔案"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f_shared = src_dir / "shared.py"
            f_shared.write_text(
                "class SharedService:\n    def execute(self) -> None:\n        pass\n",
                encoding="utf-8",
            )

            sp = FileSpaceConfig(name="source", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"source": sp.to_dict()}},
            )

            # 1. 先由 ast_engine 執行一次 JIT 同步產出 ASTSnapshot
            ast_snap = engine.ast_engine.ensure_jit_synced(force=True)
            gen1 = ast_snap.ast_generation
            self.assertGreaterEqual(gen1, 1)

            # 2. 攔截 parser_registry.parse_file，驗證 knowledge-db build_unified_index (force=True) 零重複解析
            with patch.object(
                engine.ast_engine.parser_registry,
                "parse_file",
                wraps=engine.ast_engine.parser_registry.parse_file,
            ) as spy_parse:
                idx = engine.build_unified_index(force=True)
                self.assertEqual(
                    spy_parse.call_count,
                    0,
                    "knowledge-db should directly consume ASTSnapshot without re-parsing files!",
                )
                self.assertEqual(idx.acked_ast_generation, gen1)

            # 3. 驗證當 ast_engine 先感知檔案修改並推進 ast_generation 時，knowledge-db 也能透過雙游標比對自動同步且零重解析
            write_text_and_advance_mtime(
                f_shared,
                "class SharedServiceV2:\n    def execute_v2(self) -> None:\n        pass\n",
            )
            ast_snap_v2 = engine.ast_engine.ensure_jit_synced()
            self.assertGreater(ast_snap_v2.ast_generation, gen1)

            with patch.object(
                engine.ast_engine.parser_registry,
                "parse_file",
                wraps=engine.ast_engine.parser_registry.parse_file,
            ) as spy_parse_v2:
                res = engine.search("SharedServiceV2", auto_rebuild=True)
                self.assertEqual(
                    spy_parse_v2.call_count,
                    0,
                    "Hot patch after ast_engine sync should also reuse ASTSnapshot without re-parsing!",
                )
                self.assertGreaterEqual(len(res), 1)
                self.assertEqual(res[0].items[0].symbol.name, "SharedServiceV2")

            # 4. 驗證當 space 差量已被消費為空，但 ast_engine 世代較新 (acked_ast_generation 落後) 時，自動同步對齊世代
            engine.pipeline.unified_index.acked_ast_generation = 0
            engine.pipeline.unified_index.save_binary(
                engine.pipeline.get_indices_dir() / "unified.index.bin.gz"
            )
            engine.search("SharedServiceV2", auto_rebuild=True)
            self.assertEqual(
                engine.pipeline.unified_index.acked_ast_generation,
                ast_snap_v2.ast_generation,
            )

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unified_inverted_index_and_space_filtering(self):
        """驗證單一全域倒排索引 (unified.index.bin.gz) 與 BM25 空間標籤 O(1) 過濾"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            docs_dir = temp_path / "docs"
            src_dir.mkdir(parents=True)
            docs_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            (src_dir / "service.py").write_text(
                "class AuthEngine:\n    '''驗證授權引擎'''\n    pass",
                encoding="utf-8",
            )
            (docs_dir / "AUTH.md").write_text(
                "# AuthEngine 說明文件\n說明授權流程", encoding="utf-8"
            )

            sp_code = FileSpaceConfig(name="source", include=[str(src_dir)])
            sp_docs = FileSpaceConfig(name="docs", include=[str(docs_dir)])

            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={
                    "spaces": {"source": sp_code.to_dict(), "docs": sp_docs.to_dict()}
                },
            )

            idx = engine.build_unified_index(force=True)
            self.assertEqual(idx.space_name, "unified")
            self.assertGreaterEqual(idx.doc_count, 2)

            res_all = engine.search("AuthEngine", auto_rebuild=False)
            self.assertEqual(len(res_all), 2)

            res_src = engine.search("AuthEngine", space="source", auto_rebuild=False)
            self.assertEqual(len(res_src), 1)
            self.assertEqual(res_src[0].items[0].symbol.name, "AuthEngine")
            self.assertIn("source", res_src[0].spaces)

            res_doc = engine.search("AuthEngine", space="docs", auto_rebuild=False)
            self.assertEqual(len(res_doc), 1)
            self.assertIn("docs", res_doc[0].spaces)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_no_auto_rebuild_flag(self):
        """驗證 auto_rebuild=False 正確略過 JIT 重建"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            app_file = src_dir / "app.py"
            app_file.write_text("class AlphaService:\n    pass", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("AlphaService", auto_rebuild=True)

            write_text_and_advance_mtime(
                app_file,
                "class AlphaService:\n    pass\nclass BetaWorker:\n    pass",
            )

            res = engine.search("BetaWorker", auto_rebuild=False)
            self.assertEqual(len(res), 0)

            res_healed = engine.search("BetaWorker", auto_rebuild=True)
            self.assertEqual(len(res_healed), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cold_start_vector_search_loads_disk_index(self):
        """驗證全新進程冷啟動 search 能解除死鎖並正確載入磁碟上的向量索引"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file1 = src_dir / "target.py"
            file1.write_text("class ColdStartSymbol:\n    pass\n", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine1 = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )
            engine1.build_unified_index(force=True)

            indices_dir = engine1.pipeline.get_indices_dir()
            vec_file = indices_dir / "unified.vectors.bin.gz"
            self.assertTrue(vec_file.exists())

            engine2 = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )
            self.assertFalse(engine2.pipeline.hybrid_engine.is_vector_available)

            results = engine2.search("ColdStartSymbol", lexical_only=False)
            self.assertGreater(len(results), 0)
            self.assertTrue(engine2.pipeline.hybrid_engine.is_vector_available)

        self.mark_passed()


class TestIncrementalHotReload(YSCBTestCase):
    """增量檔案變更偵測與差量索引修補測試"""

    @require(Requirement.LOGIC)
    def test_consume_diff_full_scan(self):
        """驗證 consume_diff 在多檔有修改/新增時完整掃描，回傳差量明細並推進游標"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            files = []
            for i in range(5):
                f = src_dir / f"file_{i}.py"
                f.write_text(f"class Class{i}: pass", encoding="utf-8")
                files.append(f)

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.build_unified_index(force=True)
            snap_path = engine.scanner.get_snapshot_path("main")
            self.assertTrue(snap_path.exists())

            write_text_and_advance_mtime(files[0], "class Class0Modified: pass")
            write_text_and_advance_mtime(files[4], "class Class4Modified: pass")
            f5 = src_dir / "file_5.py"
            f5.write_text("class Class5: pass", encoding="utf-8")

            with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_res:
                self.assertTrue(diff_res.has_changes)
                self.assertEqual(diff_res.total_changed + diff_res.unchanged_count, 6)
                self.assertEqual(diff_res.modified_count, 2)
                self.assertEqual(diff_res.added_count, 1)
                self.assertEqual(diff_res.deleted_count, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_incremental_hot_patch_preserves_unmodified_file_symbols(self):
        """驗證 IndexingPipeline.hot_patch_unified_index 僅更新變更檔案符號，未變更檔案之 UnifiedSymbol 實例原封保留"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "mod1.py"
            f2 = src_dir / "mod2.py"
            f1.write_text("class Mod1:\n    def run(self): pass", encoding="utf-8")
            f2.write_text("class Mod2:\n    def exec(self): pass", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )

            idx = engine.build_unified_index(force=True)
            sym1_before = next(s for s in idx.symbols.values() if s.name == "Mod1")

            write_text_and_advance_mtime(f2, "class Mod2Updated:\n    pass")
            with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_res:
                patch_res = engine.pipeline.hot_patch_unified_index(diff_res.detail)
                self.assertTrue(patch_res.success)
                self.assertGreaterEqual(patch_res.patched_count, 1)

            idx_after = engine.pipeline.unified_index
            sym1_after = next(s for s in idx_after.symbols.values() if s.name == "Mod1")
            self.assertIs(sym1_after, sym1_before)
            sym_names = {s.name for s in idx_after.symbols.values()}
            self.assertIn("Mod2Updated", sym_names)
            self.assertNotIn("Mod2", sym_names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inverted_index_patch_incremental(self):
        """驗證 InvertedIndex.patch_incremental 拔除舊 Postings、注入新 Postings 並動態重算 avgdl"""
        idx = InvertedIndex(space_name="unified")
        tok = MultilingualTokenizer()

        sym1 = UnifiedSymbol(
            id="id1",
            name="AlphaService",
            kind="class",
            file_path="src/alpha.py",
            line_number=1,
            language="python",
            docstring="Alpha service implementation",
            metadata={"spaces": ["main"]},
        )
        sym2 = UnifiedSymbol(
            id="id2",
            name="BetaService",
            kind="class",
            file_path="src/beta.py",
            line_number=1,
            language="python",
            docstring="Beta service helper",
            metadata={"spaces": ["main"]},
        )

        idx.build([sym1, sym2], tokenizer=tok, space="unified")
        self.assertEqual(idx.doc_count, 2)
        self.assertIn("alphaservice", idx.index)
        self.assertIn("betaservice", idx.index)

        sym2_new = UnifiedSymbol(
            id="id3",
            name="GammaService",
            kind="class",
            file_path="src/beta.py",
            line_number=1,
            language="python",
            docstring="Gamma service replacement",
            metadata={"spaces": ["main"]},
        )

        idx.patch_incremental(
            dirty_file_paths={"src/beta.py"},
            new_symbols=[sym2_new],
            tokenizer=tok,
        )

        self.assertEqual(idx.doc_count, 2)
        self.assertIn("alphaservice", idx.index)
        self.assertNotIn("betaservice", idx.index)
        self.assertIn("gammaservice", idx.index)
        self.assertEqual(idx.get_symbol("id3").name, "GammaService")
        self.assertIsNone(idx.get_symbol("id2"))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_incremental_hot_reload_search(self):
        """驗證 KnowledgeEngine.search 觸發增量熱自愈後，檢索結果與雙水位線即刻反映新增與修改之符號"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            app_file = src_dir / "app.py"
            app_file.write_text(
                "class UserQueryEngine:\n    '''用戶查詢引擎'''\n    pass",
                encoding="utf-8",
            )

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )

            r1 = engine.search("UserQueryEngine", auto_rebuild=True)
            self.assertEqual(len(r1), 1)
            gen1 = engine.pipeline.unified_index.acked_ast_generation

            write_text_and_advance_mtime(
                app_file,
                "class UserQueryEngine:\n    '''用戶查詢引擎'''\n    pass\n"
                "class PaymentEngine:\n    '''金流支付引擎'''\n    pass",
            )

            r2 = engine.search("PaymentEngine", auto_rebuild=True)
            self.assertEqual(len(r2), 1)
            self.assertEqual(r2[0].items[0].symbol.name, "PaymentEngine")
            self.assertGreater(
                engine.pipeline.unified_index.acked_ast_generation, gen1
            )

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_file_deletion_handling(self):
        """驗證檔案刪除情境，從 symbols、doc_lengths 與 vector_index.doc_ids 徹底移除過期符號"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "keeper.py"
            f2 = src_dir / "to_delete.py"
            f1.write_text("class PermanentKeeper: pass", encoding="utf-8")
            f2.write_text("class TemporaryObject: pass", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )

            engine.search("PermanentKeeper", auto_rebuild=True)
            self.assertEqual(len(engine.search("TemporaryObject", auto_rebuild=False)), 1)
            temp_sid = next(
                sid
                for sid, sym in engine.pipeline.unified_index.symbols.items()
                if sym.name == "TemporaryObject"
            )
            self.assertIn(temp_sid, engine.pipeline.hybrid_engine.vector_index.doc_ids)

            f2.unlink()

            r = engine.search("TemporaryObject", auto_rebuild=True)
            self.assertEqual(len(r), 0)
            self.assertEqual(len(engine.search("PermanentKeeper", auto_rebuild=True)), 1)
            self.assertNotIn(temp_sid, engine.pipeline.unified_index.symbols)
            self.assertNotIn(temp_sid, engine.pipeline.unified_index.doc_lengths)
            self.assertNotIn(
                temp_sid, engine.pipeline.hybrid_engine.vector_index.doc_ids
            )

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_empty_file_handling(self):
        """驗證檔案修改為空內容 (Empty/Non-symbol File)：舊符號乾淨移除不拋例外"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "target.py"
            f1.write_text("class WillBeEmpty: pass", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("WillBeEmpty", auto_rebuild=True)

            write_text_and_advance_mtime(f1, "# only comment line\n")

            r = engine.search("WillBeEmpty", auto_rebuild=True)
            self.assertEqual(len(r), 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_corrupted_snapshot_and_index_fallback(self):
        """驗證指紋快照或 unified.index.bin.gz 損毀時，自動安全降級重建並恢復正常狀態"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "code.py"
            f1.write_text("class SafeFallbackClass: pass", encoding="utf-8")

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("SafeFallbackClass", auto_rebuild=True)

            # 1. 損毀 file-space 指紋快照
            snap_path = engine.scanner.get_snapshot_path("main")
            snap_path.write_bytes(b"CORRUPTED_BIN_HEADER_123")

            r1 = engine.search("SafeFallbackClass", auto_rebuild=True)
            self.assertEqual(len(r1), 1)

            # 2. 損毀 unified.index.bin.gz 並清空記憶體快取，觸發變更時自動退回全量重建
            bin_file = engine.pipeline.get_indices_dir() / "unified.index.bin.gz"
            bin_file.write_bytes(b"CORRUPTED_GZIP_INDEX_PAYLOAD")
            engine.pipeline.unified_index = None
            write_text_and_advance_mtime(
                f1, "class SafeFallbackClass: pass\nclass RebuiltAfterCorrupt: pass\n"
            )

            r2 = engine.search("RebuiltAfterCorrupt", auto_rebuild=True)
            self.assertEqual(len(r2), 1)
            self.assertEqual(r2[0].items[0].symbol.name, "RebuiltAfterCorrupt")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_no_infinite_hot_reload_loop(self):
        """修改 1 檔觸發熱自愈後，游標推進至最新世代，後續查詢絕對不再重複觸發熱重載"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            for i in range(10):
                (src_dir / f"file_{i}.py").write_text(
                    f"class FileClass{i}: pass", encoding="utf-8"
                )

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("FileClass0", auto_rebuild=True)

            write_text_and_advance_mtime(
                src_dir / "file_2.py", "class FileClass2Modified: pass"
            )

            r1 = engine.search("FileClass2Modified", auto_rebuild=True)
            self.assertGreaterEqual(len(r1), 1)
            self.assertEqual(r1[0].items[0].symbol.name, "FileClass2Modified")

            with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_res:
                self.assertFalse(
                    diff_res.has_changes,
                    f"Expected clean cursor state but got changes: {diff_res}",
                )
                self.assertEqual(len(diff_res.detail.dirty_files), 0)
                self.assertEqual(diff_res.total_changed + diff_res.unchanged_count, 10)

            for q in ["FileClass0", "FileClass5", "FileClass9"]:
                res = engine.search(q, auto_rebuild=True)
                self.assertGreaterEqual(len(res), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_incremental_latency_benchmark(self):
        """模擬 50 檔規模下單檔微小修改觸發之增量熱自愈端到端耗時"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            files = []
            for i in range(50):
                f = src_dir / f"service_{i}.py"
                f.write_text(
                    f"class ServiceWorker{i}:\n"
                    f"    '''第 {i} 號服務背景處理器'''\n"
                    f"    def process_{i}(self, data: str) -> None:\n"
                    f"        '''處理資料管線 {i}'''\n"
                    f"        pass\n",
                    encoding="utf-8",
                )
                files.append(f)

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("ServiceWorker0", auto_rebuild=True)

            write_text_and_advance_mtime(
                files[25],
                "class ServiceWorker25:\n"
                "    '''第 25 號服務背景處理器 (更新版)'''\n"
                "    def process_25(self, data: str) -> None: pass\n"
                "class HotHealedClass25:\n"
                "    '''增量熱自愈新類別'''\n"
                "    pass\n",
            )

            t0 = time.perf_counter()
            res = engine.search("HotHealedClass25", auto_rebuild=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            self.assertGreaterEqual(len(res), 1)
            self.assertEqual(res[0].items[0].symbol.name, "HotHealedClass25")

            self.assertLessEqual(
                elapsed_ms,
                1500.0,
                f"Incremental hot reload took {elapsed_ms:.2f}ms, exceeding target <= 1500ms in sandbox",
            )

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
