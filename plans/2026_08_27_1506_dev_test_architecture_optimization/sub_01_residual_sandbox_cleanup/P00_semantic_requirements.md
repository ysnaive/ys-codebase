# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 計畫類型：Feature / Maintenance  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 建立第一子計畫，殘留 sandbox 清理，現當測試失敗時，會保留沙盒環境，但沒有清除機制，導致在開發過程中持續增量占用硬碟空間。
  2. 直接內建，不需要給予選項：
     - **Case 1**：當 sandbox 緩存保留了第四個沙盒，將最舊的一個刪除（保持殘留上限為 3 個）。
     - **Case 2**：當 `test --all` 選項通過時（必須為 `--all`，`test <mod>` 不適用），清除所有 sandbox 緩存。
- **核心目標**：
  1. **自動滾動修剪 (Rolling Prune)**：沙盒保留上限設定為 3 個。每當生成或保留沙盒導致數量達到 4 個時，自動刪除時間戳最舊的 1 個沙盒，確保殘留沙盒永不超過 3 個。
  2. **全量通過清理 (Full-Pass Flush)**：當執行全模組回歸測試 `python yscb.py dev test --all` 且 100% 通過時，自動清理 `cache://dev/sandbox/` 下的所有殘留歷史沙盒。
  3. **零侵入無選項 (Zero-Config Internal Logic)**：完全內建於 `dev` 測試與沙盒生命週期中，無須開發者手動輸入額外 CLI 參數。
- **邊界排除 (Explicitly Excluded)**：
  - 單一模組跑測 `dev test <mod>` 通過時，不觸發 Case 2 全量清空（僅維持其正常清理當次沙盒，歷史殘留由 Case 1 控管）。
  - 不新增冗餘的手動 CLI 清理開關或選項。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 內建自動化策略**：淘汰手動 CLI 選項設計，改為全自動內建管理機制。
- **[P00:DR-02] 雙軌清理觸發機制**：
  - 軌道一（滾動上限）：殘留沙盒數量 $\ge 4$ 時，自動清理最舊者，常態維持最多 3 個。
  - 軌道二（全系統乾淨交付）：`dev test --all` 成功通過時自動清空整個 sandbox 緩存目錄。

---

## 3. 開放議題與確認紀錄

- [x] 清理機制確定：Case 1 (保留達第 4 個時淘汰最舊) + Case 2 (`test --all` 通過時清空全量緩存)。
- [x] Phase 0 語意需求定稿確認 (Confirmed)。
