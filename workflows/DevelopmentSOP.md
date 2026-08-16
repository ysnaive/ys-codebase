---
description: 標準開發作業流程 (Development SOP) — 定義專案從需求到發布的完整規範與分級管控
---

# 標準開發作業流程 (Development SOP)

本文件定義 AI Agent 在本專案中進行功能開發、架構重構或問題修復時**必須強制遵守**的標準作業流程 (SOP)。

---

## 核心原則

所有開發活動必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的需求、API 行為或架構細節，必須主動向開發者釐清，嚴禁自行假設。
2. **可追溯 (Traceability)**：從需求 (FR/EC) 到架構、API、程式碼、測試計畫與 Commit 訊息，每個階段皆有對應文件留痕。
3. **分級管控 (Graduated Control)**：依 Phase 0 分流評估任務規模，嚴格執行 Full Track 或 Fast Track。

---

## 🚨 Agent 執行紀律（防呆鐵律）

- **嚴禁連發**：單次 Turn 最多執行一個 Phase。產出階段文件後，必須詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予「確認/同意/推進」指示，嚴禁 Agent 自行假設通過並跨入下一個 Phase。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須於 Phase 2~3 隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段與 `P04_implementation_plan.md` 一併剛性定稿 (Confirmed)，嚴禁延至 Phase 6 才開始憑空設計測試項目。Phase 6 之主軸純粹為「測試執行 + 缺陷修復 + 互動/UX/硬體驗證」。
- **Phase 6 人工/UX/硬體測試 Checkpoint 強制等待關卡**：即使自動化測試 100% Passed，Agent **絕對禁止**自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須呈遞測試結果，並明確詢問開發者進行實際互動/視覺/硬體驗證。必須等待開發者明確回覆「驗證通過/指示免測」後，方可將 P06 標記為 Passed 並推進至 Phase 7。
- **Phase 6 驗證防呆鐵律 (無 Log 即未驗證)**：若 CLI 編譯/測試命令執行受阻（例如環境權限或 log 無法截取），Agent **絕對禁止**在 `P06_test_plan.md` 與對話中標記 `Passed`。必須明確標記 `[未實機編譯/僅靜態檢查]`，並呈遞精確命令請開發者於控制台執行回填。
- **全階段文件模板剛性對齊**：所有 Phase (P01~P07 / FT_plan) 產出文件 **必須 100% 嚴格鏡像標準模板結構**（包含指定欄位、表格與 Header 標頭），嚴禁 Agent 自行簡化或遺漏模板區塊。
- **目錄歸檔紀律與腳本優先**：
  - 定式作業（歸檔、檢索、掃描）優先呼叫 `.agents/scripts/` 下的 Python 工具腳本。
  - **嚴禁 Agent 主動歸檔**：所有計畫預設留存於 `.agents/dev_plans/` 原位，僅在開發者明確下達歸檔指令時才執行歸檔腳本。

---

## 工作流概覽

```
[使用者提出需求]
       │
       ▼
┌──────────────┐
│   Phase 0    │ ── 評估規模 ──> [小型/修復] ──> Fast Track (FT-1 ~ FT-3)
│  Track 分流  │
└──────────────┘
       │
       ▼ [中大型/架構/新功能]
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Phase 1    │ ───> │   Phase 2    │ ───> │   Phase 3    │
│  需求規格書  │       │ 架構計畫書   │       │  API 規格書  │
│    (P01)     │       │    (P02)     │       │    (P03)     │
└──────────────┘       └──────────────┘       └──────────────┘
                                                     │
                                                     ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Phase 6    │ <─── │   Phase 5    │ <─── │   Phase 4    │
│  測試與驗證  │       │ 程式碼實作   │       │ 最終審查&定稿│
│    (P06)     │       │    (P05)     │       │  (P04 + P06) │
└──────────────┘       └──────────────┘       └──────────────┘
       │
       ▼
┌──────────────┐
│   Phase 7    │ ───> [知識庫同步 & Walkthrough] ───> ✅ 開發完成
│  最終品質審查│
│    (P07)     │
└──────────────┘
```

---

## 階段詳細規範

### Phase 0：Track 分流與需求初探

#### 目標
快速評估任務規模與影響範圍，決定走 **Full Track** 還是 **Fast Track**。

#### 判定標準

| Track | 適用場景 | 產出物 |
| :--- | :--- | :--- |
| **Fast Track** | • 修改檔案數 $\le 2$<br>• 不變更 Public API / 介面簽名<br>• 不引入新的跨模組依賴<br>• 純 Bug 修復、內部微調或簡單擴充 | `FT_plan.md` |
| **Full Track** | • 新增功能或跨模組重大變更<br>• 修改 Public API / 介面簽名<br>• 涉及架構調整、底層重構或資料流變更<br>• 任何高複雜度或高風險任務 | `P01` ~ `P07` 完整文件 |

#### 執行步驟
1. 分析使用者需求，比對分流矩陣。
2. 建立開發計畫目錄：`.agents/dev_plans/{YYYY_MM_DD_HHMM_功能名稱}/`。
3. 若為 Fast Track，直接於工作目錄建立 `FT_plan.md` 並進入 FT-1。
4. 若為 Full Track，建立 `changelog.md` 並進入 Phase 1。

---

### Phase 1：需求規格定義

#### 目標
將模糊需求收斂為精確的功能需求 (FR)、非功能需求 (NFR) 與邊界條件 (EC)。

#### 執行步驟
1. 依 `.agents/workflows/templates/P01_requirements_spec.md` 建立 `P01_requirements_spec.md`（狀態標記為 `Draft`）。
2. 列出核心功能需求 (FR) 與邊界/異常情況 (EC)。
3. **查閱踩坑紀錄**：主動查閱相關模組在 `docs/` 及 `DESIGN_NOTES.md` 中的 `[!CAUTION]` 或 `[!WARNING]`。
4. 於 `changelog.md` 記錄本階段決策。

→ **Checkpoint** → 開發者確認（狀態更新為 `Confirmed`） → 進入 Phase 2

---

### Phase 2：架構與模組設計

#### 目標
進行架構分層、模組劃分、依賴邊界與資料流設計。

#### 執行步驟
1. 依 `.agents/workflows/templates/P02_architecture_plan.md` 建立 `P02_architecture_plan.md`（標記為 `Draft`）。
2. 繪製 Mermaid 循序圖或資料流圖。
3. 盤點受影響的模組與檔案清單。
4. **Test-First 初始化**：依 `.agents/workflows/templates/P06_test_plan.md` 建立初始草稿 `P06_test_plan.md`（標記為 `Draft`），預先將 FR/EC 映射為測試項目。

→ **Checkpoint** → 開發者確認（狀態更新為 `Confirmed`） → 進入 Phase 3

---

### Phase 3：API 規格定義與依賴拓撲

#### 目標
定義所有 Public/Protected API 簽名、型態、錯誤處理與依賴拓撲順序。

#### 執行步驟
1. 依 `.agents/workflows/templates/P03_api_spec.md` 建立 `P03_api_spec.md`（標記為 `Draft`）。
2. 定義型態簽名、命名風格與物理/數學顯式單位。
3. 定義依賴拓撲（實作順序）。
4. **執行 Extension 擴充**：若專案定義了 `P03_*_ext.md`，於標準步驟完成後執行擴充檢查。

→ **Checkpoint** → 開發者確認（狀態更新為 `Confirmed`） → 進入 Phase 4

---

### Phase 4：最終審查與定稿 (Review & Test-First Confirmed)

#### 目標
全面交叉審查 Phase 1~3 產出物，並將實作計畫與測試計畫一併剛性定稿。

#### 執行步驟
1. **交叉驗證 Checklist**：
   - [ ] 需求規格書中的每個 FR，在 API 規格書中有對應介面
   - [ ] 需求規格書中的每個 EC，在 API 規格書中有對應錯誤策略
   - [ ] 風險評估有對應緩解措施
   - [ ] 物理/數學變數皆帶有顯式單位後綴
2. **靈魂拷問 (Stress Test)**：Agent 主動扮演架構審查員，提出至少 1 個尖銳且具建設性的問題，開發者回答後方可繼續。
3. **產出最終計畫書**：依 `P04_implementation_plan.md` 模板彙整 DR 與實作細節，狀態更新為 `Confirmed`。
4. **Test-First 定稿**：同步審查並定稿 `P06_test_plan.md`，狀態更新為 `Confirmed`。

→ **Checkpoint** → 開發者確認「開始實作」 → 進入 Phase 5

---

### Phase 5：程式碼實作

#### 目標
嚴格按照 `P04_implementation_plan.md` 依序撰寫程式碼。

#### 執行步驟
1. **進度追蹤**：於工作目錄建立 `P05_task.md`，列出 TODO 清單 `[ ]`。
2. **依序實作**：按依賴拓撲實作，每完成一項於 `P05_task.md` 標記 `[x]`。
3. **編譯驗證**：每個主要模組實作完成後執行編譯檢查。
4. **偏差處置**：
   - **Critical**（影響 Public API / 架構）：**立即停止實作**，觸發討論並回退修正計畫。
   - **Major**（不影響 Public API 但影響內部邏輯）：暫停當前項目並向開發者回報。
   - **Minor**（不影響架構之細微調整）：自行處理並記錄於 `P05_task.md`。

→ 所有 TODO 項目完成 → 進入 Phase 6

---

### Phase 6：測試與驗證

#### 目標
執行 Phase 4 定稿之 `P06_test_plan.md`，完成自動化驗證、人工/UX 驗證與缺陷修復。

#### 執行步驟
1. **自動化測試執行**：執行 CLI 編譯與單元測試，記錄輸出日誌。若命令受阻，標記 `[未實機編譯/僅靜態檢查]`。
2. **人工 / UX / 硬體驗證 Checkpoint（強制等待）**：
   - Agent **絕對禁止**代勾或自行標記 `Passed`。
   - 呈遞測試結果，明確詢問開發者進行實際互動/視覺/實機驗證。
   - 獲得開發者明確回覆「驗證通過」後，方可將 P06 標記為 `Passed`。
3. **Bug 修復子循環**：
   - 計畫缺陷：回退 Phase 1~4 修正計畫後再修復。
   - 實作錯誤：修復後重新執行受影響測試。

→ 所有測試 Passed + 開發者驗證確認 → 進入 Phase 7

---

### Phase 7：最終品質 Review

#### 目標
全面審查程式碼品質、同步知識庫文檔與產出 Commit 訊息。

#### 執行步驟
1. **代碼清理與規範檢查**：移除 Debug 語句、檢查命名規範、日誌與記憶體安全。
2. **知識庫同步 (Knowledge Base Sync)**：
   - 依 `DocumentationStandards.md` 與專案鏡像規則更新 `docs/` 下對應模組之 `README.md`、`[topic].md` 或 `DESIGN_NOTES.md`。
   - 依 `global_changelog.md` 模板將本次變更摘要追加至專案根目錄 `CHANGELOG.md` 最上方。
3. **產出 Commit 訊息**：依 Conventional Commits 格式（`<type>(<scope>): <標題>`）產出。
4. **產出變更摘要**：依 `P07_walkthrough.md` 模板撰寫變更摘要。
5. **目錄保留原位**：工作目錄維持原位，僅在開發者明確指示時呼叫 `archive_plan.py` 歸檔。

→ 開發者確認審查通過 → ✅ 開發完成

---

## Fast Track 流程

適用於小型、低風險修改（$\le 2$ 檔案且無 Public API 變更）。

### FT-1：需求確認 & 變更規劃
1. 建立 `FT_plan.md`（標記為 `Planning`）。
2. 確認無 Public API 與跨模組依賴影響（通過架構確認 Checklist）。
3. → **Checkpoint** → 開發者確認 → FT-2

### FT-2：實作
1. `FT_plan.md` 狀態更新為 `Implementing`。
2. 逐項實作並追蹤進度，每步執行編譯驗證。若遇 Critical 偏差立即升級為 Full Track。
3. → 實作完成 → FT-3

### FT-3：品質 Review
1. `FT_plan.md` 狀態更新為 `Reviewing`。
2. 通過代碼清理、命名、文檔同步與驗證 Checklist。
3. 填入 Commit 訊息與變更摘要，狀態更新為 `Completed`。
4. → **Checkpoint** → 開發者確認 → ✅ 開發完成
