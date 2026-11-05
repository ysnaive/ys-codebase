---
name: gdrive-local-ops
description: 於本地端透過 `yscb gdrive` (`module:gdrive-support`) 操作 Google Drive 純雲端原子儲存區 (`ls/get/put/rm/mkdir/shortcut`) 與受控工作區分支同步倉 (`<repo_sync_root>/` 之 `init/branch/checkout/pull/push/sync`)。觸發情境：需要在本地上傳或下載不拉到本地同步之純雲端檔案、檢查 Google Drive 憑證與狀態、或於 `repo_sync.enable: true` 時執行雲端分支管理與雙向同步。
---

# 本地端 Google Drive 原子操作與 `repo_sync` 分支同步指南 (`gdrive-local-ops`)

本技能專供**本地開發環境之 Agent** 調用 `python __${yscb.host://yscb.py}__ gdrive` 操作 Google Drive 雲端空間。

---

## 1. 雲端雙區正交邊界（純雲端原子儲存區 vs `<repo_sync_root>/` 同步倉）

`<root_folder_id>` 代表專案在 Google Drive 的總根目錄（例如 `ys-codebase/`），嚴格區分為兩個正交區域（受控同步倉子目錄由 `repo_sync.repo_sync_root` 設定，預設為 `"repo"`）：

| 區域 | 雲端相對路徑 | 本地同步行為 | 允許之 CLI 指令 |
| :--- | :--- | :--- | :--- |
| **① 純雲端自由儲存區 (Pure Cloud Storage)** | `<root_folder_id>/**/*`（**不含 `<repo_sync_root>/`**） | **絕不拉到本地自動同步**；平時不占本地硬碟與 Git 版控空間，按需單點讀寫 | 原子指令：`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`（**無論 `repo_sync.enable` 為 true 或 false 皆可隨時使用**） |
| **② 受控分支同步倉 (`<repo_sync_root>/`，預設 `repo/`)** | `<root_folder_id>/<repo_sync_root>/`（含 `.yscb_gdrive.json`、`main/`、`<branch>/`、`.history/`、`.trash/`） | 僅在 `repo_sync.enable: true` 時與本地 `file-space` 受管空間進行三方對帳雙向同步 | 倉庫與同步指令：`init`, `branch`, `checkout`, `pull`, `push`, `sync`（**當 `repo_sync.enable: false` 時一律拒絕執行**） |

> [!IMPORTANT]
> **操作鐵律**：
> 1. 當開發者要求「把某個大檔/參考資料放到雲端存著（不進本地同步）」或「從雲端抓取某個參考檔下來」時，**一律使用原子指令 (`gdrive ls / get / put / mkdir / rm`) 操作 `<root_folder_id>/` 下非 `<repo_sync_root>/` 的路徑**。
> 2. **刪除與 `.trash/` 自動清理機制**：
>    - 本地執行 `gdrive rm <remote_path>`、刪除分支或無引用 `.history/` GC 時，皆直接將雲端檔案移入 **Google Drive 原生 30 天垃圾桶 (`trashed=true`)**，不會在雲端根目錄建立 `.trash/` 資料夾。
>    - `<repo_sync_root>/.trash/` 僅作為無原生垃圾桶權限之外部/網頁版 AI 搬移舊檔的暫存緩衝區；本地執行 `sync / pull / push / branch delete` 時**會自動清空 `<repo_sync_root>/.trash/` 並將其內容移入 Google Drive 原生 30 天垃圾桶**（**嚴禁將 `.trash/` 視為可長期留存檔案之目錄**）。
> 3. **嚴禁**使用原子指令手動竄改 `<repo_sync_root>/.yscb_gdrive.json` 或 `<repo_sync_root>/.history/` 內之受保護凍結實體檔。

---

## 2. 標準指令速查 (Recipes)

### 2.1 狀態與 OAuth 2.0 授權檢查
```bash
# 檢視 root_folder_id、repo_sync.enable 總開關、repo_sync_root、活躍分支與空間映射
python __${yscb.host://yscb.py}__ gdrive status [--json]

# 檢查 OAuth2 Client ID 憑證與 Token 狀態（不啟動瀏覽器）
python __${yscb.host://yscb.py}__ gdrive auth --check [--json]
```

### 2.2 純雲端原子操作（不受 `repo_sync.enable` 限制，隨時可用）
```bash
# 列舉雲端根目錄或指定子目錄（如檢視不拉到本地同步之純雲端資產）
python __${yscb.host://yscb.py}__ gdrive ls [remote_path] [-r] [--json]

# 單點上傳本地檔案至純雲端區（100% 保持原檔案類型）
python __${yscb.host://yscb.py}__ gdrive put <local_path> <remote_path> [--json]

# 單點從純雲端區下載檔案至本地指定路徑（如 /tmp 或指定目錄）
python __${yscb.host://yscb.py}__ gdrive get <remote_path> <local_path> [--json]

# 於純雲端區建立資料夾、建立 Shortcut 或將項目移入 Google Drive 原生 30 天垃圾桶 (沙盒模式為 .trash/)
python __${yscb.host://yscb.py}__ gdrive mkdir <remote_path> [--json]
python __${yscb.host://yscb.py}__ gdrive shortcut <target_file_id> <shortcut_remote_path> [--json]
python __${yscb.host://yscb.py}__ gdrive rm <remote_path> [--json]
```

### 2.3 `repo_sync` 分支管理與雙向同步（僅於 `repo_sync.enable: true` 時開放）
```bash
# 初始化 <root_folder_id>/<repo_sync_root>/ 同步倉並軟合併頂層 README.md
python __${yscb.host://yscb.py}__ gdrive init [--json]

# 管理 Shortcut 差量分支（刪除分支時自動將無引用 .history/ 歷史檔回收至 Google Drive 原生 30 天垃圾桶）
python __${yscb.host://yscb.py}__ gdrive branch list [--json]
python __${yscb.host://yscb.py}__ gdrive branch create <branch_name> [--from=main] [--json]
python __${yscb.host://yscb.py}__ gdrive branch delete <branch_name> [--json]

# 原子切換工作樹分支
python __${yscb.host://yscb.py}__ gdrive checkout <target_branch> [--force] [--backup] [--json]

# 執行單向拉取、單向推送或三方雙向同步
python __${yscb.host://yscb.py}__ gdrive pull [--delete] [--force] [--backup] [--json]
python __${yscb.host://yscb.py}__ gdrive push [--delete] [--force] [--json]
python __${yscb.host://yscb.py}__ gdrive sync [--delete] [--json]
```
