# 實作任務清單 (Task Breakdown)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/dev/dev/checker.py` 實作 `_check_pip_dependencies` 並整合至 `_check_manifest`
- [x] **TASK-02**：在 `source/dev/dev/testing/sandbox.py` 實作 `adapt_build_pip_dependencies` 與 `_project_venv`
- [x] **TASK-03**：在 `create_sandbox` 與 `cleanup_sandbox` 中整合微環境投影與安全斷開防護
- [x] **TASK-04**：在 `source/dev/tests/test_pip_adaptation.py` 撰寫單元與整合測試 (FT-01~04, ET-01~02)
- [x] **TASK-05**：執行自動化測試驗證 (`python yscb.py dev test dev --quiet`)
- [x] **TASK-DOC**：同步更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
