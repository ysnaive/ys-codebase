"""
AST lifecycle hook for `module:knowledge-db` (`scripts/hook.ast.py`).
Ensures all spaces configured in `knowledge-db` (`space_weights`) are declaratively
and dynamically registered as target spaces in `ASTEngine`.
"""

from typing import Any, Dict, List


def on_register_ast_spaces(context: Any = None, **kwargs: Any) -> Dict[str, List[str]]:
    """
    Triggered when `ASTEngine` / `SemanticBundler` resolves target spaces (`on_register_ast_spaces`).
    Returns all weighted spaces configured for `knowledge-db`.
    """
    spaces: List[str] = []
    try:
        from core import contributes as core_contributes

        raw_kdb = core_contributes.get("knowledge-db")
        if isinstance(raw_kdb, dict) and isinstance(raw_kdb.get("space_weights"), dict):
            for k in raw_kdb["space_weights"].keys():
                s = str(k).strip()
                if s and not s.startswith("_") and s not in spaces:
                    spaces.append(s)
    except Exception:
        pass

    if isinstance(context, dict) and callable(context.get("register_spaces")) and spaces:
        try:
            context["register_spaces"](spaces)
        except Exception:
            pass

    return {"spaces": spaces}
