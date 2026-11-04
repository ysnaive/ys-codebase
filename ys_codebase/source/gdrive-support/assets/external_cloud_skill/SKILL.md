---
name: gdrive-external-cloud-ops
description: 專供外部 AI Agent 或雲端網頁版 Gemini 直接掛載/操作 Google Drive 雲端資料夾 (`<root_folder_id>/`) 時遵循之目錄結構與安全讀寫規範。
---

# 外部 / 雲端 AI Agent 操作 Google Drive 空間規範 (`gdrive-external-cloud-ops`)

本文件專供**直接連線或掛載 Google Drive 雲端目錄的外部 AI Agent / 網頁版 Gemini** 閱讀與遵循（非本地 `yscb` CLI 技能）。

---

## 1. 雲端根目錄拓撲 (`<root_folder_id>/`)

本 Google Drive 資料夾分為兩個嚴格隔離的區域（受控同步倉子目錄由 `repo_sync.repo_sync_root` 設定，預設為 `repo/`）：

```text
<root_folder_id>/
├── README.md                      # 頂層雲端空間說明（含 YSCB 託管區塊，請勿刪除手寫段落）
├── <其他頂層資料夾與檔案...>       # 【區域 A：純雲端自由儲存區】不與本地程式碼庫自動同步
└── <repo_sync_root>/ (預設 repo/) # 【區域 B：受 yscb gdrive 納管之版本同步倉】（若已啟用）
    ├── .yscb_gdrive.json          # 同步倉分支與引用索引帳本（嚴禁手動修改或刪除）
    ├── README.md                  # 同步倉操作守則
    ├── .history/                  # 歷史分支凍結實體檔保護區（嚴禁修改或刪除）
    ├── .trash/                    # 外部 AI 專用待刪緩衝區（本地 yscb 同步時會自動清空並移入 Google Drive 原生 30 天垃圾桶，切勿留存檔案於此！）
    ├── main/                      # 主幹分支（100% 真實資料夾與最新完整實體檔）
    └── <branch_name>/             # 差量版本分支（真實資料夾骨架 + 差異檔 + Google Drive Shortcut）
```

---

## 2. 外部雲端 Agent 操作三大鐵律

### 鐵律 ①：操作「區域 A：純雲端自由儲存區 (`<repo_sync_root>/` 以外）」
- 在 `<root_folder_id>/` 下除了 `<repo_sync_root>/`（預設 `repo/`）以外的所有目錄，皆屬於**不拉到本地同步之純雲端空間**。
- 外部雲端 Agent 可在此區域自由新增、讀取或整理參考文件、大型素材與備份資料。
- 修改頂層 `README.md` 時，**嚴禁刪除或破壞 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->` 至 `<!-- === YSCB GDRIVE REPO_SYNC END === -->` 之間的託管區塊**。

### 鐵律 ②：操作「區域 B：`<repo_sync_root>/`（預設 `repo/`）受控同步倉」
1. **保持原檔案類型（嚴禁轉檔）**：
    - 所有在 `<repo_sync_root>/main/` 或分支內建立/更新的檔案，**100% 必須保持原始檔案格式**（如 `.md`, `.json`, `.py`, `.png`, `.pdf`, `.xlsx`），**嚴禁**將檔案轉換為 Google Docs / Sheets / Slides 原生線上文件格式。
2. **無原生覆寫能力時的「先移入 `<repo_sync_root>/.trash/` 再重建」協議（注意：`.trash/` 會被自動清空！）**：
    - 當你在雲端環境無法原地覆寫同一個 `file_id`（只能建立同名新檔）或無權限呼叫 Google Drive 原生垃圾桶時，**必須先將舊檔案（或舊 Shortcut）移動至 `<repo_sync_root>/.trash/`，再於原路徑建立新檔案**，防止同一目錄下產生同名重複檔案。
    - **[!CAUTION] 嚴禁將 `<repo_sync_root>/.trash/` 當作備份或留存區**：本地端 `yscb gdrive` 在執行同步或分支管理時，**會自動清空 `<repo_sync_root>/.trash/` 內的所有項目並將其轉移至 Google Drive 原生 30 天垃圾桶 (`trashed=true`)**。任何放入 `.trash/` 的檔案都代表「確認丟棄」，請勿以為放在 `.trash/` 內以後還能直接從該資料夾取回！
3. **保護歷史分支凍結完整性**：
    - 若要修改某個非 `main` 分支（如 `v1.0/`）內的 Google Drive Shortcut 檔案，請先移除該分支下的 Shortcut（移入 `<repo_sync_root>/.trash/`），再於該分支路徑建立新的實體檔案（**切勿直接透過 Shortcut 去修改它指向的 `.history/` 或 `main/` 目標實體檔**，否則會污染其他已凍結的版本分支）。

### 鐵律 ③：絕對禁區
- **嚴禁**手動編輯或刪除 `<repo_sync_root>/.yscb_gdrive.json`。
- **嚴禁**手動修改、搬移或刪除 `<repo_sync_root>/.history/` 內的任何檔案（該目錄由 `yscb gdrive` 引用計數器自動管理，當無任何分支引用時會自動移入 Google Drive 原生 30 天垃圾桶）。
