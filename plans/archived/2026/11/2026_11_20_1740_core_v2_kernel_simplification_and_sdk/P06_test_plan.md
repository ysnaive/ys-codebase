# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 內核精簡、統一運行資料流聚合與 SDK 門面設計  
> 建立日期：2026-11-21  
> 所屬主計畫：無（獨立 Full Track 重構計畫）  
> 狀態：Passed  
> 模型：Gemini 4 Neon (High)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 靜態架構守門 (`Gate 0`) | 驗證 37 個核心檔與全部分域測試檔零 `Any`/`print`/`getattr`/`# type: ignore`/工單噪訊註解、嚴格 6 域單向 DAG（含 `core.surface.sdk` 負向違規攔截）、跨套件 `__all__` 邊界、8 份活規格（含 `surface/sdk.md` 25 符號 1:1 與 `surface/cli.md` `Draft` 白名單）與多檔自審 | FR-04, FR-05, FR-06, NFR-02, NFR-03 | `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0` |
| **FT-02** | 域單元與邊界測試 (`foundation_fs`) | 驗證簡化後 `DataclassCodec`（嚴格純量/宣告序 `Union`/深度/驅逐/`infer_sequence_element_dataclass`）、單執行緒 `SignalWakeupGuard`、`ManagedProcessTree`、`safe_exception_summary` 有毒 `__str__` 隔離、原子寫入與 symlink containment、`FileLock`、`PollingDirectoryWatcher`、`DoubleBufferedEventQueue`、`LifoResourceStack` 與 `MultiplexedChannel` | FR-03, FR-06, EC-03, EC-05 | `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs` |
| **FT-03** | SDK 契約與端到端測試 (`surface_sdk`) | 驗證 `core.surface.sdk.__all__` 精準 25 符號零洩漏、`Module` + 靜態 `groups`、任意順序疊加 `@task`/`@on_event`/`@periodic`、字串 `EventId` 弱訂閱、`Arg`/`Option`、`define_event`、編譯期 `ValueError` 防呆、`HumanRenderable`/`ExitCodeProvider`/`format_output`、`ModuleEnv` LIFO 與 `MODULE_DEGRADED`/`TEARDOWN_ERROR` 隔離、`InMemoryModule` 與 `YscbClient` | FR-05, EC-04, EC-05, NFR-01 | `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk` |
| **FT-04** | 運行與守護整合測試 (`runtime_daemon`) | 驗證同倉頂層 `COALESCE` 單飛（`equivalence_key`/`PriorityHandle`/取消/Step 5 錯誤廣播）、巢狀與事件鏈 `COALESCE -> SERIALIZE` 降級、`ILLEGAL_LOCK_REENTRANCY`、`PREEMPT`、`CrossProcessLockPaths` 與跨進程 `SERIALIZE` 重入、單一全域 `QUIESCE` 屏障（拒收 `modules` 與 `CONTROL_REQUEST`、租約自癒、`expected_epoch`、延遲重載）、SHA-256 `MUTATES_CORE` 忽略純時間戳與交棒、10 欄位 `CallPropagationContext`、3 系統 `EventId`、`in_memory_modules` 與扁平診斷 | FR-01, FR-02, FR-04, EC-01, EC-02, EC-05 | `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite runtime_daemon` |
| **FT-05** | 實機多進程端到端回歸 (`rc_e2e` + 全量) | 驗證 `R01` 定義之 `RC-01 ~ RC-08` 真實多進程/獨立 Venv/Daemon/PTY/取消/熱重載/核心交棒/中斷樹回收/跨進程鎖與安全守門 100% 通過，且全量跑測 `0 ResourceWarning`、零殘留孤兒行程與背景無窗執行 | FR-01 ~ FR-06, EC-01 ~ EC-06, NFR-04 | `python -B -W error::ResourceWarning core_v2/verify_execution_live.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Pass` | `Gate 0 verified (5.67s)`：37 個核心檔、8 份活規格（含 `surface/sdk.md` 25 符號 `__all__` 1:1）+ `surface/cli.md` (`Draft`)、`verify_execution_live.py` 與 `core_v2/tests/*.py`（8 檔）全部通過 | 2026-11-21 14:38 |
| **FT-02** | `Pass` | `suite 'foundation_fs' completed (1.30s)`：Codec/Proc/SignalWakeupGuard/FS/Event/Lifecycle/RPC 邊界與有毒 `__str__` 全過，`0 ResourceWarning` | 2026-11-21 14:38 |
| **FT-03** | `Pass` | `suite 'surface_sdk' completed (0.50s)`：`core.surface.sdk` 25 符號、`Module`/`TaskGroup`/裝飾器疊加/`EC-04`/`EC-05`/`InMemoryModule`/`YscbClient` 全過，`0 ResourceWarning` | 2026-11-21 14:38 |
| **FT-04** | `Pass` | `suite 'runtime_daemon' completed (12.61s)`：7 大運行與守護子套件全過（含全域 `QUIESCE`、SHA-256 `MUTATES_CORE` 忽略 `os.utime` 與交棒、跨進程 `SERIALIZE` 重入、扁平診斷），`0 ResourceWarning` | 2026-11-21 14:38 |
| **FT-05** | `Pass` | `ALL SELECTED LIVE VERIFICATIONS PASSED (gate0, foundation_fs, surface_sdk, runtime_daemon, rc_e2e, 95.95s, 0 ResourceWarning)`：`RC-01 ~ RC-08` 全綠（`rc_e2e` 75.56s），零孤兒行程、零殘留檔案、Windows 全背景無窗執行 | 2026-11-21 14:38 |

### 量化與體量對照摘要
- **核心體量 (`core_v2/source/core/core/`, 37 檔)**：`20,753 LOC`（`foundation`: 4,013、`filesystem`: 2,033、`execution/event`: 495、`execution/lifecycle`: 834、`execution/rpc`: 2,370、`execution/runtime`: 8,607、`execution/daemon`: 1,397、`surface/sdk`: 998、套件根: 6）；目標重構模組實裁 `-9,685 LOC`（`-51% ~ -55%`），`NFR-01` 骨幹保留算術偏差詳見 `P01-05_auto.md` §5.2。
- **驗證套件體量 (`core_v2/tests/` 8 檔 + `verify_execution_live.py` 145 行)**：`9,541 LOC`（自 `25,167 LOC` 單檔精簡 `-62.1%`，支援 `--suite` 秒級靶向執行；依 `FR-06` 裁剪退役之多層泛型 MRO/多維 Union/多工 SignalWakeupGuard/`FlightCascade`/局部 `QUIESCE`/1040-FD 探針，100% 保留有毒 `__str__` 異常隔離與 `RC-01 ~ RC-08`）。
- **基準與工作區保護**：`archive/core-v2-maximalist` Tag（`9847b1a`）、`ys_codebase/source/*` 與 `.vscode/settings.json` 均零異動。

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0,surface_sdk` 秒級檢驗 Gate 0 與 25 符號 `core.surface.sdk` 門面體驗（`Module`/`TaskGroup`/`@task`/`@on_event`/`InMemoryModule`/`YscbClient`） | `[跳過/免測]` | 開發者明示免測（2026-11-21） |
| **UX-02** | 審閱 `core_v2/sub_module_design/surface/{sdk,cli}.md` 與 `P01-05_auto.md` §5.2 偏差紀錄（含 `NFR-01` 骨幹保留體量 `20,753 LOC` 與 Windows 背景無窗訊號策略），確認可進入 Phase 07 結案與後續 Wave 1.2 | `[跳過/免測]` | 開發者明示免測（2026-11-21） |
