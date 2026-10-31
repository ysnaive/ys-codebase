# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_04_knowledge_db_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書中有對應介面（涵蓋 `M-01~M-10` 清除與 `F-01~F-09` 重構）
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略（複合字 50% 門檻、`.tmp` 原子清理、消歧回退與損毀重建）
- [x] **依賴純淨**：符合 NFR-01 與 NFR-02 指標約束，零跨模組修改

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/Technical_Modules/knowledge-db/README.md` | Modify | 於 Phase 7 同步更新 `TopologyQueryService` 與移除舊別名後之模組結構說明 |
| **專題手冊** | `docs/Technical_Modules/knowledge-db/ARCHITECTURE.md` | Modify | 於 Phase 7 對齊單一 `nx.DiGraph` 與 `BM25Engine` 共用打分流程 |
| **設計決策** | `docs/Technical_Modules/knowledge-db/DESIGN_NOTES.md` | Modify | 於 Phase 7 登記 `Mode A` 移除雙軌序列化與舊別名之設計紀錄 |
| **微觀註解** | `ys_codebase/source/knowledge-db/knowledge_db/*.py` | Modify | 同步更新新增與重構模組/函式之 Docstrings |
| **發布日誌** | CHANGELOG.md | Modify | 於主計畫 Phase 7 結案時統一記錄版本摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：將 `UnifiedSymbol` 的 `"members"` 與 `"space"` 雙重序列化鍵移除後，若磁碟上仍有舊結構快取是否會導致讀取異常？  
> [*] **防護解法**：`UnifiedSymbol.from_dict` 與持久化索引載入器均受索引 schema 版本號（`"2.1"`）與欄位預設值保護；且 `Mode A` 明確移除舊版相容負擔，統一以 `"children"` 與 `"spaces"` 為唯一正統格式 (`[P04:DR-01]`)。

> [?] **尖銳問題 2**：移除 `KnowledgeEngine` 的 16 個內部組件代理與 `HotPatchResult(int)` 後，既有單元測試與 CLI 是否會大面積斷裂？  
> [*] **防護解法**：生產環境 `scripts/cli.py` 與 `scripts/hook.server.py` 僅呼叫高階方法（並已於 TASK-05 同步移除廢棄參數）；`tests/` 中直接存取 `engine.scanner`、`engine.act_callers` 或將 `HotPatchResult` 當作 `int` 比較之斷言，將於 TASK-06 全面對齊至正統 API (`[P04:DR-02]`)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：建立 `knowledge_db/io_utils.py` 並重構 `config.py`、`schema.py`、`tokenizer.py`、`space.py`（完成 `M-01`, `M-03`, `M-05`, `M-07` 與 `F-07`, `F-08` 基礎層）。
2. **TASK-02**：重構 `scanner.py`（抽取 `_iter_eligible_files` 並移除 `M-04` 舊方法）與 `parsers/registry.py`、`parsers/__init__.py`、`parsers/treesitter.py`、`parsers/spice.py`（完成 `M-02`, `M-10` 部分與 `F-05`, `F-09`）。
3. **TASK-03**：重構 `retrieval.py`（抽取 `_score_candidate_documents` 修復 `F-02`、清除 `M-06`）、`graph.py`（純化 `nx.DiGraph` 修復 `F-06`、拆解 `resolve_call_site` 修復 `F-09`、清除 `M-10`）、`embedding.py`（原子寫入修復 `F-04`、清除 `M-10`）與 `bundler.py`（套用 `io_utils`、清除 `M-10`）。
4. **TASK-04**：新建 `knowledge_db/topology_query.py` (`TopologyQueryService`)，並重構 `pipeline.py`（拆解熱修補與檢索階段、純化 `HotPatchResult` 清除 `M-09`）與 `engine.py`（清除 16 個薄代理與 `act_*` 修復 `M-08`）。
5. **TASK-05**：重構 `formatter.py`（抽取 `_format_topology_tree` 修復 `F-03`、公開 `get_workspace_root`）、`scripts/cli.py`（抽取 `_run_topology_cli_command` 與 `search` 共用 `_parse_common_display_options` 修復 `F-03`）與 `scripts/hook.server.py`（清除 `M-10`）。
6. **TASK-06**：同步更新 `ys_codebase/source/knowledge-db/tests/` 測試案例對齊 `Mode A` 正統 API，並執行 `python -m py_compile` 驗證全模組與測試檔案零語法錯誤。
7. **TASK-07**：完成 `R02` 審查收斂：修復 `config.py`/`embedding.py` 之 `resolve_threads` 唯一真理與 `_resolve_config_uri` 匯入 `resolve`、透傳 `pipeline.py` 之 `context_lines`、移除 `hybrid.py` 死分支與 `linker.py`/`registry.py`/`pipeline.py` 單行殘留轉發。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 序列化與圖譜單一真理來源**：`UnifiedSymbol` 序列化僅保留 `"children"` 與 `"spaces"`；`CallGraphIndex` 100% 依賴 `nx.DiGraph`；所有 Gzip+Pickle 持久化統一經由 `io_utils.py` 原子讀寫。
- **[P04:DR-02] 並行子代理驗證策略**：依主計畫並行隔離規則，本子代理完成源碼與測試重構後以 `py_compile` 進行靜態語法檢核與 `plan verify` 結構驗證，不啟動 `dev test` / `dev build` 沙盒程序。
