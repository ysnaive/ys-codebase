<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時必須遵守的通用核心原則與條件技能分流導航。

---

## 1. 核心原則 (Core Principles)

1. **零臆測 (Zero Speculation Axiom)**：
   - 不確定細節必須向開發者釐清；嚴禁自行假設需求、猜測 API 或臆測解法。
   - **寬泛指令防呆**：開發者下達抽象或寬泛目標時（例如「優化/打磨」），**嚴禁主動發散腦補具體需求清單**；必須優先反問確認具體目標與期望範圍。
   - **分析授權例外**：唯有開發者明確指示「幫我分析/評估」時，方可基於代碼現況展開客觀架構分析與候選方案對比。
2. **檔案為唯一真理，對話極簡節流 (SSOT & Session Response Throttle)**：
   - **檔案唯一真理來源 (SSOT)**：專案所有規格、代碼、架構、任務與測試成果，以實體檔案（如 plans、docs 等）為唯一真理載體。
   - **對話極簡節流 (Session Response Throttle)**：凡產物已成功落檔或已有實體檔案可查者，對話 Session **嚴禁全文重複、代碼傾倒或冗長轉述**；任何時刻皆應極致精簡對話輸出（僅呈遞必要路徑、核心摘要、關鍵阻塞與下一步），嚴格節約 Token。
3. **嚴禁淺層敷衍與架構債逃逸 (Zero Shallow Patches & Architecture Integrity Axiom)**：
   - **根因導向，嚴禁敷衍 (RCA First)**：嚴禁為求表面編譯通過、測試全綠或掩蓋警告，而採用死代碼、無意義 mock、降低型別約束、靜默吞掉例外或硬編碼特例等敷衍修補 (Quick-and-dirty hacks)。
   - **敷衍修補反模式紅線清單 (Anti-Patterns)**（不限於程式碼，涵蓋測試、規格、文檔與組態）：
     1. **異常掩蓋**：以空白/過度寬鬆之 `except Exception: pass` 吞掉底層錯誤，或偽造 dummy 預設值規避校驗。
     2. **死代碼與特例硬編碼**：加入僅為滿足單一邊界、且無架構擴充性的孤立 `if` 特判、未引用之冗餘變數或暫時性 hack。
     3. **測試自欺 (Tautological Tests)**：非因需求變更，而擅自修改、刪除或放寬既有測試斷言以迎合錯誤邏輯。
     4. **規格與組態敷衍**：為避開 Schema 剛性校驗，隨意填入非真理佔位字串或擅自變更全域預設值。
   - **次要衍生問題處置鐵律 (Secondary Blocker Discipline)**：
     - 推進主要目標時，若遭遇非當前範疇之次要報錯或相依障礙，**嚴禁將敷衍修復作為繞道墊腳石**。
     - 必須落實「停手 $\to$ 深度歸因 $\to$ 範疇保護」：若無法在當前計畫範疇內進行標準架構修復，強制發起 [/Discuss](.agents/workflows/Discuss.md) 或向開發者呈遞請示，由開發者裁定擴充範疇或另闢計畫，絕不隱蔽殘留技術債。

---

## 2. 條件式技能分流導航矩陣 (Conditional Skill Trigger Routing)

除「核心原則」為全域強制遵循外，所有開發情境、工作流子步驟與工具調用均依條件分流至專屬 Skill。**執行對應動作或調用原生工具前必須強制觸發並遵循該技能手冊（工作流執行中涉及具體動作時強制複合觸發，嚴禁以工作流替代技能手冊）**：

| 任務情境、業務意圖與原生工具調用攔截 (Trigger Condition & Action Gate) | 強制觸發之技能 (Mandatory Skill) |
| :--- | :--- |
| **開立/推進計畫 / 代碼實作 / plans/ 產物維護**<br/>*(調用檔案編輯寫入工具前；[!] 模板唯一來源為 .agents/.yscb/templates，嚴禁翻讀歷史封存)* | `development-sop` |
| **執行任何 CLI 命令列指令**<br/>*(調用各環境之終端機/命令列執行工具時)* | `yscb-cli-guild` |
| **編寫代碼註解 / 撰寫或維護專案文檔 / Review 階段三層文檔對齊**<br/>*(撰寫 Docstring、維護 docs/、更新 README 或 Review 交付前)* | `documentation` |
| **生態系模組開發 / 多模組熱調試 (Dogfooding)**<br/>*(修改 project://source/ 源碼、沙盒測試、@build 安裝或發布前)* | `yscb-module-dev` |
| **代碼檢索 / 閱讀探索 / 符號查簽名 / 架構調研 / 調用圖譜 / 影響面評估**<br/>*(調用各環境之檔案讀取/檢視或文字搜尋/走訪工具進行探索前；[!] 探索非明確知悉路徑之文檔強制以 search --ftype=md 為唯一第一反射取得精確路徑，嚴禁未檢索直接逐檔翻讀或盲猜讀取)* | `knowledge-db-search` |

> [!NOTE]
> **專案特化技能擴充導引 (Project Contributed Routing)**：  
> 若當前專案需擴充特化條件技能，請於專案組態 `config/agents-workflow/contribute.json` 宣告 `insert` 至 `AGENTS_SKILL_ROUTING` 錨點（宣告式一等公民，升級自動編譯注入，杜絕物化檔案衝突）。
<!-- YSCB_AGENTS_END -->