"""
Development and Sandbox Test Execution Hook for `module:vscode-support` (`scripts/hook.dev.py`).
"""

from typing import Any

from core.log import log_debug


def on_test_setup(context: Any = None, **kwargs: Any) -> None:
    """Prepare sandbox environment before test execution."""
    log_debug(f"[hook.dev] Setup vscode-support sandbox: {context}")


def on_test_teardown(context: Any = None, **kwargs: Any) -> None:
    """Clean up temporary state after sandbox test execution."""
    log_debug(f"[hook.dev] Teardown vscode-support sandbox: {context}")

