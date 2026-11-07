# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Sub-04 生態系消費端全面遷移與 `module:file-space` 過渡轉發殼收斂  
> 建立日期：2026-11-07  
> 所屬主計畫：`2026_11_06_1020_core_file_space_architecture/sub_04_ecosystem_migration_and_legacy_removal`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元 / 整合測試 | 驗證 `core` 1.2.7.x 遷移腳本將舊版 `config/file-space/contribute.json` 雙欄位無損轉譯為 `config/core/contribute.json`，並清理殘留舊檔；驗證單一空間短名查詢正規化為 `<owner>/<name>` 與顯式 `storage_root` 鎖檔目錄隔離 | FR-01, EC-01, EC-02 | `python yscb.py dev test core -q` |
| **FT-02** | 單元 / 整合測試 | 驗證 `agents-workflow` 在零 `file-space` 依賴下完成 `PROJECT_ROLE_AND_BOUNDARIES` 渲染、Stage 1/2 編譯與多 Target 發布 | FR-02, NFR-01 | `python yscb.py dev test agents-workflow -q` |
| **FT-03** | 單元 / 整合測試 | 驗證 `module:ast` 100% `Mode A` 零 `file_space` 耦合、`scripts/hook.core.py` 事件訂閱、`contributes/core.json` 空間與預設集宣告，以及 `1.0.1.x.py` 升級游標重置 | FR-03, EC-03, NFR-01, NFR-02 | `python yscb.py dev test ast -q` |
| **FT-04** | 單元 / 整合測試 | 驗證 `module:knowledge-db` 100% `Mode A` 零 `file_space` 耦合、`scripts/hook.core.py` 事件熱補丁與微批次佇列、`contributes/core.json` 空間宣告，以及 `1.2.1.x.py` 升級游標重置 | FR-04, EC-04, NFR-01, NFR-02 | `python yscb.py dev test knowledge-db -q` |
| **FT-05** | 單元 / 整合測試 | 驗證 `module:gdrive-support` 100% `Mode A` 零 `file_space` 耦合、`contributes/core.json` `cloud` 空間宣告與 `repo_sync` 暫態空間過濾同步 | FR-05, NFR-01 | `python yscb.py dev test gdrive-support -q` |
| **FT-06** | 單元 / 整合測試 | 驗證 `module:file-space` 過渡棄用純轉發殼 (`dependencies: {"core": ">=1.2.7.4"}`) 零 `watchdog` 依賴、零 `server` 背景服務宣告，且所有公開 API 與 CLI 指令委派至 `core.space` | FR-04, EC-05, NFR-03 | `python yscb.py dev test file-space -q` |
| **FT-07** | 靜態合規檢查 | 驗證全倉 9 大模組 (`core`, `dev`, `server`, `ast`, `knowledge-db`, `agents-workflow`, `vscode-support`, `gdrive-support`, `file-space`) 通過 `dev check --all` 零錯誤、零警告 | FR-01, FR-02, FR-03, FR-04, NFR-01, NFR-02, NFR-03 | `python yscb.py dev check --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Pass: 267(99.6%), Fail: 0, Skip: 1`；驗證 `_migrate_legacy_file_space_config`、`_canonical_space_key` 與 `_resolve_default_lock_dir` 全數通過 | 2026-11-07 |
| **FT-02** | `Passed` | `Pass: 145(100.0%), Fail: 0, Skip: 0`；驗證 `agents-workflow` 零 `file-space` 耦合與多 Target 發布測試全綠 | 2026-11-07 |
| **FT-03** | `Passed` | `Pass: 37(100.0%), Fail: 0, Skip: 0`；驗證 `ast` `Mode A` 遷移、`hook.core.py` 與 `1.0.1.x` 遷移腳本全數通過 | 2026-11-07 |
| **FT-04** | `Passed` | `Pass: 109(100.0%), Fail: 0, Skip: 0`；驗證 `knowledge-db` `Mode A` 遷移、`hook.core.py`、跨空間同名檔案隔離與 `1.2.1.x` 遷移腳本全數通過 | 2026-11-07 |
| **FT-05** | `Passed` | `Pass: 34(100.0%), Fail: 0, Skip: 0`；驗證 `gdrive-support` `Mode A` 遷移與 `repo_sync` 暫態空間過濾全數通過 | 2026-11-07 |
| **FT-06** | `Passed` | `Pass: 18(100.0%), Fail: 0, Skip: 0`；驗證 `file-space` 過渡轉發殼委派至 `core.space` 全數通過 | 2026-11-07 |
| **FT-07** | `Passed` | `Summary : 9 Total, 9 Passed, 0 Warnings, 0 Failed (Status: PASSED)` | 2026-11-07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於母倉本機環境與臨時隔離工作區（已移除 `.modules/file-space/`）執行 `python yscb.py fs status`、`python yscb.py ast status`、`python yscb.py knowledge-db status` 與升級自動遷移驗證，確認各模組完全透過 `core.space` 正常運作且無任何 `file-space` 殘留依賴 | `[測試通過]` | 開發者於臨時隔離環境實機驗收確認 7 階段全鏈路 100% 通過 |
