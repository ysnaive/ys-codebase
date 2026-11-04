# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 註冊 `config.local://` 與 `storage.local://` 語意 URI 協議 | 1. 於 `core/uri.py:_BOOTSTRAP_FALLBACK_SCHEMES`（完整保留既有 `yscb.host: "{yscb_host}"` 與 `yscb.venv: "yscb://.venv/"`）及 `core/contributes/core.json` 之 `uri_schemes` 註冊兩項常數語意協議：<br/>   - `config.local`：`type: "const"`, `value: "yscb://.config.local/"`<br/>   - `storage.local`：`type: "const"`, `value: "yscb://.storage.local/"`<br/>2. `uri.resolve` 完整支援 `config.local://` 與 `storage.local://` 之根目錄解析、顯式模組路徑、`@/` 活躍模組上下文解析與路徑穿越防禦（`PermissionError`）。<br/>3. `uri.to_uri` 支援將 `<yscb_root>/.config.local/...` 與 `<yscb_root>/.storage.local/...` 反向轉譯為 `config.local://...` 與 `storage.local://...`。 | P0 | [P00:DR-01] |
| **FR-02** | 預設 `.gitignore` 規則與 `core.gitignore` 語意轉換擴充 | 1. 於 `core/contributes/core.json` 之 `gitignore` 清單新增 `"yscb://.config.local/"` 與 `"yscb://.storage.local/"`。<br/>2. 於 `core/gitignore.py:LEGACY_UNANCHORED_LINES` 與 `core/installer.py:INTERNAL_IGNORE_PATTERNS` 同步納入 `"/.config.local/"` 與 `"/.storage.local/"`。<br/>3. 於 `core/gitignore.py:normalize_pattern` 支援在自訂 `proj_root` / `yscb_root` 下直接將 `config.local://...`、`storage.local://...`、`config://...`、`storage://...`、`cache://...` 映射至 `eff_yscb` 對應子目錄。 | P0 | [P00:DR-01] |
| **FR-03** | `core.config` 雙軌物理純淨分離與 `act_migrate` 多段式遷移引擎升級 (`1.2.7.x.py`) | 1. `ConfigManager.get_config_path(module: str, local: bool = False) -> str`（100% 純淨定址，零舊版遷移分支）：<br/>   - `local=False` 解析為 `config://{module}/config.project.json`。<br/>   - `local=True` 解析為 `config.local://{module}/config.local.json`。<br/>2. `ConfigManager.list_modules() -> List[str]`：同時掃描 `config://<mod>/config.project.json` 與 `config.local://<mod>/config.local.json` 回傳具備設定檔的模組名稱排序聯集。<br/>3. `core/commands/dispatcher.py:_read_server_spawn_config(yscb_abs)`：純淨依序讀取 `config/server/config.project.json` 與 `.config.local/server/config.local.json`。<br/>4. **升級 `AtomicEngine.act_migrate(module_name, old_version, new_version)`**：<br/>   - 掃描 `module://{module_name}/scripts/migrations/*.py`，支援三種版本命名階梯：`{major}.{minor}.x.py`（第 2 段晉升觸發）、`{major}.{minor}.{patch}.x.py`（第 3 段晉升觸發）與 `{major}.{minor}.{patch}.{rev}.py`（第 4 段晉升觸發）；在同一 `major` 下篩選介於 `(old_version, new_version]` 區間內之遷移腳本並依版本號升序執行 `migrate(context)`。<br/>   - `Installer.cmd_restore` 在覆寫已安裝模組前，若偵測到目標版本高於既有已安裝版本（`semver.compare_semver(ver, installed_ver) > 0`），於 `act_reload` 後同步觸發 `act_migrate(mod_name, installed_ver, ver)`。<br/>5. **`core` `1.2.7.x.py` 遷移腳本** (`ys_codebase/source/core/scripts/migrations/1.2.7.x.py` & `core/manifest.json` 推進至 `1.2.7.0`)：實作 `migrate(context)`，自動掃描 `<config_dir>/<mod>/config*.local.json` 並無損遷移（若目標已存在預設種子則以舊版使用者自訂值覆蓋合併）至 `<config_local_dir>/<mod>/config*.local.json` 後刪除舊檔，並呼叫 `core.config.reload()`。 | P0 | [P00:DR-02] |
| **FR-04** | `AtomicEngine` 組態模板部署、快照排除與 `--purge` 生命週期治理 | 1. **組態模板部署** (`core/engine.py`)：<br/>   - `_resolve_target_cfg_uris(mod, tmpl_file)`：當 `tmpl_file == "config.local.json"` 或 `config.<sub_name>.local.json` 時，目標 URI 指向 `config.local://{mod}/{tmpl_file}`。<br/>   - `_infill_single_template` 與 `_deploy_and_strip_single_module_config`：針對 `is_local=True` 確保建立 `config.local://{mod}` 目錄；`core` 初始 `locale` 種子寫入 `config.local://core/config.local.json`。<br/>2. **快照與還原** (`act_snapshot` / `act_restore_snapshot`)：<br/>   - `act_snapshot` 備份 `yscb.config.json`、`config://`、`config.local://`（若存在）、`storage://` 與 `module://`；**明確排除 `storage.local://` 與 `cache://`**。<br/>   - `act_restore_snapshot` 同步還原 `config.local://`（若快照內含 `config.local` 則還原，否則清理目標 `config.local://` 並重建空目錄）。<br/>3. **模組刪除與遷移上下文** (`act_delete` / `act_migrate`)：<br/>   - `act_delete(module_name, clean_mirror=False, purge=False)`：當 `purge=True` 時，一併清理 `("storage", "storage.local", "config", "config.local")` 下該模組之子目錄。<br/>   - `act_migrate`：於 `context` 字典提供 `"host_dir"`、`"yscb_dir"`、`"config_dir"`、`"config_local_dir"`、`"storage_dir"`、`"storage_local_dir"`、`"old_version"` 與 `"target_version"`。 | P0 | [P00:DR-02]<br/>[P00:DR-03] |
| **FR-05** | `vscode-support` 與 `dev` 沙盒工具鏈對齊 | 1. `vscode-support/vscode_support/schema_compiler.py`：<br/>   - `_collect_uri_scheme_snippets` 預設字典加入 `"config.local"` 與 `"storage.local"`。<br/>   - `sync_all_schemas` 為每個模組的 `config/{mod}.schema.json` 綁定 `fileMatch: [f"**/config/{mod}/config.*.json", f"**/.config.local/{mod}/config.*.json"]`。<br/>2. `vscode-support/vscode_support/projector.py`：<br/>   - `ANALYSIS_EXCLUDE_PATTERNS` 新增 `"**/.config.local/**"` 與 `"**/.storage.local/**"`。<br/>3. `dev/dev/testing/sandbox.py`：<br/>   - `SandboxContext.set_module_config(module_name, config_filename, data)`：當 `config_filename == "config.local.json"` 或以 `.local.json` 結尾時，寫入 `os.path.join(self.engine_dir, ".config.local", module_name, config_filename)`，其餘寫入 `os.path.join(self.engine_dir, "config", module_name, config_filename)`。 | P0 | [P00:DR-01]<br/>[P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `core` 升級至 `1.2.7.*` 時，`act_reload` 先於 `act_migrate` 為 `core` 播種了預設 `.config.local/core/config.local.json`，而舊版 `config/core/config.local.json` 亦有使用者自訂設定 | `scripts/migrations/1.2.7.x.py` 讀取雙邊 JSON，以舊版使用者自訂 `legacy_data` 覆蓋剛生成的預設 `new_data`（`_deep_merge(new_data, legacy_data)`）後原子寫入 `.config.local/<mod>/config.local.json` 並刪除舊檔，確保使用者原有的本地設定 100% 保留。 |
| **EC-02** | 舊版 `config/<mod>/config.local.json` 內容損毀（非合法 JSON） | `scripts/migrations/1.2.7.x.py` 若發現新路徑尚不存在，原樣搬移該檔案至 `.config.local/<mod>/config.local.json`；若新路徑已存在有效 JSON，則保留新路徑檔案並移除損毀之舊檔，不拋出未捕獲異常中斷升級。 |
| **EC-03** | 透過 `config.local://@/../../../etc/passwd` 或兄弟前綴 `storage.local://../storage.local_evil/x` 進行路徑穿越 | `uri.resolve` 透過 `os.path.commonpath([base_real, final_real]) != base_real` 剛性攔截並拋出 `PermissionError`。 |
| **EC-04** | `.storage.local/` 內存有百 MB 級模型或索引時執行 `act_snapshot` | `act_snapshot` 僅備份 `config://`、`config.local://`、`storage://` 與 `module://`，完全跳過 `storage.local://`，快照耗時與體積不受 `.storage.local/` 影響。 |
| **EC-05** | 協作者拉取更新後執行 `python yscb.py restore` 將既有 `core@1.2.6.0` 升級至 `core@1.2.7.0` | `Installer.cmd_restore` 在還原前紀錄原已安裝版本 `installed_ver`，並於 `act_reload` 後對 `compare_semver(ver, installed_ver) > 0` 的模組執行 `act_migrate`，確保 `restore` 與 `install`/`update` 一致觸發 `1.2.7.x.py`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 | `core/uri.py`、`core/config.py`、`core/engine.py`、`core/gitignore.py` 與 `scripts/migrations/1.2.7.x.py` 100% 僅使用 Python 標準庫。 |
| **NFR-02** | 快照輕量化 | `act_snapshot` 產出之快照目錄中，`storage.local` 與 `cache` 拷貝檔案數必須為 `0`。 |
| **NFR-03** | 業務邏輯零歷史遷移污染 | `core/config.py`、`core/engine.py` 與 `core/commands/dispatcher.py` 熱路徑中對舊版 `config/<mod>/config.local.json` 的相容探測次數必須為 `0`（全數解耦至 `scripts/migrations/1.2.7.x.py`）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` `_BOOTSTRAP_FALLBACK_SCHEMES` 結構完整性**：修改 `core/uri.py` 時，必須保留 `yscb.host` (`"{yscb_host}"`) 與 `yscb.venv` (`"yscb://.venv/"`) 既有條目，僅插入 `config.local` 與 `storage.local`。
- **`[!IMPORTANT]` 既有測試路徑同步與沙盒清理 (`tearDown`)**：除更新 `test_config.py` 與 `test_engine.py` 外，須同步對齊 `test_locale.py:L374-398`（`config.local://core/config.local.json`）與 `test_core_commands.py:L786-796`（`.config.local/server/config.local.json`）。
