# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `MasterSupervisor.start()` 剛性單例鎖守門與狀態檔時序重排 | 1. 當 `self._lock.acquire(blocking=False)` 返回 `False` 時，代表已有存活 Master 進程持有 OS 檔案鎖（`daemon.lock`），`start()` 必須立即返回既有 `state.pid`（若 `daemon.json` 尚未落盤則返回 `0`）並終止啟動流程，**嚴禁穿透向下建立第二套 HTTP Server、`WarmWorker` 或 `ModulesWatcher`**。<br/>2. 取得 `daemon.lock` 並完成 HTTP Server 動態埠綁定後，立即執行首次 `self._write_state()`（此時 `worker_pid=0`），待 `self._spawn_worker()` 完成後再執行第二次 `self._write_state()` 更新 `worker_pid`，消除啟動期狀態檔真空窗口。 | P0 | [P00:DR-01] |
| **FR-02** | `MasterSupervisor.restart_server()` 單次重入防護與優先停止 Watcher | 1. 於 `MasterSupervisor` 新增 `self._restarting: bool = False`，受 `self._stop_lock` 保護；當 `restart_server()` 被呼叫時，若 `_restarting` 或 `_is_stopped` 已為 `True`，立即忽略返回，確保單一 Master 生命週期最多僅能觸發一次自重啟執行緒。<br/>2. 於 `restart_server()` 觸發當下優先停止 `self.watcher`，防止自重啟退場期間繼續觸發輪詢回調。 | P0 | [P00:DR-02] |
| **FR-03** | `.modules/<mod>` 運行時 Staging 預組裝與目錄級原子替換 | 1. 於 `AtomicEngine` (`core/engine.py`) 實作單模組組態部署與模板剝離方法 `_deploy_and_strip_single_module_config(mod, mod_dir_path)`，支援對任意指定目錄提取 `configurable/` 與根目錄 `config.*.json` 至 `config://<mod>/` 並物理移除模板檔及 `.yscbignore`。<br/>2. 重構 `act_reload()` Stage 2 & Stage 3：針對每個目標模組，先於 `.modules/.staging_<mod>_<pid>_<ts>/` 臨時目錄完成壓縮包解壓（或鏡像複製）與 `_deploy_and_strip_single_module_config` 預組裝；隨後透過原子目錄切換辅助函式 `_atomic_swap_dir(staging_dir, target_dir)`（將舊 `target_dir` `os.replace` 至 `.modules/.old_<mod>_<pid>_<ts>`，再將 `staging_dir` `os.replace` 至 `target_dir`，最後刪除 `.old` 目錄）完成毫秒級無撕裂替換。<br/>3. 宿主 `yscb.py` 之 `_fetch_and_extract_zip(source, dest_dir)` 同步升級為在同父目錄下建立 `.staging_<basename>_<pid>` 完成解壓與校驗後，原子替換至 `dest_dir`。 | P0 | [P00:DR-03] |
| **FR-04** | 生命週期指令免預喚醒 Server 與 `daemon.lock` 啟動探測 | 1. 於 `core/commands/dispatcher.py` 定義環境變異指令集合 `_LIFECYCLE_MUTATION_COMMANDS = {"install", "update", "remove", "reload", "restore", "rollback", "bootstrap", "init", "self-update"}`；當 `module_name == "core"` 且目標主指令屬於該集合時，跳過執行前的 `_maybe_auto_spawn_server()`。<br/>2. 於 `_maybe_auto_spawn_server()` 中，除檢查 `daemon.json` 外，新增對 `.cache/server/daemon.lock` 之非阻塞鎖探測（若無法取得鎖代表已有 Master 正在啟動或運行中，立即返回不重複 `spawn_detached`）。 | P0 | [P00:DR-04] |
| **FR-05** | `Installer` 統一交易鎖覆蓋與 `ModulesWatcher` 感知 `.yscb.lock` | 1. 於 `core/installer.py` 之 `cmd_reload()` 與 `cmd_restore()` 補齊 `self.engine.act_lock("reload" / "restore")` 與 `try...finally: self.engine.act_unlock(...)` 跨進程鎖保護。<br/>2. 於 `server/watcher.py` 之 `ModulesWatcher` 新增 `_is_core_transaction_locked()` 探測（檢查 `yscb_root/.cache/.yscb.lock` 是否正被其他進程持有 OS 檔案鎖，或 `.modules/core/manifest.json` 暫時不存在）；當處於交易鎖定期間，`_poll_loop()` 略過本次快照更新與變更通知，待 `.yscb.lock` 釋放後再執行單次完整快照比對與重載通知。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 多進程同時啟動 `MasterSupervisor.start()`（`daemon.json` 尚未寫入之競爭窗口） | 後進入之進程因 `InterProcessLock.acquire(blocking=False)` 返回 `False` 立即終止返回 `0`，絕不穿透建立重複 HTTP Server 或覆寫 `daemon.json`。 |
| **EC-02** | Staging 目錄解壓失敗或發現 Zip Slip 惡意路徑 | 在 `.staging_<mod>_<pid>_<ts>` 階段即拋出異常並於 `finally` 清理 `.staging` 臨時目錄，原 `.modules/<mod>` 正式目錄 100% 保持原狀不受損毀。 |
| **EC-03** | `_atomic_swap_dir` 在將 `.staging` 移入 `target_dir` 時發生異常（或 Windows 短暫檔案佔用） | 針對 `os.replace` 提供最多 3 次短暫退避重試（`0.05s`）；若將舊目錄移至 `.old` 後、`staging` 移入 `target_dir` 失敗，自動將 `.old` 還原移回 `target_dir`，確保目標模組不消失。 |
| **EC-04** | 外部直接呼叫 `engine.act_deploy_configs_from_modules()` 單獨部署組態 | 保留 `act_deploy_configs_from_modules()` 公開介面並委派調用 `_deploy_and_strip_single_module_config`，確保向下相容與既有測試 100% 通過。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴純淨度 | `core`、`yscb.py` 與 `server` 維持 100% Python 標準庫實作（Zero Third-Party Dependencies）。 |
| **NFR-02** | 進程與記憶體隔離 | 執行 `python yscb.py update` 或連續並發觸發 `MasterSupervisor.start()` 時，背景最多僅允許存在 **1 個** Master 進程與 **1 個** Worker 進程，0 孤兒進程洩漏。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION] [DN-12]`（VFS 同目錄原子替換防跨磁碟區 `EXDEV`）**：Staging 與 Old 臨時目錄必須建立於 `.modules/`（或目標目錄之同級父目錄）下，嚴禁建立於系統 `/tmp`，以確保 `os.replace()` 位於同一檔案系統掛載點內，達成真正的毫秒級原子 rename。
- **`[!WARNING] [DN-06]`（物理剝離 `.modules/<mod>/` 組態模板與 `.yscbignore`）**：在 Staging 目錄內完成組態提取後，必須無條件刪除 `configurable/`、`config.*.json` 與 `.yscbignore`，確保交換進 `.modules/<mod>/` 的目錄 100% 純淨。
- **`[!CAUTION] [DN-08]`（`MasterSupervisor.stop()` 冪等防重入）**：`restart_server()` 與 `stop()` 共享 `_stop_lock` 狀態協調時，嚴禁在持有 `_stop_lock` 內部遞迴呼叫 `self.stop()` 造成死鎖。

