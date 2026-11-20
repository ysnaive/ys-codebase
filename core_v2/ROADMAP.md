# YS-Codebase 2.0 (`Core 2.0`) 宏觀目標服務架構與演進路線圖

> **狀態**：`Active Architecture Constitution`
> **工作區位置**：`./core_v2/`（潔淨室隔離重構空間）
> **目標範疇**：`core 2.0` 六大正交功能域微內核（內化原 `server` 與 `file-space`）、`dev 2.0` 工具鏈，以及全生態系模組強型別 OOP 遷移
> **最後更新**：`2026-11-16`

## 1. 核心願景與重構動機 (Vision & Motivation)

`YS-Codebase 1.x` 起源於單次短生命週期的冷啟動 CLI 調度器，後期逐步外掛常駐守護進程（`server`）、多執行緒檔案監聽與跨空間增量索引（`ast`、`knowledge-db`）。由於早期內核僅提供偏底層的工具函式與可變字典上下文，迫使各下游業務模組自行處理執行緒鎖、跨進程檔案鎖、多檔快取世代校驗、路徑字串正規化與執行期動態套件安裝，導致跨平台（特別是 Windows 檔案句柄鎖定與路徑大小寫）與高並發場景下反覆出現結構性隱患。

`Core 2.0` 的核心設計哲學為**「控制反轉（Inversion of Control, IoC）、萬物皆 `Task` 與派發單點收斂」**：
- 將 `Core` 升格為**以 100% Python 3.11+ 標準庫打造的強型別受管應用微內核（Managed Application Microkernel）**。
- **派發單點封閉鐵律**：除宿主啟動器 `yscb.py` 於 `core` 尚未存在前的兩個零依賴自舉原語（`init` 與 `self-update`）外，**全系統所有業務功能調用（無論來自 CLI、SDK、Daemon RPC、領域事件、定時排程或模組升級遷移）100% 必須收斂為 `Task[TIn, TOut]` 並唯一經由 `core.execution.runtime` 派發與協調**。
- 下游業務模組嚴格限制於**「零自管鎖、零裸路徑、零自建常駐執行緒、零執行期動態 `pip`」**的純淨業務沙盒內，100% 專注於領域模型與核心業務演算法。

## 2. 六大頂層架構決策與核心不變量 (Core Architectural Decisions)

| 決策編號 | 架構維度 | `Core 2.0` 拍板定案與剛性不變量 |
| :--- | :--- | :--- |
| **DR-01** | **服務範疇與單點派發** | **每專案獨立 Daemon + 內化 `server` / `file-space` + `runtime` 獨攬派發權**：每個宿主工作區擁有獨立輕量常駐進程（管理指令統一為 `daemon start/stop/status/reload`）；冷熱路由、`auto_spawn`、Tier 1 子進程池、`resource_key` 統一跨進程/記憶體互斥、單飛合併、搶占取消與具備優先級繼承之前景節流 **100% 鎖死於 `execution.runtime` 單點維護**。 |
| **DR-02** | **萬物皆 `Task` 與三大執行期生命週期** | **唯一公開執行單元 `Task[TIn, TOut]` + `execution.lifecycle` 三態狀態機**：模組所有公開或受觸發能力一律封裝為帶 `TaskMetadata` 的 `Task`；執行期統一驅動 **冷派發完整 1～6 步**、**熱請求 2～5 步**（雙緩衝凍結 Swap 事件排空迴圈，支援 `emit` + `emit_imm` 與 `ORDERED / UNORDERED` 事件批次折疊）及 **常駐容器七態生命週期體系（`ContainerState`）**；跨進程通訊統一採用原生 `socket` 長度前綴全雙工多工訊框（`execution.rpc`）。 |
| **DR-03** | **去資料庫耦合與選配快照倉** | **`execution.runtime` 零資料庫假設 + `filesystem.storage` 選配多世代快照倉**：執行引擎不預設下游為資料庫模組，中止時的資源原子性由模組按需選用的 Context Manager（如 `vfs` 暫存原子替換或 `storage` 事務）各自保證；索引型模組按需注入 `storage`（`sqlite3` WAL MVCC），預設毫秒級零鎖秒回上一版已提交快照並附帶背景追平提示（顯式指定 `--sync` 時才等待追平）。 |
| **DR-04** | **語言與依賴隔離（方案 B）** | **全 Python 3.11+ 雙層執行模型 + 不可變雜湊 `.venv` 池（`packaging.env`）**：<br>1. **Tier 0（純標準庫模組）**：直接運行於內核進程，0 第三方依賴、0 `.pyd` 鎖檔。<br>2. **Tier 1（含 `pip_dependencies` 模組）**：於安裝期依雜湊建置 `.venv/<group>_<hash>/`（支援選配 `venv_group` 共置），由 `runtime` 調度獨立單步子進程執行；廢除執行期隱式 `pip install`，升級時切換新雜湊子進程並背景回收舊環境，根除 Windows `.pyd` / `.dll` 鎖死。 |
| **DR-05** | **全程式碼 OOP 強型別化** | **領域物件三分法 + 零裸 `dict` + 靜態紅線守門**：不可變領域值物件（`@dataclass(frozen=True, slots=True)`）+ 建構子顯式 DI 領域服務（零全域單例）+ `DataclassCodec` 邊界自動編解碼；`dev check 2.0` 強制執行 Strict 型別檢核，並靜態封殺下游模組私自呼叫裸 `open()`、`os.path`、`threading.Lock`、`pickle` 或繞過 `runtime` 私開 `yscb.py` 子進程。 |
| **DR-06** | **外部宣告式擴充延續** | **`Contributes 2.0`（對外零代碼 JSON 擴充、對內強型別自動編解碼）**：100% 保留模組間 `contributes/<host>.json` 與下游專案 `config://<host>/contribute.json` 免改源碼擴充機制（維持 `merge / extend / replace / unique` 合併語意）；對內以 Host 端 Python 強型別 `@dataclass` 為唯一真理來源，自動導出 `.vscode/schemas/*.json` 並注入不可變強型別物件圖。 |

## 3. `Core 2.0` 六大正交功能域與跨分類解耦鐵律 (Orthogonal Domains & DAG)

內核依高內聚變更軸線劃分為 **6 大完全正交功能域（共 19 個子模組）**。為杜絕「雞生蛋」反向耦合，全內核強制執行三大跨分類解耦鐵律（並納入 `dev check 2.0` AST 匯入方向檢查）：

1. **`filesystem` 純機制化（嚴禁匯入 `metadata`）**：`metadata` 僅使用底層物理 `filesystem.fs` 讀取 JSON 並產出純值物件（`MountRule`、`SpaceSpec`）；`vfs` 與 `space` 僅接收建構子顯式傳入的值物件，完全不感知設定檔與擴充檔來源。
2. **`packaging` 純離線引擎化（嚴禁匯入 `execution`）**：`packaging`（`env` + `installer`）僅執行純靜態磁碟解包、校驗與 `.venv` 建置，不認識 `Task`、`Event` 或 `Daemon`；「通知線上 Daemon `quiesce` 讓位 $\rightarrow$ 發移除前事件 $\rightarrow$ 呼叫 `installer` $\rightarrow$ 發重載事件」之動態編排，统一收斂於上層內建系統管理 `Task`。
3. **底層只收純資料、消費端定義 Port、組裝根負責轉接**：`foundation.observability` 不自行掃描模組目錄；`Task / Event / YscbModule` 及 `ModuleProviderPort` / `ModuleDescriptor` 由消費端 `execution.runtime` 定義，`metadata` 與 `packaging` 維持 100% 零匯入 `execution`，由頂層 `surface` 組裝根提供 `(metadata + packaging) -> ModuleDescriptor` 薄轉接層，且 `surface.sdk` 僅做單向對外 Re-export，`execution` 嚴禁反向匯入 `surface`。

### 3.1 六大功能域嚴格單向匯入白名單（Unplug-Ready Domain DAG）

```text
[下游業務模組] ──(唯一公開匯入邊界)──> Domain 6 (surface.sdk) & Domain 1 (foundation.primitives, errors)

Domain 6: 對外門面域 (surface/)     [cli, sdk]              ── 允許依賴: Domain 1 ~ 5
   │
   ▼
Domain 5: 執行調度域 (execution/)   [daemon -> runtime -> {lifecycle -> event, rpc}] ── 允許依賴: Domain 1 ~ 4
   │
   ▼
Domain 4: 套件環境域 (packaging/)   [installer -> env]      ── 允許依賴: Domain 1 ~ 3 (嚴禁依賴 execution!)
   │
   ▼
Domain 3: 組態擴充域 (metadata/)    [contributes <- config] ── 允許依賴: Domain 1 + filesystem.fs (嚴禁依賴 vfs/space!)
   │
   ▼
Domain 2: 檔案儲存域 (filesystem/)  [space | storage <- vfs <- fs] ── 僅依賴: Domain 1 (100% 獨立可測!)
   │
   ▼
Domain 1: 基礎底座域 (foundation/)  [codec | observability | proc <- primitives | errors] ── 僅依賴: Python 標準庫!
```

### 3.2 六大功能域與 19 個內核子模組職責清冊

#### Domain 1：基礎底座域（`foundation/` — 僅依賴 Python 標準庫）
1. **`primitives`**：全系統共通不可變值物件（Wave 1.1 先行落地執行內核子集：`ModuleId`、`TaskId`、`EventId`、`HostPath` 與純量/路徑邊界校驗原語；Wave 1.2 待補完組態/空間/版本值物件：`SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash`、`MountRule`、`SpaceSpec`）。
2. **`errors`**：結構化異常階層（Wave 1.1 已落地：`YscbError` 基類、`ErrorDetail`、標準 `ErrorCode`、修復指引 `remediation` 與 `TaskCancelledException`）。
3. **`codec`**：純標準庫強型別編解碼器（Wave 1.1 已落地 `DataclassCodec`；Wave 1.2 待隨 `metadata` 補完 `SchemaExporter`、`DeepInfiller`）。
4. **`observability`**：顯式注入之可觀測性與取消原語（Wave 1.1 已落地執行內核子集：`CancellationToken`、`DeadlineGuard`、`ProgressEvent` 與執行緒局部標準輸出隔離守衛 `guard_standard_streams`；Wave 1.2 待補完 `StructuredLogger`、`LogRotator`、`ProgressStream`、`LocaleCatalog`、`SessionTelemetry`）。
5. **`proc`**：跨平台 OS 進程樹原語（Wave 1.1 已落地：`ManagedProcessTree` 基於 Windows Job Object［含顯式 `BREAKAWAY_OK`］/ POSIX Session+PGID 與環境標記清理、`spawn_detached`、`SignalWakeupGuard`、進程存活與啟動時間指紋探針）。

#### Domain 2：檔案、空間與儲存域（`filesystem/` — 僅依賴 `foundation/`）
6. **`fs`**：物理檔案系統原語（`atomic_write_bytes` / `atomic_write_json` 等原子寫入與無符號連結路徑守衛、支援 `.upg/.xchg` 防死鎖升級之跨進程檔案鎖 `FileLock`、純標準庫輪詢防抖目錄變更監聽器 `PollingDirectoryWatcher`）。
7. **`vfs`**：語意 URI 路由表（`UriMountTable`）、目錄穿越守衛（`AccessGuard`）、唯讀空間保護（`ReadonlyPolicy`）、暫存原子寫入交易與寫入免回音指紋登記之 `ScopedVfs`。
8. **`space`**：邏輯檔案空間引擎（`IgnoreRuleEngine`、`SpaceRegistry`、`SpaceScanner`），產出強型別 `SpaceDiffBatch`。
9. **`storage`**：供索引/狀態型模組按需注入的 `sqlite3` WAL 持久化引擎（`ModuleDatabase`、`SnapshotReader`、`WriteTransaction`、`BlobVault`）。

#### Domain 3：組態與擴充域（`metadata/` — 僅依賴 `foundation/` + `filesystem.fs`）
10. **`config`**：2x2 強型別組態矩陣（全域/模組 × `config.project.json` / `config.local.json`）與 `SnapshotVault` 備份回滾保險庫。
11. **`contributes`**：雙向強型別擴充聚合器（`ExtensionPointSpec`、`ContributesAggregator`、`ProvenanceGraph`）。

#### Domain 4：套件與環境域（`packaging/` — 僅依賴 Domain 1～3）
12. **`env`**：方案 B 不可變虛擬環境池（`EnvSpec`、`ImmutableVenvPool`、`EnvHealthProbe`、`EnvGarbageCollector`），支援選配 `venv_group` 共置。
13. **`installer`**：純靜態模組包獲取與部署引擎（`ProviderClient`、`DependencySolver`、`MirrorStore`、`AtomicPackageDeployer`、`UpdateChecker`）與五大資料空間 `--purge` 物理清理器。

#### Domain 5：執行與常駐調度域（`execution/` — 動態執行心臟）
14. **`event`**：強型別雙緩衝事件佇列與因果環路偵測器（`EventMetadata`、`EventOrdering`、`EventBatchEnvelope`、`DoubleBufferedEventQueue`、`CausalLineage`）。
15. **`lifecycle`**：三大執行期生命週期狀態機引擎（`ColdTurnRunner` 冷派發 1～6 步、`TurnEngine` 熱請求與事件排空 2～5 步、`WorkerContainerLifecycle` 常駐七態單一權威狀態機）。
16. **`rpc`**：純標準庫 `socket` 長度前綴全雙工多工訊框協議（`RpcFrame`、`MultiplexedChannel`、`PersistentRpcSession`、`RpcServerListener`），強制執行伺服端先送達 `CALL_ACCEPTED` 再產生副作用鐵律，統一支撐 `CLI <-> Daemon` 與 `Daemon <-> Worker` 雙向通訊與重入。
17. **`runtime`**：全系統唯一派發與執行協調中樞（`Task`、`TaskMetadata`、`RuntimeDispatcher`、`ResourceCoordinator`、`StepFlight` / `FlightCascade`、`LifecycleReloadGate`、`Tier1WorkerPool`［實作為 `HotWorkerPool`］、`OneShotVenvHost` 與 `LocalModuleSlotRegistry`）。
18. **`daemon`**：超薄每專案常駐守護外殼（`WorkspaceDaemon`、`SingleFlightDaemonSpawner`、`IdleTtlMonitor`、`DaemonWatcherConfig`、基於 `PollingDirectoryWatcher` 之空間/模組/組態三路監視實例與 `PeriodicTriggerLoop`）。

#### Domain 6：對外門面域（`surface/` — 公開契約與終端介面）
19a. **`sdk`**：下游業務模組唯一公開匯入門面（單向重匯出受管契約與程式化呼叫入口）。
19b. **`cli`**：依據預編譯靜態 `tasks.index.json` 毫秒級完成命令列解析、`--help` 卡片渲染、內建系統管理 `Task`（如 `install`、`daemon`）綁定與雙軌輸出排版。

## 4. `./core_v2` 潔淨室分域目錄拓撲與同步護欄 (Workspace Layout & Guardrails)

```text
./core_v2/
├── ROADMAP.md                # 本宏觀架構憲法與四波段遷移總路線圖
├── sub_module_design/        # 六大正交功能域子模組深度架構設計規格（多輪交叉複查演進）
│   ├── foundation/           # foundation.md
│   ├── filesystem/           # fs.md, vfs.md, space.md, storage.md
│   ├── metadata/             # config.md, contributes.md
│   ├── packaging/            # env.md, installer.md
│   ├── execution/            # event.md, lifecycle.md, rpc.md, runtime.md, daemon.md
│   └── surface/              # sdk.md, cli.md
├── yscb.py                   # 2.0 超薄自舉啟動器（僅保留 init / self-update 自舉豁免，餘 100% 交棒 surface.cli）
├── source/                   # 2.0 模組唯一真理源碼區（100% OOP + Strict Typing）
│   ├── core/                 # Wave 1：六大功能域微內核
│   ├── dev/                  # Wave 1：OOP/強型別/跨分類匯入紅線靜態守門器、打包索引編譯器與跨平台沙盒
│   ├── vscode-support/       # Wave 2：Tier 0 IDE 路徑與 Contributes JSON Schema 投影模組
│   ├── agents-workflow/      # Wave 2：Tier 0 多代理研發工作流、模板編譯與計畫管理模組
│   ├── gdrive-support/       # Wave 2：Tier 0 Google Drive 差量分支與受管定時同步模組
│   ├── ast/                  # Wave 3：Tier 1 多語言靜態語法樹與雙向呼叫圖譜模組（削殼純 Task 化）
│   └── knowledge-db/         # Wave 3：Tier 1 BM25 + ONNX 混合語意檢索模組（削殼純 Task 化）
└── config/                   # 2.0 自引用驗證組態空間
```

### 雲端與版控防呆護欄（啟動實作前強制生效）
於 `./core_v2/` 首次啟動任何本地運行或沙盒測試前，必須先於根目錄 `.gitignore` 與雲端同步排除規則（`cloud.exclude`）加入以下衍生路徑：
- `core_v2/.venv`、`core_v2/.modules`、`core_v2/.mirror`、`core_v2/.build`
- `core_v2/.cache`、`core_v2/.storage.local`、`core_v2/.config.local`、`core_v2/.snapshots`、`core_v2/.temp`

## 5. 四波段漸進遷移計畫 (4-Wave Migration Roadmap)

| 波段 | 目標範疇 | 核心交付內容與架構任務 | 出場驗收門檻 (Exit Gate) |
| :--- | :--- | :--- | :--- |
| **Wave 1：<br>內核與工具鏈地基** | `core 2.0` (6 大功能域)<br>`dev 2.0`<br>`core_v2/yscb.py` | 1. **已完成 Wave 1.1 先行收斂基線**：`Domain 5 (execution)` 全域、`Domain 1 (foundation)` 執行內核子集（`foundation.md`）與 `Domain 2.fs`（`fs.md`）活規格與實作，以及 `verify_execution_live.py` 全套實機驗證已先行落地。<br>2. **Wave 1.2 待補完規格與跨功能域 Port 複審**：補齊 `Domain 1 (foundation)` 剩餘版本/空間/日誌組件、`Domain 2.{vfs,space,storage}`、`Domain 3 (metadata)`、`Domain 4 (packaging)`、`Domain 6 (surface)` 規格並完成盲審，依消費端 Port 契約複審 `ModuleProviderPort` / `ConfigViewPort` / `VfsEchoGuardPort` 並在 `surface` 落地組裝轉接層，再完成剩餘功能域實作與逐域獨立拔除測試（Unplug Test）。<br>3. 完成 `dev build` 靜態 `tasks.index.json` 自動提取、`dev check 2.0` 與 `core_v2/yscb.py` 啟動器。 | • `0 Any` 洩漏、`0 ResourceWarning`、6 大功能域嚴格單向無環、派發 100% 鎖死於 `execution.runtime`。<br>• 壓測驗證：多工重入零死鎖、跨進程 `resource_key` 零衝突、Tier 1 子進程熱替換零句柄鎖死。 |
| **Wave 2：<br>Tier 0 輕模組移植** | `vscode-support`<br>`agents-workflow`<br>`gdrive-support` | 1. 保留既有模板/技能資產、投影邏輯與三方同步帳本演算法。<br>2. 將所有外部與背景能力全面收斂為 `Task[TIn, TOut]`，拔除自管背景執行緒、`hook.*.py` 與裸字串路徑。 | • Tier 0 全模組 0 `.venv` 秒速運行。<br>• 工作流產物編譯與 Google Drive 離線沙盒同步 100% 通過契約測試。 |
| **Wave 3：<br>Tier 1 雙引擎削殼** | `ast`<br>`knowledge-db` | 1. 刪除舊版自管 `.bin.gz` 快取、`.kdb_index.lock`、前景 JIT 修補、自管前景活動旗標與動態 `pip`。<br>2. 以 `space -> ast -> kdb` 事件鏈重構更新流，`kdb index` 透過 SDK 調用上游更新並核對世代水位，無變更天然短路。 | • 下游業務模組 0 自管鎖、代碼大幅精簡。<br>• 連續大量改檔背景索引期間，前景查詢恆定毫秒級秒回且零世代撕裂。 |
| **Wave 4：<br>宿主原子切換與退役** | 根目錄切換至 `2.0.0.0` | 1. 完成本機 Windows 與雲端 Linux VM 全套實機端到端驗收與組態平滑遷移驗證。<br>2. 將 `./core_v2` 扶正為正式主幹，退役 `1.x` 舊源碼及獨立的 `server`、`file-space` 模組（收斂為 7 大模組）。 | • 全倉 7 大模組 100% 運行於 `Core 2.0` 基座，正式發布 `2.0.0.0`。 |
