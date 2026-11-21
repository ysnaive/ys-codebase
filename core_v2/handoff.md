# Core 2.0 跨對話進度交接快照 (`core_v2/handoff.md`)

> **建立時間**：`2026-11-21`
> **當前狀態**：**Wave 1.1 內核簡化與 SDK 門面已完成且全綠驗收，開發暫停於架構消化與設計對齊階段**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1）

* **實作規模**：`core_v2/source/core/core/` 共 37 支 `.py`、**20,753 LOC**
  - `foundation/`（4,013 LOC）：`primitives` / `errors` / `observability` / `codec`（1,433L）/ `proc`（1,239L，含 `SignalWakeupGuard`、Windows `CREATE_NO_WINDOW` 與 `GetConsoleWindow` 守衛）。
  - `filesystem/fs/`（2,033 LOC）：`atomic` / `lock` / `watcher`。
  - `execution/`（13,706 LOC）：`event`（495L）/ `lifecycle`（834L）/ `rpc`（2,370L）/ `runtime`（8,607L，5 段管線、頂層同工作區 `COALESCE`、單一全域 `QUIESCE`、10 欄位 `CallPropagationContext`、記憶體模組註冊）/ `daemon`（1,397L）。
  - `surface/sdk/`（998 LOC）：零反射方案 B 公開門面（精準 25 符號 `__all__`、`Module`/`TaskGroup`/`@task`/`@on_event`/`@periodic`/`InMemoryModule`/`YscbClient`）。
* **驗證體系**：[verify_execution_live.py](./verify_execution_live.py)（145L，`--suite` 入口）+ `core_v2/tests/` 共 **9,541 LOC**（全線 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py` 實測 **PASSED，`95.95s`，`0 ResourceWarning`**）。
* **文檔對齊**：`core_v2/` 下 8 份 Active Living Specs + 2 份 Draft Specs（[surface/cli.md](./sub_module_design/surface/cli.md)、[dev/dev.md](./sub_module_design/dev/dev.md)）+ [ROADMAP.md](./ROADMAP.md) + [R01_execution_orthogonal_research.md](./R01_execution_orthogonal_research.md) 已完成同步與清查。
* **計畫與 Git 狀態**：
  - 計畫 `plans/2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 已達 **`P07 Completed`** 且 `[REV-01]` 文檔清查完成（`plan verify`: PASSED）。
  - Wave 1.1 成果與本輪設計文檔已提交至版控（`ys_codebase/source/*` 與 `.vscode/settings.json` 均未改動；計畫目錄尚未執行 `plan archive`）。

---

## 2. 本輪 5 步架構走讀與驗收結論

已完成 `core_v2` 全 6 區塊（A～F）由底向上的原理拆解與驗收：
* **整體評估**：依賴 DAG 嚴格無環、無全域業務單例（僅 3 處底層進程單例：`_StdoutProxyState`、`_SignalRegState`、`_CodecMetadataCache` 與 SDK 編譯期 `_SdkStateRegistry`），現有結構保留運作良好。
* **已登記／記錄之觀察項**：
  - **`[TODO-29]`**（已入 `plans/roadmap/TODO.md`）：評估 [atomic.py](./source/core/core/filesystem/fs/atomic.py) 的 Windows `ctypes` ACL/SID 模擬 `0o600` 權限之必要性。
  - **純未來維護觀察（目前皆保留不動）**：`rpc/channel.py`（2,315L）日後可純內部拆檔；`runtime/dispatcher.py`（1,152L）未來擴充前注意勿膨脹；`tests/_harness.py`（2,341L）後續新域測試各自拆治具。

---

## 3. 本輪新增已拍板方向 & 暫留開放議題

1. **OS 環境變數與系統常數命名憲法（已拍板，落檔於 [foundation.md](./sub_module_design/foundation/foundation.md) §3）**：
   - 公開使用者覆寫一律 `YSCB_*`（須登記，一般開關優先走 `config`/`Enum`）；內核／工具私有跨進程變數一律 `_YSCB_*`（整批按前綴封殺外部注入；既有 `YSCB_WORKER_AUTH_TOKEN` 列入 Wave 1.2 統一改名與加進 `Gate 0` 檢核）。
2. **`dev 2.0` 雛型設計草案（已落檔於 [dev/dev.md](./sub_module_design/dev/dev.md)，狀態 `Draft`）**：
   - **已對齊方向**：維持 `dev` 為 **Tier 0 純標準庫 `unittest`** 零依賴底座；正式淘汰 `scripts/hook.dev.py` 與 `self.mark_passed()`（改由 `TestResult` 判定失敗保留現場）；測試分化為 **層級 1（共用沙盒 + `yscb.config` 依賴閉包非受測模組 + 受測 `@build`）** 與 **層級 2（獨立空白沙盒 + 下游宣告 CI 建置／測試指令，允許下游自選工具如 `pytest`）**。
   - **待下次繼續討論之開放題**：
     1. 層級 1 `unittest` helper 與共用沙盒細部契約（唯讀邊界、快速微測、`@build` 更新策略）。
     2. 層級 2 獨立部署測試宣告格式與 Tier 1 快取策略（**待設計 CI 格式時一併定案**）。

---

## 4. 下次對話建議入口（Pick Next）

接手本進度時，請直接從以下 3 條路線向開發者確認優先順序：
1. **封存 Wave 1.1 計畫（選配）**：確認後對已完成的 `2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 執行 `plan archive`。
2. **繼續深化 `dev 2.0` 與 CI 宣告格式**：針對 [dev/dev.md](./sub_module_design/dev/dev.md) §4 的開放議題逐一拍板，決定是否先落地 Phase 1 薄 Demo（`dev.checker` + `dev.testing`）。
3. **啟動 Wave 1.2 剩餘內核域設計**：補齊 `foundation` 剩餘值物件、`filesystem/{vfs,space,storage}`、`metadata/{config,contributes}`、`packaging/{env,installer}`、`surface/cli` 規格設計。
