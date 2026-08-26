# 任務進度清單 (Task Tracking)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.0  

---

## 實作任務清單 (TODO Checklist)

- [x] **Task 1**：實作 `SemVer` 與 `VersionConstraint` 引擎 (`ys_codebase/source/core/scripts/semver.py`)
- [x] **Task 2**：實作鏈式線性增量遷移框架 `MigrationRunner` (`ys_codebase/source/core/scripts/migration.py`)
- [x] **Task 3**：擴充 `yscb_core.py` 與 `__init__.py` 導出公開介面與 `ProjectContext.get_module_version()`
- [x] **Task 4**：擴充 `yscb_installer.py` (相依約束檢查、5 階段事務升級流水線、快照備份與 Rollback、2x2 配置與文檔安全保護)
- [x] **Task 5**：擴充 CLI 路由器子指令 (`ys_codebase/source/core/scripts/cli.py` & `ys_codebase/yscb_cli.py` 新增 `version status/check/check-update/bump`)
- [x] **Task 6**：擴充 `verify_plan.py` 抽象外掛式 Hook (`ys_codebase/source/agents-workflow/scripts/verify_plan.py`)
- [x] **Task 7**：建立專案特化發布守門腳本與更新 SOP 擴充 (`extensions/dogfooding_pipeline_verify.py` & `extensions/dogfooding_pipeline_ext.md`)
- [x] **Task 8**：撰寫單元測試 (`test/test_semver.py`, `test/test_migration.py`) 並執行 Dogfooding 四步閉環流水線 (Build ➔ Regression ➔ Sync)
- [x] **Task 9**：實作 Installer 自舉升級 (`installer self-update`)、原子安全替換與起手腳本版本狀態檢測 (`ys_codebase/yscb_installer.py` & `ys_codebase/yscb_cli.py`)

---

## 偏差記錄表 (Deviations)

| 等級 | 偏差內容 | 處理方式 |
| :--- | :--- | :--- |
| *（本次實作無架構或規範偏差）* | | |

---

### Extension: dogfooding_pipeline_ext 執行檢核表
| 檢查項目 | 狀態 | 發現與備註 |
|:---|:---:|:---|
| Stage 1: 源碼空間修改 (ys_codebase/source/) | ✅ | 100% 於 source/ 與 yscb_*.py 修改，並將 core 遞進至 v2.1.0、agents-workflow 遞進至 v1.0.1 |
| Stage 2: 模組打包構建 (build) | ✅ | python yscb_cli.py installer build --all 順利產出 |
| Stage 3: 全量回歸測試 (test) | ✅ | python test/run_regression.py 35/35 單元測試 + E2E 下游沙盒 100% Passed |
| Stage 4: 自引用同步 (install/ide) | ✅ | modules/ 強制覆蓋安裝完成，三態矩陣均為 [SYNCED]，IDE workflows 已更新 |
