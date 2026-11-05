# 技術路線圖：`gdrive-support` Git 原生驅動之附加 Bundle 快照與雲端 Patch 雙軌加速架構 (`gdrive_git_bundle_and_patch_workflow`) (Roadmap)

> 主題：`gdrive-support` Git 原生驅動之附加 Bundle 快照與雲端 Patch 雙軌加速架構 (`gdrive_git_bundle_and_patch_workflow`)  
> 歸檔日期：2026-11-05  
> 狀態：Deferred  
> 目標範疇：`gdrive-support`（或未來獨立之上層 Git 雲端打包協同模組）、`external_skill`  
> 前置解鎖條件：維持 `gdrive-support` 專注於純粹「雲端原子操作」與「環境同步 (`repo_sync`)」職責；僅當未來跨模組雲端審計與大量源碼交換頻率顯著超越散檔同步負載、且確立不增加 `gdrive-support` 核心複雜度之正交邊界時再行評估啟動  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **外部雲端 AI（網頁版 Gemini）逐檔拉取全倉源碼之 I/O 與輪次瓶頸**：網頁版 Gemini 內建之 Google Drive 工具僅支援依單一 `file_id` 逐檔讀取或下載。當執行跨模組深度靜態審計或需參照大量源碼時，需發起數十次單檔下載呼叫並在容器內拼湊還原，耗費工具輪次與等待時間。
  - **雲端跨檔源碼預寫之 Copy-on-Write (CoW) 碎片化開銷**：若雲端 AI 嘗試協助預寫跨多個檔案的第一步源碼實作，受限於網頁端無原生 `PATCH` 覆寫 API，每修改一個檔案皆需執行「舊檔移入 `repo/.trash/` + 建立新檔」兩次 API 呼叫，易在 `.trash/` 產生大量待清理碎片。
  - **重複維護忽略規則與二進位/歸檔資產混入問題**：若另行定義獨立的快照打包目錄清單，易與 `.gitignore` 及 `file-space` 設定產生雙重維護落差，且需避免將大型圖片、模型權重或 `plans/archived/**`（歷史歸檔 Markdown）打入快照包。
- **長期願景與目標定位**：
  - 在不破壞 `module:gdrive-support` 單一職責（僅負責雲端原子操作與 `repo_sync` 環境同步）的前提下，儲備一套**基於本地 `.git` 驅動之「附加 Bundle 快照 (`git_bundle`) + 雲端 Patch (`changes.patch`)」雙軌加速藍圖**：本地透過 `git ls-files` 天然承接 `.gitignore` 並以單一固定 `file_id` 原地 `PATCH` 覆寫 `<repo_sync_root>/.bundle/<branch>.tar.gz`（零雲端垃圾）；網頁版 Gemini 則可透過 **1 次下載呼叫**秒級還原工作區，並以 **單一 `changes.patch` 補丁檔**安全交付跨檔案預寫實作供本地 `git apply --3way` 套用。
- **範疇與邊界約束**：
  - **核心架構邊界決策（暫緩納入 `gdrive-support` 本體）**：為保持 `module:gdrive-support` 架構純粹性與低複雜度，`gdrive-support` 現階段嚴格聚焦於「雲端原子操作 (`ls/get/put/rm/mkdir/shortcut`)」與「三方狀態機環境同步 (`repo_sync`)」，不將 Git 打包與補丁套用耦合進同步主幹。
  - **附加雙軌制（Additive Dual-Track）**：未來若解鎖實作，日常討論與 `plans/`、`docs/` 文檔維護維持直接讀寫雲端散檔；大範圍源碼檢索與跨檔案代碼預寫則走 `.bundle/<branch>.tar.gz` 讀取 + `changes.patch` 交付通道，並具備 100% 無 Git 環境平滑降級能力。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **派生快取原地覆寫、零雲端垃圾不變量（In-Place `PATCH` Without CoW Trash）**：`<repo_sync_root>/.bundle/<branch>.tar.gz` 定位為派生快取產物而非歷史源碼，嚴禁進入 `.history/` 或 `.trash/`。首次建立取得 `bundle_file_id` 並寫入 `.yscb_gdrive.json` 後，後續所有更新一律呼叫 `PATCH /upload/drive/v3/files/{bundle_file_id}?uploadType=media` 原地覆寫二進位內容，`bundle_file_id` 終生固定不變。同時將 `.bundle` 視為雲端系統保留目錄，確保 Level 1 (`changes.list`) 增量遠端快取修補器自動忽略 `.bundle` 變更而不退化為全量掃描。
  - **本地暫存隔離與零 `.gitignore` 污染不變量**：本地打包暫存統一置於 `storage.local://gdrive-support/bundles/<branch>.tar.gz`，待套用之雲端補丁暫存於 `storage.local://gdrive-support/tmp/`，本地快取狀態錨定於 `storage.local://gdrive-support/sync_state.json`，天然受 `core` 基座之全域 `.gitignore` 保護，無須額外擴充 `contributes/core.json` 的 `gitignore` 規則。
  - **`.gitignore` 單一真理承接 + 雙重輕量防線不變量**：打包清單直接取自 `git ls-files -z`（100% 自動排除 `.venv`、`.cache`、`.storage.local`、`.config.local` 機密憑證與未追蹤暫存檔），再疊加 `exclude` 萬用字元（預設排除 `plans/archived/**`、圖片與影音二進位檔）及 `max_file_size_kb`（預設 `512 KB`）單檔體積上限，確保壓縮包恆定維持於數百 KB 級距。
  - **基線包 (`Base Bundle`) + 差量散檔 (`Delta Loose Files`) 自洽不變量**：壓縮包內根目錄嵌入 `.yscb_bundle_meta.json`（記錄 `head_commit` SHA、`branch`、`bundle_sha1`、`created_at` 與包內各檔案之 `sha1` / `size` 映射）。即使本地在兩次 `commit` 之間同步了少數未 commit 的散檔，雲端 AI 解開基線包後只需比對 `.yscb_gdrive.json` 之 `branch_files` 最新雜湊，補抓少數有差異的散檔覆蓋即可獲得 100% 最新狀態。
  - **雲端預寫源碼之單一 `.patch` 三階段安全併入不變量**：雲端 AI 產出跨檔案代碼預寫時，匯出為單一 `changes.patch`（存放於 `repo/<branch>/plans/<plan_id>/changes.patch` 或 `_inbox/<name>.patch`）。本地套用支援「本地路徑 / 雲端相對路徑自動下載」雙模解析，並嚴格執行三階段管線：
    1. **靜態路徑安全守門**：攔截任何含 `..` 穿越、指向 `.git/` 內部或命中敏感憑證規則之目標路徑。
    2. **預檢 (`git apply --check --3way`)**：預檢失敗時保持本地工作區 100% 乾淨並回報結構化衝突資訊。
    3. **工作區套用（預設保留 Uncommitted 狀態）**：預設僅套用至本地工作區供開發者執行 `dev check` / `dev test` 驗收，另提供選配 `--commit <msg>` 旗標按需一鍵提交。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **組態契約概念 (`repo_sync.git_bundle`)**：
    ```json
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
    ```
  - **雙軌自動觸發協議**：支援透過 `.git/hooks/post-commit` 受管區塊（`# === YSCB GDRIVE GIT_BUNDLE BEGIN/END ===`）於每次 `git commit` 後以背景非阻塞子進程更新 Bundle，以及於 `push / sync` 偵測到受追蹤檔案 `bundle_sha1` 變動時順帶原位 `PATCH` 更新（支援 `--no-bundle` 略過）。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 現階段維持 `Deferred`（暫緩），優先保持 `module:gdrive-support` 僅負責「原子操作」與「環境同步」之簡潔邊界。待未來實際跨端協作對全倉源碼快照與 Patch 併入有明確高頻需求、且確認模組職責切分方式後，再透過 `roadmap promote gdrive_git_bundle_and_patch_workflow` 啟動。
- **階段演進構想 (High-Level Stages)**：
  - **Stage 1 — 組態與 `GitBundleBuilder` 打包器**：整合 `git ls-files -z`、`exclude` glob 過濾、`max_file_size_kb` 守門與 `.yscb_bundle_meta.json` 封裝，於 `storage.local://gdrive-support/bundles/` 產出確定性 `.tar.gz`，並在無 `.git` 時安全短路。
  - **Stage 2 — 固定 `file_id` 原地 `PATCH` 傳輸與系統目錄隔離**：建立 `<repo_sync_root>/.bundle/<branch>.tar.gz`、寫入 `branches[branch]["bundle"]` 元數據並支援單檔 `PATCH` 原地更新，同時於 Level 1 增量快取將 `.bundle` 納入系統保留目錄。
  - **Stage 3 — `post-commit` Git Hook 託管與 `bundle / apply` CLI 及 SDK**：實作 `.git/hooks/post-commit` 軟合併注入、`bundle` 快照上傳指令與 `apply <patch_path>` 雙模路徑解析 + 三階段安全套用管線。
  - **Stage 4 — 外部雲端技能雙軌分流協議對齊**：更新外部技能模板，將 `bundle_file_id` 單次拉取 + 差量補抓 + `changes.patch` 交付寫入雲端操作範式。

