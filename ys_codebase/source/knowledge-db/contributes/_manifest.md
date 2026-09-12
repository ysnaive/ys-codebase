# Knowledge-DB 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `knowledge-db` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令與 URI 擴充）
- **語意 URI**：`knowledge.storage://`（知識庫索引與快取空間）。
- **CLI 指令樹**：
  - `knowledge-db search`: 全庫與跨空間語意檢索。
  - `knowledge-db build`: 知識庫增量或全量索引建構。
  - `knowledge-db symbol`: 查詢類別、函式符號與簽名。
  - `knowledge-db callers`: 調用關係追蹤（誰調用了該符號）。
  - `knowledge-db callees`: 被調用依賴追蹤。
  - `knowledge-db impact`: 重構影響半徑分析。
  - `knowledge-db status`: 索引資料庫狀態診斷。

### 1.2 `server.json`（常駐微服務）
- 註冊 `knowledge-db-watcher` 背景 Worker 監聽檔案變更。

### 1.3 `agents-workflow.json`（技能注入）
- 導出 `knowledge-db-search` 領域技能包。

### 1.4 `knowledge-db.json`（自身空間註冊）
- 註冊 `knowledge-db` 模組專屬檢索空間。

## 2. 開放擴充點清冊 (Ingress Points)
- `spaces`: 允許各模組註冊自訂語意檢索空間。
- `thesaurus`: 允許注入領域同義詞典。
