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

    def test_ft_04_sub02_context_init_and_cli_guide_alignment(self):
        """FT-04 (sub_02 FR-01, FR-08): context-init 移除首行模型錨點並對齊權限標籤，yscb-cli-guide 含三級權限定義。"""
        assets = _pkg_root / "assets"
        ctx_init = (assets / "skills" / "context-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("首行強制輸出當前模型識別錨點", ctx_init)
        self.assertIn("Unknown", ctx_init)
        self.assertIn("[SAFE] 自主安全", ctx_init)

        cli_guide = (assets / "skills" / "yscb-cli-guide" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[SAFE] 自主安全", cli_guide)
        self.assertIn("[CONDITIONAL] 階段條件", cli_guide)
        self.assertIn("[GATED] 授權守門", cli_guide)
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
        self.assertIn("[Backlog | Proposed | Ready | Deferred]", roadmap_tpl)
        self.assertIn("> 目標範疇：", roadmap_tpl)
        self.assertIn("> 前置解鎖條件：", roadmap_tpl)
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
        self.assertIn("[Backlog | Proposed | Ready | Deferred]", roadmap_skill)
        self.assertIn("Consume-on-Promote", roadmap_skill)
        self.assertIn("roadmap promote", roadmap_skill)

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

    def test_ft_08_sub04_skill_optimizer_and_pure_skills_refinement(self):
        """FT-08 (sub_04 REV-01 & REV-02): 驗證 session-analysis 廢除、skill-optimizer 去特化註冊與全部 12 技能負向邊界合規。"""
        import json
        from agents_workflow.compiler import FENCED_CODE_BLOCK_REGEX, CODE_SPAN_REGEX, UNENCLOSED_TAG_REGEX

        assets = _pkg_root / "assets"
        skills_dir = assets / "skills"
        contrib = json.loads((_pkg_root / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        # 1. session-analysis 必須已完全廢除，skill-optimizer 必須已註冊
        self.assertFalse((skills_dir / "session-analysis").exists())
        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertNotIn("session-analysis", export_names)
        self.assertNotIn("SESSION_ANALYSIS_CHECK_ITEMS", token_names)
        self.assertIn("skill-optimizer", export_names)
        self.assertIn("SKILL_OPTIMIZER_STANDARDS", token_names)

        # 2. 全部 16 個技能皆具備雙軌結構化邊界 (環境攔截型採三段式『觸發情境：/排除情境：』；主動指令型採『僅於顯式輸入』) 與常見踩坑指南 (Gotchas)
        expected_skills = {
            "auto", "context-init", "continue", "development-sop", "discuss",
            "documentation", "how-to-config-yscb", "how-to-yscb", "new-plan",
            "pause", "research", "roadmap", "skill-optimizer", "testing-sop",
            "todo", "yscb-cli-guide",
        }
        command_driven_skills = {
            "auto", "pause", "continue", "context-init", "skill-optimizer",
            "how-to-config-yscb", "how-to-yscb",
        }
        ambient_skills = expected_skills - command_driven_skills
        actual_skills = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        self.assertEqual(actual_skills, expected_skills)

        for s_name in ambient_skills:
            skill_md = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("觸發情境：", skill_md, f"{s_name}/SKILL.md 缺少三段式『觸發情境：』描述")
            self.assertIn("排除情境：", skill_md, f"{s_name}/SKILL.md 缺少三段式『排除情境：』描述")
            self.assertIn("## 常見踩坑指南 (Gotchas)", skill_md, f"{s_name}/SKILL.md 缺少 Gotchas 章節")

        for s_name in command_driven_skills:
            skill_md = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            first_lines = "\n".join(skill_md.splitlines()[:4])
            self.assertIn("僅於顯式輸入", first_lines, f"{s_name}/SKILL.md 缺少主動指令型『僅於顯式輸入』契約")
            self.assertNotIn("(或 /", first_lines, f"{s_name}/SKILL.md description 不應含過度相容大小寫變體")
            self.assertIn("## 常見踩坑指南 (Gotchas)", skill_md, f"{s_name}/SKILL.md 缺少 Gotchas 章節")

        # 3. 驗證 skill-optimizer 及其 references 不含 ys-codebase 內部特化教學 (Zero Specialization Pollution)
        for md_path in (skills_dir / "skill-optimizer").rglob("*.md"):
            text = md_path.read_text(encoding="utf-8")
            self.assertNotIn("不要加反引號", text, f"{md_path.name} 不得含特化錯誤教學")
            self.assertNotIn("compiler.py", text, f"{md_path.name} 不得耦合特定專案內部檔名")

        # 4. 驗證所有技能與參考檔零未包覆反引號之動態標籤 (0 unenclosed tag warnings)
        for md_path in skills_dir.rglob("*.md"):
            text = md_path.read_text(encoding="utf-8")
            clean_text = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", text))
            unenclosed = UNENCLOSED_TAG_REGEX.findall(clean_text)
            self.assertEqual(unenclosed, [], f"{md_path} 存在未以單反引號包覆之語意標籤: {unenclosed}")

        self.mark_passed()

    def test_ft_09_sub03_testing_sop_and_three_pillar_subagent_delegation(self):
        """[sub_03 FR-01 ~ FR-06, EC-01 ~ EC-04, NFR-01]: 驗證 testing-sop 雙層結構、連鎖引用與三支柱 Subagent 隔離協定。"""
        import json

        assets = _pkg_root / "assets"
        skills_dir = assets / "skills"
        sop_ref = skills_dir / "development-sop" / "references"
        contrib = json.loads((_pkg_root / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        # 1. FR-01 & NFR-01: testing-sop/SKILL.md 主檔與 TESTING_SOP_STANDARDS 註冊
        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("testing-sop", export_names)
        self.assertIn("TESTING_SOP_STANDARDS", token_names)

        testing_sop_md = (skills_dir / "testing-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(testing_sop_md.splitlines()), 120)
        for idx in range(1, 7):
            self.assertIn(f"鐵律 {idx}：", testing_sop_md)
        self.assertIn("`__@{TESTING_SOP_STANDARDS}__`", testing_sop_md)
        self.assertIn("references/test_suite_audit_and_purification.md", testing_sop_md)

        # 2. FR-02: 存量測試集體檢與純化參考指南 (T-01 ~ T-06 與三步工作流)
        purify_ref = (
            skills_dir / "testing-sop" / "references" / "test_suite_audit_and_purification.md"
        ).read_text(encoding="utf-8")
        for idx in range(1, 7):
            self.assertIn(f"T-0{idx}", purify_ref)
        self.assertIn("Step 1", purify_ref)
        self.assertIn("Step 2", purify_ref)
        self.assertIn("Step 3", purify_ref)

        # 3. FR-03: AgentsStandards.md 與 development-sop (P04/P05/P06/Fast Track) 連鎖觸發與雙重守門
        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("`testing-sop`", standards)
        self.assertIn("testing-sop", (skills_dir / "development-sop" / "SKILL.md").read_text(encoding="utf-8"))
        for ref_name in ("phase_04_plan.md", "phase_05_task.md", "phase_06_test.md", "plan_modes.md"):
            ref_text = (sop_ref / ref_name).read_text(encoding="utf-8")
            self.assertIn("testing-sop/SKILL.md", ref_text, f"{ref_name} 缺少 testing-sop 強制連鎖引用")
        p06_ref = (sop_ref / "phase_06_test.md").read_text(encoding="utf-8")
        self.assertIn("守門 ①（子系統回歸全綠）", p06_ref)
        self.assertIn("守門 ②", p06_ref)

        # 4. FR-04 & EC-01: 支柱一 (research / discuss 唯讀廣域探索隔離與 150~300 Tokens 約束)
        for s_name in ("research", "discuss"):
            s_text = (skills_dir / s_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("支柱一", s_text)
            self.assertIn("150~300 Tokens", s_text)
            self.assertIn("自動降級", s_text)

        # 5. REV-02: 廢棄 Phase 05 實作隔離委派 (auto / phase_05 由主 Agent 直接執行，無支柱二 2-Strike 委派)
        for doc_text in ((skills_dir / "auto" / "SKILL.md").read_text(encoding="utf-8"),
                         (sop_ref / "phase_05_task.md").read_text(encoding="utf-8")):
            self.assertNotIn("支柱二", doc_text)
            self.assertNotIn("2-Strike Limit", doc_text)
            self.assertNotIn("STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)", doc_text)
            self.assertNotIn("DEVIATION_OR_BLOCKER_NOTE", doc_text)

        # 6. FR-06 & EC-03 & EC-04 & REV-02: 支柱三 (phase_06 Pre-UX 零劇透盲審傳址、純靜態唯讀禁跑測、phase_07 條件式複審、Untracked 防護與三類硬性契約)
        p06_ref = (sop_ref / "phase_06_test.md").read_text(encoding="utf-8")
        self.assertNotIn("支柱二", p06_ref)
        self.assertIn("支柱三", p06_ref)
        self.assertIn("不應告知子代理本次計畫實作內容，僅可提供計畫路徑由子代理進行探索", p06_ref)
        self.assertIn("嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查", p06_ref)
        self.assertIn("Single-Writer", p06_ref)
        self.assertIn("Untracked (??)", p06_ref)
        self.assertIn("git status --short", p06_ref)
        self.assertIn("REVIEW_STATUS: PASSED", p06_ref)
        self.assertIn("自動降級", p06_ref)

        p07_ref = (sop_ref / "phase_07_walkthrough.md").read_text(encoding="utf-8")
        self.assertIn("支柱三", p07_ref)
        self.assertIn("條件式", p07_ref)
        self.assertIn("嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查", p07_ref)

        self.mark_passed()

    def test_ft_10_sub04_onboarding_and_config_coaching_skills(self):
        """[sub_04 FR-01 ~ FR-05, EC-01 ~ EC-04, NFR-01]: 驗證 PROJECT_ROLE_AND_BOUNDARIES、/how-to-config-yscb、/how-to-yscb 與 4 大模組指南。"""
        import json
        from agents_workflow.compiler import FENCED_CODE_BLOCK_REGEX, CODE_SPAN_REGEX, UNENCLOSED_TAG_REGEX

        assets = _pkg_root / "assets"
        skills_dir = assets / "skills"
        source_root = _pkg_root.parent
        contrib = json.loads((_pkg_root / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))

        # 1. FR-01: PROJECT_ROLE_AND_BOUNDARIES 錨點與 context-init 導引
        export_names = {item.get("name") for item in contrib["export"] if "name" in item}
        token_names = {item["value"] for item in contrib["token"]}
        self.assertIn("how-to-config-yscb", export_names)
        self.assertIn("how-to-yscb", export_names)
        self.assertIn("PROJECT_ROLE_AND_BOUNDARIES", token_names)
        self.assertIn("HOW_TO_CONFIG_MODULES", token_names)
        self.assertIn("HOW_TO_YSCB_MODULES", token_names)

        standards = (assets / "standards" / "AgentsStandards.md").read_text(encoding="utf-8")
        self.assertIn("`__@{PROJECT_ROLE_AND_BOUNDARIES}__`", standards)
        self.assertLess(
            standards.index("`__@{PROJECT_ROLE_AND_BOUNDARIES}__`"),
            standards.index("## 1. 核心原則"),
        )

        ctx_init = (skills_dir / "context-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("專案角色與主客體空間邊界", ctx_init)
        self.assertIn("/how-to-yscb", ctx_init)
        self.assertIn("/how-to-config-yscb", ctx_init)

        # 2. FR-02 & EC-01 & EC-02: /how-to-config-yscb 四步閉環、全綠短路、三位一體對齊與動態二層物化路徑解析
        config_skill = (skills_dir / "how-to-config-yscb" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`__@{HOW_TO_CONFIG_MODULES}__`", config_skill)
        self.assertIn("All-Green Short-Circuit", config_skill)
        self.assertIn("First-Party Trinity Alignment", config_skill)
        self.assertIn("paths.plans", config_skill)
        self.assertIn("release_targets", config_skill)
        self.assertIn("projections", config_skill)
        self.assertIn("嚴禁硬編碼 `.agents/` 或 `.claude/`", config_skill)
        self.assertIn("① 開發者角色與專案使命", config_skill)
        self.assertIn("② 本體業務空間", config_skill)
        self.assertIn("③ 外部工具包與黑盒依賴", config_skill)
        self.assertIn("config.project.json", config_skill)
        self.assertIn("config.local.json", config_skill)
        self.assertIn("contributes check", config_skill)
        self.assertIn("agents-workflow compile", config_skill)
        self.assertIn("agents-workflow release", config_skill)

        # 3. FR-03 & EC-03 & EC-04: /how-to-yscb 資深教練角色切換、雙入口領航 (角度 A~D)、兩階段知識調度與純唯讀教練護欄
        howto_skill = (skills_dir / "how-to-yscb" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`__@{HOW_TO_YSCB_MODULES}__`", howto_skill)
        self.assertIn("Coach / Mentor Persona", howto_skill)
        self.assertIn("你想從什麼角度了解這套工具？", howto_skill)
        self.assertIn("角度 A（全景與起手式）", howto_skill)
        self.assertIn("角度 B（以任務找武器）", howto_skill)
        self.assertIn("角度 C（已安裝模組探索）", howto_skill)
        self.assertIn("角度 D（進階技巧與客製化）", howto_skill)
        self.assertIn("/skill-creator", howto_skill)
        self.assertIn("/skill-optimizer", howto_skill)
        self.assertIn("入口 A", howto_skill)
        self.assertIn("入口 B", howto_skill)
        self.assertIn("兩階段漸進式知識調度", howto_skill)
        self.assertIn("/how-to-config-yscb", howto_skill)
        self.assertIn("開啟一個全新的對話視窗", howto_skill)

        # 4. FR-04 & NFR-01: 檢查 4 大模組 (core, dev, server, knowledge-db) 若存在於同級目錄時之三要素指南結構、行數與單反引號語法
        for mod_name in ("core", "dev", "server", "knowledge-db"):
            mod_dir = source_root / mod_name
            if not mod_dir.is_dir():
                continue
            mod_contrib = json.loads((mod_dir / "contributes" / "agents-workflow.json").read_text(encoding="utf-8"))
            inserted_tokens = {ins.get("token") for ins in mod_contrib.get("insert", [])}
            self.assertIn("HOW_TO_CONFIG_MODULES", inserted_tokens, f"{mod_name} 未註冊 HOW_TO_CONFIG_MODULES")
            self.assertIn("HOW_TO_YSCB_MODULES", inserted_tokens, f"{mod_name} 未註冊 HOW_TO_YSCB_MODULES")

            for guide_name in ("config_guide.md", "usage_guide.md"):
                g_path = mod_dir / "assets" / guide_name
                self.assertTrue(g_path.is_file(), f"缺少 {g_path}")
                g_text = g_path.read_text(encoding="utf-8")
                self.assertTrue(10 <= len(g_text.splitlines()) <= 25, f"{g_path} 行數 ({len(g_text.splitlines())}) 超出 15~25 行預算")
                self.assertIn(f"(`__#{{module://{mod_name}/README.md}}__`)", g_text)
                if guide_name == "config_guide.md":
                    self.assertIn("① 組態項目與用途", g_text)
                    self.assertIn("② 健康度檢查條件", g_text)
                    self.assertIn("③ 隨包設定手冊語意連結", g_text)
                else:
                    self.assertIn("① 模組定位與適用時機", g_text)
                    self.assertIn("② 標準用法速查 (Golden Recipes)", g_text)
                    self.assertIn("③ 隨包手冊語意連結", g_text)
                clean_g = CODE_SPAN_REGEX.sub("", FENCED_CODE_BLOCK_REGEX.sub("", g_text))
                self.assertEqual(UNENCLOSED_TAG_REGEX.findall(clean_g), [], f"{g_path} 含有未包覆單反引號之標籤")

        self.mark_passed()


