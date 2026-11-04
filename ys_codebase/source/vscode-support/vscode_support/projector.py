"""
VS Code Workspace Settings Projector (`vscode_support/projector.py`).
Manages `yscb.venv://current-site-packages` stable directory link, auto-creates `project://.vscode/`,
soft-merges `extraPaths`, `excludes`, `analysisExclude`, and `json.schemas` under `_yscb_managed`,
and provides 100% clean revert on `remove vscode-support` or `vscode-support revert`.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from core import uri, vfs
from core.pip_manager import PipManager
from core.platform import list_module_search_roots
from vscode_support.schema_compiler import SchemaCompiler


def strip_jsonc(raw_text: str) -> str:
    """
    String-aware JSONC normalizer that strips single-line comments (``//``),
    multi-line comments (``/* ... */``), and trailing commas before ``}`` or ``]``
    while preserving string literals intact.
    """
    if not raw_text:
        return ""

    # Phase 1: Strip comments outside string literals
    chars: List[str] = []
    n = len(raw_text)
    i = 0
    in_string = False
    while i < n:
        ch = raw_text[i]
        if in_string:
            chars.append(ch)
            if ch == "\\" and i + 1 < n:
                chars.append(raw_text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            chars.append(ch)
            i += 1
            continue

        if ch == "/" and i + 1 < n:
            nxt = raw_text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and raw_text[i] not in ("\n", "\r"):
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (raw_text[i] == "*" and raw_text[i + 1] == "/"):
                    if raw_text[i] in ("\n", "\r"):
                        chars.append(raw_text[i])
                    i += 1
                i += 2
                continue

        chars.append(ch)
        i += 1

    no_comments = "".join(chars)

    # Phase 2: Strip trailing commas before '}' or ']' outside string literals
    out: List[str] = []
    m = len(no_comments)
    j = 0
    in_str = False
    while j < m:
        ch = no_comments[j]
        if in_str:
            out.append(ch)
            if ch == "\\" and j + 1 < m:
                out.append(no_comments[j + 1])
                j += 2
                continue
            if ch == '"':
                in_str = False
            j += 1
            continue

        if ch == '"':
            in_str = True
            out.append(ch)
            j += 1
            continue

        if ch == ",":
            k = j + 1
            while k < m and no_comments[k] in (" ", "\t", "\r", "\n"):
                k += 1
            if k < m and no_comments[k] in ("}", "]"):
                j += 1
                continue

        out.append(ch)
        j += 1

    return "".join(out)


def _safe_remove_link(link_path: str) -> bool:
    """
    安全移除目錄 Symlink 或 Windows Directory Junction，絕不使用 `shutil.rmtree` 遞迴刪除目標實體目錄。
    """
    if not (os.path.lexists(link_path) or os.path.exists(link_path)):
        return False
    try:
        os.unlink(link_path)
        return True
    except OSError:
        try:
            os.rmdir(link_path)
            return True
        except OSError:
            return False


class SettingsProjector:
    """
    VS Code 工作區設定投影器。
    負責維護穩定 site-packages 連結、編譯單檔 JSON Schema 並以 `_yscb_managed` 軟合併 `.vscode/settings.json`。
    """

    YSCB_MANAGED_KEY = "_yscb_managed"
    STABLE_LINK_NAME = "current-site-packages"
    ANALYSIS_EXCLUDE_PATTERNS = [
        "**/.cache/**",
        "**/.config.local/**",
        "**/.storage.local/**",
        "**/.snapshots/**",
        "**/.build/**",
        "**/.mirror/**",
        "**/.modules/**",
        "**/.venv/**",
    ]
    EXCLUDE_KEYS = {
        "files.watcherExclude": "**/.venv/**",
        "search.exclude": "**/.venv/**",
        "files.exclude": "**/.venv",
    }

    def __init__(self, yscb_dir: Optional[str] = None) -> None:
        self.yscb_dir = os.path.abspath(yscb_dir or self._resolve_yscb_root())
        self.pip_mgr = PipManager(self.yscb_dir)
        self.schema_compiler = SchemaCompiler(self.yscb_dir)

    def _resolve_yscb_root(self) -> str:
        return uri.resolve_yscb_root()

    @staticmethod
    def is_vscode_configured(proj_root: str) -> bool:
        """檢查 `project://.vscode` 目錄是否已存在。"""
        vscode_dir = os.path.join(proj_root, ".vscode")
        return os.path.isdir(vscode_dir)

    def get_stable_link_path(self) -> str:
        """取得 `yscb.venv://current-site-packages` 實體絕對路徑。"""
        return os.path.join(self.yscb_dir, ".venv", self.STABLE_LINK_NAME)

    def ensure_stable_site_packages_link(self, py_tag: Optional[str] = None) -> Optional[str]:
        """
        建立或更新指向當前 Python 版本 `site-packages` 之無版本號穩定目錄連結 `yscb.venv://current-site-packages`。
        先確保目標 `site-packages` 實體目錄存在（防範無 `pip_dependencies` 時產生懸空連結）；
        POSIX 使用 `os.symlink`，Windows 優先嘗試 `os.symlink` 或免管理員權限之 `cmd /c mklink /J` Directory Junction。
        若檔案系統不支援則回傳 `None` 由呼叫端自動降級為實際路徑。
        """
        target_site_pkg = os.path.abspath(self.pip_mgr.get_site_packages_dir(py_tag))
        try:
            os.makedirs(target_site_pkg, exist_ok=True)
        except OSError:
            return None

        venv_root = os.path.join(self.yscb_dir, ".venv")
        try:
            os.makedirs(venv_root, exist_ok=True)
        except OSError:
            return None

        link_path = self.get_stable_link_path()

        # 若連結已存在且已指向相同目標，直接復用；若在受限容器環境無法重建連結，保留宿主機已建立之有效目錄連結
        if os.path.lexists(link_path) or os.path.exists(link_path):
            try:
                if os.path.isdir(link_path) and os.path.normcase(os.path.realpath(link_path)) == os.path.normcase(
                    os.path.realpath(target_site_pkg)
                ):
                    return link_path
            except OSError:
                pass
            if not self.pip_mgr._can_symlink(venv_root) and platform.system() != "Windows":
                if os.path.isdir(link_path):
                    return link_path
                return None
            if not _safe_remove_link(link_path):
                return None

        # 嘗試建立目錄連結
        try:
            os.symlink(target_site_pkg, link_path, target_is_directory=True)
            return link_path
        except (OSError, NotImplementedError):
            if platform.system() == "Windows":
                try:
                    proc = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", link_path, target_site_pkg],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=10,
                    )
                    if proc.returncode == 0 and os.path.isdir(link_path):
                        return link_path
                except Exception:
                    pass
        return None

    def remove_stable_site_packages_link(self) -> bool:
        """安全移除 `yscb.venv://current-site-packages` 穩定連結。"""
        return _safe_remove_link(self.get_stable_link_path())

    def _is_yscb_managed_interpreter(
        self,
        value: Any,
        proj_root: str,
        old_managed_value: Any = None,
    ) -> bool:
        """
        判定直譯器路徑是否為 YSCB 託管值（舊版 `_yscb_managed` 記錄值，或位於 YSCB 私有微環境 `yscb_dir/.venv/` 之下）。
        避免誤刪使用者專案自有之 `.venv` 直譯器。
        """
        if not value or not isinstance(value, str):
            return False
        if old_managed_value and value == old_managed_value:
            return True
        try:
            cand = value.replace("\\", "/")
            if not os.path.isabs(cand):
                cand = os.path.join(proj_root, cand)
            abs_cand = os.path.normcase(os.path.abspath(cand))
            venv_root = os.path.normcase(os.path.abspath(os.path.join(self.yscb_dir, ".venv")))
            return abs_cand == venv_root or abs_cand.startswith(venv_root + os.sep)
        except Exception:
            return False

    @staticmethod
    def _format_proj_rel_path(proj_root: str, target_path: str) -> str:
        """將目標絕對路徑格式化為相對於 `proj_root` 之 POSIX 相對路徑（以 `./` 或 `../` 開頭）。"""
        try:
            rel_p = os.path.relpath(target_path, proj_root).replace("\\", "/")
            return f"./{rel_p}" if not rel_p.startswith(("./", "../")) else rel_p
        except Exception:
            return target_path.replace("\\", "/")

    def _compute_managed_extra_paths(
        self,
        proj_root: str,
        extra_paths: Optional[List[str]] = None,
        py_tag: Optional[str] = None,
    ) -> List[str]:
        """
        計算欲注入的 YSCB 管理路徑：
        1. 恆定寫入 `current-site-packages` 穩定連結路徑（確保切換 Python 版本或於受限容器環境同步時 `settings.json` 零變動）；
        2. 透過 `core.platform.list_module_search_roots(self.yscb_dir, prefer_source=True)` 自動投影各模組搜尋根目錄
           （優先選用 `source/<mod>`，否則選用已安裝之 `.modules/<mod>`）。
        """
        new_managed_paths: List[str] = []
        self.ensure_stable_site_packages_link(py_tag=py_tag)
        link_path = self.get_stable_link_path()
        new_managed_paths.append(self._format_proj_rel_path(proj_root, link_path))

        for mod_root in list_module_search_roots(self.yscb_dir, prefer_source=True):
            mod_entry = self._format_proj_rel_path(proj_root, mod_root)
            if mod_entry not in new_managed_paths:
                new_managed_paths.append(mod_entry)

        if extra_paths:
            for ep in extra_paths:
                clean_ep = ep.replace("\\", "/")
                if clean_ep not in new_managed_paths:
                    new_managed_paths.append(clean_ep)
        return new_managed_paths

    def _is_legacy_yscb_venv_extra_path(self, path_entry: Any, proj_root: str) -> bool:
        """識別舊版 `IdeProjector` 注入之 `./ys_codebase/.venv/py3XX/.../site-packages` 路徑以便無痛升級收斂為穩定連結。"""
        if not isinstance(path_entry, str):
            return False
        norm = path_entry.replace("\\", "/")
        if "/.venv/py" in norm and norm.endswith("/site-packages"):
            try:
                cand = norm if os.path.isabs(norm) else os.path.join(proj_root, norm)
                abs_cand = os.path.normcase(os.path.abspath(cand))
                venv_root = os.path.normcase(os.path.abspath(os.path.join(self.yscb_dir, ".venv")))
                return abs_cand.startswith(venv_root + os.sep)
            except Exception:
                return False
        return False

    def _apply_vscode_settings_merge(
        self,
        settings: Dict[str, Any],
        proj_root: str,
        new_managed_paths: List[str],
        schema_bindings: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """於 `settings` 字典原地合併 `extraPaths`、`excludes`、`analysisExclude`、`json.schemas` 與 `_yscb_managed` 標記。"""
        raw_extra = settings.get("python.analysis.extraPaths", [])
        if not isinstance(raw_extra, list):
            raw_extra = []

        old_managed_record = settings.get(self.YSCB_MANAGED_KEY, {})
        if not isinstance(old_managed_record, dict):
            old_managed_record = {}
        old_managed_paths = set(old_managed_record.get("extraPaths", []))

        retained_paths = [
            p
            for p in raw_extra
            if p not in old_managed_paths and not self._is_legacy_yscb_venv_extra_path(p, proj_root)
        ]

        final_extra_paths = list(retained_paths)
        for mp in new_managed_paths:
            if mp not in final_extra_paths:
                final_extra_paths.append(mp)

        if final_extra_paths:
            settings["python.analysis.extraPaths"] = final_extra_paths
        else:
            settings.pop("python.analysis.extraPaths", None)

        old_managed_interpreter = old_managed_record.get("defaultInterpreterPath")
        current_interpreter = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(current_interpreter, proj_root, old_managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

        managed_excludes = dict(old_managed_record.get("excludes", {}))
        for sec, pattern in self.EXCLUDE_KEYS.items():
            if sec not in settings or not isinstance(settings[sec], dict):
                settings[sec] = {}
            if pattern not in settings[sec]:
                settings[sec][pattern] = True
                managed_excludes[sec] = pattern

        has_modules_extra = any("/.modules/" in str(p).replace("\\", "/") for p in new_managed_paths)
        active_analysis_exclude = [
            pat
            for pat in self.ANALYSIS_EXCLUDE_PATTERNS
            if not (has_modules_extra and pat == "**/.modules/**")
        ]

        raw_analysis_exclude = settings.get("python.analysis.exclude", [])
        if not isinstance(raw_analysis_exclude, list):
            raw_analysis_exclude = []
        old_managed_analysis_excl = set(old_managed_record.get("analysisExclude", [])) | set(
            self.ANALYSIS_EXCLUDE_PATTERNS
        )
        final_analysis_excl = [p for p in raw_analysis_exclude if p not in old_managed_analysis_excl]
        for pat in active_analysis_exclude:
            if pat not in final_analysis_excl:
                final_analysis_excl.append(pat)
        if final_analysis_excl:
            settings["python.analysis.exclude"] = final_analysis_excl

        # 合併 json.schemas (依 url 差集替換，保留使用者自訂條目)
        managed_schema_urls: List[str] = []
        if schema_bindings is not None:
            raw_json_schemas = settings.get("json.schemas", [])
            if not isinstance(raw_json_schemas, list):
                raw_json_schemas = []
            old_managed_urls = set(old_managed_record.get("jsonSchemas", []))
            retained_schemas = [
                item
                for item in raw_json_schemas
                if not (isinstance(item, dict) and item.get("url") in old_managed_urls)
            ]
            final_schemas = list(retained_schemas)
            for b in schema_bindings:
                url = b.get("url", "")
                if url:
                    managed_schema_urls.append(url)
                final_schemas.append(b)
            if final_schemas:
                settings["json.schemas"] = final_schemas
            else:
                settings.pop("json.schemas", None)
        else:
            managed_schema_urls = list(old_managed_record.get("jsonSchemas", []))

        managed_dict: Dict[str, Any] = {
            "description": "Auto-managed by YSCB vscode-support module. Reversible via 'yscb vscode-support revert' or module uninstall.",
            "extraPaths": new_managed_paths,
            "excludes": managed_excludes,
            "analysisExclude": list(active_analysis_exclude),
        }
        if managed_schema_urls:
            managed_dict["jsonSchemas"] = managed_schema_urls
        settings[self.YSCB_MANAGED_KEY] = managed_dict

    def sync_vscode_settings(
        self,
        proj_root: str,
        extra_paths: Optional[List[str]] = None,
        py_tag: Optional[str] = None,
        compile_schemas: bool = True,
    ) -> bool:
        """
        同步 VS Code 工作區設定與單檔級 JSON Schema：
        - 若 `project://.vscode/` 不存在則自動建立；
        - 建立或更新 `yscb.venv://current-site-packages` 穩定連結；
        - 編譯所有已安裝模組之單檔 JSON Schema 至 `.vscode/schemas/`；
        - 於 `.vscode/settings.json` 軟合併設定並實作 Zero-Touch 寫入守衛；
        - 若既有 `settings.json` 含 JSONC 註解或語法錯誤，輸出 Warning 並安全略過。
        """
        if not proj_root or not os.path.isdir(proj_root):
            return False

        vscode_dir = os.path.join(proj_root, ".vscode")
        settings_path = os.path.join(vscode_dir, "settings.json")
        settings: Dict[str, Any] = {}
        had_jsonc = False
        raw_original: Optional[str] = None
        if vfs.is_file(settings_path):
            try:
                raw_original = vfs.read_text(settings_path)
            except Exception:
                return False
            try:
                data = json.loads(raw_original)
            except Exception:
                had_jsonc = True
                try:
                    data = json.loads(strip_jsonc(raw_original))
                except Exception:
                    bak_path = settings_path + ".bak"
                    try:
                        vfs.write_text(bak_path, raw_original, encoding="utf-8", atomic=True)
                    except Exception:
                        pass
                    print(
                        f"[vscode-support] Warning: '{settings_path}' contains unrecoverable JSON syntax errors "
                        f"(backed up to '{os.path.basename(bak_path)}'); skipped VS Code settings sync to preserve user file.",
                        file=sys.stderr,
                    )
                    return False
            if not isinstance(data, dict):
                return False
            settings = data
        else:
            try:
                os.makedirs(vscode_dir, exist_ok=True)
            except OSError:
                return False

        schema_bindings: Optional[List[Dict[str, Any]]] = None
        if compile_schemas:
            try:
                schema_bindings = self.schema_compiler.sync_all_schemas(proj_root)
            except Exception:
                schema_bindings = []

        new_managed_paths = self._compute_managed_extra_paths(proj_root, extra_paths=extra_paths, py_tag=py_tag)
        self._apply_vscode_settings_merge(settings, proj_root, new_managed_paths, schema_bindings=schema_bindings)

        if vfs.is_file(settings_path) and not had_jsonc:
            try:
                if vfs.read_json(settings_path) == settings:
                    return True
            except Exception:
                pass

        if had_jsonc and raw_original is not None:
            try:
                vfs.write_text(settings_path + ".bak", raw_original, encoding="utf-8", atomic=True)
            except Exception:
                pass

        try:
            vfs.write_json(settings_path, settings, indent=2, atomic=True)
            return True
        except Exception:
            return False

    def revert_vscode_settings(self, proj_root: str) -> bool:
        """
        依據 `_yscb_managed` 標記清冊，100% 乾淨剔除 YSCB 注入之 `extraPaths`、`excludes`、`analysisExclude` 與 `json.schemas`，
        並清除 `project://.vscode/schemas/` 與 `yscb.venv://current-site-packages` 穩定連結。
        """
        self.remove_stable_site_packages_link()

        schemas_dir = os.path.join(proj_root, ".vscode", "schemas")
        if os.path.isdir(schemas_dir):
            vfs.robust_rmtree(schemas_dir, ignore_errors=True)

        if not self.is_vscode_configured(proj_root):
            return False

        settings_path = os.path.join(proj_root, ".vscode", "settings.json")
        if not vfs.is_file(settings_path):
            return False

        try:
            raw_text = vfs.read_text(settings_path)
            try:
                settings = json.loads(raw_text)
            except Exception:
                settings = json.loads(strip_jsonc(raw_text))
            if not isinstance(settings, dict):
                return False
        except Exception:
            return False

        if self.YSCB_MANAGED_KEY not in settings:
            return False

        managed_record = settings.pop(self.YSCB_MANAGED_KEY, {})
        if not isinstance(managed_record, dict):
            managed_record = {}
        managed_extra = set(managed_record.get("extraPaths", []))
        managed_interpreter = managed_record.get("defaultInterpreterPath")

        # 剔除 YSCB 注入之 extraPaths
        raw_extra = settings.get("python.analysis.extraPaths", [])
        if isinstance(raw_extra, list):
            clean_extra = [
                p
                for p in raw_extra
                if p not in managed_extra and not self._is_legacy_yscb_venv_extra_path(p, proj_root)
            ]
            if clean_extra:
                settings["python.analysis.extraPaths"] = clean_extra
            else:
                settings.pop("python.analysis.extraPaths", None)

        # 剔除 YSCB 注入之 defaultInterpreterPath (若存在舊版殘留)
        curr_interp = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(curr_interp, proj_root, managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

        # 剔除 YSCB 注入之 excludes
        managed_excludes = managed_record.get("excludes", {})
        if isinstance(managed_excludes, dict):
            for sec, pattern in managed_excludes.items():
                if sec in settings and isinstance(settings[sec], dict):
                    settings[sec].pop(pattern, None)

        # 剔除 YSCB 注入之 analysisExclude
        managed_analysis_excl = set(managed_record.get("analysisExclude", []))
        raw_analysis_excl = settings.get("python.analysis.exclude", [])
        if isinstance(raw_analysis_excl, list) and managed_analysis_excl:
            clean_analysis_excl = [p for p in raw_analysis_excl if p not in managed_analysis_excl]
            if clean_analysis_excl:
                settings["python.analysis.exclude"] = clean_analysis_excl
            else:
                settings.pop("python.analysis.exclude", None)

        # 剔除 YSCB 注入之 json.schemas
        managed_schema_urls = set(managed_record.get("jsonSchemas", []))
        raw_json_schemas = settings.get("json.schemas", [])
        if isinstance(raw_json_schemas, list) and managed_schema_urls:
            clean_schemas = [
                item
                for item in raw_json_schemas
                if not (isinstance(item, dict) and item.get("url") in managed_schema_urls)
            ]
            if clean_schemas:
                settings["json.schemas"] = clean_schemas
            else:
                settings.pop("json.schemas", None)

        try:
            vfs.write_json(settings_path, settings, indent=2, atomic=True)
            return True
        except Exception:
            return False

    def get_status(self, proj_root: str) -> Dict[str, Any]:
        """查詢當前 VS Code 工作區投影、穩定連結與單檔 Schema 狀態。"""
        vscode_dir = os.path.join(proj_root, ".vscode")
        settings_path = os.path.join(vscode_dir, "settings.json")
        schemas_dir = os.path.join(vscode_dir, "schemas")
        link_path = self.get_stable_link_path()

        link_exists = os.path.lexists(link_path) or os.path.exists(link_path)
        link_target: Optional[str] = None
        if link_exists:
            try:
                link_target = os.path.realpath(link_path)
            except OSError:
                link_target = None

        is_managed = False
        managed_extra_paths: List[str] = []
        managed_schemas: List[str] = []
        if vfs.is_file(settings_path):
            try:
                data = vfs.read_json(settings_path)
                if isinstance(data, dict) and self.YSCB_MANAGED_KEY in data:
                    is_managed = True
                    rec = data[self.YSCB_MANAGED_KEY]
                    if isinstance(rec, dict):
                        managed_extra_paths = list(rec.get("extraPaths", []))
                        managed_schemas = list(rec.get("jsonSchemas", []))
            except Exception:
                pass

        return {
            "project_root": proj_root,
            "vscode_dir_exists": os.path.isdir(vscode_dir),
            "settings_managed": is_managed,
            "stable_link_path": link_path,
            "stable_link_active": bool(link_exists and link_target),
            "stable_link_target": link_target,
            "schemas_dir_exists": os.path.isdir(schemas_dir),
            "managed_extra_paths": managed_extra_paths,
            "managed_schemas": managed_schemas,
            "managed_schema_count": len(managed_schemas),
        }

