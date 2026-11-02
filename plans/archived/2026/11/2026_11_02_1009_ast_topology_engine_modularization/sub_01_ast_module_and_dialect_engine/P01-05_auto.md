# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：建立 `module:ast@1.0.0.0` 靜態語法樹、方言隔離、雙層分部符號與呼叫拓撲核心引擎  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `module:ast@1.0.0.0` 基座與 `DialectAdapter` 方言隔離 | 建立 `ys_codebase/source/ast/`（內部套件 `ast_engine/` 避免遮蔽 Python 標準庫 `ast`），僅依賴 `core` 與 `file-space`。實作 `ast_engine/dialects/`（`python`, `csharp`, `cpp`, `c`, `javascript`, `typescript`, `markdown`）與 `TreeSitterDriver`、領城解析器（`spice`, `html`, `css`）及 `contributes/ast.json` (`languages` 擴充點)，100% 零退化保留既有 AST 解析行為。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | 雙層分部符號模型與單次解析快照 (`ASTSnapshot`) | 實作 `SemanticBundler` 支援 C# `partial class/struct/interface` 雙層無損聚合（表層 `children/members` 為跨檔邏輯聚合視圖，底層 `metadata["_own_*"]` 保留單檔物理屬性）與增量退化重聚合；以 `consumer_id="ast"` 消費 `file-space`，原子持久化 `unified.symbols.bin.gz`（含 `ast_generation`、`space_generations`、`symbols`）與 `unified.graph.bin.gz`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 無 BM25 確定性符號定位器與同名多載群組定址 (`uitk.net` 邊界 ①) | 移除 BM25 依賴，實作確定性三階定位器與參數簽名選擇器 `[kind] [scope.]name[(param_types...)]`；`TopologyLinker._by_fqn` 支援同 FQN 多重載列表；當查詢命中同一父型別 `(space, parent_fqn)` 下的多個重載時預設群組化一併展開（列出各重載簽名、行號與聯集拓撲），跨不同父型別時返回結構化歧義清單。 | P0 | [P00:DR-03] |
| **FR-04** | `yscb ast outline` 單檔大綱、`[Partial Siblings]` 提示與三維度正交過濾 (`uitk.net` 邊界 ②, `[REV-01]`) | 實作 `yscb ast outline <file_or_uri> [--merged] [--public\|--protected\|--internal\|--private\|--non-private] [--static\|--non-static] [--methods\|--fields\|--types] [--json]`，輸出檔案內階層化符號大綱（Kind、Visibility、`[static]`、Signature、行號區間 `Lstart-Lend`）；支援可見度 (`visibility`)、綁定 (`binding`) 與成員型別 (`member_kind`) 三維度正交過濾（保留有匹配子成員之父容器）；檢測到 `partial` 型別在同空間存在其他分部檔時，預設顯示本檔 `_own_members` 並自動附帶 `[Partial Siblings]` 列出其餘分部檔案與成員數（`--merged` 展開全分部合併成員）。 | P0 | [P00:DR-04], [REV-01] |
| **FR-05** | 按需 Grammar 自舉之 `stderr` 純淨度與離線圍欄 (`uitk.net` 邊界 ③) | 實作 `GrammarProvisioner`，動態安裝輸出 100% 導向 `sys.stderr`；離線或安裝失敗時記錄會話級負快取、向 `stderr` 輸出結構化 Warning 並優雅略過該語言，保證 `--json` 輸出 100% 純淨。 | P0 | [P00:DR-05] |
| **FR-06** | `yscb ast` CLI 家族與 `hook.file-space.py` 熱自癒 (`uitk.net` 邊界 ④) | 提供 `yscb ast <outline|callers|callees|impact|status|clean>` 6 個 CLI 指令（支援 `--snippet`、`--depth`、`--space`、`--ftype`、`--json`）與 `scripts/hook.file-space.py`（訂閱 `on_file_space_changed` 自動熱修補並廣播 `on_ast_index_updated`）。 | P0 | [P00:DR-01], [P00:DR-03], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 查詢 `Window.Open` 命中 `Window` 類別下 3 個不同參數簽名之 `Open` 重載 | 判定屬於同一 `(space, parent_fqn)`，不報歧義錯誤，群組化列出 3 個重載簽名與聯集 `callers/callees/impact`；若同時支援 `Window.Open(string)` 則精確過濾單一重載。 |
| **EC-02** | 查詢 `Open` 同時命中 `UI.Window.Open` 與 `IO.File.Open` 兩個不同父型別 | 判定跨不同父型別，拒絕盲猜，回傳結構化歧義清單（含完整 FQN、簽名與 `file:line`）。 |
| **EC-03** | 對單一 C# 分部檔 `Window.cs` 執行 `yscb ast outline` | 僅列出 `Window.cs` 內定義之 `_own_members`，並於輸出附帶 `partial_siblings`（如 `Window.Lifecycle.cs`, `Window.Dragging.cs`）。 |
| **EC-04** | 無網路環境下遇到未安裝 Grammar 之語言檔案並執行 `yscb ast outline --json` | 安裝失敗日誌與 Warning 100% 輸出至 `stderr`，`stdout` 維持 100% 合法 JSON，且同一會話不重複重試安裝。 |
| **EC-05** | 修改單一檔案後立即呼叫 `yscb ast callers <symbol>` | `ASTEngine.ensure_jit_synced()` 自動透過 `file-space` (`consumer_id="ast"`) 偵測 dirty diff，局部重解析該檔、重聚合受影響 `partial` 群組、縫合 `CallGraph` 入度邊並推進 `ast_generation`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴隔離 | `module:ast` 100% 不依賴 `knowledge-db`、`onnxruntime`、`tokenizers` 或任何 BM25/向量檢索套件；內部套件命名為 `ast_engine` 絕不遮蔽 Python 標準庫 `ast`。 |
| **NFR-02** | 效能 / I/O | 單檔 `yscb ast outline <file>` 在無需跨分部查詢或快照已就緒時 $\le 50\text{ms}$ 完成。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** Python 標準庫內建 `import ast` 模組（`PythonASTParser` 內部即使用 `import ast as py_ast`）。因此 `ys_codebase/source/ast/` 下的 Python 套件目錄必須命名為 `ast_engine/`（同時在 `ys_codebase/source/ast/__init__.py` 匯出 `ASTEngine` 等門面 API），嚴禁建立 `ys_codebase/source/ast/ast/` 子目錄以免將 `source/ast` 加入 `sys.path` 時遮蔽標準庫 `ast`！
- **`[!NOTE]`** `UnifiedSymbol.compute_id` 針對方法/函式須兼顧重載區分與同行號修改穩定性：對同名同起始行號之符號維持穩定 ID，若同一父型別下存在同名但不同行號的重載，因 `line_number` 不同天然具備不同 ID；若同一行定義多個重載則輔以參數簽名區分，並將 `TopologyLinker._by_fqn` 改為 `Dict[str, List[UnifiedSymbol]]` 以完整保存所有重載。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
ys_codebase/source/ast/
  ├── manifest.json (id: "ast", version: "1.0.0.0", dependencies: core, file-space)
  ├── __init__.py (Export public facade: ASTEngine, outline, callers, callees, impact, ensure_jit_synced, ...)
  ├── contributes/
  │   ├── _format.json (languages extension point)
  │   ├── core.json (uri_schemes: ast.storage:// -> cache://ast/, cli: ast)
  │   └── file-space.json
  ├── assets/queries/*.scm (python, c_sharp, cpp, c, javascript, typescript, markdown)
  ├── ast_engine/
  │   ├── __init__.py
  │   ├── schema.py (UnifiedSymbol, SymbolKind, MemberInfo, SymbolCallSite, ASTSnapshot, OutlineResult, ...)
  │   ├── exceptions.py (ASTError, SymbolNotFoundError, AmbiguousSymbolError, ...)
  │   ├── io_utils.py (atomic_save_gzip_pickle, load_gzip_pickle, is_dirty_file_match)
  │   ├── provisioner.py (GrammarProvisioner with stderr isolation & offline negative cache)
  │   ├── dialects/
  │   │   ├── __init__.py
  │   │   ├── base.py (DialectAdapter)
  │   │   ├── python.py, csharp.py, cpp.py, c.py, javascript.py, typescript.py, markdown.py
  │   ├── parsers/
  │   │   ├── __init__.py, base.py, registry.py, python_ast.py, treesitter.py, markdown.py
  │   │   └── spice_parser.py, html_parser.py, css_parser.py
  │   ├── bundler.py (SemanticBundler, Two-Tier Partial Symbol aggregation & incremental restore)
  │   ├── linker.py (TopologyLinker with _by_fqn overload list support & 4-tier resolution)
  │   ├── graph.py (CallGraphIndex)
  │   ├── resolver.py (DeterministicSymbolResolver with signature filtering & overload grouping)
  │   ├── engine.py (ASTEngine: ensure_jit_synced, outline, callers, callees, impact, get_snapshot)
  │   └── formatter.py (CLI & JSON formatters for outline/callers/callees/impact/status)
  ├── scripts/
  │   ├── cli.py (yscb ast <outline|callers|callees|impact|status|clean>)
  │   ├── hook.file-space.py (on_file_space_changed -> hot-patch & emit on_ast_index_updated)
  │   └── hook.dev.py
  └── tests/
      ├── test_dialects_and_parsers.py
      ├── test_partial_and_outline.py
      ├── test_overload_and_topology.py
      └── test_provisioner_and_jit.py
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/manifest.json` | New | `module:ast@1.0.0.0` 模組宣告（依賴 `core`、`file-space`） |
| `ys_codebase/source/ast/README.md` | New | 隨包模組說明手冊 |
| `ys_codebase/source/ast/contributes/_format.json` | New | 定義 `languages` 擴充點 Schema（含 `\| merge` 策略） |
| `ys_codebase/source/ast/contributes/_manifest.md` | New | Contributes 契約說明文檔 |
| `ys_codebase/source/ast/contributes/core.json` | New | 註冊 `ast.storage://` URI 與 `yscb ast <outline\|callers\|callees\|impact\|status\|clean>` CLI |
| `ys_codebase/source/ast/assets/queries/*.scm` | New | 7 種官方語言 Tree-sitter S-expression 查詢檔 |
| `ys_codebase/source/ast/ast_engine/__init__.py` | New | 內部核心引擎套件入口 |
| `ys_codebase/source/ast/ast_engine/schema.py` | New | `UnifiedSymbol`、`SymbolCallSite`、`ASTSnapshot`、`OutlineNode`、`OutlineResult` 資料契約 |
| `ys_codebase/source/ast/ast_engine/exceptions.py` | New | `ASTError`、`SymbolNotFoundError`、`AmbiguousSymbolError` 結構化異常 |
| `ys_codebase/source/ast/ast_engine/io_utils.py` | New | Gzip+Pickle 原子持久化與路徑比對工具 |
| `ys_codebase/source/ast/ast_engine/provisioner.py` | New | `GrammarProvisioner` 按需安裝、`stderr` 隔離與離線降級圍欄 |
| `ys_codebase/source/ast/ast_engine/dialects/*.py` | New | `DialectAdapter` 基底與 `python`/`csharp`/`cpp`/`c`/`javascript`/`typescript`/`markdown` 方言隔離實作 |
| `ys_codebase/source/ast/ast_engine/parsers/*.py` | New | `ParserRegistry`、零語言特判之 `TreeSitterDriver`、`PythonASTParser`、`MarkdownParser`、`SpiceParser`、`HtmlParser`、`CssParser` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | New | `SemanticBundler` 與 C# `partial` 雙層無損聚合及增量熱修補還原 |
| `ys_codebase/source/ast/ast_engine/linker.py` | New | `TopologyLinker` 四階消歧與 `_by_fqn: Dict[str, List[UnifiedSymbol]]` 重載列表支援 |
| `ys_codebase/source/ast/ast_engine/graph.py` | New | `CallGraphIndex` 雙向呼叫圖譜與增量外部入度邊重連 |
| `ys_codebase/source/ast/ast_engine/resolver.py` | New | `DeterministicSymbolResolver` 無 BM25 三階定位、參數簽名過濾與同父型別 Overload 群組展開 |
| `ys_codebase/source/ast/ast_engine/engine.py` | New | `ASTEngine`（`ensure_jit_synced`、`outline`、`callers`、`callees`、`impact`、`get_snapshot`、`status`、`clean`） |
| `ys_codebase/source/ast/ast_engine/formatter.py` | New | `outline`（含 `[Partial Siblings]`）、`callers`、`callees`、`impact`、`status` 終端與 JSON 格式化器 |
| `ys_codebase/source/ast/scripts/cli.py` | New | `yscb ast` CLI 路由實作 |
| `ys_codebase/source/ast/scripts/hook.file-space.py` | New | 訂閱 `on_file_space_changed` 自動執行增量同步並廣播 `on_ast_index_updated` |
| `ys_codebase/source/ast/scripts/hook.dev.py` | New | 模組開發檢查與預熱 Hook |
| `ys_codebase/source/ast/tests/test_*.py` | New | 涵蓋方言解析、`partial` 雙層聚合、`outline` 姊妹檔提示、Overload 群組定址、離線 Grammar 圍欄與 JIT 熱自癒之完整測試集 |
| `ys_codebase/config/ast/contribute.json` | New | 宿主專案 `ast` 語言擴充宣告（遷移自 `config/knowledge-db/contribute.json`） |
| `docs/ast/README.md` | New | `module:ast` 系統知識庫模組手冊 |
| `docs/ast/DESIGN_NOTES.md` | New | `module:ast` 架構決策與工程妥協紀錄 (`[DN-AST-01]` ~ `[DN-AST-04]`) |
| `CHANGELOG.md` | Modify | 記錄 `sub_01` `module:ast@1.0.0.0` 建置摘要 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 內部套件目錄命名為 `ast_engine`（並於頂層 `__init__.py` 暴露門面），彻底避免與 Python 標準庫 `import ast` 發生模組遮蔽。
- **[P02:DR-02]** `ASTSnapshot` 持久化於 `ast.storage://indices/unified.symbols.bin.gz`，內含 `ast_generation: int`、`space_generations: Dict[str, int]`、`symbols: Dict[str, UnifiedSymbol]` 與 `file_to_symbol_ids: Dict[str, List[str]]`，供 `sub_02` 的 `knowledge-db` O(1) 讀取共享。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/ast/ast_engine/dialects/base.py
class DialectAdapter:
    language: str
    scope_separator: str = "."
    supports_partial_aggregation: bool = False

    def clean_docstring(self, raw_comment: str) -> str: ...
    def extract_visibility(self, node: Any, source_bytes: bytes, parent_kind: Optional[str], default_vis: str) -> str: ...
    def resolve_out_of_line_scope(self, name: str, parent_scope: str) -> Tuple[str, str]: ...
    def extract_imports(self, source_text: str, file_path: str) -> List[str]: ...

# ys_codebase/source/ast/ast_engine/resolver.py
@dataclass
class SymbolResolutionResult:
    status: str  # "matched" | "overload_group" | "ambiguous" | "not_found"
    targets: List[UnifiedSymbol] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    query: str = ""

class DeterministicSymbolResolver:
    def resolve(
        self,
        query: str,
        symbols: Dict[str, UnifiedSymbol],
        spaces: Optional[List[str]] = None,
        ftypes: Optional[List[str]] = None,
    ) -> SymbolResolutionResult: ...

# ys_codebase/source/ast/ast_engine/engine.py
class ASTEngine:
    def ensure_jit_synced(self, spaces: Optional[List[str]] = None, force: bool = False) -> ASTSnapshot: ...
    def get_snapshot(self, auto_sync: bool = True) -> ASTSnapshot: ...
    def outline(self, file_or_uri: str, merged: bool = False, visibility: Optional[str] = None, binding: Optional[str] = None, member_kind: Optional[str] = None) -> Dict[str, Any]: ...
    def callers(self, symbol_query: str, spaces: Optional[List[str]] = None, ftypes: Optional[List[str]] = None, include_snippet: bool = False) -> Dict[str, Any]: ...
    def callees(self, symbol_query: str, spaces: Optional[List[str]] = None, ftypes: Optional[List[str]] = None, include_snippet: bool = False) -> Dict[str, Any]: ...
    def impact(self, symbol_query: str, depth: int = 2, spaces: Optional[List[str]] = None, ftypes: Optional[List[str]] = None) -> Dict[str, Any]: ...
    def status(self, space_name: Optional[str] = None) -> Dict[str, Any]: ...
    def clean(self, space_name: Optional[str] = None) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當 `callers`/`callees`/`impact` 遭遇跨不同父型別之同名歧義時，返回結構化 `status="ambiguous"` 與 `candidates` 清單（CLI 輸出清晰候選簽名與 `file:line` 指引，不盲猜首項）。
  - 當 `GrammarProvisioner` 於離線環境無法安裝某語言 Grammar 時，記錄 Warning 至 `stderr` 並返回空符號集，不中斷其他語言解析或破壞 `--json` stdout。
- **階段決策紀錄**：`[P03:DR-01]` `ASTEngine.get_snapshot(auto_sync=True)` 作為下游 `knowledge-db` Single-Parse Symbol Sharing 之唯一正統資料源介面。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-05 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束（零 BM25/ONNX 依賴、零標準庫 `ast` 遮蔽）
- **靈魂拷問與防護解法**：
  - *問：若對工作區內某單一 `partial class` 檔案執行 `yscb ast outline <file>`，但此時 `ASTSnapshot` 尚未建立，如何得知其 `[Partial Siblings]`？*
  - *答*：若目標檔案所屬空間之 `ASTSnapshot` 尚未建立或處於 dirty，且該檔解析出 `is_partial=True` 的符號時，`ASTEngine.outline()` 自動觸發該空間的 `ensure_jit_synced(spaces=[space_name])` 以獲取完整的同 FQN `partial_files` 姊妹檔清單；若為非 `partial` 普通檔案且快照未建立，則可直接單檔即時解析（0 索引等待）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md` | New | `module:ast` 模組定位、方言隔離、雙層分部符號與 CLI/SDK 手冊 |
| **專題手冊** | `docs/knowledge-db/README.md` | N/A | 留待 `sub_02` / `sub_03` 遷移完成後一併同步 |
| **設計決策** | `docs/ast/DESIGN_NOTES.md` | New | 登記 `[DN-AST-01]` ~ `[DN-AST-04]`（`ast_engine` 防遮蔽、方言隔離、Overload 群組定址、`outline` 姊妹檔提示） |
| **微觀註解** | `ys_codebase/source/ast/ast_engine/*.py` | New | 完整撰寫公開類別與方法 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_01` `module:ast@1.0.0.0` 建置摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `P01-05_auto.md` 規格鎖定，進入 Pre-Code Analyze Gate 與分區實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `ys_codebase/source/ast/` 模組骨架、`manifest.json`、`contributes/{_format,core,file-space}.json`、`assets/queries/*.scm`、`ast_engine/{schema,exceptions,io_utils,provisioner}.py`、`ast_engine/dialects/*.py` 與 `ast_engine/parsers/*.py`
- [x] **TASK-02**：實作 `ast_engine/{bundler,linker,graph,resolver,engine,formatter}.py` 與 `scripts/{cli,hook.file-space,hook.dev}.py` 及 `ys_codebase/config/ast/contribute.json`
- [x] **TASK-03**：撰寫 `ys_codebase/source/ast/tests/test_*.py` 完整單元與邊界測試套件（覆蓋 FR-01~FR-06 與 EC-01~EC-05），通過 `dev check ast`、`dev test ast` 與 `install ast@build`
- [x] **TASK-DOC**：建立 `docs/ast/README.md`、`docs/ast/DESIGN_NOTES.md` 與更新 `CHANGELOG.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-01 | Minor | 實機驗證發現若於 `ys_codebase/source/ast/` 模組根目錄放置 `__init__.py`，當 `server` Warm Worker 將 `.modules` 加入 `sys.path` 時會使 `.modules/ast` 被視為名為 `ast` 的頂層 Python 套件並遮蔽標準庫 `import ast`（引發 `dataclasses` -> `inspect` -> `ast` 循環匯入錯誤）；因此移除根目錄 `__init__.py`，統一將公開 SDK 門面匯出收斂於 `ast_engine/__init__.py`，與其他模組（`file-space`、`knowledge-db`）保持一致。 | 已同步更新 `P01-05_auto.md` 檔案清單與 `docs/ast/DESIGN_NOTES.md` (`[DN-AST-01]`) |

