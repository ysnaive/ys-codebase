"""
Deprecated CLI command entry points for the file-space module.
Delegates all subcommands (`status`, `scan`, `files`, `diff`, `clean`) to `core.space`.
"""
import json
from typing import Any, Dict, Optional

from core.log import log
from core.space import SpaceError
from file_space.exceptions import FileSpaceError
from file_space.manager import FileSpaceManager
from file_space.scanner import FingerprintScanner


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
        return str(getattr(args_pos[0], "val", args_pos[0]))
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


def _create_scanner(bags: Any = None) -> FingerprintScanner:
    _ = bags
    mgr = FileSpaceManager()
    return FingerprintScanner(space_manager=mgr)


def _print_json(payload: Dict[str, Any]) -> None:
    log(json.dumps(payload, ensure_ascii=False, indent=2))


def _handle_cli_error(exc: Exception, as_json: bool) -> int:
    if as_json:
        log(
            json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
            )
        )
    else:
        log(f"[Error] {exc}")
    return 1


def status(bags: Any = None) -> int:
    """Delegate workspace status inspection to core.space."""
    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        payload = scanner.status(space_name=space_name)
        if as_json:
            _print_json(payload)
        else:
            log(
                f"=== File-Space Status [Deprecated -> core.space] ({payload.get('space_count', 0)} spaces) ==="
            )
            for s_info in payload.get("spaces", []):
                q_name = s_info.get("qualified_name", s_info.get("name", ""))
                gen = s_info.get("head_generation", 0)
                files_cnt = s_info.get("active_file_count", 0)
                merkle = str(s_info.get("merkle_root", ""))[:12] or "-"
                log(f"  [{q_name}] gen={gen} files={files_cnt} merkle={merkle}")
        return 0
    except (FileSpaceError, SpaceError) as exc:
        return _handle_cli_error(exc, as_json)


def scan(bags: Any = None) -> int:
    """Delegate incremental fingerprint scan to core.space."""
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
            _print_json(payload)
        else:
            target_label = space_name or "all spaces"
            log(
                f"[File-Space Scan] {target_label}: gen {diff_res.from_generation} -> {diff_res.to_generation} "
                f"(+{diff_res.added_count} ~{diff_res.modified_count} -{diff_res.deleted_count} "
                f"={diff_res.unchanged_count}) merkle={diff_res.merkle_root[:12]}"
            )
        return 0
    except (FileSpaceError, SpaceError) as exc:
        return _handle_cli_error(exc, as_json)


def files(bags: Any = None) -> int:
    """Delegate workspace file listing to core.space."""
    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    pattern: Optional[str] = _extract_opt(bags, "--pattern", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        entries = scanner.space_manager.registry.iter_space_files(
            space_query=space_name, pattern=pattern
        )
        records = [
            {
                "path": e.rel_path,
                "rel_path": e.rel_path,
                "abs_path": e.abs_path.as_posix(),
                "entry_path": e.entry_path.as_posix(),
                "matched_spaces": list(e.matched_spaces),
                "size": e.size,
                "mtime_ns": e.mtime_ns,
                "ctime_ns": e.ctime_ns,
            }
            for e in entries
        ]
        payload = {
            "status": "ok",
            "space": space_name or "all",
            "pattern": pattern,
            "count": len(records),
            "files": records,
        }
        if as_json:
            _print_json(payload)
        else:
            log(
                f"=== Managed Files ({len(records)} files in {space_name or 'all'}) ==="
            )
            for rec in records:
                log(f"  {rec['path']} ({rec['size']}B)")
        return 0
    except (FileSpaceError, SpaceError) as exc:
        return _handle_cli_error(exc, as_json)


def diff(bags: Any = None) -> int:
    """Delegate consumer cursor diff inspection to core.space."""
    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    consumer_id: str = _extract_opt(bags, "--consumer", "default") or "default"
    do_ack: bool = _has_opt(bags, "--ack")
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        diff_res = scanner.diff(space_name=space_name, consumer_id=consumer_id)
        if do_ack:
            scanner.ack(
                space_name=space_name,
                consumer_id=consumer_id,
                generation=diff_res.to_generation,
                space_generations=diff_res.space_generations,
            )

        payload = {
            "status": "ok",
            "space": space_name or "all",
            "consumer_id": consumer_id,
            "acknowledged": do_ack,
            **diff_res.to_dict(),
        }
        if as_json:
            _print_json(payload)
        else:
            log(
                f"[File-Space Diff] space={space_name or 'all'} consumer={consumer_id} "
                f"gen={diff_res.from_generation}->{diff_res.to_generation} "
                f"(+{diff_res.added_count} ~{diff_res.modified_count} -{diff_res.deleted_count}) "
                f"acked={do_ack}"
            )
        return 0
    except (FileSpaceError, SpaceError) as exc:
        return _handle_cli_error(exc, as_json)


def clean(bags: Any = None) -> int:
    """Delegate snapshot and cursor cleanup to core.space."""
    space_name: Optional[str] = _extract_opt(bags, "--space", None)
    consumer_id: Optional[str] = _extract_opt(bags, "--consumer", None)
    as_json: bool = _has_opt(bags, "--json")

    try:
        scanner = _create_scanner(bags)
        payload = scanner.clean(space_name=space_name, consumer_id=consumer_id)
        if as_json:
            _print_json(payload)
        else:
            log(
                f"[File-Space Clean] removed_snapshots={len(payload.get('removed_snapshots', []))}, "
                f"reset_consumers={len(payload.get('reset_consumers', []))}"
            )
        return 0
    except (FileSpaceError, SpaceError) as exc:
        return _handle_cli_error(exc, as_json)
