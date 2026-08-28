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

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (主計畫初始化與模式確立)**：完成 Umbrella 主計畫立項，確立增量滾動推進機制與無固定邊界模式。
- [x] **里程碑 2 (sub_01 啟動與 R01 調研)**：開立 `sub_01` 子計畫並產出 `R01_core_contributes_architecture_and_file_structure.md` 專題架構調研。
- [x] **里程碑 3 (sub_01 實作與驗收)**：完成 sub_01 規格、實作、全模組回歸驗證 (164/164 Passed) 與知識庫交付。



---

## 4. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 開立分類型主計畫**：開立 Umbrella 主計畫 `plans://2026_08_28_1754_module_toolchain_optimization/`，統籌各模組工具鏈優化之系列子計畫。
- **[UMBRELLA:DR-02] 確立增量動態演進模式**：本主計畫不設靜態全域邊界，採增量滾動模式，各模組工具鏈優化項目隨需開立子計畫推進。

