# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 建立日期：2026-11-07  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：借鑑 Jupyter Kernel（`ipykernel` + `InteractiveShell` + `%autoreload` + 多通道協議）之常駐執行期架構，結合統一 `core.log` 雙族系管線（`log*` 調用者終端串流 vs. `logFile*` 可配置滾動視窗增量檔案紀錄）、`RuntimeContext` 實例化隔離容器、`BaseServiceWorker` 原生受管獨立執行緒模型（含 `knowledge-db` 向量模型離線預檢守門）與 `module:dev` 封閉式單次遍歷 13 項 AST 靜態守門管線，將 `ys-codebase` 升級為具備確定性空間、時間與編譯期隔離保證的微內核執行環境。
- **架構邊界**：
  - **四大核心支柱定案**：
    1. **支柱一：統一 `core.log` 雙族系管線（`log*` vs. `logFile*`）**：全面封殺業務模組未受管之原生 `print()`、`sys.stdout.*`、`sys.stderr.*`、`logging.*` 與裸 `input()` / `sys.stdin.*`；所有終端輸出透過 `log*` 依當前 `ExecutionContext` 精準投遞予前景終端或常駐熱派發 IPC 回傳通道（100% 物理消除背景串音並自動連動 `error_hint`）；所有持久化檔案日誌透過 `logFile*` 以可配置滾動視窗（按筆數/大小截斷、歷史世代輪替、Crash 殘留檔恢復與 `os.set_inheritable(fd, False)` 句柄保護）增量寫入，統一收編 `ServerLogger` 與 `telemetry.py`。
    2. **支柱二：`RuntimeContext` 實例化容器、零拷貝唯讀視圖與受保護模組命名空間載入器**：消滅全倉模組頂層無主可變快取與 `global` 關鍵字，將 URI 映射、Contributes 聚合、Config 組態、語系與虛擬工作目錄（`virtual_cwd` / 請求級 `env`）收斂至 `RuntimeContext` 實例與 `contextvars.ContextVar`；跨模組契約全面採用 `@dataclass(frozen=True)` 與 `types.MappingProxyType` 唯讀視圖；動態模組與腳本統一透過受保護命名空間載入器原子載入（支援 `(mtime_ns, size)` 世代感知熱刷新與失敗回滾）。
    3. **支柱三：Jupyter 式常駐三平面解耦、`BaseServiceWorker` 受管獨立執行緒與 KDB 離線守門**：分離 Control Channel 與 Shell Execution Channel，拔除 `WarmWorker` 熱派發期間的全域 `sys.stdout` 插拔劫持、`os.chdir()` 與 `os.environ` 原地突變；由 `BaseServiceWorker` 原生為每個註冊服務配發專屬受管獨立執行緒與非阻塞狀態機（`STARTING`/`UPDATING`/`READY`/`DEGRADED_OFFLINE`），廢除並物理刪除 `hook.server.py` 私開野執行緒；於 `knowledge-db` 實作純本地 `< 1ms` 之 `has_local_model()` 離線預檢、保留背景受管執行緒於 Stage 1 完成後非阻塞自動下載模型（離線時降級標記 `DEGRADED_OFFLINE`）、將手動 `yscb kdb model download` 解耦為 `server_compatible: false`，並修復 `IndexingPipeline._ensure_jit_index_ready` 前景搶鎖死鎖。
    4. **支柱四：`module:dev` 封閉式單次遍歷 13 項 AST 靜態守門管線**：拔除無外部消費者的 `dev/contributes/_format.json`（`custom_checks`）與動態載入邏輯，將 `dev/checker.py` 重構為純靜態、零動態代碼載入的單次 AST 遍歷管線（Single-Pass `ast.NodeVisitor`），強制執行 6 大類共 13 項 AST 靜態守門規則（A1~F13 違規即判定 `FAIL`）。
  - **五階段正交子計畫推進策略（`sub_01` ~ `sub_05`）**：
    - 依「**先立 `core` 輸出與狀態基座（`sub_01`、`sub_02`）$\to$ 再解耦 `server` 三平面與受管 Worker/KDB 離線守門（`sub_03`）$\to$ 接著執行上層 7 大模組機械合規遷移（`sub_04`）$\to$ 最後由 `dev check` 啟用 13 道靜態守門收網（`sub_05`）**」之拓撲順序推進，確保每個子計畫皆可獨立通過 `dev check` 與 `dev test`。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_log_pipeline_and_streamer_unification` | Full Track | `Completed` | 建立 `core/core/log.py`（`log*` 調用者終端串流與 `log_file*` 可配置滾動視窗增量檔案紀錄），一併收編 `ServerLogger`（含 `os.rename` 升級 `os.replace`）、`DebouncedIOStreamer` 與 `telemetry.py` 輪替邏輯，並完成 `core` 內部 346 處輸出遷移（豁免 `yscb.py` 單檔 Bootstrap 原生輸出） |
| **sub_02** | `sub_02_core_runtime_context_and_namespace_loader` | Full Track | `Completed` | 擴充 `RuntimeContext` 與 `ContextVar`（含 `virtual_cwd` 與請求級 `env`）收斂 `core` 29 個頂層可變快取並消除 10 處 `global`、2 處 `Path.cwd()` 與非啟動器 `sys.exit()`；凍結 `core` 9 個未設 `frozen=True` 之 `@dataclass` 與 `MappingProxyType` 唯讀視圖；建立受保護模組命名空間載入器統一替換 5 處 `spec_from_file_location` / `sys.modules` 邏輯 |
| **sub_03** | `sub_03_server_three_plane_and_managed_worker_threads` | Full Track | `Completed` | 解耦 `server` 控制與執行通道，移除 `WarmWorker` 全域 `sys.stdout` 劫持、`os.chdir()` 與 `os.environ` 突變；於 `BaseServiceWorker` 內建受管獨立執行緒與非阻塞狀態機，收編 3 個常駐服務並刪除 `file-space`/`knowledge-db` 之 `hook.server.py` 野執行緒；落地 KDB `has_local_model()` 離線預檢、保留背景受管執行緒非阻塞自動下載、解耦手動 `kdb model download` CLI 並修復 `pipeline.py` 前景搜尋搶鎖阻塞 |
| **sub_04** | `sub_04_ecosystem_modules_compliance_migration` | Full Track | `Completed` | 將上層 7 大業務模組（`dev`, `file-space`, `ast`, `knowledge-db`, `agents-workflow`, `vscode-support`, `gdrive-support`）共 531 處原生輸出與 `logging` 遷移至 `core.log`；消除 24 處 `os.chdir`/`os.getcwd`/`Path.cwd`、11 處 `os.environ` 突變、2 處缺 `timeout=` 之 `subprocess.run` 與裸 `input()`；收斂 47 處頂層可變容器/`global` 與 48 處非凍結 `@dataclass`/類別可變屬性（`ast` 僅執行薄層機械合規調整，留待 Tier 2 重構） |
| **sub_05** | `sub_05_dev_closed_loop_ast_static_guardrails` | Full Track | `Completed` | 物理刪除 `dev/contributes/_format.json` 與 `dev/checker.py` 之 `_check_custom_rules`；將 `_check_source_files` 重構為封閉式單次遍歷（Single-Pass `ast.NodeVisitor`）管線，正式啟用 6 大類 13 項 AST 靜態守門規則（A1~F13 強制 `FAIL`），補齊正負向單元測試並完成全倉 9 大模組零違規驗收 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `core.log`（`log*` / `logFile*`）雙族系管線建置、`ServerLogger`/`telemetry.py` 收編與 `core` 輸出遷移
- [x] **里程碑 2 (`sub_02`)**：完成 `RuntimeContext` 隔離容器、`MappingProxyType` / `frozen=True` 唯讀契約與受保護模組命名空間載入器
- [x] **里程碑 3 (`sub_03`)**：完成 `server` 常駐三平面解耦、`BaseServiceWorker` 受管獨立執行緒、移除 `hook.server.py` 野執行緒與 KDB 離線非阻塞守門
- [x] **里程碑 4 (`sub_04`)**：完成上層 7 大業務模組存量語法與狀態合規遷移
- [x] **里程碑 5 (`sub_05`)**：完成 `module:dev` 封閉式單次遍歷 13 項 AST 靜態守門管線與全倉 `dev check` 零違規結案
