# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-10 在 API 規格書中均有明確對應之介面類別、Event 規格與 HTTP 路由。
- [x] **邊界防護**：EC-01 ~ EC-07（死鎖 PID 清理、隨機 Port 分配、連線超時冷降級、Ctrl+C 取消、Root 隔離校驗、重構期禁止自部署、Service Worker 超時強殺連動）皆有具體防禦與降級機制。
- [x] **依賴純淨**：完全基於 Python 3.10+ 標準庫與 `core.vfs` / `core.guard` / `core.platform` / `core.events`，零第三方重型網路框架依賴，符合 NFR-02 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | New | Server 模組概覽、架構定位、指令用法與常駐加速原理 |
| **專題手冊** | `docs/server/daemon_architecture.md` | New | 500ms 防抖串流協議、Master-Worker 雙進程模型、15 分鐘 TTL、預熱 Event 與 Service Worker 治理 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | New | 登記 DN-01 (方案 C 雙進程架構)、DN-02 (500ms 防抖)、DN-03 (四大耦合邊界)、DN-04 (Service 共享生命週期) |
| **平台文檔** | `docs/core/platform.md` | New | `core.platform` 跨平台原語與鎖規格說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 登記 sub_03 Server 模組新增與持久化常駐加速功能發布預備 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若執行的業務模組 process(args) 內部呼叫了 sys.exit()，是否會導致 Worker 進程直接退役？**  
> 💡 **防護解法**：
> `WarmWorker` 在調用模組 `process(args)` 時以 `try...except SystemExit as e:` 包覆，攔截退出訊號並將 `e.code` 轉換為正常回傳的 exit code，確保 Worker 常駐運行不被模組中止。

> ❓ **尖銳問題 2：若其他模組註冊了 Watchdog 檔案監聽服務，在 15 分鐘無操作後，會不會阻止 Server 退出或變成孤兒進程偷跑？**  
> 💡 **防護解法**：
> 確立「生命週期嚴格跟隨 Server」鐵律。Master 在 15 分鐘 Idle TTL 觸發自毀時，會同步呼叫所有 Service Worker 的 `stop()`，並給予 2 秒寬限期；逾時則透過 `core.platform.kill_process_tree` 強制收割進程樹，絕不殘留背景進程。

> ❓ **尖銳問題 3：模組更新後（例如更新了 .modules/ 內的代碼），常駐進程中的 Python 快取是否會導致繼續執行舊代碼？**  
> 💡 **防護解法**：
> 內建 `ModulesWatcher` 自動監控 `.modules/` 目錄之時間戳 (mtime) 與結構。檢測到變動時，Master 直接殺死舊 Worker 並重啟全新乾淨 Worker 子進程，100% 杜絕 Python reload 帶來的幽靈參考與型態不匹配問題。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `core.platform` 跨平台底層原語 (`process.py`, `lock.py`, `__init__.py`)
- [ ] **TASK-02**：編寫 `source/core/tests/test_platform.py` 單元測試並驗證通過
- [ ] **TASK-03**：初始化 `server` 模組目錄結構 (`source/server/`、`source/server/tests/`、`source/server/__init__.py`)
- [ ] **TASK-04**：實作 500ms 防抖分流串流器 `source/server/streamer.py` (`DebouncedIOStreamer`)
- [ ] **TASK-05**：實作業務 Service Worker 抽象基底 `source/server/service.py` (`BaseServiceWorker`)
- [ ] **TASK-06**：實作常駐預熱 Worker 子進程 `source/server/worker.py`（預熱 Event 廣播、按需延遲加載、SystemExit 攔截）
- [ ] **TASK-07**：實作 `.modules/` 變更感知器 `source/server/watcher.py` (`ModulesWatcher`)
- [ ] **TASK-08**：實作 Master 守護進程與 HTTP 服務 `source/server/master.py`（127.0.0.1:0、Token、15 分鐘 TTL、Service Worker 納管與連動自毀）
- [ ] **TASK-09**：實作 Server CLI 管理指令 `source/server/scripts/cli.py` (首行 `guard_dispatch("server")`)
- [ ] **TASK-10**：改裝 `ys_codebase/yscb.py` 入口（軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端）
- [ ] **TASK-11**：撰寫沙盒整合測試套件 `source/server/tests/test_server.py` 並跑通全生態系測試
- [ ] **TASK-12**：知識庫與模組文檔交付 (`docs/server/`, `docs/core/platform.md` 與 `CHANGELOG.md`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] core.platform 底層先行原則**：跨平台原語收斂於微內核 `core.platform`，`server` 與宿主均單向依賴 `core`。
- **[P04:DR-02] 方案 C: Master + Warm Worker 雙進程架構**：Master 掌理網路與排程，Worker 執行業務模組，兼具 <30ms 瞬發效能與 100% 模組隔離性。
- **[P04:DR-03] 500ms 防抖與 NDJSON 雙通道串流協議**：回傳封包嚴格區分 `terminal_stream` 與 `task_finish`，輸出端設置 500ms 緩衝防抖閥值，兼顧即時性與網路吞吐。
- **[P04:DR-04] 按需延遲加載與 Worker 重啟熱更新**：Worker 僅在派發時載入目標模組，調用 A 絕不加載 B。`.modules/` 變更時直接殺死舊 Worker 並重啟新 Worker，杜絕 Python reload 幽靈 Bug。
- **[P04:DR-05] yscb 與 Server 四大耦合邊界**：軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端，保持宿主輕量與極致穩健。
- **[P04:DR-06] 預熱事件廣播與 Service Worker 共享生命週期**：發布 `server:worker:warming/ready` 事件；Service Worker（如 Watchdog）嚴格共享 15 分鐘空閒自毀，不獨立永久長駐。
