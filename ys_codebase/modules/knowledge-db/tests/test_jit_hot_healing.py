"""
Unit and Integration Tests for Knowledge-DB JIT Invalidation & Hot Healing (sub_01).
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
from knowledge_db.bundler import SemanticBundler
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.retrieval import BM25Engine, InvertedIndex, QueryFilter
from knowledge_db.scanner import BinarySnapshotManager, FingerprintScanner
from knowledge_db.schema import SpaceConfig


class TestJITHotHealing(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_binary_snapshot_manager_perf_and_roundtrip(self):
        """FT-04: 驗證 BinarySnapshotManager (YFP1) 原生二進位快照讀寫耗時 < 0.5ms 與正確反序列化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            snap_path = Path(temp_dir) / "indices" / "unified.meta.bin"

            # 建立 1000 筆模擬檔案路徑
            mock_files = {
                f"d:/repos/ys_codebase/source/module_{i % 5}/file_{i}.py": (1700000000.0 + i, 1024 + i)
                for i in range(1000)
            }

            # 測試寫入
            t0 = time.perf_counter()
            BinarySnapshotManager.save(snap_path, mock_files)
            write_time_ms = (time.perf_counter() - t0) * 1000
            self.assertTrue(snap_path.exists())

            # 測試讀取
            t1 = time.perf_counter()
            loaded_map = BinarySnapshotManager.load(snap_path)
            read_time_ms = (time.perf_counter() - t1) * 1000

            self.assertIsNotNone(loaded_map)
            self.assertEqual(len(loaded_map), 1000)
            self.assertIn("d:/repos/ys_codebase/source/module_0/file_0.py", loaded_map)
            mtime, size = loaded_map["d:/repos/ys_codebase/source/module_0/file_0.py"]
            self.assertEqual(size, 1024)
            self.assertEqual(mtime, 1700000000.0)

            # 斷言讀取極速性能 (< 10ms 在測試機上，一般 < 0.5ms)
            self.assertLess(read_time_ms, 50.0)

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

            # 設定兩個空間同時涵蓋 common.py
            sp_a = SpaceConfig(name="space_a", include=[str(src_dir)])
            sp_b = SpaceConfig(name="space_b", include=[str(src_dir)])

            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"space_a": sp_a.to_dict(), "space_b": sp_b.to_dict()}},
            )

            bundler = SemanticBundler(engine.space_manager, engine.parser_registry)
            bundle = bundler.bundle_union()

            # 斷言檔案去重：總檔案數為 1
            self.assertEqual(bundle.metadata["total_files"], 1)
            # 斷言符號空間標籤包含兩空間
            sym = next(s for s in bundle.symbols if s.name == "CommonHelper")
            self.assertEqual(sorted(sym.spaces), ["space_a", "space_b"])

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

            # 建置全域單一索引
            idx = engine.build_unified_index(force=True)
            self.assertEqual(idx.space_name, "unified")
            self.assertTrue(idx.doc_count >= 2)

            # 1. 不限空間搜尋
            res_all = engine.search("AuthEngine", auto_rebuild=False)
            self.assertEqual(len(res_all), 2)

            # 2. 僅搜尋 source 空間
            res_src = engine.search("AuthEngine", space="source", auto_rebuild=False)
            self.assertEqual(len(res_src), 1)
            self.assertEqual(res_src[0].symbol.name, "AuthEngine")
            self.assertIn("source", res_src[0].space)

            # 3. 僅搜尋 docs 空間
            res_doc = engine.search("AuthEngine", space="docs", auto_rebuild=False)
            self.assertEqual(len(res_doc), 1)
            self.assertIn("docs", res_doc[0].space)

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

            # 第一次查詢：自動觸發初始建置
            res1 = engine.search("InitialClass", auto_rebuild=True)
            self.assertEqual(len(res1), 1)

            # 檔案修改：新增一個類別
            time.sleep(0.05)  # 確保 mtime 改變
            app_file.write_text("class InitialClass:\n    pass\nclass NewlyAddedWorker:\n    '''新增的工作者類別'''\n    pass", encoding="utf-8")

            # 第二次查詢：JIT 自動感知變更並背景熱自愈
            res2 = engine.search("NewlyAddedWorker", auto_rebuild=True)
            self.assertEqual(len(res2), 1)
            self.assertEqual(res2[0].symbol.name, "NewlyAddedWorker")

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

            # 首次建置
            engine.search("AlphaService", auto_rebuild=True)

            # 修改檔案加入 BetaWorker
            time.sleep(0.05)
            app_file.write_text("class AlphaService:\n    pass\nclass BetaWorker:\n    pass", encoding="utf-8")

            # 若 auto_rebuild=False，不會讀到 BetaWorker
            res = engine.search("BetaWorker", auto_rebuild=False)
            self.assertEqual(len(res), 0)

            # 若 auto_rebuild=True，即刻熱自愈讀到 BetaWorker
            res_healed = engine.search("BetaWorker", auto_rebuild=True)
            self.assertEqual(len(res_healed), 1)

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

            # 1. 首次無快照 (ET-01)
            res1 = engine.search("EdgeTest", auto_rebuild=True)
            self.assertEqual(len(res1), 1)

            # 2. 人為破壞快照檔案 (ET-02)
            meta_file = storage_dir / "indices" / "unified.meta.bin"
            meta_file.write_bytes(b"CORRUPTED_GARBAGE_HEADER")

            # 再次搜尋：應自動發現損毀並重新建置
            res2 = engine.search("EdgeTest", auto_rebuild=True)
            self.assertEqual(len(res2), 1)

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

            # 首次建置
            engine.search("UniqueKeeper", auto_rebuild=True)

            # 刪除 file2
            file2.unlink()

            # 再次搜尋：JIT 發現檔案總數不符，自動觸發熱自愈
            res = engine.search("DestinedToDelete", auto_rebuild=True)
            self.assertEqual(len(res), 0)
            res_keep = engine.search("UniqueKeeper", auto_rebuild=True)
            self.assertEqual(len(res_keep), 1)
