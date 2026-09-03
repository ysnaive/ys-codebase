"""
Unit tests for SessionAnalysis Workflow in agents-workflow module.
Covers FT-04, FT-05, FT-06, ET-02.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import unittest
import os
import sys
import json
from pathlib import Path

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


@require(Requirement.WORKFLOW)
class TestSessionAnalysisWorkflow(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.sa_md_path = os.path.join(_pkg_root, "assets", "workflows", "SessionAnalysis.md")
        self.retro_md_path = os.path.join(_pkg_root, "assets", "workflows", "Retro.md")
        self.contrib_aw_path = os.path.join(_pkg_root, "contributes", "agents-workflow.json")

    def test_ft_04_session_analysis_workflow_asset_content(self):
        """FT-04: 驗證 SessionAnalysis.md 存在、舊版 Retro.md 已刪除、核心章節齊全且包含四大維度與尾部 Token。"""
        self.assertTrue(os.path.exists(self.sa_md_path), "SessionAnalysis.md 檔案必須存在")
        self.assertFalse(os.path.exists(self.retro_md_path), "舊版 Retro.md 檔案必須已刪除")

        with open(self.sa_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("# 對話階段歷程分析工作流 (SessionAnalysis)", content)
        self.assertIn("異常過濾呈遞", content)
        self.assertIn("文檔根因溯源", content)
        self.assertIn("步驟 1：掃描對話歷史與工具調用軌跡", content)
        self.assertIn("步驟 2：雙核心分析與自檢", content)
        self.assertIn("2.1 流程與紀律自檢", content)
        self.assertIn("2.2 四大維度觸發與 Token 消耗分析", content)
        self.assertIn("Skills（技能手冊）", content)
        self.assertIn("Workflows（工作流程）", content)
        self.assertIn("CLI（外部命令與工具）", content)
        self.assertIn("Other（推理、對話與一般操作）", content)
        self.assertIn("Read (檔案檢視)", content)
        self.assertIn("Write (代碼寫入)", content)
        self.assertIn("Thinking (思考推理)", content)
        self.assertIn("Dialogue (對話互動)", content)
        self.assertIn("__@{SESSION_ANALYSIS_CHECK_ITEMS}__", content)
        self.assertIn("步驟 3：工作流優化建議", content)
        self.assertIn("步驟 4：呈遞分析成果摘要卡", content)
        self.assertIn("__@{WORKFLOW_SESSIONANALYSIS}__", content)
        self.assertNotIn("__@{WORKFLOW_RETRO}__", content)
        self.assertNotIn("__@{RETRO_CHECK_ITEMS}__", content)
        self.assertNotIn("__@{DYNAMIC_CONTEXT_MAP}__", content)
        self.mark_passed()

    def test_ft_05_manifest_export_and_token(self):
        """FT-05: 驗證 contributes/agents-workflow.json 正確導出 SessionAnalysis.md 與註冊新 Token 錨點。"""
        self.assertTrue(os.path.exists(self.contrib_aw_path))
        with open(self.contrib_aw_path, "r", encoding="utf-8") as f:
            contrib_data = json.load(f)

        exports = contrib_data.get("export", [])
        tokens = contrib_data.get("token", [])

        sa_export = next(
            (e for e in exports if e.get("source") == "module://agents-workflow/assets/workflows/SessionAnalysis.md"),
            None
        )
        self.assertIsNotNone(sa_export, "contributes 必須宣告導出 SessionAnalysis.md")
        self.assertEqual(sa_export.get("type"), "workflow")

        retro_export = next(
            (e for e in exports if "Retro.md" in e.get("source", "")),
            None
        )
        self.assertIsNone(retro_export, "contributes 不得再導出 Retro.md")

        token_values = [t.get("value") for t in tokens]
        self.assertIn("WORKFLOW_SESSIONANALYSIS", token_values)
        self.assertIn("SESSION_ANALYSIS_CHECK_ITEMS", token_values)
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

    def test_et_02_compilation_and_placeholder_resolution(self):
        """ET-02: 驗證 compiler.py 能順利編譯 SessionAnalysis.md 且 Stage 1 快取包含該項目。"""
        res = self.compiler.compile_stage1()
        self.assertTrue(res["success"], "Stage 1 編譯必須成功")

        resolved_items = res.get("resolved_items", [])
        sa_item = next(
            (item for item in resolved_items if item.get("base_name") == "SessionAnalysis.md"),
            None
        )
        self.assertIsNotNone(sa_item, "Stage 1 解析產物中必須包含 SessionAnalysis.md")
        sa_content = sa_item.get("content", "")
        self.assertIn("對話階段歷程分析工作流 (SessionAnalysis)", sa_content)
        self.mark_passed()
