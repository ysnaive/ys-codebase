# 專題調研與分析報告：全倉執行期隔離、core.log 管線與 13 項 AST 靜態守門之技術面暨影響半徑盤點 (R01_technical_surface_and_blast_radius_audit.md)

> 調研主題：Jupyter 式執行期核心隔離、統一 `core.log` 管線、受管獨立 Worker 執行緒與 `dev` 13 項 AST 靜態守門之全倉量化影響半徑與子計畫切分  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 本計畫（源自 `roadmap.md`）旨在系統性根治 `ys-codebase` 在「冷派發、常駐熱派發主執行緒、常駐背景服務執行緒、多沙盒測試」四平面共用 Python 進程全域狀態引發的交叉污染、日誌串音與背景阻塞卡死問題，並透過 `module:dev` 封閉式 13 項 AST 靜態守門規則建立編譯期防線。
  - 由於改造範圍橫跨 `yscb.py` 與全倉 9 大模組（`core`、`server`、`dev`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support`），在正式啟動子計畫實作前，必須先對全倉生產源碼執行 Python `ast` 語法樹精確掃描，量化每一項支柱與每一條靜態規則的真實影響半徑，並切分出可獨立交付驗收的 Umbrella 子計畫拓撲。
- **調研目標與範疇**：
  1. 對 `yscb.py`（1 檔）、`core`（45 個非測試 `.py` 檔）、`server`（8 個非測試 `.py` 檔）及上層 7 大業務模組（114 個非測試 `.py` 檔），合計 **168 個生產 `.py` 檔案**進行 100% 靜態語法樹掃描。
  2. 精確定位 `core` 全域快取與動態模組載入器、`server` 常駐串流劫持與 `BaseServiceWorker` 生命週期、`knowledge-db` 離線向量模型與前景/背景共享鎖死鏈路，以及 `dev/checker.py` 單次遍歷改造落點。
  3. 制定零循環依賴、可逐階段獨立驗收之 `sub_01` ~ `sub_05` 子計畫切分邊界。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 全倉 168 個非測試 `.py` 檔案於 6 大類 13 項 AST 守門規則下之違規分佈矩陣

| 規則代碼與檢核項目 | `yscb.py` + `core` (46 檔) | `server` (8 檔) | `dev` (13 檔) | `file-space` (11 檔) | `ast` (33 檔) | `knowledge-db` (21 檔) | `agents-workflow` (22 檔) | `vscode-support` (6 檔) | `gdrive-support` (8 檔) | 全倉總計 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **(A1) 原生 `print` / `stdout` / `stderr` / `logging`** | **386**<br>*(含 `yscb.py` 40 筆)* | **58**<br>*(含 `logger.py`)* | **139** | **12** | **57** | **78** | **206** | **30** | **9** | **975** |
| **(A2) `input()` / `sys.stdin` 讀取** | **2**<br>*(`uri.py:L433,500`)* | **1**<br>*(`worker.py:L268` 豁免)* | 0 | 0 | 0 | 0 | **3**<br>*(`initializer.py:L143`, `cli.py:L480`)* | 0 | 0 | **6** |
| **(B3) 非啟動器 `sys.exit()` / `os._exit()`** | **3**<br>*(`guard.py:L45`, `uri.py:L503,507`)* | **3**<br>*(`master.py`, `cli.py`)* | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **6** |
| **(B4) `os.chdir()` / `os.getcwd()` / `Path.cwd()`** | **11**<br>*(含 `yscb.py` 5 筆)* | **4**<br>*(`worker.py:L134,195,214`)* | **8** | 0 | **6** | **5** | **5** | 0 | 0 | **39** |
| **(B5) `os.environ` 執行期寫入/突變** | **7**<br>*(`dispatcher.py:L725-733`)* | **3**<br>*(`worker.py:L34,36,137`)* | **4** | 0 | 0 | **7**<br>*(`embedding.py`, `hook.dev.py`)* | 0 | 0 | 0 | **21** |
| **(B6) `signal.signal()`** | 0 | **2**<br>*(`master.py` 豁免)* | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **2** |
| **(C7) 可變預設參數 (`def fn(x=[])`)** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| **(C8) 頂層可變快取/容器與 `global`** *(不含 `__all__`)* | **48**<br>*(29 快取 + 9 常數 + 10 `global`)* | **2**<br>*(`service.py` 節流狀態)* | **3** | **6** | **14** | **11** | **10** | **1** | **2** | **97** |
| **(C9) 類別頂層可變屬性與非 `frozen` `@dataclass`** | **9** | **1**<br>*(`ServerConfig`)* | **4** | **1** | **16** | **6** | **16** | **2** | **3** | **58** |
| **(D10) 直接操作 `sys.path` / `sys.modules` / `sys.argv`** | **40**<br>*(分散於 7 檔)* | **3**<br>*(`service.py:L125-131`)* | **4** | 0 | **5** | 0 | 0 | 0 | 0 | **52** |
| **(D11) `eval()` / `exec()` / `__import__()`** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| **(E12) `os.rename()` 非原子改名** | 0 | **1**<br>*(`logger.py:L50`)* | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **1** |
| **(F13) 缺 `timeout=` 之 `subprocess` 與野執行緒 `Thread`** | **1**<br>*(`process.py:L95`)* | **9**<br>*(Master/Watcher/Worker)* | **2**<br>*(`tester.py:L572,922`)* | **1**<br>*(`hook.server.py:L39`)* | 0 | **2**<br>*(`service.py:L302`, `hook.server.py:L26`)* | 0 | 0 | **1**<br>*(`service.py:L114`)* | **16** |

### 2.2 四大支柱深水區架構剖析與關鍵座標

#### 2.2.1 支柱一：`core.log` 雙族系管線與既有四套日誌機制收斂
1. **收編 `server/server/logger.py` (`ServerLogger`, `L1-L336`)**：
   - `ServerLogger` 已實作 `.cache/server/log` 崩潰殘留時間戳解析與恢復歸檔（`recover_and_open` `L173-L201`）、停機歸檔（`archive_and_close` `L203-L233`）、最多 5 份歷史輪替清理（`clean_rolling_history` `L125-L156`）、`os.set_inheritable(self._file.fileno(), False)`（`L169`）與增量尾端讀取（`read_tail_chunks` `L295-L336`）。
   - 收編進 `core/core/log.py` 之 `logFile*` 族系時，一併將 `_safe_replace_file`（`L50`）中的 `os.rename(src, dst)` 升級為原子性的 `os.replace(src, dst)`（消除全倉唯一 1 處 E12 違規），並在 `server/logger.py` 保留薄相容委派以無縫銜接 `master.py`（31 處呼叫）與 `server/scripts/cli.py`（`L196`）。
2. **收編 `core/core/telemetry.py` (`L1-L259`) 與 `gdrive_support/coordinator.py` (`_append_log` `L582-L596`)**：
   - `telemetry.py` 的 `_rotate_telemetry_file`（`L175-L200`，上限 `512KB`、保留最後 `1500` 行）直接抽提為 `logFile*` 的 `keep_lines + max_bytes` 滾動策略；同時當呼叫 `core.log.log_error()` 時自動寫入當前 `ExecutionContext` 的 `error_hint`，徹底消滅 `core/commands/dispatcher.py` 的全域變數 `_LAST_DISPATCH_ERROR_HINT`（`L32, L259, L284, L469, L579`）。
3. **豁免邊界**：
   - 頂層單檔啟動器 `yscb.py`（40 處 `print`）在 `core` 尚未物化前（如 `init`、`self-update`、首次 bootstrap）必須維持零外部依賴，因此明文列入 A1、B3（`L1493` `sys.exit(main())`）、B4（`os.getcwd()`）、D10（`sys.path` 引導）之啟動器白名單豁免。

#### 2.2.2 支柱二：`RuntimeContext` 實例化容器、唯讀契約與受保護命名空間載入器
1. **`core` 29 個頂層可變快取與 10 處 `global` 清單**：
   - `core/uri.py`：`_URI_TLS` (`L54`)、`_reconciling_tokens` (`L55`, `global` 於 `L482`)、`_TOKEN_MAP_CACHE` (`L283`)、`_SCHEMES_CACHE` (`L293`)、`_URI_REENTRANCY` (`L294`)；並將 `L503, L507` 的 `sys.exit(1)` 改為拋出受控例外。
   - `core/config.py`：`ConfigManager._cache` (`L21`)、`_mtimes` (`L22`)。
   - `core/contributes.py`：`_MERGED_MEMORY_CACHE` (`L233`)、`_JSON_FILE_CACHE` (`L235`)、`_LAST_CLEAN_SCAN_TS` (`L237`)。
   - `core/commands/dispatcher.py`：`_GLOBAL_REGISTRY` (`L28`)、`_GLOBAL_REGISTRY_ROOT` (`L29`)、`_MODULE_CACHE` (`L30`)、`_AUTO_SPAWN_WARNED` (`L31`)、`_LAST_DISPATCH_ERROR_HINT` (`L32`)，消除 `L47, L78, L259, L284, L416, L469, L579` 共 7 處 `global` 及 `L725-L733` 對 `os.environ` 的直接寫入。
   - `core/locale.py`（`_LOCALE_FILE_CACHE` `L69`、`_MODULE_BASE_DIR_CACHE` `L70`、`_SAFE_SUBPATH_CACHE` `L71`）、`core/symbols.py`（`_RESOLVED_CALLABLE_CACHE` `L34`）、`core/gitignore.py`（`_CUSTOM_ROOT_DYNAMIC_STORE` `L49`）、`core/platform/process.py`（`_CAN_SPAWN_DAEMON_CACHE` `L16`, `global` `L41`）、`core/platform/venv.py`（`_ACTIVE_TEST_SOURCE_PATHS` `L11`）、`core/space/registry.py`（`_DEFAULT_REGISTRIES` `L1414`）、`core/space/scanner.py`（`_DEFAULT_SCANNERS` `L1606`）、`core/space/watcher.py`（`_SUBSCRIBERS` `L28`、`_ACTIVE_WATCHER_WORKER` `L31`, `global` `L139`）。
2. **`core` 9 個未設 `frozen=True` 之 `@dataclass` 凍結清單**：
   - `core/commands/registry.py`：`ArgSpec` (`L10`)、`OptionSpec` (`L19`)、`CommandSpec` (`L33`)、`ModuleSpec` (`L49`)。
   - `core/space/scanner.py`：`FileFingerprint` (`L58`)、`ScanDiffDetail` (`L87`)、`ScanDiffResult` (`L116`)、`SnapshotState` (`L176`)。
   - `core/space/schema.py`：`SpaceConfig` (`L655`，並移除 `L681` `default_factory=Path.cwd` 隱式工作目錄綁定）。
3. **統一受保護模組命名空間載入器（收斂 5 處分散實作）**：
   - 統一收斂 `core/symbols.py` (`L160-L197`)、`core/commands/dispatcher.py` (`L612-L645`)、`core/events.py` (`L97-L142`)、`core/engine.py` (`L2329-L2345`) 與 `server/server/service.py` (`_load_service_class_from_uri` `L108-L138`) 的 `spec_from_file_location` + `sys.modules` 邏輯，支援 `(mtime_ns, size)` 世代指紋比對熱重載與異常自動回滾。

#### 2.2.3 支柱三：`server` 三平面解耦、受管獨立 Worker 執行緒與 KDB 離線守門
1. **移除 `WarmWorker` 全域串流劫持與環境突變（`server/server/worker.py`）**：
   - 現行 `WarmWorker.execute_task` 在 `L133-L137` 直接呼叫 `os.chdir(cwd)` 與 `os.environ.update(env)`，並於 `L153, L200` 透過 `DebouncedIOStreamer` 將全域 `sys.stdout` / `sys.stderr` 替換為 `_StreamProxy`（`streamer.py:L125-L126`），導致背景執行緒日誌混入前景 CLI 輸出且相對路徑被動態切換。改由 `ContextVar` 綁定請求專屬 IPC 輸出器、`virtual_cwd` 與環境覆寫表後即可徹底拔除。
2. **`BaseServiceWorker` 原生受管執行緒與拔除 2 支 `hook.server.py` 野執行緒**：
   - 擴充 `server/server/service.py` 之 `BaseServiceWorker`（`L141-L182`），由 `ServiceManager` 自動為每個 Worker 建立專屬獨立受管 `threading.Thread`、綁定背景 `ContextVar` 與 `stop_event`，統一收編 `CoreSpaceWatcherServiceWorker`（`space_watcher.py:L239`）、`KnowledgeDBServiceWorker`（`knowledge_db/service.py:L302`）與 `GDriveSyncServiceWorker`（`gdrive_support/service.py:L114`）。
   - 物理刪除私開野執行緒搶鎖的 `file-space/scripts/hook.server.py`（`L39`）與 `knowledge-db/scripts/hook.server.py`（`L26`），並移除對應 `contributes/core.json` 中的 `worker_warming` / `server_worker_warming` 註冊。
3. **根治 `knowledge-db` 雙重阻塞死鎖與離線模型守門**：
   - **離線預檢 `has_local_model()`**：於 `knowledge_db/embedding.py`（`L125-L213`）移除 `len(sub_entries) <= 3` 寬鬆猜測，嚴格檢驗本地快取目錄內 `.onnx`、`tokenizer.json` 與 `config.json` 完整性；無模型且 `allow_download=False` 時於 `< 1ms` 內直接標記 `DEGRADED_OFFLINE` 返回，不呼叫 `TextEmbedding(...)`；有模型時強制傳入 `local_files_only=True`。
   - **拔除背景每 60 秒自動下載**：刪除 `knowledge_db/service.py` `L402-L415` 自動呼叫 `emb_svc.download_model(force=False)` 的邏輯；並將 `knowledge-db/contributes/core.json` `L285` 之 `model.download` 設為 `"server_compatible": false`。
   - **修復前景搜尋搶鎖死鎖**：重構 `knowledge_db/pipeline.py` `L1354` (`_prepare_search_context_and_filters` -> `_ensure_jit_index_ready` `L1144`)，當背景 Worker 正在重建索引時，前景 `kdb search` 採用非阻塞 Try-Lock 讀取既有快照或立即降級，不再無條件阻塞等待 `self._index_lock`。

#### 2.2.4 支柱四：`module:dev` 封閉式單次遍歷 13 項 AST 靜態守門管線
- 物理刪除無任何外部模組使用的 `dev/contributes/_format.json`（`L1-L18`），同步清理 `dev/contributes/_manifest.md`（`L27-L31`），並刪除 `dev/dev/checker.py` 的 `_check_custom_rules`（`L1233-L1351`）與 `dev/tests/test_checker.py` 對應測試（`L491-L540`）。
- 將 `dev/dev/checker.py` 的 `_check_source_files`（`L970-L1134`，原對每檔重複執行 3~4 次 `ast.walk`）重構為單次遍歷之 `ast.NodeVisitor` 規則管線，內建 A1~F13 共 13 項規則（其中規則 C8 明確允許 `__all__` 匯出清單與 `Final` / `MappingProxyType` / `frozenset` / `tuple` 不可變頂層定義）。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  - 全倉 168 個生產 `.py` 檔案的靜態影響半徑已 100% 量化定錨。為避免單一計畫變更過大，確定採用 **Pre-planned Umbrella 分類型主計畫**，依底層基座到上層收網之拓撲順序切分為 **`sub_01` ~ `sub_05` 共 5 個正交子計畫**。
  - 針對即將在 Tier 2（`2026_11_07_1548_ast_architecture_research`）全面重構的 `module:ast`，於 `sub_04` 僅執行薄層機械式合規遷移（替換 `core.log`、消除 3 處 `global`、常數加 `Final`/`MappingProxyType`），避免在舊版 `ast_engine` 內部投入無效深層重構工時。
- **後續建議**：
  - 待本機端完成 `2026_11_06_1020_core_file_space_architecture` 之 `sub_05` 收尾後，即可直接啟動本主計畫之 `sub_01_core_log_pipeline_and_streamer_unification`。
