# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Discussing  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-28 01:55 | `PHASE` | 開發者確認定稿 P00 語意需求 (狀態：`Confirmed`)，執行 /Pause 凍結現場快照 |
| 2026-08-28 01:54 | `DECISION` | 依開發者架構指示移除 `default_space` 約束：系統直接接納所有注入與組態空間，全域處理範圍天然為所有有效 Space 之聯集 (Union Scope)，擴充 `scan_all_spaces` 聯集掃描 ([P00:DR-03]) |
| 2026-08-28 01:51 | `DECISION` | 依開發者架構指導進行 Schema 解耦：`SpaceConfig` 採用 `include`/`exclude`/`file_patterns`（選填，未定義時預設 include all），`Thesaurus` 獨立為專屬同義詞組清單，消除一體式緊耦合 ([P00:DR-02], [P00:DR-03]) |
| 2026-08-28 01:47 | `DECISION` | 依開發者提醒校準模組注入途徑：明確定義 donor 模組直接以 `contributes.knowledge-db.json` 或 `manifest.json` 進行注入，專案/本機以 `config.project.json`/`config.local.json` 進行宣告與覆蓋 ([P00:DR-03]) |
| 2026-08-28 01:44 | `DECISION` | 依開發者指示完整設計 `contributes.knowledge-db` 擴充點規格（`spaces`, `thesaurus`, `parsers`）、Schema 欄位契約、JSON 範本、`source/knowledge-db/contributes.format.md` 交付物與 SpaceManager 階層式聚合流程 ([P00:DR-03]) |
| 2026-08-28 01:42 | `DECISION` | 依開發者指示全面深化 P00 規格：補齊 Manifest、Schema 完整欄位型別、雙軌空間注入格式與優先權、雙階指紋比對演算法、API 契約與例外階層 ([P00:DR-01]~[P00:DR-05]) |
| 2026-08-28 01:39 | `DECISION` | 依開發者回饋修訂空間定義架構為「模組 contributes 聯動注入 + 2x2 config 檔」雙軌機制 ([P00:DR-02]) |
| 2026-08-28 01:35 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 與本變更日誌 (狀態：`Discussing`) |
