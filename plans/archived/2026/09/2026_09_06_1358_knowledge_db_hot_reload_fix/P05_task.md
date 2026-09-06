# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 熱重載新增與修改檔案靜默 no-op 修復 (Hot Reload Silent No-op Fix)  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立標準計畫)  
> 狀態：Completed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `source/knowledge-db/knowledge_db/pipeline.py` 實作 `hot_patch_unified_index` 之 `_unified_index` 磁碟懶加載
- [x] **TASK-02**：在 `source/knowledge-db/knowledge_db/daemon.py` 實作 `_execute_debounced_patch` 與 `_run_startup_check` 失敗兜底全量自癒重建與 diff 明細日誌
- [x] **TASK-03**：在 `source/knowledge-db/tests/test_hot_reload_server.py` 編寫單元測試覆蓋 FT-01~03 與 ET-01
- [x] **TASK-04**：在 `source/knowledge-db/knowledge_db/scanner.py` 與 `engine.py` 徹底廢除 `fingerprints.json`，全權收斂至 `unified.meta.bin`
- [x] **TASK-05**：在 `source/knowledge-db/tests/test_scanner.py` 移除舊版 JSON 指紋測試，更新為二進位快照驗證
- [x] **TASK-DOC-19**：在 `docs/knowledge-db/DESIGN_NOTES.md` 追加記錄 `[DN-19]` 物理級 SSOT 廢除 JSON 指紋設計
- [x] **TASK-DOC**：在 `docs/knowledge-db/DESIGN_NOTES.md` 追加記錄 `[DN-18]`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-04/05 | Minor | 依開發者指示拍板「路線 2：物理級 SSOT」，擴充廢除 JSON 指紋並全面收斂至 unified.meta.bin | 依規範增補 TASK-04/05 與更新相關文件 |
