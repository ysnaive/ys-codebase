# 需求規格說明書 (Requirements Specification)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-18  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `context-init` 模型紀錄規則對齊與 CLI 原則表述校準 (`GAP-09`) | 1. 修正 `assets/skills/context-init/SKILL.md` 步驟 1 第 2 點，移除已廢除之「首行強制輸出當前模型識別錨點」，對齊 `AgentsStandards.md` 核心原則 2 最新之模型紀錄規範（建立計畫檔時 `> 模型：` 僅填當輪平台明確宣告之模型名稱，無法確認填 `Unknown`，嚴禁反推或猜測）。<br/>2. 校準 `context-init/SKILL.md` 核心原則 1 表述為「優先使用內建檔案讀取工具讀取靜態規範，僅於步驟 3 調用唯讀 `plan status` 查詢計畫大綱」。<br/>**驗收條件**：`context-init/SKILL.md` 不再包含「首行強制輸出」字樣，且與 `AgentsStandards.md` 模型紀錄原則 100% 一致。 | P0 | [P00:DR-02] |
| **FR-02** | `handoff.md` 消費後銷毀機制與 Umbrella 子計畫交接路徑對齊 (`GAP-01`) | 1. 於 `assets/skills/continue/SKILL.md` 步驟 2 及步驟 3-U 明定：當讀取 `handoff.md` 成功恢復斷點並開始推進下一步時，強制立即刪除該已消費之 `handoff.md`（Consume & Delete），防止後續 `plan status` 持續誤標 `(Paused)` 或下次 `/continue` 誤讀過期快照。<br/>2. 於 `assets/skills/pause/SKILL.md` 步驟 1 與步驟 2 明定：若當前進行中任務為 Umbrella 子計畫，`handoff.md` 應落檔於目標子計畫目錄 `sub_{編號}_{名稱}/handoff.md`。<br/>**驗收條件**：`continue/SKILL.md` 與 `pause/SKILL.md` 對 `handoff.md` 之生成位置（含 `sub_XX/`）與消費後刪除規則完全對稱。 | P0 | [P00:DR-02] (Q2) |
| **FR-03** | Umbrella 主從計畫狀態連動與主目錄產物契約對齊 (`GAP-02`) | 1. 於 `assets/skills/development-sop/references/plan_modes.md` §5 與 `development-sop/SKILL.md` §4 明定 Umbrella 主目錄必備產物為 `umbrella_overview.md` + `changelog.md`（主計畫級 `P00` / `R{NN}` 為選配），並定義主從狀態同步規則：首個 `sub_XX` 啟動時主計畫標頭轉為 `In Progress`；新建 `sub_XX` 時登記於 `umbrella_overview.md` §2 矩陣；`sub_XX` 結案時同步更新父目錄 `umbrella_overview.md`（§2 子計畫狀態、§3 里程碑勾選 `[x]`）與主目錄 `changelog.md`；全部子計畫完成且無後續階段時主計畫標頭轉為 `Completed`。<br/>2. 修正 `assets/skills/continue/SKILL.md` §3-U 步驟 1，改為「讀取主計畫的 `umbrella_overview.md`（若主目錄存在 `P00_discuss.md` 或 `R{NN}_*.md` 則一併參考）」。<br/>3. 於 `phase_07_walkthrough.md` §1 與 `plan_modes.md` §2 `FP-03` 補齊 Umbrella 子計畫結案回寫父目錄 `umbrella_overview.md` 與 `changelog.md` 之提示。<br/>**驗收條件**：主目錄產物定義與 `verifier.py` 要求一致，`continue §3-U` 不再強制假設主目錄必有 `P00_discuss.md`。 | P0 | [P00:DR-02] (Q3) |
| **FR-04** | 跨軌道升級/轉型之舊產物處置與 Roadmap 狀態閉環 (`GAP-03`) | 1. **Fast Track 升級 Full Track**（`plan_modes.md` §2）：明定升級時將已釐清需求轉入 `P00_discuss.md` / `P01_requirements_spec.md`，**並刪除原 `fast_track_plan.md`**（避免 `scanner.py` 與 `/continue` 因 `fast_track_plan.md` 優先匹配而誤判），同時記錄於 `changelog.md`。<br/>2. **Revision 觸發 4 大熔斷**（`plan_modes.md` §3）：區分「獨立修訂計畫（將內容轉入同目錄新軌道檔案，刪除未完成之 `revision_log.md` 或將已完成項標記 `Completed` 結算）」與「附掛於既有已結案計畫之修訂（嚴禁在原已結案目錄塞入 `fast_track_plan.md` 或 `P01~P07`；須將已完成表層微調於 `revision_log.md` 標記 `Completed` 結算或回滾刪除，並另開新計畫或新 `sub_XX`）」。<br/>3. **Research 三大出口轉化**（`plan_modes.md` §4 & `research/SKILL.md`）：明定出口 ①、②、③ 拍板時均須先將 `R{NN}_{topic}.md` 標頭更新為 `Concluded`（出口 ③ 同步將 `P00_discuss.md` 標記為 `Confirmed` / `Completed`）。<br/>4. **Roadmap 狀態閉環**（`templates/roadmap.md` & `roadmap/SKILL.md`）：將標頭狀態枚舉擴充為 `[Backlog | Proposed | Ready | Deferred | In Progress | Completed]`，並於 `roadmap/SKILL.md` 步驟 4 明定立項時更新為 `In Progress`、結案時更新為 `Completed`。<br/>**驗收條件**：4 種跨軌流轉場景在對應手冊與模板中均具備明確之舊檔清理/狀態更新規定。 | P0 | [P00:DR-02] (Q4) |
| **FR-05** | 結案管線 `plan verify` 最終守門時序校正 (`GAP-04`) | 1. 調換 `assets/skills/development-sop/references/phase_07_walkthrough.md` §1（含 Mermaid 圖與正文）之步驟 2 與步驟 3 順序：先完成「步驟 1：三層文檔交付對齊與代碼清理」$\to$「步驟 2：撰寫 `P07_walkthrough.md`（標頭設為 `Completed`、所有檢核 Checkbox 標記 `[x]`）、更新 `changelog.md` 與全域 `CHANGELOG.md`」$\to$「步驟 3：實機執行 `plan verify <plan_name>` 驗證 100% Passed 作為最終結案守門」。<br/>2. 同步校準 `templates/P07_walkthrough.md`、`templates/fast_track_plan.md`、`templates/revision_log.md` 結案檢核清單之文字時序：明定先將所有檢核項勾選 `[x]` 並將頂部標頭 `> 狀態：` 更新為 `Completed`，最後執行 `plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。<br/>**驗收條件**：消除 `P07` 漏檢與 `Completed` 狀態下未勾選 `- [ ]` 之時序死鎖。 | P0 | [P00:DR-02] |
| **FR-06** | `/discuss` 次要問題三大範疇出口與全階段回填鏈補齊 (`GAP-08`) | 1. 於 `assets/skills/discuss/SKILL.md` 步驟 2 補充：當觸發原因為「次要衍生問題 / 範疇越界」時，候選方案須明確對接 `AgentsStandards.md` §1.3 提供三大範疇裁定出口（① 擴充當前計畫範疇進行標準修復、② 維持當前範疇並另闢新計畫/子計畫、③ 登錄至 Roadmap 長期技術儲備）。<br/>2. 於 `discuss/SKILL.md` 步驟 3.2「產物回填」補齊完整溯源回填鏈：依決策影響層級同步更新 `P00` / `P01`（需求邊界）、`P02` / `P03`（架構與 API）、`P04` / `P05` / `P06`（實作與測試）或 Fast Track 之 `fast_track_plan.md`。<br/>**驗收條件**：`discuss/SKILL.md` 完整覆蓋次要衍生問題三出口與 Full/Fast Track 全階段產物回填。 | P1 | [P00:DR-02] |
| **FR-07** | `P04`/`P05` 任務清單去重與 `P04`/`P07` 三層 5 列文檔表對齊 (`GAP-10`) | 1. 將 `assets/templates/P04_implementation_plan.md` §4 修改為無 Checkbox (`- [ ]`) 之「`## 4. 實作順序與任務預排 (Implementation Sequence)`」（使用有序清單 `1. **TASK-01**：...`），將可勾選之 `- [ ] **TASK-XX**` 執行追蹤唯一收歸 `P05_task.md` §1。<br/>2. 將 `templates/P04_implementation_plan.md` §2 與 `templates/P07_walkthrough.md` §4.1 之文檔表格統一為三層 5 列（① 宏觀：`__${project://CHANGELOG.md}__`、② 中觀：`__${workflow.docs://}__/<Category>/README.md`、③ 中觀：`__${workflow.docs://}__/<Category>/[topic].md`、④ 中觀：`__${workflow.docs://}__/<Category>/DESIGN_NOTES.md`、⑤ 微觀：源碼 Public API Docstring 與 Why-Driven 註解），並將舊稱 `<Module>` 全面替換為 `<Category>`。<br/>**驗收條件**：`P04` 模板不再含 `- [ ] **TASK-` Checkbox，`P04` 與 `P07` 三層文檔表 5 列結構與 `<Category>` 命名 1:1 對齊。 | P0 | [P00:DR-02] (Q5) |
| **FR-08** | 階段手冊與模板欄位輕量對齊、標頭預設狀態定錨及路由/權限微調 (`GAP-05`, `GAP-06`, `GAP-07`, `GAP-11`, `GAP-12`) | 1. **標頭預設狀態定錨 (`GAP-05`)**：於 `development-sop/SKILL.md` §6 明定各產物落檔預設標頭狀態（`P00`：有待確認項填 `Discussing`，已確認填 `Confirmed`；`P01~P04`：落檔即填 `Confirmed` 免雙重寫檔；`P05`/`fast_track_plan`/`revision_log`：執行中填 `In Progress`，結案填 `Completed`；`changelog.md`：建檔填 `In Progress` 或 `Active`，全週期免回寫標頭），並移除 `templates/changelog.md` 範例列之硬編碼 `(狀態：Discussing)`。<br/>2. **手冊與模板既有章節內對齊 (`GAP-11`)**：不新增必填 `##` 章節；於 `templates/P00_discuss.md` §1 補 `- **架構影響範圍**：` 並將 §3 預設 `- [ ]` 改為 `- `；於 `templates/P01_requirements_spec.md` §1 表頭改為 `詳細規格與驗收條件 (Acceptance Criteria)` 並於 `phase_01_requirements.md` 說明 `[P01:DR-XX]` 記錄於對應條目或 `changelog.md`；於 `templates/P03_api_spec.md` §2 補充「錯誤與例外契約」欄位並與 `phase_03_api_spec.md` 對齊；將 `templates/roadmap.md` §1.2 標題通用化為 `### 1.2 現況與影響範圍評估`、§4 通用化為 `## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)`。<br/>3. **連續推進與權限守門定義 (`GAP-12` & `GAP-06/07` 輕量指針)**：於 `auto/SKILL.md` 步驟 2 免除 Phase 2 建立 `P06 (Draft)` 中繼寫入，改於 Phase 4 一次建立 `P06_test_plan.md (Confirmed)`；於 `yscb-cli-guild/SKILL.md` §2 表格前補齊 `[SAFE]` / `[CONDITIONAL]` / `[GATED]` 三級權限行為定義，並同步 `context-init` 與 `session-analysis` 之權限標籤表述；於 `AgentsStandards.md` §2 `development-sop` 欄附註生命週期路由提示，於 `new-plan/SKILL.md` §1 補單行跳轉 `phase_00_discuss.md` 指針。<br/>**驗收條件**：所有修改後之模板與手冊通過 `PlanVerifier` 動態章節與佔位符檢核，無新增冗餘必填 `##` 章節。 | P1 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 修改 `assets/templates/*.md` 之 `##` 或 `###` 章節標題時，觸發 `PlanVerifier.get_resolved_template_headers()` 對活躍計畫之動態章節檢查 | **[P01:DR-01]** 嚴格控制模板 `##` / `###` 標題變更：在 `P00`、`P01`、`P03` 中僅調整清單項與表格欄名，**不新增任何 `##` 或 `###` 標題**；對於 `P04 §4` 標題微調，本子計畫自身產出之 `P04_implementation_plan.md` 將直接採用新標題，且當前 `plans/` 下無其他未完成之活躍 Full Track 子計畫（`sub_01` 已 `Completed` 並將同步驗證相容性）。 |
| **EC-02** | `templates/roadmap.md` 標頭狀態枚舉擴充為 `[Backlog | Proposed | Ready | Deferred | In Progress | Completed]` 後，`PlanVerifier.get_dynamic_placeholders()` 與 `roadmap.py` 之解析相容性 | `verifier.py` 之 `get_dynamic_placeholders()` 會動態讀取模板前 35 行 `[A | B | ...]` 生成正則攔截未替換佔位符，擴充後自動生效；`roadmap.py` 保留 `## 1. 問題陳述與背景分析` 標題正則匹配，100% 向後相容。 |
| **EC-03** | 附掛於已結案計畫（如 Full Track `Completed`）之 `revision_log.md` 在修訂途中觸發 4 大熔斷條件 | 嚴禁在已結案計畫目錄內原地建立 `fast_track_plan.md` 或重開 `P01~P07`（否則 `scanner.py` 會將整個已結案計畫誤判為未完成之 Fast Track）；強制規定將已完成之表層微調於 `revision_log.md` 標記 `Completed` 結算（或回滾未完成修改並移除 `revision_log.md`），再另開獨立新計畫或新 `sub_XX`。 |
| **EC-04** | `P00_discuss.md` 在無待決開放議題時直接以 `Confirmed` 或未來 `Completed` 結案，若模板 §3 殘留空 `- [ ]` 將觸發 `verifier.py` 未勾選檢查報錯 | 將 `templates/P00_discuss.md` §3 預設範例由 `- [ ]` 改為一般無 Checkbox 清單項 `- `（或說明有待決議題時才使用 `- [ ]` 並於確認後勾選 `[x]`）。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 提示詞精簡與零雙重維護 (Token Efficiency & SSOT) | 嚴守 SSOT：不在 `AgentsStandards.md` 重複展開 7 列工作流路由表，不在 `new-plan/SKILL.md` 重複撰寫 `phase_00_discuss.md` 之步驟細節，確保常駐 System Prompt 零無謂膨脹。 |
| **NFR-02** | 測試與驗證合規性 (Verification & Test Gate) | 修改 `ys_codebase/source/agents-workflow/assets/` 後，執行 `python yscb.py dev test agents-workflow` 與 `python yscb.py dev check agents-workflow` 須 100% 通過（0 Failed, 0 Warnings, 0 Errors），且 `python yscb.py agents-workflow plan verify` 100% Passed。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 嚴禁手動直接修改 `.agents/` 物化目錄**：所有變更必須 100% 落於 `ys_codebase/source/agents-workflow/assets/` 源碼空間；待測試通過並獲授權或透過標準建置流程後，方由發布器同步物化。
- **`[!WARNING]` `PlanVerifier` 動態章節鏡像機制 (`[DN-AW-07]` / `[DN-AW-13]`)**：`verifier.py` 會動態解析 `assets/templates/*.md` 內的所有 `##` 與 `###` 標題（忽略編號前綴與括號英文後比對核心中文標題）。若修改既有模板之 `##` 標題文字（如 `P04 §4`），必須確認 `plans/` 下所有活躍計畫（含 `sub_01` 之 `P04_implementation_plan.md`）是否會受影響——**[P01:DR-01]** 為確保與同主計畫下已完成之 `sub_01/P04_implementation_plan.md`（其 §4 標題為 `## 4. 實作任務清單 (Task Breakdown & Topological Sequence)`）100% 相容且 `plan verify` 零報錯，`templates/P04_implementation_plan.md` §4 **保留原 `## 4. 實作任務清單 (Task Breakdown & Topological Sequence)` 標題文字不變**，僅將其內部清單由 `- [ ] **TASK-01**` 改為無 Checkbox 之有序清單 `1. **TASK-01**`！
- **`[!NOTE]` 模板禁用 HTML 註解 (`[DN-AW-15]`)**：編輯 `assets/templates/*.md` 時嚴禁加入任何 `<!-- ... -->` HTML 註解。

