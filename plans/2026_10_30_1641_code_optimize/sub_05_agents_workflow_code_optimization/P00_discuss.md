# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `agents-workflow` 模組（`ys_codebase/source/agents-workflow/`）派送 2 個獨立子代理（Auditor A / Auditor B）依 `/code-optimizer` 技能與 `Mode A（新功能收斂期 / 可破壞性變更）` 規則執行業務代碼五維度靜態診斷，分別於本目錄落檔 `R01_A_code_optimization_audit.md` 與 `R02_B_code_optimization_audit.md`。
- **核心目標**：
  1. 依包含式範圍階層（`單一模組 ⊃ 單一檔案`）全面盤點 `ys_codebase/source/agents-workflow/agents_workflow/` 與 `ys_codebase/source/agents-workflow/scripts/` 下所有業務程式碼（排除 `tests/` 與純靜態 `assets/` Markdown 模板）。
  2. 依 `Mode A` 零容忍清除標準，徹查薄轉發層、相容別名、廢棄參數與 0 調用死代碼，並對巨型類別與長函式擬定 `S1` 業務階段拆解與 `S2` 無狀態邏輯剝離處方。
  3. 透過 A / B 雙份獨立報告交叉比對審閱品質與收斂度。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段嚴禁修改任何生產程式碼與測試程式碼，僅產出 `R01_A` 與 `R02_B` 調研報告。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/` 與 `ys_codebase/source/agents-workflow/scripts/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 檢視範圍與生命週期定錨（`Module Scope: agents-workflow` × `Mode A`）**：
  - 鎖定 `ys_codebase/source/agents-workflow/` 單一模組範圍（含各單檔微觀 `S1/S2` 拆解）與 `Mode A` 可破壞性變更模式。
- **[P00:DR-02] 雙軌盲測獨立落檔與單一正統 `R01` 收斂**：
  - 先由 Auditor A / Auditor B 獨立盲測產出 `R01_A` 與 `R02_B`，驗證雙軌共識後合併收斂為單一正統 `R01_code_optimization_audit.md` 並移除暫存分檔。

---

## 3. 開放議題與確認紀錄

- 已完成 `R01_A` 與 `R02_B` 合併收斂為單一正統 `R01_code_optimization_audit.md`，待開發者裁決流轉出口。

