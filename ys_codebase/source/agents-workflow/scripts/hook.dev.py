"""
Development and test execution hook for module: agents-workflow.
Provides setup and teardown lifecycle integration for YSCB sandbox testing.
"""
from typing import Any
from core import config


def on_test_setup(context: Any) -> None:
    """
    Invoked when SandboxProvisioner initializes a new sandbox.
    Pre-configures agents-workflow's semantic URI paths inside the sandbox
    using core.config SDK.
    """
    try:
        config.set("agents-workflow", "paths.plans", "project://plans", local=False)
        config.set("agents-workflow", "paths.archived", "project://plans/archived", local=False)
        config.set("agents-workflow", "paths.docs", "project://docs", local=False)
        config.set("agents-workflow", "paths.roadmap", "project://docs/roadmap.md", local=False)
        config.set("agents-workflow", "release_targets", ["antigravity"], local=False)
        config.set("agents-workflow", "enable_agents_md", True, local=False)
        config.set("agents-workflow", "enable_project_changelog", True, local=False)
    except Exception:
        pass


def on_test_teardown(context: Any) -> None:
    """Invoked on sandbox teardown."""
    pass
