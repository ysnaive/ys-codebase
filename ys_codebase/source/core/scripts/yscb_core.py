"""
yscb_core — YS-Codebase 核心運行期 SDK (Core Runtime SDK Facade)

提供對外的統一型態、環境與路徑解析入口。
"""

try:
    from .context import ProjectContext
    from .config import ConfigManager, deep_merge
    from .console import Console
    from .uri import ProjectURI
    from .semver import SemVer, VersionConstraint
    from .migration import MigrationRunner
except (ImportError, ValueError):
    from context import ProjectContext
    from config import ConfigManager, deep_merge
    from console import Console
    from uri import ProjectURI
    from semver import SemVer, VersionConstraint
    from migration import MigrationRunner

__version__ = "2.1.0"

__all__ = [
    "ProjectContext",
    "ConfigManager",
    "Console",
    "ProjectURI",
    "SemVer",
    "VersionConstraint",
    "MigrationRunner",
    "deep_merge",
    "__version__",
]

