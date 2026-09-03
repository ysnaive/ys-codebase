# 實作任務清單 (Task Breakdown)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `yscb.py` 內部的 `_generate_internal_gitignore` 標記區塊，注入 `/.build/\n` 忽略規則 (FR-01)
- [x] **TASK-02**：更新 `yscb.py` 模組還原提取函式 `_restore_module_package`，將 `build_candidates` 優先探測路徑改為 `.build/` (FR-04)
- [x] **TASK-03**：更新 `source/core/contributes/core.json` 與 `source/core/core/uri.py`，將 `module.build` 空間協議預設解析值改為 `yscb://.build/` (FR-02)
- [x] **TASK-04**：檢視並更新 `source/dev/dev/builder.py`，確保 `Builder.build_package` 產物輸出路徑完全對齊 `module.build://`（即 `.build/`）(FR-03)
- [x] **TASK-05**：檢視並更新 `source/dev/dev/testing/sandbox.py`，確保沙盒環境套件覆蓋對齊 `module.build://` (FR-04)
- [x] **TASK-06**：更新最高工程規範 `docs/_project/STANDARDS.md` 空間協議表，政策修訂為 `🚫 忽略`，實體路徑改為 `yscb://.build/` (FR-05)
- [x] **TASK-07**：編寫單元測試套件 `source/core/tests/test_build_git_decoupling.py` (FT-01~FT-05, ET-01, PT-01)
- [x] **TASK-08**：Dogfooding 閉環驗證與全生態系回歸跑測 (RT-01, NFR-03) (305/305 通過)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
