# 子計畫變更日誌 (Sub-Plan Changelog) - sub_04_agents_workflow_injection_config_and_init_default

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 建立日期：2026-08-26  
> 當前狀態：`Draft` (Phase 0 討論修訂)  
> 模板版本：v1.4  

---

## 變更紀錄 (Changelog Matrix)

### Phase 0: 語意需求與討論模式
- **計畫初始化**：建立子計畫目錄 `sub_04_agents_workflow_injection_config_and_init_default`。
- **語意分析與決策校正**：產出 [`P00_semantic_requirements.md`](./P00_semantic_requirements.md)，校正確立 `config.project.json` 模板中所有路徑預設剛性為 `"!undefined"`，`"project://.agent_workflow/..."` 為 `--init-default` 指令攜帶的一鍵初始化預設推薦值，並落入 4 大架構決策。
- **狀態**：`Confirmed`。

### Phase 1: 需求規格說明書
- **規格轉譯**：產出 [`P01_requirements_spec.md`](./P01_requirements_spec.md)（FR-01~FR-07、EC-01~EC-04、NFR-01~NFR-03，100% 回溯至 P00 決策）。
- **狀態**：`Confirmed`。

### Phase 2: 架構設計說明書
- **架構設計**：產出 [`P02_architecture_plan.md`](./P02_architecture_plan.md)（4 大協議 Schema、時序圖、ADR 與衝擊清單）。
- **Test-First 前置**：同步草擬 [`P06_test_plan.md`](./P06_test_plan.md)（FT-01~FT-06、ET-01~ET-03、RT-01）。
- **狀態**：`Confirmed`。

### Phase 3: API 與介面規格說明書
- **API 定義**：產出 [`P03_api_spec.md`](./P03_api_spec.md)（Manifest URI 宣告、`config.project.json` 模板、`WorkflowInitializer` 引擎簽名與 CLI 命令規格）。
- **狀態**：`Confirmed`。

### Phase 4: 實作計畫與定稿審查
- **實作定稿**：產出 [`P04_implementation_plan.md`](./P04_implementation_plan.md)（跨階段對齊表、文檔衝擊預排、2 大靈魂拷問、TASK-01~TASK-04 任務清單）。
- **Test-First 定稿**：同步剛性定稿 [`P06_test_plan.md`](./P06_test_plan.md)。
- **狀態**：`Confirmed`。

### Phase 5: 依序程式碼實作
- **協議貢獻與模板建立**：在 `source/agents-workflow/manifest.json` 註冊 4 大 `workflow.*` 協議，建立 `config.project.json` 模板（預設為 `!undefined` 並含保留欄位）。
- **引導引擎與 CLI 擴充**：實作 `agents_workflow/initializer.py` 與 `scripts/cli.py`，支援 `--init-default`、`-y` 與 `--path-*` 參數。
- **單元測試與全域回歸**：建立 `tests/test_initializer.py`，全系統回歸測試 104/104 案例 100% Passed。
- **Dogfooding 部署**：完成 `dev build`、`install --force` 與 `uri list` 自省展示。
- **狀態**：`Completed`。

### Phase 6: 測試執行與結果記錄
- **實機測試執行**：`agents-workflow` 單元測試 (17/17 Passed) 與全系統回歸測試 (104/104 Passed, 100%)。
- **日誌回填**：已在 [`P06_test_plan.md`](./P06_test_plan.md) 中完整回填 FT-01~06、ET-01~03、RT-01 執行日誌。
- **狀態**：`Passed` (全測試通過且 UX 確認放行)。

### Phase 7: 成果展示與結案報告
- **結案報告**：產出 [`P07_walkthrough.md`](./P07_walkthrough.md)。
- **知識庫交付**：更新 `docs/agents-workflow/README.md`、登記 `[DN-AW-05]` 於 `DESIGN_NOTES.md`，追加高階日誌於 `CHANGELOG.md`。
- **狀態**：`Completed`。
