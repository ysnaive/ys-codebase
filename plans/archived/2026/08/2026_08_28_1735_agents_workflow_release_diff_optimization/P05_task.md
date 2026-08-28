# 實作任務清單 (Task Breakdown)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/agents-workflow/agents_workflow/publisher.py` 中實作 `compute_source_fingerprint()`。
- [x] **TASK-02**：在 `publisher.py` 中重構 `_soft_merge_agents_md()` 支援 Diff 檢測與 `(success, written)` 回傳。
- [x] **TASK-03**：在 `publisher.py` 中重構 `release_all()` 支援 Stage 0 短路、Stage 4 內容比對、`force` 旗標與完整指標回傳。
- [x] **TASK-04**：在 `source/agents-workflow/scripts/cli.py` 中擴充 `release` 指令支援 `--force` 參數。
- [x] **TASK-05**：在 `source/agents-workflow/scripts/hook.core.py` 中更新 `on_reload` 日誌輸出。
- [x] **TASK-06**：撰寫 `source/agents-workflow/tests/test_publisher.py` 完整覆蓋 FT-01~06 與 ET-01~03。
- [x] **TASK-07**：實機執行全模組測試 `python yscb.py dev test agents-workflow` 與 `dev test --all` (163/163 Passed)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依據 P03/P04 規格實作 |
