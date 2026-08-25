# Phase 4: 實作計畫與定稿審查 (Implementation Plan) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據設計規格：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 當前狀態：`Confirmed` (Phase 4 審查定稿完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 跨階段對齊審查表 (Cross-Phase Alignment Matrix)

| P00 語意決策 | P01 需求規格 | P02 架構設計 | P03 API 介面 | P06 測試案例 | 1:1 對齊狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `[P00:DR-01]` 4 大 URI 協議註冊 | FR-01 | §1 系統互動圖, ADR-01 | §1.1 manifest.json 宣告 | FT-01, FT-06 | 100% 對齊 |
| `[P00:DR-02]` 組態模板 `!undefined` 剛性預設 | FR-02 | §2.2, ADR-02 模板解耦 | §1.2 config.project.json 模板 | FT-02 | 100% 對齊 |
| `[P00:DR-03]` `--init-default` 互動與目錄建立 | FR-03, FR-04, FR-05, FR-06, EC-01, EC-02, EC-04 | §2.1 互動時序圖 | §2 WorkflowInitializer API | FT-03, FT-04, ET-01, ET-02 | 100% 對齊 |
| `[P00:DR-04]` `--path-*` 變種參數覆蓋 | FR-07, EC-03 | §1 CLI 調度 | §3 CLI 命令語法 | FT-05, ET-03, RT-01 | 100% 對齊 |

---

## 2. 專案文檔衝擊預排清單 (Documentation Impact Plan)

依據知識庫 7 大抽象維度管理規範，預排本次子計畫結案時需 1:1 交付之文檔衝擊：

| 維度編號 | 維度名稱 | 目標文檔路徑 | 預排交付內容摘要 |
| :---: | :--- | :--- | :--- |
| **維度 2** | 核心概念與機制手冊 | `docs/agents-workflow/README.md` | 新增 `--init-default` 一鍵初始化使用章節與 4 大 `workflow.*` 協議清冊。 |
| **維度 4** | 介面與協議字典 | `docs/core/URI_SCHEMES.md` | 登錄 `workflow.plans`, `workflow.archived`, `workflow.ext`, `workflow.docs` 4 大協議。 |
| **維度 5** | 工程妥協與設計筆記 | `docs/agents-workflow/DESIGN_NOTES.md` | 登記 `[DN-AW-05]`（組態模板 `!undefined` 剛性解耦與推薦預設值封裝策略）。 |
| **維度 7** | 全專案發布變更日誌 | `CHANGELOG.md` | 追加 `sub_04` 組態治理與一鍵初始化功能發布日誌。 |

---

## 3. 實作前兩大靈魂拷問 (Stress Test Questions)

### 拷問 1：若使用者重複執行 `--init-default`，系統是否會重複建立或損壞既有設定與目錄？
- **答覆**：**絕對安全**。實體目錄建立使用 `os.makedirs(..., exist_ok=True)`；探測器檢測到目錄已存在時會輸出黃字提醒並直接安全綁定；寫入 `config.project.json` 採用暫存檔替換原子操作，不產生寫入中斷損毀。

### 拷問 2：若 `config.project.json` 中已存在使用者自訂的其它欄位（如已配置的 `ide` 清單或自訂鍵），`--init-default` 是否會意外清除這些欄位？
- **答覆**：**完全不會**。`WorkflowInitializer` 在持久化時會先讀取磁碟上的既有 JSON 資料，僅對 `paths` 物件內的鍵值進行原地增量替換，其餘所有自訂頂層欄位與保留欄位 100% 原樣保留。

---

## 4. 實作任務拆解清單 (Task Breakdown)

- [ ] **TASK-01 (Manifest 協議貢獻與 Config 模板建立)**：
  - 在 `source/agents-workflow/manifest.json` 中註冊 4 大 `workflow.*` 協議。
  - 新增 `source/agents-workflow/config.project.json` 模板（`paths` 全為 `"!undefined"`，含 `ide: []` 等保留欄位）。
- [ ] **TASK-02 (初始化引導引擎實作 `WorkflowInitializer`)**：
  - 建立 `source/agents-workflow/agents_workflow/initializer.py`。
  - 實作推薦路徑封裝、實體存在性探測、互動式 `[-y / -n]` 提示、缺失目錄建立與組態原子增量寫入。
- [ ] **TASK-03 (CLI 指令擴充與變種參數解析)**：
  - 修改 `source/agents-workflow/scripts/cli.py`，支援 `--init-default`、`-y`/`--yes` 與 `--path-{plans|archived|ext|docs}` 參數。
- [ ] **TASK-04 (單元測試、Dogfooding 部署與全模組回歸驗證)**：
  - 建立 `source/agents-workflow/tests/test_initializer.py` 覆蓋 FT-01~06、ET-01~03。
  - 實機執行 `python yscb.py dev test --all`（維持全模組 100% Passed）。
  - 執行 `dev build` 與 `install agents-workflow --force` 完成部署。

---

## 5. 當前階段確認狀態

- **當前狀態**：`Confirmed` (Phase 4 審查定稿完成)  
- **推進關卡**：等待開發者指示「**開始實作**」，以推進至 Phase 5 初始化任務清單並編寫程式碼！
