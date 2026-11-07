"""
Structured exception hierarchy for the core.space atomic engine.
"""


class SpaceError(Exception):
    """Base exception for all core.space configuration, resolution, and traversal errors."""


class SpaceNotFoundError(SpaceError):
    """Raised when a queried space or preset identifier is not registered."""


class SpaceCycleError(SpaceError):
    """Raised when a circular reference is detected in space `compose` definitions."""

