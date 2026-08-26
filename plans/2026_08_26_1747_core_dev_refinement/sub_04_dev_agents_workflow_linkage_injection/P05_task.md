# 程式碼實作進度追蹤 (Implementation Tasks Tracker)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.2  

---

## 1. 任務實作進度看板 (Task Board)

| 任務編號 | 核心實作項目 | 負責模組 / 檔案 | 狀態 |
| :--- | :--- | :--- | :---: |
| **TASK-01** | Dev 工程規範資產建立 (`DevEngineeringStandards.md`) | `source/dev/assets/standards/DevEngineeringStandards.md` | `Completed` |
| **TASK-02** | Dev Contributes 宣告註冊 (`insert`, `mode: "below"`) | `source/dev/manifest.json` | `Completed` |
| **TASK-03** | Core Engine `@build` 特例解析與下載實作 | `source/core/core/engine.py` | `Completed` |
| **TASK-04** | 單元測試擴充 (FT-01~03, ET-01, FT-10) | `source/core/tests/`, `source/dev/tests/`, `source/agents-workflow/tests/` | `Completed` |

---

## 2. 實作細節與提交追蹤

- [x] **TASK-01**：已建立 `DevEngineeringStandards.md`（包含禁止主動 release/install、三層空間 SSOT、虛擬沙盒測試加速、靜態 AST 守門）。
- [x] **TASK-02**：已在 `dev/manifest.json` 宣告 `contributes["agents-workflow"]` (`mode: "below"` 掛載至 `WORKFLOW_SOP_STANDARDS`)。
- [x] **TASK-03**：已在 `core/engine.py` 實作 `@build` 特例解析與自 `module.build://` 強制下載。
- [x] **TASK-04**：已在三大模組測試套件中擴充單元測試。
