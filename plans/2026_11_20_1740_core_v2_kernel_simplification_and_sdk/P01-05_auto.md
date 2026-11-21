# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 內核精簡、統一運行資料流聚合與 SDK 門面設計  
> 建立日期：2026-11-21  
> 所屬主計畫：無（獨立 Full Track 重構計畫）  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

> 基準保護不變量（`[P00:DR-01]`）：完整保留 annotated Git Tag `archive/core-v2-maximalist`（`9847b1a`）不變，確保所有減法重構皆具零維持成本之可比對基準。

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **`COALESCE` 同倉單飛與 `CallPropagationContext` 瘦身** | 1. 將 `COALESCE` 收斂為同工作區頂層單飛；跨倉巢狀與事件鏈內 `COALESCE` 請求一律降級為 `SERIALIZE` 執行（保留既有 `SERIALIZE` 重入與互鎖防護）。<br>2. 物理刪除 `lineage_join.py`（移除 `FlightCascade`、`ChildCascadeJoin`、`CascadeOutcome`）、跨進程多跳 `.turn.lock`/`.turn.json` 協議、`CoalesceCallerView`、`HolderIdentity.flight_id/alt_owners`、`EmittedEventHop` 與 `CoordinatorPort.handle_remote_flight_control`；明確保留 `CrossProcessLockPaths`（`.lock`/`.owner.json`/`.pin`）支撐 `ColdInstallerLockManager` 與同倉單跳跨進程 `SERIALIZE` 重入。<br>3. 自 `CallPropagationContext` 砍除 `COALESCE` 專用欄位（`coalesce_callers`、`coalesce_flights`），收斂為 10 欄位（完整保留 `turn_id`、`call_tree_id`、`call_stack`、`lineage`、`is_internal_trigger`、`is_nested_call`、`in_event_chain`、`from_hot_container`、`hot_workspaces`、`cold_shared_workspaces`，守護 `RC-07` 2-Daemon RPC、跨倉回彈與 `RC-08`）。<br>4. 於 `contracts.py` 預留系統領域事件常數 `WORKSPACE_RELOADED_EVENT_ID`（`core.workspace_reloaded`）、`MODULE_INSTALLED_EVENT_ID`（`core.module_installed`）與 `MODULE_REMOVING_EVENT_ID`（`core.module_removing`），供模組預先靜態訂閱（實際發射源依檔位 A 留待 Wave 1.2 `packaging`/`metadata` 接線）。<br>5. 保留 `RC-03` 核心保證：依 `equivalence_key` 區分同鎖帶參排隊與無參合併、支援 `PriorityHandle` 優先級繼承、全體等待者取消才中止單步，以及 Turn Step 5 衍生異常精確傳播予所有搭便車者。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-02** | **單一全域 `QUIESCE` 屏障與 `Daemon` 簡化** | 1. 將 `LifecycleReloadGate`、`RuntimeDispatcher` 與 `WorkspaceDaemon` 收斂為單一全域 `QUIESCE` 排空屏障，透過全域遞增 `epoch: int` 管理進入與恢復（維持 `is_globally_quiesced()` 方法簽名及步驟/RPC 協調方法、`LifecycleReloadGate` 純門控零外部依賴）。<br>2. 移除局部模組租約（`DaemonQuiesceControl.modules`、`DaemonResumeControl.modules`、`DueQuiesceResume`、`ResumeConsumePlan`、`QuiesceResumeResult.still_quiesced`、`expand_quiesce_targets`）、執行期動態 `venv_group` 遷移、分模組診斷歸屬（改為扁平 `deque[ErrorDetail]`）與 `WARMING` 半途交錯重載狀態機；控制線相容保留 `DaemonQuiesceControl(lease_sec, drain_timeout_sec)`、`DaemonResumeControl(expected_epoch)`、`DaemonReloadControl(modules)`（供指定磁碟重載）與 `QuiesceResumeResult(started, need_handoff)`。<br>3. 保留 `RC-06` 核心保證：全域 `QUIESCE` 期間外部 `HYBRID` 請求安全排隊等待 `RESUME`、租約逾期自動自癒恢復 `READY`、`installer.lock` 跨進程保護，以及 `MUTATES_CORE` 刪除 `daemon.json` 並釋放 `daemon.lock` 後交棒重啟。 | P0 | `[P00:DR-02]` |
| **FR-03** | **`foundation/codec.py` 與 `proc.py` 減重收斂** | 1. `foundation/codec.py` 砍除 MRO `TypeVar` 重映射（`_build_mro_tv_maps`、`_compile_mro_base_metadata`）、多維 Union/MapKey 特異度評分排名、靜態衝突格點證明器、`_WeakTypeToken`/`_DehydratedExpr` 脫水快取與 `inspect.currentframe()` 堆疊反射，改以簡潔 `WeakKeyDictionary` + 前綴驅逐與宣告序 `Optional`/`Union` 解碼實作（約 ~700–900 LOC），100% 完整保留 `DataclassCodec` 既有公開簽名（含 `encode(obj)`、`encode_envelope(obj)`、`decode_envelope(cls, raw)`、`decode` 雙 `@overload` 與 `evict_module_prefix -> None`）及 `infer_sequence_element_dataclass(fn, *, strict_unresolved=...)`。<br>2. `foundation/proc.py` 將 `SignalWakeupGuard`（560 LOC）收斂為 `<100 LOC` 單主執行緒 `signal.signal` 註冊器（100% 保留 `__init__(sig_nums, on_signal: Callable[[], None], *, on_second_signal=None)`、`install`、`close`、`__enter__`、`__exit__ -> None`），完整保留 Windows Job Object（`KILL_ON_JOB_CLOSE \| BREAKAWAY_OK`、`NtResumeProcess`）、POSIX `start_new_session`+`killpg`+`waitid`、`spawn_detached`、`is_process_alive`、`get_process_start_tag` 與 `ManagedProcessTree` 骨幹。 | P0 | `[P00:DR-02]` |
| **FR-04** | **單向 5 階段執行管道與反碎片化聚合** | 1. 將 `execution/runtime/`（`coordinator`、`dispatcher`、`gates`、`turn_session`、`step_host`、`wire`）與 `daemon/service.py` 反向聚合為清晰線性流程，收斂為 `[1. Ingress & Gate] -> [2. Route & Transport] -> [3. Resource Coordinator] -> [4. Step Execution] -> [5. Turn Event Drain & LIFO Teardown]` 單向 5 階段執行管道。<br>2. 消除因舊 Gate 0 複雜度限制產生的無意義 3–5 行奈米私有方法與冗餘包裝物件，維持 `CodeQualityStandards.md` 階段內聚。 | P0 | `[P00:DR-02]` |
| **FR-05** | **`core.surface.sdk` 方案 B 門面實作** | 1. 新增 `core/surface/` 與 `core/surface/sdk/`（對外唯一入口，`__all__` 精準鎖定為 **25 個完全自洽核心符號**，零私有或未匯出內部型別洩漏），採內部零反射 Metaclass 掃描方案 B 獨立基類 `Module`（透過 `to_yscb_module() -> YscbModule` 轉接，公開契約不暴露私有 Metaclass）與類別級靜態 `groups: ClassVar[tuple[type[TaskGroup], ...]]`（禁止執行期 `mount`）。<br>2. 支援可任意順序疊加之 `@task`（自動推導 `exposure`、`summary` 空字串由 Docstring 首行或 `f'Execute {task_id}'` 補齊，不設 `pros`/`cons`）、`@on_event`（支援字串 `EventId` 弱耦合訂閱，無 `enabled_by`）與 `@periodic` 裝飾器及 `define_event`；無參 `(self, ctx)` 方法自動綁定 `Empty` 與預設事件工廠；測試治具 `InMemoryModule(module_id)` 以 `add_task`/`to_yscb_module` 隔離使用。<br>3. 提供 `Arg` / `Option`（配合 `Annotated`）、`HumanRenderable`（`render_text() -> str`）與 `ExitCodeProvider`（`exit_code() -> int`）及 `format_output(output) -> tuple[str, int]`、雙層初始化 `ModuleEnv(workspace_root, register_closer)`（`on_init` / `on_warmup` / `on_close` 經轉接器自動橋接 `LifoResourceStack`）與 Re-export `TaskContext`、`YscbModule`、高階客戶端 `YscbClient(workspace_root, *, modules=())`（含 `local`/`connect` 工廠，無須匯入 `RuntimeDispatcher`）。 | P0 | `[P00:DR-04]`<br>`[P00:DR-05]`<br>`[P00:DR-06]` |
| **FR-06** | **活規格同步、分域測試拆整與無痛汰除對齊** | 1. 同步更新 `foundation.md`、`runtime.md`、`daemon.md`，新增 `surface/sdk.md`（Gate 0 1:1 綁定）與登記 `surface/cli.md` 草案（`Draft`）。<br>2. 將 25k LOC `verify_execution_live.py` 拆整為 `core_v2/tests/` 分域測試模組（含獨立 `_boot.py` 與 `_harness.py`）及輕量 `verify_execution_live.py` 主調度器（支援 `--suite` 靶向跑測）。<br>3. 依 `[P00:DR-02]` 與 `testing-sop` 鐵律 4 同步裁剪已退役過度設計之探針（`codec` `_LeafReusedTvEnvelope` 多層 MRO `TypeVar` 重映射與 `_CompoundUnionProbeDto` 多維評分、`SignalWakeupGuard` 內部多工探針 `drain_retired_on_main`/`is_installed`/`mark_inactive`/`dispatch_signal`/`sig_nums`、`FlightCascade`/`.turn.json`/局部 `modules=` `QUIESCE`/`handle_remote_flight_control` 與 `CONTROL_REQUEST`/1040-FD；**完整保留**有毒 `__str__` 異常隔離、`safe_exception_summary`、`TEARDOWN_ERROR` 與 `MODULE_DEGRADED` 測試），重寫對應精簡後單元/邊界測試，升級 Gate 0 多檔自審與 DAG/Living-Spec 守門，維持 `RC-01 ~ RC-08` 核心端到端場景 100% 通過並新增 `surface.sdk` 契約驗證套件。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-07]` |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 巢狀呼叫做為子任務或事件鏈觸發宣告為 `ConcurrencyMode.COALESCE` 之任務，或同呼叫棧自我重入 `PREEMPT` / `COALESCE` | 非頂層（`is_nested_call` 或 `in_event_chain`）之 `COALESCE` 自動降級為同工作區 `SERIALIZE`；同同步 `call_stack` 祖先已持有同一 `resource_key` 時，非 `SERIALIZE` 模式仍精確拋出 `ILLEGAL_LOCK_REENTRANCY` 並中止 Turn。 |
| **EC-02** | 全域 `QUIESCE` 期間安裝器意外崩潰未送出 `RESUME`，或外部 `HYBRID` 請求與冷啟動讀者同時連入 | 租約逾時到期後 `LifecycleReloadGate` 與 `WorkspaceDaemon` 自動自癒回復 `READY` 並喚醒排隊中的外部請求；冷進程繼續等待 `installer.lock`。 |
| **EC-03** | `DataclassCodec` 遇見多分支 `Union` 模糊匹配、無效型別（`bool` 混充 `int`、`NaN`、超限 `int64`、孤立代理字元或超深 JSON） | 嚴格依欄位型別宣告順序比對 `Union` 候選；對所有非法純量、不可變違反與越界深度一律拋出 `YscbError(ErrorCode.CODEC_VALIDATION_FAILED)`，絕不靜默吞掉或降級轉型。 |
| **EC-04** | `surface.sdk` 裝飾器順序反轉（`@on_event` 在 `@task` 之上或之下）、`GATED` 任務疊加事件／定時器、重複 CLI 路徑或缺少 `Module.id` | `@task` / `@on_event` / `@periodic` 任意順序疊加皆合成同一筆 `TaskMetadata`；類別定義期即攔截 `GATED` 綁事件/排程、重複 `cli` 路徑、空白 `id` 或無效方法簽名，確定性拋出 `ValueError`。 |
| **EC-05** | `Module.on_init` / `on_warmup` 預熱失敗或 `on_close` 釋放拋錯，以及跨平台 Linux `TCP_NODELAY` 與 Python 3.12 PEP 709 `symtable` 缺陷 | `WARMING` 單模組失敗隔離為 `MODULE_DEGRADED`；`on_close` 與註冊之 `closer` 經 `LifoResourceStack` 逆序清理，單點異常轉為 `TEARDOWN_ERROR` 不中斷底層資源釋放（`0 ResourceWarning`）；保留 `TCP_NODELAY` 與 AST 推導式 `Load` 補償。 |
| **EC-06** | `verify_execution_live.py` 拆檔後隔離測試中途失敗與環境清理 | 嚴格遵循工作區隔離、`try...finally` 回收 `ManagedProcessTree` 行程樹與暫存目錄，確保測試後 `git status` 與背景進程零殘留，且絕不觸碰根目錄 `.vscode/settings.json`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 體量與門面精簡度 | `core_v2/source/core/core/` 總行數由 `29,440 LOC` 收斂至 **~12,000–14,000 LOC**（絕對上限 `15,000 LOC`）；`core.surface.sdk.__all__` 精準鎖定為 **25 個核心符號**（符合 `P00` 目標 ~20–25）。 |
| **NFR-02** | Gate 0 靜態純淨度 | 100% 通過升級後 Gate 0 AST / Symtable / DAG 白名單 / Living-Spec 1:1 / 多檔自審守門（0 `Any`、0 `print`、0 未授權反射、0 工單噪訊註解、0 孤兒 `.md`）。 |
| **NFR-03** | 執行與依賴純淨度 | 全數實作 100% 僅依賴 Python 3.11+ 標準庫；保留 6 大功能域嚴格單向 DAG（`surface -> execution -> ... -> foundation`）。 |
| **NFR-04** | 驗證完備與回歸效能 | 拆分後之 `verify_execution_live.py` 全量實機跑測（含 `-W error::ResourceWarning`）100% 通過，且依 `R01` 定義之 `RC-01 ~ RC-08` 核心端到端場景與精簡後分域測試 100% 全綠；支援 `--suite` 分域秒級執行。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` Gate 0 複雜度限制不可復原**：先前 `<=6 params / <=75 LOC / <=3 depth` 限制迫使代碼碎化為平均 `19.7 LOC/fn`；本次須主動反向聚合回清晰線性流程，但保留零 `Any`/零 `print`/零 `getattr`/嚴格 DAG/Living-Spec 守門。
- **`[!NOTE]` Linux Loopback 必開 `TCP_NODELAY` 與 Python 3.12 PEP 709 `symtable` 補償**：`execution/rpc/channel.py` 之 `_enable_tcp_nodelay()` 與 Gate 0 之 `_collect_comprehension_loads_by_lineno` 必須原樣保留。
- **`[!NOTE]` `_ensure_live_host_boot_script` 與 Gate 0 自審拆檔連動**：原 `verify_execution_live.py` 以字串錨點硬切 `Path(__file__)` 產出宿主啟動腳本並僅單檔自審；拆檔至 `core_v2/tests/` 時須同步抽離 `_boot.py` 並將 `_audit_self_test_ast` 擴展至全部測試檔。
- **`[!NOTE]` Gate 0 全域與反思白名單約束**：`sub_module_design/` 禁止存在未登記的孤兒 `.md`；任何模組級不可變建構呼叫須在 `_IMMUTABLE_GLOBAL_CALLS` 登記（`surface/sdk` 採 `_DeclarativeMeta` 零反射掃描 `namespace.items()` 即可徹底免除新增反射豁免）。
- **`[!NOTE]` 不可觸碰根目錄 `.vscode/settings.json`**：工作區該檔含未提交本地設定，所有 `git` 操作嚴格指定路徑。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[CLI / YscbClient / Periodic / FileWatcher]
   │
   ▼  Stage 1: Ingress & Global Gate
RuntimeDispatcher.invoke() / LifecycleReloadGate (單一全域 QUIESCE 屏障, epoch: int)
   │  └─ validate_stage1_gates() (SecurityTier / Exposure / TTY / SelfMutationScope / ColdInstallerLockManager)
   ▼  Stage 2: Route & Transport
Local Direct / PersistentRpcSession / OneShotVenvHost (保留 10 欄位 CallPropagationContext，砍除跨倉 COALESCE)
   │
   ▼  Stage 3: Resource Coordinator (單一權威)
ResourceCoordinator.acquire() (PARALLEL | SERIALIZE + CrossProcessLockPaths 重入 | PREEMPT | 同倉頂層 COALESCE 單飛 StepFlight)
   │
   ▼  Stage 4: Step Execution (方案 B SDK 轉接橋)
Module (_DeclarativeMeta + 靜態 groups) -> to_yscb_module() -> ModuleEnv / TaskContext -> BoundTask.execute_encoded()
   │
   ▼  Stage 5: Turn Event Drain & LIFO Teardown
TurnEngine.execute_turn() -> DoubleBufferedEventQueue (UNORDERED/ORDERED) -> TurnScope.scoped_stack.close_all_lifo()
   └─ 透過 core.surface.sdk.format_output() (HumanRenderable / ExitCodeProvider) 統一對接 CLI 與 SDK 強型別回傳
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/codec.py` | Modify | 移除 MRO `TypeVar` 重映射、多維評分排序與靜態格點證明器，收斂為 Dataclass/基本型別純淨編解碼 (~700–900 LOC) |
| `core_v2/source/core/core/foundation/proc.py` | Modify | 將 `SignalWakeupGuard` 收斂為 `<100 LOC` 單主執行緒註冊器，保留 Job Object / POSIX PGID 與 `ManagedProcessTree` 骨幹 |
| `core_v2/source/core/core/execution/runtime/lineage_join.py` | Delete | 隨跨倉合流與 `FlightCascade` 退場物理刪除 |
| `core_v2/source/core/core/execution/runtime/{contracts,coordinator,dispatcher,gates,module_slot,route_index,step_host,turn_session,wire,worker_pool,__init__}.py` | Modify | 收斂 `CallPropagationContext` 至 10 欄位、預留 3 系統 `EventId` 常數、移除 `.turn.lock`/`.turn.json` 多幀與局部 `QUIESCE`（保留 `CrossProcessLockPaths`）、支援 `in_memory_modules` 並反碎片化聚合為 5 階段管道 |
| `core_v2/source/core/core/execution/daemon/service.py` | Modify | 收斂為全域 `QUIESCE`、扁平診斷佇列、移除 `WARMING` 交錯重載與 `CONTROL_REQUEST`、線性聚合方法（`__init__.py` 12 符號 `__all__` 維持不變） |
| `core_v2/source/core/core/surface/__init__.py` | Create | Domain 6 套件根初始化 |
| `core_v2/source/core/core/surface/sdk/{__init__,declarative,client}.py` | Create | 實作方案 B 25 符號自洽門面：`Module`/`TaskGroup`/`@task`/`@on_event`/`@periodic`、`Arg`/`Option`、`HumanRenderable`/`ExitCodeProvider`/`format_output`、`ModuleEnv`/Re-export `TaskContext`/`YscbModule`、`define_event`、`YscbClient`、`InMemoryModule` |
| `core_v2/sub_module_design/foundation/foundation.md` | Modify | 同步更新 `SignalWakeupGuard` / `codec` Living-Spec 簽名 |
| `core_v2/sub_module_design/execution/{runtime,daemon}.md` | Modify | 同步更新精簡後 10 欄位上下文、同倉單飛、全域 `QUIESCE` 與簡化後公開契約 |
| `core_v2/sub_module_design/surface/{sdk,cli}.md` | Create | `sdk.md` 作為 `core.surface.sdk` 1:1 Living-Spec；`cli.md` 登記為與 `sdk.md` 對齊之 `Draft` 草案 |
| `core_v2/tests/{__init__,_boot,_harness,test_gate0,test_foundation_fs,test_runtime_daemon,test_rc_e2e,test_surface_sdk}.py` | Create | 由 25k LOC 單檔拆整之分域測試與獨立 Boot/Harness 模組，按 `FR-06` 裁剪退役探針並新增 `surface.sdk` 契約測試 |
| `core_v2/verify_execution_live.py` | Modify | 精簡為支援 `--suite` 分域調度與全量執行之極薄驗證入口，更新 Gate 0 多檔自審與 DAG/Living-Spec 規則 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `_DeclarativeMeta(ABCMeta)` 零反射與 `Module.to_yscb_module()` 轉接縫**：`Module` 為獨立基類（不直接繼承 `YscbModule`），以免 `on_init(env: ModuleEnv)` 與 `YscbModule.on_init(workspace_root: HostPath)` 違反里氏替換及 `execution -> surface` 嚴格 DAG 禁令；`TaskGroup` 透過 `Module.groups: ClassVar[tuple[type[TaskGroup], ...]]` 靜態掛載（零執行期 `mount`），由 `_DeclarativeMeta` 遍歷 `namespace.items()` 零反射收集，並經 `Module.to_yscb_module()` 轉接給 `module_slot.py` 與 `LifoResourceStack`（不變動 `YscbModule` 與既有 19 測試模板）。
- **[P02:DR-02] `CallPropagationContext` 10 欄位與共享 `CrossProcessLockPaths` 保留界線**：僅砍除跨倉 `COALESCE` 欄位（`coalesce_callers`、`coalesce_flights`）及專屬的 `.turn.lock`/`.turn.json` 多幀協議（與 `HolderIdentity.flight_id/alt_owners`）；保留 `is_nested_call`、`in_event_chain`、`hot_workspaces`、`cold_shared_workspaces` 與 `CrossProcessLockPaths`（`.lock`/`.owner.json`/`.pin`），確保 `RC-07` 2-Daemon RPC、`RC-08` 事件鏈護欄、跨倉防回彈與同倉 `SERIALIZE` / `installer.lock` 不退化（相較 `[P00:DR-02]` 初稿微調登錄於 `§5.2`）。
- **[P02:DR-03] `surface/cli.md` 草案與 Gate 0 孤兒檔守門**：將 `surface/sdk.md` 納入 Gate 0 1:1 Living-Spec 強制校驗；將 `surface/cli.md`（狀態 `Draft`）列入 Gate 0 白名單允許存在但不強檢實作簽名，待 Wave 1.2 實作 `core.surface.cli` 時轉為 `Active`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# 1. Foundation (codec.py & proc.py)
class DataclassCodec:
    @staticmethod
    def encode(obj: object) -> JsonValue: ...
    @staticmethod
    def encode_typed(expected_type: object, obj: object) -> JsonValue: ...
    @staticmethod
    def encode_object(obj: object, *, expected_type: Optional[object] = None) -> MutableJsonObject: ...
    @staticmethod
    def encode_envelope(obj: object) -> MutableJsonObject: ...
    @staticmethod
    def decode_envelope(target_cls: type[T], raw: JsonValue) -> T: ...
    @overload
    @staticmethod
    def decode(target_cls: type[T], raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> T: ...
    @overload
    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> object: ...
    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> object: ...
    @staticmethod
    def canonical_hash(raw: object) -> str: ...
    @staticmethod
    def evict_module_prefix(module_prefix: str) -> None: ...

def infer_sequence_element_dataclass(fn: object, *, strict_unresolved: bool) -> tuple[bool, Optional[object]]: ...

class SignalWakeupGuard:
    def __init__(self, sig_nums: Sequence[int], on_signal: Callable[[], None], *, on_second_signal: Optional[Callable[[], None]] = None) -> None: ...
    def __enter__(self) -> "SignalWakeupGuard": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def install(self) -> None: ...
    def close(self) -> None: ...

# 2. Execution Runtime & Daemon (contracts.py, gates.py, daemon/service.py)
WORKSPACE_RELOADED_EVENT_ID: EventId = EventId("core.workspace_reloaded")
MODULE_INSTALLED_EVENT_ID: EventId = EventId("core.module_installed")
MODULE_REMOVING_EVENT_ID: EventId = EventId("core.module_removing")

@dataclass(frozen=True, slots=True)
class CallPropagationContext:
    turn_id: Optional[str] = None
    call_tree_id: Optional[str] = None
    call_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    lineage: CausalLineage = field(default_factory=CausalLineage)
    is_internal_trigger: bool = False
    is_nested_call: bool = False
    in_event_chain: bool = False
    from_hot_container: bool = False
    hot_workspaces: frozenset[HostPath] = frozenset()
    cold_shared_workspaces: frozenset[HostPath] = frozenset()

@dataclass(frozen=True, slots=True)
class QuiesceResumeResult:
    started: bool
    need_handoff: bool

class LifecycleReloadGate:
    @property
    def quiesce_epoch(self) -> int: ...
    @property
    def transition_seq(self) -> int: ...
    def lifecycle_scope(self) -> threading.RLock: ...
    def try_lifecycle_scope(self, timeout_sec: Optional[float] = None) -> Iterator[bool]: ...
    def has_any_active_work(self) -> bool: ...
    def has_any_quiesced(self) -> bool: ...
    def register_gate_listener(self, listener: Callable[[], None]) -> None: ...
    def is_globally_quiesced(self) -> bool: ...
    def is_globally_gated(self) -> bool: ...
    def is_call_gated_for_quiesce(self, target_mod: Optional[ModuleId]) -> bool: ...
    def try_begin_global_quiesce(self, drain_deadline: Optional[float] = None, *, leased: bool = False, pre_accepted_ids: frozenset[str] = frozenset()) -> bool: ...
    def record_quiesce_lease(self, lease_sec: float) -> None: ...
    def next_quiesce_wakeup(self) -> Optional[float]: ...
    def due_quiesce_epoch(self) -> Optional[int]: ...
    def postpone_due_lease(self, epoch: int, delay_sec: float) -> None: ...
    def schedule_deferred_resume(self, expected_epoch: Optional[int]) -> None: ...
    def run_global_resume_guarded(self, expected_epoch: Optional[int], body_fn: Callable[[], bool]) -> QuiesceResumeResult: ...
    # 注：保留既有 step/RPC 追蹤方法 (is_rpc_call_gated, enter/exit_rpc_call, enter/exit_host_step, host_step_scope, wait_for_unquiesced) 並於 runtime.md 1:1 同步

class RuntimeDispatcher:
    def try_quiesce_global(self, *, drain_deadline: Optional[float] = None, leased: bool = False) -> bool: ...
    def quiesce_global(self, grace_ms: int = 3000) -> None: ...
    def execute_daemon_quiesce_resume(self, *, expected_epoch: Optional[int], check_core_mutated: Callable[[], bool], on_before_warmup: Callable[[], None]) -> QuiesceResumeResult: ...
    def resume_from_quiesce(self, *, on_before_warmup: Optional[Callable[[], None]] = None) -> None: ...

@dataclass(frozen=True, slots=True)
class DaemonQuiesceControl:
    lease_sec: float = 10.0
    drain_timeout_sec: float = 3.0

@dataclass(frozen=True, slots=True)
class DaemonResumeControl:
    expected_epoch: Optional[int] = None

@dataclass(frozen=True, slots=True)
class DaemonReloadControl:
    modules: tuple[ModuleId, ...] = ()

class WorkspaceDaemon:
    def quiesce(self, lease_sec: float = 10.0, *, drain_timeout_sec: float = 3.0) -> bool: ...
    def resume_from_quiesce(self, *, expected_epoch: Optional[int] = None) -> bool: ...

# 3. Domain 6 Surface SDK (core/surface/sdk/__init__.py — 精準 25 符號 __all__，完全自洽零未匯出型別洩漏)
# Re-exports (10): CancellationToken, ConcurrencyMode, DispatchMode, EventMetadata, HostPath,
#   ProgressEvent, SecurityTier, TaskContext, TaskOutcome, YscbModule
#   (下游經由 TaskContext.invoke_task(task_id, input_obj, output_type=TOut) 呼叫子任務，免匯入 TaskMetadata；
#    亦保留 workspace_root, caller_cwd, caller_env, cancel_token, effective_priority, emit, emit_imm, report_progress)
# SDK Symbols (15 → 合計 25): Arg, Empty, ExitCodeProvider, HumanRenderable, InMemoryModule,
#   Module, ModuleEnv, Option, TaskGroup, YscbClient, define_event, format_output, on_event, periodic, task
@dataclass(frozen=True, slots=True)
class Empty: pass

@dataclass(frozen=True, slots=True)
class Arg:
    summary: str = ""
    name: Optional[str] = None

@dataclass(frozen=True, slots=True)
class Option:
    short: Optional[str] = None
    summary: str = ""
    long_name: Optional[str] = None

class HumanRenderable(Protocol):
    def render_text(self) -> str: ...

class ExitCodeProvider(Protocol):
    def exit_code(self) -> int: ...

def format_output(output: object) -> tuple[str, int]: ...
def define_event(event_id: str, payload_type: type[TPayload], *, ordered: bool = False, description: str = "") -> EventMetadata[TPayload]: ...

class ModuleEnv:
    workspace_root: HostPath
    def __init__(self, workspace_root: HostPath) -> None: ...
    def register_closer(self, fn: Callable[[], None]) -> None: ...

class TaskGroup:
    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...

class Module:
    id: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup], ...]] = ()
    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...
    def to_yscb_module(self) -> YscbModule: ...

def task(cli: Optional[str | tuple[str, ...]] = None, *, name: Optional[str] = None, summary: str = "", aliases: tuple[str, ...] = (), dispatch_mode: DispatchMode = DispatchMode.HYBRID, interactive_tty: bool = False, security: SecurityTier = SecurityTier.SAFE, lock: Optional[str] = None, concurrency: Optional[ConcurrencyMode] = None, timeout_ms: Optional[int] = None) -> Callable[[_TFn], _TFn]: ...
def on_event(event: EventMetadata[TPayload] | EventId | str, *, payload_filter: Optional[Mapping[str, Sequence[JsonPrimitive]]] = None, mapper: Optional[Callable[[Sequence[TPayload]], Optional[TIn]]] = None) -> Callable[[_TFn], _TFn]: ...
def periodic(interval_sec: float, *, enabled_config_key: Optional[str] = None, interval_config_key: Optional[str] = None) -> Callable[[_TFn], _TFn]: ...

class InMemoryModule:
    def __init__(self, module_id: str) -> None: ...
    def add_task(self, name: str, handler: Callable[..., object], *, summary: str = "", security: SecurityTier = SecurityTier.SAFE, lock: Optional[str] = None, concurrency: Optional[ConcurrencyMode] = None) -> "InMemoryModule": ...
    def to_yscb_module(self) -> YscbModule: ...

class YscbClient:
    def __init__(self, workspace_root: HostPath, *, modules: Sequence[Module | InMemoryModule] = ()) -> None: ...
    @classmethod
    def local(cls, workspace_root: HostPath, *modules: Module | InMemoryModule) -> "YscbClient": ...
    @classmethod
    def connect(cls, workspace_root: HostPath) -> "YscbClient": ...
    @overload
    def call(self, task_id: TaskId | str, req: object = None, *, output_type: type[TOut], cwd: Optional[HostPath] = None, env: Optional[Mapping[str, str]] = None, force_cold: bool = False, cancel_token: Optional[CancellationToken] = None, approval_scope: frozenset[TaskId] = frozenset(), on_progress: Optional[Callable[[ProgressEvent], None]] = None) -> TaskOutcome[TOut]: ...
    @overload
    def call(self, task_id: TaskId | str, req: object = None, *, output_type: None = None, cwd: Optional[HostPath] = None, env: Optional[Mapping[str, str]] = None, force_cold: bool = False, cancel_token: Optional[CancellationToken] = None, approval_scope: frozenset[TaskId] = frozenset(), on_progress: Optional[Callable[[ProgressEvent], None]] = None) -> TaskOutcome[JsonValue]: ...
    def call(self, task_id: TaskId | str, req: object = None, *, output_type: Optional[type[TOut]] = None, cwd: Optional[HostPath] = None, env: Optional[Mapping[str, str]] = None, force_cold: bool = False, cancel_token: Optional[CancellationToken] = None, approval_scope: frozenset[TaskId] = frozenset(), on_progress: Optional[Callable[[ProgressEvent], None]] = None) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...
    def close(self) -> None: ...
    def __enter__(self) -> "YscbClient": ...
    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...
```

- **方法簽名與參數綁定規約**：`Module` / `TaskGroup` 任務方法僅允許 `(self, ctx: TaskContext)`（無參，自動推導 `input_type = Empty` 且於無 `mapper` 的 `@on_event` 自動綁定預設回傳 `Empty()` 之工廠）或 `(self, req: TIn, ctx: TaskContext)`（`TIn` 由 `req` 型別註解推導）；回傳型別為 `None` 時自動轉為 `output_type = Empty`（回傳 `Empty()`）。暴露層級依宣告自動推導（含 `cli` $\to$ `CLI_AND_SDK`；無 `cli` 具 `@task` $\to$ `SDK_ONLY`；僅 `@on_event`/`@periodic` $\to$ `INTERNAL_TRIGGER`）；`cli` 非空且 `summary == ""` 時依序取方法 Docstring 首行或 `f"Execute {task_id}"` 滿足 `CliBindingSpec` 非空約束；`lock` 非空且未指定 `concurrency` 時預設為 `ConcurrencyMode.SERIALIZE`。
- **錯誤與例外契約 (Error & Exception Contracts)**：非法 DTO 型別／深度拋出 `YscbError(CODEC_VALIDATION_FAILED)`；裝飾器或 `Module` 定義違法（重複 CLI、`GATED`+事件/定時、缺 `id`、無效簽名）於類定義期拋出 `ValueError`；同棧非法重入拋出 `ILLEGAL_LOCK_REENTRANCY`；生命週期釋放單點失敗隔離為 `TEARDOWN_ERROR`。
- **階段決策紀錄**：`[P03:DR-01]` `ModuleEnv` 為無狀態模組保留 `on_init` 省略彈性，`TaskContext` 亦透傳現有執行期上下文，Wave 1.2 再於 `ModuleEnv` 擴充 `vfs`/`contributes`/`storage` 欄位而不破壞簽名。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與檔案清單中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-04 指標與 Gate 0 單向 DAG 約束
- **靈魂拷問與防護解法**：若 `@on_event` 疊加在 `@task` 上方或下方會否失序？透過統一不可變裝飾包裝規格物件合併屬性（與順序無關），並在 `_DeclarativeMeta.__new__` 一次合成任務描述解決。如何避免 `Module.on_init(env: ModuleEnv)` 與 `YscbModule.on_init(workspace_root: HostPath)` 產生 Liskov 衝突及 `execution -> surface` 反向依賴？讓 `Module` 保持獨立基類並以 `to_yscb_module() -> YscbModule` 適配器橋接現有 `module_slot.py` 與 `LifoResourceStack`。系統事件（`core.workspace_reloaded`/`core.module_installed`/`core.module_removing`）依檔位 A 先於 `contracts.py` 預留 `EventId` 常數，待 Wave 1.2 `packaging`/`metadata` 接線發射源。跨倉單跳與同倉跨進程重入依賴 `CrossProcessLockPaths`（`.lock`/`.owner.json`/`.pin`）與 `CallPropagationContext` 之 10 欄位安全旗標，故僅精簡跨倉 `COALESCE` 專用 2 欄位（`coalesce_callers`/`coalesce_flights`）與多跳 `.turn.lock`/`.turn.json` 協議，絕不削弱 `RC-06`/`RC-07`/`RC-08` 安全保護。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **底座專題** | `core_v2/sub_module_design/foundation/foundation.md` | Modify | 同步簡化後 `SignalWakeupGuard` 與 `codec` 簽名 |
| **運行與守護** | `core_v2/sub_module_design/execution/{runtime,daemon}.md` | Modify | 同步 10 欄位上下文、同倉單飛、全域 `QUIESCE` 與簡化後契約 |
| **對外門面規格** | `core_v2/sub_module_design/surface/{sdk,cli}.md` | Create | `sdk.md` 1:1 活規格；`cli.md` 登記對齊之 Wave 1.2 `Draft` 草案 |
| **微觀註解** | `core_v2/source/core/core/**/*.py` Docstrings | Modify | 更新精簡模組與 `surface.sdk` 公開契約 Docstring（零工單噪訊） |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本重構計畫變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確立先執行 `Pre-Code Analyze Gate` 盲審核對，再按 `Foundation` + `Surface SDK` $\to$ `Runtime` + `Daemon` $\to$ `Tests / Gate 0 / RC-01~08` 順序收斂並於全量實機全綠後進入 Phase 06 盲審。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：執行 `Pre-Code Analyze Gate` 唯讀盲眼審查，確認 `P01-05_auto.md` 完整溯源 `[P00:DR-01]`~`[P00:DR-07]` 且無檔位 A 越界或憲法紅線衝突
- [x] **TASK-02**：精簡 `foundation/codec.py` 與 `foundation/proc.py` 並同步更新 `foundation.md`（目標 `codec ~700–900 LOC`、`SignalWakeupGuard <100 LOC`，公開簽名 100% 相容）
- [x] **TASK-03**：重構精簡 `execution/runtime/`（刪除 `lineage_join.py`、收斂 `CallPropagationContext` 至 10 欄位、預留 3 系統 `EventId` 常數、取消跨倉 `COALESCE`/`.turn.lock`/`.turn.json` 並保留 `CrossProcessLockPaths`、收斂單一全域 `QUIESCE`、擴充 `DispatcherHostOptions.in_memory_modules: tuple[YscbModule, ...] = ()` 以支援 `YscbClient.local` 記憶體模組執行、反碎片化聚合 5 階段管道）
- [x] **TASK-04**：重構精簡 `execution/daemon/service.py` 與 `__init__.py`（全域 `QUIESCE` 保留 `lease_sec`/`drain_timeout_sec`/`expected_epoch`/`need_handoff`、扁平診斷、移除 `WARMING` 交錯重載與 `CONTROL_REQUEST`、線性聚合）
- [x] **TASK-05**：新增 `core/surface/` 與 `core/surface/sdk/`（精準 25 符號 `__all__`、獨立 `Module` + 靜態 `groups` + `to_yscb_module()`、`@task`/`@on_event`/`@periodic`、`define_event`、`Arg`/`Option`、`HumanRenderable`/`ExitCodeProvider`/`format_output`、`ModuleEnv`/Re-export `TaskContext` 與 `YscbModule`、`YscbClient(workspace_root, *, modules=())` + `local`/`connect`、`InMemoryModule`）並建立 `surface/{sdk,cli}.md`
- [x] **TASK-06**：將 `verify_execution_live.py` 拆整為 `core_v2/tests/` 分域套件與獨立 `_boot.py`/`_harness.py`，依 `FR-06` 裁剪退役探針並重寫對應測試，升級 Gate 0 多檔自審、`core.surface.sdk` DAG 與 Living-Spec 守門，補齊 `test_surface_sdk.py` 並達成 `RC-01 ~ RC-08` 與全量實機 100% 通過
- [x] **TASK-DOC**：同步完成 `foundation.md`、`runtime.md`、`daemon.md`、`surface/{sdk,cli}.md` 活規格與全部源碼公開 Docstrings（零工單噪訊）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| `TASK-03` | `Minor` | `CallPropagationContext` 原擬縮至 5 欄位，考量 `RC-07` 2-Daemon RPC（非空 `call_stack` 下 `is_nested_call=False`）與 `RC-08` / 跨倉防回彈，保留 10 欄位僅砍除 `COALESCE` 專用 2 欄位及 `CoalesceCallerView` | 登錄於 `[P02:DR-02]` 並保留完整防護 |
| `TASK-03` | `Minor` | 原稱移除 5 檔 `.pin/.turn.json`，考量 `CrossProcessLockPaths`（`.lock`/`.owner.json`/`.pin`）同時支撐 `ColdInstallerLockManager` 與同倉 `SERIALIZE` 重入，僅刪除 `.turn.lock`/`.turn.json` 多幀協議與遠端單飛驅逐 | 登錄於 `FR-01` 與 `[P02:DR-02]` |
| `TASK-02~05` | `Minor` | `NFR-01` 原估全核 `12,000–14,000 LOC`（上限 `15,000 LOC`）與 `FR-03` 估 `codec.py ~700–900 LOC`，實測依 `P00` 復用保留之 OS/基建骨幹（`foundation` 不含 `codec` `2,580` + `filesystem/fs` `2,033` + `rpc` `2,370` + `lifecycle` `834` + `event` `495` + `runtime` 復用 4 檔 `3,201` + 套件根 `6` = `11,519 LOC`）、`runtime` 契約/封裝（`1,241 LOC`）加新建 `surface/sdk`（`998 LOC`）即佔 `13,758 LOC`；目標精簡區（含 `codec.py` `2,965 -> 1,433 LOC`、管道 `4,165 LOC`、`daemon` `1,397 LOC`）實裁 `-9,685 LOC`（`-51% ~ -55%`），全核收斂至 `20,753 LOC`（37 檔），測試集則自 `25,167 LOC` 收斂至 `9,541 LOC`（`-62.1%`），避免為湊行數破壞已驗證骨幹與 `RC-01 ~ RC-08` 完整性 | 透明登錄於本表與 `P06_test_plan.md` 供 UX 驗收確認 |
| `TASK-06` | `Minor` | Windows 上 `RC-07` 舊測直接發送 `CTRL_C_EVENT` 會波及共享 Console 之 IDE 後端行程，且背景測試子行程未加 `CREATE_NO_WINDOW` 會跳窗搶佔系統焦點；於 Windows 改以 `CREATE_NEW_PROCESS_GROUP` + `SW_HIDE` + `CTRL_BREAK_EVENT`（`_boot.py` 對應 `SIGBREAK -> default_int_handler` 走入完全相同 `KeyboardInterrupt`/`ColdTurnRunner`/exit `130`/LIFO 路徑），並於 `foundation/proc.py` 補齊 `CREATE_NO_WINDOW` 與 Win32 `GetConsoleWindow` + `GenerateConsoleCtrlEvent` 保護以避開 Python 3.12 無主控台 `os.kill` `SystemError` | 公開簽名 0 異動，POSIX 維持 `SIGINT`，`RC-07` 與全套件 100% 實機通過 |
