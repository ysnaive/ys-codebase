"""
Capability requirement flags and @require condition decorator.
Inspired by uitk.net RequireAttribute & TestRequirement.
"""
from enum import Flag, auto
from typing import Callable, Any
import functools
import unittest
import urllib.request

class Requirement(Flag):
    """
    Test capability requirement and classification flags.
    Supports 4-tier taxonomy + orthogonal sandbox isolation flag.
    """
    NONE = 0
    LOGIC = auto()            # Pure in-memory / unit logic test (default included)
    ENV = auto()              # Inter-module, DI, VFS environment test (default included)
    HOST_CLI = ENV            # Alias for backward compatibility
    NETWORK = auto()          # Network required test
    WORKFLOW = auto()         # Multi-step composite workflow / E2E test (default excluded)
    PERF = auto()             # Performance benchmark / stress test (default excluded)
    PERFORMANCE = PERF        # Alias
    STRESS = PERF             # Alias
    ISOLATED_SANDBOX = auto() # Dedicated per-test isolated sandbox required (orthogonal)

    # Classification composite masks
    ALL_DEFAULT = LOGIC | ENV
    ALL = LOGIC | ENV | WORKFLOW | PERF

def is_network_available(timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen("https://raw.githubusercontent.com", timeout=timeout)
        return True
    except Exception:
        return False

def require(requirement: Requirement) -> Callable[[Any], Any]:
    """
    Condition requirement decorator.
    Supports decorating both test methods and test classes.
    1. Attaches __requirement__ metadata for test suite filtering (e.g. --type=logic).
    2. Automatically triggers unittest.SkipTest if runtime environment lacks requirement.
    """
    def decorator(target: Any) -> Any:
        if isinstance(target, type):
            setattr(target, "__requirement__", requirement)
            return target

        @functools.wraps(target)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            net_available = globals().get("is_network_available", is_network_available)
            req_val = requirement.value if hasattr(requirement, "value") else int(requirement)
            if bool(req_val & Requirement.NETWORK.value) and not net_available():
                raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")
            return target(self, *args, **kwargs)
        
        # Attach requirement attribute to wrapper and original func for inspection
        setattr(wrapper, "__requirement__", requirement)
        setattr(target, "__requirement__", requirement)
        return wrapper
    return decorator
