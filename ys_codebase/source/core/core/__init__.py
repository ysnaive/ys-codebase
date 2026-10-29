"""
Core Module Package Exports (PEP 562 Lazy Loading Architecture).
100% Python Standard Library.
"""
from typing import TYPE_CHECKING
import importlib

if TYPE_CHECKING:
    from core import uri
    from core import semver
    from core.context import ExecutionContext
    from core.engine import AtomicEngine
    from core.contributes import ContributesAggregator
    from core.installer import Installer, generate_internal_gitignore
    from core import update_checker
    from core.update_checker import UpdateChecker
    from core import events
    from core import symbols
    from core.symbols import resolve_callable, parse_code_func_uri, SymbolError, InvalidSymbolURIError, SymbolNotFoundError
    from core import pip_manager
    from core.pip_manager import PipManager, PipInstallError
    from core import guard
    from core.guard import guard_dispatch
    from core import vfs
    from core.vfs import VirtualPath
    from core import platform
    from core import commands
    from core import telemetry
    from core import locale

_MODULE_MAP = {
    "uri": ("core.uri", None),
    "semver": ("core.semver", None),
    "ExecutionContext": ("core.context", "ExecutionContext"),
    "AtomicEngine": ("core.engine", "AtomicEngine"),
    "ContributesAggregator": ("core.contributes", "ContributesAggregator"),
    "Installer": ("core.installer", "Installer"),
    "generate_internal_gitignore": ("core.installer", "generate_internal_gitignore"),
    "UpdateChecker": ("core.update_checker", "UpdateChecker"),
    "update_checker": ("core.update_checker", None),
    "events": ("core.events", None),
    "symbols": ("core.symbols", None),
    "resolve_callable": ("core.symbols", "resolve_callable"),
    "parse_code_func_uri": ("core.symbols", "parse_code_func_uri"),
    "SymbolError": ("core.symbols", "SymbolError"),
    "InvalidSymbolURIError": ("core.symbols", "InvalidSymbolURIError"),
    "SymbolNotFoundError": ("core.symbols", "SymbolNotFoundError"),
    "pip_manager": ("core.pip_manager", None),
    "PipManager": ("core.pip_manager", "PipManager"),
    "PipInstallError": ("core.pip_manager", "PipInstallError"),
    "guard": ("core.guard", None),
    "guard_dispatch": ("core.guard", "guard_dispatch"),
    "vfs": ("core.vfs", None),
    "VirtualPath": ("core.vfs", "VirtualPath"),
    "platform": ("core.platform", None),
    "commands": ("core.commands", None),
    "config": ("core.config", None),
    "validator": ("core.validator", None),
    "ide_projector": ("core.ide_projector", None),
    "telemetry": ("core.telemetry", None),
    "locale": ("core.locale", None),
}


def __getattr__(name: str):
    """PEP 562 動態按需載入屬性與子模組。"""
    if name in _MODULE_MAP:
        mod_name, attr_name = _MODULE_MAP[name]
        mod = importlib.import_module(mod_name)
        val = getattr(mod, attr_name) if attr_name else mod
        globals()[name] = val
        return val
    raise AttributeError(f"module 'core' has no attribute '{name}'")


def __dir__():
    return sorted(list(globals().keys()) + list(_MODULE_MAP.keys()))


__all__ = [
    "uri",
    "semver",
    "ExecutionContext",
    "AtomicEngine",
    "ContributesAggregator",
    "Installer",
    "generate_internal_gitignore",
    "UpdateChecker",
    "update_checker",
    "events",
    "symbols",
    "resolve_callable",
    "parse_code_func_uri",
    "SymbolError",
    "InvalidSymbolURIError",
    "SymbolNotFoundError",
    "pip_manager",
    "PipManager",
    "PipInstallError",
    "guard",
    "guard_dispatch",
    "vfs",
    "VirtualPath",
    "platform",
    "commands",
    "config",
    "validator",
    "ide_projector",
    "telemetry",
    "locale",
]
