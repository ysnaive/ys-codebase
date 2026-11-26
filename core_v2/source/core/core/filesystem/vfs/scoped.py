"""Workspace VfsHub, AccessPolicy, module-isolated ScopedVfs, and privileged KernelVfs."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import errno
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import BinaryIO, Final, Iterator, Mapping, Optional, Sequence

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    has_symlink_raw_path,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    walk_nonsymlink_dir_tree,
)
from core.filesystem.vfs.capabilities import VfsCapabilities, VfsStat
from core.filesystem.vfs.echo import VfsEchoGuard
from core.filesystem.vfs.mount import (
    UriMountTable,
    VfsMountRouteInfo,
    vfs_inspect_mount_route,
    vfs_list_physical_mount_roots,
)
from core.filesystem.vfs.provider import (
    vfs_kernel_delete,
    vfs_kernel_mkdir,
    vfs_kernel_move,
    vfs_kernel_write_bytes_atomic,
    vfs_replace_entry_with_retry,
)
from core.filesystem.vfs.readonly import ReadonlyPolicy
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    MAX_USER_JSON_DEPTH,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    SemanticUri,
    clone_strict_json_object,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_frozenset,
    validate_wire_json_object,
)

_KERNEL_MODULE_ID: Final[ModuleId] = ModuleId("core")
_MAX_SUBTREE_ECHO_FILES: Final[int] = 2048

_KERNEL_ONLY_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "yscb",
        "yscb.host",
        "module",
        "module.mirror",
        "snapshot",
        "yscb.venv",
    }
)
_EXTRA_GRANTABLE_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "module.source",
        "module.build",
        "module.release",
        "config",
    }
)
_MODULE_ISOLATED_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "config.local",
        "cache",
        "storage",
        "storage.local",
    }
)
_MODULE_READ_ISOLATED_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "config.local",
        "storage.local",
    }
)
_HOST_CONTROL_FILENAMES: Final[frozenset[str]] = frozenset(
    {
        "yscb.config.json",
        "yscb.config.local.json",
        "yscb.py",
        ".gitignore",
    }
)


def _freeze_extra_writable_schemes(
    raw: Mapping[ModuleId, frozenset[str]],
) -> Mapping[ModuleId, frozenset[str]]:
    if not isinstance(raw, Mapping):
        raise ValueError("AccessPolicy.extra_writable_schemes must be a Mapping[ModuleId, frozenset[str]].")
    frozen_map: dict[ModuleId, frozenset[str]] = {}
    for mod_id, schemes in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"AccessPolicy.extra_writable_schemes keys must be ModuleId, got {mod_id!r}")
        clean_set = require_typed_frozenset(schemes, str, f"AccessPolicy.extra_writable_schemes[{mod_id}]")
        for s_tok in clean_set:
            require_pure_str(s_tok, "AccessPolicy scheme", non_empty=True)
        frozen_map[mod_id] = clean_set
    return MappingProxyType(frozen_map)


def _reject_duplicate_pairs(pairs: list[tuple[str, JsonValue]]) -> MutableJsonObject:
    out: MutableJsonObject = {}
    for key, val in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON object key rejected: {key!r}")
        out[key] = val
    return out


def _reject_nonfinite_json_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON constant rejected: {token}")


def _strict_parse_any_json_value(raw_text: str) -> JsonValue:
    require_pure_str(raw_text, "raw_text")
    try:
        decoded: JsonValue = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_json_constant,
        )
        validate_wire_json_object({"v": decoded}, max_depth=MAX_USER_JSON_DEPTH + 1, label="JSON")
    except RecursionError as exc:
        raise ValueError("JSON nesting depth limit exceeded.") from exc
    except TypeError as exc:
        raise ValueError(str(exc)) from exc
    return decoded


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """Module-level write allowlist and readonly-tunnel privilege configuration."""

    extra_writable_schemes: Mapping[ModuleId, frozenset[str]] = field(default_factory=dict)
    readonly_tunnel_modules: frozenset[ModuleId] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "extra_writable_schemes",
            _freeze_extra_writable_schemes(self.extra_writable_schemes),
        )
        object.__setattr__(
            self,
            "readonly_tunnel_modules",
            require_typed_frozenset(
                self.readonly_tunnel_modules,
                ModuleId,
                "AccessPolicy.readonly_tunnel_modules",
            ),
        )


@dataclass(frozen=True, slots=True)
class _VfsScopeConfig:
    mount_table: UriMountTable
    readonly_policy: ReadonlyPolicy
    echo_guard: VfsEchoGuard
    access_policy: AccessPolicy
    module_id: ModuleId
    is_kernel: bool


def _check_single_uri_scheme_policy(
    cfg: _VfsScopeConfig,
    candidate_uri: SemanticUri,
    granted_schemes: frozenset[str],
    *,
    allow_bound_grant: bool,
    bound_scheme: str,
) -> Optional[ErrorCode]:
    sch = candidate_uri.scheme
    if sch in _KERNEL_ONLY_SCHEMES:
        return ErrorCode.ACCESS_DENIED
    bound_compensated = allow_bound_grant and (bound_scheme in granted_schemes)
    if sch in _EXTRA_GRANTABLE_SCHEMES and sch not in granted_schemes and not bound_compensated:
        return ErrorCode.ACCESS_DENIED
    if sch in _MODULE_ISOLATED_SCHEMES and sch not in granted_schemes and not bound_compensated:
        first_seg = candidate_uri.rel_path.split("/", 1)[0] if candidate_uri.rel_path else ""
        if first_seg != cfg.module_id.value:
            return ErrorCode.ACCESS_DENIED
    return None


def _is_host_control_uri(host_uri: SemanticUri) -> bool:
    if not host_uri.rel_path:
        return False
    first_seg = host_uri.rel_path.split("/", 1)[0].lower()
    return first_seg == ".git" or first_seg in _HOST_CONTROL_FILENAMES


def _is_foreign_read_isolated_uri(
    cfg: _VfsScopeConfig,
    candidate_uri: SemanticUri,
    *,
    allow_storage_local_root: bool,
) -> bool:
    if candidate_uri.scheme not in _MODULE_READ_ISOLATED_SCHEMES:
        return False
    if not candidate_uri.rel_path:
        return not (allow_storage_local_root and candidate_uri.scheme == "storage.local")
    first_seg = candidate_uri.rel_path.split("/", 1)[0]
    return first_seg != cfg.module_id.value


def _check_scheme_read_error(
    cfg: _VfsScopeConfig,
    bound: SemanticUri,
    route: VfsMountRouteInfo,
    *,
    allow_storage_local_root: bool = False,
) -> Optional[ErrorCode]:
    if cfg.is_kernel:
        return None
    allow_root = (
        allow_storage_local_root
        and bound == SemanticUri("storage.local", "")
        and route.terminal_uri == SemanticUri("storage.local", "")
    )
    for candidate_uri in (bound, route.terminal_uri):
        if _is_foreign_read_isolated_uri(cfg, candidate_uri, allow_storage_local_root=allow_root):
            return ErrorCode.ACCESS_DENIED
    if route.unmasked_host_path is not None:
        for _m_scheme, m_uri in cfg.mount_table.iter_covering_mounts(route.unmasked_host_path):
            if _is_foreign_read_isolated_uri(cfg, m_uri, allow_storage_local_root=allow_root):
                return ErrorCode.ACCESS_DENIED
    return None


def _assert_scheme_read_allowed(
    cfg: _VfsScopeConfig,
    bound: SemanticUri,
    route: VfsMountRouteInfo,
    *,
    allow_storage_local_root: bool = False,
) -> None:
    err_code = _check_scheme_read_error(
        cfg,
        bound,
        route,
        allow_storage_local_root=allow_storage_local_root,
    )
    if err_code is not None:
        raise YscbError(
            err_code,
            f"Module '{cfg.module_id}' is not permitted to read '{bound}'.",
        )


def _filter_readable_entries(
    cfg: _VfsScopeConfig,
    raw_entries: Iterator[SemanticUri],
) -> Iterator[SemanticUri]:
    for entry_uri in raw_entries:
        entry_route = vfs_inspect_mount_route(cfg.mount_table, entry_uri)
        if _check_scheme_read_error(cfg, entry_uri, entry_route) is None:
            yield entry_uri


def _check_scheme_write_error(
    cfg: _VfsScopeConfig,
    bound: SemanticUri,
    route: VfsMountRouteInfo,
) -> Optional[ErrorCode]:
    if cfg.is_kernel:
        if route.unmasked_host_path is not None:
            return None
        if (
            VfsCapabilities.WRITABLE in route.provider.base_capabilities
            or VfsCapabilities.WRITABLE in route.terminal_provider.base_capabilities
        ):
            return None
        return ErrorCode.READONLY_VIOLATION

    granted_schemes = cfg.access_policy.extra_writable_schemes.get(cfg.module_id, frozenset())
    for candidate_uri in (bound, route.terminal_uri):
        err = _check_single_uri_scheme_policy(
            cfg,
            candidate_uri,
            granted_schemes,
            allow_bound_grant=True,
            bound_scheme=bound.scheme,
        )
        if err is not None:
            return err

    if route.unmasked_host_path is not None:
        covering = cfg.mount_table.iter_covering_mounts(route.unmasked_host_path)
        if covering:
            root_len_by_scheme = {
                m_sch: len(m_root.comparison_key.rstrip("/\\"))
                for m_sch, m_root in vfs_list_physical_mount_roots(cfg.mount_table)
            }
            max_root_len = max((root_len_by_scheme.get(m_sch, 0) for m_sch, _ in covering), default=0)
            co_deepest_schemes = frozenset(
                m_sch for m_sch, _ in covering if root_len_by_scheme.get(m_sch, 0) == max_root_len
            )
            has_colocated_project = ("project" in co_deepest_schemes) and ("yscb.host" in co_deepest_schemes)
            for m_scheme, m_uri in covering:
                if m_scheme == "yscb.host":
                    if _is_host_control_uri(m_uri):
                        return ErrorCode.ACCESS_DENIED
                    if (m_scheme in co_deepest_schemes) and not has_colocated_project:
                        return ErrorCode.ACCESS_DENIED
                    continue
                if m_scheme == "yscb":
                    if m_scheme in co_deepest_schemes:
                        return ErrorCode.ACCESS_DENIED
                    continue
                allow_grant = m_scheme in (bound.scheme, route.terminal_uri.scheme)
                cov_err = _check_single_uri_scheme_policy(
                    cfg,
                    m_uri,
                    granted_schemes,
                    allow_bound_grant=allow_grant,
                    bound_scheme=bound.scheme,
                )
                if cov_err is not None:
                    return cov_err
                m_caps = cfg.mount_table.get_provider(m_scheme).get_capabilities(m_uri)
                if VfsCapabilities.WRITABLE not in m_caps:
                    return ErrorCode.READONLY_VIOLATION

    if VfsCapabilities.WRITABLE not in route.provider.get_capabilities(bound):
        return ErrorCode.READONLY_VIOLATION
    return None


def _assert_no_protected_submount_descendant(cfg: _VfsScopeConfig, target_hp: HostPath, op_label: str) -> None:
    if cfg.is_kernel:
        return
    t_key = target_hp.comparison_key.rstrip("/\\")
    t_prefix = f"{t_key}{os.sep}"
    for m_scheme, m_root_hp in vfs_list_physical_mount_roots(cfg.mount_table):
        m_key = m_root_hp.comparison_key.rstrip("/\\")
        if m_key == t_key or m_key.startswith(t_prefix):
            m_root_uri = SemanticUri(m_scheme, "")
            m_route = vfs_inspect_mount_route(cfg.mount_table, m_root_uri)
            if _check_scheme_write_error(cfg, m_root_uri, m_route) is not None:
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Module '{cfg.module_id}' cannot {op_label} '{target_hp}' spanning protected mount '{m_scheme}://'.",
                )


def _has_tunnel_privilege(cfg: _VfsScopeConfig, *, force_tunnel: bool) -> bool:
    return force_tunnel or cfg.is_kernel or (cfg.module_id in cfg.access_policy.readonly_tunnel_modules)


def _assert_subtree_not_readonly_protected(readonly_policy: ReadonlyPolicy, dir_hp: HostPath) -> None:
    raw_dir = str(dir_hp)
    if not os.path.isdir(raw_dir):
        return
    for cur_dir, entries in walk_nonsymlink_dir_tree(raw_dir, ignored_dir_prefixes=(".tmp_", ".staging_")):
        for ent in entries:
            if ent.is_symlink() or ent.is_dir(follow_symlinks=False):
                continue
            child_hp = HostPath(os.path.join(cur_dir, ent.name))
            if readonly_policy.is_protected(child_hp) or readonly_policy.is_os_readonly(child_hp):
                raise YscbError(
                    ErrorCode.READONLY_VIOLATION,
                    f"Cannot delete directory '{dir_hp}' containing readonly-protected file '{child_hp}'.",
                )


def _collect_subtree_regular_files(dir_hp: HostPath, *, limit: int) -> list[tuple[HostPath, str]]:
    raw_dir = str(dir_hp)
    if not os.path.isdir(raw_dir) or has_symlink_raw_path(raw_dir):
        return []
    out: list[tuple[HostPath, str]] = []
    for cur_dir, entries in walk_nonsymlink_dir_tree(raw_dir, ignored_dir_prefixes=(".tmp_", ".staging_")):
        for ent in entries:
            if len(out) >= limit:
                return out
            if is_atomic_staging_filename(ent.name) or ent.is_symlink() or ent.is_dir(follow_symlinks=False):
                continue
            try:
                f_st = ent.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(f_st.st_mode):
                continue
            child_raw = os.path.join(cur_dir, ent.name)
            try:
                rel_sub = os.path.relpath(child_raw, raw_dir)
                out.append((HostPath(child_raw), rel_sub))
            except ValueError:
                continue
    return out


def _glob_segment_to_regex(segment: str) -> str:
    out: list[str] = []
    idx = 0
    length = len(segment)
    while idx < length:
        ch = segment[idx]
        if ch == "*":
            out.append("[^/]*")
            idx += 1
        elif ch == "?":
            out.append("[^/]")
            idx += 1
        elif ch == "[":
            end = idx + 1
            if end < length and segment[end] in ("!", "^"):
                end += 1
            if end < length and segment[end] == "]":
                end += 1
            while end < length and segment[end] != "]":
                end += 1
            if end >= length:
                out.append(r"\[")
                idx += 1
            else:
                body = segment[idx + 1 : end]
                neg = ""
                if body.startswith("!"):
                    neg = "^/"
                    inner = body[1:]
                else:
                    inner = body
                escaped_inner = (
                    inner.replace("\\", r"\\")
                    .replace("[", r"\[")
                    .replace("]", r"\]")
                    .replace("--", r"\-\-")
                    .replace("&&", r"\&\&")
                    .replace("~~", r"\~\~")
                    .replace("||", r"\|\|")
                )
                if not neg and escaped_inner.startswith("^"):
                    escaped_inner = r"\^" + escaped_inner[1:]
                out.append(f"[{neg}{escaped_inner}]")
                idx = end + 1
        else:
            out.append(re.escape(ch))
            idx += 1
    return "".join(out)


def _compile_posix_glob_pattern(pattern: str) -> re.Pattern[str]:
    require_pure_str(pattern, "pattern", non_empty=True)
    if (
        pattern.startswith("/")
        or "\\" in pattern
        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in pattern)
    ):
        raise ValueError(f"Invalid VFS glob pattern: {pattern!r}")
    raw_segs = pattern.split("/")
    if any(seg in ("", ".", "..") for seg in raw_segs):
        raise ValueError(f"VFS glob pattern must contain clean relative POSIX segments: {pattern!r}")
    segs: list[str] = []
    for seg in raw_segs:
        if seg == "**" and segs and segs[-1] == "**":
            continue
        segs.append(seg)
    parts: list[str] = ["^"]
    last_idx = len(segs) - 1
    for idx, seg in enumerate(segs):
        if seg == "**":
            if idx == last_idx:
                parts.append(".+" if idx == 0 else "/.+")
            else:
                parts.append("(?:.+/)?" if idx == 0 else "/(?:.+/)?")
        else:
            if idx > 0 and segs[idx - 1] != "**":
                parts.append("/")
            parts.append(_glob_segment_to_regex(seg))
    parts.append("$")
    try:
        return re.compile("".join(parts))
    except re.error as exc:
        raise ValueError(f"Invalid VFS glob pattern {pattern!r}: {exc}") from exc


def _assert_no_uncollapsed_raw_symlink(raw_joined: str, raw_label: str) -> None:
    cand = Path(raw_joined)
    acc: Optional[Path] = None
    for part in cand.parts:
        if part == "..":
            if acc is not None and (is_symlink_or_reparse(str(acc)) or has_symlink_raw_path(str(acc))):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink traversal in path: '{raw_label}'.")
            acc = acc.parent if acc is not None else Path("..")
            continue
        acc = Path(part) if acc is None else (acc / part)
        if is_symlink_or_reparse(str(acc)):
            raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink path: '{raw_label}'.")


def _select_deepest_allowed_mounts(
    cfg: _VfsScopeConfig,
    target_hp: HostPath,
    raw_label: str,
) -> tuple[tuple[str, SemanticUri], ...]:
    covering = cfg.mount_table.iter_covering_mounts(target_hp)
    if not covering:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Path '{raw_label}' is outside all mounted workspace VFS roots.",
        )
    root_len_by_scheme = {
        m_sch: len(m_root.comparison_key.rstrip("/\\"))
        for m_sch, m_root in vfs_list_physical_mount_roots(cfg.mount_table)
    }
    max_root_len = max((root_len_by_scheme.get(m_sch, 0) for m_sch, _ in covering), default=0)
    deepest = tuple((m_sch, m_uri) for m_sch, m_uri in covering if root_len_by_scheme.get(m_sch, 0) == max_root_len)
    deepest_schemes = frozenset(m_sch for m_sch, _ in deepest)
    has_colocated_project = ("project" in deepest_schemes) and ("yscb.host" in deepest_schemes)
    if not cfg.is_kernel:
        for m_sch in deepest_schemes:
            if m_sch in _KERNEL_ONLY_SCHEMES and not (m_sch == "yscb.host" and has_colocated_project):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Module '{cfg.module_id}' cannot resolve path '{raw_label}' inside protected mount '{m_sch}://'.",
                )
    return tuple(
        (m_sch, m_uri)
        for m_sch, m_uri in deepest
        if (cfg.is_kernel or m_sch not in _KERNEL_ONLY_SCHEMES)
        and not (m_sch == "yscb.host" and has_colocated_project)
    )


class ScopedVfs:
    """Module-scoped VFS facade enforcing '@/' expansion, cross-module isolation, and readonly guards."""

    __slots__ = ("_scope_cfg",)

    def _cfg(self) -> _VfsScopeConfig:
        try:
            cfg = self._scope_cfg
        except AttributeError as exc:
            raise RuntimeError("ScopedVfs must be created via VfsHub.for_module() or VfsHub.for_kernel().") from exc
        if not isinstance(cfg, _VfsScopeConfig):
            raise RuntimeError("ScopedVfs configuration is uninitialized.")
        return cfg

    @property
    def module_id(self) -> ModuleId:
        return self._cfg().module_id

    def bind_uri(self, uri: SemanticUri | str) -> SemanticUri:
        cfg = self._cfg()
        if isinstance(uri, SemanticUri):
            parsed = uri
        elif type(uri) is str:
            parsed = SemanticUri.parse(uri)
        else:
            raise ValueError(f"ScopedVfs expected SemanticUri or str, got {uri!r}")
        return parsed.bind_module(cfg.module_id)

    def get_capabilities(self, uri: SemanticUri | str) -> VfsCapabilities:
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        caps = route.provider.get_capabilities(bound)
        if _check_scheme_read_error(cfg, bound, route) is not None:
            caps = caps & ~(
                VfsCapabilities.READABLE
                | VfsCapabilities.ENUMERABLE
                | VfsCapabilities.PHYSICAL_PATH
            )
        err_code = _check_scheme_write_error(cfg, bound, route)
        if err_code is not None:
            return caps & ~VfsCapabilities.WRITABLE
        if cfg.is_kernel:
            caps = caps | VfsCapabilities.WRITABLE
        backing_hp = route.unmasked_host_path
        if backing_hp is not None and not _has_tunnel_privilege(cfg, force_tunnel=False):
            if cfg.readonly_policy.is_protected(backing_hp) or cfg.readonly_policy.is_os_readonly(backing_hp):
                caps = caps & ~VfsCapabilities.WRITABLE
        return caps

    def can_read(self, uri: SemanticUri | str) -> bool:
        return VfsCapabilities.READABLE in self.get_capabilities(uri)

    def can_write(self, uri: SemanticUri | str) -> bool:
        return VfsCapabilities.WRITABLE in self.get_capabilities(uri)

    def exists(self, uri: SemanticUri | str) -> bool:
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route)
        return route.provider.exists(bound)

    def stat(self, uri: SemanticUri | str) -> VfsStat:
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route)
        raw_st = route.provider.stat(bound)
        if not raw_st.exists:
            return raw_st
        backing_hp = route.unmasked_host_path
        is_ro = raw_st.is_readonly or (
            backing_hp is not None and cfg.readonly_policy.is_protected(backing_hp)
        )
        return VfsStat(
            exists=raw_st.exists,
            is_dir=raw_st.is_dir,
            is_readonly=is_ro,
            size_bytes=raw_st.size_bytes,
            mtime_ns=raw_st.mtime_ns,
            ino=raw_st.ino,
        )

    def read_bytes(self, uri: SemanticUri | str) -> bytes:
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route)
        return route.provider.read_bytes(bound)

    def read_text(self, uri: SemanticUri | str, *, encoding: str = "utf-8") -> str:
        require_pure_str(encoding, "encoding", non_empty=True)
        return self.read_bytes(uri).decode(encoding)

    def read_json(self, uri: SemanticUri | str) -> JsonValue:
        raw_bytes = self.read_bytes(uri)
        if len(raw_bytes) > MAX_JSON_FILE_BYTES:
            raise YscbError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"JSON file '{uri}' exceeds {MAX_JSON_FILE_BYTES} bytes limit.",
            )
        return _strict_parse_any_json_value(raw_bytes.decode("utf-8"))

    def open_read(self, uri: SemanticUri | str) -> BinaryIO:
        """Open a readable binary stream for uri under module scope and read-isolation guards."""
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route)
        return route.provider.open_read(bound)

    def _prepare_mutation(
        self,
        bound: SemanticUri,
        *,
        force_tunnel: bool,
    ) -> tuple[VfsMountRouteInfo, bool]:
        cfg = self._cfg()
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        err_code = _check_scheme_write_error(cfg, bound, route)
        if err_code is not None:
            raise YscbError(
                err_code,
                f"Module '{cfg.module_id}' is not permitted to mutate '{bound}'.",
            )
        backing_hp = route.unmasked_host_path
        needs_tunnel = False
        if backing_hp is not None:
            is_prot = cfg.readonly_policy.is_protected(backing_hp) or cfg.readonly_policy.is_os_readonly(backing_hp)
            if is_prot:
                if not _has_tunnel_privilege(cfg, force_tunnel=force_tunnel):
                    raise YscbError(
                        ErrorCode.READONLY_VIOLATION,
                        f"Write denied on readonly-protected path '{backing_hp}' ('{bound}').",
                    )
                needs_tunnel = True
            elif force_tunnel:
                needs_tunnel = True
        return (route, needs_tunnel)

    def _write_bytes_impl(self, uri: SemanticUri | str, data: bytes, *, force_tunnel: bool) -> None:
        if not isinstance(data, bytes):
            raise ValueError(f"write_bytes requires plain bytes, got {type(data).__name__}")
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route, needs_tunnel = self._prepare_mutation(bound, force_tunnel=force_tunnel)
        if not bound.rel_path:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Operation requires a non-root file URI: '{bound}'.")
        provider = route.provider
        backing_hp = route.unmasked_host_path

        def _on_before_replace(mtime_ns: int, size: int, ino: int) -> None:
            if backing_hp is not None:
                cfg.echo_guard.record_write(backing_hp, mtime_ns, size, ino)

        def _perform_write() -> None:
            if cfg.is_kernel:
                vfs_kernel_write_bytes_atomic(
                    route.terminal_provider,
                    route.terminal_uri,
                    data,
                    before_replace=_on_before_replace,
                )
            else:
                provider.write_bytes_atomic(bound, data, before_replace=_on_before_replace)

        if needs_tunnel and backing_hp is not None:
            with cfg.readonly_policy.authorized_write_tunnel(backing_hp):
                _perform_write()
            try:
                post_st = os.lstat(str(backing_hp))
                cfg.echo_guard.record_write(
                    backing_hp,
                    int(post_st.st_mtime_ns),
                    int(post_st.st_size),
                    int(post_st.st_ino),
                )
            except OSError:
                pass
        else:
            _perform_write()

    def write_bytes(self, uri: SemanticUri | str, data: bytes) -> None:
        self._write_bytes_impl(uri, data, force_tunnel=False)

    def write_text(
        self,
        uri: SemanticUri | str,
        text: str,
        *,
        encoding: str = "utf-8",
        normalize_lf: bool = True,
    ) -> None:
        require_pure_str(text, "text")
        require_pure_str(encoding, "encoding", non_empty=True)
        require_pure_bool(normalize_lf, "normalize_lf")
        out_text = text.replace("\r\n", "\n").replace("\r", "\n") if normalize_lf else text
        self.write_bytes(uri, out_text.encode(encoding))

    def write_json(self, uri: SemanticUri | str, payload: JsonObject, *, indent: int = 2) -> None:
        safe_indent = require_pure_int(indent, "indent", min_val=0, max_val=16)
        normalized = clone_strict_json_object(payload, max_depth=MAX_USER_JSON_DEPTH, label="write_json payload")
        try:
            encoded = (json.dumps(normalized, indent=safe_indent, ensure_ascii=False, allow_nan=False) + "\n").encode(
                "utf-8"
            )
        except RecursionError as exc:
            raise ValueError("write_json payload exceeded maximum recursion depth.") from exc
        self.write_bytes(uri, encoded)

    def mkdir(self, uri: SemanticUri | str, *, parents: bool = True) -> None:
        require_pure_bool(parents, "parents")
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route, _needs_tunnel = self._prepare_mutation(bound, force_tunnel=False)
        provider = route.provider
        if cfg.is_kernel and VfsCapabilities.WRITABLE not in provider.base_capabilities:
            term_prov = route.terminal_provider
            term_uri = route.terminal_uri
            if not parents and bound != term_uri:
                if not bound.rel_path and term_uri.rel_path:
                    vfs_kernel_mkdir(term_prov, term_uri, parents=True)
                    return
                if bound.rel_path and "/" not in bound.rel_path and term_uri.rel_path:
                    prefix_rel = term_uri.rel_path.rsplit("/", 1)[0] if "/" in term_uri.rel_path else ""
                    if prefix_rel:
                        vfs_kernel_mkdir(term_prov, SemanticUri(term_uri.scheme, prefix_rel), parents=True)
            vfs_kernel_mkdir(term_prov, term_uri, parents=parents)
            return
        provider.mkdir(bound, parents=parents)

    def delete(self, uri: SemanticUri | str, *, recursive: bool = False) -> bool:
        require_pure_bool(recursive, "recursive")
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route, needs_tunnel = self._prepare_mutation(bound, force_tunnel=False)
        if not bound.rel_path:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Delete operation requires a non-root URI: '{bound}'.")
        provider = route.provider
        backing_hp = route.unmasked_host_path
        if backing_hp is not None and recursive:
            _assert_no_protected_submount_descendant(cfg, backing_hp, "recursively delete")
            if not _has_tunnel_privilege(cfg, force_tunnel=False):
                _assert_subtree_not_readonly_protected(cfg.readonly_policy, backing_hp)
        subtree_files: list[tuple[HostPath, str]] = (
            _collect_subtree_regular_files(backing_hp, limit=_MAX_SUBTREE_ECHO_FILES)
            if (backing_hp is not None and recursive)
            else []
        )
        with ExitStack() as stack:
            if backing_hp is not None and needs_tunnel and os.path.isfile(str(backing_hp)):
                stack.enter_context(cfg.readonly_policy.authorized_write_tunnel(backing_hp))
            if cfg.is_kernel:
                deleted = vfs_kernel_delete(route.terminal_provider, route.terminal_uri, recursive=recursive)
            else:
                deleted = provider.delete(bound, recursive=recursive)
        if deleted and backing_hp is not None:
            cfg.echo_guard.record_write(backing_hp, -1, -1, -1)
            for child_hp, _rel_sub in subtree_files:
                cfg.echo_guard.record_write(child_hp, -1, -1, -1)
        return deleted

    def move(self, src: SemanticUri | str, dst: SemanticUri | str) -> None:
        cfg = self._cfg()
        bound_src = self.bind_uri(src)
        bound_dst = self.bind_uri(dst)
        src_route, src_tunnel = self._prepare_mutation(bound_src, force_tunnel=False)
        dst_route, dst_tunnel = self._prepare_mutation(bound_dst, force_tunnel=False)
        if not bound_src.rel_path or not bound_dst.rel_path:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Move operation requires non-root source and destination URIs: '{bound_src}' -> '{bound_dst}'.",
            )
        src_hp = src_route.unmasked_host_path
        dst_hp = dst_route.unmasked_host_path
        if src_hp is not None:
            _assert_no_protected_submount_descendant(cfg, src_hp, "move")
            if not _has_tunnel_privilege(cfg, force_tunnel=False):
                _assert_subtree_not_readonly_protected(cfg.readonly_policy, src_hp)
        if dst_hp is not None:
            _assert_no_protected_submount_descendant(cfg, dst_hp, "overwrite via move")

        src_st = self.stat(bound_src)
        if not src_st.exists:
            raise FileNotFoundError(f"Source URI does not exist: '{bound_src}'")

        term_src = src_route.terminal_uri
        term_dst = dst_route.terminal_uri
        if term_src == term_dst or (src_hp is not None and dst_hp is not None and src_hp == dst_hp):
            return

        if src_hp is not None and dst_hp is not None:
            norm_src = src_hp.comparison_key.rstrip("/\\")
            norm_dst = dst_hp.comparison_key.rstrip("/\\")
            if norm_dst.startswith(f"{norm_src}{os.sep}") or norm_src.startswith(f"{norm_dst}{os.sep}"):
                raise ValueError(f"Cannot move overlapping ancestor/descendant paths: '{bound_src}' -> '{bound_dst}'")

        moved_children: list[tuple[HostPath, str]] = (
            _collect_subtree_regular_files(src_hp, limit=_MAX_SUBTREE_ECHO_FILES // 2)
            if (src_st.is_dir and src_hp is not None)
            else []
        )

        if term_src.scheme == term_dst.scheme:
            s_rel = term_src.rel_path
            d_rel = term_dst.rel_path
            if (not s_rel) or (not d_rel) or d_rel.startswith(f"{s_rel}/") or s_rel.startswith(f"{d_rel}/"):
                raise ValueError(f"Cannot move overlapping ancestor/descendant URIs: '{bound_src}' -> '{bound_dst}'")
            term_prov = src_route.terminal_provider
            if cfg.is_kernel or VfsCapabilities.WRITABLE in term_prov.base_capabilities:
                with ExitStack() as stack:
                    if src_tunnel and src_hp is not None and os.path.isfile(str(src_hp)):
                        stack.enter_context(cfg.readonly_policy.authorized_write_tunnel(src_hp))
                    if dst_tunnel and dst_hp is not None:
                        stack.enter_context(cfg.readonly_policy.authorized_write_tunnel(dst_hp))
                    if cfg.is_kernel:
                        vfs_kernel_move(term_prov, term_src, term_dst)
                    else:
                        term_prov.move(term_src, term_dst)
                self._record_move_echo(src_hp, dst_hp, moved_children)
                return

        if src_hp is not None and dst_hp is not None:
            raw_src = str(src_hp)
            raw_dst = str(dst_hp)
            if has_symlink_raw_path(raw_src) or has_symlink_raw_path(raw_dst):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Refusing move traversing symlink: '{bound_src}' -> '{bound_dst}'",
                )
            os.makedirs(str(dst_hp.path.parent), exist_ok=True)
            if has_symlink_raw_path(raw_dst):
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing move destination traversing symlink: {raw_dst}")
            try:
                with ExitStack() as stack:
                    if src_tunnel and os.path.isfile(raw_src):
                        stack.enter_context(cfg.readonly_policy.authorized_write_tunnel(src_hp))
                    if dst_tunnel:
                        stack.enter_context(cfg.readonly_policy.authorized_write_tunnel(dst_hp))
                    vfs_replace_entry_with_retry(raw_src, raw_dst)
                self._record_move_echo(src_hp, dst_hp, moved_children)
                return
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise

        self._cross_provider_move(bound_src, bound_dst)

    def _record_move_echo(
        self,
        src_hp: Optional[HostPath],
        dst_hp: Optional[HostPath],
        moved_children: Sequence[tuple[HostPath, str]],
    ) -> None:
        cfg = self._cfg()
        if src_hp is not None:
            cfg.echo_guard.record_write(src_hp, -1, -1, -1)
            for child_src_hp, _rel_sub in moved_children:
                cfg.echo_guard.record_write(child_src_hp, -1, -1, -1)
        if dst_hp is not None:
            try:
                st = os.lstat(str(dst_hp))
                cfg.echo_guard.record_write(dst_hp, int(st.st_mtime_ns), int(st.st_size), int(st.st_ino))
            except OSError:
                pass
            for _child_src_hp, rel_sub in moved_children:
                try:
                    child_dst_hp = HostPath(os.path.join(str(dst_hp), rel_sub))
                    cst = os.lstat(str(child_dst_hp))
                    cfg.echo_guard.record_write(
                        child_dst_hp,
                        int(cst.st_mtime_ns),
                        int(cst.st_size),
                        int(cst.st_ino),
                    )
                except (OSError, ValueError):
                    continue

    def _cross_provider_move(self, bound_src: SemanticUri, bound_dst: SemanticUri) -> None:
        src_st = self.stat(bound_src)
        if not src_st.exists:
            raise FileNotFoundError(f"Source URI does not exist: '{bound_src}'")
        if not src_st.is_dir:
            payload = self.read_bytes(bound_src)
            self.write_bytes(bound_dst, payload)
            self.delete(bound_src, recursive=False)
            return
        self.mkdir(bound_dst, parents=True)
        base_len = len(bound_src.rel_path) + (1 if bound_src.rel_path else 0)
        for child_uri in list(self.iter_entries(bound_src, recursive=True)):
            sub_rel = child_uri.rel_path[base_len:]
            target_child = bound_dst.join(sub_rel)
            child_st = self.stat(child_uri)
            if child_st.is_dir:
                self.mkdir(target_child, parents=True)
            else:
                self.write_bytes(target_child, self.read_bytes(child_uri))
        self.delete(bound_src, recursive=True)

    def iter_entries(self, uri: SemanticUri | str, *, recursive: bool = False) -> Iterator[SemanticUri]:
        require_pure_bool(recursive, "recursive")
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route)
        raw_entries = route.provider.iter_entries(bound, recursive=recursive)
        if cfg.is_kernel:
            return raw_entries
        return _filter_readable_entries(cfg, raw_entries)

    def try_get_physical_path(self, uri: SemanticUri | str) -> Optional[HostPath]:
        cfg = self._cfg()
        bound = self.bind_uri(uri)
        route = vfs_inspect_mount_route(cfg.mount_table, bound)
        _assert_scheme_read_allowed(cfg, bound, route, allow_storage_local_root=True)
        return route.provider.try_get_physical_path(bound)

    def glob(self, uri_dir: SemanticUri | str, pattern: str) -> tuple[SemanticUri, ...]:
        """Return deterministically sorted file SemanticUris under uri_dir matching a relative POSIX glob pattern."""
        rx = _compile_posix_glob_pattern(pattern)
        cfg = self._cfg()
        bound_dir = self.bind_uri(uri_dir)
        route = vfs_inspect_mount_route(cfg.mount_table, bound_dir)
        _assert_scheme_read_allowed(cfg, bound_dir, route)
        dir_st = self.stat(bound_dir)
        if not dir_st.exists or not dir_st.is_dir:
            return ()
        base_prefix = f"{bound_dir.rel_path}/" if bound_dir.rel_path else ""
        matches: list[SemanticUri] = []
        for entry_uri in self.iter_entries(bound_dir, recursive=True):
            if base_prefix:
                if not entry_uri.rel_path.startswith(base_prefix):
                    continue
                rel_sub = entry_uri.rel_path[len(base_prefix) :]
            else:
                rel_sub = entry_uri.rel_path
            if not rel_sub or not rx.fullmatch(rel_sub):
                continue
            ent_st = self.stat(entry_uri)
            if not ent_st.exists or ent_st.is_dir:
                continue
            matches.append(entry_uri)
        return tuple(sorted(matches, key=str))

    def resolve_caller_uri(self, raw_path: str, caller_cwd: HostPath) -> SemanticUri:
        """Resolve a caller-supplied URI or local relative/absolute path into an accessible SemanticUri."""
        require_pure_str(raw_path, "raw_path", non_empty=True)
        if not isinstance(caller_cwd, HostPath):
            raise ValueError(f"resolve_caller_uri requires HostPath caller_cwd, got {caller_cwd!r}")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_path) or not raw_path.strip():
            raise ValueError(f"Invalid caller path containing blank or control characters: {raw_path!r}")
        clean = raw_path.strip()
        cfg = self._cfg()
        if "://" in clean:
            bound = self.bind_uri(clean)
            try:
                route = vfs_inspect_mount_route(cfg.mount_table, bound)
            except YscbError as exc:
                cause = exc.__cause__
                if exc.detail.code == ErrorCode.SECURITY_GATED or (
                    isinstance(cause, YscbError) and cause.detail.code == ErrorCode.SECURITY_GATED
                ):
                    raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink path behind URI '{bound}'.") from exc
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Mount scheme is unavailable for '{bound}': {exc.detail.message}") from exc
            if not cfg.is_kernel and (
                bound.scheme in _KERNEL_ONLY_SCHEMES or route.terminal_uri.scheme in _KERNEL_ONLY_SCHEMES
            ):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Module '{cfg.module_id}' is not permitted to resolve protected URI '{bound}'.",
                )
            _assert_scheme_read_allowed(cfg, bound, route)
            if route.unmasked_host_path is not None:
                raw_backing = str(route.unmasked_host_path)
                if has_symlink_raw_path(raw_backing) or is_symlink_or_reparse(raw_backing):
                    raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink path behind URI '{bound}'.")
                _ = _select_deepest_allowed_mounts(cfg, route.unmasked_host_path, clean)
            return bound
        cand = Path(clean)
        if (cand.drive or cand.anchor) and not cand.is_absolute():
            raise ValueError(f"Half-qualified drive or root-relative path is forbidden: {raw_path!r}")
        segs_to_check = cand.parts[1:] if cand.is_absolute() else cand.parts
        if any(":" in seg for seg in segs_to_check):
            raise ValueError(f"Illegal drive or stream syntax in path: {raw_path!r}")
        raw_joined = str(cand) if cand.is_absolute() else os.path.join(str(caller_cwd), clean)
        _assert_no_uncollapsed_raw_symlink(raw_joined, clean)
        norm_raw = os.path.normpath(raw_joined)
        if has_symlink_raw_path(norm_raw) or is_symlink_or_reparse(norm_raw):
            raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink path: '{clean}'.")
        target_hp = HostPath(norm_raw)
        candidates = _select_deepest_allowed_mounts(cfg, target_hp, clean)
        if not candidates:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"No accessible VFS mount covers path '{clean}'.")
        chosen_uri = next((m_uri for m_sch, m_uri in candidates if m_sch == "project"), candidates[0][1])
        chosen_route = vfs_inspect_mount_route(cfg.mount_table, chosen_uri)
        if not cfg.is_kernel and (
            chosen_uri.scheme in _KERNEL_ONLY_SCHEMES or chosen_route.terminal_uri.scheme in _KERNEL_ONLY_SCHEMES
        ):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{cfg.module_id}' is not permitted to resolve protected URI '{chosen_uri}'.",
            )
        _assert_scheme_read_allowed(cfg, chosen_uri, chosen_route)
        return chosen_uri


class KernelVfs(ScopedVfs):
    """Privileged kernel VFS facade for installer, config, gitignore, and lock management."""

    __slots__ = ()

    def write_bytes_through_readonly(self, uri: SemanticUri | str, data: bytes) -> None:
        self._write_bytes_impl(uri, data, force_tunnel=True)

    def write_text_through_readonly(
        self,
        uri: SemanticUri | str,
        text: str,
        *,
        encoding: str = "utf-8",
    ) -> None:
        require_pure_str(text, "text")
        require_pure_str(encoding, "encoding", non_empty=True)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.write_bytes_through_readonly(uri, normalized.encode(encoding))


def _mint_scoped_vfs(cfg: _VfsScopeConfig) -> ScopedVfs:
    inst = ScopedVfs()
    object.__setattr__(inst, "_scope_cfg", cfg)
    return inst


def _mint_kernel_vfs(cfg: _VfsScopeConfig) -> KernelVfs:
    inst = KernelVfs()
    object.__setattr__(inst, "_scope_cfg", cfg)
    return inst


class VfsHub:
    """Workspace-level VFS coordination root minting isolated ScopedVfs and KernelVfs facades."""

    def __init__(
        self,
        mount_table: UriMountTable,
        *,
        readonly_policy: Optional[ReadonlyPolicy] = None,
        echo_guard: Optional[VfsEchoGuard] = None,
        access_policy: Optional[AccessPolicy] = None,
    ) -> None:
        if not isinstance(mount_table, UriMountTable):
            raise ValueError(f"VfsHub requires UriMountTable, got {mount_table!r}")
        if readonly_policy is not None and not isinstance(readonly_policy, ReadonlyPolicy):
            raise ValueError(f"VfsHub readonly_policy must be ReadonlyPolicy or None, got {readonly_policy!r}")
        if echo_guard is not None and not isinstance(echo_guard, VfsEchoGuard):
            raise ValueError(f"VfsHub echo_guard must be VfsEchoGuard or None, got {echo_guard!r}")
        if access_policy is not None and not isinstance(access_policy, AccessPolicy):
            raise ValueError(f"VfsHub access_policy must be AccessPolicy or None, got {access_policy!r}")
        self._mount_table = mount_table
        self._readonly_policy = readonly_policy if readonly_policy is not None else ReadonlyPolicy()
        self._echo_guard = echo_guard if echo_guard is not None else VfsEchoGuard()
        self._access_policy = access_policy if access_policy is not None else AccessPolicy()

    @property
    def mount_table(self) -> UriMountTable:
        return self._mount_table

    @property
    def readonly_policy(self) -> ReadonlyPolicy:
        return self._readonly_policy

    @property
    def echo_guard(self) -> VfsEchoGuard:
        return self._echo_guard

    def for_module(self, module_id: ModuleId) -> ScopedVfs:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"VfsHub.for_module requires ModuleId, got {module_id!r}")
        return _mint_scoped_vfs(
            _VfsScopeConfig(
                mount_table=self._mount_table,
                readonly_policy=self._readonly_policy,
                echo_guard=self._echo_guard,
                access_policy=self._access_policy,
                module_id=module_id,
                is_kernel=False,
            )
        )

    def for_kernel(self) -> KernelVfs:
        return _mint_kernel_vfs(
            _VfsScopeConfig(
                mount_table=self._mount_table,
                readonly_policy=self._readonly_policy,
                echo_guard=self._echo_guard,
                access_policy=self._access_policy,
                module_id=_KERNEL_MODULE_ID,
                is_kernel=True,
            )
        )
