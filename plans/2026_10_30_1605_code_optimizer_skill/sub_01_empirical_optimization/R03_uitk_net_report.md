# 技術調研報告：下游專案 uitk.net 三波實測收斂自檢與技能優化評估 (R03_uitk_net_report.md)

> 調研主題：基於下游專案 uitk.net (C# 12 / .NET 8 0-GC UI 框架 + Roslyn Source Generator) 7 大子計畫三波盲測收斂之 `/code-optimizer` 優化評估  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1605_code_optimizer_skill (sub_01_empirical_optimization)  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  - **測試專案背景 (`uitk.net`)**：C# 12 / .NET 8 高效能 0-GC UI 框架（含 Skia 渲染後端、Flexbox 排版引擎、L1/L2 資產快取池與 Roslyn Source Generator `[Module]` 自動生成靜態門面）。
  - **執行規模**：於 Umbrella 主計畫（`2026_10_31_1029_codebase_optimization_audit`）轄下建立 7 個子計畫（`sub_01` ~ `sub_07`），歷經 **三波盲測 AB 收斂（`R01` $\to$ 第 1 波重構 $\to$ `R02` $\to$ 第 2 波重構 $\to$ `R03` $\to$ 第 3 波去蕪存菁與原地收斂）**，共產出 21 份審計報告。
  - **最終驗證狀態**：`dotnet build` `0 Warning / 0 Error`；全套單元與合約測試 `348 / 348 Passed`；`src/` 達成 `0` 審計/工單編號殘留。
  - **對話軌跡遙測基準 (`/SessionAudit`)**：
    - 診斷範圍：`Tier 1+2 (Transcript + Core Telemetry)` / 遙測事件：`50` 筆
    - 時間與步數：耗時 `3h 6m 38s` / 總步數 `1,263` 步 (`User: 14`, `Model: 334`, `Thinking: 0`, `Truncated: 234`, `Error: 34`)
    - Token 消耗結構：Full `~1,005,320` / Compact `~540,252` Tokens (`Native API Total: 41,340,606` — `In: 2,941,632`, `Out: 238,546`, `CacheRead: 38,160,428`)
    - Token 效率與浪費 (ROI)：有效產出 `~850,443` Tokens (**`84.6%`**) / 摩擦浪費 `~154,877` Tokens (`15.4%`：重複讀取 `25,900`、失敗重試 `5,155`、同檔反覆返工 `11,985`、未檢索盲讀 `111,837`)
    - 工具與檔案熱點：總工具調用 `841` 次 / 讀取 `392` 次 (`222` 檔) / 編輯 `250` 次 (`138` 檔) / 子代理調用 `57` 次 (`35` `invoke_subagent` + `22` `manage_subagents`)
    - 關鍵摩擦訊號：`GATE_BOUNCE` `14` 次（主因為 `diagnostic-matrix.md` §3 H2 標題與 `RXX_research_report.md` 模板衝突）、`EDIT_CHURN` `29` 檔、`CONTEXT_WASTE` `6` 次、單回合 7 路平行 `invoke_subagent` JSON 序列化溢出 `1` 次（`Step 316`）。
- **調研目標**：
  - 檢驗母倉 6 大共性坑點於 `uitk.net` 三波收斂中的命中表現與修復成效。
  - 提煉 `uitk.net` 實測暴露出的 **6 大全新增量發現**（特別是 `diagnostic-matrix.md §3` 與 `plan verify` 模板驗證器的結構衝突、C# `partial class` 偽拆檔掩蓋 23 個散落私有欄位、C# Default Interface Method 轉型無窮遞迴 `StackOverflowException`、`[InternalsVisibleTo]` / Source Generator 靜態欄位誤刪、三代盲測「湊數強迫症」與平行子代理單回合派發上限）。

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

針對 `uitk.net` 實測挖掘出的 6 大核心增量問題，對比各候選改進方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **增量 1：`diagnostic-matrix.md §3` 與 `plan verify` 模板衝突**<br/>**方案 1A（修改 `PlanVerifier` 放寬 `RXX` 標題檢查）** | 於 `agents-workflow` 修改 `_verifier_specs.py` 為 `RXX_code_optimization_audit.md` 開特例 | 不用改技能文檔 | 破壞全系統 `RXX_research_report.md` 單一模板 SSOT，且違反「禁止特例硬編碼」公理 | ★☆☆☆☆ |
| **增量 1：`diagnostic-matrix.md §3` 與 `plan verify` 模板衝突**<br/>**方案 1B（推薦：將 `diagnostic-matrix.md §3` 的 5 大區塊改為掛載於 `RXX_research_report.md` 標準 H2 下之 `###` H3 子章節）** | 強制對齊 `RXX_research_report.md` 四大標準 H2（`## 1. 背景與調研目標`、`## 2. 候選方案分析與對比`、`## 3. 架構設計與驗證`、`## 4. 調研結論與落地建議`），將定錨基準、契約查驗表、`D1~D5` 矩陣、`S1~S6` 處方箋作為 `### 1.1` ~ `### 4.1` 子章節 | **100% 根除 `GATE_BOUNCE [TRIAGE: FULL_REWRITE]`**（本案因該衝突耗費數十步改寫 21 份報告） | 僅需更新 `diagnostic-matrix.md §3` 結構範例 | ★★★★★ |
| **增量 2：C# `partial class` 偽拆檔掩蓋高耦合 (`D1`/`S6`)**<br/>**方案 2A（推薦：`partial class` 搭配 `S5` 內部狀態團塊封裝守門）** | 於 `diagnostic-matrix.md (D1)` 與 `refactoring-playbook.md (S6)` 明訂：`partial class` 僅解決物理導航，若跨分部檔共享超過 `5~7` 個同生命週期私有欄位（如 `m_Cached*` 量測快取、編輯歷史），必須先以 `S5` 封裝為內聚的內部狀態 struct/class（如 `TextLayoutCacheState`），禁止僅靠搬移方法至 `.partial.cs` 掩蓋狀態散落 | 完美互補 `GC_VEX_V5` (`R02`) 的 `partial class` 處方：既享受 `partial class` 零開銷分檔，又防止 23 個私有欄位跨 5 檔義大利麵化 | 無額外成本 | ★★★★★ |
| **增量 3：介面預設方法 (C# DIM / Java `default`) `S3` 去重陷阱**<br/>**方案 3A（推薦：禁寫 `((IInterface)this).Method()`，強制提取介面靜態輔助函式）** | 於 `refactoring-playbook.md §3 (S3)` 新增「介面預設實作去重安全模式」：禁止在實作類別中以 `((IInterface)this).Method()` 委派預設方法（在 C#/Java IL `callvirt` 下必觸發無窮遞迴 `StackOverflowException`），強制抽為 `IInterface.DefaultMethod(this, ...)` 靜態輔助函式 | 100% 預防編譯期 0 警告但執行期必崩潰的虛擬分派無窮遞迴災難 | 無額外成本 | ★★★★★ |
| **增量 4：`D2` 死代碼對靜態欄位、`[InternalsVisibleTo]` 與 Source Generator 之誤判**<br/>**方案 4A（推薦：擴充 `callers + search` 雙重檢索守門涵蓋欄位/屬性/Generator）** | 與 `R02` (`GC_VEX_V5`) 匯流：凡 `callers == 0` 之類別、欄位 (`s_LayoutCallCount`)、屬性、Enum 或含 Source Generator / `[InternalsVisibleTo]` 標記之符號，強制執行 `knowledge-db search "<symbol>"` 跨 `src/` 與 `tests/` 全文檢索確認 | 徹底防止測試探針欄位 (`s_LayoutCallCount`) 與編譯期合成門面被當成死代碼誤刪 | 每次刪除前多 1 次極速 `search` | ★★★★★ |
| **增量 5：多代盲測「湊數強迫症 (Audit Quota Compulsion)」與 C# 目錄 Namespace 連動**<br/>**方案 5A（推薦：強化 `P0=0 / P1=0` 零處方榮譽結案出口 + 目錄即 Namespace 紅線）** | 1. 於 `SKILL.md` 與 `diagnostic-matrix.md` 明訂：當 `P0=0` 且 `P1=0` 時，直接宣告「已達最佳內聚度，建議出口 ③ 結案」，禁止為湊處方而違反防過度設計紅線；<br/>2. 於 `S6` 明訂：在目錄與 Namespace 1:1 鏡像之專案中，新建子目錄搬移公開型別等同於破壞性變更 Public Namespace | 根除 `R03` 為了不交白卷而亂拆 `StyleSheet.Defaults.cs` 或新建子資料夾破壞 Public Namespace 的現象 | 無額外成本 | ★★★★★ |
| **增量 6：Umbrella 平行子代理單回合派發溢出與跨模組契約漂移**<br/>**方案 6A（推薦：單回合平行派發上限 `3~4` 個 + 極簡指針 Prompt + `Breaking Signature Manifest` 回報表）** | 於 `exploration-and-delegation.md` 規定：① 單一 Turn 平行 `invoke_subagent` 上限為 `3~4` 個（超過則分批），Prompt 僅傳路徑與規則指針；② 實作子代理完成回條必須附帶 `[Cross-Module Breaking Signature Manifest]` (`Old -> New`) 供主代理對齊 `tests/` 與 `samples/` | 100% 避免 `Step 316` JSON token loop 崩潰，並與 `R02` (`GC_VEX_V5`) 的跨模組交接表完全統一 | 無額外成本 | ★★★★★ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 母倉 6 大共性坑點於 `uitk.net` 之實測命中率與收斂對照

| 坑點項目 | 本次實測命中狀況與發生頻率 | 原地收斂處置與最終驗證狀態 |
| :--- | :--- | :--- |
| **1. 【S2 半調子轉發殼層殘留】** | **命中（中頻，共 6 處，集中於第 1~2 波）**<br/>子代理於 `sub_05` / `sub_07` 抽離共用靜態純函式至 `NumericInputSyntax.cs` 與 `WindowManagerModule.cs` 後，曾在原類別留下 1 行 `private static` 轉發殼層（如 `ProgressBar.ClampToRange`、`RadioButtonGroup.NormalizeIndex`、`SwitchButton.NormalizeIndex`、`InputFieldBase.GetEffectiveFontFamily`、`Window.IsDedicatedWindowPanel`）。 | **已於第 3 波收斂中 100% 物理拔除**：刪除所有 1 行內部轉發殼，同模組呼叫端直接呼叫正統入口。 |
| **2. 【S6 行數教條與過度拆分】** | **命中（雙向張力：第 1 波 `D5` 規範拆檔 vs. 第 3 波 `R03` 教條拆檔提案）**<br/>1. 第 1 波 (`R01`)：因 `docs/_project/STANDARDS.md` §2.1 訂有「一檔一主要型態」剛性條款，將 `BuiltInEventCodecs.cs`（39 型別）與 `Enums.cs` 拆為獨立型別檔（遵循 `D5`）。<br/>2. 第 3 波 (`R03`)：當真實病灶收斂後，子代理開始因行數提出教條拆分（如將高內聚 `StyleSheet.Defaults.cs` 拆為 4 檔、將 `Window*.cs` 拆入子目錄、或為 `Toggle`/`SwitchButton` 強造抽象基類）。 | **已在第 3 波「去蕪存菁評估」中攔截拒絕**：維持高內聚單檔，拒絕無正交變更軸線之碎片化拆檔與過度抽象。 |
| **3. 【S3 合併遺失 20% 邊界不變量】** | **命中（低頻高危，共 2 處）**<br/>1. 第 1 波合併 `ComputedStyle.cs` 祖先樣式表走訪時顛倒了 `hierarchy.parent ?? parent` 優先序。<br/>2. 第 3 波 (`Step 1141`) 於 `AssetManagerModule.cs` 與 `AssetCachePool.cs` 合併零引用資產回退邏輯時，抹平了「同步 `Load<T>` 保留於 L2 Standby (`disposeIfRejected: false`)」與「`LoadHandle` 零容量立即處置 (`disposeIfRejected: true`)」的邊界差異，並因 `Task.Yield()` 延遲釋放導致 L2 喚醒測試失敗。 | **已逐行比對並 100% 還原邊界不變量** (`Steps 1173–1179`)：於 `AssetCachePool.PlaceOrDisposeZeroRefNode_locked` 顯式區分 `disposeIfRejected` 參數並移除破壞同步狀態轉換的 `Task.Yield()`。 |
| **4. 【簽名變更與測試替身失步】** | **命中（高頻，三波皆發生：`Steps 325, 761, 852, 976, 1079–1109`）**<br/>在 `Mode A` + 平行子代理禁跑 `dotnet build` 下，修改 `src/` 簽名時漏改 `samples/`、`tests/UITK.Tests.Studio/` 或測試替身。 | **已全數對齊修復**：同步更新 `samples/UITK.Samples/Program.cs`、`GoldenStudioMainWindow.cs`、`FontProviderContractTests.cs` 等所有跨專案呼叫點。 |
| **5. 【審計編號註解污染】** | **命中（共 43 個檔案殘留歷史計畫/審計編號）**<br/>檢出 `[P00:DR-01]`、`[R02:DR-24]`、`(FR-11)`、`(BR-16)`、`(EC-01)`、`(F1~F3)`、`Bug 4 修復` 等殘留於 XML Docstring 與行內註解。 | **已完成原地全數清除** (`Steps 1371–1435`)：清理 43 檔，複查 `src/` 達成 **0 殘留**，`dotnet build` (`0 Warning / 0 Error`) 與測試全綠 (`348/348`)。 |
| **6. 【驗收工具摩擦】** | **命中（共 6 次 `JSON_SNIPPET_OVERFLOW`：`Steps 293, 436, 498, 817, 821, 1061`）**<br/>大範圍 `git diff` 截斷至 `output.txt`，單次讀取最高耗費 `11,462` tokens。 | **已收斂**：改用 `git status --short` 與 `knowledge-db` 精準切片定位。 |

---

### 3.2 六大實證增量發現深度剖析 (Six Deep-Dive Incremental Insights)

1. **`[UITK-INC-01]` 技能手冊與驗證器直接衝突：`diagnostic-matrix.md §3` H2 標題導致 `plan verify` 必退件 (`[TRIAGE: FULL_REWRITE]`)**：
   - **實證證據**：[`diagnostic-matrix.md:64-89`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/diagnostic-matrix.md#L64-L89) 要求 `R01` 使用 `## 1. 定錨基準與範圍摘要` ~ `## 5. 風險評估與推薦流轉出口` 作為 H2 標題，但 `PlanVerifier` 強制校驗 `R{NN}_*.md` 必須匹配 [`RXX_research_report.md`](../../../../ys_codebase/source/agents-workflow/assets/templates/RXX_research_report.md) 的 4 個標準 H2 標題（`## 1. 背景與調研目標`、`## 2. 候選方案分析與對比`、`## 3. 架構設計與驗證`、`## 4. 調研結論與落地建議`）。這導致子代理乖乖照手冊寫完 21 份 `R01~R03` 後，`plan verify` 觸發 14 次 `GATE_BOUNCE`，主代理被迫耗費數十步手動改寫標題！
2. **`[UITK-INC-02]` C# `partial class` 的「物理拆檔假象」與 `S5` 狀態團塊封裝邊界**：
   - **實證證據**：將 2,340 行的 `InputFieldBase` 拆成 5 個 `.partial.cs` 後，雖然單檔行數漂亮地降到 500 行以下，但 5 個分部檔依然直接交叉讀寫同一個類別命名空間下的 **23 個散落私有快取欄位 (`m_Cached*`)**。因此，對於支援 `partial class` 的語言，必須規定：若跨分部檔共享超過 `5~7` 個同生命週期私有欄位，必須搭配 `S5` 將那些欄位封裝為內聚的內部狀態結構（如 `TextLayoutCacheState`），否則只是「把義大利麵分裝在 5 個盤子裡」。
3. **`[UITK-INC-03]` C# Default Interface Method (DIM) 轉型委派引發執行期無窮遞迴 (`StackOverflowException`)**：
   - **實證證據**：`ITextShaper` 定義了 C# 8.0 預設介面方法 `ShapeText(...)`。子代理在執行 `S3` 去重時，於實作類別 `SimpleTextShaper` 寫出 `public ShapedText ShapeText(...) => ((ITextShaper)this).ShapeText(...);`。在 C# / Java 中，將 `this` 轉型為介面呼叫一個已被該類別實作的方法，虛擬方法表 (`vtable` / `callvirt`) 仍會派發回該具體類別自身，導致編譯期 `0 Error`、執行期瞬間 `9,683` 層 `StackOverflowException` 崩潰！
4. **`[UITK-INC-04]` `knowledge-db callers` 對靜態欄位讀寫、`[InternalsVisibleTo]` 測試探針與 Roslyn Source Generator 的 `D2` 死代碼誤判**：
   - **實證證據**：`FlexLayoutEngine.s_LayoutCallCount` 是供 `FlexLayoutEngineTests` 驗證 0 冗餘排版的 `internal static` 計數器；因 `callers` 只追蹤函式呼叫邊 (`CALLS`)，不追蹤欄位讀寫，導致第 1 波與第 3 波盲測子代理兩度將其誤判為 0 調用死欄位刪除，炸毀 4 項排版測試。這與 `R02` (`GC_VEX_V5`) 發現的 POCO 型別宣告誤刪完全同源，共同證明了 **`D2` 死代碼拔除前必須執行 `callers` + `search` 雙重檢索**。
5. **`[UITK-INC-05]` 多代盲測下的「湊數強迫症 (Audit Quota Compulsion)」與「目錄即 Public Namespace」連動紅線**：
   - **實證證據**：到了第 3 代盲測 (`R03`)，當真正的病灶都修完後，子代理為了「不交白卷」，開始建議將純宣告式的 `StyleSheet.Defaults.cs` 拆成 4 檔、為僅有 2 個控制項的 `Toggle`/`SwitchButton` 造抽象基類、或新建子資料夾搬移 21 個檔案（在 C# 資料夾與 Namespace 1:1 鏡像規範下，搬資料夾等於破壞性修改 Public Namespace）。
6. **`[UITK-INC-06]` 單回合 7 路平行 `invoke_subagent` 輸出溢出 (`Step 316`)**：
   - **實證證據**：主代理在單一 Turn 同時發出 7 個帶長 Prompt 的 `invoke_subagent` 工具呼叫時，觸發底層模型 JSON token loop (`} }] } }] ...`)。改為 **單回合最多平行派發 3~4 個子代理 + 極簡檔案路徑指針 Prompt** 後，100% 穩定。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  1. **立即修正 `diagnostic-matrix.md §3` 報告結構模板**：將五個診斷區塊改為 `RXX_research_report.md` 四大標準 H2 標題下的 `###` H3 子章節，徹底消滅 `plan verify` 的 `[TRIAGE: FULL_REWRITE]` 退件。
  2. **合流 `R01` + `R02` + `R03` 三方實證結論**：將母倉（Python CLI/Daemon 基座）、`GC_VEX_V5`（C++ 嵌入式韌體 + C# ImGui 上位機）與 `uitk.net`（C# 0-GC UI 框架 + Source Generator）的全部實證洞察，統一編入 `code-optimizer` v1.1 的 4 個核心資產檔（`SKILL.md`、`exploration-and-delegation.md`、`diagnostic-matrix.md`、`refactoring-playbook.md`）。
- **後續行動與銜接**：
  - 三份實測調研報告（`R01` 母倉、`R02` `GC_VEX_V5`、`R03` `uitk.net`）現已全數到位落檔，可立即進行跨專案三方綜合會診並呈遞升級藍圖供開發者裁決。

