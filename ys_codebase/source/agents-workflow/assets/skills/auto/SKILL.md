---
name: auto
description: 針對已確認需求之計畫自動連續執行規格產出、代碼實作與測試驗證。僅於顯式輸入 /auto 或明確指示自動連續推進計畫時觸發。
---

# 自動連續推進工作流 (Auto — Lean Context Fast-Path)

本工作流用於 Full Track 或 Umbrella 子計畫處於 Phase 00 (`Confirmed`) 或 Phase 01 ~ 05 時，跳過中間人工等待點，以最小 Context 開銷連續推進至 Phase 6 手動/UX 驗證守門點。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

```markdown
/Auto 精實連續推進檢核表：
- [ ] 步驟 1：定位目標計畫當前已確認階段，判定本次 `/auto` 自動生成之起訖階段 (附加 `_auto.md` 後綴)
- [ ] 步驟 2：依下方內聯骨架速查表 (免讀 `phase_01~05` 與模板) 單次到位寫出 `P01`~`P04` (`*_auto.md`)
- [ ] 步驟 3：完成源碼與單元測試實作 (`testing-sop`)，一次性寫出 `P05_task_auto.md` (`Completed`)
- [ ] 步驟 4：執行自動化測試、一次建立並定稿 `P06_test_plan.md` (`Passed`)、執行單次 `plan verify` 與支柱三 Pre-UX 盲審，輸出卡片並 End Turn
```

---

## 1. 適用情境、熔斷防線與 `_auto.md` 專屬命名鐵律

- **適用與排除邊界**：僅適用於已具 `P00_discuss.md` (`Confirmed`) 或處於 `P01`~`P05` 之 Full Track / Umbrella 子計畫；`P00` 尚在 `Discussing` 或屬 `Fast Track` 計畫時嚴禁觸發（若僅需恢復中斷現場請改用 [continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)）。
- **三大熔斷防線**：
  1. **零臆測熔斷**：需求語意或邊界存在歧義時，嚴禁腦補，立即暫停提問。
  2. **偏差熔斷**：實作或測試遭遇 Major/Critical 偏差或連續 2 次失敗時，立即轉入 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)。
  3. **P06 手動/UX 驗證絕對阻斷**：通過自動化測試與 Pre-UX 盲審後，強制停步等待開發者驗收，嚴禁自行標記 `Completed` 或進入 Phase 7。
- **[!] `/auto` 一次寫入產物專屬後綴命名鐵律 (`PXX_YYYY_auto.md` Provenance Rule)**：
  - 凡於 `/auto` 過程中由 Agent **自動連續生成之 `Phase 01` ~ `Phase 05` 規格與任務檔**，檔名強制附加 `_auto` 後綴，以明確區隔「人工逐步定案文件 (`PXX_YYYY.md`)」與「自動連續產出文件 (`PXX_YYYY_auto.md`)」：
    - **自 `P00` (`Confirmed`) 啟動 `/auto`**：`P01`~`P05` 全數命名為 `P01_requirements_spec_auto.md`、`P02_architecture_plan_auto.md`、`P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`。
    - **自中途階段（如人工討論至 `P02` 定案後）啟動 `/auto`**：已人工定案之 `P00`~`P02` 保持原名，後續由 `/auto` 自動生成之階段命名為 `P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`。
    - **`P06_test_plan.md`**：作為人工 / UX 驗收 Checkpoint 報告，統一使用 `P06_test_plan.md`（`plans` 工具鏈原生雙軌相容原名與 `_auto.md` 後綴）。

---

## 2. Context 精實化三大鐵律 (Direction A & B Lean Execution Rules)

1. **內聯契約免讀 11 檔 (`Zero Redundant Reads`)**：
   - 處於 `/auto` 模式時，直接依下方 §3「內聯標頭與章節骨架速查表」撰寫產物，**免除調用 `read_file` 讀取 `phase_01~05.md`（省去無效的單階段 End Turn 說明）與 `P01~P06` 模板檔**。
   - 僅於撰寫測試與執行 `Phase 06` 驗證時，強制遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 [`phase_06_test.md`](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_06_test.md}__`)（含支柱三 Pre-UX 唯讀盲審）。
2. **單檔單次到位寫入與單次彙總檢核 (`1-Write-Per-File & Single Batch Verify`)**：
   - **`P01`~`P04` (`*_auto.md`)**：直接以 `> 狀態：Confirmed` 一次建立並定稿。
   - **`P05_task_auto.md`**：完成源碼與單元測試實作後，直接以 `> 狀態：Completed` 與全勾選 `- [x]` **一次性寫入落檔**（嚴禁先寫 `In Progress` 再二次 Edit）。
   - **`P06_test_plan.md`**：於 `P06` 自動化測試 100% 通過後，直接以 `> 狀態：Passed` **一次建立並定稿**（包含 §1 完整映射 `P01` 所有 `FR/EC/NFR` ID 之測試案例、§2 實測 `Passed` 日誌與 §3 `Pending` UX 項目；若前置人工階段已建 `P06` 則直接更新該檔）。
   - **單次彙總 `plan verify`**：取消 `P01`~`P05` 逐階段 CLI 檢核，於 `P06` 檔案落檔後執行**單次**全量檢核與免讀日誌追加：
     ```bash
     python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name> --log "透過 /auto 完成 P01~P06 規格、實作與測試驗證" --model "<ModelName>"
     ```
3. **跨檔單點定義去重與禁預寫實作碼 (`DRY Spec Reference & Signature-Only`)**：
   - **檔案清單單點定義於 `P02` §3**：`P03` §1 僅列新增/變更之介面，不重複抄寫內部檔案清單。
   - **`P03`/`P04` 僅寫簽名契約 (`Signature-Only, Zero Implementation Code`)**：`P03` §2 僅寫型別簽名（`def func(...) -> ReturnType: ...`）與 1~2 行前置/後置/例外契約，**嚴禁在 `P03` 或 `P04` 預先貼入函式內部實作程式碼**。
   - **任務拆解單點定義於 `P04` §4**：`P05_task_auto.md` §1 每項僅寫 1 行指標（`- [x] **TASK-01**：<簡述>（詳見 P04 §4）`），將 `P05` 嚴格控制在 $\le 25$ 行。

---

## 3. `P01` ~ `P06` 內聯標頭與標準章節骨架速查表 (Inline Schema Cheat-Sheet)

- **共用頂部標頭（所有檔案必填，嚴禁殘留 `[...]` 佔位符或 `<!-- ... -->` 註解）**：
  ```markdown
  # <文件標題>

  > 功能名稱：<功能名稱>  
  > 建立日期：<YYYY-MM-DD>  
  > 所屬主計畫：<父計畫名稱或 N/A (Root Plan)>  
  > 狀態：<P01~P04 填 Confirmed | P05 填 Completed | P06 填 Passed>  
  > 模型：<當輪平台宣告模型名稱；無法確認填 Unknown>  
  ```
- **各階段必備 `##` 二級章節標題與精實內容契約（100% 對齊 `PlanVerifier` 動態模板鏡像）**：

| 階段與自動檔名 | 必備 `##` 二級章節標題 (`PlanVerifier` 剛性檢核) | 精實撰寫要點 (`DRY & Lean Rules`) |
| :--- | :--- | :--- |
| **`P01_requirements_spec_auto.md`** | `## 1. 功能需求清單 (Functional Requirements)`<br>`## 2. 邊界與異常情況 (Edge Cases & Failure Modes)`<br>`## 3. 非功能需求 (Non-Functional Requirements)`<br>`## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)` | §1~§3 以精簡表格編列 `FR-XX`、`EC-XX`、`NFR-XX`（全數須於 `P06` §1 100% 映射）；§4 條列關鍵防坑要點。 |
| **`P02_architecture_plan_auto.md`** | `## 1. 模組架構分層與職責邊界 (Layered Architecture)`<br>`## 2. 核心資料流與循序圖 (Data Flow & Sequence Diagram)`<br>`## 3. 受影響檔案與新建檔案清單 (Impacted & New Files Inventory)`<br>`## 4. 架構決策記錄 (Architecture Decision Records)` | §3 為**全計畫檔案變更清單唯一 SSOT**；§4 記錄 `[P02:DR-XX]`。 |
| **`P03_api_spec_auto.md`** | `## 1. 介面契約清單 (Interface Inventory)`<br>`## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)`<br>`## 3. 依賴拓撲與實作順序 (Implementation Topology)` | §2 **僅寫 `def/class` 型別簽名、錯誤與例外契約及 `[P03:DR-XX]`，嚴禁預寫實作程式碼塊**；§3 寫明 Bottom-Up DAG 順序。 |
| **`P04_implementation_plan_auto.md`** | `## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)`<br>`## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)`<br>`## 3. 架構靈魂拷問 (Stress Test & Resilience Review)`<br>`## 4. 實作任務清單 (Task Breakdown & Topological Sequence)`<br>`## 5. 決策定稿 (Confirmed Decision Records)` | §1 勾選 `- [x]`；§2 列三層 5 列文檔表（`<Category>/README.md`、`[topic].md`、`DESIGN_NOTES.md`、微觀註解、`CHANGELOG.md`）；§4 為 **`1. **TASK-XX**` 唯一 SSOT（勿加 Checkbox）**。 |
| **`P05_task_auto.md`** | `## 1. 實作任務清單 (Task Breakdown)`<br>`## 2. 實作偏差紀錄表 (Implementation Deviations)` | 於編碼完成後**一次性以 `Completed` 寫入**：§1 每項 1 行 `- [x] **TASK-XX**：<簡述>（詳見 P04 §4）`（含 `TASK-DOC`，全文 $\le 25$ 行）。 |
| **`P06_test_plan.md`** | `## 1. 自動化測試案例清單 (Automated Test Cases)`<br>`## 2. 測試執行紀錄表 (Test Execution Log)`<br>`## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)` | 於測試通過後**一次性以 `Passed` 寫入**：§1 表格必含 `FT-XX`/`ET-XX`/`RT-XX` 並 100% 覆蓋 `P01` 所有 `FR/EC/NFR` ID；§2 填 `Passed` 與實測數據；§3 填 `UX-01` (`Pending`)。 |

---

## 4. 抵達 P06 手動/UX 驗證 Checkpoint（強制等待）

完成自動化測試、單次 `plan verify` 與支柱三 Pre-UX 唯讀冷眼盲審（`REVIEW_STATUS: PASSED`）後，對話僅呈遞以下極簡卡片並**立即 End Turn 等待確認**（後續驗收確認後唯一合法流轉節點為 [Phase 7 (P07 結案與 SOP 審查)](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_07_walkthrough.md}__`)；若轉向非業務微調則建議先 P07 結案再建 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)）：

```markdown
### 🚦 /Auto 連續推進完成 (抵達 P06 驗證 Checkpoint)
- **產出文件**：[P06_test_plan.md](__${project://plans}__/{plan_name}/P06_test_plan.md) (`Passed` / 待驗收) 及 `P01`~`P05` (`*_auto.md`)
- **推進摘要**：Phase 01 ~ Phase 05 已依精實模式單次到位產出；自動化測試、單次 `plan verify` 與 Pre-UX 盲審 100% 通過
- **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
- **待確認事項**：[請確認驗收結果為 `[測試通過]` 或 `[跳過/免測]`；確認完成後將進入 Phase 7 (P07 成果展示與 SOP Review 結案)]
```

---

## 常見踩坑指南 (Gotchas)

- **切勿遺漏 `_auto.md` 後綴或省略 `P01`~`P05` 實體檔案**：`/auto` 期間自動生成之 `P01`~`P05` 必須命名為 `PXX_YYYY_auto.md`，且 `P01` 所有 `FR/EC/NFR` 編號必須 100% 出現在 `P06_test_plan.md` §1 中，否則單次 `plan verify` 會因孤兒需求 ID 失敗。
- **切勿在 `P03`/`P04` 預貼實作程式碼或對 `P05`/`P06` 重複寫檔**：嚴格落實 `Signature-Only` 與 `1-Write-Per-File`，避免無謂消耗 Output 與 Context Tokens。
