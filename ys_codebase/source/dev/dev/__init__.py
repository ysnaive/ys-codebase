"""
Dev Developer Tools Module for YS-Codebase (PEP 562 Lazy Loading Architecture).
100% Python Standard Library.
"""
from typing import TYPE_CHECKING, Any
import importlib

if TYPE_CHECKING:
    from dev.scaffold import Scaffolder
    from dev.checker import Checker
    from dev.builder import Builder
    from dev.tester import Tester
    from dev.releaser import Releaser
    from dev import testing

_MODULE_MAP = {
    "Scaffolder": ("dev.scaffold", "Scaffolder"),
    "Checker": ("dev.checker", "Checker"),
    "Builder": ("dev.builder", "Builder"),
    "Tester": ("dev.tester", "Tester"),
    "Releaser": ("dev.releaser", "Releaser"),
    "testing": ("dev.testing", None),
}


def __getattr__(name: str) -> Any:
    """PEP 562 動態按需載入屬性與子模組。"""
    if name in _MODULE_MAP:
        mod_name, attr_name = _MODULE_MAP[name]
        mod = importlib.import_module(mod_name)
        val = getattr(mod, attr_name) if attr_name else mod
        globals()[name] = val
        return val
    raise AttributeError(f"module 'dev' has no attribute '{name}'")


def __dir__():
    return sorted(list(globals().keys()) + list(_MODULE_MAP.keys()))


__all__ = ["Scaffolder", "Checker", "Builder", "Tester", "Releaser", "testing"]
