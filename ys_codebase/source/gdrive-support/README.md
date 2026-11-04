# `gdrive-support` (`gdrive`) — Google Drive 原子雲端操作與 `repo_sync` 雙層隔離同步模組

`gdrive-support`（CLI 短別名 `gdrive`，Python 套件名稱 `gdrive_support`）為 YS-Codebase 生態系之選配雲端協作與版本凍結基座，採用 **「雲端根目錄 `<root_folder_id>/*` 純雲端單檔自由區 + `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）受控分支同步倉」** 雙層物理隔離架構：

1. **永遠可用之單檔原子操作 API/CLI**（`status`, `auth`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）：
   - 無論 `repo_sync.enable` 為 `false`（預設）或 `true`，皆可直接讀寫 `<root_folder_id>/**/*` 下之任何雲端檔案（特別適合存放不想拉到本地工作區自動同步之大型資料集、跨專案共享筆記或歸檔資產）。
   - 100% 保持原檔案類型與原始位元組傳輸（不做 Google Workspace 原生線上文件特化匯出轉檔）。
   - 刪除操作（`rm`、同名衝突去重與無引用歷史回收）於真實雲端直接呼叫 Google Drive 原生 30 天垃圾桶（`PATCH /files/{id}` `{"trashed": true}`），絕不於頂層 `<root_folder_id>/` 建立額外 `.trash/` 資料夾。
2. **`repo_sync` 總開關守門與 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）隔離同步**（預設 `repo_sync.enable: false`）：
   - 當 `repo_sync.enable: false` 時，所有分支與工作區同步設定（含 `auto_sync` 與 `sync_spaces`）皆不生效，CLI 嚴格攔截拒絕 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 指令（拋出 `GDriveRepoSyncDisabledError`）。
   - 當 `repo_sync.enable: true` 時，所有受控版控結構皆隔離收斂於 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）子目錄內（`repo/.yscb_gdrive.json`、`repo/README.md`、`repo/.history/`、`repo/.trash/`、`repo/main/`、`repo/<branch>/`），絕不污染頂層純雲端自由區檔案。
   - **外部 AI 暫存區 `repo/.trash/` 自動清空機制**：`repo/.trash/` 僅供無原生 Trash API 權限之外部雲端 AI（如網頁版 Gemini）作為 Copy-on-Write 刪除緩衝區；本地執行 `sync`、`pull`、`push`、`branch delete` 時會自動將 `repo/.trash/` 內所有項目移入 Google Drive 原生 30 天垃圾桶並清空。
3. **雙層 `README.md` 與本地快取驅動之頂層軟合併 / 軟移除**：
   - `<repo_sync_root>/README.md`（預設 `repo/README.md`）：完整受控同步倉說明。
   - 頂層 `<root_folder_id>/README.md`：透過本地狀態快取 `cache://gdrive-support/readme_sync_state.json` 偵測 `(enable, repo_sync_root)` 狀態變動（僅於初始化啟用或開關切換時觸發，零日常 API 額外開銷）；啟用時自動建立或以 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN/END === -->` 區塊軟合併（100% 保留既有人工內容），關閉時自動軟移除受控區塊（若無剩餘人工內容則移入 Google Drive 原生 30 天垃圾桶）。
4. **雙技能明確分離（本地 `gdrive-local-ops` vs 外部雲端 `external_cloud_skill`）**：
   - **本地 Agent 專用 Skill (`assets/skills/gdrive-local-ops/SKILL.md`)**：透過 `contributes/agents-workflow.json` 自動貢獻至本地 `agents-workflow`，指導本地 Agent 操作 `yscb gdrive` 原子指令與 `repo_sync` 雙模式。
   - **外部雲端 AI 專用隨包 Skill (`assets/external_cloud_skill/SKILL.md`)**：僅隨包封存供外部雲端 AI（如網頁版 Gemini、Drive 外掛 Agent）直接操作 Google Drive 雲端資料夾時查閱（遵循 Copy-on-Write 先移入 `<repo_sync_root>/.trash/` 再建立新檔等規範，並警示 `<repo_sync_root>/.trash/` 會被自動清空至原生垃圾桶），不注入本地 `agents-workflow`。

---

## 1. 組態結構 (`config://gdrive-support/config.project.json`)

```json
{
  "root_folder_id": "<GOOGLE_DRIVE_FOLDER_ID>",
  "auth_mode": "oauth_user",
  "credentials_uri": "config://gdrive-support/credentials.json",
  "token_uri": "cache://gdrive-support/token.json",
  "sandbox_dir": "",
  "repo_sync": {
    "enable": false,
    "repo_sync_root": "repo",
    "active_branch": "main",
    "auto_sync": false,
    "poll_interval_sec": 30.0,
    "pull_delete_default": false,
    "push_delete_default": false
  }
}
```

---

## 2. CLI 指令速查

```bash
# 檢視組態、repo_sync.enable 狀態、repo_sync_root、活躍分支與空間映射
python yscb.py gdrive status [--sandbox-dir=<path>] [--json]

# 檢查或執行 Google Drive OAuth 2.0 Client ID 授權
python yscb.py gdrive auth [--check] [--no-launch-browser] [--code=<url_or_code>] [--port=8765] [--json]

# 單檔原子雲端操作（永遠可用，直接操作 <root_folder_id>/**/*，不拉入本地工作區同步）
python yscb.py gdrive ls [remote_path] [-r] [--sandbox-dir=<path>] [--json]
python yscb.py gdrive put <local_path> <remote_path> [--sandbox-dir=<path>] [--json]
python yscb.py gdrive get <remote_path> <local_path> [--sandbox-dir=<path>] [--json]
python yscb.py gdrive mkdir <remote_path> [--sandbox-dir=<path>] [--json]
python yscb.py gdrive shortcut <target_file_id> <shortcut_remote_path> [--sandbox-dir=<path>] [--json]
python yscb.py gdrive rm <remote_path> [--sandbox-dir=<path>] [--json]

# repo_sync 分支管理與三方同步（僅於 repo_sync.enable: true 時開放，聚焦於 <root_folder_id>/<repo_sync_root>/）
python yscb.py gdrive init [--sandbox-dir=<path>] [--json]
python yscb.py gdrive branch list [--sandbox-dir=<path>] [--json]
python yscb.py gdrive branch create <branch_name> [--from=main] [--sandbox-dir=<path>] [--json]
python yscb.py gdrive branch delete <branch_name> [--sandbox-dir=<path>] [--json]
python yscb.py gdrive checkout <target_branch> [--force] [--backup] [--sandbox-dir=<path>] [--json]
python yscb.py gdrive pull [--delete] [--force] [--backup] [--sandbox-dir=<path>] [--json]
python yscb.py gdrive push [--delete] [--force] [--backup] [--sandbox-dir=<path>] [--json]
python yscb.py gdrive sync [--delete] [--sandbox-dir=<path>] [--json]
```
