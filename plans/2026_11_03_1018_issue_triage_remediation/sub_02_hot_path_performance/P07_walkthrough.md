# 成果展示與結案報告 (Walkthrough)

> 功能名稱：熱路徑效能與增量管線深度優化  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core.contributes` 記憶體快取與 `invalidate_cache()` (`FR-01`, `EC-01`)**：於 `core/contributes.py` 新增程序內記憶體快取 `_MERGED_MEMORY_CACHE`（同時檢核 `contributes.meta.json` 與 `contributes.merged.json` 雙實體檔案 mtime）與 `40ms` 單調時鐘免重掃視窗 `_LAST_CLEAN_SCAN_TS`，並於 `scan_and_inject()` 完成時呼叫 `invalidate_cache()`，消除單次 CLI 內高頻 `locale.t()` 呼叫之重複磁碟掃描與 JSON 反序列化。
  2. **`FileSpaceManager` 路徑解析與 `load_spaces` 守衛 (`FR-02`, `EC-02`)**：於 `file_space/manager.py` 快取 `project_root`、為 `load_spaces(force: bool = False)` 加入已載入守衛、將 `ast` 與 `knowledge-db` 內部唯讀呼叫改為 `get_all_spaces()`，並於 `_walk_root` 非符號連結且 `follow_symlinks=False` 時直接使用 `DirEntry.path` 免除逐檔冗餘 `resolve()`。
  3. **`ast` 單檔增量 $O(|\text{dirty}|)$ 熱修補與全量單次讀檔快取 (`FR-03`, `FR-05`, `FR-06`, `EC-03`, `NFR-01`)**：於 `ast_engine/bundler.py` 新增 `_preload_snap_entries` 與 `_resolve_dirty_files_only`，使 `bundle_dirty_files` 與 `extract_dirty_call_sites_and_imports` 以 $O(|\text{dirty}|)$ 定位異動檔案；於 `_parse_file_task_worker` 與 `_parse_file_full` 單次讀檔同時提取 `(symbols, call_sites, imports)` 並緩存於 `_file_call_sites_cache` 與 `_file_imports_cache`；於 `ast_engine/engine.py` 新增 `hot_patch_index(_cursor_already_consumed=False)` 消除巢狀 `_consume_space_diff`、以 `file_to_symbol_ids` 加速舊符號淘汰並增量更新 `files_map`，達成單檔熱修補 `0` 次全倉走訪。
  4. **`knowledge-db` Stage 2 微批次鎖分離、檢查點持久化與 `removed_terms` 精準修剪 (`FR-04`, `FR-05`, `EC-04`, `EC-05`)**：於 `knowledge_db/retrieval.py` `InvertedIndex.patch_incremental` 收集 `removed_terms` 僅修剪受影響詞條 Postings；於 `knowledge_db/pipeline.py` 與 `service.py` 將 `sync_vector_deficit_step(batch_size=32, persist=True)` 之 `embed_texts()` 移出 `_index_lock` 外執行、重新加鎖後過濾存活符號，並由 Worker 每 8 批或 $\ge 2.0\text{s}$ 及退出 `finally` 時呼叫 `flush_vector_index()` 原子落盤。
  5. **`dev` 沙盒模組 `.build.zip` 直接解壓與壞包回退 (`FR-07`, `EC-06`)**：於 `dev/testing/sandbox.py` 優先將有效 `.build.zip` 解壓至沙盒 `.modules/<mod>`（跳過前置 `shutil.copytree` 與 `rmtree`），損壞時自動清理並回退至 `shutil.copytree`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/contributes.py` | Modify | 新增 `_MERGED_MEMORY_CACHE`、`_LAST_CLEAN_SCAN_TS`、`invalidate_cache()` 與 `get()` 快取快速路徑 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 快取 `_cached_project_root`、`load_spaces(force=False)` 守衛、`_walk_root` 免冗餘 `resolve()` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 新增 `_preload_snap_entries`、`_resolve_dirty_files_only`、單次讀檔提取與快取、`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | `hot_patch_index(_cursor_already_consumed=False)`、增量更新 `files_map`、`file_to_symbol_ids` 淘汰加速 |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 唯讀 `load_spaces()` 改為 `get_all_spaces()` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `InvertedIndex.patch_incremental` 僅修剪 `removed_terms` Postings |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `sync_vector_deficit_step(batch_size=32, persist=True)` 鎖分離與 `flush_vector_index()` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | Stage 2 每 8 批或 2.0s 存盤一次，退出 `finally` 呼叫 `flush_vector_index()` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 唯讀 `load_spaces()` 改為 `get_all_spaces()` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 優先解壓 `.build.zip` 消除雙倍拷貝並支援損壞回退 |
| `ys_codebase/source/core/tests/test_contributes.py` | Modify | 新增記憶體快取命中、`invalidate_cache()` 與 `scan_and_inject` 刷新測試 |
| `ys_codebase/source/file-space/tests/test_file_space_manager.py` | Modify | 新增 `project_root` 快取、`load_spaces(force)` 與 `follow_symlinks=True` 測試 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 新增單檔熱修補 0 全倉走訪、單次讀檔快取與 C# partial 重聚合測試 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 `removed_terms` 修剪、鎖外推論與存活過濾、Worker 批次存盤節流測試 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 新增 `.build.zip` 跳過 `copytree` 與損壞 zip 回退測試 |
| `docs/core/contributes_architecture.md` | Modify | 同步更新 `_MERGED_MEMORY_CACHE` 與 `invalidate_cache()` 說明 |
| `docs/file-space/README.md` | Modify | 同步更新 `project_root` 快取、`load_spaces(force=False)` 與 `_walk_root` 路徑優化說明 |
| `docs/ast/README.md` | Modify | 同步更新單次讀檔建置與 `_resolve_dirty_files_only` $O(|\text{dirty}|)$ 熱修補說明 |
| `docs/knowledge-db/incremental_hot_reload.md` | Modify | 同步更新 `removed_terms` 修剪、Stage 2 鎖分離與檢查點持久化說明 |
| `CHANGELOG.md` | Modify | 新增 `sub_02_hot_path_performance` 結案條目 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` (239/239 passed)、`file-space` (16/16 passed)、`ast` (21/21 passed)、`knowledge-db` (106/106 passed)、`dev` (84/84 passed)，5 模組共 **466/466 (100%)** 通過；`dev check` 5 模組全數 `PASS`。
- **實機 UX / 人工驗證**：於臨時兄弟目錄 `/workspace/ys-codebase-uat-sub02` 完成 `UX-01` 與 `UX-02` 端到端實測（`[測試通過]`）並清理環境。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 增補 `sub_02_hot_path_performance` 發布亮點與變更摘要 |
| **中觀 (Meso)** | `docs/file-space/README.md`, `docs/ast/README.md` | 已完成 | 更新 `FileSpaceManager` 快取與 `ast` 單次讀檔及 $O(|\text{dirty}|)$ 熱修補 |
| **中觀 (Meso)** | `docs/core/contributes_architecture.md`, `docs/knowledge-db/incremental_hot_reload.md` | 已完成 | 更新 `contributes` 記憶體快取、`invalidate_cache()` 與 Stage 2 鎖分離檢查點持久化 |
| **中觀 (Meso)** | `docs/knowledge-db/DESIGN_NOTES.md` | 免更 | 既有 `[DN-10]` 與 `[DN-30]` 已涵蓋架構不變量，專題手冊已完整同步 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 同步維護 `invalidate_cache`、`load_spaces`、`_resolve_dirty_files_only`、`hot_patch_index`、`sync_vector_deficit_step`、`flush_vector_index` Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
perf(core,file-space,ast,knowledge-db,dev): optimize hot-path caching, O(|dirty|) AST hot-patching and lock-free vector sync

- cache merged contributes in memory with dual mtime guard, 40ms clean-scan window and invalidate_cache()
- cache FileSpaceManager.project_root, guard load_spaces(force=False) and skip redundant resolve() on non-symlinks
- resolve dirty files in O(|dirty|) in SemanticBundler, cache single-read call sites/imports in bundle_union, and eliminate nested consume_diff in ASTEngine.hot_patch_index
- prune only removed_terms in InvertedIndex.patch_incremental, release _index_lock during embed_texts() and checkpoint vector persistence in KnowledgeDBServiceWorker
- extract valid .build.zip directly in SandboxProvisioner to eliminate double copytree/rmtree I/O with corrupt-zip fallback
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

