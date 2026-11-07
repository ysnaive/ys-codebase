# 技術路線圖：Jupyter 式執行期核心隔離、常駐雙通道、統一 core.log 管線與靜態守門架構 (Roadmap)

> 主題：Jupyter 式執行期核心隔離、常駐雙通道、統一 core.log 管線與靜態守門架構 (`jupyter_style_runtime_isolation_and_static_guardrails`)  
> 歸檔日期：2026-11-07  
> 狀態：Ready  
> 目標範疇：`core`、`server`、`dev`、`knowledge-db` 及全生態系模組（執行期狀態容器、`core.log` 雙族系受管輸出與增量滾動日誌、常駐進程三平面解耦、受管獨立 Worker 執行緒與 KDB 向量模型離線降級守門、模組命名空間載入與 `dev` 封閉式 13 項 AST 靜態守門）  
> 前置解鎖條件：完成 `2026_11_06_1020_core_file_space_architecture` 收尾階段後優先啟動（Tier 1 首要基座），並作為推進 `module:ast` 正交化重構（`2026_11_07_1548_ast_architecture_research`）與 `module:knowledge-db` 文檔管線之乾淨基座  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **四大執行平面共用進程級全域狀態引發交叉污染**：同一套模組業務代碼需同時運行於「本地單次冷派發（Cold Dispatch）」、「常駐熱派發主執行緒（Warm Dispatch Main Thread）」、「常駐背景服務執行緒（Background Service Workers）」與「同進程多沙盒測試（Multi-Sandbox Testing）」四種執行平面。由於 Python 預設之工作目錄、環境變數、標準輸出入串流、模組搜尋路徑與模組頂層變數皆屬進程級全域共享（Process-Global），當前景熱派發與背景服務併發執行、或跨回合切換工作區實例時，極易發生工作目錄突變、輸出串流串音、模組命名空間遮蔽與過期快取殘留。
  - **未受管之原生輸出（`print` / `sys.stdout` / `logging`）與分裂的四套日誌機制**：各模組混用原生 `print()`、`sys.stderr.write()`、標準庫 `logging`、私有 `ServerLogger` 與 `telemetry.py`，迫使常駐進程在每次熱派發時插拔替換全域 `sys.stdout` / `sys.stderr`，導致背景 `ServiceWorker` 日誌串音混入前景 CLI 輸出，且檔案滾動視窗與增量讀取邏輯於多處重複造輪子。
  - **野執行緒失控、背景鎖競爭與 KDB 隱式網路下載阻塞常駐進程**：
    1. 部分模組透過 `hook.server.py` 私自啟動不受 `ServiceManager` 納管之野執行緒（Raw `threading.Thread`），在停機或模組卸載時無法統一回收並釋放 Windows 檔案句柄。
    2. `knowledge-db` 在初始化 `TextEmbedding` 時，若本地 `cache/kdb/models` 尚無 ONNX 模型且處於無外網環境（如受限沙盒或離線開發機），底層 `huggingface_hub` 會陷入長時間網路重試甚至無限阻塞；同時背景 `KnowledgeDBServiceWorker` 執行掃描建模並持有阻塞鎖時，前景 CLI 熱派發進場爭搶同一把鎖即會被連帶拖下水，鎖死整個常駐 `WarmWorker`。
  - **動態語言寬容性缺乏封閉且獨立之編譯期邊界約束**：Python 語法允許隨意宣告可變預設參數（`def f(x=[])`）、類別頂層共享可變屬性、模組頂層可變字典與 `global` 改寫、原地竄改快取回傳引用及動態洗牌 `sys.path`；同時，負責全倉合規審查的裁判模組（`module:dev`）若開放外部擴充點（如 `custom_checks`）在檢查期間動態載入受審模組代碼，不僅破壞裁判獨立性，更增加執行期污染風險。
- **長期願景與目標定位**：
  - 借鑑 **Jupyter Kernel（`ipykernel` + `InteractiveShell` + `%autoreload` + 多通道協議）** 之成熟常駐執行期架構，結合**統一 `core.log` 雙族系管線（`log*` 調用者終端輸出 vs. `logFile*` 增量滾動檔案紀錄）**、**`BaseServiceWorker` 原生受管獨立執行緒模型（含 KDB 離線模型守門與非阻塞降級）** 與 **`module:dev` 封閉式編譯器級 13 項 AST 靜態守門（Standalone Closed-Loop Static Guardrails）**，將 `ys-codebase` 升級為具備確定性隔離保證的微內核執行環境：
    1. **空間維度（併發執行緒與輸出通道隔離）**：全面封殺未受管之原生 `print` / `sys.stdout`、`input` / `sys.stdin` 與私自建立之野執行緒；所有終端輸出透過 `core.log` 之 `log*` 族系依當前 `ExecutionContext` 精準投遞予調用端；所有持久化紀錄透過 `logFile*` 族系以可配置滾動視窗增量寫入目標檔案；每個背景 `ServiceWorker` 由基底類別統一配發專屬之受管獨立執行緒（Managed Worker Thread）與非阻塞狀態機，使前景執行、控制查詢與背景服務三平面徹底解耦。
    2. **時間維度（跨回合與多實例隔離）**：消滅模組頂層無主可變全域快取與 `global` 關鍵字，所有運行時狀態收斂於綁定工作區實例與檔案世代號（Generation / `mtime`）之容器內，並以唯讀視圖對外暴露。
    3. **編譯期維度（`dev check` 封閉式靜態守門）**：`module:dev` 作為全倉獨立裁判，不設任何對外擴充點（拔除無實際外部使用者之 `custom_checks`），在 `dev` 內部建立純靜態、零動態代碼載入的 AST 規則管線，於開發與測試階段自動攔截 6 大類共 13 項危險語法與隱性狀態操作。
- **已整併吸收之原獨立路線圖與待辦事項**：
  - **正式整併吸收原 `kdb_vector_model_offline_guard_and_nonblocking_worker.md`**：將 KDB 向量模型離線預檢（`has_local_model()`）、顯式模型下載 CLI（`yscb kdb model download`）與 `KnowledgeDBServiceWorker` 非阻塞讀寫分離完整納入本路線圖之支柱二。
  - **系統性收編 `TODO-02` 與 `TODO-21`**：透過 `RuntimeContext` 顯式上下文容器與統一派發前置生命週期，一併根治業務模組內部隱式 URI 解析（`TODO-02`）與事件廣播/CLI 前置自檢不一致問題（`TODO-21`）。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **禁止未受管原生輸出入流不變量（No Unmanaged OStream / Stdin）**：除 `core.log` 底層實作外，全倉業務模組與腳本嚴禁直接呼叫原生 `print()`、`sys.stdout.*`、`sys.stderr.*`、`logging.*` 或讀取 `input()` / `sys.stdin.*`（防止搶奪常駐 Worker 之 IPC 管道）；一切向調用者之輸出必須走 `log*` 族系，一切向檔案之持久化日誌必須走 `logFile*` 族系。
  - **零模組頂層可變狀態與零 `global` 不變量（Zero Module-Level Mutable State & No `global`）**：全倉所有業務模組頂層僅允許宣告不可變常數（`Final`）與型別定義；嚴禁於模組頂層放置無主可變容器、嚴禁使用 `global` 關鍵字、嚴禁宣告可變預設參數或未封裝之類別頂層可變容器屬性，所有快取與狀態必須封裝於顯式之 `RuntimeContext` 實例中。
  - **禁止進程級環境突變與自殺呼叫不變量（No Process-Wide Ambient Mutation or Exit）**：在業務模組與常駐進程中，嚴禁呼叫 `sys.exit()` / `os._exit()`、嚴禁呼叫 `os.chdir()` / `os.getcwd()` / `Path.cwd()`、嚴禁原地改寫 `os.environ` 或私自註冊 `signal.signal()`；所有請求級環境參數一律透過 `contextvars.ContextVar` 進行執行緒與協程安全之作用域綁定。
  - **零拷貝唯讀跨邊界傳遞不變量（Zero-Copy Read-Only Boundary）**：跨模組契約與快取查詢回傳值一律採用 `@dataclass(frozen=True, slots=True)`、`tuple`、`frozenset` 或 `types.MappingProxyType` 唯讀字典視圖，從執行期根絕呼叫端原地竄改快取（Mutable Aliasing）之風險，同時免除防禦性 `copy.deepcopy()` 的效能開銷。
  - **受管獨立 Worker 執行緒、非阻塞協作與離線安全不變量（Managed Worker Thread, Non-Blocking Cooperation & Offline Safety）**：業務模組嚴禁私自呼叫 `threading.Thread().start()` 建立無牌野執行緒；所有常駐背景工作統一繼承 `BaseServiceWorker`，由 `ServiceManager` 自動為每個 Worker 配發一條專屬獨立執行緒、綁定獨立背景 `ContextVar` 與統一 `stop_event` 回收機制；任何查詢、狀態巡檢與背景 Worker 預設禁止觸發隱式網路模型下載（離線無模型時必須秒級優雅降級），且前景熱派發查詢背景資源時一律採非阻塞狀態檢視（Try-Lock / 狀態機降級），絕不阻塞等待背景長耗時任務。
  - **裁判模組封閉獨立不變量（Referee Independence & Zero External Hooks in `dev`）**：`module:dev` 作為全專案合規與品質裁判，嚴禁暴露對外擴充點（不提供 `contributes/_format.json` 之 `custom_checks`），且靜態檢查全程僅讀取原始檔與解析 AST，絕不在檢查期間動態 `import` 或執行受審模組代碼。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **支柱一：統一 `core.log` 雙族系管線（`log*` 調用者終端輸出 vs. `logFile*` 增量滾動檔案紀錄）**
    1. **`log*` 族系（強定義指向「調用者終端 Caller Stream」）**：
       - 提供 `log()`（標準結果輸出）與分級診斷輸出 `log_info()`、`log_warn()`、`log_error()`、`log_debug()`。
       - 依當前 `ContextVar` 綁定之 `ExecutionContext` 自動投遞：於本地冷派發時寫入實體終端；於常駐熱派發時直接寫入該請求專屬之防抖 IPC 回傳通道（無須劫持全域 `sys.stdout`，100% 物理消除背景串音）；若於無前景調用者之背景 `ServiceWorker` 執行緒中觸發，自動轉寫入預設背景日誌檔。
       - 自動感知當前請求之 `--verbose` / `--debug` 旗標，並於呼叫 `log_error()` 時自動將結構化錯誤摘要登記至當次請求之 `error_hint`（免除事後以字串猜測錯誤原因）。
    2. **`logFile*` 族系（強定義指向「任意目標檔案之增量滾動紀錄 Incremental Rolling File Sink」）**：
       - 提供 `log_file()`（格式化文字行追加）、`log_file_jsonl()`（結構化單行 JSON 追加）與 `read_log_file_tail()`（基於 `(byte_offset, inode)` 之增量尾端讀取，自動感知截斷與輪替並歸零重讀）。
       - 支援針對任意語意 URI（如 `cache://server/log`、`cache://core/telemetry.jsonl`）或 `Path` 配置三大滾動視窗策略（Rolling Policy）：① **按筆數與大小截斷視窗（`keep_lines` + `max_bytes`）**、② **按歷史檔案世代輪替（`max_backups` + 啟動時 Crash 遺留檔自動歸檔）**、③ **即時 Flush 與句柄非繼承保護（`os.set_inheritable(fd, False)` 防範 Windows 子進程鎖死檔案）**，統一收編既有 `ServerLogger` 與 `telemetry.py`。
  - **支柱二：借鑑 Jupyter Messaging Protocol 之「執行 / 控制 / 受管獨立 Worker 執行緒」三平面解耦與 KDB 離線守門**
    1. **Control Channel 與 Shell Execution Channel 分離**：Supervisor 將狀態查詢（`status`）、心跳探針（`touch` / `health`）與優雅停機（`stop` / `release_handles`）路由至獨立之非阻塞控制通道，不與長耗時 CLI 執行任務爭搶同一把派發鎖。
    2. **`BaseServiceWorker` 原生配發「一 Worker 一獨立受管執行緒」與非阻塞狀態機**：
       - 廢除 `hook.server.py` 私開野執行緒之雙軌模式；凡有後台監聽、下載或增量更新需求之模組（如 `knowledge-db`、`gdrive-support`、`core-space-watcher`），統一繼承 `BaseServiceWorker`。
       - `ServiceManager` 啟動時自動為每個註冊之 `ServiceWorker` 實例建立專屬獨立之受管 `threading.Thread`（自動綁定背景日誌 `ContextVar` 與 `stop_event` 優雅停機信號）。
       - 內建非阻塞資源狀態協作（`STARTING` / `UPDATING` / `READY` / `DEGRADED_OFFLINE`）：當背景 Worker 執行緒正在下載模型或重建索引時，前景 Main Thread 透過非阻塞 Try-Lock 立即得知狀態並執行優雅降級（如退回關鍵字檢索或秒級回報進度），徹底根除前景執行緒被背景任務阻塞死鎖之風險。
    3. **`knowledge-db` 向量模型離線預檢守門與顯式下載 CLI 解耦（整併自原 KDB 獨立路線圖）**：
       - **本地模型完整性預檢（`has_local_model()`）**：於呼叫 `TextEmbedding` 實例化前，強制先檢驗 `cache://kdb/models` 下目標 ONNX 模型快照檔案是否已完整存在；若不存在且未傳入 `allow_download=True`，立即在 `< 1ms` 內拋出預期內之離線降級信號並將狀態標記為 `DEGRADED_OFFLINE`（自動退回純關鍵字檢索或跳過向量嵌入），嚴禁隱式發起 HuggingFace 網路請求。
       - **顯式下載指令解耦**：新增專屬 `yscb kdb model download`（或 `kdb init --download-model`）指令，將唯一允許連網拉取向量模型權重的入口收斂至使用者顯式觸發之獨立生命周期。
    4. **虛擬工作目錄與環境上下文**：透過 `ContextVar` 維護當前請求之邏輯工作目錄（`virtual_cwd`）與環境變數覆寫表，`core.uri` 與 `core.vfs` 優先讀取當前上下文之 `virtual_cwd`，徹底拔除熱派發中之 `os.chdir()`。
  - **支柱三：借鑑 `InteractiveShell` 與 `%autoreload` 之實例容器及世代感知熱重載**
    1. **`RuntimeContext` 實例化狀態容器**：將 URI 映射、Contributes 聚合結果、Config 組態與語言規範集中納管於以 `yscb_root` 為基準的 `RuntimeContext` 實例內；支援在同進程內同時實例化多個互不干擾的沙盒 Context。
    2. **固定模組命名空間與 `(mtime_ns, size)` 自動熱刷新**：廢除每次派發重排 `sys.path[:]` 的做法，所有動態模組與腳本統一透過受保護之命名空間（如 `_yscb_ext.<module>.*`）原子載入（失敗自動回滾 `sys.modules`），並於每次派發前（`pre_cli_dispatch`）自動比對檔案 `(mtime_ns, size)` 世代指紋，實現零殘留熱更新。
  - **支柱四：`module:dev` 封閉式單次遍歷 13 項 AST 靜態守門管線（Closed-Loop AST Checker Pipeline）**
    - 移除 `dev/contributes/_format.json` 及 `_check_custom_rules` 動態載入邏輯，於 `dev` 內部以純靜態單次 AST 遍歷（Single-Pass AST Rule Visitors）內建 **6 大類共 13 項強制守門規則（違規即判定 `FAIL`）**：
      - **【類別 A：輸出入串流劫持與阻塞防禦】**
        1. **禁止未受管之原生輸出語法**：攔截 `core.log` 以外之 `print(...)`、`sys.stdout.*`、`sys.stderr.*`、`sys.__stdout__`、`sys.__stderr__` 與未授權 `logging.*` 呼叫。
        2. **禁止讀取標準輸入管道**：攔截 `input(...)` 與 `sys.stdin.*` 讀取操作（僅豁免 `server/worker.py` 主 IPC 迴圈，防止誤食常駐 Worker IPC 指令流）。
      - **【類別 B：進程級環境突變與生命週期防禦】**
        3. **禁止非啟動器呼叫進程終止**：攔截 `sys.exit()`、`os._exit()`、`exit()`、`quit()`（僅豁免頂層 `yscb.py` 入口，防止殺死常駐 `WarmWorker`）。
        4. **禁止進程級工作目錄突變與隱式依賴**：攔截 `os.chdir()`、`os.getcwd()` 與 `Path.cwd()`（強制透過 `RuntimeContext` / `core.uri` 解析邏輯工作目錄）。
        5. **禁止執行期原地竄改 `os.environ`**：攔截 `os.environ[...] = ...`、`os.environ.update/pop/clear` 與 `os.putenv()`（強制走 `ExecutionContext.env`，僅豁免啟動器與測試沙盒專用 Fixture）。
        6. **禁止私自搶奪信號處理器**：攔截 `signal.signal()`（僅豁免 `server/master.py` 主守護進程）。
      - **【類別 C：Python 語法級隱性共享狀態防禦】**
        7. **禁止可變預設參數（Mutable Default Arguments）**：攔截函式定義 `defaults` / `kw_defaults` 中包含 `list`、`dict`、`set` 字面量或可變容器建構呼叫（如 `def fn(a=[], b={}):`）。
        8. **禁止模組頂層可變容器與 `global` 關鍵字**：攔截模組頂層非 `Final` 常數之可變容器賦值（如 `_CACHE = {}`）及任何函式內的 `global` 敘述。
        9. **禁止類別頂層未封裝之共享可變屬性**：攔截一般類別本體（Class Body）中直接賦值 `list` / `dict` / `set`（未使用 `@dataclass(frozen=True)` + `field(default_factory=...)`）之隱式 `static` 共享容器。
      - **【類別 D：模組載入與動態執行防禦】**
        10. **禁止直接操作 `sys.path`、`sys.modules`、`sys.argv` 與 `importlib.reload()`**：僅豁免 `core` 單點命名空間載入器與派發入口。
        11. **禁止動態字串代碼執行**：攔截 `eval()`、`exec()` 與 `__import__()`（動態載入統一走 `core.symbols.resolve_callable`）。
      - **【類別 E：跨平台檔案系統與唯讀契約防禦】**
        12. **禁止呼叫非原子覆寫之 `os.rename()`（及強制唯讀跨模組契約）**：攔截 `os.rename()`（Windows 下目標存在時必拋 `FileExistsError`，強制改用 `os.replace()` 或 `core.vfs`），並檢核跨模組公開資料契約採用 `@dataclass(frozen=True)` / `MappingProxyType`。
      - **【類別 F：無限阻塞與未受管野執行緒防禦】**
        13. **禁止缺少 `timeout=` 或帶 `shell=True` 之外部呼叫與私開無牌野執行緒**：攔截未顯式傳入 `timeout=`（或傳入 `shell=True`）之 `subprocess.run/check_output/communicate` 與 `urllib.request.urlopen`；攔截業務模組私自呼叫 `threading.Thread`（僅豁免 `server/service.py` 受管 Worker 執行緒配發器與 `core` 基礎設施）。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 待 `2026_11_06_1020_core_file_space_architecture` 完成 `sub_04` 全倉遷移收尾後即可作為 **Tier 1 首要工程**立項啟動，並排在 `module:ast` 正交化重構（`2026_11_07_1548_ast_architecture_research`）動工之前完成。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`core.log` 雙族系管線、`RuntimeContext` 實例容器、唯讀視圖與命名空間載入器）**：於 `core` 建立 `core.log`（含 `log*` 調用者終端輸出與 `logFile*` 可配置滾動視窗增量檔案紀錄，收編 `telemetry.py` 與 `ServerLogger`）、`RuntimeContext` 與 `ContextVar` 虛擬環境機制，並固化單點命名空間模組載入器。
  2. **Stage 2（`server` Jupyter 式三平面解耦、`BaseServiceWorker` 受管獨立執行緒與 KDB 離線非阻塞守門）**：重構 `WarmWorker`、`MasterSupervisor` 與 `ServiceManager`，由 `BaseServiceWorker` 原生配發受管獨立執行緒與非阻塞資源狀態機（收編並拔除 `hook.server.py` 私開野執行緒），實作 `knowledge-db` 本地模型離線預檢（`has_local_model()`）與顯式 `kdb model download` CLI 解耦，對接 `core.log` 達成零串音終端回傳與背景日誌分離，並移除熱派發 `os.chdir()`。
  3. **Stage 3（全倉既有模組遷移與 `dev` 封閉式 13 項 AST 靜態守門管線收斂）**：移除 `dev` 對外 `custom_checks` 擴充點，將 `dev/checker.py` 內部模組化為單次遍歷之純靜態規則管線，完成全倉既有模組對齊遷移並正式啟用 13 項 AST 靜態守門規則。
