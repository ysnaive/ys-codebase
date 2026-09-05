# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_04_test_suite_aggregation_and_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：整併圖譜測試套件 (`test_call_graph.py` + `test_networkx_graph.py` ➔ `test_graph.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [x] **TASK-02**：整併解析器測試套件 (`test_spice_parser.py` + `test_web_parsers.py` ➔ `test_parsers.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [x] **TASK-03**：整併檢索與聚合測試套件 (`test_search_aggregation.py` + `test_tokenizer.py` + `test_hybrid.py` ➔ `test_retrieval.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [x] **TASK-04**：整併熱重載與 JIT 修復測試套件 (`test_incremental_hot_reload.py` + `test_jit_hot_healing.py` ➔ `test_hot_reload.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [x] **TASK-05**：整併空間與 Provider 測試套件 (`test_providers.py` ➔ `test_space.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [x] **TASK-06**：為重型套件 (`test_engine.py`, `test_scanner.py`, `test_bundler.py`) 標註 `@require(Requirement.WORKFLOW)`，為 `test_benchmark_perf_and_memory.py` 標註 `@require(Requirement.PERF)`，並補齊現存全測試之 `self.mark_passed()`
- [x] **TASK-07**：清理舊測試之 `__pycache__`，執行 `dev test knowledge-db --quiet` 驗證 100% 通過、0 Unknown、0 Fail
- [x] **TASK-DOC**：更新 `docs/knowledge-db/README.md`、`docs/knowledge-db/DESIGN_NOTES.md` (登記 DN-11) 與 `CHANGELOG.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
