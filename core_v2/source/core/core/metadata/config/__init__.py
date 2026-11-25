"""Domain 3.1: Module manifest 2.0, 2x2 configuration matrix, DeepInfiller, and smart SnapshotVault."""

from core.metadata.config.infill import DeepInfiller
from core.metadata.config.manifest import (
    ModuleManifest,
    OptionalDependencySpec,
    ReleaseMeta,
    ReleaseUrgency,
    lookup_compiled_module_root_default_tasks,
    lookup_compiled_module_surface_meta,
    parse_manifest_dict,
    register_compiled_module_surface_meta,
)
from core.metadata.config.matrix import (
    ConfigStore,
    HostConfig,
    InstalledModuleRecord,
    parse_locale_chain_tokens,
)
from core.metadata.config.snapshot import SnapshotMeta, SnapshotRetentionPolicy, SnapshotVault

__all__ = (
    "ConfigStore",
    "DeepInfiller",
    "HostConfig",
    "InstalledModuleRecord",
    "ModuleManifest",
    "OptionalDependencySpec",
    "ReleaseMeta",
    "ReleaseUrgency",
    "SnapshotMeta",
    "SnapshotRetentionPolicy",
    "SnapshotVault",
    "lookup_compiled_module_root_default_tasks",
    "lookup_compiled_module_surface_meta",
    "parse_locale_chain_tokens",
    "parse_manifest_dict",
    "register_compiled_module_surface_meta",
)
