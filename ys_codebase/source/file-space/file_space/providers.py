"""
Dynamic completion and documentation token providers for the file-space module.
Provides unified Markdown table rendering for both `FILE_SPACE_REGISTERED_TABLE` and `KNOWLEDGE_DB_SPACE`.
100% Python Standard Library, Zero Third-Party Dependency.
"""
import json
from pathlib import Path
from typing import Any, List, Optional, Set

from .manager import FileSpaceManager


def _collect_space_weights(raw_weights: Any, target: Set[str]) -> bool:
    if not isinstance(raw_weights, dict):
        return False
    found = False
    for k in raw_weights:
        k_str = str(k)
        if not k_str.startswith("_"):
            target.add(k_str)
            found = True
    return found


def _escape_md_cell(text: str) -> str:
    return (
        str(text)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )


def _resolve_knowledge_db_indexed_space_names() -> Optional[Set[str]]:
    """
    Resolve the set of space names explicitly configured in `knowledge-db` `space_weights`.
    Returns `None` if no `knowledge-db` space_weights configuration is available (e.g. isolated unit test mocks).
    """
    weighted_names: Set[str] = set()
    found_cfg = False
    try:
        from core import contributes as core_contributes

        raw_merged = core_contributes.get("knowledge-db")
        if isinstance(raw_merged, dict):
            if _collect_space_weights(raw_merged.get("space_weights"), weighted_names):
                found_cfg = True
        elif isinstance(raw_merged, list):
            for item in raw_merged:
                data = item.get("data", item) if isinstance(item, dict) else {}
                if isinstance(data, dict) and _collect_space_weights(
                    data.get("space_weights"), weighted_names
                ):
                    found_cfg = True
    except Exception:
        pass

    try:
        from core import uri

        res = uri.resolve("config://knowledge-db/contribute.json", interactive=False)
        if res:
            cfg_path = Path(res).resolve()
            if cfg_path.is_file():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                if isinstance(file_data, dict) and _collect_space_weights(
                    file_data.get("space_weights"), weighted_names
                ):
                    found_cfg = True
    except Exception:
        pass

    return weighted_names if found_cfg else None


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
        origin_str = _escape_md_cell(
            getattr(cfg, "origin_display", getattr(cfg.origin, "value", str(cfg.origin)))
        )
        policy_str = _escape_md_cell(getattr(cfg.hash_policy, "value", str(cfg.hash_policy)))
        watch_str = "啟用" if cfg.watch else "停用"
        desc = _escape_md_cell(cfg.description or "-")
        safe_name = _escape_md_cell(name)
        lines.append(
            f"| `{safe_name}` | `{origin_str}` | `{policy_str}` | {watch_str} | {desc} |"
        )
    return "\n".join(lines)


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    Render a Markdown table summarizing registered workspaces (include paths & file patterns) for `KNOWLEDGE_DB_SPACE`.
    Only includes spaces that have explicit weights configured in `knowledge-db` (`space_weights`).
    """
    mgr = None
    try:
        mgr = FileSpaceManager(core_context=context)
        spaces = mgr.load_spaces()
    except Exception:
        spaces = {}

    if spaces and mgr is not None and type(mgr).__module__.startswith("file_space"):
        indexed_names = _resolve_knowledge_db_indexed_space_names()
        if indexed_names is not None:
            spaces = {k: v for k, v in spaces.items() if k in indexed_names}

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
        name_badge = f"**`{_escape_md_cell(sp_name)}`**"
        origin_label = f"`{_escape_md_cell(getattr(sp, 'origin_display', getattr(sp.origin, 'value', str(sp.origin))))}`"

        inc_parts: List[str] = [f"`{_escape_md_cell(str(inc))}`" for inc in sp.include]
        if sp.file_patterns:
            pats = ", ".join(_escape_md_cell(str(p)) for p in sp.file_patterns)
            inc_parts.append(f"*(過濾: `{pats}`)*")

        scope_desc = "<br/>".join(inc_parts) if inc_parts else "*(全目錄)*"
        desc = _escape_md_cell(sp.description or "*(無描述)*")
        lines.append(f"| {name_badge} | {origin_label} | {scope_desc} | {desc} |")

    return "\n".join(lines)
