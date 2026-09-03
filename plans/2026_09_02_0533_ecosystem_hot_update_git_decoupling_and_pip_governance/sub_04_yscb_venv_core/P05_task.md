# 實作任務清單 (Task Breakdown)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新基礎協議與忽略規則（`yscb.py` 注入 `/.venv/`、`STANDARDS.md`、`contributes/core.json`、`core/uri.py`）
- [x] **TASK-02**：實作 `source/core/core/pip_manager.py`（`PipManager` 與 `PipInstallError`）
- [x] **TASK-03**：實作 `source/core/core/ide_projector.py`（`IdeProjector` 與 `_yscb_managed` 可復原軟合併）
- [x] **TASK-04**：宿主動態注入與還原管線對接（`yscb.py` 之 `_ensure_private_venv_path` 與 `cmd_restore`）
- [x] **TASK-05**：安裝器對接（`source/core/core/installer.py` 解析 `pip_dependencies` 並物化）
- [x] **TASK-06**：編寫單元測試套件 `source/core/tests/test_venv_core.py` 並實機執行回歸跑測
- [x] **TASK-DOC**：更新 `docs/_project/STANDARDS.md` 與 `docs/core/README.md`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (100% 符合 P01~P04 規格) | - |
