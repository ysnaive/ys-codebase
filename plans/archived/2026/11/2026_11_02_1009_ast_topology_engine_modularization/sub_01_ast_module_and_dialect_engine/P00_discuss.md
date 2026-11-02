# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：建立 `module:ast@1.0.0.0` 靜態語法樹、方言隔離、雙層分部符號與呼叫拓撲核心引擎  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依據《語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`)》路線圖提案、`uitk.net` 4 項工程邊界建議與主計畫 `P00` / `R01` 定案契約，啟動 `sub_01_ast_module_and_dialect_engine` (`/auto`)。
- **核心目標**：
  1. 建立 `ys_codebase/source/ast/` (`v1.0.0.0`)，僅依賴 `core` 與 `file-space`（Layer 2，100% 零 BM25 與零 ONNX 向量依賴）。
  2. 100% 無損遷移並純化所有語法樹與領域/文檔解析器：
     - 實作 `ast/dialects/` 官方方言隔離（`base.py`, `python.py`, `csharp.py`, `cpp.py`, `c.py`, `javascript.py`, `typescript.py`, `markdown.py`），使 `TreeSitterDriver` 成為零特定語言 `if/elif` 分支的通用驅動。
     - 完整保留 `PythonASTParser`、`MarkdownParser`、`SpiceParser`、`HtmlParser`、`CssParser` 與 `assets/queries/*.scm`。
     - 實作 `contributes/_format.json` 宣告 `languages` 擴充點（支援 `tree_sitter` 與 `custom` 模式，動態綁定 `SUPPORTED_EXTENSIONS`），並將宿主 `ys_codebase/config/knowledge-db/contribute.json` 內之 `languages` 宣告同步建立於 `ys_codebase/config/ast/contribute.json`。
  3. 完整實作 C# `partial class/struct/interface` 雙層無損跨分部聚合（`aggregate_partial_symbols`、`restore_unaggregated_partial_symbol`、保留 `_own_members` / `_own_base_types` / `_own_field_types` / `_own_docstring` 及增量熱修補退化重聚合）。
  4. 完整落地 `uitk.net` 工程邊界 ① ~ ④（Layer 2 部分）：
     - **邊界 ①（無 BM25 確定性符號定位器與同名異載 Overload 群組定址）**：支援 `[kind] [scope.]name[(param_types...)]`；`TopologyLinker._by_fqn` 改為 `Dict[str, List[UnifiedSymbol]]` 防止同 FQN 重載覆蓋；當查詢 `Class.Method` 命中同一父型別下的多個重載時預設群組化一併展開（標註各重載簽名、行號與聯集拓撲），跨不同父型別才回傳歧義清單。
     - **邊界 ②（`yscb ast outline <file>` 與 `[Partial Siblings]` 提示）**：支援單檔結構化大綱，當檢測到 `partial` 型別具有其他同 FQN 分部檔時，預設顯示本檔 `_own_members` 並自動附帶 `[Partial Siblings]` 提示列出其餘分部檔案與成員數（支援 `--merged` 展開合併視圖）。
     - **邊界 ③（按需 Grammar 自舉之 `stderr` 純淨度與離線圍欄）**：`GrammarProvisioner` 將動態安裝輸出 100% 導向 `sys.stderr`，離線或安裝失敗時發出結構化 Warning 至 `stderr` 並優雅略過該語言，保證 `--json` 100% 純淨。
     - **邊界 ④（Layer 1 $\to$ Layer 2 Pull-Based JIT 水位線與快照供給）**：以 `consumer_id="ast"` 消費 `file-space`，原子持久化 `cache://ast/indices/unified.symbols.bin.gz`（含 `ast_generation`、`space_generations`、`symbols`、`file_to_symbol_ids`）與 `unified.graph.bin.gz`，並提供 `ASTEngine` Python SDK 與 `scripts/hook.file-space.py` 事件驅動熱修補（廣播 `on_ast_index_updated`）。
  5. 提供 `yscb ast <outline|callers|callees|impact|status|clean>` 6 個正交 CLI 指令。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 遷移自 `ys_codebase/source/knowledge-db/knowledge_db/{schema,bundler,linker,graph,topology_query,formatter,io_utils}.py` 與 `parsers/`。
- **邊界排除 (Explicitly Excluded)**：
  - 本子計畫（`sub_01`）專注於 `module:ast@1.0.0.0` 本體建置、測試與 `@build` 部署；`knowledge-db` 內部舊 AST 程式碼物理移除與消費切換將於 `sub_02` 執行，`agents-workflow` 技能路由更新將於 `sub_03` 執行。
- **架構影響範圍**：
  - `ys_codebase/source/ast/` (New)
  - `ys_codebase/config/ast/contribute.json` (New)
  - `docs/ast/README.md` & `docs/ast/DESIGN_NOTES.md` (New)

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `module:ast` 套件與儲存拓撲契約**：
  - 模組名稱為 `ast`（Python 匯入套件為 `yscb_ast` 或透過 `from ast_engine import ...` / `import ast`？注意：Python 標準庫內建名為 `ast` 的模組！為避免遮蔽 Python 標準庫 `import ast`（因為 `PythonASTParser` 及其他模組本身需要使用 Python 標準庫 `ast.parse`！），`ys_codebase/source/ast/` 的 CLI 模組名維持 `ast`（即 `yscb.py ast ...` 與 `module://ast`），內部套件目錄採用 `ast_engine/`（同時於 `ys_codebase/source/ast/__init__.py` 暴露公開 SDK），100% 避免與 Python 內建 `import ast` 發生命名空間遮蔽衝突！）。
- **[P00:DR-02] `DialectAdapter` 方言隔離與零特判主幹**：
  - 於 `ast_engine/dialects/` 建立 `DialectAdapter` 介面與 `python`、`csharp`、`cpp`、`c`、`javascript`、`typescript`、`markdown` 實作，將所有語言特化邏輯自 `TreeSitterDriver` 抽離。
- **[P00:DR-03] 確定性符號定位與 Overload 群組展開**：
  - `SymbolSelector` 支援括號參數簽名過濾；`find_target_symbols` 對同父型別 `(space, parent_fqn)` 下的同名多載返回群組列表，`callers` / `callees` / `impact` 自動聚合該重載群組的拓撲結果並標註各重載簽名；跨父型別同名符號則返回結構化歧義清單。
- **[P00:DR-04] `outline` 單檔大綱與 `[Partial Siblings]` 提示**：
  - `yscb ast outline <file_or_uri> [--merged] [--json]` 輸出檔案內階層化符號大綱（Kind、Visibility、Signature、行號區間 `Lstart-Lend`）；若檔案內含 `partial` 型別且同空間存在其他同 FQN 分部檔，自動輸出 `[Partial Siblings]` 提示。
- **[P00:DR-05] 按需 Grammar 自舉之 `stderr` 隔離與離線降級**：
  - `GrammarProvisioner` 僅在偵測到實際檔案副檔名且缺少對應 `tree-sitter-*` 套件時按需觸發，所有安裝日誌導向 `stderr`，離線或失敗時記錄會話級負快取、向 `stderr` 發出結構化 Warning 並安全返回空結果。

---

## 3. 開放議題與確認紀錄

- 已由開發者下達 `/auto` 確認啟動。

---

## 4. 階段修訂紀錄 (Revision History)

- **[REV-01] `yscb ast outline` 新增三維度正交過濾旗標 (`visibility` / `binding` / `member_kind`)**：
  - 依開發者於實機檢視 `UX-01` 時提出並確認之建議，為 `yscb ast outline` 新增三個彼此正交可自由組合之過濾群組：
    1. **可見度 (`visibility`)**：`--public`、`--protected`、`--internal`、`--private`、`--non-private` (alias: `--api`)。
    2. **靜態/實例綁定 (`binding`)**：`--static`、`--non-static` (aliases: `--nonstatic`, `--instance`)。
    3. **成員型別 (`member_kind`)**：`--methods`、`--fields`、`--types`。
  - 當過濾子成員時保留匹配成員所屬之父類別容器階層，並於輸出標註 `[static]` 標籤與已套用之 `filters` 摘要。

