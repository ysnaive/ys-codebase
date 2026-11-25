"""Strongly-typed immutable representation and validation for manifest.json 2.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import threading
from types import MappingProxyType
from typing import ClassVar, Final, Mapping, Optional
from weakref import WeakKeyDictionary

from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    ModuleId,
    TaskId,
    SemVer4,
    VersionConstraint,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
    validate_relative_segment,
)

CFG_RESERVED_NON_MODULE_IDS: Final[frozenset[str]] = frozenset({"locks", "wheels", "daemon", "project"})
_CFG_MANIFEST_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "id",
        "version",
        "description",
        "entry",
        "dependencies",
        "optional",
        "pip_dependencies",
        "venv_group",
        "eager_warmup",
        "onboarding",
        "release",
    }
)
_CFG_RELEASE_META_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {"type", "release_type", "urgency", "summary"}
)
_CFG_OPTIONAL_SPEC_ALLOWED_KEYS: Final[frozenset[str]] = frozenset({"version", "hint"})
_CFG_VENV_GROUP_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")
_CFG_PEP503_SEP_RE: Final[re.Pattern[str]] = re.compile(r"[-_.]+")
_CFG_PEP503_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_CFG_PEP440_CLAUSE_OP_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"^(===|~=|==|!=|<=|>=|<|>)\s+")
_CFG_PEP440_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:===|~=|==|!=|<=|>=|<|>)[0-9A-Za-z][0-9A-Za-z.*+!_-]*$"
)


def cfg_assert_not_reserved_module_id(mod_id: ModuleId, label: str) -> None:
    if mod_id.value in CFG_RESERVED_NON_MODULE_IDS:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"{label} cannot use reserved system identifier {mod_id.value!r}",
        )


def _cfg_has_control_chars(text: str) -> bool:
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text)


def _cfg_validate_pure_str(
    val: object,
    label: str,
    *,
    non_empty: bool = False,
    forbid_control: bool = False,
) -> str:
    try:
        checked = require_pure_str(val, label, non_empty=non_empty)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
    if forbid_control and _cfg_has_control_chars(checked):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"{label} must not contain control characters: {checked!r}",
        )
    return checked


def _cfg_validate_entry_rel_path(raw_entry: object) -> str:
    entry = _cfg_validate_pure_str(
        raw_entry,
        "ModuleManifest.entry",
        non_empty=True,
        forbid_control=True,
    )
    if "\\" in entry or entry.startswith("/") or entry.endswith("/"):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"ModuleManifest.entry must be a normalized POSIX relative path, got {entry!r}",
        )
    segments = entry.split("/")
    if not segments or any(not seg for seg in segments):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"ModuleManifest.entry contains empty path segment: {entry!r}",
        )
    for seg in segments:
        try:
            validate_relative_segment(seg, label="ModuleManifest.entry segment")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
    return "/".join(segments)


def _cfg_validate_venv_group(raw_group: Optional[str]) -> Optional[str]:
    if raw_group is None:
        return None
    group = _cfg_validate_pure_str(
        raw_group,
        "ModuleManifest.venv_group",
        non_empty=True,
        forbid_control=True,
    ).strip()
    if (
        not is_valid_relative_segment(group)
        or _CFG_VENV_GROUP_RE.fullmatch(group) is None
        or group.startswith("mod_")
    ):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Invalid ModuleManifest.venv_group (must be safe identifier not starting with 'mod_'): {raw_group!r}",
        )
    return group


def _cfg_freeze_dependencies(
    raw: object,
) -> Mapping[ModuleId, VersionConstraint]:
    if not isinstance(raw, Mapping):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"ModuleManifest.dependencies must be a Mapping, got {type(raw).__name__}",
        )
    out: dict[ModuleId, VersionConstraint] = {}
    for mod_id, constraint in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.dependencies keys must be ModuleId, got {mod_id!r}",
            )
        cfg_assert_not_reserved_module_id(mod_id, "ModuleManifest.dependencies key")
        if not isinstance(constraint, VersionConstraint):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.dependencies[{mod_id}] must be VersionConstraint, got {constraint!r}",
            )
        out[mod_id] = constraint
    return MappingProxyType(out)


def _cfg_freeze_optional_dependencies(
    raw: object,
) -> Mapping[ModuleId, OptionalDependencySpec]:
    if not isinstance(raw, Mapping):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"ModuleManifest.optional must be a Mapping, got {type(raw).__name__}",
        )
    out: dict[ModuleId, OptionalDependencySpec] = {}
    for mod_id, spec in raw.items():
        if not isinstance(mod_id, ModuleId):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.optional keys must be ModuleId, got {mod_id!r}",
            )
        cfg_assert_not_reserved_module_id(mod_id, "ModuleManifest.optional key")
        if not isinstance(spec, OptionalDependencySpec):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.optional[{mod_id}] must be OptionalDependencySpec, got {spec!r}",
            )
        out[mod_id] = spec
    return MappingProxyType(out)


def _cfg_normalize_pep503_token(raw_token: str, *, label: str) -> str:
    collapsed = _CFG_PEP503_SEP_RE.sub("-", raw_token.strip()).lower()
    if not collapsed or _CFG_PEP503_NAME_RE.fullmatch(collapsed) is None:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Invalid {label} in ModuleManifest.pip_dependencies: {raw_token!r}",
        )
    return collapsed


def _cfg_normalize_pip_package_key(clean_pkg: str, raw_pkg: object) -> str:
    if "[" not in clean_pkg and "]" not in clean_pkg:
        return _cfg_normalize_pep503_token(clean_pkg, label="pip package name")
    if not clean_pkg.endswith("]") or clean_pkg.count("[") != 1 or clean_pkg.count("]") != 1:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Malformed extras in ModuleManifest.pip_dependencies key: {raw_pkg!r}",
        )
    base_part, extras_part = clean_pkg[:-1].split("[", 1)
    canon_base = _cfg_normalize_pep503_token(base_part, label="pip package name")
    raw_extras = [item.strip() for item in extras_part.split(",")]
    if not raw_extras or any(not item for item in raw_extras):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Empty extra identifier in ModuleManifest.pip_dependencies key: {raw_pkg!r}",
        )
    norm_extras: list[str] = []
    seen_extras: set[str] = set()
    for extra_item in raw_extras:
        canon_extra = _cfg_normalize_pep503_token(extra_item, label="pip package extra")
        if canon_extra in seen_extras:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Duplicate extra '{canon_extra}' in ModuleManifest.pip_dependencies key: {raw_pkg!r}",
            )
        seen_extras.add(canon_extra)
        norm_extras.append(canon_extra)
    norm_extras.sort()
    return f"{canon_base}[{','.join(norm_extras)}]" 


def _cfg_validate_pip_version_spec(clean_spec: str, clean_pkg: str, raw_spec: object) -> None:
    if clean_spec.startswith("-"):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Option flag syntax forbidden in ModuleManifest.pip_dependencies[{clean_pkg!r}]: {raw_spec!r}",
        )
    if not clean_spec or clean_spec == "*":
        return
    parts = [seg.strip() for seg in clean_spec.split(",")]
    if not parts or any(not seg for seg in parts):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Malformed comma clause in ModuleManifest.pip_dependencies[{clean_pkg!r}]: {raw_spec!r}",
        )
    for seg in parts:
        compact = _CFG_PEP440_CLAUSE_OP_SPACE_RE.sub(r"\1", seg)
        if compact in ("*", "==*"):
            continue
        if _CFG_PEP440_CLAUSE_RE.fullmatch(compact) is None:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Invalid PEP 440 version specifier {seg!r} in ModuleManifest.pip_dependencies[{clean_pkg!r}]: {raw_spec!r}",
            )


def _cfg_freeze_pip_dependencies(raw: object) -> Mapping[str, str]:
    if not isinstance(raw, Mapping):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"ModuleManifest.pip_dependencies must be a Mapping, got {type(raw).__name__}",
        )
    out: dict[str, str] = {}
    seen_canonical: dict[str, str] = {}
    for pkg_name, ver_spec in raw.items():
        clean_pkg = _cfg_validate_pure_str(
            pkg_name,
            "ModuleManifest.pip_dependencies key",
            non_empty=True,
            forbid_control=True,
        ).strip()
        canon_pkg = _cfg_normalize_pip_package_key(clean_pkg, pkg_name)
        if canon_pkg in seen_canonical:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Duplicate normalized PEP 503 package key {pkg_name!r} (collides with {seen_canonical[canon_pkg]!r}) in ModuleManifest.pip_dependencies",
            )
        seen_canonical[canon_pkg] = str(pkg_name)
        clean_spec = _cfg_validate_pure_str(
            ver_spec,
            f"ModuleManifest.pip_dependencies[{canon_pkg!r}]",
            non_empty=False,
            forbid_control=True,
        ).strip()
        _cfg_validate_pip_version_spec(clean_spec, canon_pkg, ver_spec)
        out[canon_pkg] = clean_spec
    return MappingProxyType(out)


class ReleaseUrgency(Enum):
    """Urgency classification for module release metadata."""

    OPTIONAL = "optional"
    RECOMMENDED = "recommended"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class OptionalDependencySpec:
    """Optional peer module dependency specification and capability hint."""

    version: VersionConstraint
    hint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.version, VersionConstraint):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"OptionalDependencySpec.version must be VersionConstraint, got {self.version!r}",
            )
        _cfg_validate_pure_str(self.hint, "OptionalDependencySpec.hint")


@dataclass(frozen=True, slots=True)
class ReleaseMeta:
    """Release note metadata attached to a module manifest."""

    release_type: str = "patch"
    urgency: ReleaseUrgency = ReleaseUrgency.RECOMMENDED
    summary: str = ""

    def __post_init__(self) -> None:
        clean_type = _cfg_validate_pure_str(
            self.release_type,
            "ReleaseMeta.release_type",
            non_empty=True,
            forbid_control=True,
        ).strip()
        if not isinstance(self.urgency, ReleaseUrgency):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ReleaseMeta.urgency must be ReleaseUrgency, got {self.urgency!r}",
            )
        _cfg_validate_pure_str(self.summary, "ReleaseMeta.summary")
        object.__setattr__(self, "release_type", clean_type)


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Strongly-typed immutable representation of manifest.json 2.0."""

    id: ModuleId
    version: SemVer4
    description: str
    schema_version: int = 2
    entry: str = "module_entry.py"
    dependencies: Mapping[ModuleId, VersionConstraint] = field(default_factory=dict)
    optional: Mapping[ModuleId, OptionalDependencySpec] = field(default_factory=dict)
    pip_dependencies: Mapping[str, str] = field(default_factory=dict)
    venv_group: Optional[str] = None
    eager_warmup: bool = False
    onboarding: tuple[str, ...] = ()
    release: Optional[ReleaseMeta] = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ModuleId):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.id must be ModuleId, got {self.id!r}",
            )
        cfg_assert_not_reserved_module_id(self.id, "ModuleManifest.id")
        if not isinstance(self.version, SemVer4):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.version must be SemVer4, got {self.version!r}",
            )
        _cfg_validate_pure_str(self.description, "ModuleManifest.description", non_empty=True)
        try:
            ver_num = require_pure_int(self.schema_version, "ModuleManifest.schema_version")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        if ver_num != 2:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.schema_version must be 2, got {ver_num!r}",
            )
        clean_entry = _cfg_validate_entry_rel_path(self.entry)
        frozen_deps = _cfg_freeze_dependencies(self.dependencies)
        frozen_opt = _cfg_freeze_optional_dependencies(self.optional)
        frozen_pip = _cfg_freeze_pip_dependencies(self.pip_dependencies)
        clean_group = _cfg_validate_venv_group(self.venv_group)
        try:
            require_pure_bool(self.eager_warmup, "ModuleManifest.eager_warmup")
            onboarding_tup = require_typed_tuple(self.onboarding, str, "ModuleManifest.onboarding")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        for cmd in onboarding_tup:
            _cfg_validate_pure_str(
                cmd,
                "ModuleManifest.onboarding item",
                non_empty=True,
                forbid_control=True,
            )
        if self.release is not None and not isinstance(self.release, ReleaseMeta):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"ModuleManifest.release must be ReleaseMeta or None, got {self.release!r}",
            )
        object.__setattr__(self, "entry", clean_entry)
        object.__setattr__(self, "dependencies", frozen_deps)
        object.__setattr__(self, "optional", frozen_opt)
        object.__setattr__(self, "pip_dependencies", frozen_pip)
        object.__setattr__(self, "venv_group", clean_group)
        object.__setattr__(self, "onboarding", onboarding_tup)

    @property
    def is_tier1(self) -> bool:
        return bool(self.pip_dependencies)


def _cfg_validate_mapping_keys(
    raw: Mapping[object, object],
    allowed: frozenset[str],
    *,
    label: str,
) -> None:
    non_str = [repr(k) for k in raw.keys() if type(k) is not str]
    if non_str:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Non-string keys {non_str} in {label}.")
    unknown = sorted(str(k) for k in raw.keys() if k not in allowed)
    if unknown:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Unknown keys {unknown} in {label}.")


def _cfg_parse_raw_dependencies(raw_deps: object, *, label: str) -> dict[ModuleId, VersionConstraint]:
    if not isinstance(raw_deps, Mapping):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid dependencies object in {label}: expected JSON object.")
    parsed: dict[ModuleId, VersionConstraint] = {}
    for raw_k, raw_v in raw_deps.items():
        if type(raw_k) is not str or type(raw_v) is not str:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid dependency entry in {label}: expected string key/value.")
        try:
            mod_k = ModuleId(raw_k)
            ver_c = VersionConstraint.parse(raw_v)
        except ValueError as exc:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Invalid dependency specification '{raw_k}: {raw_v}' in {label}: {exc}",
            ) from exc
        cfg_assert_not_reserved_module_id(mod_k, f"Dependency key in {label}")
        parsed[mod_k] = ver_c
    return parsed


def _cfg_parse_raw_optional_specs(raw_opt: object, *, label: str) -> dict[ModuleId, OptionalDependencySpec]:
    if not isinstance(raw_opt, Mapping):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'optional' field in {label}: expected JSON object.")
    out: dict[ModuleId, OptionalDependencySpec] = {}
    for raw_k, raw_spec in raw_opt.items():
        if type(raw_k) is not str or not isinstance(raw_spec, Mapping):
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid optional dependency entry for {raw_k!r} in {label}.")
        _cfg_validate_mapping_keys(raw_spec, _CFG_OPTIONAL_SPEC_ALLOWED_KEYS, label=f"optional dependency '{raw_k}' of {label}")
        raw_ver = raw_spec.get("version")
        raw_hint = raw_spec.get("hint", "")
        if type(raw_ver) is not str or type(raw_hint) is not str:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid optional dependency fields for '{raw_k}' in {label}.")
        try:
            mod_k = ModuleId(raw_k)
            ver_c = VersionConstraint.parse(raw_ver)
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid optional dependency '{raw_k}' in {label}: {exc}") from exc
        cfg_assert_not_reserved_module_id(mod_k, f"Optional dependency key in {label}")
        out[mod_k] = OptionalDependencySpec(version=ver_c, hint=raw_hint)
    return out


def _cfg_parse_raw_pip_dependencies(raw_pip: object, *, label: str) -> dict[str, str]:
    if not isinstance(raw_pip, Mapping):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'pip_dependencies' in {label}: expected JSON object.")
    out: dict[str, str] = {}
    for pkg_k, spec_v in raw_pip.items():
        if type(pkg_k) is not str or not pkg_k.strip() or type(spec_v) is not str:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid pip_dependencies entry {pkg_k!r} in {label}.")
        clean_pkg = pkg_k.strip()
        if clean_pkg in out:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Duplicate pip_dependencies key {pkg_k!r} in {label}.")
        clean_spec = spec_v.strip()
        if clean_spec.startswith("-"):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Option flag syntax forbidden in pip_dependencies[{pkg_k!r}] of {label}.",
            )
        out[clean_pkg] = clean_spec
    return out


def _cfg_parse_raw_release_meta(raw_rel: object, *, label: str) -> Optional[ReleaseMeta]:
    if raw_rel is None:
        return None
    if not isinstance(raw_rel, Mapping):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'release' metadata in {label}: expected object or null.")
    _cfg_validate_mapping_keys(raw_rel, _CFG_RELEASE_META_ALLOWED_KEYS, label=f"'release' of {label}")
    has_type = "type" in raw_rel
    has_rel_type = "release_type" in raw_rel
    if has_type and has_rel_type:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Manifest 'release' in {label} must not specify both 'type' and 'release_type'.",
        )
    raw_t = raw_rel["type"] if has_type else raw_rel.get("release_type", "patch")
    if type(raw_t) is not str or not raw_t.strip():
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid release type in {label}.")
    raw_u = raw_rel.get("urgency", "recommended")
    if type(raw_u) is not str:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid release urgency in {label}.")
    try:
        urgency = ReleaseUrgency(raw_u.strip().lower())
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Unsupported release urgency {raw_u!r} in {label}.") from exc
    raw_sum = raw_rel.get("summary", "")
    if type(raw_sum) is not str:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid release summary in {label}.")
    return ReleaseMeta(release_type=raw_t.strip(), urgency=urgency, summary=raw_sum)


class _CompiledModuleSurfaceRegistry:
    _LOCK: ClassVar[threading.Lock] = threading.Lock()
    _META: ClassVar[WeakKeyDictionary[object, tuple[tuple[str, ...], str, frozenset[TaskId]]]] = WeakKeyDictionary()

    @classmethod
    def register(
        cls,
        yscb_module: object,
        aliases: tuple[str, ...],
        description: str,
        root_default_tasks: frozenset[TaskId] = frozenset(),
    ) -> None:
        clean_aliases = require_typed_tuple(aliases, str, "module aliases")
        clean_desc = _cfg_validate_pure_str(description, "module description")
        clean_roots = frozenset(t for t in root_default_tasks if isinstance(t, TaskId))
        with cls._LOCK:
            cls._META[yscb_module] = (clean_aliases, clean_desc, clean_roots)

    @classmethod
    def lookup(cls, yscb_module: object) -> tuple[tuple[str, ...], str]:
        with cls._LOCK:
            found = cls._META.get(yscb_module)
        return (found[0], found[1]) if found is not None else ((), "")

    @classmethod
    def lookup_root_defaults(cls, yscb_module: object) -> frozenset[TaskId]:
        with cls._LOCK:
            found = cls._META.get(yscb_module)
        return found[2] if found is not None else frozenset()


def register_compiled_module_surface_meta(
    yscb_module: object,
    *,
    aliases: tuple[str, ...] = (),
    description: str = "",
    root_default_tasks: frozenset[TaskId] = frozenset(),
) -> None:
    """Associate static CLI aliases, description, and root-default tasks with a compiled YscbModule instance."""
    _CompiledModuleSurfaceRegistry.register(yscb_module, aliases, description, root_default_tasks)


def lookup_compiled_module_surface_meta(yscb_module: object) -> tuple[tuple[str, ...], str]:
    """Retrieve (aliases, description) registered for a compiled YscbModule instance."""
    return _CompiledModuleSurfaceRegistry.lookup(yscb_module)


def lookup_compiled_module_root_default_tasks(yscb_module: object) -> frozenset[TaskId]:
    """Retrieve module-root default CLI task IDs (cli=()) registered for a compiled YscbModule instance."""
    return _CompiledModuleSurfaceRegistry.lookup_root_defaults(yscb_module)


def parse_manifest_dict(
    raw: Mapping[str, object],
    *,
    expected_id: Optional[ModuleId] = None,
) -> ModuleManifest:
    """Parse and strictly validate a raw manifest.json 2.0 dictionary into an immutable ModuleManifest."""
    if expected_id is not None and not isinstance(expected_id, ModuleId):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"expected_id must be ModuleId or None, got {expected_id!r}")
    label = f"manifest.json({expected_id})" if expected_id is not None else "manifest.json"
    if not isinstance(raw, Mapping):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid {label}: expected JSON object.")
    _cfg_validate_mapping_keys(raw, _CFG_MANIFEST_ALLOWED_KEYS, label=label)
    raw_sv = raw.get("schema_version", 2)
    if type(raw_sv) is not int or raw_sv != 2:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Unsupported schema_version {raw_sv!r} in {label} (expected 2).",
        )
    raw_id = raw.get("id")
    raw_ver = raw.get("version")
    raw_desc = raw.get("description")
    if (
        type(raw_id) is not str
        or type(raw_ver) is not str
        or type(raw_desc) is not str
        or not raw_desc.strip()
    ):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Missing or invalid required fields (id, version, description) in {label}.",
        )
    try:
        mod_id = ModuleId(raw_id)
        ver = SemVer4.parse(raw_ver)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid id or version in {label}: {exc}") from exc
    cfg_assert_not_reserved_module_id(mod_id, f"{label}.id")
    if expected_id is not None and mod_id != expected_id:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Manifest id '{mod_id}' does not match expected module '{expected_id}'.",
        )
    raw_entry = raw.get("entry", "module_entry.py")
    if type(raw_entry) is not str or not raw_entry.strip():
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'entry' in {label}.")
    deps = _cfg_parse_raw_dependencies(raw.get("dependencies", {}), label=label)
    opt_specs = _cfg_parse_raw_optional_specs(raw.get("optional", {}), label=label)
    pip_deps = _cfg_parse_raw_pip_dependencies(raw.get("pip_dependencies", {}), label=label)
    raw_group = raw.get("venv_group")
    if raw_group is not None and (type(raw_group) is not str or not is_valid_relative_segment(raw_group)):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'venv_group' {raw_group!r} in {label}.")
    raw_warmup = raw.get("eager_warmup", False)
    if type(raw_warmup) is not bool:
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'eager_warmup' in {label}.")
    raw_onboard = raw.get("onboarding", ())
    if not isinstance(raw_onboard, (list, tuple)) or any(type(x) is not str for x in raw_onboard):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid 'onboarding' list in {label}.")
    rel_meta = _cfg_parse_raw_release_meta(raw.get("release"), label=label)
    return ModuleManifest(
        id=mod_id,
        version=ver,
        description=raw_desc,
        schema_version=2,
        entry=raw_entry.strip(),
        dependencies=deps,
        optional=opt_specs,
        pip_dependencies=pip_deps,
        venv_group=raw_group,
        eager_warmup=raw_warmup,
        onboarding=tuple(raw_onboard),
        release=rel_meta,
    )
