"""
Unit & Edge Case Tests for agents-workflow Release Publisher Diff Optimization, Hooks, and Migrations.
Validates Stage 0 Fingerprint Short-Circuit, Stage 4 Content Diff, Force Release, and Edge Cases.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import io
import json
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

from tests import (
    ConfigStateSnapshot,
    load_cli_module,
    load_hook_core_module,
    load_hook_dev_module,
    load_migration_module,
)

cli_mod = load_cli_module("aw_cli_publisher_test")
cmd_release = cli_mod.release

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import (
    AGENTS_MD_BEGIN,
    AGENTS_MD_END,
    LOCAL_MANIFEST_CACHE_URI,
    PROJECT_MANIFEST_CACHE_URI,
    SHA1_CACHE_URI,
    ReleasePublisher,
    ensure_jit_release,
)
from agents_workflow.targets import ReleaseTargetManager

try:
    from core import config, uri, vfs
except ImportError:
    config = None
    uri = None
    vfs = None

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.LOGIC | Requirement.ENV)
class TestReleasePublisherDiff(YSCBTestCase):
    """測試發布引擎來源指紋短路與落地 Diff 優化。"""

    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_pub_diff_")
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    def tearDown(self):
        self._snapshot.restore()
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_initial_release_persists_fingerprint(self):
        """驗證首次發布成功物化檔案，Manifest 正確記錄指紋與發布檔案清冊。"""
        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertFalse(res["short_circuited"])
        self.assertGreater(res["published_count"], 0)
        self.assertEqual(res["written_count"], res["published_count"])
        self.assertEqual(res["skipped_count"], 0)
        self.assertIn("fingerprint", res)
        self.assertTrue(len(res["fingerprint"]) > 0)

        self.assertTrue(bool(uri and vfs.exists(PROJECT_MANIFEST_CACHE_URI)))
        manifest_data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        self.assertEqual(manifest_data.get("fingerprint"), res["fingerprint"])
        self.assertEqual(len(manifest_data.get("published_files", [])), res["published_count"])
        self.mark_passed()

    def test_short_circuit_when_no_change(self):
        """驗證二次發布在無異動情況下觸發 Stage 0 短路 (0 I/O)。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["short_circuited"])
        self.assertEqual(res2["written_count"], 0)
        self.assertEqual(res2["skipped_count"], res1["published_count"])
        self.assertEqual(res2["fingerprint"], res1["fingerprint"])
        self.mark_passed()

    def test_incremental_write_on_partial_change(self):
        """驗證目標檔案內容有局部變更時，觸發增量寫入 (僅變更檔案寫入，其餘略過)。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        self.assertTrue(bool(uri and vfs.exists(PROJECT_MANIFEST_CACHE_URI)))
        manifest_data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        target_files = manifest_data.get("published_files", [])
        self.assertGreater(len(target_files), 1)

        modified_file = target_files[0]
        if modified_file.startswith("project://"):
            modified_file = uri.resolve(modified_file, interactive=False)
        with open(modified_file, "w", encoding="utf-8") as f:
            f.write("MODIFIED CONTENT")

        manifest_data["fingerprint"] = "stale_fake_fingerprint"
        vfs.write_json(PROJECT_MANIFEST_CACHE_URI, manifest_data)

        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["short_circuited"])
        self.assertEqual(res2["written_count"], 1)
        self.assertEqual(res2["skipped_count"], len(target_files) - 1)
        self.mark_passed()

    def test_forced_release_overwrites_all(self):
        """驗證傳入 force=True 時強制跳過短路與略過邏輯，執行全量覆寫。"""
        self.publisher.release_all(force=True)

        res_forced = self.publisher.release_all(force=True)
        self.assertTrue(res_forced["success"])
        self.assertFalse(res_forced["short_circuited"])
        self.assertEqual(res_forced["written_count"], res_forced["published_count"])
        self.assertEqual(res_forced["skipped_count"], 0)
        self.mark_passed()

    def test_agents_md_soft_merge_diff(self):
        """驗證 AGENTS.md 軟合併在注入內容未變更時維持文字恆等。"""
        content_a = "# Custom Header\n\n<!-- YSCB_AGENTS_BEGIN -->\nStandard Body\n<!-- YSCB_AGENTS_END -->\n\n## Custom Footer\n"

        merged_same = self.publisher._soft_merge_agents_text(content_a, "Standard Body")
        self.assertEqual(merged_same, content_a)

        merged_new = self.publisher._soft_merge_agents_text(content_a, "New Standard Body")
        self.assertNotEqual(merged_new, content_a)
        self.assertIn("New Standard Body", merged_new)
        self.assertIn("## Custom Footer", merged_new)
        self.mark_passed()

    def test_cli_release_with_force_flag_and_error_reporting(self):
        """驗證 CLI release 指令解析 --force 參數與失敗錯誤回報。"""
        out_buf = io.StringIO()
        with redirect_stdout(out_buf):
            self.assertEqual(cmd_release([]), 0)
            self.assertEqual(cmd_release([]), 0)
            self.assertEqual(cmd_release(["--force"]), 0)

        fail_buf = io.StringIO()
        with patch.object(
            ReleasePublisher,
            "release_all",
            return_value={
                "success": False,
                "error": "Stage 1 content compilation failed",
                "details": ["Missing template X"],
            },
        ), redirect_stdout(fail_buf):
            self.assertEqual(cmd_release([]), 1)
        self.assertIn("Stage 1 content compilation failed", fail_buf.getvalue())
        self.assertIn("Missing template X", fail_buf.getvalue())
        self.mark_passed()

    def test_short_circuit_invalidated_when_file_missing(self):
        """驗證已發布檔案遭刪除時，即使指紋未變仍自動失效短路並修復補齊。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        self.assertTrue(bool(uri and vfs.exists(PROJECT_MANIFEST_CACHE_URI)))
        manifest_data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        target_files = manifest_data.get("published_files", [])
        self.assertGreater(len(target_files), 0)

        deleted_file = target_files[0]
        if deleted_file.startswith("project://"):
            deleted_file = uri.resolve(deleted_file, interactive=False)
        if os.path.isfile(deleted_file):
            os.remove(deleted_file)

        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["short_circuited"])
        self.assertTrue(os.path.isfile(deleted_file))
        self.assertEqual(res2["written_count"], 1)
        self.mark_passed()

    def test_target_configuration_change_triggers_republish(self):
        """驗證不同 Target 組合計算出不同指紋，且相同輸入計算結果恆定。"""
        fp_agy_1 = self.publisher.compute_source_fingerprint(["antigravity"])
        fp_agy_2 = self.publisher.compute_source_fingerprint(["antigravity"])
        fp_claude = self.publisher.compute_source_fingerprint(["claude"])
        fp_both = self.publisher.compute_source_fingerprint(["antigravity", "claude"])

        self.assertEqual(len(fp_agy_1), 64)
        self.assertEqual(fp_agy_1, fp_agy_2)
        self.assertNotEqual(fp_agy_1, fp_claude)
        self.assertNotEqual(fp_agy_1, fp_both)
        self.assertNotEqual(fp_claude, fp_both)
        self.mark_passed()

    def test_custom_agents_md_projection(self):
        """驗證指定 Target (如 claude) 之 agents_md (project://CLAUDE.md) 正確被發布與軟合併。"""
        config.set("agents-workflow", "release_targets", ["claude"], local=True)
        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        proj_root = uri.resolve("project://", interactive=False) if uri else os.getcwd()
        claude_md = os.path.join(proj_root, "CLAUDE.md")
        self.assertTrue(os.path.isfile(claude_md))
        with open(claude_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("YSCB_AGENTS_BEGIN", content)
        self.assertIn("YSCB_AGENTS_END", content)
        self.mark_passed()

    def test_empty_agents_md_skips_output(self):
        """驗證 Target 宣告 agents_md: '' 時跳過規範檔輸出。"""
        temp_target = {
            "name": "custom_no_rules",
            "agents_md": "",
            "projections": {
                "workflow": {
                    "target_dir": "project://.custom/workflows",
                    "extension": ".md",
                }
            },
        }
        _, items = self.publisher.build_deployment_map(temp_target, [])
        self.assertEqual(len(items), 0)
        self.mark_passed()

    def test_multi_target_shared_agents_md(self):
        """驗證多 Target 共享相同 agents_md 時（如 antigravity 與 codex），軟合併冪等無衝突。"""
        config.set("agents-workflow", "release_targets", ["antigravity", "codex"], local=True)
        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        proj_root = uri.resolve("project://", interactive=False) if uri else os.getcwd()
        agents_md = os.path.join(proj_root, "AGENTS.md")
        self.assertTrue(os.path.isfile(agents_md))
        with open(agents_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content.count("<!-- YSCB_AGENTS_BEGIN -->"), 1)
        self.assertEqual(content.count("<!-- YSCB_AGENTS_END -->"), 1)
        self.mark_passed()

    def test_skill_projection_and_deployment_map(self):
        """驗證 build_deployment_map 支援 skill 類型與 rel_path 多檔案映射。"""
        mock_target = {
            "name": "antigravity",
            "projections": {
                "skill": {
                    "target_dir": "project://.agents/skills/{export.name}",
                    "extension": ".md",
                }
            },
        }
        mock_resolved = [
            {
                "export": {"type": "skill", "name": "my-skill", "source": "module://test/assets/skills/my-skill"},
                "sub_folder": "skills",
                "base_name": "SKILL.md",
                "rel_path": "SKILL.md",
                "content": "# Main Skill",
                "is_skill": True,
                "skill_name": "my-skill",
            },
            {
                "export": {"type": "skill", "name": "my-skill", "source": "module://test/assets/skills/my-skill"},
                "sub_folder": "skills",
                "base_name": "guide.md",
                "rel_path": "references/guide.md",
                "content": "# Sub Guide",
                "is_skill": True,
                "skill_name": "my-skill",
            },
        ]

        dep_map, target_items = self.publisher.build_deployment_map(mock_target, mock_resolved)
        self.assertEqual(len(target_items), 2)

        main_item = target_items[0]
        guide_item = target_items[1]

        self.assertTrue(main_item["target_abs_path"].replace("\\", "/").endswith(".agents/skills/my-skill/SKILL.md"))
        self.assertTrue(guide_item["target_abs_path"].replace("\\", "/").endswith(".agents/skills/my-skill/references/guide.md"))

        self.assertIn("skills/my-skill", dep_map)
        self.assertIn("skills/my-skill/references/guide.md", dep_map)
        self.mark_passed()

    def test_stat_first_cache_hit_and_touch_healing(self):
        """驗證 Stat-First SHA-1 快取持久化、二次查詢快取命中與 touch 變更自癒（並完整還原 mtime）。"""
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])

        if uri:
            self.assertTrue(vfs.exists(SHA1_CACHE_URI))
            cache_data = vfs.read_json(SHA1_CACHE_URI)
            self.assertIsInstance(cache_data, dict)
            self.assertGreater(len(cache_data), 0)

        res2 = self.publisher.release_all(force=False)
        self.assertTrue(res2["short_circuited"])

        manifest_p = os.path.join(self.compiler.module_root, "manifest.json")
        if os.path.isfile(manifest_p):
            stat_before = os.stat(manifest_p)
            try:
                new_mtime = stat_before.st_mtime + 5.0
                os.utime(manifest_p, (new_mtime, new_mtime))
                self.publisher._sources_digest_cache = None

                res3 = self.publisher.release_all(force=False)
                self.assertTrue(res3["success"])
                self.assertTrue(res3["short_circuited"])
                self.assertEqual(res3["fingerprint"], res1["fingerprint"])
            finally:
                os.utime(manifest_p, (stat_before.st_atime, stat_before.st_mtime))
                self.publisher._sources_digest_cache = None
                self.publisher._get_source_file_sha1(manifest_p)
                self.publisher._save_sha1_cache()
        self.mark_passed()

    def test_soft_merge_single_source_and_external_preservation(self):
        """驗證發布軟合併為單向標準覆寫（杜絕廢棄舊技能殘留），同時保留外部自定義章節。"""
        std_content = (
            "# Agent 專案行為準則與防呆紀律規範 (Agents Standards)\n\n"
            "## 2. 條件式技能分流導航矩陣\n\n"
            "| 任務情境 | 強制觸發之技能 |\n"
            "| :--- | :--- |\n"
            "| **新版系統任務 A** | `development-sop` |\n"
        )
        existing_text = (
            "<!-- YSCB_AGENTS_BEGIN -->\n"
            "# Agent 專案行為準則與防呆紀律規範 (Agents Standards)\n\n"
            "## 2. 條件式技能分流導航矩陣\n\n"
            "| 任務情境 | 強制觸發之技能 |\n"
            "| :--- | :--- |\n"
            "| **已優化廢棄之舊系統任務** | `legacy-skill` |\n"
            "<!-- YSCB_AGENTS_END -->\n\n"
            "## 4. 專案特化工程規範\n"
            "- 自訂外部規範附錄\n"
        )
        merged_1 = self.publisher._soft_merge_agents_text(existing_text, std_content)
        self.assertIn("**新版系統任務 A**", merged_1)
        self.assertNotIn("`legacy-skill`", merged_1)
        self.assertIn("## 4. 專案特化工程規範", merged_1)
        self.assertIn("- 自訂外部規範附錄", merged_1)

        merged_2 = self.publisher._soft_merge_agents_text(merged_1, std_content)
        self.assertEqual(merged_1, merged_2)
        self.mark_passed()

    def test_contextinit_workflow_relative_links(self):
        """驗證 ContextInit 編譯後鏈接解析為相對於目前檔案之相對路徑而非 project_root 裸路徑。"""
        config.set("agents-workflow", "paths.docs", "project://docs", local=False)
        res1 = self.compiler.compile_stage1()
        self.assertTrue(res1.get("success", False))

        context_init_item = None
        for item in res1.get("resolved_items", []):
            if item.get("skill_name") == "context-init" or "context-init" in item.get("export", {}).get("name", ""):
                context_init_item = item
                break
        self.assertIsNotNone(context_init_item)

        dummy_dest = os.path.join(os.getcwd(), ".agents", "skills", "context-init", "SKILL.md")
        cur_dir = os.path.dirname(dummy_dest)
        dep_map = {}
        stage2_text = self.compiler.resolve_stage2_uri(context_init_item["content"], dummy_dest, dep_map)

        if uri:
            expected_agents = os.path.relpath(uri.resolve("project://AGENTS.md", interactive=False), cur_dir).replace("\\", "/")
            expected_changelog = os.path.relpath(uri.resolve("project://CHANGELOG.md", interactive=False), cur_dir).replace("\\", "/")
            expected_standards = os.path.relpath(uri.resolve("workflow.docs://_project/STANDARDS.md", interactive=False), cur_dir).replace("\\", "/")

            self.assertIn(f"[`AGENTS.md`]({expected_agents})", stage2_text)
            self.assertIn(f"[`CHANGELOG.md`]({expected_changelog})", stage2_text)
            self.assertIn(f"[`STANDARDS.md`]({expected_standards})", stage2_text)

        self.assertNotIn("__#{project://AGENTS.md}__", stage2_text)
        self.assertNotIn("__${project://AGENTS.md}__", stage2_text)
        self.mark_passed()

    def test_soft_unmerge_agents_text(self):
        """驗證 _soft_unmerge_agents_text 正確剝離 YSCB 託管標記與空樣板，完整保留自訂內容。"""
        self.assertEqual(self.publisher._soft_unmerge_agents_text(""), "")

        default_tpl = (
            f"{AGENTS_MD_BEGIN}\n"
            f"# Agent 專案行為準則\n"
            f"{AGENTS_MD_END}\n\n"
            f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
            f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
        )
        self.assertEqual(self.publisher._soft_unmerge_agents_text(default_tpl), "")

        custom_tpl = (
            f"{AGENTS_MD_BEGIN}\n"
            f"# Agent 專案行為準則\n"
            f"{AGENTS_MD_END}\n\n"
            f"## 4. 專案特化工程規範 (Project Specific Standards)\n"
            f"*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n\n"
            f"- 專案自訂規則 1：全庫禁止使用未受保護之裸 SQL\n"
        )
        unmerged = self.publisher._soft_unmerge_agents_text(custom_tpl)
        self.assertNotIn(AGENTS_MD_BEGIN, unmerged)
        self.assertNotIn(AGENTS_MD_END, unmerged)
        self.assertIn("專案自訂規則 1", unmerged)
        self.assertIn("## 4. 專案特化工程規範", unmerged)

        pre_custom = (
            f"# My Company Guidelines\n\n"
            f"{AGENTS_MD_BEGIN}\n# Core Rules\n{AGENTS_MD_END}\n"
        )
        unmerged_pre = self.publisher._soft_unmerge_agents_text(pre_custom)
        self.assertEqual(unmerged_pre, "# My Company Guidelines")
        self.mark_passed()

    def test_prune_stale_agents_md(self):
        """整合驗證切換 Target 移除 antigravity 時，AGENTS.md 之軟剝離保護與純淨清理。"""
        proj_root = uri.resolve("project://", interactive=False) if uri else os.getcwd()
        agents_md_path = os.path.join(proj_root, "AGENTS.md")

        config.set("agents-workflow", "release_targets", ["antigravity"], local=False)
        config.delete("agents-workflow", "release_targets", local=True)
        config.reload()
        res1 = self.publisher.release_all(force=True)
        self.assertTrue(res1["success"])
        self.assertTrue(os.path.isfile(agents_md_path))

        with open(agents_md_path, "a", encoding="utf-8") as f:
            f.write("\n## 5. 使用者自訂重要守則\n- 嚴禁更動生產資料庫連線\n")

        config.set("agents-workflow", "release_targets", ["claude"], local=False)
        config.reload()
        res2 = self.publisher.release_all(force=True)
        self.assertTrue(res2["success"])

        self.assertTrue(os.path.isfile(agents_md_path))
        with open(agents_md_path, "r", encoding="utf-8") as f:
            saved_text = f.read()
        self.assertNotIn("<!-- YSCB_AGENTS_BEGIN -->", saved_text)
        self.assertIn("使用者自訂重要守則", saved_text)
        self.assertIn("嚴禁更動生產資料庫連線", saved_text)

        config.set("agents-workflow", "release_targets", ["antigravity"], local=False)
        config.reload()
        res3 = self.publisher.release_all(force=True)
        self.assertTrue(res3["success"])

        default_content = (
            "<!-- YSCB_AGENTS_BEGIN -->\n"
            "# Agent 專案行為準則\n"
            "<!-- YSCB_AGENTS_END -->\n\n"
            "## 4. 專案特化工程規範 (Project Specific Standards)\n"
            "*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*\n"
        )
        with open(agents_md_path, "w", encoding="utf-8") as f:
            f.write(default_content)

        config.set("agents-workflow", "release_targets", ["claude"], local=False)
        config.reload()
        res4 = self.publisher.release_all(force=True)
        self.assertTrue(res4["success"])
        self.assertFalse(os.path.isfile(agents_md_path))
        self.mark_passed()

    def test_empty_project_targets_no_default_revival_and_orphan_warning(self):
        """驗證清空最後一個專案 Target [] 時不復活預設 antigravity，以及孤兒 Target 警告與 Stage 1 失敗處理。"""
        config.set("agents-workflow", "release_targets", [], local=False)
        config.set("agents-workflow", "release_targets", ["claude"], local=True)
        config.reload()

        cfg_claude_only = self.publisher._get_project_config()
        self.assertNotIn("antigravity", cfg_claude_only.get("release_targets", []))
        self.assertEqual(cfg_claude_only.get("release_targets"), ["claude"])

        config.set("agents-workflow", "release_targets", [], local=True)
        config.reload()
        cfg_all_empty = self.publisher._get_project_config()
        self.assertEqual(cfg_all_empty.get("release_targets"), [])

        # 驗證孤兒 Target 警告與回傳
        err_buf = io.StringIO()
        with patch.object(
            self.publisher,
            "_get_project_config",
            return_value={"release_targets": ["antigravity", "non_existent_orphan_target"]},
        ), redirect_stderr(err_buf):
            res_orphan = self.publisher.release_all(force=True)
        self.assertTrue(res_orphan["success"])
        self.assertIn("non_existent_orphan_target", res_orphan["orphan_targets"])
        self.assertIn("[publisher:warning] Release target 'non_existent_orphan_target' not found", err_buf.getvalue())

        # 驗證 Stage 1 失敗時 release_all 早退回傳失敗結構
        with patch.object(
            self.compiler,
            "compile_stage1",
            return_value={"success": False, "errors": ["stage1 broken"]},
        ):
            res_fail = self.publisher.release_all(force=True)
        self.assertFalse(res_fail["success"])
        self.assertEqual(res_fail["error"], "Stage 1 content compilation failed")
        self.assertEqual(res_fail["details"], ["stage1 broken"])
        self.mark_passed()


@require(Requirement.LOGIC | Requirement.ENV)
class TestJITReleaseAndHooks(YSCBTestCase):
    """測試 JIT 雜湊偵測、hook.core.py 與 hook.dev.py 生命週期掛鉤。"""

    def setUp(self):
        super().setUp()
        try:
            from core.context import invalidate_epoch_state
            invalidate_epoch_state("agents_workflow.publisher.jit_clean_bucket")
        except Exception:
            pass

    def test_ensure_jit_release_clean(self):
        """驗證當來源特徵未改變 (Clean) 時，ensure_jit_release 順暢返回 False。"""
        with patch.object(ReleasePublisher, "release_all", return_value={"success": True, "short_circuited": True, "written_count": 0}):
            result = ensure_jit_release()
            self.assertFalse(result)
            self.mark_passed()

    def test_ensure_jit_release_dirty_triggers_materialize(self):
        """驗證當指紋不一致時，ensure_jit_release 觸發 release 並返回 True。"""
        with patch.object(ReleasePublisher, "release_all", return_value={"success": True, "short_circuited": False, "written_count": 3}):
            result = ensure_jit_release()
            self.assertTrue(result)
            self.mark_passed()

    def test_ensure_jit_release_exception_safety(self):
        """驗證當 release 過程遭遇任何異常時，ensure_jit_release 安全捕獲返回 False。"""
        with patch.object(ReleasePublisher, "release_all", side_effect=PermissionError("File locked")):
            result = ensure_jit_release()
            self.assertFalse(result)
            self.mark_passed()

    def test_hook_core_and_hook_dev_lifecycle(self):
        """驗證 hook.core.py (on_reload / on_pre_cli_dispatch) 與 hook.dev.py (on_test_setup / on_test_teardown) 完整分支。"""
        hook_core = load_hook_core_module("aw_hook_core_pub")
        hook_dev = load_hook_dev_module("aw_hook_dev_pub")

        out_buf = io.StringIO()
        err_reload_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_reload_buf):
            with patch("agents_workflow.publisher.ReleasePublisher.release_all") as mock_rel:
                mock_rel.return_value = {
                    "success": True,
                    "short_circuited": False,
                    "written_count": 5,
                    "skipped_count": 10,
                    "removed_count": 1,
                    "active_targets": ["antigravity"],
                }
                hook_core.on_reload(None)
                mock_rel.assert_called_once_with(force=False)

                mock_rel.return_value = {
                    "success": True,
                    "short_circuited": True,
                    "skipped_count": 15,
                }
                hook_core.on_reload(None)

                mock_rel.return_value = {
                    "success": False,
                    "error": "mock reload fail",
                }
                hook_core.on_reload(None)

                mock_rel.side_effect = RuntimeError("unexpected crash")
                hook_core.on_reload(None)

        out_text = out_buf.getvalue()
        err_reload_text = err_reload_buf.getvalue()
        self.assertIn("Auto-released on reload", out_text)
        self.assertIn("Auto-release skipped on reload", out_text)
        self.assertIn("Auto-release failed on reload: mock reload fail", err_reload_text)
        self.assertIn("Auto-release on reload failed: unexpected crash", err_reload_text)

        with patch("agents_workflow.publisher.ensure_jit_release", return_value=True):
            self.assertTrue(hook_core.on_pre_cli_dispatch())

        with patch("agents_workflow.publisher.ensure_jit_release", return_value=False):
            self.assertFalse(hook_core.on_pre_cli_dispatch())

        err_buf = io.StringIO()
        with patch("agents_workflow.publisher.ensure_jit_release", side_effect=RuntimeError("jit fail")), redirect_stderr(err_buf):
            self.assertFalse(hook_core.on_pre_cli_dispatch())
        self.assertIn("Warning: Failed during on_pre_cli_dispatch", err_buf.getvalue())

        registered: dict = {}

        class _DummySpaceReg:
            def register_space(self, name: str, cfg: dict) -> None:
                registered[name] = cfg

        self.assertFalse(hook_core.on_register_file_spaces(None))
        with patch.object(ReleasePublisher, "collect_gitignore_patterns", return_value=["/.agents/.yscb/"]):
            self.assertTrue(hook_core.on_register_file_spaces({"registry": _DummySpaceReg()}))
        self.assertIn("agents-workflow/gitignore", registered)
        self.assertEqual(registered["agents-workflow/gitignore"]["include"], ["/.agents/.yscb/"])
        self.assertFalse(registered["agents-workflow/gitignore"]["watch"])

        self.assertIsNone(hook_dev.on_test_setup({"sandbox": "mock"}))
        self.assertIsNone(hook_dev.on_test_teardown({"sandbox": "mock"}))
        self.mark_passed()


@require(Requirement.LOGIC | Requirement.ENV)
class TestManifestPlacementAndDualTrack(YSCBTestCase):
    """測試發布清單分流 (storage.local://)、雙軌 gitignore 同步與換行符號 LF 歸一化。"""

    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)

    def tearDown(self):
        self._snapshot.restore()
        super().tearDown()

    def test_project_target_saves_project_uris_in_cache(self):
        """驗證 Project Target 清單寫入 storage.local://，且全部路徑為 project:// 語意格式。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertGreater(res["published_count"], 0)

        self.assertTrue(vfs.exists(PROJECT_MANIFEST_CACHE_URI))
        data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        self.assertEqual(data.get("active_targets"), ["antigravity"])
        published = data.get("published_files", [])
        self.assertGreater(len(published), 0)

        for p in published:
            self.assertTrue(
                p.startswith("project://"),
                f"Expected path in project manifest to start with 'project://', got: '{p}'",
            )
            self.assertNotIn(":", p.replace("project://", ""))
            self.assertNotIn("\\", p)
        self.mark_passed()

    def test_local_target_saves_absolute_paths_in_cache(self):
        """驗證 Local Target 發布至 storage.local://，且全部路徑統一為 project:// 語意格式以確保跨環境可攜性。"""
        ReleaseTargetManager.save_tier_targets([], is_project=True)
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertGreater(res["published_count"], 0)

        self.assertTrue(vfs.exists(LOCAL_MANIFEST_CACHE_URI))
        data = vfs.read_json(LOCAL_MANIFEST_CACHE_URI)
        self.assertEqual(data.get("active_targets"), ["antigravity"])
        published = data.get("published_files", [])
        self.assertGreater(len(published), 0)

        for p in published:
            self.assertTrue(
                p.startswith("project://"),
                f"Expected path in local manifest to start with 'project://', got: '{p}'",
            )
            self.assertNotIn("\\", p)
        self.mark_passed()

    def test_mixed_targets_dual_channel_manifests_and_gitignore_union(self):
        """驗證混合 Targets (Local + Project) 同步獨立更新各自 Manifest，且 sync_gitignore 合併讀取雙軌清冊。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets(["claude"], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        self.assertTrue(vfs.exists(PROJECT_MANIFEST_CACHE_URI))
        proj_data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        self.assertEqual(proj_data.get("active_targets"), ["antigravity"])
        for p in proj_data.get("published_files", []):
            self.assertTrue(p.startswith("project://"))

        self.assertTrue(vfs.exists(LOCAL_MANIFEST_CACHE_URI))
        local_data = vfs.read_json(LOCAL_MANIFEST_CACHE_URI)
        self.assertEqual(local_data.get("active_targets"), ["claude"])

        # 驗證 published_files=None 時 sync_gitignore 能夠合併讀取雙軌 Manifest
        gi_res = self.publisher.sync_gitignore(active_targets=["antigravity", "claude"], published_files=None)
        patterns = gi_res.get("patterns", [])
        self.assertTrue(any(p.startswith("/.agents/") for p in patterns))
        self.assertTrue(any(p.startswith("/.claude/") for p in patterns))
        self.mark_passed()

    def test_legacy_absolute_path_manifest_tolerance(self):
        """驗證歷史異機絕對路徑 (如 H:\\...) 讀取時不崩潰，安全自癒標準化。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        fake_legacy = {
            "fingerprint": "fake_legacy_fp",
            "active_targets": ["antigravity"],
            "published_files": [
                "H:\\UseFolder\\NonExistent\\legacy_file_01.md",
                "H:\\UseFolder\\NonExistent\\legacy_file_02.md",
            ],
            "updated_at": "2026-08-01 00:00:00",
        }
        vfs.write_json(PROJECT_MANIFEST_CACHE_URI, fake_legacy)

        res = self.publisher.release_all(force=False)
        self.assertTrue(res["success"])

        new_data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        for p in new_data.get("published_files", []):
            self.assertTrue(p.startswith("project://"))
        self.mark_passed()

    def test_line_endings_are_pure_lf(self):
        """驗證發布物化產物之換行符號 100% 為純 LF (\\n)，無 CRLF (\\r\\n)。"""
        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])

        data = vfs.read_json(PROJECT_MANIFEST_CACHE_URI)
        for p_uri in data.get("published_files", []):
            abs_p = uri.resolve(p_uri, interactive=False)
            if os.path.isfile(abs_p):
                with open(abs_p, "rb") as bf:
                    raw_bytes = bf.read()
                self.assertNotIn(
                    b"\r\n",
                    raw_bytes,
                    f"File '{abs_p}' contains CRLF (\\r\\n) but expected pure LF (\\n).",
                )
        self.mark_passed()


@require(Requirement.LOGIC | Requirement.ENV)
class TestPublisherCrossPlatform(YSCBTestCase):
    """測試發布引擎之跨平台換行符正規化、遷移腳本與清單隔離。"""

    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_cross_")

    def tearDown(self):
        self._snapshot.restore()
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_sha1_crlf_normalization(self):
        """驗證 CRLF 與 LF 文字內容計算出完全相同的 SHA-1 雜湊值。"""
        dir_lf = os.path.join(self.temp_dir, "dir_lf")
        dir_crlf = os.path.join(self.temp_dir, "dir_crlf")
        os.makedirs(dir_lf, exist_ok=True)
        os.makedirs(dir_crlf, exist_ok=True)

        with open(os.path.join(dir_lf, "sample.md"), "wb") as f:
            f.write(b"# Title\nLine 1\nLine 2\n")

        with open(os.path.join(dir_crlf, "sample.md"), "wb") as f:
            f.write(b"# Title\r\nLine 1\r\nLine 2\r\n")

        sha1_lf = self.publisher._get_source_file_sha1(dir_lf)
        sha1_crlf = self.publisher._get_source_file_sha1(dir_crlf)
        self.assertEqual(sha1_lf, sha1_crlf)

        single_lf = os.path.join(self.temp_dir, "single_lf.txt")
        single_crlf = os.path.join(self.temp_dir, "single_crlf.txt")
        with open(single_lf, "wb") as f:
            f.write(b"Hello\nWorld\n")
        with open(single_crlf, "wb") as f:
            f.write(b"Hello\r\nWorld\r\n")

        single_sha1_lf = self.publisher._get_source_file_sha1(single_lf)
        single_sha1_crlf = self.publisher._get_source_file_sha1(single_crlf)
        self.assertEqual(single_sha1_lf, single_sha1_crlf)
        self.mark_passed()

    def test_binary_file_sha1_fallback(self):
        """驗證非 UTF-8 二進位檔案安全降級至 raw bytes，不崩潰。"""
        bin_dir = os.path.join(self.temp_dir, "bin_dir")
        os.makedirs(bin_dir, exist_ok=True)

        raw_binary = b"\x80\xff\xfe\x00\x01\x02\r\n\x88\x99"
        bin_file = os.path.join(bin_dir, "data.bin")
        with open(bin_file, "wb") as f:
            f.write(raw_binary)

        sha1_val = self.publisher._get_source_file_sha1(bin_dir)
        self.assertEqual(len(sha1_val), 40)
        self.mark_passed()

    def test_release_never_writes_tracked_storage(self):
        """驗證完整發布後，Git 追蹤區 storage://agents-workflow/release_manifest.json 不被寫入，清單僅存於 storage.local://。"""
        legacy_storage_uri = "storage://agents-workflow/release_manifest.json"
        if vfs and vfs.exists(legacy_storage_uri):
            vfs.remove(legacy_storage_uri)

        ReleaseTargetManager.save_tier_targets(["antigravity"], is_project=True)
        ReleaseTargetManager.save_tier_targets([], is_project=False)

        res = self.publisher.release_all(force=True)
        self.assertTrue(res["success"])
        self.assertFalse(bool(vfs and vfs.exists(legacy_storage_uri)))
        self.assertTrue(bool(vfs and vfs.exists(PROJECT_MANIFEST_CACHE_URI)))

        self.publisher.release_all(force=False)
        self.assertFalse(bool(vfs and vfs.exists(legacy_storage_uri)))
        self.mark_passed()

    def test_migration_1_2_4_x_moves_legacy_storage_and_cache_manifests(self):
        """驗證 scripts/migrations/1.2.4.x.py 之 migrate(context) 能無損將舊 storage:// 及 cache:// 清冊遷移至 storage.local:// 並涵蓋邊界情境。"""
        mig_mod = load_migration_module("1.2.4.x", "aw_mig_1_2_4_x")

        yscb_dir = os.path.join(self.temp_dir, "ys_codebase")
        storage_dir = os.path.join(yscb_dir, "storage", "agents-workflow")
        storage_local_dir = os.path.join(yscb_dir, ".storage.local", "agents-workflow")
        cache_dir = os.path.join(yscb_dir, ".cache", "agents-workflow")
        os.makedirs(storage_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        legacy_storage_file = os.path.join(storage_dir, "release_manifest.json")
        with open(legacy_storage_file, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": "fp_legacy", "files": ["project://AGENTS.md"]}, f)

        with open(os.path.join(cache_dir, "release_manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": "fp_local", "published_files": ["/abs/CLAUDE.md"]}, f)
        with open(os.path.join(cache_dir, "source_sha1_cache.json"), "w", encoding="utf-8") as f:
            json.dump({"sample.md": [1, 10, "abc"]}, f)

        ctx = {
            "yscb_dir": yscb_dir,
            "storage_dir": storage_dir,
            "storage_local_dir": storage_local_dir,
        }
        self.assertTrue(mig_mod.migrate(ctx))

        self.assertFalse(os.path.exists(legacy_storage_file))
        self.assertFalse(os.path.exists(storage_dir))
        self.assertFalse(os.path.exists(os.path.join(cache_dir, "release_manifest.json")))
        self.assertFalse(os.path.exists(os.path.join(cache_dir, "source_sha1_cache.json")))

        proj_m_path = os.path.join(storage_local_dir, "project_release_manifest.json")
        local_m_path = os.path.join(storage_local_dir, "release_manifest.json")
        sha1_m_path = os.path.join(storage_local_dir, "source_sha1_cache.json")
        self.assertTrue(os.path.isfile(proj_m_path))
        self.assertTrue(os.path.isfile(local_m_path))
        self.assertTrue(os.path.isfile(sha1_m_path))

        with open(proj_m_path, "r", encoding="utf-8") as f:
            proj_m = json.load(f)
        self.assertEqual(proj_m.get("published_files"), ["project://AGENTS.md"])
        self.assertEqual(proj_m.get("fingerprint"), "fp_legacy")

        # 邊界 2: 當 target_proj_manifest 已存在時，遺留之 legacy_storage_manifest 被直接移除且不覆寫現有檔
        os.makedirs(storage_dir, exist_ok=True)
        with open(legacy_storage_file, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": "should_be_discarded", "files": []}, f)
        self.assertTrue(mig_mod.migrate(ctx))
        self.assertFalse(os.path.exists(legacy_storage_file))
        with open(proj_m_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("fingerprint"), "fp_legacy")

        # 邊界 3: 損毀之 legacy_storage_manifest 降級搬移與 cache:// project_release_manifest.json 遷移
        os.remove(proj_m_path)
        os.makedirs(storage_dir, exist_ok=True)
        with open(legacy_storage_file, "w", encoding="utf-8") as f:
            f.write("{corrupted_json")
        self.assertTrue(mig_mod.migrate(ctx))
        self.assertTrue(os.path.isfile(proj_m_path))
        os.remove(proj_m_path)

        with open(os.path.join(cache_dir, "project_release_manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": "fp_cache_proj", "published_files": ["project://.agents/skills/auto/SKILL.md"]}, f)

        self.assertTrue(mig_mod.migrate(ctx))
        self.assertFalse(os.path.exists(os.path.join(cache_dir, "project_release_manifest.json")))
        with open(proj_m_path, "r", encoding="utf-8") as f:
            proj_m2 = json.load(f)
        self.assertEqual(proj_m2.get("fingerprint"), "fp_cache_proj")

        # 邊界 4: 無 yscb_dir 且 uri.resolve_yscb_root 拋出異常時安全返回 True
        with patch("core.uri.resolve_yscb_root", side_effect=RuntimeError("no root")), patch(
            "core.uri.resolve", side_effect=RuntimeError("no uri")
        ):
            self.assertTrue(mig_mod.migrate({}))
        self.mark_passed()

    def test_prune_removes_legacy_workflows_and_commands_dirs(self):
        """驗證原子發布清理時自動偵測並物理移除遺留的 .agents/workflows/ 與 .claude/commands/ 目錄。"""
        proj_dir = os.path.join(self.temp_dir, "legacy_prune_proj")
        legacy_wf_dir = os.path.join(proj_dir, ".agents", "workflows")
        legacy_cmd_dir = os.path.join(proj_dir, ".claude", "commands")
        active_skill_dir = os.path.join(proj_dir, ".agents", "skills", "auto")
        os.makedirs(legacy_wf_dir, exist_ok=True)
        os.makedirs(legacy_cmd_dir, exist_ok=True)
        os.makedirs(active_skill_dir, exist_ok=True)

        old_wf_file = os.path.join(legacy_wf_dir, "old.md")
        old_cmd_file = os.path.join(legacy_cmd_dir, "old_cmd.md")
        active_skill_file = os.path.join(active_skill_dir, "SKILL.md")
        for fp in (old_wf_file, old_cmd_file, active_skill_file):
            with open(fp, "w", encoding="utf-8") as f:
                f.write("# doc\n")

        removed = self.publisher._prune_orphaned_managed_files(
            old_proj_manifest={"published_files": []},
            old_local_manifest={"published_files": []},
            current_published_set={active_skill_file},
            all_registered_targets={},
            proj_root=proj_dir,
        )
        self.assertFalse(os.path.exists(legacy_wf_dir))
        self.assertFalse(os.path.exists(legacy_cmd_dir))
        self.assertTrue(os.path.isfile(active_skill_file))
        self.assertGreaterEqual(len(removed), 2)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
