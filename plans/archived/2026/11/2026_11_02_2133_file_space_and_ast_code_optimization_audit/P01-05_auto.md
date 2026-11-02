# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：file-space 與 ast 模組業務代碼五維度靜態診斷與重構審計  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_2133_file_space_and_ast_code_optimization_audit  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `module:file-space` 過渡別名、孤兒死代碼與舊模組名殘留拔除 (`Mode A` / `S5` / `S2`) | 1. 拔除 `file_space/schema.py` 與 `file_space/__init__.py` 之 `FileSpaceDef = FileSpaceConfig` 別名、`FileFingerprint` 舊建構子別名參數（`relpath, mtime, sha1`）與唯讀別名屬性（`.relpath, .mtime, .sha1`）、`ScanDiffResult.__init__` 舊參數（`added, modified, deleted, unchanged`）；同步將 `ys_codebase/source/knowledge-db/tests/test_file_space.py` 之 `FileSpaceDef` 改為正統 `FileSpaceConfig`。<br/>2. 拔除 `file_space/manager.py` 之 `"knowledge-db"` / `config://knowledge-db/contribute.json` 舊組態空間回退分支、1 行別名 `get_space_config` 與孤兒死代碼 `get_space_storage_dir`。<br/>3. 拔除 `file_space/scanner.py` 之 `BinarySnapshotManager.save / load` 舊 tuple/dict 轉發包裝、6 個孤兒方法（`scan_all`、`scan_all_spaces`、`compute_diff`、`check_invalidation`、`save_snapshot`、`load_snapshot`）與 `ack()` 之 `consumer=None` 別名參數。<br/>4. 拔除 `file_space/providers.py` 之 `get_file_space_names`、`get_space_names`、`get_registered_spaces_table` 別名，並將 `ys_codebase/source/file-space/tests/test_service_and_cli.py` 對齊至正統 `get_registered_file_spaces_table`。<br/>5. 拔除 `file_space/service.py` 未讀取之 `self._watcher_active` 與 `scripts/cli.py` 未讀取之 `scanner.mgr_check`；將 `scripts/hook.dev.py` 殘留之 `"space"` / `.cache/space` 正名為 `"file-space"` / `.cache/file-space`。 | P0 | [P00:DR-01], [P00:DR-02], [P00:DR-04] |
| **FR-02** | `module:file-space` 跨檔循環依賴解耦、階段拆解與原子寫入收斂 (`S1` / `S2` / `S3`) | 1. 解耦 `file_space/scanner.py` 與 `file_space/service.py` 之雙向延遲匯入：將輕量級 Watcher 存活探針提取或收斂至基礎設施層（或 `scanner.py` / 獨立工具函式），使 `service.py -> scanner.py` 維持嚴格單向依賴，`scanner.py` 零匯入 `service.py`。<br/>2. 於 `file_space/scanner.py` 提煉 `_atomic_write_bytes(target_path: Path, payload: bytes)` 共用輔助函式，消除 `BinarySnapshotManager.save_state` 與 `CursorStore.set_cursor` 間重複的 `tempfile.mkstemp + fsync + os.replace` 樣板。<br/>3. 將 `FileSpaceManager.load_spaces` 與 `FingerprintScanner.scan_space` 拆解為職責單一之階段子函式，主調度函式體積顯著收斂且早期返回（Guard Clauses）扁平化。 | P0 | [P00:DR-01], [P00:DR-02], [P00:DR-04] |
| **FR-03** | `module:ast` 頂層薄轉發殼層、過渡別名與孤兒死代碼拔除 (`Mode A` / `S2` / `S5`) | 1. 拔除 `ast_engine/__init__.py`（及對應頂層匯出）8 個零引用之純轉發函式（`outline`、`callers`、`callees`、`impact`、`ensure_jit_synced`、`get_snapshot`、`status`、`clean`），僅保留 `get_engine`、`reset_default_engine` 與核心資料類別匯出。<br/>2. 拔除 `ast_engine/formatter.py` 零引用之 `AUTO_BUDGET_CHARS` 常數群與 `compute_dynamic_snippet_lines`、模組頂層 `format_*` 轉發包裝、`ASTResultFormatter.format_* = staticmethod(...)` 動態掛載與 `ASTFormatter` 別名；同步將 `tests/test_overload_and_topology.py` 與 `tests/test_partial_and_outline.py` 對齊至 `ASTResultFormatter().format_*_output(...)`。<br/>3. 於 `ast_engine/schema.py` 移除 `OutlineNode.to_dict()` 重複輸出的 `"children"` 鍵（統一以 `"members"` 為正統鍵，`from_dict` 優先讀取 `"members"`），並拔除零引用之 `ASTContributes` 與從未賦值之 `ASTSnapshot.space_stats`（同步清理測試中對該死欄位的無效斷言）。<br/>4. 拔除 `ast_engine/exceptions.py` 從未拋出之 3 個孤兒例外類別（`SymbolNotFoundError`、`AmbiguousSymbolError`、`ParserLoadError`）。<br/>5. 拔除 `SemanticBundler.bundle_space`、`import_bundle`、`TopologyLinker._overloads_by_fqn`、`resolve_call_site` 舊相容參數 `file_symbols`、`SymbolSelector.find_matches`、`GrammarProvisioner.get_instance` 以及 `ParsedSelector` 重複別名屬性/字典鍵，同步對齊 `tests/test_overload_and_topology.py`。 | P0 | [P00:DR-01], [P00:DR-02], [P00:DR-04] |
| **FR-04** | `module:ast` 巨型方法階段拆解、無狀態純函式外提與跨模組殘留清理 (`S1` / `S2` / `S3` / `S5`) | 1. 將 `ASTEngine.outline` 內部 5 個深層巢狀閉包外提為模組級無狀態純函式（`_member_to_outline_node`、`_build_outline_tree`、`_filter_outline_nodes` 等），使 `ASTEngine.outline` 收斂為清晰的三階段主流程調度器。<br/>2. 將 `ASTEngine.hot_patch_index` 拆解為 `_evict_dirty_and_reaggregate_partials` 與 `_relink_and_reconnect_edges` 兩大階段子函式；並讓 `ASTEngine._build_or_load_space_index` 直接復用 `TopologyLinker.build_graph`。<br/>3. 將 `scripts/cli.py` 之 `_run_topology_cli_command` 內嵌 JSON 序列化邏輯抽離為專用 helper；收斂 `ast_engine/bundler.py` 與 `ast_engine/io_utils.py` 之專案根目錄與相對路徑正規化邏輯，並合併 `bundler.py` 單檔解析 + `ensure_unique_overload_ids` 重複區塊。<br/>4. 將 `SpiceParser` 內部無狀態 `_split_tokens` 與 `_parse_params_from_line` 外提為模組級純函式（不留類別轉發空殼）。<br/>5. 拔除 `ast_engine/parsers/treesitter.py` 向上探測 `knowledge-db/assets/queries` 之跨模組耦合分支與 `ast_engine/parsers/registry.py` 之 `knowledge_db.parsers.` 字串轉換；全面清除兩模組源碼中殘留之歷史工單與遷移標記註解。 | P0 | [P00:DR-01], [P00:DR-02], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 移除 `OutlineNode.to_dict()` 的 `"children"` 雙重鍵後，舊快取或測試反序列化仍可能傳入 `"children"` 或 `"members"` | `OutlineNode.from_dict()` 支援 `data.get("members") or data.get("children", [])`，而 `to_dict()` 與 `ASTResultFormatter` 100% 統一讀寫 `"members"`，確保序列化零冗餘且反序列化安全。 |
| **EC-02** | 解耦 `scanner.py` 對 `service.py` 的延遲匯入時，背景 Daemon Watcher 存活探測與 CLI 自動對齊行為不可改變 | 將 `is_watcher_active(project_root)` 的 lock/status 檔案探測邏輯下沉至不依賴 `service.py` 的獨立位置（如 `scanner.py` 或共用基礎設施），`service.py` 反向匯入使用，確保 `ensure_synced` 與 `status` 探測行為 100% 一致且無循環匯入。 |
| **EC-03** | 拔除 `Mode A` 過渡別名（如 `FileSpaceDef`、`format_outline`、`resolve_call_site(..., file_symbols=...)`）時引發測試或下游匯入失敗 | 嚴格按照 `R01_code_optimization_audit.md` 雙重查證清單，同步更新 `file-space/tests/`、`ast/tests/` 與 `knowledge-db/tests/test_file_space.py` 之調用點至單一正統入口，並通過全套回歸測試驗證。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 行為無損與測試全綠 | `dev check` 與 `dev test` 於 `file-space` (15/15)、`ast` (18/18)、`knowledge-db` (103/103) 與 `agents-workflow` (141/141) 100% 通過。 |
| **NFR-02** | 架構純淨度與防膨脹 | 兩模組總體業務代碼行數（LOC）實現淨縮減（預期淨減 > 450 LOC），消滅所有 > 120 LOC 的巨型混合方法，零殘留轉發空殼（`S2`）與工單編號註解（`S5`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `file-space` 目前僅存在於本地 `.build/` 開發產物區（尚未發布至 `./ys_codebase/release`），因此在重構完成執行熱部署安裝時，必須將 `file-space@build`、`ast@build` 與 `knowledge-db@build` 一併列入 `python yscb.py install file-space@build ast@build knowledge-db@build --force`。
- **`[!NOTE]`** 依據 `CodeQualityStandards.md`，重構後的所有註解與 Docstring 嚴禁出現任何 `D1~D5`、`S1~S6`、`FR-XX`、`M-03`、`R01` 等審計代號或歷史遷移標記。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
Layer 3: module:knowledge-db (Hybrid Retrieval & FTS5/Vector Index)
   │  (imports canonical FileSpaceConfig,ASTEngine,ASTResultFormatter)
   ▼
Layer 2: module:ast (Tree-sitter / Spice / Partial Symbols / Call Graph)
   ├── ast_engine/engine.py       (Orchestrator -> delegates to pure outline & hot-patch stage helpers)
   ├── ast_engine/linker.py       (TopologyLinker.build_graph & single-signature resolve_call_site)
   ├── ast_engine/bundler.py      (SemanticBundler -> unified single-file parse & io_utils path helpers)
   ├── ast_engine/formatter.py    (ASTResultFormatter canonical format_*_output methods)
   └── ast_engine/parsers/        (Pure module-level Spice token helpers & self-contained Tree-sitter queries)
   │
   ▼
Layer 1: module:file-space (Workspace Discovery, Binary Snapshot & Watcher)
   ├── file_space/service.py      (Daemon/Service Layer -> imports is_watcher_active from scanner)
   ├── file_space/scanner.py      (FingerprintScanner + BinarySnapshotManager + CursorStore + _atomic_write_bytes + is_watcher_active)
   ├── file_space/manager.py      (FileSpaceManager -> stage-decomposed load_spaces, pure file-space contributes)
   └── file_space/schema.py       (Canonical FileSpaceConfig, FileFingerprint, ScanDiffResult)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/file-space/file_space/__init__.py` | Modify | 移除 `FileSpaceDef` 過渡別名匯出，保持公開介面精簡正統 |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 移除 `FileSpaceDef`、`FileFingerprint` 舊建構子別名與唯讀屬性、`ScanDiffResult.__init__` 舊參數分支 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 移除 `"knowledge-db"` 舊組態空間回退、`get_space_config`、`get_space_storage_dir`，並將 `load_spaces` 階段拆解為清晰子函式 |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 提煉 `_atomic_write_bytes`、下沉 `is_watcher_active` 解除對 `service.py` 循環匯入、將 `scan_space` 階段拆解，並移除 `BinarySnapshotManager.save/load` 與 `FingerprintScanner` 6 個孤兒方法 |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | 改由 `scanner.py` 匯入 `is_watcher_active`，移除未讀取之 `self._watcher_active` 死狀態寫入 |
| `ys_codebase/source/file-space/file_space/providers.py` | Modify | 移除 `get_file_space_names`、`get_space_names`、`get_registered_spaces_table` 別名，僅保留正統 `get_registered_file_spaces_table` |
| `ys_codebase/source/file-space/scripts/cli.py` | Modify | 移除未讀取之 `scanner.mgr_check` 動態屬性掛載 |
| `ys_codebase/source/file-space/scripts/hook.dev.py` | Modify | 修正殘留之 `"space"` 模組名與 `.cache/space` 快取路徑為 `"file-space"` 與 `.cache/file-space` |
| `ys_codebase/source/file-space/tests/test_service_and_cli.py` | Modify | 對齊 `get_registered_spaces_table` 測試呼叫點至正統 `get_registered_file_spaces_table` |
| `ys_codebase/source/knowledge-db/tests/test_file_space.py` | Modify | 對齊 `FileSpaceDef` 測試匯入至正統 `FileSpaceConfig` |
| `ys_codebase/source/ast/__init__.py` | Modify | 移除頂層 8 個零引用之純轉發函式匯出 |
| `ys_codebase/source/ast/ast_engine/__init__.py` | Modify | 移除 8 個零引用之頂層轉發函式與未拋出之例外匯出 |
| `ys_codebase/source/ast/ast_engine/exceptions.py` | Modify | 移除從未拋出之 `SymbolNotFoundError`、`AmbiguousSymbolError`、`ParserLoadError` |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 移除 `OutlineNode.to_dict()` 重複之 `"children"` 鍵、零引用之 `ASTContributes` 與死欄位 `ASTSnapshot.space_stats` |
| `ys_codebase/source/ast/ast_engine/io_utils.py` | Modify | 收斂共用之專案根目錄探測與相對路徑正規化輔助函式 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 外提 `outline()` 內部 5 個巢狀閉包為模組級純函式、拆解 `hot_patch_index` 為階段子函式、復用 `TopologyLinker.build_graph` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 移除 `bundle_space` 與 `import_bundle` 孤兒函式、收斂單檔解析 + `ensure_unique_overload_ids` 重複邏輯、復用 `io_utils` 路徑函式 |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | 移除死狀態 `self._overloads_by_fqn`、移除 `resolve_call_site` 之舊相容參數 `file_symbols` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 移除 `SymbolSelector.find_matches` 孤兒方法與 `ParsedSelector` 重複別名屬性/字典鍵 |
| `ys_codebase/source/ast/ast_engine/formatter.py` | Modify | 移除 `AUTO_BUDGET_CHARS`、`compute_dynamic_snippet_lines`、頂層 `format_*` 包裝、動態 `staticmethod` 掛載與 `ASTFormatter` 別名 |
| `ys_codebase/source/ast/ast_engine/provisioner.py` | Modify | 移除零引用之 `GrammarProvisioner.get_instance` |
| `ys_codebase/source/ast/ast_engine/parsers/spice_parser.py` | Modify | 將無狀態 `_split_tokens` 與 `_parse_params_from_line` 外提為模組級純函式 |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 移除向上探測 `knowledge-db/assets/queries` 之跨模組耦合分支與歷史遷移註解 |
| `ys_codebase/source/ast/ast_engine/parsers/registry.py` | Modify | 移除 `knowledge_db.parsers.` 舊路徑字串轉換與歷史遷移註解 |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 提煉 `_run_topology_cli_command` 內嵌之 JSON 序列化輔助函式 |
| `ys_codebase/source/ast/tests/test_overload_and_topology.py` | Modify | 對齊 `ASTResultFormatter().format_callers_output`、`resolve_call_site` 簽名、`ParsedSelector` 正統屬性與移除 `space_stats` 斷言 |
| `ys_codebase/source/ast/tests/test_partial_and_outline.py` | Modify | 對齊 `ASTResultFormatter().format_outline_output` 正統方法呼叫 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `scanner.py` 與 `service.py` 單向依賴收斂**：`is_watcher_active(project_root: Path) -> bool` 僅讀取 `.cache/file-space/daemon.json` 並以 `os.kill(pid, 0)` 檢查處理序存活，完全不依賴 `FileSpaceDaemon` 類別實作。將 `is_watcher_active` 移入 `scanner.py`（並由 `service.py` 匯入復用），即可徹底斬斷 `scanner.py -> service.py` 的反向延遲匯入，達成 `service.py -> scanner.py` 100% 單向無環。
- **[P02:DR-02] `OutlineNode.to_dict()` 單一正統鍵 `"members"`**：先前為過渡相容同時輸出 `"members"` 與 `"children"` 導致序列化字典膨脹一倍。收斂為 `to_dict()` 僅輸出 `"members"`，`from_dict()` 保留 `data.get("members") or data.get("children", [])` 寬進嚴出。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/file-space/file_space/scanner.py
def _atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """Write bytes to a temporary sibling file, fsync, and atomically replace target_path."""

def is_watcher_active(project_root: Optional[Path] = None) -> bool:
    """Return True if a background file-space watcher process is alive for project_root."""

# ys_codebase/source/ast/ast_engine/linker.py
class TopologyLinker:
    def resolve_call_site(
        self,
        call_site: CallSite,
        caller_symbol: Optional[SymbolNode] = None,
    ) -> Optional[str]:
        """Resolve a call site to a target symbol overload_id within the indexed symbol table."""

# ys_codebase/source/ast/ast_engine/engine.py
def _member_to_outline_node(member: SymbolNode) -> OutlineNode: ...
def _build_outline_tree(symbols: List[SymbolNode], merged_partials: List[MergedPartialSymbol]) -> List[OutlineNode]: ...
def _filter_outline_nodes(
    nodes: List[OutlineNode],
    symbol_query: Optional[str],
    max_depth: Optional[int],
    current_depth: int = 1,
) -> List[OutlineNode]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：所有公開 API 與 CLI 指令之錯誤碼、例外類別（`ASTEngineError`、`DialectNotSupportedError`、`GrammarNotReadyError`）及失敗降級行為維持 100% 恆等不變。
- **階段決策紀錄**：`[P03:DR-01]` 嚴格執行 `Mode A` 單一正統入口收斂，所有被拔除之過渡包裝函式均不保留 pass-through 空殼。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已完整涵蓋 `R01_code_optimization_audit.md` 中 `module:file-space` 與 `module:ast` 的全部 `Mode A` 處方。
- [x] **邊界防護**：EC-01 ~ EC-03 已針對序列化相容、Watcher 探針單向化與測試呼叫點同步建立明確防護。
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束，無新增任何外部或跨模組依賴。
- **靈魂拷問與防護解法**：
  - *問：`knowledge-db` 生產代碼是否有呼叫 `ast_engine` 頂層 `outline/callers` 或 `FileSpaceDef`？*
  - *答*：經 `ast callers` 與 `knowledge-db search` 全倉雙重查證，`knowledge-db` 生產代碼 100% 透過 `ASTEngine` 實例與 `FileSpaceConfig` 呼叫；僅 `ys_codebase/source/knowledge-db/tests/test_file_space.py` 引用了 `FileSpaceDef` 別名，已列入同步更新清單。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/System/README.md` | N/A | 外部 CLI 與核心類別契約未變，無需異動 |
| **專題手冊** | `docs/System/Architecture.md` | N/A | 模組層級拓撲維持三層單向 DAG，無需異動 |
| **設計決策** | `docs/System/DESIGN_NOTES.md` | N/A | 內部實現純化與過渡死代碼清理，無新增特殊工程妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 清除歷史遷移與工單標記註解，同步更新正統介面 Docstrings |
| **發布日誌** | `CHANGELOG.md` | N/A | 屬於模組內部代碼純化，於計畫 `P07_walkthrough.md` 記錄量化成果 |

- **決策定稿**：**[P04:DR-01]** 確認 `P01-05_auto.md` 規格定稿，立即啟動 `Pre-Code Analyze Gate` 盲審並推進 `TASK-01` ~ `TASK-03`。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：執行 `module:file-space` (`ys_codebase/source/file-space/` 與 `knowledge-db/tests/test_file_space.py`) `Mode A` 死代碼與別名拔除、`scanner <-> service` 循環匯入解耦、`_atomic_write_bytes` 提煉及 `load_spaces` / `scan_space` 階段拆解（對應 `FR-01`, `FR-02`）
- [x] **TASK-02**：執行 `module:ast` (`ys_codebase/source/ast/`) `Mode A` 死代碼與薄轉發殼層拔除、`ASTEngine.outline` / `hot_patch_index` 階段拆解與純函式外提、`SpiceParser` 純函式外提、`bundler` / `io_utils` / `cli` 收斂及跨模組殘留清理（對應 `FR-03`, `FR-04`）
- [x] **TASK-03**：執行 `file-space`、`ast`、`knowledge-db`、`agents-workflow` 全套 `dev check`、`dev test` 與 `@build` 重新打包安裝驗證，並產出 Before/After 結構量化對照數據（對應 `NFR-01`, `NFR-02`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

