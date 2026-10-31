# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_empirical_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1605_code_optimizer_skill  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Revision  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 於 `plans/2026_10_30_1605_code_optimizer_skill` 建立衍生子計畫：實測優化（`sub_01_empirical_optimization`）。
  2. 先落檔母倉實測調研報告於新子計畫：`R01_ys_codebase_report.md`，後續開發者將提供另外兩個下游專案的實測報告作為 `R02` / `R03` 後再一併分析檢視。
- **核心目標**：
  1. 將 `ys-codebase` 母倉於 [`2026_10_30_1641_code_optimize`](../../2026_10_30_1641_code_optimize/umbrella_overview.md) 執行 5 大核心模組（`core`, `dev`, `server`, `knowledge-db`, `agents-workflow`）三代盲審與並行重構（`R01 -> R02 -> R03`）所觀測到的具體摩擦訊號、重構缺陷與過度拆分案例，結構化落檔為 [`R01_ys_codebase_report.md`](./R01_ys_codebase_report.md)。
  2. 預留 `R02` 與 `R03` 調研報告槽位，待開發者提供另外兩個下游專案的實測回饋後，進行跨專案（母倉 + 2 下游）橫向交叉比對，提煉出高泛化性、零過度約束的 `code-optimizer` v1.1 升級規格。
- **邊界排除 (Explicitly Excluded)**：
  - 在尚未接收並綜合檢視 `R02` 與 `R03` 下游實測報告前，暫不直接修改 `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/` 生產源碼，避免僅憑單一母倉視角局部最佳化。
- **架構影響範圍**：
  - 調研階段產物：`plans/2026_10_30_1605_code_optimizer_skill/sub_01_empirical_optimization/{P00_discuss.md,R01_ys_codebase_report.md,changelog.md}`
  - 後續預定升級標的（待 `R01~R03` 會診後拍板）：
    - `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md`
    - `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/exploration-and-delegation.md`
    - `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/diagnostic-matrix.md`
    - `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/refactoring-playbook.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採「多源實測會診（Triangulated Empirical Audit: `R01` 母倉 + `R02/R03` 下游）」模式先行收斂調研報告**：
  - 為確保 `code-optimizer` 的演進同時貼合母倉 Python 模組化基座與不同下游專案架構型態，本子計畫先以 `Research` 軌道啟動，將母倉 `2026_10_30_1641_code_optimize` 的 `/session-audit` 實證數據固化為 `R01_ys_codebase_report.md`。
  - 待 `R02`、`R03` 下游實測報告到位並完成交叉檢視後，再由開發者拍板原地升級為 `Fast Track` 或 `Full Track` 執行技能源碼更新與發布。

---

## 3. 開放議題與確認紀錄

- **[待輸入]** 等待開發者提供另外兩個下游專案之實測報告以建立 `R02` 與 `R03`，並展開跨專案綜合分析。

