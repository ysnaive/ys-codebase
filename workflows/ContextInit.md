---
description: 專案上下文熱啟動 Workflow — 新 Session/Chat 開啟時快速初始化專案記憶與規範
---

# 專案上下文初始化流程 (ContextInit Workflow)

本 Workflow 用於在全新對話 (Session / Chat) 開始時，快速加載當前專案的核心架構、歷史變更、程式碼規範與 Agent 紀律。確保 Agent 即使在大語言模型上下文重置後，也能 100% 掌握專案默契與工程標準。

---

## 🎯 核心原則

1. **沙盒 100% 安全 (Sandbox Native Read)**：優先使用內建檔案讀取工具（如 `view_file`），不依賴需額外權限的 CLI 命令，確保在沙盒模式與完全存取模式下均能無障礙秒級執行。
2. **零臆測脈絡 (Zero Speculation)**：從既有真實文檔（`AGENTS.md`、`CHANGELOG.md`、專案程式碼規範）載入現況，不自行假設專案結構。
3. **極簡 Token 高效加載**：僅抽取專案的核心公理與最新變更，不載入無關細節。

---

## 🚀 執行步驟

當使用者輸入 `/ContextInit` 或 Agent 偵測到是全新的對話 Session 時， Agent **必須順序執行**以下加載步驟：

### 步驟 1：加載專案層級硬性規範與紀律
- **讀取檔案**：[.agents/AGENTS.md](file://./.agents/AGENTS.md)
- **提取要點**：
  - SOP 三大原則：零臆測、可追溯、分級管控。
  - **三大分流層級**：Level 0 (Fast Track)、Level 1 (Full Track)、Level 2 (Umbrella 分類型主計畫模式)。
  - **Phase 0-R 深度技術調研**：複雜任務啟動特化調研，產出 `R{n:2d}_{topic}.md` 報告。
  - 核心紀律：嚴禁連發（一次 Turn 最多一個 Phase）、嚴禁空降實作、嚴禁主動歸檔。
  - 專案特化之 Namespace、目錄鏡像與專案架構約定。

### 步驟 2：加載專案程式碼與命名規範
- **讀取檔案**：讀取 `AGENTS.md` 中指定的專案程式碼規範檔案（例如 `docs/_project/coding-standards.md` 或 `docs/coding-standards.md`，若存在）。
- **提取要點**：
  - 命名空間 (Namespace) 與識別碼命名風格矩陣（欄位、屬性、方法、型態）。
  - 物理與數學單位顯式規範（變數後綴 `_{unit}`，轉換嚴禁同名覆蓋）。
  - 檔案組織原則（一檔一主要型態、私有輔助型態強制 Nested 併檔）。
  - 註解雙軌哲學（`docs/` 負責宏觀公理，源碼負責微觀自包含）。

### 步驟 3：加載專案最新演進與當前進度
- **讀取檔案**：[CHANGELOG.md](file://./CHANGELOG.md) (前 2 ~ 3 個區塊，若存在)
- **提取要點**：
  - 瞭解專案最近完成了哪些 Dev Plan / 重構事項。
  - 掌握當前專案處於何種演進階段。

### 步驟 4：探測當前環境權限模式 (Permission Detection)
- **模式判定**：
  - **完全存取模式 🟢**：具備免審授權 ➔ 允許 Agent 自動執行 `run_command`。
  - **沙盒防護模式 🟡**：未授權 ➔ 啟用沙盒降級防護，CLI 指令優先排版呈遞由開發者執行，嚴禁盲目發起背景 Task 防止 IDE 掛起。

### 步驟 5：檢查進行中與歷史 Plan 結構 (可選 / 依模式)
- **原生檔案檢查**：查看 `.agents/dev_plans/` 目錄下的資料夾結構。
  - 若處於**完全存取模式**：可選擇性執行 `python .agents/scripts/scan_plan_status.py` 快速輔助。
  - 若處於**沙盒模式**：直接讀取 `.agents/dev_plans/` 當前目錄狀態。

---

## 📋 輸出成果：專案熱啟動簡報 (Context Warmup Summary)

完成上述檔案讀取與權限探測後，Agent **必須**向開發者呈現以下格式的上下文熱啟動簡報，並結束當前 Turn 等待開發者下達任務：

```markdown
# 🚀 專案上下文已成功熱啟動 (Context initialized)

已成功載入專案的核心架構、程式碼規範與歷史決策脈絡：

- **環境權限模式**：🟢 **完全存取模式**（支援 CLI 自動化執行） / 🟡 **沙盒防護模式**（CLI 命令將優先排版呈遞供手動執行，防止 Task 掛起）

### 📌 專案核心規範摘要 (Coding Standards)
- **Namespace & 路徑**：[依 AGENTS.md / 規範檔提取之 Namespace 與鏡像規則]
- **識別碼命名**：[依專案規範提取之命名風格與前綴]
- **物理單位**：變數顯式帶 `_{unit}`（例 `position_px`），轉換時嚴禁同名變數覆蓋。
- **註解哲學**：`docs/` 宏觀，源碼微觀自包含；私有函式採用自然語言【敘述式註解】。
- **檔案組織**：一檔一型態，私有專屬型態強制 Nested 併檔。

### 🛠️ 工具與 SOP 紀律 (Guardrails)
- **三大分流層級**：Level 0 (Fast Track) / Level 1 (Full Track) / Level 2 (Umbrella 主計畫，子計畫以單個 Full Track 顆粒度拆分)。
- **深度調研工作流**：複雜任務支援 Phase 0-R 深度調研，產出 `R{n:2d}_{topic}.md` 專題報告。
- **SOP 紀律**：嚴禁連發、嚴禁空降實作、嚴禁主動歸檔；子計畫目錄最多兩層結構。
- **定式作業**：歷史檢索/歸檔優先使用 `.agents/scripts/` 下的 Python 工具腳本。
- **進行中計畫**：[當前進行中之 Dev Plan 名稱與狀態，若無則標記「無」]

---

**Agent 狀態**：已準備就緒！請問今天我們準備進行什麼任務或功能開發？
```
