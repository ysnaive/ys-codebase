# 技術調研報告：下游專案 GC_VEX_V5 全專案雙代實測自檢與技能優化評估 (R02_gc_vex_v5_report.md)

> 調研主題：基於下游專案 GC_VEX_V5 (C++11/17 韌體 + C# .NET 10 上位機) 8 大子計畫雙代實測與 44 子代理調度之 `/code-optimizer` 優化評估  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1605_code_optimizer_skill (sub_01_empirical_optimization)  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  - **測試專案背景 (`GC_VEX_V5`)**：跨語言異質雙端架構（C++11/17 VEX V5 嵌入式韌體 + C# .NET 10 ImGui 上位機，含雙層自動代碼生成與二進位通訊協定）。
  - **執行規模**：於 Umbrella 主計畫（`2026_10_31_1108_project_wide_code_optimization`）轄下建立 8 個模組子計畫（`sub_01` ~ `sub_08`），歷經 **Gen 1（`R01` 調研 + 反向查驗 + 重構）** $\to$ **Gen 2（無上下文盲測 `R02` + 反向查驗 + 深度收斂重構）**，共派發 **44 個子代理**。
  - **最終驗證狀態**：C++ 韌體 `build/gcvex.elf` `0 Errors / 0 Warnings`；C# 測試套件 `153 Passed, 0 Failed`；`plan verify` `PASSED`。
  - **對話軌跡遙測基準 (`/SessionAudit`)**：
    - 診斷標的：`f1a3e04f-2f15-4f74-a993-66349c0356d5` (`Tier 1+2`, 遙測事件 `50` 筆)
    - 對話規模：歷時 `2h 56m 35s` | 總步數 `665` (`User: 16`, `Model: 236`, `Thinking: 0`, `Truncated: 124`, `Errors: 12`)
    - Token 消耗結構：Full `~449,579` / Compact `~250,759` Tokens (`Native API Total: 26,419,741` — `In: 1,874,575`, `Out: 136,043`, `CacheRead: 24,409,123`)
    - Token 有效率評估：有效 `~422,603` Tokens (**`94.0%`**) / 摩擦浪費 `~26,976` Tokens (`6.0%`：重複讀取 `16,373`、失敗重試 `3,741`、返工修改 `6,677`、盲讀探索 `185`)
    - 工具與檔案操作：總計 `349` 次 (`Read: 124` 次 / `80` 檔, `Edit: 62` 次 / `37` 檔, `Subagent: 72` 次 / 派發 `44` 個子代理)
    - 異常信號分佈：共 `31` 項 (`TOOL_MISS_AND_RETRY: 13`, `CONTEXT_WASTE: 13`, `MULTI_EDIT_CHURN: 3`, `GATE_BOUNCE: 2`)
- **調研目標**：
  - 檢驗母倉 6 大共性坑點於 C++/C# 靜態強型別雙端專案中的命中率與原地收斂效果。
  - 提煉 `GC_VEX_V5` 在跨語言靜態型別、多型虛擬分派、`Mode A` 跨子計畫平行交接、子代理直接落檔協議、`partial class` 同型別正交分檔與「反向查驗守門 (Reverse Fact-Check Gate)」上的 **5 大核心增量洞察**。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

針對 `GC_VEX_V5` 實測挖掘出的 5 大增量維度，評估各候選改進方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **增量 1：靜態型別與多型死代碼判定 (`D2`)**<br/>**方案 1A（僅靠 `knowledge-db callers`）** | 維持現狀，當 `callers == 0` 即判定為死代碼並於 `Mode A` 拔除 | 無額外檢索步驟 | 在 C++/C# 中誤刪 POCO 序列化類別 (`StateMachineLayoutAsset`)、C++ 基底指標虛擬分派 (`OdomLocator::update`) 與模板轉發方法 | ★☆☆☆☆ |
| **增量 1：靜態型別與多型死代碼判定 (`D2`)**<br/>**方案 1B（推薦：雙重查證鐵律 `callers + search` + 多型/反射守門）** | 對 `class/struct/enum/interface` 或 `virtual/override` 方法，當 `callers == 0` 時強制追加 `knowledge-db search "<SymbolName>" --json` 並檢查基底 `virtual` 契約與 `[Attribute]` / 泛型 `<T>` 引用 | 100% 攔截 C# POCO 欄位/泛型反序列化與 C++ 多型/模板誤刪 | 每個疑似殭屍類別多 1 次極速全文/符號檢索 | ★★★★★ |
| **增量 2：Umbrella 平行子代理跨模組 `Mode A` 拔除**<br/>**方案 2A（推薦：兩階段交接協議 `[Cross-Module Mode A Handoff]` + 唯讀集合介面守則）** | 平行子代理僅直接刪除「100% 本子計畫內部呼叫」之舊入口；若涉及跨子計畫或 `tests/` 呼叫，子代理於 `P05` 與完成回條附帶標準化 `[Cross-Module Mode A Handoff]` 交接表交由主代理匯流批次更新；且集合屬性收斂優先用 `IReadOnlyCollection<T>`/`IReadOnlyList<T>` 而非降級為 `IEnumerable<T>` | 消除平行子代理越界改檔衝突，同時防止 `Entities.Count` 等跨模組語法退件 | 主代理於匯流階段需依交接表執行一次跨模組更新 | ★★★★★ |
| **增量 3：Umbrella 子代理回傳契約**<br/>**方案 3A（推薦：雙模委派——Single-Plan 回傳 `<=400` Tokens vs. Umbrella 子代理直接落檔 `R{NN}` + `<50` Tokens 收據）** | 在 `exploration-and-delegation.md` 區分模式 I（局部探索回傳摘要）與模式 II（Umbrella 子計畫授權子代理直接寫入 `sub_XX/R{NN}_*.md` 並僅回傳單行 `P0/P1/P2` 計數收據） | 零資訊壓縮耗損，且大幅保護主代理 Context Window（本案 44 子代理下主視窗有效率高達 `94.0%`） | 無副作用 | ★★★★★ |
| **增量 4：`S6` 大型類別拆解之語言原生適配**<br/>**方案 4A（推薦：同型別正交物理分檔 `Same-Type Orthogonal File Partitioning`）** | 於 `refactoring-playbook.md §6 (S6)` 增列：當大型類別承載多個正交變更軸（如 `Model` vs. `Inspector UI` vs. `Codec/Codegen`）但共享同一實例私有狀態時，優先採用語言原生同型別分檔（C# `partial class`、C++ 單標頭多 `.cpp`、Rust 多子模組 `impl`） | 零執行期配置開銷、零公開 API 污染、零私有狀態外洩，徹底避免過度設計 Wrapper 類別 | 僅適用於支援同型別分檔之語言（Python 則維持模組級純函式下沉） | ★★★★★ |
| **增量 5：高複雜度專案之雙層品管掛鉤**<br/>**方案 5A（推薦：導入可選之 `Reverse Fact-Check Gate` 與 `Gen 2 Blind Convergence`）** | 於 `SKILL.md` 提供進階品管掛鉤：① 實作前對 `R{NN}` 的 `P0`/`D2`/`S3` 進行反向查驗（本案攔截 9 處物理狀態機誤判）；② 巨型模組首輪拆檔降噪後啟動無歷史包袱之第二輪盲審，收割深層跨檔同構樣板 | 動刀前消滅幻覺誤判，動刀後收斂深層結構重複（如 C++ 10 檔 `forEachInstance` 模板化） | 增加唯讀驗證子代理調度（可按專案規模選配） | ★★★★★ |

### 3.1 母倉 6 大共性坑點於 `GC_VEX_V5` 之實測命中率與收斂對照

| 坑點編號與名稱 | 實測命中頻率 | 具體發生現場與原地收斂處置 |
| :--- | :---: | :--- |
| **1. 【S2 半調子轉發殼層 / 重複純函式殘留】** | **低頻（命中 2 處）** | 1. **C++ 1 行轉發殼**：Gen 1 `sub_01` 將 `ProviderEntity::findEntityIdByDataPtr` 抽離至 `Registry::findEntityIdByDataPtr` 後，於 `ProviderEntity.h` 殘留 1 行 `return Registry::findEntityIdByDataPtr(ptr);`，已於 Gen 2 `R02` 捕獲並徹底刪除。<br/>2. **C# 跨類別重複純函式**：`DashEntity.EscapeCppStringLiteral` (`DashEntity.cs:131`) 與 `EntityDefinitionManager.EscapeCppStringLiteral` (`EntityDefinitionManager.Codegen.cs:47`) 重複定義完全相同的無狀態字串跳脫邏輯；已於自檢階段拔除 `DashEntity` 內重複定義，統一收斂呼叫 `EntityDefinitionManager.EscapeCppStringLiteral`。 |
| **2. 【S6 行數教條與過度拆分 (Over-Splitting)】** | **極低頻（C++ 0 處 / C# 1 處輕微）** | - C++ 端（`sub_01`~`sub_03`）所有 `R01`/`R02` 均明確判定 `P0 = 0`（不拆檔）。<br/>- C# 端大量運用語言原生 **`partial class` 按正交職責軸拆檔**（如 `Model` vs. `Inspector UI` vs. `Codec/Codegen`），編譯期仍為單一型別，未破壞鎖定或封裝。<br/>- 唯一輕微命中為 `sub_05` 將 387 行的 `ConcreteCommands.cs` 拆為 `LifecycleCommands.cs` (214 行) 與 `EntityCommands.cs` (304 行)，因確屬「連線生命週期」與「實體 CRUD」兩條獨立變更軸且無共享狀態，保留現狀。 |
| **3. 【S3 合併遺失 20% 邊界不變量】** | **低頻（命中 2 處，均於驗收攔截）** | 1. **`sub_06` 診斷順序偏移**：`OdomLocatorCheckRule` 合併檢查時，將新增的 `Warning`（座標未設定 `0,0`）排在 `Error`（重複 Encoder 埠號）之前，改變了 `Diagnostics[0]` 的順序假設，已更新測試斷言明確檢驗 `Severity == EntityDiagnosticSeverity.Error`。<br/>2. **`sub_08` 預設值覆寫**：`FieldMapWindow.SaveCurrentConfigToDB` 在 Gen 1 抽離存檔邏輯時直接 `new FieldMapConfigAsset`，導致未顯示於該面板的 `PickerWidth`/`PickerHeight` 被覆寫回預設值 `144f`；已於 Gen 2 `R02` (`F-04`) 捕獲並修復為先讀取既有設定再局部更新。 |
| **4. 【簽名變更與測試替身 / 跨模組呼叫失步】** | **高頻（命中 5 處，集中於跨子計畫 `Mode A`）** | `sub_04` 於 `Mode A` 拔除 `StateMachineLayoutAsset`、`DashboardDB.RenameAsset`、`Registry.GetEntity`，並將 `Registry.GetAllEntities()` (`DashEntity[]`) 改為 `Registry.Entities` (`IEnumerable<DashEntity>`)，導致平行執行的 `sub_05`/`sub_07` 與 `Dashboard.Tests/Program.cs` 發生跨模組簽名失步。已由主代理統一收斂為 `IReadOnlyCollection<DashEntity>` 並同步更新所有跨模組與測試呼叫端。 |
| **5. 【審計編號註解污染】** | **中頻（命中 10 處）** | 生產代碼註解殘留了 `(S5-1)`、`(S4-2)`、`(D4)`、`(D5)` 等工單標籤。已於自檢階段全數清除：<br/>- `include/dashboard/ProtocolUtils.h`（移除 3 處 `(S5-1)`）<br/>- `src/dashboard/Registry.cpp`（移除 1 處 `(S4-2)`）<br/>- `EntityDefinitionManager.cs`、`PersistenceHandler.cs`、`SchemaLazyCache.cs`、`Registry.cs`、`DashboardDB.Workspace.cs`（移除 6 處 `(D4)`/`(D5)`）。 |
| **6. 【驗收工具摩擦 (`output.txt` 截斷重讀)】** | **中頻（命中 3 次，Steps 619, 621, 623）** | 執行 `dotnet run --project dashboard/Dashboard.Tests/...` 時，因 153 項測試逐行 PASS 加上編譯警告超出預覽上限，觸發 3 次讀取 `output.txt`。自檢階段改用源頭過濾 `dotnet run ... --nologo \| Select-String -Pattern "FAIL\|Summary\|Passed"`，單行輸出 `Summary: 153 Passed, 0 Failed`，0 截斷。 |

---

### 3.2 五大跨語言與大規模調度增量發現詳解 (Deep-Dive Incremental Insights)

1. **`[INC-01]` 靜態強型別與多型語言中，`knowledge-db callers` 的結構性盲區（POCO 型別宣告、C++ 虛擬分派與模板轉發）**：
   - **實證現場**：
     - **C# POCO 序列化型別誤判**：`sub_04` Gen 2 對 `StateMachineLayoutAsset` 執行 `knowledge-db callers` 得 `0`（因 AST Call Graph 僅索引「函式呼叫」，不索引欄位宣告 `private StateMachineLayoutAsset _layoutAsset;` 與泛型呼叫 `LoadAsset<StateMachineLayoutAsset>()`），誤將其列為 `Z-01` 物理刪除，引發 `CS0246` 編譯錯誤（`Step 574`）。
     - **C++ 多型虛擬分派與模板轉發誤判**：`OdomLocator::update()` 係透過基底指標 `LocatorProvider* m_locator` 進行虛擬呼叫 (`m_locator->update()`)；`ProviderEntity::registerProvider` 係由 `ProviderEntity<T>::registerEntity` 模板方法內部轉發，直接 `callers` 查詢皆易產生假性 0 調用。
   - **處方定錨**：在 `exploration-and-delegation.md` 與 `diagnostic-matrix.md (D2)` 強制規定：凡判定 `class/struct/enum/interface` 或 `virtual/override/template` 成員為 0 調用死代碼前，**必須聯合執行 `knowledge-db callers` + `knowledge-db search "<SymbolName>" --json`**，確認無型別引用、泛型參數 `<T>`、序列化/反射 Attribute 或基底多型介面定義。

2. **`[INC-02]` Umbrella 平行子代理執行 `Mode A` 時之「跨模組公開入口拔除競態 (Cross-Module Mode A Handoff Race)」與唯讀集合型別退化**：
   - **實證現場**：8 個子計畫平行隔離執行時，`sub_04` 拔除了跨子計畫被呼叫的 `DashboardDB.RenameAsset` / `Registry.GetEntity`，並將 `DashEntity[]` 改為 `IEnumerable<DashEntity>`，導致平行推進的 `sub_05`/`sub_07` 呼叫 `.Entities.Count` 時觸發 `CS0428`（`Step 580`）。
   - **處方定錨**：
     - 建立 **「跨模組 `Mode A` 兩階段交接表 (`[Cross-Module Mode A Handoff]`)」**：平行子代理受限於自身目錄寫入邊界時，對涉及外部子計畫或外部測試的符號變更，必須在完成回條輸出標準化映射表（`舊符號 -> 新正統符號 + 外部調用座標`），由主代理在匯流階段統一收割。
     - 建立 **「集合型別無損唯讀化守則」**：將 `T[]` 或 `List<T>` 封裝為唯讀屬性時，應採用保留 `.Count` / 索引能力的 `IReadOnlyList<T>` / `IReadOnlyCollection<T>`（或 Python `Sequence[T]` / ` tuple[T, ...]`），禁止降級為僅支援單次迭代且無 `.Count` / `len()` 的 `IEnumerable<T>` / `Iterator[T]`。

3. **`[INC-03]` Umbrella 模式之「子代理直接落檔 `R{NN}` + `<50` Tokens 極簡收據」委派模式**：
   - **實證現場**：在 8 個子計畫、150+ 個檔案的規模下，授權子代理直接寫入 `sub_XX/R01_code_optimization_audit.md` 並僅回傳單行收據（`sub_XX R01 已完成 | P0: X, P1: Y, P2: Z`），不僅保留 100% 完整行號與處方細節，更讓主代理在派發 44 個子代理的高負載下達到 **`94.0%` 的極高 Token 有效率**。

4. **`[INC-04]` `S6` 語言原生「同型別正交物理分檔 (`partial class` / 單標頭多 `.cpp` / 多子模組 `impl`)」**：
   - **實證現場**：C# 上位機的巨型類別（`DashboardDB` 1,983L、`OdomLocatorEntity` 1,563L、`StateMachineGraphView` 1,039L）繼承自 UI/Entity 基類並共享私有狀態。透過 C# `partial class` 按正交職責軸拆分為 `.cs`（核心模型）、`.Inspector.cs`（ImGui 繪製）、`.Codec.cs` / `.Codegen.cs`（編解碼與代碼生成），在 **0 執行期開銷、0 公開 API 污染、0 狀態傳遞 Wrapper** 下完美化解千行巨石檔。

5. **`[INC-05]` 「反向查驗守門 (`Reverse Fact-Check Gate`)」與「第二代無上下文盲測 (`Gen 2 Blind Convergence`)」雙層品管閉環**：
   - **實證現場**：
     - **反向查驗**：在動刀實作前派發驗證子代理拿 `R01`/`R02` 處方反查源碼，成功攔截 9 處高風險誤判（如 `DriveToPose::on_enter` 與 `update` 表面相似，但 `update` 內含專屬 50ms 穩定計時器狀態機，強行 `S3` 合併將破壞機器人定位自控物理行為）。
     - **Gen 2 盲測深層收割**：Gen 1 完成表層降噪與 `partial class` 拆檔後，Gen 2 盲測一眼看穿了原本被千行代碼掩蓋的跨檔案同構模式（如將 10 個 C++ 實體重複的 256-slot 掃描迴圈收斂為 `EntityDetail::forEachInstance<TYPE_ID, T>` 模板；將 C# 12 處 JSON I/O try-catch 收斂為 `TryReadJsonFile<T>` / `TryWriteJsonFileAtomic<T>`）。

---

## 3. 結論 (Conclusion)

- **推薦落地策略**：
  1. **納入 `exploration-and-delegation.md`**：
     - 增設「模式 I（Single-Plan 切片回傳 `<=400` Tokens）vs. 模式 II（Umbrella 子計畫授權子代理直接落檔 `R{NN}` + `<50` Tokens 收據）」雙軌委派契約。
     - 增設「靜態強型別與多型語言 `D2` 死代碼雙重查證鐵律（`callers` + `search` 聯合查驗 POCO 型別、泛型 `<T>`、基底 `virtual` 與反射 Attribute）」。
  2. **納入 `refactoring-playbook.md`**：
     - 於 `§6 (S6)` 新增 **「同型別正交物理分檔 (Same-Type Orthogonal File Partitioning：C# `partial class` / C++ 多 `.cpp` / Rust 子模組 `impl`)」** 作為共享私有生命週期狀態之大型類別的首選無損拆解處方。
     - 於 `§5 (S5)` / `§6 (S6)` 新增「集合回傳型別唯讀化保級守則（優先 `IReadOnlyCollection`/`Sequence`，禁降級為無長度屬性之純產生器/迭代器）」與「Umbrella 平行子代理 `[Cross-Module Mode A Handoff]` 兩階段交接表」。
  3. **納入 `SKILL.md`**：
     - 新增針對大型或高風險專案的可選進階品管掛鉤：**「反向查驗守門 (Reverse Fact-Check Gate)」** 與 **「多代零錨定盲審收斂 (`R{NN}` Blind Convergence)」**。
- **後續行動與銜接**：
  - `R02_gc_vex_v5_report.md` 已完成結構化落檔；等待開發者提供第二個下游專案之實測報告（將落檔為 `R03`），隨後立即展開三方（母倉 `R01` + 下游 `R02` + 下游 `R03`）交叉會診！

