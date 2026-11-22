# 子模組架構設計規格：`core.packaging.env`（方案 B 不可變雜湊 `.venv` 池、健康探針與回滾友善 GC）

> **所屬功能域**：`Domain 4 — 套件與環境域 (packaging/)`
> **模組路徑**：`core_v2/source/core/core/packaging/env/`
> **建議內部切分**：`spec.py`、`pool.py`、`probe.py`、`gc.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{fs, vfs}`、`metadata.config`
> **禁止反向依賴（Forbidden Imports）**：`packaging.installer`、`execution/*`、`surface/*`
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

> [!NOTE]
> **實作彈性邊界**：`.venv/<group>_<py_tag>_<hash16>/` 目錄契約、`.yscb_env_meta.json` 格式、`EnvSpec` / `EnvHealthReport` / `EnvGcPolicy` 語意與 `--only-binary=:all:` 防線屬硬契約；內部 `pip` 呼叫細節與重試輔助函式可由遠端實作端微調。

---

## 1. 模組定位與 1.x $\to$ 2.0 核心演化（對齊 `DR-04`）

`core.packaging.env` 實作方案 B 的**不可變內容雜湊虛擬環境池**，徹底根除 1.x 共享 `.venv/py312/` 在 Windows 上因 `.pyd`/`.dll` 句柄鎖定導致升級崩潰與執行期隱式 `pip install` 失控問題：

1. **雙層執行分流**：
   - **Tier 0 模組**（`manifest.pip_dependencies` 為空）：完全不建立 `.venv`，直接運行於內核 Python 進程。
   - **Tier 1 模組**（`manifest.pip_dependencies` 非空）：僅於安裝／升級／修復階段建立不可變 `.venv/<group>_<py_tag>_<hash16>/`；升級相依套件時直接建置新雜湊目錄並由上層切換新 Worker，舊目錄留待舊進程退出後回收。
2. **選配 `venv_group` 共置（Co-location）**：
   - 同組 `venv_group`（未宣告時預設為模組自身 `id`）內所有 Tier 1 模組的 `pip_dependencies` 合併解算為單一共享 `.venv`（例：`ast` 與 `knowledge-db` 共置於 `code_intel`），降低重複磁碟與記憶體開銷；跨模組跨進程呼叫仍 100% 經 `execution.runtime` 協調。
3. **100% 保留 1.x 跨平台防坑不變量（`DN-08`, `DN-10`）**：
   - `include-system-site-packages = false`。
   - 強制 `--only-binary=:all:` + `--no-warn-script-location`，嚴禁觸發源碼編譯風暴；無預編譯 Wheel 即拋 `YscbError(ErrorCode.ENV_BUILD_FAILED)`。
   - 建置前動態實測 `_can_symlink()`，於 `virtiofs` / 無符號連結權限之 Windows 自動降級 `copies=True` 並自宿主 `ensurepip` / wheel 補齊 `pip`。

---

## 2. 雜湊命名規則與原子 Staging 建置格式

### 2.1 `EnvHash` 計算因子與目錄命名
- **組名（`group`）**：`manifest.venv_group or manifest.id.value`（須經 `validate_relative_segment` 驗證）。
- **Python 標籤（`py_tag`）**：`f"py{sys.version_info.major}{sys.version_info.minor}"`（例 `py312`）。
- **規範化 Pip 規格合取（`canonical_pip_specs`）**：
  - 套件名稱依 PEP 503 正規化（小寫、連續 `[-_.]` 折疊為 `-`）。
  - 同組多模組宣告同一套件不同約束（如 `numpy>=1.26` 與 `numpy<2.0`）合併為排序去重之逗號合取（`numpy<2.0,>=1.26`），全清單依字典序排序。
- **雜湊計算**：`SHA-256(json_canonical({py_tag, sys.platform, platform.machine().lower(), canonical_pip_specs}))` 取前 16 hex。
- **目錄名稱**：`{yscb_root}/.venv/{group}_{py_tag}_{hash16}/`。

### 2.2 原子 Staging 與完成標記（`.yscb_env_meta.json`）
為防建置中途被 `Ctrl-C` 或斷電留下半成品環境，所有建置嚴格採原子三步：
1. 於 `{yscb_root}/.venv/.staging_{dirname}_{pid}_{seq}/` 建立虛擬環境並安裝套件（若 `--offline`，改傳 `--no-index --find-links=<wheel_cache>`）。
2. 所有 `pip install` 成功退出後，以 `fs.atomic_write_json` 寫入 `.yscb_env_meta.json`（含 `"complete": true`）。
3. 透過 `os.replace` 將 Staging 目錄原子更名為 `{yscb_root}/.venv/{dirname}/`（若並發已由他進程搶先建成有效目標，安全清理自身 Staging 並直接復用既有環境）。

---

## 3. 核心公開契約規格 (`core/packaging/env/`)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from core.foundation.observability import CancellationToken
from core.foundation.primitives import EnvHash, HostPath, ModuleId
from core.metadata.config import ModuleManifest


@dataclass(frozen=True, slots=True)
class EnvSpec:
    """不可變 Tier 1 虛擬環境規格描述。"""
    group: str
    py_tag: str
    platform_tag: str
    pip_specs: tuple[str, ...]
    env_hash: EnvHash

    @property
    def dirname(self) -> str: ...  # "{group}_{py_tag}_{env_hash.short(16)}"


@dataclass(frozen=True, slots=True)
class EnvMetadata:
    """落盤於 <env_dir>/.yscb_env_meta.json 之完成標記與審計元數據。"""
    group: str
    env_hash: EnvHash
    py_tag: str
    platform_tag: str
    pip_specs: tuple[str, ...]
    created_at_utc: str
    last_used_epoch_sec: float
    complete: bool = True


@dataclass(frozen=True, slots=True)
class EnvBuildResult:
    spec: EnvSpec
    env_dir: HostPath
    python_exe: HostPath
    reused: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class EnvHealthReport:
    spec: Optional[EnvSpec]
    env_dir: HostPath
    quick_ok: bool
    deep_import_ok: Optional[bool] = None
    issues: tuple[str, ...] = ()
```


@dataclass(frozen=True, slots=True)
class EnvGcPolicy:
    """回滾友善孤兒環境回收策略（與 SnapshotVault 7 天視窗對齊，退化為即時回收僅需設為 0）。"""
    grace_days: float = 7.0
    keep_inactive_per_group: int = 1


@dataclass(frozen=True, slots=True)
class EnvGcResult:
    removed_dirs: tuple[HostPath, ...] = ()
    skipped_locked_dirs: tuple[HostPath, ...] = ()
    retained_rollback_dirs: tuple[HostPath, ...] = ()
    cleaned_staging_dirs: tuple[HostPath, ...] = ()


class ImmutableVenvPool:
    """不可變內容雜湊 .venv 池管理器（純標準庫建置，零執行期隱式 pip）。"""
    def __init__(self, *, yscb_root: HostPath, cache_dir: HostPath) -> None: ...

    @staticmethod
    def compute_env_spec(group: str, pip_dependencies: Mapping[str, str]) -> EnvSpec: ...
    @staticmethod
    def resolve_group_specs(manifests: Sequence[ModuleManifest]) -> Mapping[ModuleId, EnvSpec]: ...

    def get_env_dir(self, spec: EnvSpec) -> HostPath: ...
    def get_python_executable(self, spec: EnvSpec) -> Optional[HostPath]: ...
    def is_env_ready(self, spec: EnvSpec) -> bool: ...
    def list_envs(self) -> tuple[tuple[HostPath, Optional[EnvMetadata]], ...]: ...
    def ensure_env(
        self,
        spec: EnvSpec,
        *,
        offline: bool = False,
        wheel_cache_dir: Optional[HostPath] = None,
        timeout_sec: float = 300.0,
        cancel_token: Optional[CancellationToken] = None,
    ) -> EnvBuildResult: ...


class EnvHealthProbe:
    """分級健康探針：日常 O(1) 標記檔快速檢查，異常或 env check 時才開子進程深度驗證。"""
    def __init__(self, pool: ImmutableVenvPool) -> None: ...
    def check_quick(self, spec: EnvSpec) -> EnvHealthReport: ...
    def check_deep(
        self, spec: EnvSpec, *, import_modules: Sequence[str] = (), timeout_sec: float = 15.0,
    ) -> EnvHealthReport: ...
    def repair(
        self, spec: EnvSpec, *, offline: bool = False, wheel_cache_dir: Optional[HostPath] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> EnvBuildResult: ...


class EnvGarbageCollector:
    """非阻塞孤兒環境回收器（保留近期離線回滾環境；Windows 鎖檔跳過不阻斷升級）。"""
    def __init__(
        self, pool: ImmutableVenvPool, *, policy: EnvGcPolicy = EnvGcPolicy(),
    ) -> None: ...
    def collect(
        self, active_specs: Sequence[EnvSpec], *, force_all: bool = False,
    ) -> EnvGcResult: ...
```

---

## 4. 關鍵行為與跨平台防坑不變量

1. **單一跨進程建置鎖**：建置特定 `EnvSpec` 時，於 `{cache_dir}/locks/env_{env_hash.short(16)}.lock` 取得 `filesystem.fs.FileLock`，防止並發安裝同一組 Tier 1 模組重複執行 `pip install`；第二位等待者在鎖釋放後直接命中已就緒的 `is_env_ready(spec)` 零成本復用。
2. **`pip install` 嚴格安全旗標（`DN-08`）**：
   - 所有子進程一律透過 `foundation.proc.ManagedProcessTree` 啟動並帶顯式 `timeout_sec` 與 `cancel_token`（中途取消立即清殺整棵子進程樹並刪除 `.staging_*` 殘留目錄）。
   - 固定附加 `--only-binary=:all:`、`--no-warn-script-location`、`--disable-pip-version-check`；若 `offline=True` 或環境變數 `YSCB_OFFLINE=1` 則強制加入 `--no-index`（並於提供 `wheel_cache_dir` 時附加 `--find-links`）。
3. **`virtiofs` / Windows 符號連結降級（`DN-10`）**：
   - 建置 `.venv` 前於 `.venv/` 目錄內執行 `_can_symlink()` 實測（建立暫存 symlink、驗證 `realpath`、立即刪除）；探測失敗自動呼叫 `venv.EnvBuilder(symlinks=False, with_pip=False)`（即 `copies=True`）並自宿主 Python 補齊 `pip`。
4. **回滾友善 GC 與 Windows 鎖檔容忍（E3-A）**：
   - `EnvGarbageCollector.collect(active_specs)` 優先清理所有孤兒 `.staging_*` 殘留目錄（跳過 PID 仍存活之建置中暫存目錄）。
   - 對非活躍且非當前 `active_specs` 之舊環境：若 `force_all=False`，每個 `group` 保留最新 `keep_inactive_per_group`（預設 `1`）份且未超過 `grace_days`（預設 `7` 天）之環境，讓 `yscb rollback` 可毫秒級離線切換回舊環境無須重跑 `pip`；超出門檻者以 `robust_rmtree` 清理，若於 Windows 上仍被舊 Worker 鎖定（`PermissionError`），記入 `skipped_locked_dirs` 並於下次啟動／`yscb env gc` 自動補清。
5. **跨平台 IDE 路徑輔助**：提供 `get_site_packages_dirs(spec)` 同時輸出 POSIX (`lib/pythonX.Y/site-packages`) 與 Windows (`Lib/site-packages`) 雙候選路徑供 `vscode-support` 消費（`DN-09`）。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **雜湊決定性與 `venv_group` 共置測試**：同組多模組 pip 規格依任意順序傳入產出相同 `EnvHash`；同套件雙約束正確合併為合取條件；Tier 0 模組零建立 `.venv`。
2. **原子 Staging 與斷電半成品隔離**：缺少 `.yscb_env_meta.json` 或 `complete=False` 之殘留目錄必被 `check_quick` 判定不健康且不被 `is_env_ready` 復用；`cancel_token` 觸發取消後不留孤兒進程或殘留目標目錄。
3. **`--only-binary=:all:` 與 `--offline` 守門**：命令參數必含 `--only-binary=:all:`；離線模式下無對應 wheel 立即拋 `ENV_BUILD_FAILED` 且零對外網路連線。
4. **回滾友善 GC（E3-A）與鎖檔容忍**：升級後保留最新 1 份歷史環境於 7 天內供離線回滾；超過 7 天或 `force_all=True` 完整清除；模擬鎖檔時記入 `skipped_locked_dirs` 而不中斷流程。
