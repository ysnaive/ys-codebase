"""
Dialect registry and factory for module:ast.
"""

from typing import Any, Dict

from core.context import get_runtime_context

from .base import DialectAdapter
from .c import CDialect
from .cpp import CppDialect
from .csharp import CSharpDialect
from .javascript import JavaScriptDialect
from .markdown import MarkdownDialect
from .python import PythonDialect
from .typescript import TypeScriptDialect

_DEFAULT_DIALECT = DialectAdapter()


def _create_default_dialects() -> Dict[str, DialectAdapter]:
    return {
        "python": PythonDialect(),
        "c_sharp": CSharpDialect(),
        "csharp": CSharpDialect(),
        "cs": CSharpDialect(),
        "cpp": CppDialect(),
        "c++": CppDialect(),
        "c": CDialect(),
        "javascript": JavaScriptDialect(),
        "js": JavaScriptDialect(),
        "typescript": TypeScriptDialect(),
        "ts": TypeScriptDialect(),
        "markdown": MarkdownDialect(),
        "md": MarkdownDialect(),
    }


def _get_dialect_instances() -> Dict[str, DialectAdapter]:
    ctx = get_runtime_context()
    if "_DIALECT_INSTANCES" in globals():
        ext_inst = globals().pop("_DIALECT_INSTANCES")
        if isinstance(ext_inst, dict):
            ctx.set_module_state("ast.dialects.instances", ext_inst)
    return ctx.get_module_state("ast.dialects.instances", _create_default_dialects)


def __getattr__(name: str) -> Any:
    if name == "_DIALECT_INSTANCES":
        return _get_dialect_instances()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_dialect(lang_name: str) -> DialectAdapter:
    """Return the DialectAdapter instance for `lang_name` (falls back to base DialectAdapter)."""
    if not lang_name:
        return _DEFAULT_DIALECT
    key = str(lang_name).strip().lower()
    return _get_dialect_instances().get(key, _DEFAULT_DIALECT)


def register_dialect(lang_name: str, adapter: DialectAdapter) -> None:
    """Register or override a custom DialectAdapter for `lang_name`."""
    if lang_name and isinstance(adapter, DialectAdapter):
        _get_dialect_instances()[str(lang_name).strip().lower()] = adapter


__all__ = [
    "DialectAdapter",
    "PythonDialect",
    "CSharpDialect",
    "CppDialect",
    "CDialect",
    "JavaScriptDialect",
    "TypeScriptDialect",
    "MarkdownDialect",
    "get_dialect",
    "register_dialect",
]
