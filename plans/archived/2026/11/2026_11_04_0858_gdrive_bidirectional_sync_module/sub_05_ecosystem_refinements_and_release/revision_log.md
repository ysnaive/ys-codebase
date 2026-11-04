# 修訂紀錄書 (Revision Log)

> 功能名稱：`sub_05_ecosystem_refinements_and_release`  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] `module:server` 預設閒置 Timeout 調升至 30 分鐘 (`1800.0s`) 與 `touch_activity` 保活探針 SDK 整合
- **修訂類別**：Parameter
- **涉及檔案**：
  - `ys_codebase/source/server/server/config.py`
  - `ys_codebase/source/server/configurable/config.project.json`
  - `ys_codebase/source/server/configurable/_format.json`
  - `ys_codebase/config/server/config.project.json`
  - `ys_codebase/source/server/server/master.py`
  - `ys_codebase/source/server/server/service.py`
  - `ys_codebase/source/server/server/__init__.py`
  - `ys_codebase/source/file-space/file_space/service.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/service.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/service.py`
  - `ys_codebase/source/server/tests/test_server_config.py`
- **修訂摘要**：將常駐 `server` 預設 `idle_timeout_sec` 由 `900.0`（15 分鐘）調升為 `1800.0`（30 分鐘）；於 `server` 公開匯出 `touch_activity(yscb_root=None, *, source="sdk", force=False) -> bool` 探針 SDK 與 `BaseServiceWorker.touch_activity()` 方法（搭配 `MasterSupervisor` 之 `POST /api/touch` 與 1.0 秒節流防抖），並將 `file-space-watcher`、`knowledge-db-worker` 與 `gdrive-sync` 三大背景 Worker 全面接入探針，確保背景僅靠 Worker 執行任務時自動刷新 Server Idle Timeout。
- **驗證結果**：通過 `dev check` 與 `server`、`file-space`、`knowledge-db`、`gdrive-support` 單元測試驗證。

### [REV-02] 重構 `module:gdrive-support` 外部隨包技能目錄 (`assets/external_skill/`)，納入前置 7 維度專案自舉回填配置與網頁版 Gemini 專屬環境自檢引導手冊
- **修訂類別**：Docs
- **涉及檔案**：
  - `ys_codebase/source/gdrive-support/assets/external_skill/gdrive-external-ops/SKILL.md`
  - `ys_codebase/source/gdrive-support/assets/external_skill/gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md`
  - `ys_codebase/source/gdrive-support/README.md`
  - `docs/gdrive-support/README.md`
- **修訂摘要**：移除舊 `assets/external_cloud_skill/` 並建立 `assets/external_skill/` 雙層結構：
  1. `gdrive-external-ops/SKILL.md`：通用外部 AI Agent 技能範本，最前置納入「首次使用 4 步自舉指令」與「§0 專案實例化配置區塊（涵蓋雲端 `root_folder_id`、`repo_sync_root`/分支、專案簡介與必讀導航、`sync_spaces` 映射表、雙端溝通媒介 `_inbox/` 協議、角色與寫入權限邊界、環境能力自檢結果）」及三大安全鐵律。
  2. `gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md`：專供使用者複製貼給網頁版 Gemini 之隨包引導手冊，於階段 0 強制執行「網頁版 Gemini 任務模式 + 可並行任務 + Linux 虛擬運行機 + Google Drive 直連」剛性環境自檢（不合法則立即阻斷任務並提示切換環境），通過後引導 Gemini 自動探查雲端目錄、與使用者核對 7 大配置並回填內嵌之最終定製版 `SKILL.md` 模板。
- **驗證結果**：通過 `dev check gdrive-support` 與 `plan verify` 驗證。

### [REV-03] 實機驗證 `GDriveSyncServiceWorker` (`[gdrive-sync]`) 真實雲端背景自動同步與 `touch_activity` 保活聯動
- **修訂類別**：Config
- **涉及檔案**：
  - `ys_codebase/config/gdrive-support/config.project.json`
  - `ys_codebase/source/gdrive-support/gdrive_support/service.py`
- **修訂摘要**：將 `server@build` 與 `gdrive-support@build` 熱部署至本機環境後，開啟 `repo_sync.enable: true`、`auto_sync: true` 並綁定 `docs` 空間進行真實雲端 Google Drive (`1MeDEInAzn11JobNbfA_6uQ2OPpRTGAhF/repo/main/docs/`) 背景自動同步實測：
  1. **首輪全量背景同步**：Server Daemon 啟動後，`[gdrive-sync]` 自動於背景將 `docs` 空間 49 個檔案全數推送至雲端 `repo/main/docs/`（`exit_code: 0`）。
  2. **事件驅動增量同步**：於本地新增 `docs/gdrive-support/_auto_sync_probe.md` 後，`[file-space-watcher]` 即時偵測變更並喚醒 `[gdrive-sync]`，於數秒內自動將該單檔增量推送至雲端（`pushed: ["docs/gdrive-support/_auto_sync_probe.md"]`）。
  3. **保活探針與清理復原**：背景同步期間 `touch_activity()` 正常將 `Idle TTL Left` 刷新回 `1799.7s`；驗證完畢後已清除雲端與本地探針檔並復原 `config.project.json` 為預設安全狀態（`enable: false, auto_sync: false`）。
- **驗證結果**：通過真實 Google Drive 雲端背景全量與事件驅動增量自動同步驗證。

### [REV-04] 修復三維度正交邊界缺口：雙端皆刪之幽靈基準清理、雲端新建分支自動發現、`checkout --force` 對未追蹤 `.gitignore` 本地檔之保護，並同步更新外部 Skill 寫入前分支詢問守門
- **修訂類別**：Parameter
- **涉及檔案**：
  - `ys_codebase/source/gdrive-support/gdrive_support/reconciler.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`
  - `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py`
  - `ys_codebase/source/gdrive-support/assets/external_skill/gdrive-external-ops/SKILL.md`
  - `ys_codebase/source/gdrive-support/assets/external_skill/gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md`
- **修訂摘要**：針對「雲端/本地分支建立 × 無 `--delete` 刪除 × `.gitignore` 跨端同名不同內容同步檔」三維度正交交互完成架構收斂與外部 Skill 對齊：
  1. **雙端皆刪除之幽靈基準清理 (`both_deleted_prune_baseline`)**：當檔案於本地與雲端皆已刪除（`loc is None and rem is None and base is not None`）且執行無 `--delete` 之同步時，自動清理本地 `sync_state.json` 的 `branch_state_dict[rel_p]` 與雲端 `.yscb_gdrive.json` 的 `branch_files[branch][rel_p]`，杜絕後續重建同名檔案引發假性衝突與卡死 `.history/` 引用計數 GC。
  2. **雲端新建分支資料夾自動發現 (`_reconcile_unregistered_cloud_branches`)**：於 `_ensure_remote_repo_initialized()` 自動掃描 `<repo_sync_root>/` 第一層非系統子目錄（排除 `SYSTEM_NAMES` 與 `.`/`_` 前綴目錄），若外部 Agent 或使用者直接在雲端建立分支資料夾而未更新 `.yscb_gdrive.json`，自動補登錄至 `meta["branches"]`（標記 `auto_discovered: True`）並持久化。
  3. **`checkout --force` 未追蹤本地 `.gitignore` 檔案保護**：`checkout_branch()` 清理 orphan 時僅移除曾被舊分支追蹤（`rel_p in curr_base`）且不在目標分支之檔案；對於尚未進入 `curr_base` 的純本地新檔案（如 `.gitignore` 本地私有檔），若目標分支無同名檔則完整保留，若目標分支有同名碰撞則在覆寫前強制建立 `.conflict.<ts>.bak` 備份。
  4. **外部 Skill 與託管 `README.md` 寫入前分支詢問守門**：於 `gdrive-external-ops/SKILL.md`、`GEMINI_BOOTSTRAP_GUIDE.md` 內嵌模板與 `<repo_sync_root>/README.md` 明文增列「寫入前強制詢問目標分支（直接修改 `main/` vs. 建立新雲端分支 `<repo_sync_root>/<new_branch>/`）」，並說明本地 `yscb gdrive` 支援自動發現雲端新建分支。
- **驗證結果**：新增 `test_et_06_orthogonal_cloud_branch_discovery_both_deleted_prune_and_untracked_checkout_guard` 正交測試，通過 `dev check gdrive-support` 與 `dev test gdrive-support -q --sync`（24/24 100% PASSED）。

### [REV-05] 升級 GitHub Actions CI 與 `release-publish` 管線：無發布需求完全短路、僅驗證/打包新版模組、`yscb.py` 宿主納入 `releases` 分支標準發布、四元組版本防倒退與防竄改守門及 `git gc` 空間釋放
- **修訂類別**：Config
- **涉及檔案**：
  - `.github/workflows/ci.yml`
  - `.github/workflows/release-publish.yml`
  - `yscb.py`
  - `ys_codebase/source/core/core/update_checker.py`
  - `ys_codebase/source/core/tests/test_distribution_lifecycle.py`
  - `docs/core/DESIGN_NOTES.md`
  - `.gitignore`
- **修訂摘要**：重構 `.github/workflows/{ci.yml,release-publish.yml}` 與 `yscb.py` 宿主發布機制：
  1. **無發布需求完全短路 (`has_releases == 'false'` / `needs_publish == 'false'`)**：於 `ci.yml` 加入 `paths` 過濾（排除純 `plans/`、`docs/` 變更）與前置 `detect` 步驟，自動比對 `ys_codebase/release/*/index.json` 與遠端 `origin/releases` 分支；若無任何新版本待發布，直接短路跳過 pip 依賴安裝、環境初始化與測試；`release-publish.yml` 亦加入 `check_pending` 與 `TREE_SHA == REMOTE_TREE_SHA` 雙重短路，杜絕無變更時重推無意義之 orphan commit。
  2. **僅針對新版模組執行增量檢查與測試 (`changed_modules`)**：當偵測到有模組發布新版時，`ci.yml` 從 `origin/releases` 還原既有模組 `.zip`、僅打包新版模組，並僅針對 `changed_modules` 執行 `dev check` 與 `dev test`。
  3. **四元組 (`major.minor.patch.revision`) 合理跳版相容與雙重版本守門**：原生支援 3/4 元組版本號與下架重發所致的跨號跳版，但嚴格攔截「版本倒退（Rollback：`manifest.json` 版本 `<` 歷史最高版本）」、「待發新版與 `source/<mod>/manifest.json` 版本號不一致」以及「已發布版本 `sha256` 帳本竄改（Immutability Violation）」。
  4. **`yscb.py` 宿主本體納入 `releases` 分支標準發布（`main` 100% 純開發端隔離）**：將 `yscb.py` 與 `core/update_checker.py` 之 `DEFAULT_SELF_UPDATE_URL` 切換至 `https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py`；唯有當 `yscb.py` 頂部 `__version__` 正式遞增（`>` `origin/releases:yscb.py` 之 `__version__`）時，CI 與 `release-publish` 才會將新版 `yscb.py` 連同自動生成之 `yscb.py.sha256` 伴隨校驗檔發布至 `releases` 分支根目錄。
  5. **`releases` 分支更新後自動釋放 Git 空間 (`git gc`)**：於 `release-publish.yml` 推送單層 orphan commit 後立即執行 `git reflog expire --expire=now --all && git gc --prune=now` 並清理臨時 index。
- **驗證結果**：通過 `dev check core`、`dev test core -q --sync` 與 CI 檢測腳本實測驗證。

### [REV-06] 整理全模組相依 (`dependencies`) 與選配建議 (`optional`)、更新母倉組態 (`project_role.md` 與 `config/gdrive-support/contribute.json`)，並完成全倉 9 模組與 `yscb.py` 宿主版號晉升及正式打包發布
- **修訂類別**：Config
- **涉及檔案**：
  - `yscb.py`
  - `yscb.config.json`
  - `ys_codebase/source/core/manifest.json`
  - `ys_codebase/source/dev/manifest.json`
  - `ys_codebase/source/server/manifest.json`
  - `ys_codebase/source/file-space/manifest.json`
  - `ys_codebase/source/ast/manifest.json`
  - `ys_codebase/source/knowledge-db/manifest.json`
  - `ys_codebase/source/agents-workflow/manifest.json`
  - `ys_codebase/source/vscode-support/manifest.json`
  - `ys_codebase/source/gdrive-support/manifest.json`
  - `ys_codebase/source/gdrive-support/assets/usage_guide.md`
  - `ys_codebase/config/agents-workflow/snippets/project_role.md`
  - `ys_codebase/config/gdrive-support/contribute.json`
- **修訂摘要**：
  1. **全模組相依與選配建議 (`manifest.json`) 對齊**：將依賴 `core.gitignore` 統一分組軟合併引擎之模組（`agents-workflow`、`vscode-support`、`gdrive-support`）硬相依下限提升至 `core: ">=1.2.6"`；將整合 `server.touch_activity()` 保活探針之模組（`file-space`、`knowledge-db`、`gdrive-support`）選配建議更新為 `server: ">=1.0.4"`；並為 `core`、`dev`、`ast`、`agents-workflow`、`gdrive-support` 補齊結構化 `optional` 擴充建議。
  2. **母倉組態對齊**：更新 `ys_codebase/config/agents-workflow/snippets/project_role.md` 納入完整 9 大第一方模組，建立 `ys_codebase/config/gdrive-support/contribute.json` 預註冊 `docs`、`plans`、`source` 三大 `sync_spaces`，並修正 `gdrive-support/assets/usage_guide.md` 外部隨包技能路徑。
  3. **全模組版號晉升與正式發布安裝**：`yscb.py` 升版至 `1.2.2.2`；依拓撲順序完成 `core@1.2.6.0`、`server@1.0.4.0`、`dev@1.1.4.2`、`file-space@1.0.0.5`、`ast@1.0.0.5`、`knowledge-db@1.2.0.5`、`agents-workflow@1.2.3.5`、`vscode-support@1.0.0.2` 與 `gdrive-support@1.0.0.0` 正式打包發布與本機安裝切換。
- **驗證結果**：通過三步工作流驗證守門（`contributes check`、`agents-workflow compile`、`agents-workflow release`）、`yscb status`（9/9 Healthy）與 `dev check --all`（9/9 PASSED）。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

