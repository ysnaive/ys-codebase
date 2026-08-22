"""
yscb_core.uri — YS-Codebase 專用語意 URI (Semantic URI) 解析器與轉換器

支援標準協議：
  - project://<path>  : 解析至專案根目錄 (Project Root)
  - yscb://<path>     : 解析至工具庫安裝目錄 (yscb_root)
  - plans://<path>    : 解析至活躍開發計畫目錄 (由 agents-workflow paths.plans_dir 定義)
  - archive://<path>  : 解析至歷史計畫歸檔目錄 (由 agents-workflow paths.archive_dir 定義)
  - docs://<path>     : 解析至專案知識庫目錄 (由 agents-workflow / project paths.docs_dir 定義)
  - sop_ext://<path>  : 解析至專案 SOP 擴充清單目錄 (由 agents-workflow paths.extensions_dir 定義)
"""

import os
import sys
from pathlib import Path
from typing import Optional, Union, Dict, List, Any, Tuple

try:
    from .context import ProjectContext
    from .config import ConfigManager
except (ImportError, ValueError):
    from context import ProjectContext
    from config import ConfigManager


class ProjectURI:
    """Codebase 專用語意 URI (project://, yscb://, plans://, archive://, docs://, sop_ext://) 解析器"""

    # 模組特化 Scheme 映射表: scheme -> (module_name, config_key, default_fallback)
    DYNAMIC_SCHEMES = {
        "plans": ("agents-workflow", "plans_dir", None),
        "archive": ("agents-workflow", "archive_dir", None),
        "docs": ("agents-workflow", "docs_dir", "docs"),
        "sop_ext": ("agents-workflow", "extensions_dir", None),
    }

    @classmethod
    def parse_uri(cls, uri: str) -> Tuple[Optional[str], str]:
        """解析 URI 字串，分離 scheme 與相對路徑"""
        s = uri.strip()
        if "://" in s:
            scheme, rel = s.split("://", 1)
            return scheme.lower(), rel.lstrip("/\\")
        return None, s

    @classmethod
    def get_base_path(cls, scheme: str, start_dir: Optional[Union[str, Path]] = None) -> Union[Path, str]:
        """
        取得特定 scheme 的基礎路徑 (Base Path)。
        若目標模組未安裝、未啟用或路徑為 !undefined，回傳 "!undefined"。
        """
        scheme = scheme.lower()
        proj_root = ProjectContext.get_project_root(start_dir)

        if scheme == "project":
            return proj_root

        if scheme == "yscb":
            return ProjectContext.get_yscb_root(start_dir)

        if scheme in cls.DYNAMIC_SCHEMES:
            mod_name, key, default_fb = cls.DYNAMIC_SCHEMES[scheme]
            mod_dir = ProjectContext.get_module_dir(mod_name, start_dir)
            if not mod_dir.is_dir():
                # 模組未安裝
                if default_fb:
                    return (proj_root / default_fb).resolve()
                return "!undefined"

            try:
                full_cfg = ConfigManager.load(mod_name, start_dir=start_dir)
                paths = full_cfg.get("paths", {})
                raw_val = paths.get(key) if isinstance(paths, dict) and key in paths else full_cfg.get(key)
                
                if ProjectContext.is_undefined(raw_val):
                    if default_fb:
                        return (proj_root / default_fb).resolve()
                    return "!undefined"

                resolved = ProjectContext.resolve(raw_val, base_dir=proj_root)
                return resolved
            except Exception:
                if default_fb:
                    return (proj_root / default_fb).resolve()
                return "!undefined"

        return "!undefined"

    @classmethod
    def resolve(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> Union[Path, str]:
        """
        將語意 URI (例如 docs://_project/STANDARDS.md 或 project://AGENTS.md)
        解析為本機實體絕對 Path。
        若對應模組未安裝或未設定，回傳 "!undefined"。
        """
        if isinstance(uri, Path):
            return uri.resolve()

        uri_str = str(uri).strip()
        scheme, subpath = cls.parse_uri(uri_str)

        if not scheme:
            # 標準路徑，回退至 ProjectContext.resolve()
            if ProjectContext.is_undefined(uri_str):
                return "!undefined"
            return ProjectContext.resolve(uri_str, base_dir=start_dir)

        base_res = cls.get_base_path(scheme, start_dir)
        if isinstance(base_res, str) and ProjectContext.is_undefined(base_res):
            return "!undefined"

        if isinstance(base_res, Path):
            if not subpath:
                return base_res
            return (base_res / subpath).resolve()

        return "!undefined"

    @classmethod
    def to_uri(cls, path: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> str:
        """
        將本機實體路徑反向匹配轉換為最短的語意 URI。
        若無法匹配特定 scheme，回傳相對於 project:// 的路徑。
        """
        p = Path(path).resolve()
        start_dir_p = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        proj_root = ProjectContext.get_project_root(start_dir_p)

        # 依序匹配動態 scheme (plans, archive, docs, sop_ext), 再 yscb, 最後 project
        schemes_to_check = ["plans", "archive", "docs", "sop_ext", "yscb", "project"]
        for scheme in schemes_to_check:
            base = cls.get_base_path(scheme, start_dir_p)
            if isinstance(base, Path) and base.exists():
                try:
                    rel = p.relative_to(base)
                    rel_str = str(rel).replace("\\", "/")
                    if rel_str == ".":
                        return f"{scheme}://"
                    return f"{scheme}://{rel_str}"
                except ValueError:
                    pass

        try:
            rel = p.relative_to(proj_root)
            rel_str = str(rel).replace("\\", "/")
            return f"project://{rel_str}"
        except ValueError:
            return str(p).replace("\\", "/")

    @classmethod
    def list_schemes(cls, start_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
        """列出所有支援的 URI 協議清單及其當前解析狀態"""
        results = []
        start_p = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        proj_root = ProjectContext.get_project_root(start_p)

        # 1. Core Schemes
        yscb_root = ProjectContext.get_yscb_root(start_p)
        results.append({
            "scheme": "project://",
            "module": "core (Base)",
            "setting": "project_root",
            "resolved_path": str(proj_root),
            "status": "ACTIVE"
        })
        results.append({
            "scheme": "yscb://",
            "module": "core (Base)",
            "setting": "yscb_root",
            "resolved_path": str(yscb_root),
            "status": "ACTIVE" if yscb_root.is_dir() else "UNINITIALIZED"
        })

        # 2. Dynamic Schemes
        for scheme, (mod_name, key, default_fb) in cls.DYNAMIC_SCHEMES.items():
            base_res = cls.get_base_path(scheme, start_p)
            mod_dir = ProjectContext.get_module_dir(mod_name, start_p)
            
            if not mod_dir.is_dir():
                status = "UNINSTALLED"
                res_str = str(base_res) if isinstance(base_res, Path) else "!undefined"
            elif isinstance(base_res, Path):
                status = "ACTIVE"
                res_str = str(base_res)
            else:
                status = "UNINITIALIZED"
                res_str = "!undefined"

            results.append({
                "scheme": f"{scheme}://",
                "module": mod_name,
                "setting": f"paths.{key}",
                "resolved_path": res_str,
                "status": status
            })

        return results
