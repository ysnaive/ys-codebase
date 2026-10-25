# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於 `sub_01 (core)`、`sub_02 (dev)`、`sub_03 (server)`、`sub_04 (knowledge-db)` 全部完成後，執行跨模組端到端二次驗收、8 份已消費 Roadmap 儲備閉環遷移、全模組 `@build` 部署與三層文檔結案。
- **核心目標**：
  1. 執行全生態系 `python yscb.py contributes check`、`python yscb.py dev check --all` 與 `python yscb.py dev test --all -q` 聯合驗收，確認 0 Error、0 Warning、0 Unknown、100% Passed 且工作區 `git status` 零環境污染殘留。
  2. 實機驗證常駐 `server` 啟動後自動透過 `ServiceManager` 載入並啟動 `knowledge-db-watcher`，且多層子命令（如 `uri resolve`、`config get`、`contributes check`）透過 `_try_hot_dispatch` 熱派發與優雅停機握手 100% 正常運作。
  3. 將本主計畫消費之 8 份 Roadmap 儲備檔案閉環遷移歸檔，同步對齊三層文檔（`CHANGELOG.md`、`docs/`、模組 `README.md`）並完成全模組 `@build` 最終熱部署。
- **邊界排除 (Explicitly Excluded)**：不在此階段引入新的未規劃功能。
- **架構影響範圍**：`ys_codebase/source/{core,dev,server,knowledge-db}/`、`plans/roadmap/`、`docs/` 與 `CHANGELOG.md`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **收尾二次驗收與儲備遷移閉環**：集中於最後一棒執行跨模組整合驗證與 8 份路線圖儲備清理，確保主計畫交付 100% 乾淨閉環。

---

## 3. 開放議題與確認紀錄

- 規格與驗收範圍已 100% 確認收斂，狀態標記為 `Confirmed`。

