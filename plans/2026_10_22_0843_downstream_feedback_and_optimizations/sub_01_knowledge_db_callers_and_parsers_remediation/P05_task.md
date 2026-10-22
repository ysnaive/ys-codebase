# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充多語言 Tree-sitter 查詢檔（`c_sharp.scm`, `c.scm`, `cpp.scm`, `typescript.scm`, `javascript.scm`）與 `TreeSitterDriver`（`base_types` 萃取、C++ 類別外方法 `parent_scope`、鏈式/泛型/條件存取 `context_prefix` 提取與 `constructor`/`property` 作用域定位）
- [x] **TASK-02**：升級 `TopologyLinker`（多段式名稱之 `Class.Method` 雙段索引、Tier 1 無前綴隱式 `this` 與 `base_types` 繼承鏈查找、完整命名空間限定前綴尾段匹配、可調用符號遞迴自呼叫保留）
- [x] **TASK-03**：升級 `IndexingPipeline`、`KnowledgeEngine`、`scripts/cli.py` 與 `contributes/core.json`（修復 `callers --json` 之 `caller_symbol` 鍵名、實作介面/實作方法契約展開聚合、預設排除文檔節點並支援 `--ftype` 篩選）
- [x] **TASK-04**：編寫並執行單元與邊界測試（`test_graph.py`、`test_cli.py` 與全模組回歸測試）
- [x] **TASK-DOC**：同步更新 `docs/knowledge-db/` 專題手冊、模組手冊與微觀代碼 Docstrings

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
