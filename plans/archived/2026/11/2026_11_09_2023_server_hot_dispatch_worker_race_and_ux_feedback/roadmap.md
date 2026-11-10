# 技術路線圖：常駐 Server 全量熱派發、下游背景 Worker 競態治理與 CLI 即時進度反饋暨靜態速查輕量化架構 (Roadmap)

> 主題：常駐 Server 全量熱派發、下游背景 Worker 競態治理與 CLI 即時進度反饋暨靜態速查輕量化架構 (`server_hot_dispatch_worker_race_and_ux_feedback`)  
> 歸檔日期：2026-11-10  
> 狀態：Completed
> 目標範疇：`server`、`core` (`dispatcher` / `log` / `space`)、`ast`、`knowledge-db`、`gdrive-support`（全模組熱派發路由、前景/背景執行緒鎖競態治理、耗時指令即時進度串流反饋與 $O(1)$ 靜態狀態速查優化）  
> 前置解鎖條件：[Tier 1 - 緊隨 `2026_11_10_0025_declarative_readonly_file_lock_sdk` 結案後立即自動接續啟動]（已整併吸收 `kdb_vector_model_offline_guard_and_nonblocking_worker` 之非阻塞鎖探測與背景退讓需求；**強制於 `auto` `P06` 斷點執行 `@codebase-deep-auditor` / `@yscb-async-deep-audit` 最多三輪靶向深度審計融斷閉環，嚴禁直接進 `P07`**）  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **耗時重建與索引過程呈現「黑盒靜默」，使用者與 Agent 無法分辨「正常建圖中」抑或「鎖死卡住」**：當執行 `ast callers/callees/impact/traverse/slice` 或 `knowledge-db search/index` 觸發全倉首次建圖或大規模髒檔熱修補（`build_index` / `hot_patch_index` / `WorkspaceGraphLinker.link_workspace`）時，底層需解析數百至上千個原始碼檔案並計算跨檔調用邊，耗時可達數秒至十餘秒。然而現行管線在完成前 0 輸出，搭配 `WarmWorker` 的 `DebouncedIOStreamer(debounce_ms=500)` 緩衝，導致終端機長時間毫無反應，迫使使用者誤判為卡死而手動 `Ctrl+C` 中斷。
  - **靜態狀態速查指令（`status`）與單檔靶向指令（`slice`）誤觸全量載入或全盤掃描**：
    1. `knowledge-db status` 於 `KnowledgeEngine.status()` 內部無條件呼叫 `_ensure_indices_loaded(load_vectors=has_vector_index)`（同步解壓並反序列化數十 MB 的 `unified.index.bin.gz` 與 `unified.vectors.bin.gz`），且當空間尚未建立快照時退回 `len(iter_space_files())` 觸發同步全盤目錄走訪。
    2. `ast status` 在 `unified.meta.json` 尚未生成（如舊版快取或首次建圖期間）時，退回 `with self._lock: _ensure_loaded_from_disk()` 嘗試獲取排他鎖並解壓全量 `.bin.gz`。
    3. `ast slice <rel_path>::<fqn>` 雖已具備明確單檔座標，但在 `_resolve_symbol_node_for_slice()` 中仍無條件先呼叫 `get_workspace_graph(auto_sync=True)` 觸發全倉 JIT 同步與工作區圖譜連結，喪失 L0 單檔切片應有的 $O(1)$ 毫秒級響應。
  - **全量 `server` 熱派發（Hot-Dispatch）覆蓋缺口與客戶端斷線殭屍任務**：各模組 `contributes/core.json` 中仍有部分安全唯讀指令未標註 `server_compatible: true`（如 `gdrive-support branch list`、新増之 `core file-lock` 子指令群等），或冷熱派發退避邊界與客戶端 `Ctrl+C` 斷線時的 Worker 任務取消通知機制尚待收斂。
  - **前景熱派發任務與下游背景 `ServiceWorker`（`space-watcher`、`knowledge-db-worker`）跨層鎖與資源競態**：在 `WarmWorker` 單一常駐進程內，背景執行緒（`space-watcher` 定時增量掃描、`knowledge-db-worker` 消費 AST 快照與計算 ONNX 向量）與前景熱派發執行緒共享記憶體單例（`ASTEngine._lock`、`SpaceScanner._rlock`、`EmbeddingService._init_lock`）與磁碟跨進程鎖（`InterProcessLock`）。若背景執行緒長時間持有鎖或未在前景任務進入時主動禮讓（Yield），前景指令將被迫排隊等待背景批次完成。
- **長期願景與目標定位**：
  1. **全量 `server` 熱派發治理與斷線感知**：確保所有適合熱派發之跨模組指令 100% 納入 `server_compatible: true` 並具備確定性的冷熱回退與斷線偵測。
  2. **前景絕對優先與零阻塞背景競態（Foreground Preemption & Lock-Free Fast Paths）**：建立前景任務與背景 `ServiceWorker` 間之協作退讓協議與非阻塞鎖探測，杜絕背景工作阻塞前景 CLI。
  3. **確定性即時 UX 進度串流反饋（Real-Time Stage & Progress Feedback over `stderr`）**：在所有耗時建圖、掃描與索引管線植入節流式階段與百分比進度回報，讓使用者隨時掌握執行狀態。
  4. **靜態狀態速查與單檔指令 $O(1)$ 瞬時響應（Zero Full-Scan / Zero Heavy Unpickle on Status & Single-File Ops）**：所有 `status` 速查指令全面改走輕量元數據（`.meta.json` / 檔案標頭）與非阻塞探針，單檔指令嚴格禁止連帶觸發全倉建圖。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **靜態速查零重載與零全盤掃描不變量（$O(1)$ Metadata-Only Status Invariant）**：任何模組之 `status` 指令（`ast status`、`knowledge-db status`、`core file-space status`、`core status`、`vscode-support status`、`gdrive-support status`、`agents-workflow plan status`）嚴禁觸發全盤目錄遞迴走訪（`iter_space_files`）、嚴禁觸發 JIT 建圖（`ensure_jit_synced`），且嚴禁阻塞式解壓大型 `.bin.gz` 索引檔；一律透過預寫之輕量 `.meta.json` 與非阻塞鎖探針於 $<30\text{ms}$ 內返回（若背景正在建圖，直接回報 `building_in_progress` 及當前進度）。
  - **人機雙通道嚴格分離之即時進度反饋不變量（Stderr Progress Heartbeat & Pure Stdout JSON）**：凡預計耗時超過 $300\text{ms}$ 之建圖、熱修補或全量掃描操作（如 `ASTEngine.build_index` / `hot_patch_index`、`IndexingPipeline.rebuild_all`、`SpaceScanner.scan`），必須透過統一之節流進度回報器（每 $250\text{ms}\sim500\text{ms}$ 或階段切換時）向 `stderr` 輸出明確階段與進度（如 `[ast] 正在建構 AST 符號與呼叫圖譜 (1/3: 解析檔案 120/450 [27%]...)`），且在 `DebouncedIOStreamer` 中對進度訊號立即 flush；同時保證 `--json` 模式下 `stdout` 100% 純淨無污染。
  - **前景任務優先與背景非阻塞退讓不變量（Foreground Priority & Cooperative Worker Yielding）**：當 `server.worker.foreground_active` 為 `True` 時，背景 `space-watcher` 與 `knowledge-db-worker` 於迴圈及微批次（Micro-batch）切片點主動暫停讓出 CPU 與鎖資源；且前景檢索在探測 `EmbeddingService._init_lock` 或索引鎖時一律採非阻塞探測或短逾時瞬時降級（整併 `kdb_vector_model_offline_guard_and_nonblocking_worker`）。
  - **L0 單檔原語零全域副作用不變量（Single-File $O(1)$ Isolation）**：`ast outline <file>`（預設非 `--merged`）與帶明確檔案路徑之 `ast slice <rel_path>::<fqn>` 必須優先走單檔 `parse_file(rel_path)` 快速路徑，禁止無條件拉起全倉 `get_workspace_graph(auto_sync=True)`。
  - **`P06` 斷點強制三輪雙盲靶向深度審計與融斷守門不變量（Mandatory `P06` Deep-Audit Circuit-Breaker Gate）**：嚴禁於 `P06` 初次單元測試通過後直接進入 `P07`；於 `auto` `P06` 斷點時，必須依據 `@codebase-deep-auditor` 九維度標準（`C1~C9` / `A1~A5` 架構整理 / `D1~D5` 演進技術債 / 三平台相容）與 `@yscb-async-deep-audit` 三軌五步雙盲子代理閉環（`OPT/ARCH` x `PERF` x `AUD`：Fresh-Eyes 初審 $\to$ Devil's Advocate 反向查證 $\to$ 根因手術修復 $\to$ VM `0 ResourceWarning` 測試與微基準實測），針對受改動模組執行最多 3 輪（`Loop 1 ~ Loop 3`）靶向深度審查，僅在提早達成零確定性缺陷（`P0=0, P1=0, P2=0` 且無殘留 `ARCH`/`PERF` 債）融斷或完成 3 輪收斂後，方可進入 `P07` 結案。

---

## 3. 四大實施支柱與階段演進構想 (Implementation Pillars & Stages)

- **前置解鎖條件與觸發時機**：於 `2026_11_10_0025_declarative_readonly_file_lock_sdk` 完成 `P06` 靶向深度審計融斷、`P07` 結案與雲端同步後，緊接著於同一長任務直接透過 `roadmap promote server_hot_dispatch_worker_race_and_ux_feedback` 啟動實作。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（全量 `server` 熱派發路由盤點與下游 Worker 競態/鎖順序治理）**：
     - 盤點並補齊 8 大模組 `contributes/core.json` 之 `server_compatible` 標記（含 `core file-lock`、`gdrive-support branch list` 等），強化 `MasterSupervisor` / `WarmWorker` 對客戶端斷線之偵測與清理。
     - 徹查並修復 `WarmWorker` 前景執行緒與 `space-watcher`、`knowledge-db-worker` 在 `SpaceScanner`、`ASTEngine`、`KnowledgeEngine` 及 `EmbeddingService` 上的鎖競爭，實作前景活躍期間之背景微批次主動禮讓與非阻塞模型/索引鎖降級。
  2. **Stage 2（耗時指令即時 UX 進度反饋與串流低延遲刷新）**：
     - 於 `core.log` / `DebouncedIOStreamer` 支援低延遲進度訊號即時刷新（避免 500ms 吞沒進度提示）。
     - 於 `ast`（`build_index`、`hot_patch_index`、`WorkspaceGraphLinker`）與 `knowledge-db`（`index`、`search` JIT 同步）植入結構化階段與檔案計數進度反饋（輸出至 `stderr`），確保建圖期間終端機即時顯示階段與百分比。
  3. **Stage 3（靜態狀態速查指令 $O(1)$ 輕量化與單檔切片快速路徑優化）**：
     - 為 `knowledge-db` 建立 `unified.meta.json` 輕量元數據快取，拔除 `KnowledgeEngine.status()` 中解壓 `.bin.gz` 與呼叫 `iter_space_files()` 全盤掃描之重型路徑。
     - 強化 `ASTEngine.status()` 非阻塞探針（建圖中或無 `meta.json` 時免鎖快速回報狀態與建圖進度），並優化 `ASTEngine._resolve_symbol_node_for_slice()` 支援 `<rel_path>::<fqn>` 單檔 $O(1)$ 直接解析切片。
  4. **Stage 4（`P06` 斷點三輪雙盲靶向深度審計融斷閉環與全倉併發壓力回歸驗證）**：
     - 於 VM 沙盒執行「背景建圖/向量索引同步進行中 + 前景併發呼叫 `ast status` / `kdb status` / `ast slice` / `ast callers`」之整合測試與微基準實測。
     - 於 `P06` 斷點啟動 `@codebase-deep-auditor` + `@yscb-async-deep-audit` 三軌五步雙盲子代理靶向審查（`Loop 1 ~ Loop 3`，提早零缺陷則融斷），確認 `0 ResourceWarning`、`dev check` 全數通過後再進入 `P07` 結案。
