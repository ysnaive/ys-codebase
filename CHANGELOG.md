# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

---

## 2026_08_23_0055_architecture_migration

### Added
- **Dogfooding 自引用 SOP 擴充**：新增 `extensions/dogfooding_pipeline_ext.md` 與源碼模板，定義 Stage 1~4（源碼空間 ➔ build ➔ regression ➔ install）全流程 Checkpoint。
- **Dogfooding 行為準則公理**：於 `AGENTS.md` 專案特化規範（第 4 節）寫入三層空間權限矩陣與標準四步閉環流水線。
- **知識庫定式工具庫指南**：於 `DocumentationStandards.md` 追加第 7 節「知識庫定式維護工具鏈」(`docs init/new-topic/audit`)。

### Changed
- **SOP NewPlan 雙星伴隨初始化**：修改 `NewPlan.md` Phase 0 步驟 1/2，強制規定開立計畫目錄時必須【同時】建立 `P00_semantic_requirements.md` 與 `changelog.md`，徹底消除時序滯後問題。
- **定式工具鏈指令聯動**：更新 `Review.md` 步驟 2 引入 `ext list/show`、步驟 3 引入 `docs audit`；更新 `AGENTS.md` 與 `AGENTS.template.md` 補齊定式作業 CLI 清單 (`<verify|scan|search|archive|docs|ext>`)。
- **知識庫手冊路徑更新**：更新 `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md` 與 `docs/_project/CONTRIBUTING.md` 為最新 `python yscb_cli.py` 路由器指令語法。

### Fixed
- **verify_plan.py 檢查盲區加固**：加固 `verify_plan.py`，移除 `changelog.md` 略過邏輯，改為嚴格檢查存在性與 Markdown 標題/表格格式。
- **CLI discover_all_extensions 語意 URI 解析修復**：修正 `cli.py` 中直接拼接 `Path(ext_setting)` 導致 `project://` URI 解析錯誤問題，統一改為調用 `get_extensions_dir` 解析。
