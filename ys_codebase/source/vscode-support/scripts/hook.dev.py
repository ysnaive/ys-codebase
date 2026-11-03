"""
Development and Sandbox Test Execution Hook for `module:vscode-support` (`scripts/hook.dev.py`).
"""

import logging
from typing import Any


def on_test_setup(context: Any = None, **kwargs: Any) -> None:
    """Prepare sandbox environment before test execution."""
    logging.getLogger("vscode-support.hook.dev").debug("[hook.dev] Setup vscode-support sandbox: %s", context)


def on_test_teardown(context: Any = None, **kwargs: Any) -> None:
    """Clean up temporary state after sandbox test execution."""
    logging.getLogger("vscode-support.hook.dev").debug("[hook.dev] Teardown vscode-support sandbox: %s", context)

