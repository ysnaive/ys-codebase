# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core 模組生命週期 CLI 多模組批次操作與原子事務升級  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0240_batch_lifecycle_and_blind_audit / sub_02_core_batch_lifecycle_cli  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `cmd_install` 支援多模組批次安裝、混合內嵌 `@<ver>` 與 `--version`、單次 `act_reload` 與 `sync_pip_dependencies` 呼叫及向後相容單模組 `str` 呼叫 | FR-01, EC-02, NFR-01, NFR-02 | `python yscb.py dev test --target=core:TestCoreInstaller.test_batch_install_atomic_transaction_and_conflict_rollback` |
| **FT-02** | 單元測試 | 驗證 `cmd_update` 與 `cmd_remove` 支援多模組批次操作、依序去重、逆向依賴聯集豁免（免 `--force` 一次移除上下游模組）與單次 `act_reload` | FR-02, FR-03, NFR-01, NFR-02 | `python yscb.py dev test --target=core:TestCoreInstaller.test_batch_update_and_remove_reverse_deps_exemption` |
| **FT-03** | 單元測試 | 驗證 `scripts/cli.py` 與 `contributes/core.json` 之 `install`、`update`、`remove` 支援單一與多模組位置參數解析並正確轉發至 `Installer` | FR-04 | `python yscb.py dev test --target=core:TestCoreCommandsSubsystem.test_cli_lifecycle_batch_forwarding` |
| **ET-01** | 邊界測試 | 驗證 `cmd_install` 批次中對同一模組指定衝突版本約束時拋出錯誤、中止交易並回滾至前置快照 | EC-01 | `python yscb.py dev test --target=core:TestCoreInstaller.test_batch_install_atomic_transaction_and_conflict_rollback` |
| **ET-02** | 邊界測試 | 驗證 `cmd_update` 包含未安裝模組、`cmd_remove` 包含 `core` 或未安裝模組、以及存在批次外逆向依賴且無 `--force` 時精準攔截返回 `1` | EC-03, EC-04, EC-05 | `python yscb.py dev test --target=core:TestCoreInstaller.test_batch_update_and_remove_reverse_deps_exemption` |
| **RT-01** | 回歸測試 | 驗證 `core` 模組全量靜態合規檢查 (`dev check core`) 與 217 項沙盒回歸測試 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check core && python yscb.py dev test core -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreInstaller.test_batch_install_atomic_transaction_and_conflict_rollback` 通過，確認批次安裝及 `act_reload` / `sync_pip_dependencies` 均僅執行 1 次 | 2026-11-02 |
| **FT-02** | `Passed` | `TestCoreInstaller.test_batch_update_and_remove_reverse_deps_exemption` 通過，確認多模組批次更新與逆向依賴聯集豁免移除成功 | 2026-11-02 |
| **FT-03** | `Passed` | `TestCoreCommandsSubsystem.test_cli_lifecycle_batch_forwarding` 通過，確認 CLI 多參數解析與轉發無誤 | 2026-11-02 |
| **ET-01** | `Passed` | 批次版本衝突（`batch_lib@1.0.0.0` vs `batch_lib@2.0.0.0`）成功觸發攔截並執行快照回滾 | 2026-11-02 |
| **ET-02** | `Passed` | 未安裝模組更新、移除 `core` 及批次外逆向依賴阻斷皆返回非零狀態碼 `1` 且零部分破壞 | 2026-11-02 |
| **RT-01** | `Passed` | `dev check core` `PASSED`；`dev test core -q` `Pass: 217(100.0%), Fail: 0, Skip: 0` | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機安裝 `core@build` 後，測試單次批次指令 `python yscb.py install dev@build agents-workflow@build --force` 可於單一原子交易內完成多模組安裝與單次環境重載 | `[測試通過]` | 實機執行 `install core@build agents-workflow@build --force` 與 `update core agents-workflow` 驗證單次重載與批次解析通過 |
