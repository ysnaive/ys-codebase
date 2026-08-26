# 開發標準規範與工作流指南 (Development Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性規則、工作流程引導與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

Agent 必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，都必須與開發者釐清後才能推進。禁止自行假設需求、猜測 API 行為或臆測解法。
2. **可追溯 (Traceability)**：從需求到程式碼的每一步決策，都必須有文件記錄可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：完整 Phase 0 語意化討論後，依三大分流層級矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 分類型主計畫模式)。

### 🚨 執行紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予對該階段的「確認/同意/推進」指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答 Agent 提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能將當前 Phase 標記為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrail)**：
  - **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤、異常或視覺/邏輯不符預期時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
  - **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 Discuss 向開發者呈遞調用證據，由開發者判定。
  - **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 Discuss 進行 5-Whys 根因分析。
- **Phase 0 討論模式鐵律**：
  - **知識顧問模式 (Zero Speculation in Discussion)**：在 Phase 0 討論階段，Agent 僅作為知識顧問，針對開發者陳述提出釐清問題。除非開發者明確要求，否則嚴禁主動提出設計方案、功能清單或架構建議。
  - **討論結束由開發者明確宣告**：Agent 絕對禁止自行判定討論已完整並推進。必須等待開發者明確表示後，才可將 `P00_semantic_requirements.md` 標記為 `Confirmed`。
  - **先 P00 後分流**：P00 確認後，在同一輪呈遞三大分流層級建議，由開發者最終決定 Track。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須於 Phase 2 隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段與 `P04_implementation_plan.md` 一併剛性定稿 (Confirmed)，嚴禁延至 Phase 6 才開始憑空設計測試項目。
- **Phase 6 UX / 手動測試 Checkpoint 強制等待關卡**：即使 CLI 自動化測試 100% Passed，Agent **絕對禁止**自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須呈遞測試結果，並明確詢問開發者進行實際互動/視覺/UX 驗證。必須等待開發者明確回覆「UX 驗證通過/指示免測」後，方可將 P06 標記為 `Passed` 並推進至 Phase 7。
- **Phase 6 驗證防呆鐵律 (無 Log 即未驗證)**：若 CLI 編譯/測試命令執行受阻，Agent **絕對禁止**在 `P06_test_plan.md` 與對話中標記 `Passed`。必須明確標記 `[未實機編譯/僅靜態檢查]`，並呈遞精確命令請開發者於控制台執行回填。
- **全階段文件模板剛性對齊**：所有 Phase (P00~P07 / fast_track_plan / umbrella_overview) 產出文件 **必須 100% 嚴格鏡像標準模板結構**（包含所有指定欄位、表格與 Header 規範標頭），嚴禁 Agent 自行簡化或遺漏模板區塊。
- **雙星伴隨初始化鐵律**：開立計畫目錄時，`P00_semantic_requirements.md` 必須與 `changelog.md` 剛性伴隨同時建立，立即寫入第 1 筆紀錄。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（`plans://`），嚴禁 Agent 主動歸檔，僅在開發者明確下達歸檔指令時才執行歸檔工具。
- **巢狀層級硬性約束**：專案嚴格限制子計畫目錄最多**兩層結構**（主計畫 ➔ 子計畫），**絕對禁止在子計畫下再開子計畫**！

---

## 2. 工作目錄與子計畫管理規範 (Workspace & Sub-Plans)

### 2.1 計畫目錄結構與命名
- **獨立計畫（進行中）**：`plans://{YYYY_MM_DD_HHMM_功能名稱}/`
- **獨立計畫（已歸檔）**：`archive://{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
> `YYYY_MM_DD_HHMM` 採用 24 小時制時間戳，確保同一天建立多個計畫時目錄名稱不產生衝撞。

### 2.2 計畫內部日誌 vs. 全域變更日誌職責分離
- **`plans://<plan>/changelog.md`（計畫內部微觀日誌）**：記錄當前 Dev Plan 內部 Phase 轉換、DR 決策與偏差處置，開立計畫目錄時**必須與 P00 剛性伴隨初始化**。
- **`project://CHANGELOG.md`（全專案高階發布日誌）**：僅於 Phase 7 / FT-3 結案審查階段，由 Agent 追加本次 Dev Plan 的高階發布摘要。

### 2.3 巢狀子計畫管理 (Sub-Plans Architecture)
- **模式 A (衍生型子計畫)**：Phase 6 測試過程中若發現非當前範疇之衍生缺陷或優化需求，於主目錄下開立 `sub_{編號}_{目的}/`（預設 Fast Track），完成後納入主計畫結案報告。
- **模式 B (分類型主計畫 Umbrella)**：多個功能情境或跨模組大型架構演進時開立 Umbrella 主計畫，以 `umbrella_overview.md` 統籌，子計畫拆分評估以**單個 Full Track 能處理之顆粒度**為單位。
- 🚨 **最多兩層約束**：嚴格限制最多兩層目錄（主計畫 ➔ 子計畫），**絕對禁止三層或更多層嵌套**！

---

## 3. 跨文件 ID 引用與剛性追溯鏈 (Traceability & Standard ID Matrix)

為確保從需求到測試的 100% 可追溯性，所有產出文件必須遵循以下標準 ID 格式：

| ID 類別 | 前綴格式 | 範例 | 說明 |
| :--- | :--- | :--- | :--- |
| **功能需求** | `FR-{XX}` | `FR-01`, `FR-02` | 定義於 `P01`，且必須 1:1 追溯至 `P00` 語意 |
| **邊界條件** | `EC-{XX}` | `EC-01`, `EC-02` | 定義於 `P01`，涵蓋異常輸入、邊界與防禦行為 |
| **非功能需求** | `NFR-{XX}` | `NFR-01` | 定義於 `P01`，涵蓋效能、資源、安全與指標約束 |
| **決策紀錄** | `[{Phase}:DR-XX]` | `[P01:DR-01]`, `[P02:DR-02]` | 各階段關鍵架構與技術決策，Phase 前綴確保跨文件全域唯一 |
| **功能測試** | `FT-{XX}` | `FT-01` | 對應 `FR-XX` 的功能測試案例 |
| **邊界測試** | `ET-{XX}` | `ET-01` | 對應 `EC-XX` 的例外與邊界防禦測試案例 |
| **回歸測試** | `RT-{XX}` | `RT-01` | 全系統既有功能與跨模組回歸驗證 |
| **效能測試** | `PT-{XX}` | `PT-01` | 對應 `NFR-XX` 的效能與資源量測測試 |
| **UX/手動驗證** | `UX-{XX}` | `UX-01` | 開發者實機互動、視覺與原生手感驗證 |
| **缺陷紀錄** | `BUG-{XX}` | `BUG-01` | 測試過程中發現的實作錯誤或計畫缺陷 |

> **剛性追溯鏈矩陣**：  
> `P00 語意需求` ➔ `FR-XX / EC-XX` ➔ `[{Phase}:DR-XX] 設計決策` ➔ `API 簽名` ➔ `程式碼實作` ➔ `FT-XX / ET-XX / RT-XX 測試`

---

## 4. 標準生命週期 SOP 0~7 與三大分流 (Lifecycle & Tracks)

### 4.1 三大分流矩陣 (Three-Tier Phasing Matrix)
- **Level 0 (Fast Track)**：修改檔案數 $\le 2$、不變更 Public API / 介面簽名、不引入新的跨模組依賴之純 Bug 修復或輕量擴充。採用 `fast_track_plan.md`（FT-1 規劃 ➔ FT-2 實作 ➔ FT-3 結案）。
- **Level 1 (Full Track)**：單一功能情境、單一模組新增/重構、涉及 API 變更或內部架構調整。標準執行 Phase 0 ~ Phase 7（P00~P07）。
- **Level 2 (Umbrella 主計畫)**：多個功能情境、跨模組大型任務或體系重構。以 `umbrella_overview.md` 統籌，拆分多個 `sub_XX` 子計畫獨立推進。

### 4.2 Phase 0~7 階段流程與核心關卡
- **Phase 0 (語意化需求討論)**：
  - 開放式對話釐清原始意圖與邊界，建立 `P00_semantic_requirements.md` 與 `changelog.md`（雙星伴隨初始化）。
  - **深度調研 (Phase 0-R)**：高複雜度或高未知需求啟動專題調研，產出 **`R{n:2d}_{topic}.md`**（例 `R01_architecture_reference.md`），結論收斂回填 `P00`。
  - 等待開發者明確宣告結束 ➔ P00 Confirmed ➔ 呈遞三大分流建議。
- **Phase 1 (需求規格轉譯)**：
  - 將 P00 語意 1:1 轉譯為 FR、EC、NFR，產出 `P01_requirements_spec.md`。**嚴禁在 P00 範疇之外新增未經討論的功能點**。
- **Phase 2 (架構與模組設計)**：
  - 架構分層、循序/資料流設計、受影響檔案清單，產出 `P02_architecture_plan.md`。
  - **Test-First 初始化**：同步初始化 `P06_test_plan.md` (Draft)，預先映射測試案例。
- **Phase 3 (API 規格定義與依賴拓撲)**：
  - 定義 Public/Internal 介面簽名、型態契約、錯誤策略與實作依賴拓撲順序，產出 `P03_api_spec.md`。
- **Phase 4 (最終審查與定稿)**：
  - **知識庫文檔衝擊預排**：依據 7 大抽象知識維度預排 `docs/` 需新建/更新之清單。
  - **架構靈魂拷問 (Stress Test)**：Agent 提出至少 1 個尖銳架構審查問題並獲得回覆。
  - 產出 `P04_implementation_plan.md` (Confirmed) 並同步剛性定稿 `P06_test_plan.md` (Confirmed)。
- **Phase 5 (依序程式碼實作)**：
  - 建立並維護 `P05_task.md`，以 P04 為唯一權威上下文依拓撲順序實作。
  - **實作偏差三級處置策略**：
    - 🚨 **Critical**（影響 Public API / 架構）：立即停止實作，向開發者回報並退回 Phase 1~4 修正計畫。
    - ⚠️ **Major**（影響內部模組邏輯但不破壞 Public API）：暫停當前項目並向開發者回報確認。
    - ℹ️ **Minor**（不影響架構之細微調整）：自行處理並詳細記錄於 `P05_task.md` 偏差紀錄表。
- **Phase 6 (測試與驗證)**：
  - 實機執行 CLI 編譯與單元/回歸測試，回填日誌至 `P06_test_plan.md`。
  - **人工 / UX 驗證 Checkpoint（強制等待關卡）**：呈遞測試結果，明確等待開發者完成實際互動/視覺/手動 UX 驗證或指示免測後，方可標記 `Passed`。
- **Phase 7 (成果展示與結案)**：
  - 產出結案報告 `P07_walkthrough.md`。
  - **知識庫 1:1 交付驗收**：核對並交付 Phase 4 預排之 `docs/` 文檔，追加版本日誌至專案根目錄 `CHANGELOG.md`。
  - 工作目錄預設留存於 `plans://` 原位，嚴禁主動歸檔。

### 4.3 Fast Track 敏捷流程
- **FT-1 (需求確認 & 變更規劃)**：建立 `fast_track_plan.md` (Draft)，嵌入 P00 引用，通過架構確認 Checklist ➔ Checkpoint ➔ Confirmed。
- **FT-2 (程式碼實作與驗證)**：依序撰寫代碼與測試，若遇 Critical 偏差立即升級為 Full Track。
- **FT-3 (品質 Review 與結案)**：代碼清理、回歸驗證、1:1 知識庫交付，追加 `CHANGELOG.md` ➔ Checkpoint ➔ Completed。

---

