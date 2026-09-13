# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：In Progress  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `source/knowledge-db/knowledge_db/embedding.py`，徹底淘汰 `DEFAULT_EMBEDDING_DIM`，落實以加載模型為 SSOT 之動態維度、`last_error` 與環境警告抑制
- [x] **TASK-02**：調整 `source/knowledge-db/knowledge_db/pipeline.py` 與 CLI 輸出，注入結構化診斷資訊
- [x] **TASK-03**：重構 `source/knowledge-db/tests/test_retrieval.py` 單元測試，移除過期常數並補齊 FT-10~13 測試案例
- [x] **TASK-DOC**：更新 `docs/knowledge-db/README.md` 補充環境指引

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
