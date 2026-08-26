# 任務進度清單 (Task Tracking)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：none (本計畫產出 dogfooding_pipeline_ext)  
> 模板版本：v1.0  

---

## 實作任務清單 (TODO Checklist)

- [x] **Task 1**：建立 Dogfooding 專案特化擴充文件 (`extensions/dogfooding_pipeline_ext.md` & `ys_codebase/source/agents-workflow/workflows/extensions/dogfooding_pipeline_ext.md`)
- [x] **Task 2**：更新 `Review.md` 規範 (`ys_codebase/source/agents-workflow/workflows/Review.md`)
- [x] **Task 3**：更新 `DocumentationStandards.md` 規範 (`ys_codebase/source/agents-workflow/workflows/DocumentationStandards.md`)
- [x] **Task 4**：更新 `NewPlan.md` 規範 (`ys_codebase/source/agents-workflow/workflows/NewPlan.md`)
- [x] **Task 5**：更新 `AGENTS.template.md` 範本 (`ys_codebase/source/agents-workflow/workflows/templates/AGENTS.template.md`)
- [x] **Task 6**：加固 `verify_plan.py` 檢查邏輯 (`ys_codebase/source/agents-workflow/scripts/verify_plan.py`)
- [x] **Task 7**：更新根目錄 `AGENTS.md` 行為準則 (`AGENTS.md`)
- [x] **Task 8**：更新知識庫全域指南與說明 (`docs/_project/CONTRIBUTING.md` & `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md`)
- [x] **Task 9**：執行 Dogfooding Stage 2 打包構建 (`python yscb_cli.py installer build --all`)
- [x] **Task 10**：執行 Dogfooding Stage 3 全量回歸測試 (`python test/run_regression.py` - 23/23 + E2E 100% Passed)
- [x] **Task 11**：執行 Dogfooding Stage 4 自引用同步 (`installer install --all --force` + `agents-workflow --ide-antigravity`)

---

## 偏差記錄表 (Deviations)

| 等級 | 偏差內容 | 處理方式 |
| :--- | :--- | :--- |
| `Minor` | `cli.py` 在 `discover_all_extensions` 中原本未調用 `get_extensions_dir` 解析 `project://` 語意 URI | 更新 `cli.py` 調用 `get_extensions_dir(MODULE_DIR)` 正確解析 `sop_ext://` |

---

### Extension: dogfooding_pipeline_ext 執行結果
| 檢查項目 | 狀態 | 發現與備註 |
|:---|:---:|:---|
| Stage 1: 源碼空間確認 (ys_codebase/) | ✅ | 100% 於 source 目錄進行修改，無 modules/ 直修 |
| Stage 2: 模組打包構建 (build) | ✅ | build/ 目錄產物已重新生成 |
| Stage 3: 全量回歸測試 (test) | ✅ | python test/run_regression.py 23/23 + E2E 100% 通過 |
| Stage 4: 自引用同步 (install/ide) | ✅ | modules/ 已強制覆蓋安裝，IDE 指令已重新生成 |
**結論**：已通過 Dogfooding 自引用標準四步流水線驗收。
