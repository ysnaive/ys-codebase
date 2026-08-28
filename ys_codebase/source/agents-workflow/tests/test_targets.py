"""
Unit Tests for agents-workflow Release Targets (Antigravity, Claude Code, OpenAI Codex).
Covers Local by Default, --proj flag, multi-tier list_targets, and .gitignore soft-merge.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from typing import Dict, Any, List

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher, GITIGNORE_BEGIN_MARKER, GITIGNORE_END_MARKER
from agents_workflow.targets import ReleaseTargetManager

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


class TestReleaseTargets(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        try:
            from core import config
            config.reload()
        except Exception:
            pass

    def test_ft_01_manifest_targets_discovery(self):
        """FT-01: 驗證 manifest.json 中 antigravity, claude, codex 三大 target 均被正確解析。"""
        targets = self.compiler.get_release_targets()
        target_names = [t.get("name") for t in targets]
        
        self.assertIn("antigravity", target_names)
        self.assertIn("claude", target_names)
        self.assertIn("codex", target_names)
        self.mark_passed()

    def test_ft_02_list_targets_output(self):
        """FT-02: 驗證 ReleaseTargetManager.list_targets() 正確列出各 target 資訊與多層來源標籤。"""
        target_list = ReleaseTargetManager.list_targets()
        names = [t["name"] for t in target_list]
        
        self.assertIn("antigravity", names)
        self.assertIn("claude", names)
        self.assertIn("codex", names)
        
        claude_info = next(t for t in target_list if t["name"] == "claude")
        self.assertIn("Claude Code", claude_info["description"])

        codex_info = next(t for t in target_list if t["name"] == "codex")
        self.assertIn("Codex", codex_info["description"])
        self.mark_passed()

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
        self.mark_passed()

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
        self.mark_passed()

    def test_ft_05_local_by_default_and_proj_flag(self):
        """FT-05: 驗證 ReleaseTargetManager 預設 Local 操作與 is_project=True 模式。"""
        from core import config

        # 1. 預設 Local 新增 target 'claude'
        ReleaseTargetManager.add_target("claude", is_project=False)
        local_targets = config.get_raw("agents-workflow", "release_targets", local=True)
        self.assertIn("claude", local_targets)

        # 2. 以 is_project=True 新增 target 'codex'
        ReleaseTargetManager.add_target("codex", is_project=True)
        proj_targets = config.get_raw("agents-workflow", "release_targets", local=False)
        self.assertIn("codex", proj_targets)

        # 3. 檢視 list_targets 來源標註
        targets_info = {t["name"]: t for t in ReleaseTargetManager.list_targets()}
        self.assertEqual(targets_info["claude"]["status"], "[ENABLED (LOCAL)]")
        self.assertEqual(targets_info["codex"]["status"], "[ENABLED (PROJECT)]")

        # 4. 移除操作
        ReleaseTargetManager.remove_target("claude", is_project=False)
        self.assertNotIn("claude", config.get_raw("agents-workflow", "release_targets", local=True))

        ReleaseTargetManager.remove_target("codex", is_project=True)
        self.assertNotIn("codex", config.get_raw("agents-workflow", "release_targets", local=False))
        self.mark_passed()

    def test_ft_06_sync_gitignore_soft_merge(self):
        """FT-06: 驗證 .gitignore 區塊非破壞性軟合併、自訂規則保留、個別檔案精準忽略與自動新建。"""
        temp_dir = tempfile.mkdtemp(prefix="test_aw_gitignore_")
        try:
            fake_files = [
                os.path.join(temp_dir, ".agents", "workflows", "Auto.md"),
                os.path.join(temp_dir, ".agents", "workflows", "NewPlan.md"),
                os.path.join(temp_dir, ".agents", ".yscb", "templates", "P00.md"),
                os.path.join(temp_dir, ".claude", "commands", "Auto.md"),
            ]
            # 1. 在不存在的情況下新建
            res1 = self.publisher.sync_gitignore(
                active_targets=["antigravity", "claude"],
                published_files=fake_files,
                proj_root=temp_dir
            )
            self.assertTrue(res1["created"])
            gi_file = os.path.join(temp_dir, ".gitignore")
            self.assertTrue(os.path.isfile(gi_file))
            content1 = open(gi_file, "r", encoding="utf-8").read()
            self.assertIn(GITIGNORE_BEGIN_MARKER, content1)
            self.assertIn("/.agents/.yscb/templates/P00.md", content1)
            self.assertIn("/.agents/workflows/Auto.md", content1)
            self.assertIn("/.claude/commands/Auto.md", content1)
            # 確保不會整目錄忽略 /.agents/ 或 /.agents/.yscb/
            self.assertNotIn("\n.agents/\n", content1)
            self.assertNotIn("\n/.agents/\n", content1)
            self.assertNotIn("\n/.agents/.yscb/\n", content1)
            self.assertIn(GITIGNORE_END_MARKER, content1)


            # 2. 追加使用者自訂外部規則
            custom_prefix = "# User custom rules\n*.tmp\nnode_modules/\n\n"
            custom_suffix = "\n# Trailing custom rule\n.env\n"
            open(gi_file, "w", encoding="utf-8").write(custom_prefix + content1 + custom_suffix)

            # 3. 軟合併更新：更換發布檔案與 target
            fake_files_codex = [
                os.path.join(temp_dir, ".agents", "workflows", "Auto.md"),
                os.path.join(temp_dir, ".codex", "workflows", "Auto.md"),
            ]
            res2 = self.publisher.sync_gitignore(
                active_targets=["antigravity", "codex"],
                published_files=fake_files_codex,
                proj_root=temp_dir
            )
            self.assertTrue(res2["updated"])
            content2 = open(gi_file, "r", encoding="utf-8").read()

            # 斷言自訂規則 100% 完好保留
            self.assertIn("*.tmp", content2)
            self.assertIn("node_modules/", content2)
            self.assertIn(".env", content2)

            # 斷言管理區塊精確替換
            self.assertIn("/.agents/workflows/Auto.md", content2)
            self.assertIn("/.codex/workflows/Auto.md", content2)
            self.assertNotIn("/.claude/commands/Auto.md", content2)
            self.mark_passed()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

