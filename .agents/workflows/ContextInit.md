---
description: 上下文熱啟動流程
---

> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | `./ys_codebase` | `[ACTIVE]` |
> | **`workflow.plans://`** | `./plans` | `[ACTIVE]` |
> | **`workflow.archived://`** | `./plans/archived` | `[ACTIVE]` |
> | **`workflow.docs://`** | `./docs` | `[ACTIVE]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb.py uri resolve <uri>`（例：`python yscb.py uri resolve project://AGENTS.md`）

# 專案上下文初始化流程 (ContextInit)

本 Workflow 用於在全新對話 (Session / Chat) 開始時，快速加載專案的核心架構、歷史變更、程式碼規範與 Agent 紀律。確保 Agent 即使在大語言模型上下文重置後，也能 100% 掌握專案默契與工程標準。

---

## 🎯 核心原則

1. **沙盒 100% 安全 (Sandbox Native Read)**：優先使用內建檔案讀取工具（如 `view_file`），不依賴需額外權限的 CLI 命令，確保在沙盒模式與完全存取模式下均能無障礙秒級執行。
2. **零臆測脈絡 (Zero Speculation)**：從既有真實文檔（`CHANGELOG.md`、`coding-standards.md`、`AGENTS.md`）載入現況，不自行假設專案結構。
3. **語意 URI 標準化 (Semantic URI Protocol)**：透過 `project://`、`workflow.docs://`、`workflow.plans://` 等標準協議精準指向各級資源。
4. **極簡 Token 高效加載**：僅抽取專案的核心公理與最新變更，不載入無關細節。

---

## 🚀 執行步驟

當使用者輸入 `/ContextInit` 或 Agent 偵測到是全新的對話 Session 時，Agent **必須順序執行**以下加載步驟：

### 步驟 1：加載專案層級硬性規範與紀律
- **讀取檔案**：[AGENTS.md](`../../AGENTS.md`)
- **提取要點**：
  - SOP 三大原則：零臆測、可追溯、分級管控。
  - 嚴禁連發（一次 Turn 最多一個 Phase）、嚴禁空降實作。
  - 除錯排查與範疇保護鐵律、模板註解剝除鐵律。
  - 定式作業指令優先原則、嚴禁主動歸檔。
  - 專案程式碼架構與 `workflow.docs://` 知識庫之鏡像同步關係。

### 步驟 2：加載開發標準與 CLI 防呆指南
- **讀取檔案**：
  - 開發標準作業規範：[DevelopmentStandards.md](`../.yscb/standards/DevelopmentStandards.md`)
  - 指令防呆情境手冊：[AgentsCliGuild.md](`../.yscb/standards/AgentsCliGuild.md`)
  - 專案特化命名規範：[STANDARDS.md](`../../docs/_project/STANDARDS.md`) *(若專案未獨立提供則依 DevelopmentStandards.md 為準)*
- **提取要點**：
  - 掌握 Phase 0 ~ 7 標準開發作業流程 (SOP) 與三大分流原則。
  - 熟悉 CLI 語意情境對照表，嚴格執行 Default-Deny 守門。
  - 識別碼與變數命名規範、單位與型別標註約束。

### 步驟 3：加載專案最新演進與當前進度
- **讀取檔案**：[CHANGELOG.md](`../../CHANGELOG.md`) (前 2 ~ 3 個區塊)
- **提取要點**：
  - 瞭解專案最近完成了哪些 Dev Plan 與架構優化。
  - 掌握當前專案處於何種演進階段。

### 步驟 4：檢查進行中計畫狀態與大綱
- **調取狀態指令**：`python yscb.py agents-workflow plan status`
- **輕量載入與防呆鐵律**：
  - 🚨 **嚴禁批次深入閱讀**：在 ContextInit 階段**絕對禁止批次或深入讀取 `workflow.plans://` 各計畫內的詳細文件**（如 P00~P07），僅需調取 `plan status` 大綱掌握全貌即可，避免浪費 Prompt Token 與上下文污染。
  - **按需接手原則**：只有在後續收到開發者明確指示「接續/接手特定計畫開發」時，方可在 `/Continue` 流程中深入讀取該 Plan 目錄與 `handoff.md`。
- **提取要點**：
  - 快速掌握當前是否有進行中計畫及其所處 Phase。

---

## 📋 輸出成果：專案熱啟動簡報 (Context Warmup Summary)

完成上述檔案讀取後，Agent **必須**向開發者呈現以下格式的上下文熱啟動簡報，並結束當前 Turn 等待開發者下達任務：

```markdown
# 🚀 專案上下文已成功熱啟動 (Context Initialized)

已成功載入本專案的核心架構、規範與歷史決策脈絡：

### 📌 專案核心規範摘要 (Coding Standards)
- **目錄與路徑架構**：原始碼與 workflow.docs:// 知識庫鏡像對齊。
- **識別碼命名規範**：遵循專案定義之命名風格與前綴慣例。
- **單位與型別約束**：物理/數學變數顯式標註單位，轉換時嚴禁同名覆蓋。
- **註解哲學**：workflow.docs:// 宏觀，代碼文檔註解微觀自包含。

### 🛠️ 工具與 SOP 紀律 (Guardrails)
- **SOP 紀律**：零臆測、嚴禁連發、嚴禁空降實作、除錯排查範疇保護、嚴禁主動歸檔。
- **CLI 守門**：執行指令前必先查對 `AgentsCliGuild.md`，Default-Deny 阻斷未列情境。
- **定式作業**：計畫檢索/歸檔/驗證使用 `python yscb.py agents-workflow plan <status|search|verify|archive>`。
- **Plan 狀態**：透過 `plan status` 掌握進行中計畫大綱（深入閱讀留待 `/Continue` 接手時按需進行）。

---

**🤖 Agent 狀態**：已準備就緒！請問今天我們準備進行什麼任務或功能開發？
```
