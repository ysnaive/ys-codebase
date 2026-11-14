# 專題調研與分析報告：CLI 觸發鍊、Worker 協作阻塞與 AST/KDB 增量更新審計 (R01_cli_worker_and_incremental_index_audit.md)

> 調研主題：CLI 指令觸發鍊、Server/Worker 協作卡死根因與 AST/KDB 增量更新深度評估  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：日常操作 `ys-codebase` CLI 與常駐 `server` 時易出現指令偶發凍結、中斷後後續指令排隊卡死、離線環境收尾延遲，以及代碼或文檔增量修改後 `ast` / `knowledge-db` 查詢耗時放大或檢索結果失準。
- **調研目標與範疇**：針對 `yscb.py`、`core`、`server`、`ast`、`knowledge-db`、`gdrive-support` 與跨模組 `hook.*.py` 執行 100% 源碼逐行剖析，定位所有死鎖、管道洩漏、鎖競爭與增量失步之精確座標與修復處方。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- **核心分析與實證內容**：
  1. **CLI 觸發鍊與同步級聯阻塞**：
     - `dispatcher._dispatch_inner` 未檢查 `YSCB_IN_SERVER_WORKER == "1"`，導致 `WarmWorker` 內任一任務或 Hook 若呼叫 `server_compatible=True` 之子進程或 `dispatch()`，將回打 Master `/api/dispatch` 並在單一 `_dispatch_lock` 上形成 120 秒確定性自死鎖。
     - `PipManager.install_packages` 與 `installer.fetch_and_extract_zip` 缺乏顯式 `timeout`；`UpdateChecker` 在 `--json` 模式下仍執行同步網路探測，離線時序列阻塞達 18～36 秒。
  2. **Server Master / `WarmWorker` 協作與背景寄生模型**：
     - `MasterSupervisor` 僅維護單一 `WarmWorker` 子進程，且 `CoreSpaceWatcher`、`KnowledgeDBServiceWorker`、`GDriveSyncServiceWorker` 三大常駐服務以執行緒寄生於同一 `WarmWorker` 內，共享 GIL 與 OS `fd 0/1/2`。
     - `WarmWorker` 在子進程模式下未將 IPC 控制管道抽離至不可繼承之專用 `fd > 2`，亦未隔離 `sys.stdin`：背景孫進程繼承 `fd 1` 後若 Worker 死亡，`proc.stdout.readline()` 永無 EOF 且 `_stream_task_over_worker_pipe` 未檢查 `proc.poll()`，導致 Master 永久死握 `_dispatch_lock`。
     - Client `Ctrl+C` 斷線後僅送出純協作式 `cancel`，無寬限期強殺升級；長耗時任務超過 120s 無輸出欠缺心跳保活；`stop()` 受 Python 3.11+ `ThreadingHTTPServer.block_on_close=True` 與無守衛 `restart_worker()` 競態影響可能掛起或復活孤兒 Worker；`GDriveSyncServiceWorker` 每輪輪詢無條件呼叫 `touch_activity()` 導致 Server Idle TTL 永久失效。
  3. **`core.space` 與 `module:ast` 增量更新評估**：
     - `SpaceScanner.diff()` 在 `cursor_cfg_hash != state.config_hash` 時將 `from_gen` 設為 `0`，隨即因 `if from_gen > 0` 丟棄全部 `is_deleted` 項目，造成新排除規則下的殭屍符號永久殘留。
     - `GrammarProvisioner._provision_lock()` 誤傳 `timeout=60.0`（正確參數為 `timeout_sec`），觸發兩次 `TypeError` 後退化為非阻塞 `acquire()` 且未檢核回傳值，跨進程 `pip` 鎖完全失效。
     - `hot_patch_index` 清空 `workspace_graph` 後，`callers/callees/impact` 以 `auto_sync=False` 水合 4-Pass 圖譜卻不寫回磁碟，導致獨立 CLI 每次查詢重跑全量 $O(N)$ 連結；`_snapshot` 原地變異字典在並發無鎖 `status`/`outline` 時可觸發 `RuntimeError`；快取缺乏 `schema_version` / `ast_config_hash` 自動失效機制。
  4. **`module:knowledge-db` 增量索引管線評估**：
     - `UnifiedSymbol.id` 不含內文雜湊且 `VectorIndex` 未記錄文本雜湊，同行號修改內文在兩階段同步下發生舊向量永久殘留；頂部插入空行導致行號平移時又重算全檔未改符號向量。
     - `_align_index_symbols_with_ast_snapshot` 未校驗世代即覆寫舊索引符號參照，使 `InvertedIndex.patch_incremental` 對新符號分詞刪除舊詞，造成倒排幽靈詞殘留與 `field_avgdl` 失真。
     - `get_engine()` 每次無條件進入 `reconfigure_model` 爭搶阻塞鎖 `_init_lock`；`WarmWorker` 內背景 Stage 2 禮讓前景設 `busy=False` 時，前景誤判向量已就緒而拿半成品向量執行 RRF 融合；髒檔絕對路徑未先收斂為專案相對路徑即參與後綴比對，存在跨空間同名檔誤刪風險。

---

## 3. 結論 (Conclusion)

- **核心結論**：上述卡死風險與增量失真皆具明確源碼根因與 100% 確定性工程修復方案，無須破壞任何既有公開 CLI 或 SDK 契約即可在現有微內核架構下徹底收斂。
- **後續建議（選填）**：採出口 ① 立即轉入本主計畫下之 `sub_01_cli_and_server_worker_resilience` 與 `sub_02_ast_and_kdb_incremental_integrity` 雙子計畫完成實作與全量驗證閉環。
