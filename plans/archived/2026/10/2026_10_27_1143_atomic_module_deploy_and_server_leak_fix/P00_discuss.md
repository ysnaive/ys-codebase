# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 下游反饋當舊版調用 `python yscb.py update` 時，後台連續建立大量 `server` 實例洩漏導致 RAM 佔用暴表（該行為發生於人工開發者指令觸發自動背景 `server` 進程期間）。
  - 進一步討論並確立：模組運行時空間（`.modules/<mod>`）之安裝與重載應全面升級為原子寫入部署（Staging 預組裝 + 目錄級原子替換），搭配跨進程交易鎖與單例鎖防穿透機制。
- **核心目標**：
  1. **消除 `MasterSupervisor` 單例鎖穿透與重啟分裂 (`server/master.py`)**：當 `InterProcessLock` (`daemon.lock`) 獲取失敗時嚴格終止啟動（絕不因 `daemon.json` 尚未落盤而穿透執行）；拿鎖並綁定 HTTP Port 後立即寫入初始 `daemon.json`，再啟動 `WarmWorker`；於 `restart_server()` 增設單次重入守門鎖，並於 `stop()` 優先停止 `ModulesWatcher`。
  2. **模組運行時 `.modules/<mod>` 原子目錄部署 (`core/engine.py` & `yscb.py`)**：將 `act_reload()` 及自舉提取由「原地先 `rmtree` 後 `extractall`、事後刪 `configurable/`」重構為「於 `.modules/.staging_<mod>_<pid>/` 預先解壓、部署並剝除 `configurable/` 模板後，以 `os.replace` 執行目錄級原子切換（舊目錄移至 `.old_<mod>_<pid>` 後清除）」，徹底消除 `.modules/` 撕裂狀態與多次檔案變動風暴。
  3. **生命週期指令免喚醒與 `.yscb.lock` 交易鎖協同 (`core/commands/dispatcher.py`, `core/installer.py`, `server/watcher.py`)**：
     - `dispatcher.py`：執行 `core` 環境變異指令（`update`, `install`, `remove`, `reload`, `restore`, `rollback`, `bootstrap`, `init`, `self-update`）前禁止觸發 `_maybe_auto_spawn_server()`；且 `_maybe_auto_spawn_server()` 額外非阻塞探測 `daemon.lock` 防範啟動期重複 spawn。
     - `installer.py` & `watcher.py`：確保 `cmd_reload` / `cmd_restore` 亦納入 `.yscb.lock` 保護；`ModulesWatcher` 輪詢期間若偵測到 `cache://.yscb.lock` 正被持有（或 `.modules/core/manifest.json` 暫不可讀），自動延後快照比對，待整批更新與 `scan_and_inject` 交易結束釋放鎖後再觸發單次重載。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `yscb.config.json` 或模組 `manifest.json` 之外部組態 Schema。
  - 不影響日常業務指令（如 `knowledge-db search`、`agents-workflow plan`）在無鎖狀態下的正常背景喚醒與熱派發行為。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/engine.py`（`act_reload` / `act_deploy_configs_from_modules` 單模組 Staging 預組裝與原子目錄替換）
  - `ys_codebase/source/core/core/installer.py`（`cmd_reload` / `cmd_restore` 統一交易鎖覆蓋）
  - `ys_codebase/source/core/core/commands/dispatcher.py`（環境變異指令排除 `_maybe_auto_spawn_server` 與 `daemon.lock` 探測）
  - `yscb.py`（自舉與還原 `_fetch_and_extract_zip` 支援同目錄隱藏 Staging 原子替換）
  - `ys_codebase/source/server/server/master.py`（`start()` 鎖失敗剛性退出、先寫 `daemon.json` 再建 Worker、`restart_server()` 單次重入鎖）
  - `ys_codebase/source/server/server/watcher.py`（感知 `.yscb.lock` 交易鎖延後快照與防抖）
  - `ys_codebase/source/core/tests/` 與 `ys_codebase/source/server/tests/`（單元與並發回歸測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `MasterSupervisor.start()` 剛性單例鎖守門與狀態檔時序重排**：
  - `InterProcessLock` 基於 OS 核心檔案鎖（`flock` / `msvcrt.locking`），唯有持有鎖之進程存活時 `acquire(blocking=False)` 才會返回 `False`。因此一旦 `acquire` 失敗，代表必有活躍 Master 實例，必須立即返回既有 PID 或 `0` 並退出，**嚴禁穿透啟動第二套 HTTP Server 與 Worker**。
  - 取得 `daemon.lock` 並綁定 HTTP Port 後，立即呼叫 `self._write_state()`（此時 `worker_pid=0`），待 `_spawn_worker()` 完成後再次更新 `self._write_state()`，徹底消除啟動窗口期 `daemon.json` 缺失導致外部重複 spawn 的競態。
- **[P00:DR-02] `MasterSupervisor.restart_server()` 單次重入防護與 Watcher 優先停機**：
  - 新增 `self._restarting = False` 與鎖保護，確保單一 Master 實例生命週期內最多只會衍生一次 `_do_restart` 執行緒，防止 `ModulesWatcher` 或多處訊號重複呼叫 `restart_server()` 造成指數級進程分裂。
- **[P00:DR-03] `.modules/<mod>` 運行時安裝/重載採 Staging 預組裝與目錄級原子替換 (Atomic Directory Swap)**：
  - 在 `engine.py:act_reload` 中，針對每個目標模組先於 `.modules/.staging_<mod>_<pid>/` 解壓 Zip，並在 Staging 內直接完成組態模板（`configurable/` 與 `config.*.json`）提取部署至 `config://` 及物理剝除模板檔。
  - 完成預組裝後，將既有 `.modules/<mod>` 以 `os.replace` 移至 `.modules/.old_<mod>_<pid>`，隨即將 `.staging_<mod>_<pid>` 以 `os.replace` 原子替換為 `.modules/<mod>`，最後清理 `.old_<mod>_<pid>`（附帶 Windows 短暫句柄佔用退避重試與異常回滾恢復）。
  - 宿主入口 `yscb.py` 之 `_fetch_and_extract_zip` 同步升級為同層 `.staging_<name>_<pid>` 提取後原子替換。
- **[P00:DR-04] 生命週期指令免預喚醒與 `.yscb.lock` 跨進程交易感知**：
  - `dispatcher.py`：當 `module_name == "core"` 且指令為 `{"install", "update", "remove", "reload", "restore", "rollback", "bootstrap", "init", "self-update"}` 時，跳過執行前的 `_maybe_auto_spawn_server()`；並在 `_maybe_auto_spawn_server()` 中探測 `daemon.lock` 是否已上鎖。
  - `ModulesWatcher`：在 `_poll_loop` 檢測變更前，若偵測到 `yscb_root/.cache/.yscb.lock` 正處於被鎖定狀態，暫停快照更新與回調通知，待 `core` 釋放 `.yscb.lock`（即全部模組原子替換與 `scan_and_inject` 均已完成）後，才執行唯一一次差異計算與重載通知。

---

## 3. 開放議題與確認紀錄

- [x] 根因分析與四道防線（Server 單例鎖防穿透、`.modules/` Staging 原子目錄替換、Dispatcher 生命週期指令守門、Watcher 感知 `.yscb.lock` 交易鎖）已由開發者確認通過。
- [x] 分流模式判定為 **Full Track 標準開發計畫**。

