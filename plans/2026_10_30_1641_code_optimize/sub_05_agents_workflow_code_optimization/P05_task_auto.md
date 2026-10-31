# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.0  
---
## 1. 實作任務清單 (Task Breakdown)
- [x] **TASK-01**：見 P04 §4（`plans/_common.py` 共用基底與 `plans/__init__.py` PEP 562 延遲匯入）
- [x] **TASK-02**：見 P04 §4（`compiler.py`, `targets.py`, `publisher.py`, `initializer.py` 清除死碼、解循環與遷移 `vfs.<io>`）
- [x] **TASK-03**：見 P04 §4（`plans/verifier.py` 拆分為 `_verifier_specs.py`, `_verifier_healer.py` 與 `verifier.py`）
- [x] **TASK-04**：見 P04 §4（`plans/session_trace.py` 拆分為 `_trace_parser.py`, `_trace_renderer.py` 與 `session_trace.py`）
- [x] **TASK-05**：見 P04 §4（`scanner`, `status`, `archiver`, `searcher`, `roadmap`, `cli.py`, `core.json` 與 `tests/` 更新）
- [x] **TASK-06**：見 P04 §4（`R02` 缺陷修復與 14 處 `Mode A` 殘留單行轉發包裝清除及測試同步對齊）

## 2. 實作偏差紀錄表 (Implementation Deviations)
| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
