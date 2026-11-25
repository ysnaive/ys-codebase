"""Domain 4.2: Pure offline package engine, dependency solver, atomic staging deployer, mirror store, and update checker."""

from core.packaging.installer.deployer import AtomicPackageDeployer
from core.packaging.installer.engine import OfflinePackageEngine
from core.packaging.installer.mirror import MirrorStore
from core.packaging.installer.models import (
    DeploymentReport,
    IndexReleaseRecord,
    PackageRequest,
    PurgeLevel,
    RemoteModuleIndex,
    UpdateCandidate,
    UpdateCheckReport,
    UpgradeTransition,
)
from core.packaging.installer.provider import ProviderClient
from core.packaging.installer.solver import DependencySolver
from core.packaging.installer.update_checker import UpdateChecker

__all__ = (
    "AtomicPackageDeployer",
    "DependencySolver",
    "DeploymentReport",
    "IndexReleaseRecord",
    "MirrorStore",
    "OfflinePackageEngine",
    "PackageRequest",
    "ProviderClient",
    "PurgeLevel",
    "RemoteModuleIndex",
    "UpdateCandidate",
    "UpdateCheckReport",
    "UpdateChecker",
    "UpgradeTransition",
)
