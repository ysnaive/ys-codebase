"""
YS-Codebase Core Configuration Manager & Unified SDK.
Provides standard config retrieval, two-tier deep merging (Local > Project),
memory caching with mtime auto-healing, and atomic writes.

100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import json
import copy
import logging
import tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("core.config")

try:
    from core import uri
except ImportError:
    uri = None


class ConfigManager:
    """微內核設定管理器：負責模組組態之雙層合併、自愈快取與原子讀寫。"""

    _cache: Dict[str, Dict[str, Any]] = {}
    _mtimes: Dict[str, Tuple[float, float]] = {}

    @classmethod
    def _get_yscb_root(cls) -> str:
        if uri:
            try:
                return uri._get_yscb_root()
            except Exception:
                pass
        curr = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))

    @classmethod
    def get_config_path(cls, module: str, local: bool = False) -> str:
        """取得指定模組之設定檔實體路徑。"""
        filename = "config.local.json" if local else "config.project.json"
        if uri:
            try:
                return uri.resolve(f"config://{module}/{filename}", interactive=False)
            except Exception:
                pass
        yscb_root = cls._get_yscb_root()
        return os.path.normpath(os.path.join(yscb_root, "config", module, filename))

    @classmethod
    def _deep_merge(cls, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """遞迴深層合併 override 至 base 副本。"""
        result = copy.deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = cls._deep_merge(result[k], v)
            else:
                result[k] = copy.deepcopy(v)
        return result

    @classmethod
    def _get_by_dot_path(cls, data: Dict[str, Any], dot_path: str, default: Any = None) -> Any:
        """透過點分隔路徑讀取巢狀字典值。"""
        if not dot_path:
            return data
        parts = dot_path.split(".")
        curr = data
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return default
        return copy.deepcopy(curr)

    @classmethod
    def _set_by_dot_path(cls, data: Dict[str, Any], dot_path: str, value: Any) -> None:
        """透過點分隔路徑設定巢狀字典值。"""
        parts = dot_path.split(".")
        curr = data
        for part in parts[:-1]:
            if part not in curr or not isinstance(curr[part], dict):
                curr[part] = {}
            curr = curr[part]
        curr[parts[-1]] = copy.deepcopy(value)

    @classmethod
    def _delete_by_dot_path(cls, data: Dict[str, Any], dot_path: str) -> bool:
        """透過點分隔路徑刪除巢狀字典值。"""
        parts = dot_path.split(".")
        curr = data
        for part in parts[:-1]:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return False
        if isinstance(curr, dict) and parts[-1] in curr:
            del curr[parts[-1]]
            return True
        return False

    @classmethod
    def _read_json_file(cls, filepath: str) -> Dict[str, Any]:
        """安全讀取 JSON 檔案，若檔案不存在回傳空字典，損毀時輸出警告日誌。"""
        if not os.path.isfile(filepath):
            return {}
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to read or parse config file '{filepath}': {e}")
            return {}

    @classmethod
    def _atomic_write_json(cls, filepath: str, data: Dict[str, Any]) -> None:
        """原子寫入 JSON 檔案並確保目錄存在。"""
        target_dir = os.path.dirname(filepath)
        os.makedirs(target_dir, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix="cfg_tmp_", suffix=".json")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if os.path.exists(filepath):
                os.replace(tmp_path, filepath)
            else:
                os.rename(tmp_path, filepath)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

    @classmethod
    def _check_and_load(cls, module: str) -> Dict[str, Any]:
        """檢測 mtime 並載入雙層合併組態 (Local > Project)，具備 Auto-Healing 自愈快取。"""
        proj_path = cls.get_config_path(module, local=False)
        local_path = cls.get_config_path(module, local=True)

        p_mtime = os.path.getmtime(proj_path) if os.path.isfile(proj_path) else 0.0
        l_mtime = os.path.getmtime(local_path) if os.path.isfile(local_path) else 0.0

        cached_mtimes = cls._mtimes.get(module)
        if module in cls._cache and cached_mtimes == (p_mtime, l_mtime):
            return cls._cache[module]

        # 重新載入並深層合併
        proj_data = cls._read_json_file(proj_path)
        local_data = cls._read_json_file(local_path)
        merged = cls._deep_merge(proj_data, local_data)

        cls._cache[module] = merged
        cls._mtimes[module] = (p_mtime, l_mtime)
        return merged

    @classmethod
    def get(cls, module: str, key: Optional[str] = None, default: Any = None) -> Any:
        """
        查詢指定模組之有效設定值（支援點分隔路徑），自動執行 Local > Project 雙層合併與快取自愈。
        """
        if not module:
            return default
        merged = cls._check_and_load(module)
        if key is None:
            return copy.deepcopy(merged)
        return cls._get_by_dot_path(merged, key, default)

    @classmethod
    def get_all(cls, module: str) -> Dict[str, Any]:
        """獲取指定模組之完整合併組態字典副本。"""
        return cls.get(module)

    @classmethod
    def set(cls, module: str, key: str, value: Any, local: bool = False) -> None:
        """
        寫入或更新指定模組之設定值（支援點分隔鍵值），自動同步磁碟並熱自愈記憶體快取。
        """
        if not module or not key:
            raise ValueError("Module and key must not be empty.")

        target_path = cls.get_config_path(module, local=local)
        existing = cls._read_json_file(target_path)
        cls._set_by_dot_path(existing, key, value)
        cls._atomic_write_json(target_path, existing)

        # 強制刷新快取
        cls.reload(module)

    @classmethod
    def delete(cls, module: str, key: str, local: bool = False) -> bool:
        """刪除指定模組設定檔中的特定鍵值。"""
        if not module or not key:
            return False

        target_path = cls.get_config_path(module, local=local)
        existing = cls._read_json_file(target_path)
        deleted = cls._delete_by_dot_path(existing, key)
        if deleted:
            cls._atomic_write_json(target_path, existing)
            cls.reload(module)
        return deleted

    @classmethod
    def reload(cls, module: Optional[str] = None) -> None:
        """手動強制清空快取。"""
        if module:
            cls._cache.pop(module, None)
            cls._mtimes.pop(module, None)
        else:
            cls._cache.clear()
            cls._mtimes.clear()

    @classmethod
    def get_raw(
        cls,
        module: str,
        key: Optional[str] = None,
        local: bool = False,
        default: Any = None,
    ) -> Any:
        """
        讀取指定模組特定層級 (local=True 讀 Local, local=False 讀 Project) 之未合併原始組態。
        若 key 為 None 則回傳該層級完整字典副本。
        """
        if not module:
            return default
        target_path = cls.get_config_path(module, local=local)
        raw_data = cls._read_json_file(target_path)
        if key is None:
            return copy.deepcopy(raw_data)
        return cls._get_by_dot_path(raw_data, key, default)

    @classmethod
    def inspect(cls, module: str, key: str) -> Dict[str, Any]:
        """
        探測指定模組特定鍵值之來源層級與覆蓋狀態。
        回傳字典結構:
        {
            "key": key,
            "effective": effective_value,
            "source": "local" | "project" | "both" | "none",
            "local_value": ...,
            "project_value": ...,
            "is_overridden": bool
        }
        """
        if not module or not key:
            return {
                "key": key,
                "effective": None,
                "source": "none",
                "local_value": None,
                "project_value": None,
                "is_overridden": False,
            }

        sentinel = object()
        proj_val = cls.get_raw(module, key, local=False, default=sentinel)
        local_val = cls.get_raw(module, key, local=True, default=sentinel)
        effective_val = cls.get(module, key, default=None)

        has_proj = proj_val is not sentinel
        has_local = local_val is not sentinel

        if has_proj and has_local:
            source = "both"
            is_overridden = (local_val != proj_val)
        elif has_local:
            source = "local"
            is_overridden = False
        elif has_proj:
            source = "project"
            is_overridden = False
        else:
            source = "none"
            is_overridden = False

        return {
            "key": key,
            "effective": effective_val,
            "source": source,
            "local_value": copy.deepcopy(local_val) if has_local else None,
            "project_value": copy.deepcopy(proj_val) if has_proj else None,
            "is_overridden": is_overridden,
        }

    @classmethod
    def list_modules(cls) -> List[str]:
        """列出當前 config:// 空間下存在設定檔之所有模組清單。"""
        yscb_root = cls._get_yscb_root()
        cfg_root = os.path.join(yscb_root, "config")
        if not os.path.isdir(cfg_root):
            return []
        mods = []
        for item in os.listdir(cfg_root):
            mod_dir = os.path.join(cfg_root, item)
            if os.path.isdir(mod_dir):
                if os.path.isfile(os.path.join(mod_dir, "config.project.json")) or os.path.isfile(os.path.join(mod_dir, "config.local.json")):
                    mods.append(item)
        return sorted(mods)


# 頂層便捷函式 (Public API Facade)
get = ConfigManager.get
get_all = ConfigManager.get_all
get_raw = ConfigManager.get_raw
inspect = ConfigManager.inspect
set = ConfigManager.set
delete = ConfigManager.delete
reload = ConfigManager.reload
list_modules = ConfigManager.list_modules
get_config_path = ConfigManager.get_config_path

