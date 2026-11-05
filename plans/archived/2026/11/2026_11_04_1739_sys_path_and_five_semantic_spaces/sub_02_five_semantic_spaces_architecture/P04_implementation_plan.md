# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 `P03_api_spec.md` 中皆有對應的介面簽名與資料契約。
- [x] **邊界防護**：EC-01 ~ EC-05（`1.2.7.x.py` 新舊設定深層合併、損毀 JSON 容錯、路徑穿越攔截、`act_snapshot` 跳過 `.storage.local/`、`cmd_restore` 觸發 `act_migrate`）皆已納入實作與測試範圍。
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 約束，100% 標準庫實作且業務代碼零歷史版本技術債殘留。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **系統架構** | [`docs/_project/STANDARDS.md`](../../../../docs/_project/STANDARDS.md) | Modify | 更新雙層組態與五大語意空間規範表（`config://`、`config.local://`、`storage://`、`storage.local://`、`cache://`） |
| **模組手冊** | [`docs/core/README.md`](../../../../docs/core/README.md)<br/>[`docs/core/lifecycle_and_hooks.md`](../../../../docs/core/lifecycle_and_hooks.md) | Modify | 更新核心內建語意 URI 協議表、`core.config` 雙層路徑說明與五大資料空間 `--purge` 生命週期治理 |
| **設計決策** | [`docs/core/DESIGN_NOTES.md`](../../../../docs/core/DESIGN_NOTES.md) | Modify | 新增設計決策紀錄：五大語意資料空間正交解耦、快照排除 `storage.local://` 與多段式 `act_migrate` 遷移階梯 |
| **微觀註解** | `core/{uri.py,config.py,engine.py}` Docstrings | Modify | 同步更新公開 API 與內部輔助函式之 Docstring |
| **發布日誌** | [`CHANGELOG.md`](../../../../CHANGELOG.md) | Modify | 於結案時補充五大語意空間架構變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：將 `config.local.json` 遷移至 `yscb://.config.local/<mod>/config.local.json` 後，為何不將舊版遷移邏輯塞在 `ConfigManager.get_config_path` 或常態 `hook.core.py:on_reload` 中，而選擇升級 `engine.py:act_migrate` 並註冊於 `scripts/migrations/1.2.7.x.py`？  
> [*] **防護解法**：若將舊版遷移放入 `core/config.py` 或 `on_reload`，每次讀取組態或每次 `reload` 都會永久背負舊版路徑檢查的歷史技術債。透過升級 `AtomicEngine.act_migrate` 支援第 3 段 `{major}.{minor}.{patch}.x.py`（如 `1.2.7.x.py`）並在 `cmd_install`、`cmd_update`、`cmd_restore` 跨版本升級時一次性觸發，可讓核心業務邏輯保持 100% 純淨無暇。

> [?] **尖銳問題 2**：在 `cmd_install`、`cmd_update` 與 `cmd_restore` 流程中，`act_reload` 會先於 `act_migrate` 執行；當 `core` 升級至 `1.2.7` 時，`act_reload` 會先在 `.config.local/core/config.local.json` 播種預設 `{"locale": ...}`，隨後 `act_migrate` 執行 `1.2.7.x.py` 時該如何避免預設值蓋掉使用者原本在 `config/core/config.local.json` 的自訂設定？  
> [*] **防護解法**：在 `scripts/migrations/1.2.7.x.py` 中，當發現目標 `.config.local/<mod>/config*.local.json` 已存在時，將新檔案視為底層預設值、舊版 `config/<mod>/config*.local.json` 視為覆蓋層（`_deep_merge(target_default_data, legacy_user_data)`），確保使用者在舊版設定的自訂值 100% 勝出，寫回後刪除舊檔並呼叫 `config.reload()`。

> [?] **尖銳問題 3**：如果把 `config.local://` 與 `storage.local://` 都排除在 `act_snapshot` 之外，萬一 `yscb update` 失敗觸發 `act_restore_snapshot` 回滾時，模組在安裝過程中修改的 `config.local.json` 要如何回滾？反之若把 `storage.local://` 也放進 `act_snapshot` 又會發生什麼事？  
> [*] **防護解法**：`config.local://` 僅存放輕量級 JSON 設定與幾 KB 的憑證，**納入 `act_snapshot` 與 `act_restore_snapshot`**，享受完整的安裝交易回滾保護；而 `storage.local://` 存放 91MB 語意模型與 54MB 索引庫，**明確排除於 `act_snapshot` 之外**，使快照維持毫秒級速度與極小體積。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`core.uri`、`contributes/core.json`、`gitignore.py`、`installer.py` 語意協議與 Git 忽略擴充)**：
   - 修改 [`core/uri.py`](../../../../ys_codebase/source/core/core/uri.py) 與 [`core/contributes/core.json`](../../../../ys_codebase/source/core/contributes/core.json) 註冊 `config.local://` 與 `storage.local://`。
   - 修改 [`core/gitignore.py`](../../../../ys_codebase/source/core/core/gitignore.py) 與 [`core/installer.py`](../../../../ys_codebase/source/core/core/installer.py) 納入 `/.config.local/` 與 `/.storage.local/`、擴充 `normalize_pattern`，並於 `Installer.cmd_restore` 補齊升級時之 `act_migrate` 調用。
2. **TASK-02 (`core.config` 雙軌物理純淨分離、`dispatcher` 對齊與 `1.2.7.x.py` 遷移腳本)**：
   - 修改 [`core/config.py`](../../../../ys_codebase/source/core/core/config.py) 更新 `get_config_path` 與 `list_modules`（100% 純淨定址）。
   - 修改 [`core/commands/dispatcher.py`](../../../../ys_codebase/source/core/core/commands/dispatcher.py) 更新 `_read_server_spawn_config` 讀取 `.config.local/server/config.local.json`。
   - 新建 `ys_codebase/source/core/scripts/migrations/1.2.7.x.py`（`core/manifest.json` 維持 `1.2.6.0`，將於 `sub_03` 與全倉其餘模組一併執行版號晉升）。
3. **TASK-03 (`core.engine` 模板部署、快照治理、`--purge` 與多段式 `act_migrate` 升級)**：
   - 修改 [`core/engine.py`](../../../../ys_codebase/source/core/core/engine.py) 更新 `_resolve_target_cfg_uris`、`_infill_single_template`、`_deploy_and_strip_single_module_config`、`act_snapshot`、`act_restore_snapshot`、`act_delete` 與多段式 `act_migrate`。
4. **TASK-04 (`vscode-support` 與 `dev` 沙盒工具鏈對齊)**：
   - 修改 [`vscode_support/schema_compiler.py`](../../../../ys_codebase/source/vscode-support/vscode_support/schema_compiler.py)、[`vscode_support/projector.py`](../../../../ys_codebase/source/vscode-support/vscode_support/projector.py) 與 [`dev/dev/testing/sandbox.py`](../../../../ys_codebase/source/dev/dev/testing/sandbox.py)。
5. **TASK-05 (單元測試補齊、`@build` 部署、工作區 `.gitignore` / VS Code 同步與文檔更新)**：
   - 更新並擴充 `core/tests/{test_uri.py,test_config.py,test_engine.py,test_gitignore.py,test_locale.py,test_core_commands.py}` 與 `vscode-support/tests/test_vscode_support.py`。
   - 建置並安裝 `core@build`、`dev@build`、`vscode-support@build`，執行 `gitignore sync` 與 `vscode-support sync`，驗證全套測試與三層文檔對齊（全模組版號晉升與 `1.2.7.x.py` 跨版實機觸發統一於 `sub_03` 執行）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 `config.local://` 納入 `act_snapshot` 交易保護，而 `storage.local://` 與 `cache://` 排除於 `act_snapshot` 之外；`act_delete(..., purge=True)` 則完整清除 `storage`、`storage.local`、`config`、`config.local` 四大空間。
- **[P04:DR-02]** 確認採用方案 B：升級 `AtomicEngine.act_migrate` 支援 2/3/4 段版號遷移階梯（及 `cmd_restore` 升級觸發），將舊版 `config://<mod>/config*.local.json` 自動遷移註冊於 `source/core/scripts/migrations/1.2.7.x.py`，保持核心業務邏輯零版本技術債；並已完整收斂 `/blind-subagent` 審查（[`ffea99ae-654c-4b52-a4a5-cc8306070a80`](conversation://ffea99ae-654c-4b52-a4a5-cc8306070a80)）檢出之 3 項條目。
