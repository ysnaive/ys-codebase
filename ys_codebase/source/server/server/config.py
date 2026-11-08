"""
Server Module Configuration Loader & Dataclass.
Provides standard config retrieval via core.config, default constants, and type defense.
"""

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional

try:
    from core import config as core_config
except ImportError:
    core_config = None

DEFAULT_ENABLE: bool = True
DEFAULT_ENABLE_CONSOLE: bool = False
DEFAULT_IDLE_TIMEOUT_SEC: float = 1800.0
DEFAULT_AUTO_SPAWN: bool = True
DEFAULT_STRICT_HOT_DISPATCH: bool = False
DEFAULT_WORKER_ALIVE_TIMEOUT_SEC: float = 5.0


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


def _parse_float(val: Any, default: float, allow_zero: bool = True) -> float:
    """浮點數防禦解析 (攔截 None、bool、NaN、inf 與負數或非正數)。"""
    if val is None or isinstance(val, bool):
        return default
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return default
    if not math.isfinite(f_val):
        return default
    if allow_zero:
        if f_val < 0:
            return default
    elif f_val <= 0:
        return default
    return f_val


@dataclass(frozen=True)
class ServerConfig:
    enable: bool = DEFAULT_ENABLE
    enable_console: bool = DEFAULT_ENABLE_CONSOLE
    idle_timeout_sec: float = DEFAULT_IDLE_TIMEOUT_SEC
    auto_spawn: bool = DEFAULT_AUTO_SPAWN
    strict_hot_dispatch: bool = DEFAULT_STRICT_HOT_DISPATCH
    worker_alive_timeout_sec: float = DEFAULT_WORKER_ALIVE_TIMEOUT_SEC

    @classmethod
    def load(
        cls,
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
            except (OSError, ValueError, TypeError, KeyError):
                pass

        if override_dict and isinstance(override_dict, dict):
            raw_cfg.update(override_dict)

        enable_val = _parse_bool(raw_cfg.get("enable"), DEFAULT_ENABLE)
        enable_console_val = _parse_bool(raw_cfg.get("enable_console"), DEFAULT_ENABLE_CONSOLE)
        auto_spawn_val = _parse_bool(raw_cfg.get("auto_spawn"), DEFAULT_AUTO_SPAWN)
        idle_timeout_sec_val = _parse_float(
            raw_cfg.get("idle_timeout_sec", DEFAULT_IDLE_TIMEOUT_SEC),
            DEFAULT_IDLE_TIMEOUT_SEC,
            allow_zero=True,
        )
        strict_val = _parse_bool(raw_cfg.get("strict_hot_dispatch"), DEFAULT_STRICT_HOT_DISPATCH)
        alive_timeout_val = _parse_float(
            raw_cfg.get("worker_alive_timeout_sec", DEFAULT_WORKER_ALIVE_TIMEOUT_SEC),
            DEFAULT_WORKER_ALIVE_TIMEOUT_SEC,
            allow_zero=False,
        )

        return cls(
            enable=enable_val,
            enable_console=enable_console_val,
            idle_timeout_sec=idle_timeout_sec_val,
            auto_spawn=auto_spawn_val,
            strict_hot_dispatch=strict_val,
            worker_alive_timeout_sec=alive_timeout_val,
        )
