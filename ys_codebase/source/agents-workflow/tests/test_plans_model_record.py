"""
test_plans_model_record.py — 模型紀錄規則 (Model Record) 之驗證器相容性與資產規則測試。
涵蓋 plans/2026_10_17_1326_model_record_rule_revision 之 FT-01 ~ FT-03。
100% Python Standard Library + YSCB Testing Framework, Zero External Dependencies.
"""

import sys
import tempfile
from pathlib import Path

# 確保模組內部套件可引入
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

from agents_workflow.plans import PlanVerifier

MODEL_PLACEHOLDER = "[平台宣告之模型名稱；無法確認填 Unknown]"

P05_BODY = (
    "## 1. 實作任務清單 (Task Breakdown)\n\n"
    "## 2. 實作偏差紀錄表 (Implementation Deviations)\n"
)


@require(Requirement.ENV)
class TestModelRecordRule(YSCBTestCase):
    """測試模型紀錄規則對 PlanVerifier 與資產原始碼之影響 (FT-01 ~ FT-03)。"""

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="test_aw_model_record_"))
        self.plans_dir = self.root / "plans"
        self.archive_dir = self.root / "archive_plans"
        self.templates_dir = self.root / "templates"
        for d in (self.plans_dir, self.archive_dir, self.templates_dir):
            d.mkdir(parents=True, exist_ok=True)
        # 模板含新佔位符，供動態佔位符推導
        (self.templates_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n"
            "> 功能名稱：[功能名稱]\n"
            "> 建立日期：[YYYY-MM-DD]\n"
            "> 狀態：[Draft | In Progress | Completed]\n"
            f"> 模型：{MODEL_PLACEHOLDER}\n\n" + P05_BODY,
            encoding="utf-8",
        )
        self.verifier = PlanVerifier(
            plans_dir=self.plans_dir,
            archive_dir=self.archive_dir,
            templates_dir=self.templates_dir,
        )

    def _make_plan(self, name: str, model_value: str, changelog_table: str):
        p_dir = self.plans_dir / name
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "P05_task.md").write_text(
            "# 實作任務清單 (Task Breakdown)\n\n"
            "> 功能名稱：Demo\n> 建立日期：2026-10-17\n> 狀態：Draft\n"
            f"> 模型：{model_value}\n\n" + P05_BODY,
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

        name = self._make_plan("2026_10_17_1309_model_unreplaced", MODEL_PLACEHOLDER, table)
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

    def test_ft_03_assets_follow_model_record_rule(self):
        """FT-03: 規範與模板資產採用新規則，且不再含首行／尾行錨點規則。"""
        assets = _pkg_root / "assets"
        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("模型紀錄 (Model Record)", standards)
        self.assertIn("Unknown", standards)
        self.assertIn("嚴禁**從既有計畫檔", standards)
        self.assertNotIn("{model}", standards, "首行／尾行 `> {model}` 規則必須已移除")
        self.assertNotIn("Model Identity Anchor", standards)

        header = (assets / "templates" / "header.md").read_text(encoding="utf-8")
        self.assertIn(MODEL_PLACEHOLDER, header)
        changelog_tpl = (assets / "templates" / "changelog.md").read_text(encoding="utf-8")
        self.assertIn("| 日期時間 | 類型 | 模型 | 摘要 |", changelog_tpl)
        self.assertNotIn("(狀態：`Discussing`)", changelog_tpl)
        self.mark_passed()

    def test_ft_04_sub02_context_init_and_cli_guild_alignment(self):
        """FT-04 (sub_02 FR-01, FR-08): context-init 移除首行模型錨點並對齊權限標籤，yscb-cli-guild 含三級權限定義。"""
        assets = _pkg_root / "assets"
        ctx_init = (assets / "skills" / "context-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("首行強制輸出當前模型識別錨點", ctx_init)
        self.assertIn("Unknown", ctx_init)
        self.assertIn("[SAFE] 自主安全", ctx_init)

        cli_guild = (assets / "skills" / "yscb-cli-guild" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[SAFE] 自主安全", cli_guild)
        self.assertIn("[CONDITIONAL] 階段條件", cli_guild)
        self.assertIn("[GATED] 授權守門", cli_guild)

        sess_analysis = (assets / "skills" / "session-analysis" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[SAFE] 自主安全", sess_analysis)
        self.mark_passed()

    def test_ft_05_sub02_handoff_and_umbrella_lifecycle(self):
        """FT-05 (sub_02 FR-02, FR-03, FR-04): continue/pause handoff 銷毀與子計畫路徑、Umbrella 主從連動與跨軌道清理。"""
        assets = _pkg_root / "assets"
        cont = (assets / "skills" / "continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Consume & Delete", cont)
        self.assertIn("強制立即刪除該已消費之 `handoff.md`", cont)

        pause = (assets / "skills" / "pause" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("sub_{編號}_{名稱}/handoff.md", pause)

        plan_modes = (
            assets / "skills" / "development-sop" / "references" / "plan_modes.md"
        ).read_text(encoding="utf-8")
        self.assertIn("強制刪除原 `fast_track_plan.md`", plan_modes)
        self.assertIn("附掛於既有已結案計畫之修訂觸發熔斷", plan_modes)
        self.assertIn("主從計畫狀態連動規則", plan_modes)

        roadmap_tpl = (assets / "templates" / "roadmap.md").read_text(encoding="utf-8")
        self.assertIn("Completed]", roadmap_tpl)
        self.assertNotIn("全庫歷史物件量化分析", roadmap_tpl)
        self.mark_passed()

    def test_ft_06_sub02_templates_and_verify_ordering(self):
        """FT-06 (sub_02 FR-05, FR-06, FR-07, FR-08): P04/P07 三層 5 列文檔表與無 Checkbox P04 §4，以及 P07/discuss 閉環。"""
        assets = _pkg_root / "assets"
        p00_tpl = (assets / "templates" / "P00_discuss.md").read_text(encoding="utf-8")
        self.assertIn("架構影響範圍", p00_tpl)
        self.assertNotIn("- [ ]", p00_tpl)

        p04_tpl = (assets / "templates" / "P04_implementation_plan.md").read_text(encoding="utf-8")
        self.assertIn("<Category>/README.md", p04_tpl)
        self.assertIn("<Category>/[topic].md", p04_tpl)
        self.assertIn("<Category>/DESIGN_NOTES.md", p04_tpl)
        self.assertIn("微觀註解", p04_tpl)
        self.assertNotIn("- [ ] **TASK-", p04_tpl)
        self.assertIn("1. **TASK-01**", p04_tpl)

        p07_tpl = (assets / "templates" / "P07_walkthrough.md").read_text(encoding="utf-8")
        self.assertIn("<Category>/README.md", p07_tpl)
        self.assertIn("<Category>/[topic].md", p07_tpl)
        self.assertIn("<Category>/DESIGN_NOTES.md", p07_tpl)

        p07_ref = (
            assets / "skills" / "development-sop" / "references" / "phase_07_walkthrough.md"
        ).read_text(encoding="utf-8")
        self.assertIn("步驟 3：執行計畫合規檢核最終守門", p07_ref)

        discuss = (assets / "skills" / "discuss" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("三大範疇裁定出口", discuss)
        self.assertIn("fast_track_plan.md", discuss)
        self.mark_passed()

    def test_ft_07_sub02_restored_lifecycle_assets(self):
        """FT-07 (補齊 2026_10_17_1133 sub_02 遺失資產，FR-03/04/05/06/08): 驗證先前未提交而遺失之資產規範已全數恢復。"""
        assets = _pkg_root / "assets"
        sop_ref = assets / "skills" / "development-sop" / "references"

        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("生命週期工作流", standards)

        new_plan = (assets / "skills" / "new-plan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("phase_00_discuss.md", new_plan)

        research = (assets / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("均須先將 `R{NN}_{topic}.md` 標頭狀態更新為 `Concluded`", research)

        roadmap_skill = (assets / "skills" / "roadmap" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("In Progress | Completed]", roadmap_skill)
        self.assertIn("結案時更新為 `Completed`", roadmap_skill)

        sop = (assets / "skills" / "development-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`umbrella_overview` + `changelog`", sop)
        self.assertIn("落檔預設標頭狀態", sop)

        self.assertIn("Umbrella 子計畫立項登記", (sop_ref / "phase_00_discuss.md").read_text(encoding="utf-8"))
        self.assertIn("Acceptance Criteria", (sop_ref / "phase_01_requirements.md").read_text(encoding="utf-8"))
        self.assertIn("錯誤與例外契約", (sop_ref / "phase_03_api_spec.md").read_text(encoding="utf-8"))
        self.assertIn("Umbrella 子計畫結案回寫", (sop_ref / "phase_07_walkthrough.md").read_text(encoding="utf-8"))

        plan_modes = (sop_ref / "plan_modes.md").read_text(encoding="utf-8")
        self.assertIn("熔斷後舊產物雙軌處置", plan_modes)
        self.assertIn("首個 `sub_XX` 啟動時", plan_modes)

        cont = (assets / "skills" / "continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考", cont)

        auto = (assets / "skills" / "auto" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("(Draft)", auto)
        self.assertIn("一次建立並定稿", auto)

        discuss = (assets / "skills" / "discuss" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("P06_test_plan.md", discuss)

        tpl = assets / "templates"
        self.assertIn("詳細規格與驗收條件 (Acceptance Criteria)", (tpl / "P01_requirements_spec.md").read_text(encoding="utf-8"))
        roadmap_tpl = (tpl / "roadmap.md").read_text(encoding="utf-8")
        self.assertIn("### 1.2 現況與影響範圍評估", roadmap_tpl)
        self.assertIn("## 4. 核心機制與落地步驟", roadmap_tpl)
        for name in ("P07_walkthrough.md", "fast_track_plan.md", "revision_log.md"):
            content = (tpl / name).read_text(encoding="utf-8")
            self.assertLess(content.index("`Completed`"), content.index("plan verify"),
                            f"{name}: 應先更新 Completed 狀態，最後執行 plan verify")
        self.mark_passed()
