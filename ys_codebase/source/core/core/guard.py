"""
Core Security Gatekeeper SDK.
Provides runtime dispatch validation to prevent unauthorized direct invocation of internal module scripts.
"""

import os
import sys

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
    if os.environ.get(GUARD_ENV_TESTING) == "1":
        return

    # 2. Validate dispatch credentials
    token = os.environ.get(GUARD_ENV_TOKEN)
    host_dir = os.environ.get(GUARD_ENV_HOST)

    if not token or not host_dir:
        invoked_cmd = " ".join(sys.argv)
        forward_args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
        guide_cmd = f"python yscb.py {module_name} {forward_args}".strip()

        print("\n" + "=" * 66, file=sys.stderr)
        print(f"🚨 [YSCB Security Guard] 禁止直接繞道調用內部模組 '{module_name}'！", file=sys.stderr)
        print(f"❌ 非法嘗試：{invoked_cmd}", file=sys.stderr)
        print("👉 請一律透過專案唯一宿主入口調用：", file=sys.stderr)
        print(f"   {guide_cmd}", file=sys.stderr)
        print("=" * 66 + "\n", file=sys.stderr)
        sys.exit(126)
