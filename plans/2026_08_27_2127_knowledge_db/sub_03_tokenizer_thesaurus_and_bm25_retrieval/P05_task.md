# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：In Progress  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (混合分詞器實作)**：實作 `source/knowledge-db/knowledge_db/tokenizer.py` (`CodeTokenizer`)。
- [x] **TASK-02 (雙層同義詞引擎實作)**：實作 `source/knowledge-db/knowledge_db/thesaurus.py` (`ThesaurusEngine`)。
- [x] **TASK-03 (倒排索引與 BM25 評分引擎實作)**：實作 `source/knowledge-db/knowledge_db/retrieval.py` (`InvertedIndex`, `BM25Engine`, `QueryFilter`, `SearchResult`)。
- [x] **TASK-04 (入口與元數據更新)**：更新 `source/knowledge-db/scripts/cli.py`（擴充 `search` 指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [x] **TASK-05 (單元測試套件)**：實作 `tests/test_tokenizer.py`、`tests/test_thesaurus.py` 與 `tests/test_retrieval.py`，驗收 FT-01~07、ET-01 與 RT-01。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
