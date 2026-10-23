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
- [ ] 步驟 1：執行 `plan status --resume` 定位目標計畫、取得確定性下一步領航指令並自動消費刪除 handoff.md
- [ ] 步驟 2：若環境無終端權限（唯讀沙盒 Fallback），手動檢查 handoff.md（閱後即焚）與最新階段檔案標頭狀態
- [ ] 步驟 3：精讀領航指定之 `required_reference_path` 階段作業手冊
- [ ] 步驟 4：呈遞極簡接續狀態卡並依 development-sop 規範銜接下一步動作
```

### 步驟 1：執行確定性狀態領航與 `handoff.md` 原子閱後即焚 (`CLI-First Resume`)

1. **優先調用確定性狀態領航指令**：
   ```bash
   python yscb.py agents-workflow plan status --resume [--plan <plan_name_or_subpath>]
   ```
   *(實機路徑：`python __${yscb.host://yscb.py}__ agents-workflow plan status --resume [--plan <plan_name_or_subpath>]`)*
   - **單一進行中計畫（含 Umbrella 活躍 `sub_XX` 自動鑽取）**：CLI 會自動輸出目標計畫之 `Plan Mode`、`Current Breakpoint`、`Next Phase`、`Required Reference` 與具體下一步行動提示 (`Next Action Hint`)。
   - **原子化閱後即焚 (`Consume & Delete`)**：若目標計畫（或活躍子計畫）存在 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)，`plan status --resume` 會於終端完整印出 `handoff.md` 快照內容，並由 Python **立即呼叫 `os.unlink()` 物理刪除該檔案**（確認恢復現場後，強制立即刪除該已消費之 `handoff.md`），免除手動刪檔遺漏風險。
   - **多個進行中計畫防呆**：若同時存在多個未結案之進行中計畫且未指定 `--plan`，CLI 會列出狀態矩陣並拒絕盲猜；請先向開發者詢問確認目標計畫名稱（遵守零臆測原則），再帶入 `--plan <name>` 執行。

---

### 步驟 2：唯讀沙盒 Fallback 斷點速查（僅於無法執行 CLI 時使用）

若當前環境無法執行 CLI 指令，則改以唯讀工具檢視目標目錄：
1. 若存在 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)，優先讀取其斷點資訊，確認恢復現場後，強制立即刪除該已消費之 `handoff.md`。
2. 若為 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)（若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考），進入第一個未完成之 `sub_{編號}_{名稱}/` 子目錄。
3. 檢視目錄內最新階段檔案與標頭狀態：
   - **Full Track (`P00` ~ `P07`)**：若最新階段檔標頭為 `Confirmed` / `Passed` / `Completed`，則讀取下一階段 `references/phase_0X_*.md` 推進；若為 `Draft` / `Discussing` / `In Progress`，則接續完成當前階段（`P06` 為 `Passed` 時等待開發者確認 UX 驗收後進入 `P07`）。
   - **Fast Track (`fast_track_plan.md`)**：依序推進 `FP-01`（規劃確認）$\to$ `FP-02`（實作與測試）$\to$ `FP-03`（SOP Review 與結案）。
   - **Revision (`revision_log.md`) / Research (`R{NN}_*.md`)**：若為 `In Progress` / `Draft` 則接續完成；若 `R{NN}` 為 `Concluded` 則請開發者確認三大流轉出口。

---

### 步驟 3：呈遞接續狀態卡並確認下一步

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
