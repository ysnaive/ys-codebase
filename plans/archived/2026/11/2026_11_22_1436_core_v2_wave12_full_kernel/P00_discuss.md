# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 Wave 1.2 全內核子模組實作、雙盲語境裁決閉環與活規格轉正  
> 建立日期：2026-11-22  
> 所屬主計畫：無（獨立 Full Track 實作計畫）  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於本地完成 Wave 1.1 精簡基線驗收與 Wave 1.2 全內核 11 份設計規格書凍結定案（`Design Frozen`）後，採單次長任務連續按 `Wave 1.2a -> 1.2b -> 1.2c -> 1.2d` 逐子波次分段推進實作、實機跑測與雙盲審查裁決閉環，全數完成後同步雲端供本地統一驗收。
- **核心目標**：
  1. 嚴格沿六大功能域單向 DAG 由底向上完成 `Wave 1.2a`（`foundation` 擴充 + `vfs` / `storage` / `space`）、`Wave 1.2b`（`metadata.config` / `metadata.contributes` + `packaging.env` / `packaging.installer`）、`Wave 1.2c`（`execution.runtime` 最小增量接縫 + `surface.sdk` / `surface.cli` / `surface.bootstrap` / `CoreSystemModule` + 純標準庫 `core_v2/yscb.py`）與 `Wave 1.2d`（逐域拔除驗證與 11 份凍結草案轉正為 Active Living Specs）。
  2. 嚴守四大強制統一硬契約：`core.surface.sdk` 61 符號對外公開契約、磁碟與 JSON 檔案格式（`manifest.json` 2.0、`tasks.index.json`、`contributes/_schema.json`、`config.schema.json`、`*.tmpl`、`yscb.config.json`、`.yscb_env_meta.json`）、六域單向無環 DAG，以及受控環境變數憲法（`PUBLIC_ENV_ALLOWLIST` + `_YSCB_*` 私有前綴整批洗淨 + `_YSCB_WORKER_AUTH_TOKEN` 更名）。
  3. 補齊三套分域測試集（`test_vfs_storage_space.py`、`test_metadata_packaging.py`、`test_surface_cli_e2e.py`）並接入 `verify_execution_live.py --suite`，確保全套單元、邊界、跨領域拔除與 `RC-01 ~ RC-08` 實機壓測 100% 通過且 `0 ResourceWarning`。
  4. 於每一子波次與最終全域收斂執行「雙軌冷眼盲審 + 輕量設計語境校準裁決（Arbiter）+ 不限輪數真實收斂」迭代閉環。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 100% 復用 Wave 1.1 已實機驗證之 `core.foundation`（`HostPath`、`validate_relative_segment`、`DataclassCodec`、`CancellationToken`、`ManagedProcessTree`、`SignalWakeupGuard`）、`core.filesystem.fs`（`atomic_write_bytes`、`atomic_write_json`、`resolve_contained_subpath`、`FileLock`、`PollingDirectoryWatcher`）、`core.execution.*`（5 階段管線、頂層同倉 `COALESCE`、單一全域 `QUIESCE`、多工 Socket RPC 與 3 個預留系統 `EventId`）以及 `core.surface.sdk` 既有 25 符號零反射 `_DeclarativeMeta` 架構。
  - 確認根目錄 `.gitignore` 與 `ys_codebase/config/core/contribute.json`（`workspace.exclude` 與 `gitignore.include`）已涵蓋 `core_v2/.venv`、`core_v2/.modules`、`core_v2/.mirror`、`core_v2/.build`、`core_v2/.cache`、`core_v2/.storage.local`、`core_v2/.config.local`、`core_v2/.snapshots`、`core_v2/.temp` 九項衍生路徑排除護欄。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁修改 `ys_codebase/source/*`（1.x 主線業務模組源碼）與根目錄 `.vscode/settings.json`。
  - 保留已結案之 `plans/2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 於原位供參考，本輪不執行歸檔。
  - `core_v2/sub_module_design/dev/dev.md` 維持 `Draft — Prototype Design`，本期聚焦 `core 2.0` 全內核與 `core_v2/yscb.py` 落地，不提前實作 `core_v2/source/dev/`。
- **架構影響範圍**：
  - 核心源碼：`core_v2/source/core/core/{foundation,filesystem,metadata,packaging,execution,surface}/**` 與宿主啟動器 `core_v2/yscb.py`。
  - 活規格文檔：`core_v2/sub_module_design/{foundation,filesystem,metadata,packaging,execution,surface}/*.md`、`core_v2/ROADMAP.md`、`core_v2/handoff.md` 與根目錄 `CHANGELOG.md`。
  - 測試體系：`core_v2/verify_execution_live.py` 與 `core_v2/tests/{test_gate0,test_foundation_fs,test_vfs_storage_space,test_metadata_packaging,test_surface_sdk,test_surface_cli_e2e,test_runtime_daemon,test_rc_e2e}.py`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 單次長任務分波推進與輕量單一主計畫架構**：採單一 Full Track 輕量主計畫統籌 `Wave 1.2a -> 1.2b -> 1.2c -> 1.2d` 四個內部里程碑，以 `core_v2/sub_module_design/` 下 11 份凍結設計書為技術規格唯一真理（SSOT），單次連續執行至全數收斂並透過受控 CoW 同步雲端後，交由本地端統一驗收。
- **[P00:DR-02] 四大強制統一硬契約與內部實作彈性分界**：對外 `core.surface.sdk` 61 符號契約、磁碟與 JSON 序列化格式、六大功能域嚴格單向匯入白名單及受控環境變數憲法（`_YSCB_WORKER_AUTH_TOKEN` 更名與 `PUBLIC_ENV_ALLOWLIST`）必須 100% 精確對齊；各子模組內部檔案切分、私有輔助結構與受 `Gate 0` 約束之內部返回包裝（如將 3 元組健康紀錄封裝為具名不可變 `@dataclass`）允許依工程內聚度適度微調，並於 `Wave 1.2d` 同步反映至轉正後之 Active Living Specs。
- **[P00:DR-03] 廢除機械行數定罪，全面採語意聚焦度（SLAP / SRP / CCP）評估**：不設 75 行等任何固定函式行數上限；實作與審查唯一結構準則為「單一業務語意與一致抽象層級」——公開方法聚焦高階階段編排、無狀態純運算適度剝離、保護共享同一把交易鎖之狀態機連貫內聚，杜絕無獨立語意之 3~5 行奈米傳聲筒函式與 1 行轉發殼。
- **[P00:DR-04] 全新功能域開發不設 3 輪盲審上限，堅持真實收斂**：各子波次與 `Wave 1.2d` 全域終審均不設盲審輪數上限；每次先通過 `Gate 0` 與實機全套跑測（`-W error::ResourceWarning`），再平行派發零歷史記憶、純指針傳址之雙軌唯讀盲審子代理（軌道 α：架構契約、領域代數與語意聚焦度；軌道 β：並發生命週期、三平台檔案與句柄陷阱、資安非 TTY 邊界與測試純度），持續修復與全新子代理複審直至實質缺陷歸零（`REVIEW_STATUS: PASSED`）。
- **[P00:DR-05] 導入「輕量設計語境校準裁決子代理（Design-Context Arbiter）」防過度挑刺與防膨脹**：每當雙軌盲審回報 `>= 1` 項候選問題時，動刀前強制派發 1 個輕量唯讀裁決子代理，對照 `ROADMAP.md`、`handoff.md`、各設計書「明確減法清單」與第一手源碼逐條輸出三態裁決——`[ACCEPT_FIX]`（實質硬傷准予根因修復）、`[REJECT_NITPICK]`（過度挑刺或對內部彈性之主觀挑剔，駁回不改）、`[REJECT_OUT_OF_DESIGN]`（偏離 Core 2.0 減法語境或要求疊加防禦膨脹，駁回防倒退）。若當輪 `ACCEPT_FIX == 0` 則零改碼直接收斂過關；若 `ACCEPT_FIX > 0` 則僅修復確立項並進入下一輪全新無記憶雙盲複審。
- **[P00:DR-06] Wave 1 六大盲審必查雷區鎖定**：① 四大硬契約與跨分類解耦（`metadata` 解耦 `project://` 零爬樹、`packaging` 零認識執行期、`cli` 零匯入業務源碼）；② 三平台物理檔案與進程陷阱（Windows `WinError 5/32` 唯讀穿隧與 SQLite 連線池釋放、同父目錄 Staging 防 `EXDEV`、`_can_symlink()` 降級、UTF-8 LF 與 `LogRotator` `.split("\n")`）；③ SQLite WAL MVCC（`BEGIN IMMEDIATE`、`cancel_token` 回滾、`SnapshotReader` 退場 `ROLLBACK`、唯獨放行 `storage.local://`）與套件異動 `QUIESCE -> SnapshotVault -> @on_migrate -> finally RESUME` 全鏈路回滾；④ 資安與 AI Agent 非互動邊界（5 層 `CallerMode` PTY 防誤判、4x3 安全矩陣、`GATED` 單次 `--approve=<tok>` 綁定 `args_hash` 用過即焚、`CRITICAL` 雙層硬阻斷、Zip 20MiB/CRC/SHA-256/ZipSlip、`*.tmpl` 整目錄剝離、跨模組 `@/` 寫隔離）；⑤ 1.x 領域代數不變量（`SemVer4`、`DN-20` 空間剪枝與純差集、`Contributes 2.0` 零魔術鍵與離帶溯源、智能 `SnapshotVault`）；⑥ 測試純度（零假斷言、零固定 `sleep`、Tier 0/1 對稱與活規格 1:1 真實對齊）。

---

## 3. 開放議題與確認紀錄

- [x] 已拍板（`[P00:DR-01]` ~ `[P00:DR-02]`）：採單次長任務連續推進 `Wave 1.2a -> 1.2d`、輕量單一主計畫，保留前案參考並確認 9 項 `core_v2/.*` 排除護欄到位。
- [x] 已拍板（`[P00:DR-03]` ~ `[P00:DR-06]`）：確立語意聚焦評估、不限輪數盲審收斂與「雙軌初審 -> 輕量語境校準裁決 -> 根因修復」三步閉環，授權啟動長任務實作。
