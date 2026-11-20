# 子模組架構設計規格：`core.filesystem.fs`（無符號連結原子寫入、防死鎖跨進程檔案鎖與輪詢目錄監聽器）

> **所屬功能域**：`Domain 2 — 檔案、空間與儲存域 (filesystem/)`
> **模組路徑**：`core_v2/source/core/core/filesystem/fs/`
> **內部模組職責切分**：`atomic.py`、`lock.py`、`watcher.py`
> **依賴上限（Allowed Imports）**：`foundation/*`
> **禁止反向依賴（Forbidden Imports）**：`metadata/*`、`packaging/*`、`execution/*`、`surface/*`（100% 業務與呼叫樹無涉）
> **狀態**：`Active Living Spec — Implementation-Aligned SSOT`

## 1. 核心職責與設計不變量

1. **零符號連結／重解析點穿越與原子寫入（`atomic.py`）**：所有受管檔案寫入均透過同目錄 `.tmp_*` 暫存、`fsync` 與 `os.replace` 原子替換完成；`resolve_contained_subpath`、`resolve_contained_child_dir`、`is_contained_nonsymlink_path` 與 `walk_nonsymlink_dir_tree` 全鏈路拒絕符號連結、Windows 重解析點、NTFS `:` 資料流與保留裝置逃逸。
2. **支援升降級防死鎖與純 OS 存活校驗之跨進程檔案鎖（`lock.py`）**：`FileLock` 追蹤共享／排他持鎖狀態（`is_shared`），以 `.upg` 升級預約鎖即時攔截雙共享持有者同時升級死鎖並保留 POSIX 既有共享鎖不被中斷摧毀；`read_live_owner_dict` 與 `write_cross_proc_owner_json` 僅檢驗純 OS `pid` 存活與 `start_tag` 防重用，零耦合上層 `execution` 呼叫樹欄位。
3. **純標準庫防抖與免回音目錄監聽器（`watcher.py`）**：`PollingDirectoryWatcher` 支援遞迴快照比對、防抖合併、`EchoSuppressionHook` 自寫抑制與 `resync_paths` 即時同步。

## 2. 公開契約規格 (`core.filesystem.fs.__all__` 完整快照)

```python
from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable, Final, Optional

from core.foundation import CancellationToken, HostPath, JsonObject, MutableJsonObject

IGNORED_FS_PREFIXES: Final[tuple[str, ...]] = (".tmp_", ".staging_", "__pycache__")
MAX_JSON_FILE_BYTES: Final[int] = 4 * 1024 * 1024

BeforeReplaceHook = Callable[[int, int, int], None]

EchoSuppressionHook = Callable[[HostPath, int, int, int], bool]

def acquire_verified_cross_proc_pin(owner_path: HostPath, pin_path: HostPath, owner_pred: Callable[[HostPath], bool], *, timeout_sec: float, cancel_token: CancellationToken) -> Optional[FileLock]:
    ...

def assert_no_symlink_raw_path(raw_path: str) -> None:
    ...

def atomic_write_bytes(dest: HostPath, data: bytes, *, before_replace: Optional[BeforeReplaceHook]=None, file_mode: Optional[int]=None) -> None:
    ...

def atomic_write_json(dest: HostPath, payload: JsonObject, *, before_replace: Optional[BeforeReplaceHook]=None, file_mode: Optional[int]=None) -> None:
    ...

def has_symlink_raw_path(raw_path: str) -> bool:
    ...

def hash_nofollow_regular_sha256(raw_path: str, *, expected_stat: Optional[os.stat_result]=None) -> str:
    ...

def is_atomic_staging_filename(name: str) -> bool:
    ...

def is_contained_nonsymlink_path(root: HostPath | Path | str, candidate: HostPath | Path | str, *, allow_equal: bool=False, is_dir: bool=False, ignored_dir_prefixes: tuple[str, ...]=()) -> bool:
    ...

def is_symlink_or_reparse(raw_path: str) -> bool:
    ...

def read_json_dict(src: HostPath, *subparts: str, max_bytes: int=MAX_JSON_FILE_BYTES) -> Optional[MutableJsonObject]:
    ...

def read_live_owner_dict(owner_path: HostPath) -> Optional[JsonObject]:
    ...

def read_nofollow_regular_bytes(raw_path: str, *, max_bytes: Optional[int]=None, expected_stat: Optional[os.stat_result]=None) -> Optional[bytes]:
    ...

def resolve_contained_child_dir(parent_dir: HostPath, candidate_dir: Optional[HostPath | str]=None, *, expected_name: Optional[str]=None, guarded_name: Optional[str]=None) -> Optional[HostPath]:
    ...

def resolve_contained_subpath(root: HostPath, *parts: str) -> HostPath:
    ...

def silent_unlink(target: HostPath) -> None:
    ...

def silent_unlink_contained(root: HostPath, *parts: str) -> None:
    ...

def try_acquire_contained_lock(root: HostPath, *parts: str, shared: bool=True, timeout_sec: Optional[float]=None, cancel_token: Optional[CancellationToken]=None) -> Optional[FileLock]:
    ...

def try_resolve_contained_subpath(root: HostPath, *parts: str) -> Optional[HostPath]:
    ...

def unlink_owner_under_pin(owner_path: HostPath, pin_path: HostPath, after_unlink: Callable[[], None], *, grace_timeout_sec: float=5.0) -> None:
    ...

def walk_nonsymlink_dir_tree(root_dir: str, *, ignored_dir_prefixes: tuple[str, ...]=('.tmp_', '.staging_', '__pycache__')) -> Iterator[tuple[str, tuple[os.DirEntry[str], ...]]]:
    ...

def write_cross_proc_owner_json(owner_path: HostPath, payload: JsonObject) -> None:
    ...

@dataclass(frozen=True, slots=True)
class CrossProcessLockPaths:
    lock_file: FileLock
    owner_path: HostPath
    pin_path: HostPath

    @classmethod
    def for_stem(cls, locks_dir: HostPath, stem: str, *, allow_transitions: bool=True) -> CrossProcessLockPaths:
        ...

class FileLock:

    def __init__(self, lock_path: HostPath, *, allow_transitions: bool=True) -> None:
        ...

    @property
    def lock_path(self) -> HostPath:
        ...

    @property
    def is_acquired(self) -> bool:
        ...

    @property
    def is_shared(self) -> bool:
        ...

    def acquire(self, *, shared: bool=False, blocking: bool=True, timeout_sec: Optional[float]=None, cancel_token: Optional[CancellationToken]=None) -> bool:
        ...

    def release(self) -> None:
        ...

    def upgrade_to_exclusive(self, *, timeout_sec: Optional[float]=None, cancel_token: Optional[CancellationToken]=None) -> None:
        ...

    def downgrade_to_shared(self, *, timeout_sec: float=10.0, cancel_token: Optional[CancellationToken]=None) -> None:
        ...

    def __enter__(self) -> FileLock:
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

class PollingDirectoryWatcher:

    def __init__(self, roots: Sequence[HostPath], on_changed: Callable[[frozenset[HostPath]], None], *, debounce_sec: float=0.2, poll_interval_sec: float=0.05, is_suppressed: Optional[EchoSuppressionHook]=None) -> None:
        ...

    @property
    def tracked_paths(self) -> frozenset[HostPath]:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def resync_paths(self, under_roots: Sequence[HostPath]) -> frozenset[HostPath]:
        ...
```
