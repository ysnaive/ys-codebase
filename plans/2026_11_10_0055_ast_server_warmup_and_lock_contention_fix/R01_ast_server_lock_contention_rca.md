# 專題調研與分析報告：AST 指令卡死、Server 預熱阻塞與背景 Stage 1 鎖競爭根因分析 (R01_ast_server_lock_contention_rca.md)

> 調研主題：AST 指令卡死、Server WARMING 預熱阻塞與背景雙執行緒鎖競爭之六大根因診斷與修繕處方  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_0055_ast_server_warmup_and_lock_contention_fix  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 於大型專案（如 `/workspace/uitk.net`）執行 `python yscb.py server start` 後，終端面板顯示 `Worker PID: 1188983 (State: WARMING)` 與 `Background Svcs: 0 registered`。
  - 隨後執行 `python yscb.py ast status`（或其他 `ast` 指令如 `outline`、`slice`、`callers`）時，CLI 頻繁無回應，按 `Ctrl+C` 中斷後顯示阻塞於 `core/commands/dispatcher.py:L320` (`_hot_dispatch_attempt` $\to$ `chunk = resp.read(1024)`)。
- **調研目標與範疇**：
  - 追蹤 `core/commands/dispatcher.py`、`server/server/{master,worker,space_watcher}.py`、`ast/ast_engine/{engine,bundler,graph}.py`、`ast/scripts/{cli,hook.core}.py` 與 `knowledge-db/knowledge_db/{engine,pipeline,service}.py` 全鏈路，精確定位所有造成 `ast` 指令掛起、鎖死或觸發全倉重編譯之根因與行號座標。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 六大阻塞根因 (RC-01 ~ RC-06) 精確座標與機制剖析

| 根因編號 | 檔案路徑與行號座標 | 阻塞機制與觸發條件剖析 | 精確修繕處方 |
| :--- | :--- | :--- | :--- |
| **RC-01**<br>*(Critical)* | `server/server/master.py` L1108, L1281<br>`server/server/worker.py` L135-190<br>`knowledge-db/knowledge_db/engine.py` L976-994 | **Server `WARMING` 主執行緒同步解壓 4 大 `.bin.gz` 與載入 ONNX 模型**：`server start` 僅等待 `worker_alive` 即返回，而 `worker.pre_warm()` 在發出 `worker_ready` 前同步呼叫 `KnowledgeEngine.pre_warm()`，一次解壓反序列化 `unified.symbols.bin.gz`、`unified.graph.bin.gz`、`unified.index.bin.gz`、`unified.vectors.bin.gz` 並初始化 ONNX 模型。此期間任何 `server_compatible: true` 的指令（含 `ast status`）皆在 `MasterSupervisor.dispatch_task` 的 `_wait_worker_ready()` 靜默卡死；若超過 30 秒，Master L1115 還會強殺 Worker 造成無限重啟循環。 | 1. `KnowledgeEngine.pre_warm()` 改為輕量單例初始化，將索引載入與模型預熱移交 `KnowledgeDBServiceWorker` 背景執行緒於 `worker_ready` 後漸進執行。<br>2. `server/worker.py:L137` `pre_warm` 將 `virtual_cwd` 對齊為 `self.host_dir`。 |
| **RC-02**<br>*(Critical)* | `ast/scripts/hook.core.py` L134-304<br>`knowledge-db/knowledge_db/service.py` L608-615<br>`knowledge-db/knowledge_db/pipeline.py` L918-932 | **背景雙執行緒（`space-watcher` vs `knowledge-db-worker`）同時爭搶 `ASTEngine._lock` 並觸發雙重 `hot_patch_index`**：當 `space-watcher` 廣播 `on_file_space_changed` 時，`ast/scripts/hook.core.py` 直接在 `space-watcher` 執行緒同步鎖定 `ASTEngine._lock` 執行熱修補；同時 `knowledge-db-worker` 被喚醒執行 Stage 1 (`_collect_all_dirty_files`)，不僅在 `L918` 再次爭搶 `ASTEngine._lock`，更因 `L927` `(snapshot.ast_generation - current_acked_gen) > 1` 條件誤判，在 `ensure_jit_synced()` 已經更新完 AST 的情況下**重複執行第二次 `self.ast_engine.hot_patch_index(detail)`**！ | 1. 當 `KnowledgeDBServiceWorker` 在同進程運行時，`ast/scripts/hook.core.py` 對已由 `knowledge-db` 管轄之空間直接讓渡予 Worker 單點同步。<br>2. 修正 `pipeline.py:L918-932`：記錄 `gen_before = self.get_current_ast_generation()`，僅當 `ensure_jit_synced()` 未推進世代且確有未消費 dirty files 時才呼叫 `hot_patch_index`。<br>3. 於 `service.py:L608` Stage 1 前加入 `foreground_active` 禮讓檢查。 |
| **RC-03**<br>*(High)* | `ast/ast_engine/engine.py` L741-756, L840-861, L1897-1940 | **`ASTEngine.status()` 強搶 `self._lock` 並完整解壓反序列化 `symbols.bin.gz` + `graph.bin.gz`**：`status()` 在 L1899 進入 `with self._lock:` 並在 L1910 呼叫 `self._ensure_loaded_from_disk()`，每次查看狀態都必須等待背景釋放鎖並完整解壓兩個巨型二進位檔，而未利用現成的 `unified.meta.json`。 | 擴充 `_build_meta_payload()` 儲存 `total_edges`、`graph_mtime_ns`、`graph_size`、`space_symbol_counts` 與 `space_file_counts`；重構 `ASTEngine.status()` 優先以無鎖方式讀取記憶體快照引用或 `get_persisted_meta()`，達成 $<1\text{ms}$ 零阻塞回應。 |
| **RC-04**<br>*(High)* | `ast/ast_engine/engine.py` L1767-1823 | **單檔 `ast outline <file.cs>` 在未傳 `--merged` 時仍無條件觸發全倉 `ensure_jit_synced()`**：在 L1805 中只要單檔內含任何 C# `partial` 符號（Unity C# 專案幾乎檔檔皆有），即使 `merged=False`，也會無條件呼叫 `self.ensure_jit_synced()` 觸發全倉掃描或索引重建，且全程佔用 `self._lock`。 | 1. 單檔解析階段不持有 `self._lock`。<br>2. 當 `any(_is_partial_symbol(s))` 為真時：唯有 `merged=True` 才呼叫 `ensure_jit_synced()`；若 `merged=False`，僅在 `self._snapshot` 已載入（或磁碟快照已存在且鎖未被背景佔用）時提取 `partial_siblings`，絕不因單檔 `outline` 阻塞或觸發全倉 `build_index()`。 |
| **RC-05**<br>*(Medium)* | `ast/ast_engine/bundler.py` L1087-1102, L1262-1266, L1601-1628 | **`SemanticBundler` 未預先過濾非 AST 副檔名即讀取檔案內容**：`_collect_space_files()` 收集空間內所有檔案後，`_parse_file_full()` 與 `extract_all_file_graphs()` 先執行 `open(f_path).read()` 才交由 `parser_registry.extract_file_graph()` 判斷副檔名，在含大量非代碼資產之空間造成無謂磁碟 I/O 與空 `FileSymbolGraph` 堆積。 | 於 `_collect_space_files()` 與 `_resolve_dirty_files_only()` 中，先檢查 `self.parser_registry.get_parser(relpath) is not None`，直接跳過無對應 AST 解析器之檔案。 |
| **RC-06**<br>*(Medium)* | `server/server/worker.py` L137-145, L275-281 | **`WarmWorker.pre_warm()` 與 `execute_task()` 之 `virtual_cwd` 不一致**：`pre_warm()` 綁定 `virtual_cwd=self.yscb_root` (`.yscb`)，而 `execute_task()` 綁定 `virtual_cwd=eff_cwd` (`host_dir`)，易導致依賴 `get_virtual_cwd()` 的組件在首次前景任務時判定 `project_root` 變更而丟棄預熱實例。 | 將 `server/worker.py:L137` `pre_warm()` 之 `virtual_cwd` 統一設為 `self.host_dir or self.yscb_root`。 |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  - `python yscb.py ast status`（及相關 `ast` 指令）在 `/workspace/uitk.net` 卡死並非單一偶發異常，而是由 **`WARMING` 主執行緒同步重載阻塞 (`RC-01`)**、**`space-watcher` 與 `knowledge-db-worker` 雙執行緒鎖踩踏與重複熱修補 (`RC-02`)**、**`status()` 強制爭搶寫鎖與全量解壓 `.bin.gz` (`RC-03`)**、以及 **C# `partial` 單檔 `outline` 誤觸發全倉同步 (`RC-04`)** 共同疊加所致。
- **後續建議（選填）**：
  - 建議立即進入本計畫之階段 B 長任務實作與 VM 沙盒驗證閉環，一次性修復 `server`、`ast`、`knowledge-db` 上述 7 個檔案之缺陷並補齊回歸測試。
