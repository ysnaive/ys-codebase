# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-28 13:33 | `PHASE` | 推進 Phase 7 (成果展示與結案)，產出 P07_walkthrough.md，1:1 交付 3 份 docs 文檔，追加全域 CHANGELOG，子計畫正式結案 (Completed) |
| 2026-08-28 13:31 | `TEST` | 推進 Phase 6 (測試與驗證)，實機執行 python yscb.py dev test knowledge-db，全模組 15/15 測試案例 100% Passed (3.400s)，回填 P06_test_plan.md |
| 2026-08-28 13:31 | `PHASE` | 推進 Phase 5 (依序程式碼實作)，依拓撲完成 TASK-01~06 實作，包含 exceptions.py、schema.py、space.py、scanner.py、cli.py、manifest.json 與完整測試套件 |
| 2026-08-28 13:29 | `PHASE` | 推進 Phase 4 (實作計畫與定稿審查)，產出 P04_implementation_plan.md (Confirmed)，交叉驗證 FR/EC/NFR，通過 2 項架構靈魂拷問，同步剛性定稿 P06_test_plan.md (Confirmed) |
| 2026-08-28 13:29 | `PHASE` | 推進 Phase 3 (API 與介面規格定義)，產出 P03_api_spec.md (Confirmed)，定義完整模型簽名、SpaceManager 與 FingerprintScanner 契約與依賴拓撲 |
| 2026-08-28 13:28 | `PHASE` | 推進 Phase 2 (架構與模組設計)，產出 P02_architecture_plan.md (Confirmed)，同步 Test-First 初始化 P06_test_plan.md (Draft)，規劃 FT-01~09、ET-01~03 與 RT-01 |
| 2026-08-28 13:27 | `PHASE` | 啟動 Phase 1 (需求規格轉譯)，產出 P01_requirements_spec.md (Confirmed)，1:1 轉譯 FR-01~FR-10、EC-01~EC-08 與 NFR-01~NFR-04 |
| 2026-08-28 01:55 | `PHASE` | 開發者確認定稿 P00 語意需求 (狀態：`Confirmed`)，執行 /Pause 凍結現場快照 |
| 2026-08-28 01:54 | `DECISION` | 依開發者架構指示移除 `default_space` 約束：系統直接接納所有注入與組態空間，全域處理範圍天然為所有有效 Space 之聯集 (Union Scope)，擴充 `scan_all_spaces` 聯集掃描 ([P00:DR-03]) |
| 2026-08-28 01:51 | `DECISION` | 依開發者架構指導進行 Schema 解耦：`SpaceConfig` 採用 `include`/`exclude`/`file_patterns`（選填，未定義時預設 include all），`Thesaurus` 獨立為專屬同義詞組清單，消除一體式緊耦合 ([P00:DR-02], [P00:DR-03]) |
| 2026-08-28 01:47 | `DECISION` | 依開發者提醒校準模組注入途徑：明確定義 donor 模組直接以 `contributes.knowledge-db.json` 或 `manifest.json` 進行注入，專案/本機以 `config.project.json`/`config.local.json` 進行宣告與覆蓋 ([P00:DR-03]) |
| 2026-08-28 01:44 | `DECISION` | 依開發者指示完整設計 `contributes.knowledge-db` 擴充點規格（`spaces`, `thesaurus`, `parsers`）、Schema 欄位契約、JSON 範本、`source/knowledge-db/contributes.format.md` 交付物與 SpaceManager 階層式聚合流程 ([P00:DR-03]) |
| 2026-08-28 01:42 | `DECISION` | 依開發者指示全面深化 P00 規格：補齊 Manifest、Schema 完整欄位型別、雙軌空間注入格式與優先權、雙階指紋比對演算法、API 契約與例外階層 ([P00:DR-01]~[P00:DR-05]) |
| 2026-08-28 01:39 | `DECISION` | 依開發者回饋修訂空間定義架構為「模組 contributes 聯動注入 + 2x2 config 檔」雙軌機制 ([P00:DR-02]) |
| 2026-08-28 01:35 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing`) |
