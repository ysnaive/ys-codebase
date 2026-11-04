### ☁️ Google Drive 單檔原子存取與 Repo Sync 版控同步 (`gdrive-support` / `gdrive`)
<!-- yscb:ignore:begin -->
註：預設 `repo_sync.enable: false` 下僅開放單檔原子指令；啟用 `repo_sync.enable: true` 後方開放 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）分支與工作區同步。
<!-- yscb:ignore:end -->
- **① 模組定位與適用時機**：
  - **單檔原子操作（永遠可用）**：直接讀寫雲端根目錄 `<root_folder_id>/**/*` 下之純雲端檔案（大型資產、歸檔、不拉到本地工作區之檔案）或單點檢視雲端目錄。
  - **`repo_sync` 工作區版控同步（需 `repo_sync.enable: true`）**：將指定 `file-space` 雙向同步至 `<root_folder_id>/<repo_sync_root>/<branch>/`（預設 `repo/<branch>/`），支援 Google Drive Shortcut 增量分支與 `.history/` Copy-on-Write 引用計數回收。
- **② 標準用法速查 (Golden Recipes)**：
  - **狀態與授權檢查 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ gdrive status [--json]` / `python __${yscb.host://yscb.py}__ gdrive auth --check [--json]`
  - **單檔原子讀寫 (`🟢 [SAFE]` / `🟡 [CONDITIONAL]`)**：
    - 列目與下載：`python __${yscb.host://yscb.py}__ gdrive ls [remote_path] [--recursive] [--json]` / `python __${yscb.host://yscb.py}__ gdrive get <remote_path> <local_path> [--json]`
    - 上傳與移入原生垃圾桶：`python __${yscb.host://yscb.py}__ gdrive put <local_path> <remote_path> [--json]` / `python __${yscb.host://yscb.py}__ gdrive rm <remote_path> [--json]`
  - **`repo_sync` 分支與三向同步（僅 `repo_sync.enable: true` 可用，`🟡 [CONDITIONAL]`）**：
    - 初始化與分支：`python __${yscb.host://yscb.py}__ gdrive init [--json]` / `python __${yscb.host://yscb.py}__ gdrive branch <list|create|delete> ...` / `python __${yscb.host://yscb.py}__ gdrive checkout <branch>`
    - 拉取、推送與雙向同步：`python __${yscb.host://yscb.py}__ gdrive <pull|push|sync> [--delete] [--force] [--backup] [--json]`
- **③ 隨包手冊語意連結**：
  - 深入探索雙層 `README.md` 軟合併協議、Shortcut 分支與外部雲端 AI 隨包技能 (`assets/external_skill/gdrive-external-ops/SKILL.md` 及 `assets/external_skill/gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md`) 請按需唯讀查閱 [`gdrive-support 隨包手冊`](`__#{module://gdrive-support/README.md}__`)。
