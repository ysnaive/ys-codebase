# 實作任務清單 (Task Breakdown)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/core/core/pip_manager.py` 實作 `PipManager.parse_pip_dependencies` 靜態方法
- [x] **TASK-02**：在 `source/core/core/__init__.py` 匯入並將 `PipManager`、`PipInstallError` 加入 `__all__`
- [x] **TASK-03**：在 `source/core/core/installer.py` 重構 `sync_pip_dependencies` 改用標準解析方法
- [x] **TASK-04**：編寫 `source/core/tests/test_pip_manager_sdk.py` 單元測試覆蓋 FT-01~04 與 ET-01~02
- [x] **TASK-05**：執行自動化測試驗證 (`python yscb.py dev test core --quiet`)
- [x] **TASK-DOC**：同步更新 `source/core/README.md`、`docs/core/API_REFERENCE.md` 與 `docs/core/DESIGN_NOTES.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
