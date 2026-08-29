# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_thesaurus_pool_decoupling_and_enrichment  
> 建立日期：2026-08-30  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/contributes/knowledge-db.json` 建立完整六大維度初始詞彙庫（日用語、C/C++、C#、Python、SPICE、資電學系）。
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/thesaurus.py` 徹底移除 `BUILTIN_THESAURUS`，將 `ThesaurusEngine` 重構為純容器。
- [x] **TASK-03**：在 `source/knowledge-db/knowledge_db/space.py` 實作 `create_thesaurus_engine()` 工廠方法。
- [x] **TASK-04**：在 `source/knowledge-db/tests/test_thesaurus_decoupling.py` 編寫單元測試覆蓋 FT-01~FT-04 與 ET-01~ET-03。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
