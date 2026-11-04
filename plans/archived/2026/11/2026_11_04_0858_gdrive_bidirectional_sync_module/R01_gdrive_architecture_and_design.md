# 專題調研與分析報告：`module:gdrive-support` 原子雲端操作、Shortcut 差量分支與雙向同步架構提純報告 (R01_gdrive_architecture_and_design.md)

> 調研主題：`module:gdrive-support` 核心部件切分、原子 API / 手動工具設計、使用情境反推與雲端 Shortcut 差量分支架構  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  1. **三大核心訴求**：
     - **訴求 A（純粹手動調用之原子 Google Drive API 上傳/下載工具）**：提供不依賴背景常駐服務、可單獨透過 Python SDK 或 CLI (`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`) 呼叫的原子雲端檔案操作，且**背景自動同步預設關閉 (`auto_sync: false`)**，避免非預期之背景流量或自動覆寫。
     - **訴求 B（大型非 Git 資產同步與版本儲備）**：專案中的大型測試資料集、模型權重、多媒體與美術資產不適合納入 Git 版本控制，需透過 Google Drive 維持工作區目錄結構同步並支援里程碑版本切換（如 `main`、`v1.0`、`v1.5`）。
     - **訴求 C（本地工作區 ↔ Google Drive ↔ 網頁版 Gemini 無縫雙向協作）**：將指定檔案空間以 **1:1 可讀原始目錄與原檔案類型** 投影至 Google Drive，使網頁版 Gemini 可直接閱讀最新專案脈絡，並將 Gemini 在雲端新建/替換之檔案拉回本地工作區。
  2. **命名對齊與既有原型 (`brood-keeper/rclone-tool`) 的架構局限**：
     - **模組命名對齊 (`module:gdrive-support`，短別名 `gdrive`)**：對齊母倉 `vscode-support` 外部平台整合模組命名慣例，將模組正式定名為 `gdrive-support`（Python package `gdrive_support`，源碼目錄 `ys_codebase/source/gdrive-support/`），並於 `contributes/core.json` 宣告 `"module_alias": ["gdrive"]` 支援 `yscb gdrive <cmd>` 簡短呼叫。
     - **既有原型問題**：兄弟專案 `brood-keeper` 之 `rclone-tool` ① 未復用母倉 `module:file-space`，重複自建 `FilterCompiler` 與獨立 `watchdog.Observer`；② 強依賴外部 `rclone` CLI，缺乏細粒度原子 API 與原生 Shortcut 控制；③ 缺乏雲端多分支（`main` / `v1.0` / `v1.5`）Shortcut 差量切換、`.history/` 引用計數保護與網頁版 Gemini 操作防呆。
- **調研目標與範疇**：
  1. 依據 [`CodeQualityStandards.md`](../../.agents/.yscb/standards/CodeQualityStandards.md)（`D1~D5` 品質指標與 `S1~S6` 重構法則）完成 `module:gdrive-support` 核心部件的正交切分與原子 API 分層。
  2. 從真實使用情境（原子單檔 `ls/get/put/rm`、Onboarding 空間映射、日常原檔案類型雙向協作、冷啟動對帳、背景衝突隔離與 `auto_sync: false` 預設關閉、雲端分支切換與 `.history`/`.trash` 引用計數回收）反推並確立所有資料結構與安全護欄。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 基於 `CodeQualityStandards.md` (`D1~D5` / `S1~S6`) 之五大正交核心部件切分

對照 `brood-keeper/rclone-tool` 並消除與母倉 `module:file-space` 的功能重疊後，`module:gdrive-support` 依 **共同封閉原則（CCP / `S6`）** 與 **有狀態/無狀態分離（`S2`）** 切分為 **5 個正交核心部件**（外加 CLI 薄路由 `scripts/cli.py`）：

```text
scripts/cli.py ──┐
                 ├──► coordinator.py ──► transport.py ──► reconciler.py ──► config.py
service.py ──────┘
(嚴格單向無環依賴 DAG：reconciler.py 僅依賴 config.py，100% 純函式無 I/O，嚴禁反向匯入 transport.py)
```

| 部件路徑 | 正交變更軸線 (CCP / SRP) | 狀態屬性 (`S2`/`S5`) | 核心職責與設計不變量 |
| :--- | :--- | :---: | :--- |
| **1. `gdrive_support/config.py`** | 組態契約與 `file-space` / `mapping` 路徑雙向映射 | 具名 `@dataclass` (`S5`) + 映射驗證函式 | • 解析 `config://gdrive-support/`（`root_folder_id`, `active_branch="main"`, **`auto_sync=False` (預設關閉)**, `poll_interval_sec=30.0`, `pull_delete_default=False`, `push_delete_default=False`, 憑證設定）與 `contributes` 之 `sync_spaces`。<br/>• **零 `.gitignore` 耦合**：`.gitignore` 完全由專案自身配置，不由 `gdrive-support` 介入（顯式推翻 `roadmap.md` 早期假設）。<br/>• **`file-space` 單根/多根座標統一正規化與 `mapping` 子集驗證**：因 `FileSpaceManager` 在單根空間下回傳相對於 `inc_root` 之 `rel_path`，`config.py` 強制統一以 `abs_path.relative_to(project_root)` 正規化為 `project_rel_path`；若設定 `mapping: [{local, remote}]`，強制驗證每個 `mapping.local` 必須位於該 `space` 的 `include` 範圍內（越界立即拋出配置錯誤），並提供 `local_rel <-> remote_rel` 最長前綴雙向可逆轉換。 |
| **2. `gdrive_support/reconciler.py`** | 三方對帳演算法與 `.history/` 引用計數計算 | **100% 無狀態純函式 (`S2`)** + 不可變 `@dataclass` (`FileEntry`, `SyncAction`) | • **嚴格純函式與單向依賴**：僅依賴標準庫與 `config.py`，**零磁碟 I/O、零網路 I/O、零系統時間 (`time.time_ns()`) 呼叫**，嚴禁匯入 `transport.py`。<br/>• 接收由 `coordinator.py` 傳入之記憶體快照 `(local_snapshot, remote_snapshot, baseline_state)`，以原檔案類型原始位元組雜湊（`md5` / `sha256`）執行三方比對（含解析後之 Shortcut 目標摘要），純粹計算並輸出 8 態 `list[SyncAction]`。<br/>• 提供純函式計算雲端跨分支 Shortcut 引用計數（`compute_history_ref_counts`），判定被替換之舊 `file_id` 應執行原地 `PATCH`（`ref_count == 0`）或 Copy-on-Write 移入 `.history/`（`ref_count > 0`），並篩選出 `.history/` 中 `ref_count == 0` 應回收至 `.trash/` 之孤兒 `file_id` 清單。 |
| **3. `gdrive_support/transport.py`** | 原子雲端 API 操作、遠端傳輸協議與分支 Shortcut 驅動 | 抽象介面 `AbstractSyncTransport` + 雙模實作 | • **原子操作 API 基座**：提供不依賴三方對帳即可獨立呼叫之原子方法：`list_files(remote_path)`、`upload_file(local_path, remote_path, in_place_file_id=None)`、`download_file(remote_path, local_path)`、`trash_file(remote_path)`、`move_file(file_id, old_parent_id, new_parent_id)`、`mkdir(remote_path)`、`create_shortcut(target_id, remote_path)`。<br/>• **直接保持原檔案類型**：100% 原樣傳輸一般二進位/文字檔案，不做 Google Workspace 雲端原生線上文件特化匯出轉檔（若雲端遇 `application/vnd.google-apps.*` 且非 `folder`/`shortcut` 則標記 `SKIPPED_UNSUPPORTED_MIME` 略過）。<br/>• **Shortcut 目標 Metadata 批次解析**：`list_remote()` 遇 `application/vnd.google-apps.shortcut` 時，收集 `shortcutDetails.targetId` 並批次補齊目標實體檔之 `(md5Checksum, size, modifiedTime)`。<br/>• **`GoogleDriveApiTransport` & `LocalSandboxTransport`**：純標準庫 `urllib.request` 直連 Google Drive REST API v3（支援 OAuth2 Desktop Loopback、Service Account、Resumable 上傳、429 退避、涵蓋 `parents in tracked_folder_ids` 與 `shortcut_target_ids` 之 `changes.list` 探針），搭配本地檔案系統 100% 擬真之 `LocalSandboxTransport` 供離線測試。 |
| **4. `gdrive_support/coordinator.py`** | 跨進程鎖保護下之原子 CLI 委派、狀態帳本 I/O、增量落盤與分支編排 (`S1`) | 交易編排器 `SyncCoordinator` | • 先以 `core.uri.resolve("cache://gdrive-support/sync.lock")` 解析實體鎖路徑，持 `InterProcessLock`（CLI 具明確 `timeout`，背景 Worker 採 `blocking=False` 主動讓路）執行：<br/>  - **手動原子操作**：`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`。<br/>  - **本地掃描與快取持久化**：管理 `cache://gdrive-support/sync_state.json`（按 `branches[active_branch]` 分桶）與 `FingerprintCache` `(mtime_ns, size) -> (sha256, md5)`；結合該 `space` 之 `large_file_threshold_mb` 與當前 `now_ns` 過濾 `< 2.0s` 未穩定寫入之大檔。<br/>  - **批次三方同步 4 階段管線與增量落盤 (Incremental State Commit)**：① 收集三方快照 $\rightarrow$ ② 呼叫 `reconciler` 產出計畫（`sync` 遇 `CONFLICT` **按檔隔離保留不覆寫**並回傳 Exit Code 2）$\rightarrow$ ③ 執行單檔傳輸（依 `ref_count` 決定原地 `PATCH` 或 CoW 移入 `.history/`）、**每完成一檔即更新記憶體帳本並於 `try/finally` 原子落盤 `sync_state.json`**（防中斷重試假衝突）、執行 `.history/` 無引用檔案移入 `.trash/` GC $\rightarrow$ ④ 寫入 2MB 輪替之 `cache://gdrive-support/sync.log`。<br/>  - **分支管理**：`init`, `branch list/create/delete`, `checkout`（含舊分支獨有本地受管檔清理）。 |
| **5. `gdrive_support/service.py`** | 選配常駐背景事件防抖與定時差量輪詢 | 常駐狀態機 `GDriveSyncServiceWorker` | • **受 `auto_sync` 開關嚴格守門（預設 `auto_sync: false`）**：當 `config.auto_sync == False` 時，Worker 處於 `standby_mode = True`，不註冊檔案監聽亦不發起背景輪詢，且 `health_check()` 回傳 `True`（狀態標記 `mode: "standby"`，避免 `yscb server status` 誤判服務異常）。<br/>• 當顯式啟用 `auto_sync: true` 時，透過 `file_space.service.subscribe` 註冊監聽並保存 `_unsubscribe` 閉包，於 `stop()` 時確定性呼叫 `_unsubscribe()` 釋放資源（遵循 `D4`）。 |

---

### 2.2 使用情境反推與關鍵機制設計提純

#### ① 空間映射契約：`file-space` 綁定 + 選填 `mapping`（`contributes/_format.json`）
- **設計考量**：
  - 90% 常規情境下，使用者只需指定 `{"space": "docs"}`，系統即自動取該 `space` 內匹配之檔案，透過 `abs_path.relative_to(project_root)` 正規化為相對於 `project://` 的路徑（如 `docs/README.md`），1:1 映射至雲端 `<root_folder_id>/<active_branch>/docs/README.md`。
  - 當 `space` 包含深層目錄（如 `ys_codebase/source/core`）或使用者想自訂雲端資料夾階層時，可選填 `mapping` 清單：
    ```json
    {
      "sync_spaces": [
        {
          "space": "docs"
        },
        {
          "space": "source",
          "mapping": [
            { "local": "module.source://core", "remote": "code/core" },
            { "local": "module.source://dev", "remote": "code/dev" }
          ]
        }
      ]
    }
    ```
  - **剛性安全不變量**：若有填寫 `mapping`，每個 `mapping.local` 解析後的實體路徑 **必須是該 `space` 的 `include` 根路徑之子集（或相等）**；嚴禁透過 `mapping` 偷渡不屬於該 `space` 管轄的外部目錄。所有檔案過濾（`exclude`、`file_patterns`）與 `large_file_threshold_mb` 設定 100% 繼承自該 `file-space`。

#### ② 直接保持原檔案類型（零 Google Workspace 特化轉檔，100% 位元組精確同步）
- **設計考量**：
  - **100% 原檔案類型保留**：不論是程式碼、Markdown (`.md`)、Office 文件 (`.xlsx`, `.docx`, `.pptx`)、資料表 (`.csv`, `.json`)、PDF 或多媒體資產，在本地與 Google Drive 之間皆**直接以原檔案類型與原始二進位位元組 1:1 傳輸**，不做任何 Google Workspace (`application/vnd.google-apps.*`) 特化匯出或格式轉換。
  - **消除匯出失真與假衝突**：由於完全保持原檔案類型，每個雲端實體檔案皆具備 Google Drive 原生計算之 `md5Checksum` 與精確 `size`，與本地檔案之 `(md5, sha256, size)` 100% 對等可比，徹底免除 Google Docs `files.export` 10MB 硬上限、多分頁 `.csv` 截斷遺失以及匯出雜湊不一致導致的假衝突回音。
  - **雲端原生線上文件防呆略過**：若使用者在雲端資料夾內手動建立了 Google 雲端原生線上文件（`mimeType` 為 `application/vnd.google-apps.*` 且非 `folder` 與 `shortcut`），`transport.list_remote()` 直接將其標記為 `SKIPPED_UNSUPPORTED_MIME` 安全略過並記錄提示，絕不干擾受管實體檔案之同步。

#### ③ 雲端 `<root_folder_id>` 頂層架構：`.yscb_gdrive.json`、`README.md`、`.history/`（含無引用自動回收）、`.trash/` 與 Shortcut 差量分支系統
- **為什麼需要分支系統與 Shortcut 差量架構？**
  - 網頁版 Gemini 無法對既有雲端檔案直接上傳新 Revision，只能「先將舊檔移至待刪除區，再新建檔案」；此外，大型資產空間（如數百 MB 的資源包）若在每個版本分支（`v1.0`、`v1.5`）都複製一份完整實體檔案，將造成嚴重的雲端配額浪費與同步延遲；但若分支資料夾只放差量檔，網頁版 Gemini 瀏覽該分支時又會看不見未修改的檔案。
- **雲端頂層標準目錄樹**：
  ```text
  <Google Drive: root_folder_id>/
    ├── README.md             <-- [自動生成] 標註本資料夾由 yscb module:gdrive-support 自動管理，並詳列人類與網頁版 Gemini 操作規範
    ├── .yscb_gdrive.json     <-- [強制組態] 倉庫身分證、預設分支、系統目錄 ID (.history / .trash)、分支註冊表與歷史引用索引
    ├── .history/             <-- [歷史版本池] 存放被更新替換下來、但仍受其他分支 Shortcut 引用之舊版實體檔（無引用時自動移入 .trash/）
    ├── .trash/               <-- [待刪除垃圾桶] 存放被刪除檔案、無引用之歷史檔、同名重複舊檔、以及網頁版 Gemini 更新前移出之待刪舊檔
    ├── main/                 <-- [預設主幹] 100% 真實資料夾 + 100% 最新完整真實檔案
    └── <branch>/             <-- [差量分支] 如 v1.0, v1.5：100% 真實資料夾骨架 + 差量真實檔 + 未修改檔案之 Google Drive Shortcut
  ```
- **六大核心運作法則**：
  1. **根目錄綁定防呆與 `.yscb_gdrive.json` 強制校驗**：
     - 使用者必須手動於 Google Drive 建立專屬資料夾並將 `root_folder_id` 填入組態。
     - 若雲端 `<root_folder_id>` 為空，首次初始化自動建立 `.yscb_gdrive.json`、`README.md`、`.history/`、`.trash/` 與 `main/`。
     - 若雲端 `<root_folder_id>` **非空但缺少 `.yscb_gdrive.json`**，預設立即熔斷拒絕同步（防止填錯 ID 覆寫私人雲端資料夾），必須顯式執行 `yscb gdrive init` 方可納管。
  2. **分支建立（真實目錄骨架 + 檔案級 Shortcut）**：
     - 為防止在雲端往「資料夾捷徑」裡新增檔案時誤寫入 `main/`，所有分支（如 `v1.0`、`v1.5`）的**資料夾層級一律建立真實資料夾**；而未修改的檔案則建立指向 `main`（或當前來源分支）對應實體檔案 `file_id` 的 **Google Drive Shortcut (`application/vnd.google-apps.shortcut`)**（占用 0 Bytes 且提供 100% 完整目錄視野），並將各分支引用之 `target_file_id` 記錄於 `.yscb_gdrive.json`。
  3. **更新時之 In-Place `PATCH` vs. Copy-on-Write (`.history/`) 分流**：
     - 當在 `main/`（或任何分支）更新某個既有實體檔案 `old_file_id` 時，先查詢 `.yscb_gdrive.json` 中是否有**其他分支的 Shortcut 正在引用 `old_file_id`**（`ref_count > 0`）：
       - **無其他分支引用 (`ref_count == 0`)**：直接對 `old_file_id` 執行原地 `PATCH /upload/drive/v3/files/{fileId}` 更新內容，保持 `file_id` 不變且不產生歷史檔。
       - **有其他分支引用 (`ref_count > 0`)**：為防止原地 `PATCH` 竄改舊分支（如 `v1.0`）Shortcut 所指向的凍結內容，強制執行 **Copy-on-Write**——先將 `old_file_id` 的 `parents` 移至 `.history/`（保留 `old_file_id` 與舊版內容供 `v1.0` Shortcut 繼續讀取），再於當前分支目錄 `POST` 建立新實體檔寫入新內容。
     - 當在非 `main` 分支（如 `v1.5`）修改某個目前本身為 Shortcut 的項目時，直接將該 Shortcut 移入 `.trash/`，並在 `v1.5` 原路徑 `POST` 上傳新實體檔案。
  4. **`.history/` 無引用自動回收至 `.trash/`（Reference-Counted History GC）**：
     - `.history/` 僅作為「仍被至少一個活躍分支 Shortcut 引用」之舊版實體檔保護池。
     - 每當發生① 分支刪除（`branch delete`）、② 分支內某個 Shortcut 因覆寫或刪除而被移除、或③ 執行 `sync` / `push` 收尾時，`reconciler.compute_history_ref_counts()` 自動比對 `.history/` 內現存 `file_id` 與所有活躍分支仍存活之 Shortcut `target_file_id` 集合；凡是 **`ref_count == 0`（已無任何分支引用）** 的 `.history/` 檔案，立即由 `coordinator` 自動將其從 `.history/` 移入 **`.trash/`**。
  5. **`checkout <branch>` 原子工作樹切換與舊分支孤兒清理**：
     - 執行 `yscb gdrive checkout <target_branch>` 時：① 先對當前 `active_branch` 執行本地狀態檢查，若存在未同步之本地修改（`ADDED_LOCAL` / `MODIFIED_LOCAL`）且未帶 `--force`，立即阻斷並提示先同步或加 `--force --backup`；② 確認乾淨後，比對當前分支與 `<target_branch>` 之雲端快照：拉取目標分支新增/差異檔案至本地、**刪除舊分支獨有但目標分支不存在之本地受管檔案**，並逐檔增量更新 `branches[target_branch]` 基準線帳本與切換 `active_branch`。
  6. **網頁版 Gemini 同名新檔與 `.trash/` 防呆對接**：
     - `<root_folder_id>/README.md` 明確記載給網頁版 Gemini 的操作指示（更新檔案時將原檔/原捷徑移至 `.trash/` 後再建立新檔）。
     - 若 Gemini 在同一個雲端資料夾內直接新建了同名檔案（導致同路徑並存多個同名 `file_id`），`transport.py` 掃描時自動選取 `modifiedTime` 最新的檔案作為有效版本，並依引用計數將較舊的重複同名檔移入 `.history/`（若 `ref_count > 0`）或 `.trash/`（若 `ref_count == 0`）。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. 採用 **5 大正交部件（`config` / `reconciler` / `transport` / `coordinator` / `service`）** 切分 `module:gdrive-support`（短別名 `gdrive`），`reconciler.py` 維持 100% 無狀態純函式（零 I/O），100% 復用 `module:file-space` 的空間幾何與事件訂閱，且與 `core.gitignore` 完全解耦。
  2. 採用 **直接保持原檔案類型 1:1 傳輸策略**（不做 Google Workspace 特化轉檔）與 **原子 API / CLI 優先 + `auto_sync: false` 預設關閉**，使模組既能作為純粹輕量的手動 Google Drive 上傳/下載工具，又能在開啟同步時保證 100% 精確的 `md5`/`sha256` 對帳與增量帳本落盤（Incremental State Commit）。
  3. 採用 **`<root_folder_id>` 標準頂層結構（`.yscb_gdrive.json` + `README.md` + `.history/` 引用計數保護與無引用自動移入 `.trash/` + `main/` 主幹 + Shortcut 差量分支）**，完美解決網頁版 Gemini 無法原地更新檔案版本、需要完整目錄視野、分支歷史凍結以及大型資產跨版本零重複空間占用的核心痛點。
- **後續建議**：
  - 建議採納 **出口 ①（立即原地升級實作）**，將本計畫由 `Research` 升級為 `Feature` 開發計畫（Full Track 或 Umbrella 分階段實作），正式建造 `ys_codebase/source/gdrive-support/`。
