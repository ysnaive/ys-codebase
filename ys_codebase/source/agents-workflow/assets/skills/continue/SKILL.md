---
name: continue
description: 接續中斷或已存在的開發計畫工作流 (Continue)。支援 handoff.md 現場交接與狀態自動恢復。
---

# 接續開發計畫工作流 (Continue)

本工作流用於從已存在但尚未完成的開發計畫接續工作，支援 `handoff.md` 現場快照與狀態自動恢復。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 執行步驟

### 步驟 1：定位目標計畫目錄與狀態掃描

1. 檢視 `__${project://plans/}__` 進行中計畫。
2. 若使用者未明確指定計畫名稱：
   - 僅單一進行中計畫 -> 自動定位為目標。
   - 多個進行中計畫 -> 列出清單與狀態，詢問確認。

---

### 步驟 2：檢查 `handoff.md` 現場交接快照 (Handoff Detection)

檢查目標計畫目錄下是否存在 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)：
- **若存在 `handoff.md`**：
  1. 優先讀取 `handoff.md`，提取現場已完成事項、進行中待辦、注意事項與下一次接手第 1 步。
  2. 依據現場快照直接還原斷點上下文，無需漫無目的地掃描所有歷史代碼。
  3. **消費即刪除 (Consume & Delete)**：確認恢復現場後，強制立即刪除該已消費之 `handoff.md`，避免後續重複讀取殘留過期快照。
- **若無 `handoff.md`**：
  - 進入步驟 3 進行標準 Track 與 Phase 結構化判定。

---

### 步驟 3：判定計畫模式與進度

根據工作目錄中的關鍵檔案判定計畫模式：

| 判定依據 | 計畫模式 | 進入判定分支 |
| :--- | :--- | :--- |
| 存在 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) | **Umbrella 分類型主計畫** | -> 進入 **步驟 3-U** |
| 存在 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) | **Fast Track 迅捷開發** | -> 進入 **步驟 3-F** |
| 存在 `P01_requirements_spec.md` 或後續 `P02~P07` | **Full Track 標準開發 (或子計畫)** | -> 進入 **步驟 3-T** |
| 存在 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)（獨立修訂或主體已結案後之附掛修訂） | **Revision 修訂計畫** | -> 進入 **步驟 3-R** |
| 存在 `R{NN}_*.md` (如 `R01_*.md`) | **Research 調研計畫** | -> 進入 **步驟 3-S** |
| 僅存在 `P00_discuss.md` | **Phase 0 討論階段** | -> 進入 **步驟 3-0** |

---

#### 步驟 3-U：Umbrella 主計畫與子計畫定位

1. 讀取主計畫的 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)（若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考）。
2. 檢查子計畫清單矩陣：
   - 尋找處於 `進行中`、`In Progress`、`Planning` 或 `未開始` 的目標子計畫目錄 `sub_{編號}_{名稱}/`。
   - 若既有子計畫均已完成但主計畫尚有後續階段 -> 提示開發者是否開立下一個 `sub_XX` 子計畫。
3. 進入當前目標子計畫目錄，檢查該子計畫是否含有 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)（若有則依步驟 2 讀取並於恢復後刪除），若無則依其檔案結構進入 **步驟 3-T** (Full Track)、**步驟 3-F** (Fast Track) 或 **步驟 3-R** (Revision) 判定進度。

---

#### 步驟 3-T：Full Track 進度判定

根據目標工作目錄中已存在的產出物檔案及其狀態標頭判定：

| 已存在的最新檔案 | 檔案狀態為 `Confirmed` / `Passed` / `Completed` | 檔案狀態為 `Discussing` / `Draft` / `In Progress` | 判定結果 |
| :--- | :---: | :---: | :--- |
| [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) | [PASS] | — | Phase 0 已確認，尚未進行分流或進入 Phase 1 |
| [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) | — | [PASS] | Phase 0 需求討論進行中 |
| [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`) | [PASS] | — | Phase 1 已完成，應從 Phase 2 開始 |
| [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`) | — | [PASS] | Phase 1 進行中，應接續 Phase 1 |
| [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) | [PASS] | — | Phase 2 已完成，應從 Phase 3 開始 |
| [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) | — | [PASS] | Phase 2 進行中，應接續 Phase 2 |
| [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`) | [PASS] | — | Phase 3 已完成，應從 Phase 4 開始 |
| [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`) | — | [PASS] | Phase 3 進行中，應接續 Phase 3 |
| [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) | [PASS] | — | Phase 4 已完成，應進入 Phase 5 編碼實作 |
| [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) | — | [PASS] | Phase 4 進行中，應接續 Phase 4 |
| [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) | [PASS] | — | Phase 5 實作已完成，應進入 Phase 6 測試 |
| [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) | — | [PASS] | Phase 5 實作進行中，應接續 Phase 5 任務 |
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | [PASS] | — | Phase 6 測試已完成 (`Completed`) 或自動化通過待 UX 驗收 (`Passed`)，應進入 Phase 7 結案或確認 UX |
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | — | [PASS] | Phase 6 測試進行中 (`In Progress`) 或已定稿待測 (`Confirmed`)，應執行測試套件 |
| [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) | [PASS] | — | Phase 7 已結案 (`Completed`)，可歸檔或於本計畫建立 `revision_log.md` 進行後續修訂 |
| [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) | — | [PASS] | Phase 7 進行中，應接續執行 SOP Review 與結案檢核 |

---

#### 步驟 3-F：Fast Track 進度判定

若存在 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)：
1. 讀取 `fast_track_plan.md`。
2. 檢查 FP-01 規劃、FP-02 任務與測試清單、FP-03 SOP 審查之完成度：
   - FP-01 尚未確認 -> 進行快速規劃與守門條件確認。
   - 尚有未勾選的實作任務 -> 接續 FP-02 任務實作。
   - 實作完成但測試未勾選 -> 執行測試套件並回填結果。
   - 測試全數通過 -> 推進至 FP-03 結案審查與交付。

---

#### 步驟 3-R：Revision 修訂進度判定

若為獨立修訂計畫，或既有計畫主體已 `Completed` 且存在 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`)：
1. 讀取 `revision_log.md`。
2. 檢視最新 `[REV-XX]` 修訂條目與「結案與合規檢核」Checkbox 狀態：
   - 若狀態為 `In Progress` -> 接續當前修訂條目或詢問下一個修訂需求。
   - 若所有修訂已完成 -> 執行 `plan verify` 並將 `revision_log.md` 標記為 `Completed`。

---

#### 步驟 3-S：Research 調研進度判定

若存在調研報告 `R{NN}_{topic}.md`：
1. 讀取調研報告，檢查標頭 `調研狀態`：
   - 若狀態為 `Concluded` -> 調研已完成，提示開發者確認三大出口方向（立即實作 / 路線圖儲備 / 結案存檔）。
   - 若狀態為 `Draft` 或 `In Progress` -> 接續深入調研並撰寫方案對比與決策推薦。

---

#### 步驟 3-0：Phase 0 討論進度判定

若僅存在 `P00_discuss.md` 且尚未建立其他產物：
1. 讀取 `P00_discuss.md`，檢查標頭狀態：
   - 若狀態為 `Confirmed` -> 需求已確認，依規模進行分流評估（Full Track / Fast Track / Umbrella / Research）。
   - 若狀態為 `Draft` 或 `Discussing` -> 接續與開發者釐清需求與確認核心決策。

---

### 步驟 4：呈遞接續狀態卡並確認下一步

對話 Session **嚴禁代碼傾倒、全文重複或無關推論**，強制僅向開發者呈遞以下極簡接續狀態卡，並等待確認或直接進入下一個動作：

```markdown
### [CONTINUE] /Continue 計畫狀態已恢復
- **目標計畫**：[{plan_name}](__${project://plans/}__/{plan_name}/)
- **計畫模式**：[Full Track / Fast Track / Umbrella 子計畫 / Revision / Research]
- **當前斷點**：[Phase X 或檔案名稱 (狀態: Confirmed / Passed / In Progress)]
- **恢復依據**：[已成功載入 handoff.md 現場快照 / 依產出物檔案結構判定]
- **下一步動作**：[極精簡說明接下來立即執行的 1 項具體動作]
```
