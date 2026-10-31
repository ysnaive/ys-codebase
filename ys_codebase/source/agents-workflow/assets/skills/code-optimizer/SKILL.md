---
name: code-optimizer
description: 針對既有業務程式碼執行五維度靜態診斷、業務階段邏輯聚合與行為無損重構。僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發。
---

# 業務代碼五維度診斷與外科手術無損重構工作流 (Code Optimizer)

本工作流採用跨語言通用軟體工程抽象，專門針對**既有業務生產程式碼**執行「前置三維度定錨（範圍 × 生命週期 × 代理執行軌道）$\to$ 建立調研計畫落檔 `R{NN}` 五維度診斷與處方 $\to$ 三大流轉出口裁決 $\to$ 外科手術式行為無損重構（Behavior-Preserving Refactoring）」。執行規範遵循 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 適用情境與觸發時機

- **適用情境**：
  - 對臃腫業務檔案（God File / God Class）、高耦合模組或全專案跨模組邊界進行結構體檢與無損重構。
  - 執行業務方法之階段拆解（`S1`）、無狀態純函式剝離（`S2`）、控制流扁平化（`S4`）、物理模組拆分（`S6`）與死代碼清理。
- **觸發時機**：**100% 純手動觸發（B-Strict）**——僅於開發者顯式輸入 `/code-optimizer` 時啟動，**嚴禁在一般功能開發中途自動攔截觸發**。
- **排除情境（正交邊界）**：
  - **規劃、撰寫或純化自動化測試集（`tests/`）**：請改用 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`)。
  - **審查或重構 AI Agent 技能目錄（`SKILL.md`）**：請改用 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`)。
  - **包含新業務功能或改變外部行為之需求開發**：請走標準 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 開發流程。

---

## [!] 核心原則與防過度設計四大紅線 (Anti-Overengineering Guardrails)

本技能與日常開發 SOP 共用中央代碼品質標準 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`)，執行診斷與重構時強制嚴守以下四大紅線：

1. **100% 行為等價與錯誤語意保護（Preserve Behavior & Error Semantics）**：重構期間嚴禁偷渡功能變更；不得將原本向上拋出特定異常的契約改為靜默回傳空值（`null` / `None` / `false`），所有邊界條件之輸入輸出行為必須與重構前嚴格等價。
2. **禁止教條式套用設計模式（No Pattern Mania）**：不得將百行內的直觀邏輯或簡單條件分支，硬拆為繁瑣的抽象工廠（Abstract Factory）或策略類別階層；優先採用語言原生的簡潔結構（純函式、衛語句、分派映射表）。
3. **禁止碎紙機式過度拆分與行數湊數（No Nano-Functions / LOC-Driven Fragmentation）**：提取內部工具函式的唯一標準是「聚合完整業務階段（SLAP）」或「消除結構性重複（DRY）」，嚴禁將連貫的單一階段邏輯切碎為十幾個僅 3~5 行或 1 行轉發的奈米函式；物理拆檔（`S6`）唯一標準是「分離正交變更軸線（CCP/SRP）」，嚴禁僅因檔案行數較多而強拆高內聚狀態機或線性管線（成熟模組之 `P0` 與 `S6` 允許且應當為 `0` 項）。
4. **自我解釋優先於廢話與工單註解（Self-Documenting over Noise Comments）**：以精準的階段函式命名取代段落分隔註解（如 `# Step 1: ...`），清理過時註解與廢棄代碼塊；**嚴禁在生產代碼註解或 Docstring/XML 註解中留存診斷/規格工單編號（如 `D1~D5`、`S1~S6`、`F-01`、`M-05`、`DR-XX`、`FR-XX`）或「（已移除某某舊邏輯）」之變更歷史噪音**，僅保留解釋「Why（當前架構不變量、設計取捨與防坑原因）」及公開 API 契約之說明。

---

## 執行步驟

觸發 `/code-optimizer` 時，強制依序執行以下四步檢核流程：

```markdown
/code-optimizer 四步診斷與無損重構檢核表：
- [ ] 步驟 1：前置三維度定錨（向開發者確認「包含式三層範圍」、「Mode A/B 生命週期」與「代理執行軌道」，嚴禁自行猜測）並建立調研計畫
- [ ] 步驟 2：讀取 exploration-and-delegation.md 與 diagnostic-matrix.md，依選定軌道執行探索與 D1~D5 診斷，落檔 R{NN}_code_optimization_audit.md
- [ ] 步驟 3：呈遞「🔍 R{NN} 代碼診斷與三大流轉出口確認卡」並立即 End Turn 等待開發者裁決出口
- [ ] 步驟 4：(若拍板出口 ① 立即實作) 原地升級實作計畫，讀取 refactoring-playbook.md 執行 S1~S6 無損重構、回歸測試與量化對照
```

### 步驟 1：前置三維度定錨與調研計畫立項 (`Scope, Lifecycle & Execution Track Gate`)

1. **三維度前置詢問（零臆測鐵律 — `EC-01`）**：
   若開發者輸入 `/code-optimizer` 時未同時明確指定**「檢視範圍」**、**「生命週期模式」**與（針對單一/多模組之）**「代理執行軌道」**，Agent **絕對禁止自行猜測該部分是否能否破壞相容性或擅自大量派發子代理消耗 Token**，必須先向開發者確認以下三項定錨參數並等待回覆：
   - **① 檢視範圍（包含式階層：`全專案 ⊃ 單一模組 ⊃ 單一檔案`，大範圍完整包含小範圍之 `S1~S6` 微觀分析）**：
     - **特定檔案 / 小範圍 (`File Scope`)**：針對單一檔案或局部類別執行 `D1~D5` 診斷與 `S1`（業務階段拆解）、`S2`（無狀態邏輯剝離）、`S3~S5` 收斂及必要之 `S6` 拆檔。
     - **單一模組 (`Module Scope`)**：**完整包含模組內各檔案之 `S1~S6` 微觀分析**，並向上涵蓋模組內跨檔耦合拓撲（`D2` 循環依賴解除、跨檔死代碼）、共用樣板/DTO 收斂與模組公開入口治理。
     - **全專案 / 多模組 (`Project Scope`)**：**完整包含所有模組與內部檔案之 `S1~S6` 深度分析**，並再向上涵蓋跨模組邊界合規（`D5`）、跨模組調用拓撲與全專案重構熱點排序。
   - **② 生命週期與相容性模式（100% 由開發者指定，不由 Agent 判斷）**：
     - **`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**：強制單一正統入口（Single Canonical Entry），零容忍物理刪除相容別名、薄轉發層與過渡代碼，並同步更新所有內部/跨模組調用點與測試。
     - **`Mode B：維護期 / 嚴守向下相容 (Compatibility Mode)`**：對外公開入口與插件契約強制透過門面重匯出（Facade Re-export）維持外部簽名 100% 相容；但**若經全空間調用圖譜與全文檢索「嚴格查驗」確認純屬內部工具函式（非對外公開匯出契約且 0 外部跨模組調用），則同樣直接執行破壞性變更與收斂**，嚴禁為純內部工具函式保留相容轉發層！
   - **③ 代理執行與審查軌道（兼顧 Token 額度節流與平行吞吐量，由開發者按範圍選擇）**：
     - **若範圍為「單一檔案或小範圍 (`File Scope`)」**：**固定採用 `[軌道 1：純主代理內聯執行]`**（免詢問子代理模式，0 子代理冷啟動開銷）。
     - **若範圍為「單一模組 (`Module Scope`)」**，請開發者二選一：
       - **`[軌道 2A：純主代理內聯審查 (Token 節流型)]`**：由主代理親自使用檢索工具與 `__%{agent_tool.file_read_range}__` 分段讀檔逐步完成診斷與實作，適合 Token 額度有限或希望在主對話視窗細部把關之情境。
       - **`[軌道 2B：主代理 + 盲眼子代理 (Context 隔離與盲審型)]`**：委派唯讀/實作子代理執行探索、無偏見盲審（`R{NN}`）或反向查驗（`Reverse Fact-Check`），保持主代理 Context 乾淨。
     - **若範圍為「全專案 / 多模組 (`Project Scope`)」**，請開發者二選一：
       - **`[軌道 3A：主代理序列滾動推進 (`sub_n` 完成後才進 `sub_n+1`，Token 節流型)]`**：於 Umbrella 主計畫下由主代理親自逐一推進各子計畫，完成 `sub_01` 診斷、重構與測試閉環後再進入 `sub_02`，嚴格控制單輪 Token 消耗且無跨模組平行競態。
       - **`[軌道 3B：主代理統籌 + N 路盲眼子代理平行推進 (高吞吐多代盲審型)]`**：按模組分批（每回合上限 3~4 個）派發盲眼子代理平行產出 `sub_XX/R{NN}` 與實作，跳過單模各自編譯測試，由主代理依據跨模組交接表統一收斂並於 `P06` 批次驗證。
2. **建立調研計畫目錄**：
   獲開發者確認三維度參數後，讀取 [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`) 模板，依 JIT 原則於 `__${project://plans}__/` 建立調研計畫目錄（`P00_discuss.md` + `changelog.md`，記錄鎖定之範圍、`Mode A/B` 與代理執行軌道）。

### 步驟 2：環境感知探索與五維度診斷落檔 (`Research Audit -> R{NN}`)

**[!] 強制前置閱讀**：執行探索與診斷前，必須先讀取 [`references/exploration-and-delegation.md`](./references/exploration-and-delegation.md) 與 [`references/diagnostic-matrix.md`](./references/diagnostic-matrix.md)：

1. **依步驟 1 選定之代理軌道執行探索與死代碼雙重查證**：
   - 嚴格遵循開發者於步驟 1 拍板之軌道（`軌道 1 / 2A / 3A` 由主代理內聯檢索；`軌道 2B / 3B` 依 `exploration-and-delegation.md` §3~§4 調度子代理，單一回合平行派發上限 3~4 個）。
   - **[!] 靜態型別、多型與欄位死代碼雙重檢索守門**：在將任何符號列為 `D2` 死代碼前，若 `callers` 為 0，必須強制追加執行全文/符號檢索（如 `knowledge-db search "<SymbolName>"`），確認無 POCO 欄位/泛型 `<T>` 型別宣告、基底指標多型虛擬分派、跨專案靜態欄位讀寫、`[InternalsVisibleTo]` 測試探針或 Source Generator / 反射 Attribute 引用。
2. **五維度診斷（`D1~D5`）與六大重構處方（`S1~S6`）速查對照**：
   - **診斷維度**：`D1` 職責內聚與抽象層級（SLAP / 狀態分離，以正交職責為準，行數僅作探索參考）、`D2` 調用耦合與拓撲健康度（無環依賴 / 雙重查證死代碼清零）、`D3` 控制流與認知複雜度（衛語句 / DRY）、`D4` 介面契約與資源生命週期（型別簽名 / 確定性釋放）、`D5` 架構邊界與專案慣例（基礎設施抽象遵從）。
   - **重構手術刀**：`S1` 業務階段拆解與主幹管線化、`S2` 狀態依賴分析與無狀態邏輯剝離（零殘留轉發殼層）、`S3` 跨方法同構模式聚合（含 20% 差異分支不變量核對與介面預設方法防遞迴）、`S4` 控制流扁平化與表驅動分派、`S5` 資料團塊封裝與結構化契約、`S6` 正交職責之物理模組拆分（含三大免拆守門與同型別 `partial class` 分檔規範）。
3. **落檔 `R{NN}_code_optimization_audit.md`（強制對齊 `RXX_research_report.md` 四大 H2 標題）**：
   讀取 [`RXX_research_report.md`](`__#{module://agents-workflow/assets/templates/RXX_research_report.md}__`) 模板，依 `diagnostic-matrix.md` §3 將五個診斷子區塊掛載於模板標準 H2 標題（`## 1.` ~ `## 4.`）之下作為 `###` H3 子章節寫入 `R01_code_optimization_audit.md`（若為後續跨代無上下文盲審則遞增為 `R02`/`R03`），並執行 `plan verify` 檢核與追加 `changelog.md`。
   - **進階可選品管 — 反向查驗守門 (`Reverse Fact-Check Gate`)**：針對高複雜度核心模組，於 `R{NN}` 落檔後可針對所有 `P0` 拆檔、`D2` 死代碼拔除與 `S3` 合併處方反向核對源碼，攔截多型分派誤刪或物理狀態機誤合併。

### 步驟 3：呈遞診斷卡與三大流轉出口裁決 (`Export Outlet Gate` — 強制 End Turn)

對話 Session **嚴禁傾倒長篇報告或原始碼**，強制僅呈遞以下極簡診斷卡並**立即 End Turn 等待開發者選擇流轉出口**（若診斷發現 `P0 = 0` 且 `P1 = 0`，應直接主動推薦 **出口 ③ 維持現狀榮譽結案**）：

```markdown
### 🔍 R{NN} 業務代碼五維度診斷報告已落檔
- **產出文件**：[R{NN}_code_optimization_audit.md](__${project://plans}__/{plan_name}/R{NN}_code_optimization_audit.md)、[P00_discuss.md](__${project://plans}__/{plan_name}/P00_discuss.md)
- **定錨基準**：範圍 `[全專案 / 模組 / 檔案]` ｜ 模式 `[Mode A 收斂期 / Mode B 維護期]` ｜ 軌道 `[主代理內聯 / 序列推進 / 盲眼子代理]`
- **診斷摘要**：P0 共 `[X]` 項、P1 共 `[Y]` 項、P2 共 `[Z]` 項（核心瓶頸：[1~2 行摘要與預計套用之 S1~S6 策略；若 P0=0 且 P1=0 則註明已達最佳內聚度]）
- **推薦流轉出口**：
  1. **出口 ① 立即原地升級實作**：將 `R{NN}` 標記 `Concluded`，原地升級為 `[Fast Track / Full Track / Umbrella]` 執行無損重構
  2. **出口 ② 轉入技術儲備**：將重構藍圖登錄至 `/roadmap`（跨模組）或 `/todo`（局部技術債），標記 `R{NN}` 為 `Concluded`
  3. **出口 ③ 維持現狀結案**：健康度已達最佳內聚度（`P0=0, P1=0`）或暫無須動刀，標記 `R{NN}` 與 `P00` 為 `Concluded` / `Completed` 留存體檢紀錄
- **待確認事項**：請問是否採納此重構處方箋，並選擇何種流轉出口（① / ② / ③）？
```

### 步驟 4：原地升級實作、外科手術無損重構與量化驗證 (`Surgical Execution & Delta Verify`)

當開發者拍板選擇 **「出口 ① 立即原地升級實作」** 時：
1. **無痛升級計畫軌道（嚴禁轉入 `Revision Plan` — `EC-04`）**：
    將 `R{NN}_code_optimization_audit.md` 標頭更新為 `Concluded`，依範圍與規模原地升級計畫：
   - 修改 $\le 100$ 行、0 公開 API 變更、0 跨模組新依賴 $\rightarrow$ 原地建立 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) 走 **Fast Track**。
   - 單一模組深度重構、涉及物理拆檔（`S6`）或 $> 100$ 行 $\rightarrow$ 原地追加 `P01`~`P07` 走 **Full Track**（或獲授權以 [`/auto`](`__#{module://agents-workflow/assets/skills/auto/SKILL.md}__`) 推進）。
   - 全專案跨多模組重構 $\rightarrow$ 建立 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) 升級為 **Umbrella** 主計畫，依步驟 1 選定之 `軌道 3A（主代理逐一推進 sub_n -> sub_n+1）` 或 `軌道 3B（N 路子代理平行實作 + P06 統一驗證）` 推進。
2. **[!] 按需載入重構策略庫與執行無損修改**：
   讀取 [`references/refactoring-playbook.md`](./references/refactoring-playbook.md)，以 `__%{agent_tool.file_edit}__` 執行 `S1~S6` 重構，嚴守 `Mode A / Mode B` 入口規則、四大防過度設計紅線、以及測試替身（`Mock*` / `Dummy*`）與跨模組呼叫端同步更新。
3. **防截斷驗收、回歸驗證與跨代盲審收斂**：
   - **防截斷驗收紀律**：審查多檔案重構變更時，優先使用 `git status --short`、`git diff --stat` 與精準檢索，嚴禁對全模組直接執行未分頁之巨型 `git diff` 導致輸出截斷污染 Context；執行大型測試套件時可搭配管線過濾摘要行。
   - **回歸驗證與 Before/After 量化對照**：遵循 [`testing-sop`](`__#{module://agents-workflow/assets/skills/testing-sop/SKILL.md}__`) 與 `__%{agent_tool.shell_exec}__` 執行靜態合規檢查與既有回歸測試套件（確保 100% Passed 且錯誤語意零退化），並依 `refactoring-playbook.md` §7 於結案文件輸出 **Before / After 結構量化對照表**。
   - **進階可選品管 — 跨代零錨定盲審 (`R02` / `R03` Blind Convergence Audit)**：針對大型重構，可於 `P06` 驗證通過後派發無上下文盲眼子代理（嚴禁讀取 `__${project://plans}__/` 既有文檔、不給引導性方向暗示）產出 `R02_code_optimization_audit.md`，檢驗是否殘留 `S2` 轉發殼層或浮現深層跨檔同構樣板。

`__@{CODE_OPTIMIZER_STANDARDS}__`

---

## 常見踩坑指南 (Gotchas)

- **切勿由 Agent 自行猜測 `Mode A / Mode B`、範圍或擅自派發子代理（`EC-01`）**：步驟 1 若開發者未明確指定範圍、生命週期模式與（單模/多模）代理執行軌道，必須先提問確認後再建立調研計畫。
- **切勿在 `Mode B` 下為「0 外部調用的純內部工具函式」或 `S2` 剝離之私有輔助方法保留 1 行轉發垃圾（`EC-02`）**：`Mode B` 的門面保護僅限於對外公開匯出與跨模組契約；經嚴格查驗確認僅在模組內部使用之輔助函式，以及 `S2` 抽離後之原類別私有方法，必須直接刪除轉發殼並同步更新模組內與 `tests/` 調用點。
- **切勿因檔案行數較多而強拆高內聚狀態機，或為湊處方而違反防過度設計紅線（`EC-03`）**：行數僅作探索參考；若模組已無正交職責混雜（`P0=0, P1=0`），應誠實推薦「出口 ③ 維持現狀結案」。
- **切勿將業務代碼結構重構分流至 `Revision Plan` 或在步驟 3 確認出口前偷改程式碼（`EC-04`）**：`Revision Plan` 僅限非業務邏輯之表層微調；業務代碼重構於步驟 3 獲選出口 ① 後，僅能轉入 `Fast Track`、`Full Track` 或 `Umbrella`。

