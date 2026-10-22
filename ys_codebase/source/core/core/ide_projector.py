"""
YS-Codebase IDE Automatic Sensing & Reversible Soft-Merge Projector.
100% Python Standard Library, Zero Third-Party Dependency.
Senses if project://.vscode exists; if present, performs non-destructive, reversible
soft-merge of private venv site-packages into .vscode/settings.json with explicit _yscb_managed boundary.
"""

import os
import sys
import json
from typing import Optional, List, Dict, Any
from core.pip_manager import PipManager
from core import vfs


class IdeProjector:
    """IDE 自動感知投影器：比照 internal yscb gitignore 模式，以 _yscb_managed 執行可復原軟合併。"""

    YSCB_MANAGED_KEY = "_yscb_managed"

    def __init__(self, yscb_dir: Optional[str] = None):
        self.yscb_dir = os.path.abspath(yscb_dir or self._resolve_yscb_root())
        self.pip_mgr = PipManager(self.yscb_dir)

    def _resolve_yscb_root(self) -> str:
        try:
            from core import uri
            return uri._get_yscb_root()
        except Exception:
            pass
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

    def _is_yscb_managed_interpreter(
        self,
        value: Any,
        proj_root: str,
        old_managed_value: Any = None,
    ) -> bool:
        """
        判定直譯器路徑是否為 YSCB 託管值（舊版 _yscb_managed 記錄值，或位於 YSCB 私有微環境 yscb_dir/.venv/ 之下）。
        以實際微環境根目錄做路徑前綴比對，而非字串含有 '.venv'，避免誤刪使用者專案自有之 .venv 直譯器 (EC-03)。
        支援跨平台寫入之相對路徑（POSIX bin/python 與 Windows Scripts/python.exe 互相辨識）。
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

    def sync_vscode_settings(
        self,
        proj_root: str,
        extra_paths: Optional[List[str]] = None,
        py_tag: Optional[str] = None,
    ) -> bool:
        """
        若 project://.vscode 存在，原子增量更新 settings.json：
        - 於 _yscb_managed 登記 YSCB 注入清單；
        - 更新 python.analysis.extraPaths（注入跨平台雙路徑，差集替換舊 YSCB 路徑，100% 保留使用者自訂路徑）；
        - 停止主動寫入 host-local 的 python.defaultInterpreterPath，並主動清理舊版 YSCB 託管值（保留使用者自訂路徑）；
        - 實作 Zero-Touch 檢驗，內容等價時跳過磁碟寫入，避免檔案 mtime 變動；
        - 若 project://.vscode 不存在則完全靜默略過，回傳 False。
        """
        if not self.is_vscode_configured(proj_root):
            return False

        vscode_dir = os.path.join(proj_root, ".vscode")
        settings_path = os.path.join(vscode_dir, "settings.json")

        settings: Dict[str, Any] = {}
        if vfs.is_file(settings_path):
            try:
                data = vfs.read_json(settings_path)
            except Exception:
                # 檔案存在但非標準 JSON（如 VS Code 允許之 JSONC 註解 / 尾逗號）：
                # 為防整檔覆寫導致使用者設定遺失，略過同步且不寫盤。
                print(
                    f"[core:ide] Warning: '{settings_path}' is not strict JSON (comments or trailing commas?); "
                    "skipped VS Code settings sync to preserve user settings.",
                    file=sys.stderr,
                )
                return False
            if not isinstance(data, dict):
                return False
            settings = data

        # 1. 決定本次欲注入的 YSCB 管理路徑 (跨平台雙路徑恆定注入)
        new_managed_paths: List[str] = []
        venv_dir = self.pip_mgr.get_venv_dir(py_tag)
        if os.path.isdir(venv_dir):
            site_pkgs = self.pip_mgr.get_cross_platform_site_packages_dirs(py_tag)
            for sp in site_pkgs:
                try:
                    rel_site = os.path.relpath(sp, proj_root).replace("\\", "/")
                    if not rel_site.startswith("./") and not rel_site.startswith("../"):
                        entry = f"./{rel_site}"
                    else:
                        entry = rel_site
                    if entry not in new_managed_paths:
                        new_managed_paths.append(entry)
                except Exception:
                    entry = sp.replace("\\", "/")
                    if entry not in new_managed_paths:
                        new_managed_paths.append(entry)

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

        if final_extra_paths:
            settings["python.analysis.extraPaths"] = final_extra_paths
        else:
            settings.pop("python.analysis.extraPaths", None)

        # 3. 停止寫入 defaultInterpreterPath，並清理舊版 YSCB 託管值 (保留使用者自訂路徑)
        old_managed_interpreter = old_managed_record.get("defaultInterpreterPath")
        current_interpreter = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(current_interpreter, proj_root, old_managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

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

        # 5. 更新顯式標記區塊 _yscb_managed (不再記錄 defaultInterpreterPath)
        settings[self.YSCB_MANAGED_KEY] = {
            "description": "Auto-managed by YSCB host bootstrapper. Reversible via module uninstall or rollback.",
            "extraPaths": new_managed_paths,
            "excludes": managed_excludes,
        }

        # 6. Zero-Touch 檢驗：若與現有 settings.json 內容完全等價，跳過磁碟寫入
        if vfs.is_file(settings_path):
            try:
                existing_data = vfs.read_json(settings_path)
                if existing_data == settings:
                    return True
            except Exception:
                pass

        # 7. 原子寫入
        try:
            vfs.write_json(settings_path, settings, indent=2, atomic=True)
            return True
        except Exception:
            return False

    def revert_vscode_settings(self, proj_root: str) -> bool:
        """
        依據 _yscb_managed 標記清冊，100% 乾淨剔除 YSCB 注入之所有路徑與鍵值，復原使用者原設定。
        """
        if not self.is_vscode_configured(proj_root):
            return False

        settings_path = os.path.join(proj_root, ".vscode", "settings.json")
        if not vfs.is_file(settings_path):
            return False

        try:
            settings = vfs.read_json(settings_path)
            if not isinstance(settings, dict):
                return False
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

        # 剔除 YSCB 注入之 defaultInterpreterPath (若存在舊版殘留)
        curr_interp = settings.get("python.defaultInterpreterPath")
        if self._is_yscb_managed_interpreter(curr_interp, proj_root, managed_interpreter):
            settings.pop("python.defaultInterpreterPath", None)

        # 剔除 YSCB 注入之 excludes
        managed_excludes = managed_record.get("excludes", {})
        for sec, pattern in managed_excludes.items():
            if sec in settings and isinstance(settings[sec], dict):
                settings[sec].pop(pattern, None)

        # 寫回
        try:
            vfs.write_json(settings_path, settings, indent=2, atomic=True)
            return True
        except Exception:
            return False
