"""
Unit Tests for agents-workflow Release Targets (Antigravity, Claude Code, OpenAI Codex, and expanded targets).
Covers Local by Default, --proj flag, multi-tier list_targets, and .gitignore soft-merge.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if getattr(sys.modules.get("tests"), "PKG_ROOT", None) != Path(__file__).resolve().parent.parent:
    sys.modules.pop("tests", None)

from tests import ConfigStateSnapshot, load_cli_module

cli_mod = load_cli_module("aw_cli_targets_test")

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher
from agents_workflow.targets import ReleaseTargetManager
from core import config
from core.commands.bags import CmdBags, CmdOption
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

_MANAGED_GI_BEGIN = "# === YSCB MANAGED GITIGNORE BEGIN ==="
_MANAGED_GI_END = "# === YSCB MANAGED GITIGNORE END ==="


@require(Requirement.LOGIC | Requirement.ENV)
class TestReleaseTargets(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        config.delete("agents-workflow", "release_targets", local=True)
        config.set("agents-workflow", "release_targets", ["antigravity"], local=False)
        config.reload()

    def tearDown(self):
        self._snapshot.restore()
        super().tearDown()

    def test_manifest_targets_discovery(self):
        """驗證 contributes/agents-workflow.json 中 8 大預設 target 均被正確解析。"""
        targets = self.compiler.get_release_targets()
        target_names = [t.get("name") for t in targets]

        for expected_name in (
            "antigravity",
            "claude",
            "codex",
            "cursor",
            "copilot",
            "windsurf",
            "opencode",
            "roo",
        ):
            self.assertIn(expected_name, target_names)
        self.mark_passed()

    def test_list_targets_output_and_both_orphan_statuses(self):
        """驗證 ReleaseTargetManager.list_targets() 正確列出各 target 資訊與 LOCAL/PROJECT/BOTH/ORPHAN 標籤。"""
        target_list = ReleaseTargetManager.list_targets()
        names = [t["name"] for t in target_list]

        self.assertIn("antigravity", names)
        self.assertIn("claude", names)
        self.assertIn("codex", names)

        claude_info = next(t for t in target_list if t["name"] == "claude")
        self.assertIn("Claude Code", claude_info["description"])
        self.assertEqual(claude_info["status"], "[DISABLED]")

        codex_info = next(t for t in target_list if t["name"] == "codex")
        self.assertIn("Codex", codex_info["description"])

        # 驗證 BOTH 與 ORPHAN (LOCAL / PROJECT / BOTH) 狀態
        ReleaseTargetManager.save_tier_targets(["antigravity", "claude", "ghost_proj", "ghost_both"], is_project=True)
        ReleaseTargetManager.save_tier_targets(["claude", "ghost_local", "ghost_both"], is_project=False)

        by_name = {t["name"]: t for t in ReleaseTargetManager.list_targets()}
        self.assertEqual(by_name["claude"]["status"], "[ENABLED (BOTH)]")
        self.assertEqual(by_name["claude"]["source"], "both")
        self.assertEqual(by_name["ghost_local"]["status"], "[ORPHAN / NOT FOUND (LOCAL)]")
        self.assertEqual(by_name["ghost_local"]["source"], "orphan")
        self.assertEqual(by_name["ghost_proj"]["status"], "[ORPHAN / NOT FOUND (PROJECT)]")
        self.assertEqual(by_name["ghost_both"]["status"], "[ORPHAN / NOT FOUND (BOTH)]")
        self.mark_passed()

    def test_get_tier_targets_returns_shallow_copy_without_mutating_default(self):
        """驗證 get_tier_targets() 在正常、預設與異常情境下皆回傳獨立拷貝，絕不污染 DEFAULT_PROJECT_TARGETS。"""
        self.assertEqual(ReleaseTargetManager.DEFAULT_PROJECT_TARGETS, ("antigravity",))

        with patch("agents_workflow.targets.config", None):
            fallback_proj = ReleaseTargetManager.get_tier_targets(is_project=True)
            fallback_proj.append("mutated_when_config_none")
            self.assertEqual(ReleaseTargetManager.DEFAULT_PROJECT_TARGETS, ("antigravity",))
            self.assertEqual(ReleaseTargetManager.get_tier_targets(is_project=False), [])

        with patch("core.config.get_raw", side_effect=RuntimeError("config read error")):
            fallback_err = ReleaseTargetManager.get_tier_targets(is_project=True)
            fallback_err.append("mutated_on_exception")
            self.assertEqual(ReleaseTargetManager.DEFAULT_PROJECT_TARGETS, ("antigravity",))

        with patch("core.config.get_raw", return_value=None):
            fallback_none = ReleaseTargetManager.get_tier_targets(is_project=True)
            fallback_none.append("mutated_on_none")
            self.assertEqual(ReleaseTargetManager.DEFAULT_PROJECT_TARGETS, ("antigravity",))
        self.mark_passed()

    def test_claude_projections_and_materialization(self):
        """驗證 claude target 投影拓撲映射正確包含 .claude/skills/ 與 .claude/.yscb/。"""
        targets = {t["name"]: t for t in self.compiler.get_release_targets()}
        claude_target = targets.get("claude", {})

        projections = claude_target.get("projections", {})
        self.assertNotIn("workflow", projections)
        self.assertEqual(projections.get("template", {}).get("target_dir"), "project://.claude/.yscb/templates")
        self.assertEqual(projections.get("standard", {}).get("target_dir"), "project://.claude/.yscb/standards")
        self.assertEqual(projections.get("skill", {}).get("target_dir"), "project://.claude/skills/{export.name}")

        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res.get("success", False))
        resolved_items = stage1_res.get("resolved_items", [])
        dep_map, _ = self.publisher.build_deployment_map(claude_target, resolved_items)

        self.assertTrue(
            any(p.replace("\\", "/").endswith(".claude/skills/auto/SKILL.md") for p in dep_map.values())
        )
        self.mark_passed()

    def test_codex_projections_and_materialization(self):
        """驗證 codex target 官方投影拓撲映射正確對齊 .agents/skills/。"""
        targets = {t["name"]: t for t in self.compiler.get_release_targets()}
        codex_target = targets.get("codex", {})

        projections = codex_target.get("projections", {})
        self.assertNotIn("workflow", projections)
        self.assertEqual(projections.get("template", {}).get("target_dir"), "project://.agents/.yscb/templates")
        self.assertEqual(projections.get("standard", {}).get("target_dir"), "project://.agents/.yscb/standards")
        self.assertEqual(projections.get("skill", {}).get("target_dir"), "project://.agents/skills/{export.name}")

        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res.get("success", False))
        resolved_items = stage1_res.get("resolved_items", [])
        dep_map, _ = self.publisher.build_deployment_map(codex_target, resolved_items)

        self.assertTrue(
            any(p.replace("\\", "/").endswith(".agents/skills/auto/SKILL.md") for p in dep_map.values())
        )
        self.mark_passed()

    def test_local_by_default_and_proj_flag(self):
        """驗證 ReleaseTargetManager 預設 Local 操作與 is_project=True 模式（隔離 release_all 副作用）。"""
        with patch.object(ReleasePublisher, "release_all", return_value={"success": True}) as mock_rel:
            self.assertTrue(ReleaseTargetManager.add_target("claude", is_project=False))
            local_targets = config.get_raw("agents-workflow", "release_targets", local=True)
            self.assertIn("claude", local_targets)

            self.assertTrue(ReleaseTargetManager.add_target("codex", is_project=True))
            proj_targets = config.get_raw("agents-workflow", "release_targets", local=False)
            self.assertIn("codex", proj_targets)

            targets_info = {t["name"]: t for t in ReleaseTargetManager.list_targets()}
            self.assertEqual(targets_info["claude"]["status"], "[ENABLED (LOCAL)]")
            self.assertEqual(targets_info["codex"]["status"], "[ENABLED (PROJECT)]")

            self.assertTrue(ReleaseTargetManager.remove_target("claude", is_project=False))
            self.assertNotIn("claude", config.get_raw("agents-workflow", "release_targets", local=True))

            self.assertTrue(ReleaseTargetManager.remove_target("codex", is_project=True))
            self.assertNotIn("codex", config.get_raw("agents-workflow", "release_targets", local=False))
            self.assertEqual(mock_rel.call_count, 4)
        self.mark_passed()

    def test_sync_gitignore_soft_merge(self):
        """驗證 .gitignore 區塊非破壞性軟合併、自訂規則保留、個別檔案精準忽略與自動新建。"""
        temp_dir = tempfile.mkdtemp(prefix="test_aw_gitignore_")
        try:
            fake_files = [
                os.path.join(temp_dir, ".agents", "workflows", "Auto.md"),
                os.path.join(temp_dir, ".agents", "workflows", "NewPlan.md"),
                os.path.join(temp_dir, ".agents", ".yscb", "templates", "P00.md"),
                os.path.join(temp_dir, ".claude", "commands", "Auto.md"),
            ]
            res1 = self.publisher.sync_gitignore(
                active_targets=["antigravity", "claude"],
                published_files=fake_files,
                proj_root=temp_dir,
            )
            self.assertTrue(res1["created"])
            gi_file = os.path.join(temp_dir, ".gitignore")
            self.assertTrue(os.path.isfile(gi_file))
            with open(gi_file, "r", encoding="utf-8") as f:
                content1 = f.read()
            self.assertIn(_MANAGED_GI_BEGIN, content1)
            self.assertIn("/.agents/.yscb/templates/P00.md", content1)
            self.assertIn("/.agents/workflows/Auto.md", content1)
            self.assertIn("/.claude/commands/Auto.md", content1)
            self.assertNotIn("\n.agents/\n", content1)
            self.assertNotIn("\n/.agents/\n", content1)
            self.assertNotIn("\n/.agents/.yscb/\n", content1)
            self.assertIn(_MANAGED_GI_END, content1)

            custom_prefix = "# User custom rules\n*.tmp\nnode_modules/\n\n"
            custom_suffix = "\n# Trailing custom rule\n.env\n"
            with open(gi_file, "w", encoding="utf-8") as f:
                f.write(custom_prefix + content1 + custom_suffix)

            fake_files_codex = [
                os.path.join(temp_dir, ".agents", "workflows", "Auto.md"),
                os.path.join(temp_dir, ".codex", "workflows", "Auto.md"),
            ]
            res2 = self.publisher.sync_gitignore(
                active_targets=["antigravity", "codex"],
                published_files=fake_files_codex,
                proj_root=temp_dir,
            )
            self.assertTrue(res2["updated"])
            with open(gi_file, "r", encoding="utf-8") as f:
                content2 = f.read()

            self.assertIn("*.tmp", content2)
            self.assertIn("node_modules/", content2)
            self.assertIn(".env", content2)

            self.assertIn("/.agents/workflows/Auto.md", content2)
            self.assertIn("/.codex/workflows/Auto.md", content2)
            self.assertNotIn("/.claude/commands/Auto.md", content2)
            self.mark_passed()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_release_target_cli_syntax_and_boundaries(self):
        """驗證 release-target 支援 --add/add、--remove/remove/--rm 語法、--proj 旗標及錯誤邊界。"""
        # 1. --add claude --proj (選項帶值)
        bags_opt_add = CmdBags(
            raw_cmd="release-target --add claude --proj",
            command="release-target",
            args=[],
            options={
                "add": CmdOption(name="add", params="claude"),
                "proj": CmdOption(name="proj", params=True),
            },
        )
        with patch.object(ReleaseTargetManager, "add_target", return_value=True) as mock_add:
            ret = cli_mod.release_target(bags_opt_add)
            self.assertEqual(ret, 0)
            mock_add.assert_called_once_with("claude", is_project=True)

        # 2. add claude --proj (位置引數) 與 add_target 失敗返回 1
        bags_pos_add = CmdBags(
            raw_cmd="release-target add claude --proj",
            command="release-target",
            args=["add", "claude"],
            options={
                "proj": CmdOption(name="proj", params=True),
            },
        )
        with patch.object(ReleaseTargetManager, "add_target", return_value=False) as mock_add_fail:
            self.assertEqual(cli_mod.release_target(bags_pos_add), 1)
            mock_add_fail.assert_called_once_with("claude", is_project=True)

        # 3. --remove claude --proj (選項帶值)
        bags_opt_rm = CmdBags(
            raw_cmd="release-target --remove claude --proj",
            command="release-target",
            args=[],
            options={
                "remove": CmdOption(name="remove", params="claude"),
                "proj": CmdOption(name="proj", params=True),
            },
        )
        with patch.object(ReleaseTargetManager, "remove_target", return_value=True) as mock_rm:
            ret = cli_mod.release_target(bags_opt_rm)
            self.assertEqual(ret, 0)
            mock_rm.assert_called_once_with("claude", is_project=True)

        # 4. --rm claude --proj (字串陣列與 CmdBags 雙模式) 與 remove_target 失敗返回 1
        with patch.object(ReleaseTargetManager, "remove_target", return_value=True) as mock_rm_short:
            self.assertEqual(cli_mod.release_target(["--rm", "claude", "--proj"]), 0)
            mock_rm_short.assert_called_once_with("claude", is_project=True)

        bags_pos_rm = CmdBags(
            raw_cmd="release-target remove claude --proj",
            command="release-target",
            args=["remove", "claude"],
            options={
                "proj": CmdOption(name="proj", params=True),
            },
        )
        with patch.object(ReleaseTargetManager, "remove_target", return_value=False) as mock_rm_fail:
            self.assertEqual(cli_mod.release_target(bags_pos_rm), 1)
            mock_rm_fail.assert_called_once_with("claude", is_project=True)

        # 5. 邊界測試：缺少目標名稱時報錯 (--add / --remove / --rm)
        bags_missing_add = CmdBags(
            raw_cmd="release-target --add",
            command="release-target",
            args=[],
            options={"add": CmdOption(name="add", params=True)},
        )
        self.assertEqual(cli_mod.release_target(bags_missing_add), 1)

        bags_missing_rm = CmdBags(
            raw_cmd="release-target --remove",
            command="release-target",
            args=[],
            options={"remove": CmdOption(name="remove", params=True)},
        )
        self.assertEqual(cli_mod.release_target(bags_missing_rm), 1)

        # 6. 邊界測試：空清單與未知選項
        out_empty = io.StringIO()
        with patch.object(ReleaseTargetManager, "list_targets", return_value=[]), redirect_stdout(out_empty):
            self.assertEqual(cli_mod.release_target(["--list"]), 0)
        self.assertIn("No release targets found.", out_empty.getvalue())

        self.assertEqual(cli_mod.release_target(["unknown_subcmd"]), 1)
        self.mark_passed()

    def test_expanded_targets_copilot_relative_links_and_shared_union(self):
        """驗證 5 大擴充 target 投影拓撲、copilot 子目錄相對連結與多 Target 共用實體路徑並聯渲染暨 Warning。"""
        targets = {t["name"]: t for t in self.compiler.get_release_targets()}
        for t_name, expected_prefix, expected_agents_md in (
            ("cursor", "project://.cursor", "project://AGENTS.md"),
            ("copilot", "project://.github", "project://.github/copilot-instructions.md"),
            ("windsurf", "project://.windsurf", "project://AGENTS.md"),
            ("opencode", "project://.opencode", "project://AGENTS.md"),
            ("roo", "project://.roo", "project://AGENTS.md"),
        ):
            t_cfg = targets.get(t_name, {})
            self.assertEqual(t_cfg.get("agents_md"), expected_agents_md)
            proj = t_cfg.get("projections", {})
            self.assertEqual(proj.get("skill", {}).get("target_dir"), f"{expected_prefix}/skills/{{export.name}}")
            self.assertEqual(proj.get("template", {}).get("target_dir"), f"{expected_prefix}/.yscb/templates")
            self.assertEqual(proj.get("standard", {}).get("target_dir"), f"{expected_prefix}/.yscb/standards")

        stage1_res = self.compiler.compile_stage1()
        self.assertTrue(stage1_res.get("success", False))
        resolved_items = stage1_res.get("resolved_items", [])

        temp_dir = tempfile.mkdtemp(prefix="test_aw_multi_union_")
        try:
            _, _, all_copilot, _, warnings_copilot = self.publisher._prepare_target_compilations(
                active_target_names=["copilot"],
                all_registered_targets=targets,
                proj_tier_targets={"copilot"},
                resolved_items=resolved_items,
                proj_root=temp_dir,
            )
            self.assertEqual(warnings_copilot, [])
            copilot_md_abs = os.path.normpath(os.path.join(temp_dir, ".github", "copilot-instructions.md"))
            self.assertIn(copilot_md_abs, all_copilot)
            copilot_md_text = all_copilot[copilot_md_abs]
            self.assertIn("(./skills/development-sop/SKILL.md)", copilot_md_text)
            self.assertNotIn("(.github/skills/", copilot_md_text)

            gi_res = self.publisher.sync_gitignore(
                active_targets=["copilot"],
                published_files=set(all_copilot.keys()),
                proj_root=temp_dir,
            )
            self.assertNotIn("/.github/copilot-instructions.md", gi_res["patterns"])

            stderr_buf = io.StringIO()
            with redirect_stderr(stderr_buf):
                _, _, all_multi, _, warnings_multi = self.publisher._prepare_target_compilations(
                    active_target_names=["antigravity", "codex", "cursor"],
                    all_registered_targets=targets,
                    proj_tier_targets={"antigravity"},
                    resolved_items=resolved_items,
                    proj_root=temp_dir,
                )
            stderr_out = stderr_buf.getvalue()
            self.assertGreaterEqual(len(warnings_multi), 1)
            self.assertIn("[publisher:warning]", stderr_out)
            self.assertIn("config.local.json", stderr_out)

            agents_md_abs = os.path.normpath(os.path.join(temp_dir, "AGENTS.md"))
            self.assertIn(agents_md_abs, all_multi)
            agents_md_text = all_multi[agents_md_abs]
            self.assertIn(".agents/skills/development-sop/SKILL.md / .cursor/skills/development-sop/SKILL.md", agents_md_text)

            co_skill_abs = os.path.normpath(
                os.path.join(temp_dir, ".agents", "skills", "code-optimizer", "SKILL.md")
            )
            self.assertIn(co_skill_abs, all_multi)
            co_skill_text = all_multi[co_skill_abs]
            self.assertIn("read_file (StartLine/EndLine) / read_file", co_skill_text)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
