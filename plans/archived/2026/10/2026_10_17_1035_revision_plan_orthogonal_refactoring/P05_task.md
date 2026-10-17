# 實作任務清單 (Implementation Task List) — 修訂計畫正交化與留檔體系重構

> 功能名稱：修訂計畫正交化與留檔體系重構
> 建立日期：2026-10-17
> 狀態：Completed
> 模型：Gemini 4 Argon (Low)

---

## 1. 實作任務清單 (Task Breakdown)

### Step 1：修訂紀錄模板與模組匯出配置
- [x] **[TASK-01] 建立 `revision_log.md` 模板並註冊匯出資產**
  - **目標檔案**：`ys_codebase/source/agents-workflow/assets/templates/revision_log.md`、`ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - **執行內容**：建立通用無自引用的 `revision_log.md` 模板（含修訂來源脈絡、`[REV-XX]` 條目結構與收斂檢核清單），並於 `contributes/agents-workflow.json` 註冊 `workflow.template.revision_log` 匯出。

### Step 2：Plans 工具鏈正交化擴充 (`scanner.py` / `verifier.py` / `archiver.py`)
- [x] **[TASK-02] 擴充 `PlanScanner` 正交 Track 識別**
  - **目標檔案**：`ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py`
  - **執行內容**：在 `analyze_plan_dir` 中於 `Umbrella`、`Fast Track`、`Full Track` 之後、`Phase 0` 之前加入獨立 `revision_log.md` 識別（回傳 `("Revision", status)`），確保附隨型 `revision_log.md` 不干擾既有主計畫或子計畫的 Track 與狀態。
- [x] **[TASK-03] 擴充 `PlanVerifier` 對 `revision_log.md` 之模板與條目檢核**
  - **目標檔案**：`ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`
  - **執行內容**：在 `_map_file_to_template` 映射 `revision_log.md`，於 `get_resolved_template_headers` 豁免動態 `### [REV-\d+]` 標題比對，新增未替換佔位符黑名單（`[修訂主題簡述]`、`[UI/UX/DX | Parameter | Docs]`、`[檔案路徑]`），並在 `_verify_markdown_file` 強制檢核至少一筆 `[REV-\d+]` 條目。
- [x] **[TASK-04] 擴充 `PlanArchiver` 獨立與附隨修訂計畫歸檔守門**
  - **目標檔案**：`ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py`
  - **執行內容**：將 `revision_log.md` 納入獨立修訂計畫完成候選，並新增根目錄與 `sub_*` 子目錄所有 `revision_log.md` 必須標記為 `Completed` 之歸檔阻斷守門。

### Step 3：SOP 技能手冊重構與 P06 業務核心詢問機制
- [x] **[TASK-05] 重構 `development-sop` 技能與各階段參考手冊並全面去特化**
  - **目標檔案**：`ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md` 及 `references/plan_modes.md`、`phase_00_discuss.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md`
  - **執行內容**：廢除「0 計畫檔」，改為正交留檔（獨立型 vs 附隨型 `revision_log.md`）；於 `phase_06_test.md` 實作「業務核心測試聚焦與修訂分流主動詢問機制」；全面清除 YSCB 生態系模組自引用詞彙（`@build`、`dev test`、`dev check`、`dev bump`、`dev release`、`ys_codebase/source/`）。
- [x] **[TASK-06] 同步更新 `new-plan`、`continue`、`auto` 技能與三層文檔**
  - **目標檔案**：`ys_codebase/source/agents-workflow/assets/skills/new-plan/SKILL.md`、`continue/SKILL.md`、`auto/SKILL.md`、`ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/README.md`、`docs/agents-workflow/user_guide.md`
  - **執行內容**：同步更新開立分流、接續現場、`/auto` P06 暫停守門指引，以及模組與專案文檔之 Track 定義與工具鏈行為說明。

### Step 4：單元測試與自舉驗證
- [x] **[TASK-07] 新增 `test_plans_toolchain.py` 修訂計畫正交測試案例並執行自舉發布驗證**
  - **目標檔案**：`ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
  - **執行內容**：新增 `FT-11`（`PlanScanner` Revision Track 與附隨正交性）、`FT-12`（`PlanVerifier` `revision_log.md` 合規檢核）、`FT-13` & `ET-03`（`PlanArchiver` 獨立修訂歸檔與子計畫未完成修訂阻斷），並執行沙盒檢查、測試、熱部署與物化發布。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| `-` | `None` | 無偏差，完全依循 P02~P04 規格實作完成。 | `-` |

