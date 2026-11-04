# 技術路線圖：`module:gdrive` 雙向雲端同步模組與 Google Drive 協作橋接架構 (Roadmap)

> 主題：`module:gdrive` 雙向雲端同步模組與 Google Drive 協作橋接架構 (`gdrive_bidirectional_sync_module`)  
> 歸檔日期：2026-11-04  
> 狀態：Proposed  
> 目標範疇：新模組 `module:gdrive`、`core.gitignore`（忽略規則收斂）、`file-space`（空間定義與 `lazy_stabilized` 穩定度檢查）、`server`（常駐雙向同步 Worker）  
> 前置解鎖條件：完成 `core.gitignore` 統一忽略規則收斂基座後即可隨時啟動  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **大型非程式碼資產不宜進入 Git 版本控制**：大型測試資料集、模型權重、多媒體資產與封存包不適合直接納入 Git 追蹤，但仍需在專案工作區內維持標準目錄結構並跨環境同步。
  - **本地開發環境與網頁版 Gemini 缺乏無縫雙向檔案橋接**：網頁版 Gemini 原生整合 Google Drive 檢索與文檔產出能力，若能將指定專案空間以 1:1 原始可讀目錄與檔名雙向熱同步至 Google Drive，即可讓網頁版 Gemini 直接閱讀最新專案脈絡，並將其產出之測試腳本、分析報告或文件自動拉回本地工作區驗證。
- **長期願景與目標定位**：
  - 建立官方選配模組 `module:gdrive`，專注於「不入 Git 之大型資料卸載」與「本地工作區 ↔ Google Drive ↔ 網頁版 Gemini 背景雙向熱同步」兩大核心訴求，透過 1:1 可讀目錄樹投影與本地三方狀態帳本實現低延遲、防回音、零資料遺失之協作閉環。
- **範疇與邊界約束**：
  - **不追求跨雲端後端泛用化或取代 Git 分支歷史**：明確捨棄多雲端供應商抽象與跨 Git 分支切換歷史版本之複雜度，100% 聚焦 Google Drive 生態系整合。
  - **捨棄 CAS 雜湊改名，維持雲端 100% 原始可讀路徑**：雲端目錄與檔名保持原貌，確保人類與網頁版 Gemini 可直接檢索、閱讀、新增與編輯。
  - **本機同步狀態帳本嚴格隔離於版控之外**：三方基準線狀態（含本機時間戳與雲端游標）儲存於 `cache://gdrive/`（Git 忽略），雲端目錄綁定設定則存放於 `config://gdrive/`，不污染 Git 工作樹。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **雙向防回音死循環（Bidirectional Echo Immunity）**：無論是「雲端下載落盤（Remote Pull）」或「本地上傳完成（Local Push）」，皆必須在 I/O 與 API 回應當下原子更新三方狀態帳本（`(rel_path, local_mtime_ns, local_hash, drive_file_id, drive_md5_or_version, drive_modified_time)`）；後續本地監聽事件或遠端變更輪詢比對帳本一致時，強制判定為同步回音並靜默跳過。
  - **大檔寫入穩定度防抖（Write Stabilization Gate）**：本地大型檔案必須通過 `file-space` 之 `lazy_stabilized` 連續週期靜置與無排他鎖檢核後，方允許排入背景上傳佇列，嚴禁上傳寫入中之半成品。
  - **無阻塞衝突裁決與非污染伴隨備份（Non-Blocking Conflict Sidecar）**：當本地與雲端於同一同步視窗內修改同一檔案（雙邊皆偏離基準線）時，採無阻塞 Last-Writer-Wins 保留較新版本為主檔，並將另一方存為副檔名後置或隔離目錄之衝突備份檔（如 `<filename>.<ext>.gdrive-conflict-<timestamp>`），防止觸發 AST 重複符號解析或測試框架誤收錄。
  - **受控回呼沙盒邊界（Sandboxed Post-Sync Callback）**：背景 `post_pull` 自動觸發預設僅限於檔案落盤、推進 `file-space` / `ast` / `knowledge-db` 增量索引或於隔離沙盒內執行驗證，嚴禁無限制自動執行任意宿主破壞性 Shell 指令。
  - **離線與未授權優雅降級（Graceful Degradation）**：缺少雲端憑證或網路中斷時，背景服務自動轉為靜默待機並保留本地待同步狀態，僅於 `status` 診斷時呈現，絕不阻斷本地日常 CLI 操作。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **`file-space` 空間綁定與 `core.gitignore` 宣告連動**：復用 `file-space` 空間幾何定義，將指定大檔空間或協作空間映射至 Google Drive 遠端目錄，並將需排除於 Git 之外的空間路徑交由 `core.gitignore` 統一納管。
  - **`server` 常駐雙向異動引擎（`GDriveSyncServiceWorker`）**：本地端訂閱 `on_file_space_changed` 搭配批次防抖佇列（Debounce & Rate-Limit Backoff，防範 `429 Too Many Requests`）執行增量推送；雲端透過 Google Drive `changes.list`（`startPageToken` 差量游標）低開銷輪詢遠端異動並原子拉回本地，同時將覆寫或刪除之舊版移入雲端歷史回收區或保留 Drive Revisions。
  - **原生檔案與 Google Workspace 雙模透明橋接**：對 `.py`、`.md`、`.json` 等一般檔案執行 1:1 原生同步；對網頁版 Gemini 產出之 Google Docs 原生文件（無 `md5Checksum`），改以 `(drive_version, drive_modified_time, exported_local_hash)` 追蹤並自動匯出為本地 `.md` 供工具鏈讀取。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 待 `core.gitignore` 統一忽略規則收斂機制落實後，即可隨時透過 `roadmap promote` 啟動立項。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（認證管理、三方狀態帳本與 CLI 手動雙向同步）**：建立 Google Drive API v3 認證與分塊傳輸層、實作 `cache://gdrive/sync_state.json` 三方基準比對、無阻塞衝突伴隨備份、`core.gitignore` 空間忽略連動，以及 `yscb gdrive <auth|status|push|pull|sync>` CLI。
  2. **Stage 2（`GDriveSyncServiceWorker` 常駐熱同步、Google Docs 自動匯出與受控回呼）**：整合 `server` 常駐背景服務訂閱 `on_file_space_changed` 與遠端 `changes.list` 差量輪詢，實作防回音閉環、Google Docs `.md` 匯出橋接與 `post_pull` 索引連動。

