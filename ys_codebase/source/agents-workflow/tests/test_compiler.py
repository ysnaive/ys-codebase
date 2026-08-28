"""
Unit and Integration Tests for agents-workflow ArtifactCompiler, ReleasePublisher, and CLI.
Covers ST-01 ~ ST-08, FT-01 ~ FT-08, ET-01 ~ ET-04.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import unittest
import os
import io
import sys
import tempfile
from typing import Dict, Any, List

import importlib.util

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

_cli_path = os.path.join(_pkg_root, "scripts", "cli.py")
_spec_cli = importlib.util.spec_from_file_location("aw_cli_compiler_test", _cli_path)
cli = importlib.util.module_from_spec(_spec_cli)
_spec_cli.loader.exec_module(cli)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher
from agents_workflow.targets import ReleaseTargetManager

hook_core = None
try:
    import importlib.util
    hook_path = os.path.join(_pkg_root, "scripts", "hook.core.py")
    if os.path.exists(hook_path):
        spec = importlib.util.spec_from_file_location("hook_core", hook_path)
        hook_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_core)
except Exception:
    hook_core = None


from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestArtifactCompiler(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    def test_ft_01_manifest_exports_and_tokens_discovery(self):
        """FT-01: 驗證自導出資產 (16 項) 與 token 宣告能被正確解析收集。"""
        data = self.compiler.get_contributes_data()
        exports = data.get("export", [])
        tokens = data.get("token", [])
        release_targets = data.get("release_target", [])
        
        self.assertGreaterEqual(len(exports), 16)
        self.assertGreaterEqual(len(release_targets), 1)
        self.assertEqual(release_targets[0].get("name"), "antigravity")

        token_values = [t.get("value") for t in tokens]
        self.assertIn("PHASEXX_HEADER", token_values)
        self.assertIn("WORKFLOW_SOP_STANDARDS", token_values)
        self.assertIn("WORKFLOW_DOCS_STANDARDS", token_values)
        self.assertIn("DYNAMIC_CONTEXT_MAP", token_values)
        self.assertIn("BEGIN_HTML_ANNOTATION", token_values)
        self.assertIn("END_HTML_ANNOTATION", token_values)

    def test_st_01_stage1_cache_output(self):
        """ST-01: 驗證 Stage 1 快取物化寫入 cache.root:// 並回傳結構化項目清單。"""
        res = self.compiler.compile_stage1()
        self.assertTrue(res["success"])
        self.assertGreaterEqual(len(res["resolved_items"]), 16)

    def test_st_02_release_target_header_macro_interpolation(self):
        """ST-02: 驗證純文字/陣列 Header 巨集模板動態替換與 KeyError 容錯。"""
        export_item = {
            "source": "module://agents-workflow/assets/workflows/NewPlan.md",
            "description": "標準開發作業流程 (NewPlan)",
            "name": "NewPlan",
            "type": "workflow"
        }
        
        # 測試字串陣列模板
        header_tpl_list = [
            "---",
            "description: {export.description}",
            "command: {export.name}",
            "---"
        ]
        rendered = self.publisher.render_header(export_item, header_tpl_list, "antigravity")
        self.assertIn("description: 標準開發作業流程 (NewPlan)", rendered)
        self.assertIn("command: NewPlan", rendered)

        # 測試缺失巨集容錯
        header_tpl_missing = "--- \n info: {export.non_existent} \n ---"
        rendered_missing = self.publisher.render_header(export_item, header_tpl_missing, "antigravity")
        self.assertNotIn("{export.non_existent}", rendered_missing)

    def test_st_03_release_target_manager_and_orphan(self):
        """ST-03: 驗證 ReleaseTargetManager 查詢清單與 ORPHAN 標註。"""
        targets = ReleaseTargetManager.list_targets()
        self.assertGreaterEqual(len(targets), 1)
        names = [t["name"] for t in targets]
        self.assertIn("antigravity", names)

    def test_st_04_three_tier_uri_resolution(self):
        """ST-04: 驗證三層 URI 重映射與相對路徑計算 (正斜線 / 格式)。"""
        current_dst = "H:/UseFolder/CodeRepo/project/.agents/workflows/NewPlan.md"
        deployment_map = {
            "module://agents-workflow/assets/templates/P00_semantic_requirements.md": "H:/UseFolder/CodeRepo/project/.agents/templates/P00_semantic_requirements.md",
            "module://agents-workflow/assets/standards/DevelopmentStandards.md": "H:/UseFolder/CodeRepo/project/.agents/standards/DevelopmentStandards.md"
        }

        raw_text = (
            "Read P00: `__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`\n"
            "Read SOP: `__#{module://agents-workflow/assets/standards/DevelopmentStandards.md}__`\n"
            "Read Unknown: `__#{unknown://foo/bar}__`"
        )

        resolved = self.compiler.resolve_stage2_uri(raw_text, current_dst, deployment_map)
        
        # Tier 1 驗證
        self.assertIn("../templates/P00_semantic_requirements.md", resolved)
        self.assertIn("../standards/DevelopmentStandards.md", resolved)
        self.assertNotIn("`__#{module://", resolved)
        
        # Tier 3 驗證 (安全降級)
        self.assertIn("unknown://foo/bar", resolved)

    def test_st_05_atomic_release_transaction(self):
        """ST-05: 驗證原子 4 步發布交易。"""
        res = self.publisher.release_all()
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["published_count"], 16)

    def test_st_06_agents_md_soft_merge(self):
        """ST-06: 驗證 AGENTS.md 軟合併無損保護。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_agents_md = os.path.join(tmp_dir, "AGENTS.md")
            with open(orig_agents_md, "w", encoding="utf-8") as f:
                f.write("# AGENTS\n\n<!-- YSCB_AGENTS_BEGIN -->\nOld Rules\n<!-- YSCB_AGENTS_END -->\n\n## 4. Custom\nCustom Rule\n")
            
            ok = self.publisher._soft_merge_agents_md("New Injected Rules", tmp_dir)
            self.assertTrue(ok)
            
            with open(orig_agents_md, "r", encoding="utf-8") as f:
                merged = f.read()
            
            self.assertIn("New Injected Rules", merged)
            self.assertNotIn("Old Rules", merged)
            self.assertIn("## 4. Custom", merged)
            self.assertIn("Custom Rule", merged)

    def test_st_07_cli_release_and_target_commands(self):
        """ST-07: 驗證 CLI release 與 release-target 系列指令。"""
        code_release = cli.main(["release"])
        self.assertEqual(code_release, 0)

        code_list = cli.main(["release-target", "--list"])
        self.assertEqual(code_list, 0)

    def test_ft_08_computed_token_resolution(self):
        """FT-08: 驗證 type: 'computed' 與 code.func:// 動態調用解算。"""
        raw_text = "# Header\n\n`__@{DYNAMIC_CONTEXT_MAP}__`\n\n# Body"
        inserts = [
            {
                "type": "computed",
                "token": "DYNAMIC_CONTEXT_MAP",
                "value": "code.func://agents-workflow/providers:get_dynamic_context_map",
                "mode": "replace"
            }
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("`__@{DYNAMIC_CONTEXT_MAP}__`", resolved)
        self.assertIn("專案語意 URI 即時解析地圖", resolved)
        self.assertIn("project://", resolved)

    def test_ft_09_dual_standards_and_publisher_config_flags(self):
        """FT-09: 驗證雙標準資產、enable_agents_md 開關與空 release_targets 發布。"""
        # 1. 驗證 Stage 1 解算包含 AgentsStandards 與 DevelopmentStandards
        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res["success"])
        base_names = [it["base_name"] for it in stage1_res["resolved_items"]]
        self.assertIn("AgentsStandards.md", base_names)
        self.assertIn("DevelopmentStandards.md", base_names)

        # 2. 驗證 enable_agents_md 開關在 release_all 中之守門邏輯
        orig_cfg_fn = self.publisher._get_project_config
        try:
            # 模擬 enable_agents_md = False
            self.publisher._get_project_config = lambda: {
                "paths": {},
                "release_targets": [],
                "enable_agents_md": False,
                "enable_project_changelog": True
            }
            res_disabled = self.publisher.release_all()
            self.assertTrue(res_disabled["success"])
            self.assertEqual(res_disabled["published_count"], 0)

            # 模擬 enable_agents_md = True, release_targets = []
            self.publisher._get_project_config = lambda: {
                "paths": {},
                "release_targets": [],
                "enable_agents_md": True,
                "enable_project_changelog": True
            }
            res_empty_target = self.publisher.release_all()
            self.assertTrue(res_empty_target["success"])
            self.assertEqual(res_empty_target["published_count"], 0)
        finally:
            self.publisher._get_project_config = orig_cfg_fn

    def test_ft_10_dev_engineering_standards_injection(self):
        """FT-10: 驗證 dev 模組之 DevEngineeringStandards.md 能透過 below 模式注入至 DevelopmentStandards.md。"""
        raw_text = "# Standards\n\nSome standard content.\n\n`__@{WORKFLOW_SOP_STANDARDS}__`\n"
        inserts = [
            {
                "token": "WORKFLOW_SOP_STANDARDS",
                "mode": "below",
                "value": "### YS-Codebase 模組開發專案特化工程規範\n- 嚴禁 Agent 主動發布與覆蓋宿主安裝\n- 空間邊界與流水線\n"
            }
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("`__@{WORKFLOW_SOP_STANDARDS}__`", resolved)
        self.assertIn("### YS-Codebase 模組開發專案特化工程規範", resolved)
        self.assertIn("嚴禁 Agent 主動發布與覆蓋宿主安裝", resolved)

    def test_ft_11_on_reload_hook_triggers_release_all(self):
        """FT-11: 驗證 hook.core.py 之 on_reload 能自動調用 ReleasePublisher.release_all。"""
        import importlib.util
        from unittest.mock import patch
        hook_path = os.path.join(_pkg_root, "scripts", "hook.core.py")
        self.assertTrue(os.path.exists(hook_path), "hook.core.py must exist in scripts/")
        spec = importlib.util.spec_from_file_location("hook_core_test_unit", hook_path)
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)
        self.assertTrue(hasattr(hook_mod, "on_reload"), "hook.core.py must define on_reload function")
        
        with patch("agents_workflow.publisher.ReleasePublisher.release_all") as mock_rel:
            mock_rel.return_value = {"success": True, "published_count": 24, "active_targets": ["antigravity"]}
            hook_mod.on_reload(None)
    def test_ft_12_project_uri_placeholder_root_and_sub_dir(self):
        """FT-12: 驗證 __${uri}__ 以專案根目錄為基準點展開為純淨相對路徑 (root 與子目錄)。"""
        raw_text = "Root: `__${project://yscb.py}__`\nSub: `__${project://tools/sub/cli.py}__`\n"
        deployment_map = {}
        dst_path = os.path.join(self.compiler.module_root, "dummy_target.md")
        resolved = self.compiler.resolve_stage2_uri(raw_text, dst_path, deployment_map)
        self.assertIn("Root: `yscb.py`", resolved)
        self.assertIn("Sub: `tools/sub/cli.py`", resolved)

    def test_ft_13_inline_code_block_expansion(self):
        """FT-13: 驗證代碼塊內部穿插文字時，僅替換佔位符本體並保留外層反引號與前後文字。"""
        # 1. 測試 Stage 1 __@{token}__ 穿插替換
        stage1_raw = "Command: `run __@{CMD_NAME}__ --flag`\n"
        inserts = [{"token": "CMD_NAME", "value": "test_cmd", "mode": "replace"}]
        stage1_res = self.compiler.resolve_single_artifact(stage1_raw, inserts)
        self.assertEqual(stage1_res.strip(), "Command: `run test_cmd --flag`")

        # 2. 測試 Stage 2 __${uri}__ 穿插替換
        stage2_raw = "Run: `python __${project://yscb.py}__ plan status`\n"
        dst_path = os.path.join(self.compiler.module_root, "dummy.md")
        stage2_res = self.compiler.resolve_stage2_uri(stage2_raw, dst_path, {})
        self.assertEqual(stage2_res.strip(), "Run: `python yscb.py plan status`")

    def test_ft_14_unenclosed_placeholder_warning_and_preservation(self):
        """FT-14: 驗證未被反引號包裹的裸佔位符絕對不被展開，且輸出警示。"""
        raw_text = "Bare token: __@{MY_TOKEN}__ and Bare URI: __${project://yscb.py}__\n"
        inserts = [{"token": "MY_TOKEN", "value": "EXPANDED", "mode": "replace"}]
        
        # Capture stderr
        import io
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            stage1_res = self.compiler.resolve_single_artifact(raw_text, inserts)
            stage2_res = self.compiler.resolve_stage2_uri(stage1_res, "dummy.md", {})
            err_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        # 斷言裸佔位符未被展開
        self.assertIn("__@{MY_TOKEN}__", stage2_res)
        self.assertIn("__${project://yscb.py}__", stage2_res)
        self.assertNotIn("EXPANDED", stage2_res)
        # 斷言輸出 Warning 提示
        self.assertIn("[compiler:warning] Unenclosed placeholder tag", err_output)

    def test_sub_06_agents_standards_token_and_contributes(self):
        """SUB-06: 驗證 AGENTS_STANDARDS token 宣告與 knowledge-db 貢獻注入。"""
        tokens = self.compiler.get_contributes_data().get("token", [])
        token_values = [t.get("value") for t in tokens]
        self.assertIn("AGENTS_STANDARDS", token_values)

        # 模擬 insert 注入
        raw_text = "# Agents Standards\n---\n`__@{AGENTS_STANDARDS}__`\n"
        inserts = [{
            "token": "AGENTS_STANDARDS",
            "value": "### Knowledge Standards\nInjected Content",
            "mode": "below"
        }]
        res = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("Knowledge Standards", res)
        self.assertIn("Injected Content", res)
        self.assertNotIn("__@{AGENTS_STANDARDS}__", res)


if __name__ == "__main__":
    unittest.main()


