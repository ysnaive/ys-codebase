# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_04 空間指紋、AST 解析與知識庫檢索深層審計收斂 (Knowledge Pipeline Remediation)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 詳見獨立規格檔 [`P01_requirements_spec.md`](./P01_requirements_spec.md)，以下為核心契約摘要：

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `module:file-space` 跨空間游標、符號連結走訪與原子寫入加固 (`FS-01`~`06`) | 涵蓋 `.watcher_dirty` 跨行程信標、`ack(space_name=None)` 世代對齊、`_walk_root` 符號連結邏輯路徑與 `st_ino != 0` 守衛、`_apply_project_space_overrides` 沙盒隔離守衛、`_atomic_write_bytes` 退避重試、`cli.py:diff --ack` 轉發 `space_generations` 與單檔 `include` 支援。 | P0 | [P00:DR-01] |
| **FR-02** | `module:ast` 增量路徑匹配、多核心解析與跨語言拓撲連結 (`AST-01`~`06`) | 涵蓋 `is_dirty_file_match` 根目錄單檔絕對路徑匹配與 `_resolve_dirty_files_only` 之 `best_mtime_ns` 消歧、`bundle_union` 預設語言平行解析解鎖、`hook.file-space.py` 冷啟動全空間建置與 `_cursor_already_consumed=True`、C# 檔案級命名空間範圍延伸及 `_LAST_LINKER_CACHE` 世代指紋。 | P0 | [P00:DR-02] |
| **FR-03** | `module:knowledge-db` 雙水位線自癒、跨行程鎖與檢索管線優化 (`KDB-01`~`06`) | 涵蓋 `KnowledgeDBServiceWorker` 冷啟動載入索引觸發 `[DN-30]` 自癒、`save_binary` 跨行程鎖、`hybrid.py` 副檔名提取與 RRF 尺度保護、`engine.py:bundle` 多空間匯出防覆寫、移除多餘游標消費及 `InvertedIndex.build(..., pre_aggregated=True)`。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 測試沙盒傳入 `FileSpaceManager(project_root=tmp_dir)` 且未帶顯式 `config` | 透過 `self._explicit_project_root is None` 守衛阻斷宿主 `contribute.json` 跨界污染。 |
| **EC-02** | Windows 或虛擬檔案系統上 `os.stat` 回傳 `st_ino == 0` | `_walk_root` 僅於 `dir_stat.st_ino != 0` 時記錄 `(st_dev, st_ino)`。 |
| **EC-03** | 根目錄單檔（無 `/`）於多空間同名或以絕對路徑傳入髒清單 | `is_dirty_file_match` 僅允許無 `/` 符號路徑匹配絕對髒路徑，且 `_resolve_dirty_files_only` 以 `best_mtime_ns` 消歧。 |
| **EC-04** | 無副檔名但父目錄含 `.` 之檔案進行 `ftypes` 過濾 | `HybridSearchEngine` 使用 `Path(sym.file_path).suffix.lstrip(".").lower()` 提取副檔名。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與併發安全 | 免除重複 $O(N)$ 分部聚合；二進位索引持久化受跨行程鎖與 `PermissionError` 退避重試保護。 |
| **NFR-02** | 契約相容與靜態合規 | 嚴格遵守防回歸紅線 7 與紅線 8；生產源碼零審計代號殘留；通過 `dev check` 100% 零錯誤。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 防回歸紅線 7 & 8**：嚴格落實 `_explicit_project_root is None`、`is_dirty_file_match` 雙向後綴保留，以及 `HybridSearchEngine` 絕不套用 `flt.min_score` 於 RRF 分數。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[FileSpaceWatcherServiceWorker]
   ├── notify_file_event() ──> write .watcher_dirty beacon
   └── flush_dirty_spaces() ─> patch_space_files() + clear .watcher_dirty
                                      │
                                      ▼
[FingerprintScanner.consume_diff()]
   ├── is_watcher_dirty() == True ──> auto_refresh=True
   └── ack(space_name=None, space_generations=...) ──> align unified & per-space cursors
                                      │
                                      ▼
[ASTEngine / hook.file-space.py / SemanticBundler]
   ├── hook cold start (not has_existing_snapshot) ──> build_index(spaces=None)
   ├── hook incremental ──> hot_patch_index(..., _cursor_already_consumed=True)
   ├── is_dirty_file_match() + _resolve_dirty_files_only(best_mtime_ns)
   └── CSharpDialect.finalize_raw_items() + SymbolLinker(_LAST_LINKER_CACHE fingerprint)
                                      │
                                      ▼
[KnowledgeDBServiceWorker / IndexingPipeline / HybridSearchEngine]
   ├── worker cold start ──> _ensure_indices_loaded(load_vectors=False) ──> [DN-30] dual-watermark check
   ├── build_unified_index / hot_patch ──> InvertedIndex.build(pre_aggregated=True) + _kdb_index_file_lock()
   └── HybridSearchEngine.search() ──> Path(sym.file_path).suffix (preserving RRF score scale)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 實作 `.watcher_dirty` 信標讀寫、`is_watcher_dirty()`、`ack(space_name=None)` 世代計算對齊、`_atomic_write_bytes` 退避重試與 `patch_space_files` 單檔 `include` 支援 |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | 於 `notify_file_event`、`flush_space_now`、`flush_dirty_spaces` 與 `stop` 維護 `.watcher_dirty` 跨行程信標 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 修正 `_walk_root` (`st_ino != 0` 與 `entry_path` 邏輯路徑)、`_apply_project_space_overrides` (`_explicit_project_root is None` 守衛) 及單檔 `include` 走訪 |
| `ys_codebase/source/file-space/scripts/cli.py` | Modify | `diff --ack` 補齊 `space_generations=diff_res.space_generations` 參數轉發 |
| `ys_codebase/source/file-space/tests/test_file_space_manager.py` | Modify | 擴充 `FS-02`、`FS-06` 單檔 `include` 與符號連結邏輯路徑單元測試 |
| `ys_codebase/source/file-space/tests/test_fingerprint_scanner.py` | Modify | 擴充 `FS-01`、`FS-04` `.watcher_dirty` 信標與 `_atomic_write_bytes` 退避重試單元測試 |
| `ys_codebase/source/ast/ast_engine/io_utils.py` | Modify | 修正 `is_dirty_file_match` 根目錄單檔對絕對髒路徑之匹配（保留含 `/` 雙向後綴匹配） |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `_resolve_dirty_files_only` 跨空間同名 `best_mtime_ns` 消歧；`bundle_union` 精確判定非預設自訂解析器配置 |
| `ys_codebase/source/ast/ast_engine/dialects/csharp.py` | Modify | 實作 `post_process_raw_item` 與 `finalize_raw_items` 將 C# `file_scoped_namespace_declaration` 範圍延伸至 EOF |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | `_LAST_LINKER_CACHE` 快取鍵納入符號內容版本指紋，防止原地熱修補後命中過期快取 |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | `ASTSnapshot.from_dict` 支援 `list`/`tuple` 形式之 `symbols` 容錯轉換 |
| `ys_codebase/source/ast/scripts/hook.file-space.py` | Modify | 冷啟動傳入 `spaces=None` 建置全域快照；增量熱修補傳入 `_cursor_already_consumed=True` |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 擴充 `AST-01`~`06` 單元測試案例 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | `_has_pending_space_work` 與 `_sync_stage1_lexical_and_graph` 冷啟動先呼叫 `_ensure_indices_loaded(load_vectors=False)` |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 補齊 `save_binary` 跨行程鎖、移除 `_ensure_jit_index_ready_locked` 重複游標消費、傳入 `pre_aggregated=True` |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | 以 `Path(sym.file_path).suffix.lstrip(".").lower()` 正規化副檔名過濾 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `bundle()` 多空間匯出時自動區隔各空間目標匯出路徑 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `InvertedIndex.build` 新增 `pre_aggregated: bool = False` 參數 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 擴充 `KDB-01`、`KDB-04` 冷啟動雙水位線與多空間匯出單元測試案例 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 擴充 `KDB-03`、`KDB-06` 副檔名提取與 `pre_aggregated=True` 單元測試案例 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 採跨行程檔案信標 `.watcher_dirty` 搭配記憶體 `_dirty_Deadlines` 雙重判定，解決外部 CLI 行程於背景 Watcher 500ms 防抖視窗內讀取舊快照之競態，對應 `[P00:DR-01]`。
- **[P02:DR-02]** `FileSpaceManager._apply_project_space_overrides` 以 `self._explicit_project_root is None` 區分生產環境預設實例與測試沙盒 `project_root=tmp_dir`，兼顧組態合併與沙盒純淨度，對應 `[P00:DR-01]`。
- **[P02:DR-03]** `SymbolLinker` 透過計算符號映射之輕量結構指紋（含 `(id, id(sym))` 取樣雜湊）作為 `_LAST_LINKER_CACHE` 快取鍵，零外部介面變更解決原地 `hot_patch_index` 快取失準，對應 `[P00:DR-02]`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# file_space/scanner.py
class FingerprintScanner:
    def is_watcher_dirty(self, space_name: Optional[str] = None) -> bool: ...
    def mark_watcher_dirty(self, dirty: bool = True) -> None: ...

# ast_engine/io_utils.py
def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool: ...

# knowledge_db/retrieval.py
class InvertedIndex:
    def build(
        self,
        symbols: List[UnifiedSymbol],
        tokenizer: Optional[MultilingualTokenizer] = None,
        space: str = "",
        pre_aggregated: bool = False,
    ) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_atomic_write_bytes` 於 Windows 遭遇暫時性 `PermissionError` 時執行最多 5 次指數退避重試，若仍失敗則清理暫存檔並拋出原始 `PermissionError`。
  - `.watcher_dirty` 信標讀寫失敗時採 Fail-open 靜默降級，不阻斷主掃描或檢索流程。
- **階段決策紀錄**：`[P03:DR-01]` 所有新增參數（如 `pre_aggregated: bool = False`、`mark_watcher_dirty`）均具備向後相容預設值，對應 `FR-01`~`FR-03`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-03 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *Q1：若背景 Watcher 異常崩潰且未清理 `.watcher_dirty` 信標，是否會造成不良影響？*
    - **A1**：`is_watcher_dirty()` 僅在 `is_watcher_active()` 為 `True` 時生效，且效果為讓 `consume_diff()` 回退至安全的 `auto_refresh=True` 即時掃描；下次 Watcher 正常沖刷或停止時即自動清除信標。
  - *Q2：`_LAST_LINKER_CACHE` 加入指紋計算是否會拖慢大型符號表的拓撲查詢？*
    - **A2**：快取鍵使用 `len(symbols_map)` 與快速 XOR/hash 組合，耗時為微秒級且僅在 `expand_contract_symbol_ids` 入口執行一次，遠快於重建 `SymbolLinker`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/stdlib/{file-space,ast,knowledge-db}/README.md` | N/A | 內部實作加固，Public CLI 與契約無破壞性變更（交由主計畫 Phase 7 統一檢視） |
| **專題手冊** | `docs/stdlib/knowledge-db/ ARCHITECTURE.md` | N/A | 無新增專題文件需求 |
| **設計決策** | `docs/stdlib/knowledge-db/DESIGN_NOTES.md` | N/A | 維持既有 `[DN-30]` 雙水位線架構定義 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring（嚴守零審計代號鐵律） |
| **發布日誌** | `CHANGELOG.md` | N/A | 交由主計畫 `2026_11_05_0104_codebase_deep_audit_remediation` 結案時統一彙整 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_04` 18 項修復規格無歧義，進入實作與靜態檢查。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `module:file-space` 修復 (`FS-01`~`06`：`scanner.py`、`service.py`、`manager.py`、`scripts/cli.py`)
- [x] **TASK-02**：實作 `module:ast` 修復 (`AST-01`~`06`：`io_utils.py`、`bundler.py`、`dialects/csharp.py`、`linker.py`、`schema.py`、`scripts/hook.file-space.py`)
- [x] **TASK-03**：實作 `module:knowledge-db` 修復 (`KDB-01`~`06`：`service.py`、`pipeline.py`、`hybrid.py`、`engine.py`、`retrieval.py`)
- [x] **TASK-04**：編寫 `file-space`、`ast` 與 `knowledge-db` 單元測試案例並通過 `dev check` 與 `py_compile` 靜態驗證
- [x] **TASK-DOC**：同步更新異動源碼之微觀 Docstrings 與架構不變量註解

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
