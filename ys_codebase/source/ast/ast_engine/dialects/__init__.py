"""
Dialect registry and factory for module:ast.
"""

from typing import Dict

from .base import DialectAdapter
from .c import CDialect
from .cpp import CppDialect
from .csharp import CSharpDialect
from .javascript import JavaScriptDialect
from .markdown import MarkdownDialect
from .python import PythonDialect
from .typescript import TypeScriptDialect

_DIALECT_INSTANCES: Dict[str, DialectAdapter] = {
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

_DEFAULT_DIALECT = DialectAdapter()


def get_dialect(lang_name: str) -> DialectAdapter:
    """Return the DialectAdapter instance for `lang_name` (falls back to base DialectAdapter)."""
    if not lang_name:
        return _DEFAULT_DIALECT
    key = str(lang_name).strip().lower()
    return _DIALECT_INSTANCES.get(key, _DEFAULT_DIALECT)


def register_dialect(lang_name: str, adapter: DialectAdapter) -> None:
    """Register or override a custom DialectAdapter for `lang_name`."""
    if lang_name and isinstance(adapter, DialectAdapter):
        _DIALECT_INSTANCES[str(lang_name).strip().lower()] = adapter


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
