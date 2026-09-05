# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Passed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告新增 `"watchdog": ">=4.0.0"` 依賴。
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/config.py` 實作 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec` 組態及型態防禦，並實作啟用 Server 時 JIT 設定全面失效。
- [x] **TASK-03**：新建 `source/knowledge-db/knowledge_db/daemon.py`，實作 `HotReloadServer`、動態 Space Watcher 監控、500ms 防抖熱修補、PID(含空間簽名) 寫入 `cache://`、空間/版本失配強制重啟、啟動離線預檢與閒置超時自動退出。
- [x] **TASK-04**：新建 `source/knowledge-db/scripts/hook.core.py`，實作 `on_pre_cli_dispatch` 生命週期勾點（支援版本/空間簽名比對與自動拉起）。
- [x] **TASK-05**：在 `source/knowledge-db/scripts/cli.py` 註冊 `knowledge-db daemon [start|stop|status|watch]` 子命令，並在查詢類指令中探測後台 Server 提示跳過 JIT。
- [x] **TASK-06**：編寫單元與整合測試套件 `tests/test_hot_reload_server.py`，覆蓋 FT-01~16 與 EC-01~11。
- [x] **TASK-07**：執行全模組回歸驗證（`python3 yscb.py dev test -m knowledge-db`），確保 100% 通過且 0 Unknown (148/148 Passed)。
- [x] **TASK-08**：全面重構 Contributes 體系關聯邏輯：ParserRegistry 暴露 `get_supported_extensions()`；Daemon 實裝 `resolve_watch_extensions` 與 `is_path_watched` Space 雙軌過濾；SpaceManager 修復專案 `contribute.json` 階層合併。
- [x] **TASK-09**：補齊標準 `configurable/config.project.json` 與 `configurable/config.local.json` 模板檔案，落實 Core Engine 自動 deep_infill 部署到 `config://knowledge-db/`，並補齊單元測試。
- [x] **TASK-10**：在 `source/core/core/engine.py` 優化 `_deep_infill_dict`、`_seed_or_update_config` 與 `act_deploy_configs_from_modules`，實裝 local 軟合併時跳過 project 既有設定之過濾機制，並於 `tests/test_engine.py` 增補 FT-17 單元測試。
- [x] **TASK-DOC**：更新 `docs/knowledge-db/DESIGN_NOTES.md` (`[DN-15]`, `[DN-16]`) 與 `docs/knowledge-db/README.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (100% 依循 P01/P03/P04 規格落實) | - |
