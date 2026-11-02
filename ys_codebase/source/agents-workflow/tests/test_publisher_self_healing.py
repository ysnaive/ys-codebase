"""
Unit tests for agents-workflow ReleasePublisher self-healing & fingerprint enhancements:
1. Directory SHA-1 stat-first cache reuse (zero file read I/O on cache hit).
2. Stage 0 source fingerprint sensitivity to active locale chain & core config changes.
3. Stage 0 short-circuit validation of AGENTS.md / agent_rules managed block markers.
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher

try:
    from core import uri, vfs
except ImportError:
    uri = None
    vfs = None

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


@require(Requirement.LOGIC | Requirement.ENV)
class TestPublisherSelfHealing(YSCBTestCase):
    """驗證 ReleasePublisher 目錄 SHA-1 快取、語系/組態指紋與 AGENTS.md 託管標記自癒。"""

    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_self_heal_")

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_directory_sha1_cache_hit_skips_file_reads(self):
        """驗證目錄走訪計算 SHA-1 時逐檔複用 _sha1_cache，快取命中時零檔案內容讀取 I/O。"""
        skill_dir = os.path.join(self.temp_dir, "mock_skill")
        ref_dir = os.path.join(skill_dir, "references")
        os.makedirs(ref_dir, exist_ok=True)

        f1 = os.path.join(skill_dir, "SKILL.md")
        f2 = os.path.join(ref_dir, "guide.md")
        with open(f1, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Mock Skill\nContent line 1\n")
        with open(f2, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Guide\nReference details\n")

        # 第一次計算：建立快取
        sha1_first = self.publisher._get_source_file_sha1(skill_dir)
        self.assertEqual(len(sha1_first), 40)
        self.assertIn(f1, self.publisher._sha1_cache)
        self.assertIn(f2, self.publisher._sha1_cache)

        # 第二次計算：若觸發 open() 讀檔則拋出異常，驗證 100% 命中 _sha1_cache
        with patch("builtins.open", side_effect=AssertionError("Should not open file on SHA-1 cache hit")):
            sha1_second = self.publisher._get_source_file_sha1(skill_dir)
        self.assertEqual(sha1_first, sha1_second)

        # 修改其中一檔內容與大小 -> 快取失效並算出新雜湊
        with open(f2, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Guide\nUpdated reference details with new content\n")
        sha1_third = self.publisher._get_source_file_sha1(skill_dir)
        self.assertNotEqual(sha1_first, sha1_third)
        self.mark_passed()

    def test_fingerprint_sensitive_to_locale_chain_and_core_config(self):
        """驗證 compute_source_fingerprint 對 core.locale.get_active_chain() 與 config://core 變更敏感。"""
        fp_base = self.publisher.compute_source_fingerprint(["antigravity"])

        with patch("core.locale.get_active_chain", return_value=["nouns-claude", "en", "zh"]):
            fp_locale_changed = self.publisher.compute_source_fingerprint(["antigravity"])
        self.assertNotEqual(fp_base, fp_locale_changed)

        with patch("core.config.get_all", side_effect=lambda mod: {"locale": "ja", "project_root": "./"} if mod == "core" else {}):
            fp_cfg_changed = self.publisher.compute_source_fingerprint(["antigravity"])
        self.assertNotEqual(fp_base, fp_cfg_changed)
        self.mark_passed()

    def test_short_circuit_detects_missing_agents_md_markers_and_heals(self):
        """驗證 AGENTS.md 或 agent_rules 託管標記缺失時，_check_short_circuit 回傳 False 觸發自癒。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        proj_root = uri.resolve("project://", interactive=False) if uri else os.getcwd()
        agents_md_path = os.path.join(proj_root, "AGENTS.md")
        self.assertTrue(os.path.isfile(agents_md_path))

        # 破壞 AGENTS.md 內的 YSCB 託管標記但保留檔案存在
        with open(agents_md_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Corrupted AGENTS.md without markers\n\n## Custom Section\nKeep me.\n")

        # 再次執行 release_all(force=False) 應偵測標記缺失、拒絕短路並自動修復託管區塊
        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["short_circuited"])

        with open(agents_md_path, "r", encoding="utf-8") as f:
            healed_text = f.read()
        self.assertIn("<!-- YSCB_AGENTS_BEGIN -->", healed_text)
        self.assertIn("<!-- YSCB_AGENTS_END -->", healed_text)
        self.assertIn("Keep me.", healed_text)

        # 同時測試 agent_rules 結構之 inject vs copy 模式
        dummy_rule_file = os.path.join(self.temp_dir, "CUSTOM_RULES.md")
        with open(dummy_rule_file, "w", encoding="utf-8") as f:
            f.write("Plain content without custom markers\n")

        mock_targets = {
            "custom_t": {
                "name": "custom_t",
                "agent_rules": [
                    {
                        "target": dummy_rule_file,
                        "mode": "inject",
                        "marker": "CUSTOM_MARK",
                    }
                ],
            }
        }
        old_manifest = {
            "fingerprint": "fp1",
            "published_files": [dummy_rule_file],
        }
        can_sc_inject, _ = self.publisher._check_short_circuit(
            force=False,
            proj_targets=["custom_t"],
            local_targets=[],
            active_target_names=["custom_t"],
            old_proj_manifest=old_manifest,
            old_local_manifest={},
            proj_fingerprint="fp1",
            local_fingerprint="",
            all_registered_targets=mock_targets,
            proj_root=self.temp_dir,
        )
        self.assertFalse(can_sc_inject)

        # 若 mode 為 copy，則不要求標記存在即可短路
        mock_targets["custom_t"]["agent_rules"][0]["mode"] = "copy"
        can_sc_copy, _ = self.publisher._check_short_circuit(
            force=False,
            proj_targets=["custom_t"],
            local_targets=[],
            active_target_names=["custom_t"],
            old_proj_manifest=old_manifest,
            old_local_manifest={},
            proj_fingerprint="fp1",
            local_fingerprint="",
            all_registered_targets=mock_targets,
            proj_root=self.temp_dir,
        )
        self.assertTrue(can_sc_copy)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
