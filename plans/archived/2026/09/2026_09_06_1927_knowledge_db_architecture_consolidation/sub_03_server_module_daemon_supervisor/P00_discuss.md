# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「進入下一個子計畫，這屬於新 module 開發，因此需要充分討論」
  - 「感覺方案，2 / 4 合併比較好，我目前的想法是，server 是一個特化與 yscb 入口耦合的持久化系統，對於任何 module 皆無感，皆為接收 process(cli args) 和提供 SDK，差別在於沒有 server 的話就是每次都是冷啟動，你覺得呢?」
  - 「1. 直接做成防抖，比如抓個 500ms 無串流就派送，需要做區分，因為應該會設計為 cli 派發後掛起等待迴圈，因此回傳封包要分為終端串流和 task finish 以區分資訊 (cli 端應有簡單的過濾處裡環節再接回 std terminal)」
  - 「2. 要區分兩種，兩個指向(yscb root)不同的 yscb.py 不可共用 server，而在同一 server 下，採用方案 A 主進程單隊列序列化」
  - 「3. 需要熱重載，但注意，不是 source 是 modules」
- **核心目標**：
  - **模組零感知 (Zero Module Burden)**：所有生態系模組無需實作任何專有 Worker 外掛或適配代碼，100% 複用 sub_01 確立的純函式契約 `process(args: List[str]) -> int`。
  - **yscb 宿主持久化加速中樞 (Persistent Hot Runner)**：
    - `server` 作為與 `yscb` 入口高度協同的常駐進程。
    - **熱啟動 (Hot Execution)**：當 Server 運行時，`yscb.py` 將 CLI 命令委派給 Server，在常駐預熱的進程與快取中瞬間執行，CLI 啟動延遲由 500~2000ms 降至 <30ms。
    - **冷啟動無縫降級 (Cold Fallback)**：當 Server 未運行時，`yscb.py` 自動以現有本機進程直接加載並執行 `process(args)`，任何環境與沙盒 100% 零阻礙運行。
  - **方案 2/4 融合之通訊架構**：
    - 檔案元資料 (`cache://server/daemon.json`) 記錄 PID、鎖、動態 Port 與 Token，提供 100% 穩健之生命週期與強殺安全底線。
    - 本地 HTTP (`127.0.0.1:<dynamic_port>`) 提供毫秒級雙向命令派送、參數傳遞與標準輸出串流。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁強迫各業務模組自寫適配代碼，保持「模組皆無感」原則。
  - 重構期凍結：嚴格禁止 `@build` 自部署，全面在 `source/` 與沙盒中驗證。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 新模組骨架與微內核守門遵循**：
  - 決策：建立標準模組 `source/server/`。進入點 `scripts/cli.py` 宣告純函式 `process(args: List[str]) -> int`，首行調用 `core.guard.guard_dispatch("server")`。
- **[P00:DR-02] 模組零感知與純粹 process(args) 派發模型**：
  - 決策：Server 本質為「模組通用常駐執行器 (Persistent Module Runner)」，接收標準 `(module_name, args, cwd, env)` 請求，並在預熱記憶體中呼叫該模組之 `process(args)`。
- **[P00:DR-03] yscb 雙模式派發 (Hot Dispatch with Cold Fallback)**：
  - 決策：`yscb.py` 預設嘗試熱派發至常駐 Server，若探測到 Server 未運行或連線超時，自動透明降級為本地冷啟動加載執行，使用者體驗完全一致。
- **[P00:DR-04] 方案 2/4 融合之雙軌通訊架構 (File State + Localhost HTTP RPC)**：
  - 決策：採納使用者提議之方案 2/4 融合模式。檔案元資料 (`daemon.json`) 負責 PID 鎖定、存活感知與極限強殺兜底；動態 Port 本地 HTTP (`127.0.0.1:<dynamic_port>`) 負責高速派送 `process(args)`、捕獲輸出與狀態查詢。
- **[P00:DR-05] 標準輸出與環境隔離機制 (IO Redirection & Scope)**：
  - 決策：Server 支援將被調用 `process(args)` 之 `sys.stdout`、`sys.stderr` 與退出碼精確捕獲並串流回傳給 CLI，並透過 Context Manager 隔離 `cwd` 與 `os.environ`。
- **[P00:DR-06] 模組代碼熱重載與失效感知 (Module Invalidation)**：
  - 決策：Server 支援 `reload` 指令與檔案變更感知，模組安裝變更時自動刷新記憶體快取。
- **[P00:DR-07] IO 串流協議與防抖機制 (Chunked Streaming & Debounce Flush)**：
  - 決策：
    1. **封包類型劃分**：回傳串流明確區分為 `terminal_stream`（終端即時輸出塊）與 `task_finish`（任務完成封包，帶 exit_code、耗時統計）。
    2. **防抖機制 (500ms Debounce)**：輸出端以 500ms 無串流為閥值進行即時 flush 派送，兼顧大量輸出的吞吐效能與終端互動感。
    3. **CLI 掛起循環過濾**：CLI 端發派後進入 wait loop 讀取串流，經簡易過濾處理解包後無縫接入標準終端 stdout/stderr。
- **[P00:DR-08] 專案根目錄隔離與主進程單隊列序列化 (Root Isolation & Serialized Queue)**：
  - 決策：
    1. **工作區根目錄嚴格隔離**：指向不同 `yscb root` 的 `yscb.py` 嚴禁共用同一 Server 實例。Server 的生命週期與 `daemon.json` 綁定在各專案的 `cache://server/daemon.json`，不同專案獨立啟動各自的 daemon。
    2. **主進程單隊列序列化**：在同一 Server 下，採用方案 A「主進程單隊列序列化 (Queue)」，杜絕多線程環境下 `os.chdir(cwd)`、`sys.stdout/stderr` 與環境變數競爭，保證極致穩定輕量。
- **[P00:DR-09] .modules/ 部署態變更熱重載感知 (.modules/ Watcher)**：
  - 決策：熱重載之監控目標**精確鎖定為 `.modules/` 目錄**（而非 `source/`），因常駐運行態消費的是已部署模組。當 `.modules/` 目錄內容或元資料（如安裝新版本、更新模組）發生變更時，自動觸發 `sys.modules` 失效清理或子 Worker 重載。

---

### 附錄：IPC 通訊協議候選方案分析對照

  - **方案 1：輕量狀態檔案映射 + 跨進程鎖 + 訊號檔 (File-Based IPC)**：
    - 機制：Supervisor 透過 `core.vfs.write_json(atomic=True)` 維護 `cache://server/daemon.json`（含 PID、時間戳、Worker 清單）；控制命令透過 OS 訊號或指令標記檔遞交。
    - **CLI 派送接收流程**：
      1. 狀態查詢 (`server status`)：CLI 直接讀 `daemon.json`，Server 端完全無需被喚醒。
      2. 控制指令 (`server stop/restart`)：CLI 寫入 `cache://server/cmd.pending.json`；Server 背景迴圈定時（約 100~200ms）輪詢或透過檔案變更事件捕捉，執行完成後寫入 `cmd.reply.json`；CLI 輪詢等待該 reply 檔呈現結果。
    - 優點：零連接埠衝突、零防火牆彈窗、100% 容器與沙盒相容、狀態肉眼可見 (`cat daemon.json`)。
    - 缺點：非即時雙向串流，命令下發存在微小輪詢間隔 (0.1~0.5s)，不適合高頻密集傳輸大數據。
  - **方案 2：本地回環輕量 HTTP / REST 服務 (Localhost HTTP)**：
    - 機制：Supervisor 啟動標準庫 `http.server.ThreadingHTTPServer` 監聽 `127.0.0.1:<port>`（隨機動態分配 port），並將 port 與隨機 auth token 寫入 `daemon.json`。
    - **CLI 派送接收流程**：
      1. CLI 讀取 `daemon.json` 取得 `port` 與 `token`。
      2. CLI 使用 `urllib.request` 發送 HTTP POST（帶 Token Header）至 `http://127.0.0.1:<port>/api/cmd`，攜帶 JSON 負載。
      3. Server 監聽線程接收 TCP 請求，驗證 Token 後執行 Supervisor 動作，並以 HTTP 200 JSON 即時返回執行結果（延遲 < 5ms）。
    - 優點：延遲極低 (<5ms)、即時雙向 JSON RPC、天然易擴展（未來支援 Web UI / IDE 外掛）。
    - 缺點：需管理連接埠（動態 port 避免衝突）、需附加本地 Token 防禦、部分 Windows 環境可能觸發防火牆提醒。
  - **方案 3：本機原生 IPC (Unix Domain Socket / Windows Named Pipe)**：
    - 機制：POSIX 使用 `AF_UNIX` socket 檔案，Windows 使用 Named Pipe。
    - **CLI 派送接收流程**：CLI 連接本機 socket/pipe 串流，發送長度頭 + JSON Frame；Server 透過 select/selectors 事件循環讀取並回覆。
    - 優點：延遲極致、無連接埠衝突與防火牆警示。
    - 缺點：跨平台代碼複雜度高，Windows 與 POSIX 事件循環差異顯著，維護成本較高。
  - **方案 4：混合架構 (Hybrid: 檔案元資料 + 動態 Port 本地 HTTP)**：
    - 機制：基礎生命週期（PID 鎖、存活探測、強殺）走檔案映射；進階即時指令與查詢走動態分配之 `127.0.0.1:<dynamic_port>`。
    - **CLI 派送接收流程**：
      1. 唯讀狀態查詢：直接讀 `daemon.json`，零網絡延遲。
      2. 業務控制指令：走 Localhost HTTP POST，毫秒級雙向反饋。
      3. 故障強制停止：HTTP 若超時無響應，CLI 自動依賴 `daemon.json` 紀錄之 PID 直接調用 `kill_process_tree` 強制收割進程樹，安全回退。
    - 優點：兼具方案 1 的零衝突穩定性與方案 2 的即時 RPC 擴充性，兼具強大容災兜底能力。

- **[P00:DR-10] core.platform 底層先行落地原則**：
  - 決策：先於 `source/core/core/platform/` 實裝跨平台原語：`process.py` (`spawn_detached`, `is_process_alive`, `kill_process_tree`) 與 `lock.py` (`InterProcessLock`，基於 POSIX `flock` 與 Windows `msvcrt.locking`)。單元測試覆蓋通過後，再由 `server` 模組引用。
- **[P00:DR-11] 進程架構採方案 C (Master Supervisor + 常駐單一預熱 Worker)**：
  - 決策：Master 負責 HTTP 監聽、Token 防禦、單隊列調度與 Worker 生命週期監控；常駐 1 個預熱 Worker 子進程負責執行目標模組 `process(args)`。兼顧 <30ms 極速熱派發與 100% 模組記憶體隔離。
- **[P00:DR-12] 按需自動拉起 (Auto-Spawn) 與 15 分鐘空閒自毀 (Idle TTL)**：
  - 決策：
    1. 啟動拉起：`config.local.json` 添加開關，預設開啟「按需自動拉起」。
    2. 生命週期：`config.local.json` 添加開關，預設開啟「15 分鐘空閒自毀 (Idle Timeout)」，超時自動退出釋放記憶體。
- **[P00:DR-13] 模組熱重載採選項 1 (直接重啟子 Worker)**：
  - 決策：監控 `.modules/` 變動。一旦檢測到安裝/升級變動，Master 直接終止舊 Worker 並重啟全新 Worker，100% 排除 Python `importlib.reload` 帶來的 stale references 與型態不匹配幽靈 Bug。
- **[P00:DR-14] 按需延遲加載 (Lazy Load on Dispatch) 與運行期沙盒化**：
  - 決策：Worker 啟動時不預載入任何領域模組；派發時動態加載目標模組。派發 A 模組絕不加載 B 模組，零連鎖依賴污染。Worker 攔截 `SystemExit` 轉為返回碼，防護進程不崩。
- **[P00:DR-15] yscb 宿主與 Server 模組耦合邊界四大原則**：
  - 決策：
    1. **軟依賴探測**：`yscb.py` 零靜態 import server，探測無效即 100% 透明冷啟動降級。
    2. **自循環旁路**：`module == "server"` 之管理指令強制直接走本地冷啟動，嚴禁熱派發循環。
    3. **非同步拉起**：按需拉起 Master 採背景非同步脫鉤運行，當前指令走冷啟動執行，首發零等待感。
- **[P00:DR-16] 預熱生命週期事件廣播 (Warm-up Events via core.events)**：
  - 決策：Worker 在預熱開始與就緒時，透過 `core.events` 分別廣播 `server:worker:warming` 與 `server:worker:ready`（攜帶 worker_pid、耗時等 metadata），Master 的 HTTP `/api/status` 端點亦同步反饋進程 state (`warming`/`ready`/`reloading`)。
- **[P00:DR-17] 業務 Service Worker (如 Watchdog) 統一生命週期治理**：
  - 決策：各領域模組若有背景監聽需求（如 `knowledge-db` 的檔案監聽 Watchdog），以註冊式 Service Worker 形式受 Master 託管，且**生命週期 100% 綁定並跟隨 Server 配置**：
    1. 若 Server 開啟 15 分鐘空閒自毀 (Idle TTL)，Service Worker 隨同 Server 在 15 分鐘空閒後一同自毀退出。
    2. 若 Server 配置為常駐無自毀 (disable TTL)，Service Worker 也隨同常駐持續運行。
    3. 當執行 `server stop` 時，所有 Service Worker 隨同一併優雅關閉，確保無指令期間系統資源治理行為完全一致且可預測。


---

## 3. 開放議題與確認紀錄

- [x] **議題 1 (IPC 通訊選型)**：採納方案 2/4 融合（檔案元資料 PID 鎖 + 動態 Port 本地 HTTP）。
- [x] **議題 2 (並發與隔離模式)**：按專案工作區嚴格隔離 Server 實例；採方案 C (Master + 常駐單一預熱 Worker)。
- [x] **議題 3 (IO 串流與熱重載機制)**：採納 500ms 防抖串流（終端串流塊 + task finish 分流）；熱重載精確監控 `.modules/` 變更並直接重啟子 Worker。
- [x] **議題 4 (core.platform 底層先行)**：於 `core.platform` 實作進程脫鉤、進程樹強殺與跨進程鎖。
- [x] **議題 5 (yscb 與 server 耦合邊界)**：落實軟依賴探測、自循環旁路、非同步拉起與極簡客戶端四大原則。
- [x] **議題 6 (模組加載策略)**：採按需延遲加載 (Lazy Load on Dispatch)，調用 A 絕不加載 B。
- [x] **議題 7 (預熱階段 Event)**：Worker 預熱過程發布 `server:worker:warming` 與 `server:worker:ready` 事件。
- [x] **議題 8 (Watchdog 類常駐服務治理)**：統一納入 Service Worker 託管，生命週期跟隨 Server 共享 15 分鐘 TTL，不永久長駐。


