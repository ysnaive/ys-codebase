# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：core 與 dev 模組功能打磨 (Core & Dev Modules Refinement)  
> 建立日期：2026-08-26  
> 所屬主計畫：無（主計畫）  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：建立新主計畫: core & dev 功能打磨。本計畫為分類型主計畫，現在起子計畫 01，模組資料管理相關 uri 協議釐清與遷移。
- **核心目標**：以 Level 2 Umbrella 分類型主計畫模式統籌推進 `core` 與 `dev` 模組的功能打磨、體驗優化與架構健全化。
- **邊界排除 (Explicitly Excluded)**：主計畫本身不直接撰寫代碼，專注於架構總綱、子計畫拆分與依賴協調。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Umbrella 主計畫模式定調**：本計畫採用模式 B（分類型主計畫 Umbrella），以 `umbrella_overview.md` 統籌協調，拆分多個 `sub_XX` 子計畫獨立推進各項打磨專題。
- **[P00:DR-02] 子計畫 01 範疇鎖定**：優先啟動 `sub_01_module_data_uri_refactor`，聚焦於「模組資料管理相關 URI 協議釐清與遷移」。

---

## 3. 開放議題與確認紀錄

- [x] **已確認分流**：Level 2（Umbrella 分類型主計畫模式）
