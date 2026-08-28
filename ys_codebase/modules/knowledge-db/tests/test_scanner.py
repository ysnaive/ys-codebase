"""
Unit Tests for knowledge-db FingerprintScanner, Two-Stage Incremental Diff, and Atomic Persistence.
"""

import json
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
from knowledge_db.scanner import FileFingerprint, FingerprintScanner
from knowledge_db.schema import SpaceConfig
from knowledge_db.space import SpaceManager


class TestScanner(YSCBTestCase):
    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_06_stage_1_unchanged_fast_path(self):
        """FT-06: 驗證 Stage 1 (mtime+size) 初篩比對與 UNCHANGED 極速判定"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file1 = src_dir / "mod1.py"
            file1.write_text("print('hello')", encoding="utf-8")

            space_cfg = SpaceConfig(name="test_space", include=[str(src_dir)])
            sm = SpaceManager(storage_dir=storage_dir, contributes_data={"spaces": {"test_space": space_cfg.to_dict()}})
            scanner = FingerprintScanner(sm)

            # 首次掃描: 應為 ADDED
            diff1 = scanner.scan_space(space_cfg)
            self.assertEqual(len(diff1.added), 1)
            self.assertEqual(len(diff1.unchanged), 0)

            # 第二次掃描 (未修改): 應走 Stage 1 判定為 UNCHANGED
            diff2 = scanner.scan_space(space_cfg)
            self.assertEqual(len(diff2.added), 0)
            self.assertEqual(len(diff2.modified), 0)
            self.assertEqual(len(diff2.deleted), 0)
            self.assertEqual(len(diff2.unchanged), 1)
            self.assertFalse(diff2.has_changes)

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_07_stage_2_touch_file_sha1_match(self):
        """FT-07: 驗證 Stage 2 校驗：touch 檔案時比對 SHA1 一致僅更新快取 mtime 並標記 UNCHANGED (EC-04)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file1 = src_dir / "app.py"
            file1.write_text("def run(): pass", encoding="utf-8")

            space_cfg = SpaceConfig(name="test_space", include=[str(src_dir)])
            sm = SpaceManager(storage_dir=storage_dir, contributes_data={"spaces": {"test_space": space_cfg.to_dict()}})
            scanner = FingerprintScanner(sm)

            # 首次掃描
            scanner.scan_space(space_cfg)

            # 模擬 touch 檔案 (修改 mtime 但內容不變)
            old_stat = file1.stat()
            new_mtime = old_stat.st_mtime + 100.0
            os.utime(str(file1), (new_mtime, new_mtime))

            # 再次掃描: Stage 1 不符進入 Stage 2，SHA1 一致 ➔ 標記 UNCHANGED
            diff = scanner.scan_space(space_cfg)
            self.assertEqual(len(diff.added), 0)
            self.assertEqual(len(diff.modified), 0)
            self.assertEqual(len(diff.deleted), 0)
            self.assertEqual(len(diff.unchanged), 1)

            # 驗證快取中 mtime 已更新
            fps = scanner.load_fingerprints("test_space")
            self.assertAlmostEqual(fps["app.py"].mtime, new_mtime, places=1)

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_08_diff_detection_added_modified_deleted(self):
        """FT-08: 驗證檔案增量偵測：新增 (ADDED)、修改 (MODIFIED)、刪除 (DELETED)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            file_keep = src_dir / "keep.py"
            file_keep.write_text("keep content", encoding="utf-8")
            file_mod = src_dir / "mod.py"
            file_mod.write_text("original content", encoding="utf-8")
            file_del = src_dir / "del.py"
            file_del.write_text("to delete", encoding="utf-8")

            space_cfg = SpaceConfig(name="test_space", include=[str(src_dir)])
            sm = SpaceManager(storage_dir=storage_dir, contributes_data={"spaces": {"test_space": space_cfg.to_dict()}})
            scanner = FingerprintScanner(sm)

            # 首次全量掃描
            diff1 = scanner.scan_space(space_cfg)
            self.assertEqual(len(diff1.added), 3)

            # 變更狀態: 新增 new.py、修改 mod.py、刪除 del.py、保留 keep.py
            file_new = src_dir / "new.py"
            file_new.write_text("new file content", encoding="utf-8")

            # 稍微延遲並更新內容以確保 mtime 與內容均變更
            file_mod.write_text("modified new content", encoding="utf-8")
            os.remove(str(file_del))

            diff2 = scanner.scan_space(space_cfg)
            self.assertTrue(diff2.has_changes)
            self.assertEqual(len(diff2.added), 1)
            self.assertEqual(diff2.added[0].relpath, "new.py")

            self.assertEqual(len(diff2.modified), 1)
            self.assertEqual(diff2.modified[0].relpath, "mod.py")

            self.assertEqual(len(diff2.deleted), 1)
            self.assertEqual(diff2.deleted[0], "del.py")

            self.assertEqual(len(diff2.unchanged), 1)
            self.assertEqual(diff2.unchanged[0].relpath, "keep.py")

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_09_scan_all_spaces_and_atomic_save(self):
        """FT-09: 驗證 scan_all_spaces 全空間聯集掃描與原子寫入持久化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_a = temp_path / "src_a"
            src_a.mkdir(parents=True)
            (src_a / "a.py").write_text("a", encoding="utf-8")

            src_b = temp_path / "src_b"
            src_b.mkdir(parents=True)
            (src_b / "b.py").write_text("b", encoding="utf-8")

            storage_dir = temp_path / "storage"

            mock_contributes = {
                "spaces": {
                    "space_a": {"include": [str(src_a)]},
                    "space_b": {"include": [str(src_b)]},
                }
            }

            sm = SpaceManager(storage_dir=storage_dir, contributes_data=mock_contributes)
            scanner = FingerprintScanner(sm)

            results = scanner.scan_all_spaces()
            self.assertEqual(len(results), 2)
            self.assertIn("space_a", results)
            self.assertIn("space_b", results)
            self.assertEqual(len(results["space_a"].added), 1)
            self.assertEqual(len(results["space_b"].added), 1)

            # 驗證實體 fingerprints.json 是否正確寫入
            fp_a = storage_dir / "spaces" / "space_a" / "fingerprints.json"
            fp_b = storage_dir / "spaces" / "space_b" / "fingerprints.json"
            self.assertTrue(fp_a.exists())
            self.assertTrue(fp_b.exists())

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_et_01_corrupted_cache_self_healing(self):
        """ET-01: 驗證指紋快取檔案損毀時自癒重置為全量掃描並修復 (EC-03)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "test.py").write_text("content", encoding="utf-8")

            storage_dir = temp_path / "storage"
            space_dir = storage_dir / "spaces" / "corrupt_space"
            space_dir.mkdir(parents=True)

            # 人為寫入損毀的 JSON 內容
            corrupt_file = space_dir / "fingerprints.json"
            corrupt_file.write_text("NOT A VALID JSON {{{", encoding="utf-8")

            space_cfg = SpaceConfig(name="corrupt_space", include=[str(src_dir)])
            sm = SpaceManager(storage_dir=storage_dir, contributes_data={"spaces": {"corrupt_space": space_cfg.to_dict()}})
            scanner = FingerprintScanner(sm)

            # 執行掃描: 應自癒降級為全量掃描 (Added=1)
            diff = scanner.scan_space(space_cfg)
            self.assertEqual(len(diff.added), 1)

            # 驗證 fingerprints.json 已被修復為合法 JSON
            with open(corrupt_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("test.py", data)
