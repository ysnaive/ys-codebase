# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與架構設計中有對應介面與資料流。
- [x] **邊界防護**：EC-01 ~ EC-04 均有具體防禦實作策略（異機絕對路徑容錯、單軌/混合分流）。
- [x] **依賴純淨**：100% Python 標準庫，無引入任何第三方模組。
- [x] **測試覆蓋**：FT-01 ~ FT-06 與 RT-01 完整覆蓋各需求項，於 P06 剛性定稿。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 4** | `docs/agents-workflow/FACTORY_PIPELINE.md` | Modify | 更新雙軌 Manifest（Project 軌 `storage://` 與 Local 軌 `cache://`）發布管線與路徑規範 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發團隊跨主機/跨作業系統協作，且各開發者專案目錄結構名稱不同，`storage://` 中的 `project://` 協議是否會失效？  
> 💡 **防護解法**：`project://` 為相對於專案根目錄之語意協議路徑（如 `project://.agents/workflows/Auto.md`），在各主機上解算時一律由該環境之 `core.uri` 動態映射為本地實體絕對路徑，具備 100% 跨平台可攜性，徹底免疫絕對路徑漂移。

> ❓ **尖銳問題 2**：若同一檔案路徑同時被 Local Target 與 Project Target 產出（或先後由不同層級 Target 產出），孤立清理 (Pruning) 是否會發生誤刪？  
> 💡 **防護解法**：在刪除孤立檔案前，發布引擎會先匯總計算出本次所有活躍 Target 物化的「全量目標檔案實體路徑集合」，僅對「完全不在本次產出集合內」的孤立檔案執行實體刪除，杜絕跨軌誤刪。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：建立專案根目錄 [`.gitattributes`](file:///d:/repos/ys_codebase/.gitattributes) 宣告純文字統一 `eol=lf`。
- [ ] **TASK-02**：在 [`targets.py`](file:///d:/repos/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/targets.py) 新增 `get_classified_targets()` 支援分軌 Targets 查詢。
- [ ] **TASK-03**：在 [`publisher.py`](file:///d:/repos/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/publisher.py) 實作雙軌 Manifest、`project://` 路徑轉換、舊 Manifest 容錯與寫檔 `newline="\n"`。
- [ ] **TASK-04**：標準化專案現存之 [`release_manifest.json`](file:///d:/repos/ys_codebase/ys_codebase/storage/agents-workflow/release_manifest.json) 內容為 `project://` 格式。
- [ ] **TASK-05**：編寫單元與整合測試案例並於沙盒中驗證 100% 通過。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 正式定稿雙軌發布 Manifest 架構與換行符號歸一化標準，同意進入 Phase 5 編碼實作。
