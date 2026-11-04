# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:gdrive-support` 原子雲端操作、Shortcut 差量分支與雙向同步模組 (`gdrive_bidirectional_sync_module`)  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Umbrella  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 建立官方選配模組 `module:gdrive-support`（對齊 `vscode-support` 外部生態整合命名慣例，並於 `contributes/core.json` 宣告 `"module_alias": ["gdrive"]`），提供純淨的 Google Drive 原子上傳/下載 API 與 CLI 工具，並支援選配之工作區雙向同步與雲端 Shortcut 差量分支系統。
  - 先以 `/code-optimizer`（`CodeQualityStandards.md` 五維度 `D1~D5` 與六大無損重構法則 `S1~S6`）對照兄弟專案 `brood-keeper` 之 `rclone-tool` 原型，釐清應拆分為哪些正交核心部件；再從真實使用面（User Scenarios）反推檢驗基底設計，確立原子操作 API、背景自動更新預設關閉（`auto_sync: false`）、`file-space` 空間與選填 `mapping` 映射、直接保持原檔案類型同步（不做 Google Workspace 原生線上文件特化匯出轉檔）、以及雲端 `<root_folder_id>`（`.yscb_gdrive.json`、`README.md`、`.history/` 引用計數回收、`.trash/`、`main/` 主幹與 Google Drive Shortcut 差量分支系統），並將所有設計細節與考量提純落檔為 `R01`。
- **核心目標**：
  1. **模組定名 `module:gdrive-support`（短別名 `gdrive`）與五大正交核心部件切分（遵循 `CodeQualityStandards.md` CCP/SRP 與單向 DAG）**：拆分為 `gdrive_support/config.py`（組態與空間映射）、`gdrive_support/reconciler.py`（100% 無狀態三方對帳純函式演算法）、`gdrive_support/transport.py`（原生 Google Drive REST API v3 原子操作 Transport 與本地 Sandbox Transport 雙模驅動）、`gdrive_support/coordinator.py`（跨進程鎖、狀態帳本與指紋快取 I/O、增量落盤、原子檔案操作、`.history/` 引用計數回收與 4 階段同步管線）及 `gdrive_support/service.py`（受 `auto_sync: false` 開關控制之選配背景常駐 Worker）。
  2. **原子 API / CLI 優先，背景自動同步預設關閉 (`auto_sync: false`)**：將底層上傳（`upload_file` / `put`）、下載（`download_file` / `get`）、列舉（`list_files` / `ls`）、安全移入垃圾桶（`trash_file` / `rm`）、建目錄（`mkdir`）、建捷徑（`shortcut`）設計為獨立可調用之原子 SDK 與 CLI 指令，無須啟動背景服務即可作為純粹的手動 Google Drive 傳輸工具；背景自動同步由 `config://gdrive-support/` 之 `auto_sync` 控制且**預設為 `false`（關閉）**。
  3. **100% 復用 `file-space` 空間幾何與選填 `mapping` 路徑重映射（零 `.gitignore` 耦合）**：`.gitignore` 完全由專案自身於 `core.gitignore` 管理，`module:gdrive-support` 不介入 `.gitignore`；批次同步範圍僅接受已註冊之 `file-space` 名稱，並支援選填 `mapping: [{local, remote}]`（強制驗證 `mapping.local` 必須位於該 `space` 的 `include` 範圍內；未填時預設以相對於 `project://` 之 1:1 路徑映射）。
  4. **雲端 `<root_folder_id>` 標準結構與 Shortcut 差量分支系統（含 `.history/` 無引用自動回收至 `.trash/`）**：強制要求使用者先在雲端建立資料夾並提供 `root_folder_id`；根目錄強制維護 `.yscb_gdrive.json`（倉庫身分證與分支註冊表）、`README.md`（標註由 `yscb module:gdrive-support` 自動管理及對網頁版 Gemini / 人類之操作規範）、`.history/`（存放被覆寫替換但仍受舊分支 Shortcut 引用之歷史實體檔，且當 `.history/` 內檔案無任何分支引用時自動移入 `.trash/`）、`.trash/`（存放待刪除垃圾與 Gemini 更新前移出之舊檔）、`main/`（100% 真實完整主幹）與 `<branch>/`（如 `v1.0`、`v1.5`，採真實資料夾骨架 + 差量真實檔案 + 未修改檔案以 Google Drive Shortcut 指向 `main` 或 `.history`）。
  5. **直接保持原檔案類型 1:1 二進位/文字原樣傳輸（不做 Google Workspace 特化轉檔）**：所有一般檔案（含 `.md`、`.json`、`.py`、`.xlsx`、`.docx`、`.csv`、`.pdf`、`.png` 等）100% 保持原檔案類型與原始位元組 `md5Checksum` / `sha256` 原樣同步；若雲端目錄出現 Google 雲端原生線上文件（`application/vnd.google-apps.*`，排除 `folder` 與 `shortcut`），直接視為不支援之雲端專屬物件並安全略過（`SKIPPED_UNSUPPORTED_MIME`），彻底消除匯出轉檔失真、10MB 匯出上限與雜湊回音問題。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `module:file-space` 之 `FileSpaceManager`（空間包含/排除/Glob 規則、檔案列舉與 `large_file_threshold_mb` 設定）與 `file_space.service.subscribe` / `_unsubscribe` 事件（取代 `brood-keeper/rclone-tool` 中重複自建之 `FilterCompiler` 與獨立 `watchdog` 爬蟲）。
  - 復用 `core.platform.InterProcessLock`（跨進程同步排他鎖）、`core.uri` / `core.vfs`（原子讀寫與路徑解析）與 `server.service.BaseServiceWorker`（常駐背景微服務基類）。
- **邊界排除 (Explicitly Excluded)**：
  - 不負責管理或生成 `.gitignore`（已由 `core.gitignore` 統一收斂，由專案人員自行配置）。
  - 不對 Google Workspace 雲端原生線上文件（`application/vnd.google-apps.document/spreadsheet/presentation/drawing`）做特化匯出轉檔，100% 保持原檔案類型同步。
  - 不支援跨雲端供應商（如 S3 / OneDrive / Dropbox）泛用抽象，100% 聚焦 Google Drive v3 特性（原生 `file_id`、`Shortcut`、`changes.list` 差量游標與 `md5Checksum`）。
  - 不允許自動在使用者 Google Drive 根目錄盲目建資料夾；若指定之 `root_folder_id` 非空且不含 `.yscb_gdrive.json`，未執行 `init` 時強制熔斷阻斷。
- **架構影響範圍**：
  - 新建選配模組 `ys_codebase/source/gdrive-support/`（含 `gdrive_support/{config,reconciler,transport,coordinator,service}.py`、`scripts/cli.py`、`contributes/`、`configurable/` 與 `tests/`）及知識庫文檔 `docs/gdrive-support/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模組定名 `module:gdrive-support`（短別名 `gdrive`）、原子 API 優先與背景自動更新預設關閉 (`auto_sync: false`)**：
  - 對齊 `vscode-support` 命名慣例定名為 `module:gdrive-support`（套件名 `gdrive_support`，源碼目錄 `ys_codebase/source/gdrive-support/`，快取空間 `cache://gdrive-support/`），並於 `contributes/core.json` 宣告 `"module_alias": ["gdrive"]`，使 `yscb gdrive-support <cmd>` 與 `yscb gdrive <cmd>` 均受支援。
  - 將底層基本雲端操作設計為可獨立調用之原子 API 與 CLI（`ls` 列舉、`get` 單檔下載、`put` 單檔上傳/覆寫、`rm` 安全移入 `.trash/`、`mkdir`、`shortcut`），不綁定背景服務即可作為純粹手動調用 Google Drive API 上傳/下載的工具。
  - 背景自動同步（`GDriveSyncServiceWorker`）由組態 `auto_sync: bool = False` 控制，**預設關閉**；當 `auto_sync: false` 時 Worker 處於 `standby` 模式且 `health_check()` 回傳 `True`（避免 `yscb server status` 誤報死機），並在 `stop()` 時確定性呼叫 `_unsubscribe()` 釋放 `file-space` 監聽回呼（遵循 `D4`）。
  - 將 `module:gdrive-support` 切分為 `config.py`、`reconciler.py`（100% 無狀態純函式對帳演算法，零磁碟 I/O 與零系統時間依賴）、`transport.py`、`coordinator.py`（統籌鎖、帳本與指紋快取 I/O、增量落盤與分支編排）、`service.py` 五個正交部件，維持嚴格單向無環依賴（DAG）。
- **[P00:DR-02] 純 `file-space` 綁定、選填 `mapping` 子集校驗與 `.gitignore` 職責剝離**：
  - `module:gdrive-support` 不介入 `.gitignore` 管理；同步標的僅接受 `file-space` 名稱，支援選填 `mapping: [{local, remote}]` 自訂本地與雲端路徑映射（未填時預設相對於 `project://` 1:1 投影；有填時強制驗證 `mapping.local` 必須位於該 `space` 之 `include` 範圍內）。
- **[P00:DR-03] 原生 Google Drive API v3 雙模傳輸與「直接保持原檔案類型」純淨策略**：
  - 直接對接 Google Drive REST API v3（搭配 `LocalSandboxTransport` 離線沙盒），所有一般檔案（文字與二進位檔，含 `.md`, `.xlsx`, `.docx`, `.csv`, `.pdf`, `.png` 等）直接保持原檔案類型與原始位元組傳輸，不做 Google Workspace 雲端原生線上文件特化匯出/轉檔（遇 `application/vnd.google-apps.*` 非目錄/非捷徑物件直接標記 `SKIPPED_UNSUPPORTED_MIME` 略過），徹底確保 `md5Checksum` / `sha256` 100% 精確可逆。
- **[P00:DR-04] 雲端 `<root_folder_id>` 頂層結構、Copy-on-Write (`.history/`) 分支凍結與無引用自動回收至 `.trash/`**：
  - 雲端固定採 `<root_folder_id>/<active_branch>/...` 結構（預設 `active_branch: "main"`）。`main/` 存放完整真實檔案主幹；其他分支（如 `v1.0`、`v1.5`）建立真實資料夾骨架，僅有差異的檔案存為真實檔案，未修改檔案則建立指向 `main`（或 `.history`）的 Google Drive 原生捷徑（`application/vnd.google-apps.shortcut`）。
  - **受引用時 Copy-on-Write 保全分支歷史**：當更新某個實體檔案時，先檢查其 `file_id` 是否被任何其他分支的 Shortcut 引用（`ref_count > 0`）：
    - 若 **`ref_count == 0`**（無其他分支引用）：直接原地 `PATCH` 更新該 `file_id`（最快且保持 `file_id` 不變）。
    - 若 **`ref_count > 0`**（有其他分支引用）：執行 **Copy-on-Write**——將舊實體檔之 `parents` 移入 `.history/`（保持舊 `file_id` 與舊內容不變，使舊分支 Shortcut 永遠凍結在當時版本），並於當前分支目錄 `POST` 建立新實體檔寫入新內容。
  - **`.history/` 無引用自動回收至 `.trash/` (Reference-Counted History GC)**：當分支被刪除、或分支內的 Shortcut 因修改/刪除而被移除，導致 `.history/` 中的某個 `file_id` 不再被任何活躍分支引用（`ref_count == 0`）時，協調器自動將該 `file_id` 從 `.history/` 移入 `.trash/`。
  - 根目錄強制維護 `.yscb_gdrive.json`（防誤綁非空私人目錄熔斷、註冊分支、Shortcut 引用映射與系統目錄 ID）與 `README.md`（向人類與網頁版 Gemini 說明託管規則與 `.trash/` 操作規範）。
- **[P00:DR-05] 背景衝突按檔隔離保留與預設不自動傳播刪除（顯式推翻 `roadmap.md` 早期假設）**：
  - 背景 `sync` 遇到雙邊衝突（`CONFLICT`）時，按檔隔離保留雙邊原狀不覆寫（其餘無衝突檔案照常同步），待人工透過 CLI `--force --backup`（產出 `.conflict.<ts>.bak`）裁決；預設 `pull_delete_default = False`、`push_delete_default = False`。
  - **架構推翻聲明（Superseding `roadmap.md`）**：本計畫正式推翻 `roadmap.md` 早期草案中「自動將空間寫入 `core.gitignore`」（改為 `[P00:DR-02]` 零 `.gitignore` 耦合）與「背景自動 Last-Writer-Wins 覆寫」（改為 `[P00:DR-05]` 背景按檔隔離保留不覆寫）兩項早期假設。
- **[P00:DR-06] 兩批盲審（`/blind-subagent`）確立之八大跨模組與狀態機安全護欄**：
  1. **`file-space` 單根/多根路徑統一正規化與大檔靜置視窗**：匯入 `gdrive_support/config.py` 時統一以 `abs_path.relative_to(project_root)` 正規化為 `project_rel_path`；由 `coordinator.py` 掃描時讀取該 `space` 之 `large_file_threshold_mb` 並結合傳入之 `now_ns` 執行 `< 2.0s` 靜置防抖。
  2. **`reconciler.py` 100% 純函式隔離 (`S2`) 與 `coordinator.py` 增量帳本落盤 (Incremental State Commit)**：`reconciler.py` 零 I/O、零系統時間呼叫；`coordinator.py` 在每完成單檔傳輸後立即更新記憶體帳本並於 `try/finally` 中原子落盤 `sync_state.json`，確保中途斷線重試時零假衝突。
  3. **`InterProcessLock` 實體路徑解析與非阻塞讓路**：先以 `core.uri.resolve("cache://gdrive-support/sync.lock")` 解析實體路徑；背景 Worker 採 `acquire(blocking=False)` 遇鎖立即讓路，CLI 採明確 `timeout` 防死鎖。
  4. **`GDriveSyncServiceWorker` 待機健康檢查與確定性退訂 (`D4`)**：`auto_sync: false` 待機時 `health_check()` 回傳 `True`；`stop()` 顯式呼叫 `_unsubscribe()` 防止 callback 洩漏。
  5. **`transport.list_remote()` Shortcut 目標 Metadata 批次解析**：針對雲端 Shortcut 之 `shortcutDetails.targetId`，批次補齊目標實體檔之 `(md5Checksum, size, modifiedTime)` 供三方對帳比對。
  6. **受引用檔案 Copy-on-Write 與 `.history/` $\to$ `.trash/` 引用計數自動回收**：更新 `ref_count > 0` 之檔案時移入 `.history/` 並新建 `file_id`；當 `.history/` 檔案之 `ref_count` 歸零時自動移入 `.trash/`。
  7. **`checkout <branch>` 原子工作樹對齊與舊分支孤兒清理**：切換分支前強制確認本地乾淨；切換時除拉取目標分支差異檔外，同步清理「舊分支存在但目標分支不存在」之本地受管檔案並逐檔增量更新帳本。
  8. **`changes.list` 遠端異動探針涵蓋新建檔案與 Shortcut 目標**：探針同時檢查 `change.fileId in tracked_file_and_target_ids` 或 `any(p in tracked_folder_ids for p in change.file.parents)`，確保雲端新建檔案、新建子資料夾與 Shortcut 目標異動零漏檢。

---

## 3. 開放議題與確認紀錄

- 所有前置設計細節與兩批盲審（`/blind-subagent`）補強項目均已確認完畢，提純彙整至 [R01_gdrive_architecture_and_design.md](./R01_gdrive_architecture_and_design.md)。
