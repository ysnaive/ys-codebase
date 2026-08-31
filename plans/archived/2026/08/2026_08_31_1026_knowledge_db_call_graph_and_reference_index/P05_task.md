# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `schema.py` 實作 `SymbolCallSite` 與 `CallGraphNode` 資料結構模型 (FR-01)。
- [x] **TASK-02**：在 `parsers/base.py` 與 `parsers/python_parser.py` 實作 `CallSiteVisitor`、`ScopeStack` 與調用點/import 提取 (FR-02)。
- [x] **TASK-03**：新增 `linker.py`，實作 `TopologyLinker` 四階消歧鏈接演算法 (FR-03)。
- [x] **TASK-04**：新增 `graph.py`，實作 `CallGraphIndex` 雙向圖索引、整數池化、Gzip 二進位快取與 JIT 增量修補 (FR-04, FR-05)。
- [x] **TASK-05**：在 `engine.py` 整合 `act_callers`、`act_callees`、`act_impact` 與 JIT 變更嗅探流水線 (FR-06)。
- [x] **TASK-06**：在 `cli.py` 擴充 `callers`、`callees`、`impact` CLI 指令與 RFC 8089 輸出 (FR-06)。
- [x] **TASK-07**：編寫完整單元測試套件 `tests/test_call_graph.py` 並通過沙盒跑測 (FT-01~07, ET-01~02, PT-01, RT-01)。
- [x] **TASK-REV**：增量精修全套檢索指令 (`search`, `callers`, `callees`, `impact`) 輸出格式、正交模式、3500 字元預算與 `--json` 精簡完備重構。
- [x] **TASK-DOC**：同步更新 `docs/knowledge-db/` 模組手冊、專題手冊與 `DESIGN_NOTES.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
