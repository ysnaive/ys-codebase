# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：dev 測試架構優化 (Dev Test Architecture Optimization)  
> 建立日期：2026-08-27  
> 所屬主計畫：無 (分類型主計畫 Umbrella)  
> 狀態：`Completed`  
> 計畫類型：Refactor / Performance / Architecture  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 開啟新分類型計畫 dev 測試架構優化
  2. 建立第一子計畫，殘留 sandbox 清理，現當測試失敗時，會保留沙盒環境，但沒有清除機制，導致在開發過程中持續增量占用硬碟空間。
- **核心目標**：
  1. 統籌 `dev` 測試架構系列優化，建立清晰的 Umbrella 子計畫矩陣。
  2. 以 `sub_01` 優先解決測試失敗或手動保留所產生之殘留虛擬沙盒 (`cache://dev/sandbox/sandbox_*`) 的檢視、清理與管理機制。
- **邊界排除 (Explicitly Excluded)**：不涉及與測試/沙盒無關的 core 模組核心排程邏輯。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫拆分決策**：第一子計畫定名為 `sub_01_residual_sandbox_cleanup`，聚焦於殘留沙盒清理與磁碟佔用釋放機制。

---

## 3. 開放議題與確認紀錄

- [x] 第一子計畫方向確認：殘留 sandbox 清理。
