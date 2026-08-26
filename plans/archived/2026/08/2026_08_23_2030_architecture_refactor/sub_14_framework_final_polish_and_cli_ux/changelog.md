# 計畫變更日誌 (sub_14_framework_final_polish_and_cli_ux)

> 本日誌記錄 `sub_14` 計畫內部微觀狀態轉換、DR 決策與變更歷史。

---

## 2026-08-25

### Phase 0: 語意需求與技術調研
- **雙星初始化**：伴隨開立 [`P00_semantic_requirements.md`](./P00_semantic_requirements.md) 與本變更日誌。
- **決策定案**：
  - `[P00:DR-01]`：徹底移除 `dev release` Gate 1 (Git Dirty 限制)，保持本地發布純粹性。
  - `[P00:DR-02]`：確立 `yscb.py --help` 動態派發調用流，整併 `init` 於 Core 欄位，自動動態聚合已安裝模組指令。
- **狀態**：`Confirmed`，定案採納 Level 1: Full Track。

### Phase 1: 需求規格定義
- **規格轉譯**：產出 [`P01_requirements_spec.md`](./P01_requirements_spec.md)（FR-01 ~ FR-04, EC-01 ~ EC-03, NFR-01 ~ NFR-03）。
- **狀態**：`Confirmed`。

### Phase 2: 架構與模組設計
- **架構藍圖**：產出 [`P02_architecture_plan.md`](./P02_architecture_plan.md)（Help 動態派發流、Releaser Gate 1 移除、`difflib` 智慧建議）。
- **Test-First 初始化**：同步草擬 [`P06_test_plan.md`](./P06_test_plan.md)（FT-01~FT-04, ET-01~ET-02, RT-01, UX-01~UX-02）。
- **狀態**：`Confirmed`。

### Phase 3: API 規格定義與依賴拓撲
- **介面規格**：產出 [`P03_api_spec.md`](./P03_api_spec.md)（`_print_global_help`, `_suggest_command`, `act_get_installed_commands_summary`, `check_preflight_gates`）。
- **狀態**：`Confirmed`。

### Phase 4: 最終審查與定稿
- **實作定稿**：產出 [`P04_implementation_plan.md`](./P04_implementation_plan.md)（文檔衝擊盤點、靈魂拷問、4 大實作任務清單）。
- **Test-First 定稿**：同步剛性定稿 [`P06_test_plan.md`](./P06_test_plan.md)。
- **狀態**：`Confirmed`。

### Phase 5: 依序程式碼實作
- **任務落實**：TASK-01 ~ TASK-04 100% 依序實作完成。
- **編譯與回歸**：全模組回歸測試 **78/78 (100%) 全部綠燈 Passed**。
- **狀態**：`Completed`。

### Phase 6: 測試驗收與 UX 驗證
- **測試執行**：FT-01~FT-04, ET-01~ET-02, RT-01 全部 100% Passed，已真實回填日誌於 [`P06_test_plan.md`](./P06_test_plan.md)。
- **UX 驗收**：開發者實機執行驗收通過。
- **狀態**：`Passed`。

### Phase 7: 成果展示與結案報告
- **文檔交付**：1:1 更新 `RELEASE_PIPELINE.md`、追加 `DN-DEV-04` 於 `docs/dev/DESIGN_NOTES.md`，並更新頂層 `CHANGELOG.md`。
- **結案報告**：產出 [`P07_walkthrough.md`](./P07_walkthrough.md)。
- **狀態**：`Completed`。
