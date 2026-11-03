# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：可靠性強化與工程治理修復  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `dev/builder.py` 確定性壓縮（跨不同檔案 mtime 與 CRLF/LF 輸入產出恆等 SHA-256）、`_update_release_index` 自動寫入 `releases[<ver>]["sha256"]`，以及 `ys_codebase/release/*/index.json` 全數 `active` 版本皆具備有效 64 字元 SHA-256 | FR-01, NFR-01, NFR-02 | `python yscb.py dev test dev -q` |
| **FT-02** | 單元測試 | 驗證 `core/engine.py`、`core/installer.py` 與 `yscb.py` 下載正式版模組 `.zip` 時強制校驗 `index.json` 之 `sha256`（缺失或不符時拋出 `RuntimeError` 並清理暫存檔）、`--ignore-sha256` 顯式告警放行、`@build` 本地開發版豁免，以及 `self-update` 頂層符號結構（`__version__`/`main`）與 `--sha256`/`.sha256` 校驗 | FR-01, FR-02, EC-01, EC-02, EC-03, NFR-01, NFR-02 | `python yscb.py dev test core -q` |
| **FT-03** | 單元測試 | 驗證 `OSBackend.atomic_write` 於 Windows 10 次 `os.replace` 重試耗盡後直接拋出 `PermissionError` 並完整保留原目標檔與清理 `.tmp`（EC-04）；驗證 `OSBackend.remove(..., missing_ok=True)` 僅忽略 `FileNotFoundError`，對唯讀檔執行 `chmod` 重試，並對 `EBUSY`/`PermissionError` 正常拋出異常（EC-05） | FR-04, FR-05, EC-04, EC-05, NFR-02 | `python yscb.py dev test core -q` |
| **FT-04** | 單元測試 | 驗證 `UpdateChecker._check_host_script_update` 於 `yscb.py` 版本相同但內容不同時偵測 `is_drift=True` 並產生漂移警告提示，且對純 CRLF/LF 換行差異不誤報（EC-06） | FR-08, EC-06, NFR-02 | `python yscb.py dev test core -q` |
| **FT-05** | 單元測試 | 驗證 `WarmWorker.execute_task` 透過 `_restore_env_diff` 差量還原環境變數，在併發背景執行緒高頻讀取 `os.environ` 時絕不發生 `PATH` 或基準變數瞬間消失，並於任務結束後精確還原新增/修改/刪除之環境變數 | FR-03, FR-07, NFR-02 | `python yscb.py dev test server -q` |
| **FT-06** | 靜態合規與盲審 | 驗證 `dev/checker.py` 裸 `except:` 靜態告警（FR-07）、`.github/workflows/ci.yml` 工作流語法（FR-06）、全倉 7 模組 `dev check --all` 與 `contributes check` 合規，以及通過 Pre-UX 盲眼子代理審查 | FR-06, FR-07, NFR-02 | `python yscb.py dev check --all && python yscb.py contributes check` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev` 測試集 86 passed（含 `test_deterministic_zip_packaging_and_release_sha256_index`）；全倉 7 模組 43 個 active release 版本 100% 具備真實 SHA-256 | 2026-11-03 |
| **FT-02** | `Passed` | `core` 測試集 243 passed（含 `test_act_download_enforces_sha256_and_supports_ignore_flag_and_build_exemption`、`test_self_update_validates_ast_structure_and_sha256`、`test_bootstrap_enforces_sha256_and_ignore_flag`） | 2026-11-03 |
| **FT-03** | `Passed` | `core` `test_vfs.py` 通過（含 `test_atomic_write_win32_exhaustion_preserves_target_and_cleans_tmp`、`test_remove_directory_missing_ok_propagates_non_enoent_errors`） | 2026-11-03 |
| **FT-04** | `Passed` | `core` `test_update_checker.py` 通過（含 `test_host_script_same_version_content_drift_detected`、`test_host_script_crlf_vs_lf_no_false_drift`） | 2026-11-03 |
| **FT-05** | `Passed` | `server` 測試集 53 passed（含 `test_worker_restore_env_diff_without_clearing_os_environ` 併發觀察執行緒 0 次遺失環境變數） | 2026-11-03 |
| **FT-06** | `Passed` | 7 模組 `dev check --all` 與 23 檔 `contributes check` 全數 `PASS`；`test_checker_bare_except_emits_antipattern_warning` 通過；Pre-UX 盲眼子代理（`48351e40`）回傳 `REVIEW_STATUS: PASSED` | 2026-11-03 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認確定性壓縮、`index.json` SHA-256 強制驗證、`--ignore-sha256` 逃生閥、`@build` 豁免與 `self-update` 結構/雜湊檢查之實作與測試結果 | `[測試通過]` | 於臨時兄弟目錄 `/workspace/ys-codebase-uat-sub03` 完成端到端實測（確定性 SHA-256、缺失/錯誤 `sha256` 阻斷、`--ignore-sha256` 放行、`@build` 豁免與 `self-update` 結構/雜湊檢查均通過） |
| **UX-02** | 確認 `WarmWorker` 差量環境變數還原、`OSBackend` 原子寫入/刪除錯誤傳遞、`yscb.py` 內容漂移偵測、`dev check` 裸 `except:` 告警與 `.github/workflows/ci.yml` 之實作與測試結果 | `[測試通過]` | 於臨時兄弟目錄完成端到端實測（併發觀察執行緒 0 次遺失環境變數、`atomic_write` 保全原檔、`remove` 傳遞 `EBUSY`、裸 `except:` 告警與同版本內容漂移偵測均通過） |

