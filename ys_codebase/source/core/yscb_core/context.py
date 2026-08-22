"""
yscb_core.context — YS-Codebase 專案環境與路徑解析器 (Project Context & Path Resolver)
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Union, Dict, Any


class ProjectContext:
    """提供標準化的專案路徑定位與環境解析能力"""

    CONFIG_FILE = "yscb_config.json"
    LOCAL_CONFIG_FILE = "yscb_config.local.json"

    @classmethod
    def get_project_root(cls, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得專案根目錄 (Project Root)。
        優先序：
        1. 環境變數 YSCB_PROJECT_ROOT
        2. 從 start_dir 向上查找 yscb_config.json
        3. 從 start_dir 向上查找 .git
        4. 當前工作目錄 (Path.cwd())
        """
        env_root = os.environ.get("YSCB_PROJECT_ROOT")
        if env_root and os.path.isdir(env_root):
            return Path(env_root).resolve()

        cur = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()

        # 向上搜尋 yscb_config.json 或 .git
        for parent in [cur] + list(cur.parents):
            cfg_path = parent / cls.CONFIG_FILE
            if cfg_path.is_file():
                # 檢查 yscb_config.json 內部是否有定義 paths.project_root
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                    custom_proj = cfg_data.get("paths", {}).get("project_root")
                    if custom_proj:
                        resolved_proj = (parent / custom_proj).resolve()
                        if resolved_proj.is_dir():
                            return resolved_proj
                except Exception:
                    pass
                return parent

        for parent in [cur] + list(cur.parents):
            if (parent / ".git").exists():
                return parent

        return cur

    @classmethod
    def get_yscb_root(cls, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """取得工具庫安裝或配置目錄 (yscb_root)"""
        env_root = os.environ.get("YSCB_ROOT")
        if env_root and os.path.isdir(env_root):
            return Path(env_root).resolve()

        proj_root = cls.get_project_root(start_dir)
        cfg_path = proj_root / cls.CONFIG_FILE
        if cfg_path.is_file():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                custom_yscb = cfg_data.get("paths", {}).get("yscb_root")
                if custom_yscb:
                    resolved_yscb = (proj_root / custom_yscb).resolve()
                    if resolved_yscb.is_dir():
                        return resolved_yscb
            except Exception:
                pass

        return proj_root

    @classmethod
    def get_module_dir(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        取得特定模組的目錄路徑。
        優先尋找 modules/<module_name> (Build 模式)，次之 source/<module_name> (Source 模式)。
        """
        env_mod = os.environ.get("YSCB_MODULE_DIR")
        if env_mod and os.path.isdir(env_mod):
            return Path(env_mod).resolve()

        proj_root = cls.get_project_root(start_dir)
        candidate_dirs = [
            proj_root / "modules" / module_name,
            proj_root / "source" / module_name,
            proj_root / "ys_codebase" / "modules" / module_name,
            proj_root / "ys_codebase" / "source" / module_name,
            proj_root / "ys_codebase" / "build" / module_name,
        ]

        for cand in candidate_dirs:
            if cand.is_dir():
                return cand.resolve()

        # 預設回傳 modules/<module_name>
        return (proj_root / "modules" / module_name).resolve()

    @classmethod
    def resolve(cls, rel_path: Union[str, Path], base_dir: Optional[Union[str, Path]] = None) -> Path:
        """將相對於專案根目錄的路徑字串解析為標準絕對 Path"""
        p = Path(rel_path)
        if p.is_absolute():
            return p
        base = Path(base_dir).resolve() if base_dir else cls.get_project_root()
        return (base / p).resolve()
