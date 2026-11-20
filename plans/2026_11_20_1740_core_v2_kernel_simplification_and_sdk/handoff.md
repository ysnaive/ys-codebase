# 當前進度與暫停交接現場 (Handoff Context)

> 暫停時間：2026-11-20 17:40  
> 所屬計畫：2026_11_20_1740_core_v2_kernel_simplification_and_sdk  
> 當前所在階段：Phase 00 (狀態: Discussing)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 現場已完成事項
- [x] 完成 `core_v2/` 遠端同步稽核與本地剩餘缺陷／跨平台缺陷修補（含 `rpc/channel.py` 補上 `TCP_NODELAY` 消除 Linux 40ms 延遲 ACK、Python 3.12 PEP 709 `symtable` 相容修復、新增 `_verify_audit_remediation_regressions`），完整實機驗證 `python3 -B core_v2/verify_execution_live.py` 100% 通過（Gate 0 + RC-01~RC-08 + 全正交域測試、0 ResourceWarning、0 孤兒行程/執行緒）。
- [x] 已於分支 `core_v2` 提交 `9847b1a` 並確認 Google Drive `repo/main/core_v2` 雲端同步一致。
- [x] 已於 `9847b1a` 建立永久備份 annotated Git Tag：`archive/core-v2-maximalist`。
- [x] 已完成 `core_v2` 現況 LOC 量化剖析、過度設計盤點、資料流耦合診斷與 SDK 體驗評估，並開立本計畫目錄與 `P00_discuss.md`（狀態 `Discussing`，依指示暫未開始調研）。

---

## 2. 現場未完成 / 進行中待辦
- [ ] Phase 00 深化對齊：與開發者逐項拍板 `[P00:DR-02]` 四大砍留清單（特別確認是否全砍跨倉 `COALESCE`、跨層事件/前景合流、局部模組 `QUIESCE` 與泛型 `codec` 擴充）。
- [ ] 以 `1.x` 真實模組（`vscode-support` 與 `knowledge-db`）起草目標 `surface.sdk` / `TaskContext` 偽代碼原型，確認 SDK 簡潔度與 Wave 1.2 能力注入介面。
- [ ] 補完五維度防放水反詰確認，將 `P00_discuss.md` 定稿為 `Confirmed`，隨後推進 `P01`~`P07`。

---

## 3. 踩坑與注意事項 (Gotchas & Blockers)
- [WARN] **Gate 0 複雜度限制不可復原**：開發者明示移除「<=6 params / <=75 LOC / <=3 depth」是刻意的，先前該守門迫使 Agent 將內聚業務邏輯切碎為無意義散裝函式（造成平均每函式僅 19.7 LOC、61% 為私有碎函式）。本次重構應主動**反向聚合**回清晰線性流程，但仍須維持 Gate 0 的零 `Any`/零 `print`/零 `getattr`/嚴格 DAG 白名單與 Living-Spec 簽名對齊。
- [WARN] **Linux loopback TCP 必開 `TCP_NODELAY`**：`core/execution/rpc/channel.py` 必須保留 `_enable_tcp_nodelay()`，否則 Linux 連續送 `CALL_ACCEPTED` + `CALL_RESULT` 會觸發 Nagle + 40ms Delayed ACK 導致短逾時測試失敗。
- [WARN] **Python 3.12.0–3.12.3 PEP 709 `symtable` 缺陷（gh-116608）**：僅於推導式讀取之區域變數在 3.12.3 `symtable` 不會標記 `is_referenced()`，測試守門須保留 AST 推導式 `Load` 補償。
- [WARN] **不可動 `.vscode/settings.json`**：工作區根目錄 `.vscode/settings.json` 有未提交的本地環境變更，任何 `git add` 均須明確指定路徑，切勿 `git add -A`。
- [WARN] **切勿推翻已驗證的 OS 骨幹**：`RC-01 ~ RC-08` 為不可退讓回歸底線；`rpc/channel.py`、`worker_pool.py`、`module_slot.py`、`event/engine.py`、`lifecycle/engine.py`、`filesystem/fs/` 與 `proc.py` 行程樹機制應保留與適度聚合，而非重寫。

---

## 4. 上下文交接 (Compressed Task Context)
- **現行基線量測（Tag `archive/core-v2-maximalist` = `9847b1a`）**：
  - `core_v2/source/core/core/`：34 檔、**29,440 LOC**、212 類別、1,494 函式（918 私有 = 61%，平均 19.7 LOC/fn，485 LOC 在 `__post_init__`）；7 個公開套件 `__all__` 合計 **205 個匯出符號**（`foundation` 60、`runtime` 69、`fs` 28、`rpc` 24、`event` 12、`daemon` 12、`lifecycle` 10）。
  - `core_v2/verify_execution_live.py`：單檔 **25,167 LOC**（執行約 4–5 分鐘）。
  - 對比 `1.x`：`ys_codebase/source/core` (28,065) + `server` (5,129) = 33,194 LOC；全 6 大業務模組合計 57,555 LOC。
- **五大體量來源與目標瘦身藍圖（目標降至 ~12,000–14,000 LOC）**：
  1. **對稱 `COALESCE` 合流與重入網（~7.4k → ~2.0k）**：`coordinator.py` (3,155, 38+21 methods)、`lineage_join.py` (782, `FlightCascade` 46 methods)、`turn_session.py` (744, `TurnSessionRegistry` 40 methods)、`dispatcher.py` (2,710, `RuntimeDispatcher` 72 methods)、`gates.py` `ColdInstallerLockManager` (574)。目標：取消跨倉多跳 `COALESCE`、跨層事件/前景合流、逐槽剔除與磁碟五檔 `.pin/.turn.json`；`CallPropagationContext` 由 12 欄位縮減至 5 欄位（`turn_id`, `call_stack`, `lineage`, `is_internal_trigger`, `in_event_chain`）。
  2. **熱重載與選擇性靜默狀態機（~4.3k → ~1.5k）**：`gates.py` `LifecycleReloadGate` (844, 60 methods)、`daemon/service.py` (2,342, `WorkspaceDaemon` 79 methods)。目標：單一全域 `QUIESCE` 屏障取代局部模組租約／動態分組遷移／`WARMING` 交錯重載。
  3. **型別編解碼器（2,965 → ~750）**：`foundation/codec.py`（128 top-level defs）。目標：移除多層泛型 MRO `TypeVar` 重映射與 Union 多維評分排序，專注不可變 `@dataclass` DTO，為 Wave 1.2 `SchemaExporter` 鋪路。
  4. **反碎片化與 OS 過度防禦**：聚合舊 Gate 0 碎函式與參數打包 DTO；`proc.py` (1,672) 中 `SignalWakeupGuard` (~450 LOC) 收斂為單主線程喚醒器 (~80 LOC)；移除有毒 `__str__` / 1040-FD 壓測等非本機工具威脅模型。
  5. **目標統一資料流（5 階段單向管道）**：`[1. Ingress & Gate] -> [2. Route & Transport] -> [3. Resource Coordinator (單一權威)] -> [4. Step Execution (統一 TaskContext)] -> [5. Turn Event Drain & LIFO Teardown]`。
- **SDK 6 大改造要點（`surface.sdk` 目標壓至 ~20–25 符號）**：
  1. 嚴格區分 `surface.sdk` 公開門面與內核內部匯出。
  2. 減輕 Task 宣告樣板（內建 `EmptyInput`、免重複寫 `TIn/TOut`、由 `dev build` 編譯靜態索引取代雙份維護 `routes.json`）。
  3. 提前定案 `YscbModule.on_init` 與 `TaskContext` 的跨 Tier 0/1 業務能力注入（`vfs`、`config`、`contributes`、`storage`、`logger`）。
  4. 以 `Annotated` 參數描述整合 CLI 解析、`--help`、JSON Schema、SDK 與 Codec，並提供 `render_human(out) -> str` 雙軌呈現。
  5. `EventSubscriptionSpec` 提供無參/預設觸發工廠（免每個無參訂閱手寫 `lambda _items: EmptyIn()`）。
  6. 提供高階 `YscbClient` 門面隱藏 `InvokeRequest` 組裝與連線細節。
- **關鍵檔案與行號座標**：
  - `core_v2/ROADMAP.md`（全檔 129 行）、`core_v2/R01_execution_orthogonal_research.md`（全檔 167 行）
  - `core_v2/sub_module_design/execution/runtime.md`（L25-L409 核心契約與流水線）
  - `core_v2/source/core/core/execution/runtime/coordinator.py`（`StepFlight` L359-676、`ResourceCoordinator` L1149-2000）
  - `core_v2/source/core/core/execution/runtime/dispatcher.py`（`RuntimeDispatcher` L425-2710）
  - `core_v2/source/core/core/execution/runtime/gates.py`（`LifecycleReloadGate` L472-1315、`ColdInstallerLockManager` L1351-1924）
  - `core_v2/source/core/core/execution/runtime/lineage_join.py`（`FlightCascade` L140-781）
  - `core_v2/source/core/core/execution/daemon/service.py`（`WorkspaceDaemon` L856-2342）
  - `core_v2/source/core/core/foundation/codec.py`（全檔 2,965 行）
  - `1.x` 模組手感對照參考：`ys_codebase/source/vscode-support/scripts/{cli,hook.core}.py`、`ys_codebase/source/knowledge-db/manifest.json`

---

## 5. 下一次接手時的第 1 步 (Immediate Next Action)
- 讀取 `plans/2026_11_20_1740_core_v2_kernel_simplification_and_sdk/P00_discuss.md` 第 2、3 節開放議題，先向開發者確認 `[P00:DR-02]` 四項精簡邊界是否有例外保留項，再以 `vscode-support` 與 `knowledge-db` 撰寫 `surface.sdk` 體驗原型草案以收斂定稿 `P00_discuss.md`。
