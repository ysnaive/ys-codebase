# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：AST 指令卡死、Server 預熱阻塞與背景 Stage 1 鎖競爭根治修繕 (ast_server_warmup_and_lock_contention_fix)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `WarmWorker.pre_warm()` `virtual_cwd` 對齊與 `KnowledgeEngine.pre_warm()` 輕量化 | 1. 將 `server/server/worker.py:pre_warm()` 之 `virtual_cwd` 對齊為 `self.host_dir or self.yscb_root`，與 `execute_task()` 一致。<br>2. 於 `knowledge_db/engine.py:pre_warm()` 中，當處於 Server Worker 預熱 (`YSCB_IN_SERVER_WORKER == "1"` 或背景 `get_active_worker()` 已運行) 時，略過耗時之 `ast_eng._ensure_loaded_from_disk()` 與向量模型同步加載，僅保留輕量 `engine.pipeline._ensure_indices_loaded(load_vectors=...)`，使 `worker_ready` 握手毫秒級完成。 | P0 | `[P00:DR-01]` |
| **FR-02** | `ast/scripts/hook.core.py` 同進程 Worker 單點讓渡與前景禮讓 | 當 `on_file_space_changed` 未顯式傳入測試用 `engine` 實例，且同進程內 `KnowledgeDBServiceWorker` (`get_active_worker()`) 正在運行並涵蓋目標空間（或 `server.worker.foreground_active` 為 `True`）時，直接喚醒 `KnowledgeDBServiceWorker.notify_space_changed()` 並回傳 `status="noop"`，不在 `space-watcher` 執行緒上同步爭搶 `ASTEngine._lock`。 | P0 | `[P00:DR-02]` |
| **FR-03** | `IndexingPipeline._collect_all_dirty_files` 消除重複 `hot_patch_index` 與 Stage 1 前景禮讓 | 1. 於 `knowledge_db/pipeline.py:_collect_all_dirty_files` 呼叫 `ensure_jit_synced()` 前記錄 `gen_before`；若 `ensure_jit_synced()` 已推進 `ast_generation`（或 `detail` 變更已反映於 `snapshot`），不再重複呼叫第二次 `self.ast_engine.hot_patch_index(detail)`。<br>2. 於 `knowledge_db/service.py:_run_sync_cycle` 進入 Stage 1 前檢查 `server.worker.foreground_active` 禮讓前景任務，並於 `is_watcher_active()` 時為 `sync_incremental_changes` 傳入 `auto_refresh=False`。 | P0 | `[P00:DR-02]` |
| **FR-04** | `ASTEngine.status()` 無鎖 $O(1)$ `unified.meta.json` 快讀 | 擴充 `ASTEngine._build_meta_payload()` 儲存 `total_edges`、`graph_mtime_ns`、`graph_size`、`space_symbol_counts` 與 `space_file_counts`；重構 `ASTEngine.status()` 與 `get_persisted_meta()` 優先以無鎖方式讀取記憶體既有快照引用或 `unified.meta.json`，不阻塞於 `self._lock` 或 `.ast_index.lock`。 | P0 | `[P00:DR-03]` |
| **FR-05** | `ASTEngine.outline()` 單檔免鎖解析與 C# `partial` 非阻塞兄弟節點提取 | 移除 `ASTEngine.outline()` 外層全程佔用之 `with self._lock:`；當單檔含 C# `partial` 符號時，僅在 `merged=True` 時呼叫 `self.ensure_jit_synced()`；若 `merged=False`，優先讀取記憶體既有 `self._snapshot` 或以非阻塞鎖嘗試載入既有 `unified.symbols.bin.gz`，絕不在 `merged=False` 時阻塞於背景鎖或對未建索引之大型專案觸發全倉 `build_index()`。 | P0 | `[P00:DR-03]` |
| **FR-06** | `SemanticBundler` 預先過濾非 AST 可解析副檔名 | 於 `ast_engine/bundler.py:_collect_space_files()` 與 `_resolve_dirty_files_only()` 中，先透過 `self.parser_registry.get_parser(relpath) is not None` 過濾無對應 AST 解析器之非代碼檔案，避免無謂讀取數千個資源檔與堆積空 `FileSymbolGraph`。 | P1 | `[P00:DR-03]` |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `unified.meta.json` 遭外部刪除或舊版索引缺少 `total_edges` / `space_symbol_counts` 欄位 | `ASTEngine.get_persisted_meta()` 與 `status()` 自動平滑回退至既有 `_ensure_symbols_loaded()` / `_ensure_loaded_from_disk()` 載入並動態計算，且讀取過程嚴守 CQS 不產生磁碟寫入副作用。 |
| **EC-02** | 背景執行緒正持有 `ASTEngine._lock` 進行耗時全量建置時，前景執行 `ast status` 或單檔 `ast outline <file.cs>` (`merged=False`) | `status()` 透過無鎖讀取 `unified.meta.json`（或記憶體快照引用）立即回傳；`outline(..., merged=False)` 直接完成單檔解析並以非阻塞方式讀取既有快照，零卡死等待。 |
| **EC-03** | 呼叫端向 `hot_patch_unified_index(diff_detail)` 直接傳入未經 `core.space` 游標之合成 `ScanDiffDetail`（或 `ASTEngine` 先前已跨越多個世代） | `_collect_all_dirty_files` 檢測到 `ensure_jit_synced()` 未推進世代且合成 `diff_detail` 尚未反映於 `snapshot` 時，仍精準補跑一次 `hot_patch_index(detail)`，並保留跨多世代符號差集對齊 (`(snapshot.ast_generation - current_acked_gen) > 1`)。 |
| **EC-04** | 單一測試直接呼叫 `ast/scripts/hook.core.py:on_file_space_changed(context={"engine": engine, ...})` | 當顯式傳入 `engine` 或同進程無活躍 `KnowledgeDBServiceWorker` 時，保持完整原生 `consume_diff("ast")` 與 `hot_patch_index` / `build_index` 行為，100% 向下相容既有單元測試契約。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與非阻塞延遲 | 當 `unified.meta.json` 存在且背景執行緒持有 `ASTEngine._lock` 時，`ASTEngine.status()` 與單檔 `ASTEngine.outline(..., merged=False)` 呼叫延遲 $< 50\text{ms}$，零死鎖阻塞。 |
| **NFR-02** | 運行期隔離與品質守門 | 100% 通過 `dev check` 13 項 AST 靜態守門（`0 FAIL, 0 WARN`）及 `ast`、`knowledge-db`、`server` 全量單元測試（`100% Pass, 0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **[!NOTE] CQS 唯讀不變量**：`ast/tests/test_l0_l1_primitives_and_cache.py` 明確驗證當 `unified.meta.json` 被刪除後呼叫 `get_persisted_meta()`，不得在磁碟重新寫出 `unified.meta.json`；因此讀取回退路徑嚴禁呼叫 `_atomic_write_meta`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[WarmWorker.pre_warm (virtual_cwd=host_dir)]
   ├── service_manager.start_all() ──> 啟動 CoreSpaceWatcher & KnowledgeDBServiceWorker (非阻塞)
   └── 立即發送 worker_ready (< 50ms)

[檔案變更事件流]
CoreSpaceWatcher.flush_dirty_spaces()
   └── broadcast("on_file_space_changed")
         └── ast/scripts/hook.core.py:
               ├── 若 KnowledgeDBServiceWorker 同進程運行中 -> notify_space_changed() 單點讓渡 (不搶 ASTEngine._lock)
               └── KnowledgeDBServiceWorker._run_sync_cycle():
                     ├── Stage 1 前檢查 server.worker.foreground_active 禮讓前景
                     └── IndexingPipeline._collect_all_dirty_files():
                           └── ast_engine.ensure_jit_synced() 單次更新 AST (消除第二次冗餘 hot_patch_index)

[前景 CLI 快篩流]
ast status  ──> 無鎖讀取記憶體 _snapshot/_graph 或 unified.meta.json (< 1ms，免搶 _lock 與 .ast_index.lock)
ast outline ──> 無鎖解析單檔 -> merged=False 時以非阻塞方式讀取既有快照提取 partial_siblings
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `../../ys_codebase/source/ast/ast_engine/engine.py` | Modify | 擴充 `_build_meta_payload()`、無鎖化 `get_persisted_meta()` 與 `status()`，並移除 `outline()` 外層長鎖與 `merged=False` 時之全倉強制重建。 |
| `../../ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 於 `_collect_space_files()` 與 `_resolve_dirty_files_only()` 預先過濾 `parser_registry.get_parser(relpath) is not None`。 |
| `../../ys_codebase/source/ast/scripts/hook.core.py` | Modify | 於同進程 `KnowledgeDBServiceWorker` 活躍或前景任務執行中時，讓渡空間變更予背景 Worker 單點同步。 |
| `../../ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 於 `KnowledgeEngine.pre_warm()` 在 Server Worker 環境下略過阻塞式 `ast_eng._ensure_loaded_from_disk()`。 |
| `../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 於 `_collect_all_dirty_files()` 記錄 `gen_before`，防止 `ensure_jit_synced()` 推進世代後重複執行第二次 `hot_patch_index()`。 |
| `../../ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 於 `_run_sync_cycle()` 進入 Stage 1 前加入 `foreground_active` 禮讓檢查，並於 Watcher 活躍時傳遞 `auto_refresh=False`。 |
| `../../ys_codebase/source/server/server/worker.py` | Modify | 將 `WarmWorker.pre_warm()` 之 `virtual_cwd` 對齊為 `self.host_dir or self.yscb_root`。 |
| `../../ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 新增 `status()` 無鎖快讀、`outline()` 非阻塞 C# `partial`、以及 `SemanticBundler` 副檔名預過濾回歸測試。 |
| `../../ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 Stage 1 前景禮讓與 `_collect_all_dirty_files` 零重複 `hot_patch_index` 回歸測試。 |
| `../../ys_codebase/source/server/tests/test_server.py` | Modify | 新增 `WarmWorker.pre_warm()` `virtual_cwd` 對齊 `host_dir` 驗證斷言。 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `unified.meta.json` 擴充欄位與向下相容校驗**：於 `unified.meta.json` 新增 `total_edges`、`graph_mtime_ns`、`graph_size`、`space_symbol_counts` 與 `space_file_counts`；`status()` 僅在 `symbols` 與 `graph` 二進位檔之 `(mtime_ns, size)` 皆與 `meta` 吻合時走 $O(1)$ 快讀，否則安全回退至 `_ensure_loaded_from_disk()`。
- **[P02:DR-02] Single-Parse Symbol Sharing 單一背景寫入者原則**：在 `WarmWorker` 常駐進程內，由 `KnowledgeDBServiceWorker` 作為唯一背景消費者統一透過 `ensure_jit_synced()` 驅動 `ASTEngine` 與 `InvertedIndex` 更新，徹底消除 `space-watcher` 執行緒與 `knowledge-db-worker` 執行緒對 `ASTEngine._lock` 的雙重踩踏。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/ast/ast_engine/engine.py
class ASTEngine:
    def _build_meta_payload(
        self,
        snapshot: ASTSnapshot,
        graph: Optional[CallGraphIndex] = None,
    ) -> Dict[str, Any]: ...
    def get_persisted_meta(self) -> Optional[Dict[str, Any]]: ...
    def outline(
        self,
        file_or_uri: str,
        merged: bool = False,
        visibility: Optional[str] = None,
        binding: Optional[str] = None,
        member_kind: Optional[str] = None,
    ) -> Dict[str, Any]: ...
    def status(
        self,
        space: Optional[str] = None,
        space_name: Optional[str] = None,
    ) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `ASTEngine.status()` 與 `get_persisted_meta()` 在 `unified.meta.json` 損毀或缺漏時靜默降級至二進位載入，不向外拋出未捕獲之 `JSONDecodeError` 或 `OSError`。
  - `ASTEngine.outline()` 在目標檔案不存在時維持回傳含 `"error": "File not found: ..."` 之字典，不破壞既有 CLI 與測試契約。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有對外 CLI 與 Python SDK 方法簽名 100% 向下相容（Mode B）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- `[x]` **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- `[x]` **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- `[x]` **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：當 `merged=False` 時，單檔成員直接由 `parser_registry.parse_file()` 無鎖提取；若記憶體已有 `_snapshot` 或磁碟已有 `unified.symbols.bin.gz` 且鎖未被背景佔用，則非阻塞載入提取 `partial_siblings`，既保護大型專案不被單檔 `outline` 卡死，也保證已建索引專案之 `[Partial Siblings]` 提示完整顯示。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `../../docs/ast/README.md` | N/A | 對外 CLI 參數與輸出格式無變更 |
| **專題手冊** | `../../docs/server/README.md` | N/A | 對外 CLI 參數與輸出格式無變更 |
| **設計決策** | `../../docs/ast/DESIGN_NOTES.md` | Modify | 登記 `unified.meta.json` 無鎖 $O(1)$ 狀態快讀、單檔 `outline` 非阻塞提取與雙執行緒鎖讓渡機制 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `ASTEngine.status`、`outline`、`hook.core.py` 與 `IndexingPipeline._collect_all_dirty_files` 之 Docstring |
| **發布日誌** | `../../CHANGELOG.md` | Modify | 記錄 `2026_11_10_0055_ast_server_warmup_and_lock_contention_fix` 修繕摘要 |

- **決策定稿**：**[P04:DR-01]** 確認通過動刀前 `Pre-Code Analyze Gate`，進入 Phase 05 源碼實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修正 `server/server/worker.py:pre_warm()` `virtual_cwd` 對齊 `self.host_dir` 及 `knowledge_db/engine.py:pre_warm()` 非阻塞預熱 (`FR-01`)
- [x] **TASK-02**：實作 `ast/scripts/hook.core.py` 同進程 Worker 讓渡、`knowledge_db/service.py` Stage 1 前景禮讓與 `knowledge_db/pipeline.py` 消除重複 `hot_patch_index` (`FR-02`, `FR-03`)
- [x] **TASK-03**：實作 `ast/ast_engine/engine.py` 之 `status()` / `get_persisted_meta()` 無鎖 $O(1)$ `unified.meta.json` 快讀、`outline()` 非阻塞重構，以及 `ast/ast_engine/bundler.py` 副檔名預過濾 (`FR-04`, `FR-05`, `FR-06`)
- [x] **TASK-04**：編寫 `ast`、`knowledge-db`、`server` 單元與並發回歸測試並通過全量 `dev test` 與 `dev check` (`FT-01` ~ `FT-06`, `ET-01` ~ `ET-04`, `RT-01` ~ `RT-02`)
- [x] **TASK-DOC**：同步更新 `docs/ast/DESIGN_NOTES.md`、`CHANGELOG.md` 與源碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
