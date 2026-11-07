# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_server_hook_integration  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於分類型主計畫 `2026_11_06_1020_core_file_space_architecture` 推進第三階段 `sub_03_server_hook_integration`，建立 `core.space` 與選配之 `module:server` 常駐監控及事件 Hook 整合（在無 `server` 環境下天然純本地運作不觸發常駐依賴），並保留且強化 `define_ephemeral_space` 執行期動態空間註冊能力（如供 `agents-workflow` 建立 `yscb-skills` 等動態空間），所有空間（含動態空間）之 `watch` 皆預設為 `True`。
- **核心目標**：
  1. **`SpaceDef` 與 `define_ephemeral_space` 之 `watch` 屬性擴充（預設一律開啟 `watch=True`）**：
     - 於 `core/contributes/_format.json` 之 `SpaceDef` 新增 `"watch": "bool? = true @desc(常駐 Server 啟動時是否納入背景檔案變更監聽)"`。
     - 於 `SpaceConfig` 與 `define_ephemeral_space(name, config, *, watch=True)` 支援 `watch: bool = True`（可於 `config["watch"]` 或參數傳入覆寫，未指定時一律預設 `True`）。
     - 當 `define_ephemeral_space` 於常駐 Worker 進程內動態註冊且 `watch=True` 時，自動通知活躍之常駐空間監聽器動態納入（Re-schedule）該空間之入口目錄。
  2. **程序內訂閱與 `on_file_space_changed` 事件廣播 (`emit_module="core"`)**：
     - 於 `core.space` 提供程序內訂閱機制 `subscribe(callback, *, spaces=None)`、`clear_subscribers()` 與跨進程廣播觸發器：當空間快照世代 (`to_generation > from_generation`) 推進時，觸發程序內訂閱者並呼叫 `core.events.broadcast("on_file_space_changed", payload, emit_module="core")`（由下游 `scripts/hook.core.py` 接收），且於 `core/contributes/core.json` 之 `events` 正式登錄 `on_file_space_changed`。
  3. **常駐背景監聽服務 (`SpaceWatcherServiceWorker`) 與同進程/跨進程零延遲協同**：
     - 將常駐檔案變更監聽器內聚於 `module:server`（或由 `server` `ServiceManager` 自動掛載之 `SpaceWatcherServiceWorker`），並於 `server/manifest.json` 宣告 `"pip_dependencies": { "watchdog": ">=4.0.0" }`（使 `module:core` 維持 100% 純標準庫、零第三方依賴；若環境無 `watchdog` 則優雅降級）。
     - 監聽器僅負責偵測檔案系統事件（0-syscall 黑盒目錄段快篩、500ms 防抖、`.yscb.lock` 交易鎖避讓、目錄新增/搬移/刪除升級全掃），並直接調用 `core.space` SDK (`patch_files` / `scan`) 更新 `YFP2` 快照與廣播 `on_file_space_changed`。
     - 實作同進程待防抖事件即時沖刷（當呼叫 `snapshot`、`merkle_root`、`diff`、`consume_diff` 時，若當前進程存在活躍 Watcher 且目標空間有未沖刷髒事件，自動先行 `flush_space_now`）與跨進程 `.watcher_dirty` 信標感知（位於 `cache://core/space/watcher_state.json` 與 `.watcher_dirty`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_01` 與 `sub_02` 已建置之 `core.space.{SpaceRegistry, SpaceScanner, ScanDiffResult}`、`core.events.broadcast`、`core.platform.InterProcessLock` 與 `server.service.BaseServiceWorker`。
  - 吸收並精煉既有 `ys_codebase/source/file-space/file_space/service.py` 之 `_FileSpaceWatchdogHandler`、路徑快篩、`.yscb.lock` 避讓、`flush_space_now` 與失敗回滾 (`_rollback_space_batch`) 機制。
- **邊界排除 (Explicitly Excluded)**：
  - **不包含** 下游模組（`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`）之 `hook.file-space.py` 改名遷移至 `hook.core.py` 與舊 `module:file-space` 退役移除（明確歸屬下一階段 `sub_04_ecosystem_migration_and_legacy_removal`）。
  - **不包含** `core.vfs` 單點物理防誤改鎖（File Guard）。
- **架構影響範圍**：
  - `ys_codebase/source/core/contributes/_format.json`、`ys_codebase/source/core/contributes/core.json`（新增 `SpaceDef.watch` 與 `on_file_space_changed` 事件宣告）
  - `ys_codebase/source/core/core/space/`（更新 `schema.py`、`registry.py`、`scanner.py`、`__init__.py`，新增 `watcher.py` 協同原語與 `subscribe` / `flush` 支援）
  - `ys_codebase/source/server/`（更新 `manifest.json`、新增或整合 `SpaceWatcherServiceWorker` 背景監聽服務與測試）
  - `ys_codebase/source/core/tests/test_space.py` & `ys_codebase/source/server/tests/`（新增 Watcher 防抖、鎖避讓、動態空間熱掛載、同進程即時沖刷與 `on_file_space_changed` 廣播測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[`[P00:DR-01]`] 職責切分：`module:server` 承載 `watchdog` 檔案事件偵測，`module:core` 提供純標準庫 Space SDK 與事件匯流排（軸一：既有組件復用 & 軸五：邊界鎖定）**：
  - `module:core` 維持 100% Python 標準庫零第三方套件依賴，提供空間入口枚舉、規則匹配、`patch_files` / `scan` 快照更新、程序內 `subscribe` 與 `core.events.broadcast("on_file_space_changed", ..., emit_module="core")`。
  - `module:server` 於 `manifest.json` 宣告 `"pip_dependencies": { "watchdog": ">=4.0.0" }`，在常駐 `WarmWorker` 啟動時自動啟動內建之空間檔案監聽服務 (`core-space-watcher`)，負責將 OS 檔案變動（含 500ms 防抖與 `.yscb.lock` 交易鎖避讓）轉化為對 `core.space` SDK 的增量刷新呼叫。
  - 當未安裝 `module:server` 或常駐 Daemon 未啟動時，`core.space` 所有功能（`scan`、`diff`、`consume_diff`、`status` 等）100% 純本地拉取運作，絕不拋出缺少 `server` 或 `watchdog` 之異常。
- **[`[P00:DR-02]`] 靜態與動態空間 (`define_ephemeral_space`) 一律預設 `watch=True`、程序內預設共享實例與執行期動態熱掛載（軸二：預設值與隱性副作用 & 軸三：生命週期與逆向拆卸）**：
  - 於 `SpaceDef` Schema 與 `SpaceConfig` 新增 `watch: bool = True`；一般空間與透過 `define_ephemeral_space(name, config, *, watch=True)` 建立之執行期動態空間（例如 `agents-workflow` 動態建立之 `yscb-skills` 空間）預設皆開啟監聽（亦可顯式傳入 `watch=False` 關閉）。
  - **程序內依 `(project_root, yscb_root)` 快取之預設 `SpaceRegistry` 與 `SpaceScanner` 共享實例**：提供 `get_default_registry()` 與 `get_default_scanner()`（並在 `contributes` 快取失效或重載時同步刷新，同時保留已註冊之動態空間或按需重置），確保同一進程內頂層呼叫 `define_ephemeral_space`、`scan`、`diff`、`consume_diff` 與常駐 Watcher 共享同一份動態空間定義、`_ephemeral_snapshots` 與 `_ephemeral_cursors`，徹底消除動態空間記憶體孤島。
  - 當常駐進程內呼叫 `define_ephemeral_space` 新增或更新 `watch=True` 的動態空間時，若常駐監聽器在線，自動透過 `collect_all_entry_paths` 將其新入口目錄動態掛載至 `watchdog` Observer（冪等去重），無需重啟 Server。
- **[`[P00:DR-03]`] 單軌標準事件路由 (`emit_module="core"`)、`<owner>/<space>` / `<space>` / `compose` 髒快照聯動傳播與同進程/跨進程一致性信標（軸四：跨切面不變量）**：
  - 空間快照變更事件統一透過 `core.events.broadcast("on_file_space_changed", payload, emit_module="core")` 廣播（路由至各模組 `scripts/hook.core.py` 之 `on_file_space_changed`），下游既有 `hook.file-space.py` 留待 `sub_04` 統一遷移為 `hook.core.py`。
  - **複合空間入口展開與髒目標傳播**：Watcher 收集監聽目錄時，對所有 `watch=True` 空間（含 `compose` 複合空間）呼叫 `registry.collect_all_entry_paths(qname)` 遞迴展開所有參與子空間入口；當檔案事件命中某空間 `<owner>/<space>` 時，除了標記該 `<owner>/<space>`（及命中該檔之 `watch=True` 複合父空間）為髒外，於防抖沖刷完成後，自動檢查並同步更新已存在於磁碟之對應短名聯集快照 (`<short_name>.yfp2.bin`) 與全域聚合快照 (`__all__.yfp2.bin`)；且 `flush_space_now(space_query)` 支援對短名 `<space>`、`compose` 父空間與 `None`（全空間）沖刷所有關聯髒子空間。
  - **相容便捷屬性與雙軌訂閱過濾**：為 `ScanDiffResult` 補齊 `.has_changes`、`.added`、`.modified`、`.deleted`、`.unchanged` 頂層唯讀 `@property`；`subscribe(callback, *, spaces=None)` 之 `spaces` 過濾器同時支援 `<owner>/<space>` 限定名與 `<space>` 短名雙向匹配。
  - 監聽器狀態檔與髒信標統一存放於 `cache://core/space/watcher_state.json` 與 `cache://core/space/.watcher_dirty`（與 `sub_02` 之 `cache://core/space/locks/` 對齊，徹底隔離於 `yscb://.cache/core/space/`，零下游專案目錄污染）。

---

## 3. 開放議題與確認紀錄

- [x] **背景監聽器模組歸屬**：已確認採用 `module:server` 負責 `watchdog` 檔案變動偵測並觸發 `core.space` SDK，保持 `core` 100% 純標準庫。
- [x] **`define_ephemeral_space` 執行期動態空間與 `watch` 預設值**：已確認保留執行期動態註冊空間（供 `agents-workflow` 等動態建立如 `yscb-skills` 空間），且靜態與動態空間之 `watch` 一律預設為 `True`（動態空間建立時可傳入 `watch` 參數控制）。
- [x] **事件廣播路由 (`on_file_space_changed`)**：已確認採用方案 B，僅發送 `emit_module="core"` 之 `on_file_space_changed`，下游模組 `hook.file-space.py` 留待 `sub_04` 統一遷移為 `hook.core.py`。
- [x] **盲眼子代理 (`/blind-subagent`) 方案完備性審查 3 項補強處方**：已確認納入 `[P00:DR-02]` 與 `[P00:DR-03]`（程序內預設 `SpaceRegistry`/`SpaceScanner` 共享實例、`compose`/短名聯集入口展開與髒快照傳播、以及 `ScanDiffResult` 頂層屬性與 `subscribe` 雙軌過濾）。
