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
    NONE = 0
    LOGIC = auto()            # Pure in-memory / unit logic test
    HOST_CLI = auto()         # Subprocess invocation required
    NETWORK = auto()          # Active network connection required
    ISOLATED_SANDBOX = auto() # Dedicated per-test isolated sandbox required

def is_network_available(timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen("https://raw.githubusercontent.com", timeout=timeout)
        return True
    except Exception:
        return False

def require(requirement: Requirement) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Condition requirement decorator.
    1. Attaches __requirement__ metadata for test suite filtering (e.g. --type=logic).
    2. Automatically triggers unittest.SkipTest if runtime environment lacks requirement.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            net_available = globals().get("is_network_available", is_network_available)
            if Requirement.NETWORK in requirement and not net_available():
                raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")
            return func(self, *args, **kwargs)
        
        # Attach requirement attribute to wrapper and original func for inspection
        setattr(wrapper, "__requirement__", requirement)
        setattr(func, "__requirement__", requirement)
        return wrapper
    return decorator
