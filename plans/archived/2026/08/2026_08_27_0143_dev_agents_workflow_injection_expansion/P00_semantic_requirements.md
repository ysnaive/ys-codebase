# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 計畫類型：Refactor & Standards  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > "我發現 Agents 過度濫用 dev 指令，開啟新計畫 /NewPlan : dev 對 agents-workflow 注入之內容擴充"
- **核心目標**：
  - 釐清 Agent 在何種情境、階段或操作下存在過度濫用 `dev` 指令（如 `dev check`, `dev test`, `dev build`, `dev release` 等）之具體行為與問題樣態。
  - 擴充 `dev` 模組透過 `contributes["agents-workflow"]` 注入至工作流標準庫之工程規範（如 `DevEngineeringStandards.md`），建立更精準、剛性的指令調用守門與邊界防呆。
- **邊界排除 (Explicitly Excluded)**：
  - *(待討論釐清後補充)*

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (雙星伴隨初始化)**：
  - 開立計畫目錄 `workflow.plans://2026_08_27_0143_dev_agents_workflow_injection_expansion/`，伴隨建立 `P00_semantic_requirements.md` 與 `changelog.md`。
- **[P00:DR-02] (啟動 R01 專題調研：問題歸納與統整)**：
  - 依開發者指示發起專題調研 [`R01_problem_summary_and_synthesis.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_0143_dev_agents_workflow_injection_expansion/R01_problem_summary_and_synthesis.md)。
  - 將「**問題 1：Agent 認知邊界混淆，未優先依賴 `.agents/` Context-First 而是越界翻查 `source/` 源碼**」列為首要核心議題收錄並展開剖析。
- **[P00:DR-03] (定稿 6 大 dev 指令濫用情境與防呆守門)**：
  - 收錄開發者提供的 6 大具體情境（測試前多餘 build 與 `--all`、本地部署過度 bump/release、未授權 bump、微調即全量跑測、濫用內部 `op-test` 導致沙盒洩漏、忽略 `--help` 盲目翻閱 CLI 源碼）。
- **[P00:DR-04] (Core 原生宣告式 CLI 治理與 `AGENTS_CLI_GUILD` 動態 Token)**：
  - **Schema 升級與廢除頂層**：徹底廢除舊版頂層 `contributes.commands` 特例格式，100% 統一宣告於 `contributes["core"]["commands"]`。Schema 包含必填 `description` 與可選 `case_pros`、`case_cons`。
  - **`AGENTS_CLI_GUILD` 過濾與生成**：由 `core` 模組向 `agents-workflow` 宣告並提供動態 Token；若某指令之 `case_pros` 與 `case_cons` 兩者皆無或皆為空，則自動排除於 `AGENTS_CLI_GUILD` 生成清單（`yscb.py --help` 依然完整顯示）。
  - **`yscb.py` 適配**：調整 `yscb.py` 僅讀取 `contributes.core.commands`，提取 `description`。
- **[P00:DR-05] (Agents-Workflow 新增 `AgentsCliGuild.md` 與剛性確認守門)**：
  - **新增標準資產**：`agents-workflow` 新增 `standards/AgentsCliGuild.md`（宣告 export），內嵌 `__@{AGENTS_CLI_GUILD}__` 錨點自動物化。
  - **強制比對與確認守門**：在 `AgentsStandards.md` 注入剛性鐵律：Agent 想調用 `yscb` CLI 時必須比對 `AgentsCliGuild.md` 對照表；若無對應欄位或屬於未明確定義情境，嚴禁擅自執行，必須向開發者確認調用意圖與預期指令，獲允許後方可執行。
- **[P00:DR-06] (修復 ContextInit.md 編譯器原文件指針與過時配置)**：
  - **編譯器原文件路徑指針**：`ContextInit.md` 步驟 2 指向 `[DevelopmentStandards.md](__#{module://agents-workflow/assets/standards/DevelopmentStandards.md}__)` 與 `[AgentsCliGuild.md](__#{module://agents-workflow/assets/standards/AgentsCliGuild.md}__)`，由編譯器自動轉譯為各 Target 相對超連結。
  - **清理廢棄檔案讀取**：移除步驟 4 對 `config.project.json` 的讀取，改為直接檢查 `workflow.plans://` 與 `workflow.archived://`。

---

## 3. 開放議題與確認紀錄

- [x] 啟動 R01 專題調研並歸納問題 1（已於 [P00:DR-02] 記錄）
- [x] 補充並定稿 6 大 `dev` 指令濫用情境與根因（已於 [P00:DR-03] 與 R01 記錄）
- [x] 確定 Core 宣告式 `contributes.core.commands` 規格與 `AGENTS_CLI_GUILD` 動態 Token 機制（已於 [P00:DR-04] 定稿）
- [x] 確定 `agents-workflow` 新增 `AgentsCliGuild.md` 與 CLI 強制確認守門鐵律（已於 [P00:DR-05] 定稿）
- [x] 確定修復 `ContextInit.md` 原文件指針轉譯與純淨 URI 掃描（已於 [P00:DR-06] 定稿）
- [x] 待開發者確認本階段需求與調研結論是否完整，指示定稿 P00 並決定後續分流層級。（已於 2026-08-27 確認定稿）
