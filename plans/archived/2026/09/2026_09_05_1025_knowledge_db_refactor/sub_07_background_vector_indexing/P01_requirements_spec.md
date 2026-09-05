# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 組態定義與型態防禦 | `KnowledgeDBConfig` 新增 `enable_hot_reload_server: bool = False` 與 `hot_reload_server_inactivity_timer_sec: int = 600`。支援 Local / Project 層級解析、字串布林容錯轉換與合規驗證。 | P0 | [P00:DR-01] |
| **FR-02** | Pre-Dispatch Hook 自動喚醒 | 在 `scripts/hook.core.py` 實作 `on_pre_cli_dispatch(ctx)`。當 `enable_hot_reload_server == True` 時，檢測 Server 是否存活；若未存活則在背景非同步啟動 Server，耗時 $\le 10\text{ms}$，不阻塞當前 CLI。 | P0 | [P00:DR-02] |
| **FR-03** | 專屬 Server 核心與 Watcher 監控 | 實作 `HotReloadServer` 常駐服務核心，透過 `watchdog` 監控由注入之 `SpaceManager` 動態解算之空間目錄（遵循 Union Scope 公理，依注入之各空間 `include` 定位監聽路徑，嚴禁寫死特定目錄），實作 500ms 防抖緩衝窗口聚合變更事件。 | P0 | [P00:DR-03] |
| **FR-04** | AST+BM25+Graph+Vector 全流程熱修補 | 防抖結束後，Server 呼叫 `IndexingPipeline.hot_patch_unified_index`，一次性執行 AST 解析、BM25 倒排索引更新、NetworkX 調用圖譜更新與 FastEmbed 向量嵌入推論，全語意一步到位。 | P0 | [P00:DR-03] |
| **FR-05** | 原子替換與二進位快取同步 | Server 熱修補產出的二進位快取 (`unified.*.bin.gz` 與 `unified.meta.bin`) 採臨時檔寫入後透過 `os.replace` 原子替換，確保前台 CLI 隨時讀取的快取 100% 完整一致。 | P0 | [P00:DR-03] |
| **FR-06** | 閒置超時自動退出釋放記憶體 | Server 維護 `last_activity_timestamp`。若持續 `hot_reload_server_inactivity_timer_sec` 秒無檔案變更，Server 自動退出進程並清理 PID/Lock，釋放記憶體。 | P0 | [P00:DR-04] |
| **FR-07** | CLI 守護進程管理門面 | `scripts/cli.py` 新增 `knowledge-db daemon [start\|stop\|status\|watch]` 子命令，支援前台/背景啟動、狀態查詢與手動停止。 | P1 | [P00:DR-03] |
| **FR-08** | 第一軌 Standalone JIT 雙軌保底 | 當 `enable_hot_reload_server == False` 或 Server 未運行時，CLI 搜尋維持既有 Standalone JIT 與安全降級機制，保持極致靈活與無常駐環境純淨度。 | P0 | [P00:DR-05] |
| **FR-09** | PID 檔案寫入 `cache://` 邊界隔離 | PID 檔案強制寫入 `cache://knowledge-db/daemon.pid`（Git 忽略區），嚴禁寫入會被 Git 追蹤的 `storage/`；記錄 `pid`、`start_time`、`version`、`log_file`、`spaces` 與 `spaces_signature`。 | P0 | [P01:DR-02] |
| **FR-10** | 即時日誌滾動保留機制 | Server 即時於 `cache://knowledge-db/logs/daemon_{start_time}_{pid}.log` 產出執行與熱更新日誌。以每次完整 PID lifecycle 為 1 單位，採滾動式清理最多保留 3 份歷史日誌。 | P0 | [P01:DR-02] |
| **FR-11** | 模組版本或空間變更強制重啟 | PID 記錄當前 `knowledge-db` 版本與 `spaces_signature`。在 `on_pre_cli_dispatch` 或 `ensure_running` 探測時，若發現目前環境之模組版本不符或注入空間設定/簽名變更，強制終止舊進程並重啟，確保新代碼與新空間定義即刻生效。 | P0 | [P01:DR-04] |
| **FR-12** | CLI JIT 提示與 Server 旁路 | 運行相關 CLI (search, callers, callees, impact) 時，若後台探測到運行中之 Server，跳過 JIT 檢查並向 stderr 提示 `"Hot reload server(pid:<pid>) exist, skip JIT check."`，單一生命週期僅提示一次。 | P0 | [User:0905-2] |
| **FR-13** | Server 啟動離線預檢熱修補 | Server 啟動掛載 Watcher 前，先強制執行一次與 JIT 相同的 `check_invalidation` 檢查，自動修補 Server 離線期間產生的檔案異動，不依賴單一 Watchdog。 | P0 | [User:0905-2] |
| **FR-14** | Server 啟用時 JIT 設定失效 | 當 `enable_hot_reload_server == True` 時，組態中的 `jit_vector_timeout_seconds` 等 JIT 設定視為無效（邏輯失效且 `resolve_jit_vector_timeout()` 返回 `None`），由 Server 在背景全權負責無時間限制之向量推論與更新。 | P0 | [User:0905-2] |
| **FR-15** | Contributes 驅動副檔名與 Space 雙軌初篩 | Watcher 初篩 100% 透過 `ParserRegistry.get_supported_extensions()` 動態收集 contributed 語言之副檔名與各 Space `file_patterns`，杜絕硬編碼；檔案變更事件透過 `is_path_watched` 動態套用各 Space 之 `exclude` 與 `is_file_included`，確保與 Scanner 過濾標準 100% 同步。 | P0 | [User:0905-3] |
| **FR-16** | Core 組態軟合併 Local 跳過 Project 既有設定 | Core Engine 執行組態軟合併（`_deep_infill_dict`）時，`project` 層級維持正常缺項填充；`local` 層級軟合併時，若 `project` 層級已存在對應設定（非字典型態直接跳過；巢狀字典則向下比對，若子設定已於 project 存在亦跳過），自動跳過填充，避免本機預設值意外蓋過專案共享設定。 | P0 | [User:0905-4] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 重複啟動與殭屍 PID 殘留 | 若 PID 檔案存在，檢驗進程是否存活且為有效 Python 程序；若為死進程則清理殘留並重啟；若有效存活則安全短路，不重複拉起。 |
| **EC-02** | 高頻連續檔案儲存 (Burst Events) | 編輯器格式化或 Git 批次操作產生密集儲存，防抖計時器重設，變更平息 500ms 後僅觸發一次增量更新。 |
| **EC-03** | 前台讀取與 Server 寫入並行衝突 | 前台讀取與 Server 寫入互不鎖死；因採 `os.replace` 原子替換，前台永遠只讀到舊版本完整檔或新版本完整檔，絕不讀到半成品。 |
| **EC-04** | Watchdog 依賴缺失或環境異常 | 若環境未安裝 `watchdog`，拋出友善導引提示至 stderr，平滑回退 Standalone JIT 模式，不導致系統或 CLI 崩潰。 |
| **EC-05** | 系統信號中斷 (SIGTERM / SIGINT) | Server 註冊信號處理器，接收到終止信號時安全關閉 Watcher、清理 PID 檔案並退出，零殘留進程。 |
| **EC-06** | 測試沙盒環境隔離 | `dev test` 沙盒測試環境（`YSCB_TEST_SANDBOX==1`）強制禁用自動常駐 Server，避免測試進程殘留與跨環境污染。 |
| **EC-07** | 模組熱更新後代碼版本滯後 (Code Stale) | 開發者發布新版本或執行 `@build` 安裝後，`on_pre_cli_dispatch` 透過版本感知偵測到版本失配，自動強制重啟舊 Server，杜絕舊進程常駐舊代碼。 |
| **EC-08** | 日誌目錄累積與磁碟膨脹 | 啟動與終止時掃描 `cache://knowledge-db/logs/`，嚴格依 lifecycle 倒序保留最新 3 份檔案，其餘主動清理，防止磁碟無限制膨脹。 |
| **EC-09** | 空間注入變更 (Contributed / Custom Spaces Mismatch) | 當專案新增/移除空間或修改空間 include 路徑時，`spaces_signature` 產生變更，`ensure_running` 探測到失配自動終止舊 Server 並拉起新 Server 監聽新空間目錄。 |
| **EC-10** | Server 離線期間檔案異動 (Offline Gap) | Server 關閉或未啟動時進行的檔案修改，於下次 Server 啟動時透過 `_run_startup_check` 執行 JIT 相同檢查並即刻熱修補，無盲區遺漏。 |
| **EC-11** | CLI 與 Server 雙重檢查衝突 (JIT Check Redundancy) | 當背景已存在 Server，前台 CLI 自動抑制 JIT `check_invalidation`，避免重複磁碟走訪與 I/O 競爭，保證 CLI 極致零延遲。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 啟動延遲 | `on_pre_cli_dispatch` 探測與喚醒耗時 $\le 10\text{ms}$，對常規 CLI 調用零感。 |
| **NFR-02** | 閒置資源回收 | 閒置超時自動退出後進程徹底終止，背景 CPU 與 RAM 佔用歸零 (0 MB)。 |
| **NFR-03** | 熱更新即時性 | 單一檔案儲存後，防抖 + AST/BM25/Graph/Vector 增量更新於 $\le 1.5\text{s}$ 內寫入磁碟就緒。 |
| **NFR-04** | 相容性守門 | 既有對外 Public API 與 CLI 輸出格式 100% 向後相容，既有 133/133 單元測試 100% 通過。 |
| **NFR-05** | Git 零污染守門 | PID 與 Log 檔案 100% 落檔於 `cache://`（`.cache/knowledge-db/`），`git status` 零變動。 |

---

## 4. 關鍵規格決策 ([P01:DR-01] ~ [P01:DR-04])

- **[P01:DR-01] 防抖緩衝窗口與單線程消費**：
  - 監控器事件回呼僅記錄變更檔案路徑並重設防抖計時器（0.5s）。
  - 單一工作線程循序執行熱更新，避免高頻變更造成多重並發推論競爭 CPU。
- **[P01:DR-02] PID 與日誌空間規範 (cache:// 邊界與 3 世代滾動)**：
  - PID 檔案統一置於 `cache://knowledge-db/daemon.pid`（嚴禁置於 `storage/`）。
  - 日誌置於 `cache://knowledge-db/logs/daemon_{start_time}_{pid}.log`，每次 PID 生命週期為 1 單位，滾動保留最多 3 份。
- **[P01:DR-03] 閒置定時器輪詢間隔**：
  - 閒置檢查線程每 10 秒輪詢一次，比對 `time.time() - last_activity_time`，平衡時效性與 CPU 喚醒開銷。
- **[P01:DR-04] 版本感知強制重啟協議 (Version Matching Restart)**：
  - PID 檔案內建 `version` 欄位。
  - 當前環境版本（透過 `manifest.json` 或 `installed_modules` 獲取）與 PID 版本不一致時，觸發強制終止與重啟，杜絕熱代碼漂移。

---

## 5. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

> [!NOTE]
> - 在 Dev Containers 或遠端檔案系統掛載環境下，`watchdog` 原生 inotify 偶有延遲，可透過 `KNOWLEDGE_DB_FORCE_POLLING=1` 切換為 `PollingObserver`。
> - 沙盒環境下 `setUp()` 強制校驗 `YSCB_TEST_SANDBOX==1`，Server 測試案例應在沙盒內部以受控子進程或 Thread 形式執行，並於 `tearDown()` 確保終止。
> - `cache://knowledge-db` 目錄在系統執行 `python yscb.py reload --purge` 時會被自動清空，此時 Server PID 與 Logs 將被自然清理，因此 PID 探針必須安全處理檔案不存在之情境。
