# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `knowledge_db/formatter.py`（含 `UniversalRedundancyFilter`、8,000 字元預算動態衰減計算器、`ResultFormatter`）
- [x] **TASK-02**：實作 `knowledge_db/pipeline.py`（含 `IndexingPipeline` 多空間倒排與向量索引建置、JIT 增量嗅探與快取管理）
- [x] **TASK-03**：重構 `knowledge_db/engine.py` 瘦身為輕量 Facade（目標 $\le 450$ 行，實作 338 行），委派 pipeline 與 formatter，維持 100% 既有 Public API 簽名與常數匯出
- [x] **TASK-04**：擴充 `tests/test_engine.py` 單元測試（涵蓋全域去重、8,000 字元預算衰減與 IndexingPipeline），執行 `python yscb.py dev test knowledge-db --quiet` 驗證全套件 100% 通過（123/123 Passed、0 回歸、0 Unknown）
- [x] **TASK-05**：實機核驗 CLI 契約（`search`、`callers`、`callees`、`impact`、`status`）純文字與 `--json` 格式完整性
- [x] **TASK-06**：執行 `python yscb.py install knowledge-db@build --force` 完成本地物化更新與真實代碼庫檢索端到端閉環
- [x] **TASK-07**：實作索引建置防護與效能優化（[P06:DR-01]）：限制 ONNX 執行緒上限、分批推論與時間片讓渡、VectorIndex 寫盤降級至 compresslevel=1、Worker 內 ParserRegistry 快取化、調用點 AST 重用避免二次解析
- [x] **TASK-DOC**：更新 `docs/knowledge-db/README.md`、登記 `docs/knowledge-db/DESIGN_NOTES.md` (DN-12) 與全域 `CHANGELOG.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-07** | `Minor` | Phase 6 實機測試發現大量符號向量嵌入與重複 AST 解析致系統負載過重 | 觸發 `/Discuss` 決策 [P06:DR-01]，補齊防禦性執行緒上限、分批讓渡與單例快取 |
