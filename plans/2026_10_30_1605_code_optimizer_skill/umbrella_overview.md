# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 計畫狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：建立並持續打磨 `agents-workflow` 標準技能體系中之 [`code-optimizer`](../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md)，使其不僅具備五維度靜態診斷（`D1~D5`）與六大無損重構策略（`S1~S6`），更能透過母倉與多個下游專案的真實全模組實戰驗證，收斂消除「半調子 `S2` 轉發殼層」、「`D1/S6` 行數教條過度拆分」、「`S3` 合併遺失邊界不變量」與「審計工單編號污染源碼註解」等實戰摩擦。
- **架構邊界**：
  - 根目錄已完成 `code-optimizer` v1.0 技能包首發建置、Stage 1 `CODE_OPTIMIZER_STANDARDS` 錨點與 Stage 2 宿主工具投影對接（`P00` ~ `P07` 已結案）。
  - 衍生子計畫 `sub_01_empirical_optimization` 負責彙整母倉（`R01`）與另外兩個下游專案（`R02`、`R03`）之實測回饋報告，進行跨專案綜合診斷與 `code-optimizer` 技能規範升級。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **Root** | `.` (`P00`~`P07`) | Full Track | `Completed` | `code-optimizer` 技能包初始架構設計、漸進式揭露資產、Stage 1/2 編譯錨點與雙盲測試驗收 |
| **sub_01** | `sub_01_empirical_optimization` | Revision | `Completed` | 彙整母倉 (`R01`) 與兩個下游專案 (`R02`/`R03`) 之實測優化報告，修訂升級 `code-optimizer` 技能規範與三層多軌代理執行模式，抽離並正交拆分 `CodeQualityStandards.md`、`SkillDesignStandards.md`、`YscbSkillDesignToolStandards.md` 三大中央標準，完成全生態系 22 個技能 `A1 + B2` 聚合精簡與 `SKILL.md` Frontmatter `description` 單一真理來源 (`[REV-01]` ~ `[REV-06]`) |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (Root Plan)**：完成 `code-optimizer` 核心技能包（`SKILL.md` + 3 份 `references/`）建置、編譯註冊與 `P07` 結案驗證
- [x] **里程碑 2 (`sub_01` 實測調研彙整)**：完成 `R01_ys_codebase_report.md` 母倉實測報告落檔，並結合下游 `R02` / `R03` 實測報告進行跨專案綜合檢視與升級方案定錨
- [x] **里程碑 3 (`sub_01` 技能優化與雙中央標準落地)**：依綜合調研結論升級 `code-optimizer`、抽離 `CodeQualityStandards.md` / `SkillDesignStandards.md` 並整合進 `development-sop`，通過全套回歸與編譯驗證

