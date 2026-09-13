# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_03_config_hierarchy_and_hook_observability  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **組態階層遮蔽修復 (Config Hierarchy Shadowing Remediation)**：修復 `knowledge-db` 在 `configurable/` 中誤置預設 `config.local.json`，導致部署至工作區時被複製到本機層級，進而覆蓋並遮蔽 `config.project.json` 團隊設定之缺陷；將預設運作設定遷移至 `config.project.json`，移除 `config.local.json` 模板；於 `core.engine` 強化防禦，防止部署時將模組預設值誤落檔於本機 `config.local.json`。
  2. **Hook 生命週期可觀測性強化 (Hook Observability)**：修復 `core.events:broadcast` 與 `dispatcher:_ensure_hooks` 在分派 `pre_cli_dispatch`/`post_cli_dispatch` 時靜默丟棄回傳值與吞掉例外的缺陷；在 `--verbose` / `--debug` 模式或 `YSCB_VERBOSE=1` 環境變數下提供可觀測之 Hook 執行日誌與異常追蹤。
- **影響範圍**：
  - `ys_codebase/source/knowledge-db/configurable/config.local.json` (Delete)
  - `ys_codebase/source/knowledge-db/configurable/config.project.json` (Modify)
  - `ys_codebase/source/core/core/engine.py` (Modify)
  - `ys_codebase/source/core/core/events.py` (Modify)
  - `ys_codebase/source/core/core/commands/dispatcher.py` (Modify)
- **4 大剛性守門合規檢核**：
  - [x] 代碼修改行數預計 $\le 100$ 行（預估約 45 行）
  - [x] Public API 契約 0 變更（`broadcast` 與 `ConfigManager` 完全相容）
  - [x] 零跨模組新依賴引入
  - [x] 既有單元測試與回歸測試 100% 覆蓋守門

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：遷移 `knowledge-db` 預設組態至 `config.project.json` 並移除 `config.local.json` 模板；於 `core.engine` 強化防禦，避免自動建立帶預設值之 `config.local.json`
- [x] **TASK-02**：於 `core.events:broadcast` 與 `dispatcher:_ensure_hooks` 實作 `--verbose`/`--debug` 模式下之 Hook 執行狀態與異常回傳可觀測性
- [x] **TASK-03**：編寫單元測試驗證組態優先級與 Hook 可觀測性輸出
- **測試案例**：
  - `FT-01`：驗證 `config.local.json` 不再預設生成遮蔽 `config.project.json`，且 `config.project.json` 團隊設定正常生效
  - `FT-02`：驗證 `--verbose` 或 `YSCB_VERBOSE=1` 時 `pre_cli_dispatch` 等 Hook 執行結果正確輸出，異常時提供完整診斷

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - **TASK-01 (組態階層遮蔽修復)**：
    - 徹底移除 `source/knowledge-db/configurable/config.local.json` 模板，避免部署至工作區時被複製到本機層級遮蔽團隊設定。
    - 將預設運作設定 (`jit_vector_timeout_seconds`, `max_threads`, `enable_hot_reload_server`, `hot_reload_server_inactivity_timer_sec`) 整合移入 `configurable/config.project.json`。
    - 強化 `core.engine` 之 `_seed_or_update_config` 與 `act_deploy_configs_from_modules` 防禦機制，當 local infill 資料為空字典時絕不自動產生本機 `config.local.json`。
    - 修正工作區既有 `config/knowledge-db`，消除空/預設遮蔽檔，回歸單一真理來源 `[PROJECT]`。
  - **TASK-02 (Hook 生命週期可觀測性強化)**：
    - 於 `core.events:broadcast()` 新增 `verbose: Optional[bool] = None` 參數，支援自適應環境變數 (`YSCB_VERBOSE=1`, `YSCB_DEBUG=1`) 與命令列標籤 (`--verbose`, `--debug`)。
    - 於 verbose 模式下輸出標準格式執行狀態日誌 `[{emit_module}:events] Hook '{mod_name}:hook.{emit_module}.py' executed '{event_name}' -> {result}`，且於 Hook 拋出異常時輸出完整 `traceback` 至 `sys.stderr`。
    - 於 `core.commands.dispatcher:_ensure_hooks()` 支援回傳結果字典 `Dict[str, Any]`，並於 `--verbose`/`--debug` 時輸出分派完成摘要 `[core:dispatcher] Hooks for '{hook_name}' completed: {res}`。
  - **TASK-03 (測試驗證)**：
    - 新增 `source/core/tests/test_config_and_hook_observability.py`，完整涵蓋 FT-01 與 FT-02。
    - 更新 `source/knowledge-db/tests/test_space.py` 中 `test_configurable_config_templates_exist` 測試案例，對齊新組態階層契約。
- **實機測試日誌**：
  - **目標單元測試**：
    `python yscb.py dev test --target=core:TestConfigAndHookObservability` $\rightarrow$ 2 Passed, 0 Failed (100% Ready)
  - **模組全量回歸測試**：
    `python yscb.py dev test core` $\rightarrow$ 191 Total, 191 Passed, 0 Failed (132.365s)
    `python yscb.py dev test knowledge-db` $\rightarrow$ 148 Total, 148 Passed, 0 Failed (13.956s)
  - **全系統規範檢核**：
    `python yscb.py dev check --all` $\rightarrow$ 5 Total, 5 Passed, 0 Warnings, 0 Failed
  - **實機 Dogfooding 驗證**：
    - `python yscb.py install core@build` $\rightarrow$ 安裝成功
    - `python yscb.py install knowledge-db@build` $\rightarrow$ 安裝成功
    - `python yscb.py config list` $\rightarrow$ `knowledge-db` 正常顯示為 `[PROJECT]`，無多餘之 `[LOCAL OVERLAY]` 遮蔽
    - `python yscb.py dev check --all --verbose` $\rightarrow$ 正常輸出 `[core:events]` 與 `[core:dispatcher]` 之 Hook 可觀測日誌；無 `--verbose` 模式保持安靜純淨

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed` (FT-3 結案完成)

