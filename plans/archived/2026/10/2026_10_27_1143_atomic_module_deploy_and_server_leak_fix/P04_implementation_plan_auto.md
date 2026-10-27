# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中有對應介面與明確行為定義
- [x] **邊界防護**：EC-01 ~ EC-04 涵蓋鎖競爭、Zip Slip 隔離、原子交換失敗回滾與向下相容
- [x] **依賴純淨**：符合 NFR-01（100% Python 標準庫）與 NFR-02（單例進程零洩漏）指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` / `docs/server/README.md` | None | 現有架構描述已涵蓋原子重載與雙進程模型，無須變動頂層導覽 |
| **專題手冊** | `docs/server/hot_reload_and_services.md` | Modify | 補充 `ModulesWatcher` 感知 `.yscb.lock` 交易鎖與單次重載防抖說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md`、`docs/server/DESIGN_NOTES.md` | Modify | 更新 `core` `[DN-06]`（Staging 預組裝與原子目錄切換）與 `server` `[DN-08]`（`start()` 剛性單例鎖與 `restart_server()` 防重入） |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `master.py`、`watcher.py`、`engine.py`、`dispatcher.py` 關鍵方法 Docstring |
| **發布日誌** | CHANGELOG.md | Modify | 於 Phase 7 結案時記錄本計畫變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：在 `ModulesWatcher._is_core_transaction_locked()` 中，如果透過 `InterProcessLock(lock_file).acquire(blocking=False)` 探測 `.yscb.lock`，一旦探測成功（代表 `core` 沒鎖）並立即 `release()`，是否會在高頻輪詢下短暫搶走剛準備執行 `act_lock()` 的 `core` 進程的鎖？  
> [*] **防護解法**：`core` 的 `AtomicEngine.act_lock()` 採用的是 `lock.acquire(blocking=True, timeout_sec=10.0)`（阻塞等待最多 10 秒，每 `0.05s` 重試）！因此就算 `ModulesWatcher` 進行微秒級的瞬時探測並立即 `release()`，`act_lock()` 也完全不會失敗；更進一步，若 `.cache/.yscb.lock` 檔案不存在，`_is_core_transaction_locked()` 直接返回 `False` 連 `open()` 都不執行，將日常開銷降至 0。

> [?] **尖銳問題 2**：當 `MasterSupervisor.start()` 因為拿不到 `daemon.lock` 而立即返回 `0`（或既有 PID）時，若呼叫端是 `server/scripts/cli.py:start()` 或是 `master.py:restart_server()` 透過 `python -c "MasterSupervisor(...).start(foreground=True)"` 背景拉起的子進程，它返回後會發生什麼事？  
> [*] **防護解法**：在 `foreground=True` 模式下，正常拿到鎖的 Master 會在 `self._httpd.serve_forever()` 阻塞常駐；而拿不到鎖的重複子進程在 `start()` 開頭直接 `return`，因此 `python -c "..."` 單行腳本立即執行完畢並自然退出（Exit Code 0），連 HTTP Server、Logger、Watcher、WarmWorker 都不會建立，更不會覆寫 `daemon.json` 或歸檔正在運行中 Master 的日誌！

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`server/master.py` & `server/watcher.py`)**：
   - 於 `MasterSupervisor.__init__` 新增 `self._restarting = False`。
   - 於 `MasterSupervisor.start()`：當 `not self._lock.acquire(blocking=False)` 時，讀取 `state = self.read_state()`，直接返回 `state.pid if (state and is_process_alive(state.pid)) else 0`，徹底移除向下穿透執行的邏輯；在 `self._httpd` 建立後立即呼叫 `self._write_state()`，待 `self._spawn_worker()` 後再呼叫一次 `self._write_state()`。
   - 於 `MasterSupervisor.restart_server()`：在 `_stop_lock` 保護下檢查並設定 `_restarting = True`（若已為 `True` 或 `_is_stopped` 則直接返回），並優先停止 `self.watcher`。
   - 於 `ModulesWatcher` 新增 `_is_core_transaction_locked()`，在 `_poll_loop()` 中若偵測到 `.yscb.lock` 被持有或 `.modules/core/manifest.json`（當 `.modules/core` 存在時）缺失，則跳過該輪快照比對。
2. **TASK-02 (`core/engine.py`, `core/installer.py`, `core/commands/dispatcher.py`, `yscb.py`)**：
   - 於 `AtomicEngine` 實作 `_atomic_swap_dir` 與 `_deploy_and_strip_single_module_config`，重構 `act_reload` 使用 `.modules/.staging_<mod>_<pid>_<ts>` 完成解壓、組態部署與模板剝離後原子切換至 `.modules/<mod>`，並確保 `finally` 清理任何殘留 `.staging_*` / `.old_*`。
   - 於 `yscb.py:_fetch_and_extract_zip` 實作同父目錄 `.staging_<name>_<pid>` 解壓後原子切換至 `dest_dir`。
   - 於 `Installer.cmd_reload` 與 `Installer.cmd_restore` 補齊 `act_lock` / `act_unlock`。
   - 於 `dispatcher.py` 新增 `_LIFECYCLE_MUTATION_COMMANDS` 過濾，並在 `_maybe_auto_spawn_server` 中加入 `daemon.lock` 非阻塞探測。
3. **TASK-03 (單元與回歸測試 & 文檔同步)**：
   - 於 `ys_codebase/source/server/tests/test_server.py` 新增單例鎖防穿透、`restart_server` 防重入與 `ModulesWatcher` `.yscb.lock` 延後測試。
   - 於 `ys_codebase/source/core/tests/test_distribution_lifecycle.py` 新增 Staging 原子切換、異常回滾與 `update` 免喚醒 Server 測試。
   - 執行 `dev check --all`、`dev test --all` 與 `@build` 熱部署驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 `MasterSupervisor.start()` 鎖獲取失敗時 100% 立即返回退出，且 `daemon.json` 在 `_spawn_worker()` 之前先行寫入初版狀態。
- **[P04:DR-02]** 確認 `act_reload()` 將組態部署與模板剝離前移至 `.modules/.staging_<mod>_<pid>_<ts>` 內完成，使交換進 `.modules/<mod>` 的目錄一次到位且不觸發二次刪檔事件。

