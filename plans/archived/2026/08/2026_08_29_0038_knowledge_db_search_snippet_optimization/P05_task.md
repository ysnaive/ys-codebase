# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/knowledge_db/retrieval.py` 實作 `CodeSnippet` 與 `SnippetExtractor`，並擴充 `SearchResult.code_snippet`。
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/engine.py` 更新 `KnowledgeEngine.search` 支援 `snippet` 參數與路徑正規化。
- [x] **TASK-03**：在 `source/knowledge-db/scripts/cli.py` 新增 `--snippet` / `-s` / `--preview` 解析與終端多行代碼排版渲染。
- [x] **TASK-04**：更新 `KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 與 `contributes/core.json` 注入資產。
- [x] **TASK-05**：在 `source/knowledge-db/tests/test_retrieval.py` 與 `test_cli.py` 新增完整單元測試與邊界測試（FT-01~06, ET-01~04）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 嚴格依拓撲進行實作 |
