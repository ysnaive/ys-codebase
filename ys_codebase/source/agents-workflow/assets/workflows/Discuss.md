`__@{DYNAMIC_CONTEXT_MAP}__`

# 深度歸因與防淺層修復工作流 (Discuss)

本 Workflow 是開發過程中（特別是 Phase 5 實作與 Phase 6 測試）遇到非預期錯誤、測試失敗、或範疇越界時的**「強制停手與深度歸因機制」**，旨在杜絕 LLM 盲目亂槍打鳥式的淺層修補。所有階段的執行規範請嚴格遵循 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 觸發條件 (Triggers)

當發生以下任一情況時，Agent **必須立即停止編寫或修改任何原始碼**，主動發起本流程：

1. **修改範疇越界 (Out-of-Scope)**：
   - 排查或修復問題時，發現需要修改**非本次 Dev Plan 承諾範圍的外部檔案/模組**。
2. **連續修復失敗 (Anti-Trial-and-Error Loop)**：
   - 針對同一個報錯或測試缺陷，**連續 2 次修復嘗試均未通過**。
3. **架構或 API 破壞性變更 (Breaking Changes)**：
   - 發現修復方案將破壞既有 Public API 簽名、違反原始 P02 架構或引入未預期的跨模組依賴。
4. **開發者主動發起**：
   - 開發者在任何階段發現設計偏差或邏輯疑慮時下達 `/Discuss`。

---

## 🛡️ 排查優先級鐵律：由近及遠、本體優先 (Local-First Hierarchy)

在進入排查與討論前，Agent 必須強制遵循以下排查階層，嚴禁越級懷疑：

```text
優先級 1：當前本體組件 (組件內部狀態、計算邏輯與邊界防護)
   ⬇ (確認本體 100% 正確後)
優先級 2：呼叫端傳參與時序 (傳遞給外部/下游組件的參數、格式、單位與生命週期時序)
   ⬇ (確認傳參與時序 100% 正確後，方可懷疑外部)
優先級 3：下游/外部組件 (外部模組是否真有缺陷) ➔ 觸發本討論向開發者報告！
```

---

## 🚀 執行步驟 (3-Step RCA Protocol)

### 步驟 1：現象現場與呼叫證據呈遞 (Symptom & Context)
- 精確列出報錯訊息、發生檔案與行號、以及當前的傳參呼叫現場。

---

### 步驟 2：5-Whys 根因歸因分析 (Root Cause Analysis)
- 深入分析為什麼底層架構、時序或資料狀態會走到該錯誤分支（拒絕「這行拋出 null」等表面陳述，追溯「為什麼 null 會流入此處」）。

---

### 步驟 3：架構修復方案矩陣與決策 (Options & Decision)
- 呈遞 2~3 種具體修復方案（包含：根本修復方案、防禦性折衷方案，分析各自的 Trade-offs 與改動成本）。
- 推薦方案與理由。

---

### 步驟 4：決策固化與恢復執行 (DR & Plan Update)
- 與開發者達成共識後：
  1. **記錄決策**：在當前 Dev Plan 的 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)、[`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`) 或對應 Phase 文件中追加一筆標準 **`[{Phase}:DR-XX]` (Decision Record)**（`{Phase}` 為決策所屬之階段 Token，如 `P01`/`P02`/`P03`/`P04`/`FT`/`UMBRELLA`）。
  2. **更新架構/任務**：若影響架構或工作清單，回填更新 [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) / [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) / [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)。
  3. **恢復編碼**：重新進入 Phase 5/6 執行根本修復。

---

`__@{WORKFLOW_DISCUSS}__`
