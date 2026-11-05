### ⚙️ Google Drive 單檔原子與 Repo Sync 設定體檢 (`gdrive-support` / `gdrive`)
<!-- yscb:ignore:begin -->
供 `/how-to-config-yscb` Step 1 自動驗證之體檢片段；編輯者註記於編譯時自動抹除。
<!-- yscb:ignore:end -->
- **① 組態項目與用途**：
  - **連線憑證與 `repo_sync` 總開關**：[`config/gdrive-support/config.project.json`](`__#{config://gdrive-support/config.project.json}__`)（頂層設定 `root_folder_id`、`auth_mode`、`credentials_uri`、`token_uri`；巢狀物件 `"repo_sync": {"enable": false, "repo_sync_root": "repo", "active_branch": "main", "auto_sync": false, ...}` 控制工作區同步與分支功能；個人本機覆寫可放 `.config.local/gdrive-support/config.local.json`（`config.local://gdrive-support/config.local.json`））。
  - **同步空間與路徑重映射宣告**：[`config/gdrive-support/contribute.json`](`__#{config://gdrive-support/contribute.json}__`)（僅當 `repo_sync.enable: true` 時生效，宣告納入 `<root_folder_id>/<repo_sync_root>/<branch>/` 雙向同步之 `sync_spaces` 與 `mapping`）。
- **② 健康度檢查條件**：
  - `python __${yscb.host://yscb.py}__ gdrive status --json`：驗證 `root_folder_id`、`repo_sync.enable`、`repo_sync.repo_sync_root` 狀態、當前 `active_branch` 與生效之 `sync_spaces`。
  - `python __${yscb.host://yscb.py}__ gdrive auth --check --json`：驗證 OAuth 2.0 `credentials.json` 與 `token.json` 授權就緒狀態。
- **③ 隨包設定手冊語意連結**：
  - 進階雙層雲端隔離（`<root_folder_id>/*` 純雲端單檔存取 vs `<root_folder_id>/<repo_sync_root>/` 版控同步）與外部雲端 AI Skill 請按需唯讀查閱 [`gdrive-support 隨包手冊`](`__#{module://gdrive-support/README.md}__`)。
