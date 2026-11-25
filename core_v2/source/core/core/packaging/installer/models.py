"""Domain value objects, integrity validators, and manifest/index codecs for core.packaging.installer."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from enum import Enum
import hashlib
import os
import re
import stat
import time
from types import MappingProxyType
from typing import BinaryIO, Final, Mapping, Optional
import zipfile
import zlib

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
)
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    JsonObject,
    ModuleId,
    MutableJsonObject,
    SemVer4,
    VersionConstraint,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_str,
    require_typed_tuple,
    strict_parse_json_object,
)
from core.metadata.config import (
    ModuleManifest,
    ReleaseUrgency,
    parse_manifest_dict,
)
from core.packaging.env import EnvSpec

INS_RESERVED_NON_MODULE_IDS: Final[frozenset[str]] = frozenset({"locks", "wheels", "daemon", "project"})
INS_NON_FALLBACK_ERROR_CODES: Final[frozenset[ErrorCode]] = frozenset(
    {
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
        ErrorCode.SECURITY_GATED,
        ErrorCode.CONFIG_INVALID,
        ErrorCode.TASK_CANCELLED,
        ErrorCode.TASK_PREEMPTED,
    }
)
INS_ZIP_RATIO_CHECK_MIN_BYTES: Final[int] = 1024 * 1024
INS_MAX_ZIP_COMPRESSION_RATIO: Final[int] = 200
_SHA256_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
INS_MAX_ZIP_MEMBERS: Final[int] = 4096
INS_MAX_ZIP_SINGLE_BYTES: Final[int] = 32 * 1024 * 1024
INS_MAX_ZIP_TOTAL_BYTES: Final[int] = 128 * 1024 * 1024
INS_MAX_ZIP_ARCHIVE_BYTES: Final[int] = 64 * 1024 * 1024
_UNSET_DEPS_SENTINEL: Final[Mapping[ModuleId, VersionConstraint]] = MappingProxyType({})
_ZIP_NOFOLLOW_OPEN_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW | os.O_NONBLOCK)
)


def _unset_deps_factory() -> Mapping[ModuleId, VersionConstraint]:
    return _UNSET_DEPS_SENTINEL


class PurgeLevel(Enum):
    """Data-space cleanup scope when removing an installed module."""

    NONE = "none"
    CLEAN = "clean"
    PURGE = "purge"


def _freeze_dependency_map(
    raw: Mapping[ModuleId, VersionConstraint],
    *,
    label: str,
) -> Mapping[ModuleId, VersionConstraint]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a Mapping[ModuleId, VersionConstraint], got {raw!r}")
    out: dict[ModuleId, VersionConstraint] = {}
    for mod_id, constraint in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"{label} key must be ModuleId, got {mod_id!r}")
        if not isinstance(constraint, VersionConstraint):
            raise ValueError(f"{label}[{mod_id}] must be VersionConstraint, got {constraint!r}")
        out[mod_id] = constraint
    return MappingProxyType(out)


def _freeze_version_map(
    raw: Mapping[ModuleId, SemVer4],
    *,
    label: str,
) -> Mapping[ModuleId, SemVer4]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a Mapping[ModuleId, SemVer4], got {raw!r}")
    out: dict[ModuleId, SemVer4] = {}
    for mod_id, ver in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"{label} key must be ModuleId, got {mod_id!r}")
        if not isinstance(ver, SemVer4):
            raise ValueError(f"{label}[{mod_id}] must be SemVer4, got {ver!r}")
        out[mod_id] = ver
    return MappingProxyType(out)


def _freeze_env_spec_map(
    raw: Mapping[ModuleId, EnvSpec],
    *,
    label: str,
) -> Mapping[ModuleId, EnvSpec]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a Mapping[ModuleId, EnvSpec], got {raw!r}")
    out: dict[ModuleId, EnvSpec] = {}
    for mod_id, spec in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"{label} key must be ModuleId, got {mod_id!r}")
        if not isinstance(spec, EnvSpec):
            raise ValueError(f"{label}[{mod_id}] must be EnvSpec, got {spec!r}")
        out[mod_id] = spec
    return MappingProxyType(out)


def _freeze_onboarding_map(
    raw: Mapping[ModuleId, tuple[str, ...]],
    *,
    label: str,
) -> Mapping[ModuleId, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a Mapping[ModuleId, tuple[str, ...]], got {raw!r}")
    out: dict[ModuleId, tuple[str, ...]] = {}
    for mod_id, hints in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"{label} key must be ModuleId, got {mod_id!r}")
        out[mod_id] = require_typed_tuple(hints, str, f"{label}[{mod_id}]")
    return MappingProxyType(out)


@dataclass(frozen=True, slots=True)
class IndexReleaseRecord:
    """Immutable release ledger record for a single published module version."""

    version: SemVer4
    sha256: str
    status: str = "active"
    dependencies: Mapping[ModuleId, VersionConstraint] = field(default_factory=_unset_deps_factory)
    urgency: ReleaseUrgency = ReleaseUrgency.RECOMMENDED
    summary: str = ""
    yanked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.version, SemVer4):
            raise ValueError(f"IndexReleaseRecord.version must be SemVer4, got {self.version!r}")
        require_pure_str(self.sha256, "IndexReleaseRecord.sha256")
        clean_sha = self.sha256.strip().lower()
        if clean_sha and _SHA256_HEX_RE.fullmatch(clean_sha) is None:
            raise ValueError(f"IndexReleaseRecord.sha256 must be empty or 64-char hex, got {self.sha256!r}")
        object.__setattr__(self, "sha256", clean_sha)
        require_pure_str(self.status, "IndexReleaseRecord.status", non_empty=True)
        if self.status not in ("active", "pruned"):
            raise ValueError(f"IndexReleaseRecord.status must be 'active' or 'pruned', got {self.status!r}")
        if self.dependencies is not _UNSET_DEPS_SENTINEL:
            object.__setattr__(
                self,
                "dependencies",
                _freeze_dependency_map(self.dependencies, label="IndexReleaseRecord.dependencies"),
            )
        if not isinstance(self.urgency, ReleaseUrgency):
            raise ValueError(f"IndexReleaseRecord.urgency must be ReleaseUrgency, got {self.urgency!r}")
        require_pure_str(self.summary, "IndexReleaseRecord.summary")
        require_pure_bool(self.yanked, "IndexReleaseRecord.yanked")


def ins_has_dependencies_override(rec: Optional[IndexReleaseRecord]) -> bool:
    """Return True only when an IndexReleaseRecord explicitly specifies a dependencies map."""
    return rec is not None and rec.dependencies is not _UNSET_DEPS_SENTINEL


@dataclass(frozen=True, slots=True)
class RemoteModuleIndex:
    """Immutable module release index containing active window versions and historical release metadata."""

    module_id: ModuleId
    versions: tuple[SemVer4, ...]
    releases: Mapping[str, IndexReleaseRecord]

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"RemoteModuleIndex.module_id must be ModuleId, got {self.module_id!r}")
        object.__setattr__(
            self,
            "versions",
            require_typed_tuple(self.versions, SemVer4, "RemoteModuleIndex.versions"),
        )
        if not isinstance(self.releases, Mapping):
            raise ValueError("RemoteModuleIndex.releases must be a Mapping[str, IndexReleaseRecord].")
        frozen_rel: dict[str, IndexReleaseRecord] = {}
        for ver_key, rec in self.releases.items():
            require_pure_str(ver_key, "RemoteModuleIndex.releases key", non_empty=True)
            if not isinstance(rec, IndexReleaseRecord):
                raise ValueError(
                    f"RemoteModuleIndex.releases[{ver_key!r}] must be IndexReleaseRecord, got {rec!r}"
                )
            parsed_key = SemVer4.parse(ver_key)
            if parsed_key != rec.version:
                raise ValueError(
                    f"RemoteModuleIndex.releases key {ver_key!r} mismatches record version {rec.version!r}"
                )
            canon_key = str(rec.version)
            if canon_key in frozen_rel:
                raise ValueError(
                    f"Duplicate canonical SemVer4 release key {canon_key!r} in RemoteModuleIndex.releases"
                )
            frozen_rel[canon_key] = rec
        object.__setattr__(self, "releases", MappingProxyType(frozen_rel))


@dataclass(frozen=True, slots=True)
class PackageRequest:
    """Target module specification for offline package installation."""

    module_id: ModuleId
    version_spec: Optional[str] = None
    is_build: bool = False
    provider_override: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"PackageRequest.module_id must be ModuleId, got {self.module_id!r}")
        if self.version_spec is not None:
            require_pure_str(self.version_spec, "PackageRequest.version_spec")
        require_pure_bool(self.is_build, "PackageRequest.is_build")
        if self.provider_override is not None:
            require_pure_str(self.provider_override, "PackageRequest.provider_override")


@dataclass(frozen=True, slots=True)
class UpgradeTransition:
    """Version transition emitted for upper-layer system tasks to dispatch module migrations."""

    module_id: ModuleId
    old_version: Optional[SemVer4]
    new_version: SemVer4
    is_upgrade: bool

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"UpgradeTransition.module_id must be ModuleId, got {self.module_id!r}")
        if self.old_version is not None and not isinstance(self.old_version, SemVer4):
            raise ValueError(
                f"UpgradeTransition.old_version must be SemVer4 or None, got {self.old_version!r}"
            )
        if not isinstance(self.new_version, SemVer4):
            raise ValueError(f"UpgradeTransition.new_version must be SemVer4, got {self.new_version!r}")
        require_pure_bool(self.is_upgrade, "UpgradeTransition.is_upgrade")


@dataclass(frozen=True, slots=True)
class DeploymentReport:
    """Immutable outcome of an offline package transaction."""

    installed: Mapping[ModuleId, SemVer4]
    removed: tuple[ModuleId, ...]
    transitions: tuple[UpgradeTransition, ...]
    env_specs: Mapping[ModuleId, EnvSpec]
    snapshot_id: Optional[str] = None
    reconciled_dependencies: tuple[ModuleId, ...] = ()
    onboarding_hints: Mapping[ModuleId, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "installed",
            _freeze_version_map(self.installed, label="DeploymentReport.installed"),
        )
        object.__setattr__(
            self,
            "removed",
            require_typed_tuple(self.removed, ModuleId, "DeploymentReport.removed"),
        )
        object.__setattr__(
            self,
            "transitions",
            require_typed_tuple(self.transitions, UpgradeTransition, "DeploymentReport.transitions"),
        )
        object.__setattr__(
            self,
            "env_specs",
            _freeze_env_spec_map(self.env_specs, label="DeploymentReport.env_specs"),
        )
        if self.snapshot_id is not None:
            require_pure_str(self.snapshot_id, "DeploymentReport.snapshot_id", non_empty=True)
        object.__setattr__(
            self,
            "reconciled_dependencies",
            require_typed_tuple(
                self.reconciled_dependencies,
                ModuleId,
                "DeploymentReport.reconciled_dependencies",
            ),
        )
        object.__setattr__(
            self,
            "onboarding_hints",
            _freeze_onboarding_map(self.onboarding_hints, label="DeploymentReport.onboarding_hints"),
        )


@dataclass(frozen=True, slots=True)
class UpdateCandidate:
    """Available module upgrade summary aggregated across intermediate releases."""

    module_id: ModuleId
    current_version: SemVer4
    latest_version: SemVer4
    max_urgency: ReleaseUrgency
    summaries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"UpdateCandidate.module_id must be ModuleId, got {self.module_id!r}")
        if not isinstance(self.current_version, SemVer4):
            raise ValueError(f"UpdateCandidate.current_version must be SemVer4, got {self.current_version!r}")
        if not isinstance(self.latest_version, SemVer4):
            raise ValueError(f"UpdateCandidate.latest_version must be SemVer4, got {self.latest_version!r}")
        if not isinstance(self.max_urgency, ReleaseUrgency):
            raise ValueError(
                f"UpdateCandidate.max_urgency must be ReleaseUrgency, got {self.max_urgency!r}"
            )
        object.__setattr__(
            self,
            "summaries",
            require_typed_tuple(self.summaries, str, "UpdateCandidate.summaries"),
        )


@dataclass(frozen=True, slots=True)
class UpdateCheckReport:
    """Throttled non-blocking update check result."""

    candidates: tuple[UpdateCandidate, ...] = ()
    yscb_host_drift: bool = False
    checked_at_utc: str = ""
    throttled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidates",
            require_typed_tuple(self.candidates, UpdateCandidate, "UpdateCheckReport.candidates"),
        )
        require_pure_bool(self.yscb_host_drift, "UpdateCheckReport.yscb_host_drift")
        require_pure_str(self.checked_at_utc, "UpdateCheckReport.checked_at_utc")
        require_pure_bool(self.throttled, "UpdateCheckReport.throttled")


def ins_utc_now_iso(epoch_sec: Optional[float] = None) -> str:
    """Format a UTC epoch timestamp as an ISO-8601 Z string."""
    ts = time.time() if epoch_sec is None else epoch_sec
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ins_is_build_spec(version_spec: Optional[str]) -> bool:
    """Return True when a version_spec string targets a local build artifact."""
    if version_spec is None:
        return False
    cleaned = version_spec.strip()
    if not cleaned:
        return False
    if cleaned in ("build", "@build", "==build", "=build") or cleaned.endswith(".build"):
        return True
    try:
        return SemVer4.parse(cleaned.lstrip("=")).is_build
    except ValueError:
        return False


def ins_is_build_request(req: PackageRequest) -> bool:
    """Return True when a PackageRequest targets a local build package."""
    return req.is_build or ins_is_build_spec(req.version_spec)


def ins_assert_not_reserved_module_id(
    mod_id: ModuleId,
    *,
    code: ErrorCode = ErrorCode.CONFIG_INVALID,
    label: str = "module_id",
) -> None:
    if mod_id.value in INS_RESERVED_NON_MODULE_IDS:
        raise YscbError(
            code,
            f"{label} cannot use reserved system identifier {mod_id.value!r}.",
        )


def _parse_dep_dict(raw_deps: object, *, context_label: str) -> dict[ModuleId, VersionConstraint]:
    if not isinstance(raw_deps, Mapping):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid dependencies object in {context_label}: expected JSON object.",
        )
    parsed: dict[ModuleId, VersionConstraint] = {}
    for raw_k, raw_v in raw_deps.items():
        if type(raw_k) is not str or type(raw_v) is not str:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid dependency entry in {context_label}: expected string key/value.",
            )
        try:
            mod_k = ModuleId(raw_k)
            ver_c = VersionConstraint.parse(raw_v)
        except ValueError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid dependency specification '{raw_k}: {raw_v}' in {context_label}: {exc}",
            ) from exc
        ins_assert_not_reserved_module_id(
            mod_k,
            code=ErrorCode.PACKAGE_INTEGRITY_ERROR,
            label=f"Dependency key in {context_label}",
        )
        parsed[mod_k] = ver_c
    return parsed


def _parse_release_urgency(raw_urgency: object, raw_type: object, *, context_label: str) -> ReleaseUrgency:
    if raw_urgency is not None and type(raw_urgency) is not str:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid urgency field in {context_label}: expected string.",
        )
    if raw_type is not None and type(raw_type) is not str:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid release type field in {context_label}: expected string.",
        )
    urg_str = (raw_urgency or "").strip().lower() if isinstance(raw_urgency, str) else ""
    type_str = (raw_type or "").strip().lower() if isinstance(raw_type, str) else ""
    if urg_str == "critical" or type_str == "hotfix":
        return ReleaseUrgency.CRITICAL
    if urg_str == "optional":
        return ReleaseUrgency.OPTIONAL
    if urg_str in ("", "recommended"):
        return ReleaseUrgency.RECOMMENDED
    raise YscbError(
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
        f"Unsupported release urgency {raw_urgency!r} in {context_label}.",
    )


def ins_parse_remote_index(raw_doc: JsonObject, expected_module_id: ModuleId) -> RemoteModuleIndex:
    """Validate and decode a JSON index payload into an immutable RemoteModuleIndex."""
    ins_assert_not_reserved_module_id(
        expected_module_id,
        code=ErrorCode.PACKAGE_INTEGRITY_ERROR,
        label="index.json module_id",
    )
    if not isinstance(raw_doc, Mapping):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid index.json for '{expected_module_id}': expected JSON object.",
        )
    for id_field in ("module_id", "name"):
        if id_field in raw_doc:
            raw_id = raw_doc[id_field]
            if type(raw_id) is not str:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Invalid {id_field} in index.json for '{expected_module_id}'.",
                )
            try:
                parsed_id = ModuleId(raw_id)
            except ValueError as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Malformed {id_field} in index.json for '{expected_module_id}': {exc}",
                ) from exc
            if parsed_id != expected_module_id:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Index module mismatch: expected '{expected_module_id}', got '{parsed_id}'.",
                )

    raw_versions = raw_doc.get("versions", ())
    if not isinstance(raw_versions, (list, tuple)):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid 'versions' list in index.json for '{expected_module_id}'.",
        )
    parsed_versions: list[SemVer4] = []
    for item in raw_versions:
        if type(item) is not str:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Non-string version entry in index.json for '{expected_module_id}'.",
            )
        try:
            parsed_versions.append(SemVer4.parse(item))
        except ValueError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid SemVer4 '{item}' in index.json for '{expected_module_id}': {exc}",
            ) from exc

    raw_releases = raw_doc.get("releases", {})
    if not isinstance(raw_releases, Mapping):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid 'releases' map in index.json for '{expected_module_id}'.",
        )
    releases_map: dict[str, IndexReleaseRecord] = {}
    for ver_key, entry in raw_releases.items():
        if type(ver_key) is not str or not isinstance(entry, Mapping):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid release record for '{expected_module_id}' at key {ver_key!r}.",
            )
        label = f"index.json[{expected_module_id}@{ver_key}]"
        try:
            rec_ver = SemVer4.parse(ver_key)
        except ValueError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid release version key {ver_key!r} in {label}: {exc}",
            ) from exc
        if "version" in entry and entry["version"] is not None:
            raw_inner_ver = entry["version"]
            if type(raw_inner_ver) is not str:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Invalid inner version field in {label}: expected string.",
                )
            try:
                inner_ver = SemVer4.parse(raw_inner_ver)
            except ValueError as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Invalid inner version {raw_inner_ver!r} in {label}: {exc}",
                ) from exc
            if inner_ver != rec_ver:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Release key {ver_key!r} mismatches inner version {raw_inner_ver!r} in {label}.",
                )
        canon_key = str(rec_ver)
        if canon_key in releases_map:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Duplicate canonical release version {canon_key!r} in index.json for '{expected_module_id}'.",
            )
        raw_sha = entry.get("sha256", "")
        if type(raw_sha) is not str:
            raise YscbError(ErrorCode.PACKAGE_INTEGRITY_ERROR, f"Invalid sha256 in {label}.")
        clean_sha = raw_sha.strip().lower()
        if clean_sha and _SHA256_HEX_RE.fullmatch(clean_sha) is None:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Malformed sha256 digest {raw_sha!r} in {label}.",
            )
        raw_status = entry.get("status", "active")
        if type(raw_status) is not str or raw_status not in ("active", "pruned"):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Invalid release status {raw_status!r} in {label}.",
            )
        deps_arg: Mapping[ModuleId, VersionConstraint] = (
            _parse_dep_dict(entry["dependencies"], context_label=label)
            if "dependencies" in entry
            else _UNSET_DEPS_SENTINEL
        )
        urgency = _parse_release_urgency(
            entry.get("urgency"),
            entry.get("type"),
            context_label=label,
        )
        raw_summary = entry.get("summary", "")
        if type(raw_summary) is not str:
            raise YscbError(ErrorCode.PACKAGE_INTEGRITY_ERROR, f"Invalid summary in {label}.")
        raw_yanked = entry.get("yanked", False)
        if type(raw_yanked) is not bool:
            raise YscbError(ErrorCode.PACKAGE_INTEGRITY_ERROR, f"Invalid yanked flag in {label}.")
        releases_map[canon_key] = IndexReleaseRecord(
            version=rec_ver,
            sha256=clean_sha,
            status=raw_status,
            dependencies=deps_arg,
            urgency=urgency,
            summary=raw_summary,
            yanked=raw_yanked,
        )

    return RemoteModuleIndex(
        module_id=expected_module_id,
        versions=tuple(parsed_versions),
        releases=releases_map,
    )


def ins_encode_remote_index(index: RemoteModuleIndex) -> MutableJsonObject:
    """Serialize a RemoteModuleIndex into a strict JSON-compatible dictionary."""
    releases_out: MutableJsonObject = {}
    for ver_key, rec in index.releases.items():
        rel_entry: MutableJsonObject = {
            "sha256": rec.sha256,
            "status": rec.status,
            "urgency": rec.urgency.value,
            "summary": rec.summary,
            "yanked": rec.yanked,
        }
        if ins_has_dependencies_override(rec):
            rel_entry["dependencies"] = {
                mod_id.value: constraint.raw for mod_id, constraint in rec.dependencies.items()
            }
        releases_out[ver_key] = rel_entry
    return {
        "module_id": index.module_id.value,
        "versions": [str(ver) for ver in index.versions],
        "releases": releases_out,
    }


def ins_parse_manifest_dict(
    raw_doc: JsonObject,
    *,
    expected_module_id: Optional[ModuleId] = None,
) -> ModuleManifest:
    """Parse and validate a manifest.json 2.0 dictionary into a ModuleManifest."""
    label = f"manifest.json({expected_module_id})" if expected_module_id is not None else "manifest.json"
    try:
        return parse_manifest_dict(raw_doc, expected_id=expected_module_id)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.PACKAGE_INTEGRITY_ERROR:
            raise
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid {label}: {exc.detail.message}",
        ) from exc


def ins_override_manifest_dependencies(
    manifest: ModuleManifest,
    dependencies: Mapping[ModuleId, VersionConstraint],
) -> ModuleManifest:
    """Return a copy of ModuleManifest with overridden dependencies."""
    return ModuleManifest(
        id=manifest.id,
        version=manifest.version,
        description=manifest.description,
        schema_version=manifest.schema_version,
        entry=manifest.entry,
        dependencies=dict(dependencies),
        optional=manifest.optional,
        pip_dependencies=manifest.pip_dependencies,
        venv_group=manifest.venv_group,
        eager_warmup=manifest.eager_warmup,
        onboarding=manifest.onboarding,
        release=manifest.release,
    )


def ins_rewrite_manifest_dependencies_json(
    raw_doc: JsonObject,
    dependencies: Mapping[ModuleId, VersionConstraint],
) -> MutableJsonObject:
    """Build an updated manifest.json 2.0 dict with overridden dependencies."""
    updated: MutableJsonObject = dict(raw_doc)
    updated["schema_version"] = 2
    updated["dependencies"] = {
        mod_id.value: constraint.raw for mod_id, constraint in dependencies.items()
    }
    return updated


class InsZipPathCollisionTracker:
    """Cross-platform casefold ancestor consistency and file/directory prefix collision guard."""

    def __init__(self) -> None:
        self._dirs_by_folded: dict[str, tuple[str, str]] = {}
        self._files_by_folded: dict[str, str] = {}

    def register(
        self,
        parts: tuple[str, ...],
        *,
        is_dir: bool,
        raw_name: str,
        archive_label: str,
    ) -> None:
        dir_depth_end = len(parts) + 1 if is_dir else len(parts)
        for depth in range(1, dir_depth_end):
            dir_slice = parts[:depth]
            exact_dir = "/".join(dir_slice)
            folded_dir = "/".join(seg.casefold() for seg in dir_slice)
            prev_file = self._files_by_folded.get(folded_dir)
            if prev_file is not None:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"File/directory path collision between {prev_file!r} and {raw_name!r} in '{archive_label}'.",
                )
            prev_dir = self._dirs_by_folded.get(folded_dir)
            if prev_dir is not None:
                prev_exact, prev_raw = prev_dir
                if prev_exact != exact_dir:
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Case-inconsistent directory path between {prev_raw!r} and {raw_name!r} in '{archive_label}'.",
                    )
            else:
                self._dirs_by_folded[folded_dir] = (exact_dir, raw_name)

        if not is_dir:
            folded_file = "/".join(seg.casefold() for seg in parts)
            prev_file_hit = self._files_by_folded.get(folded_file)
            if prev_file_hit is not None:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Duplicate or case-colliding zip entries {prev_file_hit!r} and {raw_name!r} in '{archive_label}'.",
                )
            prev_dir_hit = self._dirs_by_folded.get(folded_file)
            if prev_dir_hit is not None:
                _prev_exact, prev_dir_raw = prev_dir_hit
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Directory/file path collision between {prev_dir_raw!r} and {raw_name!r} in '{archive_label}'.",
                )
            self._files_by_folded[folded_file] = raw_name


def ins_open_verified_zip_stream(zip_path: HostPath) -> BinaryIO:
    """Open a regular non-symlink zip archive via O_NOFOLLOW|O_NONBLOCK and verify S_ISREG and size bounds."""
    if not isinstance(zip_path, HostPath):
        raise ValueError(f"zip_path must be HostPath, got {zip_path!r}")
    raw_zip = str(zip_path)
    if is_symlink_or_reparse(raw_zip) or has_symlink_raw_path(raw_zip):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Refusing symlink or reparse zip archive path: '{zip_path}'.",
        )
    try:
        st = os.lstat(raw_zip)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Package zip archive not found or unreadable at '{zip_path}': {safe_exception_summary(exc)}",
        ) from exc
    if not stat.S_ISREG(st.st_mode):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Package zip archive is not a regular file: '{zip_path}'.",
        )
    if st.st_size > INS_MAX_ZIP_ARCHIVE_BYTES:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Package zip archive '{zip_path}' exceeds {INS_MAX_ZIP_ARCHIVE_BYTES} bytes limit.",
        )

    try:
        fd = os.open(raw_zip, _ZIP_NOFOLLOW_OPEN_FLAGS)
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed opening package zip archive '{zip_path}': {safe_exception_summary(exc)}",
        ) from exc
    try:
        f_st = os.fstat(fd)
        if not stat.S_ISREG(f_st.st_mode):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Package zip archive is not a regular file: '{zip_path}'.",
            )
        if not IS_WINDOWS and (f_st.st_dev, f_st.st_ino) != (st.st_dev, st.st_ino):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Detected file swap race while opening zip archive '{zip_path}'.",
            )
        if f_st.st_size > INS_MAX_ZIP_ARCHIVE_BYTES:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Package zip archive '{zip_path}' exceeds {INS_MAX_ZIP_ARCHIVE_BYTES} bytes limit.",
            )
        if not IS_WINDOWS:
            os.set_blocking(fd, True)
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def ins_validate_zip_member_info(info: zipfile.ZipInfo, *, archive_label: str) -> tuple[str, ...]:
    """Validate a ZipInfo entry against Zip Slip, Windows reserved names, control chars, and symlinks."""
    raw_name = info.filename
    if type(raw_name) is not str or not raw_name or "\x00" in raw_name:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Empty or NUL-containing zip entry in '{archive_label}'.",
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_name):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Control characters forbidden in zip entry {raw_name!r} of '{archive_label}'.",
        )
    if raw_name.startswith(("/", "\\")) or ":" in raw_name or "\\" in raw_name:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Zip Slip path syntax rejected in entry {raw_name!r} of '{archive_label}'.",
        )
    if info.flag_bits & 0x1:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Encrypted zip entry {raw_name!r} forbidden in '{archive_label}'.",
        )
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Unsupported zip compression method {info.compress_type} on {raw_name!r} in '{archive_label}'.",
        )
    unix_mode = info.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Symbolic link entry {raw_name!r} forbidden in zip archive '{archive_label}'.",
        )
    if unix_mode != 0:
        file_fmt = stat.S_IFMT(unix_mode)
        if file_fmt != 0 and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Special device/FIFO entry {raw_name!r} forbidden in zip archive '{archive_label}'.",
            )

    is_dir = info.is_dir() or raw_name.endswith("/")
    if not is_dir and info.compress_type == zipfile.ZIP_STORED and info.file_size != info.compress_size:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Mismatched stored zip entry size on {raw_name!r} in '{archive_label}'.",
        )
    trimmed = raw_name[:-1] if raw_name.endswith("/") else raw_name
    if not trimmed:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Invalid root-only directory entry {raw_name!r} in '{archive_label}'.",
        )
    parts = tuple(trimmed.split("/"))
    if any(not seg or seg in (".", "..") or not is_valid_relative_segment(seg) for seg in parts):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Unsafe or traversing zip entry path {raw_name!r} in '{archive_label}'.",
        )
    return () if (is_dir and not parts) else parts


def ins_verify_zip_archive(
    zip_path: HostPath,
    *,
    expected_sha256: Optional[str] = None,
    ignore_sha256: bool = False,
) -> None:
    """Verify regular non-symlink file status, SHA-256 digest, Zip format, Zip Slip, bomb bounds, and CRC."""
    if not isinstance(zip_path, HostPath):
        raise ValueError(f"zip_path must be HostPath, got {zip_path!r}")
    require_pure_bool(ignore_sha256, "ignore_sha256")
    if expected_sha256 is not None:
        require_pure_str(expected_sha256, "expected_sha256")

    raw_zip = str(zip_path)
    with ins_open_verified_zip_stream(zip_path) as raw_stream:
        if not ignore_sha256 and expected_sha256 is not None:
            exp_clean = expected_sha256.strip().lower()
            if _SHA256_HEX_RE.fullmatch(exp_clean) is None:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Invalid expected SHA-256 digest {expected_sha256!r} for '{zip_path}'.",
                )
            try:
                raw_stream.seek(0)
                hasher = hashlib.sha256()
                hashed_bytes = 0
                while True:
                    chunk = raw_stream.read(65536)
                    if not chunk:
                        break
                    hashed_bytes += len(chunk)
                    if hashed_bytes > INS_MAX_ZIP_ARCHIVE_BYTES:
                        raise YscbError(
                            ErrorCode.PACKAGE_INTEGRITY_ERROR,
                            f"Zip archive '{zip_path}' exceeds {INS_MAX_ZIP_ARCHIVE_BYTES} bytes limit.",
                        )
                    hasher.update(chunk)
                raw_stream.seek(0)
            except YscbError:
                raise
            except OSError as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Failed hashing zip archive '{zip_path}': {safe_exception_summary(exc)}",
                ) from exc
            actual_sha = hasher.hexdigest()
            if actual_sha != exp_clean:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"SHA-256 mismatch for '{zip_path}': expected {exp_clean}, got {actual_sha}.",
                )

        try:
            with zipfile.ZipFile(raw_stream, "r") as zf:
                infos = zf.infolist()
                if len(infos) > INS_MAX_ZIP_MEMBERS:
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Zip archive '{zip_path}' contains {len(infos)} entries, exceeding {INS_MAX_ZIP_MEMBERS} limit.",
                    )
                collision_tracker = InsZipPathCollisionTracker()
                total_uncompressed = 0
                for info in infos:
                    parts = ins_validate_zip_member_info(info, archive_label=raw_zip)
                    if not parts:
                        continue
                    is_dir_entry = info.is_dir() or info.filename.endswith("/")
                    collision_tracker.register(
                        parts,
                        is_dir=is_dir_entry,
                        raw_name=info.filename,
                        archive_label=raw_zip,
                    )
                    if is_dir_entry:
                        continue
                    if info.file_size > INS_MAX_ZIP_SINGLE_BYTES:
                        raise YscbError(
                            ErrorCode.PACKAGE_INTEGRITY_ERROR,
                            f"Zip entry {info.filename!r} in '{zip_path}' exceeds {INS_MAX_ZIP_SINGLE_BYTES} bytes limit.",
                        )
                    entry_bytes = 0
                    with zf.open(info, "r") as zf_stream:
                        while True:
                            chunk = zf_stream.read(65536)
                            if not chunk:
                                break
                            entry_bytes += len(chunk)
                            total_uncompressed += len(chunk)
                            if entry_bytes > INS_MAX_ZIP_SINGLE_BYTES:
                                raise YscbError(
                                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                    f"Decompressed zip entry {info.filename!r} exceeded {INS_MAX_ZIP_SINGLE_BYTES} bytes limit.",
                                )
                            if total_uncompressed > INS_MAX_ZIP_TOTAL_BYTES:
                                raise YscbError(
                                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                    f"Decompressed zip archive '{zip_path}' exceeded {INS_MAX_ZIP_TOTAL_BYTES} total bytes limit.",
                                )
                            if entry_bytes >= INS_ZIP_RATIO_CHECK_MIN_BYTES and (
                                info.compress_size <= 0
                                or entry_bytes > info.compress_size * INS_MAX_ZIP_COMPRESSION_RATIO
                            ):
                                raise YscbError(
                                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                    f"Zip entry {info.filename!r} in '{zip_path}' exceeded compression ratio limit ({INS_MAX_ZIP_COMPRESSION_RATIO}:1).",
                                )
        except YscbError:
            raise
        except (
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            zlib.error,
            EOFError,
            OSError,
            ValueError,
            RuntimeError,
            NotImplementedError,
        ) as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Corrupted or invalid zip archive '{zip_path}': {safe_exception_summary(exc)}",
            ) from exc


def ins_peek_zip_manifest(
    zip_path: HostPath,
    *,
    expected_module_id: Optional[ModuleId] = None,
    expected_version: Optional[SemVer4] = None,
) -> ModuleManifest:
    """Read and validate manifest.json directly from a regular non-symlink zip archive."""
    raw_zip = str(zip_path)
    try:
        with ins_open_verified_zip_stream(zip_path) as raw_stream, zipfile.ZipFile(raw_stream, "r") as zf:
            try:
                mf_info = zf.getinfo("manifest.json")
            except KeyError as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Archive '{zip_path}' is missing root manifest.json.",
                ) from exc
            ins_validate_zip_member_info(mf_info, archive_label=raw_zip)
            if mf_info.file_size > MAX_JSON_FILE_BYTES:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"manifest.json in '{zip_path}' exceeds size limit.",
                )
            with zf.open(mf_info, "r") as mf_in:
                raw_bytes = mf_in.read(MAX_JSON_FILE_BYTES + 1)
            if len(raw_bytes) > MAX_JSON_FILE_BYTES:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Decompressed manifest.json in '{zip_path}' exceeds {MAX_JSON_FILE_BYTES} bytes limit.",
                )
    except YscbError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
        EOFError,
        OSError,
        ValueError,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed reading manifest.json from '{zip_path}': {safe_exception_summary(exc)}",
        ) from exc
    try:
        doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Malformed manifest.json in '{zip_path}': {safe_exception_summary(exc)}",
        ) from exc
    parsed_mf = ins_parse_manifest_dict(doc, expected_module_id=expected_module_id)
    if expected_version is not None and parsed_mf.version != expected_version:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Package manifest version '{parsed_mf.version}' in '{zip_path}' does not match expected version '{expected_version}'.",
        )
    return parsed_mf


def ins_read_manifest_file(
    manifest_path: HostPath,
    *,
    expected_module_id: Optional[ModuleId] = None,
) -> Optional[ModuleManifest]:
    """Read and parse a regular non-symlink manifest.json file, returning None if absent."""
    try:
        raw_bytes = read_nofollow_regular_bytes(str(manifest_path), max_bytes=MAX_JSON_FILE_BYTES)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed reading manifest.json at '{manifest_path}': {safe_exception_summary(exc)}",
        ) from exc
    if raw_bytes is None:
        if os.path.lexists(str(manifest_path)):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Refusing symlink, non-regular, or oversized manifest.json at '{manifest_path}'.",
            )
        return None
    try:
        doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Malformed manifest.json at '{manifest_path}': {safe_exception_summary(exc)}",
        ) from exc
    return ins_parse_manifest_dict(doc, expected_module_id=expected_module_id)


def _make_path_writable(raw_path: str) -> None:
    if not raw_path or is_symlink_or_reparse(raw_path):
        return
    try:
        st = os.lstat(raw_path)
        if stat.S_ISLNK(st.st_mode):
            return
        cur_mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISDIR(st.st_mode):
            extra = (stat.S_IWRITE | stat.S_IREAD) if IS_WINDOWS else (stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
        else:
            extra = stat.S_IWRITE | stat.S_IREAD
        os.chmod(raw_path, cur_mode | extra)
    except OSError:
        return


def _unlink_single_nonsymlink_or_link(raw_entry: str) -> None:
    if is_symlink_or_reparse(raw_entry):
        try:
            os.unlink(raw_entry)
            return
        except FileNotFoundError:
            return
        except OSError:
            try:
                os.rmdir(raw_entry)
            except FileNotFoundError:
                return
            return
    try:
        os.unlink(raw_entry)
    except FileNotFoundError:
        return
    except PermissionError:
        _make_path_writable(os.path.dirname(raw_entry))
        _make_path_writable(raw_entry)
        try:
            os.unlink(raw_entry)
        except FileNotFoundError:
            return


def _iterative_rmtree_once(raw_root: str) -> None:
    if not os.path.lexists(raw_root):
        return
    if is_symlink_or_reparse(raw_root):
        _unlink_single_nonsymlink_or_link(raw_root)
        return
    try:
        top_st = os.lstat(raw_root)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(top_st.st_mode):
        _unlink_single_nonsymlink_or_link(raw_root)
        return
    stack: list[tuple[str, bool]] = [(raw_root, False)]
    while stack:
        cur_dir, visited = stack.pop()
        if visited:
            _make_path_writable(cur_dir)
            try:
                os.rmdir(cur_dir)
            except FileNotFoundError:
                pass
            continue
        _make_path_writable(cur_dir)
        stack.append((cur_dir, True))
        try:
            with os.scandir(cur_dir) as it:
                entries = list(it)
        except FileNotFoundError:
            stack.pop()
            continue
        for ent in entries:
            ent_path = ent.path
            if ent.is_symlink() or is_symlink_or_reparse(ent_path):
                _unlink_single_nonsymlink_or_link(ent_path)
            elif ent.is_dir(follow_symlinks=False):
                stack.append((ent_path, False))
            else:
                _unlink_single_nonsymlink_or_link(ent_path)


def ins_robust_rmtree(raw_dir: str) -> None:
    """Remove a file or directory tree clearing OS read-only bits without following symlinks."""
    if not raw_dir or not os.path.lexists(raw_dir):
        return
    for attempt in range(4):
        if not os.path.lexists(raw_dir):
            return
        try:
            _iterative_rmtree_once(raw_dir)
            return
        except OSError:
            if not os.path.lexists(raw_dir):
                return
            if attempt == 3:
                raise
            time.sleep(0.02 * (attempt + 1))
