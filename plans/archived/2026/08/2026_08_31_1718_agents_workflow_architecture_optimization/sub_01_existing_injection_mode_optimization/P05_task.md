# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `source/agents-workflow/contributes/agents-workflow.json` 與 `contributes.format.md`，為 `antigravity`、`claude`、`codex` 加入 `agents_md` 宣告。
- [x] **TASK-02**：更新 `source/agents-workflow/agents_workflow/initializer.py`，移除 `enable_agents_md` 預設組態寫入。
- [x] **TASK-03**：重構 `source/agents-workflow/agents_workflow/publisher.py`：
  - 實作 `_soft_merge_agents_text` 純文字演算法。
  - 將 Target 之 `agents_md` 納入 Stage 0 指紋計算。
  - 改造 Stage 2 / Step 4 軟合併邏輯與雙軌 Manifest 追蹤，移除 `enable_agents_md` 讀取邏輯。
- [x] **TASK-04**：更新單元測試套件 `source/agents-workflow/tests/test_publisher.py` 與 `test_targets.py`，覆蓋 FT-01~05、FT-07~09、ET-01~02。
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/` 下的文檔手冊。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
