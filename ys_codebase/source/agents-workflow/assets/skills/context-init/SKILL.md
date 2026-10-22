---
name: context-init
description: 上下文熱啟動流程。當全新對話 Session 開始、需要重新加載專案規範與環境上下文時觸發。
---

# 專案上下文初始化流程 (ContextInit)

本 Skill 用於在全新對話 (Session / Chat) 開始時，快速加載專案的核心架構、歷史變更、程式碼規範與 Agent 紀律。確保 Agent 即使在大語言模型上下文重置後，也能 100% 掌握專案默契與工程標準。

---

## 核心原則

1. **沙盒 100% 安全 (Sandbox Native Read)**：優先使用 Agent 內建檔案讀取工具（如 `view_file` / `read_file` / `View`），不依賴需額外權限的 CLI 命令，確保在沙盒模式與完全存取模式下均能無障礙秒級執行。
2. **零臆測脈絡 (Zero Speculation)**：從既有真實文檔（`CHANGELOG.md`、`STANDARDS.md`、`AGENTS.md`）載入現況，不自行假設專案結構。
3. **語意 URI 標準化 (Semantic URI Protocol)**：透過 `project://`、`workflow.docs://`、`workflow.plans://` 等標準協議精準指向各級資源。
4. **極簡 Token 高效加載**：僅抽取專案的核心公理與最新變更，不載入無關細節。

---

## 執行步驟

當使用者輸入 `/ContextInit` 或 Agent 偵測到是全新的對話 Session 時，Agent **必須順序執行**以下加載步驟：

### 步驟 1：[!] 加載專案行為準則與防呆紀律 (Mandatory Standards Read)
- **讀取檔案**：[`AGENTS.md`](`__#{project://AGENTS.md}__`) *(或 [`AgentsStandards.md`](`__#{module://agents-workflow/assets/standards/AgentsStandards.md}__`))*
- **強制提取要點**：
  - **三大核心原則**：
    1. **零臆測 (Zero Speculation Axiom)**：不確定細節必須向開發者釐清；寬泛指令嚴禁自行腦補，優先反問確認具體目標。
    2. **檔案唯一真理與對話極簡節流 (SSOT & Throttle)**：產物以實體檔案為唯一真理來源；對話嚴禁全文重複或代碼傾倒，極致精簡節約 Token；模型紀錄僅採當輪平台宣告模型，無明確宣告或無法確認填 `Unknown`。
    3. **嚴禁淺層敷衍與架構債逃逸 (Zero Shallow Patches Axiom)**：根因導向 (RCA First)，嚴禁敷衍修補（異常掩蓋、死代碼/特例硬編碼、測試自欺、規格組態敷衍）；次要衍生問題落實「停手 -> 深度歸因 -> 範疇保護」。
  - **條件技能分流導航 (Conditional Skill Routing)**：調用原生工具或進入特定情境前強制觸發對應技能手冊（如 `development-sop`, `yscb-cli-guild`, `documentation`, `yscb-module-dev`, `knowledge-db-search` 等）。
  - [*] **提示**：SOP 0~7 完整生命週期與模板規範已完整收錄於 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)，於開立或推進計畫時（如 [/NewPlan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)、[/Continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)）按需精讀。

### 步驟 2：加載 CLI 指令手冊與專案演進脈絡
- **讀取檔案**：
  - 指令防呆情境手冊：[`yscb-cli-guild`](`__#{module://agents-workflow/assets/skills/yscb-cli-guild/SKILL.md}__`)
  - 專案最新變更日誌：[`CHANGELOG.md`](`__#{project://CHANGELOG.md}__`) (前 2 ~ 3 個區塊)
  - 專案特化命名規範：[`STANDARDS.md`](`__#{workflow.docs://_project/STANDARDS.md}__`) *(若專案未獨立提供則略過)*
- **提取要點**：
  - 掌握 CLI 三級權限分級（🟢 [SAFE] 自主安全 / 🟡 [CONDITIONAL] 階段條件 / 🔴 [GATED] 授權守門）。
  - 瞭解專案最近完成了哪些 Dev Plan 與架構優化。

### 步驟 3：檢查進行中計畫狀態與大綱
- **調取狀態**：執行 `python __${yscb.host://yscb.py}__ agents-workflow plan status` (若環境支援 CLI) 或以唯讀工具檢視 `__${project://plans}__` 進行中計畫目錄。
- **輕量載入與防呆鐵律**：
  - [!] **嚴禁批次深入閱讀**：在 ContextInit 階段**絕對禁止批次或深入讀取 `workflow.plans://` 各計畫內的詳細文件**（如 P00~P07），僅需調取 `plan status` 大綱掌握全貌即可，避免浪費 Prompt Token 與上下文污染。
  - **按需接手原則**：只有在後續收到開發者明確指示「接續/接手特定計畫開發」時，方可在 [/Continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`) 流程中深入讀取該 Plan 目錄與 `handoff.md`。
- **提取要點**：
  - 快速掌握當前是否有進行中計畫及其所處 Phase。

`__@{WORKFLOW_CONTEXTINIT}__`

---

## 輸出成果：極精簡熱啟動狀態卡 (Context Warmup Card)

完成上述檔案讀取後，對話 Session **嚴禁傾倒冗長規範全文或重複說明**，強制僅向開發者呈遞以下極簡狀態卡並結束當前 Turn：

```markdown
### 專案上下文已成功熱啟動 (Context Initialized)
- **核心紀律**：零臆測 / SSOT 對話節流 / 條件技能分流 / CLI 權限守門已加載
- **專案脈絡**：[1 行近期架構或變更摘要]
- **進行中計畫**：[當前進行中計畫名稱與 Phase / 或無進行中計畫]
- **待命就緒**：已掌握全專案規範，請問今天準備進行什麼任務？
```
