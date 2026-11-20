# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 內核精簡、統一運行資料流聚合與 SDK 門面設計  
> 建立日期：2026-11-20  
> 所屬主計畫：無（獨立 Full Track 重構計畫）  
> 狀態：Discussing  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於完整實機驗證基線（`9847b1a`，封存備份於 Git Tag `archive/core-v2-maximalist`）確立後，評估並大刀精簡 `core_v2/` 中低 ROI 的過度防禦與對抗性拓撲設計、聚合因舊 Gate 0 複雜度守門遭切碎的內聚邏輯以統一單向運行資料流，並先確立簡潔有力的 `surface.sdk` 契約再推進 Wave 1.2。本階段先建立備份 Tag 與立項（暫不展開調研），隨即 `/pause` 留待下次繼續。
- **核心目標**：
  1. 將現行 Wave 1.1 內核體量由 `29,440 LOC`（1,494 函式）精簡聚合至 `~12,000–14,000 LOC`，使完整 6 域 `Core 2.0` 控制在比 `Core 1.x` 更精實之微內核規模。
  2. 將分散於 4 套狀態表與 11 個回呼互掛物件的執行期資料流，收斂為清楚的「單向 5 階段執行管道」（Ingress Gate → Route & Transport → Resource Coordinator → Step Execution → Turn Event Drain & LIFO Teardown）。
  3. 設計並驗證高內聚、低樣板的 `surface.sdk`（約 20–25 核心符號）與 `TaskContext` 能力注入邊界（VFS / Config / Storage / Logger / CLI 參數與雙軌輸出），確保後續 Wave 1.2 實作不再回頭震盪內核簽名。
  4. 以 `R01` 定義之 `RC-01 ~ RC-08` 真實端到端基準案例 100% 通過作為不可退讓底線，並將 25k LOC 單檔測試拆整為秒級分域測試集。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 完整保留並直接復用已實機驗證之 OS/基礎骨幹：`execution/rpc/channel.py`（多工 Socket、`CALL_ACCEPTED`、`TCP_NODELAY`）、`execution/runtime/worker_pool.py` & `worker_entry.py` & `module_slot.py`、`execution/event/engine.py`、`execution/lifecycle/engine.py`、`filesystem/fs/`（原子寫入、`FileLock`、`PollingDirectoryWatcher`）與 `foundation/proc.py` 核心行程樹管理；僅做適度去碎化聚合而非重造輪子。
  - 待下次 `/continue` 進入 P00 深化與調研時，比對 `1.x` 真實模組（`vscode-support`、`knowledge-db`、`gdrive-support`）反推 SDK 體驗。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `1.x` 主線模組源碼（`ys_codebase/source/*`）與正式發布設定。
  - 不復原已刻意移除之 Gate 0 複雜度上限（參數數 / LOC / 縮排深度）；保留零 `Any`/零 `print`/嚴格 DAG 白名單與 Living-Spec 對齊守門。
  - 暫不於本階段啟動 Wave 1.2 新域實作（`vfs`/`space`/`storage`/`config`/`contributes`/`packaging`），待本計畫確認精簡後內核與 `surface.sdk` 契約後銜接推進。
- **架構影響範圍**：
  - 核心瘦身與聚合：`core_v2/source/core/core/execution/runtime/{coordinator,lineage_join,turn_session,dispatcher,gates,contracts,step_host}.py`、`core_v2/source/core/core/execution/daemon/service.py`、`core_v2/source/core/core/foundation/{codec,proc}.py`。
  - 活規格同步：`core_v2/sub_module_design/execution/{runtime,daemon}.md`、`core_v2/sub_module_design/foundation/foundation.md` 與新增 `core_v2/sub_module_design/surface/{sdk,cli}.md`。
  - 驗證套件：`core_v2/verify_execution_live.py`（按域拆分並聚焦 `RC-01 ~ RC-08` 與真實核心回歸）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 完整保留備份基準點**：於 `9847b1a` 建立 annotated Git Tag `archive/core-v2-maximalist`，永久封存 100% 實機全綠之完整版 Wave 1.1（含跨倉多跳 `COALESCE`、五檔 `.turn.json` 協議、完整泛型 `codec` 與 25k LOC 測試），未來若真遇極端場景可隨時參照移植，平時零維護利息。
- **[P00:DR-02] 暫定減法四方向（待下次討論逐項拍板）**：
  1. `COALESCE` 收斂為同工作區頂層單飛（跨倉巢狀退回 `SERIALIZE`、事件鏈不與頂層前景跨層合流、移除 `FlightCascade` 與跨進程五檔 `.pin/.turn.json` 協議、`CallPropagationContext` 縮減至 5 欄位）。
  2. `QUIESCE` 收斂為單一全域排空屏障（取消逐模組局部租約、執行期動態 `venv_group` 遷移與 `WARMING` 半途交錯重載狀態機）。
  3. `foundation/codec.py` 專注不可變 Dataclass DTO 邊界編解碼（砍除多層泛型 MRO `TypeVar` 重映射與 Union 多維歧義評分排名）。
  4. 反碎片化聚合線性流程 + `SignalWakeupGuard` 單執行緒化 + 測試集分域瘦身（保留 `RC-01 ~ RC-08` 100% 覆蓋）。
- **[P00:DR-03] 先行立項暫停原則**：本輪先完成備份 Tag 與計畫立項，暫不啟動調研與代碼刪改，直接執行 `/pause` 凍結上下文。

---

## 3. 開放議題與確認紀錄

- [ ] 待確認（下次 `/continue` 優先對齊）：上述 4 項減法邊界中，是否有特定場景（例如同倉事件鏈與前景 `COALESCE` 或局部模組 `QUIESCE`）希望保留？
- [ ] 待確認：目標 `surface.sdk` 的 Task 宣告風格（簡化 OOP 類別 vs 裝飾器語法糖、無參 `EmptyInput`、`Annotated` 整合 CLI 參數、`render_human` 雙軌輸出）與 `TaskContext` 能力注入清單。
- [ ] 待確認：五維度防放水反詰探針逐項收斂後，拍板本計畫 `P00_discuss.md` 轉為 `Confirmed` 並決定是否先做輕量調研或直進 `P01`。
