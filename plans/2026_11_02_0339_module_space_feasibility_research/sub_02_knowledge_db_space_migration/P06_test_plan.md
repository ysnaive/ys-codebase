# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`knowledge-db` 空間與指紋底座遷移重構（`/code-optimizer` `Mode A` 單一正統入口收斂）  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_02_knowledge_db_space_migration  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Mode A` 刪除 `knowledge_db/{space,scanner,service}.py` 後，全模組與測試統一透過 `from space import ...` 運作正常，無殘留死匯出 | FR-01 | `python yscb.py dev test knowledge-db -q` (`test_space.py`, `test_schema.py`) |
| **FT-02** | 單元測試 | 驗證 `KnowledgeEngine.storage_dir` 獨立解析至 `knowledge.storage://` (`cache://knowledge-db/`)，與 `space_manager.storage_dir` (`cache://space/`) 徹底解耦，且 `space_weights` 正確載入 | FR-02 | `python yscb.py dev test knowledge-db -q` (`test_engine.py`, `test_schema.py`) |
| **FT-03** | 整合測試 | 驗證 `SearchPipeline` 透過 `space.consume_diff(consumer_id="knowledge-db")` 執行 JIT 增量熱修補，以及 `scripts/hook.space.py` 訂閱 `on_space_changed` 事件驅動熱更新 | FR-03 | `python yscb.py dev test knowledge-db -q` (`test_hot_reload.py`, `test_service_worker.py`) |
| **FT-04** | 單元測試 | 驗證 `io_utils` 髒路徑匹配純函式、`bundler` 呼叫點提取迴圈折疊與 `core.vfs` 原子寫入，以及 `search`/`callers`/`callees`/`impact` 全功能等價 | FR-04 | `python yscb.py dev test knowledge-db -q` (`test_bundler.py`, `test_graph.py`, `test_retrieval.py`) |
| **ET-01** | 邊界測試 | 驗證索引檔 (`unified.bm25.json`) 被清除時自動呼叫 `reset_cursor(consumer_id="knowledge-db")` 並觸發全量重建與游標對齊 | EC-01 | `python yscb.py dev test knowledge-db -q` (`test_engine.py`, `test_hot_reload.py`) |
| **ET-02** | 邊界測試 | 驗證未宣告於 `space_weights` 之空間回退預設權重 `1.0`，而配置 `<= 0` 權重時於 `schema.py` 拋出 `InvalidConfigError` | EC-02 | `python yscb.py dev test knowledge-db -q` (`test_schema.py`) |
| **ET-03** | 邊界測試 | 驗證測試環境直傳 `KnowledgeEngine(project_root=..., custom_spaces=...)` 時自動提取內嵌 `weight` 並正常完成索引與檢索 | EC-03 | `python yscb.py dev test knowledge-db -q` (`test_engine.py`, `test_cli.py`) |
| **RT-01** | 回歸與合規 | 驗證 `dev check knowledge-db`、`dev check agents-workflow` 與 `dev test knowledge-db --type=all` 159 項測試 100% 通過（生產與測試代碼淨減 `-973` 行） | NFR-01 | `python yscb.py dev check knowledge-db` & `python yscb.py dev test knowledge-db -q --type=all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_space.py` 與 `test_schema.py` 100% 通過，確認 `Mode A` 單一正統入口收斂完成 | 2026-11-02 |
| **FT-02** | `Passed` | `storage_dir` 確認獨立指向 `cache://knowledge-db`，`space_weights` 加權計算正確 | 2026-11-02 |
| **FT-03** | `Passed` | `test_hot_reload.py` 與 `test_service_worker.py` (`hook.space.py` + `consume_diff`) 全數通過 | 2026-11-02 |
| **FT-04** | `Passed` | `test_bundler.py`, `test_graph.py`, `test_retrieval.py` 全數通過 | 2026-11-02 |
| **ET-01** | `Passed` | 索引清除後游標自動重置並完成全量重建 | 2026-11-02 |
| **ET-02** | `Passed` | `space_weights <= 0` 非法權重攔截與預設值 `1.0` 回退斷言通過 | 2026-11-02 |
| **ET-03** | `Passed` | `custom_spaces` 沙盒注入測試全數通過 | 2026-11-02 |
| **RT-01** | `Passed` | `dev check knowledge-db` (0 Errors, 0 Warnings) 與 `dev test knowledge-db --type=all` (159/159, 100.0% Passed) | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db status --json` 與 `python yscb.py knowledge-db search "SpaceManager" --json --limit=3`，確認知識庫透過 `module:space` 游標增量同步並回傳精準 AST 切片 | `[測試通過]` | 開發者實機驗證常駐 `server` (`space-watcher -> on_space_changed -> hook.space.py`) 於臨時增檔、改檔、刪檔時自動完成增量熱自癒與游標同步 (`in_sync: true`) |

