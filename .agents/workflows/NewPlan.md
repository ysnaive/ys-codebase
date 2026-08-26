---
description: 標準開發作業流程 (NewPlan) — 定義專案從需求到發布的完整規範與三大分流管控
---

> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | `./ys_codebase` | `[ACTIVE]` |
> | **`plans://`** | `./plans` | `[!UNDEFINED]` |
> | **`archive://`** | `./archive` | `[!UNDEFINED]` |
> | **`docs://`** | `./docs` | `[!UNDEFINED]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb.py uri resolve <uri>`（例：`python yscb.py uri resolve project://AGENTS.md`）

# 標準開發作業流程 (NewPlan)

# 開發標準作業流程與指南 (Development Standards & Workflow Guide)

本文件定義專案標準開發流程 SOP 0~7、三大分流管理矩陣、跨文件追溯鏈與工作目錄規範。

---

## 1. 工作目錄與子計畫管理規範 (Workspace & Sub-Plans)

### 1.1 計畫目錄結構與命名
- **獨立計畫（進行中）**：`workflow.plans://{YYYY_MM_DD_HHMM_功能名稱}/`
- **獨立計畫（已歸檔）**：`workflow.archived://{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
> `YYYY_MM_DD_HHMM` 採用 24 小時制時間戳，確保同一天建立多個計畫時目錄名稱不產生衝撞。

### 1.2 計畫內部日誌 vs. 全域變更日誌職責分離
- **`workflow.plans://<plan>/changelog.md`（計畫內部微觀日誌）**：記錄當前 Dev Plan 內部 Phase 轉換、DR 決策與偏差處置，開立計畫目錄時**必須與 P00 剛性伴隨初始化**。
- **`project://CHANGELOG.md`（全專案高階發布日誌）**：僅於 Phase 7 / FT-3 結案審查階段，由 Agent 追加本次 Dev Plan 的高階發布摘要。

### 1.3 巢狀子計畫管理 (Sub-Plans Architecture)
- **模式 A (衍生型子計畫)**：Phase 6 測試過程中若發現非當前範疇之衍生缺陷或優化需求，於主目錄下開立 `sub_{編號}_{目的}/`（預設 Fast Track），完成後納入主計畫結案報告。
- **模式 B (分類型主計畫 Umbrella)**：多個功能情境或跨模組大型架構演進時開立 Umbrella 主計畫，以 `umbrella_overview.md` 統籌，子計畫拆分評估以**單個 Full Track 能處理之顆粒度**為單位。
- 🚨 **最多兩層約束**：嚴格限制最多兩層目錄（主計畫 ➔ 子計畫），**絕對禁止三層或更多層嵌套**！

---

## 2. 跨文件 ID 引用與剛性追溯鏈 (Traceability & Standard ID Matrix)

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

## 3. 全階段文件模板指針 (Template Address Pointer Matrix)

所有 Phase (P00~P07 / fast_track_plan / umbrella_overview) 產出文件 **必須 100% 嚴格鏡像標準模板結構**（包含所有指定欄位、表格與 Header 規範標頭），嚴禁 Agent 自行簡化或遺漏模板區塊。各階段標準模板實體路徑指針如下：

- Phase 0: [`P00_semantic_requirements.md`](../templates/P00_semantic_requirements.md)
- Phase 1: [`P01_requirements_spec.md`](../templates/P01_requirements_spec.md)
- Phase 2: [`P02_architecture_plan.md`](../templates/P02_architecture_plan.md)
- Phase 3: [`P03_api_spec.md`](../templates/P03_api_spec.md)
- Phase 4: [`P04_implementation_plan.md`](../templates/P04_implementation_plan.md)
- Phase 5: [`P05_task.md`](../templates/P05_task.md)
- Phase 6: [`P06_test_plan.md`](../templates/P06_test_plan.md)
- Phase 7: [`P07_walkthrough.md`](../templates/P07_walkthrough.md)
- Level 0 (Fast Track): [`fast_track_plan.md`](../templates/fast_track_plan.md)
- Level 2 (Umbrella): [`umbrella_overview.md`](../templates/umbrella_overview.md)
- 計畫日誌: [`changelog.md`](../templates/changelog.md)
- 現場交接: [`handoff.md`](../templates/handoff.md)

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
  - **知識庫 1:1 交付驗收**：核對並交付 Phase 4 預排之 `workflow.docs://` 文檔，追加版本日誌至專案根目錄 `CHANGELOG.md`。
  - 工作目錄預設留存於 `workflow.plans://` 原位，嚴禁主動歸檔。

### 4.3 Fast Track 敏捷流程
- **FT-1 (需求確認 & 變更規劃)**：建立 `fast_track_plan.md` (Draft)，嵌入 P00 引用，通過架構確認 Checklist ➔ Checkpoint ➔ Confirmed。
- **FT-2 (程式碼實作與驗證)**：依序撰寫代碼與測試，若遇 Critical 偏差立即升級為 Full Track。
- **FT-3 (品質 Review 與結案)**：代碼清理、回歸驗證、1:1 知識庫交付，追加 `CHANGELOG.md` ➔ Checkpoint ➔ Completed。

---



---

