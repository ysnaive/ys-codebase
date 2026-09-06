# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 建立日期：2026-09-06  
> 狀態：Draft  
> Umbrella 模式：Incremental (增量演進型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：統整修復近期 `knowledge-db` 系統在各項功能擴展與運行過程中所遭遇之整體架構問題，建立高內聚、低耦合、穩定健壯之系統架構。
- **架構邊界**：涵蓋 `source/knowledge-db` 核心模組之服務架構、生命週期管控、管線排程、快取與索引狀態維護及跨進程通訊，採增量演進滾動拆分推進各子計畫。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_cli_dispatch_and_core_guard_sdk` | Full Track | `Completed` | CLI 串接系統改造：規範宣告 process(args)、禁絕 main、Core 守門 SDK、dev create 骨架預裝與 dev check 靜態檢驗 |
| **sub_02** | `sub_02_core_vfs_unified_virtual_file_system` | Full Track | `Completed` | Core VFS 統一虛擬檔案系統：物件導向 VirtualPath、語意空間整合、跨平台路徑正規化、原子寫入與沙盒防護 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成 sub_01 CLI 串接系統改造與 Core 守門 SDK 實裝 (Phase 0~7)
- [x] **里程碑 2**：完成 sub_02 Core VFS 統一虛擬檔案系統建置與 URI 解耦遷移 (Phase 0~7)
- [ ] **里程碑 3**：依回饋動態推進後續子計畫 (Server Module 等)
- [ ] **里程碑 4**：完成全模組回歸驗證、統一發布至 v1.1.0 (server v1.0.0) 結案並恢復運行端
