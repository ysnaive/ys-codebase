# 子計畫變更日誌 (Sub-Plan Changelog) - sub_03_workflow_placeholder_format_migration

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 建立日期：2026-08-26  
> 當前狀態：`Draft` (Phase 0 討論修訂)  
> 模板版本：v1.4  

---

## 變更紀錄 (Changelog Matrix)

### Phase 0: 語意需求與討論模式
- **計畫初始化**：建立子計畫目錄 `sub_03_workflow_placeholder_format_migration`。
- **語意分析與決策整合**：產出 [`P00_semantic_requirements.md`](./P00_semantic_requirements.md)，定義視覺化佔位符語法（`__@{token}__` / `__#{uri}__`），並落入 4 大架構決策（`[P00:DR-01]` 正則空白容錯、`[P00:DR-02]` 路徑佔位符語意保留、`[P00:DR-03]` 5-Step 編譯狀態機升級、`[P00:DR-04]` 純淨升級與舊格式全面清除）。
- **狀態**：`Confirmed`。

### Phase 1: 需求規格說明書
- **規格轉譯**：產出 [`P01_requirements_spec.md`](./P01_requirements_spec.md)（FR-01~FR-08、EC-01~EC-04、NFR-01~NFR-03，100% 回溯至 P00 決策）。
- **狀態**：`Confirmed`。

### Phase 2: 架構設計說明書
- **架構設計**：產出 [`P02_architecture_plan.md`](./P02_architecture_plan.md)（正則引擎、5-Step 狀態機多輪解算時序圖、ADR 與衝擊清單）。
- **Test-First 前置**：同步草擬 [`P06_test_plan.md`](./P06_test_plan.md)（FT-01~FT-06、ET-01~ET-04、RT-01、UX-01）。
- **狀態**：`Confirmed`。

### Phase 3: API 與介面規格說明書
- **API 定義**：產出 [`P03_api_spec.md`](./P03_api_spec.md)（Token Anchor / URI Ref Schema、正則工廠簽名、5-Step 狀態機介面與邊界規格）。
- **狀態**：`Confirmed`。

### Phase 4: 實作計畫與定稿審查
- **實作定稿**：產出 [`P04_implementation_plan.md`](./P04_implementation_plan.md)（跨階段對齊表、文檔衝擊預排、2 大靈魂拷問、TASK-01~TASK-04 任務清單）。
- **Test-First 定稿**：同步剛性定稿 [`P06_test_plan.md`](./P06_test_plan.md)。
- **狀態**：`Confirmed`。

### Phase 5: 依序程式碼實作
- **編譯器升級**：更新 `source/agents-workflow/agents_workflow/compiler.py`，實作 `__@{token}__` 正則匹配、三模式注入、自指防護、殘留抹除，並保持 `__#{uri}__` 語意不變。
- **全域資產遷移**：全面將 `assets/templates/` (P01~P07)、`DevelopmentStandards.md` 與 `ContextInit.md` 之標籤升級為新語法。
- **單元測試與全域回歸**：更新 `tests/test_compiler.py`，執行 `python yscb.py dev test --all` 達到 99/99 Passed (100%)。
- **Dogfooding 部署**：完成 `dev build`、`install --force` 與 `compile` 自治驗證。
- **狀態**：`Completed`。

### Phase 6: 測試執行與結果記錄
- **實機測試執行**：`agents-workflow` 單元測試 (12/12 Passed) 與全系統回歸測試 (99/99 Passed, 100%)。
- **日誌回填**：已在 [`P06_test_plan.md`](./P06_test_plan.md) 中完整回填 FT-01~06、ET-01~04、RT-01 執行日誌，經開發者指示免測放行。
- **狀態**：`Passed`。

### Phase 7: 成果展示與結案報告 (Walkthrough)
- **結案報告**：產出 [`P07_walkthrough.md`](./P07_walkthrough.md)（變更概述、14 檔案變更清冊、關鍵代碼展示、驗證結果與 Conventional Commit 建議）。
- **知識庫交付**：更新 [`docs/agents-workflow/README.md`](../../../docs/agents-workflow/README.md)、登記 [`docs/agents-workflow/DESIGN_NOTES.md`](../../../docs/agents-workflow/DESIGN_NOTES.md) (`[DN-AW-04]`)，並追加 [`CHANGELOG.md`](../../../CHANGELOG.md)。
- **狀態**：`Completed`。
