---
name: context-init
description: 載入專案核心規範、近期變更與活躍計畫狀態以完成對話熱啟動。僅於顯式輸入 /context-init 或明確指示初始化專案上下文時觸發。
---

# 專案上下文初始化流程 (ContextInit)

本 Skill 用於在全新對話 (Session / Chat) 開始或上下文重置後，快速加載專案的核心架構、歷史變更、程式碼規範與 Agent 紀律。確保 Agent 以最小 Token 開銷 100% 掌握專案默契與工程標準。

---

## 核心原則

1. **沙盒 100% 安全與跨平台讀取 (Sandbox Native Read)**：優先使用當前宿主環境內建的唯讀檔案讀取工具（例如 `read_file`、`view_file`、`Read` 或 `View`），不強行依賴需額外權限的 Shell 命令，確保在沙盒模式與完全存取模式下均能無障礙秒級執行。
2. **零臆測脈絡 (Zero Speculation)**：從既有真實文檔（`CHANGELOG.md`、`STANDARDS.md`、`AGENTS.md`）載入現況，不自行假設專案結構。
3. **語意 URI 標準化 (Semantic URI Protocol)**：透過 `project://`、`workflow.docs://`、`workflow.plans://` 等標準協議精準指向各級資源。
4. **極簡 Token 高效加載**：僅抽取專案的核心公理與最新變更，嚴禁在此階段批次載入無關計畫內部細節。

---

## 執行步驟

當使用者輸入 `/context-init`（或 `/ContextInit`）或 Agent 偵測到是全新的對話 Session 時，Agent **必須順序執行**以下檢核步驟：

```markdown
/ContextInit 熱啟動檢核表：
- [ ] 步驟 1：讀取 AGENTS.md (或 AgentsStandards.md) 提取三大核心原則與技能分流規則
- [ ] 步驟 2：讀取 yscb-cli-guide、CHANGELOG.md 近期紀錄與 STANDARDS.md
- [ ] 步驟 3：檢視進行中計畫狀態大綱（僅看狀態，禁止深入讀取 P00~P07 細節）
- [ ] 步驟 4：輸出極簡熱啟動狀態卡並立即 End Turn
```

### 步驟 1：[!] 加載專案行為準則與防呆紀律 (Mandatory Standards Read)
- **讀取檔案**：[`AGENTS.md`](`__#{project://AGENTS.md}__`) *(或 [`AgentsStandards.md`](`__#{module://agents-workflow/assets/standards/AgentsStandards.md}__`))*
- **強制提取要點**：
  - **專案角色與主客體空間邊界 (Project Role & Scope Boundaries)** *(若專案已配置)*：第一時間辨識第一方活躍開發源碼空間、外部工具鏈/運行期黑盒目錄與工作流物化唯讀空間，嚴禁越界直接修改唯讀產物。
  - **三大核心原則**：
    1. **零臆測 (Zero Speculation Axiom)**：不確定細節必須向開發者釐清；寬泛指令嚴禁自行腦補，優先反問確認具體目標。
    2. **檔案唯一真理與對話極簡節流 (SSOT & Throttle)**：產物以實體檔案為唯一真理來源；對話嚴禁全文重複或代碼傾倒，極致精簡節約 Token；模型紀錄僅採當輪平台宣告模型，無明確宣告或無法確認填 `Unknown`。
    3. **嚴禁淺層敷衍與架構債逃逸 (Zero Shallow Patches Axiom)**：根因導向 (RCA First)，嚴禁敷衍修補（異常掩蓋、死代碼/特例硬編碼、測試自欺、規格組態敷衍）；次要衍生問題落實「停手 -> 深度歸因 -> 範疇保護」。
  - **條件技能分流導航 (Conditional Skill Routing)**：調用原生工具或進入特定情境前強制觸發對應技能手冊（如 `development-sop`, `yscb-cli-guide`, `documentation`, `yscb-module-dev`, `knowledge-db-search` 等）。
  - [*] **提示**：SOP 0~7 完整生命週期與模板規範已完整收錄於 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)，於開立或推進計畫時（如 [/NewPlan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)、[/Continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)）按需精讀。

### 步驟 2：加載 CLI 指令手冊與專案演進脈絡
- **讀取檔案**：
  - 指令防呆情境手冊：[`yscb-cli-guide`](`__#{module://agents-workflow/assets/skills/yscb-cli-guide/SKILL.md}__`)
  - 專案最新變更日誌：[`CHANGELOG.md`](`__#{project://CHANGELOG.md}__`) (前 2 ~ 3 個區塊)
  - 專案特化命名規範：[`STANDARDS.md`](`__#{workflow.docs://_project/STANDARDS.md}__`) *(若專案未獨立提供則略過)*
- **提取要點**：
  - 掌握 CLI 三級權限分級（🟢 `[SAFE] 自主安全` / 🟡 `[CONDITIONAL] 階段條件` / 🔴 `[GATED] 授權守門`）。
  - 瞭解專案最近完成了哪些 Dev Plan 與架構優化。

### 步驟 3：檢查進行中計畫狀態與大綱
- **調取狀態（預設與降級備援）**：
  - **預設方式**：若環境支援 CLI，執行 `python __${yscb.host://yscb.py}__ agents-workflow plan status` 取得計畫狀態大綱。
  - **降級備援（Fallback）**：若處於純唯讀沙盒或 CLI 尚未就緒，直接以宿主內建的唯讀檔案/目錄檢視工具列出 `__${project://plans}__` 進行中計畫目錄與最新檔案標頭狀態。
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
- **待命就緒**：已掌握全專案規範，請問今天準備進行什麼任務？（如欲接續既有計畫可輸入 `/continue`，開立新任務可輸入 `/new-plan`；初次探索功能可輸入 `/how-to-yscb`，健檢或配置專案設定可輸入 `/how-to-config-yscb`）
```

---

## 常見踩坑指南 (Gotchas)

- **切勿因找不到選配檔案而中斷初始化**：`STANDARDS.md` 或空的 `__${project://plans}__` 目錄屬於正常情況，略過並於狀態卡如實標註即可。
- **切勿在熱啟動階段預先載入所有參考檔**：`development-sop/references/` 下的各階段手冊僅在實際進入該 Phase 時按需讀取，熱啟動時切勿一次讀入。
