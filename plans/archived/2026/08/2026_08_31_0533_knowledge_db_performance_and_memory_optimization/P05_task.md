# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Completed  

> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`CodeTokenizer` Unicode 整數比對、預編譯正則與 `@lru_cache` 實作 (`knowledge_db/tokenizer.py`)
- [x] **TASK-02**：`Posting` `__slots__` 資料結構重構與內部 `field_lengths` 移除 (`knowledge_db/schema.py` / `knowledge_db/retrieval.py`)
- [x] **TASK-03**：`InvertedIndex.doc_lengths` 頂層共享池、增量打補丁維護與舊版快取自省升級實作 (`knowledge_db/retrieval.py`)
- [x] **TASK-04**：`ThesaurusEngine` 加權展開 LRU 快取實作 (`knowledge_db/thesaurus.py`)
- [x] **TASK-05**：`SemanticBundler` 動態門檻多進程並發解析 AST 實作 (`knowledge_db/bundler.py`)
- [x] **TASK-06**：`InvertedIndex.search` BM25 評分結合頂層 `doc_lengths` 與高效能檢索實作 (`knowledge_db/retrieval.py`)
- [x] **TASK-07**：新增效能與記憶體基準測試套件 `test_benchmark_perf_and_memory.py` (`tests/`)
- [x] **TASK-08**：執行全量自動化跑測與靜態合規性檢核 (`dev test knowledge-db` & `dev check knowledge-db`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無重大架構偏差，所有變更 100% 符合 P01~P04 規格。 | 順利推進至 Phase 6 |
