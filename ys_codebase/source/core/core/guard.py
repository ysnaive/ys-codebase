"""
Core Security Gatekeeper SDK.
Provides runtime dispatch validation to prevent unauthorized direct invocation of internal module scripts.

Security Boundary & Design Contract:
- The dispatch token (GUARD_ENV_TOKEN) is a cooperative architectural guard designed
  to guide developers and tooling through the unified host entry point (yscb.py).
- It is NOT intended as a cryptographic security boundary against reverse engineering or
  malicious code execution within the same environment.
"""

import os
import sys
from core.context import get_env
from core.log import log_error

GUARD_ENV_TOKEN: str = "YSCB_HOST_DISPATCH_TOKEN"
GUARD_ENV_HOST: str = "YSCB_HOST_DIR"
GUARD_ENV_TESTING: str = "YSCB_TESTING"


def guard_dispatch(module_name: str) -> None:
    """
    Validates that the current module execution was legitimately dispatched by the YSCB host bootstrapper.
    If unauthorized direct execution is detected, prints an instructive message to stderr and terminates
    immediately with exit code 126.
    """
    # 1. Safe exemption for test execution
    if get_env(GUARD_ENV_TESTING) == "1":
        return

    # 2. Validate dispatch credentials
    token = get_env(GUARD_ENV_TOKEN)
    host_dir = get_env(GUARD_ENV_HOST)

    if not token or not host_dir:
        invoked_cmd = " ".join(sys.argv)
        forward_args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
        guide_cmd = f"python yscb.py {module_name} {forward_args}".strip()

        log_error("\n" + "=" * 66, stream="stderr")
        log_error(f"[!] [YSCB Security Guard] 禁止直接繞道調用內部模組 '{module_name}'！", stream="stderr")
        log_error(f"[FAIL] 非法嘗試：{invoked_cmd}", stream="stderr")
        log_error("--> 請一律透過專案唯一宿主入口調用：", stream="stderr")
        log_error(f"   {guide_cmd}", stream="stderr")
        log_error("=" * 66 + "\n", stream="stderr")
        raise SystemExit(126)
