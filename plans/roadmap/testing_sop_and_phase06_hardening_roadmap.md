# 技術路線圖：環境型測試規範技能 (`testing-sop`)、Phase 06 連鎖守門與專案測試流程嫁接 (Roadmap)

> 主題：環境型測試規範技能 (`testing-sop`)、Phase 06 連鎖守門與專案測試流程嫁接  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

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

### 4.3 組件三：結合 `how-to-config-yscb` 嫁接專案專用測試流程與注意事項
1. **擴充 `how-to-config-yscb` 探勘與代寫項目**：
   - 在 `how-to-config-yscb` 步驟 1（全專案設定與空間拓撲自動探勘）中，自動探勘專案的測試基建（如 `pyproject.toml` / `package.json` / `Cargo.toml` / `tests/` 目錄結構、測試執行器、沙盒基底類別與 Fixture 慣例）。
   - 在步驟 2（設定健康度報告與代寫提案卡）中，若發現專案尚未配置專屬測試導引（`config://agents-workflow/snippets/testing_guide.md`），自動草擬包含以下四要素的專案測試導引：
     1. **標準測試執行指令**（單一檔案／單一子系統跑測指令 vs. 全量回歸指令，及是否禁止日常全量跑測）。
     2. **測試目錄拓撲與命名規範**（子系統測試檔對應規則）。
     3. **沙盒隔離與基底類別契約**（如 YSCB 的 `YSCBTestCase` + `@require(Requirement.ISOLATED_SANDBOX)`，或 `pytest` 的 `tmp_path` fixture）。
     4. **專案特殊測試紅線與注意事項**（如禁止連外網、Mock 邊界、特定資料庫／Daemon 隔離要求）。
   - 在步驟 3（授權後代寫修復與物化驗證）中，經開發者確認後直接代寫 `config://agents-workflow/snippets/testing_guide.md`，並自動於 `config://agents-workflow/contribute.json` 宣告注入至 `TESTING_SOP_STANDARDS` 錨點（`mode: "append"`），依序執行 `contributes check` $\to$ `agents-workflow compile` $\to$ `agents-workflow release` 三步驗證完成物化。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 核心工作流升級提案，與 `how-to-config-yscb` 及 `skill-creator` 協同構成完整的品質守門體系（`development-sop` 管開發流程、`documentation` 管知識庫文檔、`testing-sop` 管測試建置與測試集純化）。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（建立 `testing-sop` 技能與存量純化參考指南）**：
   - 建立 `assets/skills/testing-sop/SKILL.md`（含六大測試鐵律與 `__@{TESTING_SOP_STANDARDS}__` 錨點）及 `assets/skills/testing-sop/references/test_suite_audit_and_purification.md`（六維度測試集體檢與收斂指南）。
   - 於 `contributes/agents-workflow.json` 註冊 `testing-sop` 技能匯出與 `TESTING_SOP_STANDARDS` Token。
2. **Stage 2（植入 `AgentsStandards.md` 與 `development-sop` 引用連鎖觸發與 Phase 06 守門）**：
   - 更新 `AgentsStandards.md` 條件式技能路由表。
   - 於 `phase_04_plan.md`、`phase_05_task.md`、`phase_06_test.md` 與 `plan_modes.md` 植入 `` [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) `` 強制引用連鎖觸發，並強化 Phase 06 雙重驗收守門檢核表。
3. **Stage 3（對接 `how-to-config-yscb` 專案測試流程自動探勘與嫁接）**：
   - 於 `how-to-config-yscb` 納入 `config://agents-workflow/snippets/testing_guide.md` 自動探勘、草擬與確認後代寫注入 `TESTING_SOP_STANDARDS` 之閉環，並通過雙層編譯與 `evals/run_ab_benchmark.py` 驗證。
