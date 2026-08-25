"""
yscb_core.config — YS-Codebase 2×2 矩陣設定管理員 (2x2 Matrix Config Manager)
"""

import os
import json
import copy
from pathlib import Path
from typing import Optional, Union, Dict, Any

try:
    from .context import ProjectContext
except (ImportError, ValueError):
    from context import ProjectContext


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """遞迴無損合併兩個字典 (Deep Merge)"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """
    實作 2×2 矩陣設定載入、保存與 4 層 Cascade 優先級合併：
    
    1. CLI Flags (由調用端自行覆寫)
    2. [4] Module.UserLevel     (config.local.json)
    3. [3] Module.ProjectLevel  (config.project.json)
    4. [2] Codebase.UserLevel   (yscb_config.local.json -> custom_settings / module_settings)
    5. [1] Codebase.ProjectLevel(yscb_config.json -> custom_settings / module_settings)
    6. 模組內建預設範本          (config.project.template.json / config.local.template.json)
    """

    @classmethod
    def _read_json(cls, path: Path) -> Dict[str, Any]:
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    @classmethod
    def _write_json(cls, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @classmethod
    def resolve_config_uris(cls, data: Any, start_dir: Optional[Union[str, Path]] = None) -> Any:
        """遞迴解析字典或清單中包含 '://' 之語意 URI 字串為實體絕對 Path"""
        if isinstance(data, dict):
            return {k: cls.resolve_config_uris(v, start_dir=start_dir) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.resolve_config_uris(item, start_dir=start_dir) for item in data]
        elif isinstance(data, str) and "://" in data:
            try:
                from .uri import ProjectURI
            except (ImportError, ValueError):
                from uri import ProjectURI
            res = ProjectURI.resolve(data, start_dir=start_dir)
            return str(res) if isinstance(res, Path) else res
        return data

    @classmethod
    def load(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None, resolve_uris: bool = False) -> Dict[str, Any]:
        """
        按照 2×2 矩陣優先級完整載入並合併模組設定。
        :param resolve_uris: 若為 True，自動遞迴展開字典中所有的語意 URI (project://, yscb:// 等)
        """
        proj_root = ProjectContext.get_project_root(start_dir)
        mod_dir = ProjectContext.get_module_dir(module_name, start_dir)

        # 6. 模組範本 (Module Templates)
        mod_proj_tpl = cls._read_json(mod_dir / "config.project.template.json")
        if not mod_proj_tpl:
            # 向後相容舊版 config.template.json
            mod_proj_tpl = cls._read_json(mod_dir / "config.template.json")
        mod_user_tpl = cls._read_json(mod_dir / "config.local.template.json")
        merged = deep_merge(mod_proj_tpl, mod_user_tpl)

        # 5. [1] Codebase.ProjectLevel (yscb_config.json)
        codebase_proj = cls._read_json(proj_root / ProjectContext.CONFIG_FILE)
        cb_proj_settings = codebase_proj.get("custom_settings", {})
        cb_proj_mod_settings = codebase_proj.get("module_settings", {}).get(module_name, {})
        merged = deep_merge(merged, cb_proj_settings)
        merged = deep_merge(merged, cb_proj_mod_settings)

        # 4. [2] Codebase.UserLevel (yscb_config.local.json)
        codebase_user = cls._read_json(proj_root / ProjectContext.LOCAL_CONFIG_FILE)
        cb_user_settings = codebase_user.get("custom_settings", {})
        cb_user_mod_settings = codebase_user.get("module_settings", {}).get(module_name, {})
        merged = deep_merge(merged, cb_user_settings)
        merged = deep_merge(merged, cb_user_mod_settings)

        # 3. [3] Module.ProjectLevel (config.project.json)
        mod_proj = cls._read_json(mod_dir / "config.project.json")
        if not mod_proj:
            # 向後相容舊版 config_global.json 或 config.json
            mod_proj = cls._read_json(mod_dir / "config_global.json")
        merged = deep_merge(merged, mod_proj)

        # 2. [4] Module.UserLevel (config.local.json)
        mod_user = cls._read_json(mod_dir / "config.local.json")
        if not mod_user:
            # 向後相容舊版 config.json (若不存在 config.project.json)
            mod_user = cls._read_json(mod_dir / "config.json")
        merged = deep_merge(merged, mod_user)

        if resolve_uris:
            merged = cls.resolve_config_uris(merged, start_dir=start_dir)

        return merged

    @classmethod
    def get_project_config(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """取得特定模組的 ProjectLevel 設定 (config.project.json)"""
        mod_dir = ProjectContext.get_module_dir(module_name, start_dir)
        proj_cfg = cls._read_json(mod_dir / "config.project.json")
        if not proj_cfg:
            proj_cfg = cls._read_json(mod_dir / "config.project.template.json")
        return proj_cfg

    @classmethod
    def get_user_config(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """取得特定模組的 UserLevel 設定 (config.local.json)"""
        mod_dir = ProjectContext.get_module_dir(module_name, start_dir)
        user_cfg = cls._read_json(mod_dir / "config.local.json")
        if not user_cfg:
            user_cfg = cls._read_json(mod_dir / "config.local.template.json")
        return user_cfg

    @classmethod
    def save_project_config(cls, module_name: str, data: Dict[str, Any], start_dir: Optional[Union[str, Path]] = None) -> Path:
        """保存模組專案級設定至 config.project.json (進 Git)"""
        mod_dir = ProjectContext.get_module_dir(module_name, start_dir)
        target_path = mod_dir / "config.project.json"
        cls._write_json(target_path, data)
        return target_path

    @classmethod
    def save_user_config(cls, module_name: str, data: Dict[str, Any], start_dir: Optional[Union[str, Path]] = None) -> Path:
        """保存模組個人本地偏好至 config.local.json (被 .gitignore 忽略)"""
        mod_dir = ProjectContext.get_module_dir(module_name, start_dir)
        target_path = mod_dir / "config.local.json"
        cls._write_json(target_path, data)
        return target_path
