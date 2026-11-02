"""
Dynamic completion and documentation token providers for the file-space module.
Provides unified Markdown table rendering for both `FILE_SPACE_REGISTERED_TABLE` and `KNOWLEDGE_DB_SPACE`.
100% Python Standard Library, Zero Third-Party Dependency.
"""
from typing import Any, List, Optional

from .manager import FileSpaceManager


def get_registered_file_spaces_table(context: Optional[Any] = None) -> str:
    """
    Render a Markdown table summarizing registered workspaces (policy & watch status) for skill compilation.
    """
    try:
        mgr = FileSpaceManager(core_context=context)
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


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    Render a Markdown table summarizing registered workspaces (include paths & file patterns) for `KNOWLEDGE_DB_SPACE`.
    """
    try:
        mgr = FileSpaceManager(core_context=context)
        spaces = mgr.load_spaces()
    except Exception:
        spaces = {}

    if not spaces:
        return (
            "| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| - | - | *(目前無已註冊空間)* | - |"
        )

    lines = [
        "| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for sp_name, sp in sorted(spaces.items()):
        name_badge = f"**`{sp_name}`**"
        origin_label = f"`{getattr(sp, 'origin_display', getattr(sp.origin, 'value', str(sp.origin)))}`"

        inc_parts: List[str] = [f"`{inc}`" for inc in sp.include]
        if sp.file_patterns:
            pat_desc = f"*(過濾: `{', '.join(sp.file_patterns)}`)*"
            inc_parts.append(pat_desc)

        scope_desc = "<br/>".join(inc_parts) if inc_parts else "*(全目錄)*"
        desc = sp.description or "*(無描述)*"
        lines.append(f"| {name_badge} | {origin_label} | {scope_desc} | {desc} |")

    return "\n".join(lines)
