# 六大通用軟工重構策略庫與手術指南 (Refactoring Playbook)

本指南定義 [`/code-optimizer`](../SKILL.md) 在開發者於步驟 3 拍板選擇「出口 ① 立即升級實作」後，於步驟 4 基於中央標準 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`) 執行的六把跨語言結構重塑手術刀（`S1`~`S6`），強調**類別與模組的業務邏輯聚合**與**100% 行為無損（Behavior-Preserving）**。

## 目錄 (Contents)

- [1. S1：業務階段拆解與主幹管線化 (Stage Decomposition & Pipeline Orchestration)](#1-s1業務階段拆解與主幹管線化-stage-decomposition--pipeline-orchestration)
- [2. S2：狀態依賴分析與無狀態邏輯剝離 (State-Dependency Analysis & Stateless Extraction)](#2-s2狀態依賴分析與無狀態邏輯剝離-state-dependency-analysis--stateless-extraction)
- [3. S3：跨方法同構模式聚合與樣板抽離 (Isomorphic Pattern Aggregation)](#3-s3跨方法同構模式聚合與樣板抽離-isomorphic-pattern-aggregation)
- [4. S4：控制流扁平化與表驅動分派 (Guard Clauses & Table-Driven Dispatch)](#4-s4控制流扁平化與表驅動分派-guard-clauses--table-driven-dispatch)
- [5. S5：資料團塊封裝與結構化契約 (Data Clump Encapsulation & Value Objects)](#5-s5資料團塊封裝與結構化契約-data-clump-encapsulation--value-objects)
- [6. S6：正交職責之物理模組拆分與 Mode A/B 入口處置 (Orthogonal Module Splitting)](#6-s6正交職責之物理模組拆分與-mode-ab-入口處置-orthogonal-module-splitting)
- [7. 步驟 4：Before / After 結構量化對照表規範](#7-步驟-4before--after-結構量化對照表規範)

---

## 1. S1：業務階段拆解與主幹管線化 (Stage Decomposition & Pipeline Orchestration)

- **適用病灶**：`D1`（公開方法混雜宏觀業務流程與底層細節）、`D3`（超過 60~80 行之長程序）。
- **核心軟工原理**：落實**單一抽象層級原則（Single Level of Abstraction Principle, SLAP）**。一個複雜業務方法應拆解為 3~5 個線性且語意明確的領域階段（例如：`輸入校驗與正規化` $\to$ `前置上下文準備` $\to$ `核心領域計算` $\to$ `副作用提交與持久化`）。
- **外科手術動作**：
  1. 識別長方法內的自然階段邊界（通常表現為段落註解 `# Step 1...` 或局部變數群的生命週期切換點）。
  2. 將各階段的底層實作提取為職責單一、具名清晰的**內部階段輔助函式（Internal Stage Helpers）**，直接以函式名取代原先的段落分隔註解。
  3. 使頂層公開方法退化為純粹的**高階編排器（Orchestrator）**，主幹僅保留高階步驟調用與清晰的資料流傳遞，閱讀者無須跳入底層細節即可一眼掌握完整業務全貌。
- **防呆邊界**：嚴禁違反紅線 ②「碎紙機式過度拆分」——每個提取出的階段函式必須代表一個**完整的業務子階段**（通常 15~45 行），禁止將 3~5 行的單一迴圈或簡單條件判斷硬拆成無獨立語意的奈米函式。

---

## 2. S2：狀態依賴分析與無狀態邏輯剝離 (State-Dependency Analysis & Stateless Extraction)

- **適用病灶**：`D1`（肥大類別 God Class）、`D2`（類別內部狀態耦合面積過大）。
- **核心軟工原理**：分離**「有狀態的實體生命週期管理（Stateful Entity Lifecycle）」**與**「無狀態的純資料運算（Stateless Pure Computation）」**。
- **外科手術動作**：
  1. 逐一盤點類別內所有方法對實例欄位（Instance Fields / `self.*` / `this.*`）的實際讀寫情況：
     - **完全未讀寫實例狀態**（僅依賴輸入參數進行解析、格式化、校驗、雜湊或結構轉換）：一律從類別中剝離，下沉為**模組私有純函式（Module-Private Pure Functions）**或獨立的純運算工具模組。
     - **僅讀取 1~2 個基礎常數設定欄位**：改為將該設定值作為顯式參數傳入純函式，解除方法對整個類別實例的隱式依賴。
  2. 讓原類別僅保留真正需要維護與變異實例狀態（如連線池、快取字典、生命周期鎖）的核心方法，大幅降低類別行數與測試建構成本。
- **[!] S2 零殘留轉發殼層與測試調用點同步鐵律 (Zero Pass-Through Shell Mandate)**：
  - 將私有輔助方法（如 `_helper` 或 `private static` 方法）抽離為模組級純函式或下沉至輔助模組後，**嚴禁在原類別上保留 `_helper = staticmethod(_helper)` 或僅含 `return _helper(...)` 的 1 行無意義轉發方法**（此種「半調子抽離」不僅未縮減類別認知表面積，反而製造雙重命名空間噪音）。
  - 必須同步更新同檔案/同模組內的所有呼叫點，直接呼叫抽離後的純函式；若 `tests/` 中的單元測試曾直接呼叫 `instance._helper()` 或 `ClassName._helper()`，在 `Mode A`（以及 `Mode B` 下 0 外部跨模組引用之私有方法）必須**同步將測試更新為匯入並測試該純函式或公開 API**。

---

## 3. S3：跨方法同構模式聚合與樣板抽離 (Isomorphic Pattern Aggregation)

- **適用病灶**：`D3`（散落於多個方法中的結構性重複）、`D4`（重複的資源取得/釋放與異常包裝樣板）。
- **核心軟工原理**：消除結構性重複（Structural Duplication）並集中橫切關注點（Cross-Cutting Concerns）。
- **外科手術動作**：
  1. 當同一類別或模組內的多個方法出現高度同構的「前置鎖檢查 / 狀態驗證 $\to$ 核心差異操作 $\to$ 例外轉換與資源清理 / 日誌記錄」骨架時，提取單一內部通用包裹函式或上下文管理器（Internal Template Helper / Scoped Context）。
  2. 將各方法的唯一差異點透過參數或可調用委派（Callable / Callback）注入，確保資源釋放與錯誤處理契約在單點維護。
- **[!] S3 防退化雙重安全守門 (20% Divergence Audit & DIM Recursion Guard)**：
  1. **20% 差異分支不變量逐行核對（禁止取交集抹平邊界）**：當兩段程式碼有 80% 相似時，**那不相似的 20% 往往是關鍵業務邊界守門**（例如：特定路徑專屬的覆蓋率門檻 `min_cov`、零引用快取節點的 `disposeIfRejected` 差異、自控迴圈的 50ms 穩定計時器、或局部更新 vs. 全量覆寫）。合併前必須逐行比對差異處，透過顯式參數或策略回呼 **100% 無損保留所有分支特有的邊界條件與診斷優先順序**；移除過時相容分支（如 `hasattr`）時，必須同步檢查並更新 `tests/` 內的 `Dummy*` / `Mock*` 測試替身。
  2. **介面預設方法 (C# DIM / Java `default` / Rust `trait`) 去重防無窮遞迴**：在支援介面預設實作的語言中，若具體類別欲保留公開方法簽名並複用介面預設邏輯，**絕對禁止在具體類別方法內寫出 `((IInterface)this).Method(...)`**（在 C# / Java 的 `callvirt` 虛擬分派下，轉型為介面仍會派發回具體類別自身，導致編譯期 0 警告、執行期立即 `StackOverflowException` 無窮遞迴崩潰）！必須將預設邏輯提取為介面內的 `static` 輔助函式（如 `IInterface.DefaultMethod(this, ...)`），再由介面預設方法與具體類別共同呼叫。

---

## 4. S4：控制流扁平化與表驅動分派 (Guard Clauses & Table-Driven Dispatch)

- **適用病灶**：`D3`（超過 3 層之箭頭型深層巢狀 Arrow Anti-pattern、冗長對稱之 `if-elif-else` / `switch` 分支鏈）。
- **核心軟工原理**：以衛語句提早返回（Early Return / Guard Clauses）將異常與邊界條件在入口處消化，以宣告式資料結構取代重複條件分支。
- **外科手術動作**：
  1. **反轉條件作衛語句**：將空值檢查、權限攔截、前置不變量校驗全部移至函式頂部立即返回或拋出異常，使正常主幹邏輯維持在**第 1 層縮排**。
  2. **表驅動分派（Table-Driven Dispatch）**：針對超過 3~4 個且結構對稱的命令/類型分派分支，將各分支處理邏輯提取為具名內部函式，並收斂為常數或模組級**分派映射表（Dispatch Map / Handler Registry）**。

---

## 5. S5：資料團塊封裝與結構化契約 (Data Clump Encapsulation & Value Objects)

- **適用病灶**：`D4`（超過 5~6 個參數之長參數列、跨階段傳遞無結構裸字典）、`D5`（散落魔術字面量）。
- **核心軟工原理**：以具備明確欄位與靜態型別的資料結構（Value Object / DTO / Typed Record / Dataclass / Struct）取代鬆散資料團塊。
- **外科手術動作**：
  1. 將總是一起出現、跨多個內部階段函式傳遞的參數群，或原本塞在無型別 `dict` 中跨階段讀寫的中介狀態，封裝為輕量級結構化資料型別（如 `dataclass`、`NamedTuple`、`struct` 或 `interface`）。
  2. 將散落於控制流中的魔術字串、狀態碼、超時閾值與正規表達式提取至檔案或模組頂層具名常數。
  3. **集合回傳型別唯讀化保級守則**：當將公開或內部屬性從可變陣列/串列（如 `T[]`、`List<T>`）收斂為唯讀介面時，**優先採用保留 `.Count` / `len()` 與索引能力的 `IReadOnlyList<T>`、`IReadOnlyCollection<T>` 或 `Sequence[T]` / `tuple[T, ...]`**，嚴禁無故降級為僅支援單次走訪且缺乏長度屬性的純 `IEnumerable<T>` / `Iterator[T]`，以免破壞呼叫端語法或效能。

---

## 6. S6：正交職責之物理模組拆分與 Mode A/B 入口處置 (Orthogonal Module Splitting)

- **適用病灶**：`D1`（經 `S1~S5` 收斂後仍承載多個**正交變更軸線**之巨型檔案/類別）、`D2`（模組間循環依賴）。
- **核心軟工原理**：共同封閉原則（Common Closure Principle, CCP）、行為局部性（Locality of Behavior）與無環依賴拓撲（DAG）。
- **外科手術動作**：
  1. **按正交變更軸線切分物理檔案（職責優先，非行數優先）**：
     - 將單一檔案中「因不同業務原因而修改」的正交職責拆分為獨立模組，例如拆分為 `models / schema`（資料結構與靜態規格層）、`parser / healer`（無狀態底層解析或自癒運算層）與 `service / verifier`（高階業務編排層），確保依賴方向嚴格單向由上往下，徹底消除雙向/延遲循環匯入。
  2. **語言原生「同型別正交分檔 (`partial class` / 多 `.cpp` / 子模組 `impl`)」與 `S5` 狀態封裝連動**：
     - 在支援同型別分檔的語言（如 C# `partial class`、C++ 單一標頭配多個職責 `.cpp`、Rust 多子模組 `impl` 塊）中，若大型類別必須繼承框架基類並共享實例生命週期，可優先按正交軸線（如 `Core Model` vs. `Inspector/UI Rendering` vs. `Binary Codec / Codegen`）拆分為多個同型別分部檔（零執行期配置開銷、零公開 API 污染）。
     - **[!] 防偽拆檔守門**：將類別拆為多個 `partial class` 檔案**不等於消除了內部狀態耦合**！若跨分部檔直接交叉讀寫超過 5~7 個同生命週期之私有欄位（如量測快取 `m_Cached*`、拖曳狀態機、編輯歷史），**必須同步搭配 `S5` 將該組私有欄位封裝為內聚的內部狀態 struct/class**，嚴禁僅把方法搬到新檔案卻留下散落全類別的數十個私有欄位。
  3. **[!] S6 反碎片化與三大免拆守門 (Anti-Fragmentation Gate — 以下場景嚴禁拆散為多模組)**：
     - **① 共享交易鎖與記憶體狀態機**：若多個方法必須在同一個鎖（如 `InterProcessLock`、`threading.Lock`）或同一組高內聚記憶體狀態表（如 Daemon Supervisor 的 `workers` / `pending_requests`）下協同運作，物理拆成多模組會導致狀態外洩或雙向傳參耦合，**強制保留於同一檔案**（僅以 `# === Phase N ===` 與 `S1/S2` 階段純函式組織）。
     - **② 單一領域累加器之線性檢查管線**：若檔案內多個私有方法皆為針對同一 Context 與 `Report` 累加器依序執行的同質性規則步驟（如靜態合規檢查器 `Checker`），拆成多個 `rules_*.py` 僅增加跨檔跳轉成本，**禁止為壓低行數而拆分**。
     - **③ 單檔自指紋校驗或目錄即 Namespace 契約**：若檔案具有對自身 `__file__` 計算 Hash 指紋之熱更新契約，**嚴禁拆檔**；若專案採用「資料夾路徑與 Public Namespace 1:1 剛性鏡像規範」（如 C# 專案），新建子資料夾搬移公開型別等同於**破壞性修改 Public Namespace**，未經 `Mode A` 全專案影響評估嚴禁新建子目錄搬移公開型別。
  4. **嚴格依步驟 1 開發者拍板之 `Mode A / Mode B` 處理匯出契約**：
     - **若為 `Mode A（收斂期）`**：直接將所有內部、跨模組與測試調用方的匯入路徑更新至拆分後的新正統入口，**嚴禁在舊位置留下空殼轉發檔或相容別名**。
     - **若為 `Mode B（維護期）`**：
       - 對於**對外公開入口與插件契約**：於原模組入口（如 `__init__.py`、主門面檔或公開標頭）透過**門面重匯出（Facade Re-export）**保留原公開符號與簽名 100% 相容；
       - 對於**經 `callers + search` 嚴格查驗確認 0 外部跨模組引用之純內部工具函式**：直接移入新內部子模組並同步更新模組內調用點，**不為純內部工具函式在門面保留多餘重匯出**。

---

## 7. 步驟 4：Before / After 結構量化對照表規範

完成步驟 4 無損重構並通過所有靜態檢查與回歸測試後，必須於結案文件（`P07_walkthrough.md` 或 `fast_track_plan.md`）附上客觀的 **Before / After 結構量化對照表**：

| 量化指標 (Metric) | 重構前 (Before) | 重構後 (After) | 變化幅度 (Delta) | 結構改善說明 |
| :--- | :---: | :---: | :---: | :--- |
| **目標檔案總行數 (LOC)** | `[X 行]` | `[Y 行]` | `[±Z%]` | 說明拆檔、重複樣板消除或死代碼清理成果 |
| **最大單一函式行數 (Max Function LOC)** | `[X 行]` | `[Y 行]` | `[-Z%]` | 說明 `S1` 業務階段拆解後主幹管線化成果 |
| **最大控制流縮排深度 (Max Nesting Depth)** | `[X 層]` | `[Y 層]` | `[-Z 層]` | 說明 `S4` 衛語句與表驅動分派扁平化成果 |
| **剝離之無狀態純函式 / 清除之死代碼數** | `0` | `[N 個]` | `+N` | 說明 `S2` 狀態剝離與 `Mode A/B` 內部清理成果 |
| **自動化回歸測試通過率 (Regression Suite)** | `[N/N Passed]` | `[N/N Passed]` | `100% 無損` | 驗證行為、回傳值與異常語意 100% 等價 |

