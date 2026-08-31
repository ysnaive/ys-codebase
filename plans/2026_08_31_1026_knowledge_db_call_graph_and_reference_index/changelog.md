# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-31 10:51 | `PHASE` | 完成 Phase 7 成果展示與結案報告 (P07_walkthrough.md)，核對三層知識庫文檔交付，追加全域 CHANGELOG.md，計畫結案 (狀態：`Completed`) |
| 2026-08-31 10:50 | `PHASE` | 開發者指示免測通過，Phase 6 測試狀態切換為 `PASSED`，推進至 Phase 7 |
| 2026-08-31 10:49 | `FEATURE` | 補齊其餘多語言解析器 (`CppParser`, `CSharpParser`, `JsTsParser`, `MarkdownParser`) 之 `extract_imports` 與 `extract_call_sites` 實作，新增 FT-08~11 測試，全量 125 項測試 100% 通過並物化安裝 |
| 2026-08-31 10:45 | `PHASE` | 完成 Phase 5 代碼實作與 TASK-01~07、TASK-DOC，全量 121 項測試 100% 通過，物化安裝至運行端，推進至 Phase 6 (狀態：`Testing`) |
| 2026-08-31 10:39 | `PHASE` | 推進至 Phase 5 (狀態：`In Progress`)，初始化 P05_task.md 任務清單，開始依拓撲順序編寫程式碼 |
| 2026-08-31 10:39 | `PHASE` | 推進至 Phase 4，完成實作計畫定稿 P04_implementation_plan.md 與 P06_test_plan.md (Confirmed) |
| 2026-08-31 10:39 | `PHASE` | 推進至 Phase 3，完成 API 與介面規格書 P03_api_spec.md (Confirmed) |
| 2026-08-31 10:39 | `PHASE` | 推進至 Phase 2，完成架構設計說明書 P02_architecture_plan.md (Confirmed) 與 P06 測試計畫初始化 (Draft) |
| 2026-08-31 10:36 | `PHASE` | 推進至 Phase 1，完成需求規格轉譯 P01_requirements_spec.md (狀態：`P01 Confirmed`, FR-01~06, EC-01~05, NFR-01~04) |
| 2026-08-31 10:28 | `RESEARCH` | 完成 R01 專題調研報告 (R01_knowledge_db_architecture_and_tokenizer.md)，深度剖析 CodeTokenizer 與 knowledge-db 七大子系統架構、JIT 熱自愈機制與對接點 |
| 2026-08-31 10:26 | `PHASE` | 由 Roadmap 轉化正式立項，開立計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing` $\rightarrow$ `Confirmed`, 分流：`Level 1 Full Track`) |
| 2026-08-31 10:26 | `DECISION` | [P00:DR-01] 確認採用方案 3 雙層複合式靜態 AST 符號調用拓撲架構；[P00:DR-02] 確立 `SymbolCallSite` 與 `CallGraphIndex` 雙向索引模型；[P00:DR-03] 確立 Level 1 Full Track 分流 |
| 2026-08-31 10:26 | `CONTEXT` | 完成長期技術儲備庫清理：移除已立項之 `knowledge_db_call_graph_and_reference_index.md` 與已結案之 `knowledge_db_performance_and_memory_optimization.md` |
