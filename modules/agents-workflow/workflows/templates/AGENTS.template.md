# Agent 專案行為準則與工作流指南 (AGENTS.template.md)

<!-- YSCB_AGENTS_BEGIN -->
本文件定義 Agent 在專案內執行任務時**必須強制遵守**的硬性規則、工作流程引導與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

Agent 必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，都必須與開發者釐清後才能推進。禁止自行假設需求、猜測 API 行為或臆測解法。
2. **可追溯 (Traceability)**：從需求到程式碼的每一步決策，都必須有文件記錄可回溯（P00 語意 → P01 FR/EC → [{Phase}:DR-XX] → API 簽名 → 程式碼 → 測試）。
3. **分級管控 (Graduated Control)**：完整 Phase 0 語意化討論後，依三大分流層級矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 分類型主計畫模式)。

### 🚨 執行紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予對該階段的「確認/同意/推進」指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答 Agent 提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至 Phase X？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能將當前 Phase 標記為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrail)**：
  - **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤、異常或視覺/邏輯不符預期時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
  - **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 `/Discuss` 向開發者呈遞調用證據，由開發者判定。
  - **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 `/Discuss` 進行 5-Whys 根因分析。
- **模板註解剝除鐵律 (Template Guidance Stripping)**：
  - 模板開頭的 `<!-- === AGENT_GUIDANCE === ... -->` 區塊為 Agent JIT 指引，Agent 在生成實際 Markdown 檔案時**嚴禁輸出任何 HTML 導引註解**，必須保持目標文檔純淨。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須於 Phase 2~3 隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段與 `P04_implementation_plan.md` 一併剛性定稿 (Confirmed)，嚴禁延至 Phase 6 才開始憑空設計測試項目。
- **Phase 6 UX / 手動測試 Checkpoint 強制等待關卡**：即使 CLI 自動化測試 100% Passed，Agent **絕對禁止**自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須呈遞 CLI 測試結果，並明確詢問開發者進行 UX/手動視覺與互動驗證。必須等待開發者明確回覆「UX 驗證通過/指示免測」後，方可將 P06 標記為 Passed 並推進至 Phase 7。
- **Phase 6 驗證防呆鐵律 (無 Log 即未驗證)**：若 CLI 編譯/測試命令執行受阻，Agent **絕對禁止**在 `P06_test_plan.md` 與對話中標記 `Passed`。必須明確標記 `[未實機編譯/僅靜態檢查]`，並呈遞精確命令請開發者於控制台執行回填。
- **全階段文件模板剛性對齊**：所有 Phase (P00~P07 / FT_plan / umbrella_overview) 產出文件 **必須 100% 嚴格鏡像標準模板結構**（包含 `workflows/templates/` 中定義的所有指定欄位、表格與 Header 規範標頭，含 `> 擴充項目：`），嚴禁 Agent 自行簡化或遺漏模板區塊。
- **Phase 0 討論模式鐵律**：
  - **Agent 嚴禁臆測需求**：在 Phase 0 討論階段，Agent 僅作為知識顧問，針對開發者陳述提出釐清問題。除非開發者明確要求，否則嚴禁主動提出設計方案、功能清單或架構建議。
  - **討論結束必須由開發者明確宣告**：Agent 絕對禁止自行判定討論已完整並推進。必須等待開發者明確表示後，才可將 `P00_semantic_requirements.md` 標記為 `Confirmed`。
  - **三大分流層級在 P00 Confirmed 後才執行**：P00 確認後，在同一輪呈遞三大分流層級建議（Level 0: Fast Track / Level 1: Full Track / Level 2: Umbrella Full Track $\times$ n），由開發者最終決定 Track。
- **主/子計畫管理與巢狀層級硬性約束**：
  - **模式 A (衍生型子計畫)**：Phase 6 發現衍生非當前範疇問題時，於主目錄下開立 `sub_XX` 子計畫（預設 Fast Track）。
  - **模式 B (分類型主計畫 Umbrella)**：多個功能情境或跨模組大型任務時開立 Umbrella 主計畫，以 `umbrella_overview.md` 統籌，子計畫拆分評估以**單個 Full Track 能處理之顆粒度**為單位。
  - **最多兩層約束**：專案嚴格限制子計畫目錄最多**兩層結構**（主計畫 ➔ 子計畫），**絕對禁止在子計畫下再開子計畫**！
- **Phase 1 / FT-1 規格轉譯嚴禁臆測條款**：
  - `P01_requirements_spec.md` 與 `FT_plan.md` 中的**每一個 FR 必須可回溯至 `P00_semantic_requirements.md` 中的具體使用情境或 API 使用案例**，填入「對應 P00 語意」欄。
  - 嚴禁 Phase 1 / FT-1 在 P00 範疇之外新增未經討論的功能點。
- **沙盒模式命令安全防護與防卡死鐵律**：
  - **權限模式探測**：Agent 在發起任何 CLI 命令前，應探測當前權限模式。
  - **沙盒模式降級呈遞**：當處於沙盒防護模式且命令未放行時，優先呈遞精確 Terminal 指令供手動執行，嚴禁盲目發起可能掛起的背景 Task。
  - **背景 Task 限時與防堆疊**：嚴禁無窮 Polling 或重複堆疊背景 Task 防止 IDE 卡死。
- **對話視窗 vs. 文檔檔案排版與語法邊界鐵律 (Chat vs. Docs Rendering Rules)**：
  - **對話視窗 (Chat Window / CLI 終端輸出)**：
    - 🚫 **嚴禁使用 Mermaid 圖表**（終端與 CLI 無法解析渲染，一律使用純文字樹狀圖、ASCII 與 Markdown 表格）。
    - 🚫 **嚴禁使用 LaTeX 數學公式**（終端無法渲染 `$...$` / `$$...$$` 會產生混亂代碼，一律使用純文字清晰表示，例：`O(N log N)`、`x >= y`）。
  - **Markdown 文檔檔案本體 (`.md` 文件)**：
    - ✅ **盡量使用強定義語法以提高專業度與視覺化品質**：
      - 圖表排版：盡量使用 **Markdown 表格** 或 **垂直排版 Mermaid (TD / TB)**。
      - 數學與複雜算式：盡量使用 **標準 LaTeX 公式**（如 `$E = mc^2$`、`$O(N^2)$`）。
  - **超連結規範**：`.md` 文檔正文內部跳轉超連結一律採用標準相對路徑（確保 IDE / GitHub 原生點擊跳轉）。

- **知識庫 7 大抽象維度與 1:1 交付原則 (Documentation 7-Dimension & Delivery)**：
  - **事實與過程分離**：專案知識庫（`docs://`）只陳述「當前客觀事實與坑點」，不記錄歷史辯論過程（辯論留於 `plans://`）。
  - **中觀專題手冊 (Topic Docs)**：凡涉及多物件協同、狀態機、資料管線、通訊協議或並發模型（維度 3），嚴禁塞在單一函式註解或撐爆模組 README，強制建立獨立 `docs/<Module>/[topic].md`。
  - **工程妥協 (Design Notes)**：凡包含非直觀實作或 Workaround（維度 5），強制於 `docs/<Module>/DESIGN_NOTES.md` 登記 `DN-XX` 與 `[!CAUTION]`。
  - **三維錨點 1:1 交付驗收**：Phase 4 依 P03/P05/P06 預排文檔衝擊清單，Phase 7 Walkthrough 必須 1:1 核對全數交付。

- **目錄歸檔紀律與 CLI 調度優先**：
  - **統一 CLI 指令優先**：進行歷史 Dev Plan / DR 檢索、狀態掃描、合規驗證、知識庫巡檢、擴充查詢或計畫歸檔等定式作業時，必須優先呼叫 `python yscb_cli.py agents-workflow <verify|scan|search|archive|docs|ext>` 指令。
  - **嚴禁主動歸檔**：所有計畫預設留存原位（`plans://`），僅在開發者明確下達歸檔指令時才執行歸檔。

- **計畫內部日誌 vs. 全域變更日誌職責分離 (Changelog Separation)**：
  - **`plans://<plan>/changelog.md`**：【計畫內部微觀日誌】記錄當前 Dev Plan 內部 Phase 轉換、DR 決策與偏差，開立計畫目錄時**必須與 P00 剛性伴隨初始化**。
  - **`project://CHANGELOG.md`**：【全專案高階發布日誌】僅於 Phase 7 / FT-3 結案審查階段，由 Agent 追加本次 Dev Plan 的高階版本摘要。

---

## 2. Codebase 專用語意 URI 協定 (Semantic URI Protocol)

本專案支援語意 URI 協定，用於跨層級定位檔案，避免脆弱的相對路徑跳轉：

| URI 協議 | 核心語意 | 說明 |
| :--- | :--- | :--- |
| **`project://<path>`** | 專案根目錄 | 指向專案最頂層根目錄（例：`project://AGENTS.md`、`project://CHANGELOG.md`） |
| **`yscb://<path>`** | 工具庫根目錄 | 指向工具庫源碼或安裝目錄（例：`yscb://source/core`） |
| **`plans://<path>`** | 活躍開發計畫目錄 | 指向進行中 Dev Plan 目錄（由 `config.project.json` 之 `paths.plans_dir` 定義） |
| **`archive://<path>`** | 歷史歸檔目錄 | 指向歷史封存計畫目錄（由 `config.project.json` 之 `paths.archive_dir` 定義） |
| **`docs://<path>`** | 專案知識庫目錄 | 指向系統知識庫目錄（由 `config.project.json` 之 `paths.docs_dir` 定義） |
| **`sop_ext://<path>`** | 專案 SOP 擴充清單目錄 | 指向專案特化擴充清單目錄（由 `config.project.json` 之 `paths.extensions_dir` 定義） |

### 🛠️ URI 終端動態解析指令
```bash
# 解析語意 URI 為實體絕對路徑
python yscb_cli.py uri resolve docs://_project/STANDARDS.md

# 列出所有已註冊協議與當前狀態
python yscb_cli.py uri list

# 將本機實體路徑轉為語意 URI
python yscb_cli.py uri to-uri docs/_project/STANDARDS.md
```
> **注意**：同目錄下的檔案引用（如 `P01` 引用同目錄的 `P00`）仍維持標準相對路徑（例：`[P00](./P00_semantic_requirements.md)`）。

---

## 3. 自動 Workflow 觸發引導 (Workflow Triggers)

當接收到開發或文檔相關需求時，Agent 應自動對齊並參考以下 Workflow：

| 開發情境 / 指令 | 對應 Workflow 檔案 | 說明 |
| :--- | :--- | :--- |
| **新 Session/Chat 啟動上下文** | [ContextInit.md](./workflows/ContextInit.md) | 在沙盒與全權限模式下安全秒級熱啟動專案規範與歷史脈絡 |
| **開始新功能開發 / 重大修改** | [NewPlan.md](./workflows/NewPlan.md) | 從 Phase 0 開始執行完整的 SOP 分析與三大分流規劃 |
| **接續中斷或已存在的計畫** | [Continue.md](./workflows/Continue.md) | 自動掃描 `plans://` 目錄，偵測 `handoff.md` 並恢復進度 |
| **大型/跨度大的深度技術調研** | [Research.md](./workflows/Research.md) | 深度技術探討、業界方案對比與 `R01_xxx.md` 報告產出 |
| **開發遇阻/根因排查** | [Discuss.md](./workflows/Discuss.md) | 強制停手、5-Whys 根因分析、防範排查越界與淺層修補 |
| **暫停開發/現場凍結交接** | [Pause.md](./workflows/Pause.md) | 於計畫目錄生成 `handoff.md` 現場狀態，保證零斷層接手 |
| **開發完成後品質與細節審查** | [Review.md](./workflows/Review.md) | 調用 `python yscb_cli.py agents-workflow verify` 執行全量稽核 |
| **構想與靈感孵化池** | [Idea.md](./workflows/Idea.md) | 開放式自由探討，產出 What/Why/How/Related 提案書 |
| **更新 / 檢索專案知識庫文檔** | [DocumentationStandards.md](./workflows/DocumentationStandards.md) | 遵循 1:1 鏡像結構維護 `docs://` |
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化 C++11 / C# / 硬體架構規範填寫於此，不受中央標準庫覆蓋)*
