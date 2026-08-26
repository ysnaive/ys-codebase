# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：core 與 dev 模組功能打磨 (Core & Dev Modules Refinement)  
> 建立日期：2026-08-26  
> 計畫狀態：Executing  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：打磨 `core` 與 `dev` 基礎設施與開發工具鏈模組，完善 URI 協議體系、微內核持久化與快取、打包構建與測試流水線，提升整體系統穩定度與工程體驗。
- **架構邊界**：主計畫本身專注於架構總綱、子計畫矩陣管理與全域依賴協調，具體功能開發與重構透過獨立 `sub_XX` 子計畫完成。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :--- | :--- | :---: | :---: | :--- |
| **sub_01** | [`sub_01_module_data_uri_refactor`](./sub_01_module_data_uri_refactor/) | Level 1 Full Track | `Completed` | 模組資料管理相關 URI 協議釐清與遷移 |
| **sub_02** | [`sub_02_dev_release_verification_refactor`](./sub_02_dev_release_verification_refactor/) | Level 1 Full Track | `Completed` | Dev 模組發布與驗證工具鏈重構 |
| **sub_03** | [`sub_03_dev_release_force_override`](./sub_03_dev_release_force_override/) | Level 0 Fast Track | `Completed` | Dev 模組發布強制覆蓋模式 (--force 支援同版本原地修訂) |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成模組資料管理相關 URI 協議（storage / cache 等）之職責釐清與全面遷移 (`sub_01`)。
- [ ] **里程碑 2**：待依據後續討論追加其他 `core` / `dev` 打磨子計畫。
