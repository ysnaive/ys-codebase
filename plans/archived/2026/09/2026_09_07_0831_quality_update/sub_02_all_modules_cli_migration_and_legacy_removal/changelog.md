# 計畫變更紀錄 (Changelog)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-07 12:38 | `PHASE` | 完成 Phase 7 成果展示與結案報告產出（P07_walkthrough.md），標記 sub_02 結案為 Completed |
| 2026-09-07 12:38 | `PHASE` | 完成 Phase 6 人工/UX 實機驗收（UX-01/UX-02 開發者確認通過），更新 P06_test_plan.md 狀態為 Passed |
| 2026-09-07 12:33 | `ARCH` | 復原 `_maybe_auto_spawn_server` 背景非同步按需拉起機制，移除 `server/scripts/cli.py` 背景模式 `source/core` 殘留，完成自部署與熱派發驗證 |
| 2026-09-07 12:15 | `ARCH` | 剛性鎖定僅允許 `.modules` 運行時空間載入，徹底移除 `yscb.py` 與 `dispatcher.py` 中對 `source/` 的任何 fallback 與搜尋路徑；完成全生態系 5 大模組 `@build` 自部署與回歸測試 |
| 2026-09-07 11:53 | `PHASE` | 完成 Phase 6 自動化測試（FT-01~06, ET-01~03, RT-01 全生態系 5 大模組 486 案例 100% 綠燈通過），更新 P06_test_plan.md，抵達 P06 手動/UX 驗收 Checkpoint |
| 2026-09-07 11:52 | `PHASE` | 完成 Phase 5 編碼實作（TASK-01~05 全面落地，完成 dev/knowledge-db/agents-workflow 模組遷移，dispatcher 剛性拔除 process fallback，更新 P05_task.md 為 Completed） |
| 2026-09-07 11:35 | `DECISION` | 確立 [P04:DR-01] ~ [P04:DR-02]（嚴格拓撲實作順序、各命令函式守護 Token 保全） |
| 2026-09-07 11:35 | `PHASE` | 完成 Phase 4 實作計畫與定稿審查，產出 P04_implementation_plan.md，定稿 P06_test_plan.md (狀態：`Confirmed`) |
| 2026-09-07 11:35 | `PHASE` | 完成 Phase 3 API 規格定義，產出 P03_api_spec.md (三大模組精確命令函式簽名與 Hard Sunset 拓撲) (狀態：`Confirmed`) |
| 2026-09-07 11:34 | `DECISION` | 確立 [P02:DR-01] ~ [P02:DR-04]（dev 頂層指令映射、knowledge-db 查詢指令熱派發分流、plan 複合同構分支與底線平鋪命名、Hard Sunset Gate 剛性拔除過渡層） |
| 2026-09-07 11:34 | `PHASE` | 完成 Phase 2 架構設計，產出 P02_architecture_plan.md 並初始化 P06_test_plan.md (Draft) (狀態：`Confirmed`) |
| 2026-09-07 11:32 | `DECISION` | 確立 [P01:DR-01] ~ [P01:DR-04]（contributes 就地規範、knowledge-db 熱派發矩陣、plan 複合同構分支落地、過渡層拔除回歸斷言） |
| 2026-09-07 11:32 | `PHASE` | 完成 Phase 1 規格轉譯，產出 P01_requirements_spec.md (FR-01~05, EC-01~04, NFR-01~03) (狀態：`Confirmed`) |
| 2026-09-07 11:31 | `DECISION` | 確立 [P00:DR-01] ~ [P00:DR-03]（三模組分步遷移路徑、刪除向後相容層之剛性守門時序、同構遞迴指令樹最佳實踐規範） |
| 2026-09-07 11:31 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing`) |
