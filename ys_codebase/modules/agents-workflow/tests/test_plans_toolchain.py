"""
test_plans_toolchain.py — agents-workflow 模組內部 Plans 工具鏈單元測試。
"""
import sys
import os
import shutil
import tempfile
from pathlib import Path
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

# 確保模組內部套件可引入
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from agents_workflow.plans import (
    PlanArchiver,
    PlanScanner,
    PlanSearcher,
    PlanVerifier,
    PlanNotFoundError,
    PlanFormatError,
    PlanIncompleteError,
    PlanDestinationExistsError,
)

@require(Requirement.ENV)
class TestPlansToolchainInternal(YSCBTestCase):
    """模組內部 Plans 工具鏈單元測試。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_plans_int_")
        self.workspace_root = Path(self.temp_dir)
        self.plans_dir = self.workspace_root / "plans"
        self.archive_dir = self.workspace_root / "archive_plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.changelog_file = self.workspace_root / "CHANGELOG.md"
        self.changelog_file.write_text("# Changelog\n\n## 2026_08_20_1200_demo\n", encoding="utf-8")

    def tearDown(self):
        super().tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_scanner_and_archiver_flow(self):
        p_name = "2026_08_20_1200_demo"
        p_dir = self.plans_dir / p_name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "P00_semantic_requirements.md").write_text("> 狀態：Confirmed\n", encoding="utf-8")
        (p_dir / "P01_requirements_spec.md").write_text("> 狀態：Confirmed\n", encoding="utf-8")
        (p_dir / "P07_walkthrough.md").write_text("> 狀態：Completed\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n", encoding="utf-8")
        (p_dir / "handoff.md").write_text("# Handoff\n", encoding="utf-8")

        # 1. 測試 Scanner
        scanner = PlanScanner(plans_dir=self.plans_dir)
        plans = scanner.scan_active_plans()
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["name"], p_name)
        self.assertEqual(plans[0]["status"], "Completed")

        # 2. 測試 Archiver
        archiver = PlanArchiver(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            project_root=self.workspace_root
        )
        res = archiver.archive_plan(p_name)
        self.assertTrue(res["success"])
        self.assertTrue(res["cleaned_handoff"])
        self.assertTrue((self.archive_dir / "2026" / "08" / p_name).exists())
        self.assertFalse((self.plans_dir / p_name).exists())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_searcher_and_verifier_flow(self):
        p_name = "2026_08_20_1300_search_verify"
        p_dir = self.plans_dir / p_name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "P01_requirements_spec.md").write_text(
            "> 狀態：Confirmed\n> 功能名稱：SearchVerify\n> 建立日期：2026-08-20\n\n- **[P01:DR-01] 內部決策**：重要結論\n",
            encoding="utf-8"
        )

        searcher = PlanSearcher(plans_dir=self.plans_dir, archive_dir=self.archive_dir)
        drs = searcher.search_drs(query="內部決策")
        self.assertEqual(len(drs), 1)
        self.assertIn("DR-01", drs[0]["dr_id"])

        verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir)
        res = verifier.verify(plan_name=p_name)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_errors"], 0)
        self.mark_passed()
