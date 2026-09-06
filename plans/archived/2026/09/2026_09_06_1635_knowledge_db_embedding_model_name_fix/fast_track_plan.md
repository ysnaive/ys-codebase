# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge-db 向量模型名稱錯誤修復與別名自動補全正規化  
> 建立日期：2026-09-06  
> 所屬主計畫：無  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **問題診斷**：
  專案組態 `config.project.json` 中配置 `"embedding_model": "bge-small-zh-v1.5"`，遺漏 `BAAI/` 前綴。
  導致每次 CLI 調用時，FastEmbed 白名單比對失敗並輸出警示訊息：
  `Requested model 'bge-small-zh-v1.5' is not in FastEmbed supported list. Falling back to default 'BAAI/bge-small-zh-v1.5'.`
- **修復邊界**：
  1. 修正 `config/knowledge-db/config.project.json` 與 `source/knowledge-db/configurable/config.project.json` 為標準模型名稱 `"BAAI/bge-small-zh-v1.5"`。
  2. 於 `EmbeddingService._init_model()` 與 `KnowledgeDBConfig.load()` 增設自動補全正規化（若使用者配置遺漏 `BAAI/` 或 `sentence-transformers/` 前綴，自動比對並補全，避免噪音警示）。
  3. 新增單元測試覆蓋別名補全邏輯，確保 100% 測試通過。

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：修正 `config/knowledge-db/config.project.json` 與 `source/knowledge-db/configurable/config.project.json` 之 `"embedding_model"` 為 `"BAAI/bge-small-zh-v1.5"`。
- [x] **TASK-02**：於 `knowledge_db/embedding.py` 與 `knowledge_db/config.py` 增設模型名稱正規化防禦，自動解析補齊 vendor 前綴（如 `BAAI/`）。
- [x] **TASK-03**：增設單元測試驗證別名正規化與警示消除。
- [x] **TASK-04**：全量跑測 `python yscb.py dev test knowledge-db`，驗證 CLI 無警示輸出。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `config/knowledge-db/config.project.json` 與 `source/knowledge-db/configurable/config.project.json` 已修正為標準名稱 `"BAAI/bge-small-zh-v1.5"`。
  2. `EmbeddingService` 與 `KnowledgeDBConfig.load()` 實作 `normalize_model_name`，自動補齊 `BAAI/` 或 `sentence-transformers/` 前綴。
  3. `tests/test_cli_ux.py` 增設別名補全測試。
  4. 實機執行 `daemon status` 與 `search`，白名單比對完全通過，無任何降級警示輸出。

- **實機測試日誌**：
  - `python yscb.py dev test knowledge-db`：
    `Summary : 160 Total, 160 Passed, 0 Failed, 0 Skipped (19.447s)`
    `Status  : PASSED (100% Ready)`
  - `python yscb.py install knowledge-db@build` 安裝成功。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：測試 100% 通過。
- [x] **日誌與發布交付**：追加 `changelog.md`。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證合規。
- **結案狀態**：`Completed`
