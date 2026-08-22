"""
yscb_core — YS-Codebase 核心運行期 SDK (Core Runtime SDK Facade)

提供對外的統一型態、環境與路徑解析入口。
"""

try:
    from .context import ProjectContext
    from .config import ConfigManager, deep_merge
    from .console import Console
    from .uri import ProjectURI
except (ImportError, ValueError):
    from context import ProjectContext
    from config import ConfigManager, deep_merge
    from console import Console
    from uri import ProjectURI

__version__ = "2.0.0"

__all__ = [
    "ProjectContext",
    "ConfigManager",
    "Console",
    "ProjectURI",
    "deep_merge",
    "__version__",
]
