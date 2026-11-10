# `ast` — 靜態語法樹、方言隔離、雙層分部符號與呼叫拓撲核心引擎

`ast`（內部套件命名為 `ast_engine`）為 YS-Codebase 生態系的第 2 層（Layer 2）靜態語法樹與呼叫拓撲基座模組，嚴格介於底層 `core.space`（Layer 1：檔案空間與指紋底座）與上層 `knowledge-db`（Layer 3：全文與向量混合檢索）之間，負責提供單次解析符號共享（Single-Parse Symbol Sharing）、方言隔離（Dialect Isolation）、C# `partial` 型別雙層無損聚合以及確定性雙向呼叫拓撲分析。

---

## 1. 核心架構與職責

1. **方言隔離與多語言解析 (`ast_engine.dialects` & `ast_engine.parsers`)**：
   - 內建 `DialectAdapter` 介面與 `python`、`c_sharp`、`cpp`、`c`、`javascript`、`typescript`、`markdown` 方言適配器，將註解清理、存取可見度推導、類別外方法作用域反推、接收者正規化與 Import 提取完整封裝。
   - 同時內建 `PythonASTParser`、`MarkdownParser`、`SpiceParser`、`HtmlParser`、`CssParser`，並開放 `contributes/ast.json` (`languages` 擴充點) 供外部模組或專案掛載自訂 Tree-sitter `.scm` 或 Custom Parser。

2. **按需 Grammar 自舉與離線圍欄 (`GrammarProvisioner`)**：
   - 動態載入或安裝 `tree-sitter-*` 語法套件時，所有輸出強制導向 `sys.stderr`，確保 `--json` 標準輸出 100% 純淨。
   - 內建會話級負快取（`_FAILED_PACKAGES`）：離線或安裝失敗時向 `sys.stderr` 發出結構化 `[ast:warn]` 提示並優雅降級，不阻斷管線。

3. **雙層分部符號模型與單次解析快照 (`SemanticBundler` & `ASTSnapshot`)**：
   - 針對 C# `partial class/struct/interface` 同時保存表層跨檔合併邏輯視圖（`members` / `children` / `partial_files`）與底層單檔物理定義（`metadata["_own_*"]`），支援單檔 `outline` 精確檢視與增量退化重聚合。
   - 以 `consumer_id="ast"` 消費 `core.space` 游標，原子持久化 `ast.storage://indices/unified.symbols.bin.gz` 與 `unified.graph.bin.gz`。

4. **四大不可變內核原子結構、4-Pass 確定性工作區連結器與 L0/L1 圖譜原語 (`WorkspaceGraphLinker` & `ASTEngine`)**：
   - 提供 `@dataclass(frozen=True)` 之 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge`、`FileSymbolGraph`、`FileImportTable` 與 `WorkspaceSymbolGraph`，支援多 `.scm` 以 `@name` 物理座標執行交換律合流（$A \cup B = B \cup A$）與 4-Pass 確定性跨檔連結（零啟發式模糊計分）。
   - 提供 L0 無狀態單檔原語（`parse_file`、`outline`、基於 UTF-8 Byte Span 之 $O(1)$ 結構化切片 `slice_part`）與 L1 全倉圖譜原語（`get_workspace_graph`、`resolve`、`select_nodes`、多跳有向邊 BFS `traverse_edges`），以及同父型別同名異載（Overloads）群組展開與跨父型別結構化歧義攔截。

---

## 2. CLI 指令速查

```bash
# 檢視單檔結構化符號大綱（支援可見度/綁定/成員型別三維正交過濾；C# partial 自動提示 [Partial Siblings]，加 --merged 展開合併視圖）
python yscb.py ast outline <file_or_uri> [--merged] [--public|--protected|--internal|--private|--non-private] [--static|--non-static] [--methods|--fields|--types] [--json]

# 無損切取指定符號之結構化源碼部位（<symbol> 支援 "[kind] [scope.]name[(params)]" 或 "<rel_path>::<fqn>"；不支援單冒號 <file>:<symbol>）
python yscb.py ast slice <symbol> [--part <slot>] [--space <name>] [--json]

# 對全倉語意圖譜執行通用有向邊 BFS 遍歷（<symbol> 支援 "[kind] [scope.]name[(params)]" 或 "<rel_path>::<fqn>"）
python yscb.py ast traverse <symbol> [--kind <kinds>] [--direction out|in|both] [--depth <N>] [--space <name>] [--json]

# 查詢調用指定符號之上游調用者與調用點切片
python yscb.py ast callers <symbol> [--space <name>] [--ftype <ext>] [--snippet] [--json]

# 查詢指定符號內部往下游調用的目標符號清單
python yscb.py ast callees <symbol> [--space <name>] [--ftype <ext>] [--snippet] [--json]

# 評估修改指定符號後向上擴散之多階調用影響半徑
python yscb.py ast impact <symbol> [--depth <N>] [--space <name>] [--ftype <ext>] [--json]

# 檢視各空間 AST 快照世代、符號統計與語言解析器狀態
python yscb.py ast status [--space <name>] [--json]

# 清除 AST 快照與呼叫圖譜快取並重置 ast 游標水位
python yscb.py ast clean [--space <name>] [--json]
```

- **增量熱修補與快取一致性**：內建跨進程 `.ast_index.lock` 交易保護、`ast_config_hash` 組態漂移偵測與 CoW 快照無鎖併發讀取。
