# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 建立環境型技能 `testing-sop` 主檔 (`assets/skills/testing-sop/SKILL.md`) 與擴充錨點註冊 | 1. 建立 `assets/skills/testing-sop/SKILL.md`，YAML Frontmatter `name: testing-sop`，`description` 採用環境型三段式結構（功能宣告 + `觸發情境：` + `排除情境：`）。<br/>2. 內建 **「六大自動化測試建置與回歸鐵律（Six Core Test Hygiene Invariants）」**：<br/>   - **鐵律 1（子系統 1:1 歸戶）**：新增或修改測試案例時，強制依被測子系統職責歸入既有 `test_<subsystem>.*` 擴充；嚴禁以單次開發計畫名、Bug 編號或臨時話題（如 `test_fix_xxx.py`）新建碎片測試檔。<br/>   - **鐵律 2（實質副作用與正負雙向斷言）**：嚴禁將待測目標函式自身 Mock 掉、嚴禁僅斷言 `assertIsNotNone(obj)` / `assertIn(rc, (0, 1))` 或以 `if found:` 靜默放行；每個測試須驗證具體輸入 $\to$ 真實邏輯調用 $\to$ 可觀測副作用，且核心功能須包含負向錯誤攔截測試。<br/>   - **鐵律 3（管線實機產出驗證取代靜態文檔搜尋）**：驗證程式碼邏輯、CLI、編譯器、驗證器或業務管線時，須呼叫真實生成/檢驗函式並檢查產出結構，嚴禁以 grep 外部靜態 Markdown 文檔取代實機執行（專門檢驗倉庫內 Markdown 資產/計畫檔格式之 Meta-Linter 測試除外）。<br/>   - **鐵律 4（零歷史墓碑與舊測同步清理）**：重構或移除舊 API 時同步刪除或改寫舊測試，嚴禁留下僅斷言舊方法已刪除（如 `assertFalse(hasattr(cls, 'old_api'))`）之歷史墓碑測試或死代碼測試。<br/>   - **鐵律 5（100% 狀態隔離與 `tearDown` / `try...finally` 零殘留）**：凡涉及檔案系統、設定檔、註冊表或環境變數變更之測試，須於隔離沙盒或暫存目錄中進行，並將清理包入 `tearDown` 或 `try...finally`，確保跑測後工作區與 `git status` 100% 零殘留。<br/>   - **鐵律 6（本體獨立性與零跨層反向耦合）**：底層或核心模組之單元測試須可在獨立環境下 100% 通過，嚴禁反向匯入、讀取或 `patch` 上層選配業務模組。<br/>3. 內建 **「Phase 06 測試品質與回歸自檢清單（Test Hygiene Gate）」**、預留 Stage 1 專案專屬測試流程錨點 **`__@{TESTING_SOP_STANDARDS}__`**，並定義情境 A（日常增量測試）與情境 B（存量測試集大掃除 $\to$ 按需讀取 `./references/test_suite_audit_and_purification.md`）分流。<br/>4. 於 `contributes/agents-workflow.json` 註冊 `testing-sop` 技能匯出與 `TESTING_SOP_STANDARDS` Token（`[P01:DR-01]`）。 | P0 | [P00:DR-01] |
| **FR-02** | 建立存量測試集體檢與純化按需參考指南 (`references/test_suite_audit_and_purification.md`) | 1. 建立 `assets/skills/testing-sop/references/test_suite_audit_and_purification.md`，供開發者要求對既有 `tests/` 執行健檢、去重、碎片檔整併或虛假測試清理時按需讀取。<br/>2. 完整定義 **「六大測試病灶體檢模型（`T-01` ~ `T-06`）」**：<br/>   - `T-01` 虛假空殼與寬容放行斷言（Vacuous & Lenient-Pass Assertions）<br/>   - `T-02` 計畫名碎片檔與跨檔重複初始化（Plan-Named Fragmentation & Redundant Setup）<br/>   - `T-03` 歷史墓碑與死代碼殘留（Tombstone & Obsolete Tests）<br/>   - `T-04` 跨層反向耦合與非必要靜態文檔 Grep（Cross-Layer Coupling & Doc Grep）<br/>   - `T-05` 真實工作區狀態污染與漏清理（Workspace State Pollution）<br/>   - `T-06` 高風險負向邊界與核心契約漏測（Missing Negative & Boundary Coverage）<br/>3. 定義三階段純化標準工作流：**Step 1（六維度盤點與病灶標記）** $\to$ **Step 2（產出「測試集體檢與子系統 1:1 歸戶映射表」等待確認 Gate）** $\to$ **Step 3（無損整併、碎片檔清理與實機全綠回歸驗證）**。 | P0 | [P00:DR-01] |
| **FR-03** | 植入 `AgentsStandards.md` 與 `development-sop` (`P04/P05/P06/Fast Track`) 引用連鎖觸發與雙重守門 | 1. 於 `assets/standards/AgentsStandards.md` §2 條件式技能分流導航矩陣新增 `testing-sop` 強制觸發路由列。<br/>2. 於 `phase_04_plan.md` §3 植入定稿 `P06_test_plan.md` 前強制觸發 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)（確認測試檔案符合子系統 1:1 歸戶且含正負雙向斷言）。<br/>3. 於 `phase_05_task.md` §2 植入編寫或修改自動化測試前強制觸發 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)（落實實質副作用斷言與沙盒零殘留；Subagent 委派時列為必讀上下文）。<br/>4. 於 `phase_06_test.md` 頂部檢核表與 §2 植入 **「Phase 06 測試品質與回歸雙重守門（Test Hygiene & Regression Gate）」**：強制觸發 `testing-sop`，執行 **守門 ①（子系統回歸全綠）** 與 **守門 ②（新增測試反模式自檢：無計畫名碎片檔、無空殼/寬容放行斷言、無歷史墓碑、跑測後 `git status` 零殘留）**。<br/>5. 於 `plan_modes.md` §2 `Fast Track` 之 `FP-02`（實作與測試階段）同步植入 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 強制引用（`[P01:DR-02]`）。 | P0 | [P00:DR-02] |
| **FR-04** | 植入 Subagent 支柱一（`/research` 與 `/discuss` 唯讀廣域探索隔離協定） | 1. 於 `assets/skills/research/SKILL.md`（步驟 2）與 `assets/skills/discuss/SKILL.md`（步驟 1）內化 **「支柱一：唯讀廣域探索隔離（Pillar 1: Read-Only Exploration Delegation）」**。<br/>2. 明定當跨模組調研或根因排查需檢索/翻閱多份源碼與文檔時，可派發唯讀 Subagent（支援單一或平行派發，嚴守單層星型拓撲 `1-Level Hub-and-Spoke` 與 Single-Writer 禁改 `plans/`）。<br/>3. 強制約束 Subagent 回傳極簡結構化摘要（150~300 Tokens：關鍵證據、精確檔案行號與方案優劣對比），嚴禁傾倒完整源碼；主視窗基於濃縮證據撰寫 `R{NN}_{topic}.md` 或歸因討論卡；若運行環境不支援 Subagent 則無縫降級為主視窗內聯執行。 | P0 | [P00:DR-03] |
| **FR-05** | 植入 Subagent 支柱二（`/auto` 與大型 `Phase 05/06` 受限讀寫實作隔離協定） | 1. 於 `assets/skills/auto/SKILL.md`（步驟 2/3）、`phase_05_task.md` 與 `phase_06_test.md` 內化 **「支柱二：受限讀寫實作隔離（Pillar 2: Sequential Implementation Delegation）」**。<br/>2. **門檻判定**：當處於 `/auto` 模式進入 `Phase 05/06`，或 `P05_task.md` 含 $\ge 3$ 個跨模組獨立任務組時啟用委派；`Fast Track`、`Revision` 或 $\le 2$ 個簡單任務維持主視窗直行以規避 Token 入場稅。<br/>3. **強制序列與檔案路徑傳址**：依耦合度按「單一任務或高內聚任務組（Cohesive Task Group）」**強制每次僅序列派發 1 個 Subagent**（嚴禁平行改碼）；Prompt 採用「檔案路徑傳址（Pass-by-Reference）」傳遞 `P03_api_spec.md`、`P04_implementation_plan.md`、`P05_task.md` 目標 `[TASK-XX]` 及必讀技能 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)。<br/>4. **二振失敗熔斷（2-Strike Limit）與 Single-Writer**：Subagent 內部跑單元測試遇錯最多僅允許自主嘗試修復 2 次，第 2 次仍失敗必須立即停手回傳 `STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)` 交還主視窗轉入 `/discuss`；Subagent 嚴禁修改 `plans/` 下任何檔案，僅回傳 5 行結構化狀態摘要（`COMPLETED | MINOR_DEVIATION | MAJOR_BLOCKER | CRITICAL_BLOCKER`），由主視窗統一更新 `P05_task.md` 與 `changelog.md`（`[P01:DR-03]`）。 | P0 | [P00:DR-03] |
| **FR-06** | 植入 Subagent 支柱三（`Phase 07` Step 1 唯讀 Fresh-Eyes 冷眼審查協定） | 1. 於 `phase_07_walkthrough.md` 步驟 1 內化 **「支柱三：唯讀冷眼審查（Pillar 3: Read-Only Fresh-Eyes Review Delegation）」**，打破主視窗球員兼裁判之確認偏誤。<br/>2. **新建檔案 `git diff` 盲區防護（防呆 2）**：強制規定 Reviewer Subagent 先讀取 `P04_implementation_plan.md` 預計變更清單，搭配 `git status --short` 與 `git diff HEAD`，並針對 `Untracked (??)` 新建檔案直接讀取檔案內容進行審查。<br/>3. **防吹毛求疵三類硬性審查契約（防呆 3）**：限制 Reviewer Subagent 僅允許回報違反下列三類硬性契約之具體缺失：① 違反 `AGENTS.md` 核心原則 3 之淺層敷衍修補或違反 `testing-sop` 六大測試鐵律之反模式、② `P01` 需求或 `P03` 介面契約未落實之遺漏、③ `P04` 文檔衝擊盤點表列應同步但未更新之三層文檔或公開 API Docstring；嚴禁回報主觀命名或排版微調，無硬性缺失強制直接回傳 `REVIEW_STATUS: PASSED`。<br/>4. **嚴格對齊三步結案時序（防呆 4）**：維持 `Step 1`（Pillar 3 冷眼審查 + 三層文檔對齊修正）$\to$ `Step 2`（產出 `P07_walkthrough.md` `Completed` + 更新 `CHANGELOG.md` 與 `umbrella_overview.md`）$\to$ `Step 3`（執行 `plan verify --log` 最終守門）。 | P0 | [P00:DR-03] |
| **FR-07** | 補強 `RoadmapManager.promote_roadmap` 同目錄多路線圖無損追加合併與測試及文檔同步 | 1. 修改 `agents_workflow/roadmap.py` 之 `RoadmapManager.promote_roadmap()`：當透過 `--plan` 將第 2 份（或更多）Roadmap 遷入已存在 `roadmap.md` 的同一計畫/子計畫目錄時，自動以分隔線無損追加合併新路線圖內容至 `roadmap.md` 並刪除 `plans/roadmap/` 下之原檔，避免 `shutil.move` 直接覆寫。<br/>2. 專案層級對 `TESTING_SOP_STANDARDS` 錨點之 `config://agents-workflow/snippets/testing_guide.md` 注入，交由 `sub_04` `/how-to-config-yscb` 動態探勘與確認後代寫；本子計畫同步更新 `agents-workflow/tests/` 與 `docs/agents-workflow/` 三層文檔（`[P01:DR-04]`）。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 在不支援 Subagent 派發工具（如無 `invoke_subagent` / `Task` 工具）的執行環境中觸發三支柱流程 | 三支柱協定均明確定義「無子代理環境自動降級（Graceful Fallback）」：若當前運行環境未提供 Subagent 工具，主視窗直接依相同硬性檢查清單內聯執行，確保 100% 跨平台相容。 |
| **EC-02** | 支柱二 Subagent 在實作或跑單元測試時遭遇非預期錯誤且連續 2 次修復失敗 | 觸發「二振失敗熔斷（2-Strike Limit）」：Subagent 嚴禁在子視窗執行第 3 次盲目修改，必須立即停止並回傳 `STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)` 與異常現場摘要，由主視窗攔截並發起 `/discuss`。 |
| **EC-03** | `Phase 07` Step 1 執行支柱三冷眼審查時，本次計畫包含尚未 `git add` / `git commit` 之新建源碼檔或測試檔 (`??`) | Reviewer Subagent 強制先讀取 `P04_implementation_plan.md` 變更檔案矩陣並結合 `git status --short`，對所有 `Untracked (??)` 新建檔案直接调用檔案讀取工具檢視全文，杜絕單純依賴 `git diff` 導致新建檔案漏審。 |
| **EC-04** | 支柱三 Reviewer Subagent 試圖針對區域變數命名喜好或排版縮排等主觀風格提出修改建議 | 觸發「防吹毛求疵（Anti-Nitpicking）」收斂邊界：明確禁止回報非三類硬性契約之主觀建議；若無硬性缺失，強制直接回傳 `REVIEW_STATUS: PASSED`，防止引發無意義的重改迴圈。 |
| **EC-05** | 單一子計畫（如 `sub_03` 或 `2026_10_23_1122/sub_01`）需連續執行兩次 `roadmap promote <topic> --plan <sub_dir>` 合流兩份路線圖 | 當目標目錄已存在 `roadmap.md` 時，`RoadmapManager.promote_roadmap()` 自動將第二份路線圖內容追加至既有 `roadmap.md` 尾部並移除來源檔案，保證兩份路線圖內容 100% 完整保留。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 上下文經濟性 (Token Efficiency) | 1. `testing-sop/SKILL.md` 主檔行數嚴格控制在 $\le 120$ 行內，將存量測試集六維度體檢指南拆分至 `references/test_suite_audit_and_purification.md` 按需載入。<br/>2. Subagent 委派一律採用「檔案路徑傳址（Pass-by-Reference）」，且回傳摘要嚴格控制在 $150 \sim 300\text{ Tokens}$ 內。 |
| **NFR-02** | 雙層編譯與測試相容性 | 1. 新增之 `testing-sop` 技能與 `TESTING_SOP_STANDARDS` 錨點須 100% 通過 `contributes check`、`agents-workflow compile` 與 `agents-workflow release` 雙層編譯管線。<br/>2. 技能 Frontmatter 須 100% 符合 `test_plans_model_record.py` 之環境型技能三段式描述契約（含 `觸發情境：` 與 `排除情境：`）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 技能清單測試同步 (`test_plans_model_record.py`)**：`ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 中對內建技能清單（`expected_skills`）與環境型技能三段式 `description` 有剛性斷言，新增 `testing-sop` 時必須同步將 `"testing-sop"` 納入測試預期清單並確保其 Frontmatter `description` 具備 `觸發情境：` 與 `排除情境：`。
- **`[!NOTE]` Single-Writer 計畫檔保護**：所有 `plans/` 下之文件（`P00`~`P07`、`R{NN}`、`changelog.md`）100% 僅由主視窗寫入，Subagent 嚴禁觸碰 `plans/`，以確保 `> 模型：` 標頭與 `changelog.md` 狀態一致性。
- **階段決策紀錄**：
  - **`[P01:DR-01]`**：`testing-sop` 採用「主檔控日常增量（六大鐵律 + `TESTING_SOP_STANDARDS` 錨點）＋ `references/test_suite_audit_and_purification.md` 控存量純化（`T-01`~`T-06`）」雙層漸進式揭露結構。
  - **`[P01:DR-02]`**：透過 `AgentsStandards.md` 路由表與 `phase_04` / `phase_05` / `phase_06` / `plan_modes.md` (`FP-02`) 語意 URI 連結實現全鏈路強制連鎖觸發。
  - **`[P01:DR-03]`**：Subagent 委派協定採用「三支柱門檻觸發 + 檔案路徑傳址 + Single-Writer + 二振熔斷 + Fresh-Eyes 三類硬性契約」，不新增獨立 Skill 或 CLI 切片器。
  - **`[P01:DR-04]`**：`RoadmapManager.promote_roadmap` 支援同目錄多路線圖無損追加合併，解決單一子計畫合流多份 Roadmap 時的覆寫問題。

