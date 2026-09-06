# 需求規格說明書 (Requirements Specification)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | core.platform 跨平台底層 SDK 先行 | 1. 於 `source/core/core/platform/` 實作跨平台原語：`spawn_detached`（POSIX setsid / Win detached）、`kill_process_tree`（POSIX killpg / Win taskkill）、`is_process_alive`。<br/>2. 實作跨平台跨進程鎖 `InterProcessLock`（POSIX flock / Win msvcrt.locking）。<br/>3. 單元測試覆蓋先行跑通。 | P0 | [P00:DR-10] |
| **FR-02** | Server 模組骨架與微內核守門遵循 | 建立 `source/server/` 標準模組。進入點 `scripts/cli.py` 宣告純函式 `process(args: List[str]) -> int`，首行調用 `core.guard.guard_dispatch("server")`。 | P0 | [P00:DR-01] |
| **FR-03** | Master-Worker 進程架構與專案 Root 隔離 | 1. 採方案 C：Master 守護進程掌理 HTTP 與生命週期；背景常駐 1 個單一預熱 Worker 子進程執行任務。<br/>2. 狀態與 PID 鎖綁定 `cache://server/daemon.json`，多專案工作區物理隔離。<br/>3. 支援 `server start/stop/status/reload` CLI 管理指令。 | P0 | [P00:DR-04]<br/>[P00:DR-08]<br/>[P00:DR-11] |
| **FR-04** | 本地回環 HTTP 服務與 Token 防禦 | 基於 Python 標準庫監聽 `127.0.0.1:0`（動態分配闲置 Port）。所有請求需攜帶 Header `Authorization: Bearer <token>` 驗證，不符者一律回傳 HTTP 403。 | P0 | [P00:DR-04] |
| **FR-05** | 按需延遲加載與運行期沙盒化 | 1. Worker 啟動時不預先加載任何領域模組；收到派發時動態加載目標模組。派發 A 模組絕不加載 B 模組。<br/>2. Worker 內部攔截 `SystemExit` 轉為整數退出碼，杜絕業務模組中斷常駐進程。同一 Worker 內採單隊列序列化執行。 | P0 | [P00:DR-02]<br/>[P00:DR-14] |
| **FR-06** | IO 重定向與 500ms 防抖分流串流協議 | 1. 攔截業務模組執行之 `sys.stdout` 與 `sys.stderr`。<br/>2. 串流封包類型精確劃分為 `terminal_stream`（終端增量塊）與 `task_finish`（任務完成封包，含 exit_code 與耗時統計）。<br/>3. 輸出端採用 500ms 防抖機制（累積滿閥值或無串流時立即 flush），減少零碎小包。 | P0 | [P00:DR-05]<br/>[P00:DR-07] |
| **FR-07** | yscb 雙軌調度與四大耦合邊界 | 1. 軟依賴探測：`yscb.py` 零靜態 import server，探測未就緒即透明冷降級。<br/>2. 自循環旁路：`module == "server"` 強制直接走本地冷啟動。<br/>3. 按需非同步拉起：`config.local.json` 開啟時，背景脫鉤拉起 Master，當前命令冷啟動執行，首發零等待感。<br/>4. 宿主極簡客戶端：`yscb.py` 僅保留 ~60 行標準庫轉發器與 wait loop。 | P0 | [P00:DR-03]<br/>[P00:DR-12]<br/>[P00:DR-15] |
| **FR-08** | .modules/ 熱重載自癒與 15 分鐘空閒自毀 | 1. 熱重載採選項 1：監控 `.modules/` 變動，變更時 Master 直接終止舊 Worker 並重啟全新 Worker，杜絕快取殘留。<br/>2. 支援 `config.local.json` 配置 15 分鐘空閒超時自毀 (Idle TTL)，超時自動優雅關閉釋放記憶體。 | P1 | [P00:DR-06]<br/>[P00:DR-09]<br/>[P00:DR-12]<br/>[P00:DR-13] |
| **FR-09** | 預熱生命週期事件廣播與狀態探針 | 1. Worker 預熱開始與完成時，透過 `core.events` 廣播 `server:worker:warming` 與 `server:worker:ready` 事件。<br/>2. Master 的 `/api/status` 端點揭露進程 state (`warming`/`ready`/`reloading`) 與預熱耗時。 | P1 | [P00:DR-16] |
| **FR-10** | 業務 Service Worker 統一生命週期治理 | 1. Master 預留註冊式 `BaseServiceWorker` 擴充插槽（供未來 Watchdog 如 `knowledge-db` 檔案監聽接入）。<br/>2. 所有 Service Worker 之生命週期嚴格跟隨 Server 主進程設定，共享 15 分鐘 Idle TTL，嚴禁永久長駐，超時或手動停止時同步安全退出。 | P1 | [P00:DR-17] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 孤兒死鎖/異常崩潰之陳舊 PID 檔 | 啟動或派發前自動透過 `core.platform.is_process_alive(pid)` 探測進程存活。若已死亡，自動清理無效 `daemon.json` 並無縫拉起或直接冷啟動降級。 |
| **EC-02** | 本地連接埠衝突 | Server 啟動時綁定 `127.0.0.1:0`，由 OS 內核自動分配空閒隨機埠，將該埠寫入 `daemon.json`，徹底消除靜態 Port 衝突。 |
| **EC-03** | 派發中途 Worker 崩潰或超時 | Worker 崩潰時 Master 依然健在，Master 捕獲管道斷開並回傳 HTTP 500/錯誤封包給 CLI，同時自動重啟新 Worker 達成自癒。 |
| **EC-04** | 用戶在終端觸發 Ctrl+C (SIGINT) | CLI 端捕獲 `KeyboardInterrupt` 時，向 Server 發送 `/api/cancel` 取消請求；Server 中斷當前 Worker 任務或重啟 Worker，確保狀態安全復原。 |
| **EC-05** | 跨專案 yscb root 呼叫混淆 | 派發請求 Payload 附帶調用者之 `yscb_root`，Server 校驗請求來源工作區路徑，若與 Server 所屬工作區不符則拒絕執行，嚴守工作區隔離底線。 |
| **EC-06** | 重構凍結期誤執行 `@build` 自部署 | 嚴格遵守全生態系重構凍結紀律，禁止自部署到 `.modules/`；測試完全在獨立沙盒目錄或 `source/` 中進行。 |
| **EC-07** | Service Worker 阻擋 Server 關閉 | 當 Server 因 15 分鐘空閒自毀或收獲關閉訊號時，Master 給予 Service Worker 2 秒優雅關閉寬限期；超時未退出則調用 `core.platform.kill_process_tree` 強制收割，絕不殘留背景進程。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 派發延遲 | 常駐預熱熱派發命令至模組開始執行的調用延遲 < 30ms（相較於冷啟動 500~1500ms 節省 >90% 延遲）。 |
| **NFR-02** | 輕量化與零重型依賴 | 僅使用 Python 3.10+ 標準庫（`http.server`, `urllib.request`, `multiprocessing.connection`, `subprocess`, `json` 等）與 `core.vfs`/`core.guard`/`core.platform`，無任何第三方 heavy web framework。 |
| **NFR-03** | 測試覆蓋率 | 單元測試與集成測試覆蓋 `core.platform`、生命週期、HTTP 通訊、IO 防抖、Worker 重啟、預熱事件與冷熱降級，沙盒測試 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 重構期全生態系管制 (Refactor Freeze)**：
  本子計畫實作完成後，嚴禁執行 `python yscb.py install server@build` 進行運行端自部署。必須待後續子計畫完成全生態系聯調後統一發布。
- **`[!IMPORTANT]` 自循環死鎖剛性防護 (Self-Invocation Guard)**：
  `yscb.py` 處理 `server` 自身模組指令時，必須硬性走本地冷啟動，絕對不可進行熱派發。
- **`[!NOTE]` 延遲加載與 Worker 記憶體純淨 (Lazy Loading Hygiene)**：
  Worker 進程啟動時嚴禁預加載任何領域模組，確保調用 A 模組絕不加載 B 模組，杜絕代碼污染。
- **`[!NOTE]` 統一生命週期自毀鐵律 (Shared TTL Discipline)**：
  Service Worker 嚴禁脫離 Server 獨立永久苟活，必須共享 15 分鐘空閒自毀機制。
