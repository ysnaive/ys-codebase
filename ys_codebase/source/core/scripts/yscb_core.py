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

def _read_own_version() -> str:
    """自 manifest.json (SSOT) 讀取模組版本號，避免版本號多處硬編碼發散"""
    try:
        import json as _json
        from pathlib import Path as _Path
        _manifest = _Path(__file__).resolve().parent.parent / "manifest.json"
        return str(_json.loads(_manifest.read_text(encoding="utf-8")).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


__version__ = _read_own_version()

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

