"""
test_plans_aci_toolchain.py — Agents-Workflow Python 工具鏈 (ACI) 強化與狀態機下沉單元與邊界測試。
涵蓋 sub_01_python_aci_toolchain 之 FT-01 ~ FT-08 與 ET-01 ~ ET-06。
100% Python Standard Library + YSCB Testing Framework, Zero External Dependencies.
"""

import sys
import tempfile
from pathlib import Path

_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

from agents_workflow.plans import (
    PlanStatusResolver,
    PlanScanner,
    PlanVerifier,
    PlanSeverity,
)


@require(Requirement.ENV)
class TestPlansACIToolchain(YSCBTestCase):
    """驗證 sub_01 Python 工具鏈 (ACI) 強化之 FT-01~FT-08 與 ET-01~ET-06。"""

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
        # 1. Umbrella 含已完成 sub_01 與進行中 sub_02
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

        # 1. 未傳 consume_handoff (唯讀模式)：不刪除 handoff.md
        res_ro = self.scanner.execute_resume(consume_handoff=False)
        self.assertTrue(res_ro["success"])
        self.assertFalse(res_ro["handoff_consumed"])
        self.assertIn("KEY_HANDOFF_MARKER_123", res_ro["formatted_output"])
        self.assertTrue(handoff.exists(), "未傳 --resume 時嚴禁刪除 handoff.md")

        # 2. 傳入 consume_handoff=True (--resume)：印出內容並立即 unlink
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

        # P02 存在但無 P06_test_plan.md (且未傳 --log 自癒) -> 應報 COMPANION FAIL
        rep_p02 = self.verifier.verify_plan(p_dir, phase="P02")
        self.assertFalse(rep_p02.passed)
        self.assertTrue(any(i.category == "COMPANION" for i in rep_p02.issues))

        # 建立 P06 (Draft) 與 P04 -> 檢核 P04 時因 P06 仍為 Draft 應報 COMPANION FAIL
        self._write_compliant_p06(p_dir, status="Draft")
        self._write_compliant_p04(p_dir)
        rep_p04_draft = self.verifier.verify_plan(p_dir, phase="P04")
        self.assertFalse(rep_p04_draft.passed)
        self.assertTrue(any(i.category == "COMPANION" and "Draft" in i.message for i in rep_p04_draft.issues))

        # 將 P06 改為 Confirmed -> P04 檢核應 PASS
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
        # P06 僅映射 FR-01 與 EC-01，遺漏 FR-02 與 NFR-01
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

        # 目錄初始無 changelog.md 亦無 P06_test_plan.md
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

        rep = self.verifier.verify_plan(
            p_dir,
            phase="P02",
            log_msg="不應被寫入之日誌",
        )
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
        # P00 標頭為 OldModel-1.0，而 P02 標頭為 Unknown
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

        # 直接傳入唯一子計畫名稱 'sub_01_unique_target'
        res_nav = self.scanner.execute_resume("sub_01_unique_target", consume_handoff=False)
        self.assertTrue(res_nav["success"])
        self.assertEqual(res_nav["nav_info"]["current_phase"], "P01")

        rep = self.verifier.verify_plan("sub_01_unique_target", phase="P01", log_msg="Sub01 P01 完成")
        self.assertTrue(rep.passed, f"Subplan 檢核應通過: {rep.errors}")
        self.assertTrue((sub / "changelog.md").exists())
        self.mark_passed()
