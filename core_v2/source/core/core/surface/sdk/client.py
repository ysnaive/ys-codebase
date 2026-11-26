"""High-level Surface SDK Client wrapping RuntimeDispatcher and PersistentRpcSession."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import threading
from typing import Callable, ClassVar, Final, Mapping, Optional, Sequence, TypeVar, cast, overload
import uuid

from core.execution.event import normalize_payload_filter
from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession
from core.execution.runtime import (
    BoundTask,
    CallPropagationContext,
    CORE_MODULE_ID,
    CallerSurface,
    CliBindingSpec,
    ClientRoutingPolicy,
    ConcurrencyMode,
    ConfigViewPort,
    DEFAULT_CACHE_DIRNAME,
    DispatchMode,
    DispatcherHostOptions,
    Empty,
    InvokeRequest,
    MODULES_DIRNAME,
    ModuleDescriptor,
    ModuleProviderPort,
    ModuleRuntimeServices,
    PeriodicScheduleSpec,
    RuntimeDispatcher,
    SecurityTier,
    SelfMutationScope,
    SubscriptionRouteSpec,
    TaskContext,
    TaskExposure,
    TaskOutcome,
    TaskRef,
    TaskRouteSpec,
    YscbModule,
    build_default_module_services,
    build_workspace_module_services_factory,
    resolve_active_call_tree_id,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    EnvHash,
    ErrorCode,
    ErrorDetail,
    EventId,
    FlightLogConfig,
    FlightLogRouter,
    HostPath,
    IS_WINDOWS,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    ModuleId,
    ProgressEvent,
    SemVer4,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    TaskId,
    VersionConstraint,
    YscbError,
    clone_strict_json_object,
    is_disallowed_reparse_tag,
    is_public_env_truthy,
    read_flight_log_env,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    strict_parse_json_object,
    validate_relative_segment,
)
from core.metadata.config import ConfigStore, ModuleManifest
from core.metadata.contributes import (
    discover_installed_manifests_map,
    resolve_sdk_core_post_call_hook,
    resolve_sdk_core_session_factory,
)
from core.surface.sdk.declarative import InMemoryModule, Module

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")

_MAX_INDEX_FILE_BYTES: Final[int] = 8 * 1024 * 1024
_MAX_ENV_META_BYTES: Final[int] = 65536
_POSIX_ALLOWED_ROOT_LINKS: Final[frozenset[str]] = frozenset({"tmp", "var", "etc", "run"})
_PEP503_SEP_RE: Final[re.Pattern[str]] = re.compile(r"[-_.]+")
_PEP503_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_PEP440_CLAUSE_OP_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"^(===|~=|==|!=|<=|>=|<|>)\s+")
_PEP440_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:===|~=|==|!=|<=|>=|<|>)[0-9A-Za-z][0-9A-Za-z.*+!_-]*$"
)
_ENV_GROUP_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")
_NOFOLLOW_OPEN_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW | os.O_NONBLOCK)
)


def _is_symlink_or_reparse_path(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if IS_WINDOWS:
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and is_disallowed_reparse_tag(
            st.st_reparse_tag
        )
    return False


def _is_allowed_posix_root_link(cur: Path) -> bool:
    if IS_WINDOWS or cur.parent != Path("/") or cur.name not in _POSIX_ALLOWED_ROOT_LINKS:
        return False
    try:
        lst = os.lstat(cur)
        rst = os.stat(cur)
    except OSError:
        return False
    return lst.st_uid == 0 and stat.S_ISDIR(rst.st_mode)


def _has_forbidden_symlink_in_path(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return True
    cur = Path(parts[0])
    for seg in parts[1:]:
        cur = cur / seg
        if _is_symlink_or_reparse_path(cur) and not _is_allowed_posix_root_link(cur):
            return True
    return False


def _read_nofollow_bounded_bytes(target_file: Path, max_bytes: int) -> Optional[bytes]:
    if _has_forbidden_symlink_in_path(target_file) or _is_symlink_or_reparse_path(target_file):
        return None
    try:
        lst = os.lstat(target_file)
    except OSError:
        return None
    if not stat.S_ISREG(lst.st_mode) or lst.st_size > max_bytes:
        return None
    try:
        fd = os.open(str(target_file), _NOFOLLOW_OPEN_FLAGS)
    except OSError:
        return None
    try:
        os.set_inheritable(fd, False)
        if IS_WINDOWS and (_has_forbidden_symlink_in_path(target_file) or _is_symlink_or_reparse_path(target_file)):
            return None
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_size > max_bytes:
            return None
        if (lst.st_ino and fst.st_ino and lst.st_ino != fst.st_ino) or (
            lst.st_dev and fst.st_dev and lst.st_dev != fst.st_dev
        ):
            return None
        if not IS_WINDOWS:
            os.set_blocking(fd, True)
        chunks: list[bytes] = []
        total = 0
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            total += len(buf)
            if total > max_bytes:
                return None
            chunks.append(buf)
        if IS_WINDOWS and (_has_forbidden_symlink_in_path(target_file) or _is_symlink_or_reparse_path(target_file)):
            return None
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _parse_str_tuple_field(
    raw_val: object,
    label: str,
    *,
    non_empty: bool,
    forbid_ws_or_ctrl: bool = False,
) -> tuple[str, ...]:
    if raw_val is None:
        return ()
    if not isinstance(raw_val, list):
        raise ValueError(f"Expected list for {label}")
    out: list[str] = []
    for item in raw_val:
        s = require_pure_str(item, label, non_empty=non_empty)
        if forbid_ws_or_ctrl and any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in s):
            raise ValueError(f"Illegal whitespace or control character in {label}: {s!r}")
        out.append(s)
    return tuple(out)


def _parse_subscription_specs(raw_subs: object) -> tuple[SubscriptionRouteSpec, ...]:
    if raw_subs is None:
        return ()
    if not isinstance(raw_subs, list):
        raise ValueError("Expected list for subscriptions")
    out: list[SubscriptionRouteSpec] = []
    for sub_item in raw_subs:
        if not isinstance(sub_item, Mapping):
            raise ValueError("Expected object in subscriptions")
        eid = EventId(require_pure_str(sub_item.get("event_id"), "subscription.event_id", non_empty=True))
        raw_f = sub_item.get("payload_filter")
        norm_f: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None
        if raw_f is not None:
            if not isinstance(raw_f, Mapping):
                raise ValueError("Expected mapping for payload_filter")
            parsed_f: dict[str, tuple[JsonPrimitive, ...]] = {}
            for fk, fv in raw_f.items():
                key_s = require_pure_str(fk, "payload_filter key", non_empty=True)
                if not isinstance(fv, list):
                    raise ValueError("Expected list in payload_filter")
                prims: list[JsonPrimitive] = []
                for elem in fv:
                    if elem is None or isinstance(elem, (bool, int, float, str)):
                        prims.append(elem)
                    else:
                        raise ValueError("Non-primitive in payload_filter")
                parsed_f[key_s] = tuple(prims)
            norm_f = normalize_payload_filter(parsed_f)
        out.append(SubscriptionRouteSpec(event_id=eid, payload_filter=norm_f))
    return tuple(out)


def _parse_periodic_spec(raw_periodic: object) -> Optional[PeriodicScheduleSpec]:
    if raw_periodic is None:
        return None
    if not isinstance(raw_periodic, Mapping):
        raise ValueError("Expected mapping for periodic")
    raw_iv = raw_periodic.get("default_interval_sec")
    if isinstance(raw_iv, bool) or not isinstance(raw_iv, (int, float)):
        raise ValueError("Invalid default_interval_sec")
    raw_ik = raw_periodic.get("interval_config_key")
    raw_ek = raw_periodic.get("enabled_config_key")
    return PeriodicScheduleSpec(
        default_interval_sec=float(raw_iv),
        interval_config_key=require_pure_str(raw_ik, "interval_config_key", non_empty=True) if raw_ik is not None else None,
        enabled_config_key=require_pure_str(raw_ek, "enabled_config_key", non_empty=True) if raw_ek is not None else None,
    )


def _parse_single_indexed_route_spec(item: Mapping[str, object]) -> TaskRouteSpec:
    tid = TaskId(require_pure_str(item.get("task_id"), "task_id", non_empty=True))
    exposure = TaskExposure(require_pure_str(item.get("exposure"), "exposure", non_empty=True))
    security_tier = SecurityTier(require_pure_str(item.get("security_tier"), "security_tier", non_empty=True))
    dispatch_mode = DispatchMode(require_pure_str(item.get("dispatch_mode"), "dispatch_mode", non_empty=True))
    for list_key in ("args", "options"):
        raw_seq = item.get(list_key)
        if raw_seq is not None and (
            not isinstance(raw_seq, list) or not all(isinstance(elem, Mapping) for elem in raw_seq)
        ):
            raise ValueError(f"Expected list of objects for {list_key}")
    mutation_scope = SelfMutationScope(
        require_pure_str(item.get("mutation_scope", "none"), "mutation_scope", non_empty=True)
    )
    concurrency_mode = ConcurrencyMode(
        require_pure_str(item.get("concurrency_mode", "parallel"), "concurrency_mode", non_empty=True)
    )
    interactive_tty = require_pure_bool(item.get("interactive_tty", False), "interactive_tty")
    cmd_path = _parse_str_tuple_field(
        item.get("command_path", []),
        "command_path",
        non_empty=True,
        forbid_ws_or_ctrl=True,
    )
    aliases = _parse_str_tuple_field(
        item.get("aliases", []),
        "aliases",
        non_empty=True,
        forbid_ws_or_ctrl=True,
    )
    summary = require_pure_str(item.get("summary", ""), "summary")
    usage_pros = _parse_str_tuple_field(item.get("usage_pros", []), "usage_pros", non_empty=False)
    usage_cons = _parse_str_tuple_field(item.get("usage_cons", []), "usage_cons", non_empty=False)
    cli_spec: Optional[CliBindingSpec] = None
    if exposure == TaskExposure.CLI_AND_SDK:
        if not cmd_path:
            if tid.module_id == CORE_MODULE_ID or aliases:
                raise ValueError("Invalid empty command_path on core or aliased CLI task")
            eff_cp = (tid.module_id.value,)
        else:
            eff_cp = cmd_path
        cli_spec = CliBindingSpec(
            command_path=eff_cp,
            summary=summary or f"Execute {tid}",
            aliases=aliases,
            usage_pros=usage_pros,
            usage_cons=usage_cons,
        )
    raw_rk = item.get("resource_key")
    resource_key = require_pure_str(raw_rk, "resource_key", non_empty=True) if raw_rk is not None else None
    raw_tmo = item.get("timeout_ms")
    timeout_ms = require_pure_int(raw_tmo, "timeout_ms", min_val=1) if raw_tmo is not None else None
    return TaskRouteSpec(
        task_id=tid,
        exposure=exposure,
        cli=cli_spec,
        dispatch_mode=dispatch_mode,
        mutation_scope=mutation_scope,
        interactive_tty=interactive_tty,
        security_tier=security_tier,
        resource_key=resource_key,
        concurrency_mode=concurrency_mode,
        timeout_ms=timeout_ms,
        subscriptions=_parse_subscription_specs(item.get("subscriptions")),
        periodic=_parse_periodic_spec(item.get("periodic")),
    )


def _parse_indexed_route_specs(idx_file: Path, mod_id: ModuleId) -> tuple[TaskRouteSpec, ...]:
    raw_bytes = _read_nofollow_bounded_bytes(idx_file, _MAX_INDEX_FILE_BYTES)
    if raw_bytes is None:
        return ()
    try:
        doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ()
    ver = doc.get("schema_version")
    if type(ver) is not int or ver != 2 or doc.get("module_id") != mod_id.value:
        return ()
    try:
        _ = require_pure_str(doc.get("description", ""), "description")
        _ = _parse_str_tuple_field(
            doc.get("module_aliases", []),
            "module_aliases",
            non_empty=True,
            forbid_ws_or_ctrl=True,
        )
    except ValueError:
        return ()
    raw_tasks = doc.get("tasks")
    if not isinstance(raw_tasks, list):
        return ()
    routes: list[TaskRouteSpec] = []
    seen_tids: set[TaskId] = set()
    seen_cli_paths: set[tuple[str, ...]] = set()
    try:
        for item in raw_tasks:
            if not isinstance(item, Mapping):
                return ()
            spec = _parse_single_indexed_route_spec(item)
            if spec.task_id.module_id != mod_id or spec.task_id in seen_tids:
                return ()
            if spec.cli is not None:
                if spec.cli.command_path in seen_cli_paths:
                    return ()
                seen_cli_paths.add(spec.cli.command_path)
            seen_tids.add(spec.task_id)
            routes.append(spec)
    except (TypeError, ValueError, YscbError):
        return ()
    return tuple(routes)


def _normalize_pep503_name(raw_token: str) -> str:
    require_pure_str(raw_token, "pip package", non_empty=True)
    collapsed = _PEP503_SEP_RE.sub("-", raw_token.strip()).lower()
    if _PEP503_NAME_RE.fullmatch(collapsed) is None:
        raise ValueError(f"Invalid pip package token: {raw_token!r}")
    return collapsed


def _normalize_pip_pkg_key(raw_key: str) -> str:
    require_pure_str(raw_key, "pip package key", non_empty=True)
    cleaned = raw_key.strip()
    if "[" not in cleaned and "]" not in cleaned:
        return _normalize_pep503_name(cleaned)
    if not cleaned.endswith("]") or cleaned.count("[") != 1 or cleaned.count("]") != 1:
        raise ValueError(f"Malformed extras in pip package name: {raw_key!r}")
    base_part, extras_part = cleaned[:-1].split("[", 1)
    norm_base = _normalize_pep503_name(base_part)
    raw_extras = [e.strip() for e in extras_part.split(",")]
    if not raw_extras or any(not e for e in raw_extras):
        raise ValueError(f"Empty extra in pip package name: {raw_key!r}")
    norm_extras = sorted({_normalize_pep503_name(e) for e in raw_extras})
    return f"{norm_base}[{','.join(norm_extras)}]"


def _parse_pip_clauses(raw_constraint: str) -> tuple[str, ...]:
    require_pure_str(raw_constraint, "pip constraint")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_constraint):
        raise ValueError("Control characters forbidden in pip constraint")
    trimmed = raw_constraint.strip()
    if not trimmed or trimmed == "*":
        return ()
    parts = [seg.strip() for seg in trimmed.split(",")]
    if not parts or any(not seg for seg in parts):
        raise ValueError("Malformed pip constraint clause")
    out: set[str] = set()
    for seg in parts:
        compact = _PEP440_CLAUSE_OP_SPACE_RE.sub(r"\1", seg)
        if compact in ("*", "==*"):
            continue
        if _PEP440_CLAUSE_RE.fullmatch(compact) is None:
            raise ValueError(f"Invalid PEP 440 clause: {seg!r}")
        out.add(compact)
    return tuple(sorted(out))


def _build_unready_tier1_sentinel(workspace_root: HostPath, mod_id: ModuleId) -> HostPath:
    stem = f".yscb_unready_tier1_{mod_id.value}"
    cand_dir = workspace_root.path / stem
    if os.path.lexists(cand_dir):
        cand_dir = workspace_root.path / f"{stem}_{uuid.uuid4().hex[:8]}"
    rel_py = ("Scripts", "python.exe") if IS_WINDOWS else ("bin", "python")
    return HostPath(cand_dir.joinpath(*rel_py))


def _pyvenv_cfg_enforces_isolated(raw_cfg_bytes: bytes) -> bool:
    found = False
    for line in raw_cfg_bytes.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        if k.strip().lower() == "include-system-site-packages":
            if v.strip().lower() != "false":
                return False
            found = True
    return found


@dataclasses.dataclass(frozen=True, slots=True)
class _ExpectedEnvIdentity:
    group: str
    py_tag: str
    platform_tag: str
    canonical_specs: list[str]
    digest16: str

    @property
    def dirname(self) -> str:
        return f"{self.group}_{self.py_tag}_{self.digest16}"


def _resolve_verified_venv_python(
    workspace_root: HostPath,
    venv_root: Path,
    mod_id: ModuleId,
    expected: _ExpectedEnvIdentity,
) -> HostPath:
    if _is_symlink_or_reparse_path(venv_root) or not venv_root.is_dir():
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    env_dir = venv_root / expected.dirname
    if _is_symlink_or_reparse_path(env_dir) or not env_dir.is_dir():
        return _build_unready_tier1_sentinel(workspace_root, mod_id)

    cfg_bytes = _read_nofollow_bounded_bytes(env_dir / "pyvenv.cfg", _MAX_ENV_META_BYTES)
    if cfg_bytes is None or not _pyvenv_cfg_enforces_isolated(cfg_bytes):
        return _build_unready_tier1_sentinel(workspace_root, mod_id)

    meta_bytes = _read_nofollow_bounded_bytes(env_dir / ".yscb_env_meta.json", _MAX_ENV_META_BYTES)
    if meta_bytes is None:
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    try:
        meta_doc = strict_parse_json_object(meta_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    if (
        meta_doc.get("complete") is not True
        or meta_doc.get("group") != expected.group
        or meta_doc.get("env_hash") != expected.digest16
        or meta_doc.get("py_tag") != expected.py_tag
        or meta_doc.get("platform_tag") != expected.platform_tag
        or meta_doc.get("pip_specs") != expected.canonical_specs
    ):
        return _build_unready_tier1_sentinel(workspace_root, mod_id)

    bin_sub = env_dir / ("Scripts" if IS_WINDOWS else "bin")
    if _is_symlink_or_reparse_path(bin_sub) or not bin_sub.is_dir():
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    exe_cand = bin_sub / ("python.exe" if IS_WINDOWS else "python")
    if not os.path.lexists(exe_cand) or not os.path.isfile(exe_cand):
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    if not IS_WINDOWS and not os.access(exe_cand, os.X_OK):
        return _build_unready_tier1_sentinel(workspace_root, mod_id)
    try:
        return HostPath(exe_cand)
    except ValueError:
        return _build_unready_tier1_sentinel(workspace_root, mod_id)


def _resolve_tier1_venv_pythons(
    workspace_root: HostPath,
    manifests: Mapping[ModuleId, ModuleManifest],
) -> dict[ModuleId, HostPath]:
    venv_root = workspace_root.path / ".venv"
    py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    machine_lower = platform.machine().lower()
    platform_tag = f"{sys.platform}_{machine_lower}"
    members_by_group: dict[str, list[ModuleId]] = {}
    clauses_by_group: dict[str, dict[str, set[str]]] = {}
    resolved_py: dict[ModuleId, HostPath] = {}

    for mf in manifests.values():
        if not mf.is_tier1:
            continue
        try:
            raw_src = mf.venv_group if mf.venv_group else mf.id.value
            clean_group = validate_relative_segment(raw_src, label="venv group")
            if _ENV_GROUP_NAME_RE.fullmatch(clean_group) is None:
                raise ValueError("Invalid venv group token")
            pkg_bucket: dict[str, set[str]] = {}
            for raw_pkg, raw_ver in mf.pip_dependencies.items():
                norm_pkg = _normalize_pip_pkg_key(raw_pkg)
                pkg_bucket.setdefault(norm_pkg, set()).update(_parse_pip_clauses(raw_ver))
            if not pkg_bucket:
                raise ValueError("Empty Tier 1 dependencies")
        except ValueError:
            resolved_py[mf.id] = _build_unready_tier1_sentinel(workspace_root, mf.id)
            continue

        members_by_group.setdefault(clean_group, []).append(mf.id)
        grp_map = clauses_by_group.setdefault(clean_group, {})
        for pkg, cls_set in pkg_bucket.items():
            grp_map.setdefault(pkg, set()).update(cls_set)

    for clean_group, mod_ids in members_by_group.items():
        grp_map = clauses_by_group[clean_group]
        canonical_specs = [
            f"{pkg}{','.join(sorted(grp_map[pkg]))}" if grp_map[pkg] else pkg
            for pkg in sorted(grp_map)
        ]
        hash_payload = {
            "canonical_pip_specs": canonical_specs,
            "machine": machine_lower,
            "platform": sys.platform,
            "py_tag": py_tag,
        }
        canonical_json = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest16 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
        expected_id = _ExpectedEnvIdentity(
            group=clean_group,
            py_tag=py_tag,
            platform_tag=platform_tag,
            canonical_specs=canonical_specs,
            digest16=digest16,
        )
        for mid in mod_ids:
            resolved_py[mid] = _resolve_verified_venv_python(workspace_root, venv_root, mid, expected_id)
    return resolved_py


def _discover_initialized_host_context(
    workspace_root: HostPath,
) -> tuple[Optional[HostPath], Optional[ConfigStore]]:
    ws_path = workspace_root.path
    if _has_forbidden_symlink_in_path(ws_path) or _is_symlink_or_reparse_path(ws_path):
        return (None, None)
    cur_anc = ws_path
    for _depth in range(64):
        if _has_forbidden_symlink_in_path(cur_anc) or _is_symlink_or_reparse_path(cur_anc):
            break
        cfg_file = cur_anc / "yscb.config.json"
        if cfg_file.is_file() and not _is_symlink_or_reparse_path(cfg_file):
            try:
                anc_hp = HostPath(cur_anc)
                probe_store = ConfigStore(host_dir=anc_hp, yscb_root=workspace_root)
                host_cfg = probe_store.load_host_config()
                root_cand = Path(host_cfg.yscb_root.strip())
                if (root_cand.drive or root_cand.anchor) and not root_cand.is_absolute():
                    raise ValueError("Half-qualified yscb_root")
                raw_root_cand = root_cand if root_cand.is_absolute() else (cur_anc / root_cand)
                if _has_forbidden_symlink_in_path(raw_root_cand) or _is_symlink_or_reparse_path(raw_root_cand):
                    raise ValueError("Symlinked yscb_root")
                if HostPath(raw_root_cand) == workspace_root:
                    return (anc_hp, probe_store)
            except (OSError, ValueError, YscbError):
                pass
        if cur_anc.parent == cur_anc:
            break
        cur_anc = cur_anc.parent
    return (None, None)


class _SdkWorkspaceModuleProvider(ModuleProviderPort):
    """Lightweight manifest and tasks.index.json ModuleProviderPort enabling YscbClient workspace routing."""

    def __init__(self, workspace_root: HostPath, excluded_ids: frozenset[ModuleId]) -> None:
        self._workspace_root = workspace_root
        self._excluded = excluded_ids
        self._lock = threading.RLock()
        self._cached: Optional[tuple[ModuleDescriptor, ...]] = None

    def _scan_disk_descriptors(self) -> tuple[ModuleDescriptor, ...]:
        ws_path = self._workspace_root.path
        if _has_forbidden_symlink_in_path(ws_path) or _is_symlink_or_reparse_path(ws_path):
            return ()
        mods_root = ws_path / MODULES_DIRNAME
        if _is_symlink_or_reparse_path(mods_root) or not mods_root.is_dir():
            return ()
        manifests = discover_installed_manifests_map(self._workspace_root)
        tier1_pythons = _resolve_tier1_venv_pythons(self._workspace_root, manifests)
        out: list[ModuleDescriptor] = []
        for mod_id in sorted(manifests.keys(), key=lambda m: m.value):
            if mod_id == CORE_MODULE_ID or mod_id in self._excluded:
                continue
            mf = manifests[mod_id]
            mod_dir_cand = mods_root / mod_id.value
            if _is_symlink_or_reparse_path(mod_dir_cand) or not mod_dir_cand.is_dir():
                continue
            mod_dir = HostPath(mod_dir_cand)
            declared = _parse_indexed_route_specs(mod_dir.path / "tasks.index.json", mod_id)
            out.append(
                ModuleDescriptor(
                    module_id=mod_id,
                    module_dir=mod_dir,
                    entry_file=mf.entry,
                    venv_group=mf.venv_group,
                    venv_python=tier1_pythons.get(mod_id),
                    eager_warmup=mf.eager_warmup,
                    declared_tasks=declared,
                )
            )
        return tuple(out)

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        with self._lock:
            if self._cached is None:
                self._cached = self._scan_disk_descriptors()
            return self._cached

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        for desc in self.list_modules():
            if desc.module_id == module_id:
                return desc
        return None

    def reload(self) -> None:
        with self._lock:
            self._cached = None


def _coerce_yscb_modules(modules: Sequence[Module | InMemoryModule]) -> tuple[YscbModule, ...]:
    if isinstance(modules, (str, bytes, bytearray, memoryview)) or not isinstance(modules, Sequence):
        raise TypeError(f"modules must be a Sequence of Module or InMemoryModule, got {type(modules).__name__}")
    converted: list[YscbModule] = []
    for item in modules:
        if isinstance(item, (Module, InMemoryModule)):
            converted.append(item.to_yscb_module())
        else:
            raise TypeError(f"Expected Module or InMemoryModule instance, got {type(item).__name__}")
    return tuple(converted)


_CLIENT_SCALAR_VO_TYPES: tuple[type[object], ...] = (
    ModuleId,
    TaskId,
    EventId,
    HostPath,
    SemVer4,
    VersionConstraint,
    SemanticUri,
    SpaceId,
    SpacePath,
    SnapshotGen,
    EnvHash,
)


class _UnboundCoreRouteStubTask(BoundTask):
    def __init__(self, spec: TaskRouteSpec) -> None:
        self._spec = spec

    @property
    def task_id(self) -> TaskId:
        return self._spec.task_id

    @property
    def route_spec(self) -> TaskRouteSpec:
        return self._spec

    @property
    def interactive_tty(self) -> bool:
        return self._spec.interactive_tty

    def compute_normalized_equivalence(self, raw_input: JsonObject) -> str:
        return f"{self._spec.task_id}:norm:{DataclassCodec.canonical_hash(raw_input)}"

    def map_subscription_batch(
        self,
        event_id: EventId,
        raw_payloads: Sequence[JsonObject],
    ) -> tuple[bool, JsonObject]:
        _ = (self, event_id, raw_payloads)
        return (True, {})

    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue:
        _ = (raw_input, ctx)
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            "Cold execution of built-in 'core.*' tasks requires importing 'core.surface.bootstrap' first.",
            remediation="Import 'core.surface.bootstrap' before instantiating YscbClient, or start the workspace daemon.",
            source_task=str(self._spec.task_id),
        )


class _UnboundCoreRouteStubModule(YscbModule):
    def __init__(self, specs: Sequence[TaskRouteSpec]) -> None:
        self._bound = tuple(_UnboundCoreRouteStubTask(s) for s in specs)

    @property
    def module_id(self) -> ModuleId:
        return CORE_MODULE_ID

    def tasks(self) -> Sequence[BoundTask]:
        return self._bound


def _load_disk_core_route_specs(workspace_root: HostPath) -> tuple[TaskRouteSpec, ...]:
    ws_path = workspace_root.path
    if _has_forbidden_symlink_in_path(ws_path) or not ws_path.is_dir():
        return ()
    core_idx = ws_path / MODULES_DIRNAME / CORE_MODULE_ID.value / "tasks.index.json"
    return _parse_indexed_route_specs(core_idx, CORE_MODULE_ID)


def _encode_call_input(req: object) -> JsonObject:
    if req is None:
        return {}
    if isinstance(req, Mapping):
        return clone_strict_json_object(req)
    if isinstance(req, _CLIENT_SCALAR_VO_TYPES):
        raise YscbError(
            ErrorCode.CODEC_VALIDATION_FAILED,
            f"YscbClient.call req must encode as a JSON object (None, Mapping, or request @dataclass DTO), got scalar value object {type(req).__name__}",
        )
    if dataclasses.is_dataclass(req) and not isinstance(req, type):
        return DataclassCodec.encode_object(req)
    raise YscbError(
        ErrorCode.CODEC_VALIDATION_FAILED,
        f"YscbClient.call req must be None, Mapping, or dataclass instance, got {type(req).__name__}",
    )


class _ConnectContext:
    """Thread-local staging flag so YscbClient.connect() opts into RPC cleanly."""

    _STATE: ClassVar[Optional[threading.local]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _ensure_local(cls) -> threading.local:
        if cls._STATE is None:
            with cls._INIT_LOCK:
                if cls._STATE is None:
                    cls._STATE = threading.local()
        return cls._STATE

    @classmethod
    def begin_connect(cls) -> bool:
        tls = cls._ensure_local()
        try:
            prev = bool(tls.use_rpc)
        except AttributeError:
            prev = False
        tls.use_rpc = True
        return prev

    @classmethod
    def end_connect(cls, prev: bool) -> None:
        cls._ensure_local().use_rpc = prev

    @classmethod
    def is_connect_active(cls) -> bool:
        tls = cls._ensure_local()
        try:
            return bool(tls.use_rpc)
        except AttributeError:
            return False


_COLD_CORE_CONFIG_SPACE_TASKS: Final[frozenset[str]] = frozenset(
    {
        "core.config.set",
        "core.config.unset",
        "core.config.reload",
        "core.config.on_changed",
        "core.space.set_dynamic",
        "core.space.clear_dynamic",
    }
)


def _feed_stat_token(update_fn: Callable[[bytes], object], tag: str, target: Path) -> None:
    if _is_symlink_or_reparse_path(target):
        return
    try:
        st = os.lstat(target)
    except OSError:
        return
    if stat.S_ISREG(st.st_mode):
        update_fn(f"{tag}:{st.st_mtime_ns}:{st.st_size}\n".encode("utf-8"))


def _feed_json_tree_token(update_fn: Callable[[bytes], object], tag: str, root_dir: Path) -> None:
    if _is_symlink_or_reparse_path(root_dir) or not root_dir.is_dir():
        return
    stack: list[tuple[str, Path]] = [(tag, root_dir)]
    while stack:
        cur_tag, cur_p = stack.pop()
        try:
            with os.scandir(cur_p) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for ent in entries:
            if ent.name.startswith(".tmp") or ent.is_symlink():
                continue
            ent_p = cur_p / ent.name
            if _is_symlink_or_reparse_path(ent_p):
                continue
            try:
                if ent.is_dir(follow_symlinks=False):
                    stack.append((f"{cur_tag}/{ent.name}", ent_p))
                elif ent.name.endswith(".json") and ent.is_file(follow_symlinks=False):
                    fst = ent.stat(follow_symlinks=False)
                    update_fn(f"{cur_tag}/{ent.name}:{fst.st_mtime_ns}:{fst.st_size}\n".encode("utf-8"))
            except OSError:
                continue


def _compute_sdk_disk_tokens(
    workspace_root: HostPath,
    bound_host_dir: Optional[HostPath],
) -> tuple[str, str]:
    ws_p = workspace_root.path
    if _has_forbidden_symlink_in_path(ws_p) or _is_symlink_or_reparse_path(ws_p):
        return ("", "")
    mods_h = hashlib.sha256()
    cfg_h = hashlib.sha256()
    cand_hosts: list[Path] = []
    if bound_host_dir is not None:
        cand_hosts.append(bound_host_dir.path)
    else:
        disc_host, _disc_store = _discover_initialized_host_context(workspace_root)
        if disc_host is not None:
            cand_hosts.append(disc_host.path)
        else:
            anc = ws_p
            for _ in range(64):
                if _has_forbidden_symlink_in_path(anc) or _is_symlink_or_reparse_path(anc):
                    break
                cand_hosts.append(anc)
                if anc.parent == anc:
                    break
                anc = anc.parent
    for idx_h, h_dir in enumerate(cand_hosts):
        _feed_stat_token(mods_h.update, f"h{idx_h}:cfg", h_dir / "yscb.config.json")
        _feed_stat_token(cfg_h.update, f"h{idx_h}:cfg", h_dir / "yscb.config.json")
        _feed_stat_token(cfg_h.update, f"h{idx_h}:lcfg", h_dir / "yscb.config.local.json")
    mods_dir = ws_p / MODULES_DIRNAME
    if not _is_symlink_or_reparse_path(mods_dir) and mods_dir.is_dir():
        try:
            with os.scandir(mods_dir) as it:
                mod_ents = sorted(it, key=lambda e: e.name)
        except OSError:
            mod_ents = []
        for me in mod_ents:
            if me.name.startswith(".") or me.is_symlink():
                continue
            mp = mods_dir / me.name
            if _is_symlink_or_reparse_path(mp):
                continue
            _feed_stat_token(mods_h.update, f"mf:{me.name}", mp / "manifest.json")
            _feed_stat_token(mods_h.update, f"ti:{me.name}", mp / "tasks.index.json")
            _feed_json_tree_token(cfg_h.update, f"contrib:{me.name}", mp / "contributes")
    venvs_dir = ws_p / ".venv"
    if not _is_symlink_or_reparse_path(venvs_dir) and venvs_dir.is_dir():
        try:
            with os.scandir(venvs_dir) as vit:
                venv_ents = sorted(vit, key=lambda e: e.name)
        except OSError:
            venv_ents = []
        for ve in venv_ents:
            if ve.name.startswith(".") or ve.is_symlink():
                continue
            vp = venvs_dir / ve.name
            if _is_symlink_or_reparse_path(vp):
                continue
            _feed_stat_token(mods_h.update, f"vm:{ve.name}", vp / ".yscb_env_meta.json")
            _feed_stat_token(mods_h.update, f"vc:{ve.name}", vp / "pyvenv.cfg")
    _feed_json_tree_token(cfg_h.update, "cfg", ws_p / "config")
    _feed_json_tree_token(cfg_h.update, "lcfg", ws_p / ".config.local")
    sp_base = ws_p / ".storage.local" / "core" / "space"
    if not _is_symlink_or_reparse_path(sp_base):
        for db_name in ("state.db", "state.db-wal", "state.db-shm"):
            _feed_stat_token(cfg_h.update, f"sp:{db_name}", sp_base / db_name)
    return (mods_h.hexdigest()[:24], cfg_h.hexdigest()[:24])


class _LazySdkWorkspaceContext(ConfigViewPort):
    """Lazy workspace service and configuration bridge adapting seamlessly after deferred initialization."""

    def __init__(self, workspace_root: HostPath) -> None:
        self._workspace_root = workspace_root
        self._lock = threading.RLock()
        self._host_dir: Optional[HostPath] = None
        self._config_store: Optional[ConfigStore] = None
        self._svc_factory: Optional[Callable[[ModuleId], ModuleRuntimeServices]] = None
        _ = self._ensure_bound_locked()

    def _ensure_bound_locked(self) -> Optional[ConfigStore]:
        if self._host_dir is not None and not (self._host_dir.path / "yscb.config.json").is_file():
            self._host_dir = None
            self._config_store = None
            self._svc_factory = None
        if self._config_store is None:
            disc_host, disc_cfg = _discover_initialized_host_context(self._workspace_root)
            if disc_host is not None and disc_cfg is not None:
                self._host_dir = disc_host
                self._config_store = disc_cfg
                self._svc_factory = build_workspace_module_services_factory(
                    disc_host,
                    self._workspace_root,
                    config_store=disc_cfg,
                )
        return self._config_store

    @property
    def host_dir(self) -> Optional[HostPath]:
        with self._lock:
            _ = self._ensure_bound_locked()
            return self._host_dir

    def get_module_value(self, module_id: ModuleId, dotted_key: str, default: JsonValue = None) -> JsonValue:
        with self._lock:
            cfg = self._ensure_bound_locked()
        return default if cfg is None else cfg.get_module_value(module_id, dotted_key, default=default)

    def fingerprint(self) -> str:
        with self._lock:
            cfg = self._ensure_bound_locked()
        return "" if cfg is None else cfg.fingerprint()

    def reload(self) -> None:
        with self._lock:
            cfg = self._ensure_bound_locked()
        if cfg is not None:
            cfg.reload()

    def resolve_module_services(self, module_id: ModuleId) -> ModuleRuntimeServices:
        with self._lock:
            _ = self._ensure_bound_locked()
            fac = self._svc_factory
        if fac is not None:
            return fac(module_id)
        return build_default_module_services(self._workspace_root, module_id)


_TRUTHY_SDK_ENV_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def _build_sdk_flight_log_config(config_view: ConfigViewPort) -> FlightLogConfig:
    try:
        raw_obs = config_view.get_module_value(CORE_MODULE_ID, "observability", None)
    except (OSError, ValueError, YscbError):
        return FlightLogConfig()
    if isinstance(raw_obs, Mapping):
        try:
            return DataclassCodec.decode(FlightLogConfig, raw_obs)
        except (ValueError, TypeError, KeyError, YscbError):
            return FlightLogConfig()
    return FlightLogConfig()


def _build_sdk_sandbox_env() -> dict[str, str]:
    return read_flight_log_env()


@dataclasses.dataclass(frozen=True, slots=True)
class _DispatcherBundle:
    dispatcher: RuntimeDispatcher
    closers: list[Callable[[], None]]
    post_syncs: list[Callable[[], None]]
    core_bound: bool
    stub_routes: tuple[TaskRouteSpec, ...]


class YscbClient:
    """Programmatic Surface SDK client dispatching tasks across local or connected daemon runtimes."""

    def __init__(
        self,
        workspace_root: HostPath,
        *,
        modules: Sequence[Module | InMemoryModule] = (),
    ) -> None:
        if not isinstance(workspace_root, HostPath):
            raise TypeError(f"workspace_root must be HostPath, got {type(workspace_root).__name__}")
        user_modules = _coerce_yscb_modules(modules)
        self._user_modules: tuple[YscbModule, ...] = user_modules
        self._has_user_core_module = any(m.module_id == CORE_MODULE_ID for m in user_modules)
        self._workspace_root = workspace_root
        self._owned_closers: list[Callable[[], None]] = []
        self._post_call_syncs: list[Callable[[], None]] = []
        self._core_session_bound: bool = False
        self._bound_core_stub_routes: tuple[TaskRouteSpec, ...] = ()
        cache_dir = workspace_root.join(DEFAULT_CACHE_DIRNAME)
        self._cache_dir = cache_dir
        use_rpc = _ConnectContext.is_connect_active()
        self._use_rpc = use_rpc
        self._rpc_session: Optional[PersistentRpcSession] = (
            PersistentRpcSession(cache_dir=cache_dir, workspace_root=workspace_root) if use_rpc else None
        )
        self._lazy_ws_ctx = _LazySdkWorkspaceContext(workspace_root)
        disc_host = self._lazy_ws_ctx.host_dir
        self._bound_host_dir: Optional[HostPath] = disc_host
        try:
            bundle = self._create_dispatcher_bundle(disc_host)
        except Exception:
            if self._rpc_session is not None:
                self._rpc_session.close()
            raise
        self._dispatcher = bundle.dispatcher
        self._owned_closers = bundle.closers
        self._post_call_syncs = bundle.post_syncs
        self._core_session_bound = bundle.core_bound
        self._bound_core_stub_routes = bundle.stub_routes
        self._lifecycle_cond = threading.Condition()
        self._closing = False
        self._closed = False
        self._in_flight_calls = 0
        self._active_call_threads: dict[int, int] = {}
        self._active_call_trees: dict[str, int] = {}
        self._disk_sync_lock = threading.RLock()
        self._last_mods_token, self._last_cfg_token = _compute_sdk_disk_tokens(
            workspace_root,
            disc_host,
        )

    def _create_dispatcher_bundle(
        self,
        disc_host: Optional[HostPath],
    ) -> _DispatcherBundle:
        closers: list[Callable[[], None]] = []
        post_syncs: list[Callable[[], None]] = []
        all_in_mem: list[YscbModule] = list(self._user_modules)
        core_bound = False
        stub_routes: tuple[TaskRouteSpec, ...] = ()
        try:
            if not any(m.module_id == CORE_MODULE_ID for m in all_in_mem):
                core_sess_factory = resolve_sdk_core_session_factory()
                if core_sess_factory is not None:
                    built_core = core_sess_factory(disc_host or self._workspace_root, self._workspace_root)
                    if built_core is not None:
                        core_obj, core_closer = built_core
                        if not isinstance(core_obj, YscbModule):
                            try:
                                core_closer()
                            except Exception:
                                pass
                            raise TypeError("SdkCoreSessionFactory must return a YscbModule instance")
                        all_in_mem.insert(0, core_obj)
                        closers.append(core_closer)
                        post_hook = resolve_sdk_core_post_call_hook(core_obj)
                        if post_hook is not None:
                            post_syncs.append(post_hook)
                        core_bound = True
                if not core_bound:
                    stub_routes = _load_disk_core_route_specs(self._workspace_root)
                    if stub_routes:
                        all_in_mem.insert(0, _UnboundCoreRouteStubModule(stub_routes))

            yscb_modules = tuple(all_in_mem)
            flight_router: Optional[FlightLogRouter] = None
            if (
                disc_host is not None
                and not _has_forbidden_symlink_in_path(self._cache_dir.path)
                and not _is_symlink_or_reparse_path(self._cache_dir.path)
            ):
                flight_router = FlightLogRouter(
                    self._cache_dir.join("logs"),
                    config=_build_sdk_flight_log_config(self._lazy_ws_ctx),
                    env=_build_sdk_sandbox_env(),
                )
                closers.append(flight_router.close)
            conn_cfg = DaemonConnectionConfig(
                enabled=self._use_rpc,
                auto_spawn=False,
                strict_hot_dispatch=False,
            )
            options = DispatcherHostOptions(
                config_view=self._lazy_ws_ctx,
                connection_config=conn_cfg,
                persistent_rpc_session=self._rpc_session,
                in_memory_modules=yscb_modules,
                module_services_factory=self._lazy_ws_ctx.resolve_module_services,
                worker_host_dir=disc_host,
                flight_log_router=flight_router,
            )
            in_mem_ids = frozenset(m.module_id for m in yscb_modules)
            disp = RuntimeDispatcher(
                workspace_root=self._workspace_root,
                cache_dir=self._cache_dir,
                module_provider=_SdkWorkspaceModuleProvider(self._workspace_root, in_mem_ids),
                options=options,
            )
            return _DispatcherBundle(disp, closers, post_syncs, core_bound, stub_routes)
        except BaseException:
            for closer in reversed(closers):
                try:
                    closer()
                except Exception:
                    pass
            raise

    def _rebind_dispatcher_host_locked(self, new_host: Optional[HostPath]) -> None:
        bundle = self._create_dispatcher_bundle(new_host)
        old_disp = self._dispatcher
        old_closers = list(self._owned_closers)
        self._dispatcher = bundle.dispatcher
        self._owned_closers = bundle.closers
        self._post_call_syncs = bundle.post_syncs
        self._core_session_bound = bundle.core_bound
        self._bound_core_stub_routes = bundle.stub_routes
        self._bound_host_dir = new_host
        try:
            old_disp.shutdown()
        finally:
            for closer in reversed(old_closers):
                try:
                    closer()
                except Exception:
                    pass

    @classmethod
    def local(
        cls,
        workspace_root: HostPath,
        *modules: Module | InMemoryModule,
    ) -> YscbClient:
        """Create an in-process local client backed by supplied Module and InMemoryModule instances."""
        return cls(workspace_root, modules=modules)

    @classmethod
    def connect(cls, workspace_root: HostPath) -> YscbClient:
        """Create a client configured to route calls through a persistent daemon RPC session."""
        prev = _ConnectContext.begin_connect()
        try:
            return cls(workspace_root)
        finally:
            _ConnectContext.end_connect(prev)

    @overload
    def call(
        self,
        task_id: TaskRef[Empty, TOut],
        req: Optional[Empty] = None,
        *,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        task_id: TaskRef[TIn, TOut],
        req: TIn,
        *,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: type[TOut],
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: None = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def call(
        self,
        task_id: TaskRef[TIn, TOut] | TaskId | str,
        req: object = None,
        *,
        output_type: Optional[type[TOut]] = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        """Dispatch a task synchronously through RuntimeDispatcher and return its TaskOutcome."""
        ident = threading.get_ident()
        call_tree_id = resolve_active_call_tree_id() or f"sdk-{uuid.uuid4().hex}"
        with self._lifecycle_cond:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.TEARDOWN_ERROR, "YscbClient is already closed")
            self._in_flight_calls += 1
            self._active_call_threads[ident] = self._active_call_threads.get(ident, 0) + 1
            self._active_call_trees[call_tree_id] = self._active_call_trees.get(call_tree_id, 0) + 1
        try:
            return self._execute_call_under_lease(
                task_id,
                req,
                call_tree_id=call_tree_id,
                output_type=output_type,
                cwd=cwd,
                env=env,
                force_cold=force_cold,
                cancel_token=cancel_token,
                approval_scope=approval_scope,
                on_progress=on_progress,
            )
        finally:
            with self._lifecycle_cond:
                rem = self._active_call_threads.get(ident, 1) - 1
                if rem <= 0:
                    self._active_call_threads.pop(ident, None)
                else:
                    self._active_call_threads[ident] = rem
                rem_ct = self._active_call_trees.get(call_tree_id, 1) - 1
                if rem_ct <= 0:
                    self._active_call_trees.pop(call_tree_id, None)
                else:
                    self._active_call_trees[call_tree_id] = rem_ct
                self._in_flight_calls -= 1
                if self._in_flight_calls <= 0:
                    self._lifecycle_cond.notify_all()

    def _execute_call_under_lease(
        self,
        task_id: TaskRef[TIn, TOut] | TaskId | str,
        req: object,
        *,
        call_tree_id: str,
        output_type: Optional[type[TOut]],
        cwd: Optional[HostPath],
        env: Optional[Mapping[str, str]],
        force_cold: bool,
        cancel_token: Optional[CancellationToken],
        approval_scope: frozenset[TaskId],
        on_progress: Optional[Callable[[ProgressEvent], None]],
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        eff_output_type: Optional[type[object]] = output_type
        if isinstance(task_id, TaskRef):
            tid = task_id.task_id
            if output_type is not None and output_type != task_id.output_type:
                return TaskOutcome(
                    ok=False,
                    error=ErrorDetail(
                        ErrorCode.CODEC_VALIDATION_FAILED,
                        f"Conflicting output_type {output_type!r} for TaskRef '{tid}' expecting {task_id.output_type!r}.",
                        source_task=str(tid),
                    ),
                )
            eff_output_type = task_id.output_type
            if req is None:
                if task_id.input_type is Empty:
                    encoded_input: JsonObject = {}
                else:
                    return TaskOutcome(
                        ok=False,
                        error=ErrorDetail(
                            ErrorCode.CODEC_VALIDATION_FAILED,
                            f"TaskRef '{tid}' requires input of type {task_id.input_type!r}.",
                            source_task=str(tid),
                        ),
                    )
            else:
                try:
                    encoded_input = DataclassCodec.encode_object(req, expected_type=task_id.input_type)
                except YscbError as exc:
                    return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(tid)))
        else:
            tid = task_id if isinstance(task_id, TaskId) else TaskId(require_pure_str(task_id, "task_id", non_empty=True))
            encoded_input = _encode_call_input(req)
        if cwd is not None and not isinstance(cwd, HostPath):
            raise TypeError(f"cwd must be HostPath or None, got {type(cwd).__name__}")
        if env is not None and not isinstance(env, Mapping):
            raise TypeError(f"env must be Mapping[str, str] or None, got {type(env).__name__}")
        clean_env: dict[str, str] = (
            {
                require_pure_str(k, "env key", non_empty=True): require_pure_str(v, "env value")
                for k, v in env.items()
            }
            if env is not None
            else {}
        )
        if isinstance(approval_scope, (str, bytes, bytearray, memoryview)) or not isinstance(
            approval_scope, (set, frozenset, Sequence)
        ):
            raise TypeError("approval_scope must be a frozenset of TaskId")
        policy = (
            ClientRoutingPolicy.FORCE_COLD
            if require_pure_bool(force_cold, "force_cold")
            else ClientRoutingPolicy.AUTO_NO_SPAWN
        )
        scope = frozenset(
            item if isinstance(item, TaskId) else TaskId(require_pure_str(item, "approval_scope item", non_empty=True))
            for item in approval_scope
        )
        progress_cb: Optional[Callable[[JsonObject], None]] = None
        if on_progress is not None:
            if not callable(on_progress):
                raise TypeError("on_progress must be callable or None")

            def _forward_progress(payload: JsonObject) -> None:
                decoded = DataclassCodec.decode(ProgressEvent, payload)
                if isinstance(decoded, ProgressEvent):
                    on_progress(decoded)

            progress_cb = _forward_progress
        raw_env_pm: Optional[str] = None
        for ek, ev in clean_env.items():
            if ek.upper() == "YSCB_PROFILE_MEM":
                raw_env_pm = ev
        eff_profile_mem = (
            raw_env_pm.strip().lower() in _TRUTHY_SDK_ENV_VALUES
            if raw_env_pm is not None
            else is_public_env_truthy("YSCB_PROFILE_MEM")
        )
        request = InvokeRequest(
            task_id=tid,
            raw_input=encoded_input,
            workspace_root=self._workspace_root,
            caller_cwd=cwd or self._workspace_root,
            caller_env=clean_env,
            caller_surface=CallerSurface.SDK,
            routing_policy=policy,
            approval_scope=scope,
            propagation=CallPropagationContext(call_tree_id=call_tree_id, profile_mem=eff_profile_mem),
            profile_mem=eff_profile_mem,
        )
        self._sync_local_state_from_disk(allow_module_unload=(self._current_in_flight_count() <= 1))
        try:
            outcome = cast(
                TaskOutcome[TOut] | TaskOutcome[JsonValue],
                self._dispatcher.invoke(
                    request,
                    output_type=eff_output_type,
                    cancel_token=cancel_token,
                    on_progress=progress_cb,
                ),
            )
        finally:
            for sync_fn in self._post_call_syncs:
                try:
                    sync_fn()
                except Exception:
                    pass
        matched_route = (
            next((s for s in self._dispatcher.list_route_specs() if s.task_id == tid), None)
            if (outcome.ok and tid.module_id == CORE_MODULE_ID)
            else None
        )
        explicit_mods = bool(matched_route is not None and matched_route.mutation_scope != SelfMutationScope.NONE)
        explicit_cfg = bool(outcome.ok and tid.value in _COLD_CORE_CONFIG_SPACE_TASKS)
        self._sync_local_state_from_disk(
            force_mods=explicit_mods,
            force_cfg=explicit_cfg,
            allow_module_unload=True,
        )
        return outcome

    def _current_in_flight_count(self) -> int:
        with self._lifecycle_cond:
            return self._in_flight_calls

    def _sync_local_state_from_disk(
        self,
        *,
        force_mods: bool = False,
        force_cfg: bool = False,
        allow_module_unload: bool = True,
    ) -> None:
        with self._disk_sync_lock:
            if force_mods:
                self._last_mods_token = ""
            if force_cfg:
                self._last_cfg_token = ""
            cur_host = self._lazy_ws_ctx.host_dir
            cur_mods, cur_cfg = _compute_sdk_disk_tokens(self._workspace_root, cur_host)
            host_changed = cur_host != self._bound_host_dir
            can_unload = allow_module_unload and (self._current_in_flight_count() <= 1)
            late_factory_ready = (
                not self._has_user_core_module
                and not self._core_session_bound
                and resolve_sdk_core_session_factory() is not None
            )
            mods_dirty = host_changed or late_factory_ready or (cur_mods != self._last_mods_token)
            cfg_dirty = host_changed or (cur_cfg != self._last_cfg_token)
            if not mods_dirty and not cfg_dirty:
                return
            if host_changed and can_unload:
                self._lazy_ws_ctx.reload()
                self._rebind_dispatcher_host_locked(cur_host)
                refreshed_mods, refreshed_cfg = _compute_sdk_disk_tokens(
                    self._workspace_root,
                    self._lazy_ws_ctx.host_dir,
                )
                self._last_mods_token = refreshed_mods
                self._last_cfg_token = refreshed_cfg
                return
            if mods_dirty and can_unload:
                self._lazy_ws_ctx.reload()
                latest_host = self._lazy_ws_ctx.host_dir
                core_stub_stale = (
                    not self._has_user_core_module
                    and not self._core_session_bound
                    and (
                        late_factory_ready
                        or _load_disk_core_route_specs(self._workspace_root) != self._bound_core_stub_routes
                    )
                )
                if latest_host != self._bound_host_dir or core_stub_stale:
                    self._rebind_dispatcher_host_locked(latest_host)
                else:
                    _ = self._dispatcher.reload_config_and_contributes(emit_event=False)
                    self._dispatcher.reload_affected_modules(frozenset())
                refreshed_mods, refreshed_cfg = _compute_sdk_disk_tokens(
                    self._workspace_root,
                    self._lazy_ws_ctx.host_dir,
                )
                self._last_mods_token = refreshed_mods
                self._last_cfg_token = refreshed_cfg
            elif mods_dirty or cfg_dirty:
                self._lazy_ws_ctx.reload()
                _ = self._dispatcher.reload_config_and_contributes(emit_event=False)
                _, refreshed_cfg = _compute_sdk_disk_tokens(
                    self._workspace_root,
                    self._lazy_ws_ctx.host_dir,
                )
                self._last_cfg_token = refreshed_cfg

    def close(self) -> None:
        """Shut down the local RuntimeDispatcher, owned core session, and any active RPC session idempotently."""
        ident = threading.get_ident()
        active_ct = resolve_active_call_tree_id()
        with self._lifecycle_cond:
            if ident in self._active_call_threads or (
                active_ct is not None and active_ct in self._active_call_trees
            ):
                raise YscbError(
                    ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                    "Cannot close YscbClient reentrantly from an active call on the same thread.",
                )
            if self._closed:
                return
            if self._closing:
                while not self._closed:
                    self._lifecycle_cond.wait()
                return
            self._closing = True
            while self._in_flight_calls > 0:
                self._lifecycle_cond.wait()
            owned_closers = list(self._owned_closers)
            self._owned_closers.clear()
        errors: list[str] = []
        try:
            try:
                errs = self._dispatcher.shutdown()
                errors.extend(err.message for err in errs)
            except Exception as exc:
                errors.append(str(exc))
            for closer in reversed(owned_closers):
                try:
                    closer()
                except Exception as exc:
                    errors.append(str(exc))
            if self._rpc_session is not None:
                try:
                    self._rpc_session.close()
                except Exception as exc:
                    errors.append(str(exc))
        finally:
            with self._lifecycle_cond:
                self._closed = True
                self._lifecycle_cond.notify_all()
        if errors:
            raise YscbError(ErrorCode.TEARDOWN_ERROR, f"YscbClient close failed: {'; '.join(errors)}")

    def __enter__(self) -> YscbClient:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        _ = (exc_type, exc_val, exc_tb)
        self.close()
