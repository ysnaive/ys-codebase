---
name: development-sop
description: 專案標準開發流程 (SOP 0~7) 與 6 大計畫分支模式指南。當需要開立新計畫、評估計畫模式分流 (Full Track/Fast Track/Revision/Research/Umbrella/Roadmap)、推進或執行各階段開發任務 (P00~P07, FT-1~3)、查閱追溯鏈 (FR/DR/FT) 或模板指針時觸發。
---

# 開發標準作業流程指南 (Development SOP - Main Hub)

本手冊定義專案標準開發流程 SOP 0~7、6 大計畫分支全景拓撲、跨文件追溯鏈與工作目錄空間協議。

---

## 📁 1. 工作目錄與空間協議規範 (Workspace Protocols)

- **進行中計畫 (Active Plans)**：`__${workflow.plans://}__/{YYYY_MM_DD_HHMM_功能名稱}/`
- **歷史封存計畫 (Archived Plans)**：`__${workflow.archived://}__/{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
- **長期策略路線圖 (Roadmap)**：`__${workflow.roadmap://}__`（實體路徑 `./plans/roadmap/`）
- **日誌分離鐵律**：
  - `plans/<plan>/changelog.md`（微觀日誌）：記錄階段流轉、DR 決策與偏差，建檔時**必須伴隨初始化**。
  - `CHANGELOG.md`（宏觀日誌）：僅於 Phase 7 / FT-3 結案時追加高階變更摘要。
- 🚨 **巢狀子計畫最多兩層約束**：僅允許「主計畫 ➔ 子計畫（`sub_{編號}_{目的}/`）」，**絕對禁止三層或更多層嵌套**。

---

## 🔗 2. 跨文件剛性追溯鏈 (Traceability Matrix)

| ID 類別 | 前綴格式 | 範例 | 說明 |
| :--- | :--- | :--- | :--- |
| **功能需求** | `FR-{XX}` | `FR-01` | 定義於 `P01`，1:1 追溯至 `P00` 原始語意 |
| **邊界條件** | `EC-{XX}` | `EC-01` | 定義於 `P01`，涵蓋異常輸入、邊界與防禦行為 |
| **非功能需求** | `NFR-{XX}` | `NFR-01` | 定義於 `P01`，涵蓋效能、資源、安全與指標約束 |
| **決策紀錄** | `[{Phase}:DR-XX]` | `[P01:DR-01]` | 各階段關鍵架構與技術決策，Phase 前綴保證唯一 |
| **功能/邊界測試** | `FT-{XX}` / `ET-{XX}` | `FT-01`, `ET-01` | 對應 `FR-XX` / `EC-XX` 之測試案例 |
| **回歸/效能測試** | `RT-{XX}` / `PT-{XX}` | `RT-01`, `PT-01` | 全系統既有功能回歸 / 效能量測測試案例 |
| **UX / 缺陷紀錄** | `UX-{XX}` / `BUG-{XX}` | `UX-01`, `BUG-01` | 開發者實機 UX 驗證項 / 測試過程發現之缺陷 |

$$\text{剛性追溯鏈：}\; \texttt{P00 語意} \;\longrightarrow\; \texttt{FR/EC} \;\longrightarrow\; \texttt{[\{Phase\}:DR-XX]} \;\longrightarrow\; \texttt{API 簽名} \;\longrightarrow\; \texttt{程式碼} \;\longrightarrow\; \texttt{FT/ET/RT 測試}$$

---

## 🌳 3. 全景 6 大計畫分支快速判定表 (Plan Taxonomy)

在啟動任務時，依據任務規模與業務特性判定計畫模式（平等評估 6 大模式，杜絕僵化層級偏見）：

| 計畫模式 | 核心特徵與週期 | 適用情境與判定標準 | 產出檔案矩陣 | 詳細手冊 |
| :--- | :--- | :--- | :--- | :---: |
| **標準開發計畫 (Full Track)** | 8-Phase 完整週期 | 單一功能/模組重構、涉及 Public API 變更或修改 $> 100$ 行 | `P00` ➔ `P01`~`P07` + `changelog` | [模式詳解](./references/plan_modes.md#1-標準開發計畫-full-track) |
| **迅捷開發計畫 (Fast Track)** | 3-Step 敏捷閉環 | 同時滿足：修改 $\le 100$ 行、API 契約 0 變更、零跨模組新依賴、既有測試 100% 守門 | `fast_track_plan` + `changelog` | [模式詳解](./references/plan_modes.md#2-迅捷開發計畫-fast-track) |
| **修訂計畫 (Revision Plan)** | 短循環極速交付 | 文檔校閱、極小註解同步、常數微調，**免開實體目錄**保護 Token | 0 計畫文件 (僅呈遞極簡變更卡) | [模式詳解](./references/plan_modes.md#4-修訂計畫-revision-plan---短循環) |
| **調研計畫 (Research Plan)** | 調研探索 Track | 純技術選型、演算法可行性探索，支援無痛升級為實作計畫 | `P00_discuss` + `R01_{topic}` + `changelog` | [模式詳解](./references/plan_modes.md#5-調研計畫-research-plan---調研-track) |
| **分類型主計畫 (Umbrella)** | 跨子計畫史詩統籌 | 統籌多個子計畫（B-1 預先規劃型 / B-2 增量演進型藍圖） | `umbrella_overview` + 各子計畫目錄 | [模式詳解](./references/plan_modes.md#3-分類型主計畫-umbrella) |
| **長期路線圖 (Roadmap)** | 策略資產庫儲備 | 全專案層級技術願景與長期技術儲備藍圖（置於 `__${workflow.roadmap://}__`） | `roadmap.md` | [模式詳解](./references/plan_modes.md#6-長期路線圖-roadmap---策略資產庫) |

---

## 🧭 4. Full Track SOP 0~7 階段導航矩陣

在推進各階段前，請查閱對應之階段專屬手冊：

| 階段編號 | 階段名稱 | 核心任務與品質閘門 | 專屬作業手冊 | 產出檔案指針 |
| :---: | :--- | :--- | :---: | :---: |
| **Phase 0** | **需求討論** | 釐清需求邊界、技術顧問角色、JIT 延遲建檔守門 | [P00 手冊](./references/phase_00_discuss.md) | `P00_discuss.md` |
| **Phase 1** | **規格轉譯** | 原始語意 1:1 轉譯為 FR/EC/NFR，剛性追溯起點 | [P01 手冊](./references/phase_01_requirements.md) | `P01_requirements_spec.md` |
| **Phase 2** | **架構設計** | 架構拓撲與循序流，Test-First 初始化 P06 (Draft) | [P02 手冊](./references/phase_02_architecture.md) | `P02_architecture_plan.md` |
| **Phase 3** | **API 規格** | 公開介面簽名契約、錯誤策略與實作依賴拓撲順序 | [P03 手冊](./references/phase_03_api_spec.md) | `P03_api_spec.md` |
| **Phase 4** | **定稿審查** | 預排 7 維度文檔衝擊、架構靈魂拷問、P04/P06 剛性定稿 | [P04 手冊](./references/phase_04_plan.md) | `P04_implementation_plan.md` |
| **Phase 5** | **任務實作** | 依序編碼實作、微觀 Docstrings 型別契約、三大偏差處置 | [P05 手冊](./references/phase_05_task.md) | `P05_task.md` |
| **Phase 6** | **測試驗證** | 實機測試執行回填、人工/UX 驗收 Checkpoint 守門 | [P06 手冊](./references/phase_06_test.md) | `P06_test_plan.md` |
| **Phase 7** | **成果展示** | 結案報告、三層文檔 1:1 交付驗收、`CHANGELOG.md` 追加 | [P07 手冊](./references/phase_07_walkthrough.md) | `P07_walkthrough.md` |

---

## 📋 5. 全階段模板指針 (Template Pointers)

執行計畫落檔時，唯一來源為物化之 `__${project://.agents/.yscb/templates/}__`（落檔時徹底剝除頂部 HTML 導引註解 `<!-- ... -->`）：

- Phase 0: `P00_discuss.md`
- Phase 1: `P01_requirements_spec.md`
- Phase 2: `P02_architecture_plan.md`
- Phase 3: `P03_api_spec.md`
- Phase 4: `P04_implementation_plan.md`
- Phase 5: `P05_task.md`
- Phase 6: `P06_test_plan.md`
- Phase 7: `P07_walkthrough.md`
- Fast Track: `fast_track_plan.md`
- Umbrella: `umbrella_overview.md`
- 路線圖: `roadmap.md`
- 微觀日誌: `changelog.md`
- 現場交接: `handoff.md`

---

`__@{WORKFLOW_SOP_STANDARDS}__`
