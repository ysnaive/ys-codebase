# 計畫變更紀錄 (Changelog)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.1  

---

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-13 17:07 | `PHASE` | sub_01 圓滿結案，產出 P07_walkthrough.md，全量測試 148/148 通過，安裝至 .modules/ 物化 |
| 2026-09-13 17:06 | `REVIEW` | SOP Review 結案審查全數通過：三層文檔對齊、測試覆蓋 148/148 100% 通過、UX 項目確認 [跳過/免測]、計畫驗證 PASS |
| 2026-09-13 17:03 | `TEST` | [RT-01] knowledge-db 全量回歸測試 148/148 100% 通過 (Pass: 148, Fail: 0)，FT-01~13 全數通過 |
| 2026-09-13 17:01 | `PHASE` | 完成 Phase 5 代碼實作與 test_retrieval.py 重構，安裝至 .modules/ 本地自引用驗收 |
| 2026-09-13 16:56 | `DECISION` | [P01:DR-04] 完全移除 DEFAULT_EMBEDDING_DIM 常數（零特例），統一以加載之模型實例屬性為 SSOT，清理冗餘邏輯並重構單元測試 |
| 2026-09-13 16:53 | `DECISION` | [P01:DR-03] 維度統一採實際加載之 self._model.embedding_size 為 SSOT；確認 core 已在 1.1.0 全域攔截 --help，FR-05 聚焦模型名補齊 |
| 2026-09-13 16:50 | `PHASE` | 完成 Phase 1 規格轉譯，產出 P01_requirements_spec.md (FR-01~05, EC-01~05) |
| 2026-09-13 16:48 | `INIT` | 開立 sub_01 子計畫，伴隨建立 P00 需求討論說明書與微觀日誌 |
