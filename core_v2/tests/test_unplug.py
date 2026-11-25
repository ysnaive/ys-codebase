"""Top-down orthogonal domain unplug verification suite for Core 2.0 (Domains 6 -> 1)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Final, Sequence

from tests import CORE_SRC_ROOT
from tests._harness import check, log

_WALK_PACKAGES_PREAMBLE: Final[str] = """
import importlib, pkgutil
import core

def _verify_unplugged_walk(banned_prefixes, required_packages):
    def _on_walk_error(bad_mod_name):
        raise SystemExit(f"pkgutil.walk_packages failed on {bad_mod_name}")

    for banned in banned_prefixes:
        try:
            importlib.import_module(banned)
            raise SystemExit(f"Unexpected import success for unplugged {banned}")
        except ModuleNotFoundError:
            pass

    discovered = set()
    for mod_info in pkgutil.walk_packages(core.__path__, core.__name__ + ".", onerror=_on_walk_error):
        for banned in banned_prefixes:
            if mod_info.name == banned or mod_info.name.startswith(banned + "."):
                raise SystemExit(f"Unplugged prefix {banned} still discovered as {mod_info.name}")
        importlib.import_module(mod_info.name)
        discovered.add(mod_info.name)

    for req in required_packages:
        importlib.import_module(req)
        if req not in discovered:
            raise SystemExit(f"Expected package {req} missing from walk_packages")
"""

_PROBE_STAGE_WITHOUT_SURFACE: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from dataclasses import dataclass
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.surface.sdk", "core.surface.cli", "core.surface.bootstrap"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
        "core.metadata.config",
        "core.metadata.contributes",
        "core.packaging.env",
        "core.packaging.installer",
        "core.execution.event",
        "core.execution.lifecycle",
        "core.execution.rpc",
        "core.execution.runtime",
        "core.execution.daemon",
    ),
)

from core.foundation import HostPath, ModuleId, TaskId
from core.execution.runtime import (
    ClientRoutingPolicy,
    DispatcherHostOptions,
    InvokeRequest,
    ModuleProviderPort,
    RuntimeDispatcher,
    Task,
    TaskContext,
    TaskMetadata,
    YscbModule,
)
from core.execution.rpc import DaemonConnectionConfig

@dataclass(frozen=True, slots=True)
class _PingIn:
    label: str = "ok"

@dataclass(frozen=True, slots=True)
class _PingOut:
    echo: str

class _PingTask(Task[_PingIn, _PingOut]):
    @property
    def metadata(self) -> TaskMetadata[_PingIn, _PingOut]:
        return TaskMetadata(task_id=TaskId("echo.ping"), input_type=_PingIn, output_type=_PingOut)

    def run(self, req: _PingIn, ctx: TaskContext) -> _PingOut:
        _ = ctx
        return _PingOut(echo=f"pong:{req.label}")

class _EchoMod(YscbModule):
    @property
    def module_id(self) -> ModuleId:
        return ModuleId("echo")

    def tasks(self):
        return (_PingTask(),)

class _EmptyProvider(ModuleProviderPort):
    def list_modules(self):
        return ()
    def get_module(self, module_id: ModuleId):
        _ = module_id
        return None
    def reload(self) -> None:
        return None

with tempfile.TemporaryDirectory() as td:
    ws_hp = HostPath(Path(td) / ".yscb")
    cache_hp = HostPath(ws_hp.path / ".cache")
    ws_hp.path.mkdir(parents=True, exist_ok=True)
    disp = RuntimeDispatcher(
        workspace_root=ws_hp,
        cache_dir=cache_hp,
        module_provider=_EmptyProvider(),
        options=DispatcherHostOptions(
            connection_config=DaemonConnectionConfig(enabled=False, auto_spawn=False),
            in_memory_modules=(_EchoMod(),),
        ),
    )
    try:
        out = disp.invoke(
            InvokeRequest(
                task_id=TaskId("echo.ping"),
                raw_input={"label": "domain5"},
                workspace_root=ws_hp,
                caller_cwd=ws_hp,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
            ),
            output_type=_PingOut,
        )
        if not out.ok or out.value is None or out.value.echo != "pong:domain5":
            raise SystemExit(f"Domain 5 standalone dispatch failed: {out}")
    finally:
        disp.shutdown()

sys.stdout.write(json.dumps({"stage": "unplug_surface", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_EXECUTION: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import hashlib, json, sys, tempfile, zipfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.execution.runtime", "core.execution.daemon"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
        "core.metadata.config",
        "core.metadata.contributes",
        "core.packaging.env",
        "core.packaging.installer",
    ),
)

from core.foundation import HostPath, ModuleId
from core.filesystem.vfs import UriMountTable, VfsHub, build_standard_mount_rules
from core.metadata.config import ConfigStore, SnapshotVault
from core.packaging.env import ImmutableVenvPool
from core.packaging.installer import OfflinePackageEngine, PackageRequest

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    host_dir = root / "project"
    yscb_root = host_dir / ".yscb"
    prov_dir = root / "provider"
    (prov_dir / "sample").mkdir(parents=True, exist_ok=True)
    host_dir.mkdir(parents=True, exist_ok=True)
    yscb_root.mkdir(parents=True, exist_ok=True)
    (host_dir / "yscb.config.json").write_text(
        json.dumps(
            {
                "yscb_root": ".yscb",
                "default_provider": str(prov_dir),
                "installed_modules": {"core": {"version": "2.0.0.0", "provider": str(prov_dir), "installed_at": "2026-11-24T00:00:00Z"}},
            }
        ),
        encoding="utf-8",
    )
    core_dir = yscb_root / ".modules" / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "manifest.json").write_text(
        json.dumps({"id": "core", "version": "2.0.0.0", "description": "Core microkernel"}),
        encoding="utf-8",
    )
    zpath = prov_dir / "sample" / "1.0.0.0.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"id": "sample", "version": "1.0.0.0", "description": "Sample pkg", "dependencies": {"core": ">=2.0.0"}}),
        )
        zf.writestr("module_entry.py", "MARKER = 1\\n")
        zf.writestr("configurable/config.project.json.tmpl", json.dumps({"flag": True}))
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (prov_dir / "sample" / "index.json").write_text(
        json.dumps(
            {
                "module_id": "sample",
                "versions": ["1.0.0.0"],
                "releases": {
                    "1.0.0.0": {
                        "version": "1.0.0.0",
                        "status": "active",
                        "urgency": "recommended",
                        "yanked": False,
                        "sha256": sha,
                        "filename": "1.0.0.0.zip",
                        "summary": "Sample 1.0",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    host_hp = HostPath(host_dir)
    root_hp = HostPath(yscb_root)
    cfg = ConfigStore(host_dir=host_hp, yscb_root=root_hp)
    snap = SnapshotVault(host_dir=host_hp, yscb_root=root_hp)
    env_pool = ImmutableVenvPool(yscb_root=root_hp, cache_dir=HostPath(yscb_root / ".cache"))
    mt = UriMountTable(build_standard_mount_rules(host_dir=host_hp, yscb_root=root_hp, project_root=host_hp))
    kvfs = VfsHub(mt).for_kernel()
    eng = OfflinePackageEngine(
        host_dir=host_hp,
        yscb_root=root_hp,
        config_store=cfg,
        snapshot_vault=snap,
        env_pool=env_pool,
        vfs=kvfs,
    )
    res = eng.install((PackageRequest(module_id=ModuleId("sample"), version_spec="1.0.0.0"),))
    if ModuleId("sample") not in res.installed or not (yscb_root / "config" / "sample" / "config.project.json").is_file():
        raise SystemExit(f"Domain 4 standalone install failed: {res}")

sys.stdout.write(json.dumps({"stage": "unplug_execution", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_INSTALLER: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging.installer"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
        "core.metadata.config",
        "core.metadata.contributes",
        "core.packaging.env",
    ),
)

from core.foundation import HostPath, ModuleId, SemVer4
from core.metadata.config import ModuleManifest
from core.packaging.env import EnvGarbageCollector, EnvHealthProbe, ImmutableVenvPool

with tempfile.TemporaryDirectory() as td:
    root_hp = HostPath(Path(td) / ".yscb")
    cache_hp = HostPath(root_hp.path / ".cache")
    root_hp.path.mkdir(parents=True, exist_ok=True)
    pool = ImmutableVenvPool(yscb_root=root_hp, cache_dir=cache_hp)
    mf = ModuleManifest(
        id=ModuleId("worker"),
        version=SemVer4.parse("1.0.0"),
        description="Tier 1 worker",
        venv_group="grp",
        pip_dependencies={"demo_pkg": ">=1.0"},
    )
    resolved = ImmutableVenvPool.resolve_group_specs((mf,))
    spec = resolved[ModuleId("worker")]
    probe = EnvHealthProbe(pool)
    rep = probe.check_quick(spec)
    if rep.quick_ok or pool.is_env_ready(spec):
        raise SystemExit(f"Unbuilt env unexpectedly reported ready: {rep}")
    gc_res = EnvGarbageCollector(pool).collect((spec,))
    if gc_res.removed_dirs:
        raise SystemExit(f"Unexpected GC removals on empty pool: {gc_res}")

sys.stdout.write(json.dumps({"stage": "unplug_installer", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_PACKAGING: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.packaging.env", "core.packaging.installer"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
        "core.metadata.config",
        "core.metadata.contributes",
    ),
)

from core.foundation import HostPath, ModuleId
from core.metadata.config import ConfigStore, SnapshotVault
from core.metadata.contributes import ContribField, ContributesAggregator, ExtensionPointSpec, MergeStrategy, discover_installed_manifests_map

@dataclass(frozen=True, slots=True)
class _ItemSpec:
    tags: Annotated[tuple[str, ...], ContribField(merge=MergeStrategy.EXTEND)] = ()

with tempfile.TemporaryDirectory() as td:
    host_dir = Path(td) / "host"
    yscb_root = host_dir / ".yscb"
    (yscb_root / ".modules" / "donor" / "contributes").mkdir(parents=True, exist_ok=True)
    (yscb_root / ".modules" / "hostmod").mkdir(parents=True, exist_ok=True)
    (host_dir / "yscb.config.json").write_text(
        json.dumps({"yscb_root": ".yscb", "default_provider": "local", "installed_modules": {}}),
        encoding="utf-8",
    )
    (yscb_root / ".modules" / "donor" / "manifest.json").write_text(
        json.dumps({"id": "donor", "version": "1.0.0.0", "description": "Donor mod"}),
        encoding="utf-8",
    )
    (yscb_root / ".modules" / "hostmod" / "manifest.json").write_text(
        json.dumps({"id": "hostmod", "version": "1.0.0.0", "description": "Host mod"}),
        encoding="utf-8",
    )
    (yscb_root / ".modules" / "donor" / "contributes" / "hostmod.json").write_text(
        json.dumps({"items": {"tags": ["alpha", "beta"]}}),
        encoding="utf-8",
    )
    host_hp = HostPath(host_dir)
    root_hp = HostPath(yscb_root)
    store = ConfigStore(host_dir=host_hp, yscb_root=root_hp)
    store.set_value(ModuleId("donor"), "mode", "fast", local=False)
    vault = SnapshotVault(host_dir=host_hp, yscb_root=root_hp)
    rec = vault.create_snapshot("unplug-test", force=True)
    store.set_value(ModuleId("donor"), "mode", "slow", local=False)
    vault.restore_snapshot(rec.snapshot_id)
    store.reload()
    if store.get_module_dict(ModuleId("donor")).get("mode") != "fast":
        raise SystemExit("ConfigStore + SnapshotVault restore mismatch")
    mfs_map = discover_installed_manifests_map(root_hp)
    ep = ExtensionPointSpec(name="items", payload_type=_ItemSpec, merge_strategy=MergeStrategy.MERGE)
    agg = ContributesAggregator(
        yscb_root=root_hp,
        manifests=tuple(mfs_map.values()),
        live_specs={ModuleId("hostmod"): (ep,)},
    )
    agg_out = agg.aggregate(ModuleId("hostmod"))
    if agg_out.raw_merged.get("items") != {"tags": ("alpha", "beta")}:
        raise SystemExit(f"ContributesAggregator aggregate mismatch: {agg_out.raw_merged}")

sys.stdout.write(json.dumps({"stage": "unplug_packaging", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_CONTRIBUTES: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata.contributes"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
        "core.metadata.config",
    ),
)

from core.foundation import HostPath, ModuleId
from core.metadata.config import ConfigStore, DeepInfiller, SnapshotVault

with tempfile.TemporaryDirectory() as td:
    host_dir = Path(td) / "host"
    yscb_root = host_dir / ".yscb"
    host_dir.mkdir(parents=True, exist_ok=True)
    yscb_root.mkdir(parents=True, exist_ok=True)
    (host_dir / "yscb.config.json").write_text(
        json.dumps({"yscb_root": ".yscb", "default_provider": "local", "installed_modules": {}}),
        encoding="utf-8",
    )
    merged_cfg, added_keys = DeepInfiller.infill({"keep": 1}, {"keep": 9, "added": 2})
    if merged_cfg != {"keep": 1, "added": 2} or added_keys != ("added",):
        raise SystemExit(f"DeepInfiller standalone check failed: {(merged_cfg, added_keys)}")
    host_hp = HostPath(host_dir)
    root_hp = HostPath(yscb_root)
    store = ConfigStore(host_dir=host_hp, yscb_root=root_hp)
    store.set_value(ModuleId("cfgmod"), "threads", 4, local=False)
    vault = SnapshotVault(host_dir=host_hp, yscb_root=root_hp)
    snap = vault.create_snapshot("config-only", force=True)
    store.set_value(ModuleId("cfgmod"), "threads", 8, local=False)
    vault.restore_snapshot(snap.snapshot_id)
    store.reload()
    if store.get_module_dict(ModuleId("cfgmod")).get("threads") != 4:
        raise SystemExit("ConfigStore standalone snapshot restore mismatch")

sys.stdout.write(json.dumps({"stage": "unplug_contributes", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_METADATA: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata", "core.metadata.config", "core.metadata.contributes"),
    (
        "core.foundation",
        "core.filesystem.fs",
        "core.filesystem.vfs",
        "core.filesystem.storage",
        "core.filesystem.space",
    ),
)

from core.foundation import HostPath, ModuleId, SemanticUri, SpaceId
from core.filesystem.vfs import UriMountTable, VfsHub, build_standard_mount_rules
from core.filesystem.storage import ModuleDatabase, SchemaMigration
from core.filesystem.space import GitignoreMaterializer, SpaceRegistry, SpaceScanner, SpaceSpec

with tempfile.TemporaryDirectory() as td:
    host_hp = HostPath(Path(td) / "proj")
    root_hp = HostPath(host_hp.path / ".yscb")
    host_hp.path.mkdir(parents=True, exist_ok=True)
    root_hp.path.mkdir(parents=True, exist_ok=True)
    (host_hp.path / "app.py").write_text("VALUE = 42\\n", encoding="utf-8")
    mt = UriMountTable(build_standard_mount_rules(host_dir=host_hp, yscb_root=root_hp, project_root=host_hp))
    hub = VfsHub(mt)
    kvfs = hub.for_kernel()
    mvfs = hub.for_module(ModuleId("alpha"))
    mvfs.write_json(SemanticUri("storage.local", "@/doc.json"), {"ok": True})
    db = ModuleDatabase(
        kvfs,
        SemanticUri("storage.local", "core/space/state.db"),
        migrations=(SchemaMigration(version=1, description="init", sql_statements=("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);",)),),
    )
    try:
        sp = SpaceSpec(space_id=SpaceId("alpha", "src"), entries=(SemanticUri("project", ""),), include=("*.py",))
        reg = SpaceRegistry(kvfs, db, static_specs=(sp,))
        scanner = SpaceScanner(reg, db)
        batch = scanner.scan(SpaceId("alpha", "src"))
        if len(batch.added) != 1:
            raise SystemExit(f"SpaceScanner mismatch: {batch}")
        _ = GitignoreMaterializer(reg, kvfs).sync()
    finally:
        db.close()

sys.stdout.write(json.dumps({"stage": "unplug_metadata", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_SPACE: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata", "core.filesystem.space"),
    ("core.foundation", "core.filesystem.fs", "core.filesystem.vfs", "core.filesystem.storage"),
)

from core.foundation import HostPath, ModuleId, SemanticUri
from core.filesystem.vfs import UriMountTable, VfsHub, build_standard_mount_rules
from core.filesystem.storage import BlobVault, ModuleDatabase, SchemaMigration

with tempfile.TemporaryDirectory() as td:
    host_hp = HostPath(Path(td) / "proj")
    root_hp = HostPath(host_hp.path / ".yscb")
    host_hp.path.mkdir(parents=True, exist_ok=True)
    root_hp.path.mkdir(parents=True, exist_ok=True)
    mt = UriMountTable(build_standard_mount_rules(host_dir=host_hp, yscb_root=root_hp, project_root=host_hp))
    mvfs = VfsHub(mt).for_module(ModuleId("alpha"))
    db = ModuleDatabase(
        mvfs,
        SemanticUri("storage.local", "@/items.db"),
        migrations=(SchemaMigration(version=1, description="init", sql_statements=("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT);",)),),
    )
    try:
        with db.write_transaction() as tx:
            tx.execute("INSERT INTO t (id, name) VALUES (1, 'solo');")
        with db.read_snapshot() as snap:
            rows = snap.query_all("SELECT name FROM t WHERE id = 1;")
            if len(rows) != 1 or rows[0][0] != "solo":
                raise SystemExit(f"ModuleDatabase snapshot mismatch: {rows}")
    finally:
        db.close()
    bv = BlobVault(mvfs, SemanticUri("storage.local", "@/blobs"))
    digest = bv.put_content_addressed(b"payload-bytes")
    if bv.get_bytes(digest) != b"payload-bytes":
        raise SystemExit("BlobVault roundtrip mismatch")

sys.stdout.write(json.dumps({"stage": "unplug_space", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_STORAGE: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata", "core.filesystem.space", "core.filesystem.storage"),
    ("core.foundation", "core.filesystem.fs", "core.filesystem.vfs"),
)

from core.foundation import HostPath, ModuleId, SemanticUri
from core.filesystem.vfs import ReadonlyPolicy, UriMountTable, VfsHub, build_standard_mount_rules

with tempfile.TemporaryDirectory() as td:
    host_hp = HostPath(Path(td) / "proj")
    root_hp = HostPath(host_hp.path / ".yscb")
    host_hp.path.mkdir(parents=True, exist_ok=True)
    root_hp.path.mkdir(parents=True, exist_ok=True)
    mt = UriMountTable(build_standard_mount_rules(host_dir=host_hp, yscb_root=root_hp, project_root=host_hp))
    ro = ReadonlyPolicy()
    mvfs = VfsHub(mt, readonly_policy=ro).for_module(ModuleId("alpha"))
    target = SemanticUri("storage.local", "@/hello.txt")
    mvfs.write_text(target, "vfs-only")
    if mvfs.read_text(target) != "vfs-only":
        raise SystemExit("ScopedVfs read/write mismatch")

sys.stdout.write(json.dumps({"stage": "unplug_storage", "ok": True}))
"""

_PROBE_STAGE_WITHOUT_VFS: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata", "core.filesystem.space", "core.filesystem.storage", "core.filesystem.vfs"),
    ("core.foundation", "core.filesystem.fs"),
)

from core.foundation import HostPath
from core.filesystem.fs import FileLock, atomic_write_json, read_json_dict, resolve_contained_subpath

with tempfile.TemporaryDirectory() as td:
    base_hp = HostPath(Path(td))
    doc_hp = resolve_contained_subpath(base_hp, "data.json")
    lk_hp = resolve_contained_subpath(base_hp, "data.lock")
    with FileLock(lk_hp):
        atomic_write_json(doc_hp, {"fs_only": 1})
    if read_json_dict(doc_hp) != {"fs_only": 1}:
        raise SystemExit("core.filesystem.fs standalone check failed")

sys.stdout.write(json.dumps({"stage": "unplug_vfs", "ok": True}))
"""

_PROBE_STAGE_FOUNDATION_ONLY: Final[str] = _WALK_PACKAGES_PREAMBLE + """
import json, sys, tempfile
from dataclasses import dataclass
from pathlib import Path

_verify_unplugged_walk(
    ("core.surface", "core.execution", "core.packaging", "core.metadata", "core.filesystem"),
    ("core.foundation",),
)

import core.foundation as fd

@dataclass(frozen=True, slots=True)
class _FoundationDto:
    ver: fd.SemVer4
    uri: fd.SemanticUri
    space: fd.SpaceId

dto = _FoundationDto(
    ver=fd.SemVer4.parse("2.1.0"),
    uri=fd.SemanticUri.parse("storage.local://@/state.json"),
    space=fd.SpaceId.parse("core/docs"),
)
encoded = fd.DataclassCodec.encode_object(dto)
decoded = fd.DataclassCodec.decode(_FoundationDto, encoded)
if decoded != dto or not fd.VersionConstraint.parse("^2.0.0").satisfies(dto.ver):
    raise SystemExit("Foundation DataclassCodec / SemVer4 standalone check failed")

schema = fd.SchemaExporter.export(_FoundationDto)
if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
    raise SystemExit("Foundation SchemaExporter standalone check failed")

cat = fd.LocaleCatalog({fd.ModuleId("core"): {"en": {"hello": "world"}}}, default_chain=("en",))
if cat.translate("hello", caller_module=fd.ModuleId("core")) != "world":
    raise SystemExit("Foundation LocaleCatalog standalone check failed")

with tempfile.TemporaryDirectory() as td:
    rot = fd.LogRotator(fd.HostPath(Path(td) / "app.jsonl"), max_bytes=4096)
    try:
        rot.append_jsonl({"event": "boot"})
        rows = rot.read_jsonl()
        if len(rows) != 1 or rows[0].get("event") != "boot":
            raise SystemExit("Foundation LogRotator standalone check failed")
    finally:
        rot.close()

sys.stdout.write(json.dumps({"stage": "foundation_only", "ok": True}))
"""

_UNPLUG_SEQUENCE: Final[tuple[tuple[str, tuple[str, ...], str], ...]] = (
    ("Domain 6 (core/surface)", ("surface",), _PROBE_STAGE_WITHOUT_SURFACE),
    ("Domain 5 (core/execution)", ("execution",), _PROBE_STAGE_WITHOUT_EXECUTION),
    ("Domain 4.installer (core/packaging/installer)", ("packaging", "installer"), _PROBE_STAGE_WITHOUT_INSTALLER),
    ("Domain 4 (core/packaging)", ("packaging",), _PROBE_STAGE_WITHOUT_PACKAGING),
    ("Domain 3.contributes (core/metadata/contributes)", ("metadata", "contributes"), _PROBE_STAGE_WITHOUT_CONTRIBUTES),
    ("Domain 3 (core/metadata)", ("metadata",), _PROBE_STAGE_WITHOUT_METADATA),
    ("Domain 2.space (core/filesystem/space)", ("filesystem", "space"), _PROBE_STAGE_WITHOUT_SPACE),
    ("Domain 2.storage (core/filesystem/storage)", ("filesystem", "storage"), _PROBE_STAGE_WITHOUT_STORAGE),
    ("Domain 2.vfs (core/filesystem/vfs)", ("filesystem", "vfs"), _PROBE_STAGE_WITHOUT_VFS),
    ("Domain 2.fs (core/filesystem -> Foundation only)", ("filesystem",), _PROBE_STAGE_FOUNDATION_ONLY),
)


def _build_isolated_unplug_env(isolated_src_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k.upper() in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "__PYVENV_LAUNCHER__"}:
            continue
        env[k] = v
    env["PYTHONPATH"] = str(isolated_src_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_unplug_probe(isolated_src_root: Path, stage_label: str, code: str) -> None:
    win_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd: list[str] = [sys.executable, "-X", "utf8", "-B", "-W", "error::ResourceWarning"]
    if sys.flags.optimize > 0:
        cmd.append("-" + ("O" * sys.flags.optimize))
    cmd.extend(["-c", code])
    cp = subprocess.run(
        cmd,
        cwd=str(isolated_src_root),
        env=_build_isolated_unplug_env(isolated_src_root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30.0,
        check=False,
        creationflags=win_flags,
    )
    check(
        cp.returncode == 0,
        f"Unplug stage '{stage_label}' failed (rc={cp.returncode}): stdout={cp.stdout!r} stderr={cp.stderr!r}",
    )
    doc = json.loads(cp.stdout.strip())
    check(isinstance(doc, dict) and doc.get("ok") is True, f"Unexpected unplug probe output for '{stage_label}': {doc}")


def _remove_rel_dir(core_pkg_dir: Path, rel_parts: Sequence[str]) -> None:
    target = core_pkg_dir.joinpath(*rel_parts)
    check(target.is_dir(), f"Expected directory to unplug at {target}")
    shutil.rmtree(target)
    check(not target.exists(), f"Expected unplugged directory {target} to be physically absent")


def run_unplug_suite(tmp_root: Path) -> None:
    """Physically delete upper domains top-down in an isolated copy and verify zero reverse coupling."""
    log("[UNPLUG] Copying core source tree to isolated sandbox for top-down physical unplug verification...")
    unplug_root = tmp_root / "unplug_sandbox_src"
    if unplug_root.exists():
        shutil.rmtree(unplug_root)
    isolated_core = unplug_root / "core"
    shutil.copytree(
        CORE_SRC_ROOT / "core",
        isolated_core,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    for stage_label, rel_parts, probe_code in _UNPLUG_SEQUENCE:
        log(f"[UNPLUG] Physically removing {stage_label} and running isolated live contract probe...")
        _remove_rel_dir(isolated_core, rel_parts)
        _run_unplug_probe(unplug_root, stage_label, probe_code)

    remaining_entries = sorted(p.name for p in isolated_core.iterdir() if p.name != "__init__.py")
    check(
        remaining_entries == ["foundation"],
        f"Expected only ['foundation'] left after full unplug chain, got {remaining_entries}",
    )
    log("[UNPLUG] All 10 top-down domain unplug stages passed with zero reverse coupling.")


__all__ = ("run_unplug_suite",)
