# 計畫變更日誌 (sub_13_native_consumer_testing_and_hardening)

> 本日誌記錄 `sub_13` 計畫內部微觀狀態轉換、DR 決策與變更歷史。

---

## 2026-08-25

### Phase 0: 語意需求與技術調研
- **雙星初始化**：伴隨開立 [`P00_semantic_requirements.md`](./P00_semantic_requirements.md) 與本變更日誌。
- **R01 調研完備**：產出並確認 [`R01_native_consumer_e2e_testing_and_gap_analysis.md`](./R01_native_consumer_e2e_testing_and_gap_analysis.md)，確立預設 Provider 為官方 GitHub 遠端。
- **R02 調研完備**：產出並確認 [`R02_full_zip_packaging_architecture_analysis.md`](./R02_full_zip_packaging_architecture_analysis.md)，確立**全系統全面 Zip 單檔打包標準 (`{version}.zip`)**，明文空間嚴格僅限 `source/` 與 `modules/`，本地/遠端統一同構 Zip 管線。
- **Phase 0 結案**：P00 需求與 R01/R02 調研報告確認完成，選定 Level 1 (Full Track) 推進。

### Phase 1: 需求規格說明書
- **產出規格書**：產出 [`P01_requirements_spec.md`](./P01_requirements_spec.md)，定義 FR-01 ~ FR-05 全面 Zip 化與同構自舉需求、EC-01 ~ EC-04 邊界防護與 NFR-01 ~ NFR-04 非功能需求。
- **Phase 1 結案**：通過可追溯性稽核，使用者確認通過。

### Phase 2: 架構設計方案
- **產出架構書**：產出 [`P02_architecture_plan.md`](./P02_architecture_plan.md)，包含模組拓撲圖、發布單檔 Zip 打包循序圖、同構 Zip 解包自舉循序圖、受影響檔案清單與 `[P02:DR-01]` ~ `[P02:DR-04]` 決策清單。
- **Test-First 前置初始化**：隨設計同步草擬 [`P06_test_plan.md`](./P06_test_plan.md)（含 6 項 FT、4 項 ET 與 RT-01 回歸測試）。
- **Phase 2 結案**：使用者確認通過。

### Phase 3: API 規格與介面合約說明書
- **產出 API 規格書**：產出 [`P03_api_spec.md`](./P03_api_spec.md)，定義 `Builder` 單檔 Zip 產出合約、`AtomicEngine` 同構 Zip 解包介面、`yscb.py` 遠端自舉 helper、7 步實作拓撲圖與知識庫交付清單。
- **Phase 3 結案**：使用者確認通過。

### Phase 4: 實作計畫與測試定稿
- **產出實作計畫**：產出 [`P04_implementation_plan.md`](./P04_implementation_plan.md)，包含交叉審查核對清單、三大靈魂拷問防護解析、7 大維度文檔交付規劃、TASK-01 ~ TASK-07 實作矩陣與決策紀錄清單。
- **Test-First 剛性定稿**：與 Phase 4 一併將 [`P06_test_plan.md`](./P06_test_plan.md) 剛性定稿為 Confirmed。
- **Phase 4 結案**：使用者確認通過。

### Phase 5: 程式碼實作
- **TASK-01 交付**：升級 [`builder.py`](../../ys_codebase/source/dev/dev/builder.py) 實作全面 Zip 單檔打包（`build_module` 產出 `build/<mod>/<ver>.build.zip`；`package_release` 產出 `release/<mod>/<ver>.zip`；不落地展開散裝目錄）。
- **TASK-02 交付**：升級 [`releaser.py`](../../ys_codebase/source/dev/dev/releaser.py) 對齊單檔 Zip 產物與發布原子交易回滾防護。
- **TASK-03 交付**：升級 [`engine.py`](../../ys_codebase/source/core/core/engine.py) 實作統一同構 Zip 下載、4-Stage Atomic Reload 流水線與模板自動剝除純粹化。
- **TASK-04 交付**：升級 [`yscb.py`](../../yscb.py) 預設 URL 導向官方 GitHub 遠端，實作 `_fetch_and_extract_zip` 與原生遠端自舉。
- **TASK-05 交付**：升級 [`sandbox.py`](../../ys_codebase/source/dev/dev/testing/sandbox.py) 支援 Zip 套件建立與沙盒同構解包。
- **TASK-06 交付**：新增 [`test_remote_zip_bootstrap.py`](../../ys_codebase/source/core/tests/test_remote_zip_bootstrap.py) 單元測試套件。
- **Phase 5 結案**：全模組 74/74 測試 100% Passed。

### Phase 6: 驗證與測試
- **全量測試驗證**：實機執行 `python yscb.py dev test --all`，74 項測試 100% 綠燈通過。
- **現場邊界排查與加固**：
  - 修正 `.mirror/` 缺失時的 Stage 1 自動自癒拉取機制。
  - 修正 `act_reload` 解壓前剛性清空目標資料夾，消除歷史殘留檔案。
  - 將 `release.root` 與 `release` 語意協議精確移交至 `dev` 模組治理。
- **Phase 6 結案**：[`P06_test_plan.md`](./P06_test_plan.md) 標記為 `Passed` 並回填實機日誌。

### Phase 7: 結案審查與知識庫更新
- **知識庫交付**：
  - 建立 [`docs/core/ZIP_PACKAGE_SPEC.md`](../../../docs/core/ZIP_PACKAGE_SPEC.md)（維度 3）。
  - 更新 [`docs/dev/RELEASE_PIPELINE.md`](../../../docs/dev/RELEASE_PIPELINE.md)（維度 3）。
  - 追加 `[DN-12]` 與 `[DN-13]` 至 [`docs/core/DESIGN_NOTES.md`](../../../docs/core/DESIGN_NOTES.md)（維度 5）。
- **高階日誌同步**：更新專案根目錄 [`CHANGELOG.md`](../../../CHANGELOG.md)。
- **產出結案文件**：產出 [`P07_walkthrough.md`](./P07_walkthrough.md)，標記狀態為 `Completed`。
- **Phase 7 結案**：子計畫 `sub_13` 正式圓滿結案。
