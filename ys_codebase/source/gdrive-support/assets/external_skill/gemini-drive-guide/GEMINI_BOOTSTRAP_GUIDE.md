---
name: gdrive-gemini-bootstrap-guide
description: 專供使用者「單檔一鍵複製」貼給「網頁版 Gemini（任務模式）」之隨包自檢與專案專屬手冊/Skill 自舉生成指南。強制驗證「網頁版 Gemini 任務模式 + 可並行任務 + Linux 虛擬運行機 + Google Drive 直連」環境，並內嵌完整目標模板供 Gemini 探查回填後直接產出最終專屬文件。
---

# 網頁版 Gemini 專屬雲端協作自檢與專案手冊生成指南 (`GEMINI_BOOTSTRAP_GUIDE`)

> **給使用者的使用說明（單檔一鍵複製）**：  
> 當您要在**網頁版 Gemini** 開啟與本專案 Google Drive 雲端資料夾的協作時，**只需複製本文件單一檔案全文**貼給網頁版 Gemini，並附上您的 Google Drive 根目錄連結（或資料夾名稱）。  
> 網頁版 Gemini 將自動執行環境剛性自檢、盤點雲端目錄、向您確認協作細節，並根據本文件底部內嵌之模板直接為您生成回填完畢的**最終專案專屬操作手冊 (`SKILL.md`)**！

---

## 🚨 階段 0：啟用時環境剛性自檢守門（Mandatory Runtime Self-Check Gate）

**【給 Gemini 的最高優先級強制指令】**  
當你收到本文件時，在執行任何分析、讀取或回填動作之前，**你必須立即對自身當前運行環境執行以下 3 項剛性自檢**：

1. **模式檢核 — 網頁版 Gemini 任務模式（Task / Agentic Mode with Parallel Sub-tasks）**：
   - 確認當前對話處於支援多步驟規劃與**可並行派發任務（Parallel Tasks / Sub-tasks）**的網頁版 Gemini 任務模式，而非受限的單輪純聊天模式。
2. **算力沙盒檢核 — Linux 虛擬運行機（Linux Virtual Execution Environment）**：
   - 確認當前對話具備可實際執行 Shell / Python 腳本與檔案處理的 **Linux 虛擬運行機容器環境**（請在沙盒內執行輕量環境確認如 `uname -a` 與 `python3 --version` 實證）。
3. **雲端連接檢核 — Google Drive 直連能力（Google Workspace / Drive Extension）**：
   - 確認當前環境可存取使用者的 Google Drive 雲端硬碟目標資料夾。

> [!CAUTION]
> **🛑 環境不合法強制阻斷鐵律（Hard Abort on Self-Check Failure）**：  
> - 若上述任一項自檢**未通過**（例如：當前並非處於包含**可並行任務 + Linux 虛擬運行機**之網頁版 Gemini 任務模式，或未啟用 Google Drive 連接權限）：
>   1. **立即中止並阻斷當前所有後續任務**（嚴禁在無 Linux 虛擬機或非任務模式下勉強猜測、臆測或降級執行！）。
>   2. **明確向使用者報告自檢未通過的具體項目**，並提示使用者：
>      *「⚠️ 環境自檢未通過：當前對話未處於『網頁版 Gemini 任務模式（含可並行任務 + Linux 虛擬運行機）』或未開啟 Google Drive 存取權限。請先切換至正確的網頁版 Gemini 任務模式並開啟對應環境後，再重新貼入本手冊啟動任務。」*

---

## 🔍 階段 1：雲端根目錄探查與專案上下文讀取（Cloud Root Discovery）

通過階段 0 環境自檢後，請利用你的 Google Drive 連接能力與 Linux 虛擬運行機（可並行拉取與解析檔案），針對使用者提供的 Google Drive 根目錄（`<root_folder_id>`）執行以下探查：

1. **確認頂層結構 (`<root_folder_id>/`)**：
   - 讀取頂層 `README.md`（檢查是否存在 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->` 託管區塊，從中識別受控同步倉子目錄名稱 `<repo_sync_root>`，預設為 `repo/`）。
   - 盤點頂層除了 `<repo_sync_root>/` 以外有哪些「區域 A：純雲端自由儲存區」資料夾（例如 `cloud_vault/`、`_inbox/` 等）。
2. **探查受控同步倉 (`<root_folder_id>/<repo_sync_root>/`，預設 `repo/`)**：
   - 若存在 `<repo_sync_root>/.yscb_gdrive.json`，讀取（**嚴禁修改**）其內容以獲知目前註冊的分支清單（如 `main`、`v1.0`）。
   - 檢查 `<repo_sync_root>/main/` 下的頂層目錄結構（如 `docs/`、`plans/`、`ys_codebase/`），並讀取關鍵入門文檔（如 `docs/_project/ARCHITECTURE.md` 或 `README.md`）以掌握專案核心架構。

---

## 💬 階段 2：向使用者核對 7 大初始化參數（Interactive Alignment）

完成雲端自動探查後，將你探查到的已知事實整理成簡潔清單，並針對無法僅靠探查決定的項目向使用者發起一次性的確認提問：

1. **雲端根目錄定位 (`root_folder_id` & 資料夾名稱/連結)**：呈現你鎖定的 Folder ID 與名稱請使用者確認無誤。
2. **`repo_sync` 狀態、同步倉路徑 (`repo_sync_root`) 與預設分支 (`active_branch`)**：呈現探查到的狀態（如 `enable: true`, `repo_sync_root: "repo"`, 預設操作 `main/`）。
3. **專案簡介與核心文檔上手導航地圖**：根據你讀到的 `ARCHITECTURE.md` / `README.md` 擬定 2~3 行專案簡介與必讀入口路徑，請使用者確認。
4. **空間映射表 (`sync_spaces`)**：列出你在 `<repo_sync_root>/main/` 下看到的同步目錄（如 `docs/`、`plans/`）。
5. **雙端溝通媒介與交接協議（Cross-Agent Handoff & Inbox）**：
   - 詢問使用者：當網頁版 Gemini 完成調研報告、程式碼審查或跨端交接給本地開發 Agent（如 Antigravity / Cursor）時，希望透過哪種媒介溝通？
     - *選項 A（雲端交換區）*：寫入頂層純雲端區 `_inbox/`（或指定資料夾），由本地端透過 `python yscb.py gdrive get` 拉取。
     - *選項 B（容器打包匯出 + 使用者上傳/同步）*：於網頁版 Gemini 的 Linux 虛擬機內直接產出完整 Markdown / Patch / 壓縮包供下載，或寫入雲端指定位置。
6. **網頁版 Gemini 的角色定位與寫入邊界**：
   - 詢問使用者本次（或常態）授權 Gemini 的操作邊界（例如：僅限唯讀審查與寫入區域 A / `_inbox/`，或允許依 Copy-on-Write 規範將舊檔移入 `<repo_sync_root>/.trash/` 後更新 `<repo_sync_root>/main/`）。
7. **環境能力自檢結果固化**：記錄已驗證通過之「網頁版 Gemini 任務模式 + 可並行任務 + Linux 虛擬運行機 + Google Drive 直連」狀態。

---

## 🛠️ 階段 3：回填下方內嵌模板並生成最終專案專屬 `SKILL.md`

待使用者回覆確認階段 2 的問題後：
1. 於你的 **Linux 虛擬運行機**中，直接提取下方 **「📦 附錄：待回填之最終專案專屬 `SKILL.md` 標準模板」**。
2. 將 **「§1 專案實例化配置區塊 (Project Instance Profile)」** 中的 `<TODO:...>` 全數替換為確認後的真實專案資訊。
3. 產出完整定製後的 `SKILL.md` 檔案供使用者下載保存（或依使用者指示存放至雲端目錄），作為後續所有網頁版 Gemini 任務的標準啟動技能！

---

## 📦 附錄：待回填之最終專案專屬 `SKILL.md` 標準模板

*(Gemini 請於階段 3 將下方區塊內的 `<TODO:...>` 替換為真實專案資訊後，輸出為獨立的 `SKILL.md` 檔案)*

````markdown
---
name: gdrive-gemini-project-ops
description: 專供網頁版 Gemini（任務模式 + 可並行任務 + Linux 虛擬運行機）直連操作本專案 Google Drive 雲端空間 (`<root_folder_id>/`) 之定製化協作技能手冊。
---

# 網頁版 Gemini 專案雲端協作與 Google Drive 操作規範 (`gdrive-gemini-project-ops`)

## 🚨 0. 啟動時強制環境自檢守門（Mandatory Runtime Self-Check Gate）

每次載入本技能啟動任務時，**你（Gemini）必須先驗證自身當前環境是否同時滿足以下 3 項條件**：
1. **網頁版 Gemini 任務模式（含可並行派發子任務能力）**。
2. **具備 Linux 虛擬運行機容器環境**（可執行 Shell / Python 進行精確檔案處理、Diff 比對、雜湊計算與打包）。
3. **已開啟 Google Drive 雲端硬碟連接權限**。

> **[!CAUTION] 環境不合法強制阻斷**：若當前環境缺少上述任一條件（例如處於一般單輪聊天模式或無 Linux 虛擬機），**必須立即中止並阻斷任務**，明確告知使用者切換至「網頁版 Gemini 任務模式（含可並行任務 + Linux 虛擬運行機）」後再重新執行！

---

## 1. 專案實例化配置區塊 (Project Instance Profile)

| 配置維度 | 專案設定值 |
| :--- | :--- |
| **1. 雲端根目錄 (`root_folder_id` & URL)** | `<TODO: 填入 Google Drive Folder ID 與完整資料夾連結>` |
| **2. `repo_sync` 狀態與同步倉路徑 (`repo_sync_root` / `active_branch`)** | `<TODO: 填入 enable=true/false、repo_sync_root（預設 repo/）與預設分支（預設 main/）>` |
| **3. 專案簡介與核心上手導航 (Project Overview & Entrypoints)** | `<TODO: 1~3 句話簡述專案核心使命，並列出首次必讀雲端路徑，如 README.md、repo/main/docs/_project/ARCHITECTURE.md>` |
| **4. 空間映射表 (`sync_spaces` & Mapping Table)** | `<TODO: 列出雲端 repo/<branch>/ 下各目錄與本地專案空間之對應關係，如 docs/ <-> project://docs/>` |
| **5. 雙端溝通媒介與交接協議 (Cross-Agent Handoff & Inbox)** | `<TODO: 定義網頁版 Gemini 與本地開發 Agent 的訊息/調研報告交換路徑與命名規範，如頂層 _inbox/YYYYMMDD_topic.md 或 Linux 虛擬機打包匯出>` |
| **6. 網頁版 Gemini 角色定位與讀寫權限邊界 (Role & Write Scope)** | `<TODO: 明確定義角色與寫入範圍，如：唯讀審查 / 僅寫入區域 A 純雲端區與 _inbox/ / 允許依 CoW 規範更新 repo/main/docs/>` |
| **7. 環境能力自檢基準 (Verified Environment Capabilities)** | `網頁版 Gemini 任務模式 + 可並行任務 + Linux 虛擬運行機 + Google Drive 直連` |

---

## 2. 雲端根目錄雙層拓撲 (`<root_folder_id>/`)

本 Google Drive 資料夾分為兩個嚴格隔離的區域（受控同步倉子目錄由 `repo_sync.repo_sync_root` 設定，預設為 `repo/`）：

```text
<root_folder_id>/
├── README.md                      # 頂層雲端空間說明（含 YSCB 託管區塊，請勿刪除手寫段落）
├── _inbox/ (或約定之溝通目錄)       # 【雙端溝通交換區】供網頁版 Gemini 與本地 Agent 交換調研報告、問題單與交接快照
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

## 3. 網頁版 Gemini 操作四大鐵律

### 鐵律 ①：善用「可並行任務 + Linux 虛擬運行機」
- 面對跨多目錄（如 `repo/main/docs/`、`repo/main/plans/` 與頂層純雲端資料夾）的檢索、架構調研或盲審任務時，優先拆分為**可並行子任務**同時讀取與分析。
- 需要比對差異 (`diff`)、驗證 JSON/YAML 語法、計算雜湊 (`md5sum`/`sha256sum`)、批量整理文件或生成結構化報告時，一律將雲端檔案載入 **Linux 虛擬運行機** 內以 Python / Shell 工具精確處理並驗證無誤後，再輸出或寫回雲端。

### 鐵律 ②：操作「區域 A：純雲端自由儲存區（`<repo_sync_root>/` 以外）」與雙端交接
- 在 `<root_folder_id>/` 下除了 `<repo_sync_root>/`（預設 `repo/`）以外的所有目錄，皆屬於**不拉到本地同步之純雲端空間**。
- 產出調研報告或交接檔案時，依 §1 約定之雙端溝通媒介存放，並提供精確雲端相對路徑供本地端以 `python yscb.py gdrive get <remote_path> <local_path>` 單點拉取。
- 修改頂層 `README.md` 時，**嚴禁刪除或破壞 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->` 至 `<!-- === YSCB GDRIVE REPO_SYNC END === -->` 之間的託管區塊**。

### 鐵律 ③：操作「區域 B：`<repo_sync_root>/`（預設 `repo/`）受控同步倉」
1. **寫入前強制詢問目標分支（直接改 `main` vs. 新增雲端分支 `<new_branch>`）**：
   - 每次任務涉及寫入或修改 `<repo_sync_root>/` 內的受控同步檔案前，**嚴禁未經詢問直接覆寫 `main/`**！你必須先向使用者確認本次任務要：
     - **直接修改 `main/`（或當前指定分支）**：完成後提醒使用者於本地執行 `python yscb.py gdrive pull`（或 `sync`）。
     - **建立新雲端分支 `<repo_sync_root>/<new_branch>/` 隔離修改**：可直接於雲端建立 `<repo_sync_root>/<new_branch>/` 資料夾寫入（本地 `yscb gdrive` 支援**雲端未註冊分支自動發現**，無須手動改 `.yscb_gdrive.json` 即可由本地透過 `python yscb.py gdrive branch list` 與 `checkout <new_branch>` 自動識別並拉取），或請使用者於本地執行 `python yscb.py gdrive branch create <new_branch>` 建立零空間捷徑分支後再修改。
2. **保持原檔案類型（嚴禁轉檔）**：
   - 所有在 `<repo_sync_root>/main/` 或分支內建立/更新的檔案，**100% 必須保持原始檔案格式**（如 `.md`, `.json`, `.py`, `.png`, `.pdf`, `.xlsx`），**嚴禁**轉換為 Google Docs / Sheets / Slides 原生線上文件格式。
3. **無原生覆寫或無原生垃圾桶權限時的「先移入 `<repo_sync_root>/.trash/` 再重建」協議**：
   - 當無法原地覆寫同一個 `file_id` 或無權限呼叫 Google Drive 原生垃圾桶時，**必須先將舊檔案（或舊 Shortcut）移動至 `<repo_sync_root>/.trash/`，再於原路徑建立新檔案**，防止同一目錄下產生同名重複檔案。
   - **[!CAUTION] 嚴禁將 `<repo_sync_root>/.trash/` 當作備份或留存區**：本地端 `yscb gdrive` 在執行同步或分支管理時，**會自動清空 `<repo_sync_root>/.trash/` 內的所有項目並將其轉移至 Google Drive 原生 30 天垃圾桶 (`trashed=true`)**。任何放入 `.trash/` 的檔案都代表「確認丟棄」，請勿以為放在 `.trash/` 內以後還能直接從該資料夾取回！
   - 若直接修改了 `<repo_sync_root>/<branch>/` 內的檔案，完成後**必須主動提醒使用者**於本地執行 `python yscb.py gdrive pull`（或 `checkout <new_branch>`）。
4. **保護歷史分支凍結完整性**：
   - 若要修改某個非 `main` 分支（如 `v1.0/`）內的 Google Drive Shortcut 檔案，請先移除該分支下的 Shortcut（移入 `<repo_sync_root>/.trash/`），再於該分支路徑建立新的實體檔案（**切勿直接透過 Shortcut 去修改它指向的 `.history/` 或 `main/` 目標實體檔**）。

### 鐵律 ④：絕對禁區
- **嚴禁**手動編輯或刪除 `<repo_sync_root>/.yscb_gdrive.json`。
- **嚴禁**手動修改、搬移或刪除 `<repo_sync_root>/.history/` 內的任何檔案。
````
