"""
Unit tests for Auto Workflow in agents-workflow module.
Covers FT-01, FT-02, FT-03, ET-01, ET-02, ET-03.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import unittest
import os
import sys
import json

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher


class TestAutoWorkflow(unittest.TestCase):
    def setUp(self):
        self.compiler = ArtifactCompiler()
        self.publisher = ReleasePublisher(compiler=self.compiler)
        self.auto_md_path = os.path.join(_pkg_root, "assets", "workflows", "Auto.md")
        self.manifest_path = os.path.join(_pkg_root, "manifest.json")

    def test_ft_01_auto_workflow_asset_content(self):
        """FT-01: 驗證 Auto.md 檔案存在，包含動態地圖、四大步驟、三大熔斷機制與尾部 Token。"""
        self.assertTrue(os.path.exists(self.auto_md_path), "Auto.md 檔案必須存在")
        
        with open(self.auto_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("__@{DYNAMIC_CONTEXT_MAP}__", content)
        self.assertIn("__${yscb.host://yscb.py}__", content)
        self.assertIn("# 自動連續推進工作流 (Auto)", content)
        self.assertIn("三大熔斷機制", content)
        self.assertIn("零臆測熔斷", content)
        self.assertIn("偏差熔斷", content)
        self.assertIn("P06 手動/UX 驗證絕對阻斷", content)
        self.assertIn("步驟 1：掃描目標計畫與斷點狀態", content)
        self.assertIn("步驟 2：連續推進閉環", content)
        self.assertIn("步驟 3：Phase 6 自動化測試與日誌登載", content)
        self.assertIn("步驟 4：抵達 P06 UX/手動驗證 Checkpoint", content)
        self.assertIn("__@{WORKFLOW_AUTO}__", content)

    def test_ft_02_manifest_export_and_token(self):
        """FT-02: 驗證 manifest.json 正確註冊 Auto.md 導出與 WORKFLOW_AUTO token 錨點。"""
        self.assertTrue(os.path.exists(self.manifest_path))
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        exports = manifest_data.get("contributes", {}).get("agents-workflow", {}).get("export", [])
        tokens = manifest_data.get("contributes", {}).get("agents-workflow", {}).get("token", [])

        auto_export = next(
            (e for e in exports if e.get("source") == "module://agents-workflow/assets/workflows/Auto.md"),
            None
        )
        self.assertIsNotNone(auto_export, "manifest.json 必須宣告導出 Auto.md")
        self.assertEqual(auto_export.get("type"), "workflow")

        token_values = [t.get("value") for t in tokens]
        self.assertIn("WORKFLOW_AUTO", token_values, "manifest.json 必須註冊 WORKFLOW_AUTO token")

    def test_ft_03_compilation_and_placeholder_resolution(self):
        """FT-03: 驗證 compiler.py 能順利編譯 Auto.md 且佔位符與相對路徑解算正確。"""
        res = self.compiler.compile_stage1()
        self.assertTrue(res["success"], "Stage 1 編譯必須成功")

        resolved_items = res.get("resolved_items", [])
        auto_item = next(
            (item for item in resolved_items if item.get("base_name") == "Auto.md"),
            None
        )
        self.assertIsNotNone(auto_item, "Stage 1 解析產物中必須包含 Auto.md")
        auto_content = auto_item.get("content", "")
        self.assertIn("自動連續推進工作流 (Auto)", auto_content)

    def test_et_01_et_02_et_03_edge_cases_in_specification(self):
        """ET-01 ~ ET-03: 驗證 Auto.md 規範中明確包含 Phase 0、Fast Track 與 Phase 6 UX 邊界條款。"""
        with open(self.auto_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ET-01: Phase 0 邊界
        self.assertIn("Phase 0 討論階段", content)
        self.assertIn("P00 標記為 `Confirmed` 後方可啟用 `/Auto`", content)

        # ET-02: Fast Track 邊界
        self.assertIn("Fast Track (Level 0) 無多階段等待需求，不適用 `/Auto`", content)

        # ET-03: P06 UX 阻斷
        self.assertIn("Agent 自行將 P06 標記為 `Passed` 或擅自進入 Phase 7 結案", content)


if __name__ == "__main__":
    unittest.main()
