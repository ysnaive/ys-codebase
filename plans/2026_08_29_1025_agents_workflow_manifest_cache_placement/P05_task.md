# 實作任務清單 (Task Breakdown)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立專案根目錄 `.gitattributes` 宣告純文字統一 `eol=lf`。
- [x] **TASK-02**：在 `targets.py` 新增 `ReleaseTargetManager.get_classified_targets()`。
- [x] **TASK-03**：在 `publisher.py` 實作雙軌 Manifest（`storage` 存 `project://`，`cache` 存絕對路徑）、孤立 Pruning 與 `newline="\n"` 寫檔。
- [x] **TASK-04**：標準化現存 `release_manifest.json` 內容為 `project://` 格式。
- [x] **TASK-05**：編寫自動化測試套件並驗證 100% 通過。


---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 依 P04 規劃執行中 |
