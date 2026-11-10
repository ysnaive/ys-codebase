# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：常駐 Server 全量熱派發、下游背景 Worker 競態治理與 CLI 即時進度反饋暨靜態速查輕量化架構 (server_hot_dispatch_worker_race_and_ux_feedback)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 於 `2026_11_10_0025_declarative_readonly_file_lock_sdk` 長任務結束後，接續執行另一項涵蓋四大支柱之綜合架構升級：全量 `server` 熱派發盤點與斷線治理 + 下游背景 Worker 競態審查與前景禮讓 + 使用者 UX 指令即時進度反饋（例如 `ast` 在重建圖時，要反饋正在建圖、進度怎樣，至少要確認還有在運行不是卡死）+ 靜態狀態速查指令優化不要跑全量。
  2. 整併吸收 `kdb_vector_model_offline_guard_and_nonblocking_worker` 路線圖（拔除背景未授權隱式下載向量模型、實作 `EmbeddingService._init_lock` 非阻塞探測與 $O(1)$ 可用性短路）。
  3. **剛性守門約束（`[P00:DR-05]`）**：嚴禁從 `P06` 直接一路進入 `P07`；於 `auto` `P06` 斷點時，必須依 `@codebase-deep-auditor` 九維度標準（`C1~C9` / `A1~A5` / `D1~D5`）與 `@yscb-async-deep-audit` 三軌五步雙盲子代理融斷閉環進行靶向審查（最多 3 輪 `Loop 1 ~ Loop 3`，除非提早滿足 `P0=0, P1=0, P2=0` 且無殘留 `ARCH`/`PERF` 技術債而觸發融斷）。
- **核心目標**：
  1. **支柱一（全量 `server` 熱派發覆蓋與客戶端斷線協作取消）**：補齊 `gdrive-support` 之 `branch`（`list` / `create` / `delete`）等安全無狀態指令之 `server_compatible: true`；強化 `MasterSupervisor` HTTP 串流對客戶端斷線（`BrokenPipeError` / `ConnectionResetError` / TCP FIN）之主動探測，並透過非阻塞控制訊號 `{"action": "cancel"}` 通知 `WarmWorker` 設定協作取消旗標（`core.context.is_task_cancelled()`），防止客戶端 `Ctrl+C` 後長任務繼續無謂霸佔 Worker。
  2. **支柱二（前景絕對優先、背景 Worker 競態退讓與離線模型非阻塞守門）**：為 `WarmWorker` 前景任務建立引用計數保護之 `server.worker.foreground_active` 狀態；為 `CoreSpaceWatcherServiceWorker` 補齊前景活躍期間之背景掃描禮讓；拔除 `KnowledgeDBServiceWorker` Stage 2 未授權外網自動下載模型邏輯，將 `EmbeddingService._ensure_model()` 升級為非阻塞鎖探測（`acquire(blocking=False)`），並調整 `HybridSearchEngine.is_vector_available` 為 $O(1)$ `vector_index` 非空優先短路。
  3. **支柱三（人機雙通道嚴格分離之即時 UX 進度反饋與低延遲刷新）**：修正 `core.log`（`_write_to_active_target` 與 `DebouncedIOStreamer`）使顯式 `flush=True` 及 `stderr` `\r` 進度更新立即跨 IPC 推出；於 `core.log` 提供統一節流進度回報器 `ProgressReporter`，植入 `ast`（`build_index`、`hot_patch_index`、`WorkspaceGraphLinker.link_workspace`）與 `knowledge-db`（`build_unified_index`、`sync_incremental_changes`），確保耗時建圖期間終端機即時顯示階段與百分比，且 `--json` `stdout` 100% 純淨。
  4. **支柱四（靜態狀態速查 $O(1)$ 輕量化與單檔切片快速路徑）**：為 `knowledge-db` 建立 `unified.meta.json` 輕量元數據快取，徹底移除 `KnowledgeEngine.status()` 解壓 `.bin.gz` 與呼叫 `iter_space_files()` 全盤掃描之重型路徑；於 `BinarySnapshotManager` 增設零物件配置之 `load_summary()` 加速空間快照計數；強化 `ASTEngine.status()` 非阻塞鎖探針與 `building_in_progress` 即時進度回報；優化 `ASTEngine._resolve_symbol_node_for_slice()` 對 `<rel_path>::<fqn>` 與 `UnifiedSymbol` 走單檔 `parse_file()` $O(1)$ 快速路徑。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.context.RuntimeContext` 管理執行緒安全之 `foreground_active` 計數、任務取消事件（`task_cancel_event`）與跨模組狀態。
  - 復用 `core.log.DebouncedIOStreamer` 與 `LogExecutionScope` 平面隔離路由，避免進度訊息混入背景 `RollingFileLogger`。
  - 對齊 `ASTEngine` 既有 `unified.meta.json` 範式為 `knowledge-db` 建立對稱之 `indices/unified.meta.json`。
- **邊界排除 (Explicitly Excluded)**：
  - 模組生命週期變異指令（`core install/update/remove/reload/rollback/restore`、`server start/stop/status/reload`、`dev test`、`knowledge-db model download`、`ast/file-space/knowledge-db clean`）維持既有 `server_compatible: false` 契約不變。
  - 客戶端斷線時採協作式取消（`is_task_cancelled()` 迴圈切片檢查），絕不以 `SIGKILL` 粗暴強殺正在執行 `vfs` 原子寫入或持有跨進程鎖之 `WarmWorker`。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/{context.py,log.py}`、`core/commands/dispatcher.py`、`core/space/scanner.py`
  - `ys_codebase/source/server/server/{master.py,worker.py,space_watcher.py}`
  - `ys_codebase/source/gdrive-support/contributes/core.json`
  - `ys_codebase/source/ast/ast_engine/{engine.py,bundler.py,linker.py}`
  - `ys_codebase/source/knowledge-db/knowledge_db/{engine.py,pipeline.py,embedding.py,hybrid.py,service.py}`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

| 決策編號 | 議題描述 | 最終定案決策 |
| :--- | :--- | :--- |
| **DR-01** | 全量 `server_compatible` 邊界與客戶端斷線處理策略 | 補齊 `gdrive-support` `branch` (`list` / `create` / `delete`) 為 `server_compatible: true`；於 `MasterSupervisor` 偵測客戶端斷線並透過非阻塞控制流傳遞 `{"action": "cancel"}` 至 `WarmWorker` 觸發協作取消，同時保持 NDJSON `task_finish` 幀同步不失步。 |
| **DR-02** | 背景 Worker 競態禮讓與向量模型離線守門（吸收 `kdb_vector_model_offline_guard_and_nonblocking_worker`） | `CoreSpaceWatcherServiceWorker` 與 `KnowledgeDBServiceWorker` 雙重遵守 `server.worker.foreground_active` 禮讓；拔除 `KnowledgeDBServiceWorker` 未授權背景 `download_model()`；`EmbeddingService._ensure_model()` 採非阻塞鎖探測；`HybridSearchEngine.is_vector_available` 改為 `len(vector_index.doc_ids) > 0` $O(1)$ 優先短路。 |
| **DR-03** | 即時 UX 進度反饋與 `--json` / 單元測試零干擾設計 | `ProgressReporter` 預設具 `200ms` 啟動延遲門檻與 `250ms` 節流視窗（極短操作零噪音，耗時建圖即時輸出階段與百分比至 `stderr` 並強制 `flush=True`），支援 `YSCB_FORCE_PROGRESS=1` 測試強制啟用與背景 `ServiceWorker` 自動靜默，保證 `stdout` 100% 純淨。 |
| **DR-04** | 靜態狀態速查 $O(1)$ 元數據化與單檔 `slice` 隔離 | `KnowledgeEngine.status()` 優先讀取記憶體或 `unified.meta.json` 與 `BinarySnapshotManager.load_summary()`，嚴禁呼叫 `iter_space_files()` 或阻塞解壓 `.bin.gz`；`ASTEngine.status()` 全面改採非阻塞鎖探針並回報 `building_in_progress`；`ASTEngine._resolve_symbol_node_for_slice()` 對 `<rel_path>::<fqn>` 與 `UnifiedSymbol` 走單檔 `parse_file()` 快速路徑。 |
| **DR-05** | `P06` 斷點強制三輪靶向深度審計融斷守門 | 於 `P06` 初次測試通過後，強制啟動 `@codebase-deep-auditor` + `@yscb-async-deep-audit` 三軌雙盲子代理審查（最多 3 輪，零 `P0/P1/P2` 及零 `ARCH`/`PERF` 債方可融斷進入 `P07`）。 |

---

## 3. 開放議題與確認紀錄

- 所有範圍、四大支柱技術方案與 `P06` 靶向深度審計守門條件均已與開發者確認定案（無未決開放議題）。
