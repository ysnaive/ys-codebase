# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 計畫類型：Refactor / Optimization  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 使用者原始需求與意圖 (User Intent)

本子計畫 `sub_02` 聚焦於 **微內核 `core` 模組的 contribute 依賴注入系統優化** 與 **語意 URI 路徑系統及時熱補齊打磨**：
- **核心目標 1 (`__provider__` 來源標記)**：在微內核搜集階段為 Dict 與 List[Dict] 項目自動注入 `"__provider__": donor_module_name`，達成 100% 來源可追溯性。
- **核心目標 2 (拓撲排序與 SDK)**：聚合引擎嚴格按照依賴拓撲順序遍歷模組；`core` 提供標準查詢 SDK `core.contributes.get()` 與 `get_for_current_module()`。
- **核心目標 3 (`!undefined` JIT 熱補齊引擎)**：`uri.resolve()` 遇到 `!undefined` 時自動攔截並彈出終端互動提示（`[-y <path> / -n / --help]`），支援 `yscb://` 相對基準、複合協議輸入、連鎖依賴遞迴補齊與自引用防護，自動持久化寫回 `config.project.json` 並熱重載無縫繼續執行。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `__provider__` 來源標記**：在自動搜集階段為物件與列表物件自動注入來源模組名稱，非破壞性且不覆蓋顯式指定值。
- **[P00:DR-02] 依賴拓撲順序保證**：依賴解析器提供已安裝模組的 Topological Order，保證基礎模組先於擴充模組被合併。
- **[P00:DR-03] 微內核高階查詢 SDK**：提供 `core.contributes.get(target, key)`，內建快取與損毀自動重聚自愈。
- **[P00:DR-04] `!undefined` JIT 及時熱補齊與 `--help` 展開**：
  - 互動模式下彈出 `[-y <path> / -n / --help]` 提示，明確標明 `yscb://` 相對基準。
  - 輸入 `--help` 展開該協議詳細定義並即時列出全系統已註冊之可用 URI 協議清冊。
  - 支援連鎖未定義協議遞迴先補齊基礎協議，並提供 `_reconciling_tokens` 自引用循環防護。
  - 自動定位寫回 `config.root://{__provider__}/config.project.json` 並記憶體熱刷新。
  - 非互動或靜態診斷模式拋出結構化 `UndefinedURIError`。

---

## 3. 開放議題與確認紀錄

- [x] Contribute 自動來源標記機制已釐清
- [x] 拓撲依賴排序與 SDK 介面已定案
- [x] `!undefined` JIT 及時熱補齊、`--help` 協議清單與連鎖防護已定案
