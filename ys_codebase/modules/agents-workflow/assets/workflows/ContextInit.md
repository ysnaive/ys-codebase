`__@{DYNAMIC_CONTEXT_MAP}__`

# 專案上下文初始化流程 (ContextInit)

本 Workflow 用於在全新對話 (Session / Chat) 開始時，快速加載專案的核心架構、歷史變更、程式碼規範與 Agent 紀律。確保 Agent 即使在大語言模型上下文重置後，也能 100% 掌握專案默契與工程標準。

---

## 🎯 核心原則

1. **沙盒 100% 安全 (Sandbox Native Read)**：優先使用 Agent 內建檔案讀取工具（如 `view_file` / `read_file` / `View`），不依賴需額外權限的 CLI 命令，確保在沙盒模式與完全存取模式下均能無障礙秒級執行。
2. **零臆測脈絡 (Zero Speculation)**：從既有真實文檔（`CHANGELOG.md`、`coding-standards.md`、`AGENTS.md`）載入現況，不自行假設專案結構。
3. **語意 URI 標準化 (Semantic URI Protocol)**：透過 `project://`、`workflow.docs://`、`workflow.plans://` 等標準協議精準指向各級資源。
4. **極簡 Token 高效加載**：僅抽取專案的核心公理與最新變更，不載入無關細節。

---

## 🚀 執行步驟

當使用者輸入 `/ContextInit` 或 Agent 偵測到是全新的對話 Session 時，Agent **必須順序執行**以下加載步驟：

### 步驟 1：🚨 加載專案行為準則與防呆紀律 (Mandatory Standards Read)
- **讀取檔案**：[`__${project://AGENTS.md}__`](`__#{project://AGENTS.md}__`) *(或 [`__${module://agents-workflow/assets/standards/AgentsStandards.md}__`](`__#{module://agents-workflow/assets/standards/AgentsStandards.md}__`))*
- **強制提取要點**：
  - **核心三大原則**：零臆測、可追溯、分級管控。
  - **🚨 執行紀律（絕對禁止條款）**：
    - 嚴禁連發（一次 Turn 最多一個 Phase 或一個獨立動作）、Checkpoint 強制等待。
    - 「問答 $\neq$ 推進」防呆條款、嚴禁空降實作。
    - 除錯排查由近及遠與範疇保護鐵律。
  - **🛡️ CLI 指令 Default-Deny 守門鐵律**：嚴格查表比對，未列指令絕對禁止擅自調用。
  - **🧩 模組擴充紀律 (Contributed Standards)**：嚴格遵循各模組於 `AGENTS.md` 注入之特化執行鐵律（如日常檢索工具替代、註解結構防護等）。
  - 💡 **提示**：SOP 0~7 完整生命週期與模板規範已完整收錄於 [`__${module://agents-workflow/assets/skills/development-sop/SKILL.md}__`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)，於開立或推進計畫時（如 `/NewPlan`、`/Continue`）按需精讀。

### 步驟 2：加載 CLI 指令手冊與專案演進脈絡
- **讀取檔案**：
  - 指令防呆情境手冊：[`__${module://agents-workflow/assets/skills/yscb-cli-guild/SKILL.md}__`](`__#{module://agents-workflow/assets/skills/yscb-cli-guild/SKILL.md}__`)
  - 專案最新變更日誌：[`__${project://CHANGELOG.md}__`](`__#{project://CHANGELOG.md}__`) (前 2 ~ 3 個區塊)
  - 專案特化命名規範：[`__${workflow.docs://_project/STANDARDS.md}__`](`__#{workflow.docs://_project/STANDARDS.md}__`) *(若專案未獨立提供則略過)*
- **提取要點**：
  - 掌握 CLI 三級權限分級（🟢 自主安全 / 🟡 階段條件 / 🔴 授權守門）。
  - 瞭解專案最近完成了哪些 Dev Plan 與架構優化。

### 步驟 3：檢查進行中計畫狀態與大綱
- **調取狀態指令**：`python __${yscb.host://yscb.py}__ agents-workflow plan status`
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

### 🛠️ 工具與 SOP 紀律 (Guardrails & SOP)
- **核心紀律防呆**：零臆測、嚴禁連發、嚴禁空降實作、除錯排查範疇保護、嚴禁主動歸檔。
- **CLI 權限守門**：嚴格查對 `yscb-cli-guild` Skill（🟢 自主安全 / 🟡 階段條件 / 🔴 授權守門），Default-Deny 阻斷未列情境。
- **模組特化紀律**：遵循各模組於 `AGENTS.md` 注入之執行鐵律（如日常檢索工具替代、Docstring 防護等）。
- **計畫作業與狀態**：透過 `plan status` 掌握進行中計畫大綱；SOP 0~7 規範留待開啟計畫時（`/NewPlan`）按需精讀。

---

**🤖 Agent 狀態**：已準備就緒！請問今天我們準備進行什麼任務或功能開發？
```

---

`__@{WORKFLOW_CONTEXTINIT}__`
