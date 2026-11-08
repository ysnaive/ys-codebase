---
target: "AST"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/ast/ast_engine/__init__.py"
  - "yscb://source/ast/ast_engine/schema.py"
  - "yscb://source/ast/ast_engine/engine.py"
  - "yscb://source/ast/ast_engine/bundler.py"
  - "yscb://source/ast/ast_engine/linker.py"
  - "yscb://source/ast/ast_engine/resolver.py"
  - "yscb://source/ast/ast_engine/dialects/base.py"
  - "yscb://source/ast/ast_engine/parsers/treesitter.py"
  - "yscb://source/ast/ast_engine/parsers/registry.py"
  - "yscb://source/ast/scripts/cli.py"
related_docs:
  - "./DESIGN_NOTES.md"
  - "../core/README.md"
  - "../knowledge-db/README.md"
last_updated: "2026-11-08"
---

# AST 靜態語法樹、方言隔離、雙層分部符號與呼叫拓撲核心引擎手冊 (AST Overview)

> 模組名稱：`ast`  
> 職責定位：YS-Codebase 三階單向無環圖（`core.space` $\to$ `ast` $\to$ `knowledge-db`）之 Layer 2 靜態語法分析與呼叫拓撲核心引擎，專責多語言 Tree-sitter / AST 結構化解析、官方方言隔離（`dialects/<lang>`）、`contributes` 宣告式語言擴充、C# `partial class` 雙層無損聚合、確定性同名異載（Method Overloads）群組定址、雙向呼叫圖譜（`CallGraph`）與單檔結構大綱（`outline`），並向 Layer 3 `knowledge-db` 提供單次解析符號共享快照（Single-Parse Symbol Sharing）。

---

## 1. 模組定位與核心能力 (Vision & Capabilities)

`module:ast` 將「確定性語法結構推理與呼叫拓撲」自上層全文與向量檢索（`knowledge-db`）中徹底正交分離，具備 **100% 零 BM25 與零 ONNX 向量依賴**：

- **四大不可變內核原子結構與平權交換律提取器 (`Span` / `ProvenanceStep` / `SymbolNode` / `RelationEdge` & `FileSymbolGraph`)**：
  - 於 `ast_engine.schema` 提供四大 `@dataclass(frozen=True)` 原子模型與單檔自包含圖譜 `FileSymbolGraph`，以 `"{canonical_path}::{fqn}[({param_types})]"` 作為與空間及行號解耦之穩定符號 ID。
  - `TreeSitterDriver` 原生支援 Tree-sitter 官方 `queries/tags.scm`（`@definition.<kind>`、`@name`、`@doc`、`@reference.<kind>`）與擴充標籤（`@def.<kind>`、`@part.<slot>`、`@facet.<key>`、`@edge.<kind>`）；當多組 `.scm` 在同檔案捕獲相同 `@name` / `@part.name` 物理 `Span(start_byte, end_byte)` 時，自動執行交換律聯集（$A \cup B = B \cup A$）並以包含關係堆疊（Containment Stack）組裝無限層級遞迴 `SymbolNode.children`。
  - 支援 `SymbolProcessor` 平權精煉管線與 `contributes` 之 `spaces: list[str]?` 規則範圍綁定（透過 `core.space` 自動對目標檔案執行空間匹配過濾）。
- **內建官方方言隔離 (`ast_engine/dialects/<lang>`) + `contributes` 外部語言擴充**：
  - 內建 `python`、`csharp`、`cpp`、`c`、`javascript`、`typescript`、`markdown` 7 大官方方言適配器（`DialectAdapter`）及 `spice`、`html`、`css` 領域解析器，通用 `TreeSitterDriver` 維持零特定語言條件分支。
  - 外部模組與宿主專案可透過 `contributes/ast.json` 或 `config/ast/contribute.json` 宣告 `languages`（支援 `tree_sitter` 掛載 `query_file` / `query_files: list[uri]`、`spaces` 範圍約束、`processors` 精煉器，或 `custom` 掛載 Python 解析類別）。
- **C# `partial class/struct/interface` 雙層無損儲存模型 (Two-Tier Partial Symbol Model)**：
  - **表層邏輯聚合視圖 (`children` / `members`)**：跨檔案合併同空間、同 FQN 分部型別的所有成員、基底型別 (`base_types`)、欄位型別 (`field_types`) 與分部檔案清單 (`partial_files`)，供 `TopologyLinker` 解析跨分部成員呼叫。
  - **底層物理檔案視圖 (`metadata["_own_*"]`)**：完整保留各單一分部檔案自身定義之 `_own_members`、`_own_base_types`、`_own_field_types` 與 `_own_docstring`，供單檔 `outline` 精確顯示及下游 `knowledge-db` 倒排索引去重（消除 $N^2$ Posting 膨脹）。
- **無 BM25 確定性符號定位器與同名異載 (Method Overloads) 群組定址**：
  - 支援 `[kind] [scope.]name[(param_types...)]` 語法（如 `Window.Open(string, int)`）。
  - 當查詢 `Class.Method`（不含括號）命中**同一父型別下的多個重載（Overloads）**時，預設視為同一邏輯群組一併展開（標註各重載簽名、行號與聯集 `callers/callees/impact`）；唯有命中**跨不同父型別**（如 `UI.Window.Open` vs `IO.File.Open`）時，才返回結構化歧義候選清單。
- **`yscb ast outline <file>` 單檔結構化大綱、三維度正交過濾與 `[Partial Siblings]` 提示**：
  - 毫秒級輸出檔案內類別、方法/函式簽名、可見度、`[static]` 標籤與起訖行號（`Lstart-Lend`），作為 AI Agent 區段讀檔前的高精準行號導航器。
  - 支援 **可見度 (`--public|--protected|--internal|--private|--non-private`)**、**靜態/實例綁定 (`--static|--non-static`)** 與 **成員型別 (`--methods|--fields|--types`)** 三個正交維度自由組合過濾，並保留有匹配子成員之父容器階層。
  - 當檔案內型別為 `partial` 且同空間存在其他同 FQN 分部檔時，預設僅顯示本物理檔案之 `_own_members`，並自動附帶 `[Partial Siblings]` 提示列出其餘分部檔案與成員數摘要（加 `--merged` 可展開跨分部合併視圖）。
- **按需語法依賴自舉 (On-Demand Grammar Provisioning) 之 `stderr` 與離線圍欄**：
  - 動態安裝日誌與離線降級 Warning 100% 導向 `sys.stderr`，內建會話級負快取避免重複重試，保證 `--json` stdout 在任何網路/沙盒環境下 100% 純淨可解析。
- **Single-Parse Symbol Sharing、單次讀檔建置與 $O(|\text{dirty}|)$ Pull-Based JIT 熱自癒**：
  - 全量建置 `bundle_union` 於單次讀檔中同時提取 `(symbols, call_sites, imports)` 並緩存於 `SemanticBundler`（`_file_call_sites_cache` / `_file_imports_cache`），使後續 `extract_all_call_sites_and_imports` 零重複讀盤。
  - 以 `consumer_id="ast"` 消費 `core.space` 指紋差量；單檔或增量熱修補 `hot_patch_index` 透過 `_resolve_dirty_files_only` 直接從 `YFP2` 快照與 `core.space.resolve_file_path` 以 $O(|\text{dirty}|)$ 定位異動檔案（零全倉走訪）、透過 `file_to_symbol_ids` 快速淘汰舊符號並增量合成 `files_map`，原子持久化 `ast.storage://indices/unified.symbols.bin.gz` (`ASTSnapshot`) 與 `unified.graph.bin.gz` (`CallGraphIndex`)，並透過 `scripts/hook.core.py` 訂閱 `on_file_space_changed` 自動熱修補及廣播 `on_ast_index_updated`。

---

## 2. CLI 快速上手 (Quick Start)

`module:ast` 提供 6 個標準 CLI 指令：`outline`, `callers`, `callees`, `impact`, `status`, `clean`。

```bash
# 1. 檢視單一檔案之結構化符號大綱、簽名、起訖行號、正交過濾與 [Partial Siblings] 提示
python yscb.py ast outline ys_codebase/source/core/core/uri.py
python yscb.py ast outline ys_codebase/source/core/core/uri.py --public --methods
python yscb.py ast outline Window.cs --merged --non-private --static --json

# 2. 查詢呼叫指定符號之上游呼叫者 (支援同型別 Overload 自動群組展開或帶參數精確定址)
python yscb.py ast callers UnifiedSymbol --snippet --json
python yscb.py ast callers "Window.Open(string, int)" --json

# 3. 查詢指定符號內部呼叫之下游目標
python yscb.py ast callees ASTEngine.ensure_jit_synced --snippet --json

# 4. 執行 N 階遞迴影響半徑 (Blast Radius) 評估
python yscb.py ast impact FileSpaceManager --depth 2 --json

# 5. 檢視 AST 索引狀態、世代水位 (ast_generation)、已註冊方言與解析器狀態
python yscb.py ast status --json

# 6. 清除 AST 符號與呼叫圖譜快取並重置 ast 消費者游標
python yscb.py ast clean --json
```

---

## 3. Python SDK 與語言擴充範例 (Python SDK & Contributes)

### 3.1 Python 門面 SDK

```python
from ast_engine import ASTEngine

engine = ASTEngine()

# 1. 取得最新已同步之單次解析符號快照 (供下游模組如 knowledge-db 直接共享消費)
snapshot = engine.get_snapshot(auto_sync=True)

# 2. 單檔結構化大綱與呼叫拓撲查詢
outline_data = engine.outline("project://ys_codebase/source/core/core/uri.py")
callers_data = engine.callers("resolve_yscb_root", include_snippet=True)
impact_data = engine.impact("ContributesValidator", depth=2)
```

### 3.2 宣告式語言擴充 (`contributes/ast.json` 或 `config/ast/contribute.json`)

```json
{
  "languages": {
    "spice": {
      "mode": "custom",
      "extensions": [".sp", ".cir", ".lib"],
      "parser_entry": "ast_engine.parsers.spice_parser:SpiceParser"
    }
  }
}
```

---

## 4. 相關技術文件指針

- 🛡️ **設計決策與工程妥協手冊**：[DESIGN_NOTES.md](./DESIGN_NOTES.md)
- 📂 **File-Space 模組手冊**：[../file-space/README.md](../file-space/README.md)
- 🔍 **Knowledge-DB 模組手冊**：[../knowledge-db/README.md](../knowledge-db/README.md)

