"""
Unit tests for agents-workflow ReleasePublisher self-healing & fingerprint enhancements:
1. Directory SHA-1 stat-first cache reuse (zero file read I/O on cache hit).
2. Stage 0 source fingerprint sensitivity to active locale chain & core config changes.
3. Stage 0 short-circuit validation of AGENTS.md / agent_rules managed block markers.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if getattr(sys.modules.get("tests"), "PKG_ROOT", None) != Path(__file__).resolve().parent.parent:
    sys.modules.pop("tests", None)

from tests import ConfigStateSnapshot

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.LOGIC | Requirement.ENV)
class TestPublisherSelfHealing(YSCBTestCase):
    """驗證 ReleasePublisher 目錄 SHA-1 快取、語系/組態指紋與 AGENTS.md 託管標記自癒。"""

    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_self_heal_")
        self.compiler = ArtifactCompiler(host_dir=self.temp_dir)
        self.publisher = ReleasePublisher(compiler=self.compiler, host_dir=self.temp_dir)

    def tearDown(self):
        self._snapshot.restore()
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

        sha1_first = self.publisher._get_source_file_sha1(skill_dir)
        self.assertEqual(len(sha1_first), 40)
        self.assertIn(f1, self.publisher._sha1_cache)
        self.assertIn(f2, self.publisher._sha1_cache)

        with patch("builtins.open", side_effect=AssertionError("Should not open file on SHA-1 cache hit")):
            sha1_second = self.publisher._get_source_file_sha1(skill_dir)
        self.assertEqual(sha1_first, sha1_second)

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
        """驗證 AGENTS.md 或 agent_rules 託管標記缺失時，_check_short_circuit 回傳 False 觸發自癒（完全隔離於 self.temp_dir）。"""
        from core import uri as core_uri

        orig_resolve = core_uri.resolve

        def _isolated_resolve(uri_str: str, *args, **kwargs) -> str:
            if uri_str == "project://":
                return self.temp_dir
            if isinstance(uri_str, str) and uri_str.startswith("project://"):
                rel = uri_str[len("project://"):].lstrip("/\\")
                return os.path.normpath(os.path.join(self.temp_dir, rel.replace("/", os.sep)))
            return orig_resolve(uri_str, *args, **kwargs)

        with patch("core.uri.resolve", side_effect=_isolated_resolve):
            res1 = self.publisher.release_all(force=True)
            self.assertTrue(res1["success"])

            agents_md_path = os.path.join(self.temp_dir, "AGENTS.md")
            self.assertTrue(os.path.isfile(agents_md_path))

            with open(agents_md_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("# Corrupted AGENTS.md without markers\n\n## Custom Section\nKeep me.\n")

            res2 = self.publisher.release_all(force=False)
            self.assertTrue(res2["success"])
            self.assertFalse(res2["short_circuited"])

            with open(agents_md_path, "r", encoding="utf-8") as f:
                healed_text = f.read()
            self.assertIn("<!-- YSCB_AGENTS_BEGIN -->", healed_text)
            self.assertIn("<!-- YSCB_AGENTS_END -->", healed_text)
            self.assertIn("Keep me.", healed_text)

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
