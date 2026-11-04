# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Passed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 (`core.uri`) | 驗證 `config.local://` 與 `storage.local://` 根目錄解析、顯式模組定址、`@/` 活躍模組上下文自省、`uri.to_uri` 最長前綴反向轉換與 `PermissionError` 路徑穿越防禦 | FR-01, EC-03, NFR-01 | `python yscb.py dev test core` (`test_uri.py`) |
| **FT-02** | 單元測試 (`core.gitignore`) | 驗證 `core` 預設 `.gitignore` 規則包含 `/ys_codebase/.config.local/` 與 `/ys_codebase/.storage.local/`，且 `normalize_pattern` 正確轉換 `config.local://` 與 `storage.local://` | FR-02 | `python yscb.py dev test core` (`test_gitignore.py`) |
| **FT-03** | 單元測試 (`core.config` & `1.2.7.x.py` Migration) | 驗證 `get_config_path(..., local=True)` 純淨指向 `.config.local/<mod>/config.local.json`，以及 `act_migrate("core", "1.2.6.0", "1.2.7.0")` 執行 `scripts/migrations/1.2.7.x.py` 將舊版 `config://<mod>/config.local.json` 自動無縫搬移、雙邊並存深層合併與損毀 JSON 容錯 | FR-03, EC-01, EC-02, EC-05, NFR-03 | `python yscb.py dev test core` (`test_config.py` & `test_engine.py`) |
| **FT-04** | 單元測試 (`core.engine`) | 驗證 `act_deploy_configs_from_modules` 將 `config.local.json` 部署至 `config.local://<mod>/`；驗證 `act_snapshot` / `act_restore_snapshot` 包含 `config.local://` 且明確排除 `storage.local://`；驗證 `act_delete(..., purge=True)` 完整清除四大持久空間 | FR-04, EC-04, NFR-02 | `python yscb.py dev test core` (`test_engine.py`) |
| **FT-05** | 單元測試 (`vscode-support`) | 驗證 `SchemaCompiler` 產出含 `config.local://` / `storage.local://` 之 `defaultSnippets`，且 `sync_all_schemas` 綁定 `**/.config.local/<mod>/config.*.json`；`SettingsProjector` 排除 `**/.config.local/**` 與 `**/.storage.local/**` | FR-05 | `python yscb.py dev test vscode-support` (`test_vscode_support.py`) |
| **FT-06** | 整合與靜態合規驗證 | 安裝 `core@build`、`dev@build`、`vscode-support@build` 後執行 `python yscb.py dev check --all` 與模組回歸測試 | FR-01~FR-05 | `python yscb.py dev check --all` & `python yscb.py dev test` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreURI` 全數通過：`config.local://` -> `/.config.local`、`storage.local://` -> `/.storage.local`、`@/` 自省與越界防禦驗證無誤 | 2026-11-04 |
| **FT-02** | `Passed` | `TestCoreGitignore` 全數通過：`normalize_pattern` 正確轉換 `config.local://` 與 `storage.local://` 為 `/ys_codebase/.config.local/` 與 `/ys_codebase/.storage.local/` | 2026-11-04 |
| **FT-03** | `Passed` | `TestConfigManager` 全數通過（含新增 `test_migration_script_1_2_7_x_sweeps_and_deep_merges_legacy_local_configs`），且 `core@build` 安裝時自動觸發 `Running migration ladder for 'core' (1.2.6.build -> 1.2.7.build)...` 將工作區 `ys_codebase/config/core/config.local.json` 無損遷移至 `ys_codebase/.config.local/core/config.local.json` | 2026-11-04 |
| **FT-04** | `Passed` | `TestCoreEngine` 全數通過（含新增 `test_act_delete_purge_and_multi_segment_act_migrate` 與更新 `test_dual_layer_snapshot_and_execution_context_immutability`） | 2026-11-04 |
| **FT-05** | `Passed` | `TestVSCodeSupport` 11/11 (100%) 通過 | 2026-11-04 |
| **FT-06** | `Passed` | `core` (244/244 Passed)、`vscode-support` (11/11 Passed)、`dev` (87/87 Passed)，`dev check --all` 9/9 Passed (0 Warnings, 0 Failed)，`uri check` 25/25 HEALTHY | 2026-11-04 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `yscb uri check` 語意協議清冊、根目錄 `.gitignore` 與 `.vscode/settings.json`，確認 `config.local://` 與 `storage.local://` 已註冊生效且舊版 `ys_codebase/config/core/config.local.json` 已透過 `1.2.7.x.py` 遷入 `ys_codebase/.config.local/core/config.local.json` | `[跳過/免測]` | CLI 實機驗證 `uri check`、`config list --local` 與 `.vscode/settings.json` 同步皆已確認通過 |
