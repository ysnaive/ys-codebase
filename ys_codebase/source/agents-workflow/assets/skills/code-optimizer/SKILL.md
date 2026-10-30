---
name: code-optimizer
description: 針對既有業務程式碼執行五維度靜態診斷、業務階段邏輯聚合與行為無損重構。僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發。
---

# 業務代碼五維度診斷與外科手術無損重構工作流 (Code Optimizer)

本工作流採用跨語言通用軟體工程抽象，專門針對**既有業務生產程式碼**執行「前置雙維度定錨（範圍 × 生命週期）$\to$ 建立調研計畫落檔 `R01` 五維度診斷與處方 $\to$ 三大流轉出口裁決 $\to$ 外科手術式行為無損重構（Behavior-Preserving Refactoring）」。執行規範遵循 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 適用情境與觸發時機

- **適用情境**：
  - 對臃腫業務檔案（God File / God Class）、高耦合模組或全專案跨模組邊界進行結構體檢與無損重構。
  - 執行業務方法之階段拆解（`S1`）、無狀態純函式剝離（`S2`）、控制流扁平化（`S4`）、物理模組拆分（`S6`）與死代碼清理。
- **觸發時機**：**100% 純手動觸發**——僅於開發者顯式輸入 `/code-optimizer` 或明確指定調用本技能重構業務代碼時啟動，**嚴禁在一般功能開發中途自動攔截觸發**。
- **排除情境（正交邊界）**：
  - **規劃、撰寫或純化自動化測試集（`tests/`）**：請改用 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)。
  - **審查或重構 AI Agent 技能目錄（`SKILL.md`）**：請改用 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`)。
  - **包含新業務功能或改變外部行為之需求開發**：請走標準 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 開發流程。

---

## [!] 核心原則與防過度設計四大紅線 (Anti-Overengineering Guardrails)

1. **100% 行為等價與錯誤語意保護（Preserve Behavior & Error Semantics）**：重構期間嚴禁偷渡功能變更；不得將原本向上拋出特定異常的契約改為靜默回傳空值（`null` / `None` / `false`），所有邊界條件之輸入輸出行為必須與重構前嚴格等價。
2. **禁止教條式套用設計模式（No Pattern Mania）**：不得將百行內的直觀邏輯或簡單條件分支，硬拆為繁瑣的抽象工廠（Abstract Factory）或策略類別階層；優先採用語言原生的簡潔結構（純函式、衛語句、分派映射表）。
3. **禁止碎紙機式過度拆分（No Nano-Functions / Fragmentation）**：提取內部工具函式的唯一標準是「聚合完整業務階段（SLAP）」或「消除結構性重複（DRY）」，嚴禁將連貫的單一階段邏輯切碎為十幾個僅 3~5 行、迫使閱讀者上下頻繁跳轉的奈米函式。
4. **自我解釋優先於廢話註解（Self-Documenting over Noise Comments）**：以精準的階段函式命名取代段落分隔註解（如 `# Step 1: ...`），清理過時註解與廢棄代碼塊，僅保留解釋「Why（設計取捨與防坑原因）」及公開 API 契約之說明。

---

## 執行步驟

觸發 `/code-optimizer` 時，強制依序執行以下四步檢核流程：

```markdown
/CodeOptimizer 四步診斷與無損重構檢核表：
- [ ] 步驟 1：前置雙維度定錨（向開發者確認「包含式三層範圍」與「Mode A/B 生命週期」，嚴禁 Agent 自行猜測）並建立調研計畫
- [ ] 步驟 2：讀取 exploration-and-delegation.md 與 diagnostic-matrix.md，執行探索與 D1~D5 診斷，落檔 R01_code_optimization_audit.md
- [ ] 步驟 3：呈遞「🔍 R01 代碼診斷與三大流轉出口確認卡」並立即 End Turn 等待開發者裁決出口
- [ ] 步驟 4：(若拍板出口 ① 立即實作) 原地升級實作計畫，讀取 refactoring-playbook.md 執行 S1~S6 無損重構、回歸測試與量化對照
```

### 步驟 1：前置雙維度定錨與調研計畫立項 (`Scope & Lifecycle Triage Gate`)

1. **雙維度前置詢問（零臆測鐵律 — `EC-01`）**：
   若開發者輸入 `/code-optimizer` 時未同時明確指定**「檢視範圍」**與**「生命週期模式」**，Agent **絕對禁止自行根據代碼現況猜測該部分是否已釋出或能否破壞相容性**，必須先向開發者確認以下兩項定錨參數並等待回覆：
   - **① 檢視範圍（包含式階層：`全專案 ⊃ 單一模組 ⊃ 單一檔案`，大範圍完整包含小範圍之 `S1~S6` 微觀分析）**：
     - **特定檔案 / 類別 (`File Scope`)**：針對單一檔案執行 `D1~D5` 診斷與 `S1`（業務階段拆解）、`S2`（無狀態邏輯剝離）、`S3~S5` 收斂及必要之 `S6` 拆檔。
     - **單一模組 (`Module Scope`)**：**完整包含模組內各檔案之 `S1~S6` 微觀分析**，並向上涵蓋模組內跨檔耦合拓撲（`D2` 循環依賴解除、跨檔死代碼）、共用樣板/DTO 收斂與模組公開入口治理。
     - **全專案 (`Project Scope`)**：**完整包含所有模組與內部檔案之 `S1~S6` 深度分析**，並再向上涵蓋跨模組邊界合規（`D5`）、跨模組調用拓撲與全專案重構熱點排序。
   - **② 生命週期與相容性模式（100% 由開發者指定，不由 Agent 判斷）**：
     - **`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**：強制單一正統入口（Single Canonical Entry），零容忍物理刪除相容別名、薄轉發層与過渡代碼，並同步更新所有內部/跨模組調用點。
     - **`Mode B：維護期 / 嚴守向下相容 (Compatibility Mode)`**：對外公開入口與插件契約強制透過門面重匯出（Facade Re-export）維持外部簽名 100% 相容；但**若經全空間調用圖譜與匯出清單「嚴格查驗」確認純屬內部工具函式（非對外公開匯出契約且 0 外部跨模組調用），則同樣直接執行破壞性變更與收斂**，嚴禁為純內部工具函式保留相容轉發層！
2. **建立調研計畫目錄**：
   獲開發者確認雙維度參數後，讀取 [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) 模板，依 JIT 原則於 `__${project://plans}__/` 建立調研計畫目錄（`P00_discuss.md` + `changelog.md`，記錄鎖定之範圍與 `Mode A/B`）。

### 步驟 2：環境感知探索與五維度診斷落檔 (`Research Audit -> R01`)

**[!] 強制前置閱讀**：執行探索與診斷前，必須先讀取 [`references/exploration-and-delegation.md`](./references/exploration-and-delegation.md) 與 [`references/diagnostic-matrix.md`](./references/diagnostic-matrix.md)：

1. **環境感知探索與子代理隔離**：
   - 當目標為 `Project Scope`、`Module Scope`（$\ge 3$ 檔）或單檔 $> 400$ 行時，依 `exploration-and-delegation.md` §3 派發支柱一唯讀探索子代理（傳入已鎖定之 `Mode A/B` 約束，子代理僅用唯讀檢索與 `__%{agent_tool.file_read_range}__` 執行調用圖譜與 `D1~D5` 初篩，回傳 $\le 400$ Tokens 結構化摘要，禁傾倒原始碼）；單一中小型檔案（$\le 400$ 行）由主代理直接內聯檢索。
2. **五維度診斷（`D1~D5`）與六大重構處方（`S1~S6`）速查對照**：
   - **診斷維度**：`D1` 職責內聚與抽象層級（SLAP / 狀態分離）、`D2` 調用耦合與拓撲健康度（無環依賴 / 死代碼清零）、`D3` 控制流與認知複雜度（衛語句 / DRY）、`D4` 介面契約與資源生命週期（型別簽名 / 確定性釋放）、`D5` 架構邊界與專案慣例（基礎設施抽象遵從）。
   - **重構手術刀**：`S1` 業務階段拆解與主幹管線化、`S2` 狀態依賴分析與無狀態邏輯剝離、`S3` 跨方法同構模式聚合、`S4` 控制流扁平化與表驅動分派、`S5` 資料團塊封裝與結構化契約、`S6` 正交職責之物理模組拆分。
3. **落檔 `R01_code_optimization_audit.md`**：
   讀取 [`RXX_research_report.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`) 模板，將契約邊界查驗表（含 `Mode B` 下經嚴格查驗 0 外部調用之內部工具函式清單）、`D1~D5` 分級病灶座標表（`P0/P1/P2`）與 `S1~S6` 重構處方箋寫入計畫目錄之 `R01_code_optimization_audit.md`，並執行 `plan verify` 檢核與追加 `changelog.md`。

### 步驟 3：呈遞診斷卡與三大流轉出口裁決 (`Export Outlet Gate` — 強制 End Turn)

對話 Session **嚴禁傾倒長篇報告或原始碼**，強制僅呈遞以下極簡診斷卡並**立即 End Turn 等待開發者選擇流轉出口**：

```markdown
### 🔍 R01 業務代碼五維度診斷報告已落檔
- **產出文件**：[R01_code_optimization_audit.md](__${project://plans}__/{plan_name}/R01_code_optimization_audit.md)、[P00_discuss.md](__${project://plans}__/{plan_name}/P00_discuss.md)
- **定錨基準**：範圍 `[全專案 / 模組 / 檔案]` ｜ 模式 `[Mode A 收斂期 / Mode B 維護期 (內部工具函式嚴格查證收斂)]`
- **診斷摘要**：P0 共 `[X]` 項、P1 共 `[Y]` 項、P2 共 `[Z]` 項（核心瓶頸：[1~2 行摘要與預計套用之 S1~S6 策略]）
- **推薦流轉出口**：
  1. **出口 ① 立即原地升級實作**：將 `R01` 標記 `Concluded`，原地升級為 `[Fast Track / Full Track / Umbrella]` 執行無損重構
  2. **出口 ② 轉入技術儲備**：將重構藍圖登錄至 `/roadmap`（跨模組）或 `/todo`（局部技術債），標記 `R01` 為 `Concluded`
  3. **出口 ③ 維持現狀結案**：健康度良好或暫無須動刀，標記 `R01` 與 `P00` 為 `Concluded` / `Completed` 留存體檢紀錄
- **待確認事項**：請問是否採納此重構處方箋，並選擇何種流轉出口（① / ② / ③）？
```

### 步驟 4：原地升級實作、外科手術無損重構與量化驗證 (`Surgical Execution & Delta Verify`)

當開發者拍板選擇 **「出口 ① 立即原地升級實作」** 時：
1. **無痛升級計畫軌道（嚴禁轉入 `Revision Plan` — `EC-04`）**：
   將 `R01_code_optimization_audit.md` 標頭更新為 `Concluded`，依範圍與規模原地升級計畫：
   - 修改 $\le 100$ 行、0 公開 API 變更、0 跨模組新依賴 $\rightarrow$ 原地建立 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) 走 **Fast Track**。
   - 單一模組深度重構、涉及物理拆檔（`S6`）或 $> 100$ 行 $\rightarrow$ 原地追加 `P01`~`P07` 走 **Full Track**（或獲授權以 [`/auto`](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`) 推進）。
   - 全專案跨多模組重構 $\rightarrow$ 建立 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) 升級為 **Umbrella** 主計畫，按模組拆分 `sub_XX` 子計畫分批推進。
2. **[!] 按需載入重構策略庫與執行無損修改**：
   讀取 [`references/refactoring-playbook.md`](./references/refactoring-playbook.md)，以 `__%{agent_tool.file_edit}__` 執行 `S1~S6` 重構，嚴守 `Mode A / Mode B` 入口規則與四大防過度設計紅線。
3. **回歸驗證與 Before/After 量化對照**：
   遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 `__%{agent_tool.shell_exec}__` 執行靜態合規檢查與既有回歸測試套件（確保 100% Passed 且錯誤語意零退化），並依 `refactoring-playbook.md` §7 於結案文件輸出 **Before / After 結構量化對照表**。

`__@{CODE_OPTIMIZER_STANDARDS}__`

---

## 常見踩坑指南 (Gotchas)

- **切勿由 Agent 自行猜測 `Mode A / Mode B` 或未確認範圍即掃描全專案（`EC-01`）**：步驟 1 若開發者未明確指定範圍與生命週期模式，必須先提問確認後再建立調研計畫。
- **切勿在 `Mode B` 下為「0 外部調用的純內部工具函式」保留相容轉發垃圾（`EC-02`）**：`Mode B` 的門面保護僅限於對外公開匯出與跨模組契約；經嚴格查驗確認僅在模組內部使用之輔助函式，必須直接破壞性收斂並同步更新模組內調用點。
- **切勿將業務代碼結構重構分流至 `Revision Plan` 或在步驟 3 確認出口前偷改程式碼（`EC-04`）**：`Revision Plan` 僅限非業務邏輯之表層微調；業務代碼重構於步驟 3 獲選出口 ① 後，僅能轉入 `Fast Track`、`Full Track` 或 `Umbrella`。

