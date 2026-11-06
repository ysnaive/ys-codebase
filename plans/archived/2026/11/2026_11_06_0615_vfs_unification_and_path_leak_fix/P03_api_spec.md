# API 與介面規格書 (API & Interface Specification)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `WarmWorker.__init__` | `ys_codebase/source/server/server/worker.py` | Public | 初始化常駐 Worker 子進程，並於啟動任何背景服務前將 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` 錨定至 `os.environ`。 |
| `FileSpaceManager.storage_root` | `ys_codebase/source/file-space/file_space/manager.py` | Public | 解析 `file-space.storage://` 或退避至 `<yscb_root>/.storage.local/file-space`。 |
| `FileSpaceWatcherServiceWorker._resolve_watcher_state_path` | `ys_codebase/source/file-space/file_space/service.py` | Internal | 解析 Watcher 狀態檔路徑（優先顯式 `state_file` / 顯式沙盒 `storage_root` -> `file-space.cache://watcher_state.json` -> `<yscb_root>/.cache/file-space/watcher_state.json`）。 |
| `_read_watcher_state_file` / `_is_daemon_pid_alive` | `ys_codebase/source/file-space/file_space/scanner.py` | Internal | 透過 `core.vfs.read_json` 讀取 `file-space.cache://watcher_state.json` 與 `cache://server/daemon.json`。 |
| `_resolve_default_ast_storage_dir` / `ASTEngine._resolve_index_lock_path` | `ys_codebase/source/ast/ast_engine/bundler.py`, `engine.py` | Internal | 解析 `ast.storage://` 與 `ast.cache://.ast_index.lock`，退避錨定 `<yscb_root>`。 |
| `_resolve_default_knowledge_storage_dir` / `write_worker_state` | `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`, `service.py` | Public / Internal | 解析 `knowledge.storage://`（退避錨定 `<yscb_root>`），並以 `core.vfs.write_json` 原子寫入 `.kdb_worker_state.json`。 |
| `_write_cache_file` / `_write_text_atomic` / `_atomic_write_text` | `ys_codebase/source/agents-workflow/agents_workflow/{compiler,publisher,roadmap}.py` | Internal | 統一透過 `core.vfs.write_text(..., atomic=True)` 執行跨平台 LF 原子寫入。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. file_space/scanner.py
def _read_watcher_state_file(
    project_root: Optional[Path] = None,
    space_manager: Optional[FileSpaceManager] = None,
) -> Optional[Dict[str, Any]]:
    """
    Read watcher_state.json from explicit sandbox storage_root (if configured on space_manager)
    or via core.vfs ('file-space.cache://watcher_state.json'). Never probes project_root/.cache.
    """

# 2. ast_engine/bundler.py & engine.py
def _resolve_default_ast_storage_dir(project_root: Optional[Path] = None) -> Path:
    """Resolve 'ast.storage://' -> 'storage.local://ast/' -> '<yscb_root>/.storage.local/ast'."""

# 3. knowledge_db/pipeline.py
def _resolve_default_knowledge_storage_dir(project_root: Optional[Path] = None) -> Path:
    """Resolve 'knowledge.storage://' -> 'storage.local://knowledge-db/' -> '<yscb_root>/.storage.local/knowledge-db'."""
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 所有公開函式與方法之參數簽名與回傳型別維持 100% 向後相容。
  - 當底層磁碟發生 `PermissionError` 時，`core.vfs` 內部之 `robust_replace` 自動執行漸進重試，並在重試耗盡時清理 `.tmp` 暫存檔並向上拋出原始 `PermissionError`。
- **階段決策紀錄**：`[P03:DR-01]` `_read_watcher_state_file` 新增可選參數 `space_manager: Optional[FileSpaceManager] = None`，使 `is_watcher_active(project_root, space_name, space_manager=...)` 能直接讀取顯式沙盒 `storage_root` 下的 `watcher_state.json`，同時保持單參數呼叫 `_read_watcher_state_file(project_root)` 相容。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: module:server (worker.py 環境變數錨定)
  │
  ├──> Step 2: module:file-space (manager.py, service.py, scanner.py + tests)
  │
  ├──> Step 3: module:ast (bundler.py, engine.py + tests)
  │
  ├──> Step 4: module:knowledge-db (pipeline.py, config.py, service.py + tests)
  │
  └──> Step 5: module:agents-workflow (compiler.py, publisher.py, roadmap.py, verifier.py, _verifier_healer.py, session_trace.py + tests)
```
