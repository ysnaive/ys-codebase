# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：模組工具鏈優化主計畫 (Module Toolchain Optimization Umbrella)  
> 建立日期：2026-08-28  
> 主計畫目錄：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：`Planning`  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：統籌 YS-Codebase 各模組在開發日常、測試驗證、構建打包與 CLI 使用體驗上的工具鏈深度優化，提升模組化開發與自動化維護效率。
- **架構邊界**：涉及 `source/` 內各核心模組（`core`, `dev`, `agents-workflow`, `knowledge-db` 等）與其對應的 CLI/SDK/腳本工具鏈，嚴格遵循 YSCB 模組工程規範、Dogfooding 三層空間與虛擬沙盒測試流水線。
- **推進機制**：採增量滾動推進（Open & Incremental Roadmap），不設靜態固定邊界，隨時依實務開發痛點動態追加子計畫。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_contributes_file_structure_upgrade` | Full Track | `Completed` | **Core Contributes 系統檔案結構升級**：全系統 contributes 現況調研 (R01)、目錄化多軌 Discovery 掃描 (`contributes/<target>.json`)、Manifest 瘦身 (>98%)、專案級 config 空間特化注入、消費端 SDK 統一收斂與全系統沙盒回歸 100% Passed。 |
| **sub_02** | `sub_02_config_system_upgrade` | Full Track | `Completed` | **Config 系統架構升級、Contribute 專案特化規範與工具鏈建立**：微內核 `core.config` SDK、`configurable/` 模板目錄規範、專案特化 `contribute.json` 類別 (強制 Git 追蹤)、消費端 100% 收斂、CLI `config` 工具鏈與全模組 172/172 測試通過。 |
| **sub_03** | `sub_03_dev_module_check_upgrade` | Full Track | `Completed` | **Dev 模組狀態檢核工具升級**：5 步流水線合規檢查引擎、三級嚴重度 (`[PASS]`/`[WARN]`/`[FAIL]`)、Release 剛性守門阻斷、反模式靶向攔截、CLI 彩色診斷輸出與全模組 178/178 測試通過。 |
| **sub_04** | `sub_04_agents_workflow_plan_check_upgrade` | Full Track | `Completed` | **Agents-Workflow Plan 核查工具鏈升級**：5 步計畫檢核流水線、動態模板 `#Header` 鏡像核對、嚴禁 HTML 註解與佔位符、Noise-Free 聚焦排版、PlanArchiver 剛性守門阻斷與全模組 178/178 測試通過。 |
| **sub_05** | `sub_05_agents_workflow_release_local_mode` | Full Track | `Completed` | **Agents-Workflow Release 預設 Local 模式與 Gitignore 軟合併同步**：release-target 啟用/停用預設寫入本機私有 `config.local.json`、`--proj` 寫入專案組態、Target 來源辨識排版、微內核 `core.config.get_raw/inspect` 溯源 API、發布時 `project://.gitignore` 區塊非破壞性軟合併與全模組 181/181 測試通過。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (主計畫初始化與模式確立)**：完成 Umbrella 主計畫立項，確立增量滾動推進機制與無固定邊界模式。
- [x] **里程碑 2 (sub_01 啟動與 R01 調研)**：開立 `sub_01` 子計畫並產出 `R01_core_contributes_architecture_and_file_structure.md` 專題架構調研。
- [x] **里程碑 3 (sub_01 實作與驗收)**：完成 sub_01 規格、實作、全模組回歸驗證 (164/164 Passed) 與知識庫交付。
- [x] **里程碑 4 (sub_02 啟動與 R01 調研)**：開立 `sub_02` 子計畫並產出 `R01_config_system_architecture_and_mechanisms.md` 調研報告。
- [x] **里程碑 5 (sub_02 實作與結案交付)**：完成 sub_02 微內核 SDK、模板標準目錄、專案特化 `contribute.json`、全模組消費端收斂、CLI 工具鏈、全系統沙盒回歸 (172/172 Passed) 與 Walkthrough 交付。
- [x] **里程碑 6 (sub_03 狀態檢核工具升級與結案交付)**：完成 sub_03 5 步檢核流水線、反模式靜態靶向攔截、Release 守門阻斷、全模組沙盒回歸 (178/178 Passed) 與 Walkthrough 交付。
- [x] **里程碑 7 (sub_04 Plan 核查工具鏈升級與結案交付)**：完成 sub_04 動態模板 Header 鏡像核對、5 步流水線、Noise-Free 排版、歸檔剛性守門、全模組沙盒回歸 (178/178 Passed) 與 Walkthrough 交付。
- [x] **里程碑 8 (sub_05 Release 預設 Local 模式與 Gitignore 軟合併結案交付)**：完成 sub_05 Local 預設、`--proj` 支援、`core.config.get_raw/inspect` 溯源 API、`.gitignore` 軟合併、全模組沙盒回歸 (181/181 Passed)、本地 `@build` 部屬與既有 target 成功遷移至 local。







---

## 4. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 開立分類型主計畫**：開立 Umbrella 主計畫 `plans://2026_08_28_1754_module_toolchain_optimization/`，統籌各模組工具鏈優化之系列子計畫。
- **[UMBRELLA:DR-02] 確立增量動態演進模式**：本主計畫不設靜態全域邊界，採增量滾動模式，各模組工具鏈優化項目隨需開立子計畫推進。

