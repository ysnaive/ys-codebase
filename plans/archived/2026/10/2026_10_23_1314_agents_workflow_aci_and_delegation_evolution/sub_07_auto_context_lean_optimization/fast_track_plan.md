# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`/auto` 連續推進工作流 Context 精實化重構 (sub_07_auto_context_lean_optimization)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼與技能資產修改行數預估 $\le 100$ 行（`plans/{status,scanner,verifier,archiver}.py` 新增 `_auto.md` 雙軌相容約 35 行、重構 `auto/SKILL.md` 與 `development-sop/SKILL.md` 約 55 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 破壞性變更（`PlanStatusResolver.resolve_phase_file` 向下相容原名與 `_auto.md` 後綴）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  1. **`[FP-01:DR-01]` 方向 A — `/auto` 內聯契約免讀 11 檔、單檔單次寫入 (`1-Write-Per-File`) 與單次彙總 `plan verify`**：
     - **內聯 `P01`~`P06` 必填標頭與章節標題契約**：於 `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md` 內建精簡之共用 Blockquote Header 規格與 `P01`~`P06` 必備 `##` 二級章節標題速查表；同時於 `development-sop/SKILL.md` §5 明確標註：**觸發 `/auto` 連續推進時，直接依 `auto/SKILL.md` 內聯契約產出 `P01`~`P05`，免除逐一 `read_file` 讀取 `phase_01~05.md`（省去無效的單階段 End Turn 卡片規範）與 `.yscb/templates/P01~P06.md`（共省去 11 次讀檔）**，僅於編寫測試與執行 `Phase 06` 時觸發 `testing-sop` 與 `phase_06_test.md`（含支柱三 Pre-UX 唯讀盲審）。
     - **單檔單次到位寫入 (`1-Write-Per-File Rule`)**：消除中間過渡態重複寫檔——`P01`~`P04` 直接以 `> 狀態：Confirmed` 寫入一次；完成 `P04` 規劃後直接進行代碼與測試實作，實作完成後將 `P05` 直接以 `> 狀態：Completed` 與全勾選 `- [x]` 一次性寫入（免除先寫 `In Progress` 再 Edit）；隨後執行自動化測試，測試 100% 通過後將 `P06_test_plan.md` 直接以 `> 狀態：Passed` 一次性寫入（或更新既有 `P06` Draft，免除 `/auto` 內部 `P02 Draft` 與 `P04 Confirmed` 兩次過渡寫檔）。
     - **單次彙總合規檢核 (`Single Batch Verify`)**：取消 `P01`~`P05` 逐階段執行 `plan verify --phase P0X` 的 5 次 CLI 調用，改於 `P06` 落檔並通過測試後，執行**單次** `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name> --log "<摘要>" --model "<ModelName>"` 一次完成全檔合規、`P01<->P06` 追溯差集比對與 `changelog.md` 免讀盲寫追加。
  2. **`[FP-01:DR-02]` 方向 B — `P01`~`P05` 規格去重精實化 (`DRY Spec Reference & Signature-Only`)**：
     - **單點定義、跨檔指標引用 (`Single-Definition & Pointer Rule`)**：
       - **檔案清單單點定義於 `P02` §3**：`P03` §1 僅列新增/變更之公開或核心類別/函式接口，`P04` §4 實作任務直接引用 `P02 §3` 檔案，不重複抄寫長篇檔案職責表。
       - **任務拆解單點定義於 `P04` §4**：`P05` §1 採極簡完成清單（每項 1 行：`- [x] **TASK-XX**：<簡述>（詳見 P04 §4）`），將 `P05` 嚴格控制在 $\le 25$ 行。
     - **`P03`/`P04` 僅寫簽名契約、嚴禁預寫實作程式碼塊 (`Signature-Only, Zero Implementation Code`)**：`P03` §2 僅允許撰寫類別/函式型別簽名（`def func(...) -> ReturnType: ...`）與 1~2 行前置/後置/例外契約，**嚴禁在 `P03` 或 `P04` 中預先貼入方法內部實作程式碼**（杜絕同一段程式碼在 `P03`、`P04`、`P05` 重複生成 3 次）。
  3. **`[FP-01:DR-03]` `/auto` 自動生成產物專屬後綴命名規範 (`PXX_YYYY_auto.md`) 與 `plans` 工具鏈雙軌相容**：
     - **依起點動態標記 `_auto.md` 後綴**：凡於 `/auto` 連續推進過程中由 Agent 一次自動生成之階段規格檔（`P01`~`P05`），檔名強制附加 `_auto` 後綴（即 `P01_requirements_spec_auto.md`、`P02_architecture_plan_auto.md`、`P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`）：
       - 例 1：開發者於 `P00_discuss.md` 定案後即觸發 `/auto` $\to$ `P01`~`P05` 全數命名為 `P01_*_auto.md` ~ `P05_task_auto.md`。
       - 例 2：開發者人工討論定案至 `P02_architecture_plan.md` 後才觸發 `/auto` $\to$ `P00`~`P02` 維持原名，`P03`~`P05` 命名為 `P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`。
     - **`plans` 工具鏈 `_auto.md` 雙軌相容 (`PlanStatusResolver.resolve_phase_file`)**：於 `status.py` 實作 `resolve_phase_file(plan_dir, phase_code)`，並串聯 `status.py`、`scanner.py`、`verifier.py` 與 `archiver.py`，使狀態掃描、`--resume` 斷點領航、模板章節鏡像檢核、`P02/P04 <-> P06` 雙檔檢核與 `P01 <-> P06` 追溯差集比對均原生相容 `<stem>.md` 與 `<stem>_auto.md` 混用或全自動情境。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/{status.py,scanner.py,verifier.py,archiver.py}`
  - `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `docs/agents-workflow/user_guide.md`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `agents_workflow/plans/{status.py,scanner.py,verifier.py,archiver.py}` 實作 `PlanStatusResolver.resolve_phase_file` 並全面支援 `PXX_YYYY_auto.md` 雙軌相容解析與檢核。
- [x] **TASK-02**：重構 `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`（控制在 $\le 115$ 行，實際 84 行），植入「`PXX_YYYY_auto.md` 動態後綴命名規範」、「`P01`~`P06` 內聯標頭與章節骨架速查表（免讀 11 檔）」、「單檔單次到位寫入 (`1-Write-Per-File`) + 單次彙總 `plan verify`」與「`DRY Spec & Signature-Only` 去重精實規範」，並於 `development-sop/SKILL.md` §5 補入 `/auto` 豁免說明。
- [x] **TASK-03**：於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 新增 `test_ft_13_sub07_auto_context_lean_and_auto_suffix_support`，驗證 `auto/SKILL.md` 內聯章節骨架對齊，以及全 `_auto.md`（`P01`~`P05`）與半途 `_auto.md`（`P01`~`P02` 原名 + `P03`~`P05` `_auto.md`）在 `PlanScanner`、`PlanStatusResolver` 與 `PlanVerifier` 下 100% 通過；同步更新 `docs/agents-workflow/user_guide.md` 與 `docs/agents-workflow/DESIGN_NOTES.md`。
- **測試案例清冊**：
  - [x] **FT-01**：驗證 `auto/SKILL.md` 內聯之 `P01`~`P06` 章節骨架經 `PlanVerifier` 檢核 100% 匹配標準模板章節標題，且包含 `PXX_YYYY_auto.md` 後綴命名、免讀 `phase_01~05` / 模板、單次寫檔 (`1-Write-Per-File`)、單次 `plan verify` 與 `Signature-Only` 禁預寫實作碼規範。
  - [x] **FT-02**：驗證 `PlanScanner`、`PlanStatusResolver.resolve_next_action` 與 `PlanVerifier.verify_plan` 針對「`P00` 後全自動 (`P01~P05_auto.md`)」與「`P02` 後半途自動 (`P01~P02.md` + `P03~P05_auto.md`)」雙情境皆能正確推導狀態、檢核模板標題與 `P01<->P06` 追溯鏈。
  - [x] **RT-01**：`agents-workflow` 全模組單元測試套件 100% 回歸通過（`Pass: 136(100.0%), Fail: 0, Skip: 0`）。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  - 於 `PlanStatusResolver` (`status.py`) 新增 `resolve_phase_file(plan_dir, phase_code)`，支援標準檔名 `<stem>.md` 與 `/auto` 一次生成檔名 `<stem>_auto.md` 雙軌解析，並串聯至 `scanner.py`、`verifier.py` 與 `archiver.py`。
  - 重構 `auto/SKILL.md`（共 84 行）：內建「`PXX_YYYY_auto.md` 動態後綴命名規範」、「`P01`~`P06` 內聯標頭與章節骨架速查表（免除 11 次 `read_file`）」、「單檔單次到位寫入 (`1-Write-Per-File`) + 單次彙總 `plan verify`」與「`DRY Spec Reference & Signature-Only` 去重精實規範」；同步於 `development-sop/SKILL.md` §5 增補 `/auto` 豁免說明。
  - 完成 `agents-workflow@build` 打包安裝、`contributes check`、`compile` 與 `release --force` 雙層同步物化。
- **實機測試日誌**：
  - `python yscb.py dev check agents-workflow`：`Status: PASSED`
  - `python yscb.py dev test agents-workflow -q`：`Pass: 136(100.0%), Fail: 0, Skip: 0`（含新增之 `test_ft_13_sub07_auto_context_lean_and_auto_suffix_support` 正向與混合後綴雙情境驗證）

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/agents-workflow/user_guide.md` §5、`docs/agents-workflow/DESIGN_NOTES.md` `[DN-AW-15]`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 CHANGELOG.md 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_07_auto_context_lean_optimization` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

