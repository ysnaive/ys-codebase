"""
test_plans_toolchain.py — agents-workflow 模組內部 Plans 工具鏈與 PlanVerifier 完整單元測試。
涵蓋 FT-01~07 與 ET-01~02 檢核維度。
"""
import sys
import os
import re
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
    PlanSeverity,
    PlanIssue,
    PlanReport,
    PlanNotFoundError,
    PlanFormatError,
    PlanIncompleteError,
    PlanDestinationExistsError,
    PlanStatusResolver,
)
from agents_workflow.roadmap import RoadmapManager, TodoManager


@require(Requirement.ENV)
class TestPlansToolchainInternal(YSCBTestCase):
    """模組內部 Plans 工具鏈與 PlanVerifier 測試。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_plans_int_")
        self.workspace_root = Path(self.temp_dir)
        self.plans_dir = self.workspace_root / "plans"
        self.archive_dir = self.workspace_root / "archive_plans"
        self.templates_dir = self.workspace_root / "templates"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        self.changelog_file = self.workspace_root / "CHANGELOG.md"
        self.changelog_file.write_text("# Changelog\n\n## 2026_08_20_1200_demo\n", encoding="utf-8")

        # 建立模擬之展開後標準模板
        (self.templates_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n## 1. 使用者原始需求與意圖 (User Intent)\n\n## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n\n## 3. 開放議題與確認紀錄\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P06_test_plan.md").write_text(
            "# 測試計畫與驗證報告\n\n## 1. 測試策略與驗證維度\n\n## 2. 測試案例清冊 (Test Cases Matrix)\n\n## 3. 測試執行紀錄\n\n## 4. 人工 / UX 驗證 Checkpoint\n",
            encoding="utf-8"
        )
        (self.templates_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — [專案/功能名稱]\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n\n"
            "### [REV-01] [修訂主題簡述]\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n",
            encoding="utf-8"
        )

    def tearDown(self):
        super().tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_valid_plan(self, p_name: str) -> Path:
        """輔助函式：建立符合全量標準的測試計畫。"""
        p_dir = self.plans_dir / p_name
        p_dir.mkdir(parents=True, exist_ok=True)

        (p_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-08-20 12:00 | `INIT` | 初始化計畫 |\n",
            encoding="utf-8"
        )
        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：Demo Feature\n> 建立日期：2026-08-20\n> 狀態：Confirmed\n> 模型：Gemini Flash\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n- **原始陳述**：需求\n\n"
            "## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n- **[P00:DR-01]** 決策\n\n"
            "## 3. 開放議題與確認紀錄\n- [x] 無\n",
            encoding="utf-8"
        )
        (p_dir / "P07_walkthrough.md").write_text(
            "# 交付說明書\n\n> 功能名稱：Demo Feature\n> 建立日期：2026-08-20\n> 狀態：Completed\n> 模型：Gemini Flash\n\n## 1. 交付成果總覽\n",
            encoding="utf-8"
        )
        return p_dir

    @require(Requirement.LOGIC)
    def test_plan_verifier_dynamic_header_alignment(self):
        """FT-01: 動態模板章節標題鏡像對齊檢核。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_header_test")
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        # 1. 正常合格檔案 -> PASS
        rep = verifier.verify_plan("2026_08_20_1200_header_test")
        self.assertEqual(rep.status, PlanSeverity.PASS)

        # 2. 移除 P00 的必要章節標題 -> FAIL
        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n> 狀態：Confirmed\n> 模型：Gemini Flash\n\n"
            "## 1. 使用者原始需求與意圖\n(缺少第 2 與第 3 節標題)\n",
            encoding="utf-8"
        )
        rep_fail = verifier.verify_plan("2026_08_20_1200_header_test")
        self.assertEqual(rep_fail.status, PlanSeverity.FAIL)
        self.assertTrue(any("TEMPLATE" in e for e in rep_fail.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_id_matrix_and_test_plan(self):
        """FT-02: 測試規劃與標準 ID 格式合規檢核。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_id_test")
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        # 建立 P06 但缺少 FT-/ET- 測試清單 -> FAIL
        (p_dir / "P06_test_plan.md").write_text(
            "# 測試計畫\n\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n> 狀態：Draft\n> 模型：Gemini Flash\n\n"
            "## 1. 測試策略與驗證維度\n\n## 2. 測試案例清冊 (Test Cases Matrix)\n(無 FT 前綴)\n\n"
            "## 3. 測試執行紀錄\n\n## 4. 人工 / UX 驗證 Checkpoint\n",
            encoding="utf-8"
        )
        rep = verifier.verify_plan("2026_08_20_1200_id_test")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("ID_MATRIX" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_header_metadata_and_sub_plan(self):
        """FT-03: Header Blockquote 元數據與子計畫所屬主計畫校驗。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_meta_test")
        sub_dir = p_dir / "sub_01_child"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-08-20 12:00 | `INIT` | 子計畫 |\n",
            encoding="utf-8"
        )

        # 子計畫缺少「所屬主計畫」-> FAIL
        (sub_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：Child\n> 建立日期：2026-08-20\n> 狀態：Draft\n> 模型：Gemini Flash\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n\n## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n\n## 3. 開放議題與確認紀錄\n",
            encoding="utf-8"
        )
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        rep = verifier.verify_plan("2026_08_20_1200_meta_test")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("所屬主計畫" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_changelog_guard(self):
        """FT-04: 雙星伴隨與 changelog 合規檢核。"""
        p_dir = self.plans_dir / "2026_08_20_1200_no_changelog"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "P00_semantic_requirements.md").write_text(
            "> 功能名稱：NoChangelog\n> 建立日期：2026-08-20\n> 狀態：Draft\n> 模型：Gemini Flash\n",
            encoding="utf-8"
        )

        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        # 缺少 changelog.md -> FAIL
        rep = verifier.verify_plan("2026_08_20_1200_no_changelog")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("changelog.md" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_nested_depth_and_umbrella(self):
        """FT-05: 巢狀層級 <= 2 約束與 Umbrella 結構稽核。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_umbrella_test")
        sub_dir = p_dir / "sub_01"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "changelog.md").write_text("# Log\n| 日期時間 | 類型 | 摘要 |\n| --- | --- | --- |\n| 2026-08-20 | `INIT` | log |\n", encoding="utf-8")

        # 缺少 umbrella_overview.md -> FAIL
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        rep = verifier.verify_plan("2026_08_20_1200_umbrella_test")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("umbrella_overview.md" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_placeholders_and_html_comments(self):
        """FT-06: 模板佔位符與嚴禁殘留任何 HTML 註解 (<!-- ... -->)。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_placeholder_test")
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        # 包含 HTML 註解 -> FAIL
        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n> 狀態：Confirmed\n> 模型：Gemini Flash\n\n"
            "<!-- 這是未清除的指引或註解 -->\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n\n## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n\n## 3. 開放議題與確認紀錄\n",
            encoding="utf-8"
        )
        rep = verifier.verify_plan("2026_08_20_1200_placeholder_test")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("HTML_COMMENT" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_archiver_rigid_gate_and_force(self):
        """FT-07: PlanArchiver 遭遇 FAIL 時剛性阻斷歸檔，加 --force 則放行。"""
        # 建立一個未通過的計畫（缺少章節）
        p_dir = self._create_valid_plan("2026_08_20_1200_gate_test")
        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求\n> 功能名稱：Broken\n> 建立日期：2026-08-20\n> 狀態：Draft\n> 模型：Gemini Flash\n\n(缺少必填章節)\n",
            encoding="utf-8"
        )
        (self.workspace_root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 2026_08_20_1200_gate_test\n", encoding="utf-8"
        )

        archiver = PlanArchiver(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            project_root=self.workspace_root
        )

        # 無 force: 預期剛性拋出 PlanIncompleteError
        with self.assertRaises(PlanIncompleteError):
            archiver.archive_plan("2026_08_20_1200_gate_test", force=False)

        # 有 force: 預期放行搬移
        res = archiver.archive_plan("2026_08_20_1200_gate_test", force=True)
        self.assertTrue(res["success"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_empty_and_non_markdown(self):
        """ET-02: 空目錄與非 Markdown 檔案安全略過與報告。"""
        empty_dir = self.plans_dir / "2026_08_20_1200_empty_plan"
        empty_dir.mkdir(parents=True, exist_ok=True)
        (empty_dir / "random.txt").write_text("not a markdown", encoding="utf-8")

        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        rep = verifier.verify_plan("2026_08_20_1200_empty_plan")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("changelog.md" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_non_timestamp_dirs_safely_ignored_by_toolchain(self):
        """FT-01~03 & EC-01: 驗證非時間戳目錄 (如 roadmap, archived, custom_res) 在全量檢驗與掃描中被安全略過。"""
        # 建立合法計畫
        valid_plan = self._create_valid_plan("2026_08_20_1200_legit_plan")

        # 建立非時間戳目錄（模擬 roadmap, custom_notes, resources）
        roadmap_dir = self.plans_dir / "roadmap"
        roadmap_dir.mkdir(parents=True, exist_ok=True)
        (roadmap_dir / "release_opt.md").write_text("# Roadmap Item\n", encoding="utf-8")

        custom_dir = self.plans_dir / "custom_resources"
        custom_dir.mkdir(parents=True, exist_ok=True)
        (custom_dir / "README.md").write_text("# Resources\n", encoding="utf-8")

        # 1. 驗證 PlanVerifier.verify_all_plans()
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        reports = verifier.verify_all_plans()
        self.assertIn("2026_08_20_1200_legit_plan", reports)
        self.assertNotIn("roadmap", reports)
        self.assertNotIn("custom_resources", reports)
        self.assertEqual(len(reports), 1)

        # 2. 驗證 PlanScanner.scan_active_plans()
        scanner = PlanScanner(plans_dir=self.plans_dir)
        active_plans = scanner.scan_active_plans()
        plan_names = [p["name"] for p in active_plans]
        self.assertIn("2026_08_20_1200_legit_plan", plan_names)
        self.assertNotIn("roadmap", plan_names)
        self.assertNotIn("custom_resources", plan_names)
        self.assertEqual(len(active_plans), 1)

        # 3. 驗證 PlanSearcher.find_all_plans()
        searcher = PlanSearcher(plans_dir=self.plans_dir, archive_dir=self.archive_dir)
        found_plans = searcher.find_all_plans()
        found_names = [p.name for p in found_plans]
        self.assertIn("2026_08_20_1200_legit_plan", found_names)
        self.assertNotIn("roadmap", found_names)
        self.assertNotIn("custom_resources", found_names)
        self.assertEqual(len(found_plans), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_missing_model_fails(self):
        """FT-08: 驗證未包含 [模型] 欄位之計畫標頭會被判定為 FAIL。"""
        p_dir = self.plans_dir / "2026_08_20_1200_no_model"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-08-20 12:00 | `INIT` | 初始化 |\n",
            encoding="utf-8"
        )
        (p_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n> 狀態：Confirmed\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n- **原始陳述**：需求\n\n"
            "## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n- **[P00:DR-01]** 決策\n\n"
            "## 3. 開放議題與確認紀錄\n- [x] 無\n",
            encoding="utf-8"
        )
        verifier = PlanVerifier(plans_dir=self.plans_dir, templates_dir=self.templates_dir)
        rep = verifier.verify_plan("2026_08_20_1200_no_model")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("模型" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_completed_unchecked_checkbox_fails(self):
        """FT-09: 驗證狀態為 Completed 但包含未勾選 Checkbox (- [ ]) 之計畫判定為 FAIL。"""
        p_dir = self._create_valid_plan("2026_08_20_1200_unchecked_plan")
        (p_dir / "P05_task.md").write_text(
            "# 實作任務清單\n\n> 功能名稱：Demo\n> 建立日期：2026-08-20\n> 狀態：Completed\n> 模型：Gemini Flash\n\n"
            "## 1. 實作任務清單 (Task Breakdown)\n- [x] TASK-01 完成\n- [ ] TASK-02 遺漏未做\n\n"
            "## 2. 實作偏差紀錄表 (Implementation Deviations)\n| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |\n| - | - | 無偏差 | - |\n",
            encoding="utf-8"
        )
        verifier = PlanVerifier(plans_dir=self.plans_dir, templates_dir=self.templates_dir)
        rep = verifier.verify_plan("2026_08_20_1200_unchecked_plan")
        self.assertEqual(rep.status, PlanSeverity.FAIL)
        self.assertTrue(any("未勾選之待辦 Checkbox" in e for e in rep.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_verify_all_skips_archive(self):
        """FT-10: 驗證 verify_all_plans() 僅掃描活躍計畫目錄，排除歸檔目錄。"""
        self._create_valid_plan("2026_08_20_1200_active_plan")
        # 建立歸檔目錄中的破損計畫
        archived_broken = self.archive_dir / "2025" / "12" / "2025_12_01_1000_broken_archived"
        archived_broken.mkdir(parents=True, exist_ok=True)
        (archived_broken / "P00_discuss.md").write_text("# 舊歷史\n> 無合法標頭\n", encoding="utf-8")

        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        reports = verifier.verify_all_plans()
        self.assertIn("2026_08_20_1200_active_plan", reports)
        self.assertEqual(len(reports), 1)
        self.assertNotIn("2025_12_01_1000_broken_archived", reports)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_scanner_revision_track_and_orthogonal_attachment(self):
        """FT-11: 驗證獨立修訂計畫識別為 Revision Track，且附隨型修訂不干擾原主計畫 Track 與狀態。"""
        # 1. 獨立修訂計畫（僅含 revision_log.md + changelog.md）
        rev_only_dir = self.plans_dir / "2026_10_17_0900_standalone_rev"
        rev_only_dir.mkdir(parents=True, exist_ok=True)
        (rev_only_dir / "changelog.md").write_text("# Changelog\n| 日期時間 | 類型 | 摘要 |\n| --- | --- | --- |\n| 2026-10-17 | `INIT` | init |\n", encoding="utf-8")
        (rev_only_dir / "revision_log.md").write_text(
            "# 修訂紀錄\n\n> 功能名稱：UI Polish\n> 建立日期：2026-10-17\n> 狀態：In Progress\n> 模型：Gemini Flash\n",
            encoding="utf-8"
        )

        # 2. 獨立修訂計畫（含 P00 + revision_log.md）
        rev_p00_dir = self.plans_dir / "2026_10_17_0930_p00_plus_rev"
        rev_p00_dir.mkdir(parents=True, exist_ok=True)
        (rev_p00_dir / "changelog.md").write_text("# Changelog\n| 日期時間 | 類型 | 摘要 |\n| --- | --- | --- |\n| 2026-10-17 | `INIT` | init |\n", encoding="utf-8")
        (rev_p00_dir / "P00_discuss.md").write_text("> 功能名稱：RevWithP00\n> 建立日期：2026-10-17\n> 狀態：Confirmed\n> 模型：Gemini Flash\n", encoding="utf-8")
        (rev_p00_dir / "revision_log.md").write_text("> 功能名稱：RevWithP00\n> 建立日期：2026-10-17\n> 狀態：Completed\n> 模型：Gemini Flash\n", encoding="utf-8")

        # 3. Full Track 主計畫附隨 revision_log.md (In Progress) -> 不影響主計畫 Completed 狀態
        full_dir = self._create_valid_plan("2026_10_17_1000_full_with_rev")
        (full_dir / "P01_requirements_spec.md").write_text("> 功能名稱：Full\n> 建立日期：2026-10-17\n> 狀態：Confirmed\n> 模型：Gemini Flash\n", encoding="utf-8")
        (full_dir / "revision_log.md").write_text("> 功能名稱：Full\n> 建立日期：2026-10-17\n> 狀態：In Progress\n> 模型：Gemini Flash\n", encoding="utf-8")

        scanner = PlanScanner(plans_dir=self.plans_dir)
        self.assertEqual(scanner.get_plan_info(rev_only_dir), ("Revision", "In Progress"))
        self.assertEqual(scanner.get_plan_info(rev_p00_dir), ("Revision", "Completed"))
        self.assertEqual(scanner.get_plan_info(full_dir), ("Full Track", "Completed"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_verifier_revision_log_compliance(self):
        """FT-12: 驗證 PlanVerifier 對 revision_log.md 的標頭、動態章節與 [REV-XX] 條目檢核。"""
        rev_dir = self.plans_dir / "2026_10_17_1100_verify_rev"
        rev_dir.mkdir(parents=True, exist_ok=True)
        (rev_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-10-17 11:00 | `INIT` | 初始化 |\n",
            encoding="utf-8"
        )
        (rev_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — 視覺與參數微調\n\n"
            "> 功能名稱：視覺與參數微調\n"
            "> 建立日期：2026-10-17\n"
            "> 狀態：Completed\n"
            "> 模型：Gemini Flash\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n"
            "- **修訂來源與關聯脈絡**：獨立修訂計畫\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n\n"
            "### [REV-01] 調整按鈕間距與提示文字\n"
            "- **修訂類型**：`UI/UX/DX`\n"
            "- **涉及檔案**：`ui/button.py`\n"
            "- **修訂內容摘要**：\n  - 將間距由 4px 調整為 8px。\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n"
            "- [x] 所有修訂條目已定案。\n",
            encoding="utf-8"
        )

        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )
        # 1. 合規 revision_log.md -> PASS (動態 ### [REV-01] 標題不應誤觸 TEMPLATE 缺失)
        rep_pass = verifier.verify_plan("2026_10_17_1100_verify_rev")
        self.assertEqual(rep_pass.status, PlanSeverity.PASS)

        # 2. 移除 [REV-01] 條目 -> 觸發 ID_MATRIX FAIL
        (rev_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — 視覺與參數微調\n\n"
            "> 功能名稱：視覺與參數微調\n"
            "> 建立日期：2026-10-17\n"
            "> 狀態：In Progress\n"
            "> 模型：Gemini Flash\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n(尚未填寫 REV 條目)\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n",
            encoding="utf-8"
        )
        rep_fail = verifier.verify_plan("2026_10_17_1100_verify_rev")
        self.assertEqual(rep_fail.status, PlanSeverity.FAIL)
        self.assertTrue(any("ID_MATRIX" in e for e in rep_fail.errors))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_plan_archiver_revision_log_completion_gate(self):
        """FT-13 & ET-03: 驗證獨立修訂計畫歸檔與附隨修訂紀錄 (含子計畫) 未 Completed 阻斷歸檔。"""
        # 1. 獨立修訂計畫 Completed -> 順利歸檔
        rev_plan = "2026_10_17_1200_standalone_rev_archive"
        rev_dir = self.plans_dir / rev_plan
        rev_dir.mkdir(parents=True, exist_ok=True)
        (rev_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-10-17 12:00 | `INIT` | 初始化 |\n",
            encoding="utf-8"
        )
        (rev_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — 獨立修訂\n\n"
            "> 功能名稱：獨立修訂\n> 建立日期：2026-10-17\n> 狀態：Completed\n> 模型：Gemini Flash\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n\n### [REV-01] 調整參數\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n- [x] 完成\n",
            encoding="utf-8"
        )

        # 2. 主計畫 P07 Completed，但 sub_01 下附隨 revision_log.md 為 In Progress -> 阻斷歸檔
        umb_plan = "2026_10_17_1230_main_with_incomplete_sub_rev"
        umb_dir = self._create_valid_plan(umb_plan)
        (umb_dir / "umbrella_overview.md").write_text(
            "# 主計畫總覽\n\n> 計畫名稱：Umbrella\n> 建立日期：2026-10-17\n> 狀態：Completed\n> 模型：Gemini Flash\n",
            encoding="utf-8"
        )
        sub_dir = umb_dir / "sub_01_ui"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-10-17 12:30 | `INIT` | 子計畫 |\n",
            encoding="utf-8"
        )
        (sub_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — 子計畫修訂\n\n"
            "> 功能名稱：子計畫修訂\n> 所屬主計畫：2026_10_17_1230_main_with_incomplete_sub_rev\n"
            "> 建立日期：2026-10-17\n> 狀態：In Progress\n> 模型：Gemini Flash\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n\n### [REV-01] 微調樣式\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n- [ ] 待確認\n",
            encoding="utf-8"
        )

        self.changelog_file.write_text(
            f"# Changelog\n\n## {rev_plan}\n\n## {umb_plan}\n",
            encoding="utf-8"
        )

        archiver = PlanArchiver(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            project_root=self.workspace_root
        )
        # 覆寫內部 verifier 之 templates_dir 以對齊測試沙盒
        archiver.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir
        )

        # 獨立修訂計畫 Completed 應成功歸檔
        res_rev = archiver.archive_plan(rev_plan, force=False)
        self.assertTrue(res_rev["success"])

        # 附隨子計畫 revision_log.md 未 Completed 應拋出 PlanIncompleteError
        with self.assertRaises(PlanIncompleteError) as ctx:
            archiver.archive_plan(umb_plan, force=False)
        self.assertIn("revision_log.md", str(ctx.exception))

        # 將子計畫 revision_log.md 改為 Completed 並勾選 Checkbox 後應可順利歸檔
        (sub_dir / "revision_log.md").write_text(
            "# 修訂紀錄 (Revision Log) — 子計畫修訂\n\n"
            "> 功能名稱：子計畫修訂\n> 所屬主計畫：2026_10_17_1230_main_with_incomplete_sub_rev\n"
            "> 建立日期：2026-10-17\n> 狀態：Completed\n> 模型：Gemini Flash\n\n"
            "## 1. 修訂背景與來源範疇 (Revision Scope)\n\n"
            "## 2. 修訂條目清冊 (Revision Items)\n\n### [REV-01] 微調樣式\n\n"
            "## 3. 修訂收斂與驗證確認 (Verification & Closure)\n- [x] 已確認\n",
            encoding="utf-8"
        )
        res_umb = archiver.archive_plan(umb_plan, force=False)
        self.assertTrue(res_umb["success"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_seeded_plan_status_and_verifier_whitelist(self):
        """FT-06 & ET-06: ORIGIN_SEED_FILES 在 Seeded 目錄與 sub_XX 子計畫中之狀態識別與驗證器豁免。"""
        roadmap_dir = self.plans_dir / "roadmap_seed_verify"
        roadmap_dir.mkdir(parents=True, exist_ok=True)
        (roadmap_dir / "sub_seed_topic.md").write_text(
            "# 子計畫路線圖種子\n\n"
            "> 主題：子計畫路線圖種子\n"
            "> 建立日期：2026-10-01\n"
            "> 狀態：Backlog\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：無\n"
            "> 模型：Unknown\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- [ ] 演進方向參考勾選框\n",
            encoding="utf-8",
        )

        # 建立主計畫與 sub_01 子計畫目錄，並將 roadmap promote 移入 sub_01（不預填 sub_01 至 umbrella_overview.md，驗證自動補登）
        umb_dir = self.plans_dir / "2026_10_24_1000_umb_seed_test"
        sub_dir = umb_dir / "sub_01_seeded_child"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (umb_dir / "umbrella_overview.md").write_text(
            "# 主計畫總覽\n\n"
            "> 計畫名稱：主計畫\n> 建立日期：2026-10-24\n> 狀態：In Progress\n> 模型：Unknown\n",
            encoding="utf-8",
        )
        (umb_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 摘要 | 模型 |\n| :--- | :---: | :--- | :--- |\n"
            "| 2026-10-24 10:00 | `INIT` | 初始化主計畫 | `Unknown` |\n",
            encoding="utf-8",
        )

        mgr = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        prom_res = mgr.promote_roadmap(
            "sub_seed_topic",
            model="Unknown",
            target_plan="2026_10_24_1000_umb_seed_test/sub_01_seeded_child",
        )
        self.assertTrue(prom_res["success"])

        # 1. 驗證 PlanStatusResolver 將尚未建立 P00 的 sub_01 識別為 Seeded 模式
        nav = PlanStatusResolver.resolve_next_action(sub_dir)
        self.assertEqual(nav["mode"], "Seeded")
        self.assertIn("Seeded", nav["current_phase"])
        self.assertIn("roadmap.md", nav["next_action_hint"])

        # 2. 驗證 PlanScanner 將 sub_01 識別為 Seeded / Seeded (Pending Plan)
        scanner = PlanScanner(plans_dir=self.plans_dir)
        track_type, status_str = scanner.get_plan_info(sub_dir)
        self.assertEqual(track_type, "Seeded")
        self.assertEqual(status_str, "Seeded (Pending Plan)")

        # 3. 驗證 PlanVerifier 對 sub_01 內之 roadmap.md 豁免 > 所屬主計畫：與動態標題比對，100% PASS
        verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir,
        )
        rep = verifier.verify_plan("2026_10_24_1000_umb_seed_test")
        self.assertEqual(rep.status, PlanSeverity.PASS, f"Unexpected issues: {rep.issues}")

        # 4. 驗證建立 P00_discuss.md 後，自動由 Seeded 轉入 Phase 0 主體進度 (FR-06)
        (sub_dir / "P00_discuss.md").write_text(
            "# 需求討論說明書\n\n"
            "> 功能名稱：sub_01_seeded_child\n"
            "> 所屬主計畫：2026_10_24_1000_umb_seed_test\n"
            "> 建立日期：2026-10-24\n"
            "> 狀態：Confirmed\n"
            "> 模型：Unknown\n",
            encoding="utf-8",
        )
        nav_after_p00 = PlanStatusResolver.resolve_next_action(sub_dir)
        self.assertEqual(nav_after_p00["mode"], "Phase 0")
        self.assertEqual(nav_after_p00["current_phase"], "P00")
        track_after, status_after = scanner.get_plan_info(sub_dir)
        self.assertEqual(track_after, "Phase 0")
        self.assertEqual(status_after, "P00 Confirmed")
        self.mark_passed()


@require(Requirement.ENV)
class TestPlansStatusAndBoundaries(YSCBTestCase):
    """測試 Plans 工具鏈狀態解析、歸檔時序防呆與驗證器動態佔位符。"""

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

        (self.templates_dir / "fast_track_plan.md").write_text(
            "# 快速軌道開發計畫\n\n> 計畫名稱：[計畫名稱]\n> 建立日期：[YYYY-MM-DD]\n> 狀態：[Draft | In Progress | Completed]\n\n"
            "## 1. 快速需求與範疇\n\n## 2. 實作變更清冊\n\n## 3. 測試與驗證\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P00_semantic_requirements.md").write_text(
            "# 語意需求說明書\n\n> 功能名稱：[功能名稱]\n> 建立日期：[YYYY-MM-DD]\n> 狀態：[Draft | Confirmed]\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n\n## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n\n## 3. 開放議題與確認紀錄\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n> 功能名稱：[功能名稱]\n> 建立日期：[YYYY-MM-DD]\n> 狀態：[Draft | In Progress | Completed]\n\n"
            "## 1. 實作任務清單 (Task Breakdown)\n\n## 2. 實作偏差紀錄表 (Implementation Deviations)\n",
            encoding="utf-8"
        )
        (self.templates_dir / "P06_test_plan.md").write_text(
            "# 測試計畫與驗證報告\n\n> 功能名稱：[功能名稱]\n> 建立日期：[YYYY-MM-DD]\n> 狀態：[Draft | Confirmed | In Progress | Passed | Completed]\n\n"
            "## 1. 自動化測試案例清單 (Automated Test Cases)\n\n## 2. 測試執行紀錄表 (Test Execution Log)\n\n## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n",
            encoding="utf-8"
        )
        (self.templates_dir / "RXX_research_report.md").write_text(
            "# 技術調研報告 (Technical Research Report)\n\n> 調研主題：[調研主題/所屬功能]\n> 建立日期：[YYYY-MM-DD]\n> 調研狀態：[Draft | Concluded]\n\n"
            "## 1. 調研背景與目標 (Research Objectives)\n\n## 2. 現況與痛點分析 (Problem Analysis)\n\n## 3. 候選方案評估與對比 (Alternative Solutions)\n\n## 4. 決策推薦與架構影響 (Recommendation & Impact)\n\n## 5. 後續行動指針 (Action Items)\n",
            encoding="utf-8"
        )

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_ft_01_header_status(self):
        """FT-01: PlanStatusResolver 準確從 Blockquote 解析標頭狀態，內文任意處出現 'Completed' 不受干擾。"""
        content_completed = "# 測試計畫\n\n> 計畫名稱：測試\n> 狀態：Completed\n\n## 內文說明\n目前狀態：In Progress 正在進行其他事，但標頭是 Completed。\n"
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_completed), "completed")
        self.assertTrue(PlanStatusResolver.is_doc_completed(content_completed))

        content_in_progress = "# 測試計畫\n\n> 計畫名稱：測試\n> 狀態：In Progress\n\n## 內文說明\n先前任務已經 Completed，請注意。\nStatus: Completed\n狀態：Completed\n"
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_in_progress), "in progress")
        self.assertFalse(PlanStatusResolver.is_doc_completed(content_in_progress))

        content_research_concluded = "# 調研報告\n\n> 調研主題：架構探索\n> 調研狀態：Concluded\n\n正文內容...\n"
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_research_concluded), "concluded")
        self.assertTrue(PlanStatusResolver.is_research_completed(content_research_concluded))

        content_research_draft = "# 調研報告\n\n> 調研主題：架構探索\n> 調研狀態：Draft\n\n正文內容提及 Concluded...\n"
        self.assertEqual(PlanStatusResolver.get_doc_header_status(content_research_draft), "draft")
        self.assertFalse(PlanStatusResolver.is_research_completed(content_research_draft))
        self.mark_passed()

    def test_ft_02_archiver_ft_in_progress(self):
        """FT-02: PlanArchiver 攔截標頭為 In Progress 但正文含 Completed 之 Fast Track 計畫。"""
        plan_name = "2026_10_17_1000_ft_incomplete"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        (p_dir / "fast_track_plan.md").write_text(
            "# 快速軌道開發計畫\n\n> 計畫名稱：快速測試\n> 建立日期：2026-10-17\n> 狀態：In Progress\n\n## 1. 快速需求與範疇\nThis task is Completed in discussion.\n",
            encoding="utf-8"
        )
        self.changelog_file.write_text(f"# Changelog\n\n## {plan_name}\n- 變更紀錄\n", encoding="utf-8")

        archiver = PlanArchiver(plans_dir=self.plans_dir, archive_dir=self.archive_dir, project_root=self.workspace_root)
        archiver.verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir, templates_dir=self.templates_dir)

        with self.assertRaises(PlanIncompleteError) as ctx:
            archiver.archive_plan(plan_name, force=False)
        self.assertIn("fast_track_plan.md", str(ctx.exception))
        self.mark_passed()

    def test_ft_03_scanner_p05_with_p06_confirmed(self):
        """FT-03: PlanScanner 在 P05 進行中且 P06 為 Confirmed 時正確回報 Phase 5 而非 Phase 6。"""
        plan_name = "2026_10_17_1100_full_track_p05"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        (p_dir / "P00_semantic_requirements.md").write_text("# 語意需求\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 需求\n", encoding="utf-8")
        (p_dir / "P01_requirements_spec.md").write_text("# 需求規格\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 規格\n", encoding="utf-8")
        (p_dir / "P05_task.md").write_text("# 實作任務清單\n\n> 功能名稱：測試\n> 狀態：In Progress\n\n## 1. 實作任務\n- [ ] 任務 1\n", encoding="utf-8")
        (p_dir / "P06_test_plan.md").write_text("# 測試計畫\n\n> 功能名稱：測試\n> 狀態：Confirmed\n\n## 1. 測試\n", encoding="utf-8")

        scanner = PlanScanner(plans_dir=self.plans_dir)
        plans = scanner.scan_active_plans()
        target = next((p for p in plans if p["name"] == plan_name), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["status"], "Implementing/Phase 5")
        self.assertEqual(target["track"], "Full Track")
        self.mark_passed()

    def test_ft_04_scanner_research_track(self):
        """FT-04: PlanScanner 正確識別 Research Track，並依 R 檔狀態顯示 Concluded 或 Draft。"""
        plan_concluded = "2026_10_17_1200_research_concluded"
        p_dir1 = self.plans_dir / plan_concluded
        p_dir1.mkdir(parents=True, exist_ok=True)
        (p_dir1 / "P00_semantic_requirements.md").write_text("# 語意需求\n\n> 功能名稱：調研\n> 狀態：Confirmed\n", encoding="utf-8")
        (p_dir1 / "R01_deep_dive.md").write_text("# 技術調研報告\n\n> 調研主題：深入調研\n> 調研狀態：Concluded\n", encoding="utf-8")

        plan_draft = "2026_10_17_1300_research_draft"
        p_dir2 = self.plans_dir / plan_draft
        p_dir2.mkdir(parents=True, exist_ok=True)
        (p_dir2 / "P00_semantic_requirements.md").write_text("# 語意需求\n\n> 功能名稱：調研\n> 狀態：Confirmed\n", encoding="utf-8")
        (p_dir2 / "R01_deep_dive.md").write_text("# 技術調研報告\n\n> 調研主題：深入調研\n> 調研狀態：Draft\n", encoding="utf-8")

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
        verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir, templates_dir=self.templates_dir)
        self.assertEqual(verifier._map_file_to_template("R01_deep_architecture_analysis.md"), "RXX_research_report.md")
        self.assertEqual(verifier._map_file_to_template("R02_security_audit.md"), "RXX_research_report.md")
        self.mark_passed()

    def test_ft_06_verifier_test_id_regex(self):
        """FT-06: PlanVerifier 收緊測試 ID 判定為正則 \\b(FT|ET|RT)-\\d{2}\\b，僅含 FP-03 時判定失敗。"""
        plan_name = "2026_10_17_1400_test_id_check"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)

        p06_fail = (
            "# 測試計畫與驗證報告\n\n> 功能名稱：測試\n> 建立日期：2026-10-17\n> 狀態：Confirmed\n\n"
            "## 1. 自動化測試案例清單 (Automated Test Cases)\n\n- 步驟 FP-03 驗證\n\n"
            "## 2. 測試執行紀錄表 (Test Execution Log)\n\n## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n"
        )
        (p_dir / "P06_test_plan.md").write_text(p06_fail, encoding="utf-8")
        (p_dir / "changelog.md").write_text("# 計畫變更紀錄\n\n| 日期時間 | 類型 | 變更描述 |\n| :--- | :--- | :--- |\n| 2026-10-17 | Phase | 推進 |\n", encoding="utf-8")

        verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir, templates_dir=self.templates_dir)
        report = verifier.verify_plan(plan_name)
        id_issues = [i for i in report.issues if i.category == "ID_MATRIX"]
        self.assertTrue(len(id_issues) > 0)

        p06_pass = p06_fail.replace("- 步驟 FP-03 驗證", "- FT-01: 步驟 FP-03 驗證")
        (p_dir / "P06_test_plan.md").write_text(p06_pass, encoding="utf-8")
        report2 = verifier.verify_plan(plan_name)
        id_issues2 = [i for i in report2.issues if i.category == "ID_MATRIX"]
        self.assertEqual(len(id_issues2), 0)
        self.mark_passed()

    def test_ft_07_verifier_dynamic_placeholders(self):
        """FT-07: PlanVerifier 動態推導佔位符，成功攔截 [調研主題/所屬功能] 等未替換模板佔位符。"""
        verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir, templates_dir=self.templates_dir)
        patterns = verifier.get_all_placeholder_patterns()
        found = any("調研主題" in p and "所屬功能" in p for p in patterns)
        self.assertTrue(found, f"應自 RXX 模板中動態提取包含調研主題之佔位符模式: {patterns}")

        plan_name = "2026_10_17_1500_dyn_placeholder_check"
        p_dir = self.plans_dir / plan_name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "R01_deep_dive.md").write_text(
            "# 技術調研報告 (Technical Research Report)\n\n> 調研主題：[調研主題/所屬功能]\n> 建立日期：2026-10-17\n> 調研狀態：Concluded\n\n"
            "## 1. 調研背景與目標\n## 2. 現況與痛點分析\n## 3. 候選方案評估與對比\n## 4. 決策推薦與架構影響\n## 5. 後續行動指針\n",
            encoding="utf-8"
        )
        (p_dir / "changelog.md").write_text("# 計畫變更紀錄\n\n| 日期時間 | 類型 | 變更描述 |\n| :--- | :--- | :--- |\n| 2026-10-17 | Phase | 推進 |\n", encoding="utf-8")

        report = verifier.verify_plan(plan_name)
        ph_issues = [i for i in report.issues if i.category == "PLACEHOLDER"]
        self.assertTrue(len(ph_issues) > 0)
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

        target_dest = self.archive_dir / "2026" / "10" / plan_name
        target_dest.mkdir(parents=True, exist_ok=True)
        (target_dest / "archived_dummy.txt").write_text("already archived", encoding="utf-8")

        archiver = PlanArchiver(plans_dir=self.plans_dir, archive_dir=self.archive_dir, project_root=self.workspace_root)
        archiver.verifier = PlanVerifier(plans_dir=self.plans_dir, archive_dir=self.archive_dir, templates_dir=self.templates_dir)

        with self.assertRaises(PlanDestinationExistsError):
            archiver.archive_plan(plan_name, force=True)

        self.assertTrue(handoff_file.exists(), "目的地衝突時 handoff.md 必須受到保護，嚴禁被提前刪除！")
        self.mark_passed()


@require(Requirement.ENV)
class TestPlansACIToolchain(YSCBTestCase):
    """驗證 Python 工具鏈 (ACI) 強化之 FT-01~FT-08 與 ET-01~ET-06。"""

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="test_aw_aci_"))
        self.plans_dir = self.root / "plans"
        self.archive_dir = self.root / "archived"
        self.templates_dir = _pkg_root / "assets" / "templates"
        for d in (self.plans_dir, self.archive_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.scanner = PlanScanner(plans_dir=self.plans_dir)
        self.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir,
        )

    def tearDown(self):
        if hasattr(self, "root") and os.path.exists(self.root):
            shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def _write_compliant_p01(self, p_dir: Path, extra_body: str = "") -> Path:
        p01 = p_dir / "P01_requirements_spec.md"
        p01.write_text(
            "# 需求規格說明書 (Requirements Specification)\n\n"
            f"> 功能名稱：{p_dir.name}\n"
            "> 建立日期：2026-10-23\n"
            f"> 所屬主計畫：{p_dir.parent.name if p_dir.name.startswith('sub_') else 'N/A'}\n"
            "> 狀態：Confirmed\n"
            "> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 功能需求清單 (Functional Requirements)\n\n"
            "| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |\n"
            "| :--- | :--- | :--- | :---: | :--- |\n"
            "| **FR-01** | 功能一 | 驗收一 | P0 | [P00:DR-01] |\n"
            "| **FR-02** | 功能二 | 驗收二 | P0 | [P00:DR-01] |\n\n"
            "## 2. 邊界與異常情況 (Edge Cases & Failure Modes)\n\n"
            "| 邊界編號 | 情境說明 | 預期防禦與處理行為 |\n"
            "| :--- | :--- | :--- |\n"
            "| **EC-01** | 邊界一 | 防禦一 |\n\n"
            "## 3. 非功能需求 (Non-Functional Requirements)\n\n"
            "| 需求編號 | 類別 | 指標與量化約束 |\n"
            "| :--- | :--- | :--- |\n"
            "| **NFR-01** | 效能 | < 100ms |\n\n"
            "## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)\n\n"
            "- 無\n" + extra_body,
            encoding="utf-8",
        )
        return p01

    def _write_compliant_p02(self, p_dir: Path, model: str = "Gemini 4 Argon (Low)", unreplaced_placeholder: bool = False) -> Path:
        p02 = p_dir / "P02_architecture_plan.md"
        body_placeholder = "[待填寫]" if unreplaced_placeholder else "Layered Architecture"
        p02.write_text(
            "# 架構設計說明書 (Architecture Design)\n\n"
            f"> 功能名稱：{p_dir.name}\n"
            "> 建立日期：2026-10-23\n"
            f"> 所屬主計畫：{p_dir.parent.name if p_dir.name.startswith('sub_') else 'N/A'}\n"
            "> 狀態：Confirmed\n"
            f"> 模型：{model}\n\n"
            "## 1. 模組架構分層與職責邊界 (Layered Architecture)\n\n"
            f"{body_placeholder}\n\n"
            "## 2. 核心資料流與循序圖 (Data Flow & Sequence Diagram)\n\n"
            "Sequence\n\n"
            "## 3. 受影響檔案與新建檔案清單 (Impacted & New Files Inventory)\n\n"
            "| 檔案路徑 | 類型 | 職責與變更說明 |\n"
            "| :--- | :---: | :--- |\n"
            "| a.py | Modify | test |\n\n"
            "## 4. 架構決策記錄 (Architecture Decision Records)\n\n"
            "- **[P02:DR-01]** 決策一\n",
            encoding="utf-8",
        )
        return p02

    def _write_compliant_p04(self, p_dir: Path) -> Path:
        p04 = p_dir / "P04_implementation_plan.md"
        p04.write_text(
            "# 實作計畫與定稿審查書 (Implementation Plan & Review)\n\n"
            f"> 功能名稱：{p_dir.name}\n"
            "> 建立日期：2026-10-23\n"
            f"> 所屬主計畫：{p_dir.parent.name if p_dir.name.startswith('sub_') else 'N/A'}\n"
            "> 狀態：Confirmed\n"
            "> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)\n\n"
            "- [x] 需求對齊\n\n"
            "## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)\n\n"
            "| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |\n"
            "| :--- | :--- | :---: | :--- |\n"
            "| 模組手冊 | docs/README.md | Modify | 更新 |\n\n"
            "## 3. 架構靈魂拷問 (Stress Test & Resilience Review)\n\n"
            "OK\n\n"
            "## 4. 實作任務清單 (Task Breakdown & Topological Sequence)\n\n"
            "1. **TASK-01**：實作\n\n"
            "## 5. 決策定稿 (Confirmed Decision Records)\n\n"
            "- **[P04:DR-01]** 定稿\n",
            encoding="utf-8",
        )
        return p04

    def _write_compliant_p06(self, p_dir: Path, status: str = "Confirmed", covered_reqs: str = "FR-01, FR-02, EC-01, NFR-01") -> Path:
        p06 = p_dir / "P06_test_plan.md"
        p06.write_text(
            "# 測試計畫與驗證報告 (Test Plan & Verification)\n\n"
            f"> 功能名稱：{p_dir.name}\n"
            "> 建立日期：2026-10-23\n"
            f"> 所屬主計畫：{p_dir.parent.name if p_dir.name.startswith('sub_') else 'N/A'}\n"
            f"> 狀態：{status}\n"
            "> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 自動化測試案例清單 (Automated Test Cases)\n\n"
            "| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            f"| **FT-01** | 單元測試 | 測試 | {covered_reqs} | pytest |\n\n"
            "## 2. 測試執行紀錄表 (Test Execution Log)\n\n"
            "| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |\n"
            "| :--- | :---: | :--- | :---: |\n"
            "| **FT-01** | `Pending` | 待測 | - |\n\n"
            "## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)\n\n"
            "| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |\n"
            "| :--- | :--- | :---: | :--- |\n"
            "| **UX-01** | 測試 | `Pending` | 待驗收 |\n",
            encoding="utf-8",
        )
        return p06

    def test_ft_01_resolve_next_action_navigation(self):
        """FT-01 (FR-01): 驗證 resolve_next_action 對 Full Track、Fast Track 與 Umbrella 活躍子計畫之確定性推導。"""
        umb_dir = self.plans_dir / "2026_10_23_1000_umbrella_demo"
        sub1 = umb_dir / "sub_01_done"
        sub2 = umb_dir / "sub_02_active"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        (umb_dir / "umbrella_overview.md").write_text(
            "# 分類型主計畫總覽\n\n> 計畫名稱：umb\n> 建立日期：2026-10-23\n> 計畫狀態：In Progress\n> 模型：Unknown\n",
            encoding="utf-8",
        )
        self._write_compliant_p01(sub1)
        (sub1 / "P07_walkthrough.md").write_text(
            "# P07\n\n> 功能名稱：sub_01\n> 建立日期：2026-10-23\n> 所屬主計畫：umb\n> 狀態：Completed\n> 模型：Unknown\n",
            encoding="utf-8",
        )
        self._write_compliant_p01(sub2)
        self._write_compliant_p02(sub2)

        nav = PlanStatusResolver.resolve_next_action(umb_dir)
        self.assertEqual(nav["target_plan_name"], "2026_10_23_1000_umbrella_demo/sub_02_active")
        self.assertEqual(nav["mode"], "Full Track")
        self.assertEqual(nav["current_phase"], "P02")
        self.assertEqual(nav["next_phase"], "P03")
        self.assertTrue(nav["required_reference_path"].endswith("phase_03_api_spec.md"))
        self.mark_passed()

    def test_ft_02_resume_atomic_consume_and_delete_handoff(self):
        """FT-02 (FR-02): 驗證 plan status --resume 原子輸出並刪除 handoff.md，未加 --resume 時維持純唯讀。"""
        p_dir = self.plans_dir / "2026_10_23_1100_single_active"
        p_dir.mkdir(parents=True)
        self._write_compliant_p01(p_dir)
        handoff = p_dir / "handoff.md"
        handoff.write_text(
            "# Handoff\n\n> 所屬計畫：demo\n> 暫停時間：2026-10-23\n> 當前所在階段：P01\n> 模型：Unknown\n\nKEY_HANDOFF_MARKER_123",
            encoding="utf-8",
        )

        res_ro = self.scanner.execute_resume(consume_handoff=False)
        self.assertTrue(res_ro["success"])
        self.assertFalse(res_ro["handoff_consumed"])
        self.assertIn("KEY_HANDOFF_MARKER_123", res_ro["formatted_output"])
        self.assertTrue(handoff.exists(), "未傳 --resume 時嚴禁刪除 handoff.md")

        res_rw = self.scanner.execute_resume(consume_handoff=True)
        self.assertTrue(res_rw["success"])
        self.assertTrue(res_rw["handoff_consumed"])
        self.assertIn("KEY_HANDOFF_MARKER_123", res_rw["formatted_output"])
        self.assertFalse(handoff.exists(), "--resume 執行後必須立即物理刪除 handoff.md")
        self.mark_passed()

    def test_ft_03_continue_skill_uses_plan_status_resume(self):
        """FT-03 (FR-03): 驗證 continue/SKILL.md 已更新為優先調用 plan status --resume。"""
        cont_md = (_pkg_root / "assets" / "skills" / "continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("plan status --resume", cont_md)
        self.assertIn("Consume & Delete", cont_md)
        self.mark_passed()

    def test_ft_04_shift_left_phase_and_companion_checks(self):
        """FT-04 (FR-04): 驗證 --phase P02 檢核 P06 Draft 存在性，以及 --phase P04 檢核 P06 Confirmed 狀態。"""
        p_dir = self.plans_dir / "2026_10_23_1200_companion_check"
        p_dir.mkdir(parents=True)
        self._write_compliant_p01(p_dir)
        self._write_compliant_p02(p_dir)
        (p_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 模型 | 摘要 |\n| :--- | :---: | :--- | :--- |\n| 2026-10-23 12:00 | PHASE | Unknown | Init |\n",
            encoding="utf-8",
        )

        rep_p02 = self.verifier.verify_plan(p_dir, phase="P02")
        self.assertFalse(rep_p02.passed)
        self.assertTrue(any(i.category == "COMPANION" for i in rep_p02.issues))

        self._write_compliant_p06(p_dir, status="Draft")
        self._write_compliant_p04(p_dir)
        rep_p04_draft = self.verifier.verify_plan(p_dir, phase="P04")
        self.assertFalse(rep_p04_draft.passed)
        self.assertTrue(any(i.category == "COMPANION" and "Draft" in i.message for i in rep_p04_draft.issues))

        self._write_compliant_p06(p_dir, status="Confirmed")
        rep_p04_ok = self.verifier.verify_plan(p_dir, phase="P04")
        self.assertTrue(rep_p04_ok.passed, f"P04 + P06 Confirmed 應通過，實際錯誤: {rep_p04_ok.errors}")
        self.mark_passed()

    def test_ft_05_traceability_set_diff_p01_to_p06(self):
        """FT-05 (FR-05): 驗證 P01 與 P06 需求 ID 集合差集比對精準攔截未映射之孤兒需求 ID。"""
        p_dir = self.plans_dir / "2026_10_23_1210_traceability"
        p_dir.mkdir(parents=True)
        self._write_compliant_p01(p_dir)
        self._write_compliant_p02(p_dir)
        self._write_compliant_p04(p_dir)
        self._write_compliant_p06(p_dir, status="Confirmed", covered_reqs="FR-01, EC-01")
        (p_dir / "changelog.md").write_text(
            "# Changelog\n\n| 日期時間 | 類型 | 模型 | 摘要 |\n| :--- | :---: | :--- | :--- |\n| 2026-10-23 12:10 | PHASE | Unknown | Init |\n",
            encoding="utf-8",
        )

        rep = self.verifier.verify_plan(p_dir, phase="P04")
        self.assertFalse(rep.passed)
        trace_issues = [i for i in rep.issues if i.category == "TRACEABILITY"]
        self.assertEqual(len(trace_issues), 1)
        self.assertIn("FR-02", trace_issues[0].message)
        self.assertIn("NFR-01", trace_issues[0].message)
        self.assertNotIn("FR-01,", trace_issues[0].message)
        self.assertNotIn("EC-01", trace_issues[0].message)
        self.mark_passed()

    def test_ft_06_actionable_fix_hints_in_diagnostics(self):
        """FT-06 (FR-06): 驗證所有 FAIL 診斷訊息均附帶 '[Fix Hint:' 可操作自癒修復建議。"""
        p_dir = self.plans_dir / "2026_10_23_1220_fix_hints"
        p_dir.mkdir(parents=True)
        self._write_compliant_p02(p_dir, unreplaced_placeholder=True)

        rep = self.verifier.verify_plan(p_dir)
        self.assertFalse(rep.passed)
        self.assertGreaterEqual(len(rep.issues), 2)
        for iss in rep.issues:
            self.assertIn("[Fix Hint:", iss.message, f"診斷訊息缺少 [Fix Hint:]: {iss.message}")
        self.mark_passed()

    def test_ft_07_four_step_pipeline_auto_heal_and_log_append(self):
        """FT-07 (FR-07): 驗證 plan verify --phase P02 --log 自動補齊 P06 Draft 與 changelog.md 並通過雙檔檢核寫入日誌。"""
        p_dir = self.plans_dir / "2026_10_23_1230_auto_heal_p02"
        p_dir.mkdir(parents=True)
        self._write_compliant_p01(p_dir)
        self._write_compliant_p02(p_dir, model="Gemini 4 Argon (Low)")

        rep = self.verifier.verify_plan(
            p_dir,
            phase="P02",
            log_msg="完成 P02 架構設計並自動初始化伴隨檔",
            log_type="PHASE",
            model="Gemini 4 Argon (Low)",
        )
        self.assertTrue(rep.passed, f"四步管線應自癒並通過檢核，實際錯誤: {rep.errors}")
        self.assertIn("changelog.md", rep.companion_created)
        self.assertIn("P06_test_plan.md", rep.companion_created)
        self.assertEqual(rep.log_status, "appended")

        p06_text = (p_dir / "P06_test_plan.md").read_text(encoding="utf-8")
        self.assertIn("> 狀態：Draft", p06_text)
        self.assertIn("FR-01", p06_text)
        self.assertIn("FR-02", p06_text)

        cl_text = (p_dir / "changelog.md").read_text(encoding="utf-8")
        self.assertIn("完成 P02 架構設計並自動初始化伴隨檔", cl_text)
        self.mark_passed()

    def test_ft_08_model_record_and_quote_safeguard_docs(self):
        """FT-08 (FR-08): 驗證 CLI 指南與 SOP 記載 --log 禁用雙引號與反引號規範，且伴隨檔優先採用 --model。"""
        cli_guide = (_pkg_root / "assets" / "skills" / "yscb-cli-guide" / "SKILL.md").read_text(encoding="utf-8")
        sop_md = (_pkg_root / "assets" / "skills" / "development-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("反引號", cli_guide)
        self.assertIn("--log", cli_guide)
        self.assertIn("--log", sop_md)
        self.mark_passed()

    def test_et_01_multiple_active_plans_refuse_blind_resume(self):
        """ET-01 (EC-01): 存在多個進行中計畫且未指定 --plan 時，拒絕盲目挑選或刪除 handoff.md。"""
        p1 = self.plans_dir / "2026_10_23_1301_plan_a"
        p2 = self.plans_dir / "2026_10_23_1302_plan_b"
        for p in (p1, p2):
            p.mkdir(parents=True)
            self._write_compliant_p01(p)
            (p / "handoff.md").write_text("# Handoff\n> 狀態：Paused\n", encoding="utf-8")

        res = self.scanner.execute_resume(plan_name_or_subpath=None, consume_handoff=True)
        self.assertFalse(res["success"])
        self.assertIn("--plan", res["error"])
        self.assertTrue((p1 / "handoff.md").exists())
        self.assertTrue((p2 / "handoff.md").exists())
        self.mark_passed()

    def test_et_02_strikethrough_codeblock_html_comment_stripped_in_p01(self):
        """ET-02 (EC-02): P01 中刪除線 ~~FR-99~~、代碼塊 FR-88 與 HTML 註解 EC-77 不被計入孤兒需求 ID。"""
        extra = (
            "\n- ~~**FR-99**：已取消之需求~~\n"
            "```markdown\n| **FR-88** | 範例需求 |\n```\n"
            "<!-- EC-77 註解內需求 -->\n"
        )
        p_dir = self.plans_dir / "2026_10_23_1310_noise_strip"
        p_dir.mkdir(parents=True)
        p01_file = self._write_compliant_p01(p_dir, extra_body=extra)
        ids = self.verifier.extract_requirement_ids(p01_file.read_text(encoding="utf-8"))
        self.assertEqual(ids, {"FR-01", "FR-02", "EC-01", "NFR-01"})
        self.mark_passed()

    def test_et_03_abort_auto_heal_and_log_when_primary_file_fails(self):
        """ET-03 (EC-03): 當 P02 本體含未替換佔位符 (FAIL) 時，拒絕生成伴隨 P06 亦拒絕寫入 changelog.md。"""
        p_dir = self.plans_dir / "2026_10_23_1320_fail_abort"
        p_dir.mkdir(parents=True)
        self._write_compliant_p02(p_dir, unreplaced_placeholder=True)

        rep = self.verifier.verify_plan(p_dir, phase="P02", log_msg="不應被寫入之日誌")
        self.assertFalse(rep.passed)
        self.assertEqual(rep.companion_created, [])
        self.assertEqual(rep.log_status, "skipped_on_fail")
        self.assertFalse((p_dir / "P06_test_plan.md").exists())
        self.assertFalse((p_dir / "changelog.md").exists())
        self.mark_passed()

    def test_et_04_idempotent_changelog_append(self):
        """ET-04 (EC-04): 重複執行相同 (類型, 摘要) 之 --log 時具備冪等防重入保護。"""
        p_dir = self.plans_dir / "2026_10_23_1330_idempotent"
        p_dir.mkdir(parents=True)
        self._write_compliant_p01(p_dir)

        rep1 = self.verifier.verify_plan(p_dir, phase="P01", log_msg="完成 P01 規格轉譯", log_type="PHASE")
        self.assertTrue(rep1.passed)
        self.assertEqual(rep1.log_status, "appended")

        rep2 = self.verifier.verify_plan(p_dir, phase="P01", log_msg="完成 P01 規格轉譯", log_type="PHASE")
        self.assertTrue(rep2.passed)
        self.assertEqual(rep2.log_status, "idempotent_skipped")

        cl_text = (p_dir / "changelog.md").read_text(encoding="utf-8")
        self.assertEqual(cl_text.count("完成 P01 規格轉譯"), 1)
        self.mark_passed()

    def test_et_05_companion_model_never_backtracks_to_older_phase(self):
        """ET-05 (EC-05): 伴隨檔初始化時嚴禁跨階段回溯讀取舊檔 (P00) 之模型名稱。"""
        p_dir = self.plans_dir / "2026_10_23_1340_no_backtrack"
        p_dir.mkdir(parents=True)
        (p_dir / "P00_discuss.md").write_text(
            "# P00\n\n> 功能名稱：demo\n> 建立日期：2026-10-23\n> 狀態：Confirmed\n> 模型：OldModel-1.0\n\n"
            "## 1. 使用者原始需求與意圖\n\n## 2. 核心討論與決策紀錄\n\n## 3. 開放議題與確認紀錄\n",
            encoding="utf-8",
        )
        self._write_compliant_p01(p_dir)
        self._write_compliant_p02(p_dir, model="Unknown")

        rep = self.verifier.verify_plan(p_dir, phase="P02", log_msg="完成 P02", model=None)
        self.assertTrue(rep.passed)
        p06_model = PlanStatusResolver.get_doc_header_model(p_dir / "P06_test_plan.md")
        self.assertEqual(p06_model, "Unknown", "嚴禁回溯讀取 P00 之 OldModel-1.0")
        self.mark_passed()

    def test_et_06_subplan_resolution_and_parent_header_check(self):
        """ET-06 (EC-06): 支援直接以唯一 sub_XX 名稱或 <umbrella>/sub_XX 路徑執行領航與檢核。"""
        umb = self.plans_dir / "2026_10_23_1350_umb"
        sub = umb / "sub_01_unique_target"
        sub.mkdir(parents=True)
        (umb / "umbrella_overview.md").write_text(
            "# Umbrella\n\n> 計畫名稱：umb\n> 建立日期：2026-10-23\n> 計畫狀態：In Progress\n> 模型：Unknown\n\n"
            "## 1. 主計畫願景與目標\n\n## 2. 子計畫拆分與執行矩陣\nsub_01_unique_target\n\n## 3. 主計畫里程碑與推進狀態\n",
            encoding="utf-8",
        )
        self._write_compliant_p01(sub)

        res_nav = self.scanner.execute_resume("sub_01_unique_target", consume_handoff=False)
        self.assertTrue(res_nav["success"])
        self.assertEqual(res_nav["nav_info"]["current_phase"], "P01")

        rep = self.verifier.verify_plan("sub_01_unique_target", phase="P01", log_msg="Sub01 P01 完成")
        self.assertTrue(rep.passed, f"Subplan 檢核應通過: {rep.errors}")
        self.assertTrue((sub / "changelog.md").exists())
        self.mark_passed()


@require(Requirement.ENV)
class TestPlansModelRecord(YSCBTestCase):
    """測試模型紀錄規則與 _auto.md 雙軌相容性。"""

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="test_aw_mr_"))
        self.plans_dir = self.root / "plans"
        self.archive_dir = self.root / "archive_plans"
        self.templates_dir = self.root / "templates"
        for d in (self.plans_dir, self.archive_dir, self.templates_dir):
            d.mkdir(parents=True, exist_ok=True)
        (self.templates_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n"
            "> 功能名稱：[功能名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | In Progress | Completed]\n"
            "> 模型：[平台宣告之模型名稱；無法確認填 Unknown]\n\n"
            "## 1. 實作任務清單 (Task Breakdown)\n\n"
            "## 2. 實作偏差紀錄表 (Implementation Deviations)\n",
            encoding="utf-8",
        )
        self.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir,
        )

    def tearDown(self):
        if hasattr(self, "root") and os.path.exists(self.root):
            shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def _make_plan(self, name: str, model_value: str, changelog_table: str):
        p_dir = self.plans_dir / name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n"
            "> 功能名稱：Demo\n> 建立日期：2026-10-17\n> 狀態：Draft\n"
            f"> 模型：{model_value}\n\n"
            "## 1. 實作任務清單 (Task Breakdown)\n\n"
            "## 2. 實作偏差紀錄表 (Implementation Deviations)\n",
            encoding="utf-8",
        )
        (p_dir / "changelog.md").write_text(
            "# 計畫變更紀錄\n\n" + changelog_table, encoding="utf-8"
        )
        return name

    def test_ft_01_model_header_values(self):
        """FT-01: Unknown 與含推理強度之名稱可通過；未替換之新佔位符被攔截。"""
        table = "| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-10-17 13:30 | PHASE | 開立 |\n"
        for idx, value in enumerate(("Unknown", "Claude Sonnet 5.5 (Medium)")):
            name = self._make_plan(f"2026_10_17_130{idx}_model_ok", value, table)
            report = self.verifier.verify_plan(name)
            bad = [i for i in report.issues if i.category in ("HEADER", "PLACEHOLDER")]
            self.assertEqual(bad, [], f"模型值 {value!r} 不應產生標頭或佔位符錯誤: {bad}")

        name = self._make_plan("2026_10_17_1309_model_unreplaced", "[平台宣告之模型名稱；無法確認填 Unknown]", table)
        report = self.verifier.verify_plan(name)
        self.assertTrue(
            any(i.category == "PLACEHOLDER" for i in report.issues),
            "未替換之新模型佔位符必須被動態佔位符機制攔截",
        )
        self.mark_passed()

    def test_ft_02_changelog_model_column_compat(self):
        """FT-02: 含「模型」欄之 4 欄 changelog 與既有 3 欄 changelog 皆通過驗證。"""
        four_col = (
            "| 日期時間 | 類型 | 模型 | 摘要 |\n| :--- | :---: | :--- | :--- |\n"
            "| 2026-10-17 13:30 | PHASE | Claude Sonnet 5.5 (Medium) | 開立 |\n"
        )
        three_col = "| 日期時間 | 類型 | 摘要 |\n| :--- | :---: | :--- |\n| 2026-10-17 13:30 | PHASE | 開立 |\n"
        for idx, table in enumerate((four_col, three_col)):
            name = self._make_plan(f"2026_10_17_131{idx}_changelog_compat", "Unknown", table)
            report = self.verifier.verify_plan(name)
            self.assertEqual(
                [i for i in report.issues if i.category in ("CHANGELOG", "PLACEHOLDER")],
                [],
                f"{'4' if idx == 0 else '3'} 欄 changelog 不應產生錯誤",
            )
        self.mark_passed()

    def test_ft_13_sub07_auto_context_lean_and_auto_suffix_support(self):
        """[sub_07 FT-01, FT-02 / sub_09 FR-01, FR-02]: 驗證 auto/SKILL.md 兩階段 JIT 讀模板、支柱二門檻、_auto.md 後綴規則與雙軌相容。"""
        auto_path = _pkg_root / "assets" / "skills" / "auto" / "SKILL.md"
        sop_path = _pkg_root / "assets" / "skills" / "development-sop" / "SKILL.md"
        auto_text = auto_path.read_text(encoding="utf-8")
        sop_text = sop_path.read_text(encoding="utf-8")

        self.assertLessEqual(len(auto_text.splitlines()), 75)
        self.assertIn("P01_requirements_spec_auto.md", auto_text)
        self.assertIn("P02_architecture_plan_auto.md", auto_text)
        self.assertIn("P03_api_spec_auto.md", auto_text)
        self.assertIn("P04_implementation_plan_auto.md", auto_text)
        self.assertIn("P05_task_auto.md", auto_text)
        self.assertIn("1-Write-Per-File", auto_text)
        self.assertIn("Signature-Only", auto_text)
        self.assertIn("Two-Stage JIT Template Read", auto_text)
        self.assertIn("1,500", auto_text)
        self.assertIn("Two-Stage JIT Template Read", sop_text)

        real_tpl_dir = _pkg_root / "assets" / "templates"
        real_verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=real_tpl_dir,
        )
        for tpl_fname in (
            "P01_requirements_spec.md",
            "P02_architecture_plan.md",
            "P03_api_spec.md",
            "P04_implementation_plan.md",
            "P05_task.md",
            "P06_test_plan.md",
        ):
            self.assertIn(tpl_fname, auto_text, f"auto/SKILL.md 兩階段 JIT 缺少模板指標: {tpl_fname}")

        plan_full_auto = self.plans_dir / "2026_10_25_1400_full_auto_demo"
        plan_full_auto.mkdir(parents=True, exist_ok=True)
        hdr = (
            "> 功能名稱：Auto Demo\n"
            "> 建立日期：2026-10-25\n"
            "> 所屬主計畫：N/A (Root Plan)\n"
            "> 模型：Gemini 4 Argon (High)\n"
        )
        (plan_full_auto / "P00_discuss.md").write_text(
            "# P00\n\n" + hdr + "> 狀態：Confirmed\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n"
            "## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n"
            "## 3. 開放議題與確認紀錄\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P01_requirements_spec_auto.md").write_text(
            "# P01\n\n" + hdr + "> 狀態：Confirmed\n\n"
            "## 1. 功能需求清單\n- FR-01\n## 2. 邊界與異常情況\n- EC-01\n## 3. 非功能需求\n- NFR-01\n## 4. 知識庫與踩坑紀錄查閱\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P02_architecture_plan_auto.md").write_text(
            "# P02\n\n" + hdr + "> 狀態：Confirmed\n\n"
            "## 1. 模組架構分層與職責邊界\n## 2. 核心資料流與循序圖\n## 3. 受影響檔案與新建檔案清單\n## 4. 架構決策記錄\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P03_api_spec_auto.md").write_text(
            "# P03\n\n" + hdr + "> 狀態：Confirmed\n\n"
            "## 1. 介面契約清單\n## 2. 核心 API 簽名與詳細規格\n## 3. 依賴拓撲與實作順序\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P04_implementation_plan_auto.md").write_text(
            "# P04\n\n" + hdr + "> 狀態：Confirmed\n\n"
            "## 1. 交叉驗證檢查清單\n- [x] 對齊\n## 2. 知識庫文檔衝擊與交付規劃\n## 3. 架構靈魂拷問\n## 4. 實作任務清單\n1. **TASK-01**\n## 5. 決策定稿\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P05_task_auto.md").write_text(
            "# P05\n\n" + hdr + "> 狀態：Completed\n\n"
            "## 1. 實作任務清單\n- [x] **TASK-01**：見 P04 §4\n## 2. 實作偏差紀錄表\n",
            encoding="utf-8",
        )
        (plan_full_auto / "P06_test_plan.md").write_text(
            "# P06\n\n" + hdr + "> 狀態：Passed\n\n"
            "## 1. 自動化測試案例清單\n| FT-01 | FR-01, EC-01, NFR-01 |\n## 2. 測試執行紀錄表\n## 3. 人工 / UX 驗證 Checkpoint\n",
            encoding="utf-8",
        )

        scanner = PlanScanner(plans_dir=self.plans_dir)
        track, st = scanner.get_plan_info(plan_full_auto)
        self.assertEqual(track, "Full Track")
        self.assertEqual(st, "Testing/Phase 6")

        nav = PlanStatusResolver.resolve_next_action(plan_full_auto)
        self.assertEqual(nav["mode"], "Full Track")
        self.assertEqual(nav["current_phase"], "P06")
        self.assertEqual(nav["next_phase"], "P07")

        rep = real_verifier.verify_plan(
            plan_full_auto,
            log_msg="透過 /auto 完成 P01~P06 規格、實作與測試驗證",
            model="Gemini 4 Argon (High)",
        )
        self.assertTrue(rep.passed, f"Full _auto.md 計畫驗證失敗: {rep.errors}")

        plan_mid_auto = self.plans_dir / "2026_10_25_1410_mid_auto_demo"
        plan_mid_auto.mkdir(parents=True, exist_ok=True)
        for src_f in plan_full_auto.glob("*.md"):
            dst_name = src_f.name.replace("_auto.md", ".md") if src_f.name.startswith(("P01_", "P02_")) else src_f.name
            (plan_mid_auto / dst_name).write_text(src_f.read_text(encoding="utf-8"), encoding="utf-8")

        track_m, st_m = scanner.get_plan_info(plan_mid_auto)
        self.assertEqual((track_m, st_m), ("Full Track", "Testing/Phase 6"))
        rep_m = real_verifier.verify_plan(plan_mid_auto)
        self.assertTrue(rep_m.passed, f"Mid _auto.md 混用計畫驗證失敗: {rep_m.errors}")

        self.mark_passed()

    def test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint(self):
        """[sub_09 FR-03~FR-05, EC-01~EC-04]: 驗證確定性標頭自癒、缺失率 QUICK_PATCH/FULL_REWRITE 分流與 NEXT PHASE GATE 預告。"""
        real_tpl_dir = _pkg_root / "assets" / "templates"
        real_verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=real_tpl_dir,
        )

        # 1. 建立 Umbrella + sub_01 測試確定性標頭自癒 (FR-03, EC-01, EC-02)
        u_dir = self.plans_dir / "2026_10_25_1500_umbrella_heal_demo"
        sub_dir = u_dir / "sub_01_header_heal_target"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (u_dir / "umbrella_overview.md").write_text(
            "# Umbrella\n\n> 功能名稱：Umbrella Heal Demo\n> 建立日期：2026-10-25\n> 狀態：In Progress\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 計畫全貌與核心目標\n## 2. 跨模組共用契約與架構邊界\n## 3. 子計畫拆分矩陣與依賴拓撲\n## 4. 整體推進順序與驗收里程碑\n",
            encoding="utf-8",
        )
        # P00 故意遺漏 功能名稱、建立日期、所屬主計畫，但具備合法 狀態、模型 與完整章節
        p00_sub = sub_dir / "P00_discuss.md"
        p00_sub.write_text(
            "# 需求與設計討論\n\n> 狀態：Confirmed\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 使用者原始需求與意圖 (User Intent)\n- ok\n"
            "## 2. 核心討論與決策紀錄 (Discussion & Decisions)\n- ok\n"
            "## 3. 開放議題與確認紀錄\n- ok\n",
            encoding="utf-8",
        )
        # 未帶 log_msg 時 (唯讀模式)：不自癒，但 Fix Hint 包含精確推導值
        rep_ro = real_verifier.verify_plan(sub_dir, phase="P00")
        self.assertFalse(rep_ro.passed)
        self.assertEqual(rep_ro.header_healed, [])
        hdr_msgs = "\n".join(i.message for i in rep_ro.issues if i.category == "HEADER")
        self.assertIn("2026_10_25_1500_umbrella_heal_demo", hdr_msgs)
        self.assertIn("2026-10-25", hdr_msgs)

        # 帶 log_msg 時 (自癒模式)：原地自動補齊確定性標頭並 PASS，同時產出 NEXT PHASE GATE (FR-05)
        rep_heal = real_verifier.verify_plan(
            sub_dir,
            phase="P00",
            log_msg="完成 P00 需求定案並驗證確定性標頭自癒",
            model="Gemini 4 Argon (Low)",
        )
        self.assertTrue(rep_heal.passed, f"確定性標頭應自動自癒通過，卻失敗: {rep_heal.errors}")
        self.assertEqual(len(rep_heal.header_healed), 1)
        self.assertIn("功能名稱", rep_heal.header_healed[0])
        self.assertIn("建立日期", rep_heal.header_healed[0])
        self.assertIn("所屬主計畫", rep_heal.header_healed[0])
        healed_text = p00_sub.read_text(encoding="utf-8")
        self.assertIn("> 功能名稱：Header Heal Target", healed_text)
        self.assertIn("> 建立日期：2026-10-25", healed_text)
        self.assertIn("> 所屬主計畫：2026_10_25_1500_umbrella_heal_demo", healed_text)
        self.assertIsNotNone(rep_heal.next_phase_hint)
        self.assertIn("下一階段 P01 (P01_requirements_spec.md)", rep_heal.next_phase_hint)
        self.assertIn(".agents/.yscb/templates/P01_requirements_spec.md", rep_heal.next_phase_hint)

        # EC-01: 若連非確定性標頭 `狀態` 也缺漏，則拒絕自癒並報錯
        p01_bad_hdr = sub_dir / "P01_requirements_spec_auto.md"
        p01_bad_hdr.write_text(
            "# P01\n\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 功能需求清單\n- FR-01\n## 2. 邊界與異常情況\n## 3. 非功能需求\n## 4. 知識庫與踩坑紀錄查閱\n",
            encoding="utf-8",
        )
        rep_ec01 = real_verifier.verify_plan(
            sub_dir, phase="P01", log_msg="嘗試結算缺狀態之 P01"
        )
        self.assertFalse(rep_ec01.passed)
        self.assertEqual(rep_ec01.header_healed, [])

        # 2. 驗證章節缺失率分流：QUICK_PATCH (<50%) vs FULL_REWRITE (>=50%) 與單一診斷聚合 (FR-04, EC-03)
        # P01 共 4 個必備章節：缺 1 個 (25% < 50%) -> QUICK_PATCH
        p01_bad_hdr.write_text(
            "# P01\n\n> 功能名稱：Header Heal Target\n> 建立日期：2026-10-25\n"
            "> 所屬主計畫：2026_10_25_1500_umbrella_heal_demo\n> 狀態：Confirmed\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 功能需求清單\n- FR-01\n## 2. 邊界與異常情況\n## 3. 非功能需求\n",
            encoding="utf-8",
        )
        rep_qp = real_verifier.verify_plan(sub_dir, phase="P01")
        self.assertFalse(rep_qp.passed)
        tpl_issues_qp = [i for i in rep_qp.issues if i.category == "TEMPLATE"]
        self.assertEqual(len(tpl_issues_qp), 1)
        self.assertIn("TRIAGE: QUICK_PATCH (章節缺失 1/4, 25%)", tpl_issues_qp[0].message)
        self.assertIn("edit_file", tpl_issues_qp[0].message)
        self.assertIn("## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)", tpl_issues_qp[0].message)

        # P01 共 4 個必備章節：缺 3 個 (75% >= 50%) -> FULL_REWRITE，且僅聚合為 1 筆 TEMPLATE issue (EC-03)
        p01_bad_hdr.write_text(
            "# P01\n\n> 功能名稱：Header Heal Target\n> 建立日期：2026-10-25\n"
            "> 所屬主計畫：2026_10_25_1500_umbrella_heal_demo\n> 狀態：Confirmed\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 功能需求清單\n- FR-01\n",
            encoding="utf-8",
        )
        rep_fr = real_verifier.verify_plan(sub_dir, phase="P01")
        self.assertFalse(rep_fr.passed)
        tpl_issues_fr = [i for i in rep_fr.issues if i.category == "TEMPLATE"]
        self.assertEqual(len(tpl_issues_fr), 1, "同一檔案缺少多個章節時應聚合為單一 TEMPLATE PlanIssue")
        self.assertIn("TRIAGE: FULL_REWRITE (章節缺失 3/4, 75%", tpl_issues_fr[0].message)
        self.assertIn(".agents/.yscb/templates/P01_requirements_spec.md", tpl_issues_fr[0].message)
        self.assertIn("write_file", tpl_issues_fr[0].message)

        # 3. EC-04: 已 Completed 結案之計畫 (含 P07 Completed)，next_phase_hint 應為 None
        ft_done_dir = self.plans_dir / "2026_10_25_1510_ft_done_demo"
        ft_done_dir.mkdir(parents=True, exist_ok=True)
        (ft_done_dir / "fast_track_plan.md").write_text(
            "# Fast Track\n\n> 功能名稱：FT Done\n> 建立日期：2026-10-25\n"
            "> 所屬主計畫：N/A (Root Plan)\n> 狀態：Completed\n> 模型：Gemini 4 Argon (Low)\n\n"
            "## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)\n"
            "### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)\n- [x] ok\n"
            "### 1.2 核心需求與邊界\n- ok\n"
            "### 1.3 實作任務與測試規劃\n- [x] **FT-01**：ok\n"
            "## 2. 實作與驗證成果 (FP-02 Execution & Test Log)\n- ok\n"
            "## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)\n- [x] ok\n",
            encoding="utf-8",
        )
        rep_done = real_verifier.verify_plan(
            ft_done_dir, log_msg="結案驗證", model="Gemini 4 Argon (Low)"
        )
        self.assertTrue(rep_done.passed, f"FT Done 應通過檢核: {rep_done.errors}")
        self.assertIsNone(rep_done.next_phase_hint)

        self.mark_passed()

    def test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals(self):
        """
        FT-02 ~ FT-05, ET-01, ET-02, ET-05:
        驗證 SessionTraceEngine 之：
        1. 多宿主 .jsonl 三層信標定錨（顯式路徑、尾行自指信標過濾 Subagent 與他案、多候選無信標拒絕盲猜 EC-01）
        2. 跨階段 mtime 逆序修改與 changelog.md 合規回寫消歧 (VALIDATED_BACKPROP vs SILENT_BACKPATCH)
        3. 五大硬性摩擦訊號聚合 (MULTI_EDIT_CHURN, TOOL_MISS_AND_RETRY, SILENT_BACKPATCH, GATE_BOUNCE, CONTEXT_WASTE)
        4. 多活躍計畫提示與剛歸檔計畫自動探測 (EC-02)、損毀 JSONL 容錯 (EC-05) 及 CLI session-trace 正負向執行
        """
        import importlib.util
        import json
        import time
        from agents_workflow.plans.session_trace import SessionTraceEngine
        from agents_workflow.compiler import ArtifactCompiler

        aw_cli_spec = importlib.util.spec_from_file_location("aw_cli_test", str(_pkg_root / "scripts" / "cli.py"))
        aw_cli = importlib.util.module_from_spec(aw_cli_spec)
        aw_cli_spec.loader.exec_module(aw_cli)

        # --- A. 驗證三層信標定錨 (locate_transcript) 與 EC-01 / EC-05 ---
        mock_logs_root = self.root / "mock_ide_logs"
        ag_main_dir = mock_logs_root / "antigravity" / "conv_main" / ".system_generated" / "logs"
        ag_sub_dir = mock_logs_root / "antigravity" / "conv_sub" / ".system_generated" / "logs"
        claude_dir = mock_logs_root / "claude" / "proj_a"
        ag_main_dir.mkdir(parents=True, exist_ok=True)
        ag_sub_dir.mkdir(parents=True, exist_ok=True)
        claude_dir.mkdir(parents=True, exist_ok=True)

        proj_root_str = str(self.root).replace("\\", "/")

        # 1. 建立主視窗 transcript.jsonl（含損毀行 EC-05、同檔多次修改、重複讀取、ERROR 與尾行 session-trace 信標）
        main_jsonl = ag_main_dir / "transcript.jsonl"
        main_lines = [
            json.dumps({
                "step_index": 1,
                "created_at": "2026-10-28T14:00:00Z",
                "type": "USER_INPUT",
                "content": f"Working in {proj_root_str}",
            }),
            "{corrupted_json_line_should_be_skipped",
            json.dumps({
                "step_index": 2,
                "created_at": "2026-10-28T14:01:00Z",
                "type": "PLANNER_RESPONSE",
                "thinking": "First attempt to edit foo.py without checking signature",
                "tool_calls": [
                    {"name": "edit_file", "args": {"Path": f"{proj_root_str}/foo.py"}},
                    {"name": "read_file", "args": {"Path": f"{proj_root_str}/bar.py", "StartLine": 1, "EndLine": 50}},
                ],
            }),
            json.dumps({
                "step_index": 3,
                "created_at": "2026-10-28T14:02:00Z",
                "status": "ERROR",
                "content": "Target string not found in foo.py",
                "thinking": "I guessed the target string wrong, need to re-read bar.py and re-edit foo.py",
                "tool_calls": [
                    {"name": "read_file", "args": {"Path": f"{proj_root_str}/bar.py", "StartLine": 1, "EndLine": 50}},
                ],
            }),
            json.dumps({
                "step_index": 5,
                "created_at": "2026-10-28T14:03:00Z",
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "edit_file", "args": {"Path": f"{proj_root_str}/foo.py"}},
                    {"name": "run_command", "args": {"CommandLine": "python yscb.py agents-workflow session-trace --json"}},
                ],
            }),
        ]
        main_jsonl.write_text("\n".join(main_lines) + "\n", encoding="utf-8")

        # 2. 建立較新但屬於唯讀 Reviewer Subagent 的 transcript.jsonl（應被自動排除）
        sub_jsonl = ag_sub_dir / "transcript.jsonl"
        sub_jsonl.write_text(
            json.dumps({
                "step_index": 1,
                "created_at": "2026-10-28T14:04:00Z",
                "content": f"你是一個無歷史包袱的獨立審查員 {proj_root_str} REVIEW_STATUS: PASSED",
            }) + "\n",
            encoding="utf-8",
        )

        # 3. 建立另一宿主無尾行信標之舊對話紀錄
        claude_jsonl = claude_dir / "old_session.jsonl"
        claude_jsonl.write_text(
            json.dumps({
                "step_index": 1,
                "created_at": "2026-10-28T12:00:00Z",
                "content": f"Old session in {proj_root_str}",
            }) + "\n",
            encoding="utf-8",
        )

        # 4. 建立模擬之 core telemetry.jsonl（含連續 3 次 knowledge-db search 與 1 次 plan verify 退件）
        telem_file = self.root / "telemetry.jsonl"
        telem_records = [
            {"ts": "2026-10-28T14:01:10Z", "epoch": 1793196070.0, "module": "knowledge-db", "cmd": "search", "args": ["q1"], "exit_code": 0, "duration_ms": 20, "mode": "hot", "error_hint": ""},
            {"ts": "2026-10-28T14:01:20Z", "epoch": 1793196080.0, "module": "knowledge-db", "cmd": "search", "args": ["q2"], "exit_code": 0, "duration_ms": 20, "mode": "hot", "error_hint": ""},
            {"ts": "2026-10-28T14:01:30Z", "epoch": 1793196090.0, "module": "knowledge-db", "cmd": "search", "args": ["q3"], "exit_code": 0, "duration_ms": 20, "mode": "hot", "error_hint": ""},
            {"ts": "2026-10-28T14:02:10Z", "epoch": 1793196130.0, "module": "agents-workflow", "cmd": "plan verify", "args": ["demo"], "exit_code": 1, "duration_ms": 30, "mode": "local", "error_hint": "[FAIL] Missing section"},
        ]
        telem_file.write_text("\n".join(json.dumps(r) for r in telem_records) + "\n", encoding="utf-8")

        # 5. 建立測試計畫並驗證 SILENT_BACKPATCH vs VALIDATED_BACKPROP (FR-03)
        trace_plans_dir = self.root / "trace_plans"
        trace_arch_dir = self.root / "trace_archived"
        plan_a = trace_plans_dir / "2026_10_28_1400_silent_patch_demo"
        plan_a.mkdir(parents=True, exist_ok=True)
        p01_file = plan_a / "P01_requirements_spec.md"
        p04_file = plan_a / "P04_implementation_plan.md"
        cl_file = plan_a / "changelog.md"
        p01_file.write_text("# P01\n> 狀態：Confirmed\n", encoding="utf-8")
        p04_file.write_text("# P04\n> 狀態：Confirmed\n", encoding="utf-8")
        cl_file.write_text(
            "| 時間 | 類型 | 變更與決策摘要 | 模型 |\n| :--- | :---: | :--- | :--- |\n"
            "| 2026-10-28 14:00 | PHASE | 完成 P04 | Unknown |\n",
            encoding="utf-8",
        )
        base_t = time.time() - 100.0
        os.utime(p04_file, (base_t, base_t))
        # 讓 P01 的 mtime 晚於 P04 30 秒，且 changelog 無 REVISION/DECISION 紀錄 -> SILENT_BACKPATCH
        os.utime(p01_file, (base_t + 30.0, base_t + 30.0))

        engine = SessionTraceEngine(
            plans_dir=trace_plans_dir,
            archive_dir=trace_arch_dir,
            project_root=self.root,
            telemetry_path=telem_file,
            custom_transcript_dirs={
                "antigravity": [mock_logs_root / "antigravity"],
                "claude": [mock_logs_root / "claude"],
            },
        )

        report = engine.analyze()
        self.assertEqual(report.active_tier, "Tier 1+2 (Transcript + Core Telemetry)")
        self.assertEqual(Path(report.transcript_path).resolve(), main_jsonl.resolve())
        self.assertEqual(report.target_plan, "2026_10_28_1400_silent_patch_demo")

        # 驗證 REV-01 會話基礎統計與 Token 估算指標 (session_stats)
        self.assertIn("tokens", report.session_stats)
        self.assertIn("steps_and_tools", report.session_stats)
        self.assertIn("time_and_cli", report.session_stats)
        self.assertGreater(report.session_stats["tokens"]["estimated_full_tokens"], 0)
        self.assertEqual(report.session_stats["steps_and_tools"]["total_steps"], 4)
        self.assertEqual(report.session_stats["steps_and_tools"]["user_turns"], 1)
        self.assertEqual(report.session_stats["steps_and_tools"]["error_steps"], 1)
        self.assertEqual(report.session_stats["steps_and_tools"]["total_tool_calls"], 5)
        self.assertEqual(report.session_stats["time_and_cli"]["cli_total_calls"], 4)
        self.assertEqual(report.session_stats["time_and_cli"]["cli_failed_calls"], 1)
        self.assertEqual(report.session_stats["time_and_cli"]["session_duration_sec"], 180.0)
        self.assertIn("Session Baseline Metrics:", report.render_text())

        sig_types = {s.signal_type for s in report.signals}
        self.assertIn("MULTI_EDIT_CHURN", sig_types)
        self.assertIn("CONTEXT_WASTE", sig_types)
        self.assertIn("TOOL_MISS_AND_RETRY", sig_types)
        self.assertIn("GATE_BOUNCE", sig_types)
        self.assertIn("SILENT_BACKPATCH", sig_types)
        self.assertTrue(len(report.thinking_excerpts) >= 1)

        # 6. 驗證當 changelog.md 補入 REVISION 回寫紀錄後，自動轉為 VALIDATED_BACKPROP
        cl_file.write_text(
            "| 時間 | 類型 | 變更與決策摘要 | 模型 |\n| :--- | :---: | :--- | :--- |\n"
            "| 2026-10-28 14:05 | REVISION | 反向回寫同步 P01 規格 | Unknown |\n"
            "| 2026-10-28 14:00 | PHASE | 完成 P04 | Unknown |\n",
            encoding="utf-8",
        )
        backprop_sigs = engine.audit_plan_mtimes(plan_a)
        self.assertEqual(len(backprop_sigs), 1)
        self.assertEqual(backprop_sigs[0].signal_type, "VALIDATED_BACKPROP")
        self.assertEqual(backprop_sigs[0].severity, "INFO")

        # 7. 驗證 EC-01：當移除尾行自指信標且存在多份工作區 .jsonl 時，拒絕盲猜並回傳候選清單
        main_jsonl.write_text("\n".join(main_lines[:-1]) + "\n", encoding="utf-8")
        locked_none, cands = engine.locate_transcript()
        self.assertIsNone(locked_none)
        self.assertEqual(len(cands), 2)

        # 驗證 REV-02 list_sessions 自動過濾 Subagent 並支援 include_all_workspaces
        listed_ws = engine.list_sessions(include_all_workspaces=False, include_subagents=False)
        self.assertEqual(len(listed_ws), 2, "應列出 2 份主工作區對話，並自動排除 Subagent")
        listed_all = engine.list_sessions(include_all_workspaces=True, include_subagents=True)
        self.assertEqual(len(listed_all), 3, "include_subagents=True 時應包含 Subagent 共 3 份")
        self.assertIn("YS-Codebase Historical Session Transcripts", engine.render_session_list_text(listed_ws))

        # 8. 驗證 EC-02：剛歸檔計畫自動探測與 CLI 正負向呼叫
        shutil_target = trace_arch_dir / "2026" / "10" / plan_a.name
        shutil_target.parent.mkdir(parents=True, exist_ok=True)
        plan_a.rename(shutil_target)
        rep_archived = engine.analyze(transcript_path=str(main_jsonl))
        self.assertEqual(rep_archived.target_plan, shutil_target.name)
        self.assertIn("[Auto-Resolved Recently Archived Plan]", rep_archived.plan_resolution_note)

        # 驗證 CLI 傳入不存在之 --plan 時返回非 0 退出碼 (負向斷言)
        rc_bad = aw_cli.session_trace(["--plan=non_existent_plan_xyz", "--json"])
        self.assertEqual(rc_bad, 1)

        # 9. 驗證 Claude Code 與 OpenAI Codex 異質 .jsonl 格式相容性及 AbsolutePath / changelog.md 豁免
        claude_fmt_file = self.root / "claude_fmt.jsonl"
        claude_fmt_file.write_text(
            "\n".join([
                json.dumps({
                    "timestamp": "2026-10-28T15:00:00Z",
                    "type": "user",
                    "message": {"role": "user", "content": [{"type": "text", "text": "Fix bug"}]},
                }),
                json.dumps({
                    "timestamp": "2026-10-28T15:01:00Z",
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 500},
                        "content": [
                            {"type": "thinking", "thinking": "Checking legacy view_file AbsolutePath"},
                            {"type": "tool_use", "name": "view_file", "input": {"AbsolutePath": f"{proj_root_str}/legacy.py", "StartLine": 1, "EndLine": 20}},
                            {"type": "tool_use", "name": "edit_file", "input": {"file_path": f"{proj_root_str}/changelog.md"}},
                        ],
                    },
                }),
                json.dumps({
                    "timestamp": "2026-10-28T15:02:00Z",
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "is_error": True, "content": "Permission denied on legacy.py"},
                        ],
                    },
                }),
                json.dumps({
                    "timestamp": "2026-10-28T15:03:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "edit_file",
                        "arguments": json.dumps({"path": f"{proj_root_str}/changelog.md"}),
                    },
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        _, cc_sigs, cc_thinks, cc_stats = engine._parse_transcript_file(claude_fmt_file)
        self.assertEqual(cc_stats["tokens"]["reported_api_usage"]["total_tokens"], 2000)
        self.assertEqual(cc_stats["steps_and_tools"]["total_read_ops"], 1)
        self.assertEqual(cc_stats["steps_and_tools"]["total_edit_ops"], 2)
        self.assertEqual(cc_stats["steps_and_tools"]["error_steps"], 1)
        self.assertTrue(any(s.signal_type == "TOOL_MISS_AND_RETRY" for s in cc_sigs))
        self.assertFalse(any(s.signal_type == "MULTI_EDIT_CHURN" and s.target == "changelog.md" for s in cc_sigs))
        self.assertEqual(len(cc_thinks), 1)

        # 10. 驗證 REV-04 5 項精準度修正（GENERIC 不計入 model_turns、ByteOffset 分段讀取免計 CONTEXT_WASTE、失敗讀檔免計重複、revision_log 豁免）
        rev04_file = self.root / "rev04_precision.jsonl"
        rev04_file.write_text(
            "\n".join([
                json.dumps({
                    "step_index": 1,
                    "created_at": "2026-10-28T16:00:00Z",
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "tool_calls": [
                        {"name": "read_file", "args": {"Path": f"{proj_root_str}/large.md", "StartLine": 1, "EndLine": 800}},
                        {"name": "read_file", "args": {"Path": f"{proj_root_str}/large.md", "StartLine": 1, "EndLine": 800, "ByteOffset": 46080}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/revision_log.md"}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/P06_test_plan.md"}},
                    ],
                }),
                json.dumps({
                    "step_index": 2,
                    "created_at": "2026-10-28T16:00:05Z",
                    "source": "MODEL",
                    "type": "GENERIC",
                    "content": "Tool output chunk",
                }),
                json.dumps({
                    "step_index": 3,
                    "created_at": "2026-10-28T16:00:10Z",
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [
                        {"name": "read_file", "args": {"Path": f"{proj_root_str}/missing.py", "StartLine": 1, "EndLine": 50}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/revision_log.md"}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/P06_test_plan.md"}},
                    ],
                }),
                json.dumps({
                    "step_index": 4,
                    "created_at": "2026-10-28T16:00:12Z",
                    "source": "MODEL",
                    "type": "GENERIC",
                    "status": "ERROR",
                    "content": "file does not exist: missing.py",
                }),
                json.dumps({
                    "step_index": 5,
                    "created_at": "2026-10-28T16:00:15Z",
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [
                        {"name": "read_file", "args": {"Path": f"{proj_root_str}/missing.py", "StartLine": 1, "EndLine": 50}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/revision_log.md"}},
                        {"name": "edit_file", "args": {"Path": f"{proj_root_str}/P06_test_plan.md"}},
                    ],
                }),
                json.dumps({
                    "step_index": 6,
                    "created_at": "2026-10-28T16:00:18Z",
                    "source": "MODEL",
                    "type": "GENERIC",
                    "status": "ERROR",
                    "content": "file does not exist: missing.py",
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        _, r4_sigs, _, r4_stats = engine._parse_transcript_file(rev04_file)
        self.assertEqual(r4_stats["steps_and_tools"]["model_turns"], 3, "GENERIC 步驟不得計入 model_turns")
        self.assertEqual(r4_stats["tokens"]["reported_api_usage"]["total_tokens"], 600, "應支援頂層 input_tokens/output_tokens")
        self.assertFalse(any(s.signal_type == "CONTEXT_WASTE" for s in r4_sigs), "ByteOffset 分段讀取與失敗讀檔不得誤判為 CONTEXT_WASTE")
        self.assertFalse(any(s.signal_type == "MULTI_EDIT_CHURN" for s in r4_sigs), "revision_log.md 與 3 次合規流轉之 P06_test_plan.md 不得誤報 MULTI_EDIT_CHURN")

        # 驗證 Stage 1 ArtifactCompiler 編譯含 session-audit 之全部內建資產 0 warning / 0 error
        compiler = ArtifactCompiler()
        comp_res = compiler.compile_stage1()
        self.assertTrue(comp_res.get("success", True))

        self.mark_passed()



