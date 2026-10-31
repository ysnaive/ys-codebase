---
name: development-sop
description: 管理 `__${project://plans/}__` 開發計畫全生命週期 (Phase 00~07 與 6 大計畫模式)、追溯鏈編列與業務代碼實作。觸發情境：推進各階段開發任務、撰寫或更新 `__${project://plans/}__` 下之計畫規格與日誌產物、查閱階段模板指針。
---

# 開發標準作業流程指南 (Development SOP - Main Hub)

本手冊定義專案標準開發流程 SOP 0~7、6 大計畫分支全景拓撲、跨文件追溯鏈、工作目錄空間協議與極精簡 Session 回覆節流規範。

---

## 1. 工作目錄與空間協議規範 (Workspace Protocols)

- **進行中計畫 (Active Plans)**：`__${project://plans}__/{YYYY_MM_DD_HHMM_功能名稱}/`
- **歷史封存計畫 (Archived Plans)**：`__${project://plans/archived}__/{YYYY}/{MM}/{YYYY_MM_DD_HHMM_功能名稱}/`
- **長期策略路線圖 (Roadmap)**：`__${workflow.roadmap://}__`
- **日誌分離與免讀盲寫鐵律**：
  - `__${project://plans}__/<plan>/changelog.md`（微觀日誌）：記錄階段流轉、DR 決策與偏差，建檔時**必須伴隨初始化**。推進各階段時，優先調用 `python __${yscb.host://yscb.py}__ agents-workflow plan verify [plan_name] [--phase <P0X>] --log "<摘要>" [--type PHASE|DECISION|REVISION] --model "<ModelName>"` 一次完成合規檢核、伴隨檔自癒與 `changelog.md` 免讀盲寫追加（注意：`--phase <P0X>` **僅適用於 Full Track 單一階段檢核**；若為 Fast Track、Revision 或 Research 計畫，請直接省略 `--phase` 執行全計畫結構檢核。`--log` 內文嚴禁使用雙引號 `"` 與反引號 `` ` ``，一律改用單引號 `'...'` 或方括號 `[...]`），免除手動讀取與編輯 `changelog.md` 的 Context 消耗。
  - [`__${project://CHANGELOG.md}__`](`__#{project://CHANGELOG.md}__`)（宏觀日誌）：僅於 Phase 7 / FP-03 結案時追加高階變更摘要。
- [!] **巢狀子計畫最多兩層約束**：僅允許「主計畫 -> 子計畫（`sub_{編號}_{目的}/`）」，**絕對禁止三層或更多層嵌套**。
- **生命週期工作流中樞分流 (Lifecycle Workflow Hub Routing)**：
  - **開立新計畫** -> [`new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)
  - **恢復中斷進度 / 消費 `handoff.md`** -> [`continue`](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)
  - **中斷開發 / 產出 `handoff.md` 現場交接快照** -> [`pause`](`__#{module://agents-workflow/assets/skills/pause/SKILL.md}__`)
  - **P00 定稿後自動連續推進 Phase 01~05** -> [`auto`](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`)
  - **遇阻深度歸因 (連續 2 次失敗 / 範疇越界)** -> [`discuss`](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)
  - **專題技術調研** -> [`research`](`__#{module://agents-workflow/assets/skills/research/SKILL.md}__`)
  - **長期技術儲備盤點與收錄** -> [`roadmap`](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`)
  - **輕量待辦與微觀技術債速記 (`TODO.md`)** -> [`todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`)
  - **自動化測試建置、Phase 06 回歸守門與測試集純化** -> [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)
  - **建立專案特化 Skill、環境攔截規則或階段錨點注入配置** -> [`skill-creator`](`__#{module://agents-workflow/assets/skills/skill-creator/SKILL.md}__`)
  - **既有 Skill 五維度審查、漸進式揭露重構與 A/B 評測** -> [`skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`)
  - **既有業務程式碼五維度診斷、階段聚合與行為無損重構** -> [`code-optimizer`](`__#{module://agents-workflow/assets/skills/code-optimizer/SKILL.md}__`)

---

## [!] 2. 極精簡 Session 回覆節流規範 (Session Response Throttle Protocol)

遵循全域最高行為公理，執行任何計畫或階段推進時嚴格執行對話節流：
1. **實體檔案為唯一真理 (SSOT)**：所有架構、規格、代碼、任務與測試細節均落檔於實體 Markdown，禁止在 Session 對話重複轉述。
2. **對話 Session 嚴禁傾倒**：**嚴禁全文重複、代碼傾倒、圖表傾倒或冗長轉述**。
3. **強制極簡卡片回覆**：產出文件後，僅呈遞 5~10 行極簡卡片（產出文件超連結、核心摘要、關鍵決策/待驗項、推進詢問），並**立即 End Turn 等待確認**（唯獨處於 [`/auto`](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`) 模式之 Phase 01~05 除外）。各階段卡片格式詳見各階段專屬作業手冊與模式手冊。

---

## 3. 跨文件剛性追溯鏈 (Traceability Matrix)

| ID 類別 | 前綴格式 | 範例 | 說明 |
| :--- | :--- | :--- | :--- |
| **功能需求** | `FR-{XX}` | `FR-01` | 定義於 `P01`，1:1 追溯至 `P00` 原始語意 |
| **邊界條件** | `EC-{XX}` | `EC-01` | 定義於 `P01`，涵蓋異常輸入、邊界與防禦行為 |
| **非功能需求** | `NFR-{XX}` | `NFR-01` | 定義於 `P01`，涵蓋效能、資源、安全與指標約束 |
| **決策紀錄** | `[{Phase}:DR-XX]` | `[P01:DR-XX]`, `[FP-01:DR-01]`, `[REV-01:DR-01]` | 各階段、步驟或修訂關鍵架構與技術決策，Phase/步驟/修訂前綴保證唯一 |
| **功能/邊界測試** | `FT-{XX}` / `ET-{XX}` | `FT-01`, `ET-01` | 對應 `FR-XX` / `EC-XX` 之測試案例 |
| **回歸/效能測試** | `RT-{XX}` / `PT-{XX}` | `RT-01`, `PT-01` | 全系統既有功能回歸 / 效能量測測試案例 |
| **UX / 缺陷紀錄** | `UX-{XX}` / `BUG-{XX}` | `UX-01`, `BUG-01` | 開發者實機 UX 驗證項 / 測試過程發現之缺陷 |
| **修訂紀錄** | `REV-{XX}` | `REV-01` | 定義於 `revision_log.md`，記錄非業務邏輯之 UI/UX/DX、參數或文檔修訂條目 |

$$\text{剛性追溯鏈：}\; \texttt{P00 語意} \;\longrightarrow\; \texttt{FR/EC} \;\longrightarrow\; \texttt{[\{Phase\}:DR-XX]} \;\longrightarrow\; \texttt{API 簽名} \;\longrightarrow\; \texttt{程式碼} \;\longrightarrow\; \texttt{FT/ET/RT 測試} \;\longrightarrow\; \texttt{P07 成果與 SOP 審查}$$

---

## 4. 全景 6 大計畫分支快速判定表 (Plan Taxonomy)

在啟動任務時，先由下方分流表判定計畫模式（平等評估 6 大模式，杜絕僵化層級偏見），再按需**單點讀取**右側對應之專屬模式手冊或技能，嚴禁預先全量通讀所有模式規範：

| 計畫模式 | 核心特徵與週期 | 適用情境與判定標準 | 產出檔案矩陣 | 專屬模式手冊 / 技能 |
| :--- | :--- | :--- | :--- | :---: |
| **標準開發計畫 (Full Track)** | 8-Phase 完整週期 | 單一功能/模組重構、涉及 Public API 變更或修改 $> 100$ 行 | `P00` -> `P01`~`P06` -> `P07 (含 SOP Review)` + `changelog` | [P00~P07 導航](#5-full-track-sop-階段導航矩陣-mandatory-navigation-matrix) |
| **迅捷開發計畫 (Fast Track)** | 3-Step 敏捷閉環 | 同時滿足：修改 $\le 100$ 行、API 契約 0 變更、零跨模組新依賴、既有測試 100% 守門 | `fast_track_plan` (含 Review 核驗) + `changelog` | [Fast Track 手冊](./references/fast_track_plan.md) |
| **修訂計畫 (Revision Plan)** | 正交修訂留檔閉環 | **不牽涉核心業務邏輯**之 UI/UX/DX 表層微調、靜態參數調整、文檔調整（嚴禁用於 Bug Fix；可無衍生來源獨立開立，或衍生附掛於既有主計畫/子計畫） | `[P00] + [RXX] + revision_log + changelog`（獨立）或於既有計畫追加 `revision_log` | [Revision 手冊](./references/revision_plan.md) |
| **調研計畫 (Research Plan)** | 調研探索 Track | 純技術選型、演算法可行性探索，支援無痛升級為實作計畫 | `P00_discuss` + `R{NN}_{topic}` + `changelog` | [Research 技能](`__#{module://agents-workflow/assets/skills/research/SKILL.md}__`) |
| **分類型主計畫 (Umbrella)** | 跨子計畫史詩統籌 | 統籌多個子計畫（預先規劃型 / 增量演進型藍圖） | `umbrella_overview` + `changelog` + 各子計畫目錄（主計畫級 `P00` / `R{NN}` 選配） | [Umbrella 手冊](./references/umbrella_plan.md) |
| **長期路線圖 (Roadmap)** | 策略資產庫儲備 | 全專案層級技術願景與長期技術儲備藍圖（置於 `__${workflow.roadmap://}__`） | `{topic}.md` | [Roadmap 技能](`__#{module://agents-workflow/assets/skills/roadmap/SKILL.md}__`) |

---

## 5. Full Track SOP 階段導航矩陣 (Mandatory Navigation Matrix)

> [!IMPORTANT]
> **🚨 階段前置閱讀鐵律 (Mandatory Phase Reference Read)**：  
> 開始任何一個階段（Phase 0~7 / Fast Track 各步驟）前，**強制必須先精讀下方導航矩陣對應之專屬作業手冊（分流 Reference）**，嚴禁憑記憶盲目推進或跳過階段指針！（唯獨觸發 [`/auto`](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`) 自動連續推進時，`Phase 01 ~ 05` 改依 `auto/SKILL.md` 兩階段寫檔前即時讀取模板（Two-Stage JIT Template Read）與 `PXX_YYYY_auto.md` 單次到位寫檔規範執行，免除逐一讀取 `phase_01~05` 手冊之開銷）。

| 階段 | 專屬作業手冊 | 產出檔案 / 卡片 |
| :---: | :---: | :---: |
| **Phase 0** | [P00 需求討論](./references/phase_00_discuss.md) | `P00_discuss.md` |
| **Phase 1** | [P01 規格轉譯](./references/phase_01_requirements.md) | `P01_requirements_spec.md` |
| **Phase 2** | [P02 架構設計](./references/phase_02_architecture.md) | `P02_architecture_plan.md` + `P06_test_plan.md` (`Draft`) |
| **Phase 3** | [P03 API 規格](./references/phase_03_api_spec.md) | `P03_api_spec.md` |
| **Phase 4** | [P04 定稿審查](./references/phase_04_plan.md) | `P04_implementation_plan.md` + `P06_test_plan.md` (`Confirmed`) |
| **Phase 5** | [P05 任務實作](./references/phase_05_task.md) | `P05_task.md` |
| **Phase 6** | [P06 測試驗證](./references/phase_06_test.md) | `P06_test_plan.md` |
| **Phase 7** | [P07 結案與 SOP 審查](./references/phase_07_walkthrough.md) | `P07_walkthrough.md` |

---

## 6. 全階段模板指針 (Template Pointers)

執行計畫落檔時，直接由下方對應模板路徑讀取（落檔時務必將頂部標頭 `[...]` 佔位符全數替換為真實資訊，並依核心原則「模型紀錄」填寫 `> 模型：`（僅採平台當輪宣告之名稱，無法確認填 `Unknown`），且嚴禁包含任何 `<!-- ... -->` HTML 註解）：

- **Phase 0**：[`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)
- **Phase 1**：[`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)
- **Phase 2**：[`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)
- **Phase 3**：[`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)
- **Phase 4**：[`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)
- **Phase 5**：[`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)
- **Phase 6**：[`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)
- **Phase 7**：[`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`)
- **修訂紀錄**：[`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)
- **調研報告**：[`RXX_research_report.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`)
- **Fast Track**：[`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)
- **Umbrella**：[`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)
- **路線圖**：[`roadmap.md`](`__#{module://agents-workflow/assets/templates/roadmap.md}__`)
- **待辦種子**：[`todo.md`](`__#{module://agents-workflow/assets/templates/todo.md}__`)
- **微觀日誌**：[`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)
- **現場交接**：[`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)

### [!] 模板調取三大鐵律 (Template Axiom)
1. **唯一 SSOT**：所有計畫產物模板一律直接讀取上方條列之模板路徑，不得自造或臆測格式。
2. **嚴禁歷史考古**：嚴禁以 `find`、`grep` 或唯讀工具翻閱歷史封存計畫檔案當作格式參考。
3. **無痛遷移轉換**：將外部或 Roadmap 想法遷移進計畫時，必須直接套用標準標頭，不得直接複製舊標頭。

### 落檔預設標頭狀態 (Default Header Status)
| 產物 | 落檔預設狀態 |
| :--- | :--- |
| `P00_discuss.md` | 有待確認項填 `Discussing`；已確認填 `Confirmed` |
| `P01` ~ `P04` | 落檔即填 `Confirmed`（免雙重寫檔） |
| `P05_task.md` / `fast_track_plan.md` / `revision_log.md` | 執行中填 `In Progress`；結案填 `Completed` |
| `changelog.md` | 建檔填 `In Progress` 或 `Active`，全週期免回寫標頭 |

---

## 常見踩坑指南 (Gotchas)

- **嚴禁跳過雙階段測試計畫 (`P06_test_plan.md`) 的同步時機**：在 Full Track 中，`P06_test_plan.md` 並非等到 `Phase 6` 才建立，而是必須在 **`Phase 2` 建立 `Draft` 草案**、在 **`Phase 4` 定稿為 `Confirmed`**，最後在 `Phase 6` 執行並回填結果。
- **切勿混淆計畫內 `changelog.md` 與專案根目錄 `CHANGELOG.md`**：每個計畫資料夾下皆有一份小寫 `changelog.md`（每階段更新）；根目錄大寫 `CHANGELOG.md` 僅在 `Phase 7` 或 `FP-03` 結案時更新。

---

`__@{WORKFLOW_SOP_STANDARDS}__`
