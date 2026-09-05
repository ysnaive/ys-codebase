# 計畫變更紀錄 (Changelog)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-05 14:23 | `PHASE` | 完成 Phase 7 成果展示 (P07_walkthrough.md) 與版本發布 (core@1.0.3.2, dev@1.0.1.13)，子計畫圓滿結案 |
| 2026-09-05 14:21 | `FEAT` | Summary 統計支援 Unknown 報告：於 TestRunner 運行前預先保留測試實例引用（規避 Python unittest suite 執行後清空為 None 機制），當存在 UNKNOWN 案例時，於 summary 與 throttled 輸出精準呈遞 Unknown 數量 |
| 2026-09-05 14:17 | `FIX` | 根治假失敗洗版：於 YSCBTestCase 引入三態分類 (PASSED / FAILED / UNKNOWN)，未顯式 mark_passed 且無異常之測試精準歸類為 UNKNOWN，徹底杜絕 tearDown 誤報 [Test Failed] 與輸出污染 |
| 2026-09-05 14:11 | `PHASE` | 完成 Phase 5 實作與 Phase 6 自動化測試驗證：完成 dev/core 測試純化整併、刪除零散測試檔、標註 WORKFLOW 重型測試、雙軌測試 100% 通過，抵達 P06 手動/UX 驗收 Checkpoint |
| 2026-09-05 14:04 | `PHASE` | 連續推進 Phase 2~4 並完成定稿 (P02, P03, P04, P06 Confirmed)，啟動 Phase 5 任務實作 (P05_task.md) |
| 2026-09-05 14:02 | `PHASE` | 完成 Phase 1 需求規格轉譯，產出 P01_requirements_spec.md (FR-01~04, EC-01~03, NFR-01~03) |
| 2026-09-05 13:59 | `DECISION` | 確立 [P00:DR-02] 測試純化三維策略矩陣（合併同質測試、淘汰重複案例、重型高耗時測試遷移至 WORKFLOW 分類）與 [P00:DR-03] 零回歸保證 |
| 2026-09-05 13:59 | `DECISION` | 確立 [P00:DR-01] 子計畫編號接續為 sub_04，採 Full Track 推進 |
| 2026-09-05 13:59 | `PHASE` | 建立子計畫目錄，伴隨產出 P00 與本變更日誌 (狀態：`Confirmed`) |
