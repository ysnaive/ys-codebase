---
target: "gdrive-support"
doc_type: "readme"
status: "active"
source_paths:
  - "ys_codebase/source/gdrive-support/gdrive_support/config.py"
  - "ys_codebase/source/gdrive-support/gdrive_support/reconciler.py"
  - "ys_codebase/source/gdrive-support/gdrive_support/transport.py"
  - "ys_codebase/source/gdrive-support/gdrive_support/coordinator.py"
  - "ys_codebase/source/gdrive-support/gdrive_support/service.py"
  - "ys_codebase/source/gdrive-support/scripts/cli.py"
related_docs:
  - "../_project/ARCHITECTURE.md"
last_updated: "2026-11-04"
---

# `module:gdrive-support` 系統架構與開發手冊

本文件定義 `module:gdrive-support`（短別名 `gdrive`）之五大正交核心部件架構、`repo_sync` 雙層雲端隔離契約（`<root_folder_id>/*` 純雲端單檔存取區 vs `<root_folder_id>/<repo_sync_root>/` 預設 `repo/` 受控同步倉）、雙層 `README.md` 本地快取軟合併機制、Shortcut 差量分支與 `.history/` $\to$ Google Drive 原生 30 天垃圾桶（`trashed=true`）引用計數回收及 `<repo_sync_root>/.trash/` 自動清空機制，以及本地/外部雲端雙 Skill 分離設計。

---

## 1. 五大正交核心部件與單向 DAG

```text
scripts/cli.py ──┐
                 ├──► coordinator.py ──► transport.py ──► reconciler.py ──► config.py
service.py ──────┘
```

| 部件路徑 | 核心職責與不變量 |
| :--- | :--- |
| **`gdrive_support/config.py`** | 解析頂層連線憑證與巢狀 `repo_sync` 組態（`RepoSyncConfig`，預設 `enable: false`、`repo_sync_root: "repo"`、`auto_sync: false`、`active_branch: "main"`）。當 `repo_sync.enable == false` 時強制停用 `auto_sync` 與 `sync_spaces`；`SyncSpaceSpec.is_local_abs_allowed()` 強制校驗所有拉取/刪除路徑不得越出 `file-space` 註冊之 `include` 根目錄。 |
| **`gdrive_support/reconciler.py`** | **100% 無狀態純函式 (`S2`)**：零磁碟/網路 I/O、零系統時間呼叫；計算三方 8 態 `SyncAction` 與 `.history/` 跨分支引用計數（`compute_history_ref_counts`、`compute_orphan_history_file_ids`）。 |
| **`gdrive_support/transport.py`** | 100% 保持原檔案類型與原始位元組之原子傳輸介面（`AbstractSyncTransport`），提供 `LocalSandboxTransport` 與純標準庫 `GoogleDriveApiTransport`（含執行緒本地 `HTTPSConnection` Keep-Alive 連線池、`_folder_cache` 目錄路徑快取、`_scanned_prefixes` 遞迴掃描後免重查 `get_entry`、OAuth 2.0 Loopback / `--no-launch-browser` + `--code` 兩階段授權、`token.json` 零 `client_secret` 落盤與 `0o600` 權限保護），直接以 `<root_folder_id>` 為基準提供單檔原子操作；雲端刪除與同名去重一律直接移入 Google Drive 原生 30 天垃圾桶 (`{"trashed": true}`)。 |
| **`gdrive_support/coordinator.py`** | 透過 `ensure_repo_sync_enabled()` 守門（當 `repo_sync.enable == false` 時拋出 `GDriveRepoSyncDisabledError`）；將所有同步與分支目錄隔離於 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）下，於執行 `push`、`pull` 與 `branch create` 前先依路徑深度預建所有父目錄 (`_precreate_remote_dirs`) 並透過 `ThreadPoolExecutor` 多執行緒並發傳輸與增量狀態落盤，於同步或刪除分支時自動清空外部 AI 暫存之 `<repo_sync_root>/.trash/` 至原生 30 天垃圾桶，並以 `reconcile_root_readme_state()` 依據本地快取 `cache://gdrive-support/readme_sync_state.json` 的狀態變動對頂層 `<root_folder_id>/README.md` 執行軟合併或軟移除。 |
| **`gdrive_support/service.py`** | `GDriveSyncServiceWorker`：當 `repo_sync.enable == false` 或 `repo_sync.auto_sync == false` 時處於零輪詢 `standby` 模式（`health_check() -> True`）；啟用時訂閱 `file_space.service.subscribe` 並於 `stop()` 確定性呼叫 `_unsubscribe()`。 |

---

## 2. 雲端雙層目錄隔離與雙層 `README.md` 軟合併機制

1. **頂層純雲端自由區 (`<root_folder_id>/*`，不含 `<repo_sync_root>/`)**：
   - 存放不需要拉到本地工作區自動同步的雲端資料，永遠可透過原子指令（`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）單點讀寫，且頂層絕不產生 `.trash/` 資料夾。
2. **受控同步子倉庫 (`<root_folder_id>/<repo_sync_root>/`，預設 `repo/`)**：
   - 僅於 `repo_sync.enable: true` 時啟用，內部包含 `repo/.yscb_gdrive.json`、`repo/README.md`、`repo/.history/`、`repo/.trash/`（供無原生 Trash API 權限之外部 AI 暫存刪除檔，並於下次本地 `sync/pull/push/branch delete` 時自動清空至 Google Drive 原生 30 天垃圾桶）、`repo/main/` 與 `repo/<branch>/`。
3. **本地快取驅動之頂層 `<root_folder_id>/README.md` 軟合併 / 軟移除**：
   - 本地 `cache://gdrive-support/readme_sync_state.json` 記錄各目標根目錄最後已知的 `(enable, repo_sync_root)` 狀態；僅於狀態發生變動時才檢查頂層 `README.md`（使用 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN/END === -->` 標記，100% 保留使用者自寫內容）。

---

## 3. 雙技能明確分離架構

- **本地操作技能 (`assets/skills/gdrive-local-ops/SKILL.md`)**：透過 `contributes/agents-workflow.json` 注入本地 `agents-workflow`，供本地 Agent 操作 `module:gdrive-support` CLI 與 SDK。
- **外部雲端操作隨包技能組 (`assets/external_skill/`)**：隨包提供給外部雲端 AI 直接操作 Google Drive 雲端資料夾時遵循，不注入本地 `agents-workflow`：
  - `assets/external_skill/gdrive-external-ops/SKILL.md`：通用外部 AI Agent 技能範本（含 `§0` 7 維度專案實例化回填配置區塊与雙端溝通媒介協議）。
  - `assets/external_skill/gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md`：專供複製給網頁版 Gemini 之隨包引導手冊（啟用時強制執行「網頁版 Gemini 任務模式 + 可並行任務 + Linux 虛擬運行機 + Google Drive 直連」環境自檢，不合法即阻斷任務，通過後自動探查雲端根目錄並回填生成專屬 `SKILL.md`）。
