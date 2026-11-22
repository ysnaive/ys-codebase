# 子模組架構設計規格：`core.packaging.installer`（純離線模組包引擎、依賴求解、原子部署與更新檢查）

> **所屬功能域**：`Domain 4 — 套件與環境域 (packaging/)`
> **模組路徑**：`core_v2/source/core/core/packaging/installer/`
> **建議內部切分**：`models.py`、`provider.py`、`mirror.py`、`solver.py`、`deployer.py`、`update_checker.py`、`engine.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{fs, vfs}`、`metadata.{config, contributes}`、`packaging.env`
> **禁止反向依賴（Forbidden Imports）**：`execution/*`、`surface/*`（**100% 純離線引擎，嚴禁認識 `Task` / `Event` / `Daemon` / `QUIESCE`**）
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

> [!NOTE]
> **實作彈性邊界**：2.0 Zip 套件結構（`tasks.index.json`、`*.tmpl` 模板與完整剝除規則）、`index.json` 遠端協議、`UpgradeTransition` 與 `PurgeLevel` 語意屬硬契約；內部下載器與求解輔助結構可由遠端實作端微調。

---

## 1. 模組定位與跨分類解耦鐵律（對齊 [ROADMAP.md](../../ROADMAP.md) §3）

`core.packaging.installer` 專責**純靜態磁碟與網路套件管理**，絕不介入執行期調度：
1. **零 `execution` 耦合**：不發送 `QUIESCE`、不廣播事件、不執行任何模組 Python 代碼（含升級遷移）。所有動態編排（`QUIESCE` $\to$ `MODULE_REMOVING` $\to$ 呼叫 `OfflinePackageEngine` $\to$ 依回傳之 `UpgradeTransition` 經 `RuntimeDispatcher` 派發模組內部遷移 `Task` $\to$ `MODULE_INSTALLED` / `WORKSPACE_RELOADED` $\to$ `RESUME`）全數收斂於 Batch 4 頂層系統管理 `Task`。
2. **2.0 Zip 套件結構與 `*.tmpl` 零殘留剝離契約**：
   - 維持明文二分法（僅 `source/<mod>/` 與 `.modules/<mod>/` 明文展開；`.build/`、`release/`、`.mirror/` 皆單檔 `.zip`）。
   - **2.0 隨包靜態中繼檔（物化至 `.modules/<mod>/` 後保留）**：
     - `manifest.json`（2.0 強型別清單）
     - `tasks.index.json`（由 `core` 編譯 API 產出，供 `surface.cli` 零匯入路由與 `--help` 渲染）
     - `config.schema.json`（選配，由模組 `@dataclass` Config 編譯產出，內含欄位預設值與 JSON Schema）
     - `contributes/_schema.json`（選配，由 `core.metadata.contributes.compile_extension_points` 產出）
     - `contributes/<target>.json`（選配，Donor 擴充宣告）
   - **部署模板強制 `*.tmpl` 命名與整目錄無條件剝離（進化自 `DN-06`）**：
     - 模組包內所有初始化模板皆置於 `configurable/` 並強制帶 `.tmpl` 副檔名（例 `configurable/config.project.json.tmpl`、`configurable/contribute.json.tmpl`；`vscode-support` 負責關聯 `*.json.tmpl` 至 JSON 語法高亮）。
     - Staging 部署時：`config.schema.json` 預設值（或 `config.project.json.tmpl`）經 `DeepInfiller` 補齊至 `config://<mod>/config.project.json`；其餘 `configurable/<rel>.tmpl` 僅於目標不存在時剝去 `.tmpl` 複製至 `config://<mod>/<rel>`。
     - 完成組態部署後，**無條件整目錄刪除 Staging 內的 `configurable/` 與 `.yscbignore`**，從根本消除模板殘留或命名判斷漏網風險。

---

## 2. 核心公開契約規格 (`core/packaging/installer/`)

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence

from core.filesystem.vfs import KernelVfs
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, ModuleId, SemVer4, VersionConstraint
from core.metadata.config import ConfigStore, ModuleManifest, ReleaseUrgency, SnapshotVault
from core.packaging.env import EnvSpec, ImmutableVenvPool


class PurgeLevel(Enum):
    NONE = "none"      # 僅移除 .modules/<mod> 與 yscb.config.json 登錄（保留設定與資料）
    CLEAN = "clean"    # 額外清除本機衍生空間：cache://<mod> 與 storage.local://<mod>
    PURGE = "purge"    # 全清五大資料空間：config / config.local / storage / storage.local / cache


@dataclass(frozen=True, slots=True)
class IndexReleaseRecord:
    version: SemVer4
    sha256: str
    status: str = "active"  # "active" | "pruned"
    dependencies: Mapping[ModuleId, VersionConstraint] = ...
    urgency: ReleaseUrgency = ReleaseUrgency.RECOMMENDED
    summary: str = ""
    yanked: bool = False


@dataclass(frozen=True, slots=True)
class RemoteModuleIndex:
    module_id: ModuleId
    versions: tuple[SemVer4, ...]
    releases: Mapping[str, IndexReleaseRecord]


@dataclass(frozen=True, slots=True)
class PackageRequest:
    module_id: ModuleId
    version_spec: Optional[str] = None  # 例 "2.1.0", "^2.0", "build"
    is_build: bool = False
    provider_override: Optional[str] = None


@dataclass(frozen=True, slots=True)
class UpgradeTransition:
    """回報予上層系統 Task，供其經 RuntimeDispatcher 派發模組內部遷移 Task。"""
    module_id: ModuleId
    old_version: Optional[SemVer4]
    new_version: SemVer4
    is_upgrade: bool


@dataclass(frozen=True, slots=True)
class DeploymentReport:
    installed: Mapping[ModuleId, SemVer4]
    removed: tuple[ModuleId, ...]
    transitions: tuple[UpgradeTransition, ...]
    env_specs: Mapping[ModuleId, EnvSpec]
    snapshot_id: Optional[str] = None
    reconciled_dependencies: tuple[ModuleId, ...] = ()
    onboarding_hints: Mapping[ModuleId, tuple[str, ...]] = ...
```


@dataclass(frozen=True, slots=True)
class UpdateCandidate:
    module_id: ModuleId
    current_version: SemVer4
    latest_version: SemVer4
    max_urgency: ReleaseUrgency
    summaries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateCheckReport:
    candidates: tuple[UpdateCandidate, ...] = ()
    yscb_host_drift: bool = False
    checked_at_utc: str = ""
    throttled: bool = False


class ProviderClient:
    """多來源套件獲取器（本地目錄 / HTTP(S) / @build / 嚴格同版動態打包 / --offline 隔離）。"""
    MAX_REMOTE_PACKAGE_BYTES: int = 20 * 1024 * 1024  # 20 MiB 串流下載上限

    def __init__(
        self, *, yscb_root: HostPath, default_provider: str, offline: bool = False,
        timeout_sec: float = 15.0,
    ) -> None: ...
    def fetch_index(self, module_id: ModuleId, *, provider: Optional[str] = None) -> RemoteModuleIndex: ...
    def fetch_package_zip(
        self, module_id: ModuleId, version: SemVer4, dest_zip: HostPath, *,
        provider: Optional[str] = None, expected_sha256: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> HostPath: ...


class MirrorStore:
    """不可變本機鏡像倉（.mirror/<mod>/<ver>.zip 與 index.json 離線快取）。"""
    def __init__(self, *, yscb_root: HostPath) -> None: ...
    def has_package(self, module_id: ModuleId, version: SemVer4) -> bool: ...
    def get_package_path(self, module_id: ModuleId, version: SemVer4) -> HostPath: ...
    def verify_zip_integrity(
        self, zip_path: HostPath, *, expected_sha256: Optional[str] = None, ignore_sha256: bool = False,
    ) -> None: ...
    def save_index_cache(self, index: RemoteModuleIndex) -> None: ...
    def load_index_cache(self, module_id: ModuleId) -> Optional[RemoteModuleIndex]: ...


class DependencySolver:
    """依賴約束交集求解與三態自癒引擎（core 先行、index.json releases 覆寫優先、同 Major 鎖定）。"""
    def resolve_install_plan(
        self,
        requests: Sequence[PackageRequest],
        installed: Mapping[ModuleId, SemVer4],
        provider: ProviderClient,
        mirror: MirrorStore,
        *,
        same_major_only: bool = False,
    ) -> Mapping[ModuleId, tuple[SemVer4, Optional[IndexReleaseRecord]]]: ...

    def reconcile_installed_dependencies(
        self,
        installed: Mapping[ModuleId, SemVer4],
        provider: ProviderClient,
        mirror: MirrorStore,
    ) -> Mapping[ModuleId, SemVer4]: ...


class AtomicPackageDeployer:
    """Staging 預組裝、*.tmpl 模板部署與整目錄剝離、原子目錄替換與五大空間清理器。"""
    def __init__(self, *, yscb_root: HostPath, config_store: ConfigStore, vfs: KernelVfs) -> None: ...
    def materialize_module(
        self,
        module_id: ModuleId,
        zip_path: HostPath,
        *,
        release_override: Optional[IndexReleaseRecord] = None,
    ) -> ModuleManifest: ...
    def remove_module(self, module_id: ModuleId, *, purge_level: PurgeLevel = PurgeLevel.NONE) -> None: ...


class UpdateChecker:
    """12 小時節流更新探測器（前置寫入 last_checked_at、跨 pruned 聚合 critical、yscb.py LF SHA-256 漂移）。"""
    DEFAULT_INTERVAL_SEC: float = 12 * 3600.0
    DEFAULT_TIMEOUT_SEC: float = 2.0

    def __init__(
        self, *, host_dir: HostPath, yscb_root: HostPath, config_store: ConfigStore,
        provider: ProviderClient, self_update_url: str,
    ) -> None: ...
    def check_if_due(self, *, force: bool = False, offline: bool = False) -> UpdateCheckReport: ...


class OfflinePackageEngine:
    """純離線批次交易套件引擎（組合 SnapshotVault / Provider / Mirror / Solver / EnvPool / Deployer）。"""
    def __init__(
        self, *, host_dir: HostPath, yscb_root: HostPath, config_store: ConfigStore,
        snapshot_vault: SnapshotVault, env_pool: ImmutableVenvPool, vfs: KernelVfs,
    ) -> None: ...

    def install(
        self, requests: Sequence[PackageRequest], *, force: bool = False,
        ignore_sha256: bool = False, offline: bool = False, cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport: ...
    def update(
        self, modules: Sequence[ModuleId] = (), *, provider: Optional[str] = None,
        ignore_sha256: bool = False, offline: bool = False, cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport: ...
    def restore(
        self, *, provider: Optional[str] = None, force: bool = False,
        ignore_sha256: bool = False, offline: bool = False, cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport: ...
    def remove(
        self, modules: Sequence[ModuleId], *, purge_level: PurgeLevel = PurgeLevel.NONE,
        force: bool = False,
    ) -> DeploymentReport: ...
    def reload_from_mirror(self, *, offline: bool = True) -> DeploymentReport: ...
    def rollback(self, snapshot_id: Optional[str] = None) -> DeploymentReport: ...
```

---

## 3. 關鍵安全與容錯不變量（承襲 `DN-06`, `DN-14`, `DN-15`, `DN-16`, `DN-19`）

1. **依賴覆寫與三態自癒（`DN-15`, `DN-16`）**：
   - `index.json["releases"][ver]["dependencies"]` 永遠優先覆寫 Zip 內部 `manifest.json["dependencies"]`，且於解壓 Staging 時同步回寫入 `staging/manifest.json`，確保離線 `reload`/`rollback` 100% 冪等保留事後依賴修補。
   - `update` 預設鎖定同 Major（`^current_version`）並優先評估 `core` 候選版號；批次完成前執行 `reconcile_installed_dependencies`：全滿足即 $O(1)$ 短路、缺相依自動補裝、過舊自動交集升級、無交集即拋 `YscbError(ErrorCode.DEPENDENCY_CONFLICT)` 並由 `SnapshotVault.restore_snapshot()` 全量回滾。
2. **嚴格同版動態打包與 `pruned` 自動補位（`DN-14`）**：
   - 本地 `release/<mod>/` 缺失目標 `<ver>.zip` 時，僅於 `source/<mod>/manifest.json` 之 `version == target_version` 嚴格相等時方可即時打包寫入 `.mirror/`，嚴禁版本不符混裝或直接 `copytree` 源碼進 `.modules/`。
   - `restore` 遇到已被遠端滑動視窗淘汰之 `pruned` 版本且本機無鏡像時，自動補位同 `(major, minor, patch)` 三元組最高 `active` 版本並同步更新 `yscb.config.json`。
3. **Zip 安全、三階段目錄句柄探針與 `*.tmpl` 零殘留（`DN-06`, `DN-15`）**：
   - 下載採 20 MiB 串流上限、CRC (`testzip`) + SHA-256 校驗（`@build` 免檢或顯式 `--ignore-sha256`）與嚴格 Zip Slip 路徑邊界檢查；任何違規拋 `YscbError(ErrorCode.PACKAGE_INTEGRITY_ERROR)`。
   - Staging 完成 `config.schema.json` / `configurable/*.tmpl` 部署後，無條件整目錄刪除 `staging/configurable/` 與 `.yscbignore`。
   - 目錄原子替換（`.modules/<mod>` $\leftrightarrow$ `.old_*` $\leftrightarrow$ `.staging_*`）遇 `EACCES`/`EBUSY`/`WinError 5,32` 時，執行三階段句柄鎖探針（權限位元 $\to$ `.yscb_probe` 實機建立替換刪除 $\to$ 逐檔備份原子同步，任一失敗全量回滾原檔案）。
4. **批次交易失敗全量回滾**：`install` / `update` / `remove` / `restore` 開始前先經 `SnapshotVault.create_snapshot()` 取得保護點；任一環節（下載、求解、`.venv` 建置、物化或上層遷移 `Task`）失敗即還原快照與鏡像重物化。

---

## 4. 必測驗收門檻 (Verification Gate)

1. **套件完整性與安全邊界**：Zip Slip 路徑穿越、損毀 CRC、SHA-256 不符、超過 20 MiB 下載與 `--offline` 網路阻斷均精準拋錯並零殘留檔案。
2. **`*.tmpl` 剝離與 `DeepInfiller` 測試**：部署後 `.modules/<mod>/` 不含 `configurable/`、`.yscbignore` 或任何 `*.tmpl` 檔，保留 `manifest.json`/`tasks.index.json`/`config.schema.json`/`contributes/_schema.json`；既有使用者組態值 100% 原地保留。
3. **依賴求解與衝突回滾（`DN-15`, `DN-16`）**：`index.json` 覆寫 Zip 依賴生效、同 Major 升級鎖定、跨版本無交集拋 `DEPENDENCY_CONFLICT` 並完整還原 `SnapshotVault`；`pruned` 同三元組自動補位並更新 `yscb.config.json`。
4. **三級清理與 `UpdateChecker`**：`NONE`/`CLEAN`/`PURGE` 精準對應五大資料空間邊界；`UpdateChecker` 離線前置寫入 `last_checked_at` 零重複逾時、跨 `pruned` 聚合 `critical`、`yscb.py` LF 漂移偵測與沙盒靜音。
