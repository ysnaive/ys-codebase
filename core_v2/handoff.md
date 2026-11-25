# Core 2.0 跨對話與遠端異步開發交接快照 (`core_v2/handoff.md`)

> **最後更新**：`2026-11-25`
> **當前狀態**：**Wave 1.1 + Wave 1.2 全內核 6 大功能域 + 止血收斂 + `core_v2/yscb.py` + 17 份正式活規格已 100% 實作完封，並通過 Linux 雙模與 Windows 11 實機全 9 套件驗收及 Phase 7 唯讀盲審（`Completed`），就緒推進 Wave 1.3 (`dev 2.0`) / Wave 2**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **關聯結案計畫**：[2026_11_25_0706_core_v2_wave12_stabilization](../plans/2026_11_25_0706_core_v2_wave12_stabilization/P07_walkthrough.md)（承接 [2026_11_22_1436_core_v2_wave12_full_kernel](../plans/2026_11_22_1436_core_v2_wave12_full_kernel/P07_walkthrough.md)）
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1 + Wave 1.2 止血收斂微內核）

* **內核與啟動器規模**：
  - `core_v2/source/core/core/` 共 **92 支 `.py`、`62,130 LOC`**（100% Python 3.11+ 標準庫、零第三方依賴、零 `Any`、零 `# type: ignore`），另含 `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 真實元資料：
    - **Domain 1 `foundation/`**（6 檔，`5,920 LOC`）：`primitives`（含 `SemVer4`/`VersionConstraint`/`SemanticUri`/`SpaceId`/`SpacePath`/`SnapshotGen`/`EnvHash`/`PUBLIC_ENV_ALLOWLIST`/`_YSCB_*` + POSIX URI glob 修正）、`errors`（33 碼）、`codec`（`DataclassCodec` + `SchemaExporter` Draft 2020-12）、`observability`（`StructuredLogger`/`LogRotator`/`LocaleCatalog`/`SessionTelemetryWriter`）、`proc`（Job Object / Session+PGID）。
    - **Domain 2 `filesystem/`**（21 檔，`11,043 LOC`）：`fs`（Windows `st_reparse_tag` 精準判別 + Watcher 預設雜訊剪枝）、`vfs`（Scheme B 15 協議、多掛載最嚴格權限聚合、雙層 `ReadonlyPolicy`、`VfsEchoGuard`、`ScopedVfs.open_read()` 與 `config.local://`/`storage.local://` 跨模組讀取隔離）、`storage`（SQLite WAL MVCC 錯誤細分 + 併發 WAL 切換重試 + `BlobVault`）、`space`（SQLite WAL `state.db` `SpaceRegistry`、`SpaceScanner`、`GitignoreMaterializer`）。
    - **Domain 3 `metadata/`**（14 檔，`7,869 LOC`）：`config`（統一 `parse_manifest_dict` 相容 `release.type`/`release_type`、`ModuleManifest` 2.0、2×2 `ConfigStore`、`DeepInfiller`、智能 `SnapshotVault`）、`contributes`（`@dataclass` SSOT、`_schema.json` 編譯、5 大合併策略、離帶 `ProvenanceGraph`、`ContributesAggregator`）。
    - **Domain 4 `packaging/`**（14 檔，`9,088 LOC`）：`env`（不可變雜湊 `.venv` 池、`acquire_env_shared_lease` 運行期保護與節流 `touch_env_last_used`、E3-A 回滾友善 GC）、`installer`（純離線 `OfflinePackageEngine`、RFC 8089 Windows `file://` 校驗、SSRF/CRC/SHA-256/ZipSlip 防線、`configurable/*.tmpl` 整目錄剝離、三級 `PurgeLevel`、`UpdateChecker`）。
    - **Domain 5 `execution/`**（22 檔，`15,844 LOC`）：`event`、`lifecycle`、`rpc`、`runtime`（5 段管線、佇列 `COALESCE` Leader 取消存活、Step 5↔`QUIESCE` 零死鎖、Tier 1 共享 `.venv` 租約 DI、與 `caller_mode.py` 對齊之精準環境方言推導）、`daemon`（解除輪詢 `100ms` 硬上限）。
    - **Domain 6 `surface/`**（14 檔，`12,363 LOC`）：`sdk`（**75 符號**零反射門面 + `TaskGroup.parent_module` 狀態共享 + `@on_migrate` + `ModuleEnv` LIFO）、`cli`（零匯入 `tasks.index.json` 路由 + 1.x `HelpRenderer` + 5 層 `CallerMode` `AGENT > CI` 與精準鍵 + 兩段式單次 `--approve`）、`bootstrap`（`WorkspaceKernelFactory` + 零 TLS `CoreSystemModule` + `core.space.ack_cursor` 游標所有權隔離 + Windows 啟動/RPC 視窗適配）。
  - `core_v2/yscb.py`（**`3,375 LOC`**）：100% 純標準庫單檔超薄自舉啟動器（唯二冷自舉 `init` / `self-update`、非人類環境覆寫守門 `--allow-bootstrap-mutation`、RFC 8089 Windows `file://` 校驗與確定性 `.modules/core` 還原）。
* **17 份正式活規格（Active Living Specs）**：
  - 全數 17 份活規格與實碼維持 1:1 雙向對齊並通過 `Gate 0` 靜態／執行期校驗與圍欄衛生檢查；僅 [dev/dev.md](./sub_module_design/dev/dev.md) 維持 `Draft — Prototype Design`。
* **雙平台驗證體系與盲審收斂**：
  - [verify_execution_live.py](./verify_execution_live.py) + `core_v2/tests/`（共 13 檔、`25,195 LOC`），涵蓋全部 9 大套件（`gate0`、`foundation_fs`、`vfs_storage_space`、`metadata_packaging`、`surface_sdk`、`surface_cli_e2e`、`unplug`、`runtime_daemon`、`rc_e2e`）。
  - **Linux 雙模全綠**：全 9 套件標準模式（`217.00s`）與 `-O` 模式（`273.97s`）全通過，Pillar 3 加固後覆驗 `gate0`（`9.93s`）、`runtime_daemon`（`9.80s`/`14.35s`）、`surface_cli_e2e`（`128.40s`/`133.21s`）均 `0 ResourceWarning`；Phase 7 唯讀盲審 `REVIEW_STATUS: PASSED`。
  - **Windows 11 實機全綠（`UX-01` 已簽核）**：全 9 大套件（含 `surface_cli_e2e` `637.91s`、`rc_e2e` `RC-01~RC-08`、`unplug` 10 階段）於 Windows 11 原生環境 100% 通過（`0 ResourceWarning`）；實測延伸之 2 項後續優化已登錄 `plans/roadmap/TODO.md`（`TODO-30` 測試異常殘留行程防呆、`TODO-31` Daemon 啟動消除雙次冷核心與全量雜湊重算）。
  - 潔淨室隔離護欄：`ys_codebase/source/*`（1.x 主線）與 `.vscode/settings.json` 全程零異動。

---

## 2. 本機拉取驗收指令（Local Acceptance Commands）

1. 拉取雲端同步倉變更：
   ```bash
   python yscb.py gdrive pull
   ```
2. 執行全內核 9 大套件實機驗證（標準模式與 `-O` 模式）：
   ```bash
   python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   ```

---

## 3. 下次對話建議入口（Pick Next）

1. **推進 Wave 1.3：`dev 2.0` 工具鏈設計定案與實作（主線首選）**：以 [dev/dev.md](./sub_module_design/dev/dev.md) §4 開放議題為起點，拍板 `dev build`（靜態提取 `tasks.index.json`、`config.schema.json`、`contributes/_schema.json` 並打包 `.zip` + `index.json`）、`dev check 2.0`（下游業務模組 AST 紅線守門）與跨平台模組沙盒測試器，落地 `core_v2/source/dev/`。
2. **推進 Wave 2：Tier 0 輕模組移植（`vscode-support` / `agents-workflow` / `gdrive-support`）**：基於已鎖定的 75 符號 `core.surface.sdk` 公開門面與 `TaskGroup.parent_module`，將三大 Tier 0 模組純 `Task` 化遷移至 `core_v2/source/`。
3. **排程跟進技術債與歸檔（選配）**：視需要評估 `TODO-30`、`TODO-31` 或封存已結案之 `core_v2` 歷史計畫。
