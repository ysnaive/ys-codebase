"""
AST lifecycle hook for `module:knowledge-db` (`scripts/hook.ast.py`).
Ensures all spaces configured in `knowledge-db` (`space_weights` and `spaces`) are declaratively
and dynamically registered as target spaces in `ASTEngine`.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from knowledge_db.engine import collect_spaces_from_config_entry as _collect_spaces_from_entry


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
