# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 模組開發 (Knowledge Database Module)  
> 建立日期：2026-08-27  
> 所屬主計畫：無 (分類型主計畫 Umbrella)  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-28 15:53 | `PHASE` | 執行 /Review 工作流完成五維度品質審查，交付 Core 解析嚴格化、Build 包隔離與資料庫本地端快取儲存遷移 (cache://knowledge-db/) |
| 2026-08-28 14:45 | `PHASE` | 主計畫下四大子計畫 (sub_01~sub_04) 全數圓滿完工，37/37 單元測試 100% Passed，模組正式發布並結案 |
| 2026-08-28 14:44 | `PHASE` | sub_04_cli_sdk_and_workflow_interlock 完工，交付 KnowledgeEngine Facade SDK 與 6 大 CLI 指令 |
| 2026-08-28 13:54 | `PHASE` | sub_03_tokenizer_thesaurus_and_bm25_retrieval 完工，交付 CodeTokenizer, ThesaurusEngine, BM25Engine |
| 2026-08-28 13:40 | `PHASE` | sub_02_parsers_and_semantic_bundler 完工，交付 ParserRegistry, 4 大多語言解析器與 SemanticBundler |
| 2026-08-28 01:50 | `PHASE` | sub_01_space_management_and_schema 完工，交付 SpaceManager, 2x2 組態, FingerprintScanner |
| 2026-08-28 01:35 | `PHASE` | 開發者確認定稿 P00 語意需求與四大子計畫矩陣 (狀態：`Confirmed`)，正式啟動 sub_01 |
| 2026-08-27 21:43 | `RESEARCH` | 產出 R01 專題架構調研報告，確立四大子系統維度劃分與 sub_01~sub_04 執行矩陣 ([P00:DR-03]) |
| 2026-08-27 21:35 | `DECISION` | 引用 GC_VEX_V5 原型架構實踐，確立純標準庫 Zero Dependency、BM25 多欄位加權與分詞同義詞等核心基底 ([P00:DR-02]) |
| 2026-08-27 21:27 | `PHASE` | 開立分類型主計畫目錄，伴隨建立 P00、umbrella_overview 與本變更日誌 (狀態：`Discussing`) |
