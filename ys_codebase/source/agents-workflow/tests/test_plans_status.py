"""
test_plans_status.py — agents-workflow 模組內部 Plans 狀態解析器、動態佔位符與邊界防呆測試。
涵蓋 FT-01 ~ FT-09 自動化測試案例清單。
100% Python Standard Library + YSCB Testing Framework, Zero External Dependencies.
"""

import os
import sys
import tempfile
import re
from pathlib import Path

# 確保模組內部套件可引入
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

from agents_workflow.plans import (
    PlanArchiver,
    PlanScanner,
    PlanVerifier,
    PlanStatusResolver,
    PlanIncompleteError,
    PlanDestinationExistsError,
)


@require(Requirement.ENV)
class TestPlansStatusAndBoundaries(YSCBTestCase):
    """測試 Plans 工具鏈狀態解析、歸檔時序防呆與驗證器動態佔位符 (FT-01 ~ FT-09)。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_status_")
        self.workspace_root = Path(self.temp_dir)
        self.plans_dir = self.workspace_root / "plans"
        self.archive_dir = self.workspace_root / "archive_plans"
        self.templates_dir = self.workspace_root / "templates"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        self.changelog_file = self.workspace_root / "CHANGELOG.md"
        self.changelog_file.write_text("# Changelog\n\n", encoding="utf-8")

        # 建立測試用標準模板
        (self.templates_dir / "fast_track_plan.md").write_text(
            "# 快速軌道開發計畫\n\n"
            "> 計畫名稱：[計畫名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | In Progress | Completed]\n\n"
            "## 1. 快速需求與範疇\n\n"
            "## 2. 實作變更清冊\n\n"
            "## 3. 測試與驗證\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n"
            "> 功能名稱：[功能名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | Confirmed]\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n\n"
            "## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n\n"
            "## 3. 開放議題與確認紀錄\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n"
            "> 功能名稱：[功能名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | In Progress | Completed]\n\n"
            "## 1. 實作任務清單 (Task Breakdown)\n\n"
            "## 2. 實作偏差紀錄表 (Implementation Deviations)\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P06_test_plan.md").write_text(
            "# 測試計畫與驗證報告\n\n"
            "> 功能名稱：[功能名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | Confirmed | In Progress | Passed | Completed]\n\n"
            "## 1. 自動化測試案例清單 (Automated Test Cases)\n\n"
            "## 2. 測試執行紀錄表 (Test Execution Log)\n\n"
            "## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n",
            encoding="utf-8"
        )
        (self.templates_dir / "RXX_research_report.md").write_text(
            "# 技術調研報告 (Technical Research Report)\n\n"
            "> 調研主題：[調研主題/所屬功能]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 調研狀態：[Draft | Concluded]\n\n"
            "## 1. 調研背景與目標 (Research Objectives)\n\n"
            "## 2. 現況與痛點分析 (Problem Analysis)\n\n"
            "## 3. 候選方案評估與對比 (Alternative Solutions)\n\n"
            "## 4. 決策推薦與架構影響 (Recommendation & Impact)\n\n"
            "## 5. 後續行動指針 (Action Items)\n",
            encoding="utf-8"
        )

    def test_ft_01_header_status(self):
        """FT-01: PlanStatusResolver 準確從 Blockquote 解析標頭狀態，內文任意處出現 'Completed' 不受干擾。"""
        # Case A: 標頭 Completed，內文包含 In Progress
        content_completed = (
            "# 測試計畫\n\n"
            "> 計畫名稱：測試\n"
            "> 狀態：Completed\n\n"
            "## 內文說明\n"
            "目前狀態：In Progress 正在進行其他事，但標頭是 Completed。\n"
        )
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_completed), "completed")
        self.assertTrue(PlanStatusResolver.is_doc_completed(content_completed))

        # Case B: 標頭 In Progress，內文包含 Completed
        content_in_progress = (
            "# 測試計畫\n\n"
            "> 計畫名稱：測試\n"
            "> 狀態：In Progress\n\n"
            "## 內文說明\n"
            "先前任務已經 Completed，請注意。\n"
            "Status: Completed\n"
            "狀態：Completed\n"
        )
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_in_progress), "in progress")
        self.assertFalse(PlanStatusResolver.is_doc_completed(content_in_progress))

        # Case C: Research 調研狀態 Concluded
        content_research_concluded = (
            "# 調研報告\n\n"
            "> 調研主題：架構探索\n"
            "> 調研狀態：Concluded\n\n"
            "正文內容...\n"
        )
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_research_concluded), "concluded")
        self.assertTrue(PlanStatusResolver.is_research_completed(content_research_concluded))

        # Case D: Research 調研狀態 Draft
        content_research_draft = (
            "# 調研報告\n\n"
            "> 調研主題：架構探索\n"
            "> 調研狀態：Draft\n\n"
            "正文內容提及 Concluded...\n"
        )
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_research_draft), "draft")
        self.assertFalse(PlanStatusResolver.is_research_completed(content_research_draft))
        self.mark_passed()

    def test_ft_02_archiver_ft_in_progress(self):
        """FT-02: PlanArchiver 攔截標頭為 In Progress 但正文含 Completed 之 Fast Track 計畫。"""
        plan_name = "2026_10_17_1000_ft_incomplete"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        # fast_track_plan.md 標頭為 In Progress，正文有 Completed
        (p_dir / "fast_track_plan.md").write_text(
            "# 快速軌道開發計畫\n\n"
            "> 計畫名稱：快速測試\n"
            "> 建立日期：2026-10-17\n"
            "> 狀態：In Progress\n\n"
            "## 1. 快速需求與範疇\n"
            "This task is Completed in discussion.\n",
            encoding="utf-8"
        )
        self.changelog_file.write_text(f"# Changelog\n\n## {plan_name}\n- 變更紀錄\n", encoding="utf-8")

        archiver = PlanArchiver(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            project_root=self.workspace_root
        )
        archiver.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        with self.assertRaises(PlanIncompleteError) as ctx:
            archiver.archive_plan(plan_name, force=False)
        self.assertIn("fast_track_plan.md", str(ctx.exception))
        self.mark_passed()

    def test_ft_03_scanner_p05_with_p06_confirmed(self):
        """FT-03: PlanScanner 在 P05 進行中且 P06 為 Confirmed 時正確回報 Phase 5 而非 Phase 6。"""
        plan_name = "2026_10_17_1100_full_track_p05"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 需求\n", encoding="utf-8"
        )
        (p_dir / "P01_requirements_spec.md").write_text(
            "# 需求規格\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 規格\n", encoding="utf-8"
        )
        (p_dir / "P05_task.md").write_text(
            "# 實作任務清單\n\n> 功能名稱：測試\n> 狀態：In Progress\n\n## 1. 實作任務\n- [ ] 任務 1\n", encoding="utf-8"
        )
        (p_dir / "P06_test_plan.md").write_text(
            "# 測試計畫\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 測試\n", encoding="utf-8"
        )

        scanner = PlanScanner(plans_dir=self.plans_dir)
        plans = scanner.scan_active_plans()
        target = next((p for p in plans if p["name"] == plan_name), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["status"], "Implementing/Phase 5")
        self.assertEqual(target["track"], "Full Track")
        self.mark_passed()

    def test_ft_04_scanner_research_track(self):
        """FT-04: PlanScanner 正確識別 Research Track，並依 R 檔狀態顯示 Concluded 或 Draft。"""
        # Case 1: Research Concluded
        plan_concluded = "2026_10_17_1200_research_concluded"
        p_dir1 = self.plans_dir / plan_concluded
        p_dir1.mkdir(parents=True, exist_ok=True)
        (p_dir1 / "P00_semantic_requirements.md").write_text(
            "# 語意需求\n\n> 功能名稱：調研\n> 狀態：Confirmed\n", encoding="utf-8"
        )
        (p_dir1 / "R01_deep_dive.md").write_text(
            "# 技術調研報告\n\n> 調研主題：深入調研\n> 調研狀態：Concluded\n", encoding="utf-8"
        )

        # Case 2: Research Draft
        plan_draft = "2026_10_17_1300_research_draft"
        p_dir2 = self.plans_dir / plan_draft
        p_dir2.mkdir(parents=True, exist_ok=True)
        (p_dir2 / "P00_semantic_requirements.md").write_text(
            "# 語意需求\n\n> 功能名稱：調研\n> 狀態：Confirmed\n", encoding="utf-8"
        )
        (p_dir2 / "R01_deep_dive.md").write_text(
            "# 技術調研報告\n\n> 調研主題：深入調研\n> 調研狀態：Draft\n", encoding="utf-8"
        )

        scanner = PlanScanner(plans_dir=self.plans_dir)
        plans = scanner.scan_active_plans()

        t1 = next((p for p in plans if p["name"] == plan_concluded), None)
        self.assertIsNotNone(t1)
        self.assertEqual(t1["track"], "Research")
        self.assertEqual(t1["status"], "Concluded")

        t2 = next((p for p in plans if p["name"] == plan_draft), None)
        self.assertIsNotNone(t2)
        self.assertEqual(t2["track"], "Research")
        self.assertEqual(t2["status"], "Draft")
        self.mark_passed()

    def test_ft_05_verifier_research_mapping(self):
        """FT-05: PlanVerifier 正確將 R01_xxx.md 映射至調研模板，即便檔名無 'research' 字樣。"""
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        tmpl_name = verifier._map_file_to_template("R01_deep_architecture_analysis.md")
        self.assertEqual(tmpl_name, "RXX_research_report.md")

        tmpl_name_2 = verifier._map_file_to_template("R02_security_audit.md")
        self.assertEqual(tmpl_name_2, "RXX_research_report.md")
        self.mark_passed()

    def test_ft_06_verifier_test_id_regex(self):
        """FT-06: PlanVerifier 收緊測試 ID 判定為正則 \\b(FT|ET|RT)-\\d{2}\\b，僅含 FP-03 時判定失敗。"""
        plan_name = "2026_10_17_1400_test_id_check"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        # 僅含 FP-03，無 FT-XX / ET-XX / RT-XX
        p06_fail = (
            "# 測試計畫與驗證報告\n\n"
            "> 功能名稱：測試\n"
            "> 建立日期：2026-10-17\n"
            "> 狀態：Confirmed\n\n"
            "## 1. 自動化測試案例清單 (Automated Test Cases)\n\n"
            "- 步驟 FP-03 驗證\n\n"
            "## 2. 測試執行紀錄表 (Test Execution Log)\n\n"
            "## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n"
        )
        (p_dir / "P06_test_plan.md").write_text(p06_fail, encoding="utf-8")
        (p_dir / "changelog.md").write_text("# 計畫變更紀錄\n\n| 日期時間 | 類型 | 變更描述 |\n| :--- | :--- | :--- |\n| 2026-10-17 | Phase | 推進 |\n", encoding="utf-8")

        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        report = verifier.verify_plan(plan_name)
        id_issues = [i for i in report.issues if i.category == "ID_MATRIX"]
        self.assertTrue(len(id_issues) > 0, "應檢測出缺少 FT-XX/ET-XX/RT-XX 前綴之 ID_MATRIX 錯誤")

        # 加入合規之 FT-01 測試案例後再次驗證
        p06_pass = p06_fail.replace("- 步驟 FP-03 驗證", "- FT-01: 步驟 FP-03 驗證")
        (p_dir / "P06_test_plan.md").write_text(p06_pass, encoding="utf-8")
        report2 = verifier.verify_plan(plan_name)
        id_issues2 = [i for i in report2.issues if i.category == "ID_MATRIX"]
        self.assertEqual(len(id_issues2), 0, "具備 FT-01 後不應再回報 ID_MATRIX 錯誤")
        self.mark_passed()

    def test_ft_07_verifier_dynamic_placeholders(self):
        """FT-07: PlanVerifier 動態推導佔位符，成功攔截 [調研主題/所屬功能] 等未替換模板佔位符。"""
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        patterns = verifier.get_all_placeholder_patterns()
        # 驗證動態提取到了 [調研主題/所屬功能]
        found = any("調研主題" in p and "所屬功能" in p for p in patterns)
        self.assertTrue(found, f"應自 RXX 模板中動態提取包含調研主題之佔位符模式: {patterns}")

        # 測試在文件中出現未替換之 [調研主題/所屬功能] 是否被攔截
        plan_name = "2026_10_17_1500_dyn_placeholder_check"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "R01_deep_dive.md").write_text(
            "# 技術調研報告 (Technical Research Report)\n\n"
            "> 調研主題：[調研主題/所屬功能]\n"
            "> 建立日期：2026-10-17\n"
            "> 調研狀態：Concluded\n\n"
            "## 1. 調研背景與目標 (Research Objectives)\n\n"
            "## 2. 現況與痛點分析 (Problem Analysis)\n\n"
            "## 3. 候選方案評估與對比 (Alternative Solutions)\n\n"
            "## 4. 決策推薦與架構影響 (Recommendation & Impact)\n\n"
            "## 5. 後續行動指針 (Action Items)\n",
            encoding="utf-8"
        )
        (p_dir / "changelog.md").write_text("# 計畫變更紀錄\n\n| 日期時間 | 類型 | 變更描述 |\n| :--- | :--- | :--- |\n| 2026-10-17 | Phase | 推進 |\n", encoding="utf-8")

        report = verifier.verify_plan(plan_name)
        ph_issues = [i for i in report.issues if i.category == "PLACEHOLDER"]
        self.assertTrue(len(ph_issues) > 0, "應檢測到未替換之動態佔位符 [調研主題/所屬功能]")
        self.mark_passed()

    def test_ft_08_archiver_handoff_preserved_on_conflict(self):
        """FT-08: PlanArchiver 目的地衝突時不刪除 handoff.md。"""
        plan_name = "2026_10_17_1600_conflict_test"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)
        handoff_file = p_dir / "handoff.md"
        handoff_file.write_text("# Handoff\n\n現場交接紀錄\n", encoding="utf-8")

        (p_dir / "fast_track_plan.md").write_text(
            "# 快速軌道開發計畫\n\n> 計畫名稱：測試\n> 狀態：Completed\n\n## 1. 快速需求\n## 2. 實作\n## 3. 測試\n",
            encoding="utf-8"
        )
        self.changelog_file.write_text(f"# Changelog\n\n## {plan_name}\n- 變更\n", encoding="utf-8")

        # 在歸檔目標建立同名目錄製造衝突 (archive_dir / YYYY / MM / plan_name)
        target_dest = self.archive_dir / "2026" / "10" / plan_name
        target_dest.mkdir(parents=True, exist_ok=True)
        (target_dest / "archived_dummy.txt").write_text("already archived", encoding="utf-8")

        archiver = PlanArchiver(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            project_root=self.workspace_root
        )
        archiver.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        with self.assertRaises(PlanDestinationExistsError):
            archiver.archive_plan(plan_name, force=True)

        # 斷言 handoff.md 依然完整存在，未被提前刪除
        self.assertTrue(handoff_file.exists(), "目的地衝突時 handoff.md 必須受到保護，嚴禁被提前刪除！")
        self.mark_passed()

    def test_ft_09_verifier_deadcode_clean(self):
        """FT-09: PlanVerifier 死代碼清理無未引用之 VALID_CHANGELOG_TYPES 且 docstring 對齊。"""
        self.assertFalse(hasattr(PlanVerifier, "VALID_CHANGELOG_TYPES"), "VALID_CHANGELOG_TYPES 必須已被清理")
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        doc = verifier._check_changelog_content.__doc__ or ""
        self.assertNotIn("VALID_CHANGELOG_TYPES", doc, "docstring 應清理對 VALID_CHANGELOG_TYPES 的過時引用")
        self.mark_passed()

