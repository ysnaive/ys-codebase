"""Pluggable VfsProvider protocol, symlink-guarded PhysicalDirectoryProvider, and isolated MemoryVfsProvider."""

from __future__ import annotations

import errno
import io
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import BinaryIO, ClassVar, Final, Iterator, Optional, Protocol
from weakref import WeakKeyDictionary

from core.filesystem.fs import (
    BeforeReplaceHook,
    atomic_write_bytes,
    has_symlink_raw_path,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.filesystem.vfs.capabilities import VfsCapabilities, VfsStat
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    SemanticUri,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_str,
)

_SCHEME_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*$")
_NOFOLLOW_OPEN_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW | os.O_NONBLOCK)
)


def _validate_vfs_scheme(scheme: str, *, label: str = "scheme") -> str:
    require_pure_str(scheme, label, non_empty=True)
    if _SCHEME_TOKEN_RE.fullmatch(scheme) is None:
        raise ValueError(f"Invalid VFS {label}: {scheme!r}")
    return scheme


def _validate_provider_uri(uri: SemanticUri, expected_scheme: str) -> tuple[str, ...]:
    if not isinstance(uri, SemanticUri):
        raise ValueError(f"Expected SemanticUri, got {uri!r}")
    if uri.scheme != expected_scheme:
        raise ValueError(f"URI scheme mismatch: provider handles '{expected_scheme}://', got '{uri}'")
    if uri.uses_module_placeholder:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Unbound module placeholder '@/' cannot be passed directly to VfsProvider: {uri}",
        )
    if not uri.rel_path:
        return ()
    parts = tuple(seg for seg in uri.rel_path.split("/") if seg)
    if not parts or any(not is_valid_relative_segment(seg) for seg in parts):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Illegal or traversing segment in URI: {uri}")
    return parts


def _ensure_realpath_contained(root_dir: HostPath, target: HostPath, *, allow_equal: bool) -> None:
    real_root = os.path.normcase(os.path.realpath(str(root_dir)))
    real_target = os.path.normcase(os.path.realpath(str(target)))
    seps = ("/", "\\") if IS_WINDOWS else ("/",)
    strip_chars = "/\\" if IS_WINDOWS else "/"
    trimmed_root = real_root.rstrip(strip_chars) or real_root
    if real_target == real_root or real_target == trimmed_root:
        if allow_equal:
            return
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Operation requires a non-root path inside '{root_dir}'.")
    prefix = trimmed_root if trimmed_root.endswith(seps) else f"{trimmed_root}{os.sep}"
    if not real_target.startswith(prefix):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Path escaped VFS root '{root_dir}': {target}")


def _is_lstat_readonly(st: os.stat_result) -> bool:
    if IS_WINDOWS:
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY) or ((st.st_mode & stat.S_IWRITE) == 0)
    return (stat.S_IMODE(st.st_mode) & 0o222) == 0


def _strip_os_readonly_best_effort(raw_path: str, *, is_dir: bool) -> None:
    try:
        if is_symlink_or_reparse(raw_path):
            return
        mode = (stat.S_IREAD | stat.S_IWRITE) if IS_WINDOWS else (0o700 if is_dir else 0o600)
        os.chmod(raw_path, mode)
    except OSError:
        return


def _unlink_with_retry(raw_path: str) -> None:
    for attempt in range(6):
        if is_symlink_or_reparse(raw_path):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing to delete symlink or reparse point: {raw_path}")
        try:
            os.unlink(raw_path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            _strip_os_readonly_best_effort(raw_path, is_dir=False)
            if attempt == 5:
                raise
            time.sleep(0.01 * (attempt + 1))
        except OSError as exc:
            if exc.errno in (errno.EBUSY, errno.EACCES) and attempt < 5:
                _strip_os_readonly_best_effort(raw_path, is_dir=False)
                time.sleep(0.01 * (attempt + 1))
                continue
            raise


def _rmdir_with_retry(raw_dir: str) -> None:
    for attempt in range(6):
        if is_symlink_or_reparse(raw_dir):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing to remove symlinked directory: {raw_dir}")
        try:
            os.rmdir(raw_dir)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            _strip_os_readonly_best_effort(raw_dir, is_dir=True)
            if attempt == 5:
                raise
            time.sleep(0.01 * (attempt + 1))
        except OSError as exc:
            if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                raise
            if exc.errno in (errno.EBUSY, errno.EACCES) and attempt < 5:
                _strip_os_readonly_best_effort(raw_dir, is_dir=True)
                time.sleep(0.01 * (attempt + 1))
                continue
            raise


def _robust_rmtree_nonsymlink(target: HostPath) -> None:
    raw_root = str(target)
    if has_symlink_raw_path(raw_root) or is_symlink_or_reparse(raw_root):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing recursive delete across symlink path: {raw_root}")
    dirs_to_scan: list[str] = [raw_root]
    post_order_dirs: list[str] = []
    files_to_remove: list[str] = []
    while dirs_to_scan:
        cur_dir = dirs_to_scan.pop()
        if is_symlink_or_reparse(cur_dir):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink directory inside rmtree: {cur_dir}")
        post_order_dirs.append(cur_dir)
        with os.scandir(cur_dir) as it:
            entries = tuple(it)
        for ent in entries:
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink entry inside rmtree: {ent.path}")
            if ent.is_dir(follow_symlinks=False):
                dirs_to_scan.append(ent.path)
            else:
                files_to_remove.append(ent.path)
    for file_p in files_to_remove:
        _unlink_with_retry(file_p)
    for dir_p in reversed(post_order_dirs):
        _rmdir_with_retry(dir_p)


def _replace_entry_with_retry(raw_src: str, raw_dst: str) -> None:
    for attempt in range(6):
        if has_symlink_raw_path(raw_src) or has_symlink_raw_path(raw_dst):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing move across symlink path: {raw_src} -> {raw_dst}")
        try:
            os.replace(raw_src, raw_dst)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.01 * (attempt + 1))
        except OSError as exc:
            if exc.errno == errno.EBUSY and attempt < 5:
                time.sleep(0.01 * (attempt + 1))
                continue
            raise


def vfs_replace_entry_with_retry(raw_src: str, raw_dst: str) -> None:
    """Internal VFS helper replacing a physical file or directory with symlink checks and transient lock retry."""
    _replace_entry_with_retry(raw_src, raw_dst)


class VfsProvider(Protocol):
    """Pluggable storage backend backing a single VFS scheme."""

    @property
    def scheme(self) -> str: ...

    @property
    def base_capabilities(self) -> VfsCapabilities: ...

    @property
    def description(self) -> str: ...

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities: ...

    def exists(self, uri: SemanticUri) -> bool: ...

    def stat(self, uri: SemanticUri) -> VfsStat: ...

    def read_bytes(self, uri: SemanticUri) -> bytes: ...

    def open_read(self, uri: SemanticUri) -> BinaryIO: ...

    def write_bytes_atomic(
        self,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None: ...

    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool: ...

    def move(self, src: SemanticUri, dst: SemanticUri) -> None: ...

    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None: ...

    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]: ...

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]: ...


def _resolve_physical_dir_target(
    scheme: str,
    root_dir: HostPath,
    uri: SemanticUri,
    *,
    allow_root: bool,
) -> HostPath:
    parts = _validate_provider_uri(uri, scheme)
    raw_root = str(root_dir)
    if is_symlink_or_reparse(raw_root) or has_symlink_raw_path(raw_root):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"VFS root directory became a symlink or reparse point: {raw_root}")
    if not parts:
        if not allow_root:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Operation requires a non-root file path for '{uri}'.")
        return root_dir
    try:
        resolved = resolve_contained_subpath(root_dir, *parts)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.SECURITY_GATED:
            raise YscbError(ErrorCode.ACCESS_DENIED, exc.detail.message, remediation=exc.detail.remediation) from exc
        raise
    except ValueError as exc:
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Invalid contained subpath for '{uri}': {exc}") from exc
    _ensure_realpath_contained(root_dir, resolved, allow_equal=False)
    return resolved


def _physical_write_bytes_atomic(
    scheme: str,
    root_dir: HostPath,
    uri: SemanticUri,
    data: bytes,
    *,
    before_replace: Optional[BeforeReplaceHook] = None,
) -> None:
    if not isinstance(data, bytes):
        raise ValueError(f"write_bytes_atomic requires plain bytes, got {type(data).__name__}")
    target = _resolve_physical_dir_target(scheme, root_dir, uri, allow_root=False)
    raw_t = str(target)
    if os.path.isdir(raw_t) and not is_symlink_or_reparse(raw_t):
        raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), raw_t)
    try:
        atomic_write_bytes(target, data, before_replace=before_replace)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.SECURITY_GATED:
            raise YscbError(ErrorCode.ACCESS_DENIED, exc.detail.message, remediation=exc.detail.remediation) from exc
        raise


def _physical_delete(scheme: str, root_dir: HostPath, uri: SemanticUri, *, recursive: bool = False) -> bool:
    require_pure_bool(recursive, "recursive")
    target = _resolve_physical_dir_target(scheme, root_dir, uri, allow_root=False)
    raw_t = str(target)
    if not os.path.lexists(raw_t):
        return False
    if is_symlink_or_reparse(raw_t):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing to delete symlink or reparse target: {raw_t}")
    if os.path.isdir(raw_t):
        if recursive:
            _robust_rmtree_nonsymlink(target)
        else:
            _rmdir_with_retry(raw_t)
        return True
    _unlink_with_retry(raw_t)
    return True


def _physical_move(scheme: str, root_dir: HostPath, src: SemanticUri, dst: SemanticUri) -> None:
    src_hp = _resolve_physical_dir_target(scheme, root_dir, src, allow_root=False)
    dst_hp = _resolve_physical_dir_target(scheme, root_dir, dst, allow_root=False)
    raw_src = str(src_hp)
    raw_dst = str(dst_hp)
    if not os.path.lexists(raw_src):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), raw_src)
    if src_hp == dst_hp:
        return
    trimmed_src = src_hp.comparison_key.rstrip("/\\")
    src_prefix = f"{trimmed_src}{os.sep}"
    if dst_hp.comparison_key.startswith(src_prefix):
        raise ValueError(f"Cannot move directory '{src}' into its own descendant '{dst}'.")
    os.makedirs(str(dst_hp.path.parent), exist_ok=True)
    if has_symlink_raw_path(raw_dst):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing move destination traversing symlink: {raw_dst}")
    _replace_entry_with_retry(raw_src, raw_dst)


def _physical_mkdir(scheme: str, root_dir: HostPath, uri: SemanticUri, *, parents: bool = True) -> None:
    require_pure_bool(parents, "parents")
    target = _resolve_physical_dir_target(scheme, root_dir, uri, allow_root=True)
    raw_t = str(target)
    if os.path.lexists(raw_t):
        if is_symlink_or_reparse(raw_t):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink target in mkdir: {raw_t}")
        if not os.path.isdir(raw_t):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), raw_t)
        return
    if parents:
        os.makedirs(raw_t, exist_ok=True)
    else:
        os.makedirs(str(root_dir), exist_ok=True)
        os.mkdir(raw_t)
    if has_symlink_raw_path(raw_t):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Directory path traverses symlink after mkdir: {raw_t}")


class _VfsProviderInternals:
    physical_roots: ClassVar[WeakKeyDictionary[PhysicalDirectoryProvider, tuple[str, HostPath]]] = WeakKeyDictionary()

    @classmethod
    def register_physical(cls, inst: PhysicalDirectoryProvider, scheme: str, root_dir: HostPath) -> None:
        cls.physical_roots[inst] = (scheme, root_dir)

    @classmethod
    def resolve_unmasked(cls, prov: VfsProvider, uri: SemanticUri) -> Optional[HostPath]:
        if isinstance(prov, PhysicalDirectoryProvider):
            meta = cls.physical_roots.get(prov)
            if meta is not None:
                return _resolve_physical_dir_target(meta[0], meta[1], uri, allow_root=True)
        return prov.try_get_physical_path(uri)

    @classmethod
    def kernel_write_bytes_atomic(
        cls,
        prov: VfsProvider,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None:
        if isinstance(prov, PhysicalDirectoryProvider):
            meta = cls.physical_roots.get(prov)
            if meta is not None:
                _physical_write_bytes_atomic(meta[0], meta[1], uri, data, before_replace=before_replace)
                return
        prov.write_bytes_atomic(uri, data, before_replace=before_replace)

    @classmethod
    def kernel_delete(cls, prov: VfsProvider, uri: SemanticUri, *, recursive: bool = False) -> bool:
        if isinstance(prov, PhysicalDirectoryProvider):
            meta = cls.physical_roots.get(prov)
            if meta is not None:
                return _physical_delete(meta[0], meta[1], uri, recursive=recursive)
        return prov.delete(uri, recursive=recursive)

    @classmethod
    def kernel_move(cls, prov: VfsProvider, src: SemanticUri, dst: SemanticUri) -> None:
        if isinstance(prov, PhysicalDirectoryProvider):
            meta = cls.physical_roots.get(prov)
            if meta is not None:
                _physical_move(meta[0], meta[1], src, dst)
                return
        prov.move(src, dst)

    @classmethod
    def kernel_mkdir(cls, prov: VfsProvider, uri: SemanticUri, *, parents: bool = True) -> None:
        if isinstance(prov, PhysicalDirectoryProvider):
            meta = cls.physical_roots.get(prov)
            if meta is not None:
                _physical_mkdir(meta[0], meta[1], uri, parents=parents)
                return
        prov.mkdir(uri, parents=parents)


def vfs_try_resolve_unmasked_host_path(prov: VfsProvider, uri: SemanticUri) -> Optional[HostPath]:
    """Internal VFS helper resolving physical HostPath for kernel routing even when PHYSICAL_PATH is masked."""
    return _VfsProviderInternals.resolve_unmasked(prov, uri)


def vfs_kernel_write_bytes_atomic(
    prov: VfsProvider,
    uri: SemanticUri,
    data: bytes,
    *,
    before_replace: Optional[BeforeReplaceHook] = None,
) -> None:
    """Internal privileged write bypassing PhysicalDirectoryProvider base_capabilities for KernelVfs."""
    _VfsProviderInternals.kernel_write_bytes_atomic(prov, uri, data, before_replace=before_replace)


def vfs_kernel_delete(prov: VfsProvider, uri: SemanticUri, *, recursive: bool = False) -> bool:
    """Internal privileged delete bypassing PhysicalDirectoryProvider base_capabilities for KernelVfs."""
    return _VfsProviderInternals.kernel_delete(prov, uri, recursive=recursive)


def vfs_kernel_move(prov: VfsProvider, src: SemanticUri, dst: SemanticUri) -> None:
    """Internal privileged move bypassing PhysicalDirectoryProvider base_capabilities for KernelVfs."""
    _VfsProviderInternals.kernel_move(prov, src, dst)


def vfs_kernel_mkdir(prov: VfsProvider, uri: SemanticUri, *, parents: bool = True) -> None:
    """Internal privileged mkdir bypassing PhysicalDirectoryProvider base_capabilities for KernelVfs."""
    _VfsProviderInternals.kernel_mkdir(prov, uri, parents=parents)


class PhysicalDirectoryProvider:
    """Sandboxed 1:1 physical directory provider enforcing symlink-free containment and atomic writes."""

    def __init__(
        self,
        scheme: str,
        root_dir: HostPath,
        *,
        base_capabilities: VfsCapabilities,
        description: str = "",
    ) -> None:
        clean_scheme = _validate_vfs_scheme(scheme)
        if not isinstance(root_dir, HostPath):
            raise ValueError(f"PhysicalDirectoryProvider requires HostPath root_dir, got {root_dir!r}")
        if not isinstance(base_capabilities, VfsCapabilities):
            raise ValueError(f"PhysicalDirectoryProvider requires VfsCapabilities, got {base_capabilities!r}")
        require_pure_str(description, "description")
        if is_symlink_or_reparse(str(root_dir)) or has_symlink_raw_path(str(root_dir)):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse VFS root directory: {root_dir}")
        self._scheme = clean_scheme
        self._root_dir = root_dir
        self._base_capabilities = base_capabilities
        self._description = description
        _VfsProviderInternals.register_physical(self, clean_scheme, root_dir)

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def base_capabilities(self) -> VfsCapabilities:
        return self._base_capabilities

    @property
    def description(self) -> str:
        return self._description

    def _resolve_target(self, uri: SemanticUri, *, allow_root: bool) -> HostPath:
        return _resolve_physical_dir_target(self._scheme, self._root_dir, uri, allow_root=allow_root)

    def _require_writable(self) -> None:
        if VfsCapabilities.WRITABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Physical scheme '{self._scheme}://' is read-only.")

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        _ = self._resolve_target(uri, allow_root=True)
        return self._base_capabilities

    def exists(self, uri: SemanticUri) -> bool:
        target = self._resolve_target(uri, allow_root=True)
        raw_t = str(target)
        if is_symlink_or_reparse(raw_t):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse target: {raw_t}")
        return os.path.lexists(raw_t)

    def stat(self, uri: SemanticUri) -> VfsStat:
        target = self._resolve_target(uri, allow_root=True)
        raw_t = str(target)
        if is_symlink_or_reparse(raw_t):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse target: {raw_t}")
        try:
            st = os.lstat(raw_t)
        except FileNotFoundError:
            return VfsStat(exists=False, is_dir=False, is_readonly=False, size_bytes=0, mtime_ns=0, ino=0)
        if stat.S_ISLNK(st.st_mode):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink target: {raw_t}")
        is_dir = stat.S_ISDIR(st.st_mode)
        return VfsStat(
            exists=True,
            is_dir=is_dir,
            is_readonly=_is_lstat_readonly(st),
            size_bytes=0 if is_dir else int(st.st_size),
            mtime_ns=int(st.st_mtime_ns),
            ino=int(st.st_ino),
        )

    def read_bytes(self, uri: SemanticUri) -> bytes:
        if VfsCapabilities.READABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not readable.")
        target = self._resolve_target(uri, allow_root=False)
        raw_t = str(target)
        data = read_nofollow_regular_bytes(raw_t)
        if data is None:
            if os.path.isdir(raw_t) and not is_symlink_or_reparse(raw_t):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), raw_t)
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing to read non-regular or symlinked path: {raw_t}")
        return data

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        if VfsCapabilities.READABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not readable.")
        target = self._resolve_target(uri, allow_root=False)
        raw_t = str(target)
        for attempt in range(6):
            if has_symlink_raw_path(raw_t):
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink path in open_read: {raw_t}")
            try:
                l_st = os.lstat(raw_t)
            except FileNotFoundError:
                if IS_WINDOWS and attempt < 5:
                    time.sleep(0.005 * (attempt + 1))
                    continue
                raise
            if stat.S_ISLNK(l_st.st_mode):
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink target in open_read: {raw_t}")
            if stat.S_ISDIR(l_st.st_mode):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), raw_t)
            if not stat.S_ISREG(l_st.st_mode):
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing non-regular file in open_read: {raw_t}")
            try:
                fd = os.open(raw_t, _NOFOLLOW_OPEN_FLAGS)
            except PermissionError:
                if IS_WINDOWS and attempt < 5 and not has_symlink_raw_path(raw_t):
                    time.sleep(0.005 * (attempt + 1))
                    continue
                raise
            except FileNotFoundError:
                if IS_WINDOWS and attempt < 5:
                    time.sleep(0.005 * (attempt + 1))
                    continue
                raise
            except OSError as exc:
                if not IS_WINDOWS and exc.errno in (errno.ELOOP, errno.ENXIO, errno.EOPNOTSUPP, errno.EMLINK):
                    raise YscbError(
                        ErrorCode.ACCESS_DENIED,
                        f"Refusing non-regular or symlink target in open_read: {raw_t}",
                    ) from exc
                raise
            fd_owned = True
            try:
                f_st = os.fstat(fd)
                if stat.S_ISDIR(f_st.st_mode):
                    raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), raw_t)
                if not stat.S_ISREG(f_st.st_mode) or has_symlink_raw_path(raw_t):
                    raise YscbError(
                        ErrorCode.ACCESS_DENIED,
                        f"Refusing non-regular or symlinked file in open_read: {raw_t}",
                    )
                if IS_WINDOWS and (f_st.st_ino, f_st.st_dev) != (l_st.st_ino, l_st.st_dev) and attempt < 5:
                    os.close(fd)
                    fd_owned = False
                    time.sleep(0.005 * (attempt + 1))
                    continue
                if not IS_WINDOWS:
                    os.set_blocking(fd, True)
                os.set_inheritable(fd, False)
                raw_io = io.FileIO(fd, "rb", closefd=True)
                fd_owned = False
                return io.BufferedReader(raw_io)
            except BaseException:
                if fd_owned:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                raise
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), raw_t)

    def write_bytes_atomic(
        self,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None:
        self._require_writable()
        _physical_write_bytes_atomic(self._scheme, self._root_dir, uri, data, before_replace=before_replace)

    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool:
        self._require_writable()
        return _physical_delete(self._scheme, self._root_dir, uri, recursive=recursive)

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        self._require_writable()
        _physical_move(self._scheme, self._root_dir, src, dst)

    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None:
        self._require_writable()
        _physical_mkdir(self._scheme, self._root_dir, uri, parents=parents)

    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]:
        require_pure_bool(recursive, "recursive")
        if VfsCapabilities.ENUMERABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not enumerable.")
        target = self._resolve_target(uri, allow_root=True)
        raw_t = str(target)
        if not os.path.lexists(raw_t):
            return iter(())
        if is_symlink_or_reparse(raw_t):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink directory in iter_entries: {raw_t}")
        if not os.path.isdir(raw_t):
            raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), raw_t)
        real_root = os.path.realpath(str(self._root_dir))
        collected: list[SemanticUri] = []
        if not recursive:
            with os.scandir(raw_t) as it:
                entries = sorted(it, key=lambda e: e.name)
            for ent in entries:
                if is_atomic_staging_filename(ent.name) or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                    continue
                if not is_valid_relative_segment(ent.name) or ent.name == "@":
                    continue
                child_uri = uri.join(ent.name) if uri.rel_path else SemanticUri(self._scheme, ent.name)
                collected.append(child_uri)
            return iter(collected)
        for cur_dir, entries in walk_nonsymlink_dir_tree(raw_t, ignored_dir_prefixes=(".tmp_", ".staging_")):
            for ent in entries:
                if is_atomic_staging_filename(ent.name) or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                    continue
                rel_os = os.path.relpath(os.path.join(cur_dir, ent.name), real_root)
                rel_parts = tuple(p for p in Path(rel_os).parts if p not in ("", "."))
                if not rel_parts or rel_parts[0] == "@" or any(not is_valid_relative_segment(p) for p in rel_parts):
                    continue
                collected.append(SemanticUri(self._scheme, "/".join(rel_parts)))
        collected.sort(key=lambda item: item.rel_path)
        return iter(collected)

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        target = self._resolve_target(uri, allow_root=True)
        if VfsCapabilities.PHYSICAL_PATH not in self._base_capabilities:
            return None
        return target


class _VfsMemFileNode:
    __slots__ = ("data", "mtime_ns", "ino")

    def __init__(self, data: bytes, mtime_ns: int, ino: int) -> None:
        self.data = data
        self.mtime_ns = mtime_ns
        self.ino = ino


class _VfsMemDirNode:
    __slots__ = ("mtime_ns", "ino")

    def __init__(self, mtime_ns: int, ino: int) -> None:
        self.mtime_ns = mtime_ns
        self.ino = ino


class MemoryVfsProvider:
    """Zero-disk thread-safe in-memory VFS provider without PHYSICAL_PATH capability."""

    def __init__(
        self,
        scheme: str,
        *,
        base_capabilities: VfsCapabilities = (
            VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE
        ),
        description: str = "",
    ) -> None:
        clean_scheme = _validate_vfs_scheme(scheme)
        if not isinstance(base_capabilities, VfsCapabilities):
            raise ValueError(f"MemoryVfsProvider requires VfsCapabilities, got {base_capabilities!r}")
        if VfsCapabilities.PHYSICAL_PATH in base_capabilities:
            raise ValueError("MemoryVfsProvider cannot declare VfsCapabilities.PHYSICAL_PATH.")
        require_pure_str(description, "description")
        self._scheme = clean_scheme
        self._base_capabilities = base_capabilities
        self._description = description
        self._lock = threading.RLock()
        self._next_inode = 2
        self._files: dict[str, _VfsMemFileNode] = {}
        self._dirs: dict[str, _VfsMemDirNode] = {"": _VfsMemDirNode(mtime_ns=time.time_ns(), ino=1)}

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def base_capabilities(self) -> VfsCapabilities:
        return self._base_capabilities

    @property
    def description(self) -> str:
        return self._description

    def _alloc_ino_locked(self) -> int:
        ino = self._next_inode
        self._next_inode += 1
        return ino

    def _validate_uri(self, uri: SemanticUri, *, allow_root: bool) -> str:
        parts = _validate_provider_uri(uri, self._scheme)
        if not parts:
            if not allow_root:
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Operation requires a non-root path for '{uri}'.")
            return ""
        return "/".join(parts)

    def _ensure_ancestors_not_files_locked(self, rel_path: str) -> list[str]:
        segments = rel_path.split("/")
        ancestors: list[str] = []
        cur = ""
        for seg in segments[:-1]:
            cur = f"{cur}/{seg}" if cur else seg
            if cur in self._files:
                raise FileExistsError(errno.EEXIST, "Ancestor path exists as a regular file.", cur)
            ancestors.append(cur)
        return ancestors

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        _ = self._validate_uri(uri, allow_root=True)
        return self._base_capabilities

    def exists(self, uri: SemanticUri) -> bool:
        rel = self._validate_uri(uri, allow_root=True)
        with self._lock:
            return rel in self._files or rel in self._dirs

    def stat(self, uri: SemanticUri) -> VfsStat:
        rel = self._validate_uri(uri, allow_root=True)
        is_ro = VfsCapabilities.WRITABLE not in self._base_capabilities
        with self._lock:
            fnode = self._files.get(rel)
            if fnode is not None:
                return VfsStat(
                    exists=True,
                    is_dir=False,
                    is_readonly=is_ro,
                    size_bytes=len(fnode.data),
                    mtime_ns=fnode.mtime_ns,
                    ino=fnode.ino,
                )
            dnode = self._dirs.get(rel)
            if dnode is not None:
                return VfsStat(
                    exists=True,
                    is_dir=True,
                    is_readonly=is_ro,
                    size_bytes=0,
                    mtime_ns=dnode.mtime_ns,
                    ino=dnode.ino,
                )
        return VfsStat(exists=False, is_dir=False, is_readonly=False, size_bytes=0, mtime_ns=0, ino=0)

    def read_bytes(self, uri: SemanticUri) -> bytes:
        if VfsCapabilities.READABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not readable.")
        rel = self._validate_uri(uri, allow_root=False)
        with self._lock:
            if rel in self._dirs:
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(uri))
            fnode = self._files.get(rel)
            if fnode is None:
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(uri))
            return fnode.data

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        return io.BytesIO(self.read_bytes(uri))

    def write_bytes_atomic(
        self,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None:
        if not isinstance(data, bytes):
            raise ValueError(f"write_bytes_atomic requires plain bytes, got {type(data).__name__}")
        if VfsCapabilities.WRITABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Memory scheme '{self._scheme}://' is read-only.")
        rel = self._validate_uri(uri, allow_root=False)
        payload = bytes(data)
        with self._lock:
            if rel in self._dirs:
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(uri))
            ancestors = self._ensure_ancestors_not_files_locked(rel)
            now_ns = time.time_ns()
            for anc in ancestors:
                if anc not in self._dirs:
                    self._dirs[anc] = _VfsMemDirNode(mtime_ns=now_ns, ino=self._alloc_ino_locked())
            new_ino = self._alloc_ino_locked()
            if before_replace is not None:
                before_replace(now_ns, len(payload), new_ino)
            self._files[rel] = _VfsMemFileNode(data=payload, mtime_ns=now_ns, ino=new_ino)

    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool:
        require_pure_bool(recursive, "recursive")
        if VfsCapabilities.WRITABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Memory scheme '{self._scheme}://' is read-only.")
        rel = self._validate_uri(uri, allow_root=False)
        with self._lock:
            if rel in self._files:
                self._files.pop(rel, None)
                return True
            if rel not in self._dirs:
                return False
            prefix = f"{rel}/"
            child_files = [k for k in self._files if k.startswith(prefix)]
            child_dirs = [k for k in self._dirs if k.startswith(prefix)]
            if (child_files or child_dirs) and not recursive:
                raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), str(uri))
            for k in child_files:
                self._files.pop(k, None)
            for k in child_dirs:
                self._dirs.pop(k, None)
            self._dirs.pop(rel, None)
            return True

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        if VfsCapabilities.WRITABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Memory scheme '{self._scheme}://' is read-only.")
        src_rel = self._validate_uri(src, allow_root=False)
        dst_rel = self._validate_uri(dst, allow_root=False)
        with self._lock:
            if src_rel not in self._files and src_rel not in self._dirs:
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(src))
            if src_rel == dst_rel:
                return
            if dst_rel.startswith(f"{src_rel}/"):
                raise ValueError(f"Cannot move directory '{src}' into its own descendant '{dst}'.")
            ancestors = self._ensure_ancestors_not_files_locked(dst_rel)
            now_ns = time.time_ns()
            for anc in ancestors:
                if anc not in self._dirs:
                    self._dirs[anc] = _VfsMemDirNode(mtime_ns=now_ns, ino=self._alloc_ino_locked())
            if src_rel in self._files:
                if dst_rel in self._dirs:
                    raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(dst))
                self._files[dst_rel] = self._files.pop(src_rel)
                return
            if dst_rel in self._files:
                raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(dst))
            dst_prefix = f"{dst_rel}/"
            if dst_rel in self._dirs and (
                any(k.startswith(dst_prefix) for k in self._files)
                or any(k.startswith(dst_prefix) for k in self._dirs)
            ):
                raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), str(dst))
            src_prefix = f"{src_rel}/"
            moved_dirs = {dst_rel: self._dirs.pop(src_rel)}
            for k in [key for key in self._dirs if key.startswith(src_prefix)]:
                moved_dirs[f"{dst_rel}/{k[len(src_prefix):]}"] = self._dirs.pop(k)
            moved_files: dict[str, _VfsMemFileNode] = {}
            for k in [key for key in self._files if key.startswith(src_prefix)]:
                moved_files[f"{dst_rel}/{k[len(src_prefix):]}"] = self._files.pop(k)
            self._dirs.update(moved_dirs)
            self._files.update(moved_files)

    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None:
        require_pure_bool(parents, "parents")
        if VfsCapabilities.WRITABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Memory scheme '{self._scheme}://' is read-only.")
        rel = self._validate_uri(uri, allow_root=True)
        with self._lock:
            if rel in self._files:
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(uri))
            if rel in self._dirs:
                return
            ancestors = self._ensure_ancestors_not_files_locked(rel)
            if not parents:
                parent_rel = ancestors[-1] if ancestors else ""
                if parent_rel not in self._dirs:
                    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(uri))
            now_ns = time.time_ns()
            for anc in ancestors:
                if anc not in self._dirs:
                    self._dirs[anc] = _VfsMemDirNode(mtime_ns=now_ns, ino=self._alloc_ino_locked())
            self._dirs[rel] = _VfsMemDirNode(mtime_ns=now_ns, ino=self._alloc_ino_locked())

    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]:
        require_pure_bool(recursive, "recursive")
        if VfsCapabilities.ENUMERABLE not in self._base_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not enumerable.")
        rel = self._validate_uri(uri, allow_root=True)
        with self._lock:
            if rel in self._files:
                raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(uri))
            if rel not in self._dirs:
                return iter(())
            all_paths = [k for k in (*self._files.keys(), *self._dirs.keys()) if k]
        prefix = f"{rel}/" if rel else ""
        matched: set[str] = set()
        for cand in all_paths:
            if prefix and not cand.startswith(prefix):
                continue
            tail = cand[len(prefix) :] if prefix else cand
            if not tail:
                continue
            if recursive:
                matched.add(cand)
            elif "/" not in tail:
                matched.add(cand)
        return iter([SemanticUri(self._scheme, p) for p in sorted(matched)])

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        _ = self._validate_uri(uri, allow_root=True)
        return None
