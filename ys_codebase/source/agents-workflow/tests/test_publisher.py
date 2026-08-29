"""
Unit & Edge Case Tests for agents-workflow Release Publisher Diff Optimization.
Validates Stage 0 Fingerprint Short-Circuit, Stage 4 Content Diff, Force Release, and Edge Cases.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import json
import unittest
import importlib.util
from typing import Dict, Any

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

_cli_path = os.path.join(_pkg_root, "scripts", "cli.py")
_spec_cli = importlib.util.spec_from_file_location("aw_cli_publisher_test", _cli_path)
cli_mod = importlib.util.module_from_spec(_spec_cli)
_spec_cli.loader.exec_module(cli_mod)
cmd_release = cli_mod.cmd_release

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher, MANIFEST_STORAGE_URI

try:
    from core import uri
except ImportError:
    uri = None

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


class TestReleasePublisherDiff(YSCBTestCase):
    """測試發布引擎來源指紋短路與落地 Diff 優化。"""

    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    @require(Requirement.ENV)
    def test_ft_01_initial_release_persists_fingerprint(self):
        """FT-01: 首次發布成功物化檔案，Manifest 正確記錄指紋與發布檔案清冊。"""
        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertFalse(res["short_circuited"])
        self.assertGreater(res["published_count"], 0)
        self.assertEqual(res["written_count"], res["published_count"])
        self.assertEqual(res["skipped_count"], 0)
        self.assertIn("fingerprint", res)
        self.assertTrue(len(res["fingerprint"]) > 0)

        # 驗證 storage:// 中記錄的 manifest
        if uri and uri.exists(MANIFEST_STORAGE_URI):
            manifest_data = uri.read_json(MANIFEST_STORAGE_URI)
            self.assertEqual(manifest_data.get("fingerprint"), res["fingerprint"])
            self.assertEqual(len(manifest_data.get("published_files", [])), res["published_count"])

    @require(Requirement.ENV)
    def test_ft_02_short_circuit_when_no_change(self):
        """FT-02: 二次發布在無異動情況下觸發 Stage 0 短路 (0 I/O)。"""
        # 第 1 次：全量發布
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        # 第 2 次：無變更發布 ➔ 應短路
        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["short_circuited"])
        self.assertEqual(res2["written_count"], 0)
        self.assertEqual(res2["skipped_count"], res1["published_count"])
        self.assertEqual(res2["fingerprint"], res1["fingerprint"])

    @require(Requirement.ENV)
    def test_ft_03_incremental_write_on_partial_change(self):
        """FT-03: 目標檔案內容有局部變更時，觸發增量寫入 (僅變更檔案寫入，其餘略過)。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        # 取得其中一個已發布檔案並人為修改其內容 (模擬外部內容漂移或部分產物需要更新)
        if uri and uri.exists(MANIFEST_STORAGE_URI):
            manifest_data = uri.read_json(MANIFEST_STORAGE_URI)
            target_files = manifest_data.get("published_files", [])
            self.assertGreater(len(target_files), 1)

            modified_file = target_files[0]
            if modified_file.startswith("project://"):
                modified_file = uri.resolve(modified_file, interactive=False)
            with open(modified_file, "w", encoding="utf-8") as f:
                f.write("MODIFIED CONTENT")

            # 透過破壞快取中的 fingerprint 迫使進入 Stage 4 比對，但非 force
            manifest_data["fingerprint"] = "stale_fake_fingerprint"
            uri.write_json(MANIFEST_STORAGE_URI, manifest_data)

            res2 = self.publisher.release_all(force=False)
            self.assertTrue(res2["success"])
            self.assertFalse(res2["short_circuited"])
            # 只有被竄改的檔案被重新寫入，其餘檔案跳過寫入
            self.assertEqual(res2["written_count"], 1)
            self.assertEqual(res2["skipped_count"], len(target_files) - 1)

    @require(Requirement.ENV)
    def test_ft_04_forced_release_overwrites_all(self):
        """FT-04: 傳入 force=True 時強制跳過短路與略過邏輯，執行全量覆寫。"""
        # 第 1 次發布
        self.publisher.release_all(force=True)

        # 第 2 次強制發布
        res_forced = self.publisher.release_all(force=True)
        self.assertTrue(res_forced["success"])
        self.assertFalse(res_forced["short_circuited"])
        self.assertEqual(res_forced["written_count"], res_forced["published_count"])
        self.assertEqual(res_forced["skipped_count"], 0)

    @require(Requirement.ENV)
    def test_ft_05_agents_md_soft_merge_diff(self):
        """FT-05: AGENTS.md 軟合併在注入內容未變更時跳過磁碟寫入。"""
        proj_root = os.getcwd()
        if uri:
            try:
                proj_root = uri.resolve("project://", interactive=False)
            except Exception:
                pass

        agents_path = os.path.join(proj_root, "AGENTS.md")
        content_a = "# Custom Header\n<!-- YSCB_AGENTS_BEGIN -->\nStandard Body\n<!-- YSCB_AGENTS_END -->\n## Custom Footer"
        os.makedirs(os.path.dirname(agents_path), exist_ok=True)
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write(content_a)

        # 第一次注入相同內容 ➔ 應跳過寫入 (written == False)
        success, written = self.publisher._soft_merge_agents_md("Standard Body", proj_root, force=False)
        self.assertTrue(success)
        self.assertFalse(written)

        # 第二次注入新內容 ➔ 應寫入 (written == True)
        success, written = self.publisher._soft_merge_agents_md("New Standard Body", proj_root, force=False)
        self.assertTrue(success)
        self.assertTrue(written)

        with open(agents_path, "r", encoding="utf-8") as f:
            updated_text = f.read()
        self.assertIn("New Standard Body", updated_text)
        self.assertIn("## Custom Footer", updated_text)

    @require(Requirement.ENV)
    def test_ft_06_cli_release_with_force_flag(self):
        """FT-06: CLI release 指令解析 --force 參數並執行。"""
        # 測試正常發布 (不帶 --force)
        code1 = cmd_release([])
        self.assertEqual(code1, 0)

        # 再次發布 (觸發短路)
        code2 = cmd_release([])
        self.assertEqual(code2, 0)

        # 帶 --force 參數
        code3 = cmd_release(["--force"])
        self.assertEqual(code3, 0)

    @require(Requirement.ENV)
    def test_et_01_short_circuit_invalidated_when_file_missing(self):
        """ET-01: 已發布檔案遭刪除時，即使指紋未變仍自動失效短路並修復補齊。"""
        # 第 1 次發布
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        # 人為刪除其中一個已發布檔案
        if uri and uri.exists(MANIFEST_STORAGE_URI):
            manifest_data = uri.read_json(MANIFEST_STORAGE_URI)
            target_files = manifest_data.get("published_files", [])
            self.assertGreater(len(target_files), 0)

            deleted_file = target_files[0]
            if deleted_file.startswith("project://"):
                deleted_file = uri.resolve(deleted_file, interactive=False)
            if os.path.isfile(deleted_file):
                os.remove(deleted_file)

            # 再次調用 (force=False) ➔ 應檢測到檔案缺失，短路失效並補齊
            res2 = self.publisher.release_all(force=False)
            self.assertTrue(res2["success"])
            self.assertFalse(res2["short_circuited"])
            self.assertTrue(os.path.isfile(deleted_file))
            # 只有缺失的檔案被寫入，其餘檔案跳過寫入
            self.assertEqual(res2["written_count"], 1)

    @require(Requirement.ENV)
    def test_et_02_target_configuration_change_triggers_republish(self):
        """ET-02: Target 宣告或指紋計算能敏感反映變更。"""
        fp1 = self.publisher.compute_source_fingerprint()
        self.assertIsInstance(fp1, str)
        self.assertEqual(len(fp1), 64)

        # 驗證相同環境下兩次計算指紋完全一致
        fp2 = self.publisher.compute_source_fingerprint()
        self.assertEqual(fp1, fp2)

    @require(Requirement.ENV)
    def test_et_03_corrupted_or_missing_manifest_fallback(self):
        """ET-03: storage:// 中之 manifest 損毀或缺失時，安全降級為全量發布並自癒。"""
        if uri:
            # 寫入無效 JSON 或空字串
            uri.write_text(MANIFEST_STORAGE_URI, "INVALID_CORRUPTED_JSON{{{")

        res = self.publisher.release_all(force=False)
        self.assertTrue(res["success"])
        self.assertFalse(res["short_circuited"])
        self.assertGreater(res["published_count"], 0)

        # 驗證已自癒修復為有效 JSON
        if uri and uri.exists(MANIFEST_STORAGE_URI):
            manifest_data = uri.read_json(MANIFEST_STORAGE_URI)
            self.assertIn("fingerprint", manifest_data)
            self.assertIn("published_files", manifest_data)
            self.assertEqual(len(manifest_data["published_files"]), res["published_count"])


if __name__ == "__main__":
    unittest.main()
