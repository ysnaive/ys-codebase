"""
Dynamic completion and documentation token providers for the file-space module.
"""
from typing import Any, List, Optional

from .manager import FileSpaceManager


def get_file_space_names(context: Optional[Any] = None) -> List[str]:
    """
    Return registered workspace names for CLI argument autocompletion.
    """
    try:
        mgr = FileSpaceManager()
        return mgr.list_spaces()
    except Exception:
        return ["source", "docs", "plans"]


def get_registered_file_spaces_table(context: Optional[Any] = None) -> str:
    """
    Render a Markdown table summarizing registered workspaces for skill compilation.
    """
    try:
        mgr = FileSpaceManager()
        spaces = mgr.get_all_spaces()
    except Exception:
        spaces = {}

    if not spaces:
        return "| 空間名稱 | 來源 | 雜湊策略 | 監聽 | 說明 |\n| :--- | :--- | :--- | :--- | :--- |\n| *(尚未註冊空間)* | - | - | - | - |"

    lines = [
        "| 空間名稱 | 來源 | 雜湊策略 | 監聽 | 說明 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for name, cfg in spaces.items():
        origin_str = getattr(cfg, "origin_display", getattr(cfg.origin, "value", str(cfg.origin)))
        policy_str = getattr(cfg.hash_policy, "value", str(cfg.hash_policy))
        watch_str = "啟用" if cfg.watch else "停用"
        desc = cfg.description or "-"
        lines.append(
            f"| `{name}` | `{origin_str}` | `{policy_str}` | {watch_str} | {desc} |"
        )
    return "\n".join(lines)


get_space_names = get_file_space_names
get_registered_spaces_table = get_registered_file_spaces_table
