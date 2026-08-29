# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `source/knowledge-db/knowledge_db/space.py`，移除 `_get_storage_root()` 本地相對路徑 Fallback，實施零 Fallback 異常拋出。
- [x] **TASK-02**：於 `source/knowledge-db/knowledge_db/engine.py` 實作 `to_file_uri()` 與 `format_file_link()` 方法。
- [x] **TASK-03**：重構 `source/knowledge-db/scripts/cli.py` 中 `search` 簡易模式、詳細模式、預覽模式與 JSON 模式，全面輸出 Markdown 連結。
- [x] **TASK-04**：更新並擴充 `test_space.py`、`test_engine.py` 與 `test_cli.py` 單元測試套件。
- [x] **TASK-05**：實機執行 `python yscb.py dev test knowledge-db` 與全量跑測，確認 100% Passed。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依據 P04 拓撲完成實作與測試驗證 |
