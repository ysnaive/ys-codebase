"""
Unit Tests for agents-workflow Release Targets (Antigravity, Claude Code, OpenAI Codex).
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import unittest
from typing import Dict, Any, List

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher
from agents_workflow.targets import ReleaseTargetManager

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


class TestReleaseTargets(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    def test_ft_01_manifest_targets_discovery(self):
        """FT-01: 驗證 manifest.json 中 antigravity, claude, codex 三大 target 均被正確解析。"""
        targets = self.compiler.get_release_targets()
        target_names = [t.get("name") for t in targets]
        
        self.assertIn("antigravity", target_names)
        self.assertIn("claude", target_names)
        self.assertIn("codex", target_names)

    def test_ft_02_list_targets_output(self):
        """FT-02: 驗證 ReleaseTargetManager.list_targets() 正確列出各 target 資訊。"""
        target_list = ReleaseTargetManager.list_targets()
        names = [t["name"] for t in target_list]
        
        self.assertIn("antigravity", names)
        self.assertIn("claude", names)
        self.assertIn("codex", names)
        
        claude_info = next(t for t in target_list if t["name"] == "claude")
        self.assertIn("Claude Code", claude_info["description"])

        codex_info = next(t for t in target_list if t["name"] == "codex")
        self.assertIn("Codex", codex_info["description"])

    def test_ft_03_claude_projections_and_materialization(self):
        """FT-03: 驗證 claude target 投影拓撲映射正確包含 .claude/commands 與 .claude/.yscb/。"""
        targets = {t["name"]: t for t in self.compiler.get_release_targets()}
        claude_target = targets.get("claude", {})
        
        projections = claude_target.get("projections", {})
        self.assertEqual(projections.get("workflow", {}).get("target_dir"), "project://.claude/commands")
        self.assertEqual(projections.get("template", {}).get("target_dir"), "project://.claude/.yscb/templates")
        self.assertEqual(projections.get("standard", {}).get("target_dir"), "project://.claude/.yscb/standards")

        # 驗證 deployment_map 計算
        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res.get("success", False))
        resolved_items = stage1_res.get("resolved_items", [])
        dep_map, target_items = self.publisher.build_deployment_map(claude_target, resolved_items)
        
        # 斷言工作流路徑指向 commands
        workflow_paths = [p for p in dep_map.values() if os.path.basename(os.path.dirname(p)) == "commands"]
        self.assertGreater(len(workflow_paths), 0)

    def test_ft_04_codex_projections_and_materialization(self):
        """FT-04: 驗證 codex target 投影拓撲映射正確包含 .codex/workflows 與 .codex/.yscb/。"""
        targets = {t["name"]: t for t in self.compiler.get_release_targets()}
        codex_target = targets.get("codex", {})
        
        projections = codex_target.get("projections", {})
        self.assertEqual(projections.get("workflow", {}).get("target_dir"), "project://.codex/workflows")
        self.assertEqual(projections.get("template", {}).get("target_dir"), "project://.codex/.yscb/templates")
        self.assertEqual(projections.get("standard", {}).get("target_dir"), "project://.codex/.yscb/standards")

        # 驗證 deployment_map 計算
        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res.get("success", False))
        resolved_items = stage1_res.get("resolved_items", [])
        dep_map, target_items = self.publisher.build_deployment_map(codex_target, resolved_items)
        
        # 斷言工作流路徑指向 workflows
        workflow_paths = [p for p in dep_map.values() if os.path.basename(os.path.dirname(p)) == "workflows"]
        self.assertGreater(len(workflow_paths), 0)


if __name__ == "__main__":
    unittest.main()
