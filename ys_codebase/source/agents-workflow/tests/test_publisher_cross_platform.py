"""
Unit tests for ReleasePublisher cross-platform stability, CRLF->LF sha1 normalization,
and release manifest migration/isolation to cache://.
Validates:
- _get_source_file_sha1 returns identical sha1 for CRLF and LF text files
- Binary files fallback safely to raw bytes sha1 without UnicodeDecodeError
- PROJECT_MANIFEST_CACHE_URI is used under cache://
- Legacy storage manifest is automatically migrated and cleaned up
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import (
    ReleasePublisher,
    PROJECT_MANIFEST_CACHE_URI,
    LEGACY_PROJECT_MANIFEST_STORAGE_URI,
)
from agents_workflow.targets import ReleaseTargetManager

try:
    from core import uri
except ImportError:
    uri = None

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


@require(Requirement.ENV)
class TestPublisherCrossPlatform(YSCBTestCase):
    """測試發布引擎之跨平台換行符正規化與清單隔離。"""

    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_cross_")

    def test_sha1_crlf_normalization(self):
        """FT-01: 驗證 CRLF 與 LF 文字內容計算出完全相同的 SHA-1 雜湊值。"""
        # 建立目錄型資產測試
        dir_lf = os.path.join(self.temp_dir, "dir_lf")
        dir_crlf = os.path.join(self.temp_dir, "dir_crlf")
        os.makedirs(dir_lf, exist_ok=True)
        os.makedirs(dir_crlf, exist_ok=True)

        with open(os.path.join(dir_lf, "sample.md"), "wb") as f:
            f.write(b"# Title\nLine 1\nLine 2\n")

        with open(os.path.join(dir_crlf, "sample.md"), "wb") as f:
            f.write(b"# Title\r\nLine 1\r\nLine 2\r\n")

        sha1_lf = self.publisher._get_source_file_sha1(dir_lf)
        sha1_crlf = self.publisher._get_source_file_sha1(dir_crlf)
        self.assertEqual(sha1_lf, sha1_crlf)

        # 建立單檔案測試
        single_lf = os.path.join(self.temp_dir, "single_lf.txt")
        single_crlf = os.path.join(self.temp_dir, "single_crlf.txt")
        with open(single_lf, "wb") as f:
            f.write(b"Hello\nWorld\n")
        with open(single_crlf, "wb") as f:
            f.write(b"Hello\r\nWorld\r\n")

        single_sha1_lf = self.publisher._get_source_file_sha1(single_lf)
        single_sha1_crlf = self.publisher._get_source_file_sha1(single_crlf)
        self.assertEqual(single_sha1_lf, single_sha1_crlf)
        self.mark_passed()

    def test_binary_file_sha1_fallback(self):
        """ET-01 (EC-01): 驗證非 UTF-8 二進位檔案安全降級至 raw bytes，不崩潰。"""
        bin_dir = os.path.join(self.temp_dir, "bin_dir")
        os.makedirs(bin_dir, exist_ok=True)

        # 寫入無效 UTF-8 位元組序列 (如 0x80, 0xFF)
        raw_binary = b"\x80\xff\xfe\x00\x01\x02\r\n\x88\x99"
        bin_file = os.path.join(bin_dir, "data.bin")
        with open(bin_file, "wb") as f:
            f.write(raw_binary)

        sha1_val = self.publisher._get_source_file_sha1(bin_dir)
        self.assertEqual(len(sha1_val), 40)
        self.mark_passed()

    def test_manifest_cache_isolation_and_migration(self):
        """FT-02 (EC-02): 驗證 manifest 儲存至 cache:// 且舊版 storage manifest 自動遷移並物理刪除。"""
        # 清理可能既有的快取檔
        if uri.exists(PROJECT_MANIFEST_CACHE_URI):
            uri.remove(PROJECT_MANIFEST_CACHE_URI)

        # 1. 模擬舊版 storage manifest 存在
        fake_legacy = {
            "fingerprint": "fake_hash_123",
            "active_targets": ["antigravity"],
            "published_files": ["project://AGENTS.md"],
            "combined_fingerprint": "fake_hash_123",
            "updated_at": "2026-10-18 00:00:00"
        }
        uri.write_json(LEGACY_PROJECT_MANIFEST_STORAGE_URI, fake_legacy)
        self.assertTrue(uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI))

        # 2. 觸發遷移
        self.publisher._migrate_legacy_storage_manifest()

        # 3. 驗證舊檔已刪除，新檔已存在於 cache:// 且內容一致
        self.assertFalse(uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI))
        self.assertTrue(uri.exists(PROJECT_MANIFEST_CACHE_URI))
        migrated = uri.read_json(PROJECT_MANIFEST_CACHE_URI)
        self.assertEqual(migrated.get("fingerprint"), "fake_hash_123")
        self.mark_passed()

    def test_release_never_writes_tracked_storage(self):
        """ET-02 (FR-02): 完整發布後，Git 追蹤區 storage://agents-workflow/release_manifest.json 不存在，清單僅存於 cache://。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)
        uri.write_json(LEGACY_PROJECT_MANIFEST_STORAGE_URI, {"published_files": [], "fingerprint": "legacy"})

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertFalse(uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI))
        self.assertTrue(uri.exists(PROJECT_MANIFEST_CACHE_URI))

        # 再次發布（短路路徑）亦不得重建舊檔
        self.publisher.release_all(force=False)
        self.assertFalse(uri.exists(LEGACY_PROJECT_MANIFEST_STORAGE_URI))
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
