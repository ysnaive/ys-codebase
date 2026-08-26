# Phase 0 語意需求說明書 (Semantic Requirements Specification)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 計畫類型：Refactor & Feature  
> 模板版本：v1.4  

---

## 1. 原始需求陳述與問題意識 (Problem Statement & User Voice)

### 1.1 原始意圖 (User Voice)
1. `DevelopmentStandards.md` 中僅將「核心原則與防呆紀律」抽離成獨立的 `AgentsStandards.md`，其他（工作目錄、ID 追溯鏈、SOP 0~7 流程、模板尋址等）均保留於 `DevelopmentStandards.md`（標準開發規範）。
2. 發布時注入至 `AGENTS.md` 的部分改為僅插入極簡的 `AgentsStandards.md`。
3. `NewPlan.md` 維持載入完整的流程指引（`DevelopmentStandards.md`）。
4. 落實預留的專案組態開關：
   - `"enable_agents_md": true | false`（控制是否自動軟合併維護 `project://AGENTS.md`）。
   - `"enable_project_changelog": true | false`（控制是否啟用專案級 `project://CHANGELOG.md` 結案登載）。
5. `config.project.json` 中 `"release_targets"` 預設改為空陣列 `[]`（無）。
6. 為 `agents-workflow` 模組建立官方 `contributes.format.md` 擴充規範描述文檔。

---

## 2. 語意決策紀錄表 (Semantic Decision Records)

- **`[P00:DR-01]` (AgentsStandards 極簡收斂邊界)**：
  - **`AgentsStandards.md`（通用核心準則）**：僅保留「1. 核心原則與防呆紀律 (Core Principles & Guardrails)」，包含三大原則、執行紀律（嚴禁連發、Checkpoint 強制等待、問答 $\neq$ 推進、範疇保護、知識顧問模式、無 Log 即未驗證等）。
  - **`DevelopmentStandards.md`（標準開發流程與工作規範）**：包含 1. 工作目錄與子計畫管理規範、2. 跨文件 ID 引用與剛性追溯鏈、3. 全階段文件模板指針、4. 三大分流矩陣、5. SOP 0~7 階段流程與核心關卡、6. Fast Track 敏捷流程。
  - **`NewPlan.md`**：保持引用完整的 `DevelopmentStandards.md`（包含流程與目錄/追溯鏈規範）。
- **`[P00:DR-02]` (`AGENTS.md` 軟合併注入標的)**：
  - `ReleasePublisher._soft_merge_agents_md` 提取 `AgentsStandards.md` 內容注入至 `AGENTS.md` 的 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 區塊，大幅精簡系統 Prompt 上下文，保留專案自定義特化章節。
- **`[P00:DR-03]` (專案組態開關落實方案)**：
  - **`enable_agents_md`**：
    - `true`：發布時若 target 啟用且有 `AgentsStandards`，自動執行 `AGENTS.md` 軟合併。
    - `false`：發布時完全跳過 `AGENTS.md` 檢查與軟合併。
  - **`enable_project_changelog`**：
    - 作為專案級全域發布日誌功能開關，供 CLI 與 Plan 工具鏈（如 `PlanArchiver` 歸檔時的守門檢查、結案驗收流程）讀取判定是否強制要求 `project://CHANGELOG.md`。
- **`[P00:DR-04]` (`release_targets` 預設值變更)**：
  - 將 `source/agents-workflow/config.project.json` 中 `"release_targets"` 預設改為 `[]`。
  - 專案一鍵初始化 `--init-default` 時若使用者未指定 `--target`，預設為空清單，避免在非 Antigravity 環境下主動產生未預期的 IDE 配置目錄。
- **`[P00:DR-05]` (`contributes.format.md` 建立)**：
  - 在 `source/agents-workflow/contributes.format.md` 完整定義 `core.uri_schemes`、`agents-workflow.export`、`agents-workflow.token`、`agents-workflow.insert`、`agents-workflow.release_target` 的結構、欄位型別、模式說明與範例。

---

## 3. 待確認項目與開放式討論 (Clarifications)

- 語意需求與決策 `[P00:DR-01~05]` 已完整定義收斂，等待開發者確認定稿。
