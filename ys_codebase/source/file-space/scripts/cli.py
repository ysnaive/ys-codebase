"""
CLI command entry points for the file-space module.
"""
import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_module_path() -> None:
    import sys

    module_root = Path(__file__).resolve().parent.parent
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))


def _extract_opt(bags: Any, name: str, default: Any = None) -> Any:
    if bags is None:
        return default
    clean_name = name.lstrip("-")
    if hasattr(bags, "get_option_value"):
        val = bags.get_option_value(clean_name)
        if val is not None:
            return val
    opts = getattr(bags, "options", None)
    if isinstance(opts, dict):
        for candidate in (clean_name, f"--{clean_name}"):
            if candidate in opts:
                opt_bag = opts[candidate]
                if hasattr(opt_bag, "params") and opt_bag.params is not None:
                    return opt_bag.params
                args_list = getattr(opt_bag, "args", None)
                if args_list:
                    return getattr(args_list[0], "val", default)
                return True
    args_pos = getattr(bags, "args", None)
    if clean_name == "space" and isinstance(args_pos, list) and args_pos:
        return str(args_pos[0])
    return default


def _has_opt(bags: Any, name: str) -> bool:
    if bags is None:
        return False
    clean_name = name.lstrip("-")
    if hasattr(bags, "has_option"):
        if bags.has_option(clean_name):
            return True
    opts = getattr(bags, "options", None)
    if isinstance(opts, dict):
        return (clean_name in opts) or (f"--{clean_name}" in opts)
    return False


def _create_scanner(bags: Any = None) -> Any:
    _ensure_module_path()
    from file_space.manager import FileSpaceManager
    from file_space.scanner import FingerprintScanner

    mgr = FileSpaceManager()
    return FingerprintScanner(space_manager=mgr)


def status(bags: Any = None) -> int:
    """
    Display workspace geometry, active file count, head_generation, merkle_root,
    and per-consumer cursor lag status.
    """
    _ensure_module_path()
    from file_space.exceptions import FileSpaceError

    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        mgr = scanner.space_manager
        target_spaces = (
            [space_name] if space_name is not None else mgr.list_spaces()
        )
        consumers = scanner.cursor_store.list_consumers()
        if "default" not in consumers:
            consumers = ["default"] + consumers

        spaces_report: Dict[str, Any] = {}
        for s_name in target_spaces:
            cfg = mgr.get_space(s_name)
            snap_path = scanner.get_snapshot_path(s_name)
            state, _ = scanner._load_or_recover_state(s_name)
            active_count = len(state.active_entries)
            tombstone_count = sum(
                1 for fp in state.entries.values() if fp.is_deleted
            )
            cursor_summary: Dict[str, Any] = {}
            for cid in consumers:
                c_rec = scanner.cursor_store.get_cursor(s_name, cid)
                acked_gen = c_rec["acked_gen"]
                lag = max(0, state.head_generation - acked_gen)
                cursor_summary[cid] = {
                    "acked_gen": acked_gen,
                    "lag_generations": lag,
                    "in_sync": (
                        acked_gen == state.head_generation
                        and state.head_generation > 0
                    ),
                }

            spaces_report[s_name] = {
                "name": s_name,
                "origin": getattr(cfg.origin, "value", str(cfg.origin)),
                "origin_display": cfg.origin_display,
                "owner_modules": list(cfg.owner_modules),
                "description": cfg.description,
                "include": [
                    p.as_posix() for p in cfg.resolved_include_paths
                ],
                "raw_include_uris": list(cfg.raw_include_uris),
                "hash_policy": getattr(
                    cfg.hash_policy, "value", str(cfg.hash_policy)
                ),
                "large_file_threshold_mb": cfg.large_file_threshold_mb,
                "watch": cfg.watch,
                "weight": cfg.weight,
                "snapshot_exists": snap_path.exists(),
                "head_generation": state.head_generation,
                "merkle_root": state.merkle_root,
                "active_files": active_count,
                "deleted_tombstones": tombstone_count,
                "cursors": cursor_summary,
            }

        payload = {
            "status": "ok",
            "storage_root": mgr.storage_root.as_posix(),
            "space_count": len(spaces_report),
            "spaces": spaces_report,
        }

        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"=== File-Space Status ({len(spaces_report)} workspaces) ===")
            for s_name, info in spaces_report.items():
                print(
                    f"  [{s_name}] {info['origin_display']} policy={info['hash_policy']} "
                    f"gen={info['head_generation']} files={info['active_files']} "
                    f"merkle={info['merkle_root'][:12] or '-'}"
                )
        return 0
    except FileSpaceError as exc:
        if as_json:
            print(
                json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[Error] {exc}")
        return 1


def scan(bags: Any = None) -> int:
    """
    Trigger two-stage incremental fingerprint scan for one or all workspaces
    and update YFP2 binary snapshots.
    """
    _ensure_module_path()
    from file_space.exceptions import FileSpaceError

    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    force: bool = _has_opt(bags, "--force")
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        diff_res = scanner.refresh(space_name=space_name, force=force)
        payload = {
            "status": "ok",
            "space": space_name or "all",
            "force": force,
            **diff_res.to_dict(),
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            target_label = space_name or "all spaces"
            print(
                f"[File-Space Scan] {target_label}: gen {diff_res.from_generation} -> {diff_res.to_generation} "
                f"(+{diff_res.added_count} ~{diff_res.modified_count} -{diff_res.deleted_count} "
                f"={diff_res.unchanged_count}) merkle={diff_res.merkle_root[:12]}"
            )
        return 0
    except FileSpaceError as exc:
        if as_json:
            print(
                json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[Error] {exc}")
        return 1


def files(bags: Any = None) -> int:
    """
    List active files managed within the specified workspace (or all workspaces).
    """
    _ensure_module_path()
    from file_space.exceptions import FileSpaceError

    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    pattern: Optional[str] = _extract_opt(bags, "--pattern", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        snap = scanner.snapshot(space_name=space_name)
        records: List[Dict[str, Any]] = []
        for rel_path in sorted(snap.keys()):
            if pattern and not fnmatch.fnmatch(rel_path, pattern) and not fnmatch.fnmatch(
                Path(rel_path).name, pattern
            ):
                continue
            fp = snap[rel_path]
            records.append(fp.to_dict())

        payload = {
            "status": "ok",
            "space": space_name or "all",
            "pattern": pattern,
            "count": len(records),
            "files": records,
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"=== Managed Files ({len(records)} files in {space_name or 'all'}) ==="
            )
            for rec in records:
                print(
                    f"  {rec['path']} ({rec['size']}B, gen={rec['updated_gen']}, hash={rec['content_hash'][:12]})"
                )
        return 0
    except FileSpaceError as exc:
        if as_json:
            print(
                json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[Error] {exc}")
        return 1


def diff(bags: Any = None) -> int:
    """
    Inspect pending incremental changes for a consumer cursor relative to current snapshot.
    Optionally advances the cursor when `--ack` is passed.
    """
    _ensure_module_path()
    from file_space.exceptions import FileSpaceError

    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    consumer_id: str = _extract_opt(bags, "--consumer", "default") or "default"
    do_ack: bool = _has_opt(bags, "--ack")
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        diff_res = scanner.diff(
            space_name=space_name, consumer_id=consumer_id
        )
        if do_ack:
            scanner.ack(
                space_name=space_name,
                consumer_id=consumer_id,
                generation=diff_res.to_generation,
            )

        payload = {
            "status": "ok",
            "space": space_name or "all",
            "consumer_id": consumer_id,
            "acknowledged": do_ack,
            **diff_res.to_dict(),
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"[File-Space Diff] space={space_name or 'all'} consumer={consumer_id} "
                f"gen={diff_res.from_generation}->{diff_res.to_generation} "
                f"(+{diff_res.added_count} ~{diff_res.modified_count} -{diff_res.deleted_count}) "
                f"acked={do_ack}"
            )
        return 0
    except FileSpaceError as exc:
        if as_json:
            print(
                json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[Error] {exc}")
        return 1


def clean(bags: Any = None) -> int:
    """
    Remove YFP2 binary snapshots and/or reset consumer watermark cursors.
    """
    _ensure_module_path()
    import shutil
    from file_space.exceptions import FileSpaceError

    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    consumer_id: Optional[str] = _extract_opt(bags, "--consumer", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        removed_snapshots: List[str] = []
        reset_consumers: List[str] = []

        if consumer_id is not None:
            scanner.reset_cursor(
                space_name=space_name, consumer_id=consumer_id
            )
            reset_consumers.append(consumer_id)
        elif space_name is not None:
            scanner.space_manager.get_space(space_name)
            snap_path = scanner.get_snapshot_path(space_name)
            if snap_path.exists():
                snap_path.unlink()
                removed_snapshots.append(snap_path.name)
            for cid in scanner.cursor_store.list_consumers():
                scanner.reset_cursor(space_name=space_name, consumer_id=cid)
                reset_consumers.append(cid)
        else:
            if scanner.snapshots_dir.exists():
                for p in sorted(scanner.snapshots_dir.glob("*.yfp2.bin")):
                    removed_snapshots.append(p.name)
                    p.unlink()
            if scanner.cursor_store.cursors_dir.exists():
                for cid in scanner.cursor_store.list_consumers():
                    reset_consumers.append(cid)
                shutil.rmtree(
                    scanner.cursor_store.cursors_dir, ignore_errors=True
                )
                scanner.cursor_store.cursors_dir.mkdir(
                    parents=True, exist_ok=True
                )

        payload = {
            "status": "ok",
            "space": space_name or "all",
            "consumer": consumer_id,
            "removed_snapshots": removed_snapshots,
            "reset_consumers": reset_consumers,
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"[File-Space Clean] removed_snapshots={len(removed_snapshots)}, "
                f"reset_consumers={len(reset_consumers)}"
            )
        return 0
    except FileSpaceError as exc:
        if as_json:
            print(
                json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[Error] {exc}")
        return 1
