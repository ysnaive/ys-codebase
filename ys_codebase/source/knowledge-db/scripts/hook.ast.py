"""
AST lifecycle hook for `module:knowledge-db` (`scripts/hook.ast.py`).
Ensures all spaces configured in `knowledge-db` (`space_weights` and `spaces`) are declaratively
and dynamically registered as target spaces in `ASTEngine`.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


def _collect_spaces_from_entry(entry: Any, out: List[str]) -> None:
    if not isinstance(entry, dict):
        return
    sw = entry.get("space_weights")
    if isinstance(sw, dict):
        for k in sw.keys():
            s = str(k).strip()
            if s and not s.startswith("_") and s not in out:
                out.append(s)
    sp_map = entry.get("spaces")
    if isinstance(sp_map, dict):
        for s_name, s_val in sp_map.items():
            if isinstance(s_val, dict) and s_val.get("weight") is None and "space_weights" in entry:
                continue
            s = str(s_name).strip()
            if s and not s.startswith("_") and s not in out:
                out.append(s)


def on_register_ast_spaces(context: Any = None, **kwargs: Any) -> Dict[str, List[str]]:
    """
    Triggered when `ASTEngine` / `SemanticBundler` resolves target spaces (`on_register_ast_spaces`).
    Returns all weighted spaces configured for `knowledge-db` across module contributes and project config.
    """
    spaces: List[str] = []
    try:
        from core import contributes as core_contributes

        raw_kdb = core_contributes.get("knowledge-db")
        if isinstance(raw_kdb, dict):
            _collect_spaces_from_entry(raw_kdb, spaces)
        elif isinstance(raw_kdb, list):
            for item in raw_kdb:
                data = item.get("data", item) if isinstance(item, dict) else {}
                _collect_spaces_from_entry(data, spaces)
    except Exception:
        pass

    try:
        from core import uri

        res = uri.resolve("config://knowledge-db/contribute.json", interactive=False)
        if res and not str(res).startswith("!undefined"):
            cfg_file = Path(str(res)).resolve()
            if cfg_file.is_file():
                with open(cfg_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                _collect_spaces_from_entry(file_data, spaces)
    except Exception:
        pass

    if isinstance(context, dict) and callable(context.get("register_spaces")) and spaces:
        try:
            context["register_spaces"](spaces)
        except Exception:
            pass

    return {"spaces": spaces}
