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
- **若無 `handoff.md`**：
  - 進入步驟 3 進行標準 Track 與 Phase 結構化判定。

---

### 步驟 3：判定計畫模式與進度

根據工作目錄中的關鍵檔案判定計畫模式：

| 判定依據 | 計畫模式 | 進入判定分支 |
| :--- | :--- | :--- |
| 存在 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) | **Umbrella 分類型主計畫** | -> 進入 **步驟 3-U** |
| 存在 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) | **Fast Track 迅捷開發** | -> 進入 **步驟 3-F** |
| 存在 `P00` / `P01` ~ `P07` | **Full Track 標準開發 (或子計畫)** | -> 進入 **步驟 3-T** |

---

#### 步驟 3-U：Umbrella 主計畫與子計畫定位

1. 讀取主計畫的 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) 與 [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)。
2. 檢查子計畫清單矩陣：
   - 尋找處於 `進行中`、`In Progress`、`Planning` 或 `未開始` 的目標子計畫目錄 `sub_{編號}_{名稱}/`。
   - 若既有子計畫均已完成但主計畫尚有後續階段 -> 提示開發者是否開立下一個 `sub_XX` 子計畫。
3. 進入當前目標子計畫目錄，檢查該子計畫是否含有 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)，若無則依其檔案結構進入 **步驟 3-T** (Full Track) 或 **步驟 3-F** (Fast Track) 判定進度。

---

#### 步驟 3-T：Full Track 進度判定

根據目標工作目錄中已存在的產出物檔案及其狀態標頭判定：

| 已存在的最新檔案 | 檔案狀態為 `Confirmed` / `Passed` | 檔案狀態為 `Discussing` / `Draft` / `Pending` | 判定結果 |
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
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | [PASS] | — | Phase 6 測試已全部通過，應進入 Phase 7 結案 |
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | — | [PASS] | Phase 6 測試進行中，應接續執行未通過測試 |

---

#### 步驟 3-F：Fast Track 進度判定

若存在 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`)：
1. 讀取 `fast_track_plan.md`。
2. 檢查「實作任務清單」與「測試驗證清單」的 Checkbox 完成度：
   - 尚有未勾選的任務 -> 接續該任務實作。
   - 任務全數勾選但測試未勾選 -> 執行測試驗證。
   - 測試全數通過 -> 推進至結案發布。

---

### 步驟 4：呈遞接續狀態卡並確認下一步

對話 Session **嚴禁代碼傾倒、全文重複或無關推論**，強制僅向開發者呈遞以下極簡接續狀態卡，並等待確認或直接進入下一個動作：

```markdown
### [CONTINUE] /Continue 計畫狀態已恢復
- **目標計畫**：[{plan_name}](__${project://plans/}__/{plan_name}/)
- **計畫模式**：[Full Track / Fast Track / Umbrella 子計畫]
- **當前斷點**：[Phase X: 檔案名稱 (狀態: Confirmed / In Progress)]
- **恢復依據**：[已成功載入 handoff.md 現場快照 / 依產出物檔案結構判定]
- **下一步動作**：[極精簡說明接下來立即執行的 1 項具體動作]
```
