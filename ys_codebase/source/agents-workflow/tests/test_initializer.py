"""
Unit and Integration Tests for agents-workflow WorkflowInitializer and init CLI.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if getattr(sys.modules.get("tests"), "PKG_ROOT", None) != Path(__file__).resolve().parent.parent:
    sys.modules.pop("tests", None)

from tests import PKG_ROOT, ConfigStateSnapshot, load_cli_module

cli = load_cli_module("aw_cli_init_test")

from agents_workflow.initializer import WorkflowInitializer
from core import config
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.LOGIC | Requirement.ENV)
class TestWorkflowInitializer(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self._snapshot = ConfigStateSnapshot()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_init_")
        self.initializer = WorkflowInitializer(host_dir=self.temp_dir)

    def tearDown(self):
        self._snapshot.restore()
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_manifest_and_template_structure(self):
        """驗證 contributes/core.json 宣告 URI 協議與 config 模板欄位結構。"""
        contrib_path = os.path.join(PKG_ROOT, "contributes", "core.json")
        self.assertTrue(os.path.isfile(contrib_path))
        with open(contrib_path, "r", encoding="utf-8") as f:
            c_data = json.load(f)

        core_uri_list = c_data.get("uri_schemes", [])
        tokens = [item.get("token") for item in core_uri_list if isinstance(item, dict)]
        self.assertIn("workflow.plans", tokens)
        self.assertIn("workflow.archived", tokens)
        self.assertIn("workflow.docs", tokens)
        self.assertNotIn("workflow.ext", tokens)

        candidates = [
            os.path.join(PKG_ROOT, "configurable", "config.project.json"),
            os.path.join(PKG_ROOT, "config.project.json"),
            os.path.join(os.path.dirname(os.path.dirname(PKG_ROOT)), "config", "agents-workflow", "config.project.json"),
        ]
        tpl_path = next((p for p in candidates if os.path.isfile(p)), candidates[0])

        self.assertTrue(os.path.isfile(tpl_path), f"config template must exist at {tpl_path}")
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl_data = json.load(f)

        paths = tpl_data.get("paths", {})
        self.assertIn("plans", paths)
        self.assertIn("archived", paths)
        self.assertIn("docs", paths)
        self.assertNotIn("ext", paths)
        self.assertIn("release_targets", tpl_data)
        self.assertIn("enable_agents_md", tpl_data)
        self.assertIn("enable_project_changelog", tpl_data)
        self.mark_passed()

    def test_probe_paths_and_resolve_physical_path_guard(self):
        """驗證 probe_paths 與 _resolve_physical_path 正確識別實體路徑、!undefined 攔截與存在性。"""
        existing_sub = os.path.join(self.temp_dir, "existing_docs")
        os.makedirs(existing_sub, exist_ok=True)
        missing_sub = os.path.join(self.temp_dir, "missing_plans")

        probed = self.initializer.probe_paths(
            {
                "docs": existing_sub,
                "plans": missing_sub,
            }
        )

        self.assertEqual(len(probed), 2)
        docs_item = next(p for p in probed if p["key"] == "docs")
        plans_item = next(p for p in probed if p["key"] == "plans")

        self.assertTrue(docs_item["exists"])
        self.assertFalse(plans_item["exists"])
        self.assertEqual(self.initializer._resolve_physical_path(""), "")
        self.assertEqual(self.initializer._resolve_physical_path("!undefined"), "")
        self.mark_passed()

    def test_init_default_auto_confirm(self):
        """驗證自動確認時建立目錄並寫入組態。"""
        plans_dir = os.path.join(self.temp_dir, "plans")
        archived_dir = os.path.join(self.temp_dir, "plans", "archived")
        docs_dir = os.path.join(self.temp_dir, "docs")
        roadmap_dir = os.path.join(self.temp_dir, "plans", "roadmap")

        res = self.initializer.run_init_default(
            paths_override={
                "plans": plans_dir,
                "archived": archived_dir,
                "docs": docs_dir,
                "roadmap": roadmap_dir,
            },
            auto_confirm=True,
            interactive=False,
        )

        self.assertTrue(res["success"])
        self.assertFalse(res["cancelled"])
        self.assertTrue(os.path.isdir(plans_dir))
        self.assertTrue(os.path.isdir(archived_dir))
        self.assertTrue(os.path.isdir(docs_dir))
        self.assertTrue(os.path.isdir(roadmap_dir))
        self.mark_passed()

    def test_cli_invocation_with_all_four_path_overrides(self):
        """驗證 CLI init 指令解析 -y 與全部 4 項 --path-* 參數。"""
        custom_plans = os.path.join(self.temp_dir, "cli_plans")
        custom_archived = os.path.join(self.temp_dir, "cli_archived")
        custom_docs = os.path.join(self.temp_dir, "cli_docs")
        custom_roadmap = os.path.join(self.temp_dir, "cli_roadmap")

        ret = cli.init(
            [
                "-y",
                f"--path-plans={custom_plans}",
                f"--path-archived={custom_archived}",
                f"--path-docs={custom_docs}",
                f"--path-roadmap={custom_roadmap}",
            ]
        )
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isdir(custom_plans))
        self.assertTrue(os.path.isdir(custom_archived))
        self.assertTrue(os.path.isdir(custom_docs))
        self.assertTrue(os.path.isdir(custom_roadmap))
        self.mark_passed()

    def test_non_interactive_cancellation_and_interactive_prompts(self):
        """驗證非自動確認無 TTY 退出，以及 interactive=True 下 y / n / EOFError / KeyboardInterrupt 分支。"""
        cancel_dir = os.path.join(self.temp_dir, "cancelled_plans")
        res_no_tty = self.initializer.run_init_default(
            paths_override={"plans": cancel_dir},
            auto_confirm=False,
            interactive=False,
        )
        self.assertTrue(res_no_tty["success"])
        self.assertTrue(res_no_tty["cancelled"])
        self.assertFalse(os.path.exists(cancel_dir))

        for side_eff in ("n", EOFError(), KeyboardInterrupt()):
            p_cand = os.path.join(self.temp_dir, f"cancel_{type(side_eff).__name__}")
            overrides = {
                "plans": p_cand,
                "archived": os.path.join(p_cand, "archived"),
                "docs": os.path.join(p_cand, "docs"),
                "roadmap": os.path.join(p_cand, "roadmap"),
            }
            with patch("builtins.input", side_effect=[side_eff]):
                res_c = self.initializer.run_init_default(
                    paths_override=overrides,
                    auto_confirm=False,
                    interactive=True,
                )
            self.assertTrue(res_c["success"])
            self.assertTrue(res_c["cancelled"])
            self.assertFalse(os.path.exists(p_cand))

        ok_base = os.path.join(self.temp_dir, "interactive_yes")
        yes_overrides = {
            "plans": os.path.join(ok_base, "plans"),
            "archived": os.path.join(ok_base, "archived"),
            "docs": os.path.join(ok_base, "docs"),
            "roadmap": os.path.join(ok_base, "roadmap"),
        }
        with patch("builtins.input", return_value="y"):
            res_yes = self.initializer.run_init_default(
                paths_override=yes_overrides,
                auto_confirm=False,
                interactive=True,
            )
        self.assertTrue(res_yes["success"])
        self.assertFalse(res_yes["cancelled"])
        for d in yes_overrides.values():
            self.assertTrue(os.path.isdir(d))
        self.mark_passed()

    def test_sync_gitignore_and_write_project_config_failure(self):
        """驗證 sync_gitignore 委託與 _write_project_config 失敗降級。"""
        gi_res = self.initializer.sync_gitignore(host_dir=self.temp_dir)
        self.assertIsInstance(gi_res, dict)
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, ".gitignore")))

        with patch("core.config.set", side_effect=OSError("disk full")):
            self.assertFalse(self.initializer._write_project_config({"plans": "project://plans"}))

        fail_base = os.path.join(self.temp_dir, "write_cfg_fail")
        fail_overrides = {
            "plans": os.path.join(fail_base, "plans"),
            "archived": os.path.join(fail_base, "archived"),
            "docs": os.path.join(fail_base, "docs"),
            "roadmap": os.path.join(fail_base, "roadmap"),
        }
        err_buf = io.StringIO()
        with patch.object(self.initializer, "_write_project_config", return_value=False), redirect_stderr(err_buf):
            res_fail = self.initializer.run_init_default(
                paths_override=fail_overrides,
                auto_confirm=True,
                interactive=False,
            )
        self.assertFalse(res_fail["success"])
        self.assertFalse(res_fail["cancelled"])
        self.assertIn("failed to update config.project.json", err_buf.getvalue())
        self.mark_passed()

    def test_check_project_protocol_valid_and_undefined_guardrail(self):
        """驗證 project:// 正確配置與未配置 (!undefined) 時之前置防呆阻斷。"""
        is_valid, proj_path = self.initializer.check_project_protocol()
        self.assertTrue(is_valid)
        self.assertTrue(bool(proj_path))

        config.set("core", "project_root", "!undefined", local=False)
        config.reload()
        initializer = WorkflowInitializer(host_dir=self.temp_dir)
        is_valid_after, _ = initializer.check_project_protocol()
        self.assertFalse(is_valid_after)

        res = initializer.run_init_default(auto_confirm=True, interactive=False)
        self.assertFalse(res["success"])
        self.assertEqual(res.get("error"), "project:// protocol is undefined")
        self.assertEqual(len(res.get("created_dirs", [])), 0)

        ret = cli.init(["-y"])
        self.assertEqual(ret, 1)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
