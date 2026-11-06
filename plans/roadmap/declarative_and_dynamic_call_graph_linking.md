# 技術路線圖：跨層宣告式與動態符號連結器 (`declarative_ref` Call Graph Linking) (Roadmap)

> 主題：跨層宣告式與動態符號連結器 (`declarative_and_dynamic_call_graph_linking`)  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：`ast`（`ast_engine` 拓撲連結器、呼叫圖譜索引與跨空間宣告式配置解析）、`knowledge-db`（消費端轉發同步）  
> 前置解鎖條件：[Tier 2 - 排序 #4] 獨立小型高價值升級；建議於 #5 (ast 大型編譯管線重構) 之前先行落地，消除 contributes/*.json 插件入口 0 callers 盲區  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **純 AST 呼叫圖對宣告式、插件與編譯期生成代碼存在結構性盲區**：`module:ast` (`ast_engine`) 透過 Tree-sitter 與 `TopologyLinker` 建立的呼叫圖譜對直接函式呼叫具備高精度，但在微核心插件架構（如 YSCB 自身的 `contributes/*.json` CLI 路由、`code.symbol://` / `code.class://` 動態綁定、`hook.*.py` 事件掛載）或框架型專案（如 C# Roslyn Incremental Source Generator 之 `[Module(..., facadeName=...)]` 靜態門面轉發、Unity UXML/USS 與序列化事件綁定）中，組件間透過設定檔字串、Attribute 標註或編譯期生成規約進行跨層耦合。
  - **影響面分析（`ast impact` / `ast callers`）與死代碼診斷（`D2`）誤判孤兒節點**：由於純 AST 解析無法將「宣告式設定檔內的符號引用 / Attribute 生成門面」與「目標程式碼函式/類別」連成圖譜邊，導致 Agent 執行 `ast callers` 或 `ast impact` 時，被動態掛載或透過生成門面呼叫的公開函式常顯示為 `0 callers` 或斷鏈，在重構或 `/code-optimizer` 死代碼排查時需額外人工核對。
- **長期願景與目標定位**：
  - 於 `module:ast` (`ast_engine`) 拓撲連結管線引入輕量、可擴充的「跨層宣告式符號連結器（Declarative Symbol Linker）」，將宣告式設定檔與目標程式碼符號連通為顯式有向邊，使 `ast callers`、`ast callees` 與 `ast impact` 真實反映全系統跨層耦合拓撲。
- **範疇與邊界約束**：
  - 聚焦於確定性高、格式明確的宣告式引用（如 `contributes/*.json` 內的 `code.symbol://`、`code.class://`、CLI `entry` / `handler` 及標準 Hook 規約），不對任意無結構純文字進行模糊字串猜測，嚴防引入假陽性幽靈邊。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **高確定性顯式協議優先（Zero Speculative String Matching）**：僅針對具備明確語意前綴（如 `code.symbol://`、`code.class://`）或結構化配置欄位提取宣告式引用，嚴禁將普通文字常數或日誌字串誤連為呼叫邊。
  - **邊型別正交區分（Edge Type Orthogonality）**：於呼叫圖譜中區分標準程式碼呼叫邊（`ast_call`）與跨層宣告式引用邊（`declarative_ref`），使 `callers` / `impact` 查詢能清楚標示上游來源為「程式碼直接呼叫」或「宣告式配置掛載」。
  - **增量熱修補相容（Hot-Patch Consistency）**：當宣告式設定檔（如 `contributes/*.json`）或目標 `.py`/程式碼檔案發生變更時，增量熱修補管線必須同步更新對應的 `declarative_ref` 入度與出度邊。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **虛擬配置節點與有向邊建構**：將宣告式配置項（例如 `contributes/core.json` 中註冊的 CLI 命令或服務）建模為輕量配置端點符號，並向其指向的目標 Python/C#/C++ 函式或類別建立 `declarative_ref` 有向邊。
  - **可插拔提取規則**：內建支援 YSCB `contributes/*.json` 與 `hook.*.py` 綁定解析，並預留宣告式配置提取規則接口供下游專案（如 C# / Unity 資產事件綁定）擴充。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - **[Tier 2 - 排序 #4]** 無外部阻塞依賴；建議於啟動 `#5 (ast_compile_pipeline_and_kdb_doc_governance)` 大型重構前先行獨立交付，讓後續跨模組重構與靜態審計直接受惠於完整的 `contributes/*.json` (`code.symbol://` / `code.class://`) 跨層呼叫圖譜。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`contributes/*.json` 與 `code.*://` 宣告式邊提取器）**：於 `ast_engine` 實作宣告式配置符號掃描與 `declarative_ref` 圖譜邊連通，支援增量熱修補。
  2. **Stage 2（`TopologyQueryService` 與 CLI 輸出整合）**：於 `ast callers`、`ast callees`、`ast impact` 查詢結果中呈現宣告式掛載來源，消除插件入口函式的孤兒節點假象。
  3. **Stage 3（下游跨語言宣告式規則擴充）**：開放透過 `contributes/ast.json` 宣告自訂配置檔之符號提取模式。

