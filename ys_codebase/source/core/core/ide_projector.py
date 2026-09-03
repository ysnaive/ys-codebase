"""
YS-Codebase IDE Automatic Sensing & Reversible Soft-Merge Projector.
100% Python Standard Library, Zero Third-Party Dependency.
Senses if project://.vscode exists; if present, performs non-destructive, reversible
soft-merge of private venv site-packages into .vscode/settings.json with explicit _yscb_managed boundary.
"""

import os
import json
from typing import Optional, List, Dict, Any
from core.pip_manager import PipManager


class IdeProjector:
    """IDE 自動感知投影器：比照 internal yscb gitignore 模式，以 _yscb_managed 執行可復原軟合併。"""

    YSCB_MANAGED_KEY = "_yscb_managed"

    def __init__(self, yscb_dir: Optional[str] = None):
        self.yscb_dir = os.path.abspath(yscb_dir or self._resolve_yscb_root())
        self.pip_mgr = PipManager(self.yscb_dir)

    def _resolve_yscb_root(self) -> str:
        cur = os.path.abspath(os.path.dirname(__file__))
        while cur and cur != os.path.dirname(cur):
            cfg_p = os.path.join(cur, "yscb.config.json")
            if os.path.isfile(cfg_p):
                return cur
            cur = os.path.dirname(cur)
        return os.getcwd()

    @staticmethod
    def is_vscode_configured(proj_root: str) -> bool:
        """
        自動感知檢測 project://.vscode 是否存在為目錄。
        若不存在則嚴格返回 False，不主動生成目錄，達成零目錄污染。
        """
        vscode_dir = os.path.join(proj_root, ".vscode")
        return os.path.isdir(vscode_dir)

    def sync_vscode_settings(
        self,
        proj_root: str,
        extra_paths: Optional[List[str]] = None,
        py_tag: Optional[str] = None,
    ) -> bool:
        """
        若 project://.vscode 存在，原子增量更新 settings.json：
        - 於 _yscb_managed 登記 YSCB 注入清單；
        - 更新 python.analysis.extraPaths（差集替換舊 YSCB 路徑，100% 保留使用者自訂路徑）；
        - 更新 python.defaultInterpreterPath 指向微環境 Python（若微環境已就緒）；
        - 若 project://.vscode 不存在則完全靜默略過，回傳 False。
        """
        if not self.is_vscode_configured(proj_root):
            return False

        vscode_dir = os.path.join(proj_root, ".vscode")
        settings_path = os.path.join(vscode_dir, "settings.json")

        settings: Dict[str, Any] = {}
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except Exception:
                # 若檔案存在但格式非標準 JSON，為防破壞原檔，暫不覆蓋或安全略過
                settings = {}

        # 1. 決定本次欲注入的 YSCB 管理路徑
        new_managed_paths: List[str] = []
        site_pkg = self.pip_mgr.get_site_packages_dir(py_tag)
        if os.path.isdir(site_pkg):
            try:
                rel_site = os.path.relpath(site_pkg, proj_root).replace("\\", "/")
                new_managed_paths.append(f"./{rel_site}")
            except Exception:
                new_managed_paths.append(site_pkg.replace("\\", "/"))

        # 補入額外指定之路徑 (如 source/*)
        if extra_paths:
            for ep in extra_paths:
                clean_ep = ep.replace("\\", "/")
                if clean_ep not in new_managed_paths:
                    new_managed_paths.append(clean_ep)

        # 2. 差集更新 python.analysis.extraPaths
        raw_extra = settings.get("python.analysis.extraPaths", [])
        if not isinstance(raw_extra, list):
            raw_extra = []

        # 取得舊版 _yscb_managed 記錄之路徑
        old_managed_record = settings.get(self.YSCB_MANAGED_KEY, {})
        old_managed_paths = set(old_managed_record.get("extraPaths", []))

        # 保留使用者自訂路徑 (不在 old_managed_paths 中的項目)
        retained_paths = [p for p in raw_extra if p not in old_managed_paths]

        # 將新的 managed paths 依序加入 (避免重複)
        final_extra_paths = list(retained_paths)
        for mp in new_managed_paths:
            if mp not in final_extra_paths:
                final_extra_paths.append(mp)

        settings["python.analysis.extraPaths"] = final_extra_paths

        # 3. 計算並更新 defaultInterpreterPath
        py_exec = self.pip_mgr.get_python_executable(py_tag)
        new_interpreter = ""
        if os.path.isfile(py_exec):
            try:
                rel_py = os.path.relpath(py_exec, proj_root).replace("\\", "/")
                new_interpreter = f"./{rel_py}"
            except Exception:
                new_interpreter = py_exec.replace("\\", "/")

        old_managed_interpreter = old_managed_record.get("defaultInterpreterPath")
        current_interpreter = settings.get("python.defaultInterpreterPath")

        # 若使用者未自訂（或當前值等於舊的 YSCB 注入值），則更新為新微環境直譯器
        if new_interpreter:
            if not current_interpreter or current_interpreter == old_managed_interpreter:
                settings["python.defaultInterpreterPath"] = new_interpreter

        # 4. 同步維護 VS Code 排除項 (避免檔案監視與搜尋開銷)
        exclude_keys = {
            "files.watcherExclude": "**/.venv/**",
            "search.exclude": "**/.venv/**",
            "files.exclude": "**/.venv",
        }
        managed_excludes = dict(old_managed_record.get("excludes", {}))
        for sec, pattern in exclude_keys.items():
            if sec not in settings or not isinstance(settings[sec], dict):
                settings[sec] = {}
            if pattern not in settings[sec]:
                settings[sec][pattern] = True
                managed_excludes[sec] = pattern

        # 5. 更新顯式標記區塊 _yscb_managed
        settings[self.YSCB_MANAGED_KEY] = {
            "description": "Auto-managed by YSCB host bootstrapper. Reversible via module uninstall or rollback.",
            "extraPaths": new_managed_paths,
            "defaultInterpreterPath": new_interpreter if (settings.get("python.defaultInterpreterPath") == new_interpreter) else current_interpreter,
            "excludes": managed_excludes,
        }

        # 5. 原子寫入
        tmp_settings = settings_path + ".tmp"
        try:
            with open(tmp_settings, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_settings, settings_path)
            return True
        except Exception:
            if os.path.exists(tmp_settings):
                try:
                    os.remove(tmp_settings)
                except Exception:
                    pass
            return False

    def revert_vscode_settings(self, proj_root: str) -> bool:
        """
        依據 _yscb_managed 標記清冊，100% 乾淨剔除 YSCB 注入之所有路徑與鍵值，復原使用者原設定。
        """
        if not self.is_vscode_configured(proj_root):
            return False

        settings_path = os.path.join(proj_root, ".vscode", "settings.json")
        if not os.path.isfile(settings_path):
            return False

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            return False

        if self.YSCB_MANAGED_KEY not in settings:
            return False

        managed_record = settings.pop(self.YSCB_MANAGED_KEY, {})
        managed_extra = set(managed_record.get("extraPaths", []))
        managed_interpreter = managed_record.get("defaultInterpreterPath")

        # 剔除 YSCB 注入之 extraPaths
        raw_extra = settings.get("python.analysis.extraPaths", [])
        if isinstance(raw_extra, list):
            clean_extra = [p for p in raw_extra if p not in managed_extra]
            if clean_extra:
                settings["python.analysis.extraPaths"] = clean_extra
            else:
                settings.pop("python.analysis.extraPaths", None)

        # 剔除 YSCB 注入之 defaultInterpreterPath
        if settings.get("python.defaultInterpreterPath") == managed_interpreter:
            settings.pop("python.defaultInterpreterPath", None)

        # 剔除 YSCB 注入之 excludes
        managed_excludes = managed_record.get("excludes", {})
        for sec, pattern in managed_excludes.items():
            if sec in settings and isinstance(settings[sec], dict):
                settings[sec].pop(pattern, None)

        # 寫回
        tmp_settings = settings_path + ".tmp"
        try:
            with open(tmp_settings, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_settings, settings_path)
            return True
        except Exception:
            return False
