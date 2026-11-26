"""Domain 3 and Domain 4 verification suite covering core.metadata.{config,contributes} and core.packaging.{env,installer}."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, make_dataclass
import gc
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Annotated, Mapping, Optional, Union
import warnings
import weakref
import zipfile

from core.filesystem.fs import FileLock, atomic_write_json
from core.filesystem.vfs import UriMountTable, VfsHub, build_standard_mount_rules
from core.foundation import (
    TEST_SANDBOX_ENV_KEY,
    CancellationToken,
    DataclassCodec,
    EnvHash,
    ErrorCode,
    IS_WINDOWS,
    HostPath,
    ManagedProcessTree,
    ModuleId,
    SemVer4,
    TaskCancelledException,
    VersionConstraint,
    YscbError,
    secret_field,
)
from core.metadata.config import (
    ConfigStore,
    DeepInfiller,
    HostConfig,
    InstalledModuleRecord,
    ModuleManifest,
    OptionalDependencySpec,
    ReleaseMeta,
    ReleaseUrgency,
    SnapshotMeta,
    SnapshotRetentionPolicy,
    SnapshotVault,
    parse_manifest_dict,
)
from core.metadata.contributes import (
    AggregatedContributes,
    ContribField,
    ContributesAggregator,
    ContributesSchemaBundle,
    ExtensionPointSpec,
    MergeStrategy,
    ProvenanceEntry,
    ProvenanceGraph,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    compile_extension_points,
    discover_installed_manifests_map,
    validate_locale_bundle,
)
from core.packaging.env import (
    EnvBuildResult,
    EnvGarbageCollector,
    EnvGcPolicy,
    EnvGcResult,
    EnvHealthProbe,
    EnvHealthReport,
    EnvSpec,
    ImmutableVenvPool,
    acquire_env_lease_for_python,
    acquire_env_shared_lease,
    touch_env_last_used,
)
from core.packaging.installer import (
    AtomicPackageDeployer,
    DependencySolver,
    DeploymentReport,
    MigrationRollbackHandle,
    MirrorStore,
    OfflinePackageEngine,
    PackageRequest,
    ProviderClient,
    PurgeLevel,
    UpdateChecker,
)
from tests import CORE_SRC_ROOT
from tests._harness import assert_raises_val_error, check, expect_yscb_code, log


@dataclass(frozen=True, slots=True)
class _NestedCacheConfigDto:
    max_mb: int = 64
    evict_policy: str = "lru"


@dataclass(frozen=True, slots=True)
class _SampleModuleConfigDto:
    enabled: bool = True
    workers: int = 2
    tags: tuple[str, ...] = ("default",)
    cache: _NestedCacheConfigDto = field(default_factory=_NestedCacheConfigDto)


@dataclass(frozen=True, slots=True)
class _TypedKeyQuotaConfigDto:
    quotas: Mapping[ModuleId, int] = field(default_factory=lambda: {ModuleId("core"): 16})


@dataclass(frozen=True, slots=True)
class _CredBlockDto:
    label: str = "main"
    dsn: str = secret_field(default="")


@dataclass(frozen=True, slots=True)
class _MultiNestedSecretDto:
    primary: _CredBlockDto = field(default_factory=_CredBlockDto)
    secondary: Annotated[Optional[_CredBlockDto], "backup"] = None
    replicas: tuple[_CredBlockDto, ...] = ()
    profiles: Mapping[str, _CredBlockDto] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _ContribRouteRuleDto:
    prefix: str
    priority: int = 10
    banner: str = "nested_default"


@dataclass(frozen=True, slots=True)
class _ContribNamedActionDto:
    id: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class _ContribPluginPointDto:
    routes: Annotated[
        Mapping[str, _ContribRouteRuleDto],
        ContribField(merge=MergeStrategy.UNIQUE, description="Unique named routes"),
    ] = field(default_factory=dict)
    hooks: Annotated[
        tuple[str, ...],
        ContribField(merge=MergeStrategy.EXTEND, description="Ordered hook names", dedupe=True),
    ] = ()
    banner: Annotated[
        str,
        ContribField(merge=MergeStrategy.REPLACE, description="Active banner text"),
    ] = "init"
    flags: Annotated[
        Mapping[str, bool],
        ContribField(merge=MergeStrategy.MERGE, description="Merged feature flags"),
    ] = field(default_factory=dict)
    bounds: Optional[tuple[int, int]] = None
    actions: Annotated[
        tuple[_ContribNamedActionDto, ...],
        ContribField(merge=MergeStrategy.UNIQUE, description="Unique action items"),
    ] = ()


@dataclass(frozen=True, slots=True)
class _ContribLocaleEntryDto:
    definition: str
    zh: str = ""
    en: str = ""


def _build_int_group_point_type() -> type[object]:
    leaf_cls = make_dataclass("_SharedLeafDto", [("val", int, 1)], frozen=True, slots=True)
    group_cls = make_dataclass(
        "_SharedGroupDto",
        [("leaf", leaf_cls, field(default_factory=leaf_cls))],
        frozen=True,
        slots=True,
    )
    return make_dataclass(
        "_PointHolderDto",
        [("group", group_cls, field(default_factory=group_cls))],
        frozen=True,
        slots=True,
    )


def _build_str_group_point_type() -> type[object]:
    leaf_cls = make_dataclass("_SharedLeafDto", [("val", str, "x")], frozen=True, slots=True)
    group_cls = make_dataclass(
        "_SharedGroupDto",
        [("leaf", leaf_cls, field(default_factory=leaf_cls))],
        frozen=True,
        slots=True,
    )
    return make_dataclass(
        "_PointHolderDto",
        [("group", group_cls, field(default_factory=group_cls))],
        frozen=True,
        slots=True,
    )


def _build_pure_wheel(wheel_dir: Path, dist_name: str, pkg_import_name: str, version: str, marker_val: int) -> Path:
    wheel_dir.mkdir(parents=True, exist_ok=True)
    whl_name = f"{pkg_import_name}-{version}-py3-none-any.whl"
    whl_path = wheel_dir / whl_name
    init_bytes = f"MARKER_VALUE = {marker_val}\nVERSION = {version!r}\n".encode("utf-8")
    meta_bytes = f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: {version}\n".encode("utf-8")
    wheel_meta = b"Wheel-Version: 1.0\nGenerator: yscb-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    rec_lines: list[str] = []
    entries = (
        (f"{pkg_import_name}/__init__.py", init_bytes),
        (f"{pkg_import_name}-{version}.dist-info/METADATA", meta_bytes),
        (f"{pkg_import_name}-{version}.dist-info/WHEEL", wheel_meta),
    )
    for arc_name, payload in entries:
        b64_hash = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")
        rec_lines.append(f"{arc_name},sha256={b64_hash},{len(payload)}")
    rec_arc = f"{pkg_import_name}-{version}.dist-info/RECORD"
    rec_lines.append(f"{rec_arc},,")
    rec_bytes = ("\n".join(rec_lines) + "\n").encode("utf-8")
    with zipfile.ZipFile(whl_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc_name, payload in entries:
            zf.writestr(arc_name, payload)
        zf.writestr(rec_arc, rec_bytes)
    return whl_path


def _build_sdist_tar_gz(wheel_dir: Path, dist_name: str, version: str) -> Path:
    wheel_dir.mkdir(parents=True, exist_ok=True)
    tar_path = wheel_dir / f"{dist_name}-{version}.tar.gz"
    setup_src = (
        "from setuptools import setup\n"
        f"setup(name={dist_name!r}, version={version!r}, py_modules=['sdist_mod'])\n"
    ).encode("utf-8")
    pkg_info = f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: {version}\n".encode("utf-8")
    mod_src = b"SDIST_ONLY = True\n"
    with tarfile.open(tar_path, "w:gz") as tf:
        for rel_name, raw_data in (
            ("setup.py", setup_src),
            ("PKG-INFO", pkg_info),
            ("sdist_mod.py", mod_src),
        ):
            ti = tarfile.TarInfo(name=f"{dist_name}-{version}/{rel_name}")
            ti.size = len(raw_data)
            tf.addfile(ti, io.BytesIO(raw_data))
    return tar_path


def _build_custom_zip_bytes(entries: tuple[tuple[zipfile.ZipInfo, bytes], ...]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for zinfo, payload in entries:
            zf.writestr(zinfo, payload, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def _build_module_zip_bytes(
    mod_id: str,
    version: str,
    *,
    dependencies: Optional[dict[str, str]] = None,
    pip_dependencies: Optional[dict[str, str]] = None,
    venv_group: Optional[str] = None,
    config_defaults: Optional[dict[str, object]] = None,
    tmpl_files: Optional[dict[str, str]] = None,
    extra_files: Optional[dict[str, bytes]] = None,
) -> tuple[bytes, str]:
    manifest_doc: dict[str, object] = {
        "schema_version": 2,
        "id": mod_id,
        "version": version,
        "description": f"Module {mod_id} package {version}",
        "entry": "module_entry.py",
        "dependencies": dependencies or {},
        "pip_dependencies": pip_dependencies or {},
        "eager_warmup": False,
        "onboarding": [f"yscb {mod_id} status"],
        "release": {"type": "minor", "urgency": "recommended", "summary": f"Release {version}"},
    }
    if venv_group is not None:
        manifest_doc["venv_group"] = venv_group
    tmp_fd, tmp_raw = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    tmp_p = Path(tmp_raw)
    try:
        with zipfile.ZipFile(tmp_p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest_doc, indent=2) + "\n")
            zf.writestr("module_entry.py", f"MODULE_VERSION = {version!r}\n")
            zf.writestr("tasks.index.json", json.dumps({"schema_version": 2, "tasks": [], "subscriptions": []}) + "\n")
            zf.writestr(".yscbignore", "*.secret\n")
            if config_defaults is not None:
                props = {k: {"default": v} for k, v in config_defaults.items()}
                zf.writestr(
                    "config.schema.json",
                    json.dumps({"type": "object", "properties": props}, indent=2) + "\n",
                )
            if tmpl_files is not None:
                for rel_tmpl, content_str in tmpl_files.items():
                    zf.writestr(f"configurable/{rel_tmpl}", content_str)
            if extra_files is not None:
                for arc_rel, raw_b in extra_files.items():
                    zf.writestr(arc_rel, raw_b)
        raw_zip = tmp_p.read_bytes()
    finally:
        tmp_p.unlink(missing_ok=True)
    return (raw_zip, hashlib.sha256(raw_zip).hexdigest())


class _RepoHttpMirrorState:
    def __init__(self, static_routes: dict[str, bytes]) -> None:
        self.routes: dict[str, bytes] = dict(static_routes)
        self.redirects: dict[str, str] = {}
        self.oversized_route = "/oversized/9.9.9.zip"


def _start_test_http_mirror(state: _RepoHttpMirrorState) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.close_connection = True
            if self.path == state.oversized_route:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                chunk = b"X" * (1024 * 1024)
                try:
                    for _ in range(22):
                        self.wfile.write(chunk)
                except OSError:
                    return
                return
            redir_target = state.redirects.get(self.path)
            if redir_target is not None:
                self.send_response(302)
                self.send_header("Location", redir_target)
                self.end_headers()
                return
            payload = state.routes.get(self.path)
            if payload is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            _ = (self, format, args)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = int(srv.server_address[1])
    thr = threading.Thread(target=srv.serve_forever, name="test-pkg-http", daemon=True)
    thr.start()
    return (srv, thr, f"http://127.0.0.1:{port}")


def _verify_metadata_config_and_snapshot_vault(suite_root: Path) -> None:
    cfg_ws = suite_root / "cfg_suite"
    host_dir = HostPath(cfg_ws / "repo")
    yscb_root = HostPath(cfg_ws / "repo" / ".yscb")
    host_dir.path.mkdir(parents=True, exist_ok=True)
    yscb_root.path.mkdir(parents=True, exist_ok=True)

    mf_t0 = ModuleManifest(
        id=ModuleId("dev"),
        version=SemVer4.parse("2.0.0"),
        description="Developer workflow tools",
        dependencies={ModuleId("core"): VersionConstraint.parse(">=2.0.0")},
        optional={ModuleId("ast"): OptionalDependencySpec(VersionConstraint.parse("^2.0.0"), hint="AST checks")},
        onboarding=("yscb dev check",),
        release=ReleaseMeta(release_type="minor", urgency=ReleaseUrgency.RECOMMENDED, summary="Init"),
    )
    check(not mf_t0.is_tier1, "Empty pip_dependencies must classify as Tier 0")
    mf_roundtrip = DataclassCodec.decode(ModuleManifest, DataclassCodec.encode(mf_t0))
    check(mf_roundtrip == mf_t0, "ModuleManifest DataclassCodec round-trip mismatch")

    mf_t1 = ModuleManifest(
        id=ModuleId("ast"),
        version=SemVer4.parse("2.1.0.0"),
        description="AST indexer",
        pip_dependencies={"tree-sitter": ">=0.23.0"},
        venv_group="code_intel",
        eager_warmup=True,
    )
    check(mf_t1.is_tier1, "Non-empty pip_dependencies must classify as Tier 1")

    expect_yscb_code(
        lambda: ModuleManifest(id=ModuleId("ast"), version=SemVer4.parse("2.0.0"), description="x", schema_version=1),
        ErrorCode.CONFIG_INVALID,
    )
    expect_yscb_code(
        lambda: ModuleManifest(
            id=ModuleId("ast"), version=SemVer4.parse("2.0.0"), description="x", venv_group="mod_reserved"
        ),
        ErrorCode.CONFIG_INVALID,
    )
    expect_yscb_code(
        lambda: ModuleManifest(id=ModuleId("ast"), version=SemVer4.parse("2.0.0"), description="x", entry="../bad.py"),
        ErrorCode.CONFIG_INVALID,
    )

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    expect_yscb_code(store.load_host_config, ErrorCode.CONFIG_INVALID)

    base_host_cfg = HostConfig(
        yscb_root=".yscb",
        default_provider="https://mirror.example.invalid/yscb",
        installed_modules={
            ModuleId("core"): InstalledModuleRecord(
                version=SemVer4.parse("2.0.0"),
                installed_at="2026-11-22T00:00:00Z",
                provider="local",
            )
        },
    )
    store.save_host_config(base_host_cfg)
    check(store.load_host_config() == base_host_cfg, "HostConfig save/load mismatch")

    atomic_write_json(HostPath(host_dir.path / "yscb.config.local.json"), {"default_provider": "./local_mirror"})
    overlaid_host = store.load_host_config()
    check(
        overlaid_host.default_provider == "./local_mirror"
        and ModuleId("core") in overlaid_host.installed_modules,
        f"yscb.config.local.json overlay failed: {overlaid_host}",
    )
    roundtrip_overlaid = store.load_host_config()
    store.save_host_config(roundtrip_overlaid)
    raw_saved_base = json.loads((host_dir.path / "yscb.config.json").read_text(encoding="utf-8"))
    check(
        raw_saved_base["default_provider"] == "https://mirror.example.invalid/yscb"
        and store.load_host_config().default_provider == "./local_mirror",
        f"save_host_config leaked local overlay into git-tracked yscb.config.json: {raw_saved_base}",
    )

    typed_key_cfg = store.load_typed(ModuleId("quota-mod"), _TypedKeyQuotaConfigDto)
    check(
        typed_key_cfg.quotas == {ModuleId("core"): 16},
        f"ConfigStore.load_typed failed on Mapping[ModuleId, int] default value: {typed_key_cfg}",
    )

    fp_initial = store.fingerprint()
    mod_kdb = ModuleId("kdb")
    store.set_value(mod_kdb, "workers", 4, local=False, schema_cls=_SampleModuleConfigDto)
    store.set_value(mod_kdb, "cache.max_mb", 256, local=False, schema_cls=_SampleModuleConfigDto)
    store.set_value(mod_kdb, "cache.evict_policy", "fifo", local=True, schema_cls=_SampleModuleConfigDto)
    fp_after = store.fingerprint()
    check(fp_after != fp_initial, "ConfigStore.fingerprint() must update on module config write")

    typed_cfg = store.load_typed(mod_kdb, _SampleModuleConfigDto)
    check(
        typed_cfg.workers == 4
        and typed_cfg.cache.max_mb == 256
        and typed_cfg.cache.evict_policy == "fifo"
        and typed_cfg.enabled is True,
        f"2x2 config matrix overlay failed: {typed_cfg}",
    )
    check(store.get_module_value(mod_kdb, "cache.max_mb") == 256)

    expect_yscb_code(
        lambda: store.set_value(mod_kdb, "workers", "not_an_int", local=False, schema_cls=_SampleModuleConfigDto),
        ErrorCode.CONFIG_INVALID,
    )
    check(store.load_typed(mod_kdb, _SampleModuleConfigDto).workers == 4, "Failed schema check must not mutate disk")
    if not IS_WINDOWS:
        local_cfg_file = yscb_root.path / ".config.local" / "kdb" / "config.local.json"
        check(
            stat.S_IMODE(local_cfg_file.stat().st_mode) == 0o600
            and stat.S_IMODE(local_cfg_file.parent.stat().st_mode) == 0o700
            and stat.S_IMODE((yscb_root.path / ".config.local").stat().st_mode) == 0o700,
            "config.local.json and .config.local/ directories must enforce 0o600/0o700 permissions",
        )
    check(store.unset_value(mod_kdb, "cache.evict_policy", local=True) is True)
    if not IS_WINDOWS:
        local_cfg_file = yscb_root.path / ".config.local" / "kdb" / "config.local.json"
        check(
            stat.S_IMODE(local_cfg_file.stat().st_mode) == 0o600,
            "unset_value(..., local=True) must preserve 0o600 permissions",
        )
    check(store.load_typed(mod_kdb, _SampleModuleConfigDto).cache.evict_policy == "lru")

    @dataclass(frozen=True, slots=True)
    class _SecretModCfgDto:
        endpoint: str = "https://default.example"
        api_token: str = secret_field(default="")
        nested: _NestedCacheConfigDto = field(default_factory=_NestedCacheConfigDto)

    mod_sec = ModuleId("seccfg")
    store.set_value(mod_sec, "endpoint", "https://proj.example", local=False, schema_cls=_SecretModCfgDto)
    store.set_value(mod_sec, "nested.max_mb", 128, local=False, schema_cls=_SecretModCfgDto)
    store.set_value(mod_sec, "nested.evict_policy", "secret_local_policy", local=True, schema_cls=_SecretModCfgDto)
    store.set_value(mod_sec, "api_token", "sk-live-secret-123", local=True, schema_cls=_SecretModCfgDto)
    check(
        store.get_module_local_dict(mod_sec)
        == {"nested": {"evict_policy": "secret_local_policy"}, "api_token": "sk-live-secret-123"},
        f"Unexpected get_module_local_dict: {store.get_module_local_dict(mod_sec)}",
    )
    redacted_sec = store.get_module_redacted_dict(mod_sec, schema_cls=_SecretModCfgDto)
    check(
        redacted_sec["endpoint"] == "https://proj.example"
        and redacted_sec["api_token"] == "[REDACTED]"
        and isinstance(redacted_sec["nested"], dict)
        and redacted_sec["nested"]["max_mb"] == 128
        and redacted_sec["nested"]["evict_policy"] == "[REDACTED]",
        f"Unexpected get_module_redacted_dict: {redacted_sec}",
    )
    unredacted_sec = store.load_typed(mod_sec, _SecretModCfgDto)
    check(unredacted_sec.api_token == "sk-live-secret-123" and unredacted_sec.nested.evict_policy == "secret_local_policy")

    mod_disk_sec = ModuleId("disksec")
    disk_schema_dir = yscb_root.path / ".modules" / "disksec"
    disk_schema_dir.mkdir(parents=True, exist_ok=True)
    (disk_schema_dir / "config.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "custom_key": {"type": "string", "writeOnly": True},
                    "plain_key": {"type": "string"},
                },
            }
        ),
        encoding="utf-8",
    )
    store.set_value(mod_disk_sec, "custom_key", "hidden-by-disk-schema", local=False)
    store.set_value(mod_disk_sec, "plain_key", "visible-plain", local=False)
    redacted_disk = store.get_module_redacted_dict(mod_disk_sec)
    check(
        redacted_disk == {"custom_key": "[REDACTED]", "plain_key": "visible-plain"},
        f"Disk config.schema.json writeOnly redaction failed: {redacted_disk}",
    )

    mod_multi_sec = ModuleId("multisec")
    store.set_value(mod_multi_sec, "primary", {"label": "p1", "dsn": "pg://secret-primary"}, local=False)
    store.set_value(mod_multi_sec, "secondary", {"label": "p2", "dsn": "pg://secret-secondary"}, local=False)
    store.set_value(mod_multi_sec, "replicas", [{"label": "r1", "dsn": "pg://secret-rep"}], local=False)
    store.set_value(mod_multi_sec, "profiles", {"prod": {"label": "m1", "dsn": "pg://secret-map"}}, local=False)
    red_multi = store.get_module_redacted_dict(mod_multi_sec, schema_cls=_MultiNestedSecretDto)
    check(
        red_multi == {
            "primary": {"label": "p1", "dsn": "[REDACTED]"},
            "secondary": {"label": "p2", "dsn": "[REDACTED]"},
            "replicas": [{"label": "r1", "dsn": "[REDACTED]"}],
            "profiles": {"prod": {"label": "m1", "dsn": "[REDACTED]"}},
        },
        f"Sibling/list/map secret_field redaction failed: {red_multi}",
    )
    disk_multi_dir = yscb_root.path / ".modules" / "diskmulti"
    disk_multi_dir.mkdir(parents=True, exist_ok=True)
    (disk_multi_dir / "config.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "items_cfg": {"type": "array", "items": {"type": "object", "properties": {"dsn": {"type": "string", "writeOnly": True}, "name": {"type": "string"}}}},
                    "map_cfg": {"type": "object", "additionalProperties": {"type": "object", "properties": {"dsn": {"type": "string", "x-yscb-secret": True}}}},
                },
            }
        ),
        encoding="utf-8",
    )
    mod_disk_multi = ModuleId("diskmulti")
    store.set_value(mod_disk_multi, "items_cfg", [{"dsn": "hidden-item", "name": "ok"}], local=False)
    store.set_value(mod_disk_multi, "map_cfg", {"eu": {"dsn": "hidden-map"}}, local=False)
    red_disk_multi = store.get_module_redacted_dict(mod_disk_multi)
    check(
        red_disk_multi == {"items_cfg": [{"dsn": "[REDACTED]", "name": "ok"}], "map_cfg": {"eu": {"dsn": "[REDACTED]"}}},
        f"Disk schema array/map secret redaction failed: {red_disk_multi}",
    )

    infilled_obj, added_paths = DeepInfiller.infill(
        {"workers": 8, "cache": {"max_mb": 512}},
        {"enabled": True, "workers": 2, "cache": {"max_mb": 64, "evict_policy": "lru"}},
    )
    check(
        infilled_obj == {"workers": 8, "enabled": True, "cache": {"max_mb": 512, "evict_policy": "lru"}}
        and set(added_paths) == {"enabled", "cache.evict_policy"},
        f"DeepInfiller failed to preserve user values or infill nested keys: {infilled_obj}, {added_paths}",
    )

    staging_cfg = HostPath(cfg_ws / "staging_configurable")
    staging_cfg.path.mkdir(parents=True, exist_ok=True)
    (staging_cfg.path / "config.project.json.tmpl").write_text(
        json.dumps({"enabled": False, "workers": 1, "tags": ["tmpl"], "cache": {"max_mb": 32, "evict_policy": "arc"}}),
        encoding="utf-8",
    )
    (staging_cfg.path / "contribute.json.tmpl").write_text('{"hooks": ["from_tmpl"]}\n', encoding="utf-8")
    existing_contrib = yscb_root.path / "config" / "kdb" / "extra.json"
    existing_contrib.parent.mkdir(parents=True, exist_ok=True)
    existing_contrib.write_text('{"user_kept": true}\n', encoding="utf-8")
    (staging_cfg.path / "extra.json.tmpl").write_text('{"user_kept": false}\n', encoding="utf-8")

    deployed_files = store.deploy_configurable(mod_kdb, staging_cfg)
    check("contribute.json" in deployed_files and "extra.json" not in deployed_files, f"Unexpected deploy: {deployed_files}")
    check(
        json.loads(existing_contrib.read_text(encoding="utf-8")) == {"user_kept": True},
        "Existing non-config .tmpl target must never be overwritten",
    )
    post_deploy_typed = store.load_typed(mod_kdb, _SampleModuleConfigDto)
    check(
        post_deploy_typed.workers == 4 and post_deploy_typed.cache.max_mb == 256 and post_deploy_typed.enabled is False,
        f"deploy_configurable clobbered user-edited config.project.json keys: {post_deploy_typed}",
    )

    bad_staging_cfg = HostPath(cfg_ws / "bad_staging_configurable")
    bad_staging_cfg.path.mkdir(parents=True, exist_ok=True)
    (bad_staging_cfg.path / "raw_without_tmpl.json").write_text("{}\n", encoding="utf-8")
    expect_yscb_code(lambda: store.deploy_configurable(mod_kdb, bad_staging_cfg), ErrorCode.CONFIG_INVALID)

    local_db_sentinel = yscb_root.path / ".storage.local" / "kdb" / "index.db"
    local_cfg_sentinel = yscb_root.path / ".config.local" / "kdb" / "config.local.json"
    cache_sentinel = yscb_root.path / ".cache" / "kdb" / "ephemeral.bin"
    tracked_storage_file = yscb_root.path / "storage" / "kdb" / "glossary.json"
    local_db_sentinel.parent.mkdir(parents=True, exist_ok=True)
    cache_sentinel.parent.mkdir(parents=True, exist_ok=True)
    tracked_storage_file.parent.mkdir(parents=True, exist_ok=True)
    local_db_sentinel.write_bytes(b"sqlite_v1_keep")
    cache_sentinel.write_bytes(b"cache_v1_keep")
    tracked_storage_file.write_text('{"ver": 1}\n', encoding="utf-8")
    store.set_value(mod_kdb, "cache.evict_policy", "local_v1", local=True, schema_cls=_SampleModuleConfigDto)

    vault = SnapshotVault(
        host_dir=host_dir,
        yscb_root=yscb_root,
        policy=SnapshotRetentionPolicy(max_snapshots=3, max_age_days=7.0, coalesce_window_sec=60.0),
    )
    snap_one = vault.create_snapshot("pre_install")
    check(isinstance(snap_one, SnapshotMeta) and not snap_one.reused)
    check(
        not (yscb_root.path / ".snapshots" / snap_one.snapshot_id / "config_local").exists(),
        "SnapshotVault must NEVER back up .config.local/ secrets into .snapshots/",
    )
    snap_zero_diff = vault.create_snapshot("repeat_noop")
    check(snap_zero_diff.reused and snap_zero_diff.snapshot_id == snap_one.snapshot_id, "Zero-diff must short-circuit")

    tracked_storage_file.write_text('{"ver": 2}\n', encoding="utf-8")
    snap_burst = vault.create_snapshot("burst_within_60s")
    check(
        snap_burst.reused and snap_burst.snapshot_id == snap_one.snapshot_id,
        "Burst coalesce window (<60s) must preserve window-start snapshot",
    )

    snap_forced_two = vault.create_snapshot("forced_v2", force=True)
    check((not snap_forced_two.reused) and snap_forced_two.snapshot_id != snap_one.snapshot_id)
    tracked_storage_file.write_text('{"ver": 3}\n', encoding="utf-8")
    snap_forced_three = vault.create_snapshot("forced_v3", force=True)
    tracked_storage_file.write_text('{"ver": 4}\n', encoding="utf-8")
    snap_forced_four = vault.create_snapshot("forced_v4", force=True)
    listed_snaps = vault.list_snapshots()
    check(
        len(listed_snaps) == 3
        and {s.snapshot_id for s in listed_snaps}
        == {snap_forced_two.snapshot_id, snap_forced_three.snapshot_id, snap_forced_four.snapshot_id},
        f"max_snapshots=3 failed to prune oldest snapshot: {listed_snaps}",
    )

    oldest_dir = yscb_root.path / ".snapshots" / snap_forced_two.snapshot_id
    expired_meta_file = oldest_dir / "snapshot.meta.json"
    if expired_meta_file.is_file():
        meta_doc = json.loads(expired_meta_file.read_text(encoding="utf-8"))
        meta_doc["created_epoch_sec"] = time.time() - (9.0 * 86400.0)
        expired_meta_file.write_text(json.dumps(meta_doc), encoding="utf-8")
    old_mtime = time.time() - (9.0 * 86400.0)
    os.utime(oldest_dir, (old_mtime, old_mtime))

    ext_ro_file = cfg_ws / "external_readonly.txt"
    ext_ro_file.write_text("immutable", encoding="utf-8")
    orphan_sym_tmp = yscb_root.path / ".snapshots" / ".tmp_999999_deadbeef"
    os.chmod(ext_ro_file, stat.S_IREAD)
    try:
        ro_mode_before = stat.S_IMODE(os.lstat(ext_ro_file).st_mode)
        try:
            os.symlink(ext_ro_file, orphan_sym_tmp)
        except (OSError, NotImplementedError):
            pass

        pruned_ids = vault.prune()
        check(snap_forced_two.snapshot_id in pruned_ids, f"Expired >7d snapshot not pruned: {pruned_ids}")
        check(not os.path.lexists(orphan_sym_tmp), "Orphan .tmp_* symlink in .snapshots must be unlinked during prune")
        check(
            stat.S_IMODE(os.lstat(ext_ro_file).st_mode) == ro_mode_before,
            "SnapshotVault cleanup must never chmod through symlinks to external files",
        )
    finally:
        orphan_sym_tmp.unlink(missing_ok=True)
        os.chmod(ext_ro_file, stat.S_IWRITE | stat.S_IREAD)

    local_db_sentinel.write_bytes(b"sqlite_v2_must_survive_restore")
    cache_sentinel.write_bytes(b"cache_v2_must_survive_restore")
    store.set_value(mod_kdb, "cache.evict_policy", "local_v2_must_survive", local=True, schema_cls=_SampleModuleConfigDto)
    tracked_storage_file.write_text('{"ver": 999}\n', encoding="utf-8")
    store.set_value(mod_kdb, "workers", 99, local=False, schema_cls=_SampleModuleConfigDto)

    restored_meta = vault.restore_snapshot(snap_forced_three.snapshot_id)
    check(restored_meta.snapshot_id == snap_forced_three.snapshot_id)
    check(
        json.loads(tracked_storage_file.read_text(encoding="utf-8")) == {"ver": 3}
        and store.load_typed(mod_kdb, _SampleModuleConfigDto).workers == 4,
        "SnapshotVault.restore_snapshot failed to restore tracked storage and config",
    )
    check(
        local_db_sentinel.read_bytes() == b"sqlite_v2_must_survive_restore"
        and cache_sentinel.read_bytes() == b"cache_v2_must_survive_restore"
        and json.loads(local_cfg_sentinel.read_text(encoding="utf-8")).get("cache", {}).get("evict_policy")
        == "local_v2_must_survive",
        "SnapshotVault MUST NEVER back up or overwrite .config.local/, .storage.local/, or .cache/",
    )

    mod_sym_test = ModuleId("symcfg")
    check(store.get_module_dict(mod_sym_test) == {}, "Initial absent config must return empty dict")
    sym_local_dir = yscb_root.path / ".config.local" / "symcfg"
    sym_local_dir.mkdir(parents=True, exist_ok=True)
    secret_outside = cfg_ws / "outside_secret.json"
    secret_outside.write_text('{"leaked": true}\n', encoding="utf-8")
    sym_target = sym_local_dir / "config.local.json"
    symlink_supported = True
    try:
        os.symlink(secret_outside, sym_target)
    except (OSError, NotImplementedError):
        symlink_supported = False
    if symlink_supported:
        expect_yscb_code(lambda: store.get_module_dict(mod_sym_test), ErrorCode.SECURITY_GATED)


def _verify_metadata_contributes_engine(suite_root: Path) -> None:
    ctb_ws = suite_root / "ctb_suite" / ".yscb"
    ctb_ws.mkdir(parents=True, exist_ok=True)
    yscb_hp = HostPath(ctb_ws)

    mod_core = ModuleId("core")
    mod_alpha = ModuleId("alpha")
    mod_beta = ModuleId("beta")
    mod_host = ModuleId("host-ext")

    transitive_bundle = compile_extension_points(
        mod_host,
        (
            ExtensionPointSpec(name="pt_int", payload_type=_build_int_group_point_type()),
            ExtensionPointSpec(name="pt_str", payload_type=_build_str_group_point_type()),
        ),
    )
    trans_defs = transitive_bundle.points_schema.get("$defs")
    check(
        isinstance(trans_defs, Mapping)
        and "_SharedGroupDto" in trans_defs
        and "pt_str__SharedGroupDto" in trans_defs,
        f"Transitive $defs collision across extension points was not isolated by fixed-point rename: {trans_defs}",
    )

    specs = (
        ExtensionPointSpec(
            name="plugins",
            payload_type=_ContribPluginPointDto,
            description="Plugin registry point",
            merge_strategy=MergeStrategy.MERGE,
            strict_fields=True,
        ),
        ExtensionPointSpec(
            name="locales",
            payload_type=_ContribLocaleEntryDto,
            description="Module locale pointers",
            merge_strategy=MergeStrategy.BUCKET_BY_DONOR,
            strict_fields=True,
        ),
    )
    bundle = compile_extension_points(mod_host, specs)
    check(isinstance(bundle, ContributesSchemaBundle) and bundle.target_module == mod_host)
    roundtrip_bundle = ContributesSchemaBundle.from_json(bundle.to_json())
    check(roundtrip_bundle.to_json() == bundle.to_json(), "ContributesSchemaBundle JSON round-trip drift")

    bundle_defs = bundle.points_schema.get("$defs")
    check(isinstance(bundle_defs, Mapping) and "_ContribRouteRuleDto" in bundle_defs)
    if isinstance(bundle_defs, Mapping):
        nested_def = bundle_defs["_ContribRouteRuleDto"]
        nested_props = nested_def.get("properties") if isinstance(nested_def, Mapping) else None
        nested_banner = nested_props.get("banner") if isinstance(nested_props, Mapping) else None
        check(
            isinstance(nested_banner, Mapping) and "x-yscb-merge" not in nested_banner,
            f"Nested $defs dataclass field 'banner' must not inherit root ContribField metadata: {nested_banner}",
        )

    host_schema_file = ctb_ws / ".modules" / "host-ext" / "contributes" / "_schema.json"
    host_schema_file.parent.mkdir(parents=True, exist_ok=True)
    host_schema_file.write_text(json.dumps(bundle.to_json(), indent=2) + "\n", encoding="utf-8")

    alpha_contrib = {
        "plugins": {
            "routes": {"search": {"prefix": "/search", "priority": 10}, "shared~1key": {"prefix": "/s1"}},
            "hooks": ["init", "index"],
            "banner": "from_alpha",
            "flags": {"fast": True, "debug": False},
            "bounds": [10, 20],
            "actions": [{"id": "act.open", "label": "Open"}],
        },
        "locales": {"definition": "locales/def.json", "zh": "locales/zh.json", "en": "locales/en.json"},
    }
    beta_contrib = {
        "plugins": {
            "routes": {"lint": {"prefix": "/lint", "priority": 20}},
            "hooks": ["index", "verify"],
            "banner": "from_beta",
            "flags": {"debug": True},
            "bounds": [30, 40],
            "actions": [{"id": "act.lint", "label": "Lint"}],
        },
        "locales": {"definition": "locales/def.json", "zh": "locales/zh.json"},
    }
    proj_override = {
        "plugins": {
            "routes": {"search": {"prefix": "/search_v2", "priority": 99}},
            "hooks": ["project_post"],
        }
    }

    for donor_name, payload in (("alpha", alpha_contrib), ("beta", beta_contrib)):
        c_file = ctb_ws / ".modules" / donor_name / "contributes" / "host-ext.json"
        c_file.parent.mkdir(parents=True, exist_ok=True)
        c_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    proj_c_dir = ctb_ws / "config" / "host-ext"
    proj_c_dir.mkdir(parents=True, exist_ok=True)
    (proj_c_dir / "contribute.json").write_text(json.dumps(proj_override, indent=2) + "\n", encoding="utf-8")
    (proj_c_dir / "contribute.local.json").write_text('{"plugins": {"banner": "forbidden_local"}}\n', encoding="utf-8")

    manifests = (
        ModuleManifest(id=mod_core, version=SemVer4.parse("2.0.0"), description="core"),
        ModuleManifest(
            id=mod_beta,
            version=SemVer4.parse("2.0.0"),
            description="beta depends on alpha",
            dependencies={mod_alpha: VersionConstraint.parse(">=2.0.0")},
        ),
        ModuleManifest(id=mod_alpha, version=SemVer4.parse("2.0.0"), description="alpha"),
        ModuleManifest(id=mod_host, version=SemVer4.parse("2.0.0"), description="host"),
    )

    agg_live = ContributesAggregator(yscb_root=yscb_hp, manifests=manifests, live_specs={mod_host: specs})
    agg_disk = ContributesAggregator(yscb_root=yscb_hp, manifests=manifests)

    res_live = agg_live.aggregate(mod_host, strict=False)
    res_disk = agg_disk.aggregate(mod_host, strict=False)
    check(isinstance(res_live, AggregatedContributes))
    check(res_live.raw_merged == res_disk.raw_merged, "Tier 1 _schema.json aggregation must match live_specs 1:1")
    check(
        not (ctb_ws / ".cache").exists(),
        "ContributesAggregator must be pure in-memory with zero .cache/ disk writes",
    )
    check(
        any("contribute.local.json" in w.source_label or "contribute.local.json" in w.message for w in res_live.warnings),
        f"contribute.local.json must emit a warning and be ignored: {res_live.warnings}",
    )

    single_point_specs = (
        ExtensionPointSpec(
            name="locales",
            payload_type=_ContribLocaleEntryDto,
            description="Only locales point after reload",
            merge_strategy=MergeStrategy.BUCKET_BY_DONOR,
            strict_fields=True,
        ),
    )
    host_schema_file.write_text(
        json.dumps(compile_extension_points(mod_host, single_point_specs).to_json(), indent=2) + "\n",
        encoding="utf-8",
    )
    agg_disk.reload(manifests=manifests)
    reloaded_bundle = agg_disk.get_schema_bundle(mod_host)
    reloaded_props = reloaded_bundle.points_schema.get("properties") if reloaded_bundle is not None else None
    check(
        isinstance(reloaded_props, Mapping) and "locales" in reloaded_props and "plugins" not in reloaded_props,
        f"ContributesAggregator.reload failed to invalidate cached disk schema bundle: {reloaded_props}",
    )
    host_schema_file.write_text(json.dumps(bundle.to_json(), indent=2) + "\n", encoding="utf-8")
    agg_disk.reload(manifests=manifests)

    decoded_plugins = res_live.decode_point("plugins", _ContribPluginPointDto)
    check(decoded_plugins.banner == "from_beta", f"Topological order alpha -> beta failed: {decoded_plugins.banner}")
    check(
        decoded_plugins.bounds == (30, 40),
        f"Optional fixed-length tuple bounds must replace rather than concatenate: {decoded_plugins.bounds}",
    )
    check(
        decoded_plugins.hooks == ("init", "index", "verify", "project_post"),
        f"EXTEND dedupe hooks mismatch: {decoded_plugins.hooks}",
    )
    check(decoded_plugins.flags == {"fast": True, "debug": True}, f"MERGE flags mismatch: {decoded_plugins.flags}")
    check(
        decoded_plugins.routes["search"].prefix == "/search_v2" and decoded_plugins.routes["search"].priority == 99,
        "Project contribute.json must be allowed to override UNIQUE key",
    )

    dup_nested_unique_report = agg_live.validate_donor_file(
        "module:alpha/contributes/host-ext.json",
        mod_host,
        {"plugins": {"actions": [{"id": "dup.act"}, {"id": "dup.act"}]}},
        strict=True,
    )
    check(
        not dup_nested_unique_report.ok and len(dup_nested_unique_report.errors) >= 1,
        f"Nested UNIQUE array duplicate inside single donor must be rejected: {dup_nested_unique_report}",
    )

    donor_locales = res_live.decode_donor_bucket("locales", _ContribLocaleEntryDto)
    check(set(donor_locales.keys()) == {"alpha", "beta"}, f"BUCKET_BY_DONOR keys mismatch: {donor_locales}")
    raw_str_dump = json.dumps(DataclassCodec.encode(res_live.raw_merged))
    check(
        "__provider__" not in raw_str_dump and "__modules__" not in raw_str_dump,
        "Zero magic keys allowed in raw_merged payload",
    )

    prov: ProvenanceGraph = res_live.provenance
    search_entry = prov.origin_for("/plugins/routes/search")
    escaped_entry = prov.origin_for("/plugins/routes/shared~01key")
    check(
        isinstance(search_entry, ProvenanceEntry)
        and search_entry.contributors == ("alpha", "project")
        and search_entry.final_owner == "project",
        f"Provenance chain mismatch on /plugins/routes/search: {search_entry}",
    )
    check(
        escaped_entry is not None and escaped_entry.final_owner == "alpha",
        f"RFC 6901 ~0/~1 escaped pointer provenance missing: {escaped_entry}",
    )
    check("/plugins/routes/lint" in prov.pointers_by_donor("beta"))

    typo_report: ValidationReport = agg_live.validate_donor_file(
        "module:beta/contributes/host-ext.json",
        mod_host,
        {"plugnis": {}},
        strict=True,
    )
    check(
        (not typo_report.ok)
        and len(typo_report.errors) >= 1
        and typo_report.errors[0].suggestion is not None
        and "plugins" in (typo_report.errors[0].suggestion or ""),
        f"Expected 'Did you mean' suggestion for typo point: {typo_report.issues}",
    )

    beta_dup_unique = dict(beta_contrib)
    beta_dup_unique["plugins"] = {
        "routes": {"search": {"prefix": "/collision", "priority": 50}},
    }
    (ctb_ws / ".modules" / "beta" / "contributes" / "host-ext.json").write_text(
        json.dumps(beta_dup_unique), encoding="utf-8"
    )
    expect_yscb_code(lambda: agg_live.aggregate(mod_host, strict=True), ErrorCode.CONTRIBUTES_INVALID)

    alpha_mod_root = HostPath(ctb_ws / ".modules" / "alpha")
    loc_dir = alpha_mod_root.path / "locales"
    loc_dir.mkdir(parents=True, exist_ok=True)
    (loc_dir / "def.json").write_text(
        json.dumps({"greet.msg": "Greeting with {user}", "plain.msg": "Static text"}),
        encoding="utf-8",
    )
    (loc_dir / "zh.json").write_text(
        json.dumps({"greet.msg": "你好 {user} {{literal}}", "plain.msg": "靜態文字"}),
        encoding="utf-8",
    )
    (loc_dir / "en.json").write_text(
        json.dumps({"greet.msg": "Hello {wrong_param}", "orphan.key": "extra"}),
        encoding="utf-8",
    )
    ok_loc_issues = validate_locale_bundle(
        mod_alpha,
        alpha_mod_root,
        {"definition": "locales/def.json", "zh": "locales/zh.json"},
    )
    check(not ok_loc_issues, f"Valid zh locale bundle reported unexpected issues: {ok_loc_issues}")

    bad_loc_issues = validate_locale_bundle(
        mod_alpha,
        alpha_mod_root,
        {"definition": "locales/def.json", "en": "locales/en.json", "escape": "../outside.json"},
    )
    check(
        len(bad_loc_issues) >= 3
        and all(isinstance(i, ValidationIssue) and i.severity == ValidationSeverity.ERROR for i in bad_loc_issues),
        f"Expected traversal, orphan key, and placeholder mismatch errors: {bad_loc_issues}",
    )

    check(
        not isinstance(bundle.points_schema, dict) and not isinstance(res_live.raw_merged, dict),
        "ContributesSchemaBundle.points_schema and AggregatedContributes.raw_merged must be immutable MappingProxyType",
    )

    @dataclass(frozen=True, slots=True)
    class _LocalClosurePointDto:
        opt_tags: Optional[
            Annotated[
                tuple[str, ...],
                ContribField(merge=MergeStrategy.EXTEND, description="Closure tags", dedupe=False),
            ]
        ] = None

    closure_bundle = compile_extension_points(
        mod_host,
        (ExtensionPointSpec(name="closure_pt", payload_type=_LocalClosurePointDto),),
    )
    closure_props = closure_bundle.points_schema["properties"]
    check(
        isinstance(closure_props, Mapping)
        and "closure_pt" in closure_props
        and '"x-yscb-dedupe": false' in json.dumps(closure_bundle.to_json()),
        "Closure @dataclass with Optional[Annotated[..., ContribField]] failed to preserve field merge metadata",
    )

    nested_inner_cls = make_dataclass(
        "_NestedReplaceInnerDto",
        [("req_x", int), ("req_y", int)],
        frozen=True,
        slots=True,
    )
    nested_outer_cls = make_dataclass(
        "_NestedReplaceOuterDto",
        [
            ("inner", nested_inner_cls),
            (
                "opt_sub",
                Optional[
                    Annotated[
                        nested_inner_cls,
                        ContribField(merge=MergeStrategy.REPLACE, description="Optional replace sub"),
                    ]
                ],
                None,
            ),
        ],
        frozen=True,
        slots=True,
    )

    rep_ws = suite_root / "ctb_suite" / "replace_strict_ws"
    rep_host = ModuleId("rep-host")
    rep_donor = ModuleId("rep-donor")
    (rep_ws / ".modules" / "rep-donor" / "contributes").mkdir(parents=True, exist_ok=True)
    (rep_ws / "config" / "rep-host").mkdir(parents=True, exist_ok=True)
    (rep_ws / ".modules" / "rep-donor" / "contributes" / "rep-host.json").write_text(
        json.dumps(
            {
                "rep_pt": {"inner": {"req_x": 1, "req_y": 2}},
                "merge_pt": {"inner": {"req_x": 1, "req_y": 2}, "opt_sub": {"req_x": 3, "req_y": 4}},
            }
        ),
        encoding="utf-8",
    )
    (rep_ws / "config" / "rep-host" / "contribute.json").write_text(
        json.dumps(
            {
                "rep_pt": {"inner": {"req_x": 99}},
                "merge_pt": {"opt_sub": {"req_x": 77}},
            }
        ),
        encoding="utf-8",
    )
    rep_agg = ContributesAggregator(
        yscb_root=HostPath(rep_ws),
        manifests=(
            ModuleManifest(id=rep_host, version=SemVer4.parse("2.0.0.0"), description="rep host"),
            ModuleManifest(id=rep_donor, version=SemVer4.parse("2.0.0.0"), description="rep donor"),
        ),
        live_specs={
            rep_host: (
                ExtensionPointSpec(
                    name="rep_pt",
                    payload_type=nested_outer_cls,
                    merge_strategy=MergeStrategy.REPLACE,
                ),
                ExtensionPointSpec(
                    name="merge_pt",
                    payload_type=nested_outer_cls,
                    merge_strategy=MergeStrategy.MERGE,
                ),
            )
        },
    )
    rep_reports: tuple[ValidationReport, ...] = rep_agg.validate_all(strict=True)
    rep_host_reports = [r for r in rep_reports if r.target_module == rep_host]
    check(
        len(rep_host_reports) == 1
        and (not rep_host_reports[0].ok)
        and len(rep_host_reports[0].errors) >= 2,
        f"Project override missing required child fields under REPLACE must fail validate_all: {rep_reports}",
    )

    branch_a_cls = make_dataclass("_BranchAlphaDto", [("only_a", int)], frozen=True, slots=True)
    branch_b_cls = make_dataclass(
        "_BranchBetaDto",
        [
            ("only_b", str),
            (
                "uniq_routes",
                Annotated[
                    Mapping[str, str],
                    ContribField(merge=MergeStrategy.UNIQUE, description="Unique routes in branch B"),
                ],
                field(default_factory=dict),
            ),
        ],
        frozen=True,
        slots=True,
    )
    multi_union_cls = make_dataclass(
        "_MultiUnionRootDto",
        [
            ("pair_or_label", Union[str, tuple[int, int]], "none"),
            ("disjoint", Union[branch_a_cls, branch_b_cls], field(default_factory=lambda: branch_a_cls(only_a=0))),
            (
                "opt_vo_union",
                Optional[
                    Annotated[
                        Union[ModuleId, int],
                        ContribField(merge=MergeStrategy.REPLACE, description="Optional VO union"),
                    ]
                ],
                None,
            ),
        ],
        frozen=True,
        slots=True,
    )
    mu_ws = suite_root / "ctb_suite" / "multi_union_ws"
    mu_host = ModuleId("mu-host")
    mu_d1 = ModuleId("mu-d1")
    mu_d2 = ModuleId("mu-d2")
    (mu_ws / ".modules" / "mu-d1" / "contributes").mkdir(parents=True, exist_ok=True)
    (mu_ws / ".modules" / "mu-d2" / "contributes").mkdir(parents=True, exist_ok=True)
    (mu_ws / ".modules" / "mu-d1" / "contributes" / "mu-host.json").write_text(
        json.dumps(
            {
                "mu_pt": {
                    "pair_or_label": [10, 20],
                    "disjoint": {"only_a": 7},
                    "opt_vo_union": "valid-mod",
                }
            }
        ),
        encoding="utf-8",
    )
    (mu_ws / ".modules" / "mu-d2" / "contributes" / "mu-host.json").write_text(
        json.dumps(
            {
                "mu_pt": {
                    "pair_or_label": [30, 40],
                    "disjoint": {"only_b": "switched", "uniq_routes": {"home": "/h"}},
                }
            }
        ),
        encoding="utf-8",
    )
    mu_agg = ContributesAggregator(
        yscb_root=HostPath(mu_ws),
        manifests=(
            ModuleManifest(id=mu_host, version=SemVer4.parse("2.0.0.0"), description="mu host"),
            ModuleManifest(id=mu_d1, version=SemVer4.parse("2.0.0.0"), description="mu d1"),
            ModuleManifest(id=mu_d2, version=SemVer4.parse("2.0.0.0"), description="mu d2"),
        ),
        live_specs={mu_host: (ExtensionPointSpec(name="mu_pt", payload_type=multi_union_cls),)},
    )
    mu_res = mu_agg.aggregate(mu_host, strict=True)
    mu_decoded = mu_res.decode_point("mu_pt", multi_union_cls)
    check(
        mu_decoded is not None
        and mu_decoded.pair_or_label == (30, 40)
        and isinstance(mu_decoded.disjoint, branch_b_cls)
        and mu_decoded.disjoint.only_b == "switched",
        f"Multi-branch Union failed fixed-tuple replacement or disjoint branch switch: {mu_decoded}",
    )
    bad_vo_rep = mu_agg.validate_donor_file(
        "module:mu-d2/contributes/mu-host.json",
        mu_host,
        {"mu_pt": {"opt_vo_union": "INVALID UPPERCASE MODULE ID"}},
        strict=True,
    )
    check(
        not bad_vo_rep.ok,
        f"Optional[Annotated[Union[ModuleId, int], ContribField]] failed to enforce ModuleId VO validation: {bad_vo_rep}",
    )
    (mu_ws / ".modules" / "mu-d1" / "contributes" / "mu-host.json").write_text(
        json.dumps({"mu_pt": {"disjoint": {"only_b": "first", "uniq_routes": {"home": "/1"}}}}),
        encoding="utf-8",
    )
    mu_agg.reload()
    expect_yscb_code(lambda: mu_agg.aggregate(mu_host, strict=True), ErrorCode.CONTRIBUTES_INVALID)


def _verify_packaging_env_pool_probe_and_gc(suite_root: Path) -> None:
    env_ws = suite_root / "env_suite"
    yscb_hp = HostPath(env_ws / ".yscb")
    cache_hp = HostPath(env_ws / ".yscb" / ".cache")
    wheels_hp = HostPath(env_ws / "wheels")
    yscb_hp.path.mkdir(parents=True, exist_ok=True)
    cache_hp.path.mkdir(parents=True, exist_ok=True)

    _build_pure_wheel(wheels_hp.path, "alpha-wheel-lib", "alpha_wheel_lib", "1.2.0", 120)
    _build_pure_wheel(wheels_hp.path, "alpha-wheel-lib", "alpha_wheel_lib", "1.3.0", 130)

    pool = ImmutableVenvPool(yscb_root=yscb_hp, cache_dir=cache_hp)
    spec_a = ImmutableVenvPool.compute_env_spec("code_intel", {"Alpha_Wheel.Lib": ">=1.0.0"})
    spec_b = ImmutableVenvPool.compute_env_spec("code_intel", {"alpha-wheel-lib": ">=1.0.0"})
    check(spec_a == spec_b and spec_a.env_hash == spec_b.env_hash, "PEP 503 normalization hash mismatch")
    assert_raises_val_error(lambda: ImmutableVenvPool.compute_env_spec("empty_grp", {}))
    assert_raises_val_error(lambda: ImmutableVenvPool.compute_env_spec(".hidden_grp", {"alpha-wheel-lib": ">=1.0.0"}))
    for bad_direct_spec in (
        "https://evil.example/pkg-1.0-py3-none-any.whl",
        "pkg@https://evil.example/pkg.whl",
        "./local_pkg.tar.gz",
        "bad/pkg>=1.0.0",
    ):
        assert_raises_val_error(
            lambda s=bad_direct_spec: EnvSpec(
                group="direct_guard",
                py_tag=spec_a.py_tag,
                platform_tag=spec_a.platform_tag,
                pip_specs=(s,),
                env_hash=spec_a.env_hash,
            )
        )
    mf_mod_prefix = ModuleManifest(
        id=ModuleId("mod_ast"),
        version=SemVer4.parse("2.0.0"),
        description="mod prefix default fallback",
        pip_dependencies={"alpha-wheel-lib": ">=1.2.0"},
    )
    mod_prefix_specs = ImmutableVenvPool.resolve_group_specs((mf_mod_prefix,))
    check(
        mod_prefix_specs[ModuleId("mod_ast")].group == "mod_ast",
        f"ModuleId starting with mod_ must resolve fallback venv group cleanly: {mod_prefix_specs}",
    )

    mf_zero = ModuleManifest(id=ModuleId("dev"), version=SemVer4.parse("2.0.0"), description="tier0")
    mf_one = ModuleManifest(
        id=ModuleId("ast"),
        version=SemVer4.parse("2.0.0"),
        description="tier1 a",
        pip_dependencies={"alpha-wheel-lib": ">=1.2.0"},
        venv_group="code_intel",
    )
    mf_two = ModuleManifest(
        id=ModuleId("kdb"),
        version=SemVer4.parse("2.0.0"),
        description="tier1 b",
        pip_dependencies={"Alpha.Wheel_Lib": "<1.3.0"},
        venv_group="code_intel",
    )
    group_map = ImmutableVenvPool.resolve_group_specs((mf_zero, mf_one, mf_two))
    check(ModuleId("dev") not in group_map, "Tier 0 module must not resolve an EnvSpec")
    colocated_spec = group_map[ModuleId("ast")]
    check(
        group_map[ModuleId("kdb")] == colocated_spec
        and colocated_spec.pip_specs == ("alpha-wheel-lib<1.3.0,>=1.2.0",),
        f"Co-located venv_group conjunction failed: {colocated_spec}",
    )

    pre_cancel = CancellationToken()
    pre_cancel.cancel(reason="abort_venv")
    caught_cancel = False
    try:
        _ = pool.ensure_env(colocated_spec, offline=True, wheel_cache_dir=wheels_hp, cancel_token=pre_cancel)
    except TaskCancelledException:
        caught_cancel = True
    check(caught_cancel and not pool.is_env_ready(colocated_spec), "Cancelled ensure_env must not leave ready env")

    missing_spec = ImmutableVenvPool.compute_env_spec("missing_pkg", {"nonexistent-wheel-xyz": "==9.9.9"})
    expect_yscb_code(
        lambda: pool.ensure_env(missing_spec, offline=True, wheel_cache_dir=wheels_hp),
        ErrorCode.ENV_BUILD_FAILED,
    )

    build_v1 = pool.ensure_env(colocated_spec, offline=True, wheel_cache_dir=wheels_hp)
    check(isinstance(build_v1, EnvBuildResult) and (not build_v1.reused) and pool.is_env_ready(colocated_spec))
    build_v1_reuse = pool.ensure_env(colocated_spec, offline=True, wheel_cache_dir=wheels_hp)
    check(build_v1_reuse.reused and build_v1_reuse.env_dir == build_v1.env_dir)

    probe = EnvHealthProbe(pool)
    quick_ok: EnvHealthReport = probe.check_quick(colocated_spec)
    check(quick_ok.quick_ok and not quick_ok.issues, f"Healthy env failed check_quick: {quick_ok}")
    deep_ok = probe.check_deep(colocated_spec, import_modules=("alpha_wheel_lib",))
    check(deep_ok.quick_ok and deep_ok.deep_import_ok is True, f"Healthy env failed check_deep: {deep_ok}")

    meta_file = build_v1.env_dir.path / ".yscb_env_meta.json"
    meta_doc = json.loads(meta_file.read_text(encoding="utf-8"))
    orig_plat = meta_doc["platform_tag"]
    meta_doc["platform_tag"] = "mismatched_platform_arch"
    meta_file.write_text(json.dumps(meta_doc), encoding="utf-8")
    check(
        not pool.is_env_ready(colocated_spec) and not probe.check_quick(colocated_spec).quick_ok,
        "Mismatched platform_tag in .yscb_env_meta.json must fail quick probe",
    )
    meta_doc["platform_tag"] = orig_plat
    meta_doc["complete"] = False
    meta_file.write_text(json.dumps(meta_doc), encoding="utf-8")
    check(not pool.is_env_ready(colocated_spec) and not probe.check_quick(colocated_spec).quick_ok)

    repaired = probe.repair(colocated_spec, offline=True, wheel_cache_dir=wheels_hp)
    check((not repaired.reused) and pool.is_env_ready(colocated_spec), "EnvHealthProbe.repair failed to rebuild env")

    upgraded_spec = ImmutableVenvPool.compute_env_spec("code_intel", {"alpha-wheel-lib": ">=1.3.0"})
    build_v2 = pool.ensure_env(upgraded_spec, offline=True, wheel_cache_dir=wheels_hp)
    check(build_v2.env_dir != build_v1.env_dir and pool.is_env_ready(upgraded_spec))

    dead_staging = yscb_hp.path / ".venv" / f".staging_{upgraded_spec.dirname}_999999_1"
    dead_staging.mkdir(parents=True, exist_ok=True)
    (dead_staging / "partial.txt").write_text("dead", encoding="utf-8")
    orphan_gc_dir = yscb_hp.path / ".venv" / f".staging_gc_orphan_1_{upgraded_spec.dirname}"
    orphan_gc_dir.mkdir(parents=True, exist_ok=True)
    (orphan_gc_dir / "leftover.txt").write_text("orphan", encoding="utf-8")

    gc_keep = EnvGarbageCollector(pool, policy=EnvGcPolicy(grace_days=7.0, keep_inactive_per_group=1))
    gc_res_1: EnvGcResult = gc_keep.collect((upgraded_spec,), force_all=False)
    check(
        HostPath(dead_staging) in gc_res_1.cleaned_staging_dirs
        and HostPath(orphan_gc_dir) in gc_res_1.cleaned_staging_dirs
        and not dead_staging.exists()
        and not orphan_gc_dir.exists(),
        f"Dead-PID .staging_* or .staging_gc_orphan_* directory was not cleaned: {gc_res_1}",
    )
    check(
        build_v1.env_dir in gc_res_1.retained_rollback_dirs and build_v1.env_dir.path.is_dir(),
        f"Recent rollback environment must be retained within 7-day grace window: {gc_res_1}",
    )

    live_staging = yscb_hp.path / ".venv" / f".staging_{upgraded_spec.dirname}_{os.getpid()}_77"
    live_staging.mkdir(parents=True, exist_ok=True)
    (live_staging / "active_build.txt").write_text("building", encoding="utf-8")
    try:
        gc_live_pid = gc_keep.collect((upgraded_spec,), force_all=False)
        check(
            live_staging.is_dir() and HostPath(live_staging) not in gc_live_pid.cleaned_staging_dirs,
            "EnvGarbageCollector must never delete .staging_* owned by a live PID",
        )
    finally:
        shutil.rmtree(live_staging, ignore_errors=True)

    contended_lock = FileLock(
        cache_hp.join("locks", f"env_{colocated_spec.env_hash.short(16)}.lock"),
        allow_transitions=False,
    )
    contended_lock.acquire(shared=False, blocking=False)
    try:
        gc_locked = gc_keep.collect((upgraded_spec,), force_all=True)
        check(
            build_v1.env_dir in gc_locked.skipped_locked_dirs and build_v1.env_dir.path.is_dir(),
            f"Locked environment must be placed in skipped_locked_dirs without failing GC: {gc_locked}",
        )
    finally:
        contended_lock.release()

    future_touch_meta = build_v1.env_dir.path / ".yscb_env_meta.json"
    future_doc = json.loads(future_touch_meta.read_text(encoding="utf-8"))
    future_doc["last_used_epoch_sec"] = time.time() + 120.0
    future_touch_meta.write_text(json.dumps(future_doc), encoding="utf-8")
    gc_fresh_touch = gc_keep.collect((upgraded_spec,), force_all=True)
    check(
        build_v1.env_dir.path.is_dir() and build_v1.env_dir not in gc_fresh_touch.removed_dirs,
        f"Environment touched concurrently after GC scan start must not be deleted even under force_all: {gc_fresh_touch}",
    )

    nometa_spec = ImmutableVenvPool.compute_env_spec("nometa_grp", {"alpha-wheel-lib": "==1.2.0"})
    nometa_dir = pool.get_env_dir(nometa_spec)
    nometa_dir.path.mkdir(parents=True, exist_ok=True)
    (nometa_dir.path / "marker.txt").write_text("inflight", encoding="utf-8")
    nometa_lock = FileLock(
        cache_hp.join("locks", f"env_{nometa_spec.env_hash.short(16)}.lock"),
        allow_transitions=False,
    )
    nometa_lock.acquire(shared=False, blocking=False)
    try:
        gc_nometa = gc_keep.collect((upgraded_spec,), force_all=False)
        check(
            nometa_dir in gc_nometa.skipped_locked_dirs and nometa_dir.path.is_dir(),
            f"Locked env missing .yscb_env_meta.json must still respect hash lock: {gc_nometa}",
        )
    finally:
        nometa_lock.release()
        shutil.rmtree(nometa_dir.path, ignore_errors=True)

    v1_meta_file = build_v1.env_dir.path / ".yscb_env_meta.json"
    v1_meta_doc = json.loads(v1_meta_file.read_text(encoding="utf-8"))
    v1_meta_doc["last_used_epoch_sec"] = time.time() - (9.0 * 86400.0)
    v1_meta_file.write_text(json.dumps(v1_meta_doc), encoding="utf-8")
    gc_expired = gc_keep.collect((upgraded_spec,), force_all=False)
    check(
        build_v1.env_dir in gc_expired.removed_dirs
        and not build_v1.env_dir.path.exists()
        and build_v2.env_dir.path.is_dir(),
        f"Expired (>7d) inactive environment must be evicted automatically: {gc_expired}",
    )

    _build_sdist_tar_gz(wheels_hp.path, "sdist-only-pkg", "1.0.0")
    sdist_spec = ImmutableVenvPool.compute_env_spec("sdist_grp", {"sdist-only-pkg": "==1.0.0"})
    expect_yscb_code(
        lambda: pool.ensure_env(sdist_spec, offline=True, wheel_cache_dir=wheels_hp),
        ErrorCode.ENV_BUILD_FAILED,
    )

    for idx_w in range(6):
        _build_pure_wheel(wheels_hp.path, f"cancel-pkg-{idx_w}", f"cancel_pkg_{idx_w}", "1.0.0", idx_w)
    mid_cancel_spec = ImmutableVenvPool.compute_env_spec(
        "mid_cancel_grp",
        {f"cancel-pkg-{idx_w}": "==1.0.0" for idx_w in range(6)},
    )
    mid_token = CancellationToken()
    mid_errors: list[BaseException] = []

    def _cancel_worker() -> None:
        try:
            _ = pool.ensure_env(
                mid_cancel_spec,
                offline=True,
                wheel_cache_dir=wheels_hp,
                cancel_token=mid_token,
            )
        except BaseException as exc:
            mid_errors.append(exc)

    cancel_thr = threading.Thread(target=_cancel_worker, name="test-mid-cancel", daemon=True)
    cancel_thr.start()
    deadline_cancel = time.monotonic() + 5.0
    while time.monotonic() < deadline_cancel:
        if list((yscb_hp.path / ".venv").glob(".staging_mid_cancel_grp*")):
            mid_token.cancel(reason="mid_flight_abort")
            break
        if not cancel_thr.is_alive():
            break
        time.sleep(0.005)
    else:
        mid_token.cancel(reason="mid_flight_abort_fallback")
    cancel_thr.join(timeout=10.0)
    check(not cancel_thr.is_alive(), "Cancellation worker thread did not terminate within timeout")
    if mid_errors:
        check(
            len(mid_errors) == 1
            and isinstance(mid_errors[0], TaskCancelledException)
            and not pool.is_env_ready(mid_cancel_spec),
            f"Mid-flight cancel must raise TaskCancelledException and leave no ready env: {mid_errors}",
        )
    else:
        check(
            pool.is_env_ready(mid_cancel_spec),
            "Completed ensure_env prior to cancel signal must leave a ready environment",
        )
    check(
        not list((yscb_hp.path / ".venv").glob(".staging_mid_cancel_grp*")),
        "Mid-flight cancelled ensure_env must clean up all .staging_* directories",
    )

    conc_spec = ImmutableVenvPool.compute_env_spec("conc_grp", {"alpha-wheel-lib": "==1.3.0"})
    barrier = threading.Barrier(4)
    conc_results: list[EnvBuildResult] = []
    conc_errs: list[BaseException] = []
    conc_lock = threading.Lock()

    def _conc_worker() -> None:
        try:
            barrier.wait(timeout=5.0)
            res = pool.ensure_env(conc_spec, offline=True, wheel_cache_dir=wheels_hp)
            with conc_lock:
                conc_results.append(res)
        except BaseException as exc:
            with conc_lock:
                conc_errs.append(exc)

    conc_threads = [threading.Thread(target=_conc_worker, daemon=True) for _ in range(4)]
    for t in conc_threads:
        t.start()
    for t in conc_threads:
        t.join(timeout=30.0)
    check(all(not t.is_alive() for t in conc_threads), "Concurrent ensure_env threads did not finish cleanly")
    check(
        not conc_errs
        and len(conc_results) == 4
        and len({r.env_dir for r in conc_results}) == 1
        and sum(1 for r in conc_results if r.reused) >= 3,
        f"Concurrent ensure_env FileLock double-check reuse failed: results={conc_results}, errs={conc_errs}",
    )


def _build_sanitized_subprocess_env() -> dict[str, str]:
    core_src_root = str(Path(__file__).resolve().parents[1] / "source" / "core")
    core_v2_root = str(Path(__file__).resolve().parents[1])
    blocked_exact = {"YSCB_OFFLINE", "YSCB_NO_UPDATE_CHECK", TEST_SANDBOX_ENV_KEY}
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in blocked_exact and not k.upper().endswith("_PROXY")
    }
    existing_py = clean_env.get("PYTHONPATH", "")
    prefix_paths = os.pathsep.join((core_src_root, core_v2_root))
    clean_env["PYTHONPATH"] = f"{prefix_paths}{os.pathsep}{existing_py}" if existing_py else prefix_paths
    return clean_env


def _run_clean_env_update_checker_checks(
    host_dir: HostPath,
    yscb_root: HostPath,
    ins_ws: Path,
    base_url: str,
    remote_yscb_lf: bytes,
    can_make_sym: bool,
) -> None:
    (host_dir.path / "yscb.py").write_bytes(remote_yscb_lf.replace(b"\n", b"\r\n"))
    child_script = r"""
import os
from pathlib import Path
import sys

from core.foundation import HostPath, ModuleId, SemVer4
from core.metadata.config import ConfigStore, ReleaseUrgency
from core.packaging.installer import ProviderClient, UpdateChecker

host_dir = HostPath(Path(sys.argv[1]))
yscb_root = HostPath(Path(sys.argv[2]))
ins_ws = Path(sys.argv[3])
base_url = sys.argv[4]
can_make_sym = sys.argv[5] == "1"

cfg_store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
prov_online = ProviderClient(yscb_root=yscb_root, default_provider=base_url, offline=False)
checker = UpdateChecker(
    host_dir=host_dir,
    yscb_root=yscb_root,
    config_store=cfg_store,
    provider=prov_online,
    self_update_url=f"{base_url}/yscb.py",
)
upd_first = checker.check_if_due(force=False, offline=False)
alpha_cand = next((c for c in upd_first.candidates if c.module_id == ModuleId("alpha")), None)
if not (
    alpha_cand is not None
    and alpha_cand.latest_version == SemVer4.parse("3.0.0")
    and alpha_cand.max_urgency == ReleaseUrgency.CRITICAL
    and any("2.0.5" in s for s in alpha_cand.summaries)
    and upd_first.yscb_host_drift is False
):
    raise SystemExit(f"UpdateChecker initial check failed: {upd_first!r}")

upd_throttled = checker.check_if_due(force=False, offline=False)
if upd_throttled.throttled is not True:
    raise SystemExit(f"Expected throttled second check, got {upd_throttled!r}")

(host_dir.path / "yscb.py").write_bytes(b"#!/usr/bin/env python3\n# outdated launcher\n")
upd_drift = checker.check_if_due(force=True, offline=False)
if upd_drift.yscb_host_drift is not True:
    raise SystemExit(f"Expected host drift detection, got {upd_drift!r}")

if can_make_sym:
    ext_script = ins_ws / "external_yscb_drift.py"
    ext_script.write_bytes(b"#!/usr/bin/env python3\n# external target\n")
    sym_script_url = host_dir.path / "sym_yscb_ref.py"
    os.symlink(ext_script, sym_script_url)
    try:
        sym_checker_root = HostPath(ins_ws / "sym_uc_root")
        sym_checker_root.path.mkdir(parents=True, exist_ok=True)
        sym_checker = UpdateChecker(
            host_dir=host_dir,
            yscb_root=sym_checker_root,
            config_store=cfg_store,
            provider=prov_online,
            self_update_url="sym_yscb_ref.py",
        )
        sym_uc_rep = sym_checker.check_if_due(force=True, offline=False)
        if sym_uc_rep.yscb_host_drift is not False:
            raise SystemExit("Expected symlink self_update_url refusal")
    finally:
        sym_script_url.unlink(missing_ok=True)

dead_yscb_root = HostPath(ins_ws / "dead_uc_root")
dead_yscb_root.path.mkdir(parents=True, exist_ok=True)
prov_dead = ProviderClient(
    yscb_root=dead_yscb_root,
    default_provider="http://127.0.0.1:1",
    offline=False,
    timeout_sec=0.1,
)
dead_checker = UpdateChecker(
    host_dir=host_dir,
    yscb_root=dead_yscb_root,
    config_store=cfg_store,
    provider=prov_dead,
    self_update_url="http://127.0.0.1:1/yscb.py",
)
dead_first = dead_checker.check_if_due(force=False, offline=False)
dead_second = dead_checker.check_if_due(force=False, offline=False)
if not (dead_first.throttled is False and dead_second.throttled is True):
    raise SystemExit(f"Unreachable throttle pre-stamp failed: {dead_first!r} / {dead_second!r}")
"""
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            child_script,
            str(host_dir.path),
            str(yscb_root.path),
            str(ins_ws),
            base_url,
            "1" if can_make_sym else "0",
        ],
        env=_build_sanitized_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )
    check(
        proc.returncode == 0,
        f"Sanitized UpdateChecker subprocess check failed (rc={proc.returncode}): {proc.stderr or proc.stdout}",
    )


def _verify_dual_dns_public_to_private_ssrf_guard(yscb_root: HostPath, srv_port: int) -> None:
    child_script = """
from pathlib import Path
import socket
import sys

from core.foundation import ErrorCode, HostPath, ModuleId, YscbError
from core.packaging.installer import ProviderClient

yscb_root = HostPath(Path(sys.argv[1]))
port_num = int(sys.argv[2])
real_getaddrinfo = socket.getaddrinfo


def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    clean_h = host.strip().lower() if isinstance(host, str) else ""
    if clean_h == "dual-origin.example":
        if port is None:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
            ]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", int(port)))]
    if clean_h == "public-only.example":
        if port is None:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", int(port)))]
    return real_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = fake_getaddrinfo
client = ProviderClient(yscb_root=yscb_root, default_provider=f"http://127.0.0.1:{port_num}", offline=False)
for origin_host in ("dual-origin.example", "public-only.example"):
    for scheme_tok in ("http", "https"):
        try:
            client.fetch_index(ModuleId("evil"), provider=f"{scheme_tok}://{origin_host}:{port_num}/loopbackredir")
        except YscbError as exc:
            if exc.detail.code != ErrorCode.SECURITY_GATED:
                raise SystemExit(f"Expected SECURITY_GATED for {scheme_tok}://{origin_host}, got {exc.detail.code}")
        else:
            raise SystemExit(f"Expected SSRF / DNS-rebinding block for {scheme_tok}://{origin_host}")

for forbidden_url in (
    f"https://169.254.169.254:{port_num}/latest/meta-data",
    f"https://0.0.0.0:{port_num}/meta",
):
    try:
        client.fetch_index(ModuleId("evil"), provider=forbidden_url)
    except YscbError as exc:
        if exc.detail.code != ErrorCode.SECURITY_GATED:
            raise SystemExit(f"Expected SECURITY_GATED for {forbidden_url}, got {exc.detail.code}")
    else:
        raise SystemExit(f"Expected link-local / unspecified IP block for {forbidden_url}")
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", child_script, str(yscb_root.path), str(srv_port)],
        env=_build_sanitized_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=20.0,
        check=False,
    )
    check(
        proc.returncode == 0,
        f"Dual-DNS public-to-private SSRF subprocess test failed (rc={proc.returncode}): {proc.stderr or proc.stdout}",
    )


def _verify_locked_workspace_dirs_snapshot_and_tx_rollback(base_root: Path) -> None:
    lock_ws = base_root / "ext_contract_suite" / "locked_rollback_ws"
    lock_ws.mkdir(parents=True, exist_ok=True)
    host_dir = HostPath(lock_ws)
    yscb_root = HostPath(lock_ws / ".yscb")
    repo_dir = lock_ws / "repo"
    (repo_dir / "core").mkdir(parents=True, exist_ok=True)
    (repo_dir / "keepmod").mkdir(parents=True, exist_ok=True)
    (repo_dir / "failtmpl").mkdir(parents=True, exist_ok=True)
    (repo_dir / "goodstep").mkdir(parents=True, exist_ok=True)

    core_b, core_sha = _build_module_zip_bytes("core", "2.0.0.0")
    keep_v1_b, keep_v1_sha = _build_module_zip_bytes(
        "keepmod",
        "2.0.0.0",
        dependencies={"core": ">=2.0.0.0"},
        tmpl_files={"settings.json.tmpl": '{"tier": "baseline"}\n'},
    )
    good_step_b, good_step_sha = _build_module_zip_bytes(
        "goodstep",
        "2.0.0.0",
        dependencies={"core": ">=2.0.0.0"},
        tmpl_files={"step.json.tmpl": '{"step": 1}\n'},
    )
    fail_tmpl_b, fail_tmpl_sha = _build_module_zip_bytes(
        "failtmpl",
        "2.0.0.0",
        dependencies={"core": ">=2.0.0.0"},
        extra_files={"configurable/bad_raw.json": b'{"illegal": true}\n'},
    )
    (repo_dir / "core" / "2.0.0.0.zip").write_bytes(core_b)
    (repo_dir / "core" / "index.json").write_text(
        json.dumps({"module_id": "core", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"sha256": core_sha, "status": "active"}}}),
        encoding="utf-8",
    )
    (repo_dir / "keepmod" / "2.0.0.0.zip").write_bytes(keep_v1_b)
    (repo_dir / "keepmod" / "index.json").write_text(
        json.dumps({"module_id": "keepmod", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"sha256": keep_v1_sha, "status": "active"}}}),
        encoding="utf-8",
    )
    (repo_dir / "goodstep" / "2.0.0.0.zip").write_bytes(good_step_b)
    (repo_dir / "goodstep" / "index.json").write_text(
        json.dumps({"module_id": "goodstep", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"sha256": good_step_sha, "status": "active"}}}),
        encoding="utf-8",
    )
    (repo_dir / "failtmpl" / "2.0.0.0.zip").write_bytes(fail_tmpl_b)
    (repo_dir / "failtmpl" / "index.json").write_text(
        json.dumps({"module_id": "failtmpl", "versions": ["2.0.0.0"], "releases": {"2.0.0.0": {"sha256": fail_tmpl_sha, "status": "active"}}}),
        encoding="utf-8",
    )

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    store.save_host_config(HostConfig(yscb_root=".yscb", default_provider=str(repo_dir), installed_modules={}))
    vault = SnapshotVault(
        host_dir=host_dir,
        yscb_root=yscb_root,
        policy=SnapshotRetentionPolicy(max_snapshots=5, max_age_days=7.0, coalesce_window_sec=60.0),
    )
    pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=HostPath(yscb_root.path / ".cache"))
    vfs = VfsHub(UriMountTable(build_standard_mount_rules(host_dir, yscb_root))).for_kernel()
    eng = OfflinePackageEngine(
        host_dir=host_dir,
        yscb_root=yscb_root,
        config_store=store,
        snapshot_vault=vault,
        env_pool=pool,
        vfs=vfs,
    )
    _ = eng.install(
        (
            PackageRequest(module_id=ModuleId("core"), version_spec="==2.0.0.0"),
            PackageRequest(module_id=ModuleId("keepmod"), version_spec="==2.0.0.0"),
        )
    )
    storage_mod_dir = yscb_root.path / "storage" / "keepmod"
    config_mod_dir = yscb_root.path / "config" / "keepmod"
    storage_mod_dir.mkdir(parents=True, exist_ok=True)
    (storage_mod_dir / "state.json").write_text('{"saved": 42}\n', encoding="utf-8")
    snap_clean = vault.create_snapshot("locked_baseline", force=True)

    storage_holder = ManagedProcessTree(
        [sys.executable, "-B", "-c", "import time; time.sleep(0.8)"],
        cwd=HostPath(storage_mod_dir),
    )
    config_holder = ManagedProcessTree(
        [sys.executable, "-B", "-c", "import time; time.sleep(0.8)"],
        cwd=HostPath(config_mod_dir),
    )
    try:
        time.sleep(0.08)
        (storage_mod_dir / "state.json").write_text('{"saved": 999}\n', encoding="utf-8")
        (storage_mod_dir / "transient.json").write_text('{"temp": true}\n', encoding="utf-8")
        (config_mod_dir / "settings.json").write_text('{"tier": "mutated"}\n', encoding="utf-8")
        _ = vault.restore_snapshot(snap_clean.snapshot_id)
        check(
            json.loads((storage_mod_dir / "state.json").read_text(encoding="utf-8")) == {"saved": 42}
            and not (storage_mod_dir / "transient.json").exists()
            and json.loads((config_mod_dir / "settings.json").read_text(encoding="utf-8")) == {"tier": "baseline"},
            "SnapshotVault.restore_snapshot failed while child processes held cwd inside storage/ and config/",
        )

        expect_yscb_code(
            lambda: eng.install(
                (
                    PackageRequest(module_id=ModuleId("goodstep"), version_spec="==2.0.0.0"),
                    PackageRequest(module_id=ModuleId("failtmpl"), version_spec="==2.0.0.0"),
                )
            ),
            ErrorCode.CONFIG_INVALID,
        )
        store.reload()
        post_cfg = store.load_host_config()
        check(
            ModuleId("goodstep") not in post_cfg.installed_modules
            and ModuleId("failtmpl") not in post_cfg.installed_modules
            and not (yscb_root.path / ".modules" / "goodstep").exists()
            and not (yscb_root.path / "config" / "goodstep").exists()
            and json.loads((storage_mod_dir / "state.json").read_text(encoding="utf-8")) == {"saved": 42},
            f"Transactional rollback under cwd-locked storage/config left partial state: {post_cfg}",
        )
    finally:
        storage_holder.terminate_tree(grace_sec=0.5)
        config_holder.terminate_tree(grace_sec=0.5)

    sim_script = r"""
import json
import os
from pathlib import Path
import sys

from core.filesystem.vfs import UriMountTable, VfsHub, build_standard_mount_rules
from core.foundation import ErrorCode, HostPath, ModuleId, YscbError
from core.metadata.config import ConfigStore, SnapshotRetentionPolicy, SnapshotVault
from core.packaging.env import ImmutableVenvPool
from core.packaging.installer import OfflinePackageEngine, PackageRequest

ws_dir = Path(sys.argv[1])
host_dir = HostPath(ws_dir)
yscb_root = HostPath(ws_dir / ".yscb")
real_replace = os.replace
locked_names = {"config", ".config.local", "storage"}


def locked_dir_replace(src, dst, *args, **kwargs):
    src_s = os.fspath(src)
    dst_s = os.fspath(dst)
    if os.path.isdir(src_s) and (
        os.path.basename(src_s) in locked_names or os.path.basename(dst_s) in locked_names
    ):
        raise PermissionError(13, "Simulated directory handle lock", src_s, 32, dst_s)
    return real_replace(src, dst, *args, **kwargs)


os.replace = locked_dir_replace
store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
vault = SnapshotVault(
    host_dir=host_dir,
    yscb_root=yscb_root,
    policy=SnapshotRetentionPolicy(max_snapshots=5, max_age_days=7.0, coalesce_window_sec=60.0),
)
snaps = vault.list_snapshots()
if not snaps:
    raise SystemExit("Expected existing snapshot")
snap_id = snaps[0].snapshot_id
(yscb_root.path / "storage" / "keepmod" / "state.json").write_text('{"saved": 777}\n', encoding="utf-8")
(yscb_root.path / "storage" / "keepmod" / "extra_locked.json").write_text('{"drop": 1}\n', encoding="utf-8")
(yscb_root.path / "config" / "keepmod" / "settings.json").write_text('{"tier": "dirty"}\n', encoding="utf-8")
vault.restore_snapshot(snap_id)
if json.loads((yscb_root.path / "storage" / "keepmod" / "state.json").read_text(encoding="utf-8")) != {"saved": 42}:
    raise SystemExit("In-place SnapshotVault restore failed on state.json")
if (yscb_root.path / "storage" / "keepmod" / "extra_locked.json").exists():
    raise SystemExit("In-place SnapshotVault restore failed to prune extra_locked.json")
if json.loads((yscb_root.path / "config" / "keepmod" / "settings.json").read_text(encoding="utf-8")) != {"tier": "baseline"}:
    raise SystemExit("In-place SnapshotVault restore failed on settings.json")

pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=HostPath(yscb_root.path / ".cache"))
vfs = VfsHub(UriMountTable(build_standard_mount_rules(host_dir, yscb_root))).for_kernel()
eng = OfflinePackageEngine(
    host_dir=host_dir,
    yscb_root=yscb_root,
    config_store=store,
    snapshot_vault=vault,
    env_pool=pool,
    vfs=vfs,
)
try:
    eng.install(
        (
            PackageRequest(module_id=ModuleId("goodstep"), version_spec="==2.0.0.0"),
            PackageRequest(module_id=ModuleId("failtmpl"), version_spec="==2.0.0.0"),
        )
    )
except YscbError as exc:
    if exc.detail.code != ErrorCode.CONFIG_INVALID:
        raise SystemExit(f"Unexpected error code: {exc.detail.code}")
else:
    raise SystemExit("Expected install failure for failtmpl")

store.reload()
cfg_after = store.load_host_config()
if ModuleId("goodstep") in cfg_after.installed_modules or (yscb_root.path / ".modules" / "goodstep").exists():
    raise SystemExit("In-place tx_guard rollback failed to clean goodstep")
if (yscb_root.path / "config" / "goodstep").exists():
    raise SystemExit("In-place tx_guard rollback failed to prune config/goodstep")
"""
    sim_proc = subprocess.run(
        [sys.executable, "-B", "-c", sim_script, str(lock_ws)],
        env=_build_sanitized_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )
    check(
        sim_proc.returncode == 0,
        f"Simulated directory-lock in-place fallback subprocess check failed (rc={sim_proc.returncode}): {sim_proc.stderr or sim_proc.stdout}",
    )


def _verify_packaging_installer_engine_and_update_checker(suite_root: Path) -> None:
    ins_ws = suite_root / "installer_suite"
    host_dir = HostPath(ins_ws / "repo")
    yscb_root = HostPath(ins_ws / "repo" / ".yscb")
    proj_root = HostPath(ins_ws / "repo" / "project")
    for p in (host_dir.path, yscb_root.path, proj_root.path):
        p.mkdir(parents=True, exist_ok=True)

    wheels_cache = yscb_root.path / ".cache" / "wheels"
    _build_pure_wheel(wheels_cache, "alpha-wheel-lib", "alpha_wheel_lib", "1.2.0", 120)

    core_200_bytes, core_200_sha = _build_module_zip_bytes("core", "2.0.0")
    core_210_bytes, core_210_sha = _build_module_zip_bytes("core", "2.1.0")
    alpha_200_bytes, alpha_200_sha = _build_module_zip_bytes(
        "alpha",
        "2.0.0",
        dependencies={"core": ">=2.0.0"},
        config_defaults={"workers": 2, "mode": "std"},
        tmpl_files={
            "config.project.json.tmpl": json.dumps({"workers": 2, "mode": "std"}) + "\n",
            "notes.json.tmpl": '{"hello": "tmpl"}\n',
        },
    )
    alpha_210_bytes, alpha_210_sha = _build_module_zip_bytes(
        "alpha",
        "2.1.0",
        dependencies={"core": ">=2.0.0"},
        config_defaults={"workers": 2, "mode": "std", "new_flag": True},
        tmpl_files={
            "config.project.json.tmpl": json.dumps({"workers": 2, "mode": "std", "new_flag": True}) + "\n",
            "notes.json.tmpl": '{"hello": "updated_tmpl_must_not_overwrite"}\n',
        },
    )
    alpha_300_bytes, alpha_300_sha = _build_module_zip_bytes("alpha", "3.0.0", dependencies={"core": ">=2.0.0"})
    tier1_mod_bytes, tier1_mod_sha = _build_module_zip_bytes(
        "intel",
        "2.0.0",
        dependencies={"alpha": ">=2.0.0"},
        pip_dependencies={"alpha-wheel-lib": "==1.2.0"},
        venv_group="intel_grp",
    )
    leaf_200_bytes, leaf_200_sha = _build_module_zip_bytes(
        "leaf",
        "2.0.0",
        dependencies={"core": ">=2.0.0,<2.1.0"},
    )
    leaf_210_bytes, leaf_210_sha = _build_module_zip_bytes(
        "leaf",
        "2.1.0",
        dependencies={"core": ">=2.1.0"},
    )
    omitted_dep_bytes, omitted_dep_sha = _build_module_zip_bytes(
        "omitted-dep",
        "2.0.0",
        dependencies={"gamma": ">=2.0.0.2"},
    )
    pin_conflict_bytes, pin_conflict_sha = _build_module_zip_bytes(
        "pin-conflict",
        "2.0.0",
        dependencies={"alpha": ">=3.0.0"},
    )
    conflict_mod_bytes, conflict_mod_sha = _build_module_zip_bytes(
        "broken",
        "2.0.0",
        dependencies={"core": ">=9.0.0"},
    )
    badtmpl_bytes, badtmpl_sha = _build_module_zip_bytes(
        "badtmpl",
        "2.0.0",
        dependencies={"core": ">=2.0.0"},
        extra_files={"configurable/unstripped.json": b'{"bad": 1}\n'},
    )
    pruned_active_bytes, pruned_active_sha = _build_module_zip_bytes("gamma", "2.0.0.2")

    zip_slip_buf_fd, zip_slip_raw = tempfile.mkstemp(suffix=".zip")
    os.close(zip_slip_buf_fd)
    zip_slip_p = Path(zip_slip_raw)
    try:
        with zipfile.ZipFile(zip_slip_p, "w") as zf:
            zf.writestr("../escape.py", "evil = 1\n")
        zip_slip_bytes = zip_slip_p.read_bytes()
    finally:
        zip_slip_p.unlink(missing_ok=True)
    corrupt_crc_bytes = bytearray(core_200_bytes)
    corrupt_crc_bytes[len(corrupt_crc_bytes) // 2] ^= 0xFF

    zi_abs = zipfile.ZipInfo("/etc/passwd")
    zi_drive = zipfile.ZipInfo("C:/evil.py")
    zi_ctrl = zipfile.ZipInfo("bad\x07file.py")
    zi_sym = zipfile.ZipInfo("evil_link.py")
    zi_sym.external_attr = (stat.S_IFLNK | 0o777) << 16
    zi_case_a = zipfile.ZipInfo("Pkg.py")
    zi_case_b = zipfile.ZipInfo("pkg.py")
    zi_dir_case_a = zipfile.ZipInfo("Pkg/a.py")
    zi_dir_case_b = zipfile.ZipInfo("pkg/b.py")
    zi_file_vs_dir_a = zipfile.ZipInfo("foo")
    zi_file_vs_dir_b = zipfile.ZipInfo("FOO/bar.py")
    zi_bomb = zipfile.ZipInfo("bomb.bin")
    zip_abs_bytes = _build_custom_zip_bytes(((zi_abs, b"x"),))
    zip_drive_bytes = _build_custom_zip_bytes(((zi_drive, b"x"),))
    zip_ctrl_bytes = _build_custom_zip_bytes(((zi_ctrl, b"x"),))
    zip_sym_bytes = _build_custom_zip_bytes(((zi_sym, b"target"),))
    zip_case_bytes = _build_custom_zip_bytes(((zi_case_a, b"A = 1\n"), (zi_case_b, b"B = 2\n")))
    zip_dir_case_bytes = _build_custom_zip_bytes(((zi_dir_case_a, b"A = 1\n"), (zi_dir_case_b, b"B = 2\n")))
    zip_file_dir_col_bytes = _build_custom_zip_bytes(((zi_file_vs_dir_a, b"x"), (zi_file_vs_dir_b, b"y")))
    zip_bomb_bytes = _build_custom_zip_bytes(((zi_bomb, b"\x00" * (33 * 1024 * 1024)),))
    zip_nodesc_bytes = _build_custom_zip_bytes(
        ((zipfile.ZipInfo("manifest.json"), b'{"schema_version": 2, "id": "nodesc", "version": "2.0.0"}\n'),)
    )
    remote_yscb_lf = b"#!/usr/bin/env python3\n# launcher v2\n"
    routes: dict[str, bytes] = {
        "/core/index.json": json.dumps(
            {
                "module_id": "core",
                "versions": ["2.0.0", "2.1.0"],
                "releases": {
                    "2.0.0": {"version": "2.0.0", "sha256": core_200_sha, "status": "active", "urgency": "optional"},
                    "2.1.0": {
                        "version": "2.1.0",
                        "sha256": core_210_sha,
                        "status": "active",
                        "urgency": "recommended",
                        "summary": "Core 2.1",
                    },
                },
            }
        ).encode("utf-8"),
        "/core/2.0.0.zip": core_200_bytes,
        "/core/2.1.0.zip": core_210_bytes,
        "/alpha/index.json": json.dumps(
            {
                "module_id": "alpha",
                "versions": ["2.0.0", "2.0.5", "2.1.0", "3.0.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": alpha_200_sha,
                        "status": "active",
                        "dependencies": {"core": ">=2.0.0"},
                        "urgency": "optional",
                    },
                    "2.0.5": {
                        "version": "2.0.5",
                        "sha256": "0" * 64,
                        "status": "pruned",
                        "urgency": "critical",
                        "summary": "Security fix in pruned 2.0.5",
                    },
                    "2.1.0": {
                        "version": "2.1.0",
                        "sha256": alpha_210_sha,
                        "status": "active",
                        "dependencies": {"core": ">=2.1.0"},
                        "urgency": "recommended",
                        "summary": "Feature 2.1.0",
                    },
                    "3.0.0": {
                        "version": "3.0.0",
                        "sha256": alpha_300_sha,
                        "status": "active",
                        "dependencies": {"core": ">=2.1.0"},
                        "urgency": "optional",
                    },
                },
            }
        ).encode("utf-8"),
        "/alpha/2.0.0.zip": alpha_200_bytes,
        "/alpha/2.1.0.zip": alpha_210_bytes,
        "/alpha/3.0.0.zip": alpha_300_bytes,
        "/leaf/index.json": json.dumps(
            {
                "module_id": "leaf",
                "versions": ["2.0.0", "2.1.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": leaf_200_sha,
                        "status": "active",
                        "dependencies": {"core": ">=2.0.0,<2.1.0"},
                    },
                    "2.1.0": {
                        "version": "2.1.0",
                        "sha256": leaf_210_sha,
                        "status": "active",
                        "dependencies": {"core": ">=2.1.0"},
                    },
                },
            }
        ).encode("utf-8"),
        "/leaf/2.0.0.zip": leaf_200_bytes,
        "/leaf/2.1.0.zip": leaf_210_bytes,
        "/omitted-dep/index.json": json.dumps(
            {
                "module_id": "omitted-dep",
                "versions": ["2.0.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": omitted_dep_sha,
                        "status": "active",
                    }
                },
            }
        ).encode("utf-8"),
        "/omitted-dep/2.0.0.zip": omitted_dep_bytes,
        "/pin-conflict/index.json": json.dumps(
            {
                "module_id": "pin-conflict",
                "versions": ["2.0.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": pin_conflict_sha,
                        "status": "active",
                    }
                },
            }
        ).encode("utf-8"),
        "/pin-conflict/2.0.0.zip": pin_conflict_bytes,
        "/intel/index.json": json.dumps(
            {
                "module_id": "intel",
                "versions": ["2.0.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": tier1_mod_sha,
                        "status": "active",
                        "dependencies": {"alpha": ">=2.0.0"},
                    }
                },
            }
        ).encode("utf-8"),
        "/intel/2.0.0.zip": tier1_mod_bytes,
        "/broken/index.json": json.dumps(
            {
                "module_id": "broken",
                "versions": ["2.0.0"],
                "releases": {
                    "2.0.0": {
                        "version": "2.0.0",
                        "sha256": conflict_mod_sha,
                        "status": "active",
                        "dependencies": {"core": ">=9.0.0"},
                    }
                },
            }
        ).encode("utf-8"),
        "/broken/2.0.0.zip": conflict_mod_bytes,
        "/gamma/index.json": json.dumps(
            {
                "module_id": "gamma",
                "versions": ["2.0.0.1", "2.0.0.2"],
                "releases": {
                    "2.0.0.1": {"version": "2.0.0.1", "sha256": "a" * 64, "status": "pruned"},
                    "2.0.0.2": {"version": "2.0.0.2", "sha256": pruned_active_sha, "status": "active"},
                },
            }
        ).encode("utf-8"),
        "/gamma/2.0.0.2.zip": pruned_active_bytes,
        "/badtmpl/index.json": json.dumps({"module_id": "badtmpl", "versions": ["2.0.0"], "releases": {"2.0.0": {"version": "2.0.0", "sha256": badtmpl_sha, "status": "active"}}}).encode("utf-8"),
        "/badtmpl/2.0.0.zip": badtmpl_bytes,
        "/slip/2.0.0.zip": zip_slip_bytes,
        "/abspath/2.0.0.zip": zip_abs_bytes,
        "/drivepath/2.0.0.zip": zip_drive_bytes,
        "/ctrlchar/2.0.0.zip": zip_ctrl_bytes,
        "/zipsym/2.0.0.zip": zip_sym_bytes,
        "/casecol/2.0.0.zip": zip_case_bytes,
        "/dircase/2.0.0.zip": zip_dir_case_bytes,
        "/filedircol/2.0.0.zip": zip_file_dir_col_bytes,
        "/zipbomb/2.0.0.zip": zip_bomb_bytes,
        "/nodesc/2.0.0.zip": zip_nodesc_bytes,
        "/corrupt/2.0.0.zip": bytes(corrupt_crc_bytes),
        "/yscb.py": remote_yscb_lf,
    }

    http_state = _RepoHttpMirrorState(routes)
    srv, srv_thr, base_url = _start_test_http_mirror(http_state)
    try:
        prov_online = ProviderClient(yscb_root=yscb_root, default_provider=base_url, offline=False, timeout_sec=5.0)
        prov_offline = ProviderClient(yscb_root=yscb_root, default_provider=base_url, offline=True, timeout_sec=5.0)
        mirror = MirrorStore(yscb_root=yscb_root)

        tmp_dl_dir = HostPath(ins_ws / "dl_checks")
        tmp_dl_dir.path.mkdir(parents=True, exist_ok=True)
        expect_yscb_code(
            lambda: prov_online.fetch_package_zip(
                ModuleId("oversized"), SemVer4.parse("9.9.9"), tmp_dl_dir.join("over.zip"), ignore_sha256=True
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )
        expect_yscb_code(
            lambda: prov_online.fetch_package_zip(
                ModuleId("slip"), SemVer4.parse("2.0.0"), tmp_dl_dir.join("slip.zip"), ignore_sha256=True
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )
        for bad_mod in (
            "abspath",
            "drivepath",
            "ctrlchar",
            "zipsym",
            "casecol",
            "dircase",
            "filedircol",
            "zipbomb",
        ):
            expect_yscb_code(
                lambda m=bad_mod: prov_online.fetch_package_zip(
                    ModuleId(m), SemVer4.parse("2.0.0"), tmp_dl_dir.join(f"{m}.zip"), ignore_sha256=True
                ),
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
            )
        nodesc_local = tmp_dl_dir.join("nodesc_raw.zip")
        nodesc_local.path.write_bytes(zip_nodesc_bytes)
        mirror.verify_zip_integrity(nodesc_local, ignore_sha256=True)

        bad_nodesc_dep = HostPath(ins_ws / "nodesc_check")
        nodesc_yscb = HostPath(bad_nodesc_dep.path / ".yscb")
        nodesc_proj = HostPath(bad_nodesc_dep.path / "project")
        for sub_dir_p in (bad_nodesc_dep.path, nodesc_yscb.path, nodesc_proj.path):
            sub_dir_p.mkdir(parents=True, exist_ok=True)
        nodesc_vfs = VfsHub(
            UriMountTable(build_standard_mount_rules(bad_nodesc_dep, nodesc_yscb, project_root=nodesc_proj))
        ).for_kernel()
        nodesc_deployer = AtomicPackageDeployer(
            yscb_root=nodesc_yscb,
            config_store=ConfigStore(host_dir=bad_nodesc_dep, yscb_root=nodesc_yscb),
            vfs=nodesc_vfs,
        )
        expect_yscb_code(
            lambda: nodesc_deployer.materialize_module(ModuleId("nodesc"), nodesc_local),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )

        ext_mirror_dir = ins_ws / "ext_mirror_target"
        (ext_mirror_dir / "core").mkdir(parents=True, exist_ok=True)
        (ext_mirror_dir / "core" / "index.json").write_bytes(routes["/core/index.json"])
        sym_prov_link = yscb_root.path / "sym_provider"
        can_make_sym = True
        try:
            os.symlink(ext_mirror_dir, sym_prov_link, target_is_directory=True)
        except (OSError, NotImplementedError):
            can_make_sym = False
        if can_make_sym:
            prov_sym = ProviderClient(yscb_root=yscb_root, default_provider="sym_provider", offline=True)
            expect_yscb_code(
                lambda: prov_sym.fetch_index(ModuleId("core")),
                ErrorCode.SECURITY_GATED,
            )
            sym_prov_link.unlink(missing_ok=True)

        sub_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from core.foundation import ErrorCode, HostPath, ModuleId, YscbError\n"
            "from core.packaging.installer import ProviderClient, UpdateChecker\n"
            "from core.metadata.config import ConfigStore, HostConfig\n"
            "root = HostPath(Path(sys.argv[1]))\n"
            "host = HostPath(Path(sys.argv[2]))\n"
            "url = sys.argv[3]\n"
            "p = ProviderClient(yscb_root=root, default_provider=url, offline=False)\n"
            "try:\n"
            "    p.fetch_index(ModuleId('core'))\n"
            "    sys.exit(3)\n"
            "except YscbError as e:\n"
            "    if e.detail.code != ErrorCode.TRANSPORT_LOST:\n"
            "        sys.exit(4)\n"
            "cs = ConfigStore(host_dir=host, yscb_root=root)\n"
            "cs.save_host_config(HostConfig(yscb_root='.yscb', default_provider=url, installed_modules={}))\n"
            "uc = UpdateChecker(host_dir=host, yscb_root=root, config_store=cs, provider=p, self_update_url=url + '/yscb.py')\n"
            "rep = uc.check_if_due(force=True, offline=False)\n"
            "if rep.candidates or rep.yscb_host_drift:\n"
            "    sys.exit(5)\n"
        )
        core_src_dir = str(Path(__file__).resolve().parents[1] / "source" / "core")
        sub_res = subprocess.run(
            [sys.executable, "-B", "-c", sub_code, str(bad_nodesc_dep.path / ".yscb"), str(bad_nodesc_dep.path), base_url],
            env={**os.environ, "YSCB_OFFLINE": "1", "PYTHONPATH": core_src_dir},
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
        check(sub_res.returncode == 0, f"YSCB_OFFLINE=1 subprocess enforcement failed: rc={sub_res.returncode}, err={sub_res.stderr}")

        sandbox_silence_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from core.foundation import HostPath, ModuleId, SemVer4\n"
            "from core.packaging.installer import ProviderClient, UpdateChecker\n"
            "from core.metadata.config import ConfigStore, HostConfig, InstalledModuleRecord\n"
            "root = HostPath(Path(sys.argv[1]))\n"
            "host = HostPath(Path(sys.argv[2]))\n"
            "url = sys.argv[3]\n"
            "(host.path / 'yscb.py').write_bytes(b'# old\\n')\n"
            "p = ProviderClient(yscb_root=root, default_provider=url, offline=False)\n"
            "cs = ConfigStore(host_dir=host, yscb_root=root)\n"
            "cs.save_host_config(HostConfig(yscb_root='.yscb', default_provider=url, installed_modules={\n"
            "    ModuleId('core'): InstalledModuleRecord(version=SemVer4.parse('2.0.0'), installed_at='2026-11-22T00:00:00Z', provider=url)\n"
            "}))\n"
            "uc = UpdateChecker(host_dir=host, yscb_root=root, config_store=cs, provider=p, self_update_url=url + '/yscb.py')\n"
            "rep = uc.check_if_due(force=True, offline=False)\n"
            "if rep.candidates or rep.yscb_host_drift or rep.checked_at_utc:\n"
            "    sys.exit(6)\n"
        )
        sandbox_sub_dir = ins_ws / "sandbox_uc_sub"
        (sandbox_sub_dir / ".yscb").mkdir(parents=True, exist_ok=True)
        clean_sub_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_OFFLINE", "YSCB_NO_UPDATE_CHECK")}
        clean_sub_env[TEST_SANDBOX_ENV_KEY] = "1"
        clean_sub_env["PYTHONPATH"] = core_src_dir
        sandbox_res = subprocess.run(
            [sys.executable, "-B", "-c", sandbox_silence_code, str(sandbox_sub_dir / ".yscb"), str(sandbox_sub_dir), base_url],
            env=clean_sub_env,
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
        check(
            sandbox_res.returncode == 0,
            f"TEST_SANDBOX_ENV_KEY UpdateChecker auto-silence failed: rc={sandbox_res.returncode}, err={sandbox_res.stderr}",
        )

        expect_yscb_code(
            lambda: prov_online.fetch_package_zip(
                ModuleId("corrupt"), SemVer4.parse("2.0.0"), tmp_dl_dir.join("corrupt.zip"), ignore_sha256=True
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )
        expect_yscb_code(
            lambda: prov_online.fetch_package_zip(
                ModuleId("core"), SemVer4.parse("2.0.0"), tmp_dl_dir.join("bad_sha.zip"), expected_sha256="f" * 64
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )
        caught_offline_block = False
        try:
            _ = prov_offline.fetch_package_zip(
                ModuleId("core"), SemVer4.parse("2.0.0"), tmp_dl_dir.join("offline.zip"), ignore_sha256=True
            )
        except YscbError:
            caught_offline_block = True
        check(caught_offline_block and not mirror.has_package(ModuleId("core"), SemVer4.parse("2.0.0")))

        src_dyn_dir = yscb_root.path / "source" / "local-dyn"
        src_dyn_dir.mkdir(parents=True, exist_ok=True)
        (src_dyn_dir / "manifest.json").write_text(
            json.dumps({"schema_version": 2, "id": "local-dyn", "version": "1.4.0", "description": "dyn"}),
            encoding="utf-8",
        )
        (src_dyn_dir / "module_entry.py").write_text("DYN = True\n", encoding="utf-8")
        local_rel_root = yscb_root.path / "release"
        local_rel_root.mkdir(parents=True, exist_ok=True)
        prov_local = ProviderClient(yscb_root=yscb_root, default_provider=str(local_rel_root), offline=True)
        dyn_zip = prov_local.fetch_package_zip(
            ModuleId("local-dyn"), SemVer4.parse("1.4.0"), tmp_dl_dir.join("dyn_ok.zip")
        )
        mirror.verify_zip_integrity(dyn_zip)
        expect_yscb_code(
            lambda: prov_local.fetch_package_zip(
                ModuleId("local-dyn"), SemVer4.parse("1.5.0"), tmp_dl_dir.join("dyn_mismatch.zip")
            ),
            ErrorCode.DEPENDENCY_CONFLICT,
        )

        mount_rules = build_standard_mount_rules(host_dir, yscb_root, project_root=proj_root)
        vfs_hub = VfsHub(UriMountTable(mount_rules))
        kernel_vfs = vfs_hub.for_kernel()
        cfg_store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
        cfg_store.save_host_config(
            HostConfig(yscb_root=".yscb", default_provider=base_url, installed_modules={})
        )
        snap_vault = SnapshotVault(
            host_dir=host_dir,
            yscb_root=yscb_root,
            policy=SnapshotRetentionPolicy(max_snapshots=5, max_age_days=7.0, coalesce_window_sec=60.0),
        )
        env_pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=HostPath(yscb_root.path / ".cache"))
        engine = OfflinePackageEngine(
            host_dir=host_dir,
            yscb_root=yscb_root,
            config_store=cfg_store,
            snapshot_vault=snap_vault,
            env_pool=env_pool,
            vfs=kernel_vfs,
        )

        install_rep: DeploymentReport = engine.install(
            (
                PackageRequest(module_id=ModuleId("core"), version_spec="==2.0.0"),
                PackageRequest(module_id=ModuleId("alpha"), version_spec="==2.0.0"),
                PackageRequest(module_id=ModuleId("intel"), version_spec="==2.0.0"),
                PackageRequest(module_id=ModuleId("leaf"), version_spec="==2.0.0"),
            ),
            offline=False,
        )
        check(
            install_rep.installed[ModuleId("core")] == SemVer4.parse("2.0.0")
            and install_rep.installed[ModuleId("alpha")] == SemVer4.parse("2.0.0")
            and install_rep.installed[ModuleId("intel")] == SemVer4.parse("2.0.0")
            and install_rep.installed[ModuleId("leaf")] == SemVer4.parse("2.0.0")
            and ModuleId("intel") in install_rep.env_specs,
            f"Batch install + Tier 1 venv materialization failed: {install_rep}",
        )

        healed_non_downgrade = DependencySolver().reconcile_installed_dependencies(
            {
                ModuleId("core"): SemVer4.parse("2.1.0"),
                ModuleId("leaf"): SemVer4.parse("2.0.0"),
            },
            prov_online,
            mirror,
        )
        check(
            healed_non_downgrade == {ModuleId("leaf"): SemVer4.parse("2.1.0")},
            f"reconcile_installed_dependencies must upgrade leaf rather than downgrading core: {healed_non_downgrade}",
        )

        alpha_mod_dir = yscb_root.path / ".modules" / "alpha"
        check(
            (alpha_mod_dir / "manifest.json").is_file()
            and (alpha_mod_dir / "tasks.index.json").is_file()
            and (alpha_mod_dir / "config.schema.json").is_file()
            and not (alpha_mod_dir / "configurable").exists()
            and not (alpha_mod_dir / ".yscbignore").exists()
            and not list(alpha_mod_dir.rglob("*.tmpl")),
            "Staging deployment must unconditionally strip configurable/, .yscbignore, and all *.tmpl files",
        )

        cfg_store.set_value(ModuleId("alpha"), "workers", 16, local=False)
        check(cfg_store.unset_value(ModuleId("alpha"), "mode", local=False) is True)
        notes_cfg_file = yscb_root.path / "config" / "alpha" / "notes.json"
        check(json.loads(notes_cfg_file.read_text(encoding="utf-8")) == {"hello": "tmpl"})
        notes_cfg_file.write_text('{"hello": "user_customized"}\n', encoding="utf-8")

        offline_checker = UpdateChecker(
            host_dir=host_dir,
            yscb_root=yscb_root,
            config_store=cfg_store,
            provider=prov_online,
            self_update_url=f"{base_url}/yscb.py",
        )
        offline_uc_rep = offline_checker.check_if_due(offline=True)
        check(
            offline_uc_rep.candidates == () and offline_uc_rep.throttled is False,
            f"UpdateChecker(offline=True) must return empty non-throttled report: {offline_uc_rep}",
        )
        _run_clean_env_update_checker_checks(
            host_dir=host_dir,
            yscb_root=yscb_root,
            ins_ws=ins_ws,
            base_url=base_url,
            remote_yscb_lf=remote_yscb_lf,
            can_make_sym=can_make_sym,
        )

        checkpoint_200 = snap_vault.create_snapshot("pre_update_checkpoint", force=True)
        upd_rep = engine.update((ModuleId("alpha"),), offline=False)
        check(
            upd_rep.snapshot_id == checkpoint_200.snapshot_id,
            "Within 60s coalesce window, engine.update must reuse checkpoint snapshot without wasting slots",
        )
        check(
            upd_rep.installed[ModuleId("alpha")] == SemVer4.parse("2.1.0")
            and upd_rep.installed[ModuleId("core")] == SemVer4.parse("2.1.0")
            and upd_rep.installed[ModuleId("leaf")] == SemVer4.parse("2.1.0")
            and ModuleId("leaf") in upd_rep.reconciled_dependencies,
            f"Same-major update lock (^2.0) + installed leaf intersection upgrade failed: {upd_rep}",
        )
        deployed_alpha_mf = json.loads((alpha_mod_dir / "manifest.json").read_text(encoding="utf-8"))
        check(
            deployed_alpha_mf.get("dependencies") == {"core": ">=2.1.0"},
            f"index.json dependency override was not persisted into .modules/alpha/manifest.json: {deployed_alpha_mf}",
        )
        check(
            cfg_store.get_module_value(ModuleId("alpha"), "workers") == 16
            and cfg_store.get_module_value(ModuleId("alpha"), "new_flag") is True
            and json.loads(notes_cfg_file.read_text(encoding="utf-8")) == {"hello": "user_customized"},
            "Module update must infill new keys while preserving user config and non-config templates",
        )

        expect_yscb_code(
            lambda: engine.install(
                (
                    PackageRequest(module_id=ModuleId("alpha"), version_spec="==2.0.0"),
                    PackageRequest(module_id=ModuleId("pin-conflict"), version_spec="==2.0.0"),
                ),
                offline=False,
            ),
            ErrorCode.DEPENDENCY_CONFLICT,
        )
        check(
            cfg_store.load_host_config().installed_modules[ModuleId("alpha")].version == SemVer4.parse("2.1.0")
            and ModuleId("pin-conflict") not in cfg_store.load_host_config().installed_modules,
            "Omitted index dependencies conflicting with explicit == pin must raise DEPENDENCY_CONFLICT and roll back",
        )

        expect_yscb_code(
            lambda: engine.install((PackageRequest(module_id=ModuleId("broken"), version_spec="==2.0.0"),)),
            ErrorCode.DEPENDENCY_CONFLICT,
        )
        expect_yscb_code(
            lambda: engine.install(
                (
                    PackageRequest(module_id=ModuleId("badtmpl"), version_spec="==2.0.0"),
                    PackageRequest(module_id=ModuleId("gamma"), version_spec="==2.0.0.2"),
                ),
                offline=False,
            ),
            ErrorCode.CONFIG_INVALID,
        )
        check(
            not (yscb_root.path / ".modules" / "gamma").exists()
            and not (yscb_root.path / ".modules" / "badtmpl").exists()
            and not (yscb_root.path / ".temp").exists()
            and cfg_store.load_host_config().installed_modules[ModuleId("alpha")].version == SemVer4.parse("2.1.0"),
            "Mid-write failure within 60s coalesce window must roll back partial deployment and clean .temp",
        )
        host_after_conflict = cfg_store.load_host_config()
        check(
            ModuleId("broken") not in host_after_conflict.installed_modules
            and host_after_conflict.installed_modules[ModuleId("alpha")].version == SemVer4.parse("2.1.0")
            and not (yscb_root.path / ".modules" / "broken").exists(),
            f"Failed conflicting install did not roll back cleanly via SnapshotVault: {host_after_conflict}",
        )

        rb_rep = engine.rollback(upd_rep.snapshot_id)
        check(
            cfg_store.load_host_config().installed_modules[ModuleId("alpha")].version == SemVer4.parse("2.0.0")
            and rb_rep.installed[ModuleId("alpha")] == SemVer4.parse("2.0.0")
            and cfg_store.get_module_value(ModuleId("alpha"), "mode") is None,
            f"OfflinePackageEngine.rollback must restore pre-update 2.0.0 state without re-infilling unset config keys: {rb_rep}",
        )

        omitted_rep = engine.install(
            (PackageRequest(module_id=ModuleId("omitted-dep"), version_spec="==2.0.0"),),
            offline=False,
        )
        omitted_mf_doc = json.loads(
            (yscb_root.path / ".modules" / "omitted-dep" / "manifest.json").read_text(encoding="utf-8")
        )
        check(
            omitted_mf_doc.get("dependencies") == {"gamma": ">=2.0.0.2"}
            and omitted_rep.installed.get(ModuleId("gamma")) == SemVer4.parse("2.0.0.2"),
            f"Omitted dependencies key in HTTP index.json must preserve zip manifest dependencies and heal transitive deps: {omitted_rep}, {omitted_mf_doc}",
        )
        _ = engine.remove((ModuleId("omitted-dep"), ModuleId("gamma")), purge_level=PurgeLevel.PURGE)

        cur_host = cfg_store.load_host_config()
        with_pruned_gamma = HostConfig(
            yscb_root=cur_host.yscb_root,
            default_provider=cur_host.default_provider,
            installed_modules={
                **cur_host.installed_modules,
                ModuleId("gamma"): InstalledModuleRecord(
                    version=SemVer4.parse("2.0.0.1"),
                    installed_at="2026-11-22T00:00:00Z",
                    provider=base_url,
                ),
            },
        )
        cfg_store.save_host_config(with_pruned_gamma)
        restore_rep = engine.restore(offline=False)
        check(
            restore_rep.installed[ModuleId("gamma")] == SemVer4.parse("2.0.0.2")
            and cfg_store.load_host_config().installed_modules[ModuleId("gamma")].version == SemVer4.parse("2.0.0.2"),
            f"Pruned restore failed to substitute highest active same-triplet version 2.0.0.2: {restore_rep}",
        )

        for space_sub in ("config", ".config.local", "storage", ".storage.local", ".cache"):
            p_sp = yscb_root.path / space_sub / "gamma"
            p_sp.mkdir(parents=True, exist_ok=True)
            (p_sp / "data.txt").write_text("x", encoding="utf-8")

        _ = engine.remove((ModuleId("gamma"),), purge_level=PurgeLevel.CLEAN)
        check(
            not (yscb_root.path / ".modules" / "gamma").exists()
            and not (yscb_root.path / ".cache" / "gamma").exists()
            and not (yscb_root.path / ".storage.local" / "gamma").exists()
            and (yscb_root.path / "config" / "gamma").is_dir()
            and (yscb_root.path / "storage" / "gamma").is_dir(),
            "PurgeLevel.CLEAN must remove .cache and .storage.local while keeping config and storage",
        )

        _ = engine.install((PackageRequest(module_id=ModuleId("gamma"), version_spec="==2.0.0.2"),), offline=True)
        _ = engine.remove((ModuleId("gamma"),), purge_level=PurgeLevel.PURGE)
        check(
            all(
                not (yscb_root.path / sub / "gamma").exists()
                for sub in (".modules", "config", ".config.local", "storage", ".storage.local", ".cache")
            ),
            "PurgeLevel.PURGE must clean all five module data spaces plus .modules",
        )

        tx_lock_file = HostPath(yscb_root.path / ".cache" / "locks" / "package_engine.lock")
        holder_entered = threading.Event()
        holder_release = threading.Event()
        writer_finished = threading.Event()

        def _hold_engine_lock_and_stage_config() -> None:
            with FileLock(tx_lock_file, allow_transitions=False):
                holder_entered.set()
                _ = holder_release.wait(timeout=5.0)
                cfg_store.set_value(ModuleId("alpha"), "guarded_marker", "committed_under_lock", local=False)
                writer_finished.set()

        lock_thr = threading.Thread(target=_hold_engine_lock_and_stage_config, daemon=True)
        lock_thr.start()
        check(holder_entered.wait(timeout=5.0), "Background package_engine.lock holder did not start")
        holder_release.set()
        with engine.migration_rollback_scope() as restore_tx_guard:
            check(writer_finished.is_set(), "migration_rollback_scope must wait for package_engine.lock before capturing guard")
            _ = engine.install((PackageRequest(module_id=ModuleId("gamma"), version_spec="==2.0.0.2"),), offline=True)
            cfg_store.set_value(ModuleId("alpha"), "guarded_marker", "transient_mutation", local=False)
            restore_tx_guard()
        lock_thr.join(timeout=5.0)
        check(
            cfg_store.get_module_value(ModuleId("alpha"), "guarded_marker") == "committed_under_lock"
            and ModuleId("gamma") not in cfg_store.load_host_config().installed_modules
            and not (yscb_root.path / ".temp").exists(),
            "migration_rollback_scope must capture and restore post-lock state cleanly without leaving .temp",
        )
    finally:
        srv.shutdown()
        srv.server_close()
        srv_thr.join(timeout=3.0)
        check(not srv_thr.is_alive(), "Test HTTP mirror server thread did not terminate cleanly")

    shutil.rmtree(ins_ws)




def _build_optional_unique_holder_type() -> type[object]:
    inner_cls = make_dataclass(
        "_NestedUniqueMapDto",
        [
            (
                "entries",
                Annotated[
                    Mapping[str, str],
                    ContribField(merge=MergeStrategy.UNIQUE, description="Unique map"),
                ],
                field(default_factory=dict),
            )
        ],
        frozen=True,
        slots=True,
    )
    return make_dataclass(
        "_OptionalUniqueSectionDto",
        [("section", Optional[inner_cls], None)],
        frozen=True,
        slots=True,
    )


def _verify_boundary_hardening_and_tx_recovery(suite_root: Path) -> None:
    guard_ws = suite_root / "boundary_suite"
    host_dir = HostPath(guard_ws / "ws_host")
    yscb_root = HostPath(guard_ws / "ws_host" / ".yscb")
    host_dir.path.mkdir(parents=True, exist_ok=True)
    yscb_root.path.mkdir(parents=True, exist_ok=True)

    for reserved_name in ("locks", "wheels", "daemon", "project"):
        expect_yscb_code(
            lambda r_nm=reserved_name: ModuleManifest(
                id=ModuleId(r_nm),
                version=SemVer4.parse("2.0.0.0"),
                description="Reserved id test",
            ),
            ErrorCode.CONFIG_INVALID,
        )

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    base_cfg = HostConfig(
        yscb_root=".yscb",
        default_provider=str(guard_ws / "local_repo" / "release"),
        installed_modules={},
    )
    store.save_host_config(base_cfg)
    expect_yscb_code(lambda: store.get_module_dict(ModuleId("locks")), ErrorCode.CONFIG_INVALID)

    local_cfg_path = host_dir.path / "yscb.config.local.json"
    local_cfg_path.write_text(
        json.dumps(
            {
                "installed_modules": {
                    "rogue": {
                        "version": "2.0.0.0",
                        "installed_at": "2026-11-22T00:00:00Z",
                        "provider": "local",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    expect_yscb_code(store.load_host_config, ErrorCode.CONFIG_INVALID)
    local_cfg_path.unlink()

    vault = SnapshotVault(
        host_dir=host_dir,
        yscb_root=yscb_root,
        policy=SnapshotRetentionPolicy(max_snapshots=5, max_age_days=7.0, coalesce_window_sec=60.0),
    )
    first_snap = vault.create_snapshot("aged-check", force=True)
    aged_meta_path = yscb_root.path / ".snapshots" / first_snap.snapshot_id / "snapshot.meta.json"
    aged_doc = json.loads(aged_meta_path.read_text(encoding="utf-8"))
    aged_doc["created_epoch_sec"] = time.time() - (9.0 * 86400.0)
    aged_meta_path.write_text(json.dumps(aged_doc), encoding="utf-8")
    refreshed_snap = vault.create_snapshot("post-expiry-check", force=False)
    check(
        not refreshed_snap.reused and refreshed_snap.snapshot_id != first_snap.snapshot_id,
        f"Expired snapshot must not be short-circuit reused: {refreshed_snap}",
    )
    _ = vault.prune()
    remaining_ids = {m.snapshot_id for m in vault.list_snapshots()}
    check(refreshed_snap.snapshot_id in remaining_ids, "Fresh replacement snapshot must survive prune()")

    opt_holder_cls = _build_optional_unique_holder_type()
    mod_target = ModuleId("target-host")
    opt_bundle = compile_extension_points(
        mod_target,
        (ExtensionPointSpec(name="cfg_pt", payload_type=opt_holder_cls),),
    )
    ctb_root = HostPath(guard_ws / "ctb_guard" / ".yscb")
    target_schema_dir = ctb_root.path / ".modules" / "target-host" / "contributes"
    target_schema_dir.mkdir(parents=True, exist_ok=True)
    (target_schema_dir / "_schema.json").write_text(json.dumps(opt_bundle.to_json()), encoding="utf-8")

    donor_null = ModuleId("alpha-null")
    donor_seed = ModuleId("beta-seed")
    donor_exist = ModuleId("existing")
    for d_id, payload_obj in (
        (donor_null, {"cfg_pt": {"section": None}}),
        (donor_seed, {"cfg_pt": {"section": {"entries": {"k1": "from-beta"}}}}),
        (donor_exist, {"cfg_pt": {"section": {"entries": {"k1": "from-existing"}}}}),
    ):
        d_dir = ctb_root.path / ".modules" / d_id.value / "contributes"
        d_dir.mkdir(parents=True, exist_ok=True)
        (d_dir / "target-host.json").write_text(json.dumps(payload_obj), encoding="utf-8")

    donors_mfs = tuple(
        ModuleManifest(id=m, version=SemVer4.parse("2.0.0.0"), description=f"Donor {m.value}")
        for m in (mod_target, donor_null, donor_seed, donor_exist)
    )
    agg = ContributesAggregator(yscb_root=ctb_root, manifests=donors_mfs)
    expect_yscb_code(
        lambda: agg.aggregate(mod_target, strict=True),
        ErrorCode.CONTRIBUTES_INVALID,
    )

    outside_dir = guard_ws / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    (outside_dir / "contribute.local.json").write_text("{}", encoding="utf-8")
    sym_local_cfg = ctb_root.path / ".config.local"
    sym_created = True
    try:
        os.symlink(outside_dir, sym_local_cfg)
    except (OSError, NotImplementedError):
        sym_created = False
    if sym_created:
        try:
            reports = agg.validate_all(strict=False)
            all_iss = [iss for rep in reports for iss in rep.issues]
            check(
                all("contribute.local.json" not in iss.source_label for iss in all_iss),
                f"Symlink .config.local must not be traversed to external contribute.local.json: {all_iss}",
            )
        finally:
            sym_local_cfg.unlink(missing_ok=True)

    env_pool = ImmutableVenvPool(
        yscb_root=yscb_root,
        cache_dir=HostPath(yscb_root.path / ".cache"),
    )
    sample_spec = ImmutableVenvPool.compute_env_spec("ide_grp", {"demo-pkg": ">=1.0.0"})
    posix_sp, win_sp = env_pool.get_site_packages_dirs(sample_spec)
    check(
        "site-packages" in str(posix_sp) and str(win_sp).endswith(os.path.join("Lib", "site-packages")),
        f"Unexpected get_site_packages_dirs output: {(posix_sp, win_sp)}",
    )

    ext_dir = guard_ws / "ext_protected_dir"
    ext_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ext_dir, stat.S_IREAD | stat.S_IXUSR)
    try:
        ext_dir_mode = stat.S_IMODE(os.lstat(ext_dir).st_mode)
        stale_stage = yscb_root.path / ".venv" / ".staging_dead_999999_1"
        stale_stage.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(ext_dir, stale_stage / "linked_dir")
        except (OSError, NotImplementedError):
            pass
        _ = EnvGarbageCollector(env_pool).collect(())
        check(
            stat.S_IMODE(os.lstat(ext_dir).st_mode) == ext_dir_mode,
            "EnvGarbageCollector must never chmod external directory through symlink",
        )
    finally:
        os.chmod(ext_dir, stat.S_IWRITE | stat.S_IREAD | stat.S_IXUSR)

    mirror = MirrorStore(yscb_root=yscb_root)
    enc_zi = zipfile.ZipInfo("manifest.json")
    enc_zip_p = guard_ws / "encrypted_entry.zip"
    raw_enc = bytearray(_build_custom_zip_bytes(((enc_zi, b"{}"),)))
    enc_lfh = raw_enc.find(b"PK\x03\x04")
    enc_cdh = raw_enc.find(b"PK\x01\x02")
    raw_enc[enc_lfh + 6 : enc_lfh + 8] = (1).to_bytes(2, "little")
    raw_enc[enc_cdh + 8 : enc_cdh + 10] = (1).to_bytes(2, "little")
    enc_zip_p.write_bytes(bytes(raw_enc))
    expect_yscb_code(
        lambda: mirror.verify_zip_integrity(HostPath(enc_zip_p), ignore_sha256=True),
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
    )

    bad_comp_zi = zipfile.ZipInfo("manifest.json")
    bad_comp_p = guard_ws / "bad_compress.zip"
    with zipfile.ZipFile(bad_comp_p, "w") as zf_bc:
        zf_bc.writestr(bad_comp_zi, b"{}")
    raw_bc = bytearray(bad_comp_p.read_bytes())
    lfh_idx = raw_bc.find(b"PK\x03\x04")
    cdh_idx = raw_bc.find(b"PK\x01\x02")
    if lfh_idx >= 0 and cdh_idx >= 0:
        raw_bc[lfh_idx + 8 : lfh_idx + 10] = (99).to_bytes(2, "little")
        raw_bc[cdh_idx + 10 : cdh_idx + 12] = (99).to_bytes(2, "little")
        bad_comp_p.write_bytes(bytes(raw_bc))
        expect_yscb_code(
            lambda: mirror.verify_zip_integrity(HostPath(bad_comp_p), ignore_sha256=True),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )

    bomb_zip_p = guard_ws / "high_ratio_bomb.zip"
    with zipfile.ZipFile(bomb_zip_p, "w", compression=zipfile.ZIP_DEFLATED) as zf_bomb:
        zf_bomb.writestr(
            "manifest.json",
            json.dumps({"schema_version": 2, "id": "bomb", "version": "2.0.0.0", "description": "Bomb"}),
        )
        zf_bomb.writestr("zeroes.bin", b"\x00" * (2 * 1024 * 1024))
    expect_yscb_code(
        lambda: mirror.verify_zip_integrity(HostPath(bomb_zip_p), ignore_sha256=True),
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
    )

    local_repo = guard_ws / "local_repo"
    dyn_src = local_repo / "source" / "dynmod"
    dyn_src.mkdir(parents=True, exist_ok=True)
    (dyn_src / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "id": "dynmod",
                "version": "2.0.0.0",
                "description": "Dynamic source module",
                "entry": "module_entry.py",
                "onboarding": ["yscb dynmod init"],
            }
        ),
        encoding="utf-8",
    )
    (dyn_src / "module_entry.py").write_text("READY = True\n", encoding="utf-8")
    dyn_rel = local_repo / "release" / "dynmod"
    dyn_rel.mkdir(parents=True, exist_ok=True)
    (dyn_rel / "index.json").write_text(
        json.dumps({"module_id": "dynmod", "versions": ["2.0.0.0"]}),
        encoding="utf-8",
    )

    vfs = VfsHub(
        UriMountTable(build_standard_mount_rules(host_dir, yscb_root, project_root=host_dir))
    ).for_kernel()
    deployer = AtomicPackageDeployer(yscb_root=yscb_root, config_store=store, vfs=vfs)
    expect_yscb_code(lambda: deployer.remove_module(ModuleId("core")), ErrorCode.DEPENDENCY_CONFLICT)
    expect_yscb_code(lambda: deployer.remove_module(ModuleId("locks")), ErrorCode.CONFIG_INVALID)

    engine = OfflinePackageEngine(
        host_dir=host_dir,
        yscb_root=yscb_root,
        config_store=store,
        snapshot_vault=vault,
        env_pool=env_pool,
        vfs=vfs,
    )
    expect_yscb_code(
        lambda: engine.install((PackageRequest(module_id=ModuleId("wheels")),)),
        ErrorCode.CONFIG_INVALID,
    )

    dyn_rep = engine.install((PackageRequest(module_id=ModuleId("dynmod")),))
    check(
        dyn_rep.installed.get(ModuleId("dynmod")) == SemVer4.parse("2.0.0.0")
        and (yscb_root.path / ".modules" / "dynmod" / "module_entry.py").is_file(),
        f"Exact-version local source dynamic packaging failed: {dyn_rep}",
    )

    flat_parent = guard_ws / "flat_shared"
    flat_mirror = flat_parent / "custom_mirror"
    (flat_mirror / "sneak").mkdir(parents=True, exist_ok=True)
    (flat_mirror / "sneak" / "index.json").write_text(
        json.dumps({"module_id": "sneak", "versions": ["2.0.0.0"]}),
        encoding="utf-8",
    )
    (flat_parent / "source" / "sneak").mkdir(parents=True, exist_ok=True)
    (flat_parent / "source" / "sneak" / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "id": "sneak", "version": "2.0.0.0", "description": "Sneak"}),
        encoding="utf-8",
    )
    (flat_parent / "source" / "sneak" / "module_entry.py").write_text("X = 1\n", encoding="utf-8")
    expect_yscb_code(
        lambda: engine.install(
            (PackageRequest(module_id=ModuleId("sneak"), provider_override=str(flat_mirror)),)
        ),
        ErrorCode.DEPENDENCY_CONFLICT,
    )

    core_200_b, core_200_sha = _build_module_zip_bytes("core", "2.0.0.0")
    core_201_b, core_201_sha = _build_module_zip_bytes("core", "2.0.1.0")
    app_200_b, app_200_sha = _build_module_zip_bytes(
        "app",
        "2.0.0.0",
        dependencies={"helper": ">=2.0.0.0"},
        extra_files={},
    )
    app_210_b, app_210_sha = _build_module_zip_bytes(
        "app",
        "2.1.0.0",
        dependencies={"helper": ">=2.0.0.0"},
    )
    hlp_200_b, hlp_200_sha = _build_module_zip_bytes(
        "helper",
        "2.0.0.0",
        dependencies={"core": ">=2.0.0.0"},
    )
    hlp_210_b, hlp_210_sha = _build_module_zip_bytes(
        "helper",
        "2.1.0.0",
        dependencies={"core": ">=2.5.0.0"},
    )
    ynk_200_b, ynk_200_sha = _build_module_zip_bytes("yankpeer", "2.0.0.0")

    http_state = _RepoHttpMirrorState(
        {
            "/core/index.json": json.dumps(
                {
                    "module_id": "core",
                    "versions": ["2.0.0.0", "2.0.1.0"],
                    "releases": {
                        "2.0.0.0": {"sha256": core_200_sha, "status": "active"},
                        "2.0.1.0": {"sha256": core_201_sha, "status": "active"},
                    },
                }
            ).encode("utf-8"),
            "/core/2.0.0.0.zip": core_200_b,
            "/core/2.0.1.0.zip": core_201_b,
            "/app/index.json": json.dumps(
                {
                    "module_id": "app",
                    "versions": ["2.0.0.0", "2.1.0.0"],
                    "releases": {
                        "2.0.0.0": {"sha256": app_200_sha, "status": "active"},
                        "2.1.0.0": {"sha256": app_210_sha, "status": "active"},
                    },
                }
            ).encode("utf-8"),
            "/app/2.0.0.0.zip": app_200_b,
            "/app/2.1.0.0.zip": app_210_b,
            "/helper/index.json": json.dumps(
                {
                    "module_id": "helper",
                    "versions": ["2.0.0.0", "2.1.0.0"],
                    "releases": {
                        "2.0.0.0": {"sha256": hlp_200_sha, "status": "active"},
                        "2.1.0.0": {"sha256": hlp_210_sha, "status": "active"},
                    },
                }
            ).encode("utf-8"),
            "/helper/2.0.0.0.zip": hlp_200_b,
            "/helper/2.1.0.0.zip": hlp_210_b,
            "/yankpeer/index.json": json.dumps(
                {
                    "module_id": "yankpeer",
                    "versions": ["2.0.0.0"],
                    "releases": {"2.0.0.0": {"sha256": ynk_200_sha, "status": "active"}},
                }
            ).encode("utf-8"),
            "/yankpeer/2.0.0.0.zip": ynk_200_b,
            "/poison/app/index.json": json.dumps(
                {
                    "module_id": "app",
                    "versions": ["2.0.0.0", "2.1.0.0"],
                    "releases": {
                        "2.0.0.0": {
                            "sha256": "f" * 64,
                            "status": "active",
                            "dependencies": {"core": ">=2.0.1.0"},
                        },
                        "2.1.0.0": {
                            "sha256": "e" * 64,
                            "status": "active",
                            "dependencies": {"core": ">=2.0.1.0"},
                        },
                    },
                }
            ).encode("utf-8"),
            "/poison/app/2.1.0.0.zip": b"corrupted_zip_payload",
        }
    )
    http_state.redirects["/badredir/evil/index.json"] = "ftp://127.0.0.1/evil/index.json"
    http_state.redirects["/fileredir/evil/index.json"] = "file:///etc/passwd"
    http_state.redirects["/gopherredir/evil/index.json"] = "gopher://127.0.0.1:6379/evil"

    srv, srv_thr, srv_url = _start_test_http_mirror(http_state)
    http_state.redirects["/loopbackredir/evil/index.json"] = f"{srv_url}/evil/index.json"
    try:
        _verify_dual_dns_public_to_private_ssrf_guard(yscb_root, int(srv.server_address[1]))
        prov_cli = ProviderClient(yscb_root=yscb_root, default_provider=srv_url)
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider=f"{srv_url}/badredir"),
            ErrorCode.SECURITY_GATED,
        )
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider=f"{srv_url}/fileredir"),
            ErrorCode.SECURITY_GATED,
        )
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider=f"{srv_url}/gopherredir"),
            ErrorCode.SECURITY_GATED,
        )
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider="file://[::1/bad_uri"),
            ErrorCode.CONFIG_INVALID,
        )
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider="file://127.0.0.1:8080/repo"),
            ErrorCode.CONFIG_INVALID,
        )
        if not IS_WINDOWS:
            expect_yscb_code(
                lambda: prov_cli.fetch_index(ModuleId("evil"), provider="file://remotehost/repo"),
                ErrorCode.CONFIG_INVALID,
            )
        expect_yscb_code(
            lambda: prov_cli.fetch_index(ModuleId("evil"), provider="http://127.0.0.1:99999"),
            ErrorCode.CONFIG_INVALID,
        )

        store.save_host_config(
            HostConfig(
                yscb_root=".yscb",
                default_provider=srv_url,
                installed_modules={
                    ModuleId("core"): InstalledModuleRecord(
                        version=SemVer4.parse("2.0.0.0"),
                        installed_at="2026-11-22T00:00:00Z",
                        provider=srv_url,
                    ),
                    ModuleId("app"): InstalledModuleRecord(
                        version=SemVer4.parse("2.0.0.0"),
                        installed_at="2026-11-22T00:00:00Z",
                        provider=srv_url,
                    ),
                },
            )
        )
        shutil.rmtree(yscb_root.path / ".mirror", ignore_errors=True)
        orphan_disk = yscb_root.path / ".modules" / "dynmod"
        check(orphan_disk.is_dir(), "Precondition: dynmod exists on disk prior to restore")

        res_backtrack = engine.restore(offline=False)
        check(
            res_backtrack.installed.get(ModuleId("helper")) == SemVer4.parse("2.0.0.0")
            and ModuleId("dynmod") in res_backtrack.removed
            and not orphan_disk.exists(),
            f"restore() failed slim-index downward backtracking or orphan cleanup: {res_backtrack}",
        )
        check(
            any(t.module_id == ModuleId("app") and t.old_version is None for t in res_backtrack.transitions),
            f"restore() after empty .modules must emit initial UpgradeTransition: {res_backtrack.transitions}",
        )

        store.save_host_config(
            HostConfig(
                yscb_root=".yscb",
                default_provider=srv_url,
                installed_modules={
                    ModuleId("core"): InstalledModuleRecord(
                        version=SemVer4.parse("2.0.0.0"),
                        installed_at="2026-11-22T00:00:00Z",
                        provider=srv_url,
                    ),
                    ModuleId("app"): InstalledModuleRecord(
                        version=SemVer4.parse("2.1.0.0"),
                        installed_at="2026-11-22T00:00:00Z",
                        provider=srv_url,
                    ),
                    ModuleId("helper"): InstalledModuleRecord(
                        version=SemVer4.parse("2.0.0.0"),
                        installed_at="2026-11-22T00:00:00Z",
                        provider=srv_url,
                    ),
                },
            )
        )
        res_pull = engine.restore(offline=False)
        check(
            any(
                t.module_id == ModuleId("app")
                and t.old_version == SemVer4.parse("2.0.0.0")
                and t.new_version == SemVer4.parse("2.1.0.0")
                and t.is_upgrade
                for t in res_pull.transitions
            ),
            f"restore() after lockfile bump must emit 2.0.0.0 -> 2.1.0.0 UpgradeTransition: {res_pull.transitions}",
        )

        orig_app_idx = (yscb_root.path / ".mirror" / "app" / "index.json").read_bytes()
        expect_yscb_code(
            lambda: engine.install(
                (
                    PackageRequest(
                        module_id=ModuleId("app"),
                        version_spec="==2.1.0.0",
                        provider_override=f"{srv_url}/poison",
                    ),
                ),
                force=True,
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )
        check(
            (yscb_root.path / ".mirror" / "app" / "index.json").read_bytes() == orig_app_idx,
            "Failed transaction must roll back overwritten .mirror/<mod>/index.json",
        )

        snap_pre_yank = vault.create_snapshot("pre-yankpeer", force=True)
        _ = engine.install((PackageRequest(module_id=ModuleId("yankpeer")),))
        http_state.routes["/yankpeer/index.json"] = json.dumps(
            {
                "module_id": "yankpeer",
                "versions": ["2.0.0.0"],
                "releases": {"2.0.0.0": {"sha256": ynk_200_sha, "status": "active", "yanked": True}},
            }
        ).encode("utf-8")
        upd_rep = engine.update()
        check(
            upd_rep.installed.get(ModuleId("core")) == SemVer4.parse("2.0.1.0")
            and ModuleId("yankpeer") not in upd_rep.installed,
            f"Batch update() must retain healthy yanked peer while upgrading core: {upd_rep}",
        )

        (yscb_root.path / ".mirror" / "core" / "2.0.0.0.zip").unlink()
        (yscb_root.path / ".mirror" / "yankpeer" / "2.0.0.0.zip").unlink()
        expect_yscb_code(
            lambda: engine.rollback(snap_pre_yank.snapshot_id),
            ErrorCode.TRANSPORT_LOST,
        )
        check(
            (yscb_root.path / ".modules" / "yankpeer" / "manifest.json").is_file(),
            "Failed rollback must not delete existing .modules/yankpeer when target mirror archive is missing",
        )
    finally:
        srv.shutdown()
        srv.server_close()
        srv_thr.join(timeout=3.0)
        check(not srv_thr.is_alive(), "Boundary HTTP test server thread did not terminate")




def _build_none_first_union_holder_type() -> type[object]:
    sub_cls = make_dataclass(
        "_UnionSubSpecDto",
        [
            (
                "tags",
                Annotated[
                    tuple[str, ...],
                    ContribField(merge=MergeStrategy.EXTEND, description="Ordered tags", dedupe=False),
                ],
                (),
            )
        ],
        frozen=True,
        slots=True,
    )
    ann_map = Annotated[
        Mapping[ModuleId, sub_cls],
        ContribField(merge=MergeStrategy.MERGE, description="Module map"),
    ]
    return make_dataclass(
        "_NoneFirstUnionHolderDto",
        [("mapping", None | ann_map, None)],
        frozen=True,
        slots=True,
    )


def _verify_build_packages_and_error_passthrough(suite_root: Path) -> None:
    ext_ws = suite_root / "ext_contract_suite"
    host_dir = HostPath(ext_ws / "ws_host")
    yscb_root = HostPath(ext_ws / "ws_host" / ".yscb")
    host_dir.path.mkdir(parents=True, exist_ok=True)
    yscb_root.path.mkdir(parents=True, exist_ok=True)

    mf_empty_pip = ModuleManifest(
        id=ModuleId("unconstrained-pip"),
        version=SemVer4.parse("2.0.0.0"),
        description="Unconstrained pip spec",
        pip_dependencies={"demo-wheel": ""},
    )
    check(mf_empty_pip.pip_dependencies["demo-wheel"] == "", "Empty pip version constraint must be accepted")
    for bad_pip_map in (
        {"demo-wheel": "--extra-index-url=http://evil"},
        {"demo-wheel": "1.2.0"},
        {"demo-wheel": "^1.2.0"},
        {"demo-wheel": "@ https://evil.example/pkg.whl"},
        {"demo[-bad]": ">=1.0.0"},
        {"demo[a,,b]": ">=1.0.0"},
    ):
        expect_yscb_code(
            lambda m=bad_pip_map: ModuleManifest(
                id=ModuleId("bad-pip-flag"),
                version=SemVer4.parse("2.0.0.0"),
                description="Bad pip syntax",
                pip_dependencies=m,
            ),
            ErrorCode.CONFIG_INVALID,
        )

    union_holder_cls = _build_none_first_union_holder_type()
    union_bundle = compile_extension_points(
        ModuleId("union-host"),
        (ExtensionPointSpec(name="u_pt", payload_type=union_holder_cls),),
    )
    u_defs = union_bundle.points_schema.get("$defs")
    check(isinstance(u_defs, Mapping) and "_UnionSubSpecDto" in u_defs)
    if isinstance(u_defs, Mapping):
        sub_def = u_defs["_UnionSubSpecDto"]
        sub_props = sub_def.get("properties") if isinstance(sub_def, Mapping) else None
        tags_sc = sub_props.get("tags") if isinstance(sub_props, Mapping) else None
        check(
            isinstance(tags_sc, Mapping) and tags_sc.get("x-yscb-dedupe") is False,
            f"None-first union failed to enrich nested $defs ContribField metadata: {tags_sc}",
        )
    pt_props = union_bundle.points_schema.get("properties")
    u_pt_sc = pt_props.get("u_pt") if isinstance(pt_props, Mapping) else None
    u_pt_fields = u_pt_sc.get("properties") if isinstance(u_pt_sc, Mapping) else None
    map_sc = u_pt_fields.get("mapping") if isinstance(u_pt_fields, Mapping) else None
    any_of = map_sc.get("anyOf") if isinstance(map_sc, Mapping) else None
    check(
        isinstance(any_of, (list, tuple))
        and len(any_of) == 2
        and isinstance(any_of[1], Mapping)
        and isinstance(any_of[1].get("propertyNames"), Mapping)
        and any_of[1]["propertyNames"].get("x-yscb-vo") == "ModuleId",
        f"None-first union misaligned anyOf enrichment: {any_of}",
    )

    env_pool = ImmutableVenvPool(
        yscb_root=yscb_root,
        cache_dir=HostPath(yscb_root.path / ".cache"),
    )
    sp_spec = ImmutableVenvPool.compute_env_spec("sp_guard", {"demo-lib": ">=1.0.0"})
    sp_env_dir = env_pool.get_env_dir(sp_spec)
    sp_env_dir.path.mkdir(parents=True, exist_ok=True)
    ext_sp_target = ext_ws / "outside_site_packages"
    ext_sp_target.mkdir(parents=True, exist_ok=True)
    sym_lib = sp_env_dir.path / "lib"
    sym_sp_ok = True
    try:
        os.symlink(ext_sp_target, sym_lib)
    except (OSError, NotImplementedError):
        sym_sp_ok = False
    if sym_sp_ok:
        try:
            expect_yscb_code(
                lambda: env_pool.get_site_packages_dirs(sp_spec),
                ErrorCode.SECURITY_GATED,
            )
        finally:
            sym_lib.unlink(missing_ok=True)
    shutil.rmtree(sp_env_dir.path, ignore_errors=True)

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    vault = SnapshotVault(host_dir=host_dir, yscb_root=yscb_root)
    vfs = VfsHub(
        UriMountTable(build_standard_mount_rules(host_dir, yscb_root, project_root=host_dir))
    ).for_kernel()
    deployer = AtomicPackageDeployer(yscb_root=yscb_root, config_store=store, vfs=vfs)
    engine = OfflinePackageEngine(
        host_dir=host_dir,
        yscb_root=yscb_root,
        config_store=store,
        snapshot_vault=vault,
        env_pool=env_pool,
        vfs=vfs,
    )

    def _check_weak_registry_release() -> tuple[weakref.ReferenceType[ImmutableVenvPool], weakref.ReferenceType[AtomicPackageDeployer]]:
        eph_pool = ImmutableVenvPool(
            yscb_root=yscb_root,
            cache_dir=HostPath(yscb_root.path / ".cache"),
        )
        eph_dep = AtomicPackageDeployer(yscb_root=yscb_root, config_store=store, vfs=vfs)
        return (weakref.ref(eph_pool), weakref.ref(eph_dep))

    pool_wref, dep_wref = _check_weak_registry_release()
    gc.collect()
    check(
        pool_wref() is None and dep_wref() is None,
        "ImmutableVenvPool and AtomicPackageDeployer must not leak via global WeakKeyDictionary",
    )

    swap_v1_b, _ = _build_module_zip_bytes(
        "swapmod",
        "2.0.0.0",
        extra_files={"legacy.txt": b"old", "Helper.py": b"V = 1\n", "SubPkg/mod.py": b"S = 1\n"},
    )
    swap_v2_b, _ = _build_module_zip_bytes(
        "swapmod",
        "2.1.0.0",
        extra_files={"helper.py": b"V = 2\n", "subpkg/mod.py": b"S = 2\n"},
    )
    swap_v1_zip = ext_ws / "swapmod_200.zip"
    swap_v2_zip = ext_ws / "swapmod_210.zip"
    swap_v1_zip.write_bytes(swap_v1_b)
    swap_v2_zip.write_bytes(swap_v2_b)
    _ = deployer.materialize_module(ModuleId("swapmod"), HostPath(swap_v1_zip))
    swap_mod_dir = yscb_root.path / ".modules" / "swapmod"
    check((swap_mod_dir / "legacy.txt").is_file(), "Initial swapmod deployment missing legacy.txt")
    ext_sentinel = ext_ws / "swap_outside_sentinel.txt"
    ext_sentinel.write_text("keep_me", encoding="utf-8")
    orphan_sym = swap_mod_dir / "orphan_link.txt"
    try:
        os.symlink(ext_sentinel, orphan_sym)
    except (OSError, NotImplementedError):
        pass

    holder_tree = ManagedProcessTree(
        [sys.executable, "-B", "-c", "import time; time.sleep(0.6)"],
        cwd=HostPath(swap_mod_dir),
    )
    try:
        time.sleep(0.08)
        _ = deployer.materialize_module(ModuleId("swapmod"), HostPath(swap_v2_zip))
        top_entries = set(os.listdir(swap_mod_dir))
        check(
            not (swap_mod_dir / "legacy.txt").exists()
            and not os.path.lexists(orphan_sym)
            and ext_sentinel.read_text(encoding="utf-8") == "keep_me"
            and "helper.py" in top_entries
            and "subpkg" in top_entries
            and "SubPkg" not in top_entries
            and (swap_mod_dir / "subpkg" / "mod.py").is_file(),
            f"Module upgrade while subprocess holds cwd failed file/subdir case rename or symlink purge: {top_entries}",
        )
    finally:
        holder_tree.terminate_tree(grace_sec=0.5)

    if not IS_WINDOWS and os.geteuid() != 0:
        ro_gc_ws = ext_ws / "ro_gc_ws"
        ro_pool = ImmutableVenvPool(
            yscb_root=HostPath(ro_gc_ws / ".yscb"),
            cache_dir=HostPath(ro_gc_ws / ".yscb" / ".cache"),
        )
        ro_spec = ImmutableVenvPool.compute_env_spec("ro_grp", {"demo-lib": "==1.0.0"})
        ro_env_dir = ro_pool.get_env_dir(ro_spec)
        ro_env_dir.path.mkdir(parents=True, exist_ok=True)
        (ro_env_dir.path / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (ro_env_dir.path / ".yscb_env_meta.json").write_text(
            json.dumps(
                {
                    "group": ro_spec.group,
                    "env_hash": ro_spec.env_hash.value,
                    "py_tag": ro_spec.py_tag,
                    "platform_tag": ro_spec.platform_tag,
                    "pip_specs": list(ro_spec.pip_specs),
                    "created_at_utc": "2026-11-22T00:00:00Z",
                    "last_used_epoch_sec": 100.0,
                    "complete": True,
                }
            ),
            encoding="utf-8",
        )
        ro_listed = ro_pool.list_envs()
        check(
            len(ro_listed) == 1 and ro_listed[0][1] is not None and ro_listed[0][1].complete,
            f"Expected valid complete EnvMetadata before read-only GC check: {ro_listed}",
        )
        ro_venv_parent = ro_env_dir.path.parent
        os.chmod(ro_venv_parent, stat.S_IREAD | stat.S_IXUSR)
        try:
            ro_gc = EnvGarbageCollector(ro_pool)
            ro_gc_res = ro_gc.collect((), force_all=True)
            check(
                ro_env_dir in ro_gc_res.skipped_locked_dirs
                and (ro_env_dir.path / "pyvenv.cfg").is_file()
                and (ro_env_dir.path / ".yscb_env_meta.json").is_file(),
                f"GC eviction blocked by parent permissions must preserve env files intact: {ro_gc_res}",
            )
        finally:
            os.chmod(ro_venv_parent, stat.S_IWRITE | stat.S_IREAD | stat.S_IXUSR)
            shutil.rmtree(ro_gc_ws, ignore_errors=True)

    if not IS_WINDOWS and os.geteuid() != 0:
        mods_root = yscb_root.path / ".modules"
        os.chmod(mods_root, stat.S_IREAD | stat.S_IXUSR)
        try:
            expect_yscb_code(
                lambda: deployer.materialize_module(ModuleId("swapmod"), HostPath(swap_v1_zip)),
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
            )
        finally:
            os.chmod(mods_root, stat.S_IWRITE | stat.S_IREAD | stat.S_IXUSR)
    cache_sym_dir = yscb_root.path / ".cache" / "swapmod"
    cache_sym_dir.mkdir(parents=True, exist_ok=True)
    cache_sentinel = ext_ws / "cache_outside_sentinel.txt"
    cache_sentinel.write_text("safe_cache_target", encoding="utf-8")
    try:
        os.symlink(cache_sentinel, cache_sym_dir / "nested_cache_sym.txt")
    except (OSError, NotImplementedError):
        pass
    deployer.remove_module(ModuleId("swapmod"), purge_level=PurgeLevel.PURGE)
    check(
        not (yscb_root.path / ".modules" / "swapmod").exists()
        and not cache_sym_dir.exists()
        and cache_sentinel.read_text(encoding="utf-8") == "safe_cache_target",
        "remove_module(PURGE) must remove space containing internal symlinks without touching external target",
    )

    top_sym_mod = yscb_root.path / ".modules" / "topsym"
    top_sym_ok = True
    try:
        os.symlink(ext_ws, top_sym_mod)
    except (OSError, NotImplementedError):
        top_sym_ok = False
    if top_sym_ok:
        try:
            expect_yscb_code(
                lambda: deployer.remove_module(ModuleId("topsym")),
                ErrorCode.SECURITY_GATED,
            )
        finally:
            top_sym_mod.unlink(missing_ok=True)

    uninit_ws = ext_ws / "uninit_rel_ws"
    uninit_rel_repo = uninit_ws / "release" / "relpkg"
    uninit_rel_repo.mkdir(parents=True, exist_ok=True)
    (uninit_rel_repo / "index.json").write_text(
        json.dumps({"module_id": "relpkg", "versions": ["2.0.0.0"]}),
        encoding="utf-8",
    )
    uninit_prov = ProviderClient(
        yscb_root=HostPath(uninit_ws / ".yscb"),
        default_provider="../release",
    )
    rel_idx = uninit_prov.fetch_index(ModuleId("relpkg"))
    check(
        SemVer4.parse("2.0.0.0") in rel_idx.versions,
        "ProviderClient with uncreated .yscb root must resolve '../release' without false SECURITY_GATED",
    )
    expect_yscb_code(
        lambda: uninit_prov.fetch_index(ModuleId("relpkg"), provider="bad:provider"),
        ErrorCode.CONFIG_INVALID,
    )
    expect_yscb_code(
        lambda: uninit_prov.fetch_index(ModuleId("relpkg"), provider="file:///bad:path"),
        ErrorCode.CONFIG_INVALID,
    )

    local_repo = ext_ws / "local_repo"
    (local_repo / "release" / "dynkeep").mkdir(parents=True, exist_ok=True)
    (local_repo / "release" / "dynkeep" / "index.json").write_text(
        json.dumps({"module_id": "dynkeep", "versions": ["2.0.0.0", "2.1.0.0"]}),
        encoding="utf-8",
    )
    dyn_src = local_repo / "source" / "dynkeep"
    dyn_src.mkdir(parents=True, exist_ok=True)
    (dyn_src / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "id": "dynkeep", "version": "2.0.0.0", "description": "Dyn keep"}),
        encoding="utf-8",
    )
    (dyn_src / "module_entry.py").write_text("VER = 1\n", encoding="utf-8")

    store.save_host_config(
        HostConfig(
            yscb_root=".yscb",
            default_provider=str(local_repo / "release"),
            installed_modules={},
        )
    )
    _ = engine.install((PackageRequest(module_id=ModuleId("dynkeep"), version_spec="==2.0.0.0"),))
    (dyn_src / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "id": "dynkeep", "version": "2.1.0.0", "description": "Dyn bumped"}),
        encoding="utf-8",
    )
    idem_rep = engine.restore(force=False)
    check(
        idem_rep.installed.get(ModuleId("dynkeep")) == SemVer4.parse("2.0.0.0"),
        f"restore(force=False) must reuse .mirror package after local source version bump: {idem_rep}",
    )

    build_dir = yscb_root.path / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)
    wrong_build_b, _ = _build_module_zip_bytes("bplug", "1.0.0.0")
    right_build_b, _ = _build_module_zip_bytes("bplug", "2.0.0.0", extra_files={"tag.txt": b"v2build"})
    (build_dir / "bplug.zip").write_bytes(wrong_build_b)
    (build_dir / "bplug").mkdir(parents=True, exist_ok=True)
    (build_dir / "bplug" / "2.0.0.build.zip").write_bytes(right_build_b)

    b_rep = engine.install(
        (PackageRequest(module_id=ModuleId("bplug"), version_spec="2.0.0.build", is_build=True),)
    )
    check(
        b_rep.installed.get(ModuleId("bplug")) == SemVer4.parse("2.0.0.build")
        and (yscb_root.path / ".modules" / "bplug" / "tag.txt").read_bytes() == b"v2build",
        f"@build installation selected wrong artifact: {b_rep}",
    )
    b_disk_mf = json.loads((yscb_root.path / ".modules" / "bplug" / "manifest.json").read_text(encoding="utf-8"))
    check(
        b_disk_mf.get("version") == "2.0.0.build",
        f"@build materialized manifest.json version was not normalized to 2.0.0.build: {b_disk_mf}",
    )
    b_restore = engine.restore(offline=True)
    check(
        b_restore.installed.get(ModuleId("bplug")) == SemVer4.parse("2.0.0.build"),
        f"restore() failed on installed @build package: {b_restore}",
    )

    (build_dir / "bplug.zip").unlink()
    (build_dir / "bplug" / "2.0.0.build.zip").unlink()
    b_src = yscb_root.path / "source" / "bplug"
    b_src.mkdir(parents=True, exist_ok=True)
    (b_src / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "id": "bplug", "version": "2.2.0.0", "description": "Source build"}),
        encoding="utf-8",
    )
    (b_src / "module_entry.py").write_text("SRC_BUILD = True\n", encoding="utf-8")
    b_src_rep = engine.install((PackageRequest(module_id=ModuleId("bplug"), is_build=True),))
    check(
        b_src_rep.installed.get(ModuleId("bplug")) == SemVer4.parse("2.2.0.build"),
        f"Source-directory @build packaging failed: {b_src_rep}",
    )
    _ = engine.remove((ModuleId("bplug"), ModuleId("dynkeep")), purge_level=PurgeLevel.PURGE)

    ok_200_b, ok_200_sha = _build_module_zip_bytes("secmod", "2.0.0.0")
    mismatch_ver_b, mismatch_ver_sha = _build_module_zip_bytes("secmod", "1.0.0.0")
    http_st = _RepoHttpMirrorState(
        {
            "/secmod/index.json": json.dumps(
                {
                    "module_id": "secmod",
                    "versions": ["2.0.0.0"],
                    "releases": {"2.0.0.0": {"sha256": ok_200_sha, "status": "active"}},
                }
            ).encode("utf-8"),
            "/secmod/2.0.0.0.zip": ok_200_b,
            "/badver/secmod/index.json": json.dumps(
                {
                    "module_id": "secmod",
                    "versions": ["2.1.0.0"],
                    "releases": {"2.1.0.0": {"sha256": mismatch_ver_sha, "status": "active"}},
                }
            ).encode("utf-8"),
            "/badver/secmod/2.1.0.0.zip": mismatch_ver_b,
        }
    )
    http_st.redirects["/ssrf/secmod/index.json"] = "ftp://127.0.0.1/secmod/index.json"
    http_st.redirects["/filescheme/secmod/index.json"] = "file:///etc/passwd"
    srv2, thr2, url2 = _start_test_http_mirror(http_st)
    try:
        store.save_host_config(
            HostConfig(yscb_root=".yscb", default_provider=url2, installed_modules={})
        )
        _ = engine.install((PackageRequest(module_id=ModuleId("secmod"), version_spec="==2.0.0.0"),))
        check((yscb_root.path / ".mirror" / "secmod" / "index.json").is_file())

        for blocked_sub in ("ssrf", "filescheme"):
            expect_yscb_code(
                lambda sub=blocked_sub: engine.install(
                    (
                        PackageRequest(
                            module_id=ModuleId("secmod"),
                            provider_override=f"{url2}/{sub}",
                        ),
                    )
                ),
                ErrorCode.SECURITY_GATED,
            )
        expect_yscb_code(
            lambda: engine.update(provider="http://127.0.0.1:99999"),
            ErrorCode.CONFIG_INVALID,
        )
        expect_yscb_code(
            lambda: engine.install(
                (
                    PackageRequest(
                        module_id=ModuleId("secmod"),
                        version_spec="==2.1.0.0",
                        provider_override=f"{url2}/badver",
                    ),
                )
            ),
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
        )

        (yscb_root.path / ".mirror" / "secmod" / "index.json").unlink()
        shutil.rmtree(yscb_root.path / ".modules" / "secmod")
        off_rep = engine.restore(offline=True)
        check(
            off_rep.installed.get(ModuleId("secmod")) == SemVer4.parse("2.0.0.0")
            and (yscb_root.path / ".modules" / "secmod" / "manifest.json").is_file(),
            f"Offline restore with pre-seeded .mirror zip and absent index.json failed: {off_rep}",
        )
    finally:
        srv2.shutdown()
        srv2.server_close()
        thr2.join(timeout=3.0)
        check(not thr2.is_alive(), "Secondary HTTP mirror server thread did not terminate")


def _verify_manifest_parser_core_metadata_and_env_leases(suite_root: Path) -> None:
    lease_ws = suite_root / "lease_manifest_suite"
    host_dir = HostPath(lease_ws / "host")
    yscb_root = HostPath(lease_ws / "host" / ".yscb")
    cache_dir = HostPath(yscb_root.path / ".cache")
    wheels_dir = HostPath(lease_ws / "wheels")
    for d in (host_dir.path, yscb_root.path, cache_dir.path, wheels_dir.path):
        d.mkdir(parents=True, exist_ok=True)

    mf_spec = parse_manifest_dict(
        {
            "schema_version": 2,
            "id": "rel-spec",
            "version": "2.1.0.0",
            "description": "Manifest with spec release type key",
            "release": {"type": "minor", "urgency": "recommended", "summary": "Spec key release"},
        },
        expected_id=ModuleId("rel-spec"),
    )
    check(
        mf_spec.release == ReleaseMeta(release_type="minor", urgency=ReleaseUrgency.RECOMMENDED, summary="Spec key release"),
        f"parse_manifest_dict failed to normalize release.type: {mf_spec.release}",
    )
    mf_alias = parse_manifest_dict(
        {
            "schema_version": 2,
            "id": "rel-alias",
            "version": "2.1.0.1",
            "description": "Manifest with release_type alias",
            "release": {"release_type": "hotfix", "urgency": "critical", "summary": "Alias key release"},
        }
    )
    check(
        mf_alias.release == ReleaseMeta(release_type="hotfix", urgency=ReleaseUrgency.CRITICAL, summary="Alias key release"),
        f"parse_manifest_dict failed to accept release.release_type: {mf_alias.release}",
    )
    for bad_rel in (
        {"type": "minor", "release_type": "minor"},
        {"type": "minor", "release_type": "patch"},
        {"type": "minor", "extra_key": "nope"},
    ):
        expect_yscb_code(
            lambda rel_obj=bad_rel: parse_manifest_dict(
                {
                    "schema_version": 2,
                    "id": "rel-bad",
                    "version": "2.0.0.0",
                    "description": "Invalid release payload",
                    "release": rel_obj,
                }
            ),
            ErrorCode.CONFIG_INVALID,
        )
    expect_yscb_code(
        lambda: parse_manifest_dict(
            {"schema_version": 2, "id": "wrong-id", "version": "2.0.0.0", "description": "Mismatch"},
            expected_id=ModuleId("expected-id"),
        ),
        ErrorCode.CONFIG_INVALID,
    )
    expect_yscb_code(
        lambda: parse_manifest_dict(
            {"schema_version": 2, "id": "unk-key", "version": "2.0.0.0", "description": "Unknown", "extra": 1}
        ),
        ErrorCode.CONFIG_INVALID,
    )

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    vfs = VfsHub(UriMountTable(build_standard_mount_rules(host_dir, yscb_root, project_root=host_dir))).for_kernel()
    deployer = AtomicPackageDeployer(yscb_root=yscb_root, config_store=store, vfs=vfs)
    rel_zip_b, _ = _build_module_zip_bytes("relmod", "2.0.0.0")
    rel_zip_p = lease_ws / "relmod_200.zip"
    rel_zip_p.write_bytes(rel_zip_b)
    _ = deployer.materialize_module(ModuleId("relmod"), HostPath(rel_zip_p))
    discovered = discover_installed_manifests_map(yscb_root)
    check(
        ModuleId("relmod") in discovered
        and discovered[ModuleId("relmod")].release is not None
        and discovered[ModuleId("relmod")].release.release_type == "minor",
        f"discover_installed_manifests_map skipped or misparsed module with release.type: {discovered}",
    )

    core_mf_path = CORE_SRC_ROOT / "manifest.json"
    check(core_mf_path.is_file(), f"Missing core package manifest at {core_mf_path}")
    core_mf_doc = json.loads(core_mf_path.read_text(encoding="utf-8"))
    core_mf = parse_manifest_dict(core_mf_doc, expected_id=ModuleId("core"))
    check(
        core_mf.id == ModuleId("core")
        and core_mf.schema_version == 2
        and core_mf.version == SemVer4.parse("2.0.0.0")
        and not core_mf.is_tier1
        and core_mf.release is not None
        and (CORE_SRC_ROOT / core_mf.entry).is_file(),
        f"Core source manifest.json validation failed: {core_mf}",
    )
    core_tmpl_path = CORE_SRC_ROOT / "configurable" / "config.project.json.tmpl"
    core_ignore_path = CORE_SRC_ROOT / ".yscbignore"
    check(core_tmpl_path.is_file() and core_ignore_path.is_file(), "Missing core configurable template or .yscbignore")
    core_tmpl_doc = json.loads(core_tmpl_path.read_text(encoding="utf-8"))
    check(
        core_tmpl_doc.get("project_root") == "./"
        and core_tmpl_doc.get("locale") == ["zh", "en"]
        and core_tmpl_doc.get("idle_timeout_sec") == 300.0,
        f"Unexpected core config.project.json.tmpl payload: {core_tmpl_doc}",
    )
    deployed_core_cfg = store.deploy_configurable(ModuleId("core"), HostPath(CORE_SRC_ROOT / "configurable"))
    check("config.project.json" in deployed_core_cfg, f"Core configurable deployment failed: {deployed_core_cfg}")
    ignore_text = core_ignore_path.read_text(encoding="utf-8")
    check("__pycache__/" in ignore_text and "tests/" in ignore_text, "Core .yscbignore missing expected exclusions")

    _build_pure_wheel(wheels_dir.path, "lease-wheel-lib", "lease_wheel_lib", "1.0.0", 100)
    pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=cache_dir)
    spec = ImmutableVenvPool.compute_env_spec("lease_grp", {"lease-wheel-lib": "==1.0.0"})
    built = pool.ensure_env(spec, offline=True, wheel_cache_dir=wheels_dir)
    env_dir = built.env_dir
    meta_path = env_dir.path / ".yscb_env_meta.json"
    st_before = os.lstat(meta_path)
    check(
        touch_env_last_used(env_dir, min_interval_sec=3600.0) is False,
        "Throttled touch_env_last_used must skip write within min_interval_sec",
    )
    st_after_skip = os.lstat(meta_path)
    check(
        st_after_skip.st_ino == st_before.st_ino and st_after_skip.st_mtime_ns == st_before.st_mtime_ns,
        "Throttled touch_env_last_used unexpectedly rewrote metadata file",
    )
    check(touch_env_last_used(env_dir, min_interval_sec=0.0) is True, "touch_env_last_used(min_interval_sec=0) must write")

    aged_doc = json.loads(meta_path.read_text(encoding="utf-8"))
    aged_doc["last_used_epoch_sec"] = time.time() - (9.0 * 86400.0)
    meta_path.write_text(json.dumps(aged_doc), encoding="utf-8")
    check(touch_env_last_used(env_dir, min_interval_sec=3600.0) is True, "Aged env must refresh on touch_env_last_used")
    refreshed_doc = json.loads(meta_path.read_text(encoding="utf-8"))
    check(
        abs(time.time() - float(refreshed_doc["last_used_epoch_sec"])) < 30.0,
        f"touch_env_last_used did not refresh last_used_epoch_sec: {refreshed_doc}",
    )
    gc_policy = EnvGcPolicy(grace_days=7.0, keep_inactive_per_group=1)
    gc_retained = EnvGarbageCollector(pool, policy=gc_policy).collect((), force_all=False)
    check(
        env_dir in gc_retained.retained_rollback_dirs and env_dir.path.is_dir(),
        f"Touched env must regain 7-day grace retention: {gc_retained}",
    )
    check(touch_env_last_used(HostPath(lease_ws / "missing_env")) is False)

    lease_one = acquire_env_shared_lease(pool, spec.env_hash)
    lease_two = acquire_env_shared_lease(pool, spec.env_hash)
    try:
        check(
            lease_one is not None
            and lease_one.is_acquired
            and lease_one.is_shared
            and lease_two is not None
            and lease_two.is_acquired
            and lease_two.is_shared,
            "Concurrent acquire_env_shared_lease calls must both succeed in shared mode",
        )
        gc_shared_held = EnvGarbageCollector(pool, policy=gc_policy).collect((), force_all=True)
        check(
            env_dir in gc_shared_held.skipped_locked_dirs
            and env_dir not in gc_shared_held.removed_dirs
            and (env_dir.path / "pyvenv.cfg").is_file(),
            f"GC must skip active .venv protected by acquire_env_shared_lease: {gc_shared_held}",
        )
    finally:
        if lease_two is not None:
            lease_two.release()
        if lease_one is not None:
            lease_one.release()

    check(
        acquire_env_lease_for_python(pool, HostPath(sys.executable)) is None,
        "Host system python outside pool must return None from acquire_env_lease_for_python",
    )
    aged_doc["last_used_epoch_sec"] = time.time() - (9.0 * 86400.0)
    meta_path.write_text(json.dumps(aged_doc), encoding="utf-8")
    py_exe = pool.get_python_executable(spec)
    check(py_exe is not None, "Expected valid python executable for managed env")
    py_lease = acquire_env_lease_for_python(pool, py_exe) if py_exe is not None else None
    try:
        check(py_lease is not None and py_lease.is_acquired and py_lease.is_shared, "acquire_env_lease_for_python failed")
        touched_via_py = json.loads(meta_path.read_text(encoding="utf-8"))
        check(
            abs(time.time() - float(touched_via_py["last_used_epoch_sec"])) < 30.0,
            f"acquire_env_lease_for_python failed to refresh aged last_used_epoch_sec: {touched_via_py}",
        )
        gc_py_held = EnvGarbageCollector(pool, policy=gc_policy).collect((), force_all=True)
        check(
            env_dir in gc_py_held.skipped_locked_dirs
            and env_dir not in gc_py_held.removed_dirs
            and (env_dir.path / "pyvenv.cfg").is_file(),
            f"GC must skip active .venv protected by acquire_env_lease_for_python: {gc_py_held}",
        )
    finally:
        if py_lease is not None:
            py_lease.release()

    excl_hash = EnvHash("0" * 16)
    excl_lock = FileLock(cache_dir.join("locks", f"env_{excl_hash.short(16)}.lock"), allow_transitions=False)
    excl_lock.acquire(shared=False, blocking=False)
    try:
        check(
            acquire_env_shared_lease(pool, excl_hash) is None,
            "acquire_env_shared_lease must return None while exclusive lock is held",
        )
    finally:
        excl_lock.release()

    gc_after_release = EnvGarbageCollector(pool, policy=gc_policy).collect((), force_all=True)
    check(
        env_dir in gc_after_release.removed_dirs and not env_dir.path.exists(),
        f"Released env must be removable by force_all GC: {gc_after_release}",
    )


def _verify_migration_rollback_storage_local(base_root: Path) -> None:
    ws_dir = base_root / "mig_storage_rb_suite"
    host_dir = HostPath(ws_dir / "repo")
    yscb_root = HostPath(ws_dir / "repo" / ".yscb")
    host_dir.path.mkdir(parents=True, exist_ok=True)
    yscb_root.path.mkdir(parents=True, exist_ok=True)

    store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
    store.save_host_config(
        HostConfig(
            yscb_root=".yscb",
            default_provider="./releases",
            installed_modules={},
        )
    )
    store.set_value(ModuleId("mod_exist"), "secret_tok", "keep-secret", local=True)
    vault = SnapshotVault(host_dir=host_dir, yscb_root=yscb_root)
    pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=HostPath(yscb_root.path / ".cache"))
    vfs = VfsHub(UriMountTable(build_standard_mount_rules(host_dir, yscb_root))).for_kernel()
    eng = OfflinePackageEngine(
        host_dir=host_dir,
        yscb_root=yscb_root,
        config_store=store,
        snapshot_vault=vault,
        env_pool=pool,
        vfs=vfs,
    )

    exist_dir = yscb_root.path / ".storage.local" / "mod_exist"
    (exist_dir / "nested").mkdir(parents=True, exist_ok=True)
    (exist_dir / "state.db").write_bytes(b"DB_V1_BYTES")
    (exist_dir / "state.db-wal").write_bytes(b"WAL_V1_BYTES")
    (exist_dir / "state.db-shm").write_bytes(b"SHM_V1_BYTES")
    (exist_dir / "nested" / "keep.bin").write_bytes(b"NESTED_V1")
    fresh_dir = yscb_root.path / ".storage.local" / "mod_fresh"
    check(not fresh_dir.exists())

    with eng.migration_rollback_scope() as rb_handle:
        check(isinstance(rb_handle, MigrationRollbackHandle) and callable(rb_handle))
        rb_handle.snapshot_module_storage_local(ModuleId("mod_exist"))
        rb_handle.snapshot_module_storage_local(ModuleId("mod_exist"))  # idempotent
        rb_handle.snapshot_module_storage_local(ModuleId("mod_fresh"))
        (exist_dir / "state.db").write_bytes(b"DB_V2_CORRUPT")
        (exist_dir / "state.db-wal").unlink()
        (exist_dir / "extra_v2.db").write_bytes(b"EXTRA")
        fresh_dir.mkdir(parents=True, exist_ok=True)
        (fresh_dir / "created_in_v2.db").write_bytes(b"FRESH_V2")
        rb_handle.restore()

    check((exist_dir / "state.db").read_bytes() == b"DB_V1_BYTES")
    check((exist_dir / "state.db-wal").read_bytes() == b"WAL_V1_BYTES")
    check((exist_dir / "state.db-shm").read_bytes() == b"SHM_V1_BYTES")
    check((exist_dir / "nested" / "keep.bin").read_bytes() == b"NESTED_V1")
    check(not (exist_dir / "extra_v2.db").exists())
    check(not fresh_dir.exists(), "Newly created .storage.local/<mod>/ must be removed on migration rollback")
    if not IS_WINDOWS:
        loc_f = yscb_root.path / ".config.local" / "mod_exist" / "config.local.json"
        check(stat.S_IMODE(loc_f.stat().st_mode) == 0o600, "Restored .config.local must retain 0o600 mode")
    temp_dir = yscb_root.path / ".temp"
    check(not temp_dir.exists() or not list(temp_dir.iterdir()), "migration_rollback_scope must clean .temp/ guard on exit")


def _execute_all_domain34_checks(base_root: Path) -> None:
    try:
        log("[METADATA-PACKAGING] Verifying manifest.json 2.0, 2x2 ConfigStore, DeepInfiller & SnapshotVault...")
        _verify_metadata_config_and_snapshot_vault(base_root)
        log("[METADATA-PACKAGING] Verifying Contributes 2.0 schema round-trip, 5 merge strategies, ProvenanceGraph & locales...")
        _verify_metadata_contributes_engine(base_root)
        log("[METADATA-PACKAGING] Verifying ImmutableVenvPool offline wheel builds, EnvHealthProbe & EnvGarbageCollector...")
        _verify_packaging_env_pool_probe_and_gc(base_root)
        log("[METADATA-PACKAGING] Verifying unified manifest parser, core packaging metadata, and env shared leases...")
        _verify_manifest_parser_core_metadata_and_env_leases(base_root)
        log("[METADATA-PACKAGING] Verifying OfflinePackageEngine, Zip security, pruned fallback, rollback & UpdateChecker...")
        _verify_packaging_installer_engine_and_update_checker(base_root)
        _verify_boundary_hardening_and_tx_recovery(base_root)
        _verify_build_packages_and_error_passthrough(base_root)
        _verify_locked_workspace_dirs_snapshot_and_tx_rollback(base_root)
        _verify_migration_rollback_storage_local(base_root)
        log("[METADATA-PACKAGING] All Domain 3 & Domain 4 checks passed.")
    finally:
        for sub_name in (
            "cfg_suite",
            "ctb_suite",
            "env_suite",
            "lease_manifest_suite",
            "installer_suite",
            "boundary_suite",
            "ext_contract_suite",
            "mig_storage_rb_suite",
        ):
            sub_p = base_root / sub_name
            if sub_p.exists():
                shutil.rmtree(sub_p, ignore_errors=True)


def run_metadata_packaging_suite(tmp_root: Optional[Path] = None) -> None:
    """Execute the full Wave 1.2b verification suite for metadata.{config,contributes} and packaging.{env,installer}."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        if tmp_root is not None:
            suite_dir = tmp_root / "domain_metadata_packaging"
            suite_dir.mkdir(parents=True, exist_ok=True)
            _execute_all_domain34_checks(suite_dir)
            return
        with tempfile.TemporaryDirectory(prefix="yscb_v2_d34_") as raw_tmp:
            _execute_all_domain34_checks(Path(raw_tmp))


__all__ = ("run_metadata_packaging_suite",)


if __name__ == "__main__":
    run_metadata_packaging_suite()
