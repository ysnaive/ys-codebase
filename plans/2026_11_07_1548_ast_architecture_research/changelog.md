# 計畫變更紀錄 (Changelog)

> 功能名稱：AST 模組正交化重構與全倉符號 SSOT 架構深度調研  
> 建立日期：2026-11-07  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 變更紀錄

| 日期時間 | 類型 | 模型 | 摘要 |
| :--- | :---: | :--- | :--- |
| 2026-11-09 03:35 | `PHASE` | Gemini 4 Argon (Low) | 完成子計畫 sub_02 (4-Pass Linker & WorkspaceSymbolGraph) 結案並更新里程碑 2 |
| 2026-11-09 02:42 | `PHASE` | Gemini 4 Argon (Low) | 啟動子計畫 sub_02_deterministic_linker_and_workspace_graph 並完成 P00_discuss.md 定案 |
| 2026-11-08 13:56 | `PHASE` | Gemini 4 Argon (Low) | 完成里程碑 1 (sub_01) 結案 |
| 2026-11-08 12:44 | `PHASE` | Gemini 4 Argon (Low) | 更新 umbrella_overview.md 狀態為 In Progress 並啟動 sub_01_atomic_schema_and_commutative_extractor |
| 2026-11-08 12:39 | `PHASE` | Gemini 4 Argon (Low) | 將計畫原地升級為 Umbrella 分階段主計畫，建立 umbrella_overview.md 並規劃 sub_01 ~ sub_03 三大子計畫 |
| 2026-11-07 16:43 | `PHASE` | Gemini 3.1 Pro | 定案 AST 貢獻規則直接引用 `core.space`（預設 `project://` 全掃描），更新 `R01` 並完成第三大項調研報告 `R03_graph_primitives_incremental_cache_and_kdb_contract.md`（狀態 `Concluded`） |
| 2026-11-07 16:29 | `PHASE` | Gemini 3.1 Pro | 完成第二大項跨檔語意連結與全倉圖譜組裝調研報告 `R02_cross_file_linking_and_workspace_graph.md`（狀態 `Concluded`），並推進至第三大項討論 |
| 2026-11-07 16:26 | `PHASE` | Gemini 3.1 Pro | 於 `R01` 增補原生相容 Tree-sitter 官方 `queries/tags.scm` 標準與伴隨 `.scm` 平權合流架構，免除各語言基礎規則手寫維護負擔 |
| 2026-11-07 16:12 | `PHASE` | Gemini 3.1 Pro | 定案 `R01` 多 `.scm` 全平權一等公民（`kinds: FrozenSet[str]` 無主從之分）與 `@part.name` 錨點交換律合流機制，`R01` 標記為 `Concluded` 並推進至第二大項討論 |
| 2026-11-07 15:48 | `PHASE` | Gemini 3.1 Pro | 開立 AST 架構深度調研計畫，建立 `P00_discuss.md` 與第一大項原子符號定義調研報告 `R01_atomic_symbol_definition_and_contributes_boundary.md` |
