# 計畫變更日誌 (sub_12_versioning_and_release_pipeline)

> 本日誌記錄 `sub_12` 計畫內部微觀狀態轉換、DR 決策與變更歷史。

---

## 2026-08-25

### Phase 0: 語意需求與技術調研
- **雙星初始化**：伴隨開立 [`P00_semantic_requirements.md`](./P00_semantic_requirements.md) 與本變更日誌。
- **R01 調研完備**：產出並收斂 [`R01_release_and_build_distinction_analysis.md`](./R01_release_and_build_distinction_analysis.md)，確立四段式版本號、雙軌來源庫、`build://index.json` 同構規範、同 `X.Y.Z` 單一 Revision 淘汰原則與常態三元安裝約定。
- **R02 調研完備**：產出並收斂 [`R02_release_cli_boundary_and_pipeline_analysis.md`](./R02_release_cli_boundary_and_pipeline_analysis.md)，確立 `dev release` CLI 規格、發布安全交易防護（原子回滾）、智慧 Tag 觸發矩陣與 Revision 淘汰清理。
- **R03 調研完備**：產出並收斂 [`R03_migration_mechanism_and_gitignore_boundary_analysis.md`](./R03_migration_mechanism_and_gitignore_boundary_analysis.md)，確立四大語意維度分析表、核心 Git 追蹤表、`yscb://.gitignore` 零污染生成、模組 Migration 階梯調用協定、同 Major 鎖定原則與 Snapshot 範圍矩陣。
- **Phase 0 結案**：使用者確認 P00 需求與 R01~R03 調研報告，正式選定 Level 1 (Full Track) 推進。

### Phase 1: 需求規格說明書
- **產出規格書**：產出 [`P01_requirements_spec.md`](./P01_requirements_spec.md)，包含 FR-01 ~ FR-13 十三項功能需求、EC-01 ~ EC-08 八項邊界防護處置與 NFR-01 ~ NFR-03 非功能需求。
- **Phase 1 結案**：通過可追溯性稽核，100% 映射 R01~R03 所有架構點，使用者確認通過。

### Phase 2: 架構設計方案
- **產出架構書**：產出 [`P02_architecture_plan.md`](./P02_architecture_plan.md)，包含模組拓撲圖、三大循序圖（發布流水線交易防護、`dev test` 全黑盒流水線、Migration 階梯調用流程）、受影響檔案矩陣與 `[P02:DR-01]` ~ `[P02:DR-09]` 決策清單。
- **Test-First 前置初始化**：隨設計同步初始化草擬 [`P06_test_plan.md`](./P06_test_plan.md)（含 8 項 FT、6 項 ET 與 RT-01 回歸測試）。
- **Phase 2 結案**：使用者確認通過。

### Phase 3: API 規格與介面合約說明書
- **產出 API 規格書**：產出 [`P03_api_spec.md`](./P03_api_spec.md)，包含四段式 SemVer 運算器介面、雙軌來源庫 URI 擴充、三層安裝降級鏈與 Migration 引擎介面、`dev.releaser` 發布流水線介面、8 步實作依賴拓撲圖與 7 大維度知識庫交付清單。
- **Phase 3 結案**：使用者確認通過。

### Phase 4: 實作計畫與測試定稿
- **產出實作計畫**：產出 [`P04_implementation_plan.md`](./P04_implementation_plan.md)，包含交叉審查核對清單、三大靈魂拷問防護解析、7 大維度文檔交付規劃、TASK-01 ~ TASK-09 實作矩陣與決策紀錄清單。
- **Test-First 剛性定稿**：與 Phase 4 一併將 [`P06_test_plan.md`](./P06_test_plan.md) 剛性定稿為 Confirmed。
- **Phase 4 結案**：使用者確認通過，授權進入 Phase 5 實作。

### Phase 5: 程式碼實作
- **全量實作完成**：完成 TASK-01 ~ TASK-09 所有代碼修改與單元測試建置。
- **Phase 5 結案**：使用者確認通過，授權進入 Phase 6 驗證。

### Phase 6: 測試驗證
- **全量自動化回歸測試 100% 綠燈**：實機執行 `python yscb.py dev test --all`，全模組 (core, dev) 70 項測試（Contract 6/6 + Custom 64/64）**100% Passed (70/70, 0 Failed, 0 Skipped)**。
- **Dogfooding 閉環同步完成**：執行 `python yscb.py reload` 完成運行空間重構與同步。
- **回填測試紀錄**：已將真實 Log 回填至 [`P06_test_plan.md`](./P06_test_plan.md)。
- **運行空間純粹化加固**：修復 `modules/core/` 殘留 `config.project.json` 模板問題，於物化安裝後自動剝除。
- **Phase 6 結案**：使用者實機審閱、執行環境遷移與 commit 斷點保護，核准通過。

### Phase 7: 結案審查與知識庫 1:1 交付
- **產出結案報告**：產出 [`P07_walkthrough.md`](./P07_walkthrough.md)。
- **7 大維度知識庫 1:1 全數交付**：
  - 更新 [`docs/core/SEMVER.md`](../../docs/core/SEMVER.md)（四段式 SemVer 規範說明書，維度 3）。
  - 新增 [`docs/core/MIGRATION_LADDER.md`](../../docs/core/MIGRATION_LADDER.md)（模組增量資料遷移與階梯調用手冊，維度 3）。
  - 更新 [`docs/core/DESIGN_NOTES.md`](../../docs/core/DESIGN_NOTES.md)（登記 `DN-09`, `DN-10`, `DN-11`，維度 5）。
  - 新增 [`docs/dev/RELEASE_PIPELINE.md`](../../docs/dev/RELEASE_PIPELINE.md)（開發者工具模組發布流水線手冊，維度 3）。
  - 更新 [`docs/dev/testing_guide.md`](../../docs/dev/testing_guide.md)（高階測試指令與全黑盒流水線說明，維度 3）。
  - 更新 [`project://CHANGELOG.md`](../../CHANGELOG.md)（追加 `sub_12` 高階版本摘要）。
- **更新主計畫狀態**：[`umbrella_overview.md`](../umbrella_overview.md) 標記 `sub_12` 為 Completed。
- **Phase 7 結案**：本子計畫正式完工結案！
