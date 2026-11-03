"""
CLI Router & Subcommand Entry Points for `module:vscode-support@1.0.0.0`.
Aligned with `core.commands.CmdBags` contract and `contributes/core.json`.
"""

import json
import os
import sys
from typing import Any, Dict, List

from core import uri
from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch


def _ensure_module_path() -> None:
    module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if module_root not in sys.path:
        sys.path.insert(0, module_root)


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


def status(cmd_bags: Any) -> int:
    """檢視 `.vscode/settings.json` 託管狀態、`current-site-packages` 連結與已編譯 Schema 清單。"""
    guard_dispatch("vscode-support")
    _ensure_module_path()
    bags = _normalize_bags(cmd_bags, "status")
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    projector = SettingsProjector()
    info = projector.get_status(proj_root)

    if _is_json_mode(bags):
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0

    print("======================================================================")
    print("YS-Codebase VS Code Workspace Support Status")
    print("======================================================================")
    print(f"Project Root        : {info['project_root']}")
    print(f".vscode/ Exists     : {info['vscode_dir_exists']}")
    print(f"Settings Managed    : {info['settings_managed']}")
    print(f"Stable Venv Link    : {info['stable_link_path']} (active={info['stable_link_active']})")
    if info.get("stable_link_target"):
        print(f"Link Target         : {info['stable_link_target']}")
    print(f"Extra Paths         : {', '.join(info['managed_extra_paths']) if info['managed_extra_paths'] else '(none)'}")
    print(f"Managed Schemas     : {info['managed_schema_count']} schema(s)")
    for s_url in info["managed_schemas"]:
        print(f"  - {s_url}")
    print("======================================================================")
    return 0


def sync(cmd_bags: Any) -> int:
    """重新建立穩定 `site-packages` 連結、編譯全模組單檔 JSON Schema 並軟合併 `.vscode/settings.json`。"""
    guard_dispatch("vscode-support")
    _ensure_module_path()
    bags = _normalize_bags(cmd_bags, "sync")
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    projector = SettingsProjector()
    ok = projector.sync_vscode_settings(proj_root)
    info = projector.get_status(proj_root)
    info["synced"] = ok

    if _is_json_mode(bags):
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    if ok:
        print(
            f"[vscode-support] Synced .vscode/settings.json and {info['managed_schema_count']} JSON schema(s) at '{proj_root}'."
        )
        return 0
    print(f"[vscode-support] Failed or skipped syncing VS Code settings at '{proj_root}'.", file=sys.stderr)
    return 1


def revert(cmd_bags: Any) -> int:
    """依據 `_yscb_managed` 乾淨剔除所有 YSCB 注入之 VS Code 設定，並移除 `.vscode/schemas/` 與穩定連結。"""
    guard_dispatch("vscode-support")
    _ensure_module_path()
    bags = _normalize_bags(cmd_bags, "revert")
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    projector = SettingsProjector()
    ok = projector.revert_vscode_settings(proj_root)

    if _is_json_mode(bags):
        print(json.dumps({"project_root": proj_root, "reverted": ok}, indent=2, ensure_ascii=False))
        return 0

    if ok:
        print(f"[vscode-support] Reverted YSCB managed VS Code settings and removed schemas at '{proj_root}'.")
    else:
        print(f"[vscode-support] No active _yscb_managed settings found to revert at '{proj_root}'.")
    return 0

