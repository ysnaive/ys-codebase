# 技術路線圖：`gdrive-support` Git 原生驅動之附加 Bundle 快照與雲端 Patch 雙軌加速架構 (`gdrive_git_bundle_and_patch_workflow`) (Roadmap)

> 主題：`gdrive-support` Git 原生驅動之附加 Bundle 快照與雲端 Patch 雙軌加速架構 (`gdrive_git_bundle_and_patch_workflow`)  
> 歸檔日期：2026-11-05  
> 狀態：Ready  
> 目標範疇：`gdrive-support`（`config.py`、`coordinator.py`、`transport.py`、`cli.py` 與隨包 `external_skill`）、`git-support`（選配 `post-commit` Hook 協同）  
> 前置解鎖條件：無  
> 模型：Gemini  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **外部雲端 AI（網頁版 Gemini）逐檔拉取全倉源碼之 I/O 與輪次瓶頸**：網頁版 Gemini 內建之 Google Drive 工具僅支援依單一 `file_id` 逐檔讀取或下載。當執行跨模組深度靜態審計（如 `/codebase-deep-auditor`）或需參照大量源碼時，被迫發起 50+ 次單檔下載呼叫並在 9p 掛載目錄下逐一拼湊還原，耗費大量工具輪次與等待時間。
  - **雲端跨檔源碼預寫之 Copy-on-Write (CoW) 碎片化開銷**：若雲端 AI 嘗試協助預寫跨 15~20 個檔案的第一步源碼實作，受限於網頁端無原生 `PATCH` 覆寫 API，每修改一個檔案皆需執行「舊檔移入 `repo/.trash/` + 建立新檔」兩次 API 呼叫，不僅耗時、易因未跑過本地完整測試而直接污染 `repo/main/`，亦會在 `.trash/` 產生大量待清理碎片。
  - **重複維護忽略規則與二進位/歸檔資產混入問題**：若於 `gdrive-support` 另行定義獨立的快照打包目錄清單，易與 `.gitignore` 及 `file-space` 設定產生雙重維護落差，且需避免將大型圖片、模型權重或 `plans/archived/**`（上千個歷史歸檔 Markdown）打入快照包。
- **長期願景與目標定位**：
  - 於 `module:gdrive-support` 的 `repo_sync` 架構中，在不取代既有雲端散檔結構（保留 `plans/`、`docs/` 點對點直覽與快速單檔編修優勢）的前提下，新增**基於本地 `.git` 自動啟用之「附加 Bundle 加速模式 (`git_bundle`)」**：本地透過 `git ls-files` 天然承接 `.gitignore` 並由 `post-commit` Hook 以單一固定 `file_id` 原地 `PATCH` 覆寫 `repo/.bundle/<branch>.tar.gz`（零雲端垃圾）；網頁版 Gemini 則可透過 **1 次下載呼叫**秒級還原工作區，並以 **單一 `changes.patch` 補丁檔**安全交付跨檔案預寫實作供本地 `git apply --3way` 秒級套用。
- **範疇與邊界約束**：
  - 採**附加雙軌制（Additive Dual-Track）**：日常討論、架構設計與 `plans/`、`docs/` 文檔維護維持直接讀寫雲端散檔；大範圍源碼檢索、全倉靜態審計與跨檔案代碼預寫則走 `repo/.bundle/<branch>.tar.gz` 讀取 + `changes.patch` 交付通道。
  - 具備 **100% 無 Git 環境平滑降級**：當本地專案未安裝 `git` 或不存在 `.git` 目錄時，自動略過 `git_bundle` 邏輯並維持純散檔同步，絕不拋出未預期錯誤。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **派生快取原地覆寫、零雲端垃圾不變量（In-Place `PATCH` Without CoW Trash）**：`repo/.bundle/<branch>.tar.gz` 定位為派生快取產物而非歷史源碼，嚴禁進入 `repo/.history/` 或 `repo/.trash/`。一旦首次建立取得 `bundle_file_id` 並寫入 `repo/.yscb_gdrive.json` 後，後續所有更新一律由本地 `GoogleDriveApiTransport` 呼叫 `PATCH /upload/drive/v3/files/{bundle_file_id}?uploadType=media` 原地覆寫二進位內容，`bundle_file_id` 終生固定不變。
  - **`.gitignore` 單一真理承接 + 雙重輕量防線不變量**：打包清單直接取自 `git ls-files -z`（100% 自動排除 `.venv`、`.cache`、`.storage.local`、`.config.local` 機密憑證與未追蹤暫存檔），再疊加 `repo_sync.git_bundle.exclude` 萬用字元（預設排除 `plans/archived/**`、圖片與影音二進位檔）及 `max_file_size_kb`（預設 `512 KB`）單檔體積上限，確保壓縮包恆定維持於數百 KB 級距。
  - **基線包 (`Base Bundle`) + 差量散檔 (`Delta Loose Files`) 自洽不變量**：壓縮包內根目錄嵌入 `.yscb_bundle_meta.json`（記錄 `head_commit` SHA、`branch`、`created_at` 與包內各檔案之 `sha1` 映射）。即使本地在兩次 `commit` 之間透過 `auto_sync` 同步了少數未 commit 的散檔，雲端 AI 解開基線包後只需比對 `.yscb_gdrive.json` 之 `branch_files` 最新 `sha1`，補抓 1~3 個有差異的散檔覆蓋即可獲得 100% 最新狀態。
  - **雲端預寫源碼之單一 `.patch` 隔離交接不變量**：網頁版 Gemini 預設不直接以 CoW 覆寫 `repo/main/` 下的業務源碼散檔；如需提供第一步源碼實作預寫，一律於 Linux VM 內完成 `ast.parse` 語法靜態檢核後，透過 `git diff` 匯出為單一 `plans/<plan_id>/changes.patch`（或 `repo/.patches/<id>.patch`）隨計畫書上傳，由本地端執行 `yscb gdrive apply`（底層封裝 `git apply --3way`）原子套用並執行真實沙盒測試。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **組態契約 (`config://gdrive-support/config.project.json`)**：
    ```json
    "repo_sync": {
      "enable": true,
      "repo_sync_root": "repo",
      "active_branch": "main",
      "auto_sync": true,
      "git_bundle": {
        "enable": true,
        "auto_hook_post_commit": true,
        "max_file_size_kb": 512,
        "exclude": [
          "plans/archived/**",
          "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.webp", "**/*.svg", "**/*.ico",
          "**/*.pdf", "**/*.mp4", "**/*.mp3", "**/*.zip", "**/*.tar.gz", "**/*.onnx", "**/*.bin.gz"
        ]
      }
    }
    ```
  - **本地 `post-commit` 非阻塞觸發協議**：當 `auto_hook_post_commit: true` 時，`gdrive-support` 於 `.git/hooks/post-commit` 維護受管區塊（`# === YSCB GDRIVE GIT_BUNDLE BEGIN/END ===`），於每次 `git commit` 後以背景非阻塞子進程（或通知常駐 `gdrive-sync` Worker）建置記憶體 `.tar.gz` 並執行單檔 `PATCH` 上傳，確保終端 `git commit` 零延遲返回。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 無前置阻斷條件，隨時可透過 `/roadmap promote gdrive_git_bundle_and_patch_workflow` 晉升為正式開發計畫。
- **階段演進構想 (High-Level Stages)**：
  - **Stage 1 — 組態擴充與 `GitBundleBuilder` 記憶體打包器**：於 `gdrive_support/config.py` 擴充 `GitBundleConfig`；實作 `GitBundleBuilder`，整合 `git ls-files -z`、`exclude` glob 過濾、`max_file_size_kb` 守門與 `.yscb_bundle_meta.json` 注入，並在無 `.git` 時安全短路。
  - **Stage 2 — 固定 `file_id` 原地 `PATCH` 傳輸與 `.yscb_gdrive.json` 元數據錨定**：於 `SyncCoordinator` 實作 `sync_git_bundle(branch)`，支援首次建立 `repo/.bundle/<branch>.tar.gz`、寫入 `branches[branch]["bundle"]`（含 `file_id`, `head_commit`, `bundle_sha1`, `updated_at`）及後續單檔 `PATCH` 原地更新。
  - **Stage 3 — `post-commit` Git Hook 託管與 `yscb gdrive bundle / apply` CLI 指令**：實作 `.git/hooks/post-commit` 軟合併注入（非阻塞背景更新 `bundle`）、手動觸發指令 `python yscb.py gdrive bundle` 與雲端補丁套用指令 `python yscb.py gdrive apply <patch_path>`（封裝 `git apply --check` 與 `git apply --3way`）。
  - **Stage 4 — 外部雲端技能 (`gdrive-external-ops` / `role-*`) 雙軌分流協議對齊**：更新隨包外部技能模板與雲端 `.agents/` 指引，將 `bundle_file_id` 單次拉取 + 差量補抓 + `changes.patch` 交付寫入標準雲端操作範式。
