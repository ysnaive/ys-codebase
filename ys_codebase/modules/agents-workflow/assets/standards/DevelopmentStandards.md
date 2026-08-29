# 開發標準作業流程與指南 (Development Standards & Workflow Guide)

本文件定義專案標準開發流程 SOP 0~7、6 大計畫分支全景拓撲、跨文件追溯鏈與工作目錄規範。

---

## 1. 工作目錄與空間協議規範 (Workspace & Protocols)

### 1.1 計畫目錄結構與空間協議
- **進行中計畫 (Active Plans)**：`workflow.plans://{YYYY_MM_DD_HHMM_功能名稱}/`
- **歷史封存計畫 (Archived Plans)**：`workflow.archived://{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
- **長期策略路線圖 (Roadmap)**：`workflow.roadmap://`（預設解析為 `workflow.plans://roadmap/`，實體路徑 `./plans/roadmap/`）
> `YYYY_MM_DD_HHMM` 採用 24 小時制時間戳，確保同一天建立多個計畫時目錄名稱不產生衝撞。

### 1.2 計畫內部日誌 vs. 全域變更日誌職責分離
- **`workflow.plans://<plan>/changelog.md`（計畫內部微觀日誌）**：記錄當前 Dev Plan 內部 Phase 轉換、DR 決策與偏差處置，確立計畫分流並開立目錄時**必須剛性伴隨初始化**。
- **`project://CHANGELOG.md`（全專案高階發布日誌）**：僅於 Phase 7 / FT-3 結案審查階段，由 Agent 追加本次 Dev Plan 的高階發布摘要。

### 1.3 巢狀子計畫管理 (Sub-Plans Architecture)
- **模式 A (衍生型子計畫)**：Phase 6 測試過程中若發現非當前範疇之衍生缺陷或優化需求，於主目錄下開立 `sub_{編號}_{目的}/`（預設 Fast Track），完成後納入主計畫結案報告。
- **模式 B (分類型主計畫 Umbrella)**：以 `umbrella_overview.md` 統籌，子計畫拆分評估以**單個 Full Track 能處理之顆粒度**為單位。
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

所有 Phase 產出文件 **必須 100% 嚴格鏡像標準模板結構**（包含所有指定欄位、表格與 Header 規範標頭），嚴禁 Agent 自行簡化或遺漏模板區塊。各階段標準模板實體路徑指針如下：

> 🚨 **模板註解剝除鐵律 (Mandatory Comment Stripping)**：使用標準模板產出任何 Phase 階段文件時，**落檔時必須徹底移除頂部指引之 HTML 註解（`<!-- ... -->`）**，嚴禁將模板導引註解遺留於正式計畫文件中。

- Phase 0: [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)
- Phase 1: [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)
- Phase 2: [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)
- Phase 3: [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)
- Phase 4: [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)
- Phase 5: [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)
- Phase 6: [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)
- Phase 7: [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`)
- Level 0 (Fast Track): [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)
- Level 2 (Umbrella): [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)
- 長期路線圖: [`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`)
- 計畫日誌: [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)
- 現場交接: [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)

---

## 4. 全景計畫類型判斷矩陣與分流拓撲 (Plan Taxonomy & Archetypes)

### 4.1 全景計畫類型判斷矩陣 (6-Branch Decision Matrix)

| 計畫類型 | 分流層級 / 特徵 | 適用情境與判定標準 | 產出文件矩陣 | 生命週期流程 |
| :--- | :---: | :--- | :--- | :--- |
| **標準開發計畫<br/>(Full Track)** | Level 1 | • 單一功能情境、模組新增/重構<br/>• 涉及 Public API 變更或內部架構演進<br/>• 修改行數預估 $> 100$ 行 | [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) ➔ P01~P07 + changelog | Phase 0~7 完整生命週期 |
| **迅捷開發計畫<br/>(Fast Track)** | Level 0 | **4 維度綜合規模與風險矩陣**（需 100% 同時滿足）：<br/>1. 預估總修改行數 $\le 100$ 行 (不限檔案數)<br/>2. Public API 契約 0 變更<br/>3. 架構自包含、零跨模組新依賴<br/>4. 既有單元/回歸測試可 100% 守門 | [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) + changelog | FT-1 規劃 ➔ FT-2 實作 ➔ FT-3 結案 |
| **分類型主計畫<br/>(Umbrella)** | Level 2 | **雙軌拓撲**：<br/>• **模式 B-1 (預先規劃型 Pre-planned)**：高聚合主題藍圖，立項時預排子計畫，保持彈性調整，由開發者驗收後評估收斂。<br/>• **模式 B-2 (增量演進型 Incremental)**：主題錨定、滾動追加子計畫，由開發者評估收斂。 | [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) + 各子計畫目錄 | 統籌多個 sub_XX 子計畫 |
| **修訂計畫<br/>(Revision Plan)** | 短循環 Track | • 文檔校閱、零散文案/註解同步<br/>• 邊校驗邊修改之極短即時反饋場景<br/>• 免開立實體計畫目錄，保護 Token | 0 計畫文件 (僅呈遞極簡變更卡) | 精準定位 ➔ 原地極小修訂 ➔ 極簡變更卡 ➔ Turn Gate 待命 |
| **調研計畫<br/>(Research Plan)** | 調研 Track | • 純技術選型、演算法可行性、套件測評<br/>• 非生產代碼、無單元測試需求<br/>• 調研結案後支援無痛升級為實作計畫 | [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) + [`R01_{topic}.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`) + changelog | Step 1 (立項) ➔ Step 2 (R01報告) ➔ Step 3 (三大出口轉化) |
| **長期策略路線圖<br/>(Roadmap)** | 策略資產庫 | • 長期技術儲備、跨版本演進藍圖<br/>• 非當前立即實作之架構決策 (置於 `__${workflow.roadmap://}__`) | [`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`) | 儲備沉澱 ➔ [/Roadmap](`__#{module://agents-workflow/assets/workflows/Roadmap.md}__`) 推薦 ➔ 條件成熟一鍵轉化為 Dev Plan |

---

### 4.2 `/NewPlan` 延遲建檔與 JIT 動態分流引導守門
1. **延遲建檔機制 (Delayed Materialization)**：
   - 開發者輸入 `/NewPlan` 時，**系統不立即在磁碟上建立實體資料夾與檔案**。
   - 先於對話中啟動純粹的 `P00_discuss` 討論，釐清需求本質與技術邊界。
   - **待開發者確認計畫類型並指示分流時**，才一併於磁碟建立目錄並伴隨寫入對應模板檔案，徹底杜絕無效空目錄殘留。
2. **JIT 動態分流比對**：
   - Agent 於 P00_discuss 討論過程中，時刻根據上述 6 大分支矩陣分析需求特徵。
   - 當需求已「明確」符合某類型時，Agent 可適時主動提出建議：「依目前需求特徵符合 [XX 計畫類型]，請問是否進入該計畫？」。
   - 🚨 **絕對禁止 Agent 自行進入，必須由開發者確認或主動指定**。
3. **長對話防呆阻斷 ➔ 調研計畫無痛升級鏈**：
   - 當 P00_discuss 討論過長、技術未知數過多或架構分歧較大時，Agent 主動建議先進入【調研計畫 (Research Plan)】。
   - 調研計畫結案產出 R01 後，可 **100% 無縫無痛升級** 為實作型 Plan（直接繼承 R01 結論與背景）。

---

### 4.3 Phase 0~7 階段流程與核心關卡 (Full Track)
- **Phase 0 (開放式需求討論 P00_discuss)**：
  - 開放式對話釐清原始意圖與邊界，嚴格遵守**技術顧問角色**：除非開發者主動要求發想，絕不主動提個人主觀想法，僅以客觀事實與技術角度回覆。
  - 等待開發者明確宣告結束 ➔ P00 Confirmed ➔ 確立計畫分流並伴隨建檔。
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
  - **🚨 計畫合規性檢核 (Mandatory Plan Check)**：結案交付前**必須實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` (或 `plan check`)** 驗證 Markdown 結構完整性、追溯鏈合規性與註解剝除狀態。
  - 工作目錄預設留存於 `__${workflow.plans://}__` 原位，嚴禁主動歸檔。

---

### 4.4 Fast Track 敏捷流程 (Level 0)
- **FT-1 (需求確認 & 變更規劃)**：建立 `fast_track_plan.md` (Draft)，嵌入 P00 引用，通過 4 維度確認 Checklist ➔ Checkpoint ➔ Confirmed。
- **FT-2 (程式碼實作與驗證)**：依序撰寫代碼與測試；**若發現總行數超標或需更動 Public API，強制觸發 Escalation Gate 升級為 Full Track**。
- **FT-3 (品質 Review 與結案)**：代碼清理、回歸驗證、1:1 知識庫交付、調用 `plan verify` 檢核合規，追加 `CHANGELOG.md` ➔ Checkpoint ➔ Completed。

---

### 4.5 自動連續推進模式 (/Auto)
- **觸發時機**：於 Full Track (Level 1) 或 Umbrella (Level 2) 活躍子計畫處於 Phase 01 ~ Phase 05 區間時由開發者調用。
- **特權授權**：在無未確定技術疑問與無爭議前提下，授權 Agent 跳過中間 Phase 強制 Checkpoint 連續推進各 Phase 產出與代碼實作。
- **三大熔斷防線**：嚴格受「零臆測熔斷」（遇歧義立即停手提問）、「偏差熔斷」（Major/Critical 偏差立即轉入 `/Discuss`）與「P06 手動/UX 驗證絕對阻斷」（CLI 跑測通過後強制停步等待人工驗收）約束。
- **產出保真**：連續推進期間各 Phase 文件（P01~P06、P05 任務清單、changelog 日誌）仍必須 100% 完整生成與記錄。

---

`__@{WORKFLOW_SOP_STANDARDS}__`
