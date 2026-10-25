# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：合併落實 `server_service_hosting_and_ipc_hardening_roadmap.md`（`S-01` ～ `S-07`）與 `server_test_suite_purification_roadmap.md`（`ST-01` ～ `ST-04`），修復常駐背景服務託管斷鏈並加固 Worker IPC 管道與優雅停機。
- **核心目標**：
  1. 修復 `server/service.py` 漏寫 `import os`，接入 `core.contributes.get("server", "services")` 並支援 `__provider__` 溯源、`.modules/<provider>` `sys.path` 動態注入、`code.class://` 解析與 `auto_start` 控制（`S-01`, `S-02`）。
  2. 於 `worker_main` 實作私有 `_ipc_stdout` 句柄、執行緒安全寫入鎖 `ipc_lock` 與 `sys.stdout = sys.stderr` 重導向（`finally` 還原），並於 `MasterSupervisor._kill_worker_locked` 實作先發送 `{"action": "exit"}` 握手等待 `stop_all()` 之兩階段優雅停機（`S-03`）。
  3. 修正 `_write_state()` 之 `start_time=self._start_time`、移除 Master 冗餘 `ServiceManager`、清除所有 `source/` 路徑注入、補齊 `contributes/core.json` 之 `events` 宣告、同步 `reload` 組態刷新並移除 `_handle_start` 死代碼（`S-04` ～ `S-07`）。
  4. 裁撤空殼 `test_basic.py`，將 `server/tests/` 由 4 檔收斂為 3 檔，消滅手寫迴圈／字典之「自寫自驗」測試，並補齊跨模組服務載入、IPC 隔離與全 HTTP 端點實測（`ST-01` ～ `ST-04`）。
- **邊界排除 (Explicitly Excluded)**：不引入額外 TCP Port 或第三方依賴，維持單子進程 NDJSON 管道架構。
- **架構影響範圍**：`ys_codebase/source/server/server/{service.py,worker.py,master.py}`、`contributes/{core.json,_format.json}`、`scripts/cli.py`、`README.md` 與 `tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **連字號模組 `.modules/<provider>` 匯入防呆 (`S-01`)**：`_load_service_item` 載入前強制將 `os.path.join(yscb_root, ".modules", provider)` 插入 `sys.path`，確保 `.modules/knowledge-db/knowledge_db/service.py` 100% 可匯入。
- **[P00:DR-02]** **`worker_main` IPC 執行緒安全與防假陽性測試 (`S-03`, `ST-04`)**：`emit_fn` 以 `ipc_lock` 保護寫入，且單元測試以 `out_stream=None` 搭配 `patch.object(sys, "stdout", ...)` 真實驗證子進程重導向行為。

---

## 3. 開放議題與確認紀錄

- 規格與防呆邊界已於前置路線圖審查中 100% 確認收斂，狀態標記為 `Confirmed`。

