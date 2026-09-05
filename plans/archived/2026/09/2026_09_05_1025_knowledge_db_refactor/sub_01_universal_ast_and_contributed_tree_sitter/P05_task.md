# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告 `pip_dependencies` (`tree-sitter` 等相依性)
- [x] **TASK-02**：重構 `knowledge_db/schema.py`，實作遞迴 `UnifiedSymbol` (FQN, parameters, search_payload) 與相容適配層
- [x] **TASK-03**：實作 `knowledge_db/parsers/base.py` 抽象介面與 `knowledge_db/parsers/treesitter.py` 通用驅動器
- [x] **TASK-04**：建立各語言 S-Expression 查詢規則資產 (`assets/queries/*.scm`)
- [x] **TASK-05**：重構 `knowledge_db/parsers/registry.py`，實作基於 `contributes` 的動態 `LanguageRegistry`
- [x] **TASK-06**：在 `contributes/knowledge-db.json` 宣告自身語言能力自貢獻 (Zero-Privilege Dogfooding)
- [x] **TASK-07**：徹底清理 `parsers/` 下手刻正則檔案，並改寫/清理 `tests/` 中的過時測試案例
- [x] **TASK-08**：跑測單元/邊界測試 (FT-01~07, ET-01~05) 並回填結果
- [x] **TASK-DOC**：同步更新 `README.md` 與代碼 Docstring 註解

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
