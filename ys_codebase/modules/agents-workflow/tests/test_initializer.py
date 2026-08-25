"""
Unit and Integration Tests for agents-workflow WorkflowInitializer and --init-default CLI.
Covers FT-01 ~ FT-06, ET-01 ~ ET-03.
"""
import unittest
import os
import sys
import json
import shutil
import tempfile
from typing import Dict, Any

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.initializer import WorkflowInitializer
from scripts import cli


class TestWorkflowInitializer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_init_")
        self.initializer = WorkflowInitializer()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

    def test_ft_01_manifest_and_template_structure(self):
        """FT-01 & FT-02: 驗證 manifest.json 宣告 4 大 URI 協議與 config 模板 !undefined 剛性。"""
        mf_path = os.path.join(_pkg_root, "manifest.json")
        self.assertTrue(os.path.isfile(mf_path))
        with open(mf_path, "r", encoding="utf-8") as f:
            mf_data = json.load(f)
        
        core_uri = mf_data.get("contributes", {}).get("core", {}).get("uri", {})
        self.assertIn("workflow.plans", core_uri)
        self.assertIn("workflow.archived", core_uri)
        self.assertIn("workflow.ext", core_uri)
        self.assertIn("workflow.docs", core_uri)

        tpl_path = os.path.join(_pkg_root, "config.project.json")
        self.assertTrue(os.path.isfile(tpl_path))
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl_data = json.load(f)
        
        paths = tpl_data.get("paths", {})
        self.assertEqual(paths.get("plans"), "!undefined")
        self.assertEqual(paths.get("archived"), "!undefined")
        self.assertEqual(paths.get("ext"), "!undefined")
        self.assertEqual(paths.get("docs"), "!undefined")
        self.assertIn("ide", tpl_data)
        self.assertIn("enable_agents_md", tpl_data)
        self.assertIn("enable_project_changelog", tpl_data)

    def test_ft_02_probe_paths(self):
        """FT-02: 驗證 probe_paths 能正確識別實體路徑與存在性。"""
        existing_sub = os.path.join(self.temp_dir, "existing_docs")
        os.makedirs(existing_sub, exist_ok=True)
        missing_sub = os.path.join(self.temp_dir, "missing_plans")

        probed = self.initializer.probe_paths({
            "docs": existing_sub,
            "plans": missing_sub
        })

        self.assertEqual(len(probed), 2)
        docs_item = next(p for p in probed if p["key"] == "docs")
        plans_item = next(p for p in probed if p["key"] == "plans")

        self.assertTrue(docs_item["exists"])
        self.assertFalse(plans_item["exists"])

    def test_ft_03_init_default_auto_confirm(self):
        """FT-03: 驗證 --init-default 自動確認時建立目錄並寫入組態。"""
        plans_dir = os.path.join(self.temp_dir, "plans")
        archived_dir = os.path.join(self.temp_dir, "plans", "archived")
        ext_dir = os.path.join(self.temp_dir, "extensions")
        docs_dir = os.path.join(self.temp_dir, "docs")

        res = self.initializer.run_init_default(
            paths_override={
                "plans": plans_dir,
                "archived": archived_dir,
                "ext": ext_dir,
                "docs": docs_dir
            },
            auto_confirm=True,
            interactive=False
        )

        self.assertTrue(res["success"])
        self.assertFalse(res["cancelled"])
        self.assertTrue(os.path.isdir(plans_dir))
        self.assertTrue(os.path.isdir(archived_dir))
        self.assertTrue(os.path.isdir(ext_dir))
        self.assertTrue(os.path.isdir(docs_dir))

    def test_ft_04_cli_invocation_with_path_override(self):
        """FT-05: 驗證 CLI 指令解析 --init-default 與 --path-* 參數。"""
        custom_docs = os.path.join(self.temp_dir, "my_custom_docs")
        ret = cli.main(["--init-default", "-y", f"--path-docs={custom_docs}"])
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isdir(custom_docs))

    def test_et_01_user_cancellation(self):
        """ET-01: 驗證非自動確認且無 TTY 時使用者拒絕安全退出。"""
        res = self.initializer.run_init_default(
            paths_override={"plans": os.path.join(self.temp_dir, "cancelled_plans")},
            auto_confirm=False,
            interactive=False
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["cancelled"])
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "cancelled_plans")))


if __name__ == "__main__":
    unittest.main()
