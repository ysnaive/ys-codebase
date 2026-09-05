# 計畫變更紀錄 (Changelog)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-05 16:11 | `PHASE` | 通過 SOP Review 品質審查，產出 P07_walkthrough.md 結案報告，子計畫圓滿結案 (狀態：`Completed`) |
| 2026-09-05 16:08 | `PHASE` | 完成 Phase 6 全部測試與 UX-01 實機驗證（124/124 通過，hot-rebuild 231 檔 10.4s 零卡死），抵達 Review 審查閘門 |
| 2026-09-05 16:00 | `DECISION` | 登載索引建置防護與效能優化決策 ([P06:DR-01])：ONNX 執行緒上限 (min(2, max(1, cpu//2)))、分批推論時間片讓渡、VectorIndex compresslevel=1、Worker 內 ParserRegistry 快取化、調用點 AST 重用避免二次解析 |
| 2026-09-05 15:44 | `PHASE` | 進入 Phase 6 驗收階段，自動化測試 100% 通過 (123/123)，抵達 UX 驗收 Checkpoint |
| 2026-09-05 15:43 | `PHASE` | 完成 Phase 5 編碼實作與本機物化驗證 (TASK-01~06 全數落實完成) |
| 2026-09-05 15:26 | `PHASE` | 進入 Phase 5 任務實作，產出 P05_task.md (狀態：`In Progress`) |
| 2026-09-05 15:26 | `PHASE` | 完成 Phase 4 定稿審查 (P04_implementation_plan.md) 與 P06 測試計畫確認 (狀態：`Confirmed`) |
| 2026-09-05 15:26 | `PHASE` | 完成 Phase 3 API 規格定義，產出 P03_api_spec.md (狀態：`Confirmed`) |
| 2026-09-05 15:25 | `PHASE` | 完成 Phase 2 架構設計 (P02_architecture_plan.md) 與 P06 測試計畫初始化 (狀態：`Confirmed`) |
| 2026-09-05 15:24 | `DECISION` | 強化全域重複資訊剔除：不限於特定註解或標題，對任何與已呈現資訊重複者全面剔除，最大化 8,000 字元資訊密度 ([P00:DR-05]、FR-06) |
| 2026-09-05 15:18 | `PHASE` | 完成 Phase 1 需求規格轉譯，產出 P01_requirements_spec.md (狀態：`Confirmed`) |
| 2026-09-05 15:16 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing`) |
| 2026-09-05 15:16 | `DECISION` | 定調格式化器解耦 (`formatter.py`)、索引流程流水線化 (`pipeline.py`) 與 100% 相容門面中樞架構 ([P00:DR-01~04]) |
