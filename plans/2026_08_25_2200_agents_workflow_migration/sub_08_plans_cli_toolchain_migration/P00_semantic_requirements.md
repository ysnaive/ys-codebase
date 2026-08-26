# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 專題調研：[R01_legacy_plans_features.md](./R01_legacy_plans_features.md) (Completed)  
> 計畫類型：Feature / Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > "回到 agent workflow 部分，開啟新子計畫，plans 相關 cli 工具鍊補齊 (主要為舊版功能遷移)"
  > "先調研舊版包含哪些功能"
  > "是，並先規劃欲添加之預期 cli 指令"
- **核心目標**：
  - 在 `agents-workflow` 模組中，將舊版四大開發計畫工具鏈（歸檔 `archive`、狀態掃描 `status`、歷史與決策檢索 `search`、合規性稽核 `verify`）進行現代化重構與遷移，全面對齊 YSCB 語意 URI 體系與統一 CLI 門面。

---

## 2. 預期 CLI 指令體系與規格規劃 (CLI Specifications)

支援分群式子命令 `python yscb.py agents-workflow plan <action>` 與平鋪別名 `plan-<action>`：

### 2.1 `plan archive` (安全歸檔工具)
- **指令語法**：`python yscb.py agents-workflow plan archive <plan_name> [--force]`
- **核心規則**：
  1. 源路徑解析：`workflow.plans://{plan_name}`。
  2. 目標路徑解析：`workflow.archived://{YYYY}/{MM}/{plan_name}`（依據時間戳前綴 `YYYY_MM_` 自動分流）。
  3. 完成度檢查：檢查 `P07_walkthrough.md`、`fast_track_plan.md` 或 `umbrella_overview.md` 是否為 `Completed`（非 Completed 且無 `--force` 則阻斷）。
  4. CHANGELOG 檢查：檢查 `project://CHANGELOG.md` 是否已記載該計畫（無記載且無 `--force` 則阻斷）。
  5. 暫時交接快照清理：自動刪除 `handoff.md`。
  6. 目的地防衝突：目標目錄若已存在同名計畫則阻斷。

### 2.2 `plan status` (狀態矩陣掃描工具)
- **指令語法**：`python yscb.py agents-workflow plan status`
- **核心規則**：
  1. 僅掃描活躍進行中目錄 `workflow.plans://`（不支援 `--all`，不掃描歷史歸檔目錄 `workflow.archived://`）。
  2. 識別 4 大 Track：`Umbrella` (主/子計畫)、`Fast Track`、`Full Track`、`Phase 0`。
  3. 識別各 Phase 狀態：`P00 Discussing`, `P00 Confirmed`, `Phase 1 Planning`, `Phase 2 Architecture`, `Phase 3 API Spec`, `Phase 4 Implementation Plan`, `Phase 5 Implementation`, `Phase 6 Testing`, `Completed`, `(Paused)`。
  4. 輸出美觀 ASCII 矩陣，主計畫 ➔ 子計畫 `sub_*` 兩層樹狀縮排展示。

### 2.3 `plan search` (歷史計畫與決策檢索工具)
- **指令語法**：
  - 全文檢索：`python yscb.py agents-workflow plan search <query> [--year=YYYY] [--month=MM] [--limit=20]`
  - DR 專用檢索：`python yscb.py agents-workflow plan search [query] --dr [--limit=25]`
- **核心規則**：
  1. 跨 `workflow.plans://` 與 `workflow.archived://` 檢索 Markdown 文件。
  2. `--dr` 模式：正則結構化擷取 `[{Phase}:DR-XX]` 與結論摘要，自動去重呈現。
  3. 全文模式：搜尋匹配文字並輸出上下文行號與程式碼片段。

### 2.4 `plan verify` (計畫規範與合規稽核工具)
- **指令語法**：`python yscb.py agents-workflow plan verify [plan_name] [--all]`
- **核心規則**：
  1. 稽核指定或全量進行中（及歷史）計畫中的 Markdown 文件。
  2. 檢查是否殘留 `<!-- AGENT_GUIDANCE -->` 等模板指引註解未剝除。
  3. 檢查 Blockquote Header 元數據（`功能名稱`, `建立日期`, `狀態`）是否完整。
  4. 遞迴稽核子計畫目錄 `sub_*`。

---

## 3. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 雙星伴隨初始化與子計畫建立**：於主計畫 `2026_08_25_2200_agents_workflow_migration` 下建立 `sub_08_plans_cli_toolchain_migration`，聚焦於 plans 相關 CLI 工具鏈遷移與落地。
- **[P00:DR-02] 舊版四大核心功能盤點收斂**：完成 R01 專題調研，回溯舊版 4 大腳本（`archive`, `status`, `search`, `verify`）之完整安全規格與邊界防護。
- **[P00:DR-03] 統一 CLI 門面架構**：採用分群式指令 `agents-workflow plan <action>` 與短指令別名 `plan-<action>`，基於語意 URI（`workflow.plans://`, `workflow.archived://`, `project://`）徹底重構底層尋址。
- **[P00:DR-04] plan status 範疇純淨化**：`plan status` 專注於掃描與掌控進行中計畫（`workflow.plans://`）之即時進度與狀態矩陣，明確不掃描歷史歸檔目錄，移除 `--all` 選項。

---

## 4. 開放議題與確認紀錄

- [x] **議題 1**：預期 CLI 指令體系（`plan archive`, `plan status`, `plan search`, `plan verify`）之參數與行為規格（`plan status` 已依指示排除歷史掃描）。
