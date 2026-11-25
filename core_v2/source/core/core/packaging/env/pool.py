"""Immutable content-hashed virtual environment pool with atomic staging builds and cross-process locking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Callable, ClassVar, Final, Mapping, Optional, Sequence
import uuid
import venv
import weakref

from core.filesystem.fs import (
    FileLock,
    is_symlink_or_reparse,
    resolve_contained_subpath,
    silent_unlink,
    try_resolve_contained_subpath,
)
from core.foundation.errors import ErrorCode, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, require_non_negative_sec
from core.foundation.primitives import (
    EnvHash,
    HostPath,
    ModuleId,
    require_pure_bool,
    safe_real_to_float,
    safe_realpath,
)
from core.foundation.proc import ManagedProcessTree, build_isolated_python_env, is_public_env_truthy
from core.metadata.config import ModuleManifest
from core.packaging.env.spec import (
    EnvBuildResult,
    EnvMetadata,
    EnvSpec,
    env_compute_spec_from_deps,
    env_find_python_exe,
    env_quick_probe_issues,
    env_read_metadata,
    env_resolve_manifest_specs,
    env_robust_rmtree,
    env_write_metadata,
)

_VENV_DIRNAME: Final[str] = ".venv"
_LOCKS_SUBDIR: Final[str] = "locks"
_REPLACE_MAX_ATTEMPTS: Final[int] = 6


def _resolve_venv_subpath_nofollow(env_dir: HostPath, *parts: str) -> HostPath:
    cur = str(env_dir)
    last_idx = len(parts) - 1
    for idx, seg in enumerate(parts):
        nxt = os.path.join(cur, seg)
        if is_symlink_or_reparse(nxt):
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"Refusing symlink or reparse point inside '{env_dir}': {nxt}",
            )
        if os.path.lexists(nxt):
            if idx < last_idx and not os.path.isdir(nxt):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Non-directory intermediate path inside '{env_dir}': {nxt}",
                )
            real_nxt = safe_realpath(nxt)
            if (
                os.path.normcase(os.path.dirname(real_nxt)) != os.path.normcase(cur)
                or os.path.basename(real_nxt).casefold() != seg.casefold()
            ):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing redirected path inside '{env_dir}': {nxt}",
                )
            cur = real_nxt
        else:
            cur = nxt
    return HostPath(cur)


def _probe_can_symlink(venv_root: HostPath) -> bool:
    token = f"{os.getpid()}_{uuid.uuid4().hex[:12]}"
    target_path = venv_root.path / f".tmp_sym_target_{token}"
    link_path = venv_root.path / f".tmp_sym_link_{token}"
    try:
        target_path.write_bytes(b"")
        os.symlink(str(target_path), str(link_path))
        if not os.path.islink(link_path):
            return False
        real_link = os.path.normcase(safe_realpath(str(link_path)))
        real_target = os.path.normcase(safe_realpath(str(target_path)))
        return real_link == real_target
    except (OSError, NotImplementedError):
        return False
    finally:
        for candidate in (link_path, target_path):
            try:
                if os.path.lexists(candidate):
                    os.unlink(candidate)
            except OSError:
                pass


def _create_stdlib_staging_venv(staging_dir: HostPath, *, can_symlink: bool) -> None:
    try:
        builder = venv.EnvBuilder(
            system_site_packages=False,
            clear=False,
            symlinks=can_symlink,
            upgrade=False,
            with_pip=False,
        )
        builder.create(str(staging_dir))
        return
    except OSError as first_exc:
        if not can_symlink:
            raise YscbError(
                ErrorCode.ENV_BUILD_FAILED,
                f"Failed to create virtual environment at '{staging_dir}': {safe_exception_summary(first_exc)}",
            ) from first_exc
    try:
        _rmtree_staging_with_retry(staging_dir.path)
        fallback_builder = venv.EnvBuilder(
            system_site_packages=False,
            clear=False,
            symlinks=False,
            upgrade=False,
            with_pip=False,
        )
        fallback_builder.create(str(staging_dir))
    except OSError as retry_exc:
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"Failed to create virtual environment at '{staging_dir}': {safe_exception_summary(retry_exc)}",
        ) from retry_exc


def _build_pip_install_argv(
    staging_python: HostPath,
    spec: EnvSpec,
    *,
    offline: bool,
    wheel_cache_dir: Optional[HostPath],
) -> list[str]:
    argv: list[str] = [
        sys.executable,
        "-I",
        "-m",
        "pip",
        "--isolated",
        "--python",
        str(staging_python),
        "install",
        "--only-binary=:all:",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--no-input",
    ]
    if offline:
        argv.append("--no-index")
    if wheel_cache_dir is not None:
        argv.append(f"--find-links={wheel_cache_dir}")
    argv.extend(spec.pip_specs)
    return argv


def _run_pip_install_supervised(
    pip_argv: Sequence[str],
    *,
    staging_dir: HostPath,
    spec: EnvSpec,
    deadline: float,
    cancel_token: Optional[CancellationToken],
) -> None:
    try:
        proc_tree = ManagedProcessTree(pip_argv, cwd=staging_dir, env=build_isolated_python_env(), inherit_tty=False)
    except OSError as exc:
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"Failed to launch pip installer for '{spec.dirname}': {safe_exception_summary(exc)}",
        ) from exc
    with proc_tree:
        while True:
            if cancel_token is not None and cancel_token.is_cancelled:
                proc_tree.kill_tree_now()
                cancel_token.raise_if_cancelled()
            exit_code = proc_tree.poll()
            if exit_code is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                proc_tree.kill_tree_now()
                raise YscbError(
                    ErrorCode.TASK_TIMEOUT,
                    f"Timed out building virtual environment '{spec.dirname}'.",
                )
            wait_slice = min(0.02, max(0.002, remaining))
            if cancel_token is not None:
                cancel_token.wait(wait_slice)
            else:
                time.sleep(wait_slice)
    if exit_code != 0:
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"pip install exited with code {exit_code} while building '{spec.dirname}'.",
        )


def _populate_verified_staging_venv(
    staging_dir: HostPath,
    spec: EnvSpec,
    *,
    eff_offline: bool,
    wheel_cache_dir: Optional[HostPath],
    deadline: float,
    cancel_token: Optional[CancellationToken],
) -> None:
    venv_root = HostPath(str(staging_dir.path.parent))
    if time.monotonic() >= deadline:
        raise YscbError(
            ErrorCode.TASK_TIMEOUT,
            f"Timed out preparing staging directory for '{spec.dirname}'.",
        )
    can_sym = _probe_can_symlink(venv_root)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    _create_stdlib_staging_venv(staging_dir, can_symlink=can_sym)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    staging_py = env_find_python_exe(staging_dir)
    if staging_py is None:
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"Staging virtual environment missing Python interpreter: {staging_dir}",
        )
    if spec.pip_specs:
        pip_argv = _build_pip_install_argv(
            staging_py,
            spec,
            offline=eff_offline,
            wheel_cache_dir=wheel_cache_dir,
        )
        _run_pip_install_supervised(
            pip_argv,
            staging_dir=staging_dir,
            spec=spec,
            deadline=deadline,
            cancel_token=cancel_token,
        )
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    now_epoch = time.time()
    created_utc = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = EnvMetadata(
        group=spec.group,
        env_hash=spec.env_hash,
        py_tag=spec.py_tag,
        platform_tag=spec.platform_tag,
        pip_specs=spec.pip_specs,
        created_at_utc=created_utc,
        last_used_epoch_sec=now_epoch,
        complete=True,
    )
    env_write_metadata(staging_dir, meta)
    post_issues = env_quick_probe_issues(staging_dir, spec)
    if post_issues:
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"Staging environment verification failed for '{spec.dirname}': {'; '.join(post_issues)}",
        )


def touch_env_last_used(env_dir: HostPath, *, min_interval_sec: float = 3600.0) -> bool:
    """Safely update last_used_epoch_sec in .yscb_env_meta.json when complete and past min_interval_sec."""
    if not isinstance(env_dir, HostPath):
        raise ValueError(f"env_dir must be HostPath, got {env_dir!r}")
    interval = safe_real_to_float(min_interval_sec, label="min_interval_sec")
    if not math.isfinite(interval):
        raise ValueError(f"min_interval_sec must be finite, got {min_interval_sec!r}")
    raw_env = str(env_dir)
    if is_symlink_or_reparse(raw_env) or not os.path.isdir(raw_env):
        return False
    try:
        meta = env_read_metadata(env_dir)
    except (OSError, ValueError, YscbError):
        return False
    if meta is None or not meta.complete:
        return False
    now_epoch = time.time()
    if interval > 0.0 and (now_epoch - meta.last_used_epoch_sec) < interval:
        return False
    updated = EnvMetadata(
        group=meta.group,
        env_hash=meta.env_hash,
        py_tag=meta.py_tag,
        platform_tag=meta.platform_tag,
        pip_specs=meta.pip_specs,
        created_at_utc=meta.created_at_utc,
        last_used_epoch_sec=now_epoch,
        complete=True,
    )
    try:
        env_write_metadata(env_dir, updated)
    except (OSError, ValueError, YscbError):
        return False
    return True


def _rmtree_staging_with_retry(target_dir: Path) -> None:
    """Remove a staging or evicted directory with short retries for transient OS handle release."""
    for attempt in range(4):
        if not os.path.lexists(str(target_dir)):
            return
        try:
            env_robust_rmtree(target_dir, clear_readonly_files=True)
            return
        except OSError:
            if not os.path.lexists(str(target_dir)):
                return
            if attempt == 3:
                raise
            time.sleep(0.015 * (attempt + 1))


def _elapsed_duration_ms(started_ns: int) -> int:
    return max(0, (time.monotonic_ns() - started_ns) // 1_000_000)


@dataclass(frozen=True, slots=True)
class _EnvPoolCoords:
    yscb_root: HostPath
    cache_dir: HostPath
    next_seq: Callable[[ImmutableVenvPool], int]


class _EnvPoolRegistry:
    """Weak registry mapping ImmutableVenvPool instances to lock and root coordinates."""

    guard: ClassVar[threading.Lock] = threading.Lock()
    entries: ClassVar[weakref.WeakKeyDictionary[ImmutableVenvPool, _EnvPoolCoords]] = (
        weakref.WeakKeyDictionary()
    )

    @classmethod
    def register(
        cls,
        pool: ImmutableVenvPool,
        yscb_root: HostPath,
        cache_dir: HostPath,
        seq_fn: Callable[[ImmutableVenvPool], int],
    ) -> None:
        with cls.guard:
            cls.entries[pool] = _EnvPoolCoords(
                yscb_root=yscb_root,
                cache_dir=cache_dir,
                next_seq=seq_fn,
            )

    @classmethod
    def lookup(cls, pool: ImmutableVenvPool) -> _EnvPoolCoords:
        with cls.guard:
            return cls.entries[pool]


class ImmutableVenvPool:
    """不可變內容雜湊 .venv 池管理器（純標準庫建置，零執行期隱式 pip）。"""

    def __init__(self, *, yscb_root: HostPath, cache_dir: HostPath) -> None:
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"yscb_root must be HostPath, got {yscb_root!r}")
        if not isinstance(cache_dir, HostPath):
            raise ValueError(f"cache_dir must be HostPath, got {cache_dir!r}")
        resolve_contained_subpath(yscb_root)
        resolve_contained_subpath(cache_dir)
        self._yscb_root = yscb_root
        self._cache_dir = cache_dir
        self._seq_lock = threading.Lock()
        self._staging_seq = 0
        _EnvPoolRegistry.register(self, yscb_root, cache_dir, ImmutableVenvPool._next_staging_seq)

    def _next_staging_seq(self) -> int:
        with self._seq_lock:
            self._staging_seq += 1
            return self._staging_seq

    def _evict_corrupt_target_dir(self, venv_root: HostPath, env_dir: HostPath, spec: EnvSpec) -> None:
        raw_env = str(env_dir)
        if not os.path.lexists(raw_env):
            return
        evict_name = f".staging_evict_{spec.dirname}_{os.getpid()}_{self._next_staging_seq()}"
        evict_dir = resolve_contained_subpath(venv_root, evict_name)
        try:
            os.replace(raw_env, str(evict_dir))
        except FileNotFoundError:
            return
        except OSError:
            try:
                _rmtree_staging_with_retry(env_dir.path)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.ENV_BUILD_FAILED,
                    f"Cannot remove incomplete target directory '{env_dir}': {safe_exception_summary(exc)}",
                ) from exc
            return
        try:
            _rmtree_staging_with_retry(evict_dir.path)
        except OSError:
            pass

    def _promote_staging_to_target(self, venv_root: HostPath, staging_dir: HostPath, env_dir: HostPath, spec: EnvSpec) -> bool:
        if self.is_env_ready(spec):
            return True
        if os.path.lexists(str(env_dir)):
            self._evict_corrupt_target_dir(venv_root, env_dir, spec)
        last_exc: Optional[OSError] = None
        for attempt in range(_REPLACE_MAX_ATTEMPTS):
            if self.is_env_ready(spec):
                return True
            try:
                os.replace(str(staging_dir), str(env_dir))
                return False
            except OSError as exc:
                last_exc = exc
                if self.is_env_ready(spec):
                    return True
                if attempt + 1 < _REPLACE_MAX_ATTEMPTS:
                    time.sleep(0.01 * (attempt + 1))
        detail = safe_exception_summary(last_exc) if last_exc is not None else "unknown error"
        raise YscbError(
            ErrorCode.ENV_BUILD_FAILED,
            f"Failed to atomically promote staging environment to '{env_dir}': {detail}",
        )

    @staticmethod
    def compute_env_spec(group: str, pip_dependencies: Mapping[str, str]) -> EnvSpec:
        return env_compute_spec_from_deps(group, pip_dependencies)

    @staticmethod
    def resolve_group_specs(manifests: Sequence[ModuleManifest]) -> Mapping[ModuleId, EnvSpec]:
        return env_resolve_manifest_specs(manifests)

    def get_env_dir(self, spec: EnvSpec) -> HostPath:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        return resolve_contained_subpath(self._yscb_root, _VENV_DIRNAME, spec.dirname)

    def get_site_packages_dirs(self, spec: EnvSpec) -> tuple[HostPath, HostPath]:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        env_dir = self.get_env_dir(spec)
        py_digits = spec.py_tag[2:] if spec.py_tag.startswith("py") else ""
        if len(py_digits) >= 2 and py_digits.isdigit():
            dotted_ver = f"{py_digits[0]}.{py_digits[1:]}"
        else:
            dotted_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        posix_sp = _resolve_venv_subpath_nofollow(env_dir, "lib", f"python{dotted_ver}", "site-packages")
        win_sp = _resolve_venv_subpath_nofollow(env_dir, "Lib", "site-packages")
        return (posix_sp, win_sp)

    def get_python_executable(self, spec: EnvSpec) -> Optional[HostPath]:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        if not self.is_env_ready(spec):
            return None
        try:
            env_dir = self.get_env_dir(spec)
        except YscbError:
            return None
        return env_find_python_exe(env_dir)

    def is_env_ready(self, spec: EnvSpec) -> bool:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        try:
            env_dir = self.get_env_dir(spec)
        except YscbError:
            return False
        return len(env_quick_probe_issues(env_dir, spec)) == 0

    def list_envs(self) -> tuple[tuple[HostPath, Optional[EnvMetadata]], ...]:
        venv_root = try_resolve_contained_subpath(self._yscb_root, _VENV_DIRNAME)
        if venv_root is None or not os.path.isdir(str(venv_root)) or is_symlink_or_reparse(str(venv_root)):
            return ()
        try:
            with os.scandir(str(venv_root)) as entries_it:
                entries = sorted(entries_it, key=lambda item: item.name)
        except OSError:
            return ()
        results: list[tuple[HostPath, Optional[EnvMetadata]]] = []
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name == "__pycache__":
                continue
            if entry.is_symlink() or is_symlink_or_reparse(entry.path):
                continue
            try:
                is_subdir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if not is_subdir:
                continue
            cand_dir = try_resolve_contained_subpath(venv_root, name)
            if cand_dir is None:
                continue
            results.append((cand_dir, env_read_metadata(cand_dir)))
        return tuple(results)

    def ensure_env(
        self,
        spec: EnvSpec,
        *,
        offline: bool = False,
        wheel_cache_dir: Optional[HostPath] = None,
        timeout_sec: float = 300.0,
        cancel_token: Optional[CancellationToken] = None,
    ) -> EnvBuildResult:
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"spec must be EnvSpec, got {spec!r}")
        require_pure_bool(offline, "offline")
        eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        if wheel_cache_dir is not None and not isinstance(wheel_cache_dir, HostPath):
            raise ValueError(f"wheel_cache_dir must be HostPath or None, got {wheel_cache_dir!r}")
        if cancel_token is not None and not isinstance(cancel_token, CancellationToken):
            raise ValueError(f"cancel_token must be CancellationToken or None, got {cancel_token!r}")
        safe_timeout = require_non_negative_sec(timeout_sec, label="timeout_sec")
        started_ns = time.monotonic_ns()
        deadline = time.monotonic() + safe_timeout
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

        rem_for_lock = deadline - time.monotonic()
        if rem_for_lock <= 0.0:
            raise YscbError(
                ErrorCode.TASK_TIMEOUT,
                f"Timed out before acquiring build lock for environment '{spec.dirname}'.",
            )
        lock_path = resolve_contained_subpath(
            self._cache_dir,
            _LOCKS_SUBDIR,
            f"env_{spec.env_hash.short(16)}.lock",
        )
        build_lock = FileLock(lock_path, allow_transitions=False)
        build_lock.acquire(
            shared=False,
            blocking=True,
            timeout_sec=rem_for_lock,
            cancel_token=cancel_token,
        )
        try:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            env_dir = self.get_env_dir(spec)
            if self.is_env_ready(spec):
                locked_py = env_find_python_exe(env_dir)
                if locked_py is not None:
                    touch_env_last_used(env_dir, min_interval_sec=0.0)
                    return EnvBuildResult(
                        spec=spec,
                        env_dir=env_dir,
                        python_exe=locked_py,
                        reused=True,
                        duration_ms=_elapsed_duration_ms(started_ns),
                    )

            venv_root = resolve_contained_subpath(self._yscb_root, _VENV_DIRNAME)
            try:
                os.makedirs(str(venv_root), exist_ok=True)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.ENV_BUILD_FAILED,
                    f"Failed to create .venv root directory '{venv_root}': {safe_exception_summary(exc)}",
                ) from exc
            venv_root = resolve_contained_subpath(self._yscb_root, _VENV_DIRNAME)

            staging_name = f".staging_{spec.dirname}_{os.getpid()}_{self._next_staging_seq()}"
            staging_dir = resolve_contained_subpath(venv_root, staging_name)
            try:
                _populate_verified_staging_venv(
                    staging_dir,
                    spec,
                    eff_offline=eff_offline,
                    wheel_cache_dir=wheel_cache_dir,
                    deadline=deadline,
                    cancel_token=cancel_token,
                )
                reused_after_race = self._promote_staging_to_target(venv_root, staging_dir, env_dir, spec)
            except TaskCancelledException:
                raise
            finally:
                if os.path.lexists(str(staging_dir)):
                    try:
                        _rmtree_staging_with_retry(staging_dir.path)
                    except OSError:
                        pass

            final_py = env_find_python_exe(env_dir)
            if final_py is None:
                raise YscbError(
                    ErrorCode.ENV_BUILD_FAILED,
                    f"Promoted virtual environment missing Python interpreter: {env_dir}",
                )
            return EnvBuildResult(
                spec=spec,
                env_dir=env_dir,
                python_exe=final_py,
                reused=reused_after_race,
                duration_ms=_elapsed_duration_ms(started_ns),
            )
        finally:
            build_lock.release()


def env_resolve_venv_root(pool: ImmutableVenvPool) -> HostPath:
    """Resolve the contained .venv root directory managed by pool using only its public interface."""
    sentinel = EnvSpec(
        group="probe",
        py_tag="py312",
        platform_tag="probe",
        pip_specs=("probe",),
        env_hash=EnvHash("0" * 16),
    )
    sentinel_dir = pool.get_env_dir(sentinel)
    return HostPath(sentinel_dir.path.parent)


def env_extract_dirname_tail_hash(dirname: str) -> Optional[EnvHash]:
    """Extract the 16-hex EnvHash suffix from a managed .venv/<group>_<py_tag>_<hash16> directory name."""
    idx = dirname.rfind("_")
    if idx <= 0:
        return None
    cand = dirname[idx + 1 :]
    if len(cand) != 16:
        return None
    try:
        return EnvHash(cand)
    except ValueError:
        return None


def env_try_acquire_hash_lock_nonblocking(pool: ImmutableVenvPool, env_hash: EnvHash) -> Optional[FileLock]:
    """Attempt a non-blocking exclusive lock acquisition for env_hash, returning None if contended."""
    coords = _EnvPoolRegistry.lookup(pool)
    cache_dir = coords.cache_dir
    lock_path = resolve_contained_subpath(
        cache_dir,
        _LOCKS_SUBDIR,
        f"env_{env_hash.short(16)}.lock",
    )
    lock_obj = FileLock(lock_path, allow_transitions=False)
    if not lock_obj.acquire(shared=False, blocking=False):
        return None
    return lock_obj


def acquire_env_shared_lease(pool: ImmutableVenvPool, env_hash: EnvHash) -> Optional[FileLock]:
    """Acquire a non-blocking shared lock on env_<hash>.lock to shield an active .venv from GC."""
    if not isinstance(pool, ImmutableVenvPool):
        raise ValueError(f"pool must be ImmutableVenvPool, got {pool!r}")
    if not isinstance(env_hash, EnvHash):
        raise ValueError(f"env_hash must be EnvHash, got {env_hash!r}")
    coords = _EnvPoolRegistry.lookup(pool)
    try:
        lock_path = resolve_contained_subpath(
            coords.cache_dir,
            _LOCKS_SUBDIR,
            f"env_{env_hash.short(16)}.lock",
        )
        lock_obj = FileLock(lock_path, allow_transitions=False)
        if not lock_obj.acquire(shared=True, blocking=False):
            return None
        return lock_obj
    except (OSError, YscbError):
        return None


def acquire_env_lease_for_python(pool: ImmutableVenvPool, venv_python: HostPath) -> Optional[FileLock]:
    """Resolve the managed .venv owning venv_python, acquire its shared lease, and touch last_used_epoch_sec."""
    if not isinstance(pool, ImmutableVenvPool):
        raise ValueError(f"pool must be ImmutableVenvPool, got {pool!r}")
    if not isinstance(venv_python, HostPath):
        raise ValueError(f"venv_python must be HostPath, got {venv_python!r}")
    coords = _EnvPoolRegistry.lookup(pool)
    venv_root = try_resolve_contained_subpath(coords.yscb_root, _VENV_DIRNAME)
    if venv_root is None or not os.path.isdir(str(venv_root)) or is_symlink_or_reparse(str(venv_root)):
        return None
    venv_root_key = venv_root.comparison_key
    cur_p = venv_python.path.parent
    env_dir_path: Optional[Path] = None
    while True:
        parent_p = cur_p.parent
        if parent_p == cur_p:
            break
        if os.path.normcase(str(parent_p)) == venv_root_key:
            env_dir_path = cur_p
            break
        cur_p = parent_p
    if env_dir_path is None or env_dir_path.name.startswith("."):
        return None
    env_dir = try_resolve_contained_subpath(venv_root, env_dir_path.name)
    if env_dir is None or is_symlink_or_reparse(str(env_dir)) or not os.path.isdir(str(env_dir)):
        return None
    try:
        meta = env_read_metadata(env_dir)
    except (OSError, ValueError, YscbError):
        meta = None
    env_hash = meta.env_hash if meta is not None else env_extract_dirname_tail_hash(env_dir.path.name)
    if env_hash is None:
        return None
    lease = acquire_env_shared_lease(pool, env_hash)
    if lease is None:
        return None
    try:
        if not os.path.isdir(str(env_dir)) or is_symlink_or_reparse(str(env_dir)):
            lease.release()
            return None
        touch_env_last_used(env_dir)
        return lease
    except BaseException:
        lease.release()
        raise


def env_repair_under_lock(
    pool: ImmutableVenvPool,
    spec: EnvSpec,
    *,
    offline: bool,
    wheel_cache_dir: Optional[HostPath],
    timeout_sec: float = 300.0,
    cancel_token: Optional[CancellationToken] = None,
) -> EnvBuildResult:
    """Build a verified replacement in staging first, then evict and promote atomically under FileLock."""
    coords = _EnvPoolRegistry.lookup(pool)
    yscb_root = coords.yscb_root
    cache_dir = coords.cache_dir
    next_seq = coords.next_seq
    eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
    safe_timeout = require_non_negative_sec(timeout_sec, label="timeout_sec")
    started_ns = time.monotonic_ns()
    deadline = time.monotonic() + safe_timeout
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    rem_for_lock = deadline - time.monotonic()
    if rem_for_lock <= 0.0:
        raise YscbError(
            ErrorCode.TASK_TIMEOUT,
            f"Timed out before acquiring repair lock for environment '{spec.dirname}'.",
        )
    lock_path = resolve_contained_subpath(
        cache_dir,
        _LOCKS_SUBDIR,
        f"env_{spec.env_hash.short(16)}.lock",
    )
    build_lock = FileLock(lock_path, allow_transitions=False)
    build_lock.acquire(
        shared=False,
        blocking=True,
        timeout_sec=rem_for_lock,
        cancel_token=cancel_token,
    )
    try:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        venv_root = resolve_contained_subpath(yscb_root, _VENV_DIRNAME)
        try:
            os.makedirs(str(venv_root), exist_ok=True)
        except OSError as exc:
            raise YscbError(
                ErrorCode.ENV_BUILD_FAILED,
                f"Failed to create .venv root directory '{venv_root}': {safe_exception_summary(exc)}",
            ) from exc
        venv_root = resolve_contained_subpath(yscb_root, _VENV_DIRNAME)
        env_dir = pool.get_env_dir(spec)
        staging_name = f".staging_{spec.dirname}_{os.getpid()}_{next_seq(pool)}"
        staging_dir = resolve_contained_subpath(venv_root, staging_name)
        evict_dir: Optional[HostPath] = None
        try:
            _populate_verified_staging_venv(
                staging_dir,
                spec,
                eff_offline=eff_offline,
                wheel_cache_dir=wheel_cache_dir,
                deadline=deadline,
                cancel_token=cancel_token,
            )

            raw_env = str(env_dir)
            if os.path.lexists(raw_env):
                was_healthy = len(env_quick_probe_issues(env_dir, spec)) == 0
                evict_name = f".staging_repair_{spec.dirname}_{os.getpid()}_{next_seq(pool)}"
                evict_dir = resolve_contained_subpath(venv_root, evict_name)
                try:
                    os.replace(raw_env, str(evict_dir))
                except FileNotFoundError:
                    evict_dir = None
                except OSError as evict_err:
                    evict_dir = None
                    if was_healthy:
                        raise YscbError(
                            ErrorCode.ENV_BUILD_FAILED,
                            f"Active environment '{env_dir}' is locked by a running process and cannot be replaced: {safe_exception_summary(evict_err)}",
                        ) from evict_err
                    meta_hp = resolve_contained_subpath(env_dir, ".yscb_env_meta.json")
                    silent_unlink(meta_hp)
                    try:
                        _rmtree_staging_with_retry(env_dir.path)
                    except OSError as exc:
                        raise YscbError(
                            ErrorCode.ENV_BUILD_FAILED,
                            f"Failed to remove damaged environment directory '{env_dir}': {safe_exception_summary(exc)}",
                        ) from exc

            last_exc: Optional[OSError] = None
            promoted = False
            for attempt in range(_REPLACE_MAX_ATTEMPTS):
                try:
                    os.replace(str(staging_dir), raw_env)
                    promoted = True
                    break
                except OSError as exc:
                    last_exc = exc
                    if attempt + 1 < _REPLACE_MAX_ATTEMPTS:
                        time.sleep(0.01 * (attempt + 1))
            if not promoted:
                if evict_dir is not None and os.path.lexists(str(evict_dir)) and not os.path.lexists(raw_env):
                    try:
                        os.replace(str(evict_dir), raw_env)
                        evict_dir = None
                    except OSError:
                        pass
                detail = safe_exception_summary(last_exc) if last_exc is not None else "replace failed"
                raise YscbError(
                    ErrorCode.ENV_BUILD_FAILED,
                    f"Failed to promote repaired environment to '{env_dir}': {detail}",
                ) from last_exc
        finally:
            if os.path.lexists(str(staging_dir)):
                try:
                    _rmtree_staging_with_retry(staging_dir.path)
                except OSError:
                    pass
            if evict_dir is not None and os.path.lexists(str(evict_dir)):
                try:
                    _rmtree_staging_with_retry(evict_dir.path)
                except OSError:
                    pass

        final_py = env_find_python_exe(env_dir)
        if final_py is None:
            raise YscbError(
                ErrorCode.ENV_BUILD_FAILED,
                f"Repaired virtual environment missing Python interpreter: {env_dir}",
            )
        return EnvBuildResult(
            spec=spec,
            env_dir=env_dir,
            python_exe=final_py,
            reused=False,
            duration_ms=_elapsed_duration_ms(started_ns),
        )
    finally:
        build_lock.release()
