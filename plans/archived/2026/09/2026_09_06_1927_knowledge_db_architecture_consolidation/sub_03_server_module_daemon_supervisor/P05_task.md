# 實作任務清單 (Task Breakdown)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core.platform` 跨平台底層原語 (`process.py`, `lock.py`, `__init__.py`)
- [x] **TASK-02**：編寫 `source/core/tests/test_platform.py` 單元測試並驗證 FT-01~03 通過
- [x] **TASK-03**：初始化 `server` 模組骨架 (`source/server/scripts/cli.py`, `__init__.py`, `manifest.json`) 並通過 `dev check` (FT-04)
- [x] **TASK-04**：實作 500ms 防抖分流串流器 `source/server/streamer.py` (`DebouncedIOStreamer`) (FT-05)
- [x] **TASK-05**：實作業務 Service Worker 抽象基底 `source/server/service.py` (`BaseServiceWorker`) (FT-08)
- [x] **TASK-06**：實作常駐預熱 Worker 子進程 `source/server/worker.py`（預熱 Event 廣播、按需延遲加載、SystemExit 攔截）(FT-06, FT-07)
- [x] **TASK-07**：實作 `.modules/` 變更感知器 `source/server/watcher.py` (`ModulesWatcher`) (FT-10)
- [x] **TASK-08**：實作 Master 守護進程與 HTTP 服務 `source/server/master.py`（127.0.0.1:0、Token、15 分鐘 TTL、Service Worker 納管與自毀連動）(FT-09, FT-11)
- [x] **TASK-09**：實作 Server CLI 管理指令 `source/server/scripts/cli.py` (start/stop/status/reload)
- [x] **TASK-10**：改裝 `ys_codebase/yscb.py` 宿主入口（軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端）(FT-12)
- [x] **TASK-11**：撰寫沙盒整合測試套件 `source/server/tests/test_server.py` 並跑通全生態系測試
- [x] **TASK-12**：知識庫與模組文檔交付 (`docs/server/`, `docs/core/platform.md` 與 `CHANGELOG.md`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
