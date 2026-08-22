"""
yscb_core — YS-Codebase 核心運行期 SDK (Core Runtime SDK)

提供全模組通用的專案路徑解析、2×2 矩陣設定管理與控制台格式化輸出。
"""

from .context import ProjectContext
from .config import ConfigManager, deep_merge
from .console import Console

__all__ = ["ProjectContext", "ConfigManager", "deep_merge", "Console"]
__version__ = "2.0.0"
