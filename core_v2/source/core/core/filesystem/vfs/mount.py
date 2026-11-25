"""Semantic URI mount table, Scheme B 15 standard protocols, cycle detection, and health diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import BinaryIO, ClassVar, Final, Iterator, Mapping, NoReturn, Optional, Sequence
from weakref import WeakKeyDictionary

from core.filesystem.fs import (
    BeforeReplaceHook,
    has_symlink_raw_path,
    is_contained_nonsymlink_path,
    is_symlink_or_reparse,
    resolve_contained_subpath,
)
from core.filesystem.vfs.capabilities import VfsCapabilities, VfsStat
from core.filesystem.vfs.provider import (
    PhysicalDirectoryProvider,
    VfsProvider,
    vfs_try_resolve_unmasked_host_path,
)
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    HostPath,
    ModuleId,
    SemanticUri,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_str,
    require_typed_tuple,
)

_MOUNT_SCHEME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*$")
_CORE_PROVIDER_MODULE: Final[ModuleId] = ModuleId("core")

_CAPS_RO_TRACKED: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.GIT_TRACKED
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)
_CAPS_RO_UNTRACKED: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)
_CAPS_RW_TRACKED: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.WRITABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.GIT_TRACKED
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)
_CAPS_RW_LOCAL_PERSIST: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.WRITABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)
_CAPS_RW_EPHEMERAL: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.WRITABLE
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)


def _validate_mount_scheme_str(scheme: str, *, label: str = "scheme") -> str:
    require_pure_str(scheme, label, non_empty=True)
    if _MOUNT_SCHEME_RE.fullmatch(scheme) is None:
        raise ValueError(f"Invalid VFS {label}: {scheme!r}")
    return scheme


def _format_undefined_remediation(rule: Optional[MountRule], scheme: str) -> str:
    if rule is not None and rule.provider_module is not None and rule.config_binding is not None:
        mod_str = rule.provider_module.value
        key_str = rule.config_binding
        prefix = f"{mod_str}."
        if key_str.startswith(prefix) and len(key_str) > len(prefix):
            key_str = key_str[len(prefix) :]
        example_val = "./" if scheme == "project" else "<path>"
        return f"Configure '{scheme}://' via: yscb config set {mod_str} {key_str} {example_val}"
    if scheme == "project":
        return "Configure 'project://' via: yscb config set core project_root ./"
    return f"Configure a valid target_path or target_uri for scheme '{scheme}://'."


def _resolve_standard_subdir(yscb_root: HostPath, subdir: str) -> HostPath:
    try:
        return resolve_contained_subpath(yscb_root, subdir)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.SECURITY_GATED:
            raise YscbError(ErrorCode.ACCESS_DENIED, exc.detail.message, remediation=exc.detail.remediation) from exc
        raise


@dataclass(frozen=True, slots=True)
class MountRule:
    """Pure value-object mount declaration assembled by the workspace composition root."""

    scheme: str
    target_path: Optional[HostPath] = None
    target_uri: Optional[SemanticUri] = None
    capabilities: VfsCapabilities = VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE
    provider_module: Optional[ModuleId] = None
    config_binding: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        _validate_mount_scheme_str(self.scheme, label="MountRule.scheme")
        if self.target_path is not None and not isinstance(self.target_path, HostPath):
            raise ValueError(f"MountRule.target_path must be HostPath or None, got {self.target_path!r}")
        if self.target_uri is not None and not isinstance(self.target_uri, SemanticUri):
            raise ValueError(f"MountRule.target_uri must be SemanticUri or None, got {self.target_uri!r}")
        if self.target_path is not None and self.target_uri is not None:
            raise ValueError(f"MountRule '{self.scheme}' cannot declare both target_path and target_uri.")
        if not isinstance(self.capabilities, VfsCapabilities):
            raise ValueError(f"MountRule.capabilities must be VfsCapabilities, got {self.capabilities!r}")
        if self.provider_module is not None and not isinstance(self.provider_module, ModuleId):
            raise ValueError(f"MountRule.provider_module must be ModuleId or None, got {self.provider_module!r}")
        if self.config_binding is not None:
            require_pure_str(self.config_binding, "MountRule.config_binding", non_empty=True)
        require_pure_str(self.description, "MountRule.description")
        if self.target_uri is not None and self.target_uri.uses_module_placeholder:
            if self.provider_module is None:
                raise ValueError(
                    f"MountRule '{self.scheme}' target_uri '{self.target_uri}' uses '@/' without provider_module."
                )
            object.__setattr__(self, "target_uri", self.target_uri.bind_module(self.provider_module))


@dataclass(frozen=True, slots=True)
class MountHealthEntry:
    """Health diagnostic entry for a single mounted VFS scheme."""

    scheme: str
    healthy: bool
    detail: str

    def __post_init__(self) -> None:
        _validate_mount_scheme_str(self.scheme, label="MountHealthEntry.scheme")
        require_pure_bool(self.healthy, "MountHealthEntry.healthy")
        require_pure_str(self.detail, "MountHealthEntry.detail")


def build_standard_mount_rules(
    host_dir: HostPath,
    yscb_root: HostPath,
    *,
    project_root: Optional[HostPath] = None,
    extra_rules: Sequence[MountRule] = (),
) -> tuple[MountRule, ...]:
    """Build the canonical Scheme B 15 standard semantic VFS mount rules plus validated extra rules."""
    if not isinstance(host_dir, HostPath):
        raise ValueError(f"build_standard_mount_rules requires HostPath host_dir, got {host_dir!r}")
    if not isinstance(yscb_root, HostPath):
        raise ValueError(f"build_standard_mount_rules requires HostPath yscb_root, got {yscb_root!r}")
    if project_root is not None and not isinstance(project_root, HostPath):
        raise ValueError(f"build_standard_mount_rules project_root must be HostPath or None, got {project_root!r}")
    if is_symlink_or_reparse(str(host_dir)) or has_symlink_raw_path(str(host_dir)):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse host_dir: {host_dir}")
    if is_symlink_or_reparse(str(yscb_root)) or has_symlink_raw_path(str(yscb_root)):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse yscb_root: {yscb_root}")
    if project_root is not None and (
        is_symlink_or_reparse(str(project_root)) or has_symlink_raw_path(str(project_root))
    ):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing symlink or reparse project_root: {project_root}")
    validated_extras = require_typed_tuple(extra_rules, MountRule, "extra_rules")
    standard: tuple[MountRule, ...] = (
        MountRule(
            scheme="yscb",
            target_path=yscb_root,
            capabilities=_CAPS_RO_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="YSCB workspace root directory.",
        ),
        MountRule(
            scheme="yscb.host",
            target_path=host_dir,
            capabilities=_CAPS_RO_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Host repository directory containing the workspace.",
        ),
        MountRule(
            scheme="project",
            target_path=project_root,
            capabilities=_CAPS_RW_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            config_binding="project_root",
            description="Configured user project root directory.",
        ),
        MountRule(
            scheme="module",
            target_path=_resolve_standard_subdir(yscb_root, ".modules"),
            capabilities=_CAPS_RO_UNTRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Installed module artifacts directory.",
        ),
        MountRule(
            scheme="module.source",
            target_path=_resolve_standard_subdir(yscb_root, "source"),
            capabilities=_CAPS_RW_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Module source workspaces directory.",
        ),
        MountRule(
            scheme="module.build",
            target_path=_resolve_standard_subdir(yscb_root, ".build"),
            capabilities=_CAPS_RW_EPHEMERAL,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Ephemeral module build staging directory.",
        ),
        MountRule(
            scheme="module.release",
            target_path=_resolve_standard_subdir(yscb_root, "release"),
            capabilities=_CAPS_RW_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Packaged module releases directory.",
        ),
        MountRule(
            scheme="module.mirror",
            target_path=_resolve_standard_subdir(yscb_root, ".mirror"),
            capabilities=_CAPS_RO_UNTRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Local package mirror directory.",
        ),
        MountRule(
            scheme="config",
            target_path=_resolve_standard_subdir(yscb_root, "config"),
            capabilities=_CAPS_RW_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Git-tracked shared workspace configuration directory.",
        ),
        MountRule(
            scheme="config.local",
            target_path=_resolve_standard_subdir(yscb_root, ".config.local"),
            capabilities=_CAPS_RW_LOCAL_PERSIST,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Untracked machine-local configuration overrides directory.",
        ),
        MountRule(
            scheme="cache",
            target_path=_resolve_standard_subdir(yscb_root, ".cache"),
            capabilities=_CAPS_RW_EPHEMERAL,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Disposable runtime and module cache directory.",
        ),
        MountRule(
            scheme="storage",
            target_path=_resolve_standard_subdir(yscb_root, "storage"),
            capabilities=_CAPS_RW_TRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Git-tracked persistent module data directory.",
        ),
        MountRule(
            scheme="storage.local",
            target_path=_resolve_standard_subdir(yscb_root, ".storage.local"),
            capabilities=_CAPS_RW_LOCAL_PERSIST,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Untracked persistent local module database and blob directory.",
        ),
        MountRule(
            scheme="snapshot",
            target_path=_resolve_standard_subdir(yscb_root, ".snapshots"),
            capabilities=_CAPS_RO_UNTRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Workspace deployment snapshots directory.",
        ),
        MountRule(
            scheme="yscb.venv",
            target_path=_resolve_standard_subdir(yscb_root, ".venv"),
            capabilities=_CAPS_RO_UNTRACKED,
            provider_module=_CORE_PROVIDER_MODULE,
            description="Managed virtual environments root directory.",
        ),
    )
    seen_schemes = {rule.scheme for rule in standard}
    for extra in validated_extras:
        if extra.scheme in seen_schemes:
            raise ValueError(f"Duplicate or reserved standard MountRule scheme in extra_rules: {extra.scheme!r}")
        seen_schemes.add(extra.scheme)
    return (*standard, *validated_extras)


class _VfsUndefinedProvider:
    """Placeholder provider for !undefined mount rules raising deterministic URI_UNDEFINED on access."""

    def __init__(self, scheme: str, base_capabilities: VfsCapabilities, description: str, remediation: str) -> None:
        self._scheme = scheme
        self._base_capabilities = base_capabilities
        self._description = description
        self._remediation = remediation

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def base_capabilities(self) -> VfsCapabilities:
        return self._base_capabilities

    @property
    def description(self) -> str:
        return self._description

    def _raise_undefined(self, uri: SemanticUri) -> NoReturn:
        raise YscbError(
            ErrorCode.URI_UNDEFINED,
            f"Semantic URI scheme '{self._scheme}://' is undefined while accessing '{uri}'.",
            remediation=self._remediation,
        )

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        self._raise_undefined(uri)

    def exists(self, uri: SemanticUri) -> bool:
        self._raise_undefined(uri)

    def stat(self, uri: SemanticUri) -> VfsStat:
        self._raise_undefined(uri)

    def read_bytes(self, uri: SemanticUri) -> bytes:
        self._raise_undefined(uri)

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        self._raise_undefined(uri)

    def write_bytes_atomic(
        self,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None:
        _ = (data, before_replace)
        self._raise_undefined(uri)

    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool:
        _ = recursive
        self._raise_undefined(uri)

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        _ = dst
        self._raise_undefined(src)

    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None:
        _ = parents
        self._raise_undefined(uri)

    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]:
        _ = recursive
        self._raise_undefined(uri)

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        self._raise_undefined(uri)


class _VfsSubpathAliasProvider:
    """Delegating VfsProvider mapping a custom scheme onto a contained subpath of a target scheme."""

    def __init__(
        self,
        scheme: str,
        target_provider: VfsProvider,
        prefix_uri: SemanticUri,
        effective_capabilities: VfsCapabilities,
        description: str,
    ) -> None:
        self._scheme = scheme
        self._target_provider = target_provider
        self._prefix_uri = prefix_uri
        self._effective_capabilities = effective_capabilities
        self._description = description

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def base_capabilities(self) -> VfsCapabilities:
        return self._effective_capabilities

    @property
    def description(self) -> str:
        return self._description

    def _map_uri(self, uri: SemanticUri, *, allow_root: bool) -> SemanticUri:
        if not isinstance(uri, SemanticUri):
            raise ValueError(f"Expected SemanticUri, got {uri!r}")
        if uri.scheme != self._scheme:
            raise ValueError(f"URI scheme mismatch: expected '{self._scheme}://', got '{uri}'")
        if uri.uses_module_placeholder:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Unbound module placeholder '@/' in URI: {uri}")
        if not uri.rel_path:
            if not allow_root:
                raise YscbError(ErrorCode.ACCESS_DENIED, f"Operation requires a non-root file path for '{uri}'.")
            return self._prefix_uri
        return self._prefix_uri.join(uri.rel_path)

    def _unmap_entry(self, target_entry: SemanticUri) -> Optional[SemanticUri]:
        if target_entry.scheme != self._prefix_uri.scheme:
            return None
        base_rel = self._prefix_uri.rel_path
        if not base_rel:
            if not target_entry.rel_path or target_entry.rel_path.split("/", 1)[0] == "@":
                return None
            return SemanticUri(self._scheme, target_entry.rel_path)
        prefix = f"{base_rel}/"
        if not target_entry.rel_path.startswith(prefix):
            return None
        sub_rel = target_entry.rel_path[len(prefix) :]
        if not sub_rel or sub_rel.split("/", 1)[0] == "@":
            return None
        return SemanticUri(self._scheme, sub_rel)

    def get_capabilities(self, uri: SemanticUri) -> VfsCapabilities:
        mapped = self._map_uri(uri, allow_root=True)
        return self._target_provider.get_capabilities(mapped) & self._effective_capabilities

    def exists(self, uri: SemanticUri) -> bool:
        return self._target_provider.exists(self._map_uri(uri, allow_root=True))

    def stat(self, uri: SemanticUri) -> VfsStat:
        raw_st = self._target_provider.stat(self._map_uri(uri, allow_root=True))
        if not raw_st.exists:
            return raw_st
        is_ro = raw_st.is_readonly or (VfsCapabilities.WRITABLE not in self._effective_capabilities)
        return VfsStat(
            exists=raw_st.exists,
            is_dir=raw_st.is_dir,
            is_readonly=is_ro,
            size_bytes=raw_st.size_bytes,
            mtime_ns=raw_st.mtime_ns,
            ino=raw_st.ino,
        )

    def read_bytes(self, uri: SemanticUri) -> bytes:
        if VfsCapabilities.READABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not readable.")
        return self._target_provider.read_bytes(self._map_uri(uri, allow_root=False))

    def open_read(self, uri: SemanticUri) -> BinaryIO:
        if VfsCapabilities.READABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not readable.")
        return self._target_provider.open_read(self._map_uri(uri, allow_root=False))

    def write_bytes_atomic(
        self,
        uri: SemanticUri,
        data: bytes,
        *,
        before_replace: Optional[BeforeReplaceHook] = None,
    ) -> None:
        if VfsCapabilities.WRITABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Alias scheme '{self._scheme}://' is read-only.")
        self._target_provider.write_bytes_atomic(
            self._map_uri(uri, allow_root=False),
            data,
            before_replace=before_replace,
        )

    def delete(self, uri: SemanticUri, *, recursive: bool = False) -> bool:
        if VfsCapabilities.WRITABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Alias scheme '{self._scheme}://' is read-only.")
        return self._target_provider.delete(self._map_uri(uri, allow_root=False), recursive=recursive)

    def move(self, src: SemanticUri, dst: SemanticUri) -> None:
        if VfsCapabilities.WRITABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Alias scheme '{self._scheme}://' is read-only.")
        self._target_provider.move(
            self._map_uri(src, allow_root=False),
            self._map_uri(dst, allow_root=False),
        )

    def mkdir(self, uri: SemanticUri, *, parents: bool = True) -> None:
        if VfsCapabilities.WRITABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.READONLY_VIOLATION, f"Alias scheme '{self._scheme}://' is read-only.")
        mapped = self._map_uri(uri, allow_root=True)
        if not parents and not uri.rel_path and self._prefix_uri.rel_path:
            self._target_provider.mkdir(mapped, parents=True)
            return
        if not parents and uri.rel_path and "/" not in uri.rel_path and self._prefix_uri.rel_path:
            self._target_provider.mkdir(self._prefix_uri, parents=True)
        self._target_provider.mkdir(mapped, parents=parents)

    def iter_entries(self, uri: SemanticUri, *, recursive: bool = False) -> Iterator[SemanticUri]:
        if VfsCapabilities.ENUMERABLE not in self._effective_capabilities:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Scheme '{self._scheme}://' is not enumerable.")
        mapped = self._map_uri(uri, allow_root=True)
        remapped: list[SemanticUri] = []
        for entry in self._target_provider.iter_entries(mapped, recursive=recursive):
            unmapped = self._unmap_entry(entry)
            if unmapped is not None:
                remapped.append(unmapped)
        return iter(remapped)

    def try_get_physical_path(self, uri: SemanticUri) -> Optional[HostPath]:
        mapped = self._map_uri(uri, allow_root=True)
        if VfsCapabilities.PHYSICAL_PATH not in self._effective_capabilities:
            _ = vfs_try_resolve_unmasked_host_path(self._target_provider, mapped)
            return None
        return self._target_provider.try_get_physical_path(mapped)


@dataclass(frozen=True, slots=True)
class _VfsResolvedAliasTarget:
    terminal_scheme: str
    prefix_rel: str
    tightened_caps: VfsCapabilities


@dataclass(order=True, frozen=True, slots=True)
class _VfsPhysicalReverseEntry:
    alias_rank: int
    neg_root_len: int
    ro_rank: int
    order_index: int
    scheme: str
    root_path: HostPath


def _make_reverse_entry(
    scheme: str,
    root_path: HostPath,
    *,
    is_alias: bool,
    is_writable: bool,
    order_index: int,
) -> _VfsPhysicalReverseEntry:
    return _VfsPhysicalReverseEntry(
        alias_rank=1 if is_alias else 0,
        neg_root_len=-len(root_path.comparison_key.rstrip("/\\")),
        ro_rank=0 if is_writable else 1,
        order_index=order_index,
        scheme=scheme,
        root_path=root_path,
    )


def _match_reverse_entry(entry: _VfsPhysicalReverseEntry, abs_path: HostPath) -> Optional[SemanticUri]:
    if not is_contained_nonsymlink_path(entry.root_path, abs_path, allow_equal=True):
        return None
    if abs_path == entry.root_path:
        return SemanticUri(entry.scheme, "")
    try:
        rel_os = os.path.relpath(str(abs_path), str(entry.root_path))
    except ValueError:
        return None
    parts = tuple(p for p in Path(rel_os).parts if p not in ("", "."))
    if not parts or parts[0] == "@" or any(not is_valid_relative_segment(p) for p in parts):
        return None
    return SemanticUri(entry.scheme, "/".join(parts))


class UriMountTable:
    """Zero-singleton semantic URI routing and mount table with cycle detection and health checks."""

    def __init__(
        self,
        rules: Sequence[MountRule],
        *,
        providers: Optional[Mapping[str, VfsProvider]] = None,
    ) -> None:
        validated_rules = require_typed_tuple(rules, MountRule, "rules")
        rules_by_scheme: dict[str, MountRule] = {}
        for rule in validated_rules:
            if rule.scheme in rules_by_scheme:
                raise ValueError(f"Duplicate MountRule scheme: {rule.scheme!r}")
            rules_by_scheme[rule.scheme] = rule

        override_providers: dict[str, VfsProvider] = {}
        if providers is not None:
            if not isinstance(providers, Mapping):
                raise ValueError("UriMountTable providers must be a Mapping[str, VfsProvider] or None.")
            for raw_k, prov in providers.items():
                clean_k = _validate_mount_scheme_str(raw_k, label="providers key")
                if prov.scheme != clean_k:
                    raise ValueError(
                        f"Provider scheme mismatch for key {clean_k!r}: provider.scheme={prov.scheme!r}"
                    )
                override_providers[clean_k] = prov

        alias_targets: dict[str, _VfsResolvedAliasTarget] = {}
        for rule in validated_rules:
            if rule.scheme in override_providers or rule.target_uri is None:
                continue
            alias_targets[rule.scheme] = _resolve_alias_chain(rule, rules_by_scheme, override_providers)

        built_providers: dict[str, VfsProvider] = dict(override_providers)
        undefined_reasons: dict[str, str] = {}
        for rule in validated_rules:
            if rule.scheme in built_providers or rule.target_uri is not None:
                continue
            if rule.target_path is not None:
                built_providers[rule.scheme] = PhysicalDirectoryProvider(
                    rule.scheme,
                    rule.target_path,
                    base_capabilities=rule.capabilities,
                    description=rule.description,
                )
            else:
                remediation = _format_undefined_remediation(rule, rule.scheme)
                undefined_reasons[rule.scheme] = remediation
                built_providers[rule.scheme] = _VfsUndefinedProvider(
                    rule.scheme,
                    rule.capabilities,
                    rule.description,
                    remediation,
                )

        for rule in validated_rules:
            if rule.scheme in built_providers:
                continue
            resolved_alias = alias_targets[rule.scheme]
            term_scheme = resolved_alias.terminal_scheme
            term_prov = built_providers.get(term_scheme)
            if term_prov is None:
                remediation = _format_undefined_remediation(rules_by_scheme.get(term_scheme), term_scheme)
                undefined_reasons[rule.scheme] = (
                    f"Target scheme '{term_scheme}://' is unregistered ({remediation})."
                )
                built_providers[rule.scheme] = _VfsUndefinedProvider(
                    rule.scheme,
                    resolved_alias.tightened_caps,
                    rule.description,
                    remediation,
                )
            elif term_scheme in undefined_reasons:
                remediation = undefined_reasons[term_scheme]
                undefined_reasons[rule.scheme] = remediation
                built_providers[rule.scheme] = _VfsUndefinedProvider(
                    rule.scheme,
                    term_prov.base_capabilities & resolved_alias.tightened_caps,
                    rule.description,
                    remediation,
                )
            else:
                eff_caps = term_prov.base_capabilities & resolved_alias.tightened_caps
                prefix_uri = SemanticUri(term_scheme, resolved_alias.prefix_rel)
                built_providers[rule.scheme] = _VfsSubpathAliasProvider(
                    rule.scheme,
                    term_prov,
                    prefix_uri,
                    eff_caps,
                    rule.description,
                )

        reverse_entries: list[_VfsPhysicalReverseEntry] = []
        for idx, rule in enumerate(validated_rules):
            if rule.scheme in undefined_reasons:
                continue
            prov = built_providers[rule.scheme]
            is_alias = rule.target_uri is not None and rule.scheme not in override_providers
            root_hp = _try_extract_root_host_path(rule.scheme, prov, alias_targets, built_providers)
            if root_hp is not None:
                reverse_entries.append(
                    _make_reverse_entry(
                        rule.scheme,
                        root_hp,
                        is_alias=is_alias,
                        is_writable=(VfsCapabilities.WRITABLE in prov.base_capabilities),
                        order_index=idx,
                    )
                )
        base_idx = len(validated_rules)
        for extra_offset, (scheme_k, prov) in enumerate(override_providers.items()):
            if scheme_k in rules_by_scheme:
                continue
            root_hp = vfs_try_resolve_unmasked_host_path(prov, SemanticUri(scheme_k, ""))
            if root_hp is not None:
                reverse_entries.append(
                    _make_reverse_entry(
                        scheme_k,
                        root_hp,
                        is_alias=False,
                        is_writable=(VfsCapabilities.WRITABLE in prov.base_capabilities),
                        order_index=base_idx + extra_offset,
                    )
                )
        reverse_entries.sort()
        phys_roots = tuple((entry.scheme, entry.root_path) for entry in reverse_entries)

        self._rules = validated_rules
        self._rules_by_scheme = rules_by_scheme
        self._providers = built_providers
        self._alias_targets = alias_targets
        self._undefined_reasons = undefined_reasons
        self._reverse_entries = tuple(reverse_entries)
        _VfsMountInternals.register(
            self,
            _VfsMountState(
                providers=built_providers,
                alias_targets=alias_targets,
                undefined_reasons=undefined_reasons,
                physical_roots=phys_roots,
            ),
        )

    def list_rules(self) -> tuple[MountRule, ...]:
        return self._rules

    def get_provider(self, scheme: str) -> VfsProvider:
        clean_scheme = _validate_mount_scheme_str(scheme)
        prov = self._providers.get(clean_scheme)
        if prov is None:
            raise YscbError(
                ErrorCode.URI_UNDEFINED,
                f"Semantic URI scheme '{clean_scheme}://' is not registered in UriMountTable.",
                remediation=_format_undefined_remediation(None, clean_scheme),
            )
        return prov

    def resolve_physical(self, uri: SemanticUri) -> HostPath:
        if not isinstance(uri, SemanticUri):
            raise ValueError(f"resolve_physical requires SemanticUri, got {uri!r}")
        if uri.uses_module_placeholder:
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Unbound module placeholder '@/' in URI: {uri}")
        route = vfs_inspect_mount_route(self, uri)
        if route.unmasked_host_path is None:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"URI '{uri}' is backed by a non-physical provider and has no HostPath.",
            )
        return route.unmasked_host_path

    def to_uri(self, abs_path: HostPath) -> Optional[SemanticUri]:
        if not isinstance(abs_path, HostPath):
            raise ValueError(f"to_uri requires HostPath, got {abs_path!r}")
        if has_symlink_raw_path(str(abs_path)):
            return None
        for entry in self._reverse_entries:
            matched_uri = _match_reverse_entry(entry, abs_path)
            if matched_uri is not None:
                return matched_uri
        return None

    def iter_covering_mounts(self, host_path: HostPath) -> tuple[tuple[str, SemanticUri], ...]:
        """Return every physical mount (base and alias) whose root covers host_path."""
        if not isinstance(host_path, HostPath):
            raise ValueError(f"iter_covering_mounts requires HostPath, got {host_path!r}")
        if has_symlink_raw_path(str(host_path)):
            return ()
        matches: list[tuple[str, SemanticUri]] = []
        for entry in self._reverse_entries:
            matched_uri = _match_reverse_entry(entry, host_path)
            if matched_uri is not None:
                matches.append((entry.scheme, matched_uri))
        return tuple(matches)

    def check_health(self) -> tuple[MountHealthEntry, ...]:
        ordered_schemes: list[str] = [rule.scheme for rule in self._rules]
        seen = set(ordered_schemes)
        for scheme_k in self._providers:
            if scheme_k not in seen:
                ordered_schemes.append(scheme_k)
                seen.add(scheme_k)
        results: list[MountHealthEntry] = []
        for scheme_k in ordered_schemes:
            undef_msg = self._undefined_reasons.get(scheme_k)
            if undef_msg is not None:
                results.append(MountHealthEntry(scheme=scheme_k, healthy=False, detail=undef_msg))
                continue
            prov = self._providers[scheme_k]
            try:
                root_hp = self.resolve_physical(SemanticUri(scheme_k, ""))
            except YscbError as exc:
                if VfsCapabilities.PHYSICAL_PATH not in prov.base_capabilities:
                    try:
                        root_st = prov.stat(SemanticUri(scheme_k, ""))
                    except YscbError as stat_exc:
                        results.append(MountHealthEntry(scheme=scheme_k, healthy=False, detail=stat_exc.detail.message))
                        continue
                    if root_st.exists and not root_st.is_dir:
                        results.append(
                            MountHealthEntry(
                                scheme=scheme_k,
                                healthy=False,
                                detail=f"Mount root exists as non-directory for '{scheme_k}://'",
                            )
                        )
                    else:
                        alias_info = self._alias_targets.get(scheme_k)
                        term_prov = self._providers[alias_info.terminal_scheme] if alias_info is not None else prov
                        detail_label = (
                            "in-memory provider"
                            if VfsCapabilities.PERSISTENT not in term_prov.base_capabilities
                            else "non-physical capability mount"
                        )
                        results.append(MountHealthEntry(scheme=scheme_k, healthy=True, detail=detail_label))
                else:
                    results.append(MountHealthEntry(scheme=scheme_k, healthy=False, detail=exc.detail.message))
                continue
            raw_r = str(root_hp)
            if is_symlink_or_reparse(raw_r) or has_symlink_raw_path(raw_r):
                results.append(
                    MountHealthEntry(
                        scheme=scheme_k,
                        healthy=False,
                        detail=f"Mount root traverses symlink or reparse point: {raw_r}",
                    )
                )
            elif os.path.lexists(raw_r) and not os.path.isdir(raw_r):
                results.append(
                    MountHealthEntry(
                        scheme=scheme_k,
                        healthy=False,
                        detail=f"Mount root exists as non-directory: {raw_r}",
                    )
                )
            else:
                results.append(MountHealthEntry(scheme=scheme_k, healthy=True, detail=raw_r))
        return tuple(results)


def _resolve_alias_chain(
    start_rule: MountRule,
    rules_by_scheme: Mapping[str, MountRule],
    override_providers: Mapping[str, VfsProvider],
) -> _VfsResolvedAliasTarget:
    visited_order: list[str] = [start_rule.scheme]
    visited_set: set[str] = {start_rule.scheme}
    cur_target = start_rule.target_uri
    if cur_target is None:
        raise ValueError(f"Expected target_uri on alias MountRule '{start_rule.scheme}'.")
    accum_caps = start_rule.capabilities
    cur_scheme = cur_target.scheme
    cur_rel = cur_target.rel_path

    while True:
        if cur_scheme in visited_set:
            cycle_chain = " -> ".join([*visited_order, cur_scheme])
            raise YscbError(
                ErrorCode.URI_CYCLE,
                f"Cyclic MountRule target_uri reference detected: {cycle_chain}",
                remediation="Remove cyclic target_uri references between MountRule declarations.",
            )
        if cur_scheme in override_providers:
            return _VfsResolvedAliasTarget(
                terminal_scheme=cur_scheme,
                prefix_rel=cur_rel,
                tightened_caps=accum_caps,
            )
        next_rule = rules_by_scheme.get(cur_scheme)
        if next_rule is None or next_rule.target_uri is None:
            if next_rule is not None:
                accum_caps = accum_caps & next_rule.capabilities
            return _VfsResolvedAliasTarget(
                terminal_scheme=cur_scheme,
                prefix_rel=cur_rel,
                tightened_caps=accum_caps,
            )
        visited_order.append(cur_scheme)
        visited_set.add(cur_scheme)
        accum_caps = accum_caps & next_rule.capabilities
        parent_uri = next_rule.target_uri
        combined = parent_uri.join(cur_rel) if cur_rel else parent_uri
        cur_scheme = combined.scheme
        cur_rel = combined.rel_path


@dataclass(frozen=True, slots=True)
class VfsMountRouteInfo:
    """Internal resolved mount route uniting active provider overrides, alias targets, and physical backing."""

    provider: VfsProvider
    terminal_uri: SemanticUri
    terminal_provider: VfsProvider
    unmasked_host_path: Optional[HostPath]


@dataclass(frozen=True, slots=True)
class _VfsMountState:
    providers: Mapping[str, VfsProvider]
    alias_targets: Mapping[str, _VfsResolvedAliasTarget]
    undefined_reasons: Mapping[str, str]
    physical_roots: tuple[tuple[str, HostPath], ...]


class _VfsMountInternals:
    states: ClassVar[WeakKeyDictionary[UriMountTable, _VfsMountState]] = WeakKeyDictionary()

    @classmethod
    def register(cls, table: UriMountTable, state: _VfsMountState) -> None:
        cls.states[table] = state

    @classmethod
    def list_physical_roots(cls, table: UriMountTable) -> tuple[tuple[str, HostPath], ...]:
        state = cls.states.get(table)
        return state.physical_roots if state is not None else ()

    @classmethod
    def inspect_route(cls, table: UriMountTable, uri: SemanticUri) -> VfsMountRouteInfo:
        prov = table.get_provider(uri.scheme)
        state = cls.states.get(table)
        if state is None:
            hp = vfs_try_resolve_unmasked_host_path(prov, uri)
            return VfsMountRouteInfo(provider=prov, terminal_uri=uri, terminal_provider=prov, unmasked_host_path=hp)
        if uri.scheme in state.undefined_reasons:
            _ = prov.try_get_physical_path(uri)
            return VfsMountRouteInfo(provider=prov, terminal_uri=uri, terminal_provider=prov, unmasked_host_path=None)
        alias_info = state.alias_targets.get(uri.scheme)
        if alias_info is not None:
            term_prov = table.get_provider(alias_info.terminal_scheme)
            term_uri = SemanticUri(alias_info.terminal_scheme, alias_info.prefix_rel)
            if uri.rel_path:
                term_uri = term_uri.join(uri.rel_path)
            hp = vfs_try_resolve_unmasked_host_path(term_prov, term_uri)
            return VfsMountRouteInfo(
                provider=prov,
                terminal_uri=term_uri,
                terminal_provider=term_prov,
                unmasked_host_path=hp,
            )
        hp = vfs_try_resolve_unmasked_host_path(prov, uri)
        return VfsMountRouteInfo(provider=prov, terminal_uri=uri, terminal_provider=prov, unmasked_host_path=hp)


def vfs_inspect_mount_route(table: UriMountTable, uri: SemanticUri) -> VfsMountRouteInfo:
    """Internal VFS route inspector honoring live provider overrides and unmasked physical roots."""
    return _VfsMountInternals.inspect_route(table, uri)


def vfs_list_physical_mount_roots(table: UriMountTable) -> tuple[tuple[str, HostPath], ...]:
    """Internal VFS helper listing all defined physical (scheme, root_path) pairs in mount precedence order."""
    return _VfsMountInternals.list_physical_roots(table)


def _try_extract_root_host_path(
    scheme: str,
    prov: VfsProvider,
    alias_targets: Mapping[str, _VfsResolvedAliasTarget],
    built_providers: Mapping[str, VfsProvider],
) -> Optional[HostPath]:
    alias_info = alias_targets.get(scheme)
    try:
        if alias_info is not None:
            term_prov = built_providers.get(alias_info.terminal_scheme)
            if term_prov is None:
                return None
            return vfs_try_resolve_unmasked_host_path(
                term_prov,
                SemanticUri(alias_info.terminal_scheme, alias_info.prefix_rel),
            )
        return vfs_try_resolve_unmasked_host_path(prov, SemanticUri(scheme, ""))
    except YscbError:
        return None
