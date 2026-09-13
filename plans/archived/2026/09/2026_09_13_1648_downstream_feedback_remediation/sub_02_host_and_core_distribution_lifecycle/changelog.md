# 計畫變更紀錄 (Changelog)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-13 18:40 | `PHASE` | Phase 7 成果展示與結案完成，產出 P07_walkthrough.md 並追加全域 CHANGELOG.md (狀態：`Completed`) |
| 2026-09-13 18:38 | `REVIEW` | SOP Review 審查完成：三層文檔對齊、9/9 單元測試、5 模組合規與 plan verify 100% 通過，UX-01 開發者驗收通過 |
| 2026-09-13 18:35 | `DECISION` | 確立 init 與 self-update 為唯二不經由 core 轉發的宿主自舉指令：支援獨立 -h/--help 渲染，明確拒絕 core 前綴轉發 |
| 2026-09-13 18:30 | `FEATURE` | 補齊 init 與 self-update 宿主自舉指令之獨立 -h/--help 結構化幫助渲染 |
| 2026-09-13 18:15 | `FIX` | 打磨 init --fix 健康檢查機制：在 core 完好時輸出已就緒無需修復，避免無條件刷新；支援 --force 強制覆蓋 |
| 2026-09-13 18:10 | `PHASE` | 連續推進 (/Auto)：Phase 5 實作與 Phase 6 自動化測試全數通過 (8/8)，抵達 UX 驗收 Checkpoint |
| 2026-09-13 18:00 | `PHASE` | 連續推進 (/Auto)：完成 P01 規格、P02 架構、P03 API、P04 定稿審查與 P06 測試計畫確認，進入 Phase 5 實作階段 |
| 2026-09-13 17:58 | `DECISION` | 捨棄 [P00:DR-03] 改由 [P00:DR-05] 統一吸收，確立 fix 自癒後強制連鎖自動觸發 core reload |
| 2026-09-13 17:56 | `DECISION` | 補充 [P00:DR-05]：init 擴充 --fix 自癒修復能力，全新 init 預設 yscb_root 改為 .yscb |
| 2026-09-13 17:48 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing`) |
