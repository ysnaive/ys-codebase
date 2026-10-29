# 計畫變更紀錄 (Changelog)

> 功能名稱：sub_01_core_locale_engine  
> 建立日期：2026-10-28  
> 所屬主計畫：2026_10_28_1845_core_locale_and_ecosystem_i18n  
> 狀態：In Progress  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.1  

---

## 變更紀錄

| 日期時間 | 類型 | 模型 | 摘要 |
| :--- | :---: | :--- | :--- |
| 2026-10-29 03:39 | `REVISION` | Gemini 4 Argon (Low) | 更新 [REV-01] 並完成 Completed 結案：最終 fallback 統一採用開發團隊母語 ['zh']，先專注於專有名詞治理，CLI/模板/文檔多語系支援收斂至 Roadmap |
| 2026-10-29 03:26 | `REVISION` | Gemini 4 Argon (Low) | 追加 [REV-01] 修訂紀錄：補齊專案預設語系 ['zh', 'en'] 並支援初次安裝系統主語系播種至 config.local.json（保底 ['en']） |
| 2026-10-29 03:09 | `PHASE` | Gemini 4 Argon (Low) | UX-01 標記為 `[跳過/免測]`，完成三層文檔對齊與 P07 結案報告 |
| 2026-10-29 02:57 | `PHASE` | Gemini 4 Argon (Low) | 透過 /auto 完成 P02~P06 架構、API、實作與測試驗證 (core 204 項與 dev 80 項測試 100% 通過) |
| 2026-10-29 02:48 | `DECISION` | Gemini 4 Argon (Low) | 依開發者指示修訂 FR-03 ([P01:DR-02])：移除自動父語系切分 fallback，全面採 100% 顯式優先級鏈 |
| 2026-10-29 02:44 | `PHASE` | Gemini 4 Argon (Low) | 完成 P01 需求規格說明書落檔，定義 FR-01~FR-05、EC-01~EC-05 與 NFR-01~NFR-03 |
| 2026-10-28 18:48 | `PHASE` | Gemini 4 Argon (Low) | 開立 sub_01 子計畫目錄，完成 P00 需求討論說明書落檔 |
| 2026-10-28 18:48 | `PHASE` | Gemini 4 Argon (Low) | 自動初始化變更日誌 (changelog.md) |
