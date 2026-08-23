"""
yscb_core.context — YS-Codebase 專案環境與路徑解析器 (Project Context & Path Resolver)
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Union, Dict, Any, List, Tuple


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
                    if custom_proj and not cls.is_undefined(custom_proj):
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
                if custom_yscb and not cls.is_undefined(custom_yscb):
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
            env_path = Path(env_mod).resolve()
            # 僅在環境變數確實指向「目標模組」時採用，避免跨模組查詢
            # (如 A 模組查詢 B 模組的目錄) 被當前執行中模組的環境變數汙染
            if env_path.name == module_name:
                return env_path

        if start_dir:
            s_path = Path(start_dir).resolve()
            if s_path.is_dir() and s_path.name == module_name:
                return s_path
            if (s_path / "modules" / module_name).is_dir():
                return (s_path / "modules" / module_name).resolve()
            if (s_path / "source" / module_name).is_dir():
                return (s_path / "source" / module_name).resolve()

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
    def is_undefined(cls, val: Any) -> bool:
        """檢查設定值是否為未初始化標記 (!undefined, 空值或以 ! 開頭)"""
        if val is None:
            return True
        s = str(val).strip()
        return s == "" or s.startswith("!")

    @classmethod
    def get_module_manifest(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Optional[Dict[str, Any]]:
        """讀取指定模組之 manifest.json 內容，若不存在回傳 None"""
        mod_dir = cls.get_module_dir(module_name, start_dir)
        manifest_file = mod_dir / "manifest.json"
        if manifest_file.is_file():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    @classmethod
    def get_module_version(cls, module_name: str, start_dir: Optional[Union[str, Path]] = None) -> Optional[Any]:
        """讀取指定模組之 manifest.json 並回傳 SemVer 實例，未安裝或不存在回傳 None"""
        manifest = cls.get_module_manifest(module_name, start_dir)
        if manifest and "version" in manifest:
            try:
                from .semver import SemVer
            except (ImportError, ValueError):
                from semver import SemVer
            try:
                return SemVer(manifest["version"])
            except Exception:
                return None
        return None

    @classmethod
    def resolve(cls, rel_path: Union[str, Path], base_dir: Optional[Union[str, Path]] = None) -> Path:
        """將相對於專案根目錄的路徑字串或語意 URI (project://, yscb://, docs:// 等) 解析為標準絕對 Path"""
        if cls.is_undefined(rel_path):
            raise ValueError(f"指定路徑尚未初始化 (!undefined 或空值)：{rel_path}")
        s = str(rel_path).strip()
        if "://" in s:
            try:
                from .uri import ProjectURI
            except (ImportError, ValueError):
                from uri import ProjectURI
            res = ProjectURI.resolve(s, start_dir=base_dir)
            if isinstance(res, Path):
                return res
            if cls.is_undefined(res):
                raise ValueError(f"無法解析語意 URI ({rel_path})：目標尚未初始化 (!undefined)")
            return Path(str(res)).resolve()

        p = Path(s)
        if p.is_absolute():
            return p
        base = Path(base_dir).resolve() if base_dir else cls.get_project_root()
        return (base / p).resolve()

    @classmethod
    def get_all_installed_manifests(cls, start_dir: Optional[Union[str, Path]] = None) -> Dict[str, Tuple[Path, Dict[str, Any]]]:
        """
        掃描所有已安裝模組 (modules/) 與源碼模組 (source/) 之 manifest.json。
        回傳: Dict[mod_name, Tuple(mod_dir, manifest_dict)]
        """
        proj_root = cls.get_project_root(start_dir)
        results: Dict[str, Tuple[Path, Dict[str, Any]]] = {}

        candidate_roots = [
            proj_root / "modules",
            proj_root / "source",
            proj_root / "ys_codebase" / "modules",
            proj_root / "ys_codebase" / "source",
        ]

        for root in candidate_roots:
            if root.is_dir():
                # 依名稱排序掃描，保證跨平台/跨檔案系統之決定性結果
                for mod_dir in sorted(root.iterdir(), key=lambda p: p.name):
                    if mod_dir.is_dir():
                        manifest_path = mod_dir / "manifest.json"
                        if manifest_path.is_file() and mod_dir.name not in results:
                            try:
                                with open(manifest_path, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                if isinstance(data, dict):
                                    mod_name = data.get("name", mod_dir.name)
                                    results[mod_name] = (mod_dir.resolve(), data)
                            except Exception:
                                pass
        return results

    @classmethod
    def get_contributions(cls, namespace: str, start_dir: Optional[Union[str, Path]] = None) -> List[Tuple[str, Path, Dict[str, Any]]]:
        """
        安全掃描所有已安裝/源碼模組中，宣告於指定 namespace 之貢獻內容。
        回傳: List of Tuple(模組名稱, 模組實體目錄路徑, 貢獻 Payload 字典)
        """
        results: List[Tuple[str, Path, Dict[str, Any]]] = []
        manifests = cls.get_all_installed_manifests(start_dir)
        # 依模組名稱排序，確保多模組貢獻之疊加順序具決定性
        for mod_name, (mod_dir, manifest) in sorted(manifests.items()):
            contributes = manifest.get("contributes")
            if isinstance(contributes, dict) and namespace in contributes:
                payload = contributes[namespace]
                if isinstance(payload, dict):
                    results.append((mod_name, mod_dir, payload))
        return results

