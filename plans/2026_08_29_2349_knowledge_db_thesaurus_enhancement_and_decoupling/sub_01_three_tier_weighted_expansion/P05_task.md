# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/knowledge_db/schema.py` 定義 `WeightedToken` 與升級 `ThesaurusConfig`（支援 `aliases` 與 `related`）。
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/thesaurus.py` 實作 `ThesaurusEngine` 三階加權展開、別名與關聯詞擴展方法。
- [x] **TASK-03**：在 `source/knowledge-db/knowledge_db/space.py` 升級 `SpaceManager.load_thesaurus` 與 `load_thesaurus_config`。
- [x] **TASK-04**：在 `source/knowledge-db/knowledge_db/retrieval.py` 重構 `BM25Engine.search` 整合 Token 權重衰減計分。
- [x] **TASK-05**：在 `source/knowledge-db/tests/test_thesaurus_weighted.py` 編寫完整單元測試覆蓋 FT-01~FT-06 與 ET-01~ET-04。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
