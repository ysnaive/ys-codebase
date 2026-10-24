# Knowledge-DB 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `knowledge-db` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令、Hooks 與 URI 擴充）
- **語意 URI**：`knowledge.storage://`（知識庫索引與快取空間）。
- **CLI 指令樹**：
  - `knowledge-db search`: 全庫與跨空間語意檢索（支援 `-s` 切片與 `-d` 詳細模式）。
  - `knowledge-db index`: 知識庫增量或全量索引建構與語意包導出。
  - `knowledge-db callers`: 調用關係追蹤（誰調用了該符號）。
  - `knowledge-db callees`: 被調用依賴追蹤。
  - `knowledge-db impact`: 重構影響半徑分析。
  - `knowledge-db status`: 索引資料庫與已註冊空間狀態診斷。
  - `knowledge-db model`: 向量模型生命週期管理。
  - `knowledge-db clean`: 快取清理與索引重建。
- **生命週期 Hooks**：
  - `dev: on_test_setup`, `on_test_teardown`
  - `server: on_server_worker_warming`

### 1.2 `server.json`（常駐微服務）
- 註冊 `knowledge-db-watcher` 背景 Worker 監聽檔案變更。

### 1.3 `agents-workflow.json`（技能注入）
- 導出 `knowledge-db-search` 領域技能包，並向 `AGENTS_SKILL_ROUTING`、`HOW_TO_CONFIG_MODULES`、`HOW_TO_YSCB_MODULES` 及階段指南錨點注入檢索規範。

### 1.4 `knowledge-db.json`（語言註冊）
- 註冊 10 大程式語言、AST Parser 與副檔名對映。

## 2. 開放擴充點清冊 (Ingress Points)
- `spaces`: 允許各模組註冊自訂語意檢索空間。
- `languages`: 允許註冊支援的程式語言與 AST 解析器。
