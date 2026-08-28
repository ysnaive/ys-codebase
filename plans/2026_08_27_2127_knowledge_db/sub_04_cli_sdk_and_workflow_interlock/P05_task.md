# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Completed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-00 (本地端快取儲存遷移)**：修改 `source/knowledge-db/knowledge_db/space.py`、`manifest.json`、`scripts/hook.dev.py`，將存儲根目錄全面切換至 `cache://knowledge-db/`，並清理舊 `storage/knowledge-db/`。
- [x] **TASK-01 (統一門面 SDK 實作)**：實作 `source/knowledge-db/knowledge_db/engine.py` (`KnowledgeEngine`)。
- [x] **TASK-02 (模組自治 Hook 實作)**：實作 `source/knowledge-db/scripts/hook.dev.py` (`on_test_setup`, `on_test_teardown`)。
- [x] **TASK-03 (CLI 完整指令與導出更新)**：更新 `source/knowledge-db/scripts/cli.py`（6 大指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [x] **TASK-04 (測試套件路徑更新與回歸驗證)**：更新 `test_space.py`、`test_cli.py` 等測試案例中路徑斷言，實機跑測 FT-01~11 與 RT-01 全數通過。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依循 P04 拓撲實作完成 |
