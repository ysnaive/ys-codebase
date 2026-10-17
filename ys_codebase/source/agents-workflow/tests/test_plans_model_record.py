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
        self.mark_passed()

