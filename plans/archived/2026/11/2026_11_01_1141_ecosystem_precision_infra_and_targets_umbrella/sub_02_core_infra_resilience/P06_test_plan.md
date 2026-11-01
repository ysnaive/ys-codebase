# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core / dev / server 基礎設施韌性、跨分支 cmd_restore 自癒與 Windows 句柄釋放加固  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `yscb.py` 與 `Installer.cmd_restore` 於 `.modules/<name>/manifest.json` 之 `installed_ver != ver` 時自動覆寫更新；版本一致時正確跳過 | FR-01 | `test_installer.py:test_cmd_restore_cross_branch_version_mismatch_and_corrupted_manifest` |
| **FT-02** | 單元測試 | 驗證 `PipManager._bootstrap_pip` 與 `ensure_venv` 失敗時統一拋出 `PipInstallError`，且 `Installer.sync_pip_dependencies` 攔截並降級為 `[core:pip] Warning:` | FR-02, EC-02 | `test_venv_core.py:test_ensure_venv_and_bootstrap_pip_raise_pip_install_error` |
| **FT-03** | 單元測試 | 驗證 `ContributesValidator` (`ValidationResult.format_report`) 與 `dev.checker` (`CheckReport.format_report` / `to_dict`) 於檢核失敗時尾端注入 `[Agent Directive]` 指引查閱 `yscb-module-dev` | FR-03 | `test_validator.py:test_validator_format_meta_check`、`test_checker.py:test_ft01_manifest_missing_core_dependency` |
| **FT-04** | 單元測試 | 驗證 `_notify_server_release_handles` 於模組生命週期變異前安全通知或容錯，以及 `_atomic_swap_dir` / `act_reload` 非阻塞清理 `.old_*` 殘留目錄 | FR-04, EC-03 | `test_installer.py:test_cmd_restore_cross_branch_version_mismatch_and_corrupted_manifest`、`test_engine.py:test_atomic_swap_dir_cleans_stale_old_and_staging_remnants` |
| **FT-05** | 文檔與靜態檢查 | 驗證 `core/vfs/vfs.py` 已移除過時 `MemoryBackend` 註解，且 `docs/core/README.md` 與 `docs/core/uri_protocols.md` 完整記載 `core.vfs` 本地實體代理與遠端快取物化邊界 | FR-05, NFR-01 | `python yscb.py dev check core`、`python yscb.py dev check dev` |
| **ET-01** | 邊界測試 | 驗證已安裝模組之 `.modules/<name>/manifest.json` 內容損毀無法解析 JSON 時，視為版本不符並觸發覆寫還原修復 | EC-01 | `test_installer.py:test_cmd_restore_cross_branch_version_mismatch_and_corrupted_manifest` |
| **RT-01** | 回歸測試 | 執行 `core` 與 `dev` 全量單元與整合回歸測試套件，確保 100% 通過且無衍生迴歸錯誤 | FR-01 ~ FR-05, NFR-01 | `python yscb.py dev test core -q`、`python yscb.py dev test dev -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Installer.cmd_restore` 與 `yscb.cmd_restore` 於 `1.0.0.0 != 1.1.0.0` 時成功覆寫更新至 `1.1.0.0`，同版本時輸出 `Skipping` | 2026-11-01 |
| **FT-02** | `Passed` | `_bootstrap_pip` 與 `ensure_venv` 異常均拋出 `PipInstallError`，`sync_pip_dependencies` 捕獲並輸出 `[core:pip] Warning:` | 2026-11-01 |
| **FT-03** | `Passed` | `ValidationResult.format_report` 與 `CheckReport` 於失敗時正確包含 `[Agent Directive]` 與 `yscb-module-dev` 路由指引 | 2026-11-01 |
| **FT-04** | `Passed` | `_notify_server_release_handles` 與 `.old_*` 延遲回收邏輯運作正常，無阻斷主安裝交易 | 2026-11-01 |
| **FT-05** | `Passed` | `dev check core` (`[PASS]`) 與 `dev check dev` (`[PASS]`) 100% 通過 | 2026-11-01 |
| **ET-01** | `Passed` | 損毀之 `manifest.json` (`{corrupted_json`) 自動觸發重新解壓覆寫修復為 `1.1.0.0` | 2026-11-01 |
| **RT-01** | `Passed` | `core` 測試套件 `Pass: 208(100.0%), Fail: 0, Skip: 0`；`dev` 測試套件 `Pass: 80(100.0%), Fail: 0, Skip: 0`；並完成 `core@build` 與 `dev@build` 熱部署 | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `python yscb.py dev check core`、`python yscb.py dev check dev` 與跨分支 `restore` / 報錯 `[Agent Directive]` 行為是否符合預期 | `[測試通過]` | 開發者實機試調用確認通過 (2026-11-01) |
