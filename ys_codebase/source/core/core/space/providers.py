"""
Dynamic documentation token providers for `core.space`.
Provides Markdown table rendering for `FILE_SPACE_REGISTERED_TABLE` and `KNOWLEDGE_DB_SPACE`.
100% Python Standard Library, Zero Third-Party Dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .registry import SpaceRegistry, get_default_registry
from .schema import SpaceConfig


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


def _resolve_registry_from_context(context: Optional[Any] = None) -> SpaceRegistry:
    proj_root: Optional[Path] = None
    yscb_dir: Optional[Path] = None
    if isinstance(context, dict):
        pr = context.get("project_root") or context.get("workspace_root")
        yr = context.get("yscb_root") or context.get("yscb_dir")
        if pr:
            proj_root = Path(str(pr)).resolve()
        if yr:
            yscb_dir = Path(str(yr)).resolve()
    elif context is not None:
        pr = getattr(context, "project_root", None) or getattr(context, "workspace_root", None)
        yr = getattr(context, "yscb_root", None) or getattr(context, "yscb_dir", None)
        if pr:
            proj_root = Path(str(pr)).resolve()
        if yr:
            yscb_dir = Path(str(yr)).resolve()
    return get_default_registry(project_root=proj_root, yscb_dir=yscb_dir)


def _resolve_knowledge_db_indexed_space_names(
    context: Optional[Any] = None,
) -> Optional[Set[str]]:
    """
    Resolve the set of space names (qualified or short) configured in `knowledge-db` `space_weights`.
    Honors explicit `context` (`project_root` / `yscb_dir`) via `uri.host_scope` to prevent cross-sandbox leakage.
    Returns `None` if no `knowledge-db` space_weights configuration is available.
    """
    from contextlib import nullcontext

    proj_root: Optional[str] = None
    yscb_dir: Optional[str] = None
    if isinstance(context, dict):
        pr = context.get("project_root") or context.get("workspace_root")
        yr = context.get("yscb_dir") or context.get("yscb_root")
        if pr:
            proj_root = str(Path(str(pr)).resolve())
        if yr:
            yscb_dir = str(Path(str(yr)).resolve())
    elif context is not None:
        pr = getattr(context, "project_root", None) or getattr(context, "workspace_root", None)
        yr = getattr(context, "yscb_dir", None) or getattr(context, "yscb_root", None)
        if pr:
            proj_root = str(Path(str(pr)).resolve())
        if yr:
            yscb_dir = str(Path(str(yr)).resolve())

    weighted_names: Set[str] = set()
    found_cfg = False
    try:
        from core import contributes as core_contributes, uri

        scope_cm = (
            uri.host_scope(
                host_dir=proj_root or yscb_dir,
                yscb_dir=yscb_dir,
            )
            if (proj_root or yscb_dir)
            else nullcontext()
        )
        with scope_cm:
            try:
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
            except (OSError, ValueError, KeyError):
                pass

            try:
                res = uri.resolve("config://knowledge-db/contribute.json", interactive=False)
                if res and not str(res).startswith("!undefined"):
                    cfg_path = Path(str(res)).resolve()
                    if cfg_path.is_file():
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            file_data = json.load(f)
                        if isinstance(file_data, dict) and _collect_space_weights(
                            file_data.get("space_weights"), weighted_names
                        ):
                            found_cfg = True
            except (OSError, ValueError, KeyError):
                pass
    except (ImportError, OSError, ValueError):
        pass

    return weighted_names if found_cfg else None


def get_registered_file_spaces_table(context: Optional[Any] = None) -> str:
    """
    Render a Markdown table summarizing registered workspaces (policy & watch status) for skill compilation.
    """
    try:
        reg = _resolve_registry_from_context(context)
        spaces: List[SpaceConfig] = reg.list_spaces()
    except Exception:
        spaces = []

    if not spaces:
        return (
            "| 空間名稱 | 來源 | 雜湊策略 | 監聽 | 說明 |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            "| *(尚未註冊空間)* | - | - | - | - |"
        )

    lines = [
        "| 空間名稱 | 來源 | 雜湊策略 | 監聽 | 說明 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for cfg in spaces:
        origin_str = _escape_md_cell(cfg.owner)
        policy_str = _escape_md_cell(getattr(cfg.hash_policy, "value", str(cfg.hash_policy)))
        watch_str = "啟用" if cfg.watch else "停用"
        desc = _escape_md_cell(cfg.description or "-")
        safe_name = _escape_md_cell(cfg.qualified_name)
        lines.append(
            f"| `{safe_name}` | `{origin_str}` | `{policy_str}` | {watch_str} | {desc} |"
        )
    return "\n".join(lines)


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    Render a Markdown table summarizing registered workspaces (entries & include rules) for `KNOWLEDGE_DB_SPACE`.
    Filters by `knowledge-db` `space_weights` (matching either `qualified_name` or `short_name`) when configured.
    """
    _ = kwargs
    try:
        reg = _resolve_registry_from_context(context)
        spaces: List[SpaceConfig] = reg.list_spaces()
    except Exception:
        spaces = []

    if spaces:
        indexed_names = _resolve_knowledge_db_indexed_space_names(context=context)
        if indexed_names is not None:
            spaces = [
                sp
                for sp in spaces
                if sp.qualified_name in indexed_names or sp.short_name in indexed_names
            ]

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

    # Group by short_name or qualified_name in deterministic order
    for sp in sorted(spaces, key=lambda s: (s.short_name, s.qualified_name)):
        display_name = sp.short_name
        name_badge = f"**`{_escape_md_cell(display_name)}`** (`{_escape_md_cell(sp.qualified_name)}`)"
        origin_label = f"`{_escape_md_cell(sp.owner)}`"

        inc_parts: List[str] = [f"`{_escape_md_cell(str(ent))}`" for ent in sp.entries]
        if sp.compose:
            inc_parts.extend([f"`compose:{_escape_md_cell(str(c))}`" for c in sp.compose])
        if sp.include:
            pats = ", ".join(_escape_md_cell(str(getattr(p, "raw", p))) for p in sp.include)
            inc_parts.append(f"*(過濾: `{pats}`)*")

        scope_desc = "<br/>".join(inc_parts) if inc_parts else "*(全目錄)*"
        desc = _escape_md_cell(sp.description or "*(無描述)*")
        lines.append(f"| {name_badge} | {origin_label} | {scope_desc} | {desc} |")

    return "\n".join(lines)
