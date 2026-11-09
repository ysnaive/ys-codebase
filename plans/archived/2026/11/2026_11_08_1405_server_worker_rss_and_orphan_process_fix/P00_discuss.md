# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Server Worker 常駐記憶體演算法治理、Core Space 快取共享、AST/KDB 查表去重與測試沙盒孤兒進程清理  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 處理外部通報之嚴重缺陷：`[Bug Report] server (worker.py) 長時間常駐記憶體累增洩漏 (RSS 膨脹至 4~5 GB) 與 dev test 孤兒進程殘留`，並經開發者審查與盲眼子代理 (`/blind-subagent`) 反向查驗確認延伸治理需求：
    1. **反對寫死絕對記憶體閾值，改採「模組自治 + Server 演算法異常偵測」**：各模組必須管好常駐快取生命週期（其中 `knowledge-db` 的 `EmbeddingService` ONNX 模型應保持常駐以維持檢索低延遲）；`server` 則以演算法（相對於預熱基線之膨脹倍數、`gc + malloc_trim` 後之單調漂移率、宿主 `MemAvailable` 記憶體壓力感知）在**前景任務與所有背景 `ServiceWorker` 皆處於 `IDLE`** 時評估該 Worker 是否出現記憶體管理異常並執行無縫重啟。
    2. **根治 `ast` 內部快取滯留與 `knowledge-db` 重複搞一份 Symbol/掃描的問題**：消除 `SemanticBundler` 在 `ASTEngine.build_index` / `hot_patch_index` 完成圖譜與世代收集後仍滯留的逐檔快取，禁止常駐 Worker 內 `fork` `ProcessPoolExecutor`；讓 `knowledge-db` 在同進程內直接查表共用 `ast` 的 `UnifiedSymbol` SSOT（含冷啟動載入後對齊引用），且僅在髒檔案中確實存在 `ast` 支援之語法解析器（含 `.md` AST Markdown 解析器）且世代落後時才觸發 `ast_engine.hot_patch_index`。
    3. **全面治理 `core.space` 本身與下游模組引用問題**：解決下游模組私自 `new SpaceRegistry()` / `SpaceScanner()`、`_load_snapshot_state` 零記憶體快取反覆解包 `.yfp2.bin`、`diff` / `consume_diff` 預設 `auto_refresh=True` 忽略 Watcher 在線狀態（含移除 `ASTEngine` 內硬編碼之 `auto_refresh=True`）、`scan(None)` 對合成空間與 `__all__` 重複計算 Blake2b 雜湊、以及 `flush_dirty_spaces` 批次內重複修補 `__all__` 等問題。
    4. **根治 `dev test` 測試沙盒孤兒進程殘留**：穿透 `setsid()` (`start_new_session=True` / `spawn_detached`) 邊界遞迴收割所有子孫進程與隸屬沙盒目錄之殘留 Daemon，並加入信號轉發與 `dev op-test` 父進程存活監控（Parent-Death Watchdog）。
- **核心目標**：
  1. **Pillar 1 (`module:core` & `module:gdrive-support` & `module:server`)：`core.space` 共享單例、記憶體快照快取、Watcher 智慧感知與零冗餘雜湊複用**：
     - `SpaceScanner` 內建基於檔案 `(mtime_ns, size)` 校驗的記憶體 `SnapshotState` 快取，避免同進程內 `diff`/`snapshot`/`status` 每次重新 `struct.unpack` 數千個 `FileFingerprint`，同時在磁碟檔案 `mtime_ns` 更新時自動重載以保證跨進程一致性。
     - `SpaceScanner.diff` 與 `consume_diff` 將 `auto_refresh` 預設升級為 `Optional[bool] = None`：當 `auto_refresh is None` 時，若未指定自訂 `_explicit_storage_root` 且 `is_watcher_active(space_query)` 為 `True`、無 `.watcher_dirty` 且目標快照已存在，自動採用 `auto_refresh=False`；並移除 [`ast_engine/engine.py:345`](../../ys_codebase/source/ast/ast_engine/engine.py#L345) 等處硬編碼的 `auto_refresh=True`。
     - `SpaceScanner.scan(None)` 實施物理檔案雜湊複用（Content-Hash Memoization）：先掃描所有具體空間（Leaf Spaces）並將物理檔案 `(abs_path, size, mtime_ns) -> content_hash` 快取於當輪掃描上下文，後續合成空間（`/<short>`，含獨立 `exclude` 規則之 `/workspace`）與 `__all__` 直接查表複用 `content_hash` 並依據合成空間自身的 `prev_state` 與 `next_gen` 計算 `created_gen`/`updated_gen`，消除重複 Blake2b 檔案讀取雜湊，同時 100% 保持各空間獨立世代與排除規則契約。
     - `SpaceScanner.sync_dependent_snapshots_batch` 與 `CoreSpaceWatcherServiceWorker`：啟動時確保 `__all__` 快照同步初始化；單一防抖批次（`flush_dirty_spaces`）結束後對受影響之合成空間與 `__all__` 僅合併更新 1 次。
     - 下游 `gdrive-support`、`core/space/providers.py`、`core/space/hasher.py`、`server/space_watcher.py`、`ast`、`knowledge-db` 在未傳入自訂 `storage_root` / `raw_spaces` 時，統一透過 `get_default_registry()` 與 `get_default_scanner()` 共用進程級單例。
  2. **Pillar 2 (`module:ast` & `module:knowledge-db`)：模組記憶體自治、Symbol SSOT 查表共用與背景 CPU 空轉根治**：
     - `SemanticBundler` 提供 `clear_transient_caches()`，由 `ASTEngine.build_index` 與 `hot_patch_index` 在完成 `extract_all_call_sites_and_imports()` / `extract_dirty_call_sites_and_imports()` 與 `_collect_space_generations_and_files_map()` **之後**的收尾階段統一呼叫，釋放 `_file_symbols_cache`、`_file_call_sites_cache`、`_file_imports_cache` 與 `_last_bundle_unique_files`；且在常駐 Worker（`YSCB_IN_SERVER_WORKER=1`）或 `allow_parallel=False` 時嚴禁啟動 `ProcessPoolExecutor` (`fork`)。
     - `IndexingPipeline.build_unified_index` 完整透傳 `allow_parallel` 至 `ASTEngine`；在同進程內，`InvertedIndex`（含建構、增量與 `load_binary` 冷啟動載入後）將與 `ASTEngine._snapshot.symbols` 同 ID 的條目對齊指向同一 `UnifiedSymbol` 實例（若需裁剪 `spaces` 則透過 `dataclasses.replace` 建立輕量殼層而不原地修改共享 `metadata`），消除雙份肥大符號樹。
     - `_collect_all_dirty_files` 僅在髒檔案包含 `self.ast_engine.bundler.registry.get_parser(path) is not None` 之可解析檔案且 `snapshot.ast_generation <= current_acked_gen` 時，才觸發 `ast_engine.hot_patch_index`。
     - `EmbeddingService` 維持 ONNX 模型常駐（不卸載模型），優化 `VectorIndex.patch_incremental` 批次緩衝以減少高頻 `np.vstack` 巨型矩陣拷貝。
     - `KnowledgeDBServiceWorker` 改為世代與髒標記驅動之 O(1) 檢查，消除 2 秒無差別反序列化與無效重建死迴圈。
  3. **Pillar 3 (`module:server` & `module:core`)：Server 演算法記憶體異常偵測 (`WorkerMemoryHealthMonitor`) 與主動堆疊歸還**：
     - 於 `core.platform.process` 提供跨平台 `get_process_rss_mb(pid)`、`get_host_memory_info()` 與 `trim_process_memory()`（執行 `gc.collect()` + Linux `ctypes` `malloc_trim(0)`）。
     - `WarmWorker` 僅在前景任務結束且所有背景 `ServiceWorker` 均非繁忙（`not is_busy()`）時執行 `trim_process_memory()` 與閒置 RSS 採樣。
     - `MasterSupervisor` 透過 `WorkerMemoryHealthMonitor` 演算法評估 Worker 閒置記憶體健康度（建立預熱穩定基線 $B_{\text{base}}$，結合「相對基線膨脹倍數 $R_{\text{idle}} / B_{\text{base}}$」、「連續週期 `trim` 後單調上升漂移率（Ratcheting Drift）」與「宿主 `MemAvailable` 記憶體壓力係數」），當前景與所有背景服務皆處於 Idle 且判定記憶體管理異常時，無縫執行 `restart_worker()`。
  4. **Pillar 4 (`module:dev` & `module:core`)：沙盒進程樹跨 Session 穿透收割與父進程存活守衛**：
     - `kill_process_tree` 透過 `/proc/<pid>/task/*/children` 與 `/proc/*/stat` (`PPID`) 遞迴蒐集所有子孫進程與 Process Groups（穿透 `setsid()` / `start_new_session=True`），連同 `reap_sandbox_processes(sandbox_dir)`（掃描 `cwd`、命令列與 `YSCB_SANDBOX_DIR` 環境變數隸屬該沙盒之所有脫離 Daemon 進程）於 `cleanup_sandbox` 100% 清除殘留進程。
     - `dev/testing/runner.py` 註冊 `SIGTERM`/`SIGINT` 信號轉發與 `atexit` 活躍子進程清理；`dev op-test` 沙盒模式啟動輕量級 Parent-Death Watchdog，當原父進程消失或 `os.getppid() == 1` 時立即自我終止。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.space` 既有之 `get_default_registry()` 與 `get_default_scanner()` 作為全進程唯一空間註冊與快照入口。
  - 復用 `core.platform.process` 擴充進程樹收割與記憶體量測原語。
  - 復用 `MasterSupervisor.restart_worker()` 與 `_idle_ttl_loop()` 執行無縫回收。
- **邊界排除 (Explicitly Excluded)**：
  - **不卸載 `EmbeddingService` 常駐 ONNX 模型**（模型保持常駐以保障語義搜尋回應速度）。
  - **不採用寫死單一硬編碼 MB 水位作為唯一重啟條件**（改採基於動態工作集基線、單調漂移與系統可用記憶體壓力的演算法評估）。
  - 不變更公開 CLI 指令介面與磁碟快照二進位格式（`YFP2`）。
- **架構影響範圍**：
  - `module:core`：`core/platform/process.py`、`core/platform/__init__.py`、`core/space/scanner.py`、`core/space/registry.py`、`core/space/providers.py`、`core/space/hasher.py`。
  - `module:server`：`server/config.py`、`server/master.py`、`server/worker.py`、`server/space_watcher.py`、`scripts/cli.py`。
  - `module:ast`：`ast_engine/bundler.py`、`ast_engine/engine.py`。
  - `module:knowledge-db`：`knowledge_db/service.py`、`knowledge_db/pipeline.py`、`knowledge_db/retrieval.py`、`knowledge_db/embedding.py`。
  - `module:gdrive-support`：`gdrive_support/config.py`。
  - `module:dev`：`dev/tester.py`、`dev/testing/runner.py`、`dev/testing/sandbox.py`、`scripts/cli.py`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 廢除死板硬編碼水位，採「模組記憶體自治 + Server 演算法異常偵測 (`WorkerMemoryHealthMonitor`)」**：
  - 各模組負責清理自身建構期暫存，且 `WarmWorker` 在前景任務與所有背景 `ServiceWorker` 均處於 Idle 時執行 `gc.collect()` + `malloc_trim(0)`（避免在背景 `KnowledgeDBServiceWorker` 處於 `STATE_UPDATING` 峰值期間誤採樣或誤重啟）。
  - `MasterSupervisor` 以演算法追蹤 Worker `trim` 後的真閒置 RSS 序列：
    1. 自動學習預熱與首次索引載入後的**自然工作集基線 $B_{\text{base}}$**（含最小安全分母保底 `256 MB`）。
    2. 計算**膨脹倍率 ($R_{\text{idle}} / B_{\text{base}}$)**、**淨增量 ($\Delta R = R_{\text{idle}} - B_{\text{base}}$)** 以及**滑動視窗單調不回落斜率（Monotonic Ratcheting Score）**。
    3. 結合宿主系統 **`MemAvailable` 可用記憶體比例** 動態調整敏感度：當偵測到持續單調洩漏不回落或系統陷入高記憶體壓力時，於 Worker 完全 Idle 期間無縫觸發 `restart_worker()`。
- **[P00:DR-02] `EmbeddingService` 模型維持常駐，精準時序釋放 `SemanticBundler` 快取並共用 `UnifiedSymbol` SSOT**：
  - `EmbeddingService` 的 FastEmbed ONNX 模型保持常駐不卸載。
  - `SemanticBundler` 新增 `clear_transient_caches()`，嚴格於 `ASTEngine.build_index` 與 `hot_patch_index` 完成 `extract_all_call_sites_and_imports()` / `extract_dirty_call_sites_and_imports()` 與 `_collect_space_generations_and_files_map()` **之後**呼叫，確保圖譜作用域解析與世代收集 100% 正常運作後再釋放暫存；且在常駐 Worker 內全面禁止啟動 `ProcessPoolExecutor` (`fork`)。
  - `knowledge-db` 在同進程內（含建構、增量與冷啟動載入後）與 `ASTEngine._snapshot.symbols` 對齊指向同一 `UnifiedSymbol` 實例（裁剪 `spaces` 時以淺拷貝替換，不原地污染 `ASTEngine` 快照）；`_collect_all_dirty_files` 以 `ast_engine.bundler.registry.get_parser(path) is not None` 判定是否需要連動 `ast_engine.hot_patch_index`（保留 `.md` 的 AST 解析連動，僅排除無 AST 解析器之檔案）。
- **[P00:DR-03] `core.space` 全面單例化、快照記憶體快取、Watcher 智慧感知與 `scan(None)` 雜湊複用**：
  - 下游全面統一使用 `get_default_registry()` 與 `get_default_scanner()`（當指定自訂 `storage_root` 時保持獨立隔離）。
  - `SpaceScanner` 對 `.yfp2.bin` 快照加入 `(mtime_ns, size)` 校驗之記憶體快取；`diff` / `consume_diff` 在 `auto_refresh=None`、無自訂 `_explicit_storage_root` 且 Watcher 在線時自動採用 `auto_refresh=False`（並移除 `ASTEngine` 中硬編碼的 `auto_refresh=True`）。
  - `scan(None)` 在同輪掃描內快取物理檔案 `(abs_path, size, mtime_ns) -> content_hash`，讓合成空間與 `__all__` 免除重複 Blake2b 檔案雜湊讀取，同時保留各空間自身的 `created_gen`/`updated_gen` 世代推進與 `/workspace` 排除規則；`CoreSpaceWatcherServiceWorker` 批次合併更新合成空間與 `__all__`。
- **[P00:DR-04] 沙盒進程樹穿透 `setsid()` / `spawn_detached` 遞迴收割與父進程存活監控**：
  - 強化 `kill_process_tree` 遞迴掃描 `/proc` 子進程樹與 `reap_sandbox_processes(sandbox_dir)`（清理所有 `cwd`、命令列或 `YSCB_SANDBOX_DIR` 指向該沙盒之脫離背景進程），並於 `dev test` / `dev op-test` 實作信號轉發與 Parent-Death Watchdog。
- **[P00:DR-05] 實機 CLI 效能與常駐記憶體深度調優（`ASTEngine` 宣告式目標空間、`workflow.archived://` 排除、`Posting` 無字典緊湊槽位與 `EmbeddingService` 截斷讓渡）**：
  1. **`ASTEngine` 目標空間廢除硬編碼黑名單，改採 `contributes` + SDK/Hook 期動態注入**：
     - 徹底移除 `bundler.py` 與 `ast/scripts/hook.core.py` 中硬編碼的 `("cloud", "gitignore", "workspace")` 與 `_is_cloud_space()`。
     - 於 `ast/contributes/_format.json` 擴充 `"spaces": "list[str]? | extend"`，由 `ast/contributes/ast.json` 宣告 `{"spaces": ["source"]}`、`agents-workflow/contributes/ast.json` 宣告 `{"spaces": ["docs", "plans"]}`。
     - `ASTEngine` / `SemanticBundler` 提供 `register_spaces(spaces)` 與 `get_target_spaces()` SDK 並支援 `on_register_ast_spaces` 事件注入；`KnowledgeEngine` 初始化時自動呼叫 `ast_engine.register_spaces(self.space_weights.keys())`，確保所有被 `knowledge-db` 索引之空間 100% 納入 `ASTEngine` 解析。
     - `ASTEngine.ensure_jit_synced()` 與 `ast/scripts/hook.core.py` 嚴格以 `get_target_spaces()` 為邊界檢查/消費 diff，禁止傳入 `space_name=None` 掃描未納管之 `cloud` 空間，且當記憶體已有 `_snapshot` 且 Watcher 在線無 `.watcher_dirty` 時 $O(1)$ 極速返回。
     - 同步修復 `core/space/watcher.py:is_watcher_active`，忽略無 `entries`/`compose` 之純規則預設空間（如 `project/workspace`），避免 `is_watcher_active(None)` 誤判為 `False`。
  2. **`agents-workflow` 空間排除規則收口至語意 URI `workflow.archived://`**：
     - 於 `agents-workflow/contributes/core.json` 移除舊時代 `"archive"` 字串，`plans` 空間設為 `"exclude": [".git", "workflow.archived://"]`（保留 `workflow.roadmap://` 於 `plans` 檢索中），`docs` 空間設為 `"exclude": [".git"]`，消除 2,067 個歷史封存計畫檔造成的百萬級無效倒排節點與 2.2 GB 記憶體膨脹。
  3. **`Posting` 廢除百萬個 `SparseFieldFreqs` Python `dict` 實例，改採 4 整數固定槽位**：
     - `Posting.__slots__` 改用 `_f_name`、`_f_sig`、`_f_members`、`_f_doc` 四個 `int` 槽位（並提供 `get_field_freq(field)` 與向後相容之 `@property def field_freqs`），將每個 `Posting` 的額外字典開銷（240 bytes）降至 `0`，並於 `InvertedIndex.load_binary` 後觸發 `trim_process_memory()`。
  4. **`EmbeddingService` 嵌入文本截斷與 `KnowledgeDBServiceWorker` 前景任務讓渡**：
     - `MAX_SYMBOL_DOCSTRING_EMBED_CHARS` 由 `1000` 調降至 `400`，避免超長中文 Markdown 觸發 ONNX Runtime 512-token 最差情況記憶體競技場（Arena）暴增；`KnowledgeDBServiceWorker` Stage 2 微批次迴圈偵測前景任務活躍時主動讓渡 CPU/GIL。

---

## 3. 開放議題與確認紀錄

- 開發者已確認核心架構方向、完成 `/blind-subagent` 審查，並於實機壓力測試後確認 `[P00:DR-05]` 四項根因優化。
