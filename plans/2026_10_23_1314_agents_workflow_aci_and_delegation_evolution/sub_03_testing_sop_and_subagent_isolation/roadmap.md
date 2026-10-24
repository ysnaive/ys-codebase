# 技術路線圖合流：環境型測試規範技能 (`testing-sop`) 與 Subagent 三支柱上下文隔離協定 (Merged Roadmaps)

> 主題：環境型測試規範技能 (`testing-sop`)、Phase 06 連鎖守門與 Subagent 三支柱任務級上下文隔離協定  
> 歸檔日期：2026-10-23  
> 目標範疇：agents-workflow  
> 前置解鎖條件：已完成 sub_01 (ACI 工具鏈) 與 sub_02 (Roadmap/TODO 雙層體系)  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

# Part I：環境型測試規範技能 (`testing-sop`)、Phase 06 連鎖守門與專案測試流程嫁接

> 原始來源：`plans/roadmap/testing_sop_and_phase06_hardening_roadmap.md`

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在長期使用 AI Agent 推進開發計畫（`Full Track P04~P06` 與 `Fast Track`）的實務觀察與 `core/tests/` 實機體檢中，發現當缺乏專屬的「自動化測試建置與回歸品質規範」時，Agent 在撰寫與維護測試時會自然演化出 **6 大結構性退化病灶**：
1. **任務導向碎片檔膨脹（Plan-Named Test Fragmentation）**：Agent 習慣為單次開發計畫或修復任務新建獨立測試檔（如 `test_build_git_decoupling.py`、`test_config_and_hook_observability.py`），而非歸入被測子系統的主測試檔（`test_uri.py`、`test_config.py`），導致同一元件的測試散落於 3～4 個檔案中重複初始化。
2. **虛假測驗與寬容放行（Vacuous & Lenient-Pass Assertions）**：為求快速讓 `P06_test_plan.md` 綠燈過關，Agent 常將被測目標函式自身 Mock 掉、僅斷言 `assertIsNotNone(obj)` 或 `assertIn(rc, (0, 1))`、或以 `if found:` 包覆核心斷言在找不到檔案時靜默放行。
3. **以靜態文檔搜尋取代管線實機驗證（Static Doc Grep over Pipeline Execution）**：驗證格式或規範時，不去呼叫真實生成／驗證管線並檢查產出結構，反而去 grep 外部靜態 Markdown 文檔字面內容。
4. **歷史墓碑與死代碼測試殘留（Tombstone & Obsolete Tests）**：重構刪除舊方法後，留下專門檢查 `assertFalse(hasattr(obj, "old_deleted_api"))` 的歷史墓碑測試，或持續測試已無呼叫者的死代碼。
5. **真實環境污染與未清理狀態（Workspace State Pollution）**：測試直接寫入專案 `config://` 或 `module://`，卻未標註隔離沙盒或未於 `tearDown` / `try...finally` 復原，在工作區留下幽靈設定目錄。
6. **下游專案測試工具鏈與注意事項無法標準化嫁接（Missing Project Test Harness Grafting）**：不同專案使用的測試框架（如 YSCB `dev test`、`pytest`、`vitest`、`cargo test`）、沙盒基底類別與環境禁忌各異，現有 `phase_06_test.md` 僅有抽象口號，缺乏與 `how-to-config-yscb` 聯動的專案測試流程注入機制。

### 1.2 現況與影響範圍評估
- **架構定調：建立與 `documentation` 對偶之環境型技能 `testing-sop`，透過 `development-sop`（`P04 / P05 / P06 / Fast Track`）引用方式連鎖觸發，並結合 `how-to-config-yscb` 嫁接專案專屬測試規範**：
  1. **雙對偶環境型技能架構（`documentation` $\leftrightarrow$ `testing-sop`）**：
     - `documentation` 管轄「知識庫文檔與註解品質」（於 `P07` / `FP-03` 強制引用連鎖觸發）。
     - **`testing-sop`** 管轄「自動化測試建置、Phase 06 回歸驗證與既有測試集體檢純化」（於 `P04` 測試定稿、`P05` 測試編碼、`P06` / `FP-02` 測試驗證強制引用連鎖觸發，並掛載於 `AgentsStandards.md` 條件式技能路由表）。
  2. **漸進式揭露雙層結構（主檔控增量 ＋ 參考檔清存量）**：
     - **`testing-sop/SKILL.md`（約 90～110 行）**：定義日常開發必遵的「六大自動化測試建置與回歸鐵律」、`P06` 測試代碼自檢清單（Test Hygiene Gate），並預留 **`__@{TESTING_SOP_STANDARDS}__`** 錨點承接專案專屬測試流程。
     - **`testing-sop/references/test_suite_audit_and_purification.md`（按需載入）**：封裝「六大測試病灶體檢模型（`T-01`～`T-06`）與子系統 1:1 歸戶收斂工作流」，僅在開發者要求對既有 `tests/` 進行測試集健檢、去重與純化時按需讀取，日常寫單一測試時 **0 額外 Token 負擔**。
  3. **與 `how-to-config-yscb` 深度協同嫁接專案專用測試流程**：
     - 由 `how-to-config-yscb` 自動探勘專案之測試框架、執行指令、沙盒機制與測試目錄拓撲，經開發者確認後代寫至 `config://agents-workflow/snippets/testing_guide.md` 並掛載注入 `__@{TESTING_SOP_STANDARDS}__`（成為 `P04 / P05 / P06` 共用的單一測試真相來源 SSOT）。

### 1.3 核心根因
1. 現有 `development-sop` 之 `phase_04_plan.md`、`phase_05_task.md` 與 `phase_06_test.md` 僅規範了「測試流程步驟與狀態流轉（`Draft -> Confirmed -> Passed`）」，缺乏針對「測試代碼本身品質、檔案歸戶與防虛假斷言」的專門技能契約。
2. 缺乏統一承接下游專案專屬測試指令、沙盒規範與測試注意事項的單一真相錨點。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：將所有測試規範直接塞入 `phase_06_test.md` 單一檔案** | 不建新 Skill，直接在 `phase_06_test.md` 寫入長篇測試鐵律與存量純化指南 | 無須新增技能目錄 | 1. **時機太晚**：Agent 在 `P04` 規劃與 `P05` 寫測試代碼時尚未讀到 `phase_06_test.md`，等進到 `P06` 時碎片檔與虛假測試早已寫完<br/>2. **非計畫模式失效**：日常直接修改測試或做測試集健檢時無法獨立觸發 | ⭐️⭐️ |
| **方案 2：僅建立主動指令型 `/test-optimizer` 技能（事後大掃除）** | 平時 `P04~P06` 不變，等測試集腐化後再由人類手動輸入 `/test-optimizer` 重構 | 平時不增加 SOP 連結 | **治標不治本**：無法阻止 Agent 在每次日常開發中繼續製造新的 `test_<plan>.py` 碎片檔與空殼斷言 | ⭐️⭐️⭐️ |
| **方案 3：建立環境型技能 `testing-sop` ＋ 引用連鎖觸發 ＋ `how-to-config-yscb` 嫁接（推薦採納）** | 1. 建立環境型技能 `testing-sop`（主檔管日常六大測試鐵律與 `__@{TESTING_SOP_STANDARDS}__` 專案測試錨點；`references/` 管存量測試集體檢純化）。<br/>2. 於 `AgentsStandards.md` 路由表及 `P04 / P05 / P06 / Fast Track` 以語意連結強制引用連鎖觸發。<br/>3. 由 `how-to-config-yscb` 探勘並代寫專案專屬測試流程注入 `testing-sop`。 | 1. **事前防禦＋事後純化雙閉環**：在 `P04` 規劃與 `P05` 動筆寫測試前即攔截碎片檔與虛假斷言<br/>2. **SSOT 單點注入**：專案測試規範只需注入 `testing-sop` 一次，全階段共享<br/>3. **與 `documentation` 100% 架構對稱** | 需於 `assets/skills/` 新增 `testing-sop` 並於 `phase_04/05/06` 植入連鎖引用連結 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（全塞入 `phase_06_test.md`） | 方案 2（僅建事後 `/test-optimizer`） | 方案 3（環境型 `testing-sop` ＋ 引用連鎖觸發 ＋ 配置嫁接） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高（與既有 `documentation` 技能及雙層編譯管線 100% 同構）** |
| **事前阻斷虛假／碎片測試效果** | 低（`P04/P05` 讀不到 `P06` 規範） | 無（僅事後補救） | **最高（於 `P04` 規劃、`P05` 撰寫與 `P06` 驗收全鏈路強制引用攔截）** |
| **跨專案測試框架適配能力** | 低（需同時改 `P04/P05/P06` 多處錨點） | 低 | **最高（由 `how-to-config-yscb` 單點注入 `TESTING_SOP_STANDARDS`）** |
| **上下文經濟性 (Token Efficiency)** | 低（每次讀 P06 都載入大段純化指南） | 高 | **極高（主檔精簡百行內；存量體檢指南置於 `references/` 按需載入）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```markdown
# 1. 引用連鎖觸發拓撲 (Chained Triggering Topology)
AgentsStandards.md (條件式技能路由表)
  ├── 日常提及「寫測試 / 修測試 / 測試集體檢純化」 ──────────┐
  └── development-sop                                       ▼
        ├── phase_04_plan.md (§3 定稿 P06_test_plan.md 前) ──► 強制引用觸發 [`testing-sop`]
        ├── phase_05_task.md (§2 編寫單元/回歸測試代碼前) ───► (`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)
        ├── phase_06_test.md (§2 執行測試驗證與品質自檢前) ──►   ├── 1. 六大自動化測試建置與回歸鐵律
        └── plan_modes.md (Fast Track FP-02 實作與測試驗證) ─►   ├── 2. `__@{TESTING_SOP_STANDARDS}__` (由 how-to-config-yscb 嫁接專案測試規範)
                                                                 └── 3. 按需載入 `references/test_suite_audit_and_purification.md` (存量測試集體檢純化)
```

### 4.1 組件一：環境型技能 `testing-sop` (`assets/skills/testing-sop/SKILL.md`) 規格設計
1. **Frontmatter 觸發與負向排他邊界**：
   ```yaml
   ---
   name: testing-sop
   description: 規劃、撰寫、執行與審查專案自動化測試 (單元測試、邊界測試、整合與回歸測試)，以及對既有測試集 (tests/) 執行六維度體檢、去重與純化重構。觸發情境：定稿 P06_test_plan.md (Phase 04)、撰寫或修改測試代碼 (Phase 05 / Fast Track)、執行 Phase 06 測試驗證與回歸守門、或應開發者要求健檢與純化既有測試集。排除情境：純業務生產源碼架構設計 (改用 development-sop) 或非測試類系統知識庫文檔撰寫 (改用 documentation)。
   ---
   ```
2. **內建「六大自動化測試建置與回歸鐵律（Six Core Test Hygiene Invariants）」**：
   - **鐵律 1：子系統 1:1 歸戶（Subsystem Alignment over Plan-Named Files）**：
     新增或修改測試案例時，強制依「被測子系統／模組職責」歸入既有的 `test_<subsystem>.*` 擴充；**嚴禁以「單次開發計畫名稱、Bug 編號或臨時話題（如 `test_fix_xxx.py`）」新建碎片測試檔**（僅在專案新增全新獨立子系統時，方允許建立對應的子系統測試檔）。
   - **鐵律 2：實質副作用與正負雙向斷言（Substance & Negative Assertions）**：
     - **嚴禁虛假空殼測驗**：禁止將「待測目標函式自身」Mock 掉、禁止僅斷言 `assertIsNotNone(obj)` / `assertIn(rc, (0, 1))`、禁止以 `if found:` 包覆關鍵斷言在缺少檔案時靜默放行。
     - **正負雙向驗證**：每個測試必須驗證「具體輸入 $\to$ 真實邏輯調用 $\to$ 可觀測副作用（回傳值、寫盤內容、狀態遷移或底層依賴呼叫參數）」；核心功能除正向 Happy Path 外，必須包含**負向錯誤攔截測試（驗證非法輸入、損毀資料或越界存取時必定拋出預期異常或返回非零錯誤碼）**。
   - **鐵律 3：管線實機產出驗證取代靜態文檔搜尋（Pipeline Execution over Static Doc Grep）**：
     驗證**程式碼邏輯、CLI、編譯器、驗證器或業務管線**時，必須呼叫真實生成／編譯／檢驗函式或管線並檢查產出結構，**嚴禁在單元測試中用字串搜尋（grep）外部靜態 Markdown 規範檔取代實機執行**（*註：專門檢驗倉庫內 Markdown 資產／計畫檔標頭格式與 Frontmatter 合規性之 Meta-Linter 測試不在此限*）。
   - **鐵律 4：零歷史墓碑與舊測同步清理（Zero Tombstone & Obsolete Purge）**：
     重構或移除舊有 API 時，必須同步刪除或改寫對應舊測試；**嚴禁留下「僅斷言某舊方法已被刪除（如 `assertFalse(hasattr(cls, 'old_api'))`）」的歷史墓碑測試**，亦嚴禁保留測試死代碼的過時測試檔。
   - **鐵律 5：100% 狀態隔離與 `tearDown` / `try...finally` 零殘留（Zero Workspace Pollution）**：
     凡涉及檔案系統、設定檔、註冊表或環境變數變更之測試，必須於隔離沙盒或暫存目錄中進行，並將清理邏輯包入 `tearDown` 或 `try...finally`，確保即使斷言中途失敗，工作區與 `git status` 依然 100% 零殘留。
   - **鐵律 6：本體獨立性與零跨層反向耦合（Zero Upper-Layer Coupling）**：
     底層或核心模組之單元測試必須可在獨立環境下 100% 通過，嚴禁反向匯入、讀取或 `patch` 上層選配業務模組。
3. **預留 Stage 1 專案專屬測試流程錨點 `__@{TESTING_SOP_STANDARDS}__`**：
   - 於 `testing-sop/SKILL.md` 內配置 `__@{TESTING_SOP_STANDARDS}__` 錨點（並在 `contributes/agents-workflow.json` 的 `token` 清單註冊），專門承接各模組或下游專案注入的測試框架指令、基底類別與測試紅線。
4. **情境 A（日常增量測試）vs. 情境 B（存量測試集大掃除）按需載入分流**：
   - 當開發者要求對既有模組或專案執行「測試集體檢、去重、碎片檔整併或虛假測試清理」時，強制按需讀取 `[references/test_suite_audit_and_purification.md](./references/test_suite_audit_and_purification.md)`，依循「六大病灶掃描（`T-01` 虛假放行、`T-02` 跨檔重複、`T-03` 過時墓碑、`T-04` 跨模組耦合、`T-05` 狀態污染、`T-06` 高風險漏測）$\to$ 產出分級體檢與子系統歸戶映射表（Gate）$\to$ 執行無損整併與實機全綠驗證」標準流程。

### 4.2 組件二：`development-sop`（`P04 / P05 / P06 / Fast Track`）與 `AgentsStandards.md` 引用連鎖觸發強化
1. **`AgentsStandards.md` §2 條件式技能路由表擴充**：
   - 新增路由列：
     `| **規劃或撰寫自動化測試 / 執行 Phase 6 (P06 / FP-02) 測試驗證與回歸 / 既有測試集體檢純化**<br/>*(定稿 P06、撰寫或修改測試代碼、執行單元/邊界/回歸測試、或審查純化 tests/ 目錄前)* | \`testing-sop\` |`
2. **`phase_04_plan.md`（§3 `P06_test_plan.md` 剛性定稿鐵律）連鎖引用**：
   - 植入規定：「定稿 `P06_test_plan.md` 測試案例前，**強制先觸發並遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)**，確認測試目標檔案符合『子系統 1:1 歸戶原則（優先擴充既有 `test_<subsystem>`，禁止以計畫名新建碎片檔）』，且涵蓋正向與負向攔截斷言。」
3. **`phase_05_task.md`（§2 編碼與單元測試實作）連鎖引用與 Subagent 委派同步**：
   - 植入規定：「撰寫或修改自動化測試腳本前，**強制先觸發並遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)**，嚴格落實實質副作用斷言與 `tearDown` / `try...finally` 沙盒零殘留清理；若透過 Subagent 委派執行 Phase 05 任務包（支柱二），必須將 `testing-sop` 列為 Subagent 必讀上下文。」
4. **`phase_06_test.md`（§2 測試執行與回填鐵律 & 執行檢核表）強化守門**：
   - 於 `phase_06_test.md` 頂部檢核表與 §2 植入 **「Phase 06 測試品質與回歸雙重守門（Test Hygiene & Regression Gate）」**：
     - [!] **強制連鎖觸發 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)**。
     - **守門 ①（子系統回歸全綠）**：除執行本次新增測試案例外，強制實機跑過被修改子系統之完整回歸測試集（100% Passed）。
     - **守門 ②（新增測試反模式自檢）**：將 `P06_test_plan.md` 標為 `Passed` 前，強制自檢本次測試代碼確認：**無計畫名碎片測試檔、無空殼/寬容放行斷言（`assertIsNotNone` / `if found:`）、無歷史墓碑斷言、跑測後 `git status` 無殘留暫存或幽靈組態目錄**（並與 Phase 07 支柱三 Fresh-Eyes Review 硬性審查契約對齊）。
5. **`plan_modes.md`（`Fast Track` `FP-02` 實作與驗證）連鎖引用**：
   - 於 `FP-02` 測試驗證步驟同步加入 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 強制引用。

---

# Part II：Subagent 任務級上下文隔離與三支柱委派協定

> 原始來源：`plans/roadmap/subagent_task_isolation_evaluation.md`

## 5. 問題陳述與根因量化 (Subagent Isolation Problem & Root Cause)

### 5.1 痛點現象
在現行 `agents-workflow` 標準開發流程中，雖然檔案級狀態機（`P00`~`P07`）與跨視窗交接（`/pause` + `/continue`）已解決大部分跨階段記憶問題，但在單一主對話視窗（Main Agent Session）執行以下三種高認知負荷場景時，仍存在明顯的物理瓶頸：
1. **廣域探索與深度調研的「搜索雜訊污染」（`/research` 與 `/discuss`）**：
   執行跨模組調研或根因排查時，Agent 需檢索並翻閱 10~20 份源碼與外部文檔，其中 80% 屬於過程性淘汰資訊，卻永久殘留於主視窗 Context Window 中，干擾後續規格制定。
2. **長鏈條連續實作的「上下文熵增」（`/auto` 與大型 `Phase 05`）**：
   在 `/auto` 模式連續生成 `P01`~`P04` 後進入 `Phase 05/06`，或當 `P05_task.md` 含多個跨模組任務時，前序任務的讀取紀錄與測試失敗 Stack Trace 會快速塞爆主視窗，引發自動壓縮（Compaction）與注意力退化。
3. **球員兼裁判的「同視窗確認偏誤（Confirmation Bias）」（`Phase 07` 結案審查）**：
   讓剛寫完程式碼的同一個主視窗自己執行 `Phase 07` Step 1（三層文檔對齊與代碼品質審查），極易因近因記憶偏誤而流於形式勾選 `[x]`，漏抓淺層敷衍修補（Anti-Patterns）或遺漏 `P04` 承諾之文檔更新。

### 5.2 架構裁決：內化「三支柱門檻觸發式 Subagent 委派協定」
1. **三支柱高投報委派場景（Research 探索隔離 + Implement 實作隔離 + Review 冷眼審計）**：
   - **支柱一（`/research` 與 `/discuss` 廣域探索隔離 — 純唯讀）**：將跨模組檢索、多方案探勘委派予唯讀 Subagent（支援平行或單一派發），主視窗僅接收濃縮證據與優劣對比以撰寫 `R{NN}_{topic}.md`。
   - **支柱二（`/auto` 與大型 `Phase 05/06` 實作隔離 — 受限讀寫）**：當處於 `/auto` 模式或 `Phase 05` 含 $\ge 3$ 個跨模組任務組時，依耦合度按「單一任務或高內聚任務組（Cohesive Task Group）」**強制序列派發**實作 Subagent，將編碼與單元測試除錯 Log 隔離於子視窗；小型任務（`Fast Track`、`Revision` 或 $\le 2$ 個任務）維持主視窗直接執行以規避 Token 入場稅。
   - **支柱三（`Phase 07` 結案三層文檔與品質審查 — 純唯讀 Fresh-Eyes Review）**：派發全新無偏誤的 Reviewer Subagent，直接對照 `P01/P03/P04` 規格與實際 `git diff` 執行挑刺審計（查核核心原則 3 敷衍修補紅線、`testing-sop` 測試反模式、三層文檔對齊與需求覆蓋度），回傳缺失清單由主視窗修正。
2. **採用「檔案路徑傳址（Pass-by-Reference）」，剔除 `plan task-brief` 切片 CLI**：
   - 由於 Subagent 與主視窗共享工作區檔案系統，主視窗委派時僅需在 Prompt 中傳遞 **3 行檔案路徑指針**（如 `請讀取 plans/<plan>/P03_api_spec.md、P04 與 P05 中對應 [TASK-XX] 之規格，並遵循 testing-sop...`），由 Subagent 在獨立視窗直接讀取完整規格。
3. **單一寫入者鐵律（Single-Writer SSOT）**：
   - 所有 `plans/` 目錄下的計畫文件（`P00`~`P07`、`R{NN}`、`changelog.md`）**100% 僅由主視窗統一寫入**，Subagent 嚴禁修改任何計畫文件，徹底保護模型紀錄規則（Model Record）與狀態一致性。

### 5.3 八大安全與收斂護欄（Safety & Convergence Guardrails）
1. **嚴格單層星型拓撲（1-Level Hub-and-Spoke）**：僅主視窗可派發 Subagent，Subagent 嚴禁再遞迴派發子代理（100% 相容 Antigravity / Claude Code / Codex 三平台限制）。
2. **編碼強制序列、唯讀允許平行**：支柱二（修改源碼）每次僅能序列執行 1 個 Subagent，嚴禁平行改碼引發工作樹衝突；支柱一與支柱三（純唯讀探索與審查）允許平行派發。
3. **Single-Writer 計畫檔保護**：Subagent 嚴禁建立或修改 `plans/` 下的任何檔案，確保 `> 模型：` 標頭與 `changelog.md` 100% 由主視窗管控。
4. **極簡回傳格式約束（Return Throttle）**：強制要求 Subagent 回傳結構化摘要（控制在 150~300 Tokens 內），嚴禁將完整源碼或數百行測試通過 Log 傾倒回主視窗。
5. **[防呆 1] 支柱二內部「二振失敗熔斷（2-Strike Limit）」**：Subagent 在執行單元測試遇錯時，**內部最多僅允許自主嘗試修復 2 次**；若第 2 次修改後測試仍未通過，嚴禁在子視窗內繼續盲目試錯燒耗 Token，必須立即停手並回傳 `STATUS: MAJOR_BLOCKER (Two-Strike Test Failure)` 與異常現場摘要交還主視窗，由主視窗無縫轉入 `/discuss`。
6. **[防呆 2] 支柱三檢視新建檔案之 `git diff` 盲區防護**：由於 `Phase 07` Step 1 尚未執行最終 `git commit`，新建之源碼或測試檔處於 `Untracked (??)` 狀態（單跑 `git diff` 無法顯示）。強制規定 Reviewer Subagent **先讀取 `P04_implementation_plan.md` 預計變更清單，搭配 `git status --short` 與 `git diff HEAD`，並針對新增（Untracked）檔案直接讀取檔案內容進行審查**，杜絕漏審新建檔案。
7. **[防呆 3] 支柱三「防吹毛求疵（Anti-Nitpicking）」硬性收斂邊界**：為防止 Reviewer Subagent 為交差而回報無謂的主觀風格建議導致重改迴圈，明確限制其**僅允許回報違反下列硬性契約之具體缺失**：
   - **(1) 違反 `AGENTS.md` 核心原則 3 之淺層敷衍修補與 `testing-sop` 六大測試鐵律之反模式**（如空白 `except` 吞例外、硬編碼假資料、刪除或放寬測試斷言、新建計畫名碎片測試檔、空殼斷言）；
   - **(2) `P01` 功能/邊界需求或 `P03` 介面契約未落實之遺漏**；
   - **(3) `P04` 文檔衝擊盤點表列應同步但未更新之三層文檔或公開 API Docstring**。
   - 嚴禁回報純主觀命名偏好或表層排版微調；若無上述硬性缺失，強制直接回傳 `REVIEW_STATUS: PASSED`。
8. **[防呆 4] 對齊 `Phase 07` 最新三步結案管線時序**：支柱三植入 `phase_07_walkthrough.md` 時，嚴格維持既有三步順序：
   - **Step 1**：執行 Pillar 3 冷眼審查 ＋ 三層文檔對齊修正與代碼清理。
   - **Step 2**：產出 `P07_walkthrough.md`，將所有結案檢核 Checkbox 勾選為 `[x]`，並將頂部標頭 `> 狀態：` 更新為 `Completed`（同步更新根目錄 `CHANGELOG.md` 與主計畫 `umbrella_overview.md`）。
   - **Step 3**：最後實機執行 `plan verify`（或 `plan verify --log`）完成最終合規守門與日誌盲寫。

