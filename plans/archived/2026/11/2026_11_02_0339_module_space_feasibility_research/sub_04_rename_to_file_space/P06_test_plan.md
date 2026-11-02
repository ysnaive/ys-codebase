# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全面將 `module:space` 更名為 `module:file-space`（基於 `git diff` 腳本精準掃描替換與反查驗收）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `file-space` 模組更名後之 `FileSpaceManager` 雙軌聚合、`FileSpaceConfig`、`FileSpaceOrigin`、`FileSpaceNotFoundError` 與 `InvalidFileSpaceConfigError` 100% 通過 | FR-01, FR-02 | `python yscb.py dev check file-space && python yscb.py dev test file-space -q` |
| **FT-02** | 單元測試 | 驗證 `file-space` 模組之 `FingerprintScanner`、`BinarySnapshotManager (YFP2)`、`FileSpaceWatcherServiceWorker` (`file-space-watcher`)、`on_file_space_changed` 事件與 `file-space` CLI (`status`/`scan`/`files`/`diff`/`clean`) 100% 通過 | FR-01, FR-02 | `python yscb.py dev test file-space -q` |
| **FT-03** | 整合與回歸測試 | 驗證 `knowledge-db` 與 `agents-workflow` 依賴 `file-space`（含 `scripts/hook.file-space.py`、`test_file_space.py`、`contributes/file-space.json`）全套合規檢查與單元測試 100% 通過 | FR-02, FR-03, NFR-01 | `python yscb.py dev check knowledge-db && python yscb.py dev test knowledge-db -q && python yscb.py dev check agents-workflow && python yscb.py dev test agents-workflow -q` |
| **ET-01** | 邊界與反向查驗測試 | 驗證 `git diff` 與 `git status` 範圍內 70 個變更/新增檔案之反向殘留掃描為 `0` 命中，且未誤傷 `workspace`/`namespace`/`whitespace`/`2-space` 等保護詞；驗證 `@build` 安裝後 `file-space status`、`knowledge-db status` 與 `server status` (`[file-space-watcher]`) 正常運行 | FR-03, EC-01, EC-02, EC-03 | `python yscb.py file-space status && python yscb.py knowledge-db status && python yscb.py server status` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev check file-space`: PASSED；`test_file_space_manager.py` 3/3 passed (100%) | 2026-11-02 |
| **FT-02** | `Passed` | `dev test file-space -q`: Pass 12 (100.0%), Fail 0, Skip 0 | 2026-11-02 |
| **FT-03** | `Passed` | `dev check knowledge-db`: PASSED, `dev test knowledge-db -q`: Pass 155 (100.0%), Fail 0；`dev check agents-workflow`: PASSED, `dev test agents-workflow -q`: Pass 138 (100.0%), Fail 0 | 2026-11-02 |
| **ET-01** | `Passed` | 反向審計腳本檢查 70 個檔案：`total suspicious hits: 0`；實機安裝 `file-space@1.0.0.build`、`knowledge-db@1.3.0.build`、`agents-workflow@1.2.2.build`，`server status` 顯示 `[file-space-watcher]` 與 `[knowledge-db-worker]` 均為 `RUNNING`，`knowledge-db status` 顯示 3 空間 (`docs`/`plans`/`source`) 游標 `gen 1/1` 已對齊且向量覆蓋率 `100.0%` (`14070/14070`) | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `python yscb.py file-space status`、`python yscb.py server status`（服務名 `[file-space-watcher] (module: file-space)`）與 `git status` 目錄結構（`ys_codebase/source/file-space/`、`ys_codebase/config/file-space/`、`docs/file-space/`），確認 `space` 全面更名為 `file-space` 符合預期 | `[測試通過]` | 開發者確認「通過」(2026-11-02) |

