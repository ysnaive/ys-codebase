"""
Core module dev testing lifecycle hook.
Automatically configures the sandbox project_root when dev op-mksb / dev test provisions a sandbox.
"""
from typing import Any

def on_test_setup(context: Any) -> None:
    """
    Invoked when SandboxProvisioner initializes a new sandbox.
    Configures core's config.project.json to point project_root to sandbox mock_downstream_project.
    """
    if hasattr(context, "set_module_config"):
        context.set_module_config("core", "config.project.json", {
            "project_root": "../mock_downstream_project"
        })

def on_test_teardown(context: Any) -> None:
    """Invoked on sandbox teardown."""
    pass
