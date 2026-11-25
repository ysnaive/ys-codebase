"""Domain 4.1: Immutable content-hashed virtual environment pool, health probes, and rollback-friendly GC."""

from core.packaging.env.gc import EnvGarbageCollector
from core.packaging.env.pool import (
    ImmutableVenvPool,
    acquire_env_lease_for_python,
    acquire_env_shared_lease,
    touch_env_last_used,
)
from core.packaging.env.probe import EnvHealthProbe
from core.packaging.env.spec import (
    EnvBuildResult,
    EnvGcPolicy,
    EnvGcResult,
    EnvHealthReport,
    EnvMetadata,
    EnvSpec,
)

__all__ = (
    "EnvBuildResult",
    "EnvGarbageCollector",
    "EnvGcPolicy",
    "EnvGcResult",
    "EnvHealthProbe",
    "EnvHealthReport",
    "EnvMetadata",
    "EnvSpec",
    "ImmutableVenvPool",
    "acquire_env_lease_for_python",
    "acquire_env_shared_lease",
    "touch_env_last_used",
)
