"""
VS Code Workspace Settings Projector (`vscode_support/projector.py`).
Manages `yscb.venv://current-site-packages` stable directory link, auto-creates `project://.vscode/`,
soft-merges `extraPaths`, `excludes`, `analysisExclude`, and `json.schemas` under `_yscb_managed`,
and provides 100% clean revert on `remove vscode-support` or `vscode-support revert`.
"""

import copy
import json
import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from core import uri, vfs
from core.log import log
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

        if ch in ("}", "]"):
            k = len(chars) - 1
            while k >= 0 and chars[k] in (" ", "\t", "\r", "\n"):
                k -= 1
            while k >= 0 and chars[k] == ",":
                del chars[k]
                k -= 1

        chars.append(ch)
        i += 1

    return "".join(chars)


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
    ANALYSIS_EXCLUDE_PATTERNS = (
        "**/.cache/**",
        "**/.config.local/**",
        "**/.storage.local/**",
        "**/.snapshots/**",
        "**/.build/**",
        "**/.mirror/**",
        "**/.modules/**",
        "**/.venv/**",
    )
    EXCLUDE_KEYS = (
        ("files.watcherExclude", "**/.venv/**"),
        ("search.exclude", "**/.venv/**"),
        ("files.exclude", "**/.venv"),
    )

    def __init__(self, yscb_dir: Optional[str] = None) -> None:
        self.yscb_dir = os.path.abspath(yscb_dir or uri.resolve_yscb_root())
        self.pip_mgr = PipManager(self.yscb_dir)
        self.schema_compiler = SchemaCompiler(self.yscb_dir)
        self.last_revert_error: Optional[str] = None

    @staticmethod
    def is_vscode_configured(proj_root: str) -> bool:
        """檢查 `project://.vscode` 目錄是否已存在。"""
        vscode_dir = os.path.join(proj_root, ".vscode")
        return os.path.isdir(vscode_dir)

    @staticmethod
    def _load_settings_jsonc(settings_path: str) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
        """單次讀取 `settings.json`，依序嘗試標準 JSON 與 JSONC 解析，回傳 `(data_dict_or_none, had_jsonc, raw_original)`。"""
        try:
            raw_original = vfs.read_text(settings_path)
        except Exception:
            return None, False, None
        try:
            data = json.loads(raw_original)
            had_jsonc = False
        except Exception:
            had_jsonc = True
            try:
                data = json.loads(strip_jsonc(raw_original))
            except Exception:
                return None, True, raw_original
        if not isinstance(data, dict):
            return None, False, None
        return data, had_jsonc, raw_original

    @staticmethod
    def _set_or_pop_list(settings: Dict[str, Any], key: str, items: List[Any]) -> None:
        """當清單非空時寫入 `settings[key]`，為空時自 `settings` 移除該鍵。"""
        if items:
            settings[key] = items
        else:
            settings.pop(key, None)

    @staticmethod
    def _safe_str_list(record: Dict[str, Any], key: str) -> List[str]:
        """安全讀取字典中之字串清單欄位，若非 list 或元素非 str 則過濾並回退為空清單。"""
        val = record.get(key)
        if not isinstance(val, list):
            return []
        return [item for item in val if isinstance(item, str)]

    @staticmethod
    def _safe_dict(record: Dict[str, Any], key: str) -> Dict[str, Any]:
        """安全讀取字典中之子字典欄位，若非 dict 則回退為空字典。"""
        val = record.get(key)
        if not isinstance(val, dict):
            return {}
        return dict(val)

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

    def _is_under_yscb_venv(self, cand_path: str, proj_root: str, allow_root: bool = False) -> bool:
        """判定給定路徑正規化後是否位於 `self.yscb_dir/.venv` 目錄下。"""
        try:
            cand = cand_path.replace("\\", "/")
            if not os.path.isabs(cand):
                cand = os.path.join(proj_root, cand)
            abs_cand = os.path.normcase(os.path.abspath(cand))
            venv_root = os.path.normcase(os.path.abspath(os.path.join(self.yscb_dir, ".venv")))
            return (allow_root and abs_cand == venv_root) or abs_cand.startswith(venv_root + os.sep)
        except Exception:
            return False

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
        return self._is_under_yscb_venv(value, proj_root, allow_root=True)

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
            return self._is_under_yscb_venv(norm, proj_root, allow_root=False)
        return False

    @staticmethod
    def _translate_exclude_to_vscode_glob(raw_pattern: str) -> Optional[str]:
        """將 `core.space` 之 `workspace` 排除規則（語意 URI 如 `yscb://.modules/**` 或裸目錄名）轉譯為 VS Code `**/...` Glob。"""
        clean = str(raw_pattern or "").strip().replace("\\", "/")
        if not clean:
            return None
        if "://" in clean:
            after = clean.split("://", 1)[1].strip("/")
            if after.endswith("/**"):
                after = after[:-3].strip("/")
            elif after.endswith("/*"):
                after = after[:-2].strip("/")
            if not after or "*" in after or "?" in after:
                return None
            return f"**/{after}/**"
        if clean.startswith("**/") and clean.endswith("/**"):
            return clean
        clean_stripped = clean.strip("/")
        if clean_stripped.endswith("/**"):
            clean_stripped = clean_stripped[:-3].strip("/")
        if (
            clean_stripped
            and "/" not in clean_stripped
            and "*" not in clean_stripped
            and "?" not in clean_stripped
            and clean_stripped not in (".DS_Store", "Thumbs.db")
        ):
            return f"**/{clean_stripped}/**"
        return None

    def _resolve_workspace_exclude_patterns(
        self,
        proj_root: Optional[str] = None,
        *,
        include_all: bool = False,
    ) -> List[str]:
        """從 `core.space` 讀取 `workspace` 空間之 `effective_exclude`，搭配 `ANALYSIS_EXCLUDE_PATTERNS` 作為兜底基底。"""
        translated: List[str] = []
        try:
            from core.space import SpaceRegistry

            reg = SpaceRegistry(project_root=proj_root, yscb_dir=self.yscb_dir)
            ws_spaces = reg.resolve_spaces("workspace")
            for sp_cfg in ws_spaces:
                rules = getattr(sp_cfg, "effective_exclude", None) or getattr(sp_cfg, "exclude", ())
                for rule_item in rules:
                    raw_pat = getattr(rule_item, "raw_pattern", rule_item)
                    glob_pat = self._translate_exclude_to_vscode_glob(str(raw_pat))
                    if glob_pat and glob_pat not in translated:
                        translated.append(glob_pat)
        except Exception:
            translated = []

        merged = list(self.ANALYSIS_EXCLUDE_PATTERNS)
        if include_all:
            for pat in translated:
                if pat not in merged:
                    merged.append(pat)
            return merged
        translated_set = set(translated)
        if not translated_set:
            return merged
        return [pat for pat in self.ANALYSIS_EXCLUDE_PATTERNS if pat in translated_set or pat in merged]

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

        was_managed = self.YSCB_MANAGED_KEY in settings
        old_managed_record = settings.get(self.YSCB_MANAGED_KEY, {})
        if not isinstance(old_managed_record, dict):
            old_managed_record = {}
        old_managed_paths = set(self._safe_str_list(old_managed_record, "extraPaths"))

        retained_paths = [
            p
            for p in raw_extra
            if p not in old_managed_paths and not self._is_legacy_yscb_venv_extra_path(p, proj_root)
        ]

        final_extra_paths = list(retained_paths)
        for mp in new_managed_paths:
            if mp not in final_extra_paths:
                final_extra_paths.append(mp)

        self._set_or_pop_list(settings, "python.analysis.extraPaths", final_extra_paths)

        old_managed_interpreter = old_managed_record.get("defaultInterpreterPath")
        current_interpreter = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(current_interpreter, proj_root, old_managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

        old_managed_excludes = self._safe_dict(old_managed_record, "excludes")
        excl_map = dict(self.EXCLUDE_KEYS)
        managed_excludes: Dict[str, str] = {}
        for old_sec, old_pat in old_managed_excludes.items():
            if not isinstance(old_sec, str) or not isinstance(old_pat, str):
                continue
            if excl_map.get(old_sec) != old_pat:
                if old_sec in settings and isinstance(settings[old_sec], dict):
                    settings[old_sec].pop(old_pat, None)
                    if not settings[old_sec]:
                        settings.pop(old_sec, None)
            else:
                managed_excludes[old_sec] = old_pat

        for sec, pattern in excl_map.items():
            if sec not in settings or not isinstance(settings[sec], dict):
                settings[sec] = {}
            if pattern not in settings[sec] or sec in old_managed_excludes:
                settings[sec][pattern] = True
                managed_excludes[sec] = pattern

        has_modules_extra = any("/.modules/" in str(p).replace("\\", "/") for p in new_managed_paths)
        base_analysis_excludes = self._resolve_workspace_exclude_patterns(proj_root)
        active_analysis_exclude = [
            pat
            for pat in base_analysis_excludes
            if not (has_modules_extra and pat == "**/.modules/**")
        ]

        raw_analysis_exclude = settings.get("python.analysis.exclude", [])
        if not isinstance(raw_analysis_exclude, list):
            raw_analysis_exclude = []

        old_managed_analysis = set(self._safe_str_list(old_managed_record, "analysisExclude"))
        if was_managed and not isinstance(old_managed_record.get("analysisExclude"), list):
            removable_old_analysis = set(self.ANALYSIS_EXCLUDE_PATTERNS)
        else:
            removable_old_analysis = old_managed_analysis

        retained_analysis_excl = [
            p
            for p in raw_analysis_exclude
            if p not in removable_old_analysis and not (has_modules_extra and p == "**/.modules/**")
        ]
        final_analysis_excl = list(retained_analysis_excl)
        managed_analysis_excl: List[str] = []
        for pat in active_analysis_exclude:
            if pat not in final_analysis_excl:
                final_analysis_excl.append(pat)
                managed_analysis_excl.append(pat)
        self._set_or_pop_list(settings, "python.analysis.exclude", final_analysis_excl)

        # 合併 json.schemas (依 url 差集替換，保留使用者自訂條目)
        managed_schema_urls: List[str] = []
        if schema_bindings is not None:
            raw_json_schemas = settings.get("json.schemas", [])
            if not isinstance(raw_json_schemas, list):
                raw_json_schemas = []
            old_managed_urls = set(self._safe_str_list(old_managed_record, "jsonSchemas"))
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
            self._set_or_pop_list(settings, "json.schemas", final_schemas)
        else:
            managed_schema_urls = self._safe_str_list(old_managed_record, "jsonSchemas")

        managed_dict: Dict[str, Any] = {
            "description": "Auto-managed by YSCB vscode-support module. Reversible via 'yscb vscode-support revert' or module uninstall.",
            "extraPaths": new_managed_paths,
            "excludes": managed_excludes,
            "analysisExclude": managed_analysis_excl,
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
        initial_snapshot: Optional[Dict[str, Any]] = None
        if vfs.is_file(settings_path):
            loaded_data, had_jsonc, raw_original = self._load_settings_jsonc(settings_path)
            if loaded_data is None:
                if had_jsonc and raw_original is not None:
                    bak_path = settings_path + ".bak"
                    try:
                        vfs.write_text(bak_path, raw_original, encoding="utf-8", atomic=True)
                    except Exception:
                        pass
                    log(
                        f"[vscode-support] Warning: '{settings_path}' contains unrecoverable JSON syntax errors "
                        f"(backed up to '{os.path.basename(bak_path)}'); skipped VS Code settings sync to preserve user file.",
                        stream="stderr",
                    )
                return False
            settings = loaded_data
            if not had_jsonc:
                initial_snapshot = copy.deepcopy(settings)
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

        if initial_snapshot is not None and settings == initial_snapshot:
            return True

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
        self.last_revert_error = None
        if not self.is_vscode_configured(proj_root):
            return False

        settings_path = os.path.join(proj_root, ".vscode", "settings.json")
        if not vfs.is_file(settings_path):
            return False

        settings, had_jsonc, raw_original = self._load_settings_jsonc(settings_path)
        if settings is None:
            if raw_original is None or had_jsonc:
                self.last_revert_error = f"Failed to read or parse '{settings_path}' during revert."
            return False
        if self.YSCB_MANAGED_KEY not in settings:
            return False

        self.remove_stable_site_packages_link()

        schemas_dir = os.path.join(proj_root, ".vscode", "schemas")
        if os.path.isdir(schemas_dir):
            vfs.robust_rmtree(schemas_dir, ignore_errors=True)

        managed_record = settings.pop(self.YSCB_MANAGED_KEY, {})
        if not isinstance(managed_record, dict):
            managed_record = {}
        managed_extra = set(self._safe_str_list(managed_record, "extraPaths"))
        managed_interpreter = managed_record.get("defaultInterpreterPath")

        # 剔除 YSCB 注入之 extraPaths
        raw_extra = settings.get("python.analysis.extraPaths", [])
        if isinstance(raw_extra, list):
            clean_extra = [
                p
                for p in raw_extra
                if p not in managed_extra and not self._is_legacy_yscb_venv_extra_path(p, proj_root)
            ]
            self._set_or_pop_list(settings, "python.analysis.extraPaths", clean_extra)

        # 剔除 YSCB 注入之 defaultInterpreterPath (若存在舊版殘留)
        curr_interp = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(curr_interp, proj_root, managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

        # 剔除 YSCB 注入之 excludes
        managed_excludes = self._safe_dict(managed_record, "excludes")
        for sec, pattern in managed_excludes.items():
            if isinstance(sec, str) and isinstance(pattern, str) and sec in settings and isinstance(settings[sec], dict):
                settings[sec].pop(pattern, None)
                if not settings[sec]:
                    settings.pop(sec, None)

        # 剔除 YSCB 注入之 analysisExclude
        managed_analysis_excl = set(self._safe_str_list(managed_record, "analysisExclude"))
        raw_analysis_excl = settings.get("python.analysis.exclude", [])
        if isinstance(raw_analysis_excl, list) and managed_analysis_excl:
            clean_analysis_excl = [p for p in raw_analysis_excl if p not in managed_analysis_excl]
            self._set_or_pop_list(settings, "python.analysis.exclude", clean_analysis_excl)

        # 剔除 YSCB 注入之 json.schemas
        managed_schema_urls = set(self._safe_str_list(managed_record, "jsonSchemas"))
        raw_json_schemas = settings.get("json.schemas", [])
        if isinstance(raw_json_schemas, list) and managed_schema_urls:
            clean_schemas = [
                item
                for item in raw_json_schemas
                if not (isinstance(item, dict) and item.get("url") in managed_schema_urls)
            ]
            self._set_or_pop_list(settings, "json.schemas", clean_schemas)

        try:
            vfs.write_json(settings_path, settings, indent=2, atomic=True)
            return True
        except Exception as exc:
            self.last_revert_error = f"Failed to write '{settings_path}' during revert: {exc}"
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
        link_active = bool(
            link_exists
            and link_target
            and os.path.isdir(link_path)
            and os.path.isdir(link_target)
        )

        is_managed = False
        managed_extra_paths: List[str] = []
        managed_schemas: List[str] = []
        if vfs.is_file(settings_path):
            data, _, _ = self._load_settings_jsonc(settings_path)
            if data is not None and self.YSCB_MANAGED_KEY in data:
                is_managed = True
                rec = data[self.YSCB_MANAGED_KEY]
                if isinstance(rec, dict):
                    managed_extra_paths = self._safe_str_list(rec, "extraPaths")
                    managed_schemas = self._safe_str_list(rec, "jsonSchemas")

        return {
            "project_root": proj_root,
            "vscode_dir_exists": os.path.isdir(vscode_dir),
            "settings_managed": is_managed,
            "stable_link_path": link_path,
            "stable_link_active": link_active,
            "stable_link_target": link_target,
            "schemas_dir_exists": os.path.isdir(schemas_dir),
            "managed_extra_paths": managed_extra_paths,
            "managed_schemas": managed_schemas,
            "managed_schema_count": len(managed_schemas),
        }
