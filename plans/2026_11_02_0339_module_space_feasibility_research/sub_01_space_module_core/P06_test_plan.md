# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`module:space` 通用檔案空間、分級指紋快取與背景監聽底座模組 (`v1.0.0.0`) 實作  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_01_space_module_core  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `SpaceManager` 雙軌空間配置聚合、列表型欄位去重附加、純量欄位宿主覆寫、`define_ephemeral_space`、`iter_space_files` 與 `resolve_file_path` | FR-01 | `python yscb.py dev test space -q` (`test_space_manager.py`) |
| **FT-02** | 單元測試 | 驗證 `FingerprintScanner` 四種 `hash_policy`（`adaptive`、192KB 大檔稀疏抽樣、`full_hash`、`stat_only`、`lazy_stabilized`）計算正確性 | FR-02 | `python yscb.py dev test space -q` (`test_scanner_and_cursors.py`) |
| **FT-03** | 單元測試 | 驗證 `BinarySnapshotManager (YFP2)` 二進位快照原子寫入、`merkle_root()` O(1) 查詢與多消費者（`consumer_A` / `consumer_B`）獨立水位線 `diff` / `ack` / `reset_cursor` 隔離 | FR-03 | `python yscb.py dev test space -q` (`test_scanner_and_cursors.py`) |
| **FT-04** | 整合測試 | 驗證 `SpaceWatcherServiceWorker` 防抖批次收斂、`subscribe()` 程序內回呼與 `on_space_changed` 事件廣播 | FR-04 | `python yscb.py dev test space -q` (`test_service_and_cli.py`) |
| **FT-05** | 整合測試 | 驗證 `yscb.py space {status, scan, files, diff, clean} --json` 5 個 CLI 子命令結構化輸出與動態補全 | FR-05 | `python yscb.py dev test space -q` (`test_service_and_cli.py`) |
| **ET-01** | 邊界測試 | 驗證 10ms Racy-Clean 時間窗防護（`abs(scan_start_ns - mtime_ns) < 10_000_000` 時穿透 Stage 1 強制重算內容雜湊） | EC-01 | `python yscb.py dev test space -q` (`test_scanner_and_cursors.py`) |
| **ET-02** | 邊界測試 | 驗證 `YFP2` 快照截斷/損毀時拋出 `FingerprintCorruptedError` 並於 `refresh()` / `consume_diff()` 自動降級全量自癒重建，以及 `config_hash` 變更重置游標 | EC-02 | `python yscb.py dev test space -q` (`test_scanner_and_cursors.py`) |
| **ET-03** | 邊界測試 | 驗證 `consume_diff()` 區塊內拋出例外時**不推進** `acked_gen` 游標（At-Least-Once 語意），且不影響其他消費者 | EC-03 | `python yscb.py dev test space -q` (`test_scanner_and_cursors.py`) |
| **ET-04** | 邊界測試 | 驗證 `resolve_file_path` 路徑穿越（`..`）阻斷、未註冊空間拋出 `SpaceNotFoundError` 與非法配置拋出 `InvalidSpaceConfigError` | EC-04 | `python yscb.py dev test space -q` (`test_space_manager.py`) |
| **ET-05** | 邊界測試 | 驗證宿主持有 `.yscb.lock` 交易鎖期間 `SpaceWatcherServiceWorker` 延遲讓路，待鎖釋放後單次收斂更新 | EC-05 | `python yscb.py dev test space -q` (`test_service_and_cli.py`) |
| **PT-01** | 效能與合規 | 驗證熱快取 `refresh()` / `merkle_root()` 零檔案開啟讀取耗時 `< 30ms`，且 `python yscb.py dev check space` 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check space` & `python yscb.py dev test space -q --type=all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_space_manager.py` 雙軌配置聚合、宿主覆寫与檔案列舉全數通過 | 2026-11-02 |
| **FT-02** | `Passed` | 四模分級雜湊 (`adaptive`, `full_hash`, `stat_only`, `lazy_stabilized`) 與 192KB 抽樣斷言通過 | 2026-11-02 |
| **FT-03** | `Passed` | `YFP2` 二進位讀寫、`merkle_root()` 與多消費者獨立水位線隔離斷言通過 | 2026-11-02 |
| **FT-04** | `Passed` | `SpaceWatcherServiceWorker` 防抖與 `on_space_changed` 事件廣播斷言通過 | 2026-11-02 |
| **FT-05** | `Passed` | `space {status, scan, files, diff, clean} --json` 5 個子命令與实機掃描 (`source`/`docs`/`plans`) 通過 | 2026-11-02 |
| **ET-01** | `Passed` | Racy-Clean 10ms 時間窗內同大小改檔成功偵測內容變更 | 2026-11-02 |
| **ET-02** | `Passed` | `YFP2` 截斷/壞檔與 `config_hash` 變更自癒重建通過 | 2026-11-02 |
| **ET-03** | `Passed` | `consume_diff()` 拋出例外時 `acked_gen` 保持不變，重試可再次取得相同 diff | 2026-11-02 |
| **ET-04** | `Passed` | 路徑穿越攔截與 `SpaceNotFoundError` / `InvalidSpaceConfigError` 斷言通過 | 2026-11-02 |
| **ET-05** | `Passed` | `.yscb.lock` 存在期間延遲防抖、釋放後收斂通過 | 2026-11-02 |
| **PT-01** | `Passed` | `dev check space` (0 Errors, 0 Warnings) 與 `dev test space --type=all` (12/12, 100.0% Passed) | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py space status` 與 `python yscb.py space diff --consumer=knowledge-db`，檢視三大註冊空間 (`source`, `docs`, `plans`) 之檔案數、Merkle Root 與消費者游標狀態 | `[測試通過]` | 開發者實機驗證 `space status`、`space diff` 與常駐 `space-watcher` 世代推進 (`head_generation: 4 -> 8`) 運作正常 |

