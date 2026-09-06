"""
Core Module Package Exports.
"""
from core import uri
from core import semver
from core.context import ExecutionContext
from core.engine import AtomicEngine
from core.contributes import ContributesAggregator, print_global_help
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

__all__ = [
    "uri",
    "semver",
    "ExecutionContext",
    "AtomicEngine",
    "ContributesAggregator",
    "print_global_help",
    "Installer",
    "generate_internal_gitignore",
    "UpdateChecker",
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
]


