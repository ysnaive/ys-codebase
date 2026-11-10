# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 指令卡死、Server 預熱阻塞與背景 Stage 1 鎖競爭根治修繕 (ast_server_warmup_and_lock_contention_fix)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 開發者於 `/workspace/uitk.net` 啟動 `python yscb.py server start`（面板顯示 `Worker PID: 1188983 (State: WARMING)`、`Background Svcs: 0 registered`）後，執行 `python yscb.py ast status`（及其他 `ast` 指令）頻繁卡死於 `core/commands/dispatcher.py:L320` (`chunk = resp.read(1024)`)。
  2. 先將 `declarative_readonly_file_lock_sdk` 的路線圖調研記錄為 `R01` 後，另開本計畫優先處理 `ast status` / Server 預熱與 Stage 1 鎖競爭卡死問題。
- **核心目標**：
  1. **消除 `WarmWorker.pre_warm()` 主執行緒長阻塞與 `WARMING` 30 秒誤殺循環 (`server` & `knowledge-db`)**：
     - 修正 `WarmWorker.pre_warm()` (`server/worker.py:L137`) 將 `virtual_cwd` 設為 `self.host_dir`（與 `execute_task` 對齊，避免首次前景命令因根目錄不一致重創 Engine）。
     - 重構 `KnowledgeEngine.pre_warm()` (`knowledge_db/engine.py:L976-994`) 為非阻塞輕量預熱（僅初始化 Engine 與輕量設定，將耗時的 `.bin.gz` 大檔反序列化與 ONNX 模型載入交由 `KnowledgeDBServiceWorker` 背景執行緒在 `worker_ready` 後執行），使 Worker 能在毫秒級完成 `worker_ready` 握手，不再卡住 `MasterSupervisor.dispatch_task` 的 `_wait_worker_ready()`。
  2. **根除 `space-watcher` 與 `knowledge-db-worker` 對 `ASTEngine._lock` 的雙執行緒踩踏與重複熱修補 (`ast` & `knowledge-db`)**：
     - 在 `ast/scripts/hook.core.py:on_file_space_changed` 中，若偵測到同進程內 `KnowledgeDBServiceWorker` (`get_active_worker()`) 正在運行且該空間屬於 `knowledge-db` 管轄（Single-Parse Symbol Sharing），則不在 `space-watcher` 執行緒上同步爭搶 `ASTEngine._lock` 重複執行 `hot_patch_index`/`build_index`，統一由背景 Worker 單點推進（或在 `foreground_active` 時延後背景同步）。
     - 修正 `IndexingPipeline._collect_all_dirty_files` (`knowledge_db/pipeline.py:L918-932`)：當 `self.ast_engine.ensure_jit_synced()` 已經消費 `"ast"` 游標並推進 `ast_generation` 時，不再因 `(snapshot.ast_generation - current_acked_gen) > 1` 而誤觸發第二次冗餘的 `self.ast_engine.hot_patch_index(detail)`！
     - 在 `KnowledgeDBServiceWorker._run_sync_cycle` (`knowledge_db/service.py:L608`) 進入 Stage 1 前加入 `server.worker.foreground_active` 禮讓檢查。
  3. **實作 `ASTEngine.status()` 無鎖 $O(1)$ `unified.meta.json` 快讀與單檔 `outline()` 免全倉重編譯 (`ast`)**：
     - 擴充 `ASTEngine._build_meta_payload()` 與 `get_persisted_meta()` (`ast_engine/engine.py:L741-756, L840-861`) 納入 `total_edges`、`graph_mtime_ns`、`graph_size` 與各空間檔案/符號計數 (`space_symbol_counts`、`space_file_counts`)；讓 `ASTEngine.status()` 優先讀取記憶體既有 `_snapshot` 引用或 `unified.meta.json`，**不爭搶 `self._lock` 與 `.ast_index.lock`、不反序列化數十 MB 的 `.bin.gz`**。
     - 修正 `ASTEngine.outline()` (`ast_engine/engine.py:L1776, L1805-1809`)：移除外層對單檔解析不必要的 `with self._lock:` 全程獨佔；當檔案含 C# `partial` 符號時，若 `merged=False`（預設單檔大綱），僅在記憶體已有 `_snapshot`（或磁碟已有快照可快速載入）時提取 `partial_siblings`，**絕不在未傳 `--merged` 時對單檔 `outline` 觸發全倉 `ensure_jit_synced()` / `build_index()`**！
     - 修正 `SemanticBundler._collect_space_files()` (`ast_engine/bundler.py:L1087-1102`)：預先以 `self.parser_registry.get_parser(relpath) is not None` 過濾不可解析之非代碼檔案，避免在大型 Unity/前端專案中無謂開啟並讀取數千個資源檔。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `ASTEngine.meta_index_path` (`unified.meta.json`) 與 `get_persisted_meta()` 既有輕量元數據機制。
  - 復用 `server.worker.foreground_active` (`RuntimeContext` 模組狀態旗標) 既有前景任務禮讓信號。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `ast` 與 `knowledge-db` 對外 CLI 命令參數與 JSON 輸出欄位契約（保持 100% 向下相容）。
- **架構影響範圍**：
  - `ys_codebase/source/ast/ast_engine/engine.py`
  - `ys_codebase/source/ast/ast_engine/bundler.py`
  - `ys_codebase/source/ast/scripts/hook.core.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/engine.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/service.py`
  - `ys_codebase/source/server/server/worker.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `WarmWorker.pre_warm()` 輕量化與 `virtual_cwd` 對齊**：
  - `server/worker.py:pre_warm()` 將 `virtual_cwd` 設為 `self.host_dir`；`KnowledgeEngine.pre_warm()` 僅執行輕量單例綁定，不於 `WARMING` 主執行緒阻塞解壓 4 個 `.bin.gz` 與載入 ONNX 模型，確保 `worker_ready` 立即發出，徹底消除 `server start` 後緊接著執行 CLI 指令時的 30 秒 `_wait_worker_ready()` 掛起與誤殺循環。
- **[P00:DR-02] 消除 `space-watcher` 與 `knowledge-db-worker` 雙重熱修補及 Stage 1 前景禮讓**：
  - 當 `KnowledgeDBServiceWorker` 在同進程活躍時，`ast/scripts/hook.core.py` 將空間變更交由背景 Worker 統一透過 `Single-Parse Symbol Sharing` 消費，避免兩條背景執行緒同時爭搶 `ASTEngine._lock`；並修正 `pipeline.py:L925-932` 在 `ensure_jit_synced()` 已推進世代後又重複呼叫 `hot_patch_index(detail)` 的缺陷。
- **[P00:DR-03] `ast status` 無鎖元數據快讀、單檔 `outline` 免全倉重編譯與 `SemanticBundler` 副檔名預過濾**：
  - `ASTEngine.status()` 透過擴充後的 `unified.meta.json` 與無鎖快照引用實現 $<1\text{ms}$ 即時回傳；`ASTEngine.outline()` 在 `merged=False` 時不強制觸發全倉 `build_index()`；`SemanticBundler._collect_space_files()` 僅收集 `parser_registry.get_parser(relpath) is not None` 之可解析檔案。

---

## 3. 開放議題與確認紀錄

- **[待確認]** 六大根因診斷與修繕規格已完整落檔於 [`R01_ast_server_lock_contention_rca.md`](./R01_ast_server_lock_contention_rca.md) 與本文件，請開發者確認是否直接啟動**階段 B 全自動長任務實作、VM 沙盒測試、雙盲審查與受控 CoW 同步閉環**？
