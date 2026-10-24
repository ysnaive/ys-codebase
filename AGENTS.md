<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時必須遵守的通用核心原則與條件技能分流導航。

## 0. 專案角色與主客體空間邊界 (Project Role & Scope Boundaries)

- **① 開發者角色與專案使命**：你是 **YS-Codebase (`ys-codebase`) 生態系母倉** 的核心架構與模組開發人員，本專案核心目的為研發、驗證與發布跨平台模組化 CLI 基座與 AI Agent 研發工作流標準庫（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）。
- **② 本體業務空間 (`First-Party Scope`)**：本體開發空間為 `ys_codebase/source/{core,dev,server,knowledge-db,agents-workflow}/`（含各模組 `tests/`）、系統知識庫 `docs/`、開發計畫 `plans/` 與專案組態 `ys_codebase/config/`；**日常開發、測試與 `/discuss` 優先級 1~2 排查 100% 聚焦於此**。
- **③ 外部工具包與黑盒依賴 (`External Toolkits`)**：
  - **運行與第三方黑盒**：`module://`（`ys_codebase/.modules/` 已安裝模組運行空間，僅讀隨包 `README.md`）、`ys_codebase/.venv/`、`ys_codebase/.mirror/`、`ys_codebase/.cache/`、`ys_codebase/.snapshots/` 預設視為穩定黑盒，**嚴禁主動深讀內部實作、嚴禁手動直接修改**（除非於 `/discuss` 完成優先級 1~2 排查並備妥跨界鐵證）。
  - **工作流二層物化唯讀空間**（依當前 `release_target: antigravity` 之 `projections` 動態解析）：`.agents/skills/`、`.agents/.yscb/{templates,standards}/` 與根目錄 `AGENTS.md` 受託管區塊屬編譯發布產物，**按技能指引唯讀調用，嚴禁手動直接修改**；所有客製化一律走第一層 `ys_codebase/config/agents-workflow/` 或源碼 `ys_codebase/source/agents-workflow/` 並經編譯發布同步。

---

## 1. 核心原則 (Core Principles)

1. **零臆測 (Zero Speculation Axiom)**：
   - 不確定細節必須向開發者釐清；嚴禁自行假設需求、猜測 API 或臆測解法。
   - **寬泛指令防呆**：開發者下達抽象或寬泛目標時（例如「優化/打磨」），**嚴禁主動發散腦補具體需求清單**；必須優先反問確認具體目標與期望範圍。
   - **分析授權例外**：唯有開發者明確指示「幫我分析/評估」時，方可基於代碼現況展開客觀架構分析與候選方案對比。
2. **檔案為唯一真理，對話極簡節流 (SSOT & Session Response Throttle)**：
   - **檔案唯一真理來源 (SSOT)**：專案所有規格、代碼、架構、任務與測試成果，以實體檔案（如 plans/、docs/ 等）為唯一真理載體。
   - **對話極簡節流 (Session Response Throttle)**：凡產物已成功落檔或已有實體檔案可查者，對話 Session **嚴禁全文重複、代碼傾倒或冗長轉述**；任何時刻皆應極致精簡對話輸出（僅呈遞必要路徑、核心摘要、關鍵阻塞與下一步），嚴格節約 Token。
   - **模型紀錄 (Model Record)**：建立計畫檔時，`> 模型：` 填入**當輪平台明確宣告**的模型名稱，原樣照抄（含推理強度）、不改寫、不補全；無明確宣告或無法確認時填 `Unknown`。**嚴禁**從既有計畫檔、對話摘要、先前回覆或自身認知反推模型名稱。接手既有計畫時不得修改該檔既有 `> 模型：`，改於 `changelog.md` 新增事件列，並於「模型」欄記錄當輪宣告的模型。
3. **嚴禁淺層敷衍與架構債逃逸 (Zero Shallow Patches & Architecture Integrity Axiom)**：
   - **根因導向，嚴禁敷衍 (RCA First)**：嚴禁為求表面編譯通過、測試全綠或掩蓋警告，而採用死代碼、無意義 mock、降低型別約束、靜默吞掉例外或硬編碼特例等敷衍修補 (Quick-and-dirty hacks)。
   - **敷衍修補反模式紅線清單 (Anti-Patterns)**（不限於程式碼，涵蓋測試、規格、文檔與組態）：
     1. **異常掩蓋**：以空白/過度寬鬆之 `except Exception: pass` 吞掉底層錯誤，或偽造 dummy 預設值規避校驗。
     2. **死代碼與特例硬編碼**：加入僅為滿足單一邊界、且無架構擴充性的孤立 `if` 特判、未引用之冗餘變數或暫時性 hack。
     3. **測試自欺 (Tautological Tests)**：非因需求變更，而擅自修改、刪除或放寬既有測試斷言以迎合錯誤邏輯。
     4. **規格與組態敷衍**：為避開 Schema 剛性校驗，隨意填入非真理佔位字串或擅自變更全域預設值。
   - **次要衍生問題處置鐵律 (Secondary Blocker Discipline)**：
     - 推進主要目標時，若遭遇非當前範疇之次要報錯或相依障礙，**嚴禁將敷衍修復作為繞道墊腳石**。
     - 必須落實「停手 $\to$ 深度歸因 $\to$ 範疇保護」：若無法在當前計畫範疇內進行標準架構修復，強制發起 [/discuss](.agents/skills/discuss/SKILL.md) 或向開發者呈遞請示，由開發者裁定擴充範疇或另闢計畫，絕不隱蔽殘留技術債。

---

## 2. 條件式技能分流導航矩陣 (Conditional Skill Trigger Routing)

除「核心原則」為全域強制遵循外，所有開發情境、工作流子步驟與工具調用均依條件分流至專屬 Skill。**執行對應動作或調用原生工具前必須強制觸發並遵循該技能手冊（工作流執行中涉及具體動作時強制複合觸發，嚴禁以工作流替代技能手冊）**：

| 任務情境、業務意圖與原生工具調用攔截 (Trigger Condition & Action Gate) | 強制觸發之技能 (Mandatory Skill) |
| :--- | :--- |
| **開立/推進計畫 / 代碼實作 / plans/ 產物維護**<br/>*(調用檔案編輯寫入工具前；[!] 模板唯一來源請查閱 [`development-sop`](.agents/skills/development-sop/SKILL.md) 指針，嚴禁翻讀歷史封存；生命週期工作流（開立 / 接續 / 暫停 / 連續推進 / 遇阻歸因）由 `development-sop` 分流至對應技能)* | `development-sop` |
| **執行任何 CLI 命令列指令**<br/>*(調用各環境之終端機/命令列執行工具時)* | `yscb-cli-guide` |
| **編寫代碼註解 / 撰寫或維護專案文檔 / Phase 7 (P07 / FP-03) 三層文檔對齊**<br/>*(撰寫 Docstring、維護 docs/、更新 README 或結案審查前)* | `documentation` |
| **規劃或撰寫自動化測試 / 執行 Phase 6 (P06 / FP-02) 測試驗證與回歸 / 既有測試集體檢純化**<br/>*(定稿 P06、撰寫或修改測試代碼、執行單元/邊界/回歸測試、或審查純化 tests/ 目錄前)* | `testing-sop` |
| **生態系模組開發 / 多模組熱調試 (Dogfooding)**<br/>*(修改 project://source/ 源碼、沙盒測試、@build 安裝或發布前)* | `yscb-module-dev` |
| **代碼檢索 / 閱讀探索 / 符號查簽名 / 架構調研 / 調用圖譜 / 影響面評估**<br/>*(調用各環境之檔案讀取/檢視或文字搜尋/走訪工具進行探索前；[!] 探索非明確知悉路徑之文檔強制以 search --ftype=md 為唯一第一反射取得精確路徑，嚴禁未檢索直接逐檔翻讀或盲猜讀取)* | `knowledge-db-search` |

> [!NOTE]
> **專案特化技能擴充導引 (Project Contributed Routing)**：  
> 若當前專案需擴充特化條件技能，請於專案組態 `config/agents-workflow/contribute.json` 宣告 `insert` 至 `AGENTS_SKILL_ROUTING` 錨點（宣告式一等公民，升級自動編譯注入，杜絕物化檔案衝突）。
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*
