# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **背景服務託管引擎修復與增強 (`S-01`, `S-02`, `FR-01`, `EC-01`, `EC-02`)**：
     - 在 `server/service.py` 補齊缺失之 `import os`，接入 `core.contributes.get("server", "services")` 聚合登錄。
     - 動態將 `.modules/<provider>` 注入 `sys.path`，支援 `code.class://` 前綴去除與連字號模組名稱轉底線（優先直接匯入，相容 `knowledge_db.service:KnowledgeDBServiceWorker`）。
     - 於 `ServiceManager.register()` 與 `start_all()` 完整實作 `auto_start` 過濾控制，允許手動背景服務略過自動啟動。
  2. **Worker IPC 管道硬隔離與兩階段優雅停機 (`S-03`, `S-04`, `S-05`, `FR-02`, `FR-03`, `FR-04`, `EC-03`, `EC-04`)**：
     - 在 `server/worker.py` 實作獨立私有 `_ipc_stdout` 句柄與 `ipc_lock` 互斥鎖，並於主迴圈期間將全域 `sys.stdout` 重導向至 `sys.stderr`（`finally` 區塊恢復），徹底根除背景服務或外部庫 `print()` 雜訊污染 NDJSON 管道導致 `JSONDecodeError`。
     - 徹底移除 Worker 與 Master 中的 `source/` 源碼路徑注入，嚴守 `.modules/` 運行時空間隔離。
     - 在 `server/master.py` 實作兩階段停機協定：第一階段向 Worker 寫入 `{"action": "exit"}\n` 進行平滑應用層握手（讓 Worker 依序呼叫各託管服務之 `stop()`）；若超時 1.5 秒未退出則自動降級為第二階段 `kill_process_tree` 強制收割進程樹。
     - 移除 Master 上冗餘的 `self.service_manager` 實例，修復 `/api/shutdown` 端點潛在的 `AttributeError`，並修正 `_write_state()` 傳入 `self._start_time` 使 Worker 重啟後 Master Uptime 保持累計。
  3. **Contributes 宣告、Reload 熱刷新與 CLI 清理 (`S-06`, `S-07`, `FR-05`, `EC-05`)**：
     - 在 `contributes/core.json` 補齊 `server_worker_warming` 與 `server_worker_ready` 之 `events` 宣告，Worker 移除重複的 `worker_warming` 舊廣播。
     - `master.py:restart_worker()` 重載時同步調用 `ServerConfig.load()` 刷新記憶體中的 `idle_timeout_sec`。
     - 於 `scripts/cli.py` 刪除未使用的死代碼 `_handle_start()`，並為 `start` 指令新增負數 TTL 驗證防禦。
  4. **測試套件純化收斂 4 檔 $\to$ 3 檔與高風險路徑覆蓋 (`ST-01` ~ `ST-04`, `FR-06`, `FR-07`, `NFR-01`, `NFR-02`)**：
     - 物理刪除空測試檔案 `tests/test_basic.py`，全測試套件收斂為 3 個子系統測試檔（`test_server.py`, `test_server_config.py`, `test_server_logging.py`）。
     - 徹底消除自測自演的 dummy mock，`test_server_logging.py` 改為真實呼叫 `sup.dispatch_task()`；`test_server.py` 補齊真實 HTTP POST `/api/reload`、`/api/shutdown`、`/api/dispatch` (400 邊界) 以及真實攔截子進程 `env["PYTHONPATH"]` 之零 `source/` 嚴格斷言。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/service.py` | Modify | 補齊 `import os`，接入 `contributes`，支援 `.modules` 動態注入、連字號解析與 `auto_start` 控制 |
| `ys_codebase/source/server/server/worker.py` | Modify | 獨立私有 `_ipc_stdout` 與 `ipc_lock`，`sys.stdout -> sys.stderr` 重導向，移除 `source/` 注入與重複 event |
| `ys_codebase/source/server/server/master.py` | Modify | 兩階段停機協定、`start_time` 持久化、移除冗餘 `ServiceManager`、同步 `ServerConfig`、零 `source/` 注入 |
| `ys_codebase/source/server/contributes/core.json` | Modify | 補齊 `events` 陣列聲明 `server_worker_warming` 與 `server_worker_ready` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 移除死代碼 `_handle_start`，加固負數 TTL 輸入阻斷 |
| `ys_codebase/source/server/tests/test_basic.py` | Delete | 物理刪除無斷言之歷史空檔案 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 重構測試，補齊真實 HTTP 端點測試、動態模組載入、零 `source/` 攔截斷言與兩階段超時降級 |
| `ys_codebase/source/server/tests/test_server_config.py` | Modify | 移除 `_handle_start` 測試，新增負數 TTL、停用守衛與 events 宣告驗證 |
| `ys_codebase/source/server/tests/test_server_logging.py` | Modify | 重寫 `test_worker_ipc_logging_stream` 真實呼叫 `sup.dispatch_task()` 驗證 IPC 日誌過濾 |
| `docs/server/DESIGN_NOTES.md` | Modify | 增補 `[DN-05]` (IPC 隔離)、`[DN-06]` (兩階段關閉) 與 `[DN-07]` (零 source 隔離) |
| `docs/server/README.md` | Modify | 同步更新 Master/Worker 職責說明與兩階段關閉架構 |
| `docs/server/hot_reload_and_services.md` | Modify | 同步更新 `contributes/server.json` 服務宣告規格與動態注入機制 |
| `ys_codebase/source/server/README.md` | Modify | 同步源碼層手冊之雙進程職責、服務託管規格與路徑隔離約束 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check server`：`PASSED`（0 Fail, 0 Warn）。
  - `python yscb.py dev test server --sync`：**40/40 Passed (100% Ready, 3.78s)**（Contract: 3/3, Custom: 37/37, 0 Failed, 0 Unknown, 0 Skipped），成功熱部署 `server@1.0.0.build`。
  - 全量生態系回歸測試 `python yscb.py dev test -q`：**193/193 Passed (100%)**。
- **Pillar 3 獨立代碼審查**：
  - 於進入 UX 測試前派發 `research` 獨立審查子代理執行無偏見代碼與架構審查。
  - 歷經初審與復審整改，全數消除 `/api/shutdown` 潛在 `AttributeError`、服務路徑解析截斷問題與測試虛假宣稱，取得 `REVIEW_STATUS: PASSED` 認證。
- **實機 UX / 人工驗證**：
  - `UX-01`：`python yscb.py server status` 正確顯示 State: READY, Worker Alive, Background Svcs: knowledge-db-watcher RUNNING，未啟動時顯示 Stopped。
  - `UX-02`：`python yscb.py server reload` 實機平滑熱輪替 Worker（PID 更新），Master Uptime 持續累加不中斷；關閉時兩階段握手優雅停機並歸檔日誌。
  - **重啟情境與資源監控驗證**：在背景長時間監控資源用量下，完整測試 CLI reload、ModulesWatcher 領域模組變更重啟 Worker、核心模組變更重啟 Master 等情境，進程退場乾淨且無記憶體/FD 洩漏，開發者確認通過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [CHANGELOG.md](../../../CHANGELOG.md) | 已完成 | 記錄 `sub_03_server_hosting_ipc_and_tests` 背景服務託管、IPC 隔離與測試純化結案摘要 |
| **中觀 (Meso)** | [docs/server/README.md](../../../docs/server/README.md)、[ys_codebase/source/server/README.md](../../../ys_codebase/source/server/README.md) | 已完成 | 同步雙進程職責、兩階段關閉與 `_ipc_stdout` 隔離說明 |
| **中觀 (Meso)** | [hot_reload_and_services.md](../../../docs/server/hot_reload_and_services.md) | 已完成 | 更新 `contributes/server.json` 服務註冊規格、動態路徑注入與生命週期協定 |
| **中觀 (Meso)** | [docs/server/DESIGN_NOTES.md](../../../docs/server/DESIGN_NOTES.md) | 已完成 | 增補 `[DN-05]`、`[DN-06]`、`[DN-07]` 記錄管道隔離、兩階段停機與零 source 路徑邊界 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 完整維護 `service.py`、`worker.py`、`master.py` 之 Docstring 與型別標註 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試、邊界測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(server): harden service hosting, worker IPC isolation, and purify test suite (sub_03)

- Fix ServiceManager import and dynamic provider path injection in service.py (S-01, S-02)
- Isolate Worker IPC stdout with private handle, redirect global stdout to stderr, and add ipc_lock (S-03)
- Implement two-stage graceful shutdown handshake and preserve start_time across reload in MasterSupervisor (S-04)
- Enforce strict runtime isolation with zero source/ path injection in Worker and Master (S-05)
- Declare events in contributes/core.json, sync ServerConfig on reload, and clean cli.py dead code (S-06, S-07)
- Consolidate test suite from 4 files into 3 subsystem files, delete test_basic.py, and cover high-risk paths (ST-01~ST-04)
- Update three-tier documentation in docs/server and source/server/README.md
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify sub_03_server_hosting_ipc_and_tests` 驗證 100% Passed。

