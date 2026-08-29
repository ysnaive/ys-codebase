# 開發標準作業流程與指南 (Development Standards & Workflow Guide)

本文件定義專案標準開發流程 SOP 0~7、6 大計畫分支全景拓撲、跨文件追溯鏈與工作目錄規範。

---

## 1. 工作目錄與空間協議規範 (Workspace & Protocols)

### 1.1 計畫目錄結構與空間協議
- **進行中計畫 (Active Plans)**：`workflow.plans://{YYYY_MM_DD_HHMM_功能名稱}/`
- **歷史封存計畫 (Archived Plans)**：`workflow.archived://{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
- **長期策略路線圖 (Roadmap)**：`workflow.roadmap://`（實體路徑 `./plans/roadmap/`）
> `YYYY_MM_DD_HHMM` 採用 24 小時制時間戳，確保目錄名稱全域唯一。

### 1.2 計畫微觀日誌 vs. 全域發布日誌職責分離
- **`workflow.plans://<plan>/changelog.md`（計畫內部微觀日誌）**：記錄 Phase 轉換、DR 決策與偏差處置，分流建檔時**必須伴隨初始化**。
- **`project://CHANGELOG.md`（全專案高階發布日誌）**：僅於 Phase 7 / FT-3 結案審查時追加本次高階變更摘要。

### 1.3 巢狀子計畫管理 (Sub-Plans)
- **模式 A (衍生型子計畫)**：Phase 6 測試發現非本次範疇之衍生需求，開立 `sub_{編號}_{目的}/`（預設 Fast Track）。
- **模式 B (分類型主計畫 Umbrella)**：以 `umbrella_overview.md` 統籌多個 Full Track 顆粒度之子計畫。
- 🚨 **最多兩層約束**：嚴格限制最多兩層目錄（主計畫 ➔ 子計畫），**絕對禁止三層或更多層嵌套**。

---

## 2. 跨文件 ID 引用與剛性追溯鏈 (Traceability Matrix)

| ID 類別 | 前綴格式 | 範例 | 說明 |
| :--- | :--- | :--- | :--- |
| **功能需求** | `FR-{XX}` | `FR-01` | 定義於 `P01`，1:1 追溯至 `P00` 原始語意 |
| **邊界條件** | `EC-{XX}` | `EC-01` | 定義於 `P01`，涵蓋異常輸入、邊界與防禦行為 |
| **非功能需求** | `NFR-{XX}` | `NFR-01` | 定義於 `P01`，涵蓋效能、資源、安全與指標約束 |
| **決策紀錄** | `[{Phase}:DR-XX]` | `[P01:DR-01]` | 各階段關鍵架構與技術決策，Phase 前綴保證唯一 |
| **功能/邊界測試** | `FT-{XX}` / `ET-{XX}` | `FT-01`, `ET-01` | 對應 `FR-XX` / `EC-XX` 之測試案例 |
| **回歸/效能測試** | `RT-{XX}` / `PT-{XX}` | `RT-01`, `PT-01` | 全系統既有功能回歸 / 效能量測測試案例 |
| **UX / 缺陷紀錄** | `UX-{XX}` / `BUG-{XX}` | `UX-01`, `BUG-01` | 開發者實機 UX 驗證項 / 測試過程發現之缺陷 |

> **剛性追溯鏈**：`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `FT/ET/RT 測試`

---

## 3. 全階段文件模板指針 (Template Pointer Matrix)

各階段產出文件**必須 100% 嚴格鏡像標準模板結構**；落檔時**必須徹底剝除頂部 HTML 導引註解（`<!-- ... -->`）**。

- Phase 0: [`__${module://agents-workflow/assets/templates/P00_discuss.md}__`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)
- Phase 1: [`__${module://agents-workflow/assets/templates/P01_requirements_spec.md}__`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)
- Phase 2: [`__${module://agents-workflow/assets/templates/P02_architecture_plan.md}__`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)
- Phase 3: [`__${module://agents-workflow/assets/templates/P03_api_spec.md}__`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)
- Phase 4: [`__${module://agents-workflow/assets/templates/P04_implementation_plan.md}__`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)
- Phase 5: [`__${module://agents-workflow/assets/templates/P05_task.md}__`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)
- Phase 6: [`__${module://agents-workflow/assets/templates/P06_test_plan.md}__`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)
- Phase 7: [`__${module://agents-workflow/assets/templates/P07_walkthrough.md}__`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`)
- Level 0 (Fast Track): [`__${module://agents-workflow/assets/templates/fast_track_plan.md}__`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)
- Level 2 (Umbrella): [`__${module://agents-workflow/assets/templates/umbrella_overview.md}__`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)
- 長期路線圖: [`__${module://agents-workflow/assets/templates/roadmap.md}__`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`)
- 計畫日誌: [`__${module://agents-workflow/assets/templates/changelog.md}__`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)
- 現場交接: [`__${module://agents-workflow/assets/templates/handoff.md}__`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)

---

## 4. 全景計畫類型判斷矩陣與分流拓撲 (Plan Taxonomy & Archetypes)

### 4.1 全景 6 大計畫分支矩陣

| 計畫類型 | 分流層級 / 特徵 | 適用情境與判定標準 | 產出文件矩陣 | 生命週期流程 |
| :--- | :---: | :--- | :--- | :--- |
| **標準開發計畫 (Full Track)** | Level 1 | 單一功能/模組重構、涉及 Public API 變更或修改 $> 100$ 行 | `P00_discuss` ➔ P01~P07 + changelog | Phase 0~7 完整生命週期 |
| **迅捷開發計畫 (Fast Track)** | Level 0 | 同時滿足：修改 $\le 100$ 行、API 契約 0 變更、零跨模組新依賴、既有測試 100% 守門 | `fast_track_plan` + changelog | FT-1 規劃 ➔ FT-2 實作 ➔ FT-3 結案 |
| **分類型主計畫 (Umbrella)** | Level 2 | 統籌多個子計畫（B-1 預先規劃型 / B-2 增量演進型藍圖） | `umbrella_overview` + 各子計畫目錄 | 統籌與滾動驗收各子計畫 |
| **修訂計畫 (Revision Plan)** | 短循環 | 文檔校閱、極小註解同步，免開實體目錄保護 Token | 0 計畫文件 (僅呈遞極簡變更卡) | 原地極小修訂 ➔ 變更卡 ➔ 待命 |
| **調研計畫 (Research Plan)** | 調研 Track | 純技術選型、演算法可行性探索，支援無痛升級為實作計畫 | `P00_discuss` + `R01_{topic}` + changelog | 立項 ➔ R01 報告 ➔ 三大出口轉化 |
| **長期路線圖 (Roadmap)** | 策略資產庫 | 長期技術儲備藍圖（置於 `__${workflow.roadmap://}__`） | `roadmap.md` | 儲備沉澱 ➔ /Roadmap 推薦 ➔ 轉化立項 |

---

### 4.2 `/NewPlan` 延遲建檔與 JIT 動態分流守門
1. **延遲建檔**：輸入 `/NewPlan` 時不立即建立資料夾，先於對話中進行 `P00_discuss`，待開發者確認分流後才伴隨建立目錄與模板。
2. **JIT 動態分流**：需求特徵明確時 Agent 可主動建議分流類型，**嚴禁自行進入，必須由開發者確認**。
3. **調研無痛升級**：P00 討論過長或未知數過多時，主動建議先入調研計畫；產出 R01 後可無縫升級為實作 Plan。

---

### 4.3 Phase 0~7 階段流程與核心關卡 (Full Track)
- **Phase 0 (需求討論 P00)**：客觀釐清邊界，扮演技術顧問角色；開發者確認後確立分流並伴隨建檔。
- **Phase 1 (規格轉譯 P01)**：將 P00 語意 1:1 轉譯為 FR/EC/NFR，嚴禁超載未討論功能。
- **Phase 2 (架構設計 P02)**：完成架構與循序流，同步初始化 `P06_test_plan.md` (Draft) 測試映射。
- **Phase 3 (API 規格 P03)**：定義介面簽名、錯誤策略與實作依賴拓撲順序。
- **Phase 4 (定稿審查 P04)**：預排 7 維度文檔衝擊、完成架構靈魂拷問，剛性定稿 P04 與 P06 (Confirmed)。
- **Phase 5 (任務實作 P05)**：依 P04 拓撲順序實作；偏差處置：🚨 **Critical** 退回修正、⚠️ **Major** 暫停回報、ℹ️ **Minor** 紀錄於偏差表。
- **Phase 6 (測試驗證 P06)**：實機執行測試並回填；**人工/UX 驗證 Checkpoint**：明確等待開發者手動驗收或指示免測後方可標記 Passed。
- **Phase 7 (成果展示 P07)**：產出結案報告、1:1 知識庫交付、追加 `CHANGELOG.md`，實機執行 `plan verify` 合規檢核；計畫目錄預設留存原位。

---

### 4.4 敏捷模式與工作流
- **Fast Track (Level 0)**：FT-1 規劃 (Checklist 守門) ➔ FT-2 實作 (超標或更動 API 強制升級 Full Track) ➔ FT-3 結案。
- **自動連續推進 (/Auto)**：限 Full Track/Umbrella Phase 01~05 期間由開發者調用；具備零臆測、偏差與 P06 手動驗證三大熔斷防線。
- **開發歷程自檢 (/Retro)**：隨時調用回顧對話歷史與稽核紀律，發現不合規項強制執行 5-Whys 根因溯源。

---

`__@{WORKFLOW_SOP_STANDARDS}__`
