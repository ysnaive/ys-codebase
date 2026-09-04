"""
Unit tests for SessionAnalysis Skill in agents-workflow module.
Covers FT-04, FT-05, FT-06, ET-02.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import unittest
import os
import sys
import json
import subprocess
from pathlib import Path

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


@require(Requirement.WORKFLOW)
class TestSessionAnalysisSkill(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.skill_dir = os.path.join(_pkg_root, "assets", "skills", "session-analysis")
        self.skill_md_path = os.path.join(self.skill_dir, "SKILL.md")
        self.analyzer_py_path = os.path.join(self.skill_dir, "scripts", "analyzer.py")
        self.eval_guide_path = os.path.join(self.skill_dir, "references", "evaluation_guide.md")
        self.sa_md_path = os.path.join(_pkg_root, "assets", "workflows", "SessionAnalysis.md")
        self.retro_md_path = os.path.join(_pkg_root, "assets", "workflows", "Retro.md")
        self.contrib_aw_path = os.path.join(_pkg_root, "contributes", "agents-workflow.json")

    def test_ft_04_session_analysis_skill_asset_content(self):
        """FT-04: 驗證 session-analysis 技能資產齊全、舊版 Workflow 已刪除、核心章節齊全且包含四大坑點與腳本工具。"""
        self.assertTrue(os.path.exists(self.skill_md_path), "SKILL.md 必須存在")
        self.assertTrue(os.path.exists(self.analyzer_py_path), "analyzer.py 腳本必須存在")
        self.assertTrue(os.path.exists(self.eval_guide_path), "evaluation_guide.md 參考手冊必須存在")
        self.assertFalse(os.path.exists(self.sa_md_path), "舊版 SessionAnalysis.md 工作流必須已刪除")
        self.assertFalse(os.path.exists(self.retro_md_path), "舊版 Retro.md 工作流必須已刪除")

        with open(self.skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("name: session-analysis", content)
        self.assertIn("🚨 授權守門技能。完全禁止 Agent 主動觸發！", content)
        self.assertIn("上次分析後 (不包含) ~ 本次分析前 (不包含)", content)
        self.assertIn("步驟 1：強制優先執行分析工具腳本", content)
        self.assertIn("analyzer.py", content)
        self.assertIn("evaluation_guide.md", content)
        self.assertIn("__@{SESSION_ANALYSIS_CHECK_ITEMS}__", content)

        with open(self.eval_guide_path, "r", encoding="utf-8") as f:
            guide_content = f.read()
        self.assertIn("四大核心坑點與防禦公理", guide_content)
        self.assertIn("誤將日誌行數或 Tool Output 視為 Steps 數", guide_content)
        self.assertIn("系統固定上下文盲目乘算", guide_content)
        self.mark_passed()

    def test_ft_05_manifest_export_and_token(self):
        """FT-05: 驗證 contributes/agents-workflow.json 正確導出 session-analysis 技能與註冊新 Token 錨點。"""
        self.assertTrue(os.path.exists(self.contrib_aw_path))
        with open(self.contrib_aw_path, "r", encoding="utf-8") as f:
            contrib_data = json.load(f)

        exports = contrib_data.get("export", [])
        tokens = contrib_data.get("token", [])

        sa_export = next(
            (e for e in exports if e.get("source") == "module://agents-workflow/assets/skills/session-analysis"),
            None
        )
        self.assertIsNotNone(sa_export, "contributes 必須宣告導出 session-analysis skill")
        self.assertEqual(sa_export.get("type"), "skill")

        wf_export = next(
            (e for e in exports if "SessionAnalysis.md" in e.get("source", "") or "Retro.md" in e.get("source", "")),
            None
        )
        self.assertIsNone(wf_export, "contributes 不得再導出 SessionAnalysis.md 或 Retro.md")

        token_values = [t.get("value") for t in tokens]
        self.assertIn("SESSION_ANALYSIS_CHECK_ITEMS", token_values)
        self.assertNotIn("WORKFLOW_SESSIONANALYSIS", token_values)
        self.assertNotIn("WORKFLOW_RETRO", token_values)
        self.assertNotIn("RETRO_CHECK_ITEMS", token_values)
        self.mark_passed()

    def test_ft_06_cross_module_contributes(self):
        """FT-06: 驗證 core 退出注入，且 knowledge-db 正確對齊 SESSION_ANALYSIS_CHECK_ITEMS。"""
        source_root = Path(_pkg_root).parent

        # core
        core_contrib_path = source_root / "core" / "contributes" / "agents-workflow.json"
        if core_contrib_path.exists():
            with open(core_contrib_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            c_tokens = [i.get("token") for i in c_data.get("insert", [])]
            self.assertNotIn("RETRO_CHECK_ITEMS", c_tokens)
            self.assertNotIn("SESSION_ANALYSIS_CHECK_ITEMS", c_tokens)

        # knowledge-db
        kdb_contrib_path = source_root / "knowledge-db" / "contributes" / "agents-workflow.json"
        if kdb_contrib_path.exists():
            with open(kdb_contrib_path, "r", encoding="utf-8") as f:
                k_data = json.load(f)
            k_tokens = [i.get("token") for i in k_data.get("insert", [])]
            self.assertIn("SESSION_ANALYSIS_CHECK_ITEMS", k_tokens)
            self.assertNotIn("RETRO_CHECK_ITEMS", k_tokens)
        self.mark_passed()

    def test_et_02_compilation_and_analyzer_probe(self):
        """ET-02: 驗證 compiler.py 能順利編譯 session-analysis 技能，且 analyzer.py 探針具備健全性與降級錯誤處理。"""
        res = self.compiler.compile_stage1()
        self.assertTrue(res["success"], "Stage 1 編譯必須成功")

        resolved_items = res.get("resolved_items", [])
        sa_item = next(
            (item for item in resolved_items if item.get("skill_name") == "session-analysis" and item.get("base_name") == "SKILL.md"),
            None
        )
        self.assertIsNotNone(sa_item, "Stage 1 解析產物中必須包含 session-analysis/SKILL.md")
        sa_content = sa_item.get("content", "")
        self.assertIn("對話階段歷程分析技能指南 (Session Analysis Skill)", sa_content)

        # 驗證 analyzer.py 降級處理 (模擬不存在的 transcript 路徑)
        cmd = [sys.executable, self.analyzer_py_path, "--path", "/nonexistent/path/transcript.jsonl"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("本工具腳本僅支援 Antigravity 環境", proc.stdout)
        self.assertIn("evaluation_guide.md", proc.stdout)
        self.mark_passed()
