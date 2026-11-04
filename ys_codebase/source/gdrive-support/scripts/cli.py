"""
CLI Entry point for module:gdrive-support (atomic operations, branch management, and 3-way sync).
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from core import uri
from core.commands import CmdBags
from core.guard import guard_dispatch


def _emit(payload: Dict[str, Any], as_json: bool, summary: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(summary)


def _maybe_reconcile_root_readme(
    cfg: Any, transport: Any, *, sandbox_override: str = ""
) -> None:
    """
    Trigger local-cache-gated root/README.md soft-merge / soft-remove check if repo_sync.enable changed.
    When an ad-hoc --sandbox-dir CLI override is passed, store state inside that sandbox's .yscb_readme_state.json
    to prevent ad-hoc sandbox runs from mutating the global cache://gdrive-support/readme_sync_state.json.
    """
    from gdrive_support.coordinator import reconcile_root_readme_state

    try:
        state_path = (
            Path(sandbox_override) / ".yscb_readme_state.json"
            if sandbox_override
            else None
        )
        reconcile_root_readme_state(
            config=cfg, transport=transport, readme_state_path=state_path
        )
    except Exception:
        pass


def status(cmd_bags: CmdBags) -> int:
    """Display gdrive-support configuration, repo_sync state, active_branch, and sync_spaces."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")

    try:
        cfg = load_gdrive_config()
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support] Config Error: {exc}",
        )
        return 1

    effective_sandbox = str(sandbox_dir or cfg.sandbox_dir or "")
    spaces_info: List[Dict[str, Any]] = []
    for sp in cfg.sync_spaces:
        spaces_info.append(
            {
                "space": sp.space,
                "description": sp.description,
                "mappings": [
                    {
                        "local": m.local_uri,
                        "local_rel_prefix": m.local_rel_prefix,
                        "remote_rel_prefix": m.remote_rel_prefix,
                    }
                    for m in sp.mappings
                ],
            }
        )

    payload: Dict[str, Any] = {
        "status": "ok",
        "module": "gdrive-support",
        "alias": "gdrive",
        "root_folder_id": cfg.root_folder_id,
        "mode": "sandbox" if effective_sandbox else "google_drive_api",
        "sandbox_dir": effective_sandbox,
        "repo_sync_enabled": cfg.repo_sync_enabled,
        "repo_sync_root": cfg.repo_sync_root,
        "active_branch": cfg.active_branch,
        "auto_sync": cfg.auto_sync,
        "repo_sync": {
            "enable": cfg.repo_sync_enabled,
            "repo_sync_root": cfg.repo_sync_root,
            "active_branch": cfg.active_branch,
            "auto_sync": cfg.auto_sync,
            "poll_interval_sec": cfg.poll_interval_sec,
            "pull_delete_default": cfg.pull_delete_default,
            "push_delete_default": cfg.push_delete_default,
            "sync_spaces": spaces_info,
        },
        "sync_spaces": spaces_info,
    }
    summary = (
        f"[gdrive-support] repo_sync.enable={cfg.repo_sync_enabled} | "
        f"root={cfg.repo_sync_root} | branch={cfg.active_branch} | "
        f"auto_sync={cfg.auto_sync} | mode={payload['mode']} | spaces={len(spaces_info)}"
    )
    _emit(payload, as_json, summary)
    return 0


def auth(cmd_bags: CmdBags) -> int:
    """Verify Google Drive API credentials or execute OAuth 2.0 Client ID authorization."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import (
        build_oauth_authorize_url,
        exchange_oauth_code_for_token,
        load_oauth_client_config,
        run_oauth_loopback_flow,
    )

    as_json = bool(cmd_bags.options.get("json"))
    is_check = bool(cmd_bags.options.get("check"))
    no_launch = bool(cmd_bags.options.get("no-launch-browser"))
    raw_code = str(cmd_bags.get_option_value("code", default="") or "").strip()
    raw_port = str(cmd_bags.get_option_value("port", default="") or "").strip()
    port = int(raw_port) if raw_port.isdigit() else 8765

    try:
        cfg = load_gdrive_config()
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support] Config Error: {exc}",
        )
        return 1

    cred_path = (
        Path(uri.resolve(cfg.credentials_uri))
        if "://" in cfg.credentials_uri
        else Path(cfg.credentials_uri)
    )
    token_path = (
        Path(uri.resolve(cfg.token_uri))
        if "://" in cfg.token_uri
        else Path(cfg.token_uri)
    )
    has_creds = cred_path.is_file()
    has_token = token_path.is_file()

    if is_check:
        payload = {
            "status": "ok" if (has_creds and has_token) else ("credentials_ready" if has_creds else "missing_credentials"),
            "auth_mode": cfg.auth_mode,
            "check_only": True,
            "credentials_path": cred_path.as_posix(),
            "credentials_exists": has_creds,
            "token_path": token_path.as_posix(),
            "token_exists": has_token,
        }
        summary = (
            f"[gdrive-support:auth] mode={cfg.auth_mode} | "
            f"credentials={has_creds} ({cred_path.as_posix()}) | "
            f"token={has_token} ({token_path.as_posix()})"
        )
        _emit(payload, as_json, summary)
        return 0

    try:
        client_id, client_secret = load_oauth_client_config(cred_path)
        redirect_uri = f"http://127.0.0.1:{port}"

        if raw_code:
            token_data = exchange_oauth_code_for_token(
                client_id=client_id,
                client_secret=client_secret,
                code_or_url=raw_code,
                redirect_uri=redirect_uri,
                token_path=token_path,
            )
            payload = {
                "status": "authorized",
                "token_path": token_path.as_posix(),
                "has_refresh_token": bool(token_data.get("refresh_token")),
                "expiry_epoch": token_data.get("expiry_epoch"),
            }
            _emit(
                payload,
                as_json,
                f"[gdrive-support:auth] OAuth2 token saved to '{token_path.as_posix()}'",
            )
            return 0

        if no_launch:
            auth_url = build_oauth_authorize_url(client_id, redirect_uri)
            payload = {
                "status": "awaiting_code",
                "authorize_url": auth_url,
                "redirect_uri": redirect_uri,
                "next_command": f'python yscb.py gdrive auth --code="<CODE_OR_REDIRECT_URL>" --port={port}',
            }
            summary = (
                f"[gdrive-support:auth] Step 1 — Open this URL in your browser and authorize:\n\n"
                f"  {auth_url}\n\n"
                f"[gdrive-support:auth] Step 2 — After authorizing, copy the redirected URL "
                f"(http://127.0.0.1:{port}/?code=...) or the code parameter and run:\n\n"
                f'  python yscb.py gdrive auth --code="<CODE_OR_REDIRECT_URL>" --port={port}'
            )
            _emit(payload, as_json, summary)
            return 0

        token_data = run_oauth_loopback_flow(
            cred_path=cred_path,
            token_path=token_path,
            port=port,
            open_browser=True,
        )
        payload = {
            "status": "authorized",
            "token_path": token_path.as_posix(),
            "has_refresh_token": bool(token_data.get("refresh_token")),
            "expiry_epoch": token_data.get("expiry_epoch"),
        }
        _emit(
            payload,
            as_json,
            f"[gdrive-support:auth] OAuth2 token saved to '{token_path.as_posix()}'",
        )
        return 0
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:auth] Error: {exc}",
        )
        return 1


def ls(cmd_bags: CmdBags) -> int:
    """Atomically list files, folders, and shortcuts under remote_path."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import create_transport

    remote_path = cmd_bags.args[0] if cmd_bags.args else ""
    recursive = bool(cmd_bags.options.get("recursive"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    as_json = bool(cmd_bags.options.get("json"))

    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        entries = transport.list_files(remote_path=remote_path, recursive=recursive)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:ls] Error: {exc}",
        )
        return 1

    payload = {
        "status": "ok",
        "remote_path": remote_path,
        "recursive": recursive,
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for e in entries:
            kind = "DIR" if e.is_dir else ("SHORTCUT" if e.is_shortcut else "FILE")
            extra = f" -> {e.target_file_id}" if e.is_shortcut else ""
            if e.skipped_reason:
                extra += f" [{e.skipped_reason}]"
            print(f"[{kind}] {e.rel_path} (id={e.file_id}, size={e.size}){extra}")
    return 0


def get(cmd_bags: CmdBags) -> int:
    """Atomically download a single remote file (or shortcut target) to local_path."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if len(cmd_bags.args) < 2:
        _emit(
            {"status": "error", "error": "get requires <remote_path> and <local_path>."},
            as_json,
            "[gdrive-support:get] Error: requires <remote_path> and <local_path>.",
        )
        return 1

    remote_path = cmd_bags.args[0]
    local_path = Path(cmd_bags.args[1])

    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        entry = transport.download_file(remote_path=remote_path, local_path=local_path)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:get] Error: {exc}",
        )
        return 1

    payload = {
        "status": "ok",
        "action": "get",
        "remote_path": entry.rel_path,
        "local_path": local_path.resolve().as_posix(),
        "entry": entry.to_dict(),
    }
    _emit(
        payload,
        as_json,
        f"[gdrive-support:get] Downloaded '{entry.rel_path}' -> '{local_path.as_posix()}'",
    )
    return 0


def put(cmd_bags: CmdBags) -> int:
    """Atomically upload a local file to remote_path."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import (
        GDriveConfigError,
        GDriveError,
        is_sensitive_credential_path,
        load_gdrive_config,
    )
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    in_place_id = cmd_bags.get_option_value("in-place-id", default="")
    if len(cmd_bags.args) < 2:
        _emit(
            {"status": "error", "error": "put requires <local_path> and <remote_path>."},
            as_json,
            "[gdrive-support:put] Error: requires <local_path> and <remote_path>.",
        )
        return 1

    local_path = Path(cmd_bags.args[0])
    remote_path = cmd_bags.args[1]

    try:
        proj_root = Path(uri.resolve("project://")).resolve()
        if is_sensitive_credential_path(local_path.resolve(), proj_root):
            raise GDriveConfigError(
                f"Refusing to upload sensitive credential/token file '{local_path.as_posix()}' to Google Drive."
            )
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        entry = transport.upload_file(
            local_path=local_path,
            remote_path=remote_path,
            in_place_file_id=str(in_place_id) if in_place_id else None,
        )
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:put] Error: {exc}",
        )
        return 1

    payload = {
        "status": "ok",
        "action": "put",
        "local_path": local_path.resolve().as_posix(),
        "remote_path": entry.rel_path,
        "entry": entry.to_dict(),
    }
    _emit(
        payload,
        as_json,
        f"[gdrive-support:put] Uploaded '{local_path.as_posix()}' -> '{entry.rel_path}' (id={entry.file_id})",
    )
    return 0


def rm(cmd_bags: CmdBags) -> int:
    """Atomically move remote_path into Google Drive's native 30-day Trash (or sandbox .trash/)."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if not cmd_bags.args:
        _emit(
            {"status": "error", "error": "rm requires <remote_path>."},
            as_json,
            "[gdrive-support:rm] Error: requires <remote_path>.",
        )
        return 1

    remote_path = cmd_bags.args[0]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        removed = transport.trash_file(remote_path=remote_path)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:rm] Error: {exc}",
        )
        return 1

    if not removed:
        _emit(
            {"status": "not_found", "remote_path": remote_path},
            as_json,
            f"[gdrive-support:rm] Not found: '{remote_path}'",
        )
        return 1

    payload = {"status": "ok", "action": "rm", "remote_path": remote_path}
    _emit(payload, as_json, f"[gdrive-support:rm] Moved '{remote_path}' to Trash")
    return 0


def mkdir(cmd_bags: CmdBags) -> int:
    """Atomically create a remote folder hierarchy."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if not cmd_bags.args:
        _emit(
            {"status": "error", "error": "mkdir requires <remote_path>."},
            as_json,
            "[gdrive-support:mkdir] Error: requires <remote_path>.",
        )
        return 1

    remote_path = cmd_bags.args[0]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        entry = transport.mkdir(remote_path=remote_path)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:mkdir] Error: {exc}",
        )
        return 1

    payload = {
        "status": "ok",
        "action": "mkdir",
        "remote_path": entry.rel_path,
        "entry": entry.to_dict(),
    }
    _emit(
        payload,
        as_json,
        f"[gdrive-support:mkdir] Created '{entry.rel_path}' (id={entry.file_id})",
    )
    return 0


def shortcut(cmd_bags: CmdBags) -> int:
    """Atomically create a Google Drive Shortcut pointing to target_file_id."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if len(cmd_bags.args) < 2:
        _emit(
            {
                "status": "error",
                "error": "shortcut requires <target_file_id> and <shortcut_remote_path>.",
            },
            as_json,
            "[gdrive-support:shortcut] Error: requires <target_file_id> and <shortcut_remote_path>.",
        )
        return 1

    target_file_id = cmd_bags.args[0]
    shortcut_remote_path = cmd_bags.args[1]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        _maybe_reconcile_root_readme(cfg, transport, sandbox_override=str(sandbox_dir or ""))
        entry = transport.create_shortcut(
            target_file_id=target_file_id, shortcut_remote_path=shortcut_remote_path
        )
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:shortcut] Error: {exc}",
        )
        return 1

    payload = {
        "status": "ok",
        "action": "shortcut",
        "shortcut_remote_path": entry.rel_path,
        "target_file_id": entry.target_file_id,
        "entry": entry.to_dict(),
    }
    _emit(
        payload,
        as_json,
        f"[gdrive-support:shortcut] Created shortcut '{entry.rel_path}' -> '{entry.target_file_id}'",
    )
    return 0


def init(cmd_bags: CmdBags) -> int:
    """Initialize cloud/sandbox root with .yscb_gdrive.json, README.md, .history/, .trash/, and main/."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    force = bool(cmd_bags.options.get("force"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")

    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        res = coord.init_repo(force=force)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:init] Error: {exc}",
        )
        return 1

    _emit(
        res,
        as_json,
        f"[gdrive-support:init] Status={res['status']} | repo_id={res['meta'].get('repo_id')}",
    )
    return 0


def branch_list(cmd_bags: CmdBags) -> int:
    """List registered cloud branches."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")

    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        res = coord.list_branches()
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:branch list] Error: {exc}",
        )
        return 1

    if as_json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        active = res.get("active_branch", "main")
        for b_name in sorted(res.get("branches", {}).keys()):
            marker = "*" if b_name == active else " "
            print(f"{marker} {b_name}")
    return 0


def branch_create(cmd_bags: CmdBags) -> int:
    """Create a new delta branch populated with Google Drive Shortcuts."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    from_branch = cmd_bags.get_option_value("from", default="main")
    if not cmd_bags.args:
        _emit(
            {"status": "error", "error": "branch create requires <branch_name>."},
            as_json,
            "[gdrive-support:branch create] Error: requires <branch_name>.",
        )
        return 1

    branch_name = cmd_bags.args[0]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        res = coord.create_branch(branch_name=branch_name, from_branch=str(from_branch))
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:branch create] Error: {exc}",
        )
        return 1

    _emit(
        res,
        as_json,
        f"[gdrive-support:branch create] Created branch '{res['branch']}' from '{res['from_branch']}' "
        f"(shortcuts={res['shortcuts_created']})",
    )
    return 0


def branch_delete(cmd_bags: CmdBags) -> int:
    """Delete a branch and garbage-collect unreferenced .history/ files to .trash/."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if not cmd_bags.args:
        _emit(
            {"status": "error", "error": "branch delete requires <branch_name>."},
            as_json,
            "[gdrive-support:branch delete] Error: requires <branch_name>.",
        )
        return 1

    branch_name = cmd_bags.args[0]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        res = coord.delete_branch(branch_name=branch_name)
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:branch delete] Error: {exc}",
        )
        return 1

    _emit(
        res,
        as_json,
        f"[gdrive-support:branch delete] Deleted '{res['deleted_branch']}' "
        f"(gc_history_to_trash={len(res['gc_history_to_trash'])})",
    )
    return 0


def checkout(cmd_bags: CmdBags) -> int:
    """Atomically switch active_branch and align local tracked worktree."""
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    force = bool(cmd_bags.options.get("force"))
    backup = bool(cmd_bags.options.get("backup"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")
    if not cmd_bags.args:
        _emit(
            {"status": "error", "error": "checkout requires <target_branch>."},
            as_json,
            "[gdrive-support:checkout] Error: requires <target_branch>.",
        )
        return 1

    target_branch = cmd_bags.args[0]
    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        res = coord.checkout_branch(
            target_branch=target_branch, force=force, backup=backup
        )
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:checkout] Error: {exc}",
        )
        return 1

    _emit(
        res,
        as_json,
        f"[gdrive-support:checkout] Switched '{res['previous_branch']}' -> '{res['active_branch']}' "
        f"(pulled={len(res['pulled_files'])}, removed_orphans={len(res['removed_orphans'])})",
    )
    return 0


def _run_sync_cmd(cmd_bags: CmdBags, mode: str) -> int:
    guard_dispatch("gdrive-support")
    from gdrive_support.config import GDriveError, load_gdrive_config
    from gdrive_support.coordinator import SyncCoordinator
    from gdrive_support.transport import create_transport

    as_json = bool(cmd_bags.options.get("json"))
    delete = bool(cmd_bags.options.get("delete"))
    force = bool(cmd_bags.options.get("force"))
    backup = bool(cmd_bags.options.get("backup"))
    sandbox_dir = cmd_bags.get_option_value("sandbox-dir", default="")

    try:
        cfg = load_gdrive_config()
        transport = create_transport(cfg, sandbox_dir=sandbox_dir or None)
        coord = SyncCoordinator(config=cfg, transport=transport)
        report = coord.run_sync(
            mode=mode, delete=delete, force=force, backup=backup
        )
    except GDriveError as exc:
        _emit(
            {"status": "error", "error": str(exc)},
            as_json,
            f"[gdrive-support:{mode}] Error: {exc}",
        )
        return 1

    payload = {"status": "ok", **report.to_dict()}
    summary = (
        f"[gdrive-support:{mode}] branch={report.branch} | pushed={len(report.pushed)} | "
        f"pulled={len(report.pulled)} | conflicts={len(report.conflicts)} | "
        f"history_cow={len(report.moved_to_history)} | history_gc={len(report.gc_history_to_trash)}"
    )
    _emit(payload, as_json, summary)
    return report.exit_code


def pull(cmd_bags: CmdBags) -> int:
    """Pull changes from active remote branch to local spaces."""
    return _run_sync_cmd(cmd_bags, "pull")


def push(cmd_bags: CmdBags) -> int:
    """Push changes from local spaces to active remote branch."""
    return _run_sync_cmd(cmd_bags, "push")


def sync(cmd_bags: CmdBags) -> int:
    """Bidirectionally reconcile and synchronize local spaces with active remote branch."""
    return _run_sync_cmd(cmd_bags, "sync")
