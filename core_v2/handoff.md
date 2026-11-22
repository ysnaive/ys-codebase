# Core 2.0 跨對話與遠端異步開發交接快照 (`core_v2/handoff.md`)

> **最後更新**：`2026-11-22`
> **當前狀態**：**Wave 1.1 實作全綠 + Wave 1.2 剩餘全內核 11 份設計書已全數討論定案凍結（`Design Frozen`），就緒交付遠端異步實作**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1 實作）

* **實作規模**：`core_v2/source/core/core/` 共 37 支 `.py`、**20,753 LOC**
  - `foundation/`（4,013 LOC）：`primitives` / `errors` / `observability` / `codec`（1,433L）/ `proc`（1,239L）。
  - `filesystem/fs/`（2,033 LOC）：`atomic` / `lock` / `watcher`。
  - `execution/`（13,706 LOC）：`event` / `lifecycle` / `rpc` / `runtime`（8,607L，5 段管線、頂層同倉 `COALESCE`、單一全域 `QUIESCE`、10 欄位上下文、記憶體模組註冊）/ `daemon`（1,397L）。
  - `surface/sdk/`（998 LOC）：零反射方案 B 公開門面（精準 25 符號 `__all__`）。
* **驗證體系**：[verify_execution_live.py](./verify_execution_live.py)（`--suite` 入口）+ `core_v2/tests/`（`9,541 LOC`）；全線 `Gate 0 + foundation_fs + surface_sdk + runtime_daemon + RC-01~RC-08` 全綠（`0 ResourceWarning`）。
* **計畫與觀察項**：Wave 1.1 計畫 `plans/2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 已達 `P07 Completed`（尚未 `plan archive`）；`[TODO-29]` 保留於 `plans/roadmap/TODO.md`；`ys_codebase/source/*` 與 `.vscode/settings.json` 零異動。

---

## 2. 本輪完成：Wave 1.2 全內核設計書清冊（Ready for External / Remote Implementation）

> **實作授權與契約紅線**：**唯有 `core.surface.sdk` 對外公開契約、磁碟／JSON 檔案格式（`manifest.json` 2.0、`tasks.index.json`、`contributes/_schema.json`、`config.schema.json`、`*.tmpl`、`yscb.config.json`）、六域單向 DAG 與環境變數憲法必須嚴格統一**；各子模組內部 API 與檔案切分允許遠端實作端依實務微調。

| 批次 | 功能域 | 設計書（皆已登記於 `test_gate0.py` `_DRAFT_SPECS`） | 核心拍板決策摘要 |
| :---: | :--- | :--- | :--- |
| **1** | Domain 1 補完 | [foundation_wave12.md](./sub_module_design/foundation/foundation_wave12.md) | `SemVer4`/`VersionConstraint`/`SemanticUri`/`SpaceId`/`SpacePath`/`SnapshotGen`/`EnvHash`；`SchemaExporter`；`LogRotator`/`StructuredLogger`/`LocaleCatalog`（保留供全生態系使用）/`SessionTelemetryWriter`；受控 `YSCB_*` 白名單與 `_YSCB_WORKER_AUTH_TOKEN` 更名 |
| **1** | Domain 2 剩餘 | [vfs.md](./sub_module_design/filesystem/vfs.md)<br>[storage.md](./sub_module_design/filesystem/storage.md)<br>[space.md](./sub_module_design/filesystem/space.md) | 借鏡 `uitk.net`：`VfsCapabilities(Flag)` + `VfsProvider`（`PhysicalDirectoryProvider` + `MemoryVfsProvider`）、Scheme B 15 協議、雙層 `ReadonlyPolicy`（VFS + OS 唯讀穿隧）、`ScopedVfs` 跨模組寫隔離；`ModuleDatabase` SQLite WAL + `BlobVault` **嚴格僅限 `storage.local://`**（禁 `cache://` 與 `storage://`）；`space -> storage` SQLite WAL 取代 `YFP2`、支援持久化動態空間與 `GitignoreMaterializer` |
| **2** | Domain 3 | [config.md](./sub_module_design/metadata/config.md)<br>[contributes.md](./sub_module_design/metadata/contributes.md) | `manifest.json` 2.0（12 欄）；2×2 強型別組態 + `DeepInfiller` + 智能 `SnapshotVault`（預設 3 份／7 天／60s 防連點折疊，排除 `storage.local://` 與 `cache://`）；`Contributes 2.0` 100% 邏輯歸屬 `core`（Python `@dataclass` SSOT + 靜態 `_schema.json` + 離帶 `ProvenanceGraph` + `BUCKET_BY_DONOR` + 純記憶體聚合不落盤 + `contribute.json` 同構免剝殼） |
| **3** | Domain 4 | [env.md](./sub_module_design/packaging/env.md)<br>[installer.md](./sub_module_design/packaging/installer.md) | 方案 B `.venv/<group>_<py_tag>_<hash16>/`、`--only-binary=:all:`、E3-A 回滾友善 GC（7 天 / 每組保留 1 份歷史環境）；純離線 `OfflinePackageEngine`、`configurable/*.tmpl` 強制後綴並於 Staging 無條件整目錄剝離、跨版遷移改回傳 `UpgradeTransition` 交上層派發 `@on_migrate` `Task`、三級 `remove` / `--clean` / 獨立 `purge` |
| **4** | Domain 6 & 自舉 | [sdk_wave12.md](./sub_module_design/surface/sdk_wave12.md)<br>[cli.md](./sub_module_design/surface/cli.md)<br>[composition_and_bootstrap.md](./sub_module_design/surface/composition_and_bootstrap.md) | **唯一強制統一對外契約**：`Module` 追加 `config_type` / `extension_points` / `@on_migrate`、`ModuleEnv`（含 `open_database` 自動 LIFO 關閉）+ `TaskContext` 注入、單一 `from core.surface.sdk import ...` 匯出；`surface.cli` 零匯入 `tasks.index.json`、100% 承繼 1.x `HelpRenderer`、5 層 `CallerMode`（防 PTY Agent 誤判）+ 4 級 `SecurityTier`（`SAFE`/`CONDITIONAL`/`GATED`/`CRITICAL`，1 Task = 1 固定等級，`GATED` 非 TTY 採兩段式單次 `--approve=<tok>` 根除 Compact `-y` 慣性，`CRITICAL` 鎖人類終端）；組裝根、內建系統 `Task`、`core_v2/yscb.py` 雙原語自舉與 `Wave 1.2a ~ 1.2d` 遠端實作指南 |
| — | 工具鏈草案 | [dev/dev.md](./sub_module_design/dev/dev.md) | `Draft — Prototype Design`（開放議題待 Wave 1.2 實作後配合 CI 格式再深化） |

---

## 3. 下次對話／遠端實作建議入口（Pick Next）

1. **交付遠端異步開發執行 Wave 1.2（主線）**：直接以本檔與 [composition_and_bootstrap.md](./sub_module_design/surface/composition_and_bootstrap.md) §4 為入口，按 `Wave 1.2a -> 1.2b -> 1.2c -> 1.2d` 分波實作完整 `core 2.0` 內核，完成後拉回本地驗收優化。
2. **封存 Wave 1.1 計畫（選配）**：對已結案的 `2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 執行 `plan archive`。
3. **後續深化 `dev 2.0` 與 CI 格式**：待 Wave 1.2 內核落地或並行期間，拍板 [dev/dev.md](./sub_module_design/dev/dev.md) §4 開放議題。
