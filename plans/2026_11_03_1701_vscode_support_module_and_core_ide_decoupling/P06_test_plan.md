# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_03_1701_vscode_support_module_and_core_ide_decoupling  
> 建立日期：2026-11-03  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core` 零 IDE 假設：刪除 `ide_projector.py`，`Installer.sync_pip_dependencies()` 不再直接讀寫 `.vscode/settings.json`，改為廣播 `on_env_synced` 事件 | `FR-01` | `python yscb.py dev test core -q` (`test_venv_core.py:test_ft_08`) |
| **FT-02** | 單元測試 | 驗證 `ContributesValidator._parse_default_literal` 支援帶正負號整數 (`-1`) 與浮點數 (`1.0`, `-0.5`)，且多點字串 (`1.0.0`) 保持字串型別 | `FR-02` | `python yscb.py dev test core -q` (`test_validator.py:test_et_03`) |
| **FT-03** | 單元測試 | 驗證 `SettingsProjector.sync_vscode_settings` 於 `project://.vscode/` 不存在時自動建立目錄，並建立 `yscb.venv://current-site-packages` 穩定連結與切換版本時 `settings.json` 零變動 | `FR-03`, `FR-04` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_ft_01`) |
| **FT-04** | 單元測試 | 驗證 `SchemaCompiler.compile_contributes_schema` 支援 `_types` 自遞迴 (`$CommandNode`)、固定鍵與 `*` 萬用鍵混合字典、浮點/負整數預設值及外層模組鍵名包裹相容 | `FR-05`, `EC-04` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_ft_03`) |
| **FT-05** | 單元測試 | 驗證 `SchemaCompiler` 自 `module.mirror://<mod>/<ver>.zip` 記憶體提取 `configurable/*.json` 推導組態 Schema (`!undefined` -> `not: {const: "!undefined"}`)、產出 `.vscode/schemas/.gitignore` (`*`) 與清理孤兒 Schema | `FR-05`, `EC-05`, `EC-06` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_ft_04`) |
| **FT-06** | 單元測試 | 驗證 `SettingsProjector` Zero-Touch 軟合併（保留使用者自訂 `extraPaths`、`defaultInterpreterPath` 與 `json.schemas`）、完全可逆 `revert` 與 `scripts/cli.py` (`status` / `sync` / `revert` `--json`) | `FR-04`, `FR-06`, `EC-03` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_ft_05`, `test_ft_06`) |
| **ET-01** | 邊界測試 | 驗證 `.vscode/settings.json` 含 JSONC 註解或損毀時安全跳過不覆寫，以及 `hook.core.py:on_remove` 僅於移除目標含 `vscode-support` 時觸發還原 | `EC-01`, `FR-06` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_et_01`) |
| **ET-02** | 邊界測試 | 驗證當作業系統/檔案系統不支援建立目錄 Symlink/Junction 時自動降級為注入跨平台雙路徑列表 | `EC-02`, `FR-04` | `python yscb.py dev test vscode-support -q` (`test_vscode_support.py:test_ft_02`) |
| **NFR-01** | 靜態合規 | 驗證 `core` 與 `vscode-support` 模組 100% 通過 `dev check`（0 第三方依賴、0 `module.source://` 探測、0 `config.project.json` 硬編碼反模式） | `NFR-01`, `NFR-02` | `python yscb.py dev check core vscode-support` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev test core -q`：`Pass: 235(100.0%), Fail: 0, Skip: 0`（`test_ft_08` 驗證 `on_env_synced` 廣播通過） | 2026-11-03 |
| **FT-02** | `Passed` | `dev test core -q`：`test_et_03_parse_default_literal_signed_int_and_float` 斷言通過 | 2026-11-03 |
| **FT-03** | `Passed` | `dev test vscode-support -q`：`test_ft_01_auto_create_vscode_dir_and_stable_site_packages_link` 通過 | 2026-11-03 |
| **FT-04** | `Passed` | `dev test vscode-support -q`：`test_ft_03_schema_compiler_contributes_and_recursive_types` 通過 | 2026-11-03 |
| **FT-05** | `Passed` | `dev test vscode-support -q`：`test_ft_04_schema_compiler_config_from_mirror_zip_and_orphan_cleanup` 通過 | 2026-11-03 |
| **FT-06** | `Passed` | `dev test vscode-support -q`：`test_ft_05` 與 `test_ft_06` 通過；實機 `yscb vscode-support sync` 成功同步 14 份 JSON Schema | 2026-11-03 |
| **ET-01** | `Passed` | `dev test vscode-support -q`：`test_et_01_jsonc_settings_preserved_and_hook_lifecycle` 通過 | 2026-11-03 |
| **ET-02** | `Passed` | `dev test vscode-support -q`：`test_ft_02_fallback_when_symlink_unsupported` 通過 | 2026-11-03 |
| **NFR-01** | `Passed` | `dev check core vscode-support`：`core [PASS]`, `vscode-support [PASS]` (0 FAIL, 0 WARN) | 2026-11-03 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於 VS Code 開啟專案並檢視 `.vscode/settings.json`、`.vscode/schemas/`（含 14 份單檔 Schema 與 `.gitignore`），並於 `contribute.json` 與 `config.project.json` 驗證 `uri` 協議前綴補全（`defaultSnippets`）與 `@desc(...)` 欄位說明提示正常運作 | `[測試通過]` | 開發者實機驗收確認通過（含方案 C `current-site-packages` 恆定路徑、`uri/path` 協議前綴補全、`@desc(...)` 欄位說明與 `configurable/_format.json` 同構正規化） |

