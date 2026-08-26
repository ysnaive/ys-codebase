# 計畫變更紀錄 (Changelog)

> 功能名稱：語意化 Codebase 知識庫模組開發 (Codebase Knowledge Module)  
> 模板版本：v1.0  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
|---------|------|------|
| 2026-08-23 14:03 | `PAUSE` | 開發者發起 /Pause 暫停開發，凍結現場上下文並建立 `handoff.md`，等待下次 /Continue 喚醒 |
| 2026-08-23 14:02 | `DECISION` | 完成 /grill-me 5 大架構分支地毯式審計：(1) 定名 `knowledge-db`；(2) 動態可插拔解析器介面；(3) 雙層同義詞合併；(4) BM25+Exact Name 複合評分；(5) 全面連動與自動索引；(6) 快取路徑列為延伸議題 |
| 2026-08-23 13:43 | `DECISION` | 開發者明確裁決模組名稱定名為 `knowledge-db`，收斂開放議題 1~3 |
| 2026-08-23 13:37 | `RESEARCH` | 深入調研參考前身 `GC_VEX_V5` 之 `knowledge_db` 架構，產出調研報告 `R01_knowledge_system_reference.md`（倒排索引、多欄位加權 BM25、分詞器與增量指紋快取） |
| 2026-08-23 13:36 | `PHASE` | 開立計畫目錄，雙星伴隨初始化 `P00_semantic_requirements.md` 與 `changelog.md`，進入 Phase 0 語意化需求討論 |

---

## 類型標籤說明

| 標籤 | 用途 |
|------|------|
| `PHASE` | Phase 轉換（含 Checkpoint 通過） |
| `DECISION` | Deep Discussion 結論 |
| `DEVIATION` | 偏差處理記錄 |
| `SUB-PLAN` | 子計畫新增 |
| `SUB-DONE` | 子計畫完成 |
| `CONTEXT` | 跨 Conversation 的新增指示或偏好調整 |
| `EXTENSION` | 專案擴充機制的執行記錄 |
| `RESEARCH` | 調研報告產出與結論更新 |
