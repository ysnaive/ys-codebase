"""
gdrive-support 1.0.1.x migration hook.
Idempotently migrates legacy credentials, OAuth tokens, and sync state ledgers
into their dedicated five-semantic-space directories (`config.local://` and `storage.local://`),
and upgrades legacy default URI strings in `config.project.json`.
"""
import json
import os
import shutil
from typing import Any, Dict


def _migrate_single_file(src_path: str, dst_path: str, *, restrict_permissions: bool = False) -> None:
    """Idempotently moves `src_path` to `dst_path`, or removes `src_path` if `dst_path` already exists."""
    if not os.path.isfile(src_path):
        return

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if not os.path.exists(dst_path):
        shutil.move(src_path, dst_path)
    elif os.path.abspath(src_path) != os.path.abspath(dst_path):
        try:
            os.remove(src_path)
        except OSError:
            pass

    if restrict_permissions and os.path.isfile(dst_path):
        try:
            os.chmod(dst_path, 0o600)
        except OSError:
            pass


def _upgrade_config_uris_in_dir(target_dir: str) -> None:
    """Atomically upgrades legacy default credential and token URIs in `config.*.json` files."""
    if not os.path.isdir(target_dir):
        return

    for fname in sorted(os.listdir(target_dir)):
        if not (fname.startswith("config.") and fname.endswith(".json")):
            continue
        cfg_path = os.path.join(target_dir, fname)
        if not os.path.isfile(cfg_path):
            continue

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue

        if not isinstance(data, dict):
            continue

        changed = False
        if data.get("credentials_uri") == "config://gdrive-support/credentials.json":
            data["credentials_uri"] = "config.local://gdrive-support/credentials.json"
            changed = True
        if data.get("token_uri") == "cache://gdrive-support/token.json":
            data["token_uri"] = "config.local://gdrive-support/token.json"
            changed = True

        if changed:
            tmp_path = f"{cfg_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, cfg_path)


def migrate(context: Dict[str, Any]) -> bool:
    """
    Executes the 1.0.1.x space alignment migration for `gdrive-support`:
    1. Moves `<config_dir>/credentials.json` -> `<config_local_dir>/credentials.json` (0o600).
    2. Moves `<yscb_dir>/.cache/gdrive-support/token.json` -> `<config_local_dir>/token.json` (0o600).
    3. Moves `<yscb_dir>/.cache/gdrive-support/{sync_state,readme_sync_state}.json`
       -> `<storage_local_dir>/{sync_state,readme_sync_state}.json`.
    4. Upgrades legacy default `credentials_uri` and `token_uri` in `<config_dir>/config.project.json`.
    """
    yscb_dir = context.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri

            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    config_dir = context.get("config_dir") or os.path.join(yscb_dir, "config", "gdrive-support")
    config_local_dir = context.get("config_local_dir") or os.path.join(
        yscb_dir, ".config.local", "gdrive-support"
    )
    storage_local_dir = context.get("storage_local_dir") or os.path.join(
        yscb_dir, ".storage.local", "gdrive-support"
    )
    cache_mod_dir = os.path.join(yscb_dir, ".cache", "gdrive-support")

    _migrate_single_file(
        os.path.join(config_dir, "credentials.json"),
        os.path.join(config_local_dir, "credentials.json"),
        restrict_permissions=True,
    )
    _migrate_single_file(
        os.path.join(cache_mod_dir, "token.json"),
        os.path.join(config_local_dir, "token.json"),
        restrict_permissions=True,
    )

    for ledger_name in ("sync_state.json", "readme_sync_state.json"):
        _migrate_single_file(
            os.path.join(cache_mod_dir, ledger_name),
            os.path.join(storage_local_dir, ledger_name),
            restrict_permissions=False,
        )

    _upgrade_config_uris_in_dir(config_dir)
    _upgrade_config_uris_in_dir(config_local_dir)

    try:
        from core import config

        config.reload()
    except Exception:
        pass

    return True
