# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Server Worker 常駐記憶體演算法治理、Core Space 快取共享、AST/KDB 查表去重與測試沙盒孤兒進程清理  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core.space` 共享單例、`.yfp2.bin` 記憶體快取、Watcher 智慧感知與 `scan(None)` 雜湊複用 (`FR-01`, `EC-03`)**：於 `SpaceScanner` 建立基於 `(mtime_ns, size)` 的 `_snapshot_mem_cache`、將 `diff`/`consume_diff` 之 `auto_refresh` 預設改為 `None`（當 `is_watcher_active` 為 `True` 且無 `.watcher_dirty` 時自動採用 `auto_refresh=False` O(1) 讀取）、修正 `is_watcher_active` 忽略純規則空間（`project/workspace`）、於 `scan(None)` 複用物理檔案雜湊並新增 `sync_dependent_snapshots_batch`，統一 `gdrive-support`、`providers.py`、`hasher.py`、`space_watcher.py`、`ast`、`knowledge-db` 共用 `get_default_registry()` / `get_default_scanner()`。
  2. **`ASTEngine` 宣告式目標空間、`workflow.archived://` 排除、`SemanticBundler` 暫存釋放與 `Posting` 去字典化緊湊序列化 (`FR-02`, `FR-05`, `EC-02`, `NFR-01`)**：支援 `contributes/ast.json` 之 `"spaces"`（`ast`: `["source"]`、`agents-workflow`: `["docs", "plans"]`）與 `ASTEngine.register_spaces` / `on_register_ast_spaces` Hook 動態決定納管目標空間；於 `agents-workflow/contributes/core.json` 排除 `workflow.archived://`；於 `SemanticBundler` 新增 `clear_transient_caches()` 並在 Worker 內禁絕 `ProcessPoolExecutor`；將 `InvertedIndex` 之 `Posting` 改為四整數槽位與 6-tuple 緊湊序列化，共享 `ASTEngine._snapshot.symbols` 同 ID 實例、截斷過長 Docstring 並於前景 CLI 執行時讓渡背景微批次推論，使常駐 Worker RSS 由 `3.5~5.0 GB` 降至 **`386.5 MB`**（下降 `>89%`）。
  3. **`WorkerMemoryHealthMonitor` 演算法記憶體治理與 `dev test` 跨 Session 進程樹收割 (`FR-03`, `FR-04`, `EC-01`, `EC-04`, `NFR-02`)**：於 `core.platform.process` 新增 `get_process_rss_mb`、`get_host_memory_info`、`trim_process_memory`、`reap_sandbox_processes` 與穿透 `setsid()` 之 `kill_process_tree`；於 `MasterSupervisor` 實作 `WorkerMemoryHealthMonitor` 追蹤 Idle 基線膨脹比、單調漂移與宿主 `MemAvailable` 壓力並在背景服務非繁忙時無縫回收；於 `dev` 實作信號轉發、`cleanup_sandbox` 孤兒進程收割與 `op-test` Parent-Death Watchdog。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 新增 `get_process_rss_mb`、`get_host_memory_info`、`trim_process_memory`、`reap_sandbox_processes`，強化 `kill_process_tree` 穿透 `setsid()` 收割子孫進程 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出新增之進程記憶體與沙盒收割原語 |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 新增 `.yfp2.bin` 記憶體快取、`diff`/`consume_diff` 自動感知 Watcher、`scan(None)` 物理雜湊複用與 `sync_dependent_snapshots_batch` |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | 修正 `is_watcher_active` 忽略無 `entries` 且無 `compose` 之純規則空間 |
| `ys_codebase/source/core/core/space/providers.py` | Modify | 改用 `get_default_registry` 避免重複建構 `SpaceRegistry` |
| `ys_codebase/source/core/core/space/hasher.py` | Modify | `hash_space_or_path` 預設改用 `get_default_registry` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 改用 `get_default_registry` 共用空間配置 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 共用預設單例、啟動時確保 `__all__` 就緒、`flush_dirty_spaces` 採用 `sync_dependent_snapshots_batch` |
| `ys_codebase/source/server/server/service.py` | Modify | `BaseServiceWorker` 與 `ServiceManager` 支援查詢 `is_busy()` |
| `ys_codebase/source/server/server/worker.py` | Modify | 任務結束與背景閒置時呼叫 `trim_process_memory()`，並標記 `server.worker.foreground_active` 供背景服務讓渡 |
| `ys_codebase/source/server/server/master.py` | Modify | 實作 `WorkerMemoryHealthMonitor` 演算法記憶體異常偵測與無縫 `restart_worker()` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 於 `server status` 儀表板顯示 `Worker Memory` 即時 RSS、基線、峰值與自動回收計數 |
| `ys_codebase/source/ast/contributes/ast.json` | Modify | 宣告 `"spaces": ["source"]` 作為 AST 預設目標空間 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 新增 `clear_transient_caches()`；Worker 環境內禁絕 `ProcessPoolExecutor` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 實作 `register_spaces` / `get_target_spaces`、共用單例、目標空間非阻塞差異檢查與收尾 `clear_transient_caches()` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 新增 `_get_or_create_resolver` 快取 `DeterministicSymbolResolver` |
| `ys_codebase/source/ast/scripts/hook.core.py` | Modify | `on_space_changed` 依 `ASTEngine.get_target_spaces()` 動態過濾目標空間 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `Posting` 四整數槽位去字典化與 `InvertedIndex` 緊湊 6-tuple 序列化 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 將 `MAX_SYMBOL_DOCSTRING_EMBED_CHARS` 調降為 `400` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 初始化註冊 `space_weights` 至 `ASTEngine`，Watcher 活躍時採目標空間非阻塞差異檢查 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 共用 `ASTEngine._snapshot.symbols`、透傳 `allow_parallel`、僅對具 AST Parser 檔案觸發 `hot_patch_index` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 實作 O(1) 閒置守衛、前景 CLI 執行期間微批次讓渡與同步收斂後 `trim_process_memory()` |
| `ys_codebase/source/knowledge-db/scripts/hook.ast.py` | New | 實作 `on_register_ast_spaces` Hook 動態注入檢索空間至 `ASTEngine` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | `plans` 之 `exclude` 設為 `[".git", "workflow.archived://"]`，`docs` 設為 `[".git"]` |
| `ys_codebase/source/agents-workflow/contributes/ast.json` | New | 宣告 `"spaces": ["docs", "plans"]` 納入 `ASTEngine` 目標空間 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 快取 `source_sha1_cache.json` 與 `.gitignore` 同步指紋加速 `on_pre_cli_dispatch` |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 掛載 `SIGTERM`/`SIGINT`、`atexit` 進程樹清理與 `start_parent_death_watchdog` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | `cleanup_sandbox` 呼叫 `reap_sandbox_processes(sandbox_dir)` |
| `ys_codebase/source/dev/dev/tester.py` | Modify | `_run_op_test` 於沙盒模式啟動 Parent-Death Watchdog |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 對齊 `diff` / `consume_diff` 之 `auto_refresh: Optional[bool] = None` 簽名 |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 擴充快照記憶體快取、Watcher O(1) diff 與 `sync_dependent_snapshots_batch` 測試 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 擴充 `WorkerMemoryHealthMonitor` 演算法評估與背景繁忙防誤殺測試 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 擴充 `SemanticBundler.clear_transient_caches()` 與目標空間隔離測試 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 擴充 `UnifiedSymbol` 參照共享與非 AST 檔案免觸發 `hot_patch_index` 測試 |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 對齊 `SemanticBundler` 暫存快取釋放與符號實例共享驗證 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 擴充穿透 `setsid()` 孫進程收割與 `reap_sandbox_processes` 測試 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：8 大受影響模組合計 **811 項測試 100% 通過**（`core`: 285、`file-space`: 19、`gdrive-support`: 34、`ast`: 40、`knowledge-db`: 113、`server`: 65、`dev`: 110、`agents-workflow`: 145），0 失敗，並全數完成 `@build` 本機熱同步。
- **實機 UX / 人工驗證**：`[UX-01]` `[測試通過]` — 常駐 `WarmWorker` 連續執行 18 次 `ast` / `knowledge-db` CLI 任務後，`server status` 之 `Worker Memory` 穩定於 **386.5 MB**（Peak: `387.1 MB`, `Auto-Recycles: 0`），`ast` 平均內部派發耗時 **674.7 ms**（`outline` **274.4 ms**）、`knowledge-db search` 平均內部派發耗時 **509.4 ms**。
- **結案盲眼靜態審查**：`REVIEW_STATUS: PASSED`（確認無違反規格契約、淺層敷衍修補或死代碼）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 記錄 `2026_11_08_1405_server_worker_rss_and_orphan_process_fix` 完整架構與效能治理成果 |
| **中觀 (Meso)** | `docs/server/README.md`、`docs/core/README.md`、`docs/ast/README.md`、`docs/knowledge-db/README.md` | 已交付 | 補充 `WorkerMemoryHealthMonitor`、`core.space` 快照記憶體快取、`ASTEngine` 宣告式目標空間與 `Posting` 去字典化說明 |
| **中觀 (Meso)** | `docs/server/daemon_architecture.md` | 已交付 | 更新常駐 Worker 記憶體自治與演算法回收流程 |
| **中觀 (Meso)** | `docs/server/DESIGN_NOTES.md` | 已交付 | 登記演算法記憶體異常偵測與跨 Session 沙盒進程樹收割設計決策 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 嚴格維護 Docstring，標註動機理由 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
perf(server,core,ast,kdb,dev): govern worker RSS (~386MB), declarative AST spaces, compact postings, and sandbox process reaping
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
