# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_server_hook_integration  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SpaceConfig.watch` 與 `define_ephemeral_space` 預設 `watch=True`、可覆寫 `watch=False`，且同進程頂層 `define_ephemeral_space("yscb-skills", ...)`、`scan`、`consume_diff` 與 `get_default_registry`/`get_default_scanner` 共享動態空間定義、快照與游標 | FR-01 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_watch_default_ephemeral_shared_registry_and_watcher_coordination` |
| **FT-02** | 單元測試 | 驗證 `ScanDiffResult` 頂層 `.has_changes` / `.added` / `.modified` / `.deleted` / `.unchanged` 唯讀屬性、`subscribe` 雙軌過濾（短名 `"source"` 匹配 `"core/source"` 及反向匹配）與 `broadcast_file_space_changed` 以 `emit_module="core"` 發送 `on_file_space_changed` | FR-02 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_watch_default_ephemeral_shared_registry_and_watcher_coordination` |
| **FT-03** | 單元測試 | 驗證同進程活躍 Watcher 存在待防抖髒事件時，`snapshot`/`merkle_root`/`diff`/`consume_diff` 自動先呼叫 `flush_space_now(space_query)`，且跨進程 `.watcher_dirty` 標記自動觸發增量 `scan` | FR-03 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService.test_ephemeral_space_dynamic_registration_and_in_process_flush` |
| **FT-04** | 整合測試 | 驗證 `server/contributes/server.json` 自動註冊 `core-space-watcher` (`CoreSpaceWatcherServiceWorker`)、500ms 防抖合併、`patch_files` 局部更新、`<owner>/<space>` 更新後自動同步短名聯集 `<short_name>` 與 `__all__` 快照，以及 `define_ephemeral_space` 動態熱掛載監聽入口 | FR-04 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService` |
| **ET-01** | 邊界測試 | 驗證無 `server` 或無活躍 Watcher 時，`is_watcher_active` 回傳 `False`，`core.space` 100% 純本地拉取運作且零第三方套件依賴 | EC-01, NFR-01 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_watch_default_ephemeral_shared_registry_and_watcher_coordination` |
| **ET-02** | 邊界測試 | 驗證全域 `.yscb.lock` 持有期間，`flush_dirty_spaces` 與 `flush_space_now` 自動避讓、遞增 `deferred_by_lock_count` 並保留髒佇列，待鎖釋放後正常推進世代 | EC-02 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService.test_debounce_coalescing_lock_deference_and_event_broadcast` |
| **ET-03** | 邊界測試 | 驗證 `.git` / `__pycache__` / `.cache` / `*.tmp` / `.yscb.lock` 0-syscall 快篩忽略，以及目錄級 `created`/`moved`/`deleted` 事件自動升級為 `_full_rescan_spaces` 全量掃描 | EC-03 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService.test_debounce_coalescing_lock_deference_and_event_broadcast` |
| **ET-04** | 邊界測試 | 驗證常駐運行期間呼叫 `define_ephemeral_space("yscb-skills", ...)` 自動觸發 `sync_watched_directories` 掛載入口，且記憶體快照不產生 `.yfp2.bin` 實體檔案 | EC-04, NFR-02 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService.test_ephemeral_space_dynamic_registration_and_in_process_flush` |
| **ET-05** | 邊界測試 | 驗證 `watcher_state.json` 與 `.watcher_dirty` 嚴格落地於 `cache://core/space/`，且 `stop()` 冪等清理狀態檔與重置髒標記 | EC-05, NFR-02, NFR-03 | `python yscb.py dev test --target=server:TestCoreSpaceWatcherService.test_service_contributes_loading_and_lifecycle_beacons` |
| **RT-01** | 回歸測試 | 驗證 `module:core` 合規檢查與全套沙盒測試 100% 通過 | NFR-01~NFR-03 | `python yscb.py dev check core ; python yscb.py dev test core -q` |
| **RT-02** | 回歸測試 | 驗證 `module:server` 合規檢查與全套沙盒測試 100% 通過 | FR-04, NFR-03 | `python yscb.py dev check server ; python yscb.py dev test server -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreSpaceAtomicEngine.test_watch_default_ephemeral_shared_registry_and_watcher_coordination` 通過 (`watch=True` 預設、覆寫與共享實例完全一致) | 2026-11-07 |
| **FT-02** | `Passed` | `ScanDiffResult` 頂層屬性、`subscribe` 雙軌過濾與 `on_file_space_changed` (`emit_module="core"`) 廣播斷言通過 | 2026-11-07 |
| **FT-03** | `Passed` | 同進程 `flush_space_now` 零延遲沖刷與跨進程 `.watcher_dirty` 自動重掃斷言通過 | 2026-11-07 |
| **FT-04** | `Passed` | `TestCoreSpaceWatcherService` (3/3 tests) 全數通過 (`core-space-watcher` 載入、防抖修補、短名聯集同步與動態空間熱掛載) | 2026-11-07 |
| **ET-01** | `Passed` | 無 `server`/無活躍 Watcher 下 `is_watcher_active=False` 且純標準庫拉取正常 | 2026-11-07 |
| **ET-02** | `Passed` | `.yscb.lock` 持有期間延後刷新 (`deferred_by_lock_count == 1`)，釋放後成功推進至 generation 2 | 2026-11-07 |
| **ET-03** | `Passed` | 黑盒路徑快篩回傳 `[]` 且目錄新增事件升級全掃推進至 generation 3 | 2026-11-07 |
| **ET-04** | `Passed` | `ephemeral/yscb-skills` 動態註冊即納入 `watched_spaces` 且零磁碟 `.yfp2.bin` 污染 | 2026-11-07 |
| **ET-05** | `Passed` | `watcher_state.json` 於啟動時寫入 `cache://core/space/`，於 `stop()` 時移除 | 2026-11-07 |
| **RT-01** | `Passed` | `dev check core` `PASSED`；`dev test core -q` 267/267 `PASSED` (1 skip, 0 fail) | 2026-11-07 |
| **RT-02** | `Passed` | `dev check server` `PASSED`；`dev test server -q` 62/62 `PASSED` (100% Ready, 0 fail) | 2026-11-07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server status` 檢視 `Background Services` 清單，確認 `[core-space-watcher] (module: server) : RUNNING` 隨常駐 Server 自動啟動並寫出 `ys_codebase/.cache/core/space/watcher_state.json` | `Pending` | 待驗收 |
