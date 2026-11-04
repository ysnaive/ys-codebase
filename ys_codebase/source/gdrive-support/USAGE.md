# `module:gdrive-support` (`gdrive`) 使用說明

`module:gdrive-support` 提供：
1. **單檔原子雲端檔案操作**（`status`, `auth`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）：永遠可用，直接操作 `<root_folder_id>/**/*`（適合讀寫不拉到本地同步之純雲端檔案）。
2. **`repo_sync` 雲端分支管理與雙向同步**（`init`, `branch`, `checkout`, `pull`, `push`, `sync`）：預設關閉（`repo_sync.enable: false`），啟用後隔離運作於 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）。

## 1. 常用單檔原子 CLI 指令（永遠可用）

```bash
# 檢視組態、repo_sync.enable 總開關狀態、repo_sync_root 與空間映射
python yscb.py gdrive status [--json]

# 列舉雲端或本地沙盒目錄（<root_folder_id>/**/*）
python yscb.py gdrive ls [remote_path] [-r] [--sandbox-dir=<path>] [--json]

# 原子上傳與下載單一檔案（100% 保持原檔案類型，不觸發全倉同步）
python yscb.py gdrive put <local_path> <remote_path> [--sandbox-dir=<path>]
python yscb.py gdrive get <remote_path> <local_path> [--sandbox-dir=<path>]

# 建立目錄、建立檔案捷徑與移入 Google Drive 原生 30 天垃圾桶（本地沙盒則移入 .trash/）
python yscb.py gdrive mkdir <remote_path> [--sandbox-dir=<path>]
python yscb.py gdrive shortcut <target_file_id> <shortcut_remote_path> [--sandbox-dir=<path>]
python yscb.py gdrive rm <remote_path> [--sandbox-dir=<path>]
```

## 2. `repo_sync` 分支管理與雙向同步指令（需 `repo_sync.enable: true`）

```bash
# 初始化 <root_folder_id>/<repo_sync_root>/（預設 repo/，建立 .yscb_gdrive.json、README.md、.history/、.trash/、main/ 並軟合併頂層 README.md）
python yscb.py gdrive init [--sandbox-dir=<path>]

# 建立、列舉與刪除 Shortcut 差量分支（刪除分支時自動將無引用 <repo_sync_root>/.history/ 檔案與外部 AI 放入 <repo_sync_root>/.trash/ 之檔案移入原生 30 天垃圾桶）
python yscb.py gdrive branch list [--sandbox-dir=<path>]
python yscb.py gdrive branch create <branch_name> [--from=main] [--sandbox-dir=<path>]
python yscb.py gdrive branch delete <branch_name> [--sandbox-dir=<path>]

# 原子切換活躍分支並對齊本地工作樹
python yscb.py gdrive checkout <target_branch> [--force] [--backup] [--sandbox-dir=<path>]

# 執行單向拉取、單向推送或三方雙向同步
python yscb.py gdrive pull [--delete] [--force] [--backup] [--sandbox-dir=<path>]
python yscb.py gdrive push [--delete] [--force] [--backup] [--sandbox-dir=<path>]
python yscb.py gdrive sync [--delete] [--sandbox-dir=<path>]
```
