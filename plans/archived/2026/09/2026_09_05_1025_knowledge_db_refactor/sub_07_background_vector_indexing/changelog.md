# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge_db_background_vector_indexing  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed (Testing & Verification Passed)  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| 2026-09-05 12:10 | `FEAT` | 延伸優化 Core 組態軟合併邏輯：`_deep_infill_dict` 實裝 `project_data` 隔離，在 local 層級軟合併時若 project 已存在對應設定自動跳過，杜絕本機預設值意外掩蓋專案共享設定 (FT-17，119/119 通過) |
| 2026-09-05 11:57 | `REFACTOR` | 調整 `configurable/` 模板職責隔離：`config.project.json` 僅保留架構層全域設定 (`enable_vector_search`, `embedding_model`)；`config.local.json` 統一承載本機效能與背景服務偏好 (`jit_vector_timeout_seconds`, `max_threads`, `enable_hot_reload_server`, `hot_reload_server_inactivity_timer_sec`)，並補齊測試驗證 |
| 2026-09-05 11:53 | `FEAT` | 補齊 `configurable/config.project.json` 與 `configurable/config.local.json` 標準模組設定檔模板，落實 Core Engine 自動 deep_infill 部署至 `config://knowledge-db/` (148/148 通過) |
| 2026-09-05 11:45 | `FEAT` | 全域清查並落實 Contributes 驅動原則：ParserRegistry 暴露 `get_supported_extensions`，Watcher 初篩與 Space exclude/pattern 雙軌動態判定 (`is_path_watched`)，SpaceManager 階層覆蓋修復，完成本地物化安裝 (FT-16，147/147 通過) |
| 2026-09-05 11:30 | `FEAT` | 擴充實作 FR-12 (CLI 探測後台 Server 輸出提示並跳過 JIT)、FR-13 (Server 啟動離線檢查與熱修補)、FR-14 (啟用 Server 時 JIT 設定失效) 與動態 Space 監控及空間簽名重啟 (FT-12~15，146/146 通過) |
| 2026-09-05 11:20 | `PHASE` | 完成 Phase 5 編碼與測試實作，通過 142/142 (100%) 單元測試，抵達 Phase 6 驗收 Checkpoint |
| 2026-09-05 11:15 | `PHASE` | 完成 Phase 4 定稿審查，產出 `P04_implementation_plan.md`，定稿 `P06_test_plan.md` (Confirmed) |
| 2026-09-05 11:15 | `PHASE` | 完成 Phase 3 API 規格訂定，產出 `P03_api_spec.md` (HotReloadServer, DaemonInfo, Hook) |
| 2026-09-05 11:14 | `PHASE` | 完成 Phase 2 架構設計，產出 `P02_architecture_plan.md`，初始化 `P06_test_plan.md` (Draft) |
| 2026-09-05 11:12 | `PHASE` | 擴充 Phase 1 規格：落實 FR-09 (cache:// PID 隔離)、FR-10 (滾動 3 份日誌)、FR-11 (版本變更強制重啟) 與 [P01:DR-04] |
| 2026-09-05 11:08 | `PHASE` | 完成 Phase 1 規格轉譯，產出 `P01_requirements_spec.md` (FR-01~08, EC-01~06, [P01:DR-01]~[P01:DR-03]) |
| 2026-09-05 11:06 | `PHASE` | 依開發者裁定採出口 ① 恢復推進，定案 [P00:DR-01]~[P00:DR-05] (狀態：`Confirmed`) |
| 2026-09-05 11:00 | `RESEARCH` | 完成專屬 Server 與 Watcher 可行性評估，落檔 `R01_indexing_server_and_watcher_feasibility.md`，推薦採雙軌融合架構 (Hybrid) |
| 2026-09-05 10:59 | `PHASE` | 依開發者指示暫停當前推進，建立 `handoff.md` 完成現場上下文凍結 (狀態：`Paused`) |
| 2026-09-05 10:57 | `PHASE` | 開立 sub_07 計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Confirmed`) |
| 2026-09-05 10:57 | `DECISION` | [P00:DR-01]~[P00:DR-04] 定案背景熱建置組態、非同步進程排程、現有資料優先檢索與原子鎖定機制 |
