`__@{DYNAMIC_CONTEXT_MAP}__`

# 構想與靈感孵化池工作流 (Idea)

本 Workflow 獨立於標準開發 SOP 之外，用於記錄突發奇想、潛在技術改進、未來架構藍圖或輕量原型探索。所有階段的執行規範請嚴格遵循 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 核心原則與互動模式

1. **獨立於 SOP 之外**：
   - 靈感池存放於 `workflow.plans://ideas/`，不需要走 Phase 1~7 流程，也不需立即分流判定。
2. **開放式自由對話**：
   - 開發者怎麼問，Agent 怎麼答。靈活探索可能性、架構思路與潛在邊界，不拘泥於死板格式。
3. **提案產出 (What / Why / How / Related)**：
   - 討論收斂後，產出結構化構想書，命名為 `YYYY_MM_DD_{idea_name}.md`。
4. **立項流轉機制 (Promoted to Dev Plan)**：
   - 當靈感成熟並獲指示正式開立 Dev Plan 時，**直接將 Idea 檔案搬移至新開立的 Dev Plan 目錄並轉換為 [`P00_semantic_requirements.md`](`__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`)**，達成完美無縫銜接。

---

## 🚀 執行步驟

### 步驟 1：開放式腦力激盪與自由探討
- 開發者提出靈感或技術痛點，Agent 擔任架構思維夥伴：
  - 探討痛點的本質 (Why)。
  - 構思潛在的核心機制或功能定義 (What)。
  - 勾勒概念設計、資料流或使用方式概念 (How)。
  - 盤點關聯技術、潛在風險與未知數 (Related & Risks)。

---

### 步驟 2：產出構想提案書
- 當討論告一段落時，Agent 建立檔案：
  - **路徑**：`workflow.plans://ideas/YYYY_MM_DD_{idea_name}.md`
  - **狀態**：標記為 `Incubating`（孵化中）或 `Draft`（草擬中）。
  - **產出約束**：嚴禁將開頭的 HTML 導引註解輸出至目標文件中。

---

### 步驟 3：成熟立項流轉 (Promotion)
- 當開發者宣告「將此 Idea 正式立項開發」時：
  1. 建立標準 Dev Plan 目錄：`workflow.plans://{YYYY_MM_DD_HHMM_功能名稱}/`。
  2. 將提案文件搬移至該目錄，並轉換重命名為 [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)。
  3. 進入 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`) 標準流程，由開發者確認 P00 後執行分流！

---

`__@{WORKFLOW_IDEA}__`
