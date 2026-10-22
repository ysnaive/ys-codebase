# 技術路線圖：Agents-Workflow Python 工具鏈 (ACI) 強化與狀態機下沉演進 (Roadmap)

> 主題：Agents-Workflow Python 工具鏈 (ACI) 強化與狀態機下沉演進  
> 歸檔日期：2026-10-22  
> 狀態：Ready  
> 模型：Unknown  

---

## 1. 背景與調研目標 (Background & Objectives)

### 1.1 核心架構背景與設計權衡 (Validated Design Trade-offs)

在對 [ysnaive/ys-codebase](https://github.com/ysnaive/ys-codebase) 之 [`ys_codebase/source/agents-workflow`](../ys_codebase/source/agents-workflow) 進行全面架構審計與實戰驗證後，確認現行系統具備三項不可動搖的核心設計基石（Architectural Invariants）：

1. **SOP 00~07（7+1 階段）拆分之必要性**：
   - **人類審查認知負荷控制**：若合併 `Phase 01`（需求）、`Phase 02`（架構）、`Phase 03`（API 契約）與 `Phase 04`（實作計畫），單次產出資訊量過大，將導致人類審查員無法有效建立跨階段追溯與邊界評估；針對低風險且已定稿之工作量，系統已透過 [`/auto`](../ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md) 提供跳過中間等待的加速閥門。
   - **小參數量模型之外部化思維鏈（Externalized CoT）**：日常開發常混用較小參數量模型；若缺少強制分階段輸出規劃文件的剛性步驟，小模型直接跳入編碼時發生架構幻覺與遺漏邊界條件的機率會大幅飆升。
   - **除錯與複查雜訊隔離**：明確分離需求、架構、API、實作規劃與編碼落地，能在事後複查（Post-mortem）時快速定位問題源頭，整體收益遠大於少數跨階段修改的成本。
2. **全域憲法（`AGENTS.md`）極簡 Token 保護**：
   - 為避免永駐上下文的 [`AgentsStandards.md`](../ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md) 消耗過多 Token，`AGENTS_SKILL_ROUTING` 僅保留漏觸發會直接破壞團隊工程標準的 3 個核心技能（`development-sop`、`yscb-cli-guide`、`documentation`），其餘流程技能交由 Frontmatter `description` 路由。
3. **多跳讀取之近因權重優勢（Recency Bias Advantage）**：
   - 實務運行證實，不論大模型或小模型，最新一輪工具讀取進入 Context 的文件擁有最高注意力權重，因此「主技能 -> 階段參考檔 -> 模板檔」的鏈式讀取不會發生規則遺忘。

### 1.2 當前核心痛點：Prompt 軟性狀態機 vs. Python 工具鏈潛力未完全釋放

在維持上述三大基石的前提下，當前架構最主要的優化空間在於 **[`agents_workflow/plans/`](../ys_codebase/source/agents-workflow/agents_workflow/plans) Python 工具鏈與 Markdown Skills 之間的職責分工**：

- **痛點一（機械式庶務消耗小模型注意力）**：目前「斷點狀態推導（16 列查表）」、「`handoff.md` 閱後即焚刪除」、「模板 Header 抄寫與 `> 模型：` 填寫」以及「`changelog.md` 追加」高度依賴 LLM 閱讀 Markdown 後自行手動操作，小模型極易在機械式庶務上出錯（如漏刪 `handoff.md`、漏改 `> 狀態：`）。
- **痛點二（跨階段模型切換與局部推進對鷹架建構的約束）**：實務開發中，開發者經常**在不同 Phase 切換不同模型版本**（例如 `P00`~`P03` 用高推理模型規劃、`P05` 換成高速編碼模型實作），或**單次計畫僅規劃推進至特定階段即暫停**。若一次預建所有階段檔案，不僅會污染後續階段的 `> 模型：` 紀錄（違反 `test_plans_model_record.py` 守門原則），更會破壞 `status.py`（`PlanStatusResolver`）以「目錄下既有最新檔案」判定進度的 SSOT 邏輯。
- **痛點三（合規驗證時機過晚）**：強大的 [`verifier.py` (`PlanVerifier`)](../ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py) 目前直到 `Phase 07` 的最後一步（Step 3）才執行，導致 `Phase 01`~`06` 期間發生的標頭錯誤或追溯鏈斷裂（如 `FR-XX` 未映射至 `FT-XX`）潛伏累積至結案才爆發。

- **調研目標**：
  依據 [Anthropic《Writing Effective Tools for AI Agents》](https://www.anthropic.com/engineering/writing-tools-for-agents) 與 [SWE-agent ACI (Agent-Computer Interface) 研究](https://www.researchgate.net/publication/380907343_SWE-agent_Agent-Computer_Interfaces_Enable_Automated_Software_Engineering)，設計一套**支援跨階段模型切換、支援局部階段執行、且 100% 相容現有 7+1 SOP** 的 Python 工具鏈強化方案與開發路線圖（Roadmap）。

## 2. 候選方案分析與對比 (Candidate Evaluation)

### 2.1 階段產物鷹架建構（Scaffolding）策略評估

針對「如何透過 Python CLI 協助小模型建立各階段文件骨架，同時不破壞跨階段模型切換與局部階段推進」進行三方案對比：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：立項時全量預建 (`Batch Upfront Scaffold`)** | 在 `new-plan` 定調時一次生成 `P01`~`P07` 所有空白模板檔 | 只需呼叫一次 CLI | **嚴重破壞現有架構**：(1) 違反 JIT 延遲建檔原則；(2) 導致 `status.py` 誤判計畫已進入 `P07`；(3) 當 `P03` 或 `P05` 切換模型版本時，預先寫入的 `> 模型：` 欄位全數失真，違反 `test_plans_model_record.py` | ⭐☆☆☆☆<br>(不可行) |
| **方案 B：純手動複製模板 (`Manual Read & Write`)** | 維持現狀，進入某階段時由 Agent 先呼叫讀取工具讀 `templates/P0X.md`，再呼叫寫入工具建檔 | 完全支援動態模型切換與局部階段推進 | 每個階段多消耗 1 次讀取 Tool Call；小模型手抄 Header 時容易漏填或改錯欄位，且在 `Phase 02` 容易忘記同步建立 `P06 (Draft)` | ⭐⭐⭐☆☆<br>(現況基準) |
| **方案 C：JIT 單階段按需實例化 (`JIT Single-Phase Step-Init`)（推薦採納）** | **嚴禁預建未來階段**；僅當 Agent **正式獲准進入單一目標階段 `P0X` 的當下輪次**，才呼叫 `plan step-init --phase P0X --model <CurrentModel>`，由 Python 即時生成**該單一階段**之帶標頭鷹架檔（僅在 `P02` 特例同時生成 `P06 Draft`） | 1. **完美支援跨階段換模型**：每個 `P0X` 都在實際執行的那一刻才建檔並寫入當輪真實模型名<br>2. **完美支援局部執行**：做到哪裡才建到哪裡，`status.py` 零誤判<br>3. 省去 Agent 讀取空白模板的 I/O，Header 與模型紀錄 100% 零失誤 | 需在 `plans/` 新增約 80 行輕量鷹架實例化模組，並在 `P06` 正式執行時支援更新或保留當輪測試模型紀錄 | ⭐⭐⭐⭐⭐<br>(最佳解) |

### 2.2 狀態機路由與合規驗證時機評估

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：Prompt 查表路由 ＋ 結案單次驗證（現況）** | 由 `continue/SKILL.md` 的百行表格指導 LLM 判斷斷點，僅在 `Phase 07` Step 3 跑 `plan verify` | 無需修改 Python 程式碼 | `status.py` 與 `SKILL.md` 雙重維護狀態規則；早期階段的追溯鏈或格式錯誤要累積到結案才被發現 | ⭐⭐⭐☆☆ |
| **方案 2：CLI 確定性導航 ＋ 階段左移檢核 (`Shift-Left Gate`)（推薦採納）** | 擴充 `status.py` 直接輸出「下一跳必讀參考檔與動作指令」並原子銷毀 `handoff.md`；擴充 `verifier.py` 支援 `--phase P0X` 單階段即時檢核與自癒型報錯 | 將機械式狀態計算 100% 下沉至 Python（[Anthropic 工具卸載原則](https://www.anthropic.com/engineering/writing-tools-for-agents)）；任何階段漏寫 `FR/EC/FT` 追溯碼在當輪 End Turn 前即刻攔截修正 | 需擴充 `status.py` 與 `verifier.py` 之子命令參數（維持 100% Python 標準庫零外部依賴） | ⭐⭐⭐⭐⭐ |

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 核心設計原則：認知思考歸 Prompt，機械狀態歸 Python

本架構演進嚴格遵守 **`ys-codebase` 零第三方套件依賴（100% Python Standard Library）**與**最小侵入原則**，將工作流切分為兩個正交層面：

1. **認知層（Markdown Skills）**：負責引導模型思考「需求邊界（`P01`）、架構取捨（`P02`）、介面契約（`P03`）、實作拆解（`P04/P05`）」。
2. **機械層（Python ACI Toolchain）**：負責「計算目前斷點在哪、物理刪除已消費的 `handoff.md`、按需實例化單一階段模板 Header、連動建立 `P06 Draft`、以及即時檢核當前階段的追溯鏈與標頭合規性」。

### 3.2 四大 Python 工具鏈模組強化設計規格

#### 模組一：`status.py` 升級 —— 確定性下一步領航與 `handoff.md` 原子閱後即焚

- **解決問題**：消除小模型在 `continue` 時判錯階段、在 `Umbrella` 子計畫（`sub_{編號}_{名稱}`）迷路，或讀完 `handoff.md` 後忘記執行物理刪除的問題。
- **CLI 介面擴充**：
  ```bash
  python yscb.py agents-workflow plan status [--plan <plan_name_or_subpath>] [--resume]
  ```
- **核心行為設計**：
  1. **支援子計畫精準定位**：自動識別頂層計畫與 `Umbrella` 下活躍之 `sub_{編號}_{名稱}` 子計畫目錄。
  2. **`--resume` 原子化閱後即焚（Consume & Delete）**：當傳入 `--resume` 且檢測到目標目錄存在 `handoff.md` 時，Python 直接讀取 `handoff.md` 全文嵌入結構化輸出中，並在讀取成功後**立即呼叫 `os.unlink()` 物理刪除 `handoff.md`**，從根源保證 100% 符合閱後即焚測試要求。
  3. **輸出結構化「下一跳行動指令（Next-Action Directive）」**：
     ```text
     [PLAN STATUS] 2026_10_23_0100_auth_refactor (Mode: Full Track)
     - Current Artifact : P02_architecture_plan.md (Status: Confirmed)
     - Coupled Artifact : P06_test_plan.md (Status: Draft)
     - Handoff Consumed : True (handoff.md content printed below & deleted from disk)
     - Next Phase       : Phase 03 (API Spec)
     - Must Read Guide  : .agents/skills/development-sop/references/phase_03_api_spec.md
     - Next Command     : python yscb.py agents-workflow plan step-init --plan 2026_10_23_0100_auth_refactor --phase P03 --model "<CurrentModel>"
     ```

#### 模組二：新增 `scaffolder.py` (`plan step-init`) —— JIT 單階段按需鷹架與跨階段換模型支援

- **解決問題**：支援開發者在任意階段切換不同模型版本、支援只做到特定階段即停手，同時消滅手抄 Header 錯誤與 `Phase 02` 漏建 `P06 (Draft)` 的問題。
- **CLI 介面設計**：
  ```bash
  python yscb.py agents-workflow plan step-init --plan <plan_dir> --phase <P00|P01|P02|P03|P04|P05|P06|P07|fast|rev|research> --model "<CurrentModelName>" [--topic <rxx_topic>]
  ```
- **核心行為設計（嚴守 JIT 單階段原則）**：
  1. **前置階段守門檢查**：在建立 `P03` 前，先透過 `status.py` 檢查 `P02` 是否已存在且狀態為 `Confirmed`（若前置階段未定稿則拒絕建檔並提示原因，防止跳步建檔）。
  2. **單階段即時實例化與當輪模型綁定**：
     - 僅從 `assets/templates/` 讀取**當下指定之單一階段模板**（例如 `P03_api_spec.md`）。
     - 自動從同目錄的 `P00_discuss.md`（或主計畫檔）繼承 `> 功能名稱：` 與 `> 所屬主計畫：`，填入當下日期 `YYYY-MM-DD`，將 `> 狀態：` 初始化為該階段預設初始態（如 `Draft` 或 `In Progress`），並將 `--model` 參數精準寫入 `> 模型：`（若未傳則填 `Unknown`）。
     - **跨階段換模型完全相容**：若開發者在 `P01` 用模型 A、在 `P03` 換成模型 B，因為 `P03` 是在進入 `Phase 03` 時才執行 `step-init`，`P01` 的標頭永遠保留模型 A，而 `P03` 的標頭則精準記錄模型 B，完全符合「接手既有檔案不改標頭、新建檔案記錄當輪模型」的鐵律！
  3. **`Phase 02` / `Phase 04` 對 `P06_test_plan.md` 的生命週期特例處理**：
     - 當執行 `--phase P02` 時：除了建立 `P02_architecture_plan.md`，若目錄下尚無 `P06_test_plan.md`，自動同步從模板建立 `P06_test_plan.md`（標頭 `> 狀態：Draft`、`> 模型：` 填入當輪模型）。
     - 當執行 `--phase P06` 且 `P06_test_plan.md` 已存在時：不覆寫既有檔案與原始 `> 模型：` 標頭，僅將 `> 狀態：` 由 `Confirmed` 切換為 `In Progress` 並提示 Agent 執行測試回填。

#### 模組三：`verifier.py` 升級 —— 階段左移檢核 (`--phase`)、追溯鏈差集比對與自癒型報錯

- **解決問題**：將原本集中在 `Phase 07` Step 3 的合規檢查左移至每個階段落檔時，並用 Regex 集合運算自動抓出漏掉的追溯 ID。
- **CLI 介面擴充**：
  ```bash
  python yscb.py agents-workflow plan verify [--plan <plan_dir>] [--phase <P00..P07|current|all>]
  ```
- **核心檢核矩陣與自癒型輸出（Actionable Error Prompts）**：

| 檢核層級 | 觸發時機 | 自動檢核規則（100% Regex / 標準庫實作） | 自癒型報錯輸出範例（直接指導小模型當輪修正） |
| :--- | :--- | :--- | :--- |
| **Header 與模型欄位檢核** | 任意階段 (`--phase current`) | 檢查 `功能名稱`、`建立日期`、`狀態`、`模型` 欄位存在且非模板預設佔位符 `[...]` | `[FAIL: Header] P01_requirements_spec.md 的『> 模型：』仍為模板佔位符，請填入當輪實際模型名稱或 Unknown。` |
| **`P02` / `P04` 雙檔同步檢核** | `Phase 02` & `Phase 04` | `P02` 完成時檢查 `P06_test_plan.md` 是否存在；`P04` 定稿時檢查 `P06` 標頭是否已改為 `Confirmed` | `[FAIL: Coupled State] P04 已定稿，但同目錄下 P06_test_plan.md 狀態仍為 Draft。請補齊 P06 測試案例並將其狀態更新為 Confirmed。` |
| **跨文件追溯鏈差集檢核 (Traceability Set Diff)** | `Phase 04` / `Phase 06` / `Phase 07` | 提取 `P01` 定義之 `FR-\d+`、`EC-\d+`、`NFR-\d+` 集合，比對 `P06` 測試表是否 100% 涵蓋 | `[FAIL: Traceability Gap] P01 定義了 FR-04, EC-02，但在 P06_test_plan.md 中未找到對應映射。請於 P06 補齊對應之 FT/ET 測試項。` |
| **三層文檔同步與 Checkbox 完結檢核** | `Phase 07` Step 3 (結案最終關) | 1. 檢查 `P00`~`P07` 所有標頭皆達終態且 Checkbox 皆為 `[x]`<br>2. 比對 `P04` 文檔衝擊表所列之 `docs/` 檔案 `mtime` 是否更新 | `[WARN: Doc Sync] P04 標註需更新 docs/core/README.md，但檢測到該檔案自計畫開立以來未有修改紀錄，請確認 Phase 07 Step 1 三層文檔是否已落實。` |

#### 模組四：原子化階段定稿與狀態卡生成器 (`plan complete-phase`)

- **解決問題**：防止小模型在完成階段內文後，忘記更新檔案頂部 `> 狀態：`、忘記追加 `changelog.md`，或輸出的狀態卡格式不合規。
- **CLI 介面設計**：
  ```bash
  python yscb.py agents-workflow plan complete-phase --plan <plan_dir> --phase P02 --summary "完成雙層編譯器架構設計與 P06 草案初始化"
  ```
- **原子化四步事務（Transactional Phase Completion）**：
  1. **前置檢核**：自動呼叫 `PlanVerifier.verify_phase(plan_dir, "P02")`。若檢核為 `FAIL`，立即中止狀態變更並印出自癒型錯誤提示。
  2. **更新標頭狀態**：檢核通過後，將 `P02_architecture_plan.md` 頂部之 `> 狀態：` 原子更新為 `Confirmed`（若為 `P05` 則設為 `Completed`，若為 `P06` 自動化測試通過則設為 `Passed`）。
  3. **追加計畫日誌**：自動於 `<plan_dir>/changelog.md` 追加一筆帶當下時間戳與 `--summary` 的標準變更紀錄。
  4. **輸出標準極簡狀態卡**：直接在 stdout 印出已填妥檔案連結與摘要的 6 行 Markdown 狀態卡，Agent 只需將其呈遞給開發者並立即 End Turn。

## 4. `agents-workflow` 工具鏈演進 Roadmap 需求規格書 (Roadmap Specification)

為方便 `agents-workflow` 開發團隊排程落地，以下將上述架構設計拆解為 **4 個演進里程碑（Milestones M1 ~ M4）**，每個里程碑皆獨立可測、向後相容，且可直接透過 `/new-plan` 轉為 `Full Track` 或 `Fast Track` 子計畫實作：

### 4.1 路線圖里程碑總覽矩陣

| 里程碑編號與名稱 | 優先級狀態 | 目標修改模組 (`ys_codebase/source/agents-workflow/`) | 預估變更規模 | 核心價值與解決痛點 |
| :--- | :---: | :--- | :---: | :--- |
| **M1：狀態機領航與 `handoff` 原子閱後即焚**<br>(`roadmap_m1_state_driver.md`) | **Ready**<br>(P0 最高優先) | `agents_workflow/plans/status.py`<br>`contributes/core.json`<br>`assets/skills/continue/SKILL.md` | 約 80~120 行<br>(Fast/Full Track) | 由 Python 接管斷點計算與 `handoff.md` 自動讀取＋物理刪除，消除 `continue` 百行查表與漏刪檔風險 |
| **M2：階段左移檢核與追溯鏈差集引擎**<br>(`roadmap_m2_shift_left_verifier.md`) | **Ready**<br>(P0 最高優先) | `agents_workflow/plans/verifier.py`<br>`tests/test_plans_*.py` | 約 120~180 行<br>(Full Track) | 支援 `--phase P0X` 單階段即時檢核、`FR/EC -> FT/ET` 集合差集檢查與自癒型報錯提示 |
| **M3：JIT 單階段按需鷹架生成器**<br>(`roadmap_m3_jit_step_scaffolder.md`) | **Proposed**<br>(P1 次高優先) | `agents_workflow/plans/scaffolder.py` (新增)<br>`contributes/core.json`<br>`assets/skills/development-sop/` | 約 100~150 行<br>(Full Track) | 支援跨階段切換模型與局部階段推進的 JIT 單檔實例化，自動鎖定 `> 模型：` 與 `P02`+`P06 Draft` 連動 |
| **M4：原子化階段定稿與二振失敗熔斷提示**<br>(`roadmap_m4_atomic_transition.md`) | **Backlog**<br>(P2 中長期演進) | `agents_workflow/plans/transition.py` (新增)<br>`assets/skills/auto/SKILL.md`<br>`assets/skills/discuss/SKILL.md` | 約 100~140 行<br>(Full Track) | 將「驗證 -> 改 Header 狀態 -> 寫 `changelog.md` -> 印狀態卡」封裝為單一原子命令，並加入連續 2 次失敗之 `/discuss` 熔斷橫幅 |

### 4.2 各里程碑詳細需求與驗收規格 (Detailed Requirements for Handoff)

#### 里程碑 M1：狀態機領航與 `handoff.md` 原子閱後即焚 (`M1: Deterministic State Driver`)

- **功能需求 (Functional Requirements)**：
  - `FR-M1-01`：`PlanStatusResolver` (`status.py`) 須新增 `resolve_next_action(plan_dir)` 方法，根據現有檔案與標頭狀態，回傳結構化之 `{mode, current_phase, current_status, next_phase, required_reference_uri, target_template_uri}`。
  - `FR-M1-02`：`plan status` CLI 新增 `--resume` 旗標；當目標計畫（含 `Umbrella` 活躍之 `sub_{編號}_{名稱}` 子目錄）存在 `handoff.md` 時，輸出其內容並立即呼叫 `os.unlink()` 物理刪除該檔案。
  - `FR-M1-03`：保持唯讀無副作用預設行為——未帶 `--resume` 時，`plan status` 僅執行純唯讀掃描，絕不刪除 `handoff.md`。
- **相容性與守門條件**：
  - 100% 向下相容既有 `plan status` 輸出格式與 `test_plans_model_record.py` 測試套件。

#### 里程碑 M2：階段左移檢核與追溯鏈差集引擎 (`M2: Shift-Left PlanVerifier`)

- **功能需求 (Functional Requirements)**：
  - `FR-M2-01`：`PlanVerifier` (`verifier.py`) 新增 `--phase <P00..P07|current|all>` 參數，允許針對單一已完成階段執行局部檢核，同時完整保留 `Phase 07` Step 3 最終全量 `plan verify` 行為。
  - `FR-M2-02`：新增跨文件追溯鏈集合比對器（Traceability Set Matcher），自動解析 `P01_requirements_spec.md` 中的 `FR-\d+`、`EC-\d+`、`NFR-\d+`，並於 `--phase P04` / `P06` / `all` 時核對 `P06_test_plan.md` 是否存在未覆蓋之孤兒需求 ID。
  - `FR-M2-03`：所有 `FAIL` / `WARN` 輸出必須附帶具體修復行動指引（Actionable Fix Hint），明確指出缺失檔案、缺失欄位或未映射之 ID 清單。

#### 里程碑 M3：JIT 單階段按需鷹架生成器 (`M3: JIT Single-Phase Scaffolder`)

- **功能需求 (Functional Requirements)**：
  - `FR-M3-01`：新增 `plan step-init --plan <dir> --phase <phase_id> --model "<model_name>"` 命令（列為 `[SAFE]` 自主安全級別 CLI）。
  - `FR-M3-02`：**嚴格單階段按需建檔（Strict Single-Phase JIT）**——每次呼叫僅實例化當前指定的單一階段檔案（絕不預建後續未執行的階段），以確保開發者在後續階段切換模型版本或提前結束局部階段時，每個階段檔案的 `> 模型：` 與存在狀態均 100% 反映真實執行歷程。
  - `FR-M3-03`：當 `--phase P02` 執行時，若同目錄尚無 `P06_test_plan.md`，自動同步實例化 `P06_test_plan.md` 並將其標頭狀態設為 `Draft`。
  - `FR-M3-04`：若目標階段檔案已存在（例如接手既有階段或 `P06` 已於 `P02` 建立 Draft），`step-init` 嚴禁覆寫既有內文與原始 `> 模型：` 標頭（完全遵守「接手既有計畫檔不得修改檔頭模型紀錄」之公理）。

#### 里程碑 M4：原子化階段定稿與二振失敗熔斷提示 (`M4: Atomic Transition & Circuit Breaker`)

- **功能需求 (Functional Requirements)**：
  - `FR-M4-01`：新增 `plan complete-phase --plan <dir> --phase <phase_id> --summary "<text>"`，串聯執行「`verify --phase` -> 更新目標檔 `> 狀態：` -> 追加 `changelog.md` -> 印出該階段極簡狀態卡」。
  - `FR-M4-02`：於計畫目錄暫態快取（或狀態檢核紀錄）追蹤同階段連續驗證失敗次數；當同一階段連續 2 次驗證或測試失敗時，於 CLI 輸出頂部強制印出 `[CIRCUIT BREAKER: /discuss REQUIRED]` 熔斷提示橫幅，引導小模型立即停止盲目試錯並切換至 [`/discuss`](../ys_codebase/source/agents-workflow/assets/skills/discuss/SKILL.md)。
