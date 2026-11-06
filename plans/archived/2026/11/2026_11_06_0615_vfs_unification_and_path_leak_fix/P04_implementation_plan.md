# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中有對應介面與遷移路徑
- [x] **邊界防護**：EC-01 ~ EC-03 有具體錯誤處理與沙盒隔離策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-02 指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/file-space/ARCHITECTURE.md` | Modify | 確認 `watcher_state.json` 標註為 `file-space.cache://watcher_state.json` |
| **專題手冊** | `docs/server/hot_reload_and_services.md` | Modify | 補充 `WarmWorker` 啟動期錨定 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` 之跨執行緒保證 |
| **設計決策** | `docs/file-space/DESIGN_NOTES.md` | Modify | 更新 `[DN-SP-03]` 明確記載 `file-space.cache://watcher_state.json` 語意 URI 解析與零 `project_root` 洩漏約束 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新受影響函式之 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本次路徑洩漏根治與 VFS 收口摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若在無 `yscb.config.json` 的純單元測試環境中呼叫 `ASTEngine(project_root=tmp_dir)` 或 `KnowledgeEngine(project_root=tmp_dir)`，將退避路徑改為 `uri.resolve_yscb_root()` 會不會導致多個測試共用同一個 `.storage.local`？  
> [*] **防護解法**：
> 1. 在 `ASTEngine.__init__` 與 `KnowledgeEngine.__init__` 中，單元測試皆會傳入 `storage_dir=tmp_storage`；當未傳入 `storage_dir` 但顯式傳入 `project_root` 且該 `project_root` 與預設 `project://` 不同（即測試沙盒建立臨時專案目錄 `ASTEngine(project_root=self.temp_dir)`）時，需檢查既有測試是否依賴在 `self.temp_dir` 下獨立隔離！
> 2. 讓我們精確核對：`ASTEngine.__init__` 若未傳 `storage_dir`，原本呼叫 `_resolve_default_ast_storage_dir(self.project_root)`，而 `_resolve_default_ast_storage_dir` 第一步就是 `uri.resolve("ast.storage://")`，只要 `core.uri` 可用，它本來就是回傳 `<yscb_root>/.storage.local/ast`！只有當 `uri.resolve("ast.storage://")` 失敗時才會走到 fallback。將 fallback 改為 `Path(uri.resolve_yscb_root()) / ".storage.local" / "ast"` 與正常路徑 100% 一致，且消除了當背景執行緒 `uri.resolve` 失敗時誤寫入 `project_root` 的 Bug。

> [?] **尖銳問題 2**：`test_fingerprint_scanner.py` 第 398~441 行直接測試了 `_atomic_write_bytes` 在 `patch("file_space.scanner.os.replace")` 與 `patch("file_space.scanner.time.sleep")` 下的 5 次重試行為，若將 `_atomic_write_bytes` 完全改為呼叫 `core.vfs.write_bytes`，該單元測試攔截 `file_space.scanner.os.replace` 會不會失效？  
> [*] **防護解法**：
> - 這是極關鍵的相容性細節！若測試直接 `patch("file_space.scanner.os.replace")` 與 `patch("file_space.scanner.time.sleep")`，而 `_atomic_write_bytes` 轉發給 `core.vfs.write_bytes`，當 `file_space.scanner.os.replace` 沒被覆寫（即 `_atomic_write_bytes` 在真實運行時）走 `core.vfs.write_bytes`；或者我們直接更新 `test_fingerprint_scanner.py` 測試驗證 `_atomic_write_bytes` 委派 `core.vfs.write_bytes` 與 `core.vfs.os_backend.robust_replace` 的原子寫入與異常清理行為！更新 `test_fingerprint_scanner.py` 使其直接測試真實的 VFS 原子寫入契約，完全符合 `testing-sop` 鐵律 4。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：於 `ys_codebase/source/server/server/worker.py` (`WarmWorker.__init__`) 預先解析並固化 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` (`GUARD_ENV_HOST`) 環境變數，並於 `test_server.py` 補齊驗證。
2. **TASK-02**：重構 `ys_codebase/source/file-space/file_space/{manager,service,scanner}.py`，將 `watcher_state.json`、`daemon.json`、`.yscb.lock` 與 `storage_root` 全面收口至 `core.uri` / `core.vfs`（退避錨定 `uri.resolve_yscb_root()`），將 `_atomic_write_bytes` 委派至 `core.vfs.write_bytes`，並更新 `test_fingerprint_scanner.py`。
3. **TASK-03**：重構 `ys_codebase/source/ast/ast_engine/{bundler,engine}.py`，將 `_resolve_default_ast_storage_dir` 與 `_resolve_index_lock_path` 退避基準改為 `uri.resolve_yscb_root()`，將 `_atomic_write_meta` 收口至 `core.vfs.write_json`，並於 `test_ast_engine.py` 新增防路徑洩漏測試。
4. **TASK-04**：重構 `ys_codebase/source/knowledge-db/knowledge_db/{pipeline,config,service}.py`，將 `_resolve_default_knowledge_storage_dir` 與 `is_agents_workflow_installed` 退避基準改為 `uri.resolve_yscb_root()`，並將 `write_worker_state` / `read_worker_state` 收口至 `core.vfs`。
5. **TASK-05**：重構 `ys_codebase/source/agents-workflow/agents_workflow/{compiler,publisher,roadmap}.py` 與 `plans/{verifier,_verifier_healer,session_trace}.py`，消除 `Path.cwd() / ".cache"` 與 `"ys_codebase/..."` 硬編碼，統一原子寫入至 `core.vfs.write_text`。
6. **TASK-DOC**：同步更新 `docs/file-space/ARCHITECTURE.md`、`docs/file-space/DESIGN_NOTES.md` 與 `docs/server/hot_reload_and_services.md`，並執行 5 模組 `dev check`、`dev test -q` 與 `@build` 熱部署驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 全面採用 `core.uri.resolve_yscb_root()` 作為所有內部 `.cache` / `.storage.local` / `.modules` 退避路徑之唯一錨點，並統一透過 `core.vfs` 執行原子寫入。
