"""
Tests for agents-workflow Release Manifest Placement & Dual-Track Storage.
Validates Project targets -> storage:// (project:// format),
Local targets -> cache:// (absolute path format),
Dual-channel pruning, legacy manifest tolerance, and pure LF normalization.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import json
import unittest
from typing import Dict, Any

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import (
    ReleasePublisher,
    PROJECT_MANIFEST_STORAGE_URI,
    LOCAL_MANIFEST_CACHE_URI
)
from agents_workflow.targets import ReleaseTargetManager

try:
    from core import uri
except ImportError:
    uri = None

try:
    from core import config
except ImportError:
    config = None

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


class TestManifestPlacementAndDualTrack(YSCBTestCase):
    """測試發布清單分流 (Storage vs Cache) 與換行符號 LF 歸一化。"""

    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    @require(Requirement.ENV)
    def test_ft_01_project_target_saves_project_uris_in_storage(self):
        """FT-01: Project Target 發布至 storage://，且全部路徑為 project:// 語意格式。"""
        # 配置 Project targets = ['antigravity'], Local targets = []
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertGreater(res["published_count"], 0)

        # 驗證 storage:// manifest 存在且全為 project:// 協議
        self.assertTrue(uri.exists(PROJECT_MANIFEST_STORAGE_URI))
        data = uri.read_json(PROJECT_MANIFEST_STORAGE_URI)
        self.assertEqual(data.get("active_targets"), ["antigravity"])
        published = data.get("published_files", [])
        self.assertGreater(len(published), 0)

        for p in published:
            self.assertTrue(
                p.startswith("project://"),
                f"Expected path in storage manifest to start with 'project://', got: '{p}'"
            )
            self.assertNotIn(":", p.replace("project://", ""))
            self.assertNotIn("\\", p)

    @require(Requirement.ENV)
    def test_ft_02_local_target_saves_absolute_paths_in_cache(self):
        """FT-02: Local Target 發布至 cache://，且全部路徑為本機實體絕對路徑。"""
        # 配置 Project targets = [], Local targets = ['antigravity']
        ReleaseTargetManager.save_tier_targets([], is_project=True)
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertGreater(res["published_count"], 0)

        # 驗證 cache:// manifest 存在且全為絕對路徑
        self.assertTrue(uri.exists(LOCAL_MANIFEST_CACHE_URI))
        data = uri.read_json(LOCAL_MANIFEST_CACHE_URI)
        self.assertEqual(data.get("active_targets"), ["antigravity"])
        published = data.get("published_files", [])
        self.assertGreater(len(published), 0)

        for p in published:
            self.assertTrue(
                os.path.isabs(p),
                f"Expected path in cache manifest to be an absolute path, got: '{p}'"
            )
            self.assertFalse(p.startswith("project://"))

    @require(Requirement.ENV)
    def test_ft_03_mixed_targets_dual_channel_manifests(self):
        """FT-03: 混合 Targets (Local + Project) 同步獨立更新各自 Manifest。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        self.assertTrue(uri.exists(PROJECT_MANIFEST_STORAGE_URI))
        proj_data = uri.read_json(PROJECT_MANIFEST_STORAGE_URI)
        self.assertEqual(proj_data.get("active_targets"), ["antigravity"])
        for p in proj_data.get("published_files", []):
            self.assertTrue(p.startswith("project://"))

    @require(Requirement.ENV)
    def test_ft_04_legacy_absolute_path_manifest_tolerance(self):
        """FT-04: 歷史異機絕對路徑 (如 H:\\...) 讀取時不崩潰，安全自癒標準化。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        # 注入含有異機歷史絕對路徑的假 Manifest
        fake_legacy = {
            "fingerprint": "fake_legacy_fp",
            "active_targets": ["antigravity"],
            "published_files": [
                "H:\\UseFolder\\NonExistent\\legacy_file_01.md",
                "H:\\UseFolder\\NonExistent\\legacy_file_02.md"
            ],
            "updated_at": "2026-08-01 00:00:00"
        }
        uri.write_json(PROJECT_MANIFEST_STORAGE_URI, fake_legacy)

        # 執行發布 ➔ 不應拋出 FileNotFoundError 或路徑崩潰
        res = self.publisher.release_all(force=False)
        self.assertTrue(res["success"])

        # 發布完成後，storage manifest 應已自癒轉為 project:// 格式
        new_data = uri.read_json(PROJECT_MANIFEST_STORAGE_URI)
        for p in new_data.get("published_files", []):
            self.assertTrue(p.startswith("project://"))

    @require(Requirement.ENV)
    def test_ft_05_line_endings_are_pure_lf(self):
        """FT-05: 驗證發布物化產物之換行符號 100% 為純 LF (\\n)，無 CRLF (\\r\\n)。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        # 讀取 storage manifest 取得檔案
        data = uri.read_json(PROJECT_MANIFEST_STORAGE_URI)
        for p_uri in data.get("published_files", []):
            abs_p = uri.resolve(p_uri, interactive=False)
            if os.path.isfile(abs_p):
                with open(abs_p, "rb") as bf:
                    raw_bytes = bf.read()
                self.assertNotIn(
                    b"\r\n",
                    raw_bytes,
                    f"File '{abs_p}' contains CRLF (\\r\\n) but expected pure LF (\\n)."
                )


if __name__ == "__main__":
    unittest.main()
