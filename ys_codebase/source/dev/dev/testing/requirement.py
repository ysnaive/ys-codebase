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
    SANDBOX = auto()
    HOST_CLI = auto()
    NETWORK = auto()

def is_network_available(timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen("https://raw.githubusercontent.com", timeout=timeout)
        return True
    except Exception:
        return False

def require(requirement: Requirement) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Condition requirement decorator. If the environment does not meet requirement,
    it automatically triggers unittest.SkipTest to avoid false CI failures.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            net_available = globals().get("is_network_available", is_network_available)
            if Requirement.NETWORK in requirement and not net_available():
                raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
