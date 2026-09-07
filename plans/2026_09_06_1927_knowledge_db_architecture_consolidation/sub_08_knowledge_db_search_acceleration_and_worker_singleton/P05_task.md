# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Server 模組快取與預熱廣播)**：在 `source/server/server/worker.py` 實作 `_module_cache` 模組快取，並在 Worker 就緒後非同步調用 `core.events.broadcast("worker_warming", emit_module="server")`。
- [x] **TASK-02 (Server 動態發現與狀態擴充)**：在 `source/server/server/master.py` 透過 `core.contributes.get("server")` 動態載入 services；在 `source/server/server/service.py` 擴充元數據並在 `status` 呈現儀表板。
- [x] **TASK-03 (Knowledge-DB 服務宣告與預熱勾點)**：建立 `source/knowledge-db/contributes/server.json` 與 `source/knowledge-db/scripts/hook.server.py`，串接 `KnowledgeEngine.pre_warm()`。
- [x] **TASK-04 (Knowledge-DB 單例化與 Dirty Flag 整合)**：在 `source/knowledge-db/scripts/cli.py` 實作 `get_engine()` 單例；在 `source/knowledge-db/knowledge_db/pipeline.py` 整合 Watcher 事件驅動變更狀態，未變更 0ms 跳過 stat。
- [x] **TASK-05 (自動化與回歸測試驗證)**：執行 FT-01 ~ FT-06 單元測試與全生態系回歸測試，驗證檢索時間穩定壓在 sub-50ms。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-05** | Minor | `yscb.py` 擴充排除 `dev` 模組熱派發，防止測試執行時與常駐進程環境競爭 | 合規修復，確保 `dev test` 乾淨獨立運行 |
