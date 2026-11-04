"""
Unit and boundary tests for `core.gitignore` unified ignore rules engine.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import core
from core import gitignore, vfs
from core.commands.bags import CmdBags, CmdOption
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreGitignore(YSCBTestCase):
    """驗證 `core.gitignore` 單一根目錄 `.gitignore` 收斂引擎、`# [<module>]` 分組、語意 URI 轉換與生命週期清理。"""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_core_gitignore_")
        self.proj_root = os.path.join(self.temp_dir, "workspace")
        self.yscb_root = os.path.join(self.proj_root, "ys_codebase")
        os.makedirs(self.proj_root, exist_ok=True)
        os.makedirs(self.yscb_root, exist_ok=True)

    def tearDown(self) -> None:
        gitignore._CUSTOM_ROOT_DYNAMIC_STORE.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_ft_01_subdir_and_same_root_semantic_uri_resolution(self) -> None:
        """驗證子目錄拓撲 (`ys_codebase/`) 與同根拓撲 (`yscb:// == project://`) 之語意 URI 路徑錨定轉換。"""
        # 1. 子目錄拓撲 (project:// = workspace, yscb:// = workspace/ys_codebase)
        p_venv = gitignore.normalize_pattern("yscb://.venv/", self.proj_root, self.yscb_root)
        p_vsc = gitignore.normalize_pattern("project://.vscode/schemas/", self.proj_root, self.yscb_root)
        p_glob = gitignore.normalize_pattern("*.local.json", self.proj_root, self.yscb_root)
        self.assertEqual(p_venv, "/ys_codebase/.venv/")
        self.assertEqual(p_vsc, "/.vscode/schemas/")
        self.assertEqual(p_glob, "*.local.json")

        # 2. 同根拓撲 (yscb:// == project://)
        same_venv = gitignore.normalize_pattern("yscb://.venv/", self.proj_root, self.proj_root)
        self.assertEqual(same_venv, "/.venv/")

        # 3. 否定規則與越界路徑過濾
        neg_rule = gitignore.normalize_pattern("!project://configurable/*.local.json", self.proj_root, self.yscb_root)
        self.assertEqual(neg_rule, "!/configurable/*.local.json")
        outside_dir = os.path.join(self.temp_dir, "outside")
        self.assertIsNone(gitignore.normalize_pattern("yscb://secret/", self.proj_root, outside_dir))
        self.mark_passed()

    def test_ft_02_grouped_managed_block_and_static_dynamic_merge(self) -> None:
        """驗證靜態 contributes (`vscode-support`, `project`) 與動態 SDK (`agents-workflow`) 按 `# [<module>]` 分組合成。"""
        vsc_contrib_dir = os.path.join(self.yscb_root, ".modules", "vscode-support", "contributes")
        os.makedirs(vsc_contrib_dir, exist_ok=True)
        vfs.write_json(
            os.path.join(vsc_contrib_dir, "core.json"),
            {"gitignore": ["project://.vscode/schemas/"]},
        )

        proj_contrib_dir = os.path.join(self.yscb_root, "config", "core")
        os.makedirs(proj_contrib_dir, exist_ok=True)
        vfs.write_json(
            os.path.join(proj_contrib_dir, "contribute.json"),
            {"gitignore": ["project://datasets/large_raw/"]},
        )

        res = gitignore.register_dynamic(
            "agents-workflow",
            ["/.agents/skills/auto/SKILL.md", "/.agents/.yscb/templates/P00_discuss.md"],
            sync_now=True,
            proj_root=self.proj_root,
            yscb_root=self.yscb_root,
        )
        self.assertTrue(res["created"])
        self.assertTrue(res["updated"])

        gi_path = os.path.join(self.proj_root, ".gitignore")
        content = vfs.read_text(gi_path)
        self.assertIn(gitignore.GITIGNORE_BEGIN_MARKER, content)
        self.assertIn(gitignore.GITIGNORE_END_MARKER, content)
        self.assertIn("# [core]\n/ys_codebase/.modules/", content)
        self.assertIn("# [agents-workflow]\n/.agents/.yscb/templates/P00_discuss.md", content)
        self.assertIn("# [vscode-support]\n/.vscode/schemas/", content)
        self.assertIn("# [project]\n/datasets/large_raw/", content)

        # 順序驗證：core 置頂，agents-workflow 與 vscode-support 字母序，project 置底
        idx_core = content.index("# [core]")
        idx_aw = content.index("# [agents-workflow]")
        idx_vsc = content.index("# [vscode-support]")
        idx_proj = content.index("# [project]")
        self.assertTrue(idx_core < idx_aw < idx_vsc < idx_proj)

        # Zero-Touch 冪等性驗證：再次 sync 時不重寫磁碟 (updated=False)
        mtime_before = os.stat(gi_path).st_mtime_ns
        res_idempotent = gitignore.sync(proj_root=self.proj_root, yscb_root=self.yscb_root)
        self.assertFalse(res_idempotent["updated"])
        self.assertEqual(os.stat(gi_path).st_mtime_ns, mtime_before)

        # clear_dynamic 移除後，該模組分組自動從託管區塊消失
        res_clear = gitignore.clear_dynamic(
            "agents-workflow",
            sync_now=True,
            proj_root=self.proj_root,
            yscb_root=self.yscb_root,
        )
        self.assertTrue(res_clear["updated"])
        self.assertTrue(res_clear["had_dynamic_entries"])
        content_after = vfs.read_text(gi_path)
        self.assertNotIn("# [agents-workflow]", content_after)
        self.assertIn("# [vscode-support]", content_after)
        self.mark_passed()

    def test_ft_03_legacy_migration_and_obsolete_nested_gitignore_cleanup(self) -> None:
        """驗證舊版區塊無縫遷移、保留使用者自訂規則，以及安全清理廢棄之子目錄 `.gitignore`。"""
        gi_path = os.path.join(self.proj_root, ".gitignore")
        legacy_root_content = (
            "# YS-Codebase Autonomous Internal Ignore Rules\n"
            "/.modules/\n"
            "/.venv/\n"
            "ys_codebase/release/**/*.zip\n"
            "!**/configurable/*.local.json\n\n"
            "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===\n"
            "/.agents/skills/old/SKILL.md\n"
            "# === YSCB AGENTS_WORKFLOW IGNORE END ===\n"
        )
        vfs.write_text(gi_path, legacy_root_content)

        # 建立純舊版託管的 ys_codebase/.gitignore 與 .vscode/schemas/.gitignore
        yscb_gi = os.path.join(self.yscb_root, ".gitignore")
        vfs.write_text(
            yscb_gi,
            "# === YSCB INTERNAL IGNORE BEGIN ===\n/.venv/\n# === YSCB INTERNAL IGNORE END ===\n",
        )
        schemas_dir = os.path.join(self.proj_root, ".vscode", "schemas")
        os.makedirs(schemas_dir, exist_ok=True)
        schemas_gi = os.path.join(schemas_dir, ".gitignore")
        vfs.write_text(schemas_gi, "*\n")

        res = gitignore.sync(proj_root=self.proj_root, yscb_root=self.yscb_root)
        self.assertTrue(res["updated"])
        self.assertFalse(os.path.exists(yscb_gi))
        self.assertFalse(os.path.exists(schemas_gi))

        migrated = vfs.read_text(gi_path)
        self.assertIn("ys_codebase/release/**/*.zip", migrated)
        self.assertIn("!**/configurable/*.local.json", migrated)
        self.assertNotIn(gitignore.LEGACY_AW_BEGIN, migrated)
        self.assertNotIn("# YS-Codebase Autonomous Internal Ignore Rules", migrated)
        self.assertIn(gitignore.GITIGNORE_BEGIN_MARKER, migrated)
        self.assertIn("/ys_codebase/.venv/", migrated)

        # 若 ys_codebase/.gitignore 含有使用者手寫之非託管規則，僅剝除託管區塊而不刪除該檔案
        vfs.write_text(
            yscb_gi,
            "# Custom nested rule\nmy_custom_sub_ignore.dat\n"
            "# === YSCB INTERNAL IGNORE BEGIN ===\n/.venv/\n# === YSCB INTERNAL IGNORE END ===\n",
        )
        gitignore.sync(proj_root=self.proj_root, yscb_root=self.yscb_root)
        self.assertTrue(os.path.isfile(yscb_gi))
        yscb_gi_text = vfs.read_text(yscb_gi)
        self.assertIn("my_custom_sub_ignore.dat", yscb_gi_text)
        self.assertNotIn(gitignore.LEGACY_INTERNAL_BEGIN, yscb_gi_text)
        self.mark_passed()

    def test_et_01_sdk_mandatory_module_validation_and_cli_commands(self) -> None:
        """驗證 SDK 強制檢查非空 `module` 參數（負向測試），以及 CLI `gitignore status/sync` 行為。"""
        for bad_mod in ("", "   ", None):
            with self.assertRaises(ValueError):
                gitignore.register_dynamic(bad_mod, ["*.tmp"])  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                gitignore.clear_dynamic(bad_mod)  # type: ignore[arg-type]

        # 驗證 core.gitignore 已於 core.__all__ 公開匯出
        self.assertIn("gitignore", core.__all__)
        self.assertIs(core.gitignore, gitignore)

        # 驗證 CLI status / sync (含 --json 與未知子命令負向攔截)
        import importlib.util

        cli_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "cli.py")
        spec = importlib.util.spec_from_file_location("_test_core_gi_cli", cli_path)
        self.assertIsNotNone(spec)
        cli_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(cli_mod)  # type: ignore[union-attr]

        buf_sync = io.StringIO()
        with redirect_stdout(buf_sync):
            rc_sync = cli_mod.gitignore(
                CmdBags(
                    raw_cmd="gitignore sync --json",
                    command="gitignore",
                    args=["sync"],
                    options={"json": CmdOption(name="json", params=True)},
                )
            )
        self.assertEqual(rc_sync, 0)
        sync_data = json.loads(buf_sync.getvalue())
        self.assertIn("groups", sync_data)
        self.assertIn("core", sync_data["groups"])

        buf_status = io.StringIO()
        with redirect_stdout(buf_status):
            rc_status = cli_mod.gitignore(
                CmdBags(
                    raw_cmd="gitignore status --json",
                    command="gitignore",
                    args=["status"],
                    options={"json": CmdOption(name="json", params=True)},
                )
            )
        self.assertEqual(rc_status, 0)
        status_data = json.loads(buf_status.getvalue())
        self.assertTrue(status_data["exists"])
        self.assertTrue(status_data["has_managed_block"])
        self.assertTrue(status_data["in_sync"])

        # 未知子命令應回傳 1
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc_bad = cli_mod.gitignore(
                CmdBags(
                    raw_cmd="gitignore invalid-sub",
                    command="gitignore",
                    args=["invalid-sub"],
                    options={},
                )
            )
        self.assertEqual(rc_bad, 1)
        self.assertIn("Unknown subcommand", err_buf.getvalue())
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

