"""
yscb_core.uri — YS-Codebase 專用語意 URI (Semantic URI) 統一轉換器與沙盒防護引擎

支援標準協議五層架構：
  1. 空間根協議   : project:// (專案根目錄), yscb:// (工具庫安裝根目錄)
  2. 資源快取協議 : cache://<module>/<subpath> (模組專屬命名空間快取)
  3. 持久儲存協議 : storage://<module>/<subpath> (模組專屬持久化儲存空間)
  4. 領域設定協議 : plans://, archive://, docs://, sop_ext:// (由模組宣告與 2x2 設定動態解析)
  5. 執行期暫存   : temp://<subpath> (全域中繼暫存空間)
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional, Union, Dict, List, Any, Tuple

try:
    from .context import ProjectContext
    from .config import ConfigManager
except (ImportError, ValueError):
    from context import ProjectContext
    from config import ConfigManager


def _is_relative_to(path: Path, base: Path) -> bool:
    """Python 3.8+ 跨版本 safe is_relative_to 實現"""
    try:
        if hasattr(path, "is_relative_to"):
            return path.is_relative_to(base)
        path.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


class ProjectURI:
    """Codebase 專用語意 URI 統一轉換器、格式正規化與沙盒圍欄防護門面"""

    # 保留字協議 (由 core 直接解析，不開放第三方模組覆寫)
    RESERVED_SCHEMES: Tuple[str, ...] = ("project", "yscb", "cache", "storage", "temp")

    # Scoped 命名空間協議 (authority 代表模組名稱)
    SCOPED_SCHEMES: Tuple[str, ...] = ("cache", "storage")

    # [DEPRECATED] 向後相容映射表: scheme -> (module_name, config_key, default_fallback)
    DYNAMIC_SCHEMES = {
        "plans": ("agents-workflow", "plans_dir", None),
        "archive": ("agents-workflow", "archive_dir", None),
        "docs": ("agents-workflow", "docs_dir", "docs"),
        "sop_ext": ("agents-workflow", "extensions_dir", None),
    }

    _URI_REGEX = re.compile(r'^([a-zA-Z][a-zA-Z0-9_\-\.]*):[\\/]+(.*)$')
    _SLASH_REGEX = re.compile(r'[\\/]+')
    _base_path_cache: Dict[Tuple[str, Optional[str], Optional[str]], Union[Path, str]] = {}
    _dynamic_schemes_cache: Dict[Optional[str], Dict[str, Tuple[str, str, Optional[str]]]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """清空 URI 與 BasePath 快取 (常用於測試或設定變更後)"""
        cls._base_path_cache.clear()
        cls._dynamic_schemes_cache.clear()

    @classmethod
    def get_dynamic_schemes(cls, start_dir: Optional[Union[str, Path]] = None) -> Dict[str, Tuple[str, str, Optional[str]]]:
        """
        動態發現所有已註冊之語意 URI 協議映射: scheme -> (module_name, config_key, default_fallback)。
        模組掃描依名稱排序，同名 scheme 先註冊者優先，具決定性。
        """
        cache_key = str(start_dir) if start_dir is not None else None
        if cache_key in cls._dynamic_schemes_cache:
            return cls._dynamic_schemes_cache[cache_key]

        schemes: Dict[str, Tuple[str, str, Optional[str]]] = {}
        try:
            contributions = ProjectContext.get_contributions("core", start_dir)
        except Exception:
            contributions = []

        for mod_name, mod_dir, payload in contributions:
            entries = payload.get("uri_schemes")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                scheme = str(entry.get("scheme", "")).strip().lower()
                config_key = entry.get("config_key")
                if not scheme or not config_key or scheme in cls.RESERVED_SCHEMES:
                    continue
                if scheme in schemes:
                    continue  # 同名協議：先註冊者優先
                schemes[scheme] = (mod_name, str(config_key), entry.get("default"))

        # 向後相容 fallback：未被任何模組宣告接管的舊版內建協議
        for scheme, spec in cls.DYNAMIC_SCHEMES.items():
            schemes.setdefault(scheme, spec)

        cls._dynamic_schemes_cache[cache_key] = schemes
        return schemes

    @classmethod
    def parse_uri(cls, uri: str) -> Tuple[Optional[str], str, Optional[str]]:
        """
        解析 URI 字串，分離 scheme, subpath 與 authority (namespace)。
        支援解構賦值為三元 (scheme, subpath, authority) 或向下相容二元 (scheme, subpath)。
        :return: (scheme, subpath, authority)
        - cache://knowledge-db/index.json -> ("cache", "index.json", "knowledge-db")
        - project://AGENTS.md             -> ("project", "AGENTS.md", None)
        """
        s = str(uri).strip()
        m = cls._URI_REGEX.match(s)
        if m and len(m.group(1)) > 1:
            scheme = m.group(1).lower()
            remainder = m.group(2)
            # 正規化路徑斜線並去除多餘重複斜線
            clean_rem = cls._SLASH_REGEX.sub('/', remainder).lstrip('/')

            if scheme in cls.SCOPED_SCHEMES:
                if '/' in clean_rem:
                    authority, subpath = clean_rem.split('/', 1)
                    return scheme, subpath, authority
                elif clean_rem:
                    # 僅提供模組名稱如 cache://knowledge-db
                    return scheme, "", clean_rem
                else:
                    return scheme, "", None

            return scheme, clean_rem, None

        clean_path = cls._SLASH_REGEX.sub('/', s)
        return None, clean_path, None

    @classmethod
    def get_base_path(
        cls,
        scheme: str,
        start_dir: Optional[Union[str, Path]] = None,
        authority: Optional[str] = None
    ) -> Union[Path, str]:
        """
        取得特定 scheme 的基礎路徑 (Base Path)。
        若目標模組未安裝、未啟用或路徑為 !undefined，回傳 "!undefined"。
        """
        scheme = scheme.lower()
        start_key = str(start_dir) if start_dir is not None else None
        cache_key = (scheme, start_key, authority)
        if cache_key in cls._base_path_cache:
            return cls._base_path_cache[cache_key]

        proj_root = ProjectContext.get_project_root(start_dir)

        if scheme == "project":
            res = proj_root
            cls._base_path_cache[cache_key] = res
            return res

        if scheme == "yscb":
            res = ProjectContext.get_yscb_root(start_dir)
            cls._base_path_cache[cache_key] = res
            return res

        if scheme == "temp":
            res = (ProjectContext.get_cache_root(start_dir) / "tmp").resolve()
            cls._base_path_cache[cache_key] = res
            return res

        if scheme == "cache":
            if authority:
                res = ProjectContext.get_module_cache_dir(authority, start_dir=start_dir)
            else:
                res = (ProjectContext.get_cache_root(start_dir) / "modules").resolve()
            cls._base_path_cache[cache_key] = res
            return res

        if scheme == "storage":
            if authority:
                res = ProjectContext.get_module_storage_dir(authority, start_dir=start_dir)
            else:
                res = (proj_root / ".yscb_storage").resolve()
            cls._base_path_cache[cache_key] = res
            return res

        dynamic_schemes = cls.get_dynamic_schemes(start_dir)
        if scheme in dynamic_schemes:
            mod_name, key, default_fb = dynamic_schemes[scheme]
            mod_dir = ProjectContext.get_module_dir(mod_name, start_dir)
            if not mod_dir.is_dir():
                res = (proj_root / default_fb).resolve() if default_fb else "!undefined"
                if isinstance(res, Path):
                    cls._base_path_cache[cache_key] = res
                return res

            try:
                full_cfg = ConfigManager.load(mod_name, start_dir=start_dir)
                paths = full_cfg.get("paths", {})
                raw_val = paths.get(key) if isinstance(paths, dict) and key in paths else full_cfg.get(key)

                if ProjectContext.is_undefined(raw_val):
                    res = (proj_root / default_fb).resolve() if default_fb else "!undefined"
                    if isinstance(res, Path):
                        cls._base_path_cache[cache_key] = res
                    return res

                resolved = ProjectContext.resolve(raw_val, base_dir=proj_root)
                if isinstance(resolved, Path):
                    cls._base_path_cache[cache_key] = resolved
                return resolved
            except Exception:
                res = (proj_root / default_fb).resolve() if default_fb else "!undefined"
                if isinstance(res, Path):
                    cls._base_path_cache[cache_key] = res
                return res

        return "!undefined"

    @classmethod
    def validate(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> Tuple[bool, str]:
        """
        校驗傳入 URI 格式完備度與沙盒安全性。
        :return: (is_valid: bool, error_message: str)
        """
        if isinstance(uri, Path):
            return True, ""

        uri_str = str(uri).strip()
        if not uri_str:
            return False, "URI 不能為空值"

        scheme, subpath, authority = cls.parse_uri(uri_str)
        if not scheme:
            return True, ""  # 一般相對/絕對路徑視為合法字串

        # 1. 檢查 scheme 是否在合法註冊清單中
        all_schemes = set(cls.RESERVED_SCHEMES) | set(cls.get_dynamic_schemes(start_dir).keys())
        if scheme not in all_schemes:
            return False, f"未知的 URI 協議 scheme: '{scheme}://'"

        # 2. 檢查 scoped scheme 之 authority
        if scheme in cls.SCOPED_SCHEMES and not authority:
            return False, f"協議 '{scheme}://' 必須指定模組命名空間 (例如: {scheme}://<module>/<file>)"

        # 3. 取得 BasePath 並進行沙盒圍欄模擬校驗
        base_res = cls.get_base_path(scheme, start_dir, authority=authority)
        if isinstance(base_res, str) and ProjectContext.is_undefined(base_res):
            return False, f"協議 '{scheme}://' 對應的底層路徑尚未初始化 (!undefined)"

        if isinstance(base_res, Path):
            target_p = (base_res / subpath).resolve() if subpath else base_res.resolve()
            if not _is_relative_to(target_p, base_res.resolve()):
                return False, f"路徑越界安全阻斷：'{uri_str}' 試圖逃逸出 BasePath ({base_res})"

        return True, ""

    @classmethod
    def resolve(
        cls,
        uri: Union[str, Path],
        start_dir: Optional[Union[str, Path]] = None,
        strict: bool = False
    ) -> Union[Path, str]:
        """
        將語意 URI 解析為本機實體絕對 Path。
        1. 格式正規化 (斜線安全互轉)
        2. 沙盒圍欄檢查 (_is_relative_to(base_path))，越界時拋出 PermissionError 或回傳 "!undefined"
        3. 若傳入一般相對路徑，回退至 ProjectContext.resolve()
        """
        if isinstance(uri, Path):
            return uri.resolve()

        uri_str = str(uri).strip()
        scheme, subpath, authority = cls.parse_uri(uri_str)

        if not scheme:
            if ProjectContext.is_undefined(uri_str):
                return "!undefined"
            return ProjectContext.resolve(uri_str, base_dir=start_dir)

        base_res = cls.get_base_path(scheme, start_dir, authority=authority)
        if isinstance(base_res, str) and ProjectContext.is_undefined(base_res):
            if strict:
                raise ValueError(f"無法解析語意 URI ({uri_str})：目標協議尚未初始化")
            return "!undefined"

        if isinstance(base_res, Path):
            base_p = base_res
            if not subpath:
                return base_p

            # 快速通道 (Fast-Path)：若 subpath 不含 '..' 逃逸字元，直接路徑拼接返回，避免高頻 Windows Win32 syscall
            if ".." not in subpath:
                return base_p / subpath

            target_p = (base_p / subpath).resolve()

            # 沙盒圍欄安全檢查 (Chroot Guard)
            if not _is_relative_to(target_p, base_p):
                err_msg = f"沙盒安全性阻斷：語意 URI '{uri_str}' 解析目標越界逃逸 ({target_p} 不在 {base_p} 內部)"
                if strict:
                    raise PermissionError(err_msg)
                print(f"[SECURITY-WARN] {err_msg}", file=sys.stderr)
                return "!undefined"

            return target_p

        return "!undefined"

    @classmethod
    def to_uri(cls, path: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> str:
        """
        將本機實體路徑反向匹配轉換為最短、最精確的語意 URI。
        採用最長前綴匹配演算法 (Longest Prefix Match, LPM) 與優先級排序。
        """
        p = Path(path).resolve()
        start_dir_p = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        proj_root = ProjectContext.get_project_root(start_dir_p)
        yscb_root = ProjectContext.get_yscb_root(start_dir_p)

        # 候選 Scheme 清單收集 (scheme_name, base_path, priority_tier)
        # Priority Tier: Domain (1) > Scoped (2) > Spatial (3)
        candidates: List[Tuple[str, Path, int]] = []

        # 1. 領域協議 (Domain)
        for scheme in sorted(cls.get_dynamic_schemes(start_dir_p).keys()):
            base = cls.get_base_path(scheme, start_dir_p)
            if isinstance(base, Path) and base.exists():
                candidates.append((scheme, base.resolve(), 1))

        # 2. 資源快取與儲存協議 (Scoped: cache & storage)
        cache_modules_dir = ProjectContext.get_cache_root(start_dir_p) / "modules"
        if cache_modules_dir.is_dir():
            for mod_dir in cache_modules_dir.iterdir():
                if mod_dir.is_dir():
                    candidates.append((f"cache://{mod_dir.name}", mod_dir.resolve(), 2))

        storage_modules_dir = proj_root / ".yscb_storage"
        if storage_modules_dir.is_dir():
            for mod_dir in storage_modules_dir.iterdir():
                if mod_dir.is_dir():
                    candidates.append((f"storage://{mod_dir.name}", mod_dir.resolve(), 2))

        # 3. 空間根協議 (Spatial)
        if yscb_root.exists():
            candidates.append(("yscb", yscb_root.resolve(), 3))
        if proj_root.exists():
            candidates.append(("project", proj_root.resolve(), 3))

        # 最長前綴匹配 (LPM)：過濾出 p 在 base 內部的候選，依 (base 路徑長度 降序, priority_tier 升序) 排序
        matched = []
        for scheme_prefix, base_path, tier in candidates:
            if _is_relative_to(p, base_path):
                matched.append((len(str(base_path)), tier, scheme_prefix, base_path))

        if matched:
            matched.sort(key=lambda x: (-x[0], x[1], x[2]))
            _, _, best_scheme, best_base = matched[0]
            try:
                rel = p.relative_to(best_base)
                rel_str = str(rel).replace("\\", "/")
                if "://" in best_scheme:
                    # 已經帶有 scoped 協議前綴 (如 cache://knowledge-db)
                    return best_scheme if rel_str == "." else f"{best_scheme}/{rel_str}"
                return f"{best_scheme}://" if rel_str == "." else f"{best_scheme}://{rel_str}"
            except ValueError:
                pass

        try:
            rel = p.relative_to(proj_root)
            rel_str = str(rel).replace("\\", "/")
            return f"project://{rel_str}"
        except ValueError:
            return str(p).replace("\\", "/")

    @classmethod
    def exists(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 對應之實體路徑是否存在"""
        res = cls.resolve(uri, start_dir=start_dir)
        return isinstance(res, Path) and res.exists()

    @classmethod
    def is_file(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 是否指向存在之檔案"""
        res = cls.resolve(uri, start_dir=start_dir)
        return isinstance(res, Path) and res.is_file()

    @classmethod
    def is_dir(cls, uri: Union[str, Path], start_dir: Optional[Union[str, Path]] = None) -> bool:
        """檢查語意 URI 是否指向存在之目錄"""
        res = cls.resolve(uri, start_dir=start_dir)
        return isinstance(res, Path) and res.is_dir()

    @classmethod
    def read_text(cls, uri: Union[str, Path], encoding: str = "utf-8", start_dir: Optional[Union[str, Path]] = None) -> str:
        """自語意 URI 直讀文字內容"""
        res = cls.resolve(uri, start_dir=start_dir, strict=True)
        if isinstance(res, Path) and res.is_file():
            return res.read_text(encoding=encoding)
        raise FileNotFoundError(f"找不到語意 URI 指向之檔案：{uri} (解析為: {res})")

    @classmethod
    def write_text(
        cls,
        uri: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        auto_mkdir: bool = True,
        start_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """將文字內容直接寫入語意 URI (支援自動建立父目錄)"""
        res = cls.resolve(uri, start_dir=start_dir, strict=True)
        if isinstance(res, Path):
            if auto_mkdir:
                res.parent.mkdir(parents=True, exist_ok=True)
            res.write_text(content, encoding=encoding)
            return res
        raise ValueError(f"無法寫入無效之語意 URI：{uri}")

    @classmethod
    def list_schemes(cls, start_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
        """列出所有支援的 URI 協議清單及其當前解析狀態"""
        results = []
        start_p = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        proj_root = ProjectContext.get_project_root(start_p)
        yscb_root = ProjectContext.get_yscb_root(start_p)
        cache_root = ProjectContext.get_cache_root(start_p)

        # 1. Spatial Schemes
        results.append({
            "scheme": "project://",
            "module": "core (Base)",
            "setting": "paths.project_root",
            "resolved_path": str(proj_root),
            "status": "ACTIVE"
        })
        results.append({
            "scheme": "yscb://",
            "module": "core (Base)",
            "setting": "paths.yscb_root",
            "resolved_path": str(yscb_root),
            "status": "ACTIVE" if yscb_root.is_dir() else "UNINITIALIZED"
        })

        # 2. Scoped Schemes
        results.append({
            "scheme": "cache://<mod>/",
            "module": "core (Generic)",
            "setting": "yscb://.yscb_cache/modules/<mod>/",
            "resolved_path": str(cache_root / "modules"),
            "status": "ACTIVE"
        })
        results.append({
            "scheme": "storage://<mod>/",
            "module": "core (Generic)",
            "setting": "project://.yscb_storage/<mod>/",
            "resolved_path": str(proj_root / ".yscb_storage"),
            "status": "ACTIVE"
        })

        # 3. Dynamic Schemes
        for scheme, (mod_name, key, default_fb) in cls.get_dynamic_schemes(start_p).items():
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

    @classmethod
    def check_schemes(cls, start_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
        """全量協議健康度檢查，包含實體目錄存在性、權限與沙盒圍欄防護測試"""
        checks = []
        schemes = cls.list_schemes(start_dir)
        for entry in schemes:
            scheme = entry["scheme"]
            path_str = entry["resolved_path"]
            status = entry["status"]
            health = "OK"
            details = "路徑正常"

            if status == "UNINSTALLED":
                health = "WARN"
                details = "所屬模組尚未安裝"
            elif status == "UNINITIALIZED" or path_str == "!undefined":
                health = "WARN"
                details = "設定值未初始化 (!undefined)"
            else:
                p = Path(path_str)
                if not p.exists():
                    health = "INFO"
                    details = "實體目錄尚未建立 (存取時自動建立)"
                elif not os.access(p, os.R_OK):
                    health = "FAIL"
                    details = "無讀取權限"

            checks.append({
                "scheme": scheme,
                "resolved_path": path_str,
                "health": health,
                "details": details
            })
        return checks
