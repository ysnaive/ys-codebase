# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 確定性狀態領航 (`resolve_next_action`) | 於 `PlanStatusResolver` / `PlanScanner` 實作 `resolve_next_action(plan_dir)`，支援自動深入 `Umbrella` 活躍之 `sub_{編號}_{名稱}` 子目錄，依據現有檔案與標頭狀態回傳結構化領航資訊 `{target_plan_dir, mode, current_phase, current_status, next_phase, required_reference_path, next_action_hint}`；當單一活躍計畫或透過 `--plan <plan_name_or_subpath>` 指定時，於 `plan status` 輸出領航資訊。 (`[P01:DR-01]`) | P0 | [P00:DR-01] |
| **FR-02** | `--resume` 原子閱後即焚 (`Consume & Delete`) | `plan status` 新增 `--resume` 與 `--plan <plan_name_or_subpath>` 旗標；當傳入 `--resume` 且目標計畫（或活躍子計畫）存在 `handoff.md` 時，完整輸出 `handoff.md` 內容並於讀取成功後立即呼叫 `os.unlink()` 物理刪除該檔案；未傳入 `--resume` 時維持 100% 純唯讀掃描，絕不刪除 `handoff.md`。 | P0 | [P00:DR-01] |
| **FR-03** | `continue/SKILL.md` 查表瘦身與 CLI 優先對接 | 更新 `assets/skills/continue/SKILL.md`，改為優先執行 `python __${yscb.host://yscb.py}__ agents-workflow plan status --resume [--plan <name>]` 自動取得下一步指令、參考檔路徑並自動消費刪除 `handoff.md`（保留極簡唯讀沙盒 Fallback 指引）。 | P0 | [P00:DR-01] |
| **FR-04** | `--phase` 局部與雙檔協同左移檢核 | `PlanVerifier` 與 `plan verify`（及 `plan check`）新增 `--phase <P00..P07|current|all>` 參數；支援針對特定計畫或 `sub_XX` 子路徑進行階段左移檢核：於檢核 `P02`（或 `P02` 已存在之 `current`/`all`）時強制檢核同目錄是否已建立 `P06_test_plan.md`；於檢核 `P04`（或 `P04` 已存在之 `current`/`all`）時強制檢核 `P06_test_plan.md` 標頭狀態是否已達 `Confirmed`、`In Progress`、`Passed` 或 `Completed`。 (`[P01:DR-02]`) | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | `P01` $\leftrightarrow$ `P06` 追溯鏈集合差集比對與刪除線預過濾 | 於 `PlanVerifier` 實作需求追溯差集檢核：當目錄存在 `P01_requirements_spec.md` 與 `P06_test_plan.md` 且檢核範圍涵蓋 `P04` / `P06` / `current`（當處於 P04+ 時）/ `all` 時，自動提取 `P01` 定義之 `FR-\d+`、`EC-\d+`、`NFR-\d+` 集合（提取前預先剝除 Fenced Code Blocks `` ```...``` ``、HTML 註解 `<!--...-->` 與 Markdown 刪除線 `~~...~~`），比對 `P06_test_plan.md` 是否 100% 涵蓋，若有遺漏則回報 `FAIL` (類別 `TRACEABILITY`) 並精確列出孤兒需求 ID 清單。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-06** | 自癒型可操作修復指引 (`Actionable Fix Hint`) | 強化 `PlanVerifier` 所有 `FAIL` / `WARN` 診斷訊息（含 `STRUCTURE`、`CHANGELOG`、`PLACEHOLDER`、`HEADER`、`CHECKLIST`、`TEMPLATE`、`ID_MATRIX`、`COMPANION`、`TRACEABILITY`），確保每則問題訊息均附帶明確的修復指引（Actionable Fix Hint），直接點出缺失檔案、未替換佔位符、缺少之章節或未映射之 `FR-XX`/`EC-XX`/`NFR-XX`。 | P0 | [P00:DR-01] |
| **FR-07** | `--log` 免讀盲寫追加、伴隨檔自癒與四步管線時序 | `plan verify`（及 `plan check`）支援 `--log "<摘要>" [--type PHASE|DECISION|REVISION] [--model "<ModelName>"]`，並嚴格執行四步管線：Step 1 先檢核目標階段主體檔合規性 $\to$ Step 2 若主體檔合規且缺少 `changelog.md` 或 `--phase P02`（或當前最新為 `P02`）缺少 `P06_test_plan.md`，自動從模板初始化伴隨檔（`P06` 設為 `Draft`） $\to$ Step 3 執行雙檔協同與全項合規檢核 $\to$ Step 4 僅當檢核 100% `PASS`（0 `FAIL`）時，自動以系統當前時間 `YYYY-MM-DD HH:MM` 於 `changelog.md` 表格頂部插入新紀錄列，並比對首筆資料列之 `(類型, 摘要)` 實現冪等防重入。 (`[P01:DR-03]`) | P0 | [P00:DR-02] |
| **FR-08** | 伴隨檔模型紀錄防回溯與終端引號規範同步 | 自動初始化伴隨檔（`changelog.md` 或 `P06_test_plan.md`）時，標頭 `> 模型：` 優先取 `--model` 參數，未傳時僅允許讀取當下同階段主體檔標頭模型，否則填 `Unknown`（嚴禁跨階段回溯舊檔如 `P00`）；同步更新 `contributes/core.json`、`development-sop/SKILL.md` 及階段手冊，明定 `--log "<摘要>"` 字串內文禁用雙引號 `"` 與反引號 `` ` ``。 | P0 | [P00:DR-03], [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `plan status --resume` 於存在多個進行中計畫且未指定 `--plan` 時呼叫 | 為遵守零臆測原則，若活躍計畫（未 Completed/Concluded）超過 1 個且未傳入 `--plan`，輸出狀態矩陣並提示請以 `--plan <name>` 指定目標計畫，拒絕盲目挑選或刪除任何 `handoff.md`。 |
| **EC-02** | `P01_requirements_spec.md` 中含有以刪除線 `~~FR-99~~` 作廢之需求，或於代碼塊 `` ```...``` `` / HTML 註解中出現範例 `FR-88` | 提取 `P01` 需求 ID 集合前，預先剝除 Fenced Code Blocks、HTML 註解與 `~~...~~` 刪除線片段，確保作廢需求與範例 ID 不會被誤判為未映射之孤兒 ID。 |
| **EC-03** | Agent 執行 `plan verify --phase P02 --log "..."` 時，`P02_architecture_plan.md` 本身含有未替換佔位符或缺少必填標頭 (`FAIL`) | 四步管線於 Step 1 偵測到主體檔有 `FAIL` 時，Step 2 拒絕為不合規的主體檔憑空生成伴隨 `P06_test_plan.md`，且 Step 4 絕對禁止將 `--log` 寫入 `changelog.md`，直接回傳非 0 Exit Code 與修復指引。 |
| **EC-04** | Agent 對同一階段重複執行相同之 `plan verify --log "<相同摘要>" --type PHASE` | 冪等防重入機制比對 `changelog.md` 表格第一筆資料列之 `(類型, 摘要)`，若完全相同則跳過重複插入並輸出 `[IDEMPOTENT]` 提示，保持表格純淨。 |
| **EC-05** | 伴隨檔自動初始化時未傳入 `--model` 且同階段主體檔標頭無模型或無法識別 | 嚴格禁止回溯讀取 `P00_discuss.md` 等前序舊階段檔案之模型名稱，直接安全降級填入 `Unknown`，100% 符合 `AGENTS.md` 模型紀錄鐵律。 |
| **EC-06** | 針對 `Umbrella` 主計畫下的子計畫執行 `plan verify <umbrella_name>/sub_01_xxx` 或 `--plan <umbrella_name>/sub_01_xxx` | 路徑解析器同時支援傳入完整相對路徑 `<umbrella>/sub_XX` 或直接傳入唯一子目錄名 `sub_XX`（自動於活躍 Umbrella 下定位），並正確識別 `is_sub_plan=True` 校驗 `> 所屬主計畫：` 標頭。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 依賴 | 100% 使用 Python 標準庫（`pathlib`, `re`, `os`, `datetime`, `dataclasses`），零第三方套件新依賴；單次 `plan status --resume` 或 `plan verify --log` 本機執行時間 $\le 100\text{ms}$。 |
| **NFR-02** | 向後相容性 | `PlanVerifier.verify_plan()`、`verify_all_plans()` 與 `verify()` 原有呼叫簽名與回傳結構（含 `PlanReport` Tuple 解構 `passed, errors = verifier.verify_plan(...)`）維持 100% 向後相容，既有 `agents-workflow` 109 項單元測試全數無損通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 查閱 `[DN-AW-07]` 與 `[DN-AW-08]`：`PlanStatusResolver` 僅解析 Markdown 前 35 行 Blockquote (`> 欄位：值`)；模型紀錄嚴禁跨檔回推舊階段標頭；`PlanVerifier` 動態自模板提取佔位符與章節標題，因此自動初始化伴隨檔 `P06_test_plan.md (Draft)` 時，必須完整保留標準模板之二級/三級章節標題並填入預設佔位測試項 `- [ ] **FT-01**：待於 Phase 4 定稿補齊 (對應 FR-01)` 以通過 `ID_MATRIX` 與 `TEMPLATE` 檢核。

