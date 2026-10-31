# 業務程式碼品質、五維度診斷與無損重構標準 (Code Quality & Refactoring Standards)

本文件定義業務生產程式碼的品質基準、防過度設計四大紅線、跨語言五維度品質指標（`D1`~`D5`）與六大無損重構法則（`S1`~`S6`）。

---

## 1. [!] 核心原則與防過度設計四大紅線 (Anti-Overengineering Guardrails)

1. **100% 行為等價與錯誤語意保護（Preserve Behavior & Error Semantics）**：
   - 重構或增量修改既有模組時，嚴禁無授權偷渡外部行為變更；不得將原本向上拋出特定異常的契約改為靜默回傳空值（`null` / `None` / `false`），所有邊界條件之輸入輸出行為必須嚴格等價。
2. **禁止教條式套用設計模式（No Pattern Mania）**：
   - 不得將百行內的直觀邏輯或簡單條件分支，硬拆為繁瑣的抽象工廠（Abstract Factory）或策略類別階層；優先採用語言原生的簡潔結構（純函式、衛語句、分派映射表）。
3. **禁止碎紙機式過度拆分與行數湊數（No Nano-Functions / LOC-Driven Fragmentation）**：
   - **函式提取標準（SLAP / DRY）**：提取內部工具函式的唯一標準是「聚合完整業務階段（通常 15~45 行）」或「消除結構性重複」，嚴禁將連貫的單一階段邏輯切碎為十幾個僅 3~5 行或 1 行轉發的奈米函式。
   - **物理拆檔標準（CCP / SRP）**：物理拆檔（`S6`）唯一標準是「分離正交變更軸線」，**檔案或函式行數僅作初步探索參考，絕非拆檔定罪依據**；嚴禁僅因行數較多而強拆共享交易鎖之狀態機或單一領域累加器之線性管線（成熟模組之 `P0` 與 `S6` 允許且應當為 `0` 項）。
4. **自我解釋優先於廢話與工單註解（Self-Documenting over Noise Comments）**：
   - 以精準的階段函式命名取代段落分隔註解（如 `# Step 1: ...`），清理過時註解與廢棄代碼塊。
   - **[!] 零工單與審計編號註解鐵律**：**嚴禁在生產代碼註解或 Docstring / XML 註解中留存任何開發計畫、規格或審計工單編號（如 `FR-XX`、`EC-XX`、`DR-XX`、`[P00:DR-01]`、`D1~D5`、`S1~S6`、`F-01`、`M-05`、`REV-XX`）或「（已移除某某舊邏輯）」之變更歷史噪音**，僅保留解釋「Why（當前架構不變量、設計取捨與防坑原因）」及公開 API 契約之說明。

---

## 2. 跨語言五維度代碼品質指標 (D1 ~ D5 Quality Dimensions)

| 維度代號 | 品質維度名稱 | 核心軟工抽象與日常編碼守門標準 | 對應重構法則 |
| :---: | :--- | :--- | :---: |
| **`D1`** | **職責內聚與抽象層級**<br>*(Cohesion & Abstraction Levels)* | • **單一職責與共同封閉 (SRP / CCP)**：單一檔案/類別不混雜正交變更軸線（如同時塞入資料模型、底層 I/O 解析與高階業務/UI 渲染）。<br>• **單一抽象層級 (SLAP)**：公開入口函式作為高階編排器，不混雜底層正規表達式切割、位元操作或 I/O 緩衝細節。<br>• **有狀態與無狀態分離**：不讀寫實例欄位（`self` / `this`）的純運算邏輯應剝離為無狀態純函式；`partial class` 分部檔不得跨檔散落讀寫數十個未封裝之私有快取欄位。 | `S1`, `S2`, `S5`, `S6` |
| **`D2`** | **調用耦合與拓撲健康度**<br>*(Coupling & Topology Hygiene)* | • **無環依賴原則 (ADP)**：徹底消除模組間雙向或方法內延遲循環匯入，維持嚴格單向 DAG。<br>• **零轉發殼層與零孤兒死代碼**：抽離內部方法後嚴禁在原類別留下 1 行轉發殼；移除經 `callers` + 全文 `search` 雙重查證確認 0 引用（含無 POCO/泛型 `<T>`、多型虛擬分派、`[InternalsVisibleTo]` 或 Source Generator 引用）之死代碼。 | `S2`, `S6` |
| **`D3`** | **控制流與認知複雜度**<br>*(Control Flow & Cognitive Complexity)* | • **縮排深度上限 ($\le 3$ 層)**：以衛語句提早返回（Early Return）消除箭頭型深層巢狀（Arrow Anti-pattern）。<br>• **結構性重複收斂 (DRY)**：跨方法重複出現之「前置檢查 $\to$ 資源獲取 $\to$ 錯誤轉換 $\to$ 清理」同構骨架應提取共用樣板。 | `S1`, `S3`, `S4` |
| **`D4`** | **介面契約與資源生命週期**<br>*(Contracts & Resource Lifecycle)* | • **結構化型別契約**：禁止超過 5~6 個散裝長參數列或以無型別裸字典（`dict` / `Map` / `any`）跨多階段傳遞核心狀態。<br>• **異常透明與確定性資源釋放 (RAII / Scoped)**：嚴禁空白 `except/catch` 吞掉錯誤；檔案控制代碼、暫存目錄、互斥鎖與子進程管道必須置於 `with` / `using` / `defer` / `try...finally` 保護中。 | `S3`, `S5` |
| **`D5`** | **架構邊界與專案慣例**<br>*(Architectural Idioms)* | • **基礎設施抽象遵從**：強制使用專案統一的虛擬路徑/檔案代理層（如 `vfs` / `uri`）、日誌與組態介面。<br>• **常數集中化與零反向耦合**：魔術字面量提取為具名常數；底層核心模組嚴禁反向依賴上層選配業務模組。 | `S5`, `S6` |

---

## 3. 六大結構組織與無損重構法則 (S1 ~ S6 Refactoring Laws)

1. **`S1` 業務階段拆解與主幹管線化 (Stage Decomposition & Pipeline Orchestration)**：
   - 將超過 60~80 行的多階段業務方法拆解為 3~5 個線性領域階段輔助函式（如 `_validate_and_normalize` $\to$ `_prepare_context` $\to$ `_execute_domain_logic` $\to$ `_commit_side_effects`），使頂層公開方法退化為純粹的高階編排器。
2. **`S2` 狀態依賴分析與無狀態邏輯剝離 (State-Dependency Analysis & Stateless Extraction)**：
   - 將完全未讀寫實例狀態（或僅讀取 1~2 個基礎常數設定）的方法剝離為模組級私有純函式或獨立純運算模組。
   - **[!] 零殘留轉發殼層鐵律**：抽離後**嚴禁在原類別保留 `_helper = staticmethod(_helper)` 或 1 行 `return _helper(...)` 轉發殼**，必須同步將同模組與 `tests/` 內的呼叫點更新至正統純函式入口。
3. **`S3` 跨方法同構模式聚合與樣板抽離 (Isomorphic Pattern Aggregation)**：
   - 將重複的控制流與資源管理骨架提取為通用包裹函式或 Scoped Context。
   - **[!] 20% 差異分支不變量保護與 DIM 防遞迴守門**：合併 80% 相似代碼前，必須逐行核對那 **20% 差異分支的業務邊界不變量**（如專屬門檻、快取處置旗標、診斷優先序、局部更新 vs. 全量覆寫）並 100% 無損保留；在支援介面預設實作（C# DIM / Java `default`）的語言中，嚴禁在具體類別方法內寫出 `((IInterface)this).Method(...)` 造成虛擬分派無窮遞迴，必須提取為介面內 `static` 輔助函式共呼。
4. **`S4` 控制流扁平化與表驅動分派 (Guard Clauses & Table-Driven Dispatch)**：
   - 反轉前置條件作頂部衛語句，使主幹邏輯維持在第 1 層縮排；超過 3~4 個對稱分支改用常數分派映射表（Dispatch Map）。
5. **`S5` 資料團塊封裝與唯讀集合保級 (Data Clump Encapsulation & Read-Only Collection Preservation)**：
   - 將跨階段共現的參數群或裸字典封裝為具名結構（`dataclass` / `NamedTuple` / `struct` / `record`）。
   - **[!] 集合回傳型別唯讀化保級守則**：將陣列/串列（`T[]` / `List<T>`）收斂為唯讀介面時，優先採用保留 `.Count` / `len()` 與索引能力的 `IReadOnlyList<T>`、`IReadOnlyCollection<T>` 或 `Sequence[T]` / `tuple[T, ...]`，嚴禁無故降級為純 `IEnumerable<T>` / `Iterator[T]`。
6. **`S6` 正交職責之物理模組拆分與三大免拆守門 (Orthogonal Module Splitting)**：
   - **正交切分與 `partial class` 狀態封裝**：僅在檔案承載多個獨立變更軸線時拆檔；若使用語言原生同型別分檔（如 C# `partial class`），跨分部檔共享超過 5~7 個同生命週期私有欄位時，必須同步搭配 `S5` 封裝為內部狀態 `struct/class`。
   - **[!] 三大免拆守門（嚴禁拆散為多模組）**：① 共享同一把交易/進程鎖與高內聚記憶體狀態表之狀態機；② 針對同一 Context 與 `Report` 累加器依序執行的同質性線性規則管線；③ 具單檔 `__file__` 自指紋校驗或受「資料夾路徑 = Public Namespace」剛性約束（未經 `Mode A` 影響評估不得新建子目錄搬移公開型別）之檔案。
   - **相容性入口處置**：`Mode A（收斂期）` 零容忍刪除舊位置轉發檔並更新全部調用點；`Mode B（維護期）` 僅對外公開契約保留門面重匯出（Facade Re-export），經 `callers + search` 雙重查證 **0 外部跨模組引用之純內部工具函式** 一律直接破壞性收斂，不留相容層。

`__@{CODE_OPTIMIZER_STANDARDS}__`

