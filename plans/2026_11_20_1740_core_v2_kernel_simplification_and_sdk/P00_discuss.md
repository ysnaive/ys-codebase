# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 內核精簡、統一運行資料流聚合與 SDK 門面設計  
> 建立日期：2026-11-20  
> 所屬主計畫：無（獨立 Full Track 重構計畫）  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於完整實機驗證基線（`9847b1a`，封存備份於 Git Tag `archive/core-v2-maximalist`）確立後，評估並大刀精簡 `core_v2/` 中低 ROI 的過度防禦與對抗性拓撲設計、聚合因舊 Gate 0 複雜度守門遭切碎的內聚邏輯以統一單向運行資料流，並先確立簡潔有力的 `surface.sdk` 契約再推進 Wave 1.2。
- **核心目標**：
  1. 將現行 Wave 1.1 內核體量由 `29,440 LOC`（1,494 函式）精簡聚合至 `~12,000–14,000 LOC`，使完整 6 域 `Core 2.0` 控制在比 `Core 1.x` 更精實之微內核規模。
  2. 將分散於 4 套狀態表與 11 個回呼互掛物件的執行期資料流，收斂為清楚的「單向 5 階段執行管道」（Ingress Gate → Route & Transport → Resource Coordinator → Step Execution → Turn Event Drain & LIFO Teardown）。
  3. 設計並驗證高內聚、低樣板的 `surface.sdk`（約 20–25 核心符號）與 `ModuleEnv` / `TaskContext` 能力注入邊界，確保後續 Wave 1.2 實作不再回頭震盪內核簽名。
  4. 以 `R01` 定義之 `RC-01 ~ RC-08` 真實端到端基準案例 100% 通過作為不可退讓底線，並將 25k LOC 單檔測試拆整為秒級分域測試集。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 完整保留並直接復用已實機驗證之 OS/基礎骨幹：`execution/rpc/channel.py`（多工 Socket、`CALL_ACCEPTED`、`TCP_NODELAY`）、`execution/runtime/worker_pool.py` & `worker_entry.py` & `module_slot.py`、`execution/event/engine.py`、`execution/lifecycle/engine.py`、`filesystem/fs/`（原子寫入、`FileLock`、`PollingDirectoryWatcher`）與 `foundation/proc.py` 核心行程樹管理；僅做適度去碎化聚合而非重造輪子。
  - 以 `1.x` `module:dev`（`ys_codebase/source/dev/`，涵蓋 `contributes/core.json` 715 行與 `scripts/cli.py` 436 行）作為零心智負擔 SDK 體驗主要對照基準，輔以 `vscode-support` 對照事件訂閱疊加手感（消滅 ~1,150 行 `1.x` CLI/JSON 樣板碼），暫不納入過於龐大的 `knowledge-db` 索引細節（留待 Wave 3）。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `1.x` 主線模組源碼（`ys_codebase/source/*`）與正式發布設定。
  - 不復原已刻意移除之 Gate 0 複雜度上限（參數數 / LOC / 縮排深度）；保留零 `Any`/零 `print`/零 `getattr`/嚴格 DAG 白名單與 Living-Spec 對齊守門。
  - **採檔位 A 範疇鎖定**：本計畫不實作 Wave 1.2 新域實體（`vfs`/`space`/`storage`/`metadata`/`packaging`）、不實作 `surface.cli` 完整命令列解析器與 `HelpRenderer`、不實作 `dev 2.0` 靜態 AST `tasks.index.json` 編譯器，亦暫不加入 `SubscriptionRouteSpec.enabled_by`（無回溯成本之額外擴充，維持邏輯內聚）。
- **架構影響範圍**：
  - 核心瘦身與聚合：`core_v2/source/core/core/execution/runtime/{coordinator,lineage_join,turn_session,dispatcher,gates,contracts,step_host}.py`、`core_v2/source/core/core/execution/daemon/service.py`、`core_v2/source/core/core/foundation/{codec,proc}.py`。
  - SDK 公開門面與活規格：新增 `core_v2/source/core/core/surface/sdk/`，同步更新 `core_v2/sub_module_design/execution/{runtime,daemon}.md`、`core_v2/sub_module_design/foundation/foundation.md` 與新增 `core_v2/sub_module_design/surface/{sdk,cli}.md`（`cli.md` 固化與 `sdk.md` 對齊之規格草案）。
  - 驗證套件：`core_v2/verify_execution_live.py`（按域拆分並保留 `RC-01 ~ RC-08` 100% 覆蓋，補齊 `surface.sdk` 契約驗證）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 完整保留備份基準點**：於 `9847b1a` 建立 annotated Git Tag `archive/core-v2-maximalist`，永久封存 100% 實機全綠之完整版 Wave 1.1（含跨倉多跳 `COALESCE`、五檔 `.turn.json` 協議、完整泛型 `codec` 與 25k LOC 測試），未來若真遇極端場景可隨時參照移植，平時零維護利息。
- **[P00:DR-02] 確認減法四方向（全數拍板，無例外保留項）**：
  1. `COALESCE` 收斂為同工作區頂層單飛（跨倉巢狀退回 `SERIALIZE`、事件鏈不與頂層前景跨層合流、移除 `FlightCascade` 與跨進程五檔 `.pin/.turn.json` 協議、`CallPropagationContext` 縮減至 5 欄位）。
  2. `QUIESCE` 收斂為單一全域排空屏障（取消逐模組局部租約、執行期動態 `venv_group` 遷移與 `WARMING` 半途交錯重載狀態機）。
  3. `foundation/codec.py` 專注不可變 Dataclass DTO 邊界編解碼（砍除多層泛型 MRO `TypeVar` 重映射與 Union 多維歧義評分排名）。
  4. 反碎片化聚合線性流程 + `SignalWakeupGuard` 單執行緒化 + 測試集分域瘦身（保留 `RC-01 ~ RC-08` 100% 覆蓋）。
- **[P00:DR-03] 先行立項暫停原則**：本輪先完成備份 Tag 與計畫立項，暫不啟動調研與代碼刪改，直接執行 `/pause` 凍結上下文（已於 `/continue` 恢復推進）。
- **[P00:DR-04] `surface.sdk` 方案 B 宣告風格與靜態任務約束**：以 `module:dev`（輔以 `vscode-support`）為基準，採 `class XxxModule(Module)` 內 `@task` / `@on_event` / `@periodic` 方法裝飾器（大模組支援 `TaskGroup` 掛載子群組），兼顧零全域單例、顯式 DI 與低樣板量；支援 `@task` 與 `@on_event` 疊加宣告及字串 `EventId` 弱耦合選配訂閱；生產模組 100% 靜態 Task 宣告（禁止執行期或 `on_init` 動態註冊訂閱，防範 Tier 1 惰性載入雞生蛋死結與重啟狀態漂移），動態記憶體組裝僅限測試治具（`InMemoryModule`）；暫不實作 `@on_event` 之 `enabled_by` 以維持邏輯內聚。
- **[P00:DR-05] CLI 參數單一真理與雙軌輸出／語意退出碼規約**：Input 不可變 `@dataclass` 透過 `Annotated[T, Arg/Option]` 作為靜態索引、CLI 解析、`--help` 與 `DataclassCodec` 唯一真理；`--json`、`--help`、`--cold` 由入口統一接管；Output DTO 透過選配協定 `render_text() -> str` 與 `exit_code() -> int`（預設 `0`）承接人類排版與失敗報告語意退出碼，且不影響 SDK 強型別回傳值。
- **[P00:DR-06] 雙層初始化切分與能力注入邊界**：模組進程內內部物件初始化走生命週期方法 `on_init(self, env: ModuleEnv)` + 選配 `on_warmup(env)` + `on_close()`（底層自動橋接 `LifoResourceStack`，免回傳清理閉包）；宿主工作區磁碟產物初始化一律透過系統領域事件（`core.workspace_reloaded`、`core.module_installed`、`core.module_removing`）觸發 `Task`；能力注入分層為工作區級 `ModuleEnv` 與請求級 `TaskContext`（本計畫接線 Wave 1.1 既有能力並固化 Wave 1.2 擴充插槽），對外唯一入口 `core.surface.sdk`（目標 ~20–25 符號）。
- **[P00:DR-07] 檔位 A 實作範疇鎖定與直進 P01**：交付範疇鎖定為檔位 A（Wave 1.1 內核瘦身聚合 + 分域測試瘦身保 `RC-01 ~ RC-08` 全綠 + `core.surface.sdk` 公開門面與 `surface/{sdk,cli}.md` 活規格）；五維度防放水反詰探針全數收斂，不額外開立調研，定稿後直接推進 `P01`。

---

## 3. 開放議題與確認紀錄

- [x] 已拍板（`[P00:DR-02]`）：四項精簡邊界全數依提案執行，無例外保留項。
- [x] 已拍板（`[P00:DR-04]` ~ `[P00:DR-06]`）：採方案 B 靜態宣告、DTO 選配 `render_text()`/`exit_code()`、不實作 `enabled_by`，並確立 `on_init`/`on_warmup`/`on_close` 與系統領域事件雙層初始化切分及 `ModuleEnv`/`TaskContext` 邊界。
- [x] 已拍板（`[P00:DR-07]`）：採檔位 A 範疇鎖定，五維度防放水反詰探針完成收斂，定稿 `P00_discuss.md` 為 `Confirmed` 並直進 `P01`。
