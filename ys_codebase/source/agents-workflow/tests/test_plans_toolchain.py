"""
test_plans_toolchain.py — agents-workflow 模組內部 Plans 工具鏈與 PlanVerifier 完整單元測試。
涵蓋 FT-01~07 與 ET-01~02 檢核維度。
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

    # =========================================================================
    # sub_02: 雙層儲備 (Roadmap & TODO) 與 Seeded 白名單生命週期測試
    # =========================================================================

    @require(Requirement.LOGIC)
    def test_todo_add_and_monotonic_id(self):
        """FT-01 & ET-04: todo add 免讀盲寫追加與 > 最後分配編號：N 單調遞增防碰撞。"""
        roadmap_dir = self.plans_dir / "roadmap"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        r1 = mgr.add_todo(title="清理 compiler 死代碼", scope="agents-workflow", note="來自 sub_02")
        self.assertEqual(r1.todo_id, "TODO-01")

        r2 = mgr.add_todo(title="補充 CLI 範例", scope="core", note="補充文檔")
        self.assertEqual(r2.todo_id, "TODO-02")

        # 檢查標頭 > 最後分配編號：2
        content = mgr.todo_file.read_text(encoding="utf-8")
        self.assertIn("> 最後分配編號：2", content)

        # Pop 提取全部條目清空帳本後，再次 add_todo 必須從 TODO-03 開始，不可碰撞 TODO-01
        pop_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-02"],
            slug="cleanup_batch",
            model="Unknown",
        )
        self.assertTrue(pop_res["success"])
        self.assertEqual(len(mgr.list_todos()), 0)

        # 驗證 normalize_todo_id 正規化契約 ([P03:DR-01])
        self.assertEqual(TodoManager.normalize_todo_id("1"), "TODO-01")
        self.assertEqual(TodoManager.normalize_todo_id("todo-2"), "TODO-02")
        self.assertEqual(TodoManager.normalize_todo_id("[TODO-03]"), "TODO-03")
        self.assertIsNone(TodoManager.normalize_todo_id("invalid"))

        r3 = mgr.add_todo(title="提取清空後之新條目", scope="global", note="驗證單調遞增")
        self.assertEqual(r3.todo_id, "TODO-03")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_todo_list_and_scope_filter(self):
        """FT-02 & ET-01: todo list 空帳本優雅返回與 --scope 過濾。"""
        roadmap_dir = self.plans_dir / "roadmap_empty"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        # ET-01: 尚未建立 TODO.md 時不報錯且不寫檔
        self.assertEqual(mgr.list_todos(), [])
        self.assertIn("目前尚無活躍之輕量待辦項目", mgr.format_todo_table())
        self.assertFalse(mgr.todo_file.exists())

        mgr.add_todo(title="Item A", scope="agents-workflow", note="TechDebt")
        mgr.add_todo(title="Item B", scope="knowledge-db", note="Polish")
        mgr.add_todo(title="Item C", scope="agents-workflow", note="Idea")

        aw_items = mgr.list_todos(scope_keyword="agents-workflow")
        self.assertEqual(len(aw_items), 2)
        polish_items = mgr.list_todos(scope_keyword="Polish")
        self.assertEqual(len(polish_items), 1)
        self.assertEqual(polish_items[0].todo_id, "TODO-02")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_todo_promote_batch_and_seeded_dir(self):
        """FT-03, ET-02 & ET-03: todo promote 批次原子提取、ID/slug 防呆與 todo.md 種子生成。"""
        roadmap_dir = self.plans_dir / "roadmap_batch"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        mgr.add_todo(title="Task 1", scope="core", note="TechDebt")
        mgr.add_todo(title="Task 2", scope="core", note="Polish")
        mgr.add_todo(title="Task 3", scope="core", note="Doc")

        # ET-02: 包含不存在的 TODO-99 時強制阻斷且不修改原檔
        bad_id_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-99"],
            slug="valid_slug",
        )
        self.assertFalse(bad_id_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        # ET-03: 非法 slug 強制阻斷
        bad_slug_res = mgr.promote_todos(
            todo_ids=["TODO-01"],
            slug="Invalid-Slug!",
        )
        self.assertFalse(bad_slug_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        # FT-03: 正常打包提取 TODO-01 與 TODO-03
        ok_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-03"],
            slug="core_cleanup_batch",
            model="Unknown",
        )
        self.assertTrue(ok_res["success"])
        remaining = mgr.list_todos()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].todo_id, "TODO-02")

        seed_dir = Path(ok_res["plan_dir"])
        self.assertTrue((seed_dir / "todo.md").is_file())
        self.assertTrue((seed_dir / "changelog.md").is_file())
        todo_seed_text = (seed_dir / "todo.md").read_text(encoding="utf-8")
        self.assertIn("TODO-01", todo_seed_text)
        self.assertIn("TODO-03", todo_seed_text)
        self.assertNotIn("TODO-02", todo_seed_text)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_roadmap_status_filter_and_exclude_todo(self):
        """FT-04: RoadmapManager 自動排除 TODO.md 並支援 --status 過濾與擴充欄位解析。"""
        roadmap_dir = self.plans_dir / "roadmap_filter"
        roadmap_dir.mkdir(parents=True, exist_ok=True)

        (roadmap_dir / "TODO.md").write_text("# 專案輕量待辦清單\n> 狀態：Active\n", encoding="utf-8")
        (roadmap_dir / "topic_ready.md").write_text(
            "# 路線圖 A\n\n"
            "> 主題：路線圖 A\n"
            "> 建立日期：2026-10-20\n"
            "> 狀態：Ready\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：完成 sub_01\n"
            "> 模型：Unknown\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：需要自動晉升機制。\n",
            encoding="utf-8",
        )
        (roadmap_dir / "topic_deferred.md").write_text(
            "# 路線圖 B\n\n"
            "> 主題：路線圖 B\n"
            "> 建立日期：2026-10-21\n"
            "> 狀態：Deferred\n"
            "> 目標範疇：core\n"
            "> 前置解鎖條件：無\n"
            "> 模型：Unknown\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：延後評估。\n",
            encoding="utf-8",
        )

        mgr = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        all_items = mgr.scan_roadmaps()
        self.assertEqual(len(all_items), 2)
        filenames = [it.filename for it in all_items]
        self.assertNotIn("TODO.md", filenames)

        ready_items = mgr.scan_roadmaps(status_filter="Ready")
        self.assertEqual(len(ready_items), 1)
        self.assertEqual(ready_items[0].filename, "topic_ready.md")
        self.assertEqual(ready_items[0].scope, "agents-workflow")
        self.assertEqual(ready_items[0].trigger, "完成 sub_01")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_roadmap_promote_physical_move_and_model_isolation(self):
        """FT-05 & ET-05: roadmap promote 物理移轉 (Consume-on-Promote)、模型防回溯與防呆攔截。"""
        roadmap_dir = self.plans_dir / "roadmap_promote_test"
        roadmap_dir.mkdir(parents=True, exist_ok=True)

        (roadmap_dir / "TODO.md").write_text("# 專案輕量待辦清單\n", encoding="utf-8")
        src_roadmap = roadmap_dir / "future_arch.md"
        src_roadmap.write_text(
            "# 未來架構藍圖\n\n"
            "> 主題：未來架構藍圖\n"
            "> 建立日期：2026-09-01\n"
            "> 狀態：Ready\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：無\n"
            "> 模型：HistoricalOldModel-v1\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：跨模組解耦。\n",
            encoding="utf-8",
        )

        mgr = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        # ET-05: 禁止對 TODO.md 或不存在的主題執行 roadmap promote
        todo_err = mgr.promote_roadmap("TODO")
        self.assertFalse(todo_err["success"])
        missing_err = mgr.promote_roadmap("non_existent")
        self.assertFalse(missing_err["success"])

        # FT-05: 正常執行物理移轉，傳入當輪 --model "CurrentSessionModel"
        res = mgr.promote_roadmap(
            "future_arch",
            model="CurrentSessionModel",
        )
        self.assertTrue(res["success"])
        self.assertFalse(src_roadmap.exists())

        plan_dir = Path(res["plan_dir"])
        moved_roadmap = plan_dir / "roadmap.md"
        companion_changelog = plan_dir / "changelog.md"
        self.assertTrue(moved_roadmap.is_file())
        self.assertTrue(companion_changelog.is_file())

        # 驗證模型防回溯：roadmap.md 保留 HistoricalOldModel-v1，而 changelog.md 記載 CurrentSessionModel
        self.assertIn("> 模型：HistoricalOldModel-v1", moved_roadmap.read_text(encoding="utf-8"))
        cl_text = companion_changelog.read_text(encoding="utf-8")
        self.assertIn("CurrentSessionModel", cl_text)
        self.assertNotIn("HistoricalOldModel-v1", cl_text)

        # 測試模糊匹配多個檔案時之阻斷保護 (EC-04)
        (roadmap_dir / "ambig_one.md").write_text("# 模糊一\n> 主題：模糊一\n> 歸檔日期：2026-09-01\n> 狀態：Backlog\n", encoding="utf-8")
        (roadmap_dir / "ambig_two.md").write_text("# 模糊二\n> 主題：模糊二\n> 歸檔日期：2026-09-02\n> 狀態：Backlog\n", encoding="utf-8")
        ambig_err = mgr.promote_roadmap("ambig")
        self.assertFalse(ambig_err["success"])
        self.assertIn("同時匹配多個路線圖檔案", ambig_err["error"])
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


