---
name: continue
description: 讀取既有計畫之交接快照或階段產物以定位斷點並恢復開發進度。僅於顯式輸入 /continue 或明確指示接續既有計畫時觸發。
---

# 接續開發計畫工作流 (Continue)

本工作流用於從已存在但尚未完成的開發計畫接續工作，支援 `handoff.md` 現場快照與狀態自動恢復。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 適用情境與觸發時機

- **適用情境**：`__${project://plans/}__` 中已有進行中之開發計畫（Full Track、Fast Track、Umbrella、Revision 或 Research）。
- **觸發時機**：開發者輸入 `/continue`（或 `/Continue`），或指示接續特定既有計畫。
- **排除情境（負向邊界）**：
  - **建立全新功能計畫**：若目標計畫目錄尚不存在，請改用 [new-plan](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)。
  - **自動連續執行多階段**：若開發者要求不經中間停頓直接跑完 Phase 01~05，請改用 [auto](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`)。

---

## 執行步驟

開始執行時，請複製以下檢核表追蹤狀態恢復流程：

```markdown
/Continue 狀態恢復檢核表：
- [ ] 步驟 1：掃描 `__${project://plans/}__` 定位單一目標計畫（多計畫時先詢問確認）
- [ ] 步驟 2：優先檢查並讀取 handoff.md 現場交接快照（恢復後執行 Consume & Delete 立即刪除）
- [ ] 步驟 3：若無 handoff.md，依目錄產物與標頭狀態判定計畫模式與當前 Phase 斷點
- [ ] 步驟 4：呈遞極簡接續狀態卡並依 development-sop 規範銜接下一步動作
```

### 步驟 1：定位目標計畫目錄與狀態掃描

1. 檢視 `__${project://plans/}__` 進行中計畫（或執行 `python __${yscb.host://yscb.py}__ agents-workflow plan status`）。
2. 若使用者未明確指定計畫名稱：
   - 僅單一進行中計畫 -> 自動定位為目標。
   - 多個進行中計畫 -> 列出清單與狀態，詢問確認（遵守零臆測原則，禁止自行挑選）。

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

#### 步驟 3-U：Umbrella 主計畫與子計畫定位

1. 讀取主計畫的 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)（若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考）。
2. 檢查子計畫清單矩陣：
   - 尋找處於 `進行中`、`In Progress`、`Planning` 或 `未開始` 的目標子計畫目錄 `sub_{編號}_{名稱}/`。
   - 若既有子計畫均已完成但主計畫尚有後續階段 -> 提示開發者是否開立下一個 `sub_XX` 子計畫。
3. 進入當前目標子計畫目錄，檢查該子計畫是否含有 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)（若有則依步驟 2 讀取並於恢復後刪除），若無則依其檔案結構進入 **步驟 3-T** (Full Track)、**步驟 3-F** (Fast Track) 或 **步驟 3-R** (Revision) 判定進度。

#### 步驟 3-T：Full Track (P00 ~ P07) 斷點速查表

檢視目標目錄下**最新（編號最大）**的階段檔案及其標頭狀態：

| 最新階段檔案 | 標頭為 `Confirmed` / `Passed` / `Completed` 時的下一步 | 標頭為 `Draft` / `Discussing` / `In Progress` 時的下一步 |
| :--- | :--- | :--- |
| [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) | Phase 0 已確認，依規模分流或進入 Phase 1 建立 `P01_requirements_spec.md` | 接續 Phase 0 與開發者釐清需求邊界與待決問題 |
| [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`) | Phase 1 已完成，讀取 `phase_02_architecture.md` 進入 Phase 2 | 接續完成 P01 需求規格轉譯與確認 |
| [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) | Phase 2 已完成（確認 P06 Draft 已同步建立），進入 Phase 3 | 接續完成 P02 架構設計與 P06 Draft 初始化 |
| [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`) | Phase 3 已完成，讀取 `phase_04_plan.md` 進入 Phase 4 | 接續完成 P03 API 規格與 DAG 依賴拓撲 |
| [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) | Phase 4 已定稿（且 P06 已 Confirmed），進入 Phase 5 編碼實作 | 接續完成 P04 實作計畫定稿與文檔衝擊盤點 |
| [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) | Phase 5 實作完成，讀取 `phase_06_test.md` 進入 Phase 6 測試驗證 | 讀取 `P05_task.md` 未勾選之 `TASK-XX` 接續編碼與單元測試 |
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | 若為 `Completed`（或 `Passed` 且開發者已驗收 UX），進入 Phase 7 結案 | 若為 `Confirmed` / `In Progress` 則執行測試套件；若為 `Passed` 待驗收則請開發者確認 UX |
| [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) | Phase 7 已結案 (`Completed`)，可歸檔或建立 `revision_log.md` 進行後續修訂 | 接續執行 SOP Review 三層文檔對齊與 `plan verify` 合規檢核 |

#### 步驟 3-F / 3-R / 3-S / 3-0：其他分支進度判定

- **步驟 3-F (Fast Track)**：讀取 `fast_track_plan.md`：`FP-01` 未確認則確認守門條件；`FP-02` 任務未勾選則接續實作與測試；測試全過則推進至 `FP-03` 結案審查。
- **步驟 3-R (Revision)**：讀取 `revision_log.md` 最新 `[REV-XX]` 條目：若為 `In Progress` 則接續修訂或詢問下一項；若全數完成則執行 `plan verify` 並標記 `Completed`。
- **步驟 3-S (Research)**：讀取 `R{NN}_{topic}.md` 標頭狀態：若為 `Concluded` 則提示開發者確認三大出口方向；若為 `Draft` / `In Progress` 則接續撰寫方案對比。
- **步驟 3-0 (Phase 0)**：讀取 `P00_discuss.md`：若為 `Confirmed` 則依規模進行分流評估；若為 `Draft` / `Discussing` 則接續釐清需求。

---

### 步驟 4：呈遞接續狀態卡並確認下一步

對話 Session **嚴禁代碼傾倒、全文重複或無關推論**，強制僅向開發者呈遞以下極簡接續狀態卡，並等待確認或直接進入下一個動作：

```markdown
### [CONTINUE] /Continue 計畫狀態已恢復
- **目標計畫**：[{plan_name}](`__${project://plans/}__`/{plan_name}/)
- **計畫模式**：[Full Track / Fast Track / Umbrella 子計畫 / Revision / Research]
- **當前斷點**：[Phase X 或檔案名稱 (狀態: Confirmed / Passed / In Progress)]
- **恢復依據**：[已成功載入 handoff.md 現場快照並清除 / 依產出物檔案結構判定]
- **下一步動作**：[極精簡說明接下來立即執行的 1 項具體動作（中途若需暫停交接可輸入 `/pause`）]
```

---

## 常見踩坑指南 (Gotchas)

- **切勿略過 `handoff.md` 直接掃描全專案**：若目錄中存在 `handoff.md`，它記載了上次暫停時的環境陷阱與第一手斷點，略過它會導致重複踩坑與浪費 Token；讀取恢復後務必將其物理刪除。
- **進入具體階段前務必補讀對應 SOP 手冊**：`continue` 僅負責「定位斷點」，實際推進某個 Phase（如 Phase 5 或 Phase 7）前，仍須按 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`) 鐵律先讀取對應的 `references/phase_0X_*.md`。
