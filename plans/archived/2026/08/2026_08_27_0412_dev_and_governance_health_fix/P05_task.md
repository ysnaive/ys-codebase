# 實作任務清單 (Task Breakdown)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `source/agents-workflow/agents_workflow/plans/verifier.py`，擴充 Header 別名集合並完善標頭檢查邏輯。
- [x] **TASK-02**：更新 `source/dev/tests/test_builder.py`，改採動態版本解算驗證 `build_module` 與 `index.json`。
- [x] **TASK-03**：更新 `source/dev/tests/test_release_pipeline.py`，改採動態版本解算驗證 release 打包與 Gate 2/3 守門。
- [x] **TASK-04**：更新 `source/dev/tests/test_sandbox.py`，改採動態版本解算驗證 `hook.dev.py` 保留性。
- [x] **TASK-05**：更新專案根目錄 `docs/README.md`，登載 `agents-workflow` 模組與校準全系統版本清冊。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
