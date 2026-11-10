"""
Core Module Package Exports (PEP 562 Lazy Loading Architecture).
100% Python Standard Library.
"""
import importlib
import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core import uri
    from core import semver
    from core import context
    from core.context import (
        ExecutionContext,
        RuntimeContext,
        RuntimeScope,
        bind_runtime_context,
        get_runtime_context,
        invalidate_host_caches,
    )
    from core import loader
    from core import service_contract
    from core.service_contract import BaseServiceWorkerContract, BaseServiceWorker
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
    from core import config
    from core import validator
    from core import telemetry
    from core import locale
    from core import gitignore
    from core import file_lock
    from core import space
    from core import log

_MODULE_MAP = types.MappingProxyType({
    "uri": ("core.uri", None),
    "semver": ("core.semver", None),
    "context": ("core.context", None),
    "ExecutionContext": ("core.context", "ExecutionContext"),
    "RuntimeContext": ("core.context", "RuntimeContext"),
    "RuntimeScope": ("core.context", "RuntimeScope"),
    "bind_runtime_context": ("core.context", "bind_runtime_context"),
    "get_runtime_context": ("core.context", "get_runtime_context"),
    "invalidate_host_caches": ("core.context", "invalidate_host_caches"),
    "loader": ("core.loader", None),
    "service_contract": ("core.service_contract", None),
    "BaseServiceWorkerContract": ("core.service_contract", "BaseServiceWorkerContract"),
    "BaseServiceWorker": ("core.service_contract", "BaseServiceWorker"),
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
    "telemetry": ("core.telemetry", None),
    "locale": ("core.locale", None),
    "gitignore": ("core.gitignore", None),
    "file_lock": ("core.file_lock", None),
    "space": ("core.space", None),
    "log": ("core.log", None),
})


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


__all__ = (
    "uri",
    "semver",
    "context",
    "ExecutionContext",
    "RuntimeContext",
    "RuntimeScope",
    "bind_runtime_context",
    "get_runtime_context",
    "invalidate_host_caches",
    "loader",
    "service_contract",
    "BaseServiceWorkerContract",
    "BaseServiceWorker",
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
    "telemetry",
    "locale",
    "gitignore",
    "file_lock",
    "space",
    "log",
)
