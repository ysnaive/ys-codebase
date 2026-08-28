# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 子計畫 04: CLI 工具鏈、統一門面 SDK、生態整合與本地端快取儲存遷移 (CLI, Unified SDK, Workflow Interlock & Local Cache Storage Migration)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-28 15:53 | `PHASE` | 推進 Phase 7 (成果展示與結案) 與 /Review 工作流，五維度品質審查 100% 通過，交付 docs/knowledge-db 文檔與 root CHANGELOG.md 更新，產出 P07_walkthrough.md (Completed) |
| 2026-08-28 15:52 | `TEST` | 開發者審查通過，P06_test_plan.md 標記為 Passed |
| 2026-08-28 15:51 | `TEST` | 推進 Phase 6 (測試與驗證)，實機執行 python yscb.py dev test core (48/48 Passed) 與 dev test knowledge-db (38/38 Passed)，驗收 FT-11 (快取目錄遷移與解析)，回填 P06_test_plan.md |
| 2026-08-28 15:50 | `PHASE` | 推進 Phase 5 (依序程式碼實作)，修改 space.py, manifest.json, hook.dev.py 將資料庫儲存根目錄遷移至 cache://knowledge-db/，清理舊 storage/ 殘留，標記 P05_task.md Completed |
| 2026-08-28 15:49 | `PHASE` | 推進 Phase 4 (實作計畫定稿與審查)，產出 P04_implementation_plan.md (Confirmed)，通過 2 項快取自癒與舊檔清理架構拷問，同步定稿 P06_test_plan.md (Confirmed) |
| 2026-08-28 15:49 | `PHASE` | 推進 Phase 3 (API 與介面規格定義)，產出 P03_api_spec.md (Confirmed)，定義 SpaceManager._get_storage_root cache:// 解析規格 |
| 2026-08-28 15:48 | `PHASE` | 推進 Phase 2 (架構與模組設計)，產出 P02_architecture_plan.md (Confirmed)，繪製本地快取資料拓撲圖，同步 Test-First 初始化 P06_test_plan.md (Draft) 增加 FT-11 |
| 2026-08-28 15:48 | `PHASE` | 推進 Phase 1 (需求規格轉譯)，產出 P01_requirements_spec.md (Confirmed)，1:1 轉譯 FR-13 (本地端快取儲存) 與 EC-11 (快取遺失自癒) |
| 2026-08-28 15:48 | `PHASE` | 收到 /Auto 指令，開發者授權自動連續推進 Phase 01~05 直至 Phase 6 UX Checkpoint，P00_semantic_requirements.md 標記為 Confirmed |
| 2026-08-28 15:47 | `PHASE` | 擴充 Phase 0 (語意需求說明書)，納入資料庫與索引檔案全面遷移至本地端 cache://knowledge-db/ (.cache/knowledge-db/) 之架構決策 [P00:DR-06]，杜絕專案儲存庫膨脹與 Git 污染 |
| 2026-08-28 15:43 | `TEST` | 推進 Phase 6 (測試與驗證)，實機執行 python yscb.py dev test core (48/48 Passed) 與 dev test knowledge-db (37/37 Passed)，驗收 FT-09 (未發布拋錯) 與 FT-10 (Build 隔離)，回填 P06_test_plan.md |
| 2026-08-28 15:42 | `PHASE` | 推進 Phase 5 (依序程式碼實作)，修改 source/core/core/engine.py 徹底移除 dummy fallback 並實作嚴格 Build 隔離，同步更新 modules/core，清理 .mirror 殘留，標記 P05_task.md Completed |
| 2026-08-28 15:40 | `PHASE` | 推進 Phase 4 (實作計畫定稿與審查)，產出 P04_implementation_plan.md (Confirmed)，通過 3 項架構靈魂拷問，同步定稿 P06_test_plan.md (Confirmed) |
| 2026-08-28 15:39 | `PHASE` | 推進 Phase 3 (API 與介面規格定義)，產出 P03_api_spec.md (Confirmed)，定義 Core 模組 _get_module_manifest_from_provider_or_local 與 act_download 嚴格解析與隔離規格 |
| 2026-08-28 15:39 | `PHASE` | 推進 Phase 2 (架構與模組設計)，產出 P02_architecture_plan.md (Confirmed)，繪製 Core 依賴求解與 Build 隔離循序圖，同步 Test-First 初始化 P06_test_plan.md (Draft) 增加 FT-09/FT-10 |
| 2026-08-28 15:39 | `PHASE` | 推進 Phase 1 (需求規格轉譯)，產出 P01_requirements_spec.md (Confirmed)，1:1 轉譯 FR-11 (嚴格解析)、FR-12 (Build 隔離) 與 EC-09, EC-10 |
| 2026-08-28 15:38 | `PHASE` | 收到 /Auto 指令，開發者授權自動連續推進 Phase 01~05 直至 Phase 6 UX Checkpoint，P00_semantic_requirements.md 標記為 Confirmed |
| 2026-08-28 15:37 | `PHASE` | 擴充 Phase 0 (語意需求說明書)，納入 Core 模組套件解析嚴格化 (廢除 dummy fallback，未發布拋出 ModuleNotFoundError) 與 Build 包物理隔離 (僅 revision == "build" 時觸發) 決策記錄 [P00:DR-04, DR-05] |
| 2026-08-28 14:44 | `PHASE` | 推進 Phase 7 (成果展示與結案)，交付 docs/knowledge-db/README.md 與 architecture.md 更新，產出 P07_walkthrough.md (Completed)，追加 CHANGELOG.md |
| 2026-08-28 14:44 | `TEST` | 開發者審查通過，P06_test_plan.md 標記為 Passed |
| 2026-08-28 14:07 | `TEST` | 推進 Phase 6 (測試與驗證)，實機執行 python yscb.py dev test knowledge-db，全模組 37/37 測試案例 100% Passed (3.990s)，回填 P06_test_plan.md |
| 2026-08-28 14:05 | `PHASE` | 推進 Phase 5 (依序程式碼實作)，完成 TASK-01~04 實作，包含 KnowledgeEngine Facade SDK, hook.dev.py, CLI 6 大完整指令與整合測試套件 |
| 2026-08-28 14:04 | `PHASE` | 推進 Phase 4 (實作計畫與定稿審查)，產出 P04_implementation_plan.md (Confirmed)，交叉驗證 FR/EC/NFR，通過 2 項架構靈魂拷問，同步剛性定稿 P06_test_plan.md (Confirmed) |
| 2026-08-28 14:03 | `PHASE` | 推進 Phase 3 (API 與介面規格定義)，產出 P03_api_spec.md (Confirmed)，定義 KnowledgeEngine, hook.dev.py, CLI 6 大指令介面 |
| 2026-08-28 14:03 | `PHASE` | 推進 Phase 2 (架構與模組設計)，產出 P02_architecture_plan.md (Confirmed)，同步 Test-First 初始化 P06_test_plan.md (Draft)，規劃 FT-01~08、ET-01 與 RT-01 |
| 2026-08-28 14:03 | `PHASE` | 推進 Phase 1 (需求規格轉譯)，產出 P01_requirements_spec.md (Confirmed)，1:1 轉譯 FR-01~10、EC-01~08 與 NFR-01~04 |
| 2026-08-28 14:00 | `PHASE` | 開發者審查確認定稿 P00_semantic_requirements.md (狀態：`Confirmed`)，收斂 KnowledgeEngine SDK、6 大 CLI 指令與生態連動規格 |
| 2026-08-28 13:59 | `PHASE` | 開立 sub_04 子計畫目錄，伴隨建立 P00_semantic_requirements.md 與 changelog.md (狀態：`Discussing`) |
