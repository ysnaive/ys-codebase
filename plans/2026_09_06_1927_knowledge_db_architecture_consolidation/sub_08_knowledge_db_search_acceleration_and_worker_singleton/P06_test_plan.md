# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 Worker `_module_cache`：連續兩次調用同模組，第二次直接命中快取，不重複執行 `exec_module` | FR-01 | `python yscb.py dev test server` |
| **FT-02** | 單元測試 | 驗證 `KnowledgeEngine` 單例化：`get_engine()` 多次調用返回同一實例物件 | FR-02 | `python yscb.py dev test knowledge-db` |
| **FT-03** | 單元測試 | 驗證 `core.events` 廣播 `worker_warming`，成功觸發 `hook.server.py:on_worker_warming` 並調用 `pre_warm()` | FR-03 | `python yscb.py dev test server` |
| **FT-04** | 單元測試 | 驗證 Watcher Dirty Flag：未標記 dirty 時，`pipeline.search()` 0ms 跳過 stat 走訪 | FR-04 | `python yscb.py dev test knowledge-db` |
| **FT-05** | 單元測試 | 驗證 `core.contributes.get("server")` 成功解析 `contributes/server.json` 並動態註冊 ServiceWorker | FR-05 | `python yscb.py dev test server` |
| **FT-06** | 單元測試 | 驗證 `server status` 回傳格式中包含 Background Services 清冊與健康狀態 | FR-06 | `python yscb.py dev test server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_worker_module_cache` 通過：二度調用直接命中快取，執行次數記憶體自增 | 2026-09-07 06:34:32 |
| **FT-02** | `Passed` | `test_singleton_engine` 通過：`get_engine()` 返回同一實例物件 | 2026-09-07 06:35:18 |
| **FT-03** | `Passed` | `test_worker_warming_event` 通過：`WarmWorker.pre_warm()` 成功廣播預熱事件 | 2026-09-07 06:34:32 |
| **FT-04** | `Passed` | `test_watcher_dirty_flag_stat_bypass` 通過：無 dirty flag 時 0ms 略過 stat 走訪 | 2026-09-07 06:35:18 |
| **FT-05** | `Passed` | `test_service_manager_metadata_and_status` 通過：動態註冊並記錄 provider/description | 2026-09-07 06:34:32 |
| **FT-06** | `Passed` | `test_service_manager_metadata_and_status` 通過：狀態回傳 Background Services 完整健康狀態 | 2026-09-07 06:34:32 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 啟動 Server 後執行 `python yscb.py server status`，輸出應包含 Background Services 列表（如 `[knowledge-db-watcher] (module: knowledge-db) : RUNNING`） | `[測試通過]` | 開發者實機驗收確認通過 (Background Services 正常運行且狀態可觀測) |
| **UX-02** | 實測 `python yscb.py knowledge-db search "pipeline" --lexical-only` 與混合搜尋，第二次起響應時間穩定落在 sub-50ms | `[測試通過]` | 開發者實機驗收確認通過 (搜尋極速瞬發，status 經由 _include_cache 加速至 14ms) |
