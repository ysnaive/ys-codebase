# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`) 與三階單向 DAG 架構重構  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](./umbrella_overview.md)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「請直接針對下方《語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`)》路線圖提案開立系列計畫，並先依照 `/blind-subagent` 分別派送兩個不同的子代理，分別從「上游生產（`module:space` / `module:ast` 語法解析、方言擴充、跨分部聚合與圖譜建構）」與「下游消費（`module:knowledge-db` 符號快照消費、混合檢索對接與 `agents-workflow` CLI 技能路由）」雙角度進行分析。**必備前提條件**：`knowledge-db` 當前帶有的 AST 相關功能特性、跨分部類別聚合品質與語言可擴充性（`contributes`）絕對不可破壞，且須一併將下方「下游實戰專案 (`uitk.net`) 架構評估回饋之 4 項邊界建議」納入設計考量。」
- **核心目標**：
  1. 建立第 7 枚核心基座模組 `module:ast@1.0.0.0`（`ys_codebase/source/ast/`），形成 `file-space` (Layer 1) $\to$ `ast` (Layer 2) $\to$ `knowledge-db` (Layer 3) 的三階單向無環圖（Strict 3-Tier DAG）。
  2. 100% 無損遷移並強化既有 `knowledge-db` 的所有 AST 能力（Tree-sitter / Python AST 解析、C# `partial class` 雙層儲存與跨檔聚合、C++ access specifier 繼承、`contributes` 外部語言查詢擴充、`CallGraph` 雙向呼叫圖譜與增量熱修補）。
  3. 完整納入 `uitk.net` 實戰回饋之 4 大工程邊界：
     - **邊界 ①**：同名異載（Method Overloads）同型別群組化展開與帶參數簽名精確定址；
     - **邊界 ②**：`yscb ast outline <file>` 單檔結構化大綱與 `[Partial Siblings]` 跨分部姊妹檔提示；
     - **邊界 ③**：按需語法依賴自舉（On-Demand Grammar Provisioning）之 `stderr` 純淨度與離線優雅降級圍欄；
     - **邊界 ④**：`file-space` $\to$ `ast` $\to$ `knowledge-db` Pull-Based JIT 游標水位線連鎖同步與常駐背景服務協同。
  4. `knowledge-db` 轉型為純粹的上層全文（BM25）與向量（ONNX Embedding）混合檢索消費者（Single-Parse Symbol Sharing），並同步更新 `agents-workflow` 技能路由對接 `yscb ast <outline|callers|callees|impact>`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 遷移並重構 `ys_codebase/source/knowledge-db/knowledge_db/{schema,bundler,linker,graph,topology_query,formatter}.py`、`parsers/{base,python_ast,treesitter,markdown,registry,spice_parser,html_parser,css_parser}.py`、`assets/queries/*.scm` 與 `contributes/_format.json` (`languages` 擴充點)。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁將各官方程式語言拆分為多個頂層 `yscb` 模組（統一採 `ast/dialects/<lang>` 內建方言隔離 + `contributes/ast.json` 外部語言擴充）。
  - `module:ast` 100% 不包含任何 BM25 分詞、倒排索引或 ONNX 向量嵌入依賴。
  - 採徹底切分、完全解耦策略：不保留 `knowledge-db callers/callees/impact` 轉發殼層或 `contributes/knowledge-db.json` `languages` 相容包袱。
- **架構影響範圍**：
  - `ys_codebase/source/ast/` (New) & `ys_codebase/config/ast/` (New)
  - `ys_codebase/source/knowledge-db/` (Refactor) & `ys_codebase/config/knowledge-db/` (Update)
  - `ys_codebase/source/agents-workflow/` (Skill & Trace Parser Update)
  - `docs/{ast,knowledge-db}/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 雙盲眼子代理上下游深度架構審計 (`R01`)**：
  - 完成 `R01_ast_upstream_downstream_architecture.md`，完整鎖定 `knowledge-db` 現有 AST 與拓撲細節座標及三階單向 DAG 快照契約。
- **[P00:DR-02] 全解析器統一收斂於 `module:ast`（`knowledge-db` 零 Parser 殘留）**：
  - 包含程式碼解析器（Python AST / Tree-sitter）與領域/文檔解析器（`markdown`、`spice`、`html`、`css`）全數收斂於 `module:ast`，統一由 `ParserRegistry` 與 `dialects/<lang>` 管理並產出 `UnifiedSymbol` 快照與跨文檔引用追蹤；`knowledge-db` 100% 不保留任何 Parser，直接消費 `module:ast` 快照建立 BM25 與向量索引。
- **[P00:DR-03] CLI 與 `contributes` (`languages`) 徹底切分、完全解耦**：
  - `module:ast` 獨佔 `yscb ast <outline|callers|callees|impact|status|clean>` 與 `contributes/ast.json` (`languages` 擴充點)；`module:knowledge-db` 徹底移除 `callers/callees/impact` CLI 與 `languages` 擴充點，宿主 `config/knowledge-db/contribute.json` 內之自訂語言宣告同步遷移至 `config/ast/contribute.json`，不留轉發殼層或歷史相容包袱。
- **[P00:DR-04] `uitk.net` 四大工程邊界剛性規格**：
  1. **Overload 群組定址**：無 BM25 確定性定位器支援 `[kind] [scope.]name[(param_types...)]`；當 `Class.Method` 命中同一父型別下的多個重載時預設群組化一併展開，跨不同父型別才返回歧義清單。
  2. **`outline` 跨分部姊妹檔提示**：`yscb ast outline <file>` 對 `partial class` 預設顯示該檔 `_own_members`，並自動附帶 `[Partial Siblings]` 提示列出同型別其餘分部檔案（支援 `--merged` 展開合併視角）。
  3. **按需 Grammar 自舉之 `stderr` 與離線圍欄**：動態安裝輸出 100% 導向 `stderr`，離線或失敗時輸出結構化 Warning 至 `stderr` 並優雅略過該語言，保證 `--json` 輸出 100% 純淨。
  4. **三階 Pull-Based JIT 連鎖同步**：`file-space` (`head_generation`) $\to$ `ast` (`consumer_id="ast"`, `ast_generation`) $\to$ `knowledge-db` (`acked_ast_generation`) 按需連鎖同步與常駐背景服務事件協同。
- **[P00:DR-05] 維持單一檢索與導航入口技能 (`knowledge-db-search`)**：
  - 於單一技能手冊內整合「未知座標搜關鍵字/語意用 `knowledge-db search` $\to$ 已知檔案看結構大綱用 `ast outline` $\to$ 已知符號查呼叫拓撲用 `ast callers/callees/impact`」三階工作流。

---

## 3. 開放議題與確認紀錄

- 三項跨模組架構邊界決策已全數由開發者拍板確認，`P00_discuss.md` 鎖定為 `Confirmed`。
