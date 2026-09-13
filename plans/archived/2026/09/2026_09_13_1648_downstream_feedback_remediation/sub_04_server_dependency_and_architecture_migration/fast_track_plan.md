# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_04_server_dependency_and_architecture_migration  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **Server 模組依賴與宣告完備 (Server Dependency Declaration)**：完善 `server` 模組的 `manifest.json` 描述與中繼資料，宣告精確核心相容範圍；檢核 `knowledge-db` 的 `optional.server` 依賴宣告。
  2. **熱重載架構遷移指引 (Hot Reload Architecture Migration Guide)**：撰寫文檔手冊說明舊版 `knowledge-db` 獨立背景服務已全面統一收斂至生態系常駐 `server` 模組 (`python yscb.py server start`)，舊版獨立 server 設定全數廢棄不進行相容，提供清晰的純粹最新版使用教學。
  3. **舊版 Server 影響與殘留徹底移除 (Complete Removal of Legacy Server Residue & Zero Backward Compatibility)**：依指示不進行向後相容，維持最新版本純粹性。從 `knowledge-db/configurable/config.project.json` 與 `config/knowledge-db/config.project.json` 完全移除 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec`；從 `KnowledgeDBConfig` 徹底移除 `enable_hot_reload_server`、`hot_reload_server_inactivity_timer_sec`、`enable_server_console` 欄位與常數，移除 `is_jit_effective` 舊屬性，簡化 `resolve_jit_vector_timeout`，杜絕任何過渡向後相容負贅。
  4. **Worker Watcher 狀態可觀測性強化 (Worker Watcher Observability)**：於 `server.master` 的 `/api/status` 擴充 `watcher` 狀態字典（包含 `enabled`, `active`, `monitored_dir`）；於 `server status` CLI 輸出 `Modules Watcher` 狀態，補齊熱重載監聽的端到端可觀測性。
- **影響範圍**：
  - `ys_codebase/source/server/manifest.json` (Modify)
  - `ys_codebase/source/knowledge-db/configurable/config.project.json` (Modify)
  - `ys_codebase/config/knowledge-db/config.project.json` (Modify)
  - `ys_codebase/source/knowledge-db/knowledge_db/config.py` (Modify)
  - `ys_codebase/source/knowledge-db/tests/test_space.py` (Modify)
  - `ys_codebase/source/server/server/master.py` (Modify)
  - `ys_codebase/source/server/scripts/cli.py` (Modify)
  - `docs/knowledge-db/user_guild.md` / `docs/server/` (Modify / New)
- **4 大剛性守門合規檢核**：
  - [x] 代碼修改行數預計 $\le 100$ 行（實作原始碼變更僅約 25 行，淨減 40 餘行）
  - [x] Public API 契約 0 變更（依指示移除 legacy 廢棄配置，維持最新架構契約純粹性）
  - [x] 零跨模組新依賴引入
  - [x] 既有單元測試與回歸測試 100% 覆蓋守門

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：完善 `server` 與 `knowledge-db` 之 `manifest.json` 宣告，並於文檔撰寫熱重載架構遷移手冊指引（說明舊版獨立背景服務全面由常駐 `server` 接管，舊版設定全數廢棄不相容）
- [x] **TASK-02**：完全移除 `knowledge-db` 舊版 server 影響（清理 config 模板、移除 `KnowledgeDBConfig` 舊欄位/常數/屬性，不向後相容保持純粹性，更新測試案例）
- [x] **TASK-03**：於 `server.master` 之 `/api/status` 及 `server.scripts.cli:status` 實作 Modules Watcher 狀態可觀測性輸出
- [x] **TASK-04**：編寫單元測試驗證 Watcher 可觀測性、最新純粹組態與模組宣告，並執行全量測試驗證
- **測試案例**：
  - `FT-01`：驗證 `server status` 與 `/api/status` 輸出完整包含 `Modules Watcher` 運行狀態
  - `FT-02`：驗證 `knowledge-db` 組態與 `KnowledgeDBConfig` 純粹性（已徹底移除過期 server 鍵與舊屬性，不提供舊鍵值解析）

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. **TASK-01 完備模組宣告與架構指引**：更新 `source/server/manifest.json` 為精準描述 `"YS-Codebase Persistent Server & Warm Worker Subsystem"`；撰寫 `docs/server/hot_reload_architecture_migration.md` 架構遷移指引，說明背景守護服務全面收斂至 `server` 模組，並於 `docs/server/README.md` 與 `docs/knowledge-db/README.md` 雙向鏈接。
  2. **TASK-02 徹底移除舊版 Server 殘留**：從 `source/knowledge-db/configurable/config.project.json` 及 `config/knowledge-db/config.project.json` 完全移除 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec`；從 `KnowledgeDBConfig` 徹底移除舊版常數、屬性與解析邏輯，不留向後相容過渡負贅；更新 `test_space.py` 驗證純粹性。
  3. **TASK-03 Modules Watcher 狀態可觀測性**：於 `server.watcher:ModulesWatcher` 提供 `is_running` 屬性；於 `server.master` 之 `/api/status` 擴充 `watcher` 字典；於 `server.scripts.cli:status` 輸出 `[*] Modules Watcher: ACTIVE (Monitoring .modules/)` 或狀態說明。
  4. **TASK-04 單元測試與全量回歸覆蓋**：於 `source/server/tests/test_server.py` 新增 `test_watcher_observability_status_payload` 與 `test_server_manifest_metadata`；於 `source/knowledge-db/tests/test_space.py` 新增 `test_ft_02_knowledgedb_config_purity`。
- **實機測試日誌**：
  - `python yscb.py dev test server`：34 Total, 34 Passed, 0 Failed (3.11s)。
  - `python yscb.py dev test knowledge-db`：149 Total, 149 Passed, 0 Failed (14.12s)。
  - `python yscb.py dev check --all`：5 Total, 5 Passed, 0 Failed (agents-workflow, core, dev, knowledge-db, server 全數通過)。
  - `python yscb.py server status`：實機即時呈現 `[*] Modules Watcher: ACTIVE (Monitoring .modules/)`。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed`
