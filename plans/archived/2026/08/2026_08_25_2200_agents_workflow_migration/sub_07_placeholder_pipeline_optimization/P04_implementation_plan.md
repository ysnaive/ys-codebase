# 實作計畫說明書 (Phase 4: Implementation Plan)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 實作任務與工作分解 (Work Breakdown Structure)

依據 [P03_api_spec.md](./P03_api_spec.md) 定義之依賴拓撲順序分解實作步驟：

### 步驟 1：升級專案組態模板 (`source/agents-workflow/config/config.project.json`)
- 移除原 `"ide": []`。
- 升級為 `"release_targets": ["antigravity"]`。
- 保留 `"enable_agents_md": true` 與 `"enable_project_changelog": true`。

### 步驟 2：宣告 `release_target` Contributes (`source/agents-workflow/manifest.json`)
- 宣告 `antigravity` 釋出目標，配置 `workflow`（含純文字/陣列 Header 模板與巨集插值）、`template` 與 `standard` 投影目錄。

### 步驟 3：重構編譯器狀態機 (`source/agents-workflow/agents_workflow/compiler.py`)
- 廢棄 `exports/` 寫入，改為物化寫入 `cache.root://agents-workflow/resolved_contents/`。
- 實作 Stage 1 `compile_stage1()` 與 Stage 2 `resolve_stage2_uri(content, current_dst_path, deployment_map)`。
- 實作三層重映射階層與正斜線 `/` 路徑標準化。

### 步驟 4：實作發布引擎與原子交易 (`source/agents-workflow/agents_workflow/publisher.py`)
- 實作 `build_deployment_map`（拓撲映射表生成）。
- 實作 `render_header`（純文字/陣列 Header 巨集插值）。
- 實作 `release_all` 4 步原子交易：過往檔案清理 (`storage://`) ➔ 提前解算 ➔ 持久紀錄 ➔ 目錄落地與 `AGENTS.md` 軟合併。

### 步驟 5：實作目標管理與 CLI 指令 (`source/agents-workflow/agents_workflow/targets.py` & `scripts/cli.py`)
- 實作 `ReleaseTargetManager`（`list_targets`、`add_target`、`remove_target`）。
- 在 `cli.py` 註冊 `release` 與 `release-target` 指令體系。

### 步驟 6：全量遷移核心資產引用連結 (`source/agents-workflow/assets/`)
- 檢查並將 `assets/standards/`、`assets/workflows/`、`assets/templates/` 中所有路徑指針全面更新為 `__#{uri}__`。

### 步驟 7：單元測試與全專案回歸驗證
- 更新 `source/agents-workflow/tests/test_compiler.py`，覆蓋 ST-01 ~ ST-08 測試案例。
- 執行 Canonical Pipeline 驗證 100% Passed。

---

## 2. 知識庫文檔衝擊清單 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: compiler.py & publisher.py` | 維度 3 (中觀機制) | `docs/agents-workflow/FACTORY_PIPELINE.md` | 重構工廠流水線為兩階段 6 步標準語意管線。 |
| `P01: release_target 規範` | 維度 2 (配置與使用) | `docs/agents-workflow/README.md` | 說明 `release_target` Contributes 規格、CLI 指令與多 Target 發布。 |
| `P02: 4 步原子發布交易` | 維度 5 (工程妥協與不變量) | `docs/agents-workflow/DESIGN_NOTES.md` | 登記 `DN-03` 發布清單持久化與原子清理防護。 |

---

## 3. 架構靈魂拷問 (Stress Test & Edge Case Defense)

- **Q1 (多 Target 檔案重疊與清理安全性)**：當同時配置多個 `release_targets` 時，若其中一個 Target 的輸出路徑與另一個 Target 共享或部分重疊，清理過往檔案時如何保證不誤刪其他 Target 的檔案？
  - **防禦設計**：發布引擎以**「精確單檔實體路徑 (Exact Absolute File Paths)」**作為 `storage://agents-workflow/release_manifest.json` 的紀錄單位，嚴禁對整個目錄做遞迴式暴力 `rmtree`。清理時僅精確刪除清單內的檔案，且若檔案被當前生效的任一 Target 共享則予以保留，保證多環境發布絕對安全無損。

---

## 4. 決策紀錄 (Traceability)

- 本計畫直接落實 [P01_requirements_spec.md](./P01_requirements_spec.md)、[P02_architecture_plan.md](./P02_architecture_plan.md) 與 [P03_api_spec.md](./P03_api_spec.md)。
