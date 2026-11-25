"""Immutable virtual environment specifications, metadata codecs, quick health checks, and tree cleanup helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import sys
from types import MappingProxyType
from typing import Final, Mapping, Optional, Sequence

from core.filesystem.fs import (
    atomic_write_json,
    is_symlink_or_reparse,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
)
from core.foundation.primitives import (
    IS_WINDOWS,
    EnvHash,
    HostPath,
    JsonObject,
    ModuleId,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
    safe_real_to_float,
    validate_relative_segment,
)
from core.metadata.config import ModuleManifest

_ENV_META_FILENAME: Final[str] = ".yscb_env_meta.json"
_PYVENV_CFG_FILENAME: Final[str] = "pyvenv.cfg"
_MAX_PYVENV_CFG_BYTES: Final[int] = 65536
_PEP503_SEP_RE: Final[re.Pattern[str]] = re.compile(r"[-_.]+")
_PEP503_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_PEP440_CLAUSE_OP_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"^(===|~=|==|!=|<=|>=|<|>)\s+")
_ENV_GROUP_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")
_PEP440_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:===|~=|==|!=|<=|>=|<|>)[0-9A-Za-z][0-9A-Za-z.*+!_-]*$"
)
_PIP_SPEC_OP_SEARCH_RE: Final[re.Pattern[str]] = re.compile(r"(?:===|~=|==|!=|<=|>=|<|>)")
_FORBIDDEN_SPEC_CHARS: Final[frozenset[str]] = frozenset({"/", "\\", ":", "@", ";"})
_FORBIDDEN_ARCHIVE_SUFFIXES: Final[tuple[str, ...]] = (
    ".whl",
    ".zip",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tar.xz",
    ".tar",
)


def env_validate_group_name(group: str) -> str:
    """Validate an environment group identifier rejecting traversal and hidden dot prefixes."""
    validated = validate_relative_segment(group, label="venv group")
    if _ENV_GROUP_NAME_RE.fullmatch(validated) is None:
        raise ValueError(f"Environment group must match ^[A-Za-z0-9_-]+$: {group!r}")
    return validated


def _normalize_pep503_token(raw_token: str, *, label: str) -> str:
    require_pure_str(raw_token, label, non_empty=True)
    collapsed = _PEP503_SEP_RE.sub("-", raw_token.strip()).lower()
    if _PEP503_NAME_RE.fullmatch(collapsed) is None:
        raise ValueError(f"Invalid {label}: {raw_token!r}")
    return collapsed


def _normalize_pip_package_key(raw_key: str) -> str:
    require_pure_str(raw_key, "pip package name", non_empty=True)
    cleaned = raw_key.strip()
    if "[" not in cleaned and "]" not in cleaned:
        return _normalize_pep503_token(cleaned, label="pip package name")
    if not cleaned.endswith("]") or cleaned.count("[") != 1 or cleaned.count("]") != 1:
        raise ValueError(f"Malformed extras in pip package name: {raw_key!r}")
    base_part, extras_part = cleaned[:-1].split("[", 1)
    norm_base = _normalize_pep503_token(base_part, label="pip package name")
    raw_extras = [item.strip() for item in extras_part.split(",")]
    if not raw_extras or any(not item for item in raw_extras):
        raise ValueError(f"Empty extra identifier in pip package name: {raw_key!r}")
    norm_extras = sorted({_normalize_pep503_token(item, label="pip package extra") for item in raw_extras})
    return f"{norm_base}[{','.join(norm_extras)}]"


def _parse_pip_constraint_clauses(raw_constraint: str) -> tuple[str, ...]:
    require_pure_str(raw_constraint, "pip version constraint")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_constraint):
        raise ValueError(f"Control characters forbidden in pip version constraint: {raw_constraint!r}")
    trimmed = raw_constraint.strip()
    if not trimmed or trimmed == "*":
        return ()
    parts = [seg.strip() for seg in trimmed.split(",")]
    if not parts or any(not seg for seg in parts):
        raise ValueError(f"Malformed comma clause in pip version constraint: {raw_constraint!r}")
    normalized: set[str] = set()
    for seg in parts:
        compact = _PEP440_CLAUSE_OP_SPACE_RE.sub(r"\1", seg)
        if compact in ("*", "==*"):
            continue
        if _PEP440_CLAUSE_RE.fullmatch(compact) is None:
            raise ValueError(f"Invalid PEP 440 version specifier clause {seg!r} in {raw_constraint!r}")
        normalized.add(compact)
    return tuple(sorted(normalized))


def _validate_pip_spec_entry(raw_entry: str) -> str:
    require_pure_str(raw_entry, "EnvSpec.pip_specs entry", non_empty=True)
    cleaned = raw_entry.strip()
    if (
        cleaned != raw_entry
        or cleaned.startswith("-")
        or any(
            ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F or ch in _FORBIDDEN_SPEC_CHARS
            for ch in cleaned
        )
    ):
        raise ValueError(f"Invalid canonical pip requirement entry: {raw_entry!r}")
    if cleaned.lower().endswith(_FORBIDDEN_ARCHIVE_SUFFIXES):
        raise ValueError(f"Archive path or wheel filename forbidden in EnvSpec.pip_specs: {raw_entry!r}")
    op_match = _PIP_SPEC_OP_SEARCH_RE.search(cleaned)
    if op_match is None:
        _normalize_pip_package_key(cleaned)
    else:
        pkg_part = cleaned[: op_match.start()]
        ver_part = cleaned[op_match.start() :]
        if not pkg_part:
            raise ValueError(f"Missing package name in EnvSpec.pip_specs entry: {raw_entry!r}")
        _normalize_pip_package_key(pkg_part)
        parsed_clauses = _parse_pip_constraint_clauses(ver_part)
        if not parsed_clauses:
            raise ValueError(f"Non-canonical wildcard constraint in EnvSpec.pip_specs entry: {raw_entry!r}")
    return cleaned


@dataclass(frozen=True, slots=True)
class EnvSpec:
    """不可變 Tier 1 虛擬環境規格描述。"""

    group: str
    py_tag: str
    platform_tag: str
    pip_specs: tuple[str, ...]
    env_hash: EnvHash

    def __post_init__(self) -> None:
        env_validate_group_name(self.group)
        validate_relative_segment(self.py_tag, label="EnvSpec.py_tag")
        require_pure_str(self.platform_tag, "EnvSpec.platform_tag", non_empty=True)
        raw_tup = require_typed_tuple(self.pip_specs, str, "EnvSpec.pip_specs")
        validated_specs = tuple(_validate_pip_spec_entry(item) for item in raw_tup)
        if not isinstance(self.env_hash, EnvHash):
            raise ValueError(f"EnvSpec.env_hash must be EnvHash, got {self.env_hash!r}")
        object.__setattr__(self, "pip_specs", validated_specs)

    @property
    def dirname(self) -> str:
        return f"{self.group}_{self.py_tag}_{self.env_hash.short(16)}"


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

    def __post_init__(self) -> None:
        env_validate_group_name(self.group)
        if not isinstance(self.env_hash, EnvHash):
            raise ValueError(f"EnvMetadata.env_hash must be EnvHash, got {self.env_hash!r}")
        validate_relative_segment(self.py_tag, label="EnvMetadata.py_tag")
        require_pure_str(self.platform_tag, "EnvMetadata.platform_tag", non_empty=True)
        raw_tup = require_typed_tuple(self.pip_specs, str, "EnvMetadata.pip_specs")
        validated_specs = tuple(_validate_pip_spec_entry(item) for item in raw_tup)
        require_pure_str(self.created_at_utc, "EnvMetadata.created_at_utc", non_empty=True)
        f_last = safe_real_to_float(self.last_used_epoch_sec, label="EnvMetadata.last_used_epoch_sec")
        if not math.isfinite(f_last) or f_last < 0.0:
            raise ValueError(
                f"EnvMetadata.last_used_epoch_sec must be finite and >= 0, got {self.last_used_epoch_sec!r}"
            )
        require_pure_bool(self.complete, "EnvMetadata.complete")
        object.__setattr__(self, "pip_specs", validated_specs)
        object.__setattr__(self, "last_used_epoch_sec", f_last)


@dataclass(frozen=True, slots=True)
class EnvBuildResult:
    spec: EnvSpec
    env_dir: HostPath
    python_exe: HostPath
    reused: bool
    duration_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.spec, EnvSpec):
            raise ValueError(f"EnvBuildResult.spec must be EnvSpec, got {self.spec!r}")
        if not isinstance(self.env_dir, HostPath):
            raise ValueError(f"EnvBuildResult.env_dir must be HostPath, got {self.env_dir!r}")
        if not isinstance(self.python_exe, HostPath):
            raise ValueError(f"EnvBuildResult.python_exe must be HostPath, got {self.python_exe!r}")
        require_pure_bool(self.reused, "EnvBuildResult.reused")
        require_pure_int(self.duration_ms, "EnvBuildResult.duration_ms", min_val=0)


@dataclass(frozen=True, slots=True)
class EnvHealthReport:
    spec: Optional[EnvSpec]
    env_dir: HostPath
    quick_ok: bool
    deep_import_ok: Optional[bool] = None
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.spec is not None and not isinstance(self.spec, EnvSpec):
            raise ValueError(f"EnvHealthReport.spec must be EnvSpec or None, got {self.spec!r}")
        if not isinstance(self.env_dir, HostPath):
            raise ValueError(f"EnvHealthReport.env_dir must be HostPath, got {self.env_dir!r}")
        require_pure_bool(self.quick_ok, "EnvHealthReport.quick_ok")
        if self.deep_import_ok is not None:
            require_pure_bool(self.deep_import_ok, "EnvHealthReport.deep_import_ok")
        tup_issues = require_typed_tuple(self.issues, str, "EnvHealthReport.issues")
        object.__setattr__(self, "issues", tup_issues)


@dataclass(frozen=True, slots=True)
class EnvGcPolicy:
    """回滾友善孤兒環境回收策略（與 SnapshotVault 7 天視窗對齊，退化為即時回收僅需設為 0）。"""

    grace_days: float = 7.0
    keep_inactive_per_group: int = 1

    def __post_init__(self) -> None:
        f_grace = safe_real_to_float(self.grace_days, label="EnvGcPolicy.grace_days")
        if not math.isfinite(f_grace) or f_grace < 0.0:
            raise ValueError(f"EnvGcPolicy.grace_days must be finite and >= 0, got {self.grace_days!r}")
        require_pure_int(self.keep_inactive_per_group, "EnvGcPolicy.keep_inactive_per_group", min_val=0)
        object.__setattr__(self, "grace_days", f_grace)


@dataclass(frozen=True, slots=True)
class EnvGcResult:
    removed_dirs: tuple[HostPath, ...] = ()
    skipped_locked_dirs: tuple[HostPath, ...] = ()
    retained_rollback_dirs: tuple[HostPath, ...] = ()
    cleaned_staging_dirs: tuple[HostPath, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "removed_dirs",
            require_typed_tuple(self.removed_dirs, HostPath, "EnvGcResult.removed_dirs"),
        )
        object.__setattr__(
            self,
            "skipped_locked_dirs",
            require_typed_tuple(self.skipped_locked_dirs, HostPath, "EnvGcResult.skipped_locked_dirs"),
        )
        object.__setattr__(
            self,
            "retained_rollback_dirs",
            require_typed_tuple(self.retained_rollback_dirs, HostPath, "EnvGcResult.retained_rollback_dirs"),
        )
        object.__setattr__(
            self,
            "cleaned_staging_dirs",
            require_typed_tuple(self.cleaned_staging_dirs, HostPath, "EnvGcResult.cleaned_staging_dirs"),
        )


def env_compute_spec_from_deps(group: str, pip_dependencies: Mapping[str, str]) -> EnvSpec:
    """Compute a deterministic content-addressed EnvSpec from a group name and pip requirement map."""
    clean_group = env_validate_group_name(group)
    if not isinstance(pip_dependencies, Mapping) or not pip_dependencies:
        raise ValueError("pip_dependencies must be a non-empty Mapping[str, str].")
    clauses_by_pkg: dict[str, set[str]] = {}
    for raw_pkg, raw_ver in pip_dependencies.items():
        norm_pkg = _normalize_pip_package_key(raw_pkg)
        clauses = _parse_pip_constraint_clauses(raw_ver)
        bucket = clauses_by_pkg.setdefault(norm_pkg, set())
        bucket.update(clauses)
    canonical_specs = tuple(
        f"{pkg}{','.join(sorted(clauses_by_pkg[pkg]))}" if clauses_by_pkg[pkg] else pkg
        for pkg in sorted(clauses_by_pkg)
    )
    py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    machine_lower = platform.machine().lower()
    platform_tag = f"{sys.platform}_{machine_lower}"
    hash_payload = {
        "canonical_pip_specs": list(canonical_specs),
        "machine": machine_lower,
        "platform": sys.platform,
        "py_tag": py_tag,
    }
    canonical_json = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest16 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
    return EnvSpec(
        group=clean_group,
        py_tag=py_tag,
        platform_tag=platform_tag,
        pip_specs=canonical_specs,
        env_hash=EnvHash(digest16),
    )


def env_resolve_manifest_specs(manifests: Sequence[ModuleManifest]) -> Mapping[ModuleId, EnvSpec]:
    """Co-locate Tier 1 manifests sharing a venv_group into deterministic shared EnvSpec instances."""
    manifest_tup = require_typed_tuple(manifests, ModuleManifest, "manifests")
    seen_ids: set[ModuleId] = set()
    members_by_group: dict[str, list[ModuleId]] = {}
    clauses_by_group: dict[str, dict[str, set[str]]] = {}
    for manifest in manifest_tup:
        if manifest.id in seen_ids:
            raise ValueError(f"Duplicate ModuleManifest id in resolve_group_specs: {manifest.id}")
        seen_ids.add(manifest.id)
        if not manifest.is_tier1:
            continue
        if not isinstance(manifest.pip_dependencies, Mapping) or not manifest.pip_dependencies:
            continue
        raw_group = manifest.venv_group if manifest.venv_group else manifest.id.value
        clean_group = env_validate_group_name(raw_group)
        members_by_group.setdefault(clean_group, []).append(manifest.id)
        pkg_map = clauses_by_group.setdefault(clean_group, {})
        for raw_pkg, raw_ver in manifest.pip_dependencies.items():
            norm_pkg = _normalize_pip_package_key(raw_pkg)
            clauses = _parse_pip_constraint_clauses(raw_ver)
            pkg_map.setdefault(norm_pkg, set()).update(clauses)
    resolved: dict[ModuleId, EnvSpec] = {}
    for clean_group, mod_ids in members_by_group.items():
        pkg_map = clauses_by_group[clean_group]
        merged_deps = {
            pkg: (",".join(sorted(clauses)) if clauses else "*")
            for pkg, clauses in sorted(pkg_map.items())
        }
        group_spec = env_compute_spec_from_deps(clean_group, merged_deps)
        for mod_id in mod_ids:
            resolved[mod_id] = group_spec
    return MappingProxyType(resolved)


def env_read_metadata(env_dir: HostPath) -> Optional[EnvMetadata]:
    """Read and validate <env_dir>/.yscb_env_meta.json, returning None if missing or malformed."""
    doc = read_json_dict(env_dir, _ENV_META_FILENAME)
    if doc is None:
        return None
    raw_group = doc.get("group")
    raw_hash = doc.get("env_hash")
    raw_py_tag = doc.get("py_tag")
    raw_platform = doc.get("platform_tag")
    raw_pip_specs = doc.get("pip_specs")
    raw_created = doc.get("created_at_utc")
    raw_last_used = doc.get("last_used_epoch_sec")
    raw_complete = doc.get("complete")
    if (
        type(raw_group) is not str
        or type(raw_hash) is not str
        or type(raw_py_tag) is not str
        or type(raw_platform) is not str
        or not isinstance(raw_pip_specs, list)
        or any(type(item) is not str for item in raw_pip_specs)
        or type(raw_created) is not str
        or type(raw_last_used) not in (int, float)
        or type(raw_complete) is not bool
    ):
        return None
    try:
        return EnvMetadata(
            group=raw_group,
            env_hash=EnvHash(raw_hash),
            py_tag=raw_py_tag,
            platform_tag=raw_platform,
            pip_specs=tuple(str(item) for item in raw_pip_specs),
            created_at_utc=raw_created,
            last_used_epoch_sec=float(raw_last_used),
            complete=raw_complete,
        )
    except ValueError:
        return None


def env_write_metadata(env_dir: HostPath, meta: EnvMetadata) -> None:
    """Atomically persist EnvMetadata to <env_dir>/.yscb_env_meta.json."""
    dest = resolve_contained_subpath(env_dir, _ENV_META_FILENAME)
    payload: JsonObject = {
        "group": meta.group,
        "env_hash": meta.env_hash.value,
        "py_tag": meta.py_tag,
        "platform_tag": meta.platform_tag,
        "pip_specs": list(meta.pip_specs),
        "created_at_utc": meta.created_at_utc,
        "last_used_epoch_sec": meta.last_used_epoch_sec,
        "complete": meta.complete,
    }
    atomic_write_json(dest, payload)


def _pyvenv_cfg_disables_system_site(raw_cfg_bytes: bytes) -> bool:
    text = raw_cfg_bytes.decode("utf-8", errors="replace")
    found = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key_part, val_part = stripped.split("=", 1)
        if key_part.strip().lower() == "include-system-site-packages":
            if val_part.strip().lower() != "false":
                return False
            found = True
    return found


def env_find_python_exe(env_dir: HostPath) -> Optional[HostPath]:
    """Locate a valid, non-broken virtual environment Python interpreter path inside env_dir."""
    raw_env = str(env_dir)
    if is_symlink_or_reparse(raw_env) or not os.path.isdir(raw_env):
        return None
    cfg_raw = os.path.join(raw_env, _PYVENV_CFG_FILENAME)
    if is_symlink_or_reparse(cfg_raw) or not os.path.isfile(cfg_raw):
        return None
    bin_subdir = "Scripts" if IS_WINDOWS else "bin"
    exe_name = "python.exe" if IS_WINDOWS else "python"
    bin_raw = os.path.join(raw_env, bin_subdir)
    if is_symlink_or_reparse(bin_raw) or not os.path.isdir(bin_raw):
        return None
    exe_raw = os.path.join(bin_raw, exe_name)
    if not os.path.lexists(exe_raw) or not os.path.isfile(exe_raw):
        return None
    if not IS_WINDOWS and not os.access(exe_raw, os.X_OK):
        return None
    try:
        return HostPath(exe_raw)
    except ValueError:
        return None


def env_quick_probe_issues(env_dir: HostPath, spec: EnvSpec) -> tuple[str, ...]:
    """Run O(1) structural and metadata verification on env_dir against spec."""
    raw_env = str(env_dir)
    if is_symlink_or_reparse(raw_env) or not os.path.isdir(raw_env):
        return ("Environment directory is missing or is a symbolic link.",)
    issues: list[str] = []
    cfg_raw = os.path.join(raw_env, _PYVENV_CFG_FILENAME)
    try:
        cfg_bytes = read_nofollow_regular_bytes(cfg_raw, max_bytes=_MAX_PYVENV_CFG_BYTES)
    except OSError:
        cfg_bytes = None
    if cfg_bytes is None:
        issues.append("Missing or unreadable pyvenv.cfg.")
    elif not _pyvenv_cfg_disables_system_site(cfg_bytes):
        issues.append("pyvenv.cfg does not enforce include-system-site-packages = false.")
    if env_find_python_exe(env_dir) is None:
        issues.append("Python executable is missing or points to a broken link.")
    meta = env_read_metadata(env_dir)
    if meta is None:
        issues.append("Missing or malformed .yscb_env_meta.json.")
    else:
        if not meta.complete:
            issues.append("Environment metadata complete marker is false.")
        if meta.group != spec.group:
            issues.append("Environment metadata group does not match spec.")
        if meta.env_hash != spec.env_hash:
            issues.append("Environment metadata env_hash does not match spec.")
        if meta.py_tag != spec.py_tag:
            issues.append("Environment metadata py_tag does not match spec.")
        if meta.platform_tag != spec.platform_tag:
            issues.append("Environment metadata platform_tag does not match spec.")
        if meta.pip_specs != spec.pip_specs:
            issues.append("Environment metadata pip_specs does not match spec.")
    return tuple(issues)


def _ensure_dir_writable(raw_dir: str, *, clear_readonly: bool) -> None:
    if not clear_readonly or is_symlink_or_reparse(raw_dir):
        return
    try:
        st = os.lstat(raw_dir)
        if stat.S_ISDIR(st.st_mode):
            extra = (stat.S_IWRITE | stat.S_IREAD) if IS_WINDOWS else (stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
            os.chmod(raw_dir, stat.S_IMODE(st.st_mode) | extra)
    except OSError:
        return


def _unlink_file_or_reparse_entry(raw_entry_path: str, *, clear_readonly_files: bool) -> None:
    if is_symlink_or_reparse(raw_entry_path):
        try:
            os.unlink(raw_entry_path)
            return
        except FileNotFoundError:
            return
        except OSError:
            try:
                os.rmdir(raw_entry_path)
            except FileNotFoundError:
                return
            return
    try:
        os.unlink(raw_entry_path)
    except FileNotFoundError:
        return
    except PermissionError:
        if not clear_readonly_files or is_symlink_or_reparse(raw_entry_path):
            raise
        os.chmod(raw_entry_path, stat.S_IWRITE | stat.S_IREAD)
        os.unlink(raw_entry_path)


def env_robust_rmtree(target_dir: Path, *, clear_readonly_files: bool) -> None:
    """Iteratively remove target_dir without following symlinks or NTFS reparse points."""
    raw_root = str(target_dir)
    if not os.path.lexists(raw_root):
        return
    if is_symlink_or_reparse(raw_root) or not os.path.isdir(raw_root):
        _ensure_dir_writable(os.path.dirname(raw_root), clear_readonly=clear_readonly_files)
        _unlink_file_or_reparse_entry(raw_root, clear_readonly_files=clear_readonly_files)
        return
    dir_stack: list[tuple[str, bool]] = [(raw_root, False)]
    while dir_stack:
        cur_dir, children_visited = dir_stack.pop()
        if children_visited:
            _ensure_dir_writable(cur_dir, clear_readonly=clear_readonly_files)
            try:
                os.rmdir(cur_dir)
            except FileNotFoundError:
                pass
            continue
        _ensure_dir_writable(cur_dir, clear_readonly=clear_readonly_files)
        dir_stack.append((cur_dir, True))
        try:
            with os.scandir(cur_dir) as entries_it:
                entries = list(entries_it)
        except FileNotFoundError:
            dir_stack.pop()
            continue
        for entry in entries:
            entry_path = entry.path
            if entry.is_symlink() or is_symlink_or_reparse(entry_path):
                _unlink_file_or_reparse_entry(entry_path, clear_readonly_files=clear_readonly_files)
            elif entry.is_dir(follow_symlinks=False):
                dir_stack.append((entry_path, False))
            else:
                _unlink_file_or_reparse_entry(entry_path, clear_readonly_files=clear_readonly_files)
