# 需求規格說明書 (Requirements Specification)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 標準規範與開發流程資產拆分 | 1. 建立 `source/agents-workflow/assets/standards/AgentsStandards.md`，僅收斂「1. 核心原則與防呆紀律 (Core Principles & Guardrails)」通用硬性原則。<br/>2. 重構 `source/agents-workflow/assets/standards/DevelopmentStandards.md`，收斂「工作目錄規範、ID 追溯鏈、全階段模板指針、三大分流矩陣、SOP 0~7 階段流程、Fast Track 流程」。<br/>3. `NewPlan.md` 保持引用完整的 `DevelopmentStandards.md`。 | P0 | [P00:DR-01] |
| **FR-02** | `AGENTS.md` 軟合併注入標的切換 | `ReleasePublisher._soft_merge_agents_md` 改為提取極簡的 `AgentsStandards.md` 內容，注入至 `AGENTS.md` 的 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 標籤區塊中，保留專案自定義特化章節，大幅降低 Prompt 負載。 | P0 | [P00:DR-02] |
| **FR-03** | `manifest.json` 與 Contributes 宣告對齊 | 1. `export` 清單新增 `AgentsStandards.md`（類型 `standard`），保留 `DevelopmentStandards.md`。<br/>2. `insert` 清單提供 `AGENTS_STANDARDS` 與 `DEVELOPMENT_STANDARDS` Token 供外部與內部工作流引用。 | P0 | [P00:DR-01] [P00:DR-03] |
| **FR-04** | 專案組態開關落實方案 | 1. **`enable_agents_md`**：`true` 時發布執行 `AGENTS.md` 軟合併；`false` 時完全跳過 `AGENTS.md` 檢查與維護。<br/>2. **`enable_project_changelog`**：控制全域 `project://CHANGELOG.md` 在結案審查與 PlanArchiver 歸檔時的守門要求。 | P1 | [P00:DR-03] |
| **FR-05** | `release_targets` 預設值變更為空 | 1. 將 `source/agents-workflow/config.project.json` 中 `"release_targets"` 預設改為 `[]`。<br/>2. 一鍵初始化 `--init-default` 時若未指定 `--target` 預設為空清單，避免非 Antigravity 專案產生未預期的 IDE 目錄。 | P1 | [P00:DR-04] |
| **FR-06** | 官方 `contributes.format.md` 建立 | 建立 `source/agents-workflow/contributes.format.md`，完整描述 `core.uri_schemes`、`agents-workflow.export`、`agents-workflow.token`、`agents-workflow.insert`、`agents-workflow.release_target` 的欄位定義、型態契約、模式說明與範例。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `AGENTS.md` 既有內容替換 | 若專案根目錄已存在包含舊版整份 `DevelopmentStandards` 的 `AGENTS.md`，發布時透過正則安全置換為精簡的 `AgentsStandards`，標籤外自定義章節（如 `## 4. 專案特化工程規範`）100% 完整保留。 |
| **EC-02** | `release_targets` 為空陣列 `[]` 發布 | 當 `config.project.json` 的 `release_targets` 為 `[]` 時，執行 `agents-workflow release` 不拋出任何異常，安全略過 IDE 目錄輸出並提示 `Published files: 0`。 |
| **EC-03** | `enable_agents_md` 為 `false` | 發布時即使 `release_targets` 包含 `antigravity`，也完全跳過 `AGENTS.md` 的檢查、建立與軟合併動作。 |
| **EC-04** | 雙標準資產獨立發布投影 | `AgentsStandards.md` 與 `DevelopmentStandards.md` 作為兩個獨立 standard 資產，在 Antigravity target 下分別投影至 `.agents/standards/AgentsStandards.md` 與 `.agents/standards/DevelopmentStandards.md`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構純淨度 | 100% Python 標準庫，零第三方套件依賴，嚴格遵守 Dogfooding 三層空間邊界。 |
| **NFR-02** | 回歸測試品質 | 模組內部測試與全模組沙盒端到端測試維持 100% 通過（113/113 Passed）。 |
| **NFR-03** | 上下文輕量化 | 注入至 `AGENTS.md` 的核心標準規範字數縮減約 60% 以上，顯著減少每次對話的 Context 消耗。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `AGENTS.md` 軟合併依賴 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 標籤，發布時需先透過 `compiler.resolve_stage2_uri` 將資產內部的語意 URI 標籤（如模板指針）轉譯為相對於根目錄之路徑。
- **`[!IMPORTANT]`** `NewPlan.md` 作為標準立項引導工作流，需完整包含 SOP 0~7 各階段指引，因此 `NewPlan.md` 維持注入包含完整流程的 `DevelopmentStandards.md`。
