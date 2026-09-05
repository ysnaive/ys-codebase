# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告 `fastembed` pip 相依，並安裝至微環境
- [x] **TASK-02**：重構 `knowledge_db/tokenizer.py`，實作 `MultilingualTokenizer`，支援中英混雜與駝峰蛇形拆解
- [x] **TASK-03**：新建 `knowledge_db/embedding.py`，實作 `EmbeddingService` 與 Mock 向量機制，支援向量推論與快取
- [x] **TASK-04**：新建 `knowledge_db/hybrid.py`，實作 `HybridSearchEngine` 與標準 RRF 倒數排名融合演算法
- [x] **TASK-05**：徹底刪除舊同義詞庫檔案 `knowledge_db/thesaurus.py` 與 `tests/test_thesaurus.py`
- [x] **TASK-06**：修改 `knowledge_db/engine.py`，整合複合檢索流水線與 `--lexical-only` 命令列旗標
- [x] **TASK-07**：編寫單元與整合測試 (`test_tokenizer.py`, `test_hybrid.py`)，驗證 RRF 融合與 100% 降級防護
- [x] **TASK-08**：跑測全套單元測試與生態系回歸測試 (`dev test knowledge-db --quiet`)
- [x] **TASK-DOC**：同步更新 `README.md`、`docs/` 專題手冊與代碼 Docstring 註解

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
