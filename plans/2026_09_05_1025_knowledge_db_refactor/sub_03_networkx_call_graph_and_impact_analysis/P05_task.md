# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：In Progress  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `manifest.json` 加入 `networkx` 依賴並確保微環境相容
- [x] **TASK-02**：實作 `knowledge_db/selector.py` 全方位符號選擇器解析器與比對器
- [x] **TASK-03**：實作 `knowledge_db/protocol.py` 多語言調用拓撲協議
- [x] **TASK-04**：重構 `knowledge_db/graph.py`，以 `networkx.DiGraph` 實現圖儲存、持久化與高精度 `query_impact`
- [x] **TASK-05**：重構 `knowledge_db/linker.py`，導入 FQN 與階層作用域消歧杜絕幽靈關聯
- [x] **TASK-06**：擴充 `scripts/cli.py` 支援選擇器語法
- [x] **TASK-07**：編寫 `test_selector.py` 與 `test_networkx_graph.py` 並回歸既有測試 (132/132 100% 通過)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
