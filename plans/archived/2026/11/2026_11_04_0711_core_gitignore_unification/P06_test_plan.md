# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`core.gitignore` 統一忽略規則收斂引擎與跨模組遷移 (`core_gitignore_unification`)  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證子目錄拓撲 (`yscb:// != project://`) 與同根拓撲 (`yscb:// == project://`) 下之語意 URI (`yscb://.venv/`, `project://.vscode/schemas/`) 路徑錨定轉換、否定規則 (`!`) 與越界路徑 (`../`) 安全過濾。 | FR-01, EC-01 | `python yscb.py dev test --target=core:TestCoreGitignore.test_ft_01_subdir_and_same_root_semantic_uri_resolution` |
| **FT-02** | 單元與整合測試 | 驗證 `core` (自貢獻)、`vscode-support` (`contributes/core.json`)、`project` (`config/core/contribute.json`) 靜態規則與 `agents-workflow` (`register_dynamic`) 動態規則按 `# [<module>]` 分組合成、排序 (`core` 置頂、字母序、`project` 置底)、Zero-Touch 冪等性 (`updated=False`) 與 `clear_dynamic` 卸載清理。 | FR-02, FR-04, FR-05, EC-03, EC-04 | `python yscb.py dev test --target=core:TestCoreGitignore.test_ft_02_grouped_managed_block_and_static_dynamic_merge` |
| **FT-03** | 單元與邊界測試 | 驗證舊版 `# === YSCB INTERNAL IGNORE BEGIN ===`、`# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 與未包裹遺留行無縫遷移、保留使用者手寫規則，以及安全刪除純舊版託管之 `ys_codebase/.gitignore` 與 `.vscode/schemas/.gitignore`（且當子目錄 `.gitignore` 含使用者自訂規則時僅剝除託管區塊而不刪檔）。 | FR-03, FR-05, EC-05, NFR-02 | `python yscb.py dev test --target=core:TestCoreGitignore.test_ft_03_legacy_migration_and_obsolete_nested_gitignore_cleanup` |
| **ET-01** | 邊界與負向測試 | 驗證 `register_dynamic` / `clear_dynamic` 對空白或 `None` 之 `module` 參數強制拋出 `ValueError`；驗證 `core.gitignore` 公開匯出與 CLI `gitignore <status\|sync> [--json]` 及未知子命令負向攔截。 | FR-04, FR-06, EC-02, NFR-01 | `python yscb.py dev test --target=core:TestCoreGitignore.test_et_01_sdk_mandatory_module_validation_and_cli_commands` |
| **RT-01** | 全量回歸測試 | 執行 `core`、`vscode-support` 與 `agents-workflow` 全量測試套件（含 `test_vscode_support.py:test_ft_04` 與 `test_targets.py:test_ft_06_sync_gitignore_soft_merge`），確認跨模組相容性與零回歸。 | FR-05, NFR-02 | `python yscb.py dev test core -q && python yscb.py dev test vscode-support -q && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreGitignore.test_ft_01_subdir_and_same_root_semantic_uri_resolution` 通過（子目錄 `/ys_codebase/.venv/` 與同根 `/.venv/` 錨定正確）。 | 2026-11-04 |
| **FT-02** | `Passed` | `TestCoreGitignore.test_ft_02_grouped_managed_block_and_static_dynamic_merge` 通過（`# [core]` / `# [agents-workflow]` / `# [vscode-support]` / `# [project]` 分組、Zero-Touch `mtime` 不變與 `clear_dynamic` 清理驗證通過）。 | 2026-11-04 |
| **FT-03** | `Passed` | `TestCoreGitignore.test_ft_03_legacy_migration_and_obsolete_nested_gitignore_cleanup` 通過（舊區塊清除、手寫規則保留、子目錄舊 `.gitignore` 清理與 `EC-05` 保護驗證通過）。 | 2026-11-04 |
| **ET-01** | `Passed` | `TestCoreGitignore.test_et_01_sdk_mandatory_module_validation_and_cli_commands` 通過（`ValueError` 負向攔截與 CLI `status`/`sync` `--json` 驗證通過）。 | 2026-11-04 |
| **RT-01** | `Passed` | `core` (`240/240` Passed)、`vscode-support` (`10/10` Passed)、`agents-workflow` (`141/141` Passed) 全量回歸 100% 通過；`dev check` 與 `contributes check` (26 files) 100% 通過。 | 2026-11-04 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視工作區根目錄 `.gitignore`（確認已收斂為單一 `# === YSCB MANAGED GITIGNORE BEGIN ===` 區塊並按 `# [core]`、`# [agents-workflow]`、`# [vscode-support]` 分組，且舊有 `ys_codebase/.gitignore` 與 `.vscode/schemas/.gitignore` 已自動清理），並於臨時兄弟目錄 `/workspace/tmp_sibling_test` (`.yscb` 子目錄拓撲) 驗證 `gitignore status` 與子目錄 `.gitignore` 自動清理。 | `[測試通過]` | 開發者於 2026-11-04 確認通過（含臨時兄弟目錄端到端測試驗證無誤） |

