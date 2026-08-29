# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：發布產物二進位儲存與 Git 歷史瘦身優化 (Release Binary Storage & Git History Optimization)  
> 建立日期：2026-08-29  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Draft  
> 計畫類型：Performance  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  使用者發現本專案在僅有 100 個 Commit 的情況下，`.git/` 增長速度異常偏快（Packfile 達 3.03 MiB / 未壓縮物件 4.4 MB），遠高於其他規模更大但純代碼的專案。希望排查原因、尋求不讓二進位包無限堆疊歷史的解決機制（如孤兒發布分支、壓平 Commit、或脫鉤 Git），並提供過往歷史冗餘的清理手段。
- **核心目標**：
  1. **排查並量化根因**：精確分析 `.git/` 空間佔比，證實 `ys_codebase/release/*.zip`（43 個二進位包佔據歷史 2.08 MB 與 Packfile 60%+ 空間）為主要膨脹來源。
  2. **設計未來二進位儲存與發布機制**：制定防二進位無限膨脹方案（評估「孤兒發布分支 (Orphan Branch) + Commit 壓平」與「二進位脫鉤 Git + 僅追蹤 index.json」），使主開發分支 (`main`) 永遠維持極致純文字輕量。
  3. **提供歷史瘦身清理方案**：提供 `git-filter-repo` 一鍵剝離歷史二進位冗餘的標準作業流程。
- **邊界排除 (Explicitly Excluded)**：
  - 本次調研不修改現有 `core` 與 `agents-workflow` 的核心業務邏輯，僅聚焦於發布流程、Git 分支/追蹤策略與儲存架構。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Git 壓縮特性與二進位包衝突**：
  Git 原生 Delta Compression 對純文字具備高達 88%+ 壓縮率，但對 Deflate 已壓縮之 `.zip` 無法計算 diff，每次 Commit 都實打實寫入 100% 尺寸之 Blob。
- **[P00:DR-02] 歷史二進位沉積主因**：
  早期版本曾原地修改覆蓋同名 zip（多達 4~5 次）及刪除/重命名修訂版，導致 14 個當前檔案在 Git 歷史中沉澱了 43 個獨立二進位 Blobs。
- **[P00:DR-03] 發布分支孤兒化與壓平策略論證**：
  評估建立獨立 `release-store` 孤兒分支（Orphan Branch），發布時透過 `--amend` 或定期 Squash，讓發布分支長度恆為 1~2 個 Commit，主分支完全忽略 zip。
- **[P00:DR-04] 歷史瘦身工具選型**：
  選定 Git 官方推薦之 `git-filter-repo` 作為歷史重寫與二進位剝離工具，搭配 `git gc --prune=now --aggressive` 達成極致瘦身。

---

## 3. 開放議題與確認紀錄

- [ ] 確認未來發布架構採「孤兒分支 (Orphan Branch) 壓平模式」或「二進位完全脫鉤 Git (Local/Remote Release)」
- [ ] 確認是否於備份後執行 `git-filter-repo` 進行歷史全量清洗
