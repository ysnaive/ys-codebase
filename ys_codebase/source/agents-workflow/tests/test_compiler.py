"""
Unit and Integration Tests for agents-workflow ArtifactCompiler, ReleasePublisher, and CLI.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if getattr(sys.modules.get("tests"), "PKG_ROOT", None) != Path(__file__).resolve().parent.parent:
    sys.modules.pop("tests", None)

from tests import PKG_ROOT, ConfigStateSnapshot, load_cli_module

cli = load_cli_module("aw_cli_compiler_test")

import agents_workflow
from agents_workflow.compiler import (
    CODE_SPAN_REGEX,
    FENCED_CODE_BLOCK_REGEX,
    UNENCLOSED_TAG_REGEX,
    ArtifactCompiler,
    _lookup_deployed_abs_path,
    _resolve_project_uri_tag,
    check_unenclosed_tags,
)
from agents_workflow.publisher import ReleasePublisher
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.LOGIC | Requirement.ENV)
class TestArtifactCompiler(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    def tearDown(self):
        self._snapshot.restore()
        super().tearDown()

    def test_public_package_exports(self):
        """驗證 agents_workflow.__all__ 完整匯出 10 個公開符號且皆可存取。"""
        expected_exports = [
            "ArtifactCompiler",
            "ReleasePublisher",
            "ReleaseTargetManager",
            "RoadmapManager",
            "RoadmapItem",
            "TodoManager",
            "TodoItem",
            "FrictionSignal",
            "SessionTraceReport",
            "SessionTraceEngine",
        ]
        self.assertEqual(list(agents_workflow.__all__), expected_exports)
        for sym in expected_exports:
            self.assertTrue(hasattr(agents_workflow, sym), f"Missing exported symbol: {sym}")
            self.assertIsNotNone(getattr(agents_workflow, sym))
        self.mark_passed()

    def test_manifest_exports_and_tokens_discovery(self):
        """驗證自導出資產與 token 宣告能被正確解析收集。"""
        data = self.compiler.get_contributes_data()
        exports = data.get("export", [])
        tokens = data.get("token", [])
        release_targets = data.get("release_target", [])

        self.assertGreaterEqual(len(exports), 16)
        self.assertGreaterEqual(len(release_targets), 8)
        self.assertEqual(release_targets[0].get("name"), "antigravity")

        token_values = [t.get("value") for t in tokens]
        self.assertIn("PHASEXX_HEADER", token_values)
        self.assertIn("WORKFLOW_SOP_STANDARDS", token_values)
        self.assertIn("AGENTS_STANDARDS", token_values)
        self.assertIn("AGENTS_SKILL_ROUTING", token_values)
        self.assertIn("AGENTS_CLI_GUIDE", token_values)
        self.assertNotIn("SESSION_ANALYSIS_CHECK_ITEMS", token_values)
        self.mark_passed()

    def test_stage1_cache_output(self):
        """驗證 Stage 1 快取物化寫入 cache:// 並回傳結構化項目清單。"""
        res = self.compiler.compile_stage1()
        self.assertTrue(res["success"])
        self.assertEqual(res["errors"], [])
        self.assertGreaterEqual(len(res["resolved_items"]), 16)
        self.mark_passed()

    def test_release_target_header_macro_interpolation(self):
        """驗證純文字/陣列 Header 巨集模板動態替換與未知巨集容錯。"""
        export_item = {
            "source": "module://agents-workflow/assets/workflows/NewPlan.md",
            "description": "標準開發作業流程 (NewPlan)",
            "name": "NewPlan",
            "type": "workflow",
        }

        header_tpl_list = [
            "---",
            "description: {export.description}",
            "command: {export.name}",
            "---",
        ]
        rendered = self.publisher.render_header(export_item, header_tpl_list, "antigravity")
        self.assertIn("description: 標準開發作業流程 (NewPlan)", rendered)
        self.assertIn("command: NewPlan", rendered)

        header_tpl_missing = "--- \n info: {export.non_existent} \n ---"
        rendered_missing = self.publisher.render_header(export_item, header_tpl_missing, "antigravity")
        self.assertNotIn("{export.non_existent}", rendered_missing)
        self.assertEqual(self.publisher.render_header(export_item, None, "antigravity"), "")
        self.assertEqual(self.publisher.render_header(export_item, 12345, "antigravity"), "")
        self.mark_passed()

    def test_three_tier_uri_resolution(self):
        """驗證三層 URI 重映射與相對路徑計算 (正斜線 / 格式)。"""
        current_dst = "H:/UseFolder/CodeRepo/project/.agents/workflows/NewPlan.md"
        deployment_map = {
            "module://agents-workflow/assets/templates/P00_semantic_requirements.md": "H:/UseFolder/CodeRepo/project/.agents/templates/P00_semantic_requirements.md",
            "module://agents-workflow/assets/standards/DevelopmentStandards.md": "H:/UseFolder/CodeRepo/project/.agents/standards/DevelopmentStandards.md",
        }

        raw_text = (
            "Read P00: `__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`\n"
            "Read SOP: `__#{module://agents-workflow/assets/standards/DevelopmentStandards.md}__`\n"
            "Read Unknown: `__#{unknown://foo/bar}__`"
        )

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            resolved = self.compiler.resolve_stage2_uri(raw_text, current_dst, deployment_map)

        self.assertIn("../templates/P00_semantic_requirements.md", resolved)
        self.assertIn("../standards/DevelopmentStandards.md", resolved)
        self.assertNotIn("`__#{module://", resolved)
        self.assertIn("unknown://foo/bar", resolved)
        self.assertIn("Unresolved semantic URI tag: 'unknown://foo/bar'", err_buf.getvalue())
        self.mark_passed()

    def test_computed_token_resolution_and_error_fallback(self):
        """驗證 type: 'computed' 與 code.func:// 動態調用解算及異常降級。"""
        raw_text = "# Header\n\n`__@{DYNAMIC_CONTEXT_MAP}__`\n\n# Body"
        with mock.patch("core.symbols.resolve_callable") as mock_resolve:
            mock_resolve.return_value = lambda ctx: "### 專案語意 URI 即時解析地圖\n- project://"
            inserts = [
                {
                    "type": "computed",
                    "token": "DYNAMIC_CONTEXT_MAP",
                    "value": "code.func://mock:get_map",
                    "mode": "replace",
                }
            ]
            resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
            self.assertNotIn("`__@{DYNAMIC_CONTEXT_MAP}__`", resolved)
            self.assertIn("專案語意 URI 即時解析地圖", resolved)
            self.assertIn("project://", resolved)

        err_buf = io.StringIO()
        with mock.patch("core.symbols.resolve_callable", side_effect=RuntimeError("symbol failure")), redirect_stderr(err_buf):
            resolved_err = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("`__@{DYNAMIC_CONTEXT_MAP}__`", resolved_err)
        self.assertIn("[compiler:warning] Failed to resolve computed token 'DYNAMIC_CONTEXT_MAP'", err_buf.getvalue())
        self.mark_passed()

    def test_dual_standards_and_publisher_config_flags(self):
        """驗證雙標準資產解析與隔離沙盒下空 release_targets 發布行為。"""
        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res["success"])
        base_names = [it["base_name"] for it in stage1_res["resolved_items"]]
        self.assertIn("AgentsStandards.md", base_names)
        self.assertTrue(
            any(
                it.get("skill_name") == "development-sop" and it.get("base_name") == "SKILL.md"
                for it in stage1_res["resolved_items"]
            )
        )

        with tempfile.TemporaryDirectory(prefix="test_aw_empty_targets_") as tmp_dir:
            isolated_compiler = ArtifactCompiler(host_dir=tmp_dir)
            isolated_pub = ReleasePublisher(compiler=isolated_compiler, host_dir=tmp_dir)
            with mock.patch.object(
                isolated_pub,
                "_get_project_config",
                return_value={
                    "paths": {},
                    "release_targets": [],
                    "enable_agents_md": False,
                    "enable_project_changelog": True,
                },
            ), mock.patch.object(isolated_pub, "_load_manifest", return_value={}), mock.patch.object(
                isolated_pub, "_save_manifest", return_value=True
            ), mock.patch.object(
                isolated_pub, "sync_gitignore", return_value={"updated": False, "created": False, "patterns": []}
            ), mock.patch(
                "agents_workflow.targets.ReleaseTargetManager.get_classified_targets",
                return_value={"project": [], "local": [], "union": []},
            ):
                res_disabled = isolated_pub.release_all()
                self.assertTrue(res_disabled["success"])
                self.assertEqual(res_disabled["published_count"], 0)
                self.assertEqual(res_disabled["active_targets"], [])
        self.mark_passed()

    def test_dev_engineering_standards_injection(self):
        """驗證 dev 模組之 DevEngineeringStandards.md 能透過 below 模式注入至 DevelopmentStandards.md。"""
        raw_text = "# Standards\n\nSome standard content.\n\n`__@{WORKFLOW_SOP_STANDARDS}__`\n"
        inserts = [
            {
                "token": "WORKFLOW_SOP_STANDARDS",
                "mode": "below",
                "value": "### YS-Codebase 模組開發專案特化工程規範\n- 嚴禁 Agent 主動發布與覆蓋宿主安裝\n- 空間邊界與流水線\n",
            }
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("`__@{WORKFLOW_SOP_STANDARDS}__`", resolved)
        self.assertIn("### YS-Codebase 模組開發專案特化工程規範", resolved)
        self.assertIn("嚴禁 Agent 主動發布與覆蓋宿主安裝", resolved)
        self.mark_passed()

    def test_project_uri_placeholder_root_and_sub_dir(self):
        """驗證 __${uri}__ 以專案根目錄為基準點展開為純淨相對路徑，且無自訂錨點之行內代碼塊保留外層反引號。"""
        raw_text = "Root: `__${project://yscb.py}__`\nSub: `__${project://tools/sub/cli.py}__`\nLink: [CLI](`__${project://tools/sub/cli.py}__`)\n"
        deployment_map = {}
        dst_path = os.path.join(self.compiler.module_root, "dummy_target.md")
        resolved = self.compiler.resolve_stage2_uri(raw_text, dst_path, deployment_map)
        self.assertIn("Root: `yscb.py`", resolved)
        self.assertIn("Sub: `tools/sub/cli.py`", resolved)
        self.assertIn("Link: [CLI](tools/sub/cli.py)", resolved)
        self.mark_passed()

    def test_inline_code_block_expansion(self):
        """驗證代碼塊內部穿插文字時，僅替換佔位符本體並保留外層反引號與前後文字。"""
        stage1_raw = "Command: `run __@{CMD_NAME}__ --flag`\n"
        inserts = [{"token": "CMD_NAME", "value": "test_cmd", "mode": "replace"}]
        stage1_res = self.compiler.resolve_single_artifact(stage1_raw, inserts)
        self.assertEqual(stage1_res.strip(), "Command: `run test_cmd --flag`")

        stage2_raw = "Run: `python __${project://yscb.py}__ plan status`\n"
        dst_path = os.path.join(self.compiler.module_root, "dummy.md")
        stage2_res = self.compiler.resolve_stage2_uri(stage2_raw, dst_path, {})
        self.assertEqual(stage2_res.strip(), "Run: `python yscb.py plan status`")
        self.mark_passed()

    def test_stage2_standalone_and_markdown_links(self):
        """驗證 Stage 2 佔位符二分法解析與 Markdown 超連結完全替代。"""
        deployment_map = {
            "module://agents-workflow/assets/standards/AgentsStandards.md": "/abs/project/.agents/.yscb/standards/AgentsStandards.md",
            "module://agents-workflow/assets/workflows/NewPlan.md": "/abs/project/.agents/workflows/NewPlan.md",
        }
        dst_path = "/abs/project/.agents/workflows/ContextInit.md"

        raw_standalone = "[Standards](`__#{module://agents-workflow/assets/standards/AgentsStandards.md}__`)"
        res_standalone = self.compiler.resolve_stage2_uri(raw_standalone, dst_path, deployment_map)
        self.assertEqual(res_standalone, "[Standards](../.yscb/standards/AgentsStandards.md)")

        raw_proj = "[Root](`__${project://AGENTS.md}__`)"
        res_proj = self.compiler.resolve_stage2_uri(raw_proj, dst_path, {})
        self.assertEqual(res_proj, "[Root](AGENTS.md)")

        raw_spaces = "[NewPlan](`__#{ module://agents-workflow/assets/workflows/NewPlan.md }__`)"
        res_spaces = self.compiler.resolve_stage2_uri(raw_spaces, dst_path, deployment_map)
        self.assertEqual(res_spaces, "[NewPlan](./NewPlan.md)")
        self.mark_passed()

    def test_project_uri_custom_anchor_syntax(self):
        """驗證 __$(起始錨點){uri}__ 語意擴充，支援自訂起始錨點並正確解算相對路徑。"""
        with tempfile.TemporaryDirectory() as tmp_proj:
            host_dir = os.path.normpath(tmp_proj).replace("\\", "/")
            dst_path = f"{host_dir}/.agents/workflows/ContextInit.md"
            deployment_map = {
                "workflow.workflows://Auto.md": f"{host_dir}/.agents/workflows/Auto.md",
                "workflow.workflows://ContextInit.md": dst_path,
                "module.source://core/setup.py": f"{host_dir}/source/core/setup.py",
            }
            os.makedirs(f"{host_dir}/.agents/workflows", exist_ok=True)
            os.makedirs(f"{host_dir}/source/core", exist_ok=True)

            compiler = ArtifactCompiler(host_dir=host_dir)

            raw_default = "Default: `__${workflow.workflows://Auto.md}__`"
            res_default = compiler.resolve_stage2_uri(raw_default, dst_path, deployment_map)
            self.assertIn("Default: `.agents/workflows/Auto.md`", res_default)

            raw_with_dir_anchor = "AnchorDir: `__$(.agents/workflows){workflow.workflows://Auto.md}__`"
            res_dir = compiler.resolve_stage2_uri(raw_with_dir_anchor, dst_path, deployment_map)
            self.assertIn("AnchorDir: Auto.md", res_dir)

            raw_with_file_anchor = "AnchorFile: `__$(module.source://core/setup.py){workflow.workflows://Auto.md}__`"
            res_file = compiler.resolve_stage2_uri(raw_with_file_anchor, dst_path, deployment_map)
            self.assertIn("AnchorFile: ../../.agents/workflows/Auto.md", res_file)

            raw_cross = "Cross: `__$(.agents){module.source://core/setup.py}__`"
            res_cross = compiler.resolve_stage2_uri(raw_cross, dst_path, deployment_map)
            self.assertIn("Cross: ../source/core/setup.py", res_cross)

            raw_empty_anchor = "EmptyAnchor: `__$(){workflow.workflows://Auto.md}__`"
            res_empty = compiler.resolve_stage2_uri(raw_empty_anchor, dst_path, deployment_map)
            self.assertIn("EmptyAnchor: `.agents/workflows/Auto.md`", res_empty)

        self.mark_passed()

    def test_project_uri_custom_anchor_standalone_and_inline(self):
        """驗證 __$(起始錨點){uri}__ 在 Standalone (剝除反引號) 與 Inline (保留反引號) 穿插情境。"""
        with tempfile.TemporaryDirectory() as tmp_proj:
            host_dir = os.path.normpath(tmp_proj).replace("\\", "/")
            dst_path = f"{host_dir}/.agents/workflows/ContextInit.md"
            deployment_map = {
                "workflow.workflows://Auto.md": f"{host_dir}/.agents/workflows/Auto.md",
            }
            os.makedirs(f"{host_dir}/.agents/workflows", exist_ok=True)
            compiler = ArtifactCompiler(host_dir=host_dir)

            raw_standalone = "[Auto Link](`__$(.agents/workflows){workflow.workflows://Auto.md}__`)"
            res_standalone = compiler.resolve_stage2_uri(raw_standalone, dst_path, deployment_map)
            self.assertEqual(res_standalone, "[Auto Link](Auto.md)")

            raw_spaces = "[Auto Link](`__$(  .agents/workflows  ){  workflow.workflows://Auto.md  }__`)"
            res_spaces = compiler.resolve_stage2_uri(raw_spaces, dst_path, deployment_map)
            self.assertEqual(res_spaces, "[Auto Link](Auto.md)")

            raw_inline = "Command: `run __$(.agents/workflows){workflow.workflows://Auto.md}__ --now`"
            res_inline = compiler.resolve_stage2_uri(raw_inline, dst_path, deployment_map)
            self.assertEqual(res_inline, "Command: `run Auto.md --now`")

            raw_fenced = "```bash\ncat __$(.agents/workflows){workflow.workflows://Auto.md}__\n```"
            res_fenced = compiler.resolve_stage2_uri(raw_fenced, dst_path, deployment_map)
            self.assertIn("cat Auto.md", res_fenced)
            self.assertTrue(res_fenced.startswith("```bash\n") and res_fenced.endswith("\n```"))

        self.mark_passed()

    def test_unenclosed_tags_warning_with_anchor_syntax(self):
        """驗證 check_unenclosed_tags 能精確攔截裸露未包裹之 __$(anchor){uri}__ 標籤。"""
        captured = io.StringIO()
        with redirect_stderr(captured):
            check_unenclosed_tags("Here is an unenclosed tag: __$(docs){project://README.md}__", doc_name="test.md")
        output = captured.getvalue()
        self.assertIn("[compiler:warning]", output)
        self.assertIn("__$(docs){project://README.md}__", output)
        self.mark_passed()

    def test_unenclosed_placeholder_warning_and_preservation(self):
        """驗證未被反引號包裹的裸佔位符絕對不被展開，且輸出警示。"""
        raw_text = "Bare token: __@{MY_TOKEN}__ and Bare URI: __${project://yscb.py}__\n"
        inserts = [{"token": "MY_TOKEN", "value": "EXPANDED", "mode": "replace"}]

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            stage1_res = self.compiler.resolve_single_artifact(raw_text, inserts)
            stage2_res = self.compiler.resolve_stage2_uri(stage1_res, "dummy.md", {})
        err_output = err_buf.getvalue()

        self.assertIn("__@{MY_TOKEN}__", stage2_res)
        self.assertIn("__${project://yscb.py}__", stage2_res)
        self.assertNotIn("EXPANDED", stage2_res)
        self.assertIn("[compiler:warning] Unenclosed placeholder tag", err_output)
        self.mark_passed()

    def test_agents_standards_token_and_contributes(self):
        """驗證 AGENTS_STANDARDS token 宣告與貢獻注入。"""
        tokens = self.compiler.get_contributes_data().get("token", [])
        token_values = [t.get("value") for t in tokens]
        self.assertIn("AGENTS_STANDARDS", token_values)

        raw_text = "# Agents Standards\n---\n`__@{AGENTS_STANDARDS}__`\n"
        inserts = [
            {
                "token": "AGENTS_STANDARDS",
                "value": "### Knowledge Standards\nInjected Content",
                "mode": "below",
            }
        ]
        res = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("Knowledge Standards", res)
        self.assertIn("Injected Content", res)
        self.assertNotIn("__@{AGENTS_STANDARDS}__", res)
        self.mark_passed()

    def test_multi_donor_insert_aggregation(self):
        """驗證同一個 Token 錨點支援多模組同時注入 (above, replace, below 拓撲聚合)。"""
        raw_text = "# Standards\n\n`__@{MULTI_TEST_TOKEN}__`\n\n# End"
        inserts = [
            {"token": "MULTI_TEST_TOKEN", "value": "### Above Block 1", "mode": "above"},
            {"token": "MULTI_TEST_TOKEN", "value": "### Replace Block 1", "mode": "replace"},
            {"token": "MULTI_TEST_TOKEN", "value": "### Below Block 1", "mode": "below"},
            {"token": "MULTI_TEST_TOKEN", "value": "### Below Block 2", "mode": "below"},
        ]
        res = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("`__@{MULTI_TEST_TOKEN}__`", res)
        self.assertIn("### Above Block 1", res)
        self.assertIn("### Replace Block 1", res)
        self.assertIn("### Below Block 1", res)
        self.assertIn("### Below Block 2", res)

        idx_above = res.index("### Above Block 1")
        idx_replace = res.index("### Replace Block 1")
        idx_below1 = res.index("### Below Block 1")
        idx_below2 = res.index("### Below Block 2")
        self.assertTrue(idx_above < idx_replace < idx_below1 < idx_below2)
        self.mark_passed()

    def test_skill_directory_scan_and_token_expansion(self):
        """驗證目錄級 Skill 掃描、保持子目錄結構與 Token 展開。"""
        with tempfile.TemporaryDirectory(prefix="test_aw_skill_") as tmp_dir:
            skill_root = os.path.join(tmp_dir, "test-skill")
            os.makedirs(os.path.join(skill_root, "references"), exist_ok=True)

            with open(os.path.join(skill_root, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("---\nname: test-skill\ndescription: Test Skill\n---\n# Main\n`__@{TEST_TOKEN}__`")
            with open(os.path.join(skill_root, "references", "sub.md"), "w", encoding="utf-8") as f:
                f.write("# Sub Reference\n`__@{TEST_TOKEN}__`")

            scanned = self.compiler._scan_directory_files(skill_root)
            rel_paths = [s[0] for s in scanned]
            self.assertEqual(rel_paths, ["SKILL.md", "references/sub.md"])

            mock_insert = [
                {
                    "token": "TEST_TOKEN",
                    "value": "EXPANDED_TOKEN_BODY",
                    "mode": "replace",
                }
            ]
            for _, _, raw_text in scanned:
                stage1 = self.compiler.resolve_single_artifact(raw_text, mock_insert)
                self.assertNotIn("`__@{TEST_TOKEN}__`", stage1)
                self.assertIn("EXPANDED_TOKEN_BODY", stage1)
        self.mark_passed()

    def test_empty_or_nonexistent_skill_directory_handling(self):
        """驗證 Skill 目錄為空或不存在時安全返回空清單，不拋出未捕獲例外。"""
        empty_res = self.compiler._scan_directory_files("/non/existent/skill/dir")
        self.assertEqual(empty_res, [])

        with tempfile.TemporaryDirectory(prefix="test_aw_empty_skill_") as tmp_dir:
            scanned_empty = self.compiler._scan_directory_files(tmp_dir)
            self.assertEqual(scanned_empty, [])
        self.mark_passed()

    def test_resolve_source_path_cross_module_and_tokens_cli(self):
        """驗證 _resolve_source_path 跨模組 sibling fallback 與 cli.py:tokens() 相容 name/value 欄位。"""
        with tempfile.TemporaryDirectory(prefix="test_aw_sibling_") as tmp_parent:
            aw_dir = os.path.join(tmp_parent, "agents-workflow")
            other_dir = os.path.join(tmp_parent, "other-mod")
            os.makedirs(os.path.join(aw_dir, "assets"), exist_ok=True)
            os.makedirs(os.path.join(other_dir, "assets"), exist_ok=True)

            aw_file = os.path.join(aw_dir, "assets", "guide.md")
            other_file = os.path.join(other_dir, "assets", "guide.md")
            with open(aw_file, "w", encoding="utf-8") as f:
                f.write("AW_CONTENT")
            with open(other_file, "w", encoding="utf-8") as f:
                f.write("OTHER_MOD_CONTENT")

            old_root = self.compiler.module_root
            try:
                self.compiler.module_root = aw_dir
                resolved = self.compiler._resolve_source_path("module://other-mod/assets/guide.md")
                self.assertEqual(os.path.abspath(resolved), os.path.abspath(other_file))
                self.assertEqual(self.compiler._read_file_content("module://other-mod/assets/guide.md"), "OTHER_MOD_CONTENT")
            finally:
                self.compiler.module_root = old_root

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.tokens([])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for line in out.splitlines():
            if "知識庫已註冊空間清單動態注入錨點" in line:
                self.assertIn("KNOWLEDGE_DB_SPACE", line)
        self.mark_passed()

    def test_uri_insert_cache_and_multi_pass_table_aggregation(self):
        """驗證 type: 'uri' 快取複用（含字面量保護不污染）、多輪遞迴展開與表格列單換行聚合。"""
        with tempfile.TemporaryDirectory(prefix="test_aw_uri_cache_") as tmp_dir:
            snippet_path = os.path.join(tmp_dir, "snippet.md")
            with open(snippet_path, "w", encoding="utf-8") as f:
                f.write(
                    "Outer Header\n"
                    "<!-- yscb:literal:begin -->\n"
                    "Literal Tag: `__@{UNTOUCHED}__`\n"
                    "<!-- yscb:literal:end -->\n"
                    "`__@{INNER_TABLE}__`\n"
                )

            inserts = [
                {"type": "uri", "token": "OUTER_URI", "value": snippet_path, "mode": "replace"},
                {"type": "const", "token": "INNER_TABLE", "value": "| Col A | Col B |", "mode": "above"},
                {"type": "const", "token": "INNER_TABLE", "value": "| :--- | :--- |", "mode": "replace"},
                {"type": "const", "token": "INNER_TABLE", "value": "| Val 1 | Val 2 |", "mode": "below"},
            ]
            shared_cache = {}
            with mock.patch.object(self.compiler, "_read_file_content", wraps=self.compiler._read_file_content) as spy_read:
                doc1 = self.compiler.resolve_single_artifact(
                    "# Doc 1\n`__@{OUTER_URI}__`\n", inserts, _insert_cache=shared_cache
                )
                doc2 = self.compiler.resolve_single_artifact(
                    "# Doc 2\n`__@{OUTER_URI}__`\n", inserts, _insert_cache=shared_cache
                )
                self.assertEqual(spy_read.call_count, 1)

            for doc in (doc1, doc2):
                self.assertNotIn("\x00YSCB_LITERAL_BLOCK_", doc)
                self.assertIn("Literal Tag: `__@{UNTOUCHED}__`", doc)
                self.assertIn("| Col A | Col B |\n| :--- | :--- |\n| Val 1 | Val 2 |", doc)
                self.assertNotIn("| Col A | Col B |\n\n| :--- | :--- |", doc)
        self.mark_passed()

    def test_project_uri_tag_fallback_and_suffix_boundary(self):
        """驗證 _resolve_project_uri_tag 異常退避與 _lookup_deployed_abs_path 後綴邊界防禦。"""
        proj_root = "/workspace/demo_proj"
        with mock.patch("agents_workflow.compiler.uri") as mock_uri:
            mock_uri.resolve.side_effect = RuntimeError("uri offline")
            docs_rel = _resolve_project_uri_tag("workflow.docs://guide/intro.md", None, proj_root, {}, "test.md")
            plans_rel = _resolve_project_uri_tag("workflow.plans://2026_11_01_demo/", None, proj_root, {}, "test.md")
            arch_rel = _resolve_project_uri_tag("workflow.archived://2026/11/demo", None, proj_root, {}, "test.md")
            self.assertEqual(docs_rel, "docs/guide/intro.md")
            self.assertEqual(plans_rel, "plans/2026_11_01_demo/")
            self.assertEqual(arch_rel, "plans/archived/2026/11/demo")

            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                unk_rel = _resolve_project_uri_tag("custom.unknown://path/a.md", None, proj_root, {}, "test.md")
            self.assertEqual(unk_rel, "custom.unknown://path/a.md")
            self.assertIn("[compiler:warning] Failed to resolve project URI", err_buf.getvalue())

        dep_map = {
            "module://agents-workflow/assets/templates/fast_track_plan.md": "/abs/templates/fast_track_plan.md",
            "templates/fast_track_plan.md": "/abs/templates/fast_track_plan.md",
            "fast_track_plan.md": "/abs/templates/fast_track_plan.md",
        }
        self.assertEqual(
            _lookup_deployed_abs_path("fast_track_plan.md", dep_map),
            "/abs/templates/fast_track_plan.md",
        )
        self.assertEqual(
            _lookup_deployed_abs_path("templates/fast_track_plan.md", dep_map),
            "/abs/templates/fast_track_plan.md",
        )
        self.assertIsNone(_lookup_deployed_abs_path("project://AGENTS.md", dep_map))
        self.assertIsNone(_lookup_deployed_abs_path("", dep_map))
        self.mark_passed()

    def test_compile_stage1_error_reporting_and_cli_commands(self):
        """驗證 compile_stage1 缺失來源/空目錄錯誤回報，以及 cli.compile / cli.list / cli.tokens 分支。"""
        with tempfile.TemporaryDirectory(prefix="test_aw_stage1_err_") as tmp_dir:
            empty_skill_dir = os.path.join(tmp_dir, "empty_skill")
            os.makedirs(empty_skill_dir, exist_ok=True)

            with mock.patch.object(
                self.compiler,
                "get_contributes_data",
                return_value={
                    "export": [
                        {"type": "template", "source": os.path.join(tmp_dir, "non_existent.md")},
                        {"type": "skill", "name": "empty-skill", "source": empty_skill_dir},
                    ],
                    "insert": [],
                    "token": [],
                    "release_target": [],
                },
            ):
                res_err = self.compiler.compile_stage1()
                self.assertFalse(res_err["success"])
                self.assertEqual(len(res_err["errors"]), 2)
                self.assertTrue(any("Cannot read export source" in e for e in res_err["errors"]))
                self.assertTrue(any("Skill directory is empty" in e for e in res_err["errors"]))

        out_ok = io.StringIO()
        with redirect_stdout(out_ok):
            self.assertEqual(cli.compile([]), 0)
        self.assertIn("Stage 1 compilation completed successfully", out_ok.getvalue())

        out_fail = io.StringIO()
        with mock.patch.object(
            ArtifactCompiler,
            "compile_stage1",
            return_value={"success": False, "errors": ["mock compile error"]},
        ), redirect_stdout(out_fail):
            self.assertEqual(cli.compile([]), 1)
        self.assertIn("mock compile error", out_fail.getvalue())

        out_list = io.StringIO()
        with redirect_stdout(out_list):
            self.assertEqual(cli.list([]), 0)
        self.assertIn("Exported Artifacts Catalog", out_list.getvalue())

        out_list_empty = io.StringIO()
        with mock.patch.object(ArtifactCompiler, "get_exported_artifacts", return_value=[]), redirect_stdout(out_list_empty):
            self.assertEqual(cli.list([]), 0)
        self.assertIn("No exported artifacts found.", out_list_empty.getvalue())

        out_tok_empty = io.StringIO()
        with mock.patch.object(ArtifactCompiler, "get_registered_tokens", return_value=[]), redirect_stdout(out_tok_empty):
            self.assertEqual(cli.tokens([]), 0)
        self.assertIn("No registered tokens found.", out_tok_empty.getvalue())
        self.mark_passed()


@require(Requirement.ENV)
class TestWorkflowAssetsCompliance(YSCBTestCase):
    """驗證內建 Skills、Templates 與 Tokens 資產規範合規性。"""

    def test_assets_follow_model_record_rule(self):
        """驗證規範與模板資產採用模型紀錄規則，且不再含首行／尾行錨點規則。"""
        assets = PKG_ROOT / "assets"
        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("模型紀錄 (Model Record)", standards)
        self.assertIn("Unknown", standards)
        self.assertIn("嚴禁**從既有計畫檔", standards)
        self.assertNotIn("{model}", standards, "首行／尾行 `> {model}` 規則必須已移除")
        self.assertNotIn("Model Identity Anchor", standards)

        placeholder = "[平台宣告之模型名稱；無法確認填 Unknown]"
        header = (assets / "templates" / "header.md").read_text(encoding="utf-8")
        self.assertIn(placeholder, header)
        changelog_tpl = (assets / "templates" / "changelog.md").read_text(encoding="utf-8")
        self.assertIn("| 日期時間 | 類型 | 模型 | 摘要 |", changelog_tpl)
        self.assertNotIn("(狀態：`Discussing`)", changelog_tpl)
        self.mark_passed()

    def test_context_init_and_cli_guide_alignment(self):
        """驗證 context-init 移除首行模型錨點並對齊權限標籤，yscb-cli-guide 含三級權限定義。"""
        assets = PKG_ROOT / "assets"
        ctx_init = (assets / "skills" / "context-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("首行強制輸出當前模型識別錨點", ctx_init)
        self.assertIn("Unknown", ctx_init)
        self.assertIn("[SAFE] 自主安全", ctx_init)

        cli_guide = (assets / "skills" / "yscb-cli-guide" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[SAFE] 自主安全", cli_guide)
        self.assertIn("[CONDITIONAL] 階段條件", cli_guide)
        self.assertIn("[GATED] 授權守門", cli_guide)
        self.mark_passed()

    def test_handoff_and_umbrella_lifecycle(self):
        """驗證 continue/pause handoff 銷毀與子計畫路徑、Umbrella 主從連動與跨軌道清理。"""
        assets = PKG_ROOT / "assets"
        cont = (assets / "skills" / "continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Consume & Delete", cont)
        self.assertIn("強制立即刪除該已消費之 `handoff.md`", cont)

        pause = (assets / "skills" / "pause" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("sub_{編號}_{名稱}/handoff.md", pause)

        sop_ref = assets / "skills" / "development-sop" / "references"
        self.assertFalse((sop_ref / "plan_modes.md").exists(), "單體 plan_modes.md 應已拆分為按需單點載入之獨立模式手冊")
        ft_ref = (sop_ref / "fast_track_plan.md").read_text(encoding="utf-8")
        rev_ref = (sop_ref / "revision_plan.md").read_text(encoding="utf-8")
        umb_ref = (sop_ref / "umbrella_plan.md").read_text(encoding="utf-8")
        self.assertIn("強制刪除原 `fast_track_plan.md`", ft_ref)
        self.assertIn("附掛於既有已結案計畫之修訂觸發熔斷", rev_ref)
        self.assertIn("主從計畫狀態連動規則", umb_ref)

        roadmap_tpl = (assets / "templates" / "roadmap.md").read_text(encoding="utf-8")
        self.assertIn("[Backlog | Proposed | Ready | Deferred]", roadmap_tpl)
        self.assertIn("> 目標範疇：", roadmap_tpl)
        self.assertIn("> 前置解鎖條件：", roadmap_tpl)
        self.assertNotIn("全庫歷史物件量化分析", roadmap_tpl)
        self.mark_passed()

    def test_templates_and_verify_ordering(self):
        """驗證模板三層文檔表與無勾選框任務清單，以及結案驗證順序。"""
        assets = PKG_ROOT / "assets"
        p00_tpl = (assets / "templates" / "P00_discuss.md").read_text(encoding="utf-8")
        self.assertIn("架構影響範圍", p00_tpl)
        self.assertNotIn("- [ ]", p00_tpl)

        p04_tpl = (assets / "templates" / "P04_implementation_plan.md").read_text(encoding="utf-8")
        self.assertIn("<Category>/README.md", p04_tpl)
        self.assertIn("<Category>/[topic].md", p04_tpl)
        self.assertIn("<Category>/DESIGN_NOTES.md", p04_tpl)
        self.assertIn("微觀註解", p04_tpl)
        self.assertNotIn("- [ ] **TASK-", p04_tpl)
        self.assertIn("1. **TASK-01**", p04_tpl)

        p07_tpl = (assets / "templates" / "P07_walkthrough.md").read_text(encoding="utf-8")
        self.assertIn("<Category>/README.md", p07_tpl)
        self.assertIn("<Category>/[topic].md", p07_tpl)
        self.assertIn("<Category>/DESIGN_NOTES.md", p07_tpl)

        p07_ref = (
            assets / "skills" / "development-sop" / "references" / "phase_07_walkthrough.md"
        ).read_text(encoding="utf-8")
        self.assertIn("步驟 3：執行計畫合規檢核最終守門", p07_ref)

        discuss = (assets / "skills" / "discuss" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("三大範疇裁定出口", discuss)
        self.assertIn("fast_track_plan.md", discuss)
        self.mark_passed()

    def test_restored_lifecycle_assets(self):
        """驗證核心生命週期工作流、路線圖與階段參考手冊資產規範完整性。"""
        assets = PKG_ROOT / "assets"
        sop_ref = assets / "skills" / "development-sop" / "references"

        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("生命週期工作流", standards)

        new_plan = (assets / "skills" / "new-plan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("phase_00_discuss.md", new_plan)

        research = (assets / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("均須先將 `R{NN}_{topic}.md` 標頭狀態更新為 `Concluded`", research)

        roadmap_skill = (assets / "skills" / "roadmap" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[Backlog | Proposed | Ready | Deferred]", roadmap_skill)
        self.assertIn("Consume-on-Promote", roadmap_skill)
        self.assertIn("roadmap promote", roadmap_skill)

        sop = (assets / "skills" / "development-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`umbrella_overview` + `changelog`", sop)
        self.assertIn("落檔預設標頭狀態", sop)

        self.assertIn("Umbrella 子計畫立項登記", (sop_ref / "phase_00_discuss.md").read_text(encoding="utf-8"))
        self.assertIn("Acceptance Criteria", (sop_ref / "phase_01_requirements.md").read_text(encoding="utf-8"))
        self.assertIn("錯誤與例外契約", (sop_ref / "phase_03_api_spec.md").read_text(encoding="utf-8"))
        self.assertIn("Umbrella 子計畫結案回寫", (sop_ref / "phase_07_walkthrough.md").read_text(encoding="utf-8"))

        rev_ref = (sop_ref / "revision_plan.md").read_text(encoding="utf-8")
        umb_ref = (sop_ref / "umbrella_plan.md").read_text(encoding="utf-8")
        self.assertIn("熔斷後舊產物雙軌處置", rev_ref)
        self.assertIn("首個 `sub_XX` 啟動時", umb_ref)

        cont = (assets / "skills" / "continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考", cont)

        auto = (assets / "skills" / "auto" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("(Draft)", auto)
        self.assertIn("一次建立並定稿", auto)

        discuss = (assets / "skills" / "discuss" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("P06_test_plan.md", discuss)

        tpl = assets / "templates"
        self.assertIn("詳細規格與驗收條件 (Acceptance Criteria)", (tpl / "P01_requirements_spec.md").read_text(encoding="utf-8"))
        roadmap_tpl = (tpl / "roadmap.md").read_text(encoding="utf-8")
        self.assertIn("## 1. 背景與長期願景 (Background & Vision)", roadmap_tpl)
        self.assertIn("## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)", roadmap_tpl)
        self.assertIn("## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)", roadmap_tpl)
        self.assertNotIn("候選架構方案對比", roadmap_tpl)
        self.assertNotIn("### 1.2 現況與影響範圍評估", roadmap_tpl)
        for name in ("P07_walkthrough.md", "fast_track_plan.md", "revision_log.md"):
            content = (tpl / name).read_text(encoding="utf-8")
            self.assertLess(
                content.index("`Completed`"),
                content.index("plan verify"),
                f"{name}: 應先更新 Completed 狀態，最後執行 plan verify",
            )
        self.mark_passed()

    def test_skill_optimizer_and_pure_skills_refinement(self):
        """驗證 skill-optimizer 註冊與全部技能雙軌邊界合規。"""
        assets = PKG_ROOT / "assets"
        skills_dir = assets / "skills"
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertNotIn("session-analysis", export_names)
        self.assertNotIn("SESSION_ANALYSIS_CHECK_ITEMS", token_names)
        self.assertIn("skill-optimizer", export_names)
        self.assertIn("SKILL_OPTIMIZER_STANDARDS", token_names)

        expected_skills = {
            "auto", "blind-subagent", "code-optimizer", "context-init", "continue", "development-sop",
            "discuss", "documentation", "how-to-config-yscb", "how-to-yscb", "new-plan",
            "pause", "research", "roadmap", "session-audit", "skill-creator",
            "skill-optimizer", "testing-sop", "todo", "yscb-cli-guide",
        }
        command_driven_skills = {
            "auto", "blind-subagent", "code-optimizer", "pause", "continue", "context-init", "session-audit",
            "skill-creator", "skill-optimizer", "how-to-config-yscb", "how-to-yscb",
        }
        ambient_skills = expected_skills - command_driven_skills
        actual_skills = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        self.assertEqual(actual_skills, expected_skills)

        compiler = ArtifactCompiler()
        skill_exports = [item for item in contrib["export"] if item.get("type") == "skill"]
        for item in skill_exports:
            self.assertNotIn("description", item, f"{item['name']} 在 agents-workflow.json 不應重複定義 description")
        export_desc_map = {item["name"]: compiler.resolve_export_description(item) for item in skill_exports}
        b_strict_skills = {"auto", "code-optimizer", "skill-optimizer", "session-audit"}
        b_assist_skills = {"blind-subagent", "pause", "continue", "context-init", "skill-creator", "how-to-config-yscb", "how-to-yscb"}

        for s_name in ambient_skills:
            skill_md = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            first_lines = "\n".join(skill_md.splitlines()[:4])
            self.assertTrue(export_desc_map[s_name], f"{s_name} 無法自動解析 SKILL.md description")
            self.assertIn(export_desc_map[s_name], first_lines, f"{s_name}/SKILL.md description 解析不一致")
            self.assertIn("觸發情境：", first_lines, f"{s_name}/SKILL.md 缺少 A1『觸發情境：』描述")
            self.assertNotIn("（改用", first_lines, f"{s_name}/SKILL.md description 不得跨技能點名『（改用 ...）』")
            self.assertIn("## 常見踩坑指南 (Gotchas)", skill_md, f"{s_name}/SKILL.md 缺少 Gotchas 章節")

        for s_name in command_driven_skills:
            skill_md = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            first_lines = "\n".join(skill_md.splitlines()[:4])
            self.assertTrue(export_desc_map[s_name], f"{s_name} 無法自動解析 SKILL.md description")
            self.assertIn(export_desc_map[s_name], first_lines, f"{s_name}/SKILL.md description 解析不一致")
            self.assertIn("僅於顯式輸入", first_lines, f"{s_name}/SKILL.md 缺少主動指令型『僅於顯式輸入』契約")
            if s_name in b_strict_skills:
                self.assertIn("時觸發，嚴禁主動觸發。", first_lines, f"{s_name}/SKILL.md 應採 B-Strict 純斜線鎖定契約")
            elif s_name in b_assist_skills:
                self.assertIn("或明確要求", first_lines, f"{s_name}/SKILL.md 應採 B-Assist 明確委託契約")
            self.assertNotIn("(或 /", first_lines, f"{s_name}/SKILL.md description 不應含過度相容大小寫變體")
            self.assertIn("## 常見踩坑指南 (Gotchas)", skill_md, f"{s_name}/SKILL.md 缺少 Gotchas 章節")

        for md_path in (skills_dir / "skill-optimizer").rglob("*.md"):
            text = md_path.read_text(encoding="utf-8")
            self.assertNotIn("不要加反引號", text, f"{md_path.name} 不得含特化錯誤教學")
            self.assertNotIn("compiler.py", text, f"{md_path.name} 不得耦合特定專案內部檔名")

        for md_path in skills_dir.rglob("*.md"):
            text = md_path.read_text(encoding="utf-8")
            clean_text = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", text))
            unenclosed = UNENCLOSED_TAG_REGEX.findall(clean_text)
            self.assertEqual(unenclosed, [], f"{md_path} 存在未以單反引號包覆之語意標籤: {unenclosed}")

        self.mark_passed()

    def test_testing_sop_and_three_pillar_subagent_delegation(self):
        """驗證 testing-sop 雙層結構、連鎖引用與三支柱 Subagent 隔離協定。"""
        assets = PKG_ROOT / "assets"
        skills_dir = assets / "skills"
        sop_ref = skills_dir / "development-sop" / "references"
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("testing-sop", export_names)
        self.assertIn("TESTING_SOP_STANDARDS", token_names)

        testing_sop_md = (skills_dir / "testing-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(testing_sop_md.splitlines()), 120)
        for idx in range(1, 7):
            self.assertIn(f"鐵律 {idx}：", testing_sop_md)
        self.assertIn("`__@{TESTING_SOP_STANDARDS}__`", testing_sop_md)
        self.assertIn("references/test_suite_audit_and_purification.md", testing_sop_md)

        purify_ref = (
            skills_dir / "testing-sop" / "references" / "test_suite_audit_and_purification.md"
        ).read_text(encoding="utf-8")
        for idx in range(1, 7):
            self.assertIn(f"T-0{idx}", purify_ref)
        self.assertIn("Step 1", purify_ref)
        self.assertIn("Step 2", purify_ref)
        self.assertIn("Step 3", purify_ref)

        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("`testing-sop`", standards)
        self.assertIn("testing-sop", (skills_dir / "development-sop" / "SKILL.md").read_text(encoding="utf-8"))
        for ref_name in ("phase_04_plan.md", "phase_05_task.md", "phase_06_test.md", "fast_track_plan.md"):
            ref_text = (sop_ref / ref_name).read_text(encoding="utf-8")
            self.assertIn("testing-sop/SKILL.md", ref_text, f"{ref_name} 缺少 testing-sop 強制連鎖引用")
        p06_ref = (sop_ref / "phase_06_test.md").read_text(encoding="utf-8")
        self.assertIn("守門 ①（子系統回歸全綠）", p06_ref)
        self.assertIn("守門 ②", p06_ref)

        for s_name in ("research", "discuss"):
            s_text = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("支柱一", s_text)
            self.assertIn("150~300 Tokens", s_text)
            self.assertIn("自動降級", s_text)

        for doc_text in (
            (skills_dir / "auto" / "SKILL.md").read_text(encoding="utf-8"),
            (sop_ref / "phase_05_task.md").read_text(encoding="utf-8"),
        ):
            self.assertNotIn("支柱二", doc_text)
            self.assertNotIn("2-Strike Limit", doc_text)
            self.assertNotIn("STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)", doc_text)
            self.assertNotIn("DEVIATION_OR_BLOCKER_NOTE", doc_text)

        p06_ref = (sop_ref / "phase_06_test.md").read_text(encoding="utf-8")
        self.assertNotIn("支柱二", p06_ref)
        self.assertIn("支柱三", p06_ref)
        self.assertIn("不應告知子代理本次計畫實作內容，僅可提供計畫路徑由子代理進行探索", p06_ref)
        self.assertIn("明確告知子代理嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查", p06_ref)
        self.assertIn("BlindSubagentStandards.md", p06_ref)
        self.assertIn("Untracked (??)", p06_ref)
        self.assertIn("git status --short", p06_ref)
        self.assertIn("REVIEW_STATUS: PASSED", p06_ref)
        self.assertIn("自動降級", p06_ref)

        p07_ref = (sop_ref / "phase_07_walkthrough.md").read_text(encoding="utf-8")
        self.assertIn("支柱三", p07_ref)
        self.assertIn("條件式", p07_ref)
        self.assertIn("嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查", p07_ref)

        self.mark_passed()

    def test_onboarding_and_config_coaching_skills(self):
        """驗證 PROJECT_ROLE_AND_BOUNDARIES、/how-to-config-yscb、/how-to-yscb 與模組指南。"""
        assets = PKG_ROOT / "assets"
        skills_dir = assets / "skills"
        source_root = PKG_ROOT.parent
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("how-to-config-yscb", export_names)
        self.assertIn("how-to-yscb", export_names)
        self.assertIn("PROJECT_ROLE_AND_BOUNDARIES", token_names)
        self.assertIn("HOW_TO_CONFIG_MODULES", token_names)
        self.assertIn("HOW_TO_YSCB_MODULES", token_names)

        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("`__@{PROJECT_ROLE_AND_BOUNDARIES}__`", standards)
        self.assertLess(
            standards.index("`__@{PROJECT_ROLE_AND_BOUNDARIES}__`"),
            standards.index("## 1. 核心原則"),
        )

        ctx_init = (skills_dir / "context-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("專案角色與主客體空間邊界", ctx_init)
        self.assertIn("/how-to-yscb", ctx_init)
        self.assertIn("/how-to-config-yscb", ctx_init)

        config_skill = (skills_dir / "how-to-config-yscb" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`__@{HOW_TO_CONFIG_MODULES}__`", config_skill)
        self.assertIn("All-Green Short-Circuit", config_skill)
        self.assertIn("First-Party Trinity Alignment", config_skill)
        self.assertIn("paths.plans", config_skill)
        self.assertIn("release_targets", config_skill)
        self.assertIn("projections", config_skill)
        self.assertIn("嚴禁硬編碼 `.agents/` 或 `.claude/`", config_skill)
        self.assertIn("① 開發者角色與專案使命", config_skill)
        self.assertIn("② 本體業務空間", config_skill)
        self.assertIn("③ 外部工具包與黑盒依賴", config_skill)
        self.assertIn("config.project.json", config_skill)
        self.assertIn("config.local.json", config_skill)
        self.assertIn("contributes check", config_skill)
        self.assertIn("agents-workflow compile", config_skill)
        self.assertIn("agents-workflow release", config_skill)

        howto_skill = (skills_dir / "how-to-yscb" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`__@{HOW_TO_YSCB_MODULES}__`", howto_skill)
        self.assertIn("Coach / Mentor Persona", howto_skill)
        self.assertIn("你想從什麼角度了解這套工具？", howto_skill)
        self.assertIn("角度 A（全景與起手式）", howto_skill)
        self.assertIn("角度 B（以任務找武器）", howto_skill)
        self.assertIn("角度 C（已安裝模組探索）", howto_skill)
        self.assertIn("角度 D（進階技巧與客製化）", howto_skill)
        self.assertIn("/skill-creator", howto_skill)
        self.assertIn("/skill-optimizer", howto_skill)
        self.assertIn("入口 A", howto_skill)
        self.assertIn("入口 B", howto_skill)
        self.assertIn("兩階段漸進式知識調度", howto_skill)
        self.assertIn("/how-to-config-yscb", howto_skill)
        self.assertIn("開啟一個全新的對話視窗", howto_skill)

        for mod_name in ("core", "dev", "server", "ast", "knowledge-db"):
            mod_dir = source_root / mod_name
            if not mod_dir.is_dir():
                continue
            mod_contrib = json.loads((mod_dir / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))
            inserted_tokens = {ins.get("token") for ins in mod_contrib.get("insert", [])}
            self.assertIn("HOW_TO_CONFIG_MODULES", inserted_tokens, f"{mod_name} 未註冊 HOW_TO_CONFIG_MODULES")
            self.assertIn("HOW_TO_YSCB_MODULES", inserted_tokens, f"{mod_name} 未註冊 HOW_TO_YSCB_MODULES")

            for guide_name in ("config_guide.md", "usage_guide.md"):
                g_path = mod_dir / "assets" / guide_name
                self.assertTrue(g_path.is_file(), f"缺少 {g_path}")
                g_text = g_path.read_text(encoding="utf-8")
                self.assertTrue(10 <= len(g_text.splitlines()) <= 25, f"{g_path} 行數 ({len(g_text.splitlines())}) 超出 15~25 行預算")
                self.assertIn(f"(`__#{{module://{mod_name}/README.md}}__`)", g_text)
                if guide_name == "config_guide.md":
                    self.assertIn("① 組態項目與用途", g_text)
                    self.assertIn("② 健康度檢查條件", g_text)
                    self.assertIn("③ 隨包設定手冊語意連結", g_text)
                else:
                    self.assertIn("① 模組定位與適用時機", g_text)
                    self.assertIn("② 標準用法速查 (Golden Recipes)", g_text)
                    self.assertIn("③ 隨包手冊語意連結", g_text)
                clean_g = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", g_text))
                self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_g), [], f"{g_path} 含有未包覆單反引號之標籤")

        self.mark_passed()

    def test_skill_creator_extension_workflow(self):
        """驗證 skill-creator 三軌分流、藍圖確認卡、單層 extension-guide 錨點地圖、三步驗證守門與實機編譯零警告。"""
        assets = PKG_ROOT / "assets"
        skills_dir = assets / "skills"
        sc_dir = skills_dir / "skill-creator"
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        export_map = {item.get("name"): item for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("skill-creator", export_map)
        self.assertIn("SKILL_CREATOR_STANDARDS", token_names)
        self.assertEqual(len(token_names), 23)

        sc_md_path = sc_dir / "SKILL.md"
        self.assertTrue(sc_md_path.is_file())
        sc_text = sc_md_path.read_text(encoding="utf-8")
        self.assertLessEqual(len(sc_text.splitlines()), 180)
        self.assertNotIn("description", export_map["skill-creator"])
        self.assertIn(ArtifactCompiler().resolve_export_description(export_map["skill-creator"]), sc_text)
        self.assertIn("`__@{SKILL_CREATOR_STANDARDS}__`", sc_text)
        self.assertIn("## 常見踩坑指南 (Gotchas)", sc_text)

        self.assertIn("軌跡 ①：純錨點注入模式", sc_text)
        self.assertIn("Anchor-Only Injection", sc_text)
        self.assertIn("軌跡 ②：被動環境攔截型 Skill", sc_text)
        self.assertIn("軌跡 ③：功能特化型 Skill", sc_text)
        self.assertIn("0 路由表膨脹", sc_text)

        self.assertIn("agents-workflow tokens", sc_text)
        self.assertIn("uri list", sc_text)
        self.assertIn("references/extension-guide.md", sc_text)
        self.assertIn("### 🛠️ /skill-creator 專案擴充藍圖確認卡", sc_text)
        self.assertIn("End Turn", sc_text)

        self.assertIn("skills/<name>/SKILL.md", sc_text)
        self.assertIn("snippets/<name>.md", sc_text)
        self.assertIn("./references/", sc_text)
        self.assertIn("contributes check", sc_text)
        self.assertIn("agents-workflow compile", sc_text)
        self.assertIn("agents-workflow release", sc_text)
        self.assertLess(sc_text.index("contributes check"), sc_text.index("agents-workflow compile"))
        self.assertLess(sc_text.index("agents-workflow compile"), sc_text.index("agents-workflow release"))

        ref_path = sc_dir / "references" / "extension-guide.md"
        self.assertTrue(ref_path.is_file())
        sub_dirs = [p for p in (sc_dir / "references").iterdir() if p.is_dir()]
        self.assertEqual(sub_dirs, [])

        ref_text = ref_path.read_text(encoding="utf-8")
        self.assertIn("## 目錄 (Contents)", ref_text)
        all_24_tokens = token_names | {"KNOWLEDGE_DB_SPACE"}
        self.assertEqual(len(all_24_tokens), 24)
        for tok in all_24_tokens:
            self.assertIn(f"`{tok}`", ref_text, f"extension-guide.md 漏列 Stage 1 錨點: {tok}")
        self.assertIn("Markdown 表格列", ref_text)
        self.assertIn('"token": "PHASE05_AGENTS_GUIDE"', ref_text)
        self.assertIn('"token": "AGENTS_SKILL_ROUTING"', ref_text)

        sop_text = (skills_dir / "development-sop" / "SKILL.md").read_text(encoding="utf-8")
        opt_text = (skills_dir / "skill-optimizer" / "SKILL.md").read_text(encoding="utf-8")
        manifest_text = (PKG_ROOT / "contributes" / "_manifest.md").read_text(encoding="utf-8")
        self.assertIn("skill-creator/SKILL.md", sop_text)
        self.assertIn("skill-creator/SKILL.md", opt_text)
        self.assertIn("/skill-creator", manifest_text)

        for p in (sc_md_path, ref_path):
            txt = p.read_text(encoding="utf-8")
            self.assertNotIn("不要加反引號", txt)
            self.assertNotIn("compiler.py", txt)
            clean_txt = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", txt))
            self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_txt), [])

        compiler = ArtifactCompiler(host_dir=str(PKG_ROOT.parent.parent))
        deployment_map = {
            "module://agents-workflow/assets/standards/SkillDesignStandards.md": str(
                PKG_ROOT.parent.parent / ".agents" / ".yscb" / "standards" / "SkillDesignStandards.md"
            ),
            "module://agents-workflow/assets/standards/YscbSkillDesignToolStandards.md": str(
                PKG_ROOT.parent.parent / ".agents" / ".yscb" / "standards" / "YscbSkillDesignToolStandards.md"
            ),
            "module://agents-workflow/assets/skills/skill-optimizer/SKILL.md": str(
                PKG_ROOT.parent.parent / ".agents" / "skills" / "skill-optimizer" / "SKILL.md"
            ),
            "module://agents-workflow/assets/skills/how-to-config-yscb/SKILL.md": str(
                PKG_ROOT.parent.parent / ".agents" / "skills" / "how-to-config-yscb" / "SKILL.md"
            ),
            "module://agents-workflow/assets/skills/new-plan/SKILL.md": str(
                PKG_ROOT.parent.parent / ".agents" / "skills" / "new-plan" / "SKILL.md"
            ),
            "module://agents-workflow/assets/skills/development-sop/SKILL.md": str(
                PKG_ROOT.parent.parent / ".agents" / "skills" / "development-sop" / "SKILL.md"
            ),
        }
        sc_dst = str(PKG_ROOT.parent.parent / ".agents" / "skills" / "skill-creator" / "SKILL.md")
        ref_dst = str(PKG_ROOT.parent.parent / ".agents" / "skills" / "skill-creator" / "references" / "extension-guide.md")

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            res_sc = compiler.resolve_single_artifact(sc_text, contrib.get("insert", []))
            res_ref = compiler.resolve_single_artifact(ref_text, contrib.get("insert", []))
            stage2_sc = compiler.resolve_stage2_uri(res_sc, sc_dst, deployment_map)
            stage2_ref = compiler.resolve_stage2_uri(res_ref, ref_dst, deployment_map)
        stderr_out = err_buf.getvalue()
        self.assertNotIn("[compiler:warning]", stderr_out, f"實機 Stage 1/2 編譯產生預期外警告: {stderr_out}")

        self.assertIn("[`/skill-optimizer`](../skill-optimizer/SKILL.md)", stage2_sc)
        self.assertIn("[`/skill-optimizer`](../../skill-optimizer/SKILL.md)", stage2_ref)
        self.assertIn("/contribute.json`", stage2_sc)
        self.assertIn("/contribute.json`", stage2_ref)

        self.assertFalse(stage2_sc.rstrip().endswith("`__@{SKILL_CREATOR_STANDARDS}__`"))
        self.assertIn("- Stage 1 錨點（獨立行）：`__@{SKILL_CREATOR_STANDARDS}__`", stage2_sc)
        self.assertIn("(`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)", stage2_sc)
        self.assertIn("`__@{SKILL_CREATOR_STANDARDS}__`", stage2_ref)
        self.assertIn("(`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)", stage2_ref)
        self.assertIn("(`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)", stage2_ref)
        self.assertIn("`__${project://plans}__/`", stage2_ref)
        self.assertIn("`__${foo://non_existent_path}__`", stage2_ref)

        self.mark_passed()

    def test_cli_guide_purification_and_help_first(self):
        """驗證 yscb-cli-guide 拔除動態指令大表、收斂至 <= 65 行，並落實雙軌執行與 -h 按需自省規範。"""
        cli_guide_path = PKG_ROOT / "assets" / "skills" / "yscb-cli-guide" / "SKILL.md"
        self.assertTrue(cli_guide_path.is_file())
        cli_text = cli_guide_path.read_text(encoding="utf-8")
        lines = cli_text.splitlines()
        self.assertLessEqual(len(lines), 65, f"yscb-cli-guide/SKILL.md 行數 ({len(lines)}) 超出 65 行上限")

        self.assertIn("Skill-Vetted Fast Pass", cli_text)
        self.assertIn("Just-in-Time -h Inspection", cli_text)
        self.assertIn("-h", cli_text)
        self.assertIn("server start --console", cli_text)
        self.assertIn("[GATED] 授權守門", cli_text)
        self.assertIn("`__@{AGENTS_CLI_GUIDE}__`", cli_text)
        self.assertNotIn("YSCB_AGENTS_CLI_GUIDE_BEGIN", cli_text)

        clean_cli = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", cli_text))
        self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_cli), [])

        core_root = PKG_ROOT.parent / "core"
        if core_root.is_dir():
            core_aw_contrib = json.loads((core_root / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))
            core_insert_tokens = {ins.get("token") for ins in core_aw_contrib.get("insert", [])}
            self.assertNotIn("AGENTS_CLI_GUIDE", core_insert_tokens)
            self.assertFalse((core_root / "core" / "providers.py").exists())

        compiler = ArtifactCompiler()
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))
        stage1_out = compiler.resolve_single_artifact(cli_text, contrib.get("insert", []))
        self.assertNotIn("| 權限分級 | 指令名稱 |", stage1_out)
        self.assertNotIn("__@{AGENTS_CLI_GUIDE}__", stage1_out)
        self.assertLessEqual(len(stage1_out.splitlines()), 65)

        self.mark_passed()

    def test_stage2_locale_noun_projection_across_targets(self):
        """驗證 Stage 2 `__%{key}__` 依 target_name (antigravity/claude/codex) 精準展開宿主專有名詞。"""
        compiler = ArtifactCompiler()
        sample_md = (
            "請調用 `__%{agent_tool.file_read_range}__` 讀取區段，或使用 `__%{agent_tool.shell_exec}__` 執行。\n"
            "```bash\n"
            "# tool: __%{agent_tool.shell_bg_daemon}__\n"
            "```\n"
        )
        dst_p = os.path.join(PKG_ROOT, "SKILL.md")

        out_agy = compiler.resolve_stage2_uri(sample_md, dst_p, {}, target_name="antigravity")
        self.assertIn("`read_file (StartLine/EndLine)`", out_agy)
        self.assertIn("`run_command`", out_agy)
        self.assertIn("# tool: run_command (IsDaemon: true)", out_agy)

        out_claude = compiler.resolve_stage2_uri(sample_md, dst_p, {}, target_name="claude")
        self.assertIn("`Read (offset/limit)`", out_claude)
        self.assertIn("`Bash`", out_claude)
        self.assertIn("# tool: Bash (run_in_background: true)", out_claude)

        out_codex = compiler.resolve_stage2_uri(sample_md, dst_p, {}, target_name="codex")
        self.assertIn("`read_file`", out_codex)
        self.assertIn("`exec_command`", out_codex)
        self.assertIn("# tool: exec_command (background)", out_codex)

        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            out_unk = compiler.resolve_stage2_uri("未知標籤 `__%{agent_tool.non_existent}__`", dst_p, {}, target_name="antigravity")
        self.assertIn("[compiler:warning] Unresolved locale noun tag: 'agent_tool.non_existent'", err_buf.getvalue())
        self.assertIn("`__%{agent_tool.non_existent}__`", out_unk)

        self.mark_passed()

    def test_code_optimizer_skill_and_standards_anchor(self):
        """驗證 code-optimizer 純手動觸發、包含式三層範圍、雙模式、參考手冊與 Stage 1/2 實機編譯零警告。"""
        assets = PKG_ROOT / "assets"
        skills_dir = assets / "skills"
        co_dir = skills_dir / "code-optimizer"
        contrib = json.loads((PKG_ROOT / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        export_map = {item.get("name"): item for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("code-optimizer", export_map)
        self.assertIn("CODE_OPTIMIZER_STANDARDS", token_names)

        standards_text = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertNotIn("`code-optimizer`", standards_text)

        co_md_path = co_dir / "SKILL.md"
        self.assertTrue(co_md_path.is_file())
        co_text = co_md_path.read_text(encoding="utf-8")
        self.assertLessEqual(len(co_text.splitlines()), 180, f"code-optimizer/SKILL.md 行數超標: {len(co_text.splitlines())}")
        self.assertNotIn("description", export_map["code-optimizer"])
        self.assertIn(ArtifactCompiler().resolve_export_description(export_map["code-optimizer"]), co_text)
        self.assertIn("僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發", co_text)
        self.assertIn("`__@{CODE_OPTIMIZER_STANDARDS}__`", co_text)
        self.assertIn("## 常見踩坑指南 (Gotchas)", co_text)

        self.assertIn("全專案 ⊃ 單一模組 ⊃ 單一檔案", co_text)
        self.assertIn("File Scope", co_text)
        self.assertIn("Module Scope", co_text)
        self.assertIn("Project Scope", co_text)
        self.assertIn("不由 Agent 判斷", co_text)
        self.assertIn("Mode A", co_text)
        self.assertIn("Mode B", co_text)
        self.assertIn("0 外部跨模組調用", co_text)
        self.assertIn("直接執行破壞性變更與收斂", co_text)

        self.assertIn("R01_code_optimization_audit.md", co_text)
        self.assertIn("出口 ① 立即原地升級實作", co_text)
        self.assertIn("出口 ② 轉入技術儲備", co_text)
        self.assertIn("出口 ③ 維持現狀結案", co_text)
        self.assertIn("嚴禁轉入 `Revision Plan`", co_text)
        self.assertIn("End Turn", co_text)

        for guard_kw in ("No Pattern Mania", "No Nano-Functions", "Preserve Behavior & Error Semantics", "Self-Documenting over Noise Comments"):
            self.assertIn(guard_kw, co_text)

        ref_dir = co_dir / "references"
        self.assertTrue(ref_dir.is_dir())
        self.assertEqual([p for p in ref_dir.iterdir() if p.is_dir()], [])

        expected_refs = ("exploration-and-delegation.md", "diagnostic-matrix.md", "refactoring-playbook.md")
        for r_name in expected_refs:
            r_path = ref_dir / r_name
            self.assertTrue(r_path.is_file(), f"缺少參考手冊: {r_name}")
            r_txt = r_path.read_text(encoding="utf-8")
            self.assertIn("## 目錄 (Contents)", r_txt, f"{r_name} 缺少目錄 (TOC)")
            clean_r = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", r_txt))
            self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_r), [], f"{r_name} 含未加單反引號之標籤")

        exp_txt = (ref_dir / "exploration-and-delegation.md").read_text(encoding="utf-8")
        self.assertIn("全專案 ⊃ 單一模組 ⊃ 單一檔案", exp_txt)
        self.assertIn("0 外部跨模組引用", exp_txt)
        self.assertIn("400", exp_txt)

        diag_txt = (ref_dir / "diagnostic-matrix.md").read_text(encoding="utf-8")
        for dim in ("D1", "D2", "D3", "D4", "D5"):
            self.assertIn(dim, diag_txt)

        play_txt = (ref_dir / "refactoring-playbook.md").read_text(encoding="utf-8")
        for strat in ("S1", "S2", "S3", "S4", "S5", "S6"):
            self.assertIn(strat, play_txt)

        compiler = ArtifactCompiler(host_dir=str(PKG_ROOT.parent.parent))
        deployment_map = {
            f"module://agents-workflow/assets/skills/{s}/SKILL.md": str(
                PKG_ROOT.parent.parent / ".agents" / "skills" / s / "SKILL.md"
            )
            for s in ("development-sop", "testing-sop", "skill-optimizer", "new-plan", "auto", "code-optimizer", "blind-subagent", "discuss")
        }
        for std_name in (
            "AgentsStandards.md",
            "CodeQualityStandards.md",
            "SkillDesignStandards.md",
            "YscbSkillDesignToolStandards.md",
            "SubagentStandards.md",
            "BlindSubagentStandards.md",
        ):
            deployment_map[f"module://agents-workflow/assets/standards/{std_name}"] = str(
                PKG_ROOT.parent.parent / ".agents" / ".yscb" / "standards" / std_name
            )
        for t_name in ("P00_discuss.md", "RXX_research_report.md", "fast_track_plan.md", "umbrella_overview.md"):
            deployment_map[f"module://agents-workflow/assets/templates/{t_name}"] = str(
                PKG_ROOT.parent.parent / ".agents" / ".yscb" / "templates" / t_name
            )

        co_dst = str(PKG_ROOT.parent.parent / ".agents" / "skills" / "code-optimizer" / "SKILL.md")
        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            stage1_co = compiler.resolve_single_artifact(co_text, contrib.get("insert", []))
            stage2_agy = compiler.resolve_stage2_uri(stage1_co, co_dst, deployment_map, target_name="antigravity")
            stage2_claude = compiler.resolve_stage2_uri(stage1_co, co_dst, deployment_map, target_name="claude")
            stage2_codex = compiler.resolve_stage2_uri(stage1_co, co_dst, deployment_map, target_name="codex")
            for r_name in expected_refs:
                r_txt = (ref_dir / r_name).read_text(encoding="utf-8")
                r_dst = str(PKG_ROOT.parent.parent / ".agents" / "skills" / "code-optimizer" / "references" / r_name)
                r_s1 = compiler.resolve_single_artifact(r_txt, contrib.get("insert", []))
                compiler.resolve_stage2_uri(r_s1, r_dst, deployment_map, target_name="antigravity")
        self.assertEqual(err_buf.getvalue(), "", f"Stage 1/2 編譯產生警告: {err_buf.getvalue()}")

        self.assertNotIn("`__@{CODE_OPTIMIZER_STANDARDS}__`", stage1_co)
        self.assertIn("`read_file (StartLine/EndLine)`", stage2_agy)
        self.assertIn("`Read (offset/limit)`", stage2_claude)
        self.assertIn("`exec_command`", stage2_codex)

        injected_co = compiler.resolve_single_artifact(
            co_text,
            [{"token": "CODE_OPTIMIZER_STANDARDS", "mode": "below", "value": "### 專案特化 D5 架構規則\n- 強制使用 core.uri"}],
        )
        self.assertIn("### 專案特化 D5 架構規則", injected_co)

        self.assertIn("軌道 1：純主代理內聯執行", co_text)
        self.assertIn("軌道 2A：純主代理內聯審查", co_text)
        self.assertIn("軌道 2B：主代理 + 盲眼子代理", co_text)
        self.assertIn("軌道 3A：主代理序列滾動推進", co_text)
        self.assertIn("軌道 3B：主代理統籌 + N 路盲眼子代理平行推進", co_text)

        std_sources = {item.get("source") for item in contrib["export"] if item.get("type") == "standard"}
        self.assertIn("module://agents-workflow/assets/standards/CodeQualityStandards.md", std_sources)
        self.assertIn("module://agents-workflow/assets/standards/SkillDesignStandards.md", std_sources)
        self.assertIn("module://agents-workflow/assets/standards/YscbSkillDesignToolStandards.md", std_sources)
        self.assertIn("module://agents-workflow/assets/standards/SubagentStandards.md", std_sources)
        self.assertIn("module://agents-workflow/assets/standards/BlindSubagentStandards.md", std_sources)

        cqs_path = assets / "standards" / "CodeQualityStandards.md"
        sds_path = assets / "standards" / "SkillDesignStandards.md"
        ysdts_path = assets / "standards" / "YscbSkillDesignToolStandards.md"
        sub_std_path = assets / "standards" / "SubagentStandards.md"
        blind_std_path = assets / "standards" / "BlindSubagentStandards.md"
        self.assertTrue(cqs_path.is_file())
        self.assertTrue(sds_path.is_file())
        self.assertTrue(ysdts_path.is_file())
        self.assertTrue(sub_std_path.is_file())
        self.assertTrue(blind_std_path.is_file())
        for std_p in (cqs_path, sds_path, ysdts_path, sub_std_path, blind_std_path):
            s_txt = std_p.read_text(encoding="utf-8")
            clean_s = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", s_txt))
            self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_s), [], f"{std_p.name} 含未加單反引號之標籤")
            s_dst = str(PKG_ROOT.parent.parent / ".agents" / ".yscb" / "standards" / std_p.name)
            with contextlib.redirect_stderr(err_buf):
                s_s1 = compiler.resolve_single_artifact(s_txt, contrib.get("insert", []))
                compiler.resolve_stage2_uri(s_s1, s_dst, deployment_map, target_name="antigravity")
        self.assertEqual(err_buf.getvalue(), "", f"Standards Stage 1/2 編譯產生警告: {err_buf.getvalue()}")

        sub_std_s1 = compiler.resolve_single_artifact(sub_std_path.read_text(encoding="utf-8"), contrib.get("insert", []))
        blind_std_s1 = compiler.resolve_single_artifact(blind_std_path.read_text(encoding="utf-8"), contrib.get("insert", []))
        self.assertTrue(blind_std_s1.startswith(sub_std_s1.rstrip("\r\n")))
        self.assertIn("去錨定提示詞淨化", blind_std_s1)
        self.assertNotIn("`__@{SUBAGENT_BASE_STANDARDS}__`", blind_std_s1)

        blind_skill_txt = (skills_dir / "blind-subagent" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("透過盲眼子代理執行任務時觸發", blind_skill_txt)
        self.assertIn("BlindSubagentStandards.md", blind_skill_txt)

        auto_txt = (skills_dir / "auto" / "SKILL.md").read_text(encoding="utf-8")
        p05_txt = (skills_dir / "development-sop" / "references" / "phase_05_task.md").read_text(encoding="utf-8")
        p06_txt = (skills_dir / "development-sop" / "references" / "phase_06_test.md").read_text(encoding="utf-8")
        p07_txt = (skills_dir / "development-sop" / "references" / "phase_07_walkthrough.md").read_text(encoding="utf-8")
        self.assertNotIn("5 個檔案", auto_txt)
        self.assertNotIn("1,500", auto_txt)
        self.assertIn("BlindSubagentStandards.md", auto_txt)
        self.assertIn("SubagentStandards.md", p05_txt)
        self.assertIn("BlindSubagentStandards.md", p06_txt)
        self.assertIn("BlindSubagentStandards.md", p07_txt)
        cqs_text = cqs_path.read_text(encoding="utf-8")
        sds_text = sds_path.read_text(encoding="utf-8")
        ysdts_text = ysdts_path.read_text(encoding="utf-8")
        self.assertIn("`__@{CODE_OPTIMIZER_STANDARDS}__`", cqs_text)
        self.assertIn("零工單與審計編號註解鐵律", cqs_text)
        self.assertIn("雙軌結構化 `description` 契約", sds_text)
        self.assertIn("A1 正向邊界契約", sds_text)
        self.assertIn("軌跡 B-Strict", sds_text)
        self.assertIn("軌跡 B-Assist", sds_text)
        self.assertIn("Artifact-in-File", sds_text)
        self.assertIn("Artifact-in-Chat", sds_text)
        self.assertNotIn("YscbSkillDesignToolStandards", sds_text)
        self.assertNotIn("skill-creator", sds_text)
        self.assertNotIn("skill-optimizer", sds_text)
        self.assertIn("<!-- yscb:literal:begin -->", ysdts_text)
        self.assertIn("<!-- yscb:literal:end -->", ysdts_text)
        self.assertIn("<!-- yscb:ignore:begin -->", ysdts_text)
        self.assertIn("<!-- yscb:ignore:end -->", ysdts_text)
        self.assertIn("contributes check", ysdts_text)
        self.assertIn("agents-workflow compile", ysdts_text)
        self.assertIn("agents-workflow release", ysdts_text)

        sop_ref = skills_dir / "development-sop" / "references"
        for sop_file in ("phase_05_task.md", "phase_06_test.md", "fast_track_plan.md"):
            self.assertIn("CodeQualityStandards.md", (sop_ref / sop_file).read_text(encoding="utf-8"))
        self.assertIn("CodeQualityStandards.md", (skills_dir / "auto" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("/code-optimizer", (sop_ref / "phase_07_walkthrough.md").read_text(encoding="utf-8"))
        self.assertIn("SkillDesignStandards.md", (skills_dir / "skill-creator" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("YscbSkillDesignToolStandards.md", (skills_dir / "skill-creator" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("SkillDesignStandards.md", (skills_dir / "skill-optimizer" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("YscbSkillDesignToolStandards.md", (skills_dir / "skill-optimizer" / "SKILL.md").read_text(encoding="utf-8"))

        self.mark_passed()

    def test_literal_and_ignore_block_directives(self):
        """驗證 yscb:literal:begin/end（含巢狀自舉）與 yscb:ignore:begin/end 區塊保護、抹除與未閉合警告。"""
        compiler = ArtifactCompiler(host_dir=str(PKG_ROOT.parent.parent))
        src_doc = (
            "# Title\n"
            "<!-- yscb:ignore:begin -->\n"
            "維護者源碼註解：包含裸標籤 __@{RAW_UNENCLOSED}__ 與假路徑 `__${fake://ignore}__`\n"
            "<!-- yscb:literal:begin -->\n"
            "在 ignore 區塊內的 literal 標記也應一併被忽略抹除\n"
            "<!-- yscb:literal:end -->\n"
            "<!-- yscb:ignore:end -->\n"
            "`__@{INJECT_TARGET}__`\n"
            "<!-- yscb:literal:begin -->\n"
            "段落字面量保護：`__@{INJECT_TARGET}__` 與裸標籤 __${raw://unenclosed}__\n"
            "```markdown\n"
            "<!-- yscb:literal:begin -->\n"
            "內層教學範例：`__#{module://demo/SKILL.md}__`\n"
            "<!-- yscb:literal:end -->\n"
            "<!-- yscb:ignore:begin -->\n"
            "內層教學展示之 ignore 註解（因外層為 literal 故保留）\n"
            "<!-- yscb:ignore:end -->\n"
            "```\n"
            "<!-- yscb:literal:end -->\n"
        )
        inserts = [
            {
                "type": "const",
                "token": "INJECT_TARGET",
                "mode": "replace",
                "value": "<!-- yscb:ignore:begin -->\n注入片段內註解\n<!-- yscb:ignore:end -->\nInjected Body",
            }
        ]
        err_buf = io.StringIO()
        dst_path = str(PKG_ROOT.parent.parent / ".agents" / "skills" / "demo" / "SKILL.md")
        with contextlib.redirect_stderr(err_buf):
            s1_out = compiler.resolve_single_artifact(src_doc, inserts)
            s2_out = compiler.resolve_stage2_uri(s1_out, dst_path, {}, target_name="antigravity")
        self.assertEqual(err_buf.getvalue(), "", f"合規 literal/ignore 區塊不應產生任何警告: {err_buf.getvalue()}")

        self.assertNotIn("維護者源碼註解", s1_out)
        self.assertNotIn("注入片段內註解", s1_out)
        self.assertIn("Injected Body", s1_out)
        self.assertNotIn("維護者源碼註解", s2_out)
        self.assertNotIn("在 ignore 區塊內的 literal", s2_out)
        self.assertIn("段落字面量保護：`__@{INJECT_TARGET}__` 與裸標籤 __${raw://unenclosed}__", s2_out)
        self.assertIn("<!-- yscb:literal:begin -->\n內層教學範例：`__#{module://demo/SKILL.md}__`\n<!-- yscb:literal:end -->", s2_out)
        self.assertIn("<!-- yscb:ignore:begin -->\n內層教學展示之 ignore 註解（因外層為 literal 故保留）\n<!-- yscb:ignore:end -->", s2_out)
        self.assertEqual(s2_out.count("<!-- yscb:literal:begin -->"), 1, "最外層 literal:begin 應於 Stage 2 被剝除，僅保留內層 1 處")
        self.assertEqual(s2_out.count("<!-- yscb:literal:end -->"), 1, "最外層 literal:end 應於 Stage 2 被剝除，僅保留內層 1 處")

        for bad_doc, expected_warn in (
            ("<!-- yscb:literal:begin -->\nunclosed", "Unclosed '<!-- yscb:literal:begin -->'"),
            ("<!-- yscb:ignore:begin -->\nunclosed", "Unclosed '<!-- yscb:ignore:begin -->'"),
            ("stray\n<!-- yscb:literal:end -->\n", "Unmatched '<!-- yscb:literal:end -->'"),
            ("stray\n<!-- yscb:ignore:end -->\n", "Unmatched '<!-- yscb:ignore:end -->'"),
        ):
            warn_buf = io.StringIO()
            with contextlib.redirect_stderr(warn_buf):
                compiler.resolve_single_artifact(bad_doc, [])
            self.assertIn(expected_warn, warn_buf.getvalue())

        from core import uri as core_uri
        proj_root = core_uri.resolve("project://", interactive=False)
        root_compiler = ArtifactCompiler(host_dir=proj_root)
        root_tag_out = root_compiler.resolve_stage2_uri("Root dir: `__${project://}__`", dst_path, {}, target_name="antigravity")
        self.assertEqual(root_tag_out, "Root dir: `./`")

        self.mark_passed()

    def test_legacy_workflow_export_translation_and_cli_normalize_bags(self):
        """驗證舊版 type: 'workflow' 於記憶體無痛轉譯為 'skill'，且 cli._normalize_bags 支援空白分隔 --key val。"""
        compiler = ArtifactCompiler(host_dir=str(PKG_ROOT.parent.parent))
        with mock.patch("core.contributes.get") as mock_get:
            mock_get.return_value = {
                "export": [
                    {"source": "module://agents-workflow/assets/skills/auto", "type": "workflow", "name": "auto"},
                    {"source": "module://agents-workflow/assets/templates/P00_discuss.md", "type": "template"},
                ],
                "insert": [],
                "token": [],
                "release_target": [],
            }
            data = compiler.get_contributes_data()
            self.assertEqual(data["export"][0]["type"], "skill")
            self.assertEqual(data["export"][1]["type"], "template")

        desc = compiler.resolve_export_description(
            {"source": "module://agents-workflow/assets/skills/auto", "type": "workflow"}
        )
        self.assertIn("/auto", desc)

        bags_todo = cli._normalize_bags(["Fix bug", "--scope", "dev", "--note", "detail"], "todo_add")
        self.assertEqual(bags_todo.args, ["Fix bug"])
        self.assertEqual(bags_todo.get_option_value("scope"), "dev")
        self.assertEqual(bags_todo.get_option_value("note"), "detail")

        bags_rt = cli._normalize_bags(["--add", "claude", "--proj"], "release-target")
        self.assertEqual(bags_rt.args, [])
        self.assertEqual(bags_rt.get_option_value("add"), "claude")
        self.assertTrue(bags_rt.has_option("proj"))
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
