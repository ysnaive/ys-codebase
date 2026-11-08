"""
CLI Router & Subcommand Entry Points for `module:vscode-support@1.0.0.0`.
Aligned with `core.commands.CmdBags` contract and `contributes/core.json`.
"""

import json
from typing import Any, Dict, List, Tuple

from core import uri
from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
from core.log import log


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (list, tuple)):
        args = list(cmd_bags)
        raw_cmd = " ".join(str(a) for a in args)
        opts: Dict[str, CmdOption] = {}
        pos: List[str] = []
        for a in args:
            a_str = str(a)
            if a_str.startswith("--"):
                k = a_str[2:]
                v: Any = True
                if "=" in k:
                    k, val = k.split("=", 1)
                    v = val
                opts[k] = CmdOption(name=k, params=v)
            elif a_str.startswith("-") and len(a_str) > 1:
                k = a_str[1:]
                opts[k] = CmdOption(name=k, params=True)
            else:
                pos.append(a_str)
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    return CmdBags(raw_cmd=default_cmd, command=default_cmd, args=[], options={})


def _is_json_mode(bags: CmdBags) -> bool:
    if hasattr(bags, "has_option"):
        return bool(bags.has_option("json"))
    return "json" in getattr(bags, "options", {})


def _init_cli_context(cmd_bags: Any, default_cmd: str) -> Tuple[CmdBags, str, Any]:
    guard_dispatch("vscode-support")
    bags = _normalize_bags(cmd_bags, default_cmd)
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    return bags, proj_root, SettingsProjector()


def status(cmd_bags: Any) -> int:
    """檢視 `.vscode/settings.json` 託管狀態、`current-site-packages` 連結與已編譯 Schema 清單。"""
    bags, proj_root, projector = _init_cli_context(cmd_bags, "status")
    info = projector.get_status(proj_root)

    if _is_json_mode(bags):
        log(json.dumps(info, indent=2, ensure_ascii=False))
        return 0

    log("======================================================================")
    log("YS-Codebase VS Code Workspace Support Status")
    log("======================================================================")
    log(f"Project Root        : {info['project_root']}")
    log(f".vscode/ Exists     : {info['vscode_dir_exists']}")
    log(f"Settings Managed    : {info['settings_managed']}")
    log(f"Stable Venv Link    : {info['stable_link_path']} (active={info['stable_link_active']})")
    if info.get("stable_link_target"):
        log(f"Link Target         : {info['stable_link_target']}")
    log(f"Extra Paths         : {', '.join(info['managed_extra_paths']) if info['managed_extra_paths'] else '(none)'}")
    log(f"Managed Schemas     : {info['managed_schema_count']} schema(s)")
    for s_url in info["managed_schemas"]:
        log(f"  - {s_url}")
    log("======================================================================")
    return 0


def sync(cmd_bags: Any) -> int:
    """重新建立穩定 `site-packages` 連結、編譯全模組單檔 JSON Schema 並軟合併 `.vscode/settings.json`。"""
    bags, proj_root, projector = _init_cli_context(cmd_bags, "sync")
    ok = projector.sync_vscode_settings(proj_root)
    info = projector.get_status(proj_root)
    info["synced"] = ok

    if _is_json_mode(bags):
        log(json.dumps(info, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    if ok:
        log(
            f"[vscode-support] Synced .vscode/settings.json and {info['managed_schema_count']} JSON schema(s) at '{proj_root}'."
        )
        return 0
    log(f"[vscode-support] Failed or skipped syncing VS Code settings at '{proj_root}'.", stream="stderr")
    return 1


def revert(cmd_bags: Any) -> int:
    """依據 `_yscb_managed` 乾淨剔除所有 YSCB 注入之 VS Code 設定，並移除 `.vscode/schemas/` 與穩定連結。"""
    bags, proj_root, projector = _init_cli_context(cmd_bags, "revert")
    ok = projector.revert_vscode_settings(proj_root)
    err_msg = getattr(projector, "last_revert_error", None)

    if _is_json_mode(bags):
        payload: Dict[str, Any] = {"project_root": proj_root, "reverted": ok}
        if err_msg:
            payload["error"] = err_msg
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if err_msg else 0

    if ok:
        log(f"[vscode-support] Reverted YSCB managed VS Code settings and removed schemas at '{proj_root}'.")
        return 0
    if err_msg:
        log(f"[vscode-support] {err_msg}", stream="stderr")
        return 1
    log(f"[vscode-support] No active _yscb_managed settings found to revert at '{proj_root}'.")
    return 0
