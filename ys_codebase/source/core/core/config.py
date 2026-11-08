"""
YS-Codebase Core Configuration Manager & Unified SDK.
Provides standard config retrieval, two-tier deep merging (Local > Project),
memory caching with mtime auto-healing, and atomic writes.

100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import copy
from typing import Any, Dict, List, Optional, Set, Tuple
from core import uri, vfs
from core.context import get_runtime_context
from core.log import log_warn


class _ConfigManagerMeta(type):
    """Metaclass delegating class-level `_cache` and `_mtimes` attribute lookups to `RuntimeContext`."""

    @property
    def _cache(cls) -> Dict[Any, Dict[str, Any]]:
        return get_runtime_context().config_cache

    @property
    def _mtimes(cls) -> Dict[Any, Tuple[float, float]]:
        return get_runtime_context().config_mtimes


class ConfigManager(metaclass=_ConfigManagerMeta):
    """微內核設定管理器：負責模組組態之雙層合併、自愈快取與原子讀寫。"""

    @staticmethod
    def _get_cache() -> Dict[Any, Dict[str, Any]]:
        return get_runtime_context().config_cache

    @staticmethod
    def _get_mtimes() -> Dict[Any, Tuple[float, float]]:
        return get_runtime_context().config_mtimes

    @staticmethod
    def _clone_if_container(val: Any) -> Any:
        """若值為可變容器 (dict, list) 則回傳深拷貝，不可變純量則直接回傳。"""
        return copy.deepcopy(val) if isinstance(val, (dict, list)) else val

    @classmethod
    def _get_yscb_root(cls) -> str:
        """解析 yscb_root 目錄，統一委派至 core.uri.resolve_yscb_root()。"""
        return uri.resolve_yscb_root()

    @classmethod
    def _get_cache_key(cls, module: str) -> Tuple[str, str]:
        """取得綁定當前 yscb_root 與模組名稱之複合快取鍵。"""
        return (os.path.normpath(cls._get_yscb_root()), module)

    @classmethod
    def get_config_path(cls, module: str, local: bool = False) -> str:
        """取得指定模組之設定檔實體路徑（local=False 指向 config://，local=True 指向 config.local://）。"""
        filename = "config.local.json" if local else "config.project.json"
        scheme = "config.local" if local else "config"
        subdir = ".config.local" if local else "config"
        try:
            return uri.resolve(f"{scheme}://{module}/{filename}", interactive=False)
        except Exception:
            yscb_root = cls._get_yscb_root()
            return os.path.normpath(os.path.join(yscb_root, subdir, module, filename))

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
            return cls._clone_if_container(data)
        parts = dot_path.split(".")
        curr: Any = data
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return cls._clone_if_container(default)
        return cls._clone_if_container(curr)

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
        if not vfs.is_file(filepath):
            return {}
        try:
            data = vfs.read_json(filepath)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            log_warn(f"Failed to read or parse config file '{filepath}': {e}", stream="stderr")
            return {}

    @classmethod
    def _atomic_write_json(cls, filepath: str, data: Dict[str, Any]) -> None:
        """原子寫入 JSON 檔案並確保目錄存在 (100% 委派 core.vfs 原子寫入)。"""
        vfs.write_json(filepath, data, indent=2, encoding="utf-8", atomic=True)

    @classmethod
    def _check_and_load(cls, module: str) -> Dict[str, Any]:
        """檢測 mtime 並載入雙層合併組態 (Local > Project)，具備 Auto-Healing 自愈快取。"""
        proj_path = cls.get_config_path(module, local=False)
        local_path = cls.get_config_path(module, local=True)

        p_mtime = os.path.getmtime(proj_path) if os.path.isfile(proj_path) else 0.0
        l_mtime = os.path.getmtime(local_path) if os.path.isfile(local_path) else 0.0

        cache_key = cls._get_cache_key(module)
        cache = cls._get_cache()
        mtimes = cls._get_mtimes()
        cached_mtimes = mtimes.get(cache_key)
        if cache_key in cache and cached_mtimes == (p_mtime, l_mtime):
            return cache[cache_key]

        # 重新載入並深層合併
        proj_data = cls._read_json_file(proj_path)
        local_data = cls._read_json_file(local_path)
        merged = cls._deep_merge(proj_data, local_data)

        cache[cache_key] = merged
        mtimes[cache_key] = (p_mtime, l_mtime)
        return merged

    @classmethod
    def get(cls, module: str, key: Optional[str] = None, default: Any = None) -> Any:
        """
        查詢指定模組之有效設定值（支援點分隔路徑），自動執行 Local > Project 雙層合併與快取自愈。
        """
        if not module:
            return cls._clone_if_container(default)
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
        cache = cls._get_cache()
        mtimes = cls._get_mtimes()
        if module:
            for store in (cache, mtimes):
                keys_to_remove = [
                    k for k in list(store.keys())
                    if k == module or (isinstance(k, tuple) and len(k) == 2 and k[1] == module)
                ]
                for k in keys_to_remove:
                    store.pop(k, None)
        else:
            cache.clear()
            mtimes.clear()

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
            return cls._clone_if_container(default)
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
            "local_value": cls._clone_if_container(local_val) if has_local else None,
            "project_value": cls._clone_if_container(proj_val) if has_proj else None,
            "is_overridden": is_overridden,
        }

    @classmethod
    def list_modules(cls) -> List[str]:
        """列出當前 config:// 與 config.local:// 空間下存在設定檔之所有模組清單。"""
        yscb_root = cls._get_yscb_root()
        mods_set: Set[str] = {m for m in ()}
        cfg_root = os.path.join(yscb_root, "config")
        if os.path.isdir(cfg_root):
            for item in os.listdir(cfg_root):
                mod_dir = os.path.join(cfg_root, item)
                if os.path.isdir(mod_dir) and os.path.isfile(os.path.join(mod_dir, "config.project.json")):
                    mods_set.add(item)
        local_root = os.path.join(yscb_root, ".config.local")
        if os.path.isdir(local_root):
            for item in os.listdir(local_root):
                mod_dir = os.path.join(local_root, item)
                if os.path.isdir(mod_dir) and os.path.isfile(os.path.join(mod_dir, "config.local.json")):
                    mods_set.add(item)
        return sorted(mods_set)


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
