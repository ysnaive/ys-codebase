# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 計畫類型：Feature & Architecture  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 「dev 模組 透過 contributes["agents-workflow"] 向 agents-workflow 宣告注入特定的 開發專屬工作流與注意事項」
- **核心目標**：
  - 由 `dev` 模組在其 `manifest.json` 中宣告 `contributes["agents-workflow"]`，向 `agents-workflow` 體系貢獻：
    1. **開發專屬工作流 (Dev Workflows)**：透過 `export` 導出模組開發專屬的 SOP / Slash Command。
    2. **開發注意事項與工程規範 (Dev Standards / Guidelines)**：透過 `insert` 向標準或工作流中的 Token 錨點注入開發環境/模組開發注意事項（如沙盒測試、打包發布流程、Dogfooding 等）。
  - 驗證 `agents-workflow` 跨模組 Contributes 聚合發布機制（可正確掃描、物化並發布來自第三方/外部模組之 `export` 與 `insert`）。
- **邊界排除 (Explicitly Excluded)**：
  - 待釐清具體注入之工作流名稱與插入位置。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (Dev 模組宣告式擴充 agents-workflow)**：確立 `dev` 模組透過宣告 `contributes["agents-workflow"]` 作為擴充提供者，不硬編碼侵入 `agents-workflow` 核心資產。
- **[P00:DR-02] (直連既有標準錨點與 below 模式)**：`dev` 模組直接向 `agents-workflow` 現有預留之 `WORKFLOW_SOP_STANDARDS` 錨點進行 `insert` 注入（位於 `DevelopmentStandards.md` 尾部），採用 **`mode: "below"`** 模式插入，確保保留錨點供多模組宣告疊加注入，最終由編譯器狀態機安全收斂。
- **[P00:DR-03] (明確模組開發定性標題)**：注入的資產檔案命名為 `DevEngineeringStandards.md`，章節標題與內文**強烈強調該區段為「YS-Codebase 模組開發專案特化工程規範 (YS-Codebase Module Engineering Standards)」**，清晰定義其為 YS-Codebase 模組作者專屬遵守之工程紀律。
- **[P00:DR-04] (install 指令 @build 本地建置產物特例安裝)**：當調用 `install` 時，若版本約束或 revision 為 `build`（例 `install <mod>@build` 或 `<mod>@<ver>.build`），`core.engine` 一律自動強制從本地端 `module.build://` (即 `yscb://build/<mod>/`) 進行解析與下載，免去開發者手動先跑 release 的繁瑣步驟。
- **[P00:DR-05] (禁止 Agent 主動 release 與本地自引用安裝防呆鐵律)**：在規範中剛性明定：在開發者未明確下達指示（如指令「發布/安裝/同步」）的前提下，**Agent 絕對禁止主動執行 `dev release` 正式發布，以及對宿主環境進行本地端自引用安裝 (`install`)**；Agent 唯一允許的代碼驗證手段為 **`python yscb.py dev test` 於隔離虛擬沙盒中進行驗證**。

---

## 3. 開放議題與確認紀錄

- [x] **Q-01 (注入標的定位)**：專注於開發工程注意事項，暫不導出獨立工作流。
- [x] **Q-02 (接收錨點確認)**：直接掛載至現有 `WORKFLOW_SOP_STANDARDS` 錨點。
- [x] **Q-03 (條文定性確認)**：冠以「YS-Codebase 模組開發專案特化工程規範」，包含四大主軸條文（含禁止主動 release/install 鐵律）。
- [x] **Q-04 (install @build 特例機制)**：支援 `install <mod>@build` 自動自 `module.build://` 安裝本地開發建置產物。





