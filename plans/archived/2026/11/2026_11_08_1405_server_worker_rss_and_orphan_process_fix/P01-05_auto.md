# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Server Worker 常駐記憶體演算法治理、Core Space 快取共享、AST/KDB 查表去重與測試沙盒孤兒進程清理  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.space` 單例化、快照記憶體快取、Watcher 智慧感知與 `scan(None)` 雜湊複用 | 1. `SpaceScanner` 對 `.yfp2.bin` 快照實作基於 `(mtime_ns, size)` 的記憶體快取。<br/>2. `SpaceScanner.diff` 與 `consume_diff` 將 `auto_refresh` 預設改為 `Optional[bool] = None`；當 `auto_refresh is None`、未指定自訂 `_explicit_storage_root`、`is_watcher_active(space_query)` 為 `True`、無 `.watcher_dirty` 且目標快照已存在時，自動採用 `auto_refresh=False`。<br/>3. `SpaceScanner.scan(None)` 快取物理檔案 `(abs_path, size, mtime_ns) -> content_hash`，讓合成空間与 `__all__` 複用雜湊並保留獨立世代號與 `/workspace` 排除規則。<br/>4. 新增 `sync_dependent_snapshots_batch` 供 `CoreSpaceWatcherServiceWorker.flush_dirty_spaces` 批次合併更新合成空間與 `__all__`，並於 Watcher 啟動時確保 `__all__` 快照同步就緒。<br/>5. 下游 `gdrive-support`、`providers.py`、`hasher.py`、`space_watcher.py`、`ast`、`knowledge-db` 統一使用 `get_default_registry()` 與 `get_default_scanner()`。 | P0 | [P00:DR-03] |
| **FR-02** | `ast` 與 `knowledge-db` 快取自治、Symbol SSOT 查表共用與背景 CPU 空轉根治 | 1. `SemanticBundler` 新增 `clear_transient_caches()`，於 `ASTEngine.build_index` 與 `hot_patch_index` 完成圖譜與世代收集後釋放 `_file_symbols_cache`、`_file_call_sites_cache`、`_file_imports_cache`、`_last_bundle_unique_files`；常駐 Worker（`YSCB_IN_SERVER_WORKER=1`）或 `allow_parallel=False` 時禁止啟動 `ProcessPoolExecutor`。<br/>2. `IndexingPipeline.build_unified_index` 透傳 `allow_parallel` 至 `ASTEngine`；移除 `ASTEngine` 硬編碼之 `auto_refresh=True`。<br/>3. `InvertedIndex` 與 `IndexingPipeline` 在同進程內（含建構、增量與 `load_binary` 冷啟動載入後）對齊共用 `ASTEngine._snapshot.symbols` 同 ID 實例。<br/>4. `_collect_all_dirty_files` 僅在髒檔案包含 `ast_engine.bundler.registry.get_parser(path) is not None` 之可解析檔案且 `snapshot.ast_generation <= current_acked_gen` 時才呼叫 `ast_engine.hot_patch_index`。<br/>5. `EmbeddingService` 維持 ONNX 模型常駐，優化 `VectorIndex.patch_incremental` 批次緩衝與 `KnowledgeDBServiceWorker` 世代/髒標記 O(1) 檢查，消除 2 秒無差別反序列化與重建死迴圈。 | P0 | [P00:DR-02] |
| **FR-03** | Server 演算法記憶體異常偵測 (`WorkerMemoryHealthMonitor`) 與主動堆疊歸還 | 1. `core.platform.process` 新增 `get_process_rss_mb(pid)`、`get_host_memory_info()` 與 `trim_process_memory()`（執行 `gc.collect()` + Linux `malloc_trim(0)`）。<br/>2. `WarmWorker` 在前景任務完成且所有背景 `ServiceWorker` 均非繁忙（`not is_busy()`）時執行 `trim_process_memory()`。<br/>3. `MasterSupervisor` 透過 `WorkerMemoryHealthMonitor` 追蹤 Worker `trim` 後之閒置 RSS 基線 $B_{\text{base}}$、膨脹倍率 $R_{\text{idle}} / B_{\text{base}}$、滑動視窗單調上升斜率與宿主 `MemAvailable` 壓力係數；當前景與所有背景服務皆 Idle 且判定記憶體異常時，無縫執行 `restart_worker()`。 | P0 | [P00:DR-01] |
| **FR-04** | `dev test` 跨 Session 進程樹穿透收割與父進程存活守衛 | 1. `kill_process_tree` 透過 `/proc` 遞迴掃描子孫進程與 Process Groups（穿透 `setsid()` / `start_new_session=True`）。<br/>2. 新增 `reap_sandbox_processes(sandbox_dir)` 於 `SandboxProvisioner.cleanup_sandbox` 清理隸屬該沙盒之所有脫離 Daemon。<br/>3. `dev/testing/runner.py` 註冊 `SIGTERM`/`SIGINT` 信號轉發與 `atexit` 活躍子進程清理；`dev op-test` 沙盒模式啟動 Parent-Death Watchdog，當原父進程消失或 `os.getppid() == 1` 時立即自我終止。 | P0 | [P00:DR-04] |
| **FR-05** | `ASTEngine` 宣告式目標空間注入、`workflow.archived://` 排除、`Posting` 去字典化緊湊序列化與前景 CLI 熱路徑加速 | 1. `ASTEngine` 透過 `contributes/ast.json` 之 `"spaces"`（`ast` 宣告 `["source"]`，`agents-workflow` 宣告 `["docs", "plans"]`）與 `ASTEngine.register_spaces(...)` / `on_register_ast_spaces` Hook 動態決定納管目標空間（零業務空間硬編碼），並於 `is_watcher_active` 時僅對目標空間執行非阻塞差異檢查。<br/>2. `agents-workflow/contributes/core.json` 將 `plans` 之 `exclude` 設為 `[".git", "workflow.archived://"]`（保留 `workflow.roadmap://`），`docs` 之 `exclude` 設為 `[".git"]`。<br/>3. `InvertedIndex` 之 `Posting` 廢除每物件 `SparseFieldFreqs` 字典，改為 `_f_name`/`_f_sig`/`_f_members`/`_f_doc` 四整數槽位，並於 `to_dict()`/`from_dict()` 採用緊湊 6-tuple `(doc_id, _f_name, _f_sig, _f_members, _f_doc, tuple(spaces))` 序列化，消除 `load_binary` 百萬級暫存字典分配。<br/>4. `EmbeddingService` 將 `MAX_SYMBOL_DOCSTRING_EMBED_CHARS` 設為 `400`，並於 `WarmWorker.execute_task` 執行前景 CLI 期間透過 `server.worker.foreground_active` 讓渡 `KnowledgeDBServiceWorker` Stage 2 微批次推論。<br/>5. 快取 `agents-workflow` 之 `on_pre_cli_dispatch`（`source_sha1_cache.json` 與 `.gitignore` 同步短路）與 `ast` 之 `_get_or_create_resolver` 索引結構，消除每次 CLI 派發的重複建構開銷。 | P0 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 背景 `KnowledgeDBServiceWorker` 正處於 `STATE_UPDATING`（執行 Stage 1/2 索引或 ONNX 推論）時，前景任務結束或巡檢觸發 | `WarmWorker` 與 `MasterSupervisor` 檢查所有背景 `ServiceWorker` 是否處於 `busy` 狀態；若任一服務繁忙，跳過 `WorkerMemoryHealthMonitor` 異常判定與重啟，防止誤殺正在建索引的 Worker。 |
| **EC-02** | 僅修改 `.md` 文檔或無 AST 解析器之純設定檔時觸發增量同步 | `.md` 具有 `ASTEngine` 內建 `markdown` parser（`get_parser(path) is not None`），正常連動 `ASTEngine` 更新文檔標題符號；無 AST parser 之檔案則跳過 `ast_engine.hot_patch_index`，避免無效重算。 |
| **EC-03** | 沙盒測試或單元測試顯式傳入自訂 `storage_root` / `raw_spaces` 時呼叫 `SpaceScanner.diff(auto_refresh=None)` | 當 `_explicit_storage_root is not None` 時，`auto_refresh=None` 自動回退為 `True`，確保自訂隔離儲存目錄不受宿主背景 Watcher 狀態影響；且磁碟 `.yfp2.bin` 之 `mtime_ns` 變更時自動失效記憶體快取。 |
| **EC-04** | 沙盒內測試案例透過 `spawn_detached` 或 `start_new_session=True` 啟動背景 Daemon，或外層 `dev test` 遭 `SIGTERM` 終止 | `cleanup_sandbox` 呼叫 `reap_sandbox_processes` 依 `/proc` 之 `cwd`/`environ`/`cmdline` 強制收割沙盒殘留進程；`dev op-test` 之 Parent-Death Watchdog 偵測父進程死亡時立即收割自身進程樹並退出。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 記憶體與 CPU | 常駐 `worker.py` 在待機 (`Idle`) 期間 CPU 佔用率趨近 `0%`（無 2 秒全量重掃迴圈），`SemanticBundler` 建構暫存快取於索引完成後 `100%` 歸零，`EmbeddingService` 模型維持常駐。 |
| **NFR-02** | 原生標準庫依賴 | `core.platform.process` 與 `core.space` 維持 `100%` Python 標準庫實現，零第三方套件依賴。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `ASTEngine.build_index` 與 `hot_patch_index` 在呼叫 `bundle_union()` / `bundle_dirty_files()` 後，緊接著會呼叫 `extract_all_call_sites_and_imports()` 與 `_collect_space_generations_and_files_map()`，因此 `bundler.clear_transient_caches()` 必須放在這兩個步驟完成之後呼叫。
- **`[!CAUTION]`** 合成空間 `/workspace` 具備獨立 `exclude` 規則，且各空間 `FileFingerprint` 的 `created_gen`/`updated_gen` 綁定該空間自身的 `head_generation`，因此 `scan(None)` 僅能複用物理檔案 `(abs_path, size, mtime_ns) -> content_hash`，不可直接複製葉節點的世代號。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Core Space Singletons & Snapshot Cache]
  get_default_registry() / get_default_scanner()
       │
       ├──► SpaceScanner._snapshot_mem_cache[(key, mtime_ns, size)] -> SnapshotState
       ├──► SpaceScanner.diff/consume_diff(auto_refresh=None) -> Watcher-aware O(1) diff
       └──► SpaceScanner.scan(None) -> Content-Hash Memoization across leaf & synthetic spaces

[AST & Knowledge-DB Co- Resident Pipeline]
  ASTEngine.build_index / hot_patch_index
       ├──► SemanticBundler (no ProcessPoolExecutor in Worker) -> clear_transient_caches() at end
       └──► ASTSnapshot.symbols (SSOT) ◄── shared UnifiedSymbol refs ── InvertedIndex / IndexingPipeline
                                       ◄── O(1) dirty/generation gate ── KnowledgeDBServiceWorker

[Server Algorithmic Memory Health Monitor & Sandbox Reaper]
  WarmWorker (Idle & all services not busy) ──► trim_process_memory() (gc.collect + malloc_trim)
       └──► MasterSupervisor.WorkerMemoryHealthMonitor(baseline, drift, host_mem_available)
                 └──► Seamless restart_worker() on anomalous monotonic bloat
  dev test / SandboxProvisioner ──► kill_process_tree (/proc descendants) + reap_sandbox_processes + Parent-Death Watchdog
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 新增 `get_process_rss_mb`、`get_host_memory_info`、`trim_process_memory`、`reap_sandbox_processes`，強化 `kill_process_tree` 穿透 `setsid()` 遞迴收割子孫進程 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出新增之進程記憶體與沙盒收割原語 |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 新增 `.yfp2.bin` 記憶體快取、`diff`/`consume_diff` 自動感知 Watcher、`scan(None)` 物理雜湊複用與 `sync_dependent_snapshots_batch` |
| `ys_codebase/source/core/core/space/providers.py` | Modify | 改用 `get_default_registry` 避免重複建構 `SpaceRegistry` |
| `ys_codebase/source/core/core/space/hasher.py` | Modify | `hash_space_or_path` 預設改用 `get_default_registry` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | `_load_space_include_roots`、`_load_space_thresholds_mb`、`collect_space_local_files_with_stat` 改用 `get_default_registry` |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 預設共用 `get_default_registry`/`get_default_scanner`，啟動時確保 `__all__` 就緒，`flush_dirty_spaces` 採用批次 `sync_dependent_snapshots_batch` |
| `ys_codebase/source/server/server/service.py` | Modify | `BaseServiceWorker` 與 `ServiceManager` 支援查詢 `is_busy()` 供閒置記憶體修剪與回收守衛判斷 |
| `ys_codebase/source/server/server/worker.py` | Modify | 任務結束與背景閒置時呼叫 `trim_process_memory()`，支援 IPC `memory_probe` / 狀態查詢回報 `rss_mb` 與 `services_busy` |
| `ys_codebase/source/server/server/master.py` | Modify | 實作 `WorkerMemoryHealthMonitor` 演算法評估基線膨脹、單調漂移與宿主可用記憶體壓力，於完全 Idle 時無縫 `restart_worker()`，並於 `get_status_dict` 暴露記憶體指標 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 新增 `clear_transient_caches()`；常駐 Worker（`YSCB_IN_SERVER_WORKER=1`）內禁止 `bundle_union` 啟動 `ProcessPoolExecutor` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 預設共用 `get_default_registry`/`get_default_scanner`；移除硬編碼 `auto_refresh=True`；於 `build_index` 與 `hot_patch_index` 收尾呼叫 `bundler.clear_transient_caches()` |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 預設共用 `get_default_registry`/`get_default_scanner`；`_consume_space_diff` 支援 `auto_refresh=None`；`build_unified_index` 透傳 `allow_parallel`；對齊共用 `ASTEngine._snapshot.symbols`；修正 `_collect_all_dirty_files` 僅對具 AST Parser 之檔案連動 `hot_patch_index` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 實作世代與髒標記 O(1) 快取守衛、避免無效重建迴圈，並於同步收斂後觸發 `trim_process_memory()` |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 維護活躍子進程註冊表，掛載 `SIGTERM`/`SIGINT` 與 `atexit` 進程樹清理守衛 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `cleanup_sandbox` 拆卸時呼叫 `reap_sandbox_processes(sandbox_dir)` |
| `ys_codebase/source/dev/dev/tester.py` | Modify | `_run_op_test` 於沙盒模式啟動輕量級 Parent-Death Watchdog 執行緒，並於沙盒結束時清理殘留進程 |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 對齊過渡轉發層 `diff` / `consume_diff` 之 `auto_refresh: Optional[bool] = None` 簽名 |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 於 `server status` 儀表板顯示 `Worker Memory` 即時 RSS、基線、峰值與自動回收計數 |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | 修正 `is_watcher_active` 忽略無 `entries` 且無 `compose` 之純規則空間（如 `project/workspace`），避免 `is_watcher_active(None)` 誤判為 `False` |
| `ys_codebase/source/ast/contributes/ast.json` | Modify | 宣告 `"spaces": ["source"]` 作為 AST 預設目標空間 |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 新增 `_get_or_create_resolver` 於 `RuntimeContext` 快取 `DeterministicSymbolResolver`，避免每次 `callers`/`callees`/`impact` 重建符號索引 |
| `ys_codebase/source/ast/scripts/hook.core.py` | Modify | `on_space_changed` 依 `ASTEngine.get_target_spaces()` 動態過濾目標空間 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `Posting` 改為四整數槽位（`_f_name`/`_f_sig`/`_f_members`/`_f_doc`），`InvertedIndex.to_dict()`/`from_dict()` 實作緊湊 6-tuple 序列化，並於 `load_binary` 後呼叫 `trim_process_memory` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 將 `MAX_SYMBOL_DOCSTRING_EMBED_CHARS` 由 `1000` 調降為 `400` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 初始化時呼叫 `ASTEngine.register_spaces` 註冊 `space_weights` 空間；Watcher 活躍時以 `auto_refresh=False` 執行目標空間非阻塞差異檢查 |
| `ys_codebase/source/knowledge-db/scripts/hook.ast.py` | Create | 實作 `on_register_ast_spaces` Hook，動態注入 `knowledge-db` 配置之檢索空間至 `ASTEngine` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | `plans` 之 `exclude` 設為 `[".git", "workflow.archived://"]`，`docs` 之 `exclude` 設為 `[".git"]` |
| `ys_codebase/source/agents-workflow/contributes/ast.json` | Create | 宣告 `"spaces": ["docs", "plans"]` 納入 `ASTEngine` 目標空間 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 於 `RuntimeContext` 快取 `source_sha1_cache.json` 與 `.gitignore` 同步指紋，加速 `on_pre_cli_dispatch` 短路檢查 |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 擴充 `SpaceScanner` 記憶體快取、Watcher 智慧感知、`scan(None)` 雜湊複用與 `sync_dependent_snapshots_batch` 測試 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 擴充 `WorkerMemoryHealthMonitor` 演算法評估、背景繁忙防誤殺與 `MasterSupervisor._is_worker_completely_idle` 測試 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 擴充 `SemanticBundler.clear_transient_caches()` 與 Worker 內禁絕 `ProcessPoolExecutor` 測試 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 擴充 `ASTEngine` Symbol 共用與非 AST 可解析檔案跳過 `hot_patch_index` 測試 |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 對齊 `SemanticBundler` 暫存快取釋放與 `ASTSnapshot`/`InvertedIndex` 同 ID 符號實例共享驗證 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 擴充跨 Session 孫進程收割、`reap_sandbox_processes` 與 Parent-Death Watchdog 測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `WorkerMemoryHealthMonitor` 演算法採三維度綜合判定：
  1. 以預熱後前 3 次 Idle 採樣建立基線 $B_{\text{base}} = \max(\text{median}(R_{1..3}), 256.0\text{ MB})$（若後續採樣低於 $B_{\text{base}}$ 則向下平滑修正基線）。
  2. 追蹤最近 $W=6$ 次任務/同步週期 `trim` 後的閒置 RSS 序列：計算膨脹比 $\text{ratio} = R_{\text{curr}} / B_{\text{base}}$、淨增量 $\Delta R = R_{\text{curr}} - B_{\text{base}}$，以及非遞減步數比例（Monotonic Drift Score）。
  3. 結合宿主 `MemAvailable`：正常壓力下當 $(\text{ratio} \ge 2.2 \text{ and } \Delta R \ge 384\text{ MB and drift} \ge 0.75)$ 或 $(\text{ratio} \ge 3.0 \text{ and } \Delta R \ge 512\text{ MB})$ 時觸發無縫重啟；當宿主高記憶體壓力（`avail_ratio < 0.15`）時，門檻自動下調至 $(\text{ratio} \ge 1.5 \text{ and } \Delta R \ge 256\text{ MB})$，兼顧零誤殺與防 Swap Thrashing。
- **[P02:DR-02]** `SpaceScanner` 的記憶體快照快取以 `key -> (mtime_ns, size, SnapshotState)` 儲存於 `SpaceScanner` 實例中，讀取時回傳 `SnapshotState` 的安全副本（`files` dict 淺拷貝，因 `FileFingerprint` 為 `frozen=True` 不可變物件），寫入時同步更新快取，達成零序列化開銷與 100% 跨進程一致性。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# module:core - core/platform/process.py
def get_process_rss_mb(pid: Optional[int] = None) -> float: ...
def get_host_memory_info() -> Dict[str, float]: ...
def trim_process_memory(min_interval_sec: float = 5.0) -> bool: ...
def reap_sandbox_processes(sandbox_dir: Union[str, Path], timeout_sec: float = 2.0) -> int: ...

# module:core - core/space/scanner.py
class SpaceScanner:
    def diff(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> ScanDiffResult: ...
    @contextmanager
    def consume_diff(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]: ...
    def sync_dependent_snapshots_batch(
        self,
        changed_qnames: Iterable[str],
        dirty_paths: Optional[Iterable[Union[str, Path]]] = None,
        *,
        exclude_keys: Optional[Iterable[str]] = None,
    ) -> Dict[str, ScanDiffResult]: ...

# module:ast - ast_engine/bundler.py
class SemanticBundler:
    def clear_transient_caches(self) -> None: ...

# module:server - server/master.py
class WorkerMemoryHealthMonitor:
    def reset_for_new_worker(self, initial_rss_mb: float = 0.0) -> None: ...
    def record_sample(self, rss_mb: float, is_idle: bool = False) -> None: ...
    def evaluate(
        self,
        current_rss_mb: float,
        host_mem: Optional[Dict[str, float]] = None,
        is_idle: bool = True,
    ) -> Tuple[bool, str]: ...
    def to_status_dict(self, live_rss_mb: Optional[float] = None) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `get_process_rss_mb`、`get_host_memory_info`、`trim_process_memory` 與 `reap_sandbox_processes` 在權限不足或進程已退出時安全返回預設值（`0.0` / `{}` / `False` / `0`），絕不拋出未捕捉之 `OSError` 中斷主流程。
- **階段決策紀錄**：`[P03:DR-01]` `diff` 與 `consume_diff` 的 `auto_refresh` 預設型別設為 `Optional[bool] = None`，向後相容所有顯式傳入 `True` 或 `False` 的既有呼叫端。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若多個測試案例在同一個進程中切換不同的臨時目錄或沙盒，共用 `get_default_registry()` / `get_default_scanner()` 是否會造成狀態污染？*
  - *答*：`get_default_registry(project_root, yscb_dir)` 與 `get_default_scanner(project_root, yscb_dir)` 內部以正規化之 `(project_root, yscb_dir, storage_root)` 作為字典 Key 隔離於 `RuntimeContext` 中；且當呼叫端顯式傳入自訂 `storage_root` 或 `raw_spaces` 時，維持獨立實例並強制 `auto_refresh=True`，100% 杜絕跨沙盒污染。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md`、`docs/core/README.md` | Modify | 補充 `WorkerMemoryHealthMonitor` 演算法記憶體治理與 `core.space` 快照記憶體快取/Watcher 智慧感知說明 |
| **專題手冊** | `docs/server/daemon_architecture.md` | Modify | 更新常駐 Worker 記憶體自治與演算法回收流程 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記演算法記憶體異常偵測與跨 Session 沙盒進程樹收割設計決策 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本版本修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認通過 Pre-Code Analyze Gate，所有盲眼審查反證與防護條款均已 100% 納入規格。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `module:core` 之 `core/platform/process.py`（`get_process_rss_mb`、`get_host_memory_info`、`trim_process_memory`、穿透 `setsid()` 之 `kill_process_tree` 與 `reap_sandbox_processes`）及 `core/space`（`SpaceScanner` 記憶體快取、`diff`/`consume_diff` 自動感知 Watcher、`scan(None)` 雜湊複用、`sync_dependent_snapshots_batch` 與 `get_default_registry`/`get_default_scanner` 單例對齊）
- [x] **TASK-02**：實作 `module:ast`、`module:knowledge-db` 與 `module:gdrive-support` 之單例共用、`SemanticBundler.clear_transient_caches()`、常駐 Worker 禁絕 `ProcessPoolExecutor`、`UnifiedSymbol` SSOT 共用與 `KnowledgeDBServiceWorker` O(1) 閒置守衛
- [x] **TASK-03**：實作 `module:server`（`WorkerMemoryHealthMonitor` 演算法記憶體異常偵測、背景服務 `is_busy()` 守衛、Idle `trim_process_memory()`、`space_watcher.py` 批次更新）與 `module:dev`（信號轉發、`cleanup_sandbox` 進程收割、`op-test` Parent-Death Watchdog）
- [x] **TASK-04**：擴充並執行 `core`、`ast`、`knowledge-db`、`server`、`dev`、`gdrive-support` 靶向與回歸測試，並熱部署 `@build`
- [x] **TASK-DOC**：同步更新 `docs/` 模組手冊與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-03** | Minor | 為符合 `dev check` `[F13]`（`scripts/cli.py` 僅限薄轉發層），將 `start_parent_death_watchdog` 置於 `dev/testing/runner.py` 並由 `dev/tester.py:_run_op_test` 調用。 | 已同步更新 §2.2 異動檔案清單，100% 通過 `dev check dev`。 |
