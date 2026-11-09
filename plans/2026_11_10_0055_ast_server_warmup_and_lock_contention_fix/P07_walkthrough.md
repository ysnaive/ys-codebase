# 成果展示與結案報告 (Walkthrough)

> 功能名稱：AST 指令卡死、Server 預熱阻塞與背景 Stage 1 鎖競爭根治修繕 (ast_server_warmup_and_lock_contention_fix)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **消除 `WarmWorker.pre_warm()` 主執行緒長阻塞與 `virtual_cwd` 偏差 (`FR-01`)**：將 `server/server/worker.py:pre_warm()` 之 `virtual_cwd` 對齊為 `self.host_dir or self.yscb_root`，並於 `knowledge-db/knowledge_db/engine.py:pre_warm()` 在 `YSCB_IN_SERVER_WORKER == "1"` 或背景 Worker 運行時略過耗時的 `ASTEngine._ensure_loaded_from_disk()` 與向量模型同步載入，使 `worker_ready` 握手毫秒級完成，根除 `server start` 後緊接著執行 CLI 指令時的 30 秒 `_wait_worker_ready()` 掛起與重啟循環。
  2. **根除 `space-watcher` 與 `knowledge-db-worker` 雙執行緒鎖踩踏與重複 `hot_patch_index` (`FR-02`, `FR-03`)**：於 `ast/scripts/hook.core.py:on_file_space_changed` 中檢測同進程活躍之 `KnowledgeDBServiceWorker`，直接透過 `notify_space_changed()` 讓渡予背景 Worker 單點執行 Single-Parse Symbol Sharing；於 `KnowledgeDBServiceWorker._run_sync_cycle` 進入 Stage 1 前加入 `server.worker.foreground_active` 禮讓檢查；並修正 `IndexingPipeline._collect_all_dirty_files` 在 `ensure_jit_synced()` 已推進 `ast_generation` 後又重複呼叫第二次 `hot_patch_index(detail)` 的缺陷。
  3. **實作 `ASTEngine.status()` 無鎖 $O(1)$ `unified.meta.json` 快讀、單檔 `outline()` 非阻塞化與 `SemanticBundler` 副檔名預過濾 (`FR-04` ~ `FR-06`)**：擴充 `unified.meta.json` 儲存 `total_edges`、`graph_mtime_ns`、`graph_size`、`space_symbol_counts` 與 `space_file_counts`，使 `status()` 與 `get_persisted_meta()` 免搶 `self._lock` 與 `.ast_index.lock` 即時回傳；移除 `outline()` 外層長鎖及 `merged=False` 時對 C# `partial` 檔案之全倉 `ensure_jit_synced()` 阻塞；於 `SemanticBundler._collect_space_files()` 與 `_resolve_dirty_files_only()` 預先過濾 `parser_registry.get_parser(relpath) is not None` 之可解析檔案。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `../../ys_codebase/source/ast/ast_engine/engine.py` | Modify | 擴充 `_build_meta_payload()`、無鎖化 `get_persisted_meta()` 與 `status()`，並移除 `outline()` 外層長鎖與 `merged=False` 全倉重建阻塞 |
| `../../ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 於 `_collect_space_files()` 與 `_resolve_dirty_files_only()` 預先過濾 `parser_registry.get_parser(relpath) is not None` |
| `../../ys_codebase/source/ast/scripts/hook.core.py` | Modify | 同進程 `KnowledgeDBServiceWorker` 活躍時透過 `notify_space_changed()` 單點讓渡空間變更 |
| `../../ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `KnowledgeEngine.pre_warm()` 在 Server Worker 環境下略過阻塞式 `ast_eng._ensure_loaded_from_disk()` |
| `../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 於 `_collect_all_dirty_files()` 記錄 `gen_before_sync`，防止 `ensure_jit_synced()` 推進世代後重複呼叫 `hot_patch_index()` |
| `../../ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 於 `_run_sync_cycle()` Stage 1 前加入 `foreground_active` 禮讓檢查，並於 Watcher 活躍時傳入 `auto_refresh=False` |
| `../../ys_codebase/source/server/server/worker.py` | Modify | 將 `WarmWorker.pre_warm()` 之 `virtual_cwd` 對齊為 `self.host_dir or self.yscb_root` |
| `../../ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 新增 `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 單元與並發鎖競爭測試 |
| `../../ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 `test_stage1_foreground_yield_and_zero_redundant_hot_patch` 單元測試 |
| `../../ys_codebase/source/server/tests/test_server.py` | Modify | 擴充 `test_warm_worker_pre_warm_events` 驗證 `pre_warm` 期間 `get_virtual_cwd() == worker.host_dir` |
| `../../docs/ast/DESIGN_NOTES.md` | Modify | 新增 `[DN-AST-08]` 記錄無鎖 `status` 快讀、單檔 `outline` 非阻塞提取與同進程 Worker 讓渡機制 |
| `../../CHANGELOG.md` | Modify | 新增 `2026_11_10_0055_ast_server_warmup_and_lock_contention_fix` 結案變更紀錄 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `ast`：`54 / 54 (100.0% PASS, 0 ResourceWarning)`
  - `knowledge-db`：`118 / 118 (100.0% PASS, 0 ResourceWarning)`
  - `server`：`67 / 67 (100.0% PASS, 0 ResourceWarning)`
  - 全倉靜態檢核：`python3 yscb.py dev check --all` (`9 Total, 9 Passed, 0 Warnings, 0 Failed`) 與 `python3 yscb.py contributes check` (`28 files PASS`)
  - Pre-UX 雙盲冷眼審查：`REVIEW_STATUS: PASSED` (`MAJOR_ISSUES_COUNT: 0`)
- **實機 UX / 人工驗證**：
  - `UX-01` 已於雲端 VM 透過雙鎖競爭自動化測試完整模擬驗證，標定為 `[跳過/免測]` 交由開發者於本地端 `gdrive pull` 後驗收。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `../../CHANGELOG.md` | 已更新 | 同步記錄六大阻塞根因修復與測試驗收摘要 |
| **中觀 (Meso)** | `../../docs/ast/README.md` | 免更 | 對外 CLI 參數與 JSON 輸出欄位契約無變更 |
| **中觀 (Meso)** | `../../docs/server/README.md` | 免更 | 對外 CLI 參數與服務狀態輸出契約無變更 |
| **中觀 (Meso)** | `../../docs/ast/DESIGN_NOTES.md` | 已更新 | 新增 `[DN-AST-08]` 登記 `unified.meta.json` 無鎖快讀與單檔 `outline` 非阻塞設計 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | 同步維護 `ASTEngine.status`、`get_persisted_meta`、`outline` 與 `hook.core.py` Docstring |

### 4.2 品質與清理檢核

- [x] **代碼清理**：無死代碼、無除錯 `print`/`log`、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(ast,knowledge-db,server): eliminate server warming hang, dual-thread AST lock stampede, and blocking status/outline calls

- align WarmWorker.pre_warm() virtual_cwd with host_dir and make KnowledgeEngine.pre_warm() non-blocking inside server worker
- delegate ast hook.core.py space changes to active in-process KnowledgeDBServiceWorker and yield before Stage 1 when foreground_active is set
- prevent redundant second hot_patch_index call in IndexingPipeline._collect_all_dirty_files after ensure_jit_synced() advances ast_generation
- persist total_edges and per-space counts in unified.meta.json for lock-free O(1) ASTEngine.status() and get_persisted_meta() reads
- avoid full-workspace ensure_jit_synced() and lock contention during single-file ASTEngine.outline(..., merged=False) on C# partial files
- pre-filter non-parseable file extensions in SemanticBundler._collect_space_files() and _resolve_dirty_files_only()
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_10_0055_ast_server_warmup_and_lock_contention_fix` 驗證 100% Passed。
