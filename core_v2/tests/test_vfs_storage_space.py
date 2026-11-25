"""Domain 2 verification suite covering core.filesystem.{vfs, storage, space}."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
from typing import Optional
import warnings

from core.filesystem.fs import atomic_write_bytes
from core.filesystem.space import (
    ConsumerCursor,
    GitignoreMaterializer,
    GitignoreSyncResult,
    HashPolicy,
    SpaceDiffBatch,
    SpaceFileEntry,
    SpaceMatchExplain,
    SpaceRegistry,
    SpaceScanner,
    SpaceSpec,
    SpaceStatusSnapshot,
)
from core.filesystem.storage import (
    BlobVault,
    ModuleDatabase,
    SchemaMigration,
    StorageOpenOptions,
    WriteTransaction,
)
from core.filesystem.vfs import (
    AccessPolicy,
    KernelVfs,
    MemoryVfsProvider,
    MountHealthEntry,
    MountRule,
    PhysicalDirectoryProvider,
    ReadonlyPolicy,
    ReadonlySyncResult,
    ScopedVfs,
    UriMountTable,
    VfsCapabilities,
    VfsEchoGuard,
    VfsHub,
    VfsStat,
    build_standard_mount_rules,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    HostPath,
    ModuleId,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    TaskCancelledException,
    YscbError,
)
from tests._harness import assert_raises_val_error, check, expect_yscb_code, log


@dataclass(frozen=True, slots=True)
class _VfsTestFixture:
    hub: VfsHub
    host_dir: HostPath
    yscb_root: HostPath
    project_root: Optional[HostPath]


def _provision_vfs_hub(
    base_dir: Path,
    *,
    with_project: bool = True,
    extra_rules: tuple[MountRule, ...] = (),
    providers: Optional[dict[str, MemoryVfsProvider | PhysicalDirectoryProvider]] = None,
    access_policy: Optional[AccessPolicy] = None,
) -> _VfsTestFixture:
    host_p = base_dir / "host"
    yscb_p = host_p / ".yscb"
    proj_p = host_p / "project"
    host_p.mkdir(parents=True, exist_ok=True)
    yscb_p.mkdir(parents=True, exist_ok=True)
    proj_hp: Optional[HostPath] = None
    if with_project:
        proj_p.mkdir(parents=True, exist_ok=True)
        proj_hp = HostPath(proj_p)
    host_hp = HostPath(host_p)
    yscb_hp = HostPath(yscb_p)
    rules = build_standard_mount_rules(
        host_hp,
        yscb_hp,
        project_root=proj_hp,
        extra_rules=extra_rules,
    )
    mount_table = UriMountTable(rules, providers=providers)
    hub = VfsHub(
        mount_table,
        readonly_policy=ReadonlyPolicy(),
        echo_guard=VfsEchoGuard(ttl_sec=10.0, max_entries=512),
        access_policy=access_policy,
    )
    return _VfsTestFixture(hub=hub, host_dir=host_hp, yscb_root=yscb_hp, project_root=proj_hp)


def _verify_vfs_scheme_matrix_and_mount_guards(suite_root: Path) -> None:
    ws_undef = suite_root / "vfs_undef"
    fx_undef = _provision_vfs_hub(ws_undef, with_project=False)
    mt_undef = fx_undef.hub.mount_table

    rules_map = {rule.scheme: rule for rule in mt_undef.list_rules()}
    expected_schemes = {
        "yscb",
        "yscb.host",
        "project",
        "module",
        "module.source",
        "module.build",
        "module.release",
        "module.mirror",
        "config",
        "config.local",
        "cache",
        "storage",
        "storage.local",
        "snapshot",
        "yscb.venv",
    }
    check(set(rules_map.keys()) == expected_schemes, f"Scheme B set mismatch: {set(rules_map.keys())}")

    ro_tracked = (
        VfsCapabilities.READABLE
        | VfsCapabilities.PERSISTENT
        | VfsCapabilities.GIT_TRACKED
        | VfsCapabilities.ENUMERABLE
        | VfsCapabilities.PHYSICAL_PATH
    )
    ro_untracked = (
        VfsCapabilities.READABLE
        | VfsCapabilities.PERSISTENT
        | VfsCapabilities.ENUMERABLE
        | VfsCapabilities.PHYSICAL_PATH
    )
    rw_tracked = ro_tracked | VfsCapabilities.WRITABLE
    rw_local_persist = ro_untracked | VfsCapabilities.WRITABLE
    rw_ephemeral = (
        VfsCapabilities.READABLE
        | VfsCapabilities.WRITABLE
        | VfsCapabilities.ENUMERABLE
        | VfsCapabilities.PHYSICAL_PATH
    )

    expected_caps_by_scheme: dict[str, VfsCapabilities] = {
        "yscb": ro_tracked,
        "yscb.host": ro_tracked,
        "project": rw_tracked,
        "module": ro_untracked,
        "module.source": rw_tracked,
        "module.build": rw_ephemeral,
        "module.release": rw_tracked,
        "module.mirror": ro_untracked,
        "config": rw_tracked,
        "config.local": rw_local_persist,
        "cache": rw_ephemeral,
        "storage": rw_tracked,
        "storage.local": rw_local_persist,
        "snapshot": ro_untracked,
        "yscb.venv": ro_untracked,
    }
    for scheme_name, exp_caps in expected_caps_by_scheme.items():
        actual_caps = rules_map[scheme_name].capabilities
        check(
            actual_caps == exp_caps,
            f"Capability drift on {scheme_name}://: expected {exp_caps!r}, got {actual_caps!r}",
        )

    caught_undef = False
    try:
        mt_undef.resolve_physical(SemanticUri.parse("project://README.md"))
    except YscbError as exc:
        caught_undef = True
        check(exc.detail.code == ErrorCode.URI_UNDEFINED, f"Expected URI_UNDEFINED, got {exc.detail.code}")
        check(bool(exc.detail.remediation), "URI_UNDEFINED must carry actionable remediation hint")
    check(caught_undef, "Expected project:// resolution to raise URI_UNDEFINED when unconfigured")

    health_entries = mt_undef.check_health()
    check(len(health_entries) == 15 and all(isinstance(h, MountHealthEntry) for h in health_entries))
    proj_health = next(h for h in health_entries if h.scheme == "project")
    check(not proj_health.healthy, "Undefined project:// must report unhealthy in check_health()")

    expect_yscb_code(
        lambda: UriMountTable(
            (
                MountRule(scheme="alpha", target_uri=SemanticUri.parse("beta://sub")),
                MountRule(scheme="beta", target_uri=SemanticUri.parse("alpha://back")),
            )
        ),
        ErrorCode.URI_CYCLE,
    )
    expect_yscb_code(
        lambda: UriMountTable((MountRule(scheme="selfloop", target_uri=SemanticUri.parse("selfloop://x")),)),
        ErrorCode.URI_CYCLE,
    )


def _verify_vfs_containment_readonly_echo_and_memory(suite_root: Path) -> None:
    ws_full = suite_root / "vfs_full"
    plans_rule = MountRule(
        scheme="workflow.plans",
        target_uri=SemanticUri.parse("project://plans"),
        capabilities=(
            VfsCapabilities.READABLE
            | VfsCapabilities.WRITABLE
            | VfsCapabilities.PERSISTENT
            | VfsCapabilities.GIT_TRACKED
            | VfsCapabilities.ENUMERABLE
            | VfsCapabilities.PHYSICAL_PATH
        ),
        provider_module=ModuleId("agents-workflow"),
        description="Workflow plans directory alias.",
    )
    mem_provider = MemoryVfsProvider("mem")
    mem_rule = MountRule(
        scheme="mem",
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE,
        description="In-memory test provider.",
    )
    mem_alias_rule = MountRule(
        scheme="mem.sub",
        target_uri=SemanticUri.parse("mem://folder"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE,
    )
    access_pol = AccessPolicy(
        extra_writable_schemes={
            ModuleId("dev"): frozenset({"module.source", "module.build", "module.release"}),
            ModuleId("agents-workflow"): frozenset({"workflow.plans"}),
        },
        readonly_tunnel_modules=frozenset({ModuleId("agents-workflow")}),
    )
    fx = _provision_vfs_hub(
        ws_full,
        with_project=True,
        extra_rules=(plans_rule, mem_rule, mem_alias_rule),
        providers={"mem": mem_provider},
        access_policy=access_pol,
    )
    hub = fx.hub
    yscb_hp = fx.yscb_root
    proj_hp = fx.project_root
    check(proj_hp is not None)
    assert_raises_val_error(lambda: SemanticUri.parse("cache://../.cache_evil/escape.txt"))
    assert_raises_val_error(lambda: SemanticUri.parse("relative/no_scheme.txt"))

    sibling_evil = yscb_hp.path.parent / (yscb_hp.path.name + "_evil")
    sibling_evil.mkdir(parents=True, exist_ok=True)
    evil_file = sibling_evil / "secret.txt"
    evil_file.write_text("secret", encoding="utf-8")
    check(
        hub.mount_table.to_uri(HostPath(evil_file)) == SemanticUri.parse("yscb.host://.yscb_evil/secret.txt"),
        "Sibling .yscb_evil under host must map to yscb.host://, never prefix-collide with yscb://",
    )
    outside_host_evil = fx.host_dir.path.parent / (fx.host_dir.path.name + "_evil") / "secret.txt"
    outside_host_evil.parent.mkdir(parents=True, exist_ok=True)
    outside_host_evil.write_text("outside", encoding="utf-8")
    check(hub.mount_table.to_uri(HostPath(outside_host_evil)) is None, "Sibling host_evil outside all mounts must map to None")

    kernel_vfs = hub.for_kernel()
    mod_a_vfs = hub.for_module(ModuleId("mod-a"))
    mod_b_vfs = hub.for_module(ModuleId("mod-b"))
    dev_vfs = hub.for_module(ModuleId("dev"))
    aw_vfs = hub.for_module(ModuleId("agents-workflow"))
    check(isinstance(kernel_vfs, KernelVfs) and isinstance(mod_a_vfs, ScopedVfs))

    check(mod_a_vfs.bind_uri("storage.local://@/data.json") == SemanticUri.parse("storage.local://mod-a/data.json"))
    mod_a_vfs.write_json("storage.local://@/data.json", {"count": 7})
    check(mod_a_vfs.read_json("storage.local://mod-a/data.json") == {"count": 7})
    expect_yscb_code(lambda: mod_a_vfs.write_text("storage.local://mod-b/tamper.txt", "bad"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_b_vfs.delete("storage.local://mod-a/data.json"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a_vfs.write_text("yscb://forbidden.txt", "no"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a_vfs.write_text("module://mod-a/entry.py", "no"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a_vfs.write_text("module.build://artifact.whl", "no"), ErrorCode.ACCESS_DENIED)
    dev_vfs.write_bytes("module.build://artifact.whl", b"wheel_bytes")
    check(mod_a_vfs.read_bytes("module.build://artifact.whl") == b"wheel_bytes")

    aw_vfs.write_text("workflow.plans://roadmap.md", "line1\r\nline2\r\n")
    check(mod_a_vfs.read_bytes("project://plans/roadmap.md") == b"line1\nline2\n")
    roadmap_stat = mod_a_vfs.stat("project://plans/roadmap.md")
    check(isinstance(roadmap_stat, VfsStat) and roadmap_stat.exists and not roadmap_stat.is_dir)
    roadmap_phys = mod_a_vfs.try_get_physical_path("project://plans/roadmap.md")
    check(roadmap_phys is not None)
    if roadmap_phys is not None:
        check(
            hub.echo_guard.is_suppressed(
                roadmap_phys,
                roadmap_stat.mtime_ns,
                roadmap_stat.size_bytes,
                roadmap_stat.ino,
            ),
            "Cross-scheme write via workflow.plans:// must register canonical HostPath in VfsEchoGuard",
        )

        sync_res = hub.readonly_policy.sync_files((roadmap_phys,))
        check(isinstance(sync_res, ReadonlySyncResult) and sync_res.locked_count == 1)
        check(hub.readonly_policy.is_protected(roadmap_phys) and hub.readonly_policy.is_os_readonly(roadmap_phys))

        expect_yscb_code(
            lambda: mod_a_vfs.write_text("project://plans/roadmap.md", "unauthorized"),
            ErrorCode.READONLY_VIOLATION,
        )
        expect_yscb_code(
            lambda: mod_a_vfs.write_text("workflow.plans://roadmap.md", "unauthorized_alias"),
            ErrorCode.READONLY_VIOLATION,
        )

        aw_vfs.write_text("workflow.plans://roadmap.md", "authorized_module_tunnel\n")
        check(mod_a_vfs.read_text("project://plans/roadmap.md") == "authorized_module_tunnel\n")
        check(
            hub.readonly_policy.is_os_readonly(roadmap_phys),
            "OS readonly bit must be restored after authorized module tunnel write",
        )

        kernel_vfs.write_text_through_readonly("project://plans/roadmap.md", "kernel_tunnel\n")
        check(mod_a_vfs.read_text("workflow.plans://roadmap.md") == "kernel_tunnel\n")
        check(
            hub.readonly_policy.is_os_readonly(roadmap_phys),
            "OS readonly bit must be restored after KernelVfs write_text_through_readonly",
        )
        aw_vfs.mkdir("workflow.plans://occupied_dir")
        aw_vfs.write_text("workflow.plans://occupied_dir/child.md", "keep")
        failed_move_caught = False
        try:
            aw_vfs.move("workflow.plans://roadmap.md", "workflow.plans://occupied_dir")
        except OSError:
            failed_move_caught = True
        check(failed_move_caught, "Moving file onto non-empty directory must fail")
        check(
            hub.readonly_policy.is_os_readonly(roadmap_phys) and hub.readonly_policy.is_protected(roadmap_phys),
            "Failed authorized move must restore OS readonly protection on source file",
        )

        unlock_sync = hub.readonly_policy.sync_files(())
        check(unlock_sync.unlocked_count == 1 and not hub.readonly_policy.is_os_readonly(roadmap_phys))

    if proj_hp is not None:
        sym_target = proj_hp.path / "real_note.txt"
        sym_target.write_text("real", encoding="utf-8")
        sym_link = proj_hp.path / "linked_note.txt"
        symlink_created = True
        try:
            os.symlink(str(sym_target), str(sym_link))
        except (OSError, NotImplementedError):
            symlink_created = False
        if symlink_created:
            caught_sym = False
            try:
                _ = mod_a_vfs.read_text("project://linked_note.txt")
            except YscbError as exc:
                caught_sym = exc.detail.code in (ErrorCode.ACCESS_DENIED, ErrorCode.SECURITY_GATED)
            check(caught_sym, "Symlink inside PhysicalDirectoryProvider must be rejected")
            sym_link.unlink(missing_ok=True)

    check(kernel_vfs.try_get_physical_path("mem://folder/item.txt") is None)
    check(not bool(kernel_vfs.get_capabilities("mem://folder/item.txt") & VfsCapabilities.PHYSICAL_PATH))
    kernel_vfs.mkdir("mem://folder/nested")
    kernel_vfs.write_text("mem://folder/nested/item.txt", "hello_mem\r\nworld")
    check(kernel_vfs.exists("mem://folder/nested/item.txt"))
    check(kernel_vfs.read_bytes("mem://folder/nested/item.txt") == b"hello_mem\nworld")
    kernel_vfs.move("mem://folder/nested/item.txt", "mem://folder/moved.txt")
    check(not kernel_vfs.exists("mem://folder/nested/item.txt") and kernel_vfs.exists("mem://folder/moved.txt"))
    mem_entries = tuple(str(u) for u in kernel_vfs.iter_entries("mem://folder", recursive=True))
    check("mem://folder/moved.txt" in mem_entries, f"Expected moved.txt in MemoryVfsProvider entries: {mem_entries}")
    mem_alias_health = next(h for h in hub.mount_table.check_health() if h.scheme == "mem.sub")
    check(mem_alias_health.healthy, f"Alias over MemoryVfsProvider must report healthy: {mem_alias_health}")
    check(kernel_vfs.delete("mem://folder", recursive=True) and not kernel_vfs.exists("mem://folder/moved.txt"))

    custom_docs_dir = suite_root / "custom_no_phys_cap"
    custom_docs_dir.mkdir(parents=True, exist_ok=True)
    ov_mem_proj = MemoryVfsProvider("project")
    ov_mt = UriMountTable(
        (
            *build_standard_mount_rules(fx.host_dir, fx.yscb_root, project_root=fx.project_root),
            plans_rule,
            MountRule(scheme="custom.docs", target_path=HostPath(custom_docs_dir)),
        ),
        providers={"project": ov_mem_proj},
    )
    ov_hub = VfsHub(ov_mt, access_policy=access_pol)
    ov_kern = ov_hub.for_kernel()
    ov_mod = ov_hub.for_module(ModuleId("agents-workflow"))
    ov_kern.write_text("project://plans/in_mem.md", "overridden_mem\n")
    check(ov_mod.read_text("workflow.plans://in_mem.md") == "overridden_mem\n")
    check(ov_mod.stat("workflow.plans://in_mem.md").exists)
    ov_kern.write_text("custom.docs://guide.md", "masked_phys\n")
    check(ov_mod.try_get_physical_path("custom.docs://guide.md") is None)
    check(ov_mod.read_text("custom.docs://guide.md") == "masked_phys\n")
    check(ov_mod.stat("custom.docs://guide.md").exists)


def _migrate_v3_backfill(tx: WriteTransaction) -> None:
    tx.execute("UPDATE items SET label = label || '_v3'")


def _verify_storage_gatekeeping_wal_mvcc_migrations_and_vault(suite_root: Path) -> None:
    ws_stg = suite_root / "storage_suite"
    mem_prov = MemoryVfsProvider("mem")
    mem_rule = MountRule(
        scheme="mem",
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE,
    )
    fx_stg = _provision_vfs_hub(
        ws_stg,
        with_project=True,
        extra_rules=(mem_rule,),
        providers={"mem": mem_prov},
    )
    mod_idx_vfs = fx_stg.hub.for_module(ModuleId("kdb"))

    for illegal_uri in (
        "cache://@/illegal.db",
        "storage://@/illegal.db",
        "config.local://@/illegal.db",
        "project://illegal.db",
        "mem://kdb/illegal.db",
        "storage.local://other-mod/illegal.db",
    ):
        expect_yscb_code(lambda u=illegal_uri: ModuleDatabase(mod_idx_vfs, u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=illegal_uri: BlobVault(mod_idx_vfs, u), ErrorCode.ACCESS_DENIED)

    mig_step_one = SchemaMigration(
        version=1,
        description="Create items table",
        sql_statements=("CREATE TABLE items (item_id INTEGER PRIMARY KEY, label TEXT NOT NULL)",),
    )
    mig_step_two = SchemaMigration(
        version=2,
        description="Add score column",
        sql_statements=("ALTER TABLE items ADD COLUMN score INTEGER NOT NULL DEFAULT 0",),
    )
    mig_step_three = SchemaMigration(
        version=3,
        description="Backfill v3 suffix",
        migrate_fn=_migrate_v3_backfill,
    )

    db_uri = "storage.local://@/index.db"
    with ModuleDatabase(
        mod_idx_vfs,
        db_uri,
        migrations=(mig_step_one, mig_step_two),
        options=StorageOpenOptions(busy_timeout_ms=5000, wal_autocheckpoint_pages=500, read_only_pool_size=4),
    ) as db_v2:
        check(db_v2.schema_version == 2 and db_v2.committed_gen() == SnapshotGen(0))
        with db_v2.write_transaction() as tx_seed:
            tx_seed.executemany(
                "INSERT INTO items (item_id, label, score) VALUES (?, ?, ?)",
                [(idx, f"seed_{idx}", idx) for idx in range(1, 101)],
            )
            tx_seed.set_watermark("upstream_space", "gen_1")
            bumped = tx_seed.mark_generation_bumped()
            check(bumped == SnapshotGen(1))
        check(db_v2.committed_gen() == SnapshotGen(1) and db_v2.get_watermark("upstream_space") == "gen_1")

    with ModuleDatabase(
        mod_idx_vfs,
        db_uri,
        migrations=(mig_step_one, mig_step_two, mig_step_three),
        options=StorageOpenOptions(read_only_pool_size=4),
    ) as db_v3:
        check(db_v3.schema_version == 3 and db_v3.verify_integrity())
        with db_v3.read_snapshot() as snap_check:
            sample_row = snap_check.query_one("SELECT label FROM items WHERE item_id = ?", (1,))
            check(sample_row == ("seed_1_v3",), f"Migration v3 callback drift: {sample_row!r}")
            check(snap_check.list_watermarks() == {"upstream_space": "gen_1"})

        writer_entered = threading.Event()
        release_writer = threading.Event()
        reader_start_barrier = threading.Barrier(4)
        writer_errors: list[BaseException] = []
        reader_errors: list[BaseException] = []

        def _bg_long_writer() -> None:
            try:
                with db_v3.write_transaction() as tx_bg:
                    tx_bg.executemany(
                        "INSERT INTO items (item_id, label, score) VALUES (?, ?, ?)",
                        [(100 + idx, f"bulk_{idx}", idx) for idx in range(1, 1001)],
                    )
                    tx_bg.set_watermark("upstream_space", "gen_2")
                    tx_bg.mark_generation_bumped()
                    writer_entered.set()
                    check(release_writer.wait(timeout=10.0), "Timed out waiting for foreground readers")
            except BaseException as exc:
                writer_errors.append(exc)
                writer_entered.set()

        def _fg_snapshot_reader() -> None:
            try:
                reader_start_barrier.wait(timeout=5.0)
                for _ in range(20):
                    with db_v3.read_snapshot() as fg_snap:
                        fg_gen = fg_snap.committed_gen()
                        cnt_row = fg_snap.query_one("SELECT COUNT(*) FROM items")
                        wm_val = fg_snap.get_watermark("upstream_space")
                        check(fg_gen == SnapshotGen(1), f"Dirty generation read during active tx: {fg_gen}")
                        check(cnt_row == (100,), f"Dirty row count read during active tx: {cnt_row}")
                        check(wm_val == "gen_1", f"Dirty watermark read during active tx: {wm_val}")
            except BaseException as exc:
                reader_errors.append(exc)

        writer_thr = threading.Thread(target=_bg_long_writer, name="test-stg-writer")
        writer_thr.start()
        check(writer_entered.wait(timeout=5.0), "Background WriteTransaction failed to start")

        fg_threads = [
            threading.Thread(target=_fg_snapshot_reader, name=f"test-stg-reader-{idx}")
            for idx in range(4)
        ]
        for thr in fg_threads:
            thr.start()
        for thr in fg_threads:
            thr.join(timeout=8.0)
            check(not thr.is_alive(), "Foreground reader thread hung during WAL write")

        release_writer.set()
        writer_thr.join(timeout=8.0)
        check(not writer_thr.is_alive(), "Background writer thread hung on commit")
        check(not writer_errors, lambda: f"Writer error: {writer_errors}")
        check(not reader_errors, lambda: f"Reader error: {reader_errors}")

        with db_v3.read_snapshot() as post_snap:
            check(post_snap.committed_gen() == SnapshotGen(2))
            check(post_snap.query_one("SELECT COUNT(*) FROM items") == (1100,))
            streamed_count = sum(1 for _ in post_snap.iter_rows("SELECT item_id FROM items", batch_size=128))
            check(streamed_count == 1100)

        serial_barrier = threading.Barrier(2)
        serial_errors: list[BaseException] = []

        def _contended_writer(offset_base: int) -> None:
            try:
                serial_barrier.wait(timeout=5.0)
                with db_v3.write_transaction() as tx_c:
                    cur_max_row = tx_c.query_one("SELECT MAX(score) FROM items")
                    cur_max = int(cur_max_row[0] or 0) if cur_max_row is not None else 0
                    tx_c.execute(
                        "INSERT INTO items (item_id, label, score) VALUES (?, ?, ?)",
                        (offset_base, f"contended_{offset_base}", cur_max + 1),
                    )
                    tx_c.mark_generation_bumped()
            except BaseException as exc:
                serial_errors.append(exc)

        contend_a = threading.Thread(target=_contended_writer, args=(5001,))
        contend_b = threading.Thread(target=_contended_writer, args=(5002,))
        contend_a.start()
        contend_b.start()
        contend_a.join(timeout=8.0)
        contend_b.join(timeout=8.0)
        check(not serial_errors, lambda: f"BEGIN IMMEDIATE contention failed: {serial_errors}")
        check(db_v3.committed_gen() == SnapshotGen(4))

        cancel_tok = CancellationToken()
        caught_cancel = False
        try:
            with db_v3.write_transaction(cancel_token=cancel_tok) as tx_abort:
                tx_abort.execute("INSERT INTO items (item_id, label, score) VALUES (?, ?, ?)", (9999, "aborted", 1))
                tx_abort.mark_generation_bumped()
                cancel_tok.cancel(reason="abort_before_commit")
        except TaskCancelledException:
            caught_cancel = True
        check(caught_cancel, "Expected TaskCancelledException when cancel_token triggers before commit")
        check(db_v3.committed_gen() == SnapshotGen(4), "Rolled-back cancelled tx must not bump generation")
        with db_v3.read_snapshot() as after_abort_snap:
            check(after_abort_snap.query_one("SELECT 1 FROM items WHERE item_id = ?", (9999,)) is None)

        _ = db_v3.checkpoint(truncate=True)

    check(db_v3.is_closed)

    expect_yscb_code(
        lambda: ModuleDatabase(mod_idx_vfs, db_uri, migrations=(mig_step_one,)),
        ErrorCode.SCHEMA_MIGRATION_ERROR,
    )

    corrupt_uri = "storage.local://@/corrupt.db"
    mod_idx_vfs.write_bytes(corrupt_uri, b"not_a_valid_sqlite3_header_payload_at_all" * 4)
    expect_yscb_code(
        lambda: ModuleDatabase(mod_idx_vfs, corrupt_uri, migrations=(mig_step_one,)),
        ErrorCode.STORAGE_CORRUPT,
    )
    if os.name != "nt":
        stg_mod_dir = mod_idx_vfs.try_get_physical_path("storage.local://@/")
        if stg_mod_dir is not None:
            fifo_db_path = stg_mod_dir.path / "fifo_trap.db"
            os.mkfifo(fifo_db_path, 0o400)
            try:
                expect_yscb_code(
                    lambda: ModuleDatabase(mod_idx_vfs, "storage.local://@/fifo_trap.db", migrations=(mig_step_one,)),
                    ErrorCode.ACCESS_DENIED,
                )
            finally:
                fifo_db_path.unlink(missing_ok=True)
            wal_victim = ws_stg / "external_wal_victim.bin"
            wal_victim.write_bytes(b"victim")
            wal_sym = stg_mod_dir.path / "index.db-wal"
            os.symlink(wal_victim, wal_sym)
            try:
                expect_yscb_code(
                    lambda: ModuleDatabase(mod_idx_vfs, db_uri, migrations=(mig_step_one, mig_step_two, mig_step_three)),
                    ErrorCode.ACCESS_DENIED,
                )
            finally:
                wal_sym.unlink(missing_ok=True)

    bad_sql_mig = SchemaMigration(
        version=1,
        description="broken_sql",
        sql_statements=("CREATE TABLE broken_syntax (id INT PRIMARY KEY,,);",),
    )
    expect_yscb_code(
        lambda: ModuleDatabase(mod_idx_vfs, "storage.local://@/bad_mig.db", migrations=(bad_sql_mig,)),
        ErrorCode.SCHEMA_MIGRATION_ERROR,
    )

    with ModuleDatabase(mod_idx_vfs, "storage.local://@/drain_close.db", migrations=(mig_step_one,)) as drain_db:
        with drain_db.read_snapshot() as _reentrant_snap:
            expect_yscb_code(drain_db.close, ErrorCode.ILLEGAL_LOCK_REENTRANCY)
            expect_yscb_code(
                lambda: drain_db.write_transaction().__enter__(),
                ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            )
            expect_yscb_code(drain_db.checkpoint, ErrorCode.ILLEGAL_LOCK_REENTRANCY)
        snap_entered = threading.Event()
        allow_snap_exit = threading.Event()
        close_done = threading.Event()

        def _hold_reader() -> None:
            with drain_db.read_snapshot() as held_r:
                _ = held_r.committed_gen()
                snap_entered.set()
                check(allow_snap_exit.wait(timeout=5.0), "Reader release timed out")

        r_thr = threading.Thread(target=_hold_reader, name="test-drain-reader")
        r_thr.start()
        check(snap_entered.wait(timeout=5.0), "Reader did not enter snapshot")

        def _closer() -> None:
            drain_db.close()
            close_done.set()

        c_thr = threading.Thread(target=_closer, name="test-drain-closer")
        c_thr.start()
        check(not close_done.wait(timeout=0.05), "close() returned before active SnapshotReader exited")
        allow_snap_exit.set()
        r_thr.join(timeout=5.0)
        c_thr.join(timeout=5.0)
        check(close_done.is_set() and drain_db.is_closed, "close() failed to finish after reader drained")

    surrogate_uri = "storage.local://@/bad_surrogate.json"
    mod_idx_vfs.write_bytes(surrogate_uri, b'{"bad": "\\ud800"}')
    assert_raises_val_error(lambda: mod_idx_vfs.read_json(surrogate_uri))
    ok_deep_json = "[" * 128 + "1" + "]" * 128
    ok_deep_uri = "storage.local://@/ok_deep_array.json"
    mod_idx_vfs.write_bytes(ok_deep_uri, ok_deep_json.encode("utf-8"))
    check(isinstance(mod_idx_vfs.read_json(ok_deep_uri), list))
    deep_json = "[" * 129 + "1" + "]" * 129
    deep_uri = "storage.local://@/deep_array.json"
    mod_idx_vfs.write_bytes(deep_uri, deep_json.encode("utf-8"))
    assert_raises_val_error(lambda: mod_idx_vfs.read_json(deep_uri))

    vault = BlobVault(mod_idx_vfs, "storage.local://@/blobs")
    check(vault.root_uri == SemanticUri.parse("storage.local://kdb/blobs"))
    blob_payload = b"vector_payload_" * 1024
    ref_primary = vault.put_content_addressed(blob_payload)
    ref_duplicate = vault.put_content_addressed(blob_payload)
    check(ref_primary == ref_duplicate and vault.exists(ref_primary))
    check(vault.get_bytes(ref_primary) == blob_payload)
    fh_opt = vault.open_read(ref_primary)
    check(fh_opt is not None)
    if fh_opt is not None:
        with fh_opt as fh:
            check(fh.read(15) == b"vector_payload_")

    orphan_ref = vault.put_content_addressed(b"orphan_blob_bytes")
    keyed_ref = vault.put_keyed("snapshots/meta.bin", b"keyed_payload")
    vault_phys = mod_idx_vfs.try_get_physical_path("storage.local://@/blobs")
    check(vault_phys is not None)
    if vault_phys is not None:
        staging_probe = vault_phys.path / ".tmp_999_abcdef012345"
        staging_probe.write_bytes(b"in_flight_atomic_write")
        gc_removed = vault.gc_unreferenced(frozenset({ref_primary}))
        check(gc_removed == 2, f"Expected 2 unreferenced blobs collected, got {gc_removed}")
        check(vault.exists(ref_primary) and not vault.exists(orphan_ref) and not vault.exists(keyed_ref))
        check(staging_probe.is_file(), "gc_unreferenced must skip transient .tmp_* staging files")
        staging_probe.unlink()
    check(vault.delete(ref_primary) and not vault.exists(ref_primary))

    storage_local_dir = fx_stg.yscb_root.path / ".storage.local"
    shutil.rmtree(storage_local_dir)
    check(not storage_local_dir.exists(), "Closed ModuleDatabase and BlobVault must release all OS file handles")


def _verify_space_algebra_pruning_and_dynamic_gitignore(suite_root: Path) -> None:
    ws_spc = suite_root / "space_algebra"
    fx_spc = _provision_vfs_hub(ws_spc, with_project=True)
    hub = fx_spc.hub
    proj_hp = fx_spc.project_root
    check(proj_hp is not None)
    if proj_hp is None:
        return
    proj_dir = proj_hp.path
    kernel_vfs = hub.for_kernel()

    sample_spec = SpaceSpec(
        space_id=SpaceId("project", "sample"),
        entries=(SemanticUri.parse("project://src"),),
        include=("*.py",),
        hash_policy=HashPolicy.FULL_HASH,
    )
    check(DataclassCodec.decode(SpaceSpec, DataclassCodec.encode(sample_spec)) == sample_spec)

    (proj_dir / "logs" / "vendor_cache" / "pkg").mkdir(parents=True, exist_ok=True)
    (proj_dir / "logs" / "build" / "sub").mkdir(parents=True, exist_ok=True)
    (proj_dir / "logs" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (proj_dir / "logs" / "debug.log").write_text("dbg\n", encoding="utf-8")
    (proj_dir / "logs" / "important.log").write_text("keep_log\n", encoding="utf-8")
    (proj_dir / "logs" / "vendor_cache" / "pkg" / "mod.py").write_text("vendored = 1\n", encoding="utf-8")
    (proj_dir / "logs" / "build" / "keep.txt").write_text("keep_artifact\n", encoding="utf-8")
    (proj_dir / "logs" / "build" / "sub" / "drop.txt").write_text("drop_artifact\n", encoding="utf-8")

    (proj_dir / "src" / "nested_dir").mkdir(parents=True, exist_ok=True)
    (proj_dir / "src" / "main.py").write_text("main = True\n", encoding="utf-8")
    (proj_dir / "src" / "README.md").write_text("# src readme\n", encoding="utf-8")
    (proj_dir / "src" / "nested_dir" / "note.txt").write_text("nested_note\n", encoding="utf-8")

    (proj_dir / "docs").mkdir(parents=True, exist_ok=True)
    (proj_dir / "docs" / "README.md").write_text("# docs readme\n", encoding="utf-8")
    (proj_dir / "docs" / "secret_plan.md").write_text("# confidential\n", encoding="utf-8")

    static_specs = (
        SpaceSpec(
            space_id=SpaceId("custom", "ignore_rules"),
            entries=(SemanticUri.parse("project://"),),
            include=("*.log", "vendor_cache/**", "build/**"),
            exclude=("important.log", "build/keep.txt"),
            watch=False,
        ),
        SpaceSpec(
            space_id=SpaceId("project", "logs_view"),
            entries=(SemanticUri.parse("project://logs"),),
            presets=("!custom/ignore_rules",),
        ),
        SpaceSpec(
            space_id=SpaceId("project", "sym_inc"),
            entries=(SemanticUri.parse("project://src"),),
            include=("nested_dir/", "*.py"),
            exclude=("README.md",),
        ),
        SpaceSpec(
            space_id=SpaceId("mod-a", "docs"),
            entries=(SemanticUri.parse("project://docs"),),
            include=("*.md",),
        ),
        SpaceSpec(
            space_id=SpaceId("custom", "secrets"),
            entries=(SemanticUri.parse("project://docs"),),
            include=("secret_*.md",),
            watch=False,
        ),
        SpaceSpec(
            space_id=SpaceId("project", "bundle"),
            entries=(SemanticUri.parse("project://src"),),
            include=("*.py",),
            exclude=("README.md",),
            compose=("mod-a/docs", "!custom/secrets"),
        ),
        SpaceSpec(
            space_id=SpaceId("mod-u", "merged"),
            entries=(SemanticUri.parse("project://src"),),
            include=("*.py",),
        ),
        SpaceSpec(
            space_id=SpaceId("mod-u", "merged"),
            entries=(SemanticUri.parse("project://docs"),),
            include=("*",),
        ),
        SpaceSpec(
            space_id=SpaceId("project", "gitignore"),
            entries=(SemanticUri.parse("project://"),),
            include=("dist/",),
            exclude=("dist/public.js",),
            watch=False,
        ),
    )

    with ModuleDatabase(kernel_vfs, "storage.local://core/space/state.db") as state_db:
        reg = SpaceRegistry(kernel_vfs, state_db, static_specs=static_specs)

        for builtin_name in ("core/gitignore", "/gitignore", "core/workspace", "/workspace", "/readonly", "readonly"):
            check(isinstance(reg.get_space(builtin_name), SpaceSpec))
        expect_yscb_code(lambda: reg.get_space("nonexistent/space"), ErrorCode.SPACE_NOT_FOUND)

        merged_u = reg.get_space("mod-u/merged")
        check(merged_u.include == ("*",), f"Wildcard union ['*'] U ['*.py'] must equal ('*',): {merged_u.include}")
        check(len(merged_u.entries) == 2)
        synth_docs = reg.get_space("docs")
        check(synth_docs.space_id == SpaceId("", "docs") and "mod-a/docs" in synth_docs.compose)

        sym_files = tuple(str(f.rel_path) for f in reg.iter_files("project/sym_inc"))
        check(
            sym_files == ("src/main.py", "src/nested_dir/note.txt"),
            f"Symmetric directory-prefix include failed: {sym_files}",
        )

        pruned_logs = tuple(str(f.rel_path) for f in reg.iter_files("project/logs_view"))
        check(
            pruned_logs == ("logs/app.py", "logs/build/keep.txt", "logs/important.log"),
            f"Negated preset subtree exemption/pruning mismatch: {pruned_logs}",
        )
        exp_keep = reg.match_path("project/logs_view", HostPath(proj_dir / "logs" / "build" / "keep.txt"))
        check(isinstance(exp_keep, SpaceMatchExplain) and exp_keep.matched)
        exp_vend = reg.match_path("project/logs_view", HostPath(proj_dir / "logs" / "vendor_cache" / "pkg" / "mod.py"))
        check((not exp_vend.matched) and exp_vend.source_space == SpaceId("custom", "ignore_rules"))

        bundle_files = tuple(str(f.rel_path) for f in reg.iter_files("project/bundle"))
        check(
            bundle_files == ("docs/README.md", "src/main.py"),
            f"Compose pure union/difference violated (parent must not filter child): {bundle_files}",
        )
        resolved_readme = reg.resolve_file_path("project/bundle", "docs/README.md")
        check(resolved_readme == HostPath(proj_dir / "docs" / "README.md"))
        expect_yscb_code(
            lambda: reg.resolve_file_path("project/bundle", "docs/secret_plan.md"),
            ErrorCode.SPACE_NOT_FOUND,
        )

        overlay_reg = reg.with_overlay(
            (
                SpaceSpec(
                    space_id=SpaceId("temp", "ephemeral"),
                    entries=(SemanticUri.parse("project://docs"),),
                    include=("*.md",),
                ),
            )
        )
        check(overlay_reg.get_space("temp/ephemeral").space_id == SpaceId("temp", "ephemeral"))
        expect_yscb_code(lambda: reg.get_space("temp/ephemeral"), ErrorCode.SPACE_NOT_FOUND)

        expect_yscb_code(
            lambda: reg.with_overlay(
                (
                    SpaceSpec(space_id=SpaceId("cyc", "left"), presets=("cyc/right",)),
                    SpaceSpec(space_id=SpaceId("cyc", "right"), presets=("!cyc/left",)),
                )
            ),
            ErrorCode.SPACE_CYCLE,
        )
        expect_yscb_code(
            lambda: reg.with_overlay(
                (
                    SpaceSpec(space_id=SpaceId("compcyc", "alpha"), compose=("compcyc/beta",)),
                    SpaceSpec(space_id=SpaceId("compcyc", "beta"), compose=("!compcyc/alpha",)),
                )
            ),
            ErrorCode.SPACE_CYCLE,
        )

        aw_mod = ModuleId("agents-workflow")
        dyn_gi_spec = SpaceSpec(
            space_id=SpaceId("agents-workflow", "gitignore"),
            entries=(SemanticUri.parse("project://"),),
            include=("project://plans/scratch/", "project://plans/*.draft.md", "*.draft.md"),
            exclude=("plans/scratch/keep.draft.md",),
            watch=False,
        )
        dyn_ro_spec = SpaceSpec(
            space_id=SpaceId("agents-workflow", "readonly"),
            entries=(SemanticUri.parse("project://docs"),),
            include=("README.md",),
            watch=False,
        )
        check(reg.set_dynamic_space(aw_mod, "gitignore", dyn_gi_spec) is True)
        check(reg.set_dynamic_space(aw_mod, "gitignore", dyn_gi_spec) is False)
        check(reg.set_dynamic_space(aw_mod, "readonly", dyn_ro_spec) is True)

    with ModuleDatabase(kernel_vfs, "storage.local://core/space/state.db") as reopened_db:
        reg_restarted = SpaceRegistry(kernel_vfs, reopened_db, static_specs=static_specs)
        check(reg_restarted.get_space("agents-workflow/gitignore") == dyn_gi_spec)
        check(reg_restarted.match_path("/readonly", HostPath(proj_dir / "docs" / "README.md")).matched)

        hub.readonly_policy.update_matcher(lambda hp: reg_restarted.match_path("/readonly", hp).matched)
        guest_vfs = hub.for_module(ModuleId("ast"))
        expect_yscb_code(
            lambda: guest_vfs.write_text("project://docs/README.md", "blocked"),
            ErrorCode.READONLY_VIOLATION,
        )

        gi_uri = SemanticUri.parse("project://.gitignore")
        kernel_vfs.write_text(gi_uri, "# Custom user header\nnode_modules/\n*.user\n")
        materializer = GitignoreMaterializer(reg_restarted, kernel_vfs)
        first_sync = materializer.sync()
        check(isinstance(first_sync, GitignoreSyncResult) and first_sync.changed is True)
        check(list(first_sync.groups.keys()) == ["core", "agents-workflow", "project"])
        check("/plans/scratch/" in first_sync.groups["agents-workflow"])
        check("/plans/*.draft.md" in first_sync.groups["agents-workflow"])
        check("!plans/scratch/keep.draft.md" in first_sync.groups["agents-workflow"])
        check("!dist/public.js" in first_sync.groups["project"])

        synced_text = kernel_vfs.read_text(gi_uri)
        check("# Custom user header\nnode_modules/\n*.user" in synced_text)
        check(synced_text.index("# [core]") < synced_text.index("# [agents-workflow]") < synced_text.index("# [project]"))

        stat_before_noop = kernel_vfs.stat(gi_uri)
        second_sync = materializer.sync()
        stat_after_noop = kernel_vfs.stat(gi_uri)
        check(second_sync.changed is False, "Second identical GitignoreMaterializer.sync() must report changed=False")
        check(
            stat_before_noop.mtime_ns == stat_after_noop.mtime_ns and stat_before_noop.ino == stat_after_noop.ino,
            "Zero-Touch invariant violated: identical .gitignore must not be rewritten",
        )

        check(reg_restarted.remove_dynamic_space(aw_mod, "nonexistent") is False)
        dep_base = SpaceSpec(
            space_id=SpaceId("agents-workflow", "shared_base"),
            entries=(SemanticUri.parse("project://docs"),),
            include=("*.md",),
            watch=False,
        )
        check(reg_restarted.set_dynamic_space(aw_mod, "shared_base", dep_base) is True)
        dep_overlay = reg_restarted.with_overlay(
            (
                SpaceSpec(
                    space_id=SpaceId("project", "needs_shared"),
                    entries=(SemanticUri.parse("project://docs"),),
                    presets=("agents-workflow/shared_base",),
                ),
            )
        )
        expect_yscb_code(
            lambda: dep_overlay.remove_dynamic_space(aw_mod, "shared_base"),
            ErrorCode.SPACE_NOT_FOUND,
        )
        check(
            reg_restarted.get_space("agents-workflow/shared_base") == dep_base,
            "Failed remove_dynamic_space must keep SQLite and in-memory SpaceRegistry atomic",
        )
        check(reg_restarted.remove_dynamic_space(aw_mod, "shared_base") is True)

        name_exempt_reg = reg_restarted.with_overlay(
            (
                SpaceSpec(
                    space_id=SpaceId("custom", "drop_build_keep_name"),
                    entries=(SemanticUri.parse("project://logs"),),
                    include=("build/",),
                    exclude=("keep.txt",),
                ),
                SpaceSpec(
                    space_id=SpaceId("project", "logs_name_exempt"),
                    entries=(SemanticUri.parse("project://logs"),),
                    include=("*",),
                    presets=("!custom/drop_build_keep_name",),
                ),
            )
        )
        name_exempt_rels = tuple(str(f.rel_path) for f in name_exempt_reg.iter_files("project/logs_name_exempt"))
        check(
            "logs/build/keep.txt" in name_exempt_rels and "logs/build/sub/drop.txt" not in name_exempt_rels,
            f"Name-based exemption inside !<preset> falsely pruned directory: {name_exempt_rels}",
        )
        assert_raises_val_error(lambda: SpaceRegistry(guest_vfs, reopened_db))
        assert_raises_val_error(lambda: GitignoreMaterializer(reg_restarted, guest_vfs))

        ext_a = fx_spc.host_dir.path / "ext_a" / "m1"
        ext_b = fx_spc.host_dir.path / "ext_b" / "m1"
        (ext_a / "m1").mkdir(parents=True, exist_ok=True)
        ext_b.mkdir(parents=True, exist_ok=True)
        (ext_a / "dup.json").write_text('{"src":"a"}\n', encoding="utf-8")
        (ext_b / "dup.json").write_text('{"src":"b"}\n', encoding="utf-8")
        (ext_a / "m1" / "nested_only.txt").write_text("nested\n", encoding="utf-8")
        multi_ent_reg = reg_restarted.with_overlay(
            (
                SpaceSpec(
                    space_id=SpaceId("project", "multi_ext"),
                    entries=(SemanticUri.parse("yscb.host://ext_a/m1"), SemanticUri.parse("yscb.host://ext_b/m1")),
                    include=("*",),
                ),
            )
        )
        multi_entries = tuple(multi_ent_reg.iter_files("project/multi_ext"))
        dup_hits = [e for e in multi_entries if str(e.rel_path) == "m1/dup.json"]
        check(len(dup_hits) == 1 and dup_hits[0].abs_path == HostPath(ext_a / "dup.json"), f"Multi-entry dedup failed: {dup_hits}")
        check(multi_ent_reg.resolve_file_path("project/multi_ext", "m1/dup.json") == HostPath(ext_a / "dup.json"))
        expect_yscb_code(
            lambda: multi_ent_reg.resolve_file_path("project/multi_ext", "m1/nested_only.txt"),
            ErrorCode.SPACE_NOT_FOUND,
        )
        (proj_dir / "docs" / "__pycache__").mkdir(parents=True, exist_ok=True)
        (proj_dir / "docs" / "__pycache__" / "cached.md").write_text("# cached\n", encoding="utf-8")
        check(
            not reg_restarted.match_path("mod-a/docs", HostPath(proj_dir / "docs" / "__pycache__" / "cached.md")).matched,
            "match_path must reject __pycache__ segments symmetrically with iter_files",
        )
        alias_plan = fx_spc.project_root.path / "plans" / "self_move.md" if fx_spc.project_root is not None else None
        if alias_plan is not None:
            alias_plan.parent.mkdir(parents=True, exist_ok=True)
            alias_plan.write_text("keep_me\n", encoding="utf-8")
            kernel_vfs.move("project://plans/self_move.md", "project://plans/self_move.md")
            check(alias_plan.is_file(), "Self-move must not delete target file")
            assert_raises_val_error(lambda: kernel_vfs.move("project://plans", "project://plans/sub_nested"))
        # Embedded scheme boundary & host control-plane carve-out when project_root overlaps host_dir
        expect_yscb_code(
            lambda: reg_restarted.set_dynamic_space(
                aw_mod,
                "bad_embed_kernel",
                SpaceSpec(
                    space_id=SpaceId("agents-workflow", "bad_embed_kernel"),
                    entries=(SemanticUri.parse("project://"),),
                    include=("yscb://.modules/**",),
                ),
            ),
            ErrorCode.ACCESS_DENIED,
        )
        expect_yscb_code(
            lambda: reg_restarted.set_dynamic_space(
                aw_mod,
                "bad_embed_foreign_cfg",
                SpaceSpec(
                    space_id=SpaceId("agents-workflow", "bad_embed_foreign_cfg"),
                    entries=(SemanticUri.parse("project://"),),
                    include=("config://other_mod/**",),
                ),
            ),
            ErrorCode.ACCESS_DENIED,
        )
        overlap_ws = suite_root / "space_overlap_host"
        overlap_ws.mkdir(parents=True, exist_ok=True)
        overlap_yscb = overlap_ws / ".yscb"
        for sub_n in ("config/core", ".config.local", "storage/core/space", ".storage.local/core/space", ".cache", ".modules", ".mirror", ".snapshots", ".build", ".venv"):
            (overlap_yscb / sub_n).mkdir(parents=True, exist_ok=True)
        (overlap_ws / "yscb.config.json").write_text('{"yscb_root": ".yscb"}\n', encoding="utf-8")
        (overlap_ws / "yscb.py").write_text("# launcher\n", encoding="utf-8")
        (overlap_ws / ".gitignore").write_text("# root gitignore\n", encoding="utf-8")
        (overlap_ws / ".git").mkdir(parents=True, exist_ok=True)
        (overlap_ws / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (overlap_ws / "app.py").write_text("x = 1\n", encoding="utf-8")
        overlap_mt = UriMountTable(
            build_standard_mount_rules(
                HostPath(overlap_ws),
                HostPath(overlap_yscb),
                project_root=HostPath(overlap_ws),
            )
        )
        overlap_hub = VfsHub(overlap_mt, readonly_policy=ReadonlyPolicy())
        overlap_kvfs = overlap_hub.for_kernel()
        with ModuleDatabase(overlap_kvfs, "storage.local://core/space/state.db") as ov_db:
            ov_reg = SpaceRegistry(
                overlap_kvfs,
                ov_db,
                static_specs=(
                    SpaceSpec(
                        space_id=SpaceId("rogue", "readonly"),
                        entries=(SemanticUri.parse("project://"),),
                        include=("*",),
                        watch=False,
                    ),
                    SpaceSpec(
                        space_id=SpaceId("rogue", "gitignore"),
                        entries=(SemanticUri.parse("project://"),),
                        include=("yscb.config.json", "yscb.py", "yscb://.modules/", "config://other/secret.json", "build_out/"),
                        watch=False,
                    ),
                ),
            )
            rogue_ro_rels = {str(e.rel_path) for e in ov_reg.iter_files("rogue/readonly")}
            check("app.py" in rogue_ro_rels, f"Expected business file in rogue/readonly: {rogue_ro_rels}")
            for protected_rel in ("yscb.config.json", "yscb.py", ".gitignore"):
                check(protected_rel not in rogue_ro_rels, f"Control-plane file {protected_rel} leaked into non-core space!")
                check(
                    not ov_reg.match_path("rogue/readonly", HostPath(overlap_ws / protected_rel)).matched,
                    f"match_path must exclude {protected_rel} for non-core spaces",
                )
            check(
                not any(r.startswith((".yscb/", ".git/")) for r in rogue_ro_rels),
                f".yscb or .git leaked into non-core space: {rogue_ro_rels}",
            )
            ov_gi = GitignoreMaterializer(ov_reg, overlap_kvfs).sync()
            rogue_gi_pats = ov_gi.groups.get("rogue", ())
            check(rogue_gi_pats == ("build_out/",), f"Expected rogue gitignore carve-out to leave only build_out/, got {rogue_gi_pats}")

        cleared_cnt = reg_restarted.clear_dynamic_spaces(aw_mod)
        check(cleared_cnt == 2, f"Expected 2 dynamic spaces cleared, got {cleared_cnt}")
        third_sync = materializer.sync()
        check(third_sync.changed is True and "agents-workflow" not in third_sync.groups)
        check("# [agents-workflow]" not in kernel_vfs.read_text(gi_uri))
        check("# Custom user header" in kernel_vfs.read_text(gi_uri))


def _verify_space_scanner_policies_racy_clean_and_cursors(suite_root: Path) -> None:
    ws_scan = suite_root / "space_scanner"
    fx_scan = _provision_vfs_hub(ws_scan, with_project=True)
    hub = fx_scan.hub
    proj_hp = fx_scan.project_root
    check(proj_hp is not None)
    if proj_hp is None:
        return
    proj_dir = proj_hp.path
    kernel_vfs = hub.for_kernel()

    code_dir = proj_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    small_py = code_dir / "small.py"
    large_bin = code_dir / "large_asset.py"
    gen_py = code_dir / "schema.generated.py"

    small_payload = b"x = 42\n"
    large_payload = (b"H" * 65536) + (b"M" * 200000) + (b"T" * 65536)
    check(len(large_payload) > 256 * 1024)
    atomic_write_bytes(HostPath(small_py), small_payload)
    atomic_write_bytes(HostPath(large_bin), large_payload)
    atomic_write_bytes(HostPath(gen_py), b"GENERATED = 1\n")

    adapt_spec = SpaceSpec(
        space_id=SpaceId("project", "code_adapt"),
        entries=(SemanticUri.parse("project://code"),),
        include=("*.py",),
        hash_policy=HashPolicy.ADAPTIVE,
    )
    full_spec = SpaceSpec(
        space_id=SpaceId("project", "code_full"),
        entries=(SemanticUri.parse("project://code"),),
        include=("*.py",),
        hash_policy=HashPolicy.FULL_HASH,
    )
    stat_spec = SpaceSpec(
        space_id=SpaceId("project", "code_stat"),
        entries=(SemanticUri.parse("project://code"),),
        include=("*.py",),
        hash_policy=HashPolicy.STAT_ONLY,
    )

    with ModuleDatabase(kernel_vfs, "storage.local://core/space/state.db") as state_db:
        reg = SpaceRegistry(kernel_vfs, state_db, static_specs=(adapt_spec, full_spec, stat_spec))
        adapt_entries = {str(e.rel_path): e for e in reg.iter_files("project/code_adapt")}
        full_entries = {str(e.rel_path): e for e in reg.iter_files("project/code_full")}
        stat_entries = {str(e.rel_path): e for e in reg.iter_files("project/code_stat")}

        check(isinstance(adapt_entries["code/small.py"], SpaceFileEntry))
        check(
            adapt_entries["code/small.py"].content_hash == full_entries["code/small.py"].content_hash,
            "ADAPTIVE <= 256 KiB must match FULL_HASH Blake2b-128 digest",
        )
        check(
            adapt_entries["code/large_asset.py"].content_hash != full_entries["code/large_asset.py"].content_hash,
            "ADAPTIVE > 256 KiB sparse sample digest must use domain-separated head/middle/tail sampling",
        )
        check(len(stat_entries["code/small.py"].content_hash) == 32)

        scanner = SpaceScanner(reg, state_db)
        init_status = scanner.status("project/code_adapt")
        check(isinstance(init_status, SpaceStatusSnapshot) and init_status.generation == SnapshotGen(0))

        batch_initial = scanner.scan("project/code_adapt")
        check(
            isinstance(batch_initial, SpaceDiffBatch)
            and batch_initial.from_gen == SnapshotGen(0)
            and batch_initial.to_gen == SnapshotGen(1)
            and batch_initial.has_changes
            and len(batch_initial.added) == 3
        )
        batch_noop = scanner.scan("project/code_adapt")
        check((not batch_noop.has_changes) and batch_noop.to_gen == SnapshotGen(1))

        racy_file = code_dir / "racy.py"
        racy_file.write_bytes(b"alpha_1")
        batch_racy_add = scanner.scan("project/code_adapt")
        check(batch_racy_add.to_gen == SnapshotGen(2) and SpacePath("code/racy.py") in batch_racy_add.added)
        def _pin_racy_mtime_to_snapshot(target_file: Path) -> int:
            for _ in range(3):
                with state_db.read_snapshot() as cur_snap:
                    ts_row = cur_snap.query_one(
                        "SELECT updated_at_ns FROM space_snapshots WHERE target_key = ?",
                        ("project/code_adapt",),
                    )
                check(ts_row is not None and type(ts_row[0]) is int)
                snap_ts = int(ts_row[0]) if ts_row is not None and type(ts_row[0]) is int else 0
                os.utime(target_file, ns=(snap_ts, snap_ts))
                actual_mt = int(target_file.stat().st_mtime_ns)
                _ = scanner.scan("project/code_adapt")
                with state_db.read_snapshot() as post_snap:
                    post_row = post_snap.query_one(
                        "SELECT updated_at_ns FROM space_snapshots WHERE target_key = ?",
                        ("project/code_adapt",),
                    )
                post_ts = int(post_row[0]) if post_row is not None and type(post_row[0]) is int else 0
                if actual_mt >= post_ts - 10_000_000:
                    return actual_mt
            raise AssertionError("Failed to pin target file mtime inside snapshot Racy-Clean window")

        pinned_racy_ns = _pin_racy_mtime_to_snapshot(racy_file)

        racy_file.write_bytes(b"bravo_2")
        os.utime(racy_file, ns=(pinned_racy_ns, pinned_racy_ns))
        batch_racy_mod = scanner.scan("project/code_adapt")
        check(
            batch_racy_mod.to_gen == SnapshotGen(3) and batch_racy_mod.modified == (SpacePath("code/racy.py"),),
            f"Racy-Clean (<20ms) protection failed to detect same-mtime/same-size rewrite: {batch_racy_mod}",
        )

        with scanner.consume_diff("project/code_adapt", "ast") as ast_first:
            check(ast_first.from_gen == SnapshotGen(0) and ast_first.to_gen == SnapshotGen(3))
            check(len(ast_first.added) == 4 and not ast_first.modified and not ast_first.deleted)

        extra_py = code_dir / "patched.py"
        atomic_write_bytes(HostPath(extra_py), b"patched = True\n")
        atomic_write_bytes(HostPath(small_py), b"x = 999\n")
        unwatched_spec = SpaceSpec(
            space_id=SpaceId("project", "code_unwatched"),
            entries=(SemanticUri.parse("project://code"),),
            include=("*.py",),
            watch=False,
            hash_policy=HashPolicy.STAT_ONLY,
        )
        reg.reload(static_specs=(adapt_spec, full_spec, stat_spec, unwatched_spec))
        _ = scanner.scan("project/code_unwatched")
        patched_batches = scanner.patch_paths(frozenset({HostPath(extra_py), HostPath(small_py)}))
        patched_ids = {b.space_id for b in patched_batches}
        check(
            SpaceId("project", "code_full") in patched_ids,
            f"Unscanned watch=True space missed by patch_paths: {patched_ids}",
        )
        check(
            SpaceId("project", "code_unwatched") not in patched_ids,
            f"watch=False space must not be mutated by patch_paths: {patched_ids}",
        )
        adapt_patch = next(b for b in patched_batches if b.space_id == SpaceId("project", "code_adapt"))
        new_sub_pkg = code_dir / "moved_pkg"
        new_sub_pkg.mkdir(parents=True, exist_ok=True)
        (new_sub_pkg / "fresh_mod.py").write_text("fresh = 1\n", encoding="utf-8")
        dir_batches = scanner.patch_paths(frozenset({HostPath(new_sub_pkg)}))
        adapt_dir_patch = next(b for b in dir_batches if b.space_id == SpaceId("project", "code_adapt"))
        check(
            SpacePath("code/moved_pkg/fresh_mod.py") in adapt_dir_patch.added,
            f"Directory-level patch_paths missed newly created *.py subdirectory: {adapt_dir_patch}",
        )
        check(adapt_patch.from_gen == SnapshotGen(3) and adapt_patch.to_gen == SnapshotGen(4))
        check(adapt_patch.added == (SpacePath("code/patched.py"),))
        check(adapt_patch.modified == (SpacePath("code/small.py"),))
        check(adapt_patch.dirty_files == (SpacePath("code/patched.py"), SpacePath("code/small.py")))

        ast_delta = scanner.diff("project/code_adapt", "ast")
        check(
            ast_delta.from_gen == SnapshotGen(3)
            and ast_delta.to_gen == SnapshotGen(5)
            and ast_delta.added == (SpacePath("code/moved_pkg/fresh_mod.py"), SpacePath("code/patched.py"))
            and ast_delta.modified == (SpacePath("code/small.py"),)
        )
        kdb_full_delta = scanner.diff("project/code_adapt", "kdb")
        check(kdb_full_delta.from_gen == SnapshotGen(0) and kdb_full_delta.to_gen == SnapshotGen(5))
        check(len(kdb_full_delta.added) == 6)

        caught_consumer_err = False
        try:
            with scanner.consume_diff("project/code_adapt", "kdb") as _failing_batch:
                raise RuntimeError("simulated downstream consumer failure")
        except RuntimeError:
            caught_consumer_err = True
        check(caught_consumer_err)

        status_after_fail = scanner.status("project/code_adapt")
        cursor_ids = tuple(c.consumer_id for c in status_after_fail.cursors)
        check(cursor_ids == ("ast",), f"Failed consume_diff must not persist kdb cursor: {status_after_fail.cursors}")
        check(isinstance(status_after_fail.cursors[0], ConsumerCursor))

        check(scanner.ack_cursor("project/code_adapt", "ast", ast_delta) is True)
        check(scanner.ack_cursor("project/code_adapt", "kdb", kdb_full_delta) is True)

        db_gen_before_short = state_db.committed_gen()
        check(
            scanner.ack_cursor("project/code_adapt", "kdb", kdb_full_delta) is False,
            "Unchanged ack_cursor must short-circuit via SnapshotReader and return False",
        )
        check(state_db.committed_gen() == db_gen_before_short)

        narrowed_adapt = SpaceSpec(
            space_id=SpaceId("project", "code_adapt"),
            entries=(SemanticUri.parse("project://code"),),
            include=("*.py",),
            exclude=("*.generated.py",),
            hash_policy=HashPolicy.ADAPTIVE,
        )
        reg.reload(static_specs=(narrowed_adapt, full_spec, stat_spec, unwatched_spec))
        cfg_del_batch = scanner.scan("project/code_adapt")
        check(
            cfg_del_batch.to_gen == SnapshotGen(6)
            and cfg_del_batch.deleted == (SpacePath("code/schema.generated.py"),),
            f"Config hash change must emit newly excluded files as deleted: {cfg_del_batch}",
        )
        ast_del_diff = scanner.diff("project/code_adapt", "ast")
        check(ast_del_diff.deleted == (SpacePath("code/schema.generated.py"),))

        pre_cancelled = CancellationToken()
        pre_cancelled.cancel(reason="abort_scan")
        caught_scan_cancel = False
        try:
            _ = scanner.scan("project/code_adapt", force=True, cancel_token=pre_cancelled)
        except TaskCancelledException:
            caught_scan_cancel = True
        check(caught_scan_cancel, "Pre-cancelled scan must raise TaskCancelledException")

        stale_old_batch = SpaceDiffBatch(
            space_id=SpaceId("project", "code_adapt"),
            from_gen=SnapshotGen(0),
            to_gen=SnapshotGen(1),
            config_hash=cfg_del_batch.config_hash,
            merkle_root="stale",
        )
        check(
            scanner.ack_cursor("project/code_adapt", "ast", stale_old_batch) is False,
            "Monotonic ack_cursor guard must reject stale lower-generation batch",
        )
        with scanner.consume_diff("project/code_adapt", "fresh_slow") as slow_b1:
            check(slow_b1.from_gen == SnapshotGen(0) and slow_b1.to_gen == SnapshotGen(6))
            late_py = code_dir / "late_during_inflight.py"
            late_py.write_text("late = 1\n", encoding="utf-8")
            _ = scanner.scan("project/code_adapt")
            with scanner.consume_diff("project/code_adapt", "ast") as fast_ast:
                check(fast_ast.to_gen == SnapshotGen(7))
        slow_b2 = scanner.diff("project/code_adapt", "fresh_slow")
        check(
            slow_b2.from_gen == SnapshotGen(6)
            and slow_b2.to_gen == SnapshotGen(7)
            and slow_b2.added == (SpacePath("code/late_during_inflight.py"),),
            f"In-flight consumer lost intermediate change log during fast peer ack: {slow_b2}",
        )

        removed_kdb = scanner.clean("project/code_adapt", consumer_id="kdb")
        check(removed_kdb == 1)

        inflight_pre_clean = scanner.diff("project/code_adapt", "stale_inflight")
        check(inflight_pre_clean.to_gen == SnapshotGen(7))
        removed_space = scanner.clean("project/code_adapt")
        check(removed_space >= 1 and scanner.status("project/code_adapt").generation == SnapshotGen(0))

        rebuilt_after_clean = scanner.scan("project/code_adapt")
        check(
            rebuilt_after_clean.from_gen == SnapshotGen(0)
            and rebuilt_after_clean.to_gen == SnapshotGen(8),
            f"clean() must preserve monotonic generation floor across rebuild: {rebuilt_after_clean}",
        )
        check(
            scanner.ack_cursor("project/code_adapt", "stale_inflight", inflight_pre_clean) is False,
            "Stale pre-clean batch must be rejected by ack_cursor after clean()",
        )
        post_clean_py = code_dir / "post_clean_delta.py"
        post_clean_py.write_text("post_clean = True\n", encoding="utf-8")
        post_clean_scan = scanner.scan("project/code_adapt")
        check(post_clean_scan.to_gen == SnapshotGen(9))
        fresh_diff_after_clean = scanner.diff("project/code_adapt", "stale_inflight")
        check(
            fresh_diff_after_clean.from_gen == SnapshotGen(0)
            and fresh_diff_after_clean.to_gen == SnapshotGen(9)
            and SpacePath("code/post_clean_delta.py") in fresh_diff_after_clean.added,
            f"Post-clean diff lost delta: {fresh_diff_after_clean}",
        )

        neg_non_py = SpaceSpec(
            space_id=SpaceId("project", "neg_non_py"),
            entries=(SemanticUri.parse("project://code"),),
            include=("*",),
            exclude=("*.py",),
        )
        composed_code = SpaceSpec(
            space_id=SpaceId("project", "composed_code"),
            entries=(SemanticUri.parse("project://code"),),
            include=("*",),
            compose=("!project/neg_non_py",),
        )
        single_file_spec = SpaceSpec(
            space_id=SpaceId("project", "single_entry_doc"),
            entries=(SemanticUri.parse("project://code/small.py"),),
            include=("*",),
        )
        host_anc_spec = SpaceSpec(
            space_id=SpaceId("project", "host_ancestor_view"),
            entries=(SemanticUri.parse("yscb.host://"),),
            include=("code/small.py",),
        )
        reg.reload(static_specs=(narrowed_adapt, full_spec, stat_spec, unwatched_spec, neg_non_py, composed_code, single_file_spec, host_anc_spec))
        check(
            reg.resolve_file_path("project/single_entry_doc", "code/small.py") == HostPath(small_py),
            "Single-file entry inside project subdirectory failed resolve_file_path symmetry",
        )
        check(
            reg.resolve_file_path("project/host_ancestor_view", "code/small.py") == HostPath(small_py),
            "Ancestor directory entry above project_root failed resolve_file_path symmetry",
        )
        check(
            reg.match_path("core/workspace", HostPath(fx_scan.yscb_root.path / ".modules")).matched is False,
            "URI coordinate wildcard yscb://.modules/** must exclude .modules root directory itself",
        )
        _ = scanner.scan("project/composed_code")
        neg_comp_sub = code_dir / "neg_comp_dir"
        neg_comp_sub.mkdir(parents=True, exist_ok=True)
        (neg_comp_sub / "kept_inside.py").write_text("kept = 1\n", encoding="utf-8")
        (neg_comp_sub / "ignored_note.txt").write_text("ignored\n", encoding="utf-8")
        comp_dir_batches = scanner.patch_paths(frozenset({HostPath(neg_comp_sub)}))
        comp_patch = next((b for b in comp_dir_batches if b.space_id == SpaceId("project", "composed_code")), None)
        check(
            comp_patch is not None
            and comp_patch.added == (SpacePath("code/neg_comp_dir/kept_inside.py"),),
            f"patch_paths missed new subdir on space with negative compose: {comp_dir_batches}",
        )

        racy_cross_a = code_dir / "cross_racy_a.py"
        racy_cross_b = code_dir / "cross_racy_b.py"
        racy_cross_a.write_bytes(b"cross_1")
        racy_cross_b.write_bytes(b"other_1")
        _ = scanner.scan("project/code_adapt")
        cr_ts = _pin_racy_mtime_to_snapshot(racy_cross_a)
        racy_cross_a.write_bytes(b"cross_2")
        os.utime(racy_cross_a, ns=(cr_ts, cr_ts))
        time.sleep(0.025)
        racy_cross_b.write_bytes(b"other_2_updated")
        _ = scanner.patch_paths(frozenset({HostPath(racy_cross_b)}))
        cross_inc_batch = scanner.scan("project/code_adapt")
        check(
            SpacePath("code/cross_racy_a.py") in cross_inc_batch.modified,
            f"Single-file patch_paths clobbered Racy-Clean updated_at_ns for untouched file: {cross_inc_batch}",
        )
        check(
            scanner.ack_cursor("project/code_adapt", "brand_new_consumer", cross_inc_batch) is False,
            "ack_cursor must reject non-contiguous single-step scan batch for uninitialized consumer",
        )

        ext_nested_root = fx_scan.host_dir.path / "ext_nested"
        (ext_nested_root / "sub").mkdir(parents=True, exist_ok=True)
        (ext_nested_root / "sub" / "cfg.json").write_text('{"ok":1}\n', encoding="utf-8")
        (ext_nested_root / "sub" / "cfg.yaml").write_text("ok: 1\n", encoding="utf-8")
        ext_dup_one = fx_scan.host_dir.path / "dup_one" / "pkg"
        ext_dup_two = fx_scan.host_dir.path / "dup_two" / "pkg"
        ext_dup_one.mkdir(parents=True, exist_ok=True)
        ext_dup_two.mkdir(parents=True, exist_ok=True)
        (ext_dup_one / "shared.py").write_text("one = 1\n", encoding="utf-8")
        (ext_dup_two / "shared.py").write_text("two = 2\n", encoding="utf-8")

        mod_a_cache_gen = fx_scan.yscb_root.path / ".cache" / "mod-a" / "gen"
        mod_a_cache_gen.mkdir(parents=True, exist_ok=True)
        gen_art = mod_a_cache_gen / "out.json"
        gen_art.write_text('{"gen":true}\n', encoding="utf-8")

        sp_ext_parent = SpaceSpec(
            space_id=SpaceId("mod-a", "assets"),
            entries=(SemanticUri.parse("yscb.host://ext_nested"),),
            include=("*.json",),
        )
        sp_ext_child = SpaceSpec(
            space_id=SpaceId("mod-b", "assets"),
            entries=(SemanticUri.parse("yscb.host://ext_nested/sub"),),
            include=("*.yaml",),
        )
        sp_dup_first = SpaceSpec(
            space_id=SpaceId("mod-a", "dup_src"),
            entries=(SemanticUri.parse("yscb.host://dup_one/pkg"),),
            include=("*.py",),
        )
        sp_dup_second = SpaceSpec(
            space_id=SpaceId("mod-b", "dup_src"),
            entries=(SemanticUri.parse("yscb.host://dup_two/pkg"),),
            include=("*.py",),
        )
        sp_dup_merged = SpaceSpec(
            space_id=SpaceId("project", "dup_merged"),
            entries=(),
            compose=("mod-a/dup_src", "mod-b/dup_src", "!mod-a/dup_src"),
        )
        sp_preset_leaf = SpaceSpec(
            space_id=SpaceId("mod-a", "gen_preset"),
            entries=(),
            include=("cache://@/gen/**",),
        )
        sp_preset_mid = SpaceSpec(
            space_id=SpaceId("mod-b", "mid_preset"),
            entries=(),
            presets=("mod-a/gen_preset",),
        )
        sp_preset_consumer = SpaceSpec(
            space_id=SpaceId("project", "all_gen"),
            entries=(SemanticUri.parse("cache://mod-a"),),
            presets=("mod-b/mid_preset",),
        )
        reg.reload(
            static_specs=(
                narrowed_adapt,
                sp_ext_parent,
                sp_ext_child,
                sp_dup_first,
                sp_dup_second,
                sp_dup_merged,
                sp_preset_leaf,
                sp_preset_mid,
                sp_preset_consumer,
            )
        )
        asset_rels = tuple(e.rel_path for e in reg.iter_files("/assets"))
        for a_rel in asset_rels:
            resolved_asset = reg.resolve_file_path("/assets", a_rel)
            check(resolved_asset.path.is_file(), f"Composed space resolve_file_path symmetry failed for {a_rel}")
        dup_merged_entries = tuple(reg.iter_files("project/dup_merged"))
        check(
            len(dup_merged_entries) == 1
            and dup_merged_entries[0].abs_path == HostPath(ext_dup_two / "shared.py")
            and reg.resolve_file_path("project/dup_merged", "pkg/shared.py") == HostPath(ext_dup_two / "shared.py"),
            f"Post-neg_compose deduplication failed to retain second member candidate: {dup_merged_entries}",
        )
        gen_explain = reg.match_path("project/all_gen", HostPath(gen_art))
        check(
            gen_explain.matched and gen_explain.source_space == SpaceId("mod-a", "gen_preset"),
            f"Multi-hop preset inheritance lost original '@/ ' owner or source_space: {gen_explain}",
        )
        if os.name != "nt":
            sym_in_code = code_dir / "sym_probe.py"
            os.symlink(small_py, sym_in_code)
            fifo_in_code = code_dir / "fifo_probe.py"
            os.mkfifo(fifo_in_code, 0o600)
            try:
                sym_exp = reg.match_path("project/code_adapt", SemanticUri.parse("project://code/sym_probe.py"))
                check(
                    (not sym_exp.matched) and sym_exp.reason == "symlink_rejected",
                    f"SemanticUri symlink must return symlink_rejected instead of raising: {sym_exp}",
                )
                fifo_exp = reg.match_path("project/code_adapt", HostPath(fifo_in_code))
                check(
                    (not fifo_exp.matched) and fifo_exp.reason == "non_regular_file",
                    f"Existing FIFO node must not match file space: {fifo_exp}",
                )
            finally:
                sym_in_code.unlink(missing_ok=True)
                fifo_in_code.unlink(missing_ok=True)



def _verify_cross_mount_boundaries_and_space_algebra_invariants(suite_root: Path) -> None:
    inv_root = suite_root / "invariants_suite"
    inv_host = inv_root / "repo"
    inv_yscb = inv_host / ".yscb"
    inv_host.mkdir(parents=True, exist_ok=True)
    inv_yscb.mkdir(parents=True, exist_ok=True)

    for bad_scheme in ("1bad", "a..b", "_lead", "-lead", ".lead", "trail.", "Upper"):
        assert_raises_val_error(lambda s=bad_scheme: MountRule(scheme=s))
        assert_raises_val_error(
            lambda s=bad_scheme: PhysicalDirectoryProvider(
                s, HostPath(inv_host), base_capabilities=VfsCapabilities.READABLE
            )
        )
        assert_raises_val_error(lambda s=bad_scheme: MemoryVfsProvider(s))

    ro_phys_dir = inv_root / "ro_phys"
    ro_phys_dir.mkdir(parents=True, exist_ok=True)
    (ro_phys_dir / "seed.txt").write_text("seed", encoding="utf-8")
    ro_phys = PhysicalDirectoryProvider(
        "vendor.ro",
        HostPath(ro_phys_dir),
        base_capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    expect_yscb_code(
        lambda: ro_phys.write_bytes_atomic(SemanticUri.parse("vendor.ro://new.txt"), b"x"),
        ErrorCode.READONLY_VIOLATION,
    )
    expect_yscb_code(lambda: ro_phys.delete(SemanticUri.parse("vendor.ro://seed.txt")), ErrorCode.READONLY_VIOLATION)
    expect_yscb_code(
        lambda: ro_phys.move(SemanticUri.parse("vendor.ro://seed.txt"), SemanticUri.parse("vendor.ro://moved.txt")),
        ErrorCode.READONLY_VIOLATION,
    )
    expect_yscb_code(lambda: ro_phys.mkdir(SemanticUri.parse("vendor.ro://sub")), ErrorCode.READONLY_VIOLATION)

    shared_store_alias = MountRule(
        scheme="shared.store",
        target_uri=SemanticUri.parse("storage://shared_pool"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    plans_alias = MountRule(
        scheme="workflow.plans",
        target_uri=SemanticUri.parse("project://plans"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    nested_ro_mount_dir = inv_host / "vendor_locked"
    nested_ro_mount_dir.mkdir(parents=True, exist_ok=True)
    nested_ro_rule = MountRule(
        scheme="vendor.locked",
        target_path=HostPath(nested_ro_mount_dir),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    std_rules = build_standard_mount_rules(
        HostPath(inv_host),
        HostPath(inv_yscb),
        project_root=HostPath(inv_host),
        extra_rules=(shared_store_alias, plans_alias, nested_ro_rule),
    )
    colocated_hub = VfsHub(
        UriMountTable(std_rules),
        echo_guard=VfsEchoGuard(ttl_sec=10.0, max_entries=2048),
        access_policy=AccessPolicy(
            extra_writable_schemes={ModuleId("mod-a"): frozenset({"shared.store", "workflow.plans"})}
        ),
    )
    kern = colocated_hub.for_kernel()
    mod_a = colocated_hub.for_module(ModuleId("mod-a"))
    mod_b = colocated_hub.for_module(ModuleId("mod-b"))

    kern.write_text("module://mod-a/entry.py", "kernel_owned = True\n")
    kern.write_text("storage://mod-b/secret.json", '{"owner":"mod-b"}\n')
    kern.write_text("config://core/settings.json", '{"k":1}\n')
    kern.write_text("vendor.locked://pinned.txt", "locked\n")

    expect_yscb_code(
        lambda: mod_a.write_text("project://.yscb/.modules/mod-a/entry.py", "tamper"),
        ErrorCode.ACCESS_DENIED,
    )
    expect_yscb_code(
        lambda: mod_a.write_text("project://.yscb/storage/mod-b/secret.json", "tamper"),
        ErrorCode.ACCESS_DENIED,
    )
    expect_yscb_code(
        lambda: mod_a.write_text("project://.yscb/config/core/settings.json", "tamper"),
        ErrorCode.ACCESS_DENIED,
    )
    expect_yscb_code(
        lambda: mod_a.write_text("project://vendor_locked/pinned.txt", "tamper"),
        ErrorCode.READONLY_VIOLATION,
    )
    expect_yscb_code(
        lambda: mod_a.delete("project://.yscb", recursive=True),
        ErrorCode.ACCESS_DENIED,
    )
    mod_a.write_text("project://.yscb/storage/mod-a/own_ok.txt", "allowed\n")
    check(mod_a.read_text("storage://@/own_ok.txt") == "allowed\n")

    mod_a.write_text("shared.store://doc.txt", "pool_ok\n")
    check(kern.read_text("storage://shared_pool/doc.txt") == "pool_ok\n")
    expect_yscb_code(lambda: mod_b.write_text("shared.store://doc.txt", "denied"), ErrorCode.ACCESS_DENIED)

    mod_a.mkdir("workflow.plans://")
    expect_yscb_code(lambda: mod_a.write_text("workflow.plans://", "root_write"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: kern.write_text("workflow.plans://", "root_write"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.delete("workflow.plans://"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: kern.delete("workflow.plans://", recursive=True), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.move("project://", "project://"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.move("workflow.plans://", "workflow.plans://"), ErrorCode.ACCESS_DENIED)

    mod_a.write_text("project://dir_echo/sub/leaf.txt", "echo_payload\n")
    leaf_src_hp = HostPath(inv_host / "dir_echo" / "sub" / "leaf.txt")
    mod_a.move("project://dir_echo", "project://dir_moved")
    leaf_dst_hp = HostPath(inv_host / "dir_moved" / "sub" / "leaf.txt")
    leaf_dst_st = os.lstat(str(leaf_dst_hp))
    check(
        colocated_hub.echo_guard.is_suppressed(leaf_src_hp, -1, -1, -1),
        "Directory move must record tombstone echo for nested regular files at source",
    )
    check(
        colocated_hub.echo_guard.is_suppressed(
            leaf_dst_hp,
            int(leaf_dst_st.st_mtime_ns),
            int(leaf_dst_st.st_size),
            int(leaf_dst_st.st_ino),
        ),
        "Directory move must record post-move stat echo for nested regular files at destination",
    )
    check(mod_a.delete("project://dir_moved", recursive=True))
    check(
        colocated_hub.echo_guard.is_suppressed(leaf_dst_hp, -1, -1, -1),
        "Recursive directory delete must record tombstone echo for nested regular files",
    )

    ext_root = inv_root / "ext_watch_src"
    (ext_root / "pkg" / "deep").mkdir(parents=True, exist_ok=True)
    (ext_root / "root_readme.md").write_text("root_doc\n", encoding="utf-8")
    (ext_root / "pkg" / "top.py").write_text("top = 1\n", encoding="utf-8")
    (ext_root / "pkg" / "deep" / "nested.py").write_text("nested = 1\n", encoding="utf-8")
    (ext_root / "gen" / "unit").mkdir(parents=True, exist_ok=True)
    (ext_root / "gen" / "unit" / "out").write_text("regular_file_not_dir\n", encoding="utf-8")
    (ext_root / "gen" / "real" / "out").mkdir(parents=True, exist_ok=True)
    (ext_root / "gen" / "real" / "out" / "artifact.json").write_text("{}\n", encoding="utf-8")
    (ext_root / "demorgan" / "sub").mkdir(parents=True, exist_ok=True)
    (ext_root / "demorgan" / "sub" / "a.keep.py").write_text("keep = 1\n", encoding="utf-8")
    (ext_root / "demorgan" / "sub" / "b.drop.py").write_text("drop = 1\n", encoding="utf-8")

    ext_rule = MountRule(
        scheme="ext.src",
        target_path=HostPath(ext_root),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    sp_hub = VfsHub(
        UriMountTable(
            build_standard_mount_rules(
                HostPath(inv_host),
                HostPath(inv_yscb),
                project_root=HostPath(inv_host),
                extra_rules=(ext_rule,),
            )
        )
    )
    sp_kern = sp_hub.for_kernel()

    seg_glob_spec = SpaceSpec(
        space_id=SpaceId("project", "seg_glob"),
        entries=(SemanticUri.parse("ext.src://"),),
        include=("pkg/*.py", "gen/*/out/**"),
        watch=False,
    )
    preset_keep = SpaceSpec(
        space_id=SpaceId("mod-a", "keep_py"),
        include=("*.keep.py",),
    )
    preset_drop_py = SpaceSpec(
        space_id=SpaceId("mod-a", "drop_py_except_keep"),
        include=("sub/**",),
        presets=("!mod-a/keep_py",),
    )
    demorgan_consumer = SpaceSpec(
        space_id=SpaceId("project", "demorgan_space"),
        entries=(SemanticUri.parse("ext.src://demorgan"),),
        include=("*",),
        presets=("!mod-a/drop_py_except_keep",),
        watch=False,
    )
    multi_path_a = SpaceSpec(
        space_id=SpaceId("mod-a", "view_outer"),
        entries=(SemanticUri.parse("ext.src://"),),
        include=("pkg/top.py",),
        watch=False,
    )
    multi_path_b = SpaceSpec(
        space_id=SpaceId("mod-b", "view_inner"),
        entries=(SemanticUri.parse("ext.src://pkg"),),
        include=("top.py",),
        watch=True,
    )
    multi_union = SpaceSpec(
        space_id=SpaceId("project", "multi_view_union"),
        compose=("mod-a/view_outer", "mod-b/view_inner"),
        watch=True,
    )

    with ModuleDatabase(sp_kern, "storage.local://core/space/inv_state.db") as sp_db:
        sp_reg = SpaceRegistry(
            sp_kern,
            sp_db,
            static_specs=(
                seg_glob_spec,
                preset_keep,
                preset_drop_py,
                demorgan_consumer,
                multi_path_a,
                multi_path_b,
                multi_union,
            ),
        )
        seg_files = {str(e.rel_path) for e in sp_reg.iter_files("project/seg_glob")}
        check(
            "ext_watch_src/pkg/top.py" in seg_files and "ext_watch_src/pkg/deep/nested.py" not in seg_files,
            f"Single-segment * glob must not cross directory separators: {seg_files}",
        )
        check(
            "ext_watch_src/gen/real/out/artifact.json" in seg_files
            and "ext_watch_src/gen/unit/out" not in seg_files,
            f"Trailing /** wildcard rule must enforce dir_only ancestor matching: {seg_files}",
        )

        dm_files = {str(e.rel_path) for e in sp_reg.iter_files("project/demorgan_space")}
        check(
            dm_files == {"demorgan/sub/a.keep.py"},
            f"Nested negated preset De Morgan evaluation failed: {dm_files}",
        )
        check(
            sp_reg.match_path("project/demorgan_space", HostPath(ext_root / "demorgan" / "sub" / "a.keep.py")).matched
            and not sp_reg.match_path(
                "project/demorgan_space", HostPath(ext_root / "demorgan" / "sub" / "b.drop.py")
            ).matched,
            "match_path disagreed with iter_files on nested negated presets",
        )

        union_rels = {str(e.rel_path) for e in sp_reg.iter_files("project/multi_view_union")}
        check(
            union_rels == {"ext_watch_src/pkg/top.py", "pkg/top.py"},
            f"Distinct SpacePaths for same physical file must both survive compose: {union_rels}",
        )
        for u_rel in union_rels:
            check(
                sp_reg.resolve_file_path("project/multi_view_union", u_rel) == HostPath(ext_root / "pkg" / "top.py"),
                f"resolve_file_path symmetry failed on multi-path union for {u_rel}",
            )

        watch_roots = sp_reg.collect_watch_roots()
        check(
            HostPath(ext_root) in watch_roots,
            f"collect_watch_roots missed unwatched space transitively composed into watched space: {watch_roots}",
        )

        top_only_spec = SpaceSpec(
            space_id=SpaceId("project", "top_level_only"),
            entries=(SemanticUri.parse("ext.src://"),),
            include=("*",),
            exclude=("*/",),
            watch=False,
        )
        subdirs_only_spec = SpaceSpec(
            space_id=SpaceId("project", "subdirs_only"),
            entries=(SemanticUri.parse("ext.src://"),),
            include=("*/",),
            watch=False,
        )
        sp_reg.reload(
            static_specs=(
                seg_glob_spec,
                preset_keep,
                preset_drop_py,
                demorgan_consumer,
                multi_path_a,
                multi_path_b,
                multi_union,
                top_only_spec,
                subdirs_only_spec,
            )
        )
        top_only_files = {str(e.rel_path) for e in sp_reg.iter_files("project/top_level_only")}
        check(
            top_only_files == {"ext_watch_src/root_readme.md"},
            f"Universal dir-only exclude ('*/') must keep root-level files without pruning entry root: {top_only_files}",
        )
        check(
            sp_reg.resolve_file_path("project/top_level_only", "ext_watch_src/root_readme.md")
            == HostPath(ext_root / "root_readme.md"),
            "resolve_file_path must match iter_files for top_level_only space",
        )
        sp_scanner = SpaceScanner(sp_reg, sp_db)
        top_scan_batch = sp_scanner.scan("project/top_level_only")
        check(
            top_scan_batch.added == (SpacePath("ext_watch_src/root_readme.md"),),
            f"SpaceScanner.scan mismatched top_level_only files: {top_scan_batch}",
        )
        check(
            not sp_reg.match_path("project/subdirs_only", SemanticUri.parse("ext.src://")).matched,
            "Universal dir-only include ('*/') must not match entry root directory itself",
        )
        check(
            sp_reg.match_path("project/subdirs_only", SemanticUri.parse("ext.src://pkg")).matched
            and sp_reg.match_path("project/subdirs_only", SemanticUri.parse("ext.src://pkg/top.py")).matched
            and not sp_reg.match_path("project/subdirs_only", SemanticUri.parse("ext.src://root_readme.md")).matched,
            "Universal dir-only include ('*/') subdirectory vs root-file matching failed",
        )


def _verify_covering_mounts_open_read_and_local_isolation(suite_root: Path) -> None:
    sec_root = suite_root / "covering_isolation_suite"
    sec_host = sec_root / "repo"
    sec_yscb = sec_host / ".yscb"
    sec_host.mkdir(parents=True, exist_ok=True)
    sec_yscb.mkdir(parents=True, exist_ok=True)

    ro_plans_rule = MountRule(
        scheme="ro.plans",
        target_uri=SemanticUri.parse("project://plans"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    ro_masked_rule = MountRule(
        scheme="ro.masked",
        target_uri=SemanticUri.parse("project://masked_ro"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE,
    )
    foreign_cfg_alias = MountRule(
        scheme="foreign.cfg",
        target_uri=SemanticUri.parse("config.local://mod-b"),
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
    )
    mem_rule = MountRule(
        scheme="mem",
        capabilities=VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE,
    )
    mt = UriMountTable(
        build_standard_mount_rules(
            HostPath(sec_host),
            HostPath(sec_yscb),
            project_root=HostPath(sec_host),
            extra_rules=(ro_plans_rule, ro_masked_rule, foreign_cfg_alias, mem_rule),
        ),
        providers={"mem": MemoryVfsProvider("mem")},
    )
    hub = VfsHub(mt)
    kern = hub.for_kernel()
    mod_a = hub.for_module(ModuleId("mod-a"))
    mod_b = hub.for_module(ModuleId("mod-b"))

    yscb_py_covers = {sch for sch, _ in mt.iter_covering_mounts(HostPath(sec_host / "yscb.py"))}
    check({"project", "yscb.host"}.issubset(yscb_py_covers), f"Missing colocated covering mounts: {yscb_py_covers}")
    plan_covers = {sch for sch, _ in mt.iter_covering_mounts(HostPath(sec_host / "plans" / "secret.md"))}
    check({"project", "yscb.host", "ro.plans"}.issubset(plan_covers), f"Missing alias covering mount: {plan_covers}")
    masked_covers = {sch for sch, _ in mt.iter_covering_mounts(HostPath(sec_host / "masked_ro" / "doc.txt"))}
    check({"project", "ro.masked"}.issubset(masked_covers), f"Missing masked alias covering mount: {masked_covers}")

    for ctrl_rel in ("yscb.py", "yscb.config.json", "yscb.config.local.json", ".gitignore", ".git/config"):
        kern.write_text(f"project://{ctrl_rel}", f"kernel_{ctrl_rel}\n")
        check(not mod_a.can_write(f"project://{ctrl_rel}"), f"Control file {ctrl_rel} must not report writable")
        expect_yscb_code(lambda r=ctrl_rel: mod_a.write_text(f"project://{r}", "tamper"), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda r=ctrl_rel: mod_a.delete(f"project://{r}"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.move("project://yscb.py", "project://stolen.py"), ErrorCode.ACCESS_DENIED)
    mod_a.write_text("project://app/main.py", "ok = 1\n")
    check(mod_a.read_text("project://app/main.py") == "ok = 1\n")

    kern.write_text("project://plans/secret.md", "locked_plan\n")
    kern.write_text("project://masked_ro/doc.txt", "locked_masked\n")
    check(not mod_a.can_write("project://plans/secret.md"))
    check(not mod_a.can_write("project://masked_ro/doc.txt"))
    expect_yscb_code(lambda: mod_a.write_text("project://plans/secret.md", "tamper"), ErrorCode.READONLY_VIOLATION)
    expect_yscb_code(lambda: mod_a.delete("project://plans/secret.md"), ErrorCode.READONLY_VIOLATION)
    expect_yscb_code(lambda: mod_a.write_text("project://masked_ro/doc.txt", "tamper"), ErrorCode.READONLY_VIOLATION)

    ro_proj_mt = UriMountTable(
        build_standard_mount_rules(
            HostPath(sec_host),
            HostPath(sec_yscb),
            project_root=HostPath(sec_host),
            extra_rules=(
                MountRule(
                    scheme="ro.proj",
                    target_uri=SemanticUri.parse("project://"),
                    capabilities=VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE | VfsCapabilities.PHYSICAL_PATH,
                ),
            ),
        )
    )
    ro_proj_mod = VfsHub(ro_proj_mt).for_module(ModuleId("mod-a"))
    check(not ro_proj_mod.can_write("project://blocked.txt"))
    expect_yscb_code(lambda: ro_proj_mod.write_text("project://blocked.txt", "nope"), ErrorCode.READONLY_VIOLATION)

    with mod_a.open_read("project://app/main.py") as phys_fh:
        check(phys_fh.read() == b"ok = 1\n", "ScopedVfs.open_read physical stream mismatch")
    kern.write_bytes("mem://stream/bin.dat", b"\x00\x01\x02")
    with mod_a.open_read("mem://stream/bin.dat") as mem_fh:
        check(mem_fh.read() == b"\x00\x01\x02", "ScopedVfs.open_read memory stream mismatch")
    missing_caught = False
    try:
        with mod_a.open_read("project://app/missing.py"):
            pass
    except FileNotFoundError:
        missing_caught = True
    check(missing_caught, "ScopedVfs.open_read on missing file must raise FileNotFoundError")
    dir_caught = False
    try:
        with mod_a.open_read("project://app"):
            pass
    except IsADirectoryError:
        dir_caught = True
    check(dir_caught, "ScopedVfs.open_read on directory must raise IsADirectoryError")

    mod_b.write_json("config.local://@/token.json", {"secret": "mod_b_only"})
    mod_b.write_bytes("storage.local://@/state.bin", b"private_b")
    mod_a.write_json("config.local://@/own.json", {"owner": "mod_a"})
    mod_a.write_bytes("storage.local://@/own.bin", b"private_a")

    check(mod_a.can_read("config.local://@/own.json") and mod_a.read_json("config.local://@/own.json") == {"owner": "mod_a"})
    with mod_a.open_read("storage.local://@/own.bin") as own_fh:
        check(own_fh.read() == b"private_a")
    check(mod_a.try_get_physical_path(SemanticUri("storage.local", "")) == HostPath(sec_yscb / ".storage.local"))
    with ModuleDatabase(mod_a, "storage.local://@/own.db") as own_db:
        check(own_db.verify_integrity())

    for foreign_uri in (
        "config.local://mod-b/token.json",
        "storage.local://mod-b/state.bin",
        "yscb://.config.local/mod-b/token.json",
        "project://.yscb/.storage.local/mod-b/state.bin",
        "foreign.cfg://token.json",
    ):
        check(not mod_a.can_read(foreign_uri), f"Foreign private URI must not report readable: {foreign_uri}")
        expect_yscb_code(lambda u=foreign_uri: mod_a.read_bytes(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.read_text(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.read_json(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.open_read(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.exists(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.stat(u), ErrorCode.ACCESS_DENIED)
        expect_yscb_code(lambda u=foreign_uri: mod_a.try_get_physical_path(u), ErrorCode.ACCESS_DENIED)

    for forbidden_root in ("config.local://", "storage.local://", "config.local://mod-b", "storage.local://mod-b"):
        expect_yscb_code(lambda u=forbidden_root: list(mod_a.iter_entries(u, recursive=True)), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.try_get_physical_path("config.local://"), ErrorCode.ACCESS_DENIED)
    expect_yscb_code(lambda: mod_a.try_get_physical_path("yscb://.storage.local"), ErrorCode.ACCESS_DENIED)

    yscb_visible = {str(u) for u in mod_a.iter_entries("yscb://", recursive=True)}
    check(
        not any("mod-b" in item for item in yscb_visible),
        f"Recursive yscb:// listing leaked foreign local private paths: {yscb_visible}",
    )
    check(kern.read_json("config.local://mod-b/token.json") == {"secret": "mod_b_only"})
    check(kern.read_bytes("storage.local://mod-b/state.bin") == b"private_b")


def _mig_duplicate_pk(tx: WriteTransaction) -> None:
    tx.execute("INSERT INTO kv (k, v) VALUES (?, ?)", ("dup", "first"))
    tx.execute("INSERT INTO kv (k, v) VALUES (?, ?)", ("dup", "second"))


def _verify_sqlite_error_classification_and_uri_globs(suite_root: Path) -> None:
    cls_root = suite_root / "sqlite_and_uri_glob_suite"
    fx = _provision_vfs_hub(cls_root, with_project=True)
    kern = fx.hub.for_kernel()
    mod_a = fx.hub.for_module(ModuleId("mod-a"))
    proj_hp = fx.project_root
    check(proj_hp is not None)
    if proj_hp is None:
        return

    kv_mig = SchemaMigration(
        version=1,
        description="Create kv table",
        sql_statements=("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)",),
    )
    with ModuleDatabase(
        mod_a,
        "storage.local://@/err_cls.db",
        migrations=(kv_mig,),
        options=StorageOpenOptions(busy_timeout_ms=0),
    ) as err_db:
        with err_db.write_transaction() as tx_init:
            tx_init.execute("INSERT INTO kv (k, v) VALUES (?, ?)", ("k1", "v1"))

        def _dup_pk_write() -> None:
            with err_db.write_transaction() as tx_dup:
                tx_dup.execute("INSERT INTO kv (k, v) VALUES (?, ?)", ("k1", "duplicate"))

        expect_yscb_code(_dup_pk_write, ErrorCode.BUSINESS_FAILURE)

        with err_db.read_snapshot() as snap_err:
            expect_yscb_code(
                lambda: snap_err.query_one("SELECT * FROM missing_corrupt_named_table"),
                ErrorCode.BUSINESS_FAILURE,
            )
            expect_yscb_code(
                lambda: snap_err.query_one("SELECT FROM BROKEN SYNTAX"),
                ErrorCode.BUSINESS_FAILURE,
            )
            expect_yscb_code(
                lambda: snap_err.query_one("SELECT v FROM kv WHERE k = ?", ("k1", "extra_arg")),
                ErrorCode.BUSINESS_FAILURE,
            )

        ext_conn = sqlite3.connect(str(err_db.physical_path), isolation_level=None)
        try:
            ext_conn.execute("BEGIN EXCLUSIVE").close()

            def _locked_tx() -> None:
                with err_db.write_transaction() as tx_lk:
                    tx_lk.execute("INSERT INTO kv (k, v) VALUES (?, ?)", ("k2", "blocked"))

            expect_yscb_code(_locked_tx, ErrorCode.TASK_TIMEOUT)
        finally:
            if ext_conn.in_transaction:
                ext_conn.execute("ROLLBACK").close()
            ext_conn.close()

    dup_mig = SchemaMigration(version=2, description="Trigger IntegrityError", migrate_fn=_mig_duplicate_pk)
    expect_yscb_code(
        lambda: ModuleDatabase(mod_a, "storage.local://@/mig_integrity.db", migrations=(kv_mig, dup_mig)),
        ErrorCode.SCHEMA_MIGRATION_ERROR,
    )

    bad_hdr_uri = "storage.local://@/bad_hdr.db"
    mod_a.write_bytes(bad_hdr_uri, b"corrupted_binary_not_sqlite_format" * 4)
    expect_yscb_code(
        lambda: ModuleDatabase(mod_a, bad_hdr_uri, migrations=(kv_mig,)),
        ErrorCode.STORAGE_CORRUPT,
    )

    plans_dir = proj_hp.path / "plans"
    (plans_dir / "sub").mkdir(parents=True, exist_ok=True)
    (plans_dir / "nested" / "deep").mkdir(parents=True, exist_ok=True)
    (plans_dir / "x" / "out").mkdir(parents=True, exist_ok=True)
    (plans_dir / "guide.md").write_text("# guide\n", encoding="utf-8")
    (plans_dir / "notes.txt").write_text("notes\n", encoding="utf-8")
    (plans_dir / "sub" / "other.md").write_text("# other\n", encoding="utf-8")
    (plans_dir / "nested" / "deep" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (plans_dir / "x" / "out" / "art.json").write_text("{}\n", encoding="utf-8")
    (plans_dir / "y").mkdir(parents=True, exist_ok=True)
    (plans_dir / "y" / "out").write_text("file_not_dir\n", encoding="utf-8")

    uri_glob_spec = SpaceSpec(
        space_id=SpaceId("project", "uri_glob_check"),
        entries=(SemanticUri.parse("project://plans"),),
        include=(
            "project://plans/*.md",
            "project://plans/nested/**/*.md",
            "project://plans/*/out/**",
        ),
        watch=False,
    )
    with ModuleDatabase(kern, "storage.local://core/space/uri_glob_state.db") as sp_db:
        sp_reg = SpaceRegistry(kern, sp_db, static_specs=(uri_glob_spec,))
        matched_rels = {str(e.rel_path) for e in sp_reg.iter_files("project/uri_glob_check")}
        expected_rels = {"plans/guide.md", "plans/nested/deep/spec.md", "plans/x/out/art.json"}
        check(
            matched_rels == expected_rels,
            f"URI coordinate glob mismatch (POSIX leading slash): expected {expected_rels}, got {matched_rels}",
        )
        check(sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "guide.md")).matched)
        check(sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "nested" / "deep" / "spec.md")).matched)
        check(sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "x" / "out" / "art.json")).matched)
        check(not sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "notes.txt")).matched)
        check(not sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "sub" / "other.md")).matched)
        check(not sp_reg.match_path("project/uri_glob_check", HostPath(plans_dir / "y" / "out")).matched)


def _execute_all_domain2_checks(base_root: Path) -> None:
    log("[VFS-STORAGE-SPACE] Verifying VFS 15-scheme capability matrix, !undefined, and URI_CYCLE...")
    _verify_vfs_scheme_matrix_and_mount_guards(base_root)
    log("[VFS-STORAGE-SPACE] Verifying VFS containment, dual-layer ReadonlyPolicy, VfsEchoGuard, ScopedVfs & MemoryVfsProvider...")
    _verify_vfs_containment_readonly_echo_and_memory(base_root)
    log("[VFS-STORAGE-SPACE] Verifying Storage capability gatekeeping, WAL MVCC concurrency, rollback, migrations & BlobVault...")
    _verify_storage_gatekeeping_wal_mvcc_migrations_and_vault(base_root)
    log("[VFS-STORAGE-SPACE] Verifying Space compilation, symmetric pruning, compose difference, dynamic spaces & GitignoreMaterializer...")
    _verify_space_algebra_pruning_and_dynamic_gitignore(base_root)
    log("[VFS-STORAGE-SPACE] Verifying SpaceScanner hash policies, Racy-Clean, patch_paths & multi-consumer cursors...")
    _verify_space_scanner_policies_racy_clean_and_cursors(base_root)
    _verify_cross_mount_boundaries_and_space_algebra_invariants(base_root)
    _verify_covering_mounts_open_read_and_local_isolation(base_root)
    _verify_sqlite_error_classification_and_uri_globs(base_root)
    log("[VFS-STORAGE-SPACE] All Domain 2 checks passed.")


def run_vfs_storage_space_suite(tmp_root: Optional[Path] = None) -> None:
    """Execute the full Domain 2 verification suite for vfs, storage, and space."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        if tmp_root is not None:
            suite_dir = tmp_root / "domain_vfs_storage_space"
            suite_dir.mkdir(parents=True, exist_ok=True)
            _execute_all_domain2_checks(suite_dir)
            return
        with tempfile.TemporaryDirectory(prefix="yscb_v2_d2_") as raw_tmp:
            _execute_all_domain2_checks(Path(raw_tmp))


__all__ = ("run_vfs_storage_space_suite",)


if __name__ == "__main__":
    run_vfs_storage_space_suite()
