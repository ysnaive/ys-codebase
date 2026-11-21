# 專題調研與正交驗證基準：運行期功能域（`execution/`）正交因子、真實入口聚合與最小完備案例集 (`R01`)

> **所屬專案與工作區**：`YS-Codebase 2.0 (./core_v2/)`
> **目標功能域**：`Domain 5 — 執行與常駐調度域 (core.execution.{event, lifecycle, rpc, runtime, daemon})`
> **關聯設計文件**：[`ROADMAP.md`](./ROADMAP.md)、[`sub_module_design/execution/`](./sub_module_design/execution/)
> **狀態**：`Active Verification Benchmark (Living Document)`
> **最後更新**：`2026-11-21`

## 1. 調研動機與方法論 (Motivation & Orthogonal Methodology)

若僅從既有架構規格書已宣告的欄位反推使用案例，極易陷入「只測試已想到情境」的自證盲區。本報告針對 `Core 2.0` 最核心的動態引擎——**運行期功能域（`execution/`）**，採取三階段正交工程方法論：

1. **第一性原理正交因子拆解**：跳脫既有 API 欄位，從作業系統進程、Python 執行模型、通訊邊界與圖論拓撲出發，拆解出彼此概念獨立的 **5 大構面、23 個正交因子（共 77 個離散水準）**。
2. **全倉真實業務入口聚合**：盤點 `YS-Codebase` 全部 8 大既有模組的真實 CLI 指令、SDK 長連線、跨任務調用、`hook.*.py` 事件與 `server.json` 背景服務，映射為 **5 大入口通道、25 個真實業務原型**。
3. **遺漏根因統籌與正交集合覆蓋壓縮（Orthogonal Set-Cover）**：交叉比對抓出 **4 大系統性盲區（共 13 項邊界漏點）** 回補規格，並將全空間無損壓縮至數學理論下界的 **8 個最小完備端到端基準案例（`RC-01` ～ `RC-08`）**，以最少案例達成 100% 正交因子覆蓋。

## 2. 運行期 Domain 完整正交因子矩陣 (5 Facets × 23 Orthogonal Factors)

任何一次運行期行為皆可唯一表示為以下五大構面的正交座標向量 $(A_1..A_9, B_1..B_7, C_1..C_3, D_1..D_4, E_1..E_2)$：

### 2.1 構面 A：任務靜態本質軸（9 個正交因子）

| 因子代號與名稱 | 獨立正交維度說明 | 離散水準值（Levels） |
| :--- | :--- | :--- |
| **A1. 暴露邊界 (`Exposure`)** | 決定誰有權直接點名發起此任務 | `CLI_AND_SDK` ｜ `SDK_ONLY` ｜ `INTERNAL_TRIGGER` |
| **A2. 宿主親和性 (`HostAffinity`)** | 決定允許承載此任務的生命週期容器 | `HYBRID` ｜ `COLD_ONLY` ｜ `DAEMON_ONLY` |
| **A3. 環境隔離層級 (`IsolationTier`)** | 決定 Python 解譯器、`sys.path` 與 `.pyd` 邊界 | `TIER_0_INPROC` ｜ `TIER_1_DEDICATED` ｜ `TIER_1_SHARED_GROUP` |
| **A4. 模組狀態駐留性 (`Statefulness`)** | 決定跨 Turn 記憶體與系統句柄生命週期（與 Tier 0/1 正交） | `STATELESS` ｜ `LAZY_HANDLE` ｜ `EAGER_WARM_SINGLETON` |
| **A5. 資源並發策略 (`ConcurrencyMode`)** | 決定同一 `resource_key` 競爭時的排程規則 | `PARALLEL` ｜ `SERIALIZE` ｜ `COALESCE` ｜ `PREEMPT` |
| **A6. 單步阻塞與可中斷性 (`Interruptibility`)** | 決定執行途中收到取消/搶占/逾時信號時能否即時停下 | `COOPERATIVE` ｜ `OPAQUE_NATIVE_OR_IO` ｜ `SPAWNS_OS_SUBPROC` |
| **A7. 業務副作用冪等性 (`SideEffectIdempotency`)** | 決定斷線結果未知時能否安全自動重跑 | `PURE_READ` ｜ `IDEMPOTENT_LOCAL_WRITE` ｜ `NON_IDEMPOTENT_EXTERNAL` |
| **A8. 運行底座自變異範圍 (`SelfMutationScope`)** | 決定執行是否改動已載入模組代碼、`.venv` 或內核本體 | `NONE` ｜ `MUTATES_MODULES` ｜ `MUTATES_CORE` |
| **A9. 安全授權等級 (`SecurityTier`)** | 決定進入流水線前是否需顯式破壞性授權確認 | `SAFE` ｜ `CONDITIONAL` ｜ `GATED` |

### 2.2 構面 B：觸發源與呼叫端上下文軸（7 個正交因子）

| 因子代號與名稱 | 獨立正交維度說明 | 離散水準值（Levels） |
| :--- | :--- | :--- |
| **B1. 觸發源與呼叫位置 (`TriggerOrigin`)** | 決定本次呼叫由哪種入口啟動 | `CLI_ONESHOT` ｜ `SDK_PERSISTENT_CLIENT` ｜ `NESTED_INVOKE_TASK` ｜ `EVENT_SUB_DEFERRED` ｜ `EVENT_SUB_IMMEDIATE` ｜ `DAEMON_FS_WATCHER` ｜ `DAEMON_PERIODIC` |
| **B2. 呼叫端路由策略 (`ClientRoutingPolicy`)** | 決定呼叫端對常駐 Daemon 的連線與拉起偏好 | `AUTO_SPAWN` ｜ `AUTO_NO_SPAWN` ｜ `FORCE_COLD` ｜ `STRICT_HOT` |
| **B3. 執行優先級身分 (`ExecutionPriority`)** | 決定搶鎖優先級繼承權與是否續命業務 Idle TTL | `FOREGROUND` ｜ `BACKGROUND` |
| **B4. 目標工作區範疇 (`WorkspaceScope`)** | 決定目標落在當前宿主倉或跨入獨立子工作區 | `SAME_WORKSPACE` ｜ `ISOLATED_CHILD_WORKSPACE` |
| **B5. 呼叫端現場耦合度 (`CallerEnvCoupling`)** | 決定任務是否依賴呼叫端當下子目錄或暫態環境變數 | `WORKSPACE_ROOT_ONLY` ｜ `CALLER_CWD_SENSITIVE` ｜ `CALLER_ENV_SENSITIVE` |
| **B6. 通訊串流與負載型態 (`IoStreamMode`)** | 決定跨越進程/RPC 邊界的資料交換形態 | `UNARY_STRUCTURED` ｜ `PROGRESS_STREAMING` ｜ `INTERACTIVE_TTY` ｜ `LARGE_PAYLOAD_BOUNDARY` |
| **B7. 併發抵達拓撲 (`ArrivalMultiplicity`)** | 決定同一瞬間進站請求的併發交錯方式 | `ISOLATED_SINGLE` ｜ `MULTI_STREAM_SAME_CONN` ｜ `MULTI_PROC_BURST` |

### 2.3 構面 C：抵達瞬間之系統與資源現場軸（3 個正交因子）

| 因子代號與名稱 | 獨立正交維度說明 | 離散水準值（Levels） |
| :--- | :--- | :--- |
| **C1. 常駐 Daemon 瞬間狀態 (`DaemonArrivalState`)** | 決定主控守護進程在請求抵達當下的狀態相位 | `OFFLINE_CLEAN` ｜ `OFFLINE_STALE_JSON` ｜ `BOOTING_WARMING` ｜ `READY` ｜ `QUIESCED` ｜ `DRAINING_STOP_OR_TTL` ｜ `DRAINING_CORE_HANDOFF` ｜ `OS_SANDBOX_RESTRICTED` |
| **C2. 目標鎖瞬間競爭態 (`ResourceContentionState`)** | 決定目標資源鎖或部署鎖當下被誰持有（含同呼叫棧重入） | `FREE` ｜ `HELD_BY_INMEM_FG` ｜ `HELD_BY_INMEM_BG` ｜ `HELD_BY_EXT_COLD_PROC` ｜ `HELD_BY_INSTALLER` ｜ `HELD_BY_SAME_CALLSTACK` |
| **C3. 常駐快取與磁碟新鮮度 (`WarmStateFreshness`)** | 決定常駐記憶體載入狀態與磁碟真實檔案是否存在時間差 | `COLD_UNLOADED` ｜ `WARM_IN_SYNC` ｜ `DISK_CONFIG_EDITED` ｜ `DISK_CODE_OR_PROTO_UPDATED` |

### 2.4 構面 D：Turn 內部呼叫與事件擴散拓撲軸（4 個正交因子）

| 因子代號與名稱 | 獨立正交維度說明 | 離散水準值（Levels） |
| :--- | :--- | :--- |
| **D1. 呼叫圖與因果圖拓撲 (`CallAndCausalGraph`)** | 決定單一 Turn 內跨任務呼叫與事件傳遞的圖結構 | `SINGLE_STEP_LEAF` ｜ `LINEAR_REENTRANT_CHAIN` ｜ `FANOUT_DIAMOND_DAG` ｜ `SIBLING_MULTI_EMIT` ｜ `TRUE_CYCLE` |
| **D2. 事件發射原語模式 (`EventEmissionMode`)** | 決定事件為單步成功後延遲雙緩衝或當場同步插入 | `NONE` ｜ `DEFERRED_OUTBOX` ｜ `IMMEDIATE_SYNC` ｜ `MIXED_BOTH` |
| **D3. 事件批次順序語意 (`EventOrderingMode`)** | 決定同輪累積多顆同 `EventId` 事件時的折疊或保序行為 | `N_A` ｜ `UNORDERED_FOLD` ｜ `ORDERED_FIFO` |
| **D4. 訂閱過濾階段 (`SubscriptionFilterStage`)** | 決定不相關事件在哪一層被篩除 | `N_A` ｜ `UNCONDITIONAL` ｜ `STATIC_TIER0_FILTER` ｜ `DYNAMIC_WORKER_MAPPER_DROP` |

### 2.5 構面 E：非預期中斷與故障時序軸（2 個正交因子）

| 因子代號與名稱 | 獨立正交維度說明 | 離散水準值（Levels） |
| :--- | :--- | :--- |
| **E1. 中斷或故障類型 (`InterruptionKind`)** | 決定打破正常執行流的信號或錯誤本質 | `NONE` ｜ `CALLER_CANCEL` ｜ `PREEMPT_ABORT` ｜ `TIMEOUT_EXCEEDED` ｜ `BUSINESS_ERROR` ｜ `FATAL_TOPOLOGY_ERROR` ｜ `HARD_CRASH_OR_EOF` ｜ `SYSTEM_DRAIN_OR_QUIESCE` |
| **E2. 中斷發生相位 (`InterruptionPhase`)** | 決定 E1 發生在生命週期的哪一個精確時間窗 | `N_A` ｜ `P0_PRE_ACCEPT` ｜ `P1_INIT_OR_WARMUP` ｜ `P2_WAITING_LOCK` ｜ `P3_PRIMARY_IN_FLIGHT` ｜ `P4_EVENT_DRAIN_LOOP` ｜ `P5_LIFO_TEARDOWN` |

### 2.6 先天物理互斥約束 (Domain Invariants)
- **終端機互斥**：`B6 = INTERACTIVE_TTY` 蘊含 `A2 = COLD_ONLY`、`B1 = CLI_ONESHOT` 且 `B3 = FOREGROUND`。
- **常駐依賴互斥**：`A2 = DAEMON_ONLY` 遇 `B2 = FORCE_COLD` 或 `C1 = OS_SANDBOX_RESTRICTED` 時於首關確定性拒絕。
- **環境變異互斥**：`A8 != NONE` 蘊含 `A2 = COLD_ONLY`，且嚴禁由常駐熱任務同步呼叫或由背景/事件觸發。
- **安全閘門互斥**：`A9 = GATED` 嚴禁綁定 `INTERNAL_TRIGGER`、事件訂閱或定時排程。

## 3. 全倉五大真實入口通道聚合總覽 (25 Real-World Archetypes)

### 3.1 手段一：外部單次指令入口（`B1 = CLI_ONESHOT`）
- **`C-00` 前置引導與靜態短路**：`yscb.py init [--fix]`、`self-update`（單檔自舉不進 `runtime`）；各級 `--help`、未知指令拼寫建議（直讀靜態索引秒回，**零模組載入、零 `auto_spawn`、零 Idle TTL 續命**）。
- **`C-01` 極速唯讀查詢與快照檢索**：`status`、`list`、`uri check`、`config get`、`vsc status`、`gdrive status`、`plan status/search`、`ast outline/callers/callees/impact`、`kdb search/status/model status`（`HYBRID + PARALLEL + PURE_READ`，支援無鎖秒回快照或 `--sync` 串聯對齊，注意子目錄 `./file` 之 `CALLER_CWD_SENSITIVE`）。
- **`C-02` 本地冪等投影與衍生建置**：`vsc sync/revert`、`agents-workflow init/release`、`plan verify --log`、`dev create/check/build`、`config set`、`reload`、`ast sync`、`kdb index [--force] [--export]`（`HYBRID + COALESCE/SERIALIZE + IDEMPOTENT_LOCAL_WRITE`，注意帶參請求等價分流與 `PROGRESS_STREAMING`）。
- **`C-03` 外部網路非冪等 I/O 傳輸**：`gdrive ls/get/put/rm/mkdir/shortcut/push/pull`、`kdb model download`、`list --remote`（`HYBRID + SERIALIZE + OPAQUE_NATIVE_OR_IO + NON_IDEMPOTENT_EXTERNAL`，`P3` 收單後斷線嚴禁自動重跑）。
- **`C-04` 前景互動式 TTY 獨佔**：`gdrive auth`（`COLD_ONLY + INTERACTIVE_TTY`，壓制 `auto_spawn`，寫入私密 `config.local://`）。
- **`C-05` 高危破壞性資料重置**：`plan archive`、`kdb clean`、`rollback`（`GATED + SERIALIZE + HYBRID`，線上 Worker 自行關檔清理免跨進程鎖衝突）。
- **`C-06` 運行底座與內核自變異**：`install`、`update`、`remove [--clean/--purge]`、`restore`（`COLD_ONLY + MUTATES_MODULES / MUTATES_CORE`，發送 `CONTROL_QUIESCE` 讓位或觸發 `core` 釋鎖交棒自重啟）。
- **`C-07` 跨倉沙盒與環境編排串聯**：`dev test [-j N] [--sync]`、`dev release`（`COLD_ONLY + SPAWNS_OS_SUBPROC + ISOLATED_CHILD_WORKSPACE`，支援 `Ctrl+C` 進程樹回收與 `--sync` 串聯宿主安裝）。
- **`C-08` 常駐守護進程元控制**：`daemon start [--console|--daemon] [--ttl]`、`daemon stop [--force]`、`daemon status`、`daemon reload`（直連控制平面，`status` 唯讀不續命 TTL）。

### 3.2 手段二：外部長連線程式化入口（`B1 = SDK_PERSISTENT_CLIENT`）
- **`S-01` 同連線多路並發檢索**：IDE 透過單一 Socket 同時發送多組奇數 `stream_id` 亂序完成回傳，零 Head-of-Line 阻塞。
- **`S-02` 打字防抖與單流精準取消**：連續輸入時對舊 `stream_id` 發送 `CANCEL` 幀中止等鎖或執行，底層 Socket 長連線不斷開。
- **`S-03` 跨狀態遷移之長壽命會話**：空閒長連線不阻擋 Daemon `Idle TTL` 休眠；Daemon 休眠或換埠重啟後，SDK 於 `P0_PRE_ACCEPT` 遇舊連線 EOF 自動廢棄舊通道、重跑探測/拉起並透明重試一次。
- **`S-04` `SDK_ONLY` 結構化呼叫與測試治具**：內部強型別批次契約與 `FORCE_COLD` 記憶體測試直連。

### 3.3 手段三：任務內同步串聯入口（`B1 = NESTED_INVOKE_TASK`）
- **`N-01` 跨模組異鎖前置水位對齊鏈**：`kdb.search(--sync) -> kdb.index -> ast.sync`、`dev.test -> dev.build`（即使共置同一 `venv_group` 亦必經主控端 `RuntimeDispatcher` 協調鎖與收集事件）。
- **`N-02` 同資源鎖之母子組合重入**：`core.install -> core.reload`（同同步 `CallStack` 祖先持鎖時僅 `SERIALIZE` 支援重入繼承持鎖）。
- **`N-03` 跨冷熱與環境變異邊界串聯**：`dev test --sync -> core.install @build`（外部 `COLD_ONLY` 串聯合法；禁止常駐熱任務同步呼叫環境變異任務防互鎖）。
- **`N-04` 宿主對隔離子工作區跨倉編排**：`dev test` 操作子沙盒倉（顯式 `AUTO_NO_SPAWN`，以 `(workspace_root, task_id)` 區分免誤報環路）。
- **`N-05` 跨安全等級之巢狀代理呼叫守門**：Stage 1 對內部 `invoke_task` 一致核驗頂層 `approval_scope`，阻斷低權限任務借道呼叫 `GATED` 任務。

### 3.4 手段四：事件訂閱觸發入口（`B1 = EVENT_SUB_DEFERRED / IMMEDIATE`）
- **`E-01` 雙緩衝折疊衍生與扇出**：`space_updated -> ast.sync -> graph_updated -> kdb.index` 及 `workspace_reloaded -> {vscode, agents_workflow}`。
- **`E-02` 破壞前立即同步清理**：`core.remove` 刪目錄前呼叫 `ctx.emit_imm(ModuleRemoving)` 同步有序執行設定還原。
- **`E-03` 同輪訂閱部分異常隔離與 `COALESCE` 傳播**：單一訂閱者業務拋錯不阻斷同輪獨立訂閱者，並向該模組 `COALESCE` 等待者精準傳播錯誤。
- **`E-04` 跨事件與 `invoke_task` 閉環熔斷**：`CausalLineage` 偵測閉環瞬間拋出致命 `EventCycleError` 中止全 Turn。

### 3.5 手段五：常駐背景自治入口（`B1 = DAEMON_FS_WATCHER / PERIODIC` & Hot-Reload）
- **`W-01` 空間防抖監聽與微批次讓渡**：`500ms` 防抖 + VFS 免回音過濾 + 啟動補掃；長耗時索引以微批次檢查 `cancel_token` 響應 `PREEMPT`。
- **`W-02` 組態閘控之定時輪詢**：如 `gdrive-support` 綁定組態開關（預設 `auto_sync: false` 零喚醒待機），採 `fixed-delay` 防慢網路堆積且空轉不續命 TTL。
- **`W-03` 容器預熱與組態/模組/內核熱重載**：`WARMING` 預熱故障隔離；監聽 `config/`、`contribute.json` 與 `.modules/` 熱刷新；`core` 更新執行先釋鎖再交棒自重啟。

## 4. 遺漏統籌與規格回補清單 (4 Blind-Spot Categories & 13 Spec Fixes)

| 盲區根因分類 | 發現編號與具體邊界漏點 | 回補目標規格文件 |
| :--- | :--- | :--- |
| **1. 呼叫端與常駐端時空錯位** | **#1** 顯式傳遞 `caller_cwd` 與白名單 `caller_env`，禁業務模組直呼 `os.getcwd()` | `runtime.md` |
| | **#2** 新增 `DaemonWatcherConfig` 搭配 `PollingDirectoryWatcher` 監聽手改 `config/` JSON + 冷啟動 Step 1 指紋校驗 | `daemon.md`, `lifecycle.md` |
| | **#3** 空閒長連線不卡 `Idle TTL` 休眠；持久客戶端於 `P0_PRE_ACCEPT` 遇舊 Socket EOF 自動重探測重連 | `rpc.md`, `daemon.md` |
| **2. 動態參數與呼叫棧血緣** | **#4** `COALESCE` 引入正規化請求等價指紋 `equivalence_key`，同鎖異參自動退為 `SERIALIZE` 排隊防吞參 | `runtime.md` |
| | **#5** 補齊 `HELD_BY_SAME_CALLSTACK`：同同步 `CallStack` 祖先持鎖僅允許 `SERIALIZE` 重入，攔截自重入 `PREEMPT/COALESCE` | `runtime.md` |
| | **#6** `InvokeRequest` 攜帶顯式 `approval_scope`，Stage 1 對巢狀呼叫一致守門 `GATED` 並禁絕背景觸發 | `runtime.md`, `event.md` |
| | **#7** 細分 `SelfMutationScope`，禁止常駐熱任務內部同步呼叫環境變異任務，根除與 `QUIESCE` 互鎖 | `runtime.md` |
| **3. 原生阻塞與物理負載邊界** | **#8** 明定長耗時原生運算微批次檢查 `cancel_token` 規範，逾 `grace_ms` 由 `foundation.proc` 強殺進程樹釋鎖 | `runtime.md` |
| | **#9** 雙端強制檢查 `MAX_FRAME_BYTES = 64 MiB`，超限回報結構化 `PAYLOAD_TOO_LARGE`，大產物走 VFS 路徑傳遞 | `rpc.md` |
| | **#10** `WorkerContainerLifecycle.warmup()` 單模組預熱失敗局部降級隔離，不拖垮 Daemon 主體啟動 | `lifecycle.md` |
| **4. 單步多發與動態排程假設** | **#11** `TaskLocalOutbox.stage()` 固定基於入站基準 `base_lineage` 分支 `.advance()`，防同單步多發同型事件假自環 | `event.md` |
| | **#12** `PeriodicTriggerLoop` 支援組態啟停開關綁定與 `fixed-delay` 計時，防預設關閉空跑與慢網路堆積 | `daemon.md`, `runtime.md` |
| | **#13** 共置 `venv_group` 跨模組呼叫強制經主控端派發；模組自有儲存清理（如 `kdb clean`）歸位 `HYBRID + SERIALIZE` | `runtime.md` |

## 5. 最小完備驗證案例集 (`RC-01` ～ `RC-08` Minimum Covering Suite)

受限於 `C1` 與 `E1` 各具 8 個互斥離散水準，最小全覆蓋下界為 **8 組端到端案例**。以下 `RC-01` ～ `RC-08` 達成 **23 正交因子、77 離散水準 100% 覆蓋**：

### `RC-01`：冷啟動並發風暴、過期端點免疫、子目錄相對路徑與受限沙盒退回
- **劇本**：工作區預置過期 `daemon.json`，由子目錄同時拉起 10 個 CLI 進程執行唯讀 Tier 1 任務（傳入 `./rel_file` 與 `--json`），並加測 `--help` / `daemon status` 零拉起，以及禁 Socket 環境 `AUTO_NO_SPAWN` 下 Tier 1 `OneShotVenvHost` 冷重入回呼 Tier 0。
- **驗收**：`daemon.json` 不被任何客戶端誤刪、`spawn.lock` 確保僅誕生 1 個 Daemon、`caller_cwd` 解析正確、受限沙盒靜默冷跑 `0` 錯誤雜訊。
- **覆蓋水準**：`A1:CLI_AND_SDK`, `A2:HYBRID`, `A3:TIER_1_DEDICATED+TIER_0`, `A4:LAZY_HANDLE`, `A5:PARALLEL`, `A7:PURE_READ`, `B1:CLI_ONESHOT`, `B2:AUTO_SPAWN+AUTO_NO_SPAWN`, `B5:CALLER_CWD_SENSITIVE`, `B7:MULTI_PROC_BURST`, `C1:OFFLINE_CLEAN+OFFLINE_STALE_JSON+BOOTING_WARMING+OS_SANDBOX_RESTRICTED`, `C3:COLD_UNLOADED`, `D1:SINGLE_STEP_LEAF`, `D2:NONE`, `D3:N_A`, `D4:N_A`, `E1:NONE`, `E2:N_A`。

### `RC-02`：常駐預熱隔離、多空間同單步多發衍生鏈、前置過濾與微批次搶占
- **劇本**：Daemon `WARMING` 預熱共置 Worker 模型（注入 1 個故障擴充模組驗證 `P1` 局部降級不崩潰）；隨後同時變更 3 個檔案空間觸發 `500ms` 防抖背景 Turn，單步連發 3 顆 `space_updated`（驗證 `base_lineage` 不誤報自環），Tier 0 `payload_filter` 篩除無關空間不誤搶占，命中者折疊為單一 `EventBatchEnvelope` 推進 `ast -> kdb`（含 `batch_mapper` 返回 `None` 短路分支），微批次執行半途新存檔觸發 `PREEMPT` 中止舊輪，且 VFS 自寫命中免回音帳本。
- **覆蓋水準**：`A1:INTERNAL_TRIGGER`, `A3:TIER_1_SHARED_GROUP`, `A4:EAGER_WARM_SINGLETON`, `A5:PREEMPT`, `A6:COOPERATIVE`, `B1:DAEMON_FS_WATCHER+EVENT_SUB_DEFERRED`, `B3:BACKGROUND`, `C1:READY`, `C2:HELD_BY_INMEM_BG`, `C3:WARM_IN_SYNC`, `D1:SIBLING_MULTI_EMIT`, `D2:DEFERRED_OUTBOX`, `D3:UNORDERED_FOLD`, `D4:STATIC_TIER0_FILTER+DYNAMIC_WORKER_MAPPER_DROP`, `E1:PREEMPT_ABORT+BUSINESS_ERROR`, `E2:P1_INIT_OR_WARMUP`。

### `RC-03`：前景快照無鎖秒回、優先級繼承与帶參 `COALESCE` 等價分流
- **劇本**：背景索引持鎖執行期間：① 前景查詢無鎖 `<5ms` 秒回快照；② 兩前景並發執行相同無參索引任務，觸發背景鎖優先級繼承與同工作區頂層 `COALESCE` 單飛合併（並模擬宿主 Step 5 `P4` 衍生異常驗證精準傳播予所有搭便車者，不誤回 `Exit 0`）；③ 另一前景帶 `--force --export ./out.json` 因 `equivalence_key` 不同自動轉為 `SERIALIZE` 排隊接續執行並回推 `PROGRESS`（含 `--sync` 前置 `NESTED_INVOKE_TASK` 對齊鏈；依內核精簡不變量，巢狀與事件鏈內之 `COALESCE` 請求一律確定性降級為 `SERIALIZE` 執行不跨層合併）。
- **覆蓋水準**：`A5:COALESCE+SERIALIZE`, `B1:NESTED_INVOKE_TASK`, `B3:FOREGROUND`, `B6:PROGRESS_STREAMING`, `C2:HELD_BY_INMEM_FG`, `D1:LINEAR_REENTRANT_CHAIN`, `E2:P4_EVENT_DRAIN_LOOP`。

### `RC-04`：IDE 長連線多路亂序並發、單流精準取消與跨 Idle TTL 休眠透明重連
- **劇本**：持久 `PersistentRpcSession` 於單一 Socket 同時並發發送快慢多路 `SDK_ONLY` 與 `DAEMON_ONLY`（`STRICT_HOT`）呼叫驗證亂序回傳；對 `P2` 等鎖中與 `P3` 執行中之指定 `stream_id` 發送 `CANCEL` 驗證連線不斷且其他流正常；保持空閒長連線驗證不阻擋 Daemon `Idle TTL` 到期進入 `DRAINING_STOP_OR_TTL`，並在到期邊界與停機後再次發單（`P0_PRE_ACCEPT`, `was_accepted=False`），驗證客戶端自動廢棄舊 Socket 重探測重拉起無感成功。
- **覆蓋水準**：`A1:SDK_ONLY`, `A2:DAEMON_ONLY`, `A9:SAFE`, `B1:SDK_PERSISTENT_CLIENT`, `B2:STRICT_HOT`, `B5:WORKSPACE_ROOT_ONLY`, `B6:UNARY_STRUCTURED`, `B7:MULTI_STREAM_SAME_CONN`, `C1:DRAINING_STOP_OR_TTL`, `C2:FREE`, `E1:CALLER_CANCEL`, `E2:P0_PRE_ACCEPT+P2_WAITING_LOCK+P3_PRIMARY_IN_FLIGHT`。

### `RC-05`：前景互動 TTY 授權、手改組態動態啟停定時排程與外部非冪等斷線保護
- **劇本**：① 執行 `INTERACTIVE_TTY` 授權任務驗證強制 `COLD_ONLY` 與壓制 `auto_spawn`；② 直接手改磁碟 `config` JSON 將 `auto_sync` 由 `false` 改為 `true`，驗證 `DaemonWatcherConfig` 搭配 `PollingDirectoryWatcher` 熱感知啟動 `fixed-delay` 定時任務（空轉不續命 TTL 且慢執行不重疊堆積）；③ 攜帶暫態環境變數執行外部非冪等 I/O 任務與定時任務互斥排隊，分別於 Worker `P0` 收單前與 `P3` 收單後注入 `SIGKILL` 硬崩潰及 `TIMEOUT_EXCEEDED`，驗證 `P0` 透明重拉成功而 `P3` 嚴格回報 `TRANSPORT_LOST` 絕不重跑。
- **覆蓋水準**：`A2:COLD_ONLY`, `A4:STATELESS`, `A6:OPAQUE_NATIVE_OR_IO`, `A7:NON_IDEMPOTENT_EXTERNAL`, `A9:CONDITIONAL`, `B1:DAEMON_PERIODIC`, `B5:CALLER_ENV_SENSITIVE`, `B6:INTERACTIVE_TTY`, `B7:ISOLATED_SINGLE`, `C3:DISK_CONFIG_EDITED`, `E1:HARD_CRASH_OR_EOF+TIMEOUT_EXCEEDED`。

### `RC-06`：套件安裝/卸載、`emit_imm` 有序清理、全域 `QUIESCED` 排隊自癒與 `core` 釋鎖交棒重啟
- **劇本**：常駐與 Tier 1 Worker 在線持句柄下：① 執行模組移除與安裝（`MUTATES_MODULES`），發送全域單一屏障 `CONTROL_QUIESCE` 釋鎖（不支援逐模組局部租約）；期間連入之外部 `HYBRID` 請求於 `QUIESCED` 閘門安全排隊等待 `RESUME`（冷啟動讀者則等待共享 `installer.lock`），移除前以 `emit_imm` + `ORDERED_FIFO` 同步執行設定還原，完成後同呼叫棧 `SERIALIZE` 重入 `reload` 扇出 `FANOUT_DIAMOND_DAG`（並模擬安裝器崩潰驗證單調租約到期自癒恢復 `READY` 與 `.modules/<mod>` 熱重載）；② 執行 `core` 內核更新（`MUTATES_CORE`），驗證舊 Daemon 排空、刪除 `daemon.json` 並釋放 `daemon.lock` 後成功交棒新 Daemon。
- **覆蓋水準**：`A8:MUTATES_MODULES+MUTATES_CORE`, `A9:GATED`, `B1:EVENT_SUB_IMMEDIATE`, `C1:QUIESCED+DRAINING_CORE_HANDOFF`, `C2:HELD_BY_INSTALLER+HELD_BY_SAME_CALLSTACK`, `C3:DISK_CODE_OR_PROTO_UPDATED`, `D1:FANOUT_DIAMOND_DAG`, `D2:IMMEDIATE_SYNC+MIXED_BOTH`, `D3:ORDERED_FIFO`, `D4:UNCONDITIONAL`, `E1:SYSTEM_DRAIN_OR_QUIESCE`。

### `RC-07`：跨倉隔離沙盒並行跑測、OS 子進程樹 `Ctrl+C` 清場與 Step 6 LIFO 卸載隔離
- **劇本**：編排任務建立多個 `ISOLATED_CHILD_WORKSPACE`（顯式 `AUTO_NO_SPAWN`，驗證跨倉同 `task_id` 合法不誤報自環），拉起多路外部 OS 子進程樹執行，中途注入 `Ctrl+C`（`SIGINT`）驗證連根強殺回收整棵子進程樹無孤兒殘留，且於 Step 6 `P5_LIFO_TEARDOWN` 注入單一資源 `close()` 異常驗證不阻斷底層資源釋放、達成 `0 ResourceWarning`，正常跑通時串聯宿主安裝閉環。
- **覆蓋水準**：`A6:SPAWNS_OS_SUBPROC`, `A7:IDEMPOTENT_LOCAL_WRITE`, `B4:ISOLATED_CHILD_WORKSPACE`, `E2:P5_LIFO_TEARDOWN`。

### `RC-08`：跨進程冷熱物理鎖互斥、安全閘門防借道提權、`64 MiB` 訊框護欄與因果閉環熔斷
- **劇本**：① 外部顯式 `--cold`（`FORCE_COLD`）進程與線上 Daemon 同時競爭同一 `resource_key`，驗證 `.cache/locks/<key>.lock` 跨進程嚴格互斥；② 驗證無 `approval_scope` 之巢狀 `invoke_task` 偷調 `GATED` 任務被攔截、熱任務同步呼叫環境變異任務被攔截、對同呼叫棧祖先鎖自重入 `PREEMPT/COALESCE` 被攔截、`>64 MiB` 超大訊框回報 `PAYLOAD_TOO_LARGE` 不崩潰，以及任務/事件 `TRUE_CYCLE` 閉環瞬間拋出 `EventCycleError` 中止全 Turn。
- **覆蓋水準**：`B2:FORCE_COLD`, `B6:LARGE_PAYLOAD_BOUNDARY`, `C2:HELD_BY_EXT_COLD_PROC`, `D1:TRUE_CYCLE`, `E1:FATAL_TOPOLOGY_ERROR`。
