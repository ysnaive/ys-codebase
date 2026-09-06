"""
Server Module Configuration Loader & Dataclass.
Provides standard config retrieval via core.config, default constants, and type defense.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from core import config as core_config
except ImportError:
    core_config = None

DEFAULT_ENABLE: bool = True
DEFAULT_ENABLE_CONSOLE: bool = False
DEFAULT_IDLE_TIMEOUT_SEC: float = 900.0


def _parse_bool(val: Any, default: bool = False) -> bool:
    """寬鬆布林值防禦解析 (支援 bool、int、字串)。"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off"):
            return False
    return default


@dataclass
class ServerConfig:
    enable: bool = DEFAULT_ENABLE
    enable_console: bool = DEFAULT_ENABLE_CONSOLE
    idle_timeout_sec: float = DEFAULT_IDLE_TIMEOUT_SEC

    @classmethod
    def load(
        cls,
        workspace_root: Optional[str] = None,
        override_dict: Optional[Dict[str, Any]] = None,
    ) -> "ServerConfig":
        """
        載入 Server 模組組態。
        支援傳入 override_dict 或自 core.config (Local > Project) 雙層讀取。
        """
        raw_cfg: Dict[str, Any] = {}
        if core_config and hasattr(core_config, "get_all"):
            try:
                mod_cfg = core_config.get_all("server")
                if isinstance(mod_cfg, dict):
                    raw_cfg.update(mod_cfg)
            except Exception:
                pass

        if override_dict and isinstance(override_dict, dict):
            raw_cfg.update(override_dict)

        enable_val = _parse_bool(raw_cfg.get("enable"), DEFAULT_ENABLE)
        enable_console_val = _parse_bool(raw_cfg.get("enable_console"), DEFAULT_ENABLE_CONSOLE)
        raw_ttl = raw_cfg.get("idle_timeout_sec", DEFAULT_IDLE_TIMEOUT_SEC)
        try:
            idle_timeout_sec_val = float(raw_ttl)
        except (ValueError, TypeError):
            idle_timeout_sec_val = DEFAULT_IDLE_TIMEOUT_SEC

        return cls(
            enable=enable_val,
            enable_console=enable_console_val,
            idle_timeout_sec=idle_timeout_sec_val,
        )
