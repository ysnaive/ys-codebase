---
name: gdrive-external-ops
description: 專供任何外部 AI Agent 直接掛載或透過雲端介面操作 Google Drive 雲端資料夾 (`<root_folder_id>/`) 時遵循之專案初始化回填設定檔、雙端溝通協議、雙層目錄架構與安全讀寫規範。
---

# 外部 AI Agent 操作 Google Drive 空間通用規範 (`gdrive-external-ops`)

> [!IMPORTANT]
> **🚨 首次使用前置自舉指令（First-Time Bootstrap Instruction for External Agents）**：  
> 當你（外部 AI Agent）首次讀取本技能範本且下方 **「§0 專案實例化配置區塊 (Project Instance Profile)」** 仍處於 `<TODO:...>` 未回填狀態時，**嚴禁直接開始執行業務修改**！你必須先依序完成以下 4 步初始化回填，產出專屬於本專案的定製版 `SKILL.md`：
> 1. **定位並探查雲端根目錄**：向使用者確認或於 Google Drive 定位目標 `<root_folder_id>`，讀取頂層 `README.md` 與（若存在）`<repo_sync_root>/.yscb_gdrive.json`、`<repo_sync_root>/README.md`、`<repo_sync_root>/main/docs/_project/ARCHITECTURE.md`。
> 2. **盤點空間映射與雙端溝通媒介**：確認雲端哪些資料夾屬於「區域 A：純雲端自由區」、哪些屬於「區域 B：`<repo_sync_root>/` 同步倉」，並與使用者確認雙端溝通交換目錄（如頂層 `_inbox/` 或指定交換檔）。
> 3. **環境能力與寫入邊界自檢**：測試並確認你當前環境對 Google Drive 的讀寫能力（是否支援搬移至 `.trash/`、是否具備 Linux 沙盒與並行任務能力），並與使用者確認你的角色與允許寫入範圍。
> 4. **回填 §0 並輸出定製版 `SKILL.md`**：將確認完畢的真實參數填入下方 **§0 專案實例化配置區塊**，移除 `<TODO:...>` 佔位符，將完整定製後的 `SKILL.md` 交還使用者保存（或存於雲端指定位置）作為後續固定載入之技能。

---

## 0. 專案實例化配置區塊 (Project Instance Profile — 待首次自舉回填)

| 配置維度 | 專案設定值（首次自舉時由外部 Agent 探查並與使用者確認後回填） |
| :--- | :--- |
| **1. 雲端根目錄 (`root_folder_id` & URL)** | `<TODO: 填入 Google Drive Folder ID 與完整資料夾連結，例如 1MeDEInAzn11JobNbfA_6uQ2OPpRTGAhF>` |
| **2. `repo_sync` 狀態與同步倉路徑 (`repo_sync_root` / `active_branch`)** | `<TODO: 填入 enable=true/false、repo_sync_root（預設 repo/）與預設分支（預設 main/）>` |
| **3. 專案簡介與核心上手導航 (Project Overview & Entrypoints)** | `<TODO: 1~3 句話簡述專案核心使命，並列出首次必讀雲端路徑，如 README.md、repo/main/docs/_project/ARCHITECTURE.md>` |
| **4. 空間映射表 (`sync_spaces` & Mapping Table)** | `<TODO: 列出雲端 repo/<branch>/ 下各目錄與本地專案空間之對應關係，如 docs/ <-> project://docs/>` |
| **5. 雙端溝通媒介與交接協議 (Cross-Agent Handoff & Inbox)** | `<TODO: 定義外部雲端 Agent 與本地開發 Agent 的訊息/調研報告交換路徑與命名規範，如頂層 _inbox/YYYYMMDD_topic.md 或 CLI get/put 流程>` |
| **6. 外部 Agent 角色定位與讀寫權限邊界 (Role & Write Scope)** | `<TODO: 明確定義本 Agent 角色，例如：唯讀審查 / 僅寫入區域 A 純雲端區與 _inbox/ / 允許依 CoW 規範更新 repo/main/docs/>` |
| **7. 外部環境能力自檢結果 (Environment Capability Flags)** | `<TODO: 記錄執行環境、是否具備 Linux 虛擬運行機、是否支援並行子任務、以及雲端檔案讀寫/搬移方式>` |

---

## 1. 雲端根目錄雙層拓撲 (`<root_folder_id>/`)

本 Google Drive 資料夾分為兩個嚴格隔離的區域（受控同步倉子目錄由 `repo_sync.repo_sync_root` 設定，預設為 `repo/`）：

```text
<root_folder_id>/
├── README.md                      # 頂層雲端空間說明（含 YSCB 託管區塊，請勿刪除手寫段落）
├── _inbox/ (或約定之溝通目錄)       # 【雙端溝通交換區】供外部雲端 Agent 與本地 Agent 交換調研報告、問題單與交接快照
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

## 2. 雙端協作與溝通媒介規範 (Cross-Agent Communication Protocol)

當外部雲端 Agent 與本地端開發 Agent（使用 `python yscb.py gdrive`）協同作業時，應遵循以下溝通契約：
1. **非侵入式非同步交接（推薦預設）**：
   - 外部雲端 Agent 產出之調研報告、審查意見、大型資料整理或待辦提案，優先存放於 **「區域 A：純雲端自由儲存區」**（例如 `<root_folder_id>/_inbox/` 或專案約定之交換資料夾），並在回應使用者時提供**精確的雲端相對路徑**（如 `_inbox/20261104_audit_report.md`）。
   - 使用者或本地 Agent 只需在本地執行單行指令：
     ```bash
     python yscb.py gdrive get _inbox/20261104_audit_report.md ./local_path.md
     ```
     即可按需拉取，完全避免雙端同時修改同一份受控同步檔造成三方衝突 (`CONFLICT`)。
2. **直接修改受控同步倉 (`<repo_sync_root>/<branch>/`) 時的「前置分支詢問守門」與同步守則**：
   - **🚨 寫入前強制詢問（`main` vs. 新建 `<branch_name>`）**：每次任務準備對 `<repo_sync_root>/` 受控同步倉寫入修改前，外部 Agent **必須先向使用者確認本次任務的目標分支策略**：
     - **選項 A — 直接修改 `main/`（或當前指定分支）**：適用於已確認可直接合入主幹之文檔或同步變更；完成後提醒使用者於本地執行 `python yscb.py gdrive pull`（或 `sync`）。
     - **選項 B — 建立新雲端分支 `<repo_sync_root>/<new_branch>/` 隔離修改**：適用於實驗性方案、大型重構草案或待審查修改。你可以請使用者在本地執行 `python yscb.py gdrive branch create <new_branch>` 建立零空間捷徑分支，或直接在雲端建立 `<repo_sync_root>/<new_branch>/` 目錄寫入變更（本地 `yscb gdrive` 具備**雲端未註冊分支自動發現機制**，無須手動修改 `.yscb_gdrive.json` 即可由本地透過 `python yscb.py gdrive branch list` 與 `checkout <new_branch>` 自動識別並拉取！）。
   - 完成修改後**必須主動提醒使用者**：於本地開始下一輪修改前先執行 `python yscb.py gdrive pull`（或 `checkout <new_branch>`），確保本地基線 (`sync_state.json`) 對齊最新雲端狀態。

---

## 3. 外部 AI Agent 操作三大鐵律

### 鐵律 ①：操作「區域 A：純雲端自由儲存區（`<repo_sync_root>/` 以外）」
- 在 `<root_folder_id>/` 下除了 `<repo_sync_root>/`（預設 `repo/`）以外的所有目錄，皆屬於**不拉到本地同步之純雲端空間**。
- 外部 Agent 可在此區域自由新增、讀取或整理參考文件、大型素材、雙端交接筆記與備份資料。
- 修改頂層 `README.md` 時，**嚴禁刪除或破壞 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->` 至 `<!-- === YSCB GDRIVE REPO_SYNC END === -->` 之間的託管區塊**。

### 鐵律 ②：操作「區域 B：`<repo_sync_root>/`（預設 `repo/`）受控同步倉」
1. **寫入前先確認目標分支（直接改 `main` vs. 新增雲端分支 `<new_branch>`）**：
   - 未獲使用者當次明確指定前，**嚴禁預設直接覆寫 `main/`**；務必先詢問使用者本次要「直接改 `main/`（或既有分支）」還是「建立新雲端分支 `<repo_sync_root>/<new_branch>/`」。
2. **保持原檔案類型（嚴禁轉檔）**：
   - 所有在 `<repo_sync_root>/main/` 或分支內建立/更新的檔案，**100% 必須保持原始檔案格式**（如 `.md`, `.json`, `.py`, `.png`, `.pdf`, `.xlsx`），**嚴禁**將檔案轉換為 Google Docs / Sheets / Slides 原生線上文件格式。
3. **無原生覆寫或無原生垃圾桶權限時的「先移入 `<repo_sync_root>/.trash/` 再重建」協議**：
   - 當你在外部雲端環境無法原地覆寫同一個 `file_id`（只能建立同名新檔）或無權限呼叫 Google Drive 原生垃圾桶時，**必須先將舊檔案（或舊 Shortcut）移動至 `<repo_sync_root>/.trash/`，再於原路徑建立新檔案**，防止同一目錄下產生同名重複檔案。
   - **[!CAUTION] 嚴禁將 `<repo_sync_root>/.trash/` 當作備份或留存區**：本地端 `yscb gdrive` 在執行同步或分支管理時，**會自動清空 `<repo_sync_root>/.trash/` 內的所有項目並將其轉移至 Google Drive 原生 30 天垃圾桶 (`trashed=true`)**。任何放入 `.trash/` 的檔案都代表「確認丟棄」，請勿以為放在 `.trash/` 內以後還能直接從該資料夾取回！
4. **保護歷史分支凍結完整性**：
   - 若要修改某個非 `main` 分支（如 `v1.0/`）內的 Google Drive Shortcut 檔案，請先移除該分支下的 Shortcut（移入 `<repo_sync_root>/.trash/`），再於該分支路徑建立新的實體檔案（**切勿直接透過 Shortcut 去修改它指向的 `.history/` 或 `main/` 目標實體檔**，否則會污染其他已凍結的版本分支）。

### 鐵律 ③：絕對禁區
- **嚴禁**手動編輯或刪除 `<repo_sync_root>/.yscb_gdrive.json`。
- **嚴禁**手動修改、搬移或刪除 `<repo_sync_root>/.history/` 內的任何檔案（該目錄由 `yscb gdrive` 引用計數器自動管理，當無任何分支引用時會自動移入 Google Drive 原生 30 天垃圾桶）。
