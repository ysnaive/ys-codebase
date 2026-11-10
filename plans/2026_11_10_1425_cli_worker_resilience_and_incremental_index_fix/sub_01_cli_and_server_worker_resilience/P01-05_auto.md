# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：CLI 觸發鍊與 Server/Worker 防卡死韌性加固  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Hot-Dispatch 重入旁路守衛 | 當 `YSCB_IN_SERVER_WORKER == "1"` 或 `YSCB_NO_HOT_DISPATCH == "1"` 時，`dispatcher._dispatch_inner` 跳過 HTTP 熱派發直走 `dispatch_local`，消除單例 Worker 自死鎖 | P0 | [P00:DR-01] |
| **FR-02** | Worker 專用不可繼承 IPC 句柄與 `stdin` 隔離 | 子進程模式 `worker_main` 以 `os.dup` 提取 `inheritable=False` 之專用 IPC 控制串流並重導向 `fd 0/1` 至 `os.devnull`，任務內隔離 `sys.stdin`；Master `_stream_task_over_worker_pipe` 檢查 `proc.poll()`、有界化 `task_q` 並將重複 `worker_ready` 改為 `continue` | P0 | [P00:DR-02] |
| **FR-03** | 兩段式斷線取消強殺升級與串流心跳 | Master 每 15 秒送出 `heartbeat` NDJSON 幀防止長任務 120s 閒置誤斷線，Client 支援 `YSCB_DISPATCH_MAX_WALL_SEC`；Client 斷線送出 `cancel` 後逾寬限期（預設 `5.0s`）自動強殺卡死 Worker 釋放 `_dispatch_lock` | P0 | [P00:DR-03] |
| **FR-04** | 停機閉鎖、Watcher 延遲重載與 CLI 逾時對齊 | HTTP Server 設 `block_on_close = False` 與請求 Socket `timeout = 10.0s`；`restart_worker` / `_spawn_worker_locked` 檢查 `_is_stopped`；`ModulesWatcher` 以 `Event.wait` 快速停機並在前景忙碌時掛起 `_pending_worker_reload`；`server reload/stop` CLI 超時提升至 `15.0s` | P0 | [P00:DR-04] |
| **FR-05** | 背景服務 Idle TTL 保全、前景禮讓與外部 I/O 逾時 | `GDriveSyncServiceWorker` 僅於實際產生變更動作時 `touch_activity()`、前景活躍時禮讓並抑制自身同步引發之空間事件喚醒；`KnowledgeDBServiceWorker` 禮讓前景時延後刷盤；`SpaceWatcher` 設 `max_debounce_seconds = 5.0`；補齊 `pip_manager`、`installer` 與 `update_checker` 逾時/防阻塞保護 | P1 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 任務啟動背景孫進程繼承預設標準句柄後 Worker 異常死亡 | 孫進程僅繼承指向 `os.devnull` 之 `fd 1`，專用 IPC 管道立即產生 EOF 且 Master `proc.poll()` 雙重偵測退出，絕不死握 `_dispatch_lock` |
| **EC-02** | 使用者按下 `Ctrl+C` 中斷卡在阻塞睡眠或鎖等待之熱派發指令 | Master 於寬限期屆滿後強殺並重建 Worker，下一條 CLI 指令立即正常執行 |
| **EC-03** | 記憶體單元測試直接傳入 `worker_main(in_stream=io.StringIO, out_stream=io.StringIO)` | 自動識別非真實標準句柄模式，不觸動宿主測試進程之 OS `fd 0/1` |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 可靠性與零洩漏 | 全模組單元測試 `0 ResourceWarning`，停機後零殘留孤兒 Worker 進程與零幽靈 `daemon.json` |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** Python 3.11+ `ThreadingHTTPServer.block_on_close` 預設為 `True`，若未覆寫為 `False`，`server_close()` 會在未設 Socket timeout 之連線執行緒上無限阻塞。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

透過環境變數守衛切斷 Worker -> Master 環路，將 Worker 子進程之控制面 NDJSON 串流與業務標準輸出入物理分流，並在 Master 派發迴圈補齊「心跳保活 + `proc.poll()` 存活巡檢 + 斷線寬限強殺 + 延遲重載佇列」。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 新增 Worker 重入與 `YSCB_NO_HOT_DISPATCH` 旁路、處理 `heartbeat` 幀與 `YSCB_DISPATCH_MAX_WALL_SEC`、`--json` 跳過更新探測 |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | `install_packages` 補齊顯式 `timeout` 參數防止持鎖無限凍結 |
| `ys_codebase/source/core/core/installer.py` | Modify | `fetch_and_extract_zip` 補齊顯式網路 `timeout` 參數 |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 探測前預寫嘗試時間戳避免離線或防火牆黑洞下併發與連續 CLI 重複逾時阻塞 |
| `ys_codebase/source/server/server/worker.py` | Modify | 子進程專用不可繼承 IPC FD 隔離、任務內 `sys.stdin` 隔離、防禦未知 `BaseException` 與 `BrokenPipeError` 停機信號 |
| `ys_codebase/source/server/server/master.py` | Modify | 心跳保活、`proc.poll()` 檢查、斷線寬限期強殺升級、有界佇列、停機閉鎖、`block_on_close=False` 與延遲重載 |
| `ys_codebase/source/server/server/watcher.py` | Modify | `Event.wait` 即時中斷睡眠與 `_last_snapshot` 執行緒鎖保護 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | `flush_dirty_spaces` 新增 `max_debounce_seconds` 最大防抖等待上限防寫入風暴餓死 |
| `ys_codebase/source/server/scripts/cli.py` | Modify | `stop` 與 `reload` 等待上限調升至 `15.0s` 對齊後端優雅停機預算 |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | `SyncReport` 新增 `yielded` 欄位並支援 `should_yield` 前景禮讓回呼 |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | 僅於實際有同步動作時觸發 `touch_activity()`、支援前景禮讓並抑制自身同步期間的空間事件自我喚醒 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | Stage 2 禮讓前景時標記延後刷盤而非當場壓縮寫盤搶佔 I/O |
| `ys_codebase/source/core/tests/test_cli_router.py` | Modify | 新增重入旁路、`heartbeat` 解析、`--json` 跳過更新檢查與 I/O 逾時單元測試 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增 IPC FD 孫進程隔離、斷線寬限強殺、停機防孤兒復活與防抖上限單元測試 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 新增無變更輪詢不誤觸 `touch_activity`、前景禮讓喚醒保留與路徑級自我喚醒抑制測試 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 Stage 2 前景禮讓延後刷盤、零忙等迴圈與結束收尾刷盤單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 專用 IPC 通道僅在 `in_stream is None and out_stream is None` 之真實子進程入口透過 `os.dup` 建立，確保白箱單元測試傳入自訂記憶體串流時行為 100% 相容。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

- `core.pip_manager.PipManager.install_packages(self, specs: List[str], py_tag: Optional[str] = None, timeout: int = 300) -> None`
- `core.installer.fetch_and_extract_zip(source_url_or_path: str, dest_dir: str, timeout: float = 30.0) -> None`
- `server.space_watcher.CoreSpaceWatcherServiceWorker.__init__(..., max_debounce_seconds: float = 5.0)`
- **錯誤與例外契約 (Error & Exception Contracts)**：外部套件安裝逾時捕獲 `subprocess.TimeoutExpired` 並轉換為明確 `PipInstallError`；網路下載逾時轉換為安裝錯誤；Client 斷線逾寬限期強制回收並熱重建 Worker 後安全釋放 `_dispatch_lock`。
- **階段決策紀錄**：[P03:DR-01] 所有新增參數均提供向下相容預設值，不破壞既有呼叫端。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：Windows 下 `os.dup` 與 `os.set_inheritable(fd, False)` 均由 Python 3.4+ 標準庫原生支援，搭配 `os.fdopen(..., closefd=True)` 確保退出時零句柄洩漏。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 補充專用 IPC 控制通道、心跳與斷線寬限強殺說明 |
| **專題手冊** | `docs/server/daemon_architecture.md` | Modify | 對齊 `warming` 超時、Idle TTL 30 分鐘常數與兩段式取消機制 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記專用 IPC FD 隔離與單例 Worker 重入旁路設計筆記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本計畫防卡死韌性加固變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認三層文檔同步範圍。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core` 派發重入旁路、心跳與總時限解析、`--json` 更新探測跳過及 `pip_manager` / `installer` / `update_checker` 逾時防護
- [x] **TASK-02**：實作 `server` Worker 專用不可繼承 IPC FD 與 `stdin` 隔離、Master 心跳保活、`proc.poll()` 檢查、斷線寬限強殺、停機閉鎖與延遲重載
- [x] **TASK-03**：實作 `GDriveSyncServiceWorker` Idle TTL 保護與前景禮讓、`KnowledgeDBServiceWorker` 延後刷盤及 `SpaceWatcher` 最大防抖上限
- [x] **TASK-04**：編寫並通過 `core`、`server`、`gdrive-support` 針對性單元與邊界測試（`0 ResourceWarning`）
- [x] **TASK-DOC**：同步更新 `docs/server/` 手冊、`CHANGELOG.md` 與代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
