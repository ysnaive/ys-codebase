# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：core_dev_toolchain_upgrade  
> 建立日期：2026-09-05  
> 狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面升級 `core` 與 `dev` 基礎工具鏈，因應近期 `core` 模組所引入的私有微環境與 `pip_dependencies` 相依性治理架構，由 `core` 正式對外開放微環境與 Pip 管理工具 SDK，並重構升級 `dev` 開發工具鏈，使其在建置虛擬基環境（沙盒）之前對當前 build 版與待測模組進行 pip 相依性適配與環境物化，確保跨模組單元與沙盒測試的高保真度與穩定性。
- **架構邊界**：
  - **包含範圍**：
    - `core` 模組導出 `PipManager`、`PipInstallError` 等 SDK 與微環境操作門面，提供外部模組調用標準契約。
    - `dev` 模組在建置沙盒虛擬基環境之前，支援對當前 build 版（或源碼/build 產物中的 `pip_dependencies`）進行相依性解析與 pip 適配。
    - `dev` 沙盒環境對微環境 site-packages 的安全穿透/共享機制，防止沙盒執行期間遺失 pip 依賴。
    - `dev check` 與 `dev release-check` 靜態合規性檢查中加入 `pip_dependencies` 格式與規範防護。
    - 相關自動化測試套件與架構文檔更新。
  - **明確排除 (Excluded)**：
    - 不更動 `core` 底層以 Wheel-Only 為核心的安全性防護原則。
    - 不更動生態系模組的標準三態生命週期（源碼、測試、運行）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_pip_sdk_and_environment_export` | Full Track | `Completed` | `core` 開放 `PipManager`、`PipInstallError` 與微環境解析等 SDK 介面，支援路徑靈活配置與標準契約導出。 |
| **sub_02** | `sub_02_dev_toolchain_pip_adaptation_and_sandbox_integration` | Full Track | `Pending` | `dev` 工具鏈升級，支援建置虛擬基環境前對當前 build 版進行 pip 適配，沙盒環境相依性繼承，以及 `dev check` 合規檢查。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (sub_01)**：`core` 模組正式導出 Pip 工具鏈 SDK 與微環境契約，單元測試通過並完成版本發布與熱重載。
- [ ] **里程碑 2 (sub_02)**：`dev` 工具鏈完成 build 版 pip 適配與沙盒微環境整合，具備 pip 依賴之模組沙盒跑測 100% 通過。
- [ ] **里程碑 3 (Final Verification & Docs)**：全生態系端到端回歸驗證通過，更新 `docs/core` 與 `docs/dev` 相關知識庫文檔，結案歸檔。
