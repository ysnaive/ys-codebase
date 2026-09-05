"""
Unit and Integration Tests for Knowledge-DB JIT Invalidation, Incremental Hot Reload, and Hot Healing.
Unified Suite consolidating test_incremental_hot_reload.py and test_jit_hot_healing.py.
"""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.bundler import SemanticBundler
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.retrieval import BM25Engine, InvertedIndex, QueryFilter
from knowledge_db.scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffDetail
from knowledge_db.schema import SpaceConfig, UnifiedSymbol
from knowledge_db.tokenizer import CodeTokenizer


class TestJITHotHealing(YSCBTestCase):
    """JIT 快照檢驗與熱自愈機制測試"""

    @require(Requirement.LOGIC)
    def test_binary_snapshot_manager_perf_and_roundtrip(self):
        """FT-04: 驗證 BinarySnapshotManager (YFP1) 原生二進位快照讀寫耗時與正確反序列化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            snap_path = Path(temp_dir) / "indices" / "unified.meta.bin"

            mock_files = {
                f"d:/repos/ys_codebase/source/module_{i % 5}/file_{i}.py": (1700000000.0 + i, 1024 + i)
                for i in range(1000)
            }

            t0 = time.perf_counter()
            BinarySnapshotManager.save(snap_path, mock_files)
            write_time_ms = (time.perf_counter() - t0) * 1000
            self.assertTrue(snap_path.exists())

            t1 = time.perf_counter()
            loaded_map = BinarySnapshotManager.load(snap_path)
            read_time_ms = (time.perf_counter() - t1) * 1000

            self.assertIsNotNone(loaded_map)
            self.assertEqual(len(loaded_map), 1000)
            self.assertIn("d:/repos/ys_codebase/source/module_0/file_0.py", loaded_map)
            mtime, size = loaded_map["d:/repos/ys_codebase/source/module_0/file_0.py"]
            self.assertEqual(size, 1024)
            self.assertEqual(mtime, 1700000000.0)
            self.assertLess(read_time_ms, 50.0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_bundle_union_and_spaces_tagging(self):
        """FT-01: 驗證全專案空間聯集去重掃描，相同檔案僅解析 1 次並標記多空間標籤"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file_a = src_dir / "common.py"
            file_a.write_text("class CommonHelper:\n    '''共用輔助工具類別'''\n    def execute(self): pass", encoding="utf-8")

            sp_a = SpaceConfig(name="space_a", include=[str(src_dir)])
            sp_b = SpaceConfig(name="space_b", include=[str(src_dir)])

            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"space_a": sp_a.to_dict(), "space_b": sp_b.to_dict()}},
            )

            bundler = SemanticBundler(engine.space_manager, engine.parser_registry)
            bundle = bundler.bundle_union()

            self.assertEqual(bundle.metadata["total_files"], 1)
            sym = next(s for s in bundle.symbols if s.name == "CommonHelper")
            self.assertEqual(sorted(sym.spaces), ["space_a", "space_b"])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unified_inverted_index_and_space_filtering(self):
        """FT-02: 驗證單一全域倒排索引 (unified.index.bin.gz) 與 BM25 空間標籤 O(1) 過濾"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            docs_dir = temp_path / "docs"
            src_dir.mkdir(parents=True)
            docs_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            (src_dir / "service.py").write_text("class AuthEngine:\n    '''驗證授權引擎'''\n    pass", encoding="utf-8")
            (docs_dir / "AUTH.md").write_text("# AuthEngine 說明文件\n說明授權流程", encoding="utf-8")

            sp_code = SpaceConfig(name="source", include=[str(src_dir)])
            sp_docs = SpaceConfig(name="docs", include=[str(docs_dir)])

            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"source": sp_code.to_dict(), "docs": sp_docs.to_dict()}},
            )

            idx = engine.build_unified_index(force=True)
            self.assertEqual(idx.space_name, "unified")
            self.assertTrue(idx.doc_count >= 2)

            res_all = engine.search("AuthEngine", auto_rebuild=False)
            self.assertEqual(len(res_all), 2)

            res_src = engine.search("AuthEngine", space="source", auto_rebuild=False)
            self.assertEqual(len(res_src), 1)
            self.assertEqual(res_src[0].symbol.name, "AuthEngine")
            self.assertIn("source", res_src[0].space)

            res_doc = engine.search("AuthEngine", space="docs", auto_rebuild=False)
            self.assertEqual(len(res_doc), 1)
            self.assertIn("docs", res_doc[0].space)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_jit_invalidation_and_hot_healing(self):
        """FT-03: 驗證檔案修改後，JIT 變更檢測精準感知並自動熱自愈"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            app_file = src_dir / "app.py"
            app_file.write_text("class InitialClass:\n    pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            res1 = engine.search("InitialClass", auto_rebuild=True)
            self.assertEqual(len(res1), 1)

            time.sleep(0.05)
            app_file.write_text("class InitialClass:\n    pass\nclass NewlyAddedWorker:\n    '''新增的工作者類別'''\n    pass", encoding="utf-8")

            res2 = engine.search("NewlyAddedWorker", auto_rebuild=True)
            self.assertEqual(len(res2), 1)
            self.assertEqual(res2[0].symbol.name, "NewlyAddedWorker")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_no_auto_rebuild_flag(self):
        """FT-05: 驗證 auto_rebuild=False 正確略過 JIT 重建"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            app_file = src_dir / "app.py"
            app_file.write_text("class AlphaService:\n    pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("AlphaService", auto_rebuild=True)

            time.sleep(0.05)
            app_file.write_text("class AlphaService:\n    pass\nclass BetaWorker:\n    pass", encoding="utf-8")

            res = engine.search("BetaWorker", auto_rebuild=False)
            self.assertEqual(len(res), 0)

            res_healed = engine.search("BetaWorker", auto_rebuild=True)
            self.assertEqual(len(res_healed), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_edge_cases_missing_and_corrupted_snapshot(self):
        """ET-01, ET-02: 驗證快照/索引缺失或損毀時，自動無縫自愈"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            (src_dir / "module.py").write_text("class EdgeTest:\n    pass", encoding="utf-8")
            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            res1 = engine.search("EdgeTest", auto_rebuild=True)
            self.assertEqual(len(res1), 1)

            meta_file = storage_dir / "indices" / "unified.meta.bin"
            meta_file.write_bytes(b"CORRUPTED_GARBAGE_HEADER")

            res2 = engine.search("EdgeTest", auto_rebuild=True)
            self.assertEqual(len(res2), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_edge_case_deleted_file(self):
        """ET-03: 驗證檔案刪除後，JIT 變更檢測感知並剔除過期符號"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file1 = src_dir / "alpha.py"
            file2 = src_dir / "beta.py"
            file1.write_text("class UniqueKeeper:\n    pass", encoding="utf-8")
            file2.write_text("class DestinedToDelete:\n    pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("UniqueKeeper", auto_rebuild=True)
            file2.unlink()

            res = engine.search("DestinedToDelete", auto_rebuild=True)
            self.assertEqual(len(res), 0)
            res_keep = engine.search("UniqueKeeper", auto_rebuild=True)
            self.assertEqual(len(res_keep), 1)

        self.mark_passed()


class TestIncrementalHotReload(YSCBTestCase):
    """增量檔案變更偵測與差量索引修補測試"""

    @require(Requirement.LOGIC)
    def test_ft_01_check_invalidation_full_scan(self):
        """FT-01: 驗證 check_invalidation 在多檔有修改/新增時完整掃描，回傳完整清冊與差量明細"""
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

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.build_unified_index(force=True)
            meta_path = storage_dir / "indices" / "unified.meta.bin"
            self.assertTrue(meta_path.exists())

            time.sleep(0.05)
            files[0].write_text("class Class0Modified: pass", encoding="utf-8")
            files[4].write_text("class Class4Modified: pass", encoding="utf-8")
            f5 = src_dir / "file_5.py"
            f5.write_text("class Class5: pass", encoding="utf-8")

            is_dirty, count, reason, files_map, diff = engine.scanner.check_invalidation(
                snapshot_path=meta_path
            )

            self.assertTrue(is_dirty)
            self.assertEqual(count, 6)
            self.assertEqual(len(files_map), 6)

            k0 = str(files[0].resolve()).replace("\\", "/")
            k4 = str(files[4].resolve()).replace("\\", "/")
            k5 = str(f5.resolve()).replace("\\", "/")

            self.assertIn(k0, diff.modified)
            self.assertIn(k4, diff.modified)
            self.assertIn(k5, diff.added)
            self.assertEqual(len(diff.deleted), 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_per_file_symbol_cache(self):
        """FT-02: 驗證 SemanticBundler 單檔符號快取：未變更檔案復用記憶體物件，僅重新解析 dirty 檔案"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "mod1.py"
            f2 = src_dir / "mod2.py"
            f1.write_text("class Mod1:\n    def run(self): pass", encoding="utf-8")
            f2.write_text("class Mod2:\n    def exec(self): pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            bundler = engine.bundler
            bundle = bundler.bundle_union()
            self.assertEqual(len(bundle.symbols), 4)

            k1 = str(f1.resolve()).replace("\\", "/")
            k2 = str(f2.resolve()).replace("\\", "/")

            self.assertIn(k1, bundler._file_symbols_cache)
            self.assertIn(k2, bundler._file_symbols_cache)
            sym1_orig = bundler._file_symbols_cache[k1][0]

            time.sleep(0.05)
            f2.write_text("class Mod2Updated:\n    pass", encoding="utf-8")
            diff = ScanDiffDetail(modified={k2})

            new_symbols_by_file, dirty_keys = bundler.bundle_dirty_files(diff)

            self.assertIn(k2, new_symbols_by_file)
            self.assertNotIn(k1, new_symbols_by_file)
            self.assertEqual(new_symbols_by_file[k2][0].name, "Mod2Updated")
            self.assertIs(bundler._file_symbols_cache[k1][0], sym1_orig)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_inverted_index_patch_incremental(self):
        """FT-03: 驗證 InvertedIndex.patch_incremental 拔除舊 Postings、注入新 Postings 並動態重算 avgdl"""
        idx = InvertedIndex(space_name="unified")
        tok = CodeTokenizer()

        sym1 = UnifiedSymbol(
            id="id1",
            name="AlphaService",
            kind="class",
            file_path="src/alpha.py",
            line_number=1,
            language="python",
            docstring="Alpha service implementation",
            metadata={"spaces": ["main"], "space": "main"},
        )
        sym2 = UnifiedSymbol(
            id="id2",
            name="BetaService",
            kind="class",
            file_path="src/beta.py",
            line_number=1,
            language="python",
            docstring="Beta service helper",
            metadata={"spaces": ["main"], "space": "main"},
        )

        idx.build_unified([sym1, sym2], tokenizer=tok)
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
            metadata={"spaces": ["main"], "space": "main"},
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
    def test_ft_04_incremental_hot_reload_search(self):
        """FT-04: 驗證 KnowledgeEngine.search 觸發增量熱自愈後，檢索結果即刻反映新增/修改/刪除之符號"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            app_file = src_dir / "app.py"
            app_file.write_text("class UserQueryEngine:\n    '''用戶查詢引擎'''\n    pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            r1 = engine.search("UserQueryEngine", auto_rebuild=True)
            self.assertEqual(len(r1), 1)

            time.sleep(0.05)
            app_file.write_text(
                "class UserQueryEngine:\n    '''用戶查詢引擎'''\n    pass\n"
                "class PaymentEngine:\n    '''金流支付引擎'''\n    pass",
                encoding="utf-8",
            )

            r2 = engine.search("PaymentEngine", auto_rebuild=True)
            self.assertEqual(len(r2), 1)
            self.assertEqual(r2[0].symbol.name, "PaymentEngine")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_file_deletion_handling(self):
        """ET-01: 驗證檔案刪除情境，快照中存在但磁碟不存在，正確移除符號、Postings 與快取"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "keeper.py"
            f2 = src_dir / "to_delete.py"
            f1.write_text("class PermanentKeeper: pass", encoding="utf-8")
            f2.write_text("class TemporaryObject: pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("PermanentKeeper", auto_rebuild=True)
            self.assertEqual(len(engine.search("TemporaryObject", auto_rebuild=False)), 1)

            time.sleep(0.05)
            f2.unlink()

            r = engine.search("TemporaryObject", auto_rebuild=True)
            self.assertEqual(len(r), 0)
            self.assertEqual(len(engine.search("PermanentKeeper", auto_rebuild=True)), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_empty_file_handling(self):
        """ET-02: 驗證檔案修改為空內容 (Empty/Non-symbol File)：舊符號乾淨移除不拋例外"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "target.py"
            f1.write_text("class WillBeEmpty: pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("WillBeEmpty", auto_rebuild=True)

            time.sleep(0.05)
            f1.write_text("# only comment line\n", encoding="utf-8")

            r = engine.search("WillBeEmpty", auto_rebuild=True)
            self.assertEqual(len(r), 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_corrupted_snapshot_fallback(self):
        """ET-03: 驗證快照損毀時自動安全降級為 Full Rebuild 並恢復正常狀態"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            f1 = src_dir / "code.py"
            f1.write_text("class SafeFallbackClass: pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("SafeFallbackClass", auto_rebuild=True)

            meta_path = storage_dir / "indices" / "unified.meta.bin"
            meta_path.write_bytes(b"CORRUPTED_BIN_HEADER_123")

            r = engine.search("SafeFallbackClass", auto_rebuild=True)
            self.assertEqual(len(r), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_rt_01_no_infinite_hot_reload_loop(self):
        """RT-01 (Bugfix 回歸防護): 修改 1 檔觸發熱自愈後，後續查詢絕對不再重複觸發熱重載"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            for i in range(10):
                (src_dir / f"file_{i}.py").write_text(f"class FileClass{i}: pass", encoding="utf-8")

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("FileClass0", auto_rebuild=True)

            time.sleep(0.05)
            (src_dir / "file_2.py").write_text("class FileClass2Modified: pass", encoding="utf-8")

            r1 = engine.search("FileClass2Modified", auto_rebuild=True)
            self.assertTrue(len(r1) >= 1)
            first_sym = r1[0].items[0].symbol if hasattr(r1[0], "items") else r1[0].symbol
            self.assertEqual(first_sym.name, "FileClass2Modified")

            meta_path = storage_dir / "indices" / "unified.meta.bin"
            is_dirty, count, reason, files_map, diff = engine.scanner.check_invalidation(
                snapshot_path=meta_path
            )

            self.assertFalse(is_dirty, f"Expected clean state but got dirty: {reason}")
            self.assertEqual(len(diff.dirty_files), 0)
            self.assertEqual(count, 10)

            for q in ["FileClass0", "FileClass5", "FileClass9"]:
                res = engine.search(q, auto_rebuild=True)
                self.assertTrue(len(res) >= 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pt_01_incremental_latency_benchmark(self):
        """PT-01: 模擬 50 檔規模下單檔微小修改觸發之增量熱自愈端到端耗時"""
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

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            engine.search("ServiceWorker0", auto_rebuild=True)

            time.sleep(0.05)
            files[25].write_text(
                "class ServiceWorker25:\n"
                "    '''第 25 號服務背景處理器 (更新版)'''\n"
                "    def process_25(self, data: str) -> None: pass\n"
                "class HotHealedClass25:\n"
                "    '''增量熱自愈新類別'''\n"
                "    pass\n",
                encoding="utf-8",
            )

            t0 = time.perf_counter()
            res = engine.search("HotHealedClass25", auto_rebuild=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            self.assertTrue(len(res) >= 1)
            first_sym = res[0].items[0].symbol if hasattr(res[0], "items") else res[0].symbol
            self.assertEqual(first_sym.name, "HotHealedClass25")

            self.assertLessEqual(
                elapsed_ms,
                1500.0,
                f"Incremental hot reload took {elapsed_ms:.2f}ms, exceeding target <= 1500ms in sandbox",
            )

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
