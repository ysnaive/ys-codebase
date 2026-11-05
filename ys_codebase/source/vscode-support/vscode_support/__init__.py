"""
VS Code Workspace Support Module (`module:vscode-support@1.0.0.0`).
PEP 562 Lazy Loading Architecture. 100% Python Standard Library.
"""

from typing import TYPE_CHECKING
import importlib

__version__ = "1.0.0.3"

if TYPE_CHECKING:
    from vscode_support.projector import SettingsProjector
    from vscode_support.schema_compiler import SchemaCompiler

_MODULE_MAP = {
    "SettingsProjector": ("vscode_support.projector", "SettingsProjector"),
    "SchemaCompiler": ("vscode_support.schema_compiler", "SchemaCompiler"),
    "projector": ("vscode_support.projector", None),
    "schema_compiler": ("vscode_support.schema_compiler", None),
}


def __getattr__(name: str):
    if name in _MODULE_MAP:
        mod_name, attr_name = _MODULE_MAP[name]
        mod = importlib.import_module(mod_name)
        val = getattr(mod, attr_name) if attr_name else mod
        globals()[name] = val
        return val
    raise AttributeError(f"module 'vscode_support' has no attribute '{name}'")


def __dir__():
    return sorted(list(globals().keys()) + list(_MODULE_MAP.keys()))


__all__ = [
    "__version__",
    "SettingsProjector",
    "SchemaCompiler",
    "projector",
    "schema_compiler",
]

