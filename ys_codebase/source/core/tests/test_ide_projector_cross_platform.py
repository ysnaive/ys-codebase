"""
Unit tests for IdeProjector & PipManager cross-platform stability and zero git dirty remediation.
Validates:
- PipManager.get_cross_platform_site_packages_dirs returns both POSIX and Windows candidates
- IdeProjector.sync_vscode_settings injects dual extraPaths deterministically
- IdeProjector.sync_vscode_settings stops writing defaultInterpreterPath and clears old managed value
- User custom defaultInterpreterPath is 100% preserved
- Zero-Touch check skips disk write when content is unchanged
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from core.pip_manager import PipManager
from core.ide_projector import IdeProjector
from core import vfs
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


@require(Requirement.ENV)
class TestIdeProjectorCrossPlatform(YSCBTestCase):
    """測試 IDE 投影器與 Pip 管理器跨平台穩定性。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_ide_cross_")
        self.project_root = os.path.join(self.temp_dir, "project")
        self.yscb_dir = os.path.join(self.project_root, ".yscb")
        os.makedirs(self.project_root, exist_ok=True)
        os.makedirs(self.yscb_dir, exist_ok=True)
        self.projector = IdeProjector(yscb_dir=self.yscb_dir)
        self.pip_mgr = self.projector.pip_mgr

    def test_get_cross_platform_site_packages_dirs(self):
        """FT-03: 驗證 get_cross_platform_site_packages_dirs 回傳 POSIX 與 Windows 雙路徑。"""
        paths = self.pip_mgr.get_cross_platform_site_packages_dirs(py_tag="py312")
        self.assertEqual(len(paths), 2)
        posix_p, win_p = paths[0].replace("\\", "/"), paths[1].replace("\\", "/")
        self.assertTrue(posix_p.endswith(".venv/py312/lib/python3.12/site-packages"))
        self.assertTrue(win_p.endswith(".venv/py312/Lib/site-packages"))
        self.mark_passed()

    def test_sync_vscode_settings_dual_extra_paths(self):
        """FT-04: 驗證 sync_vscode_settings 恆定注入雙平台 extraPaths。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        # 模擬 venv 目錄存在
        venv_dir = self.pip_mgr.get_venv_dir("py312")
        os.makedirs(venv_dir, exist_ok=True)

        res = self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        self.assertTrue(res)

        settings_path = os.path.join(vscode_dir, "settings.json")
        data = vfs.read_json(settings_path)

        extra = data.get("python.analysis.extraPaths", [])
        self.assertIn("./.yscb/.venv/py312/lib/python3.12/site-packages", extra)
        self.assertIn("./.yscb/.venv/py312/Lib/site-packages", extra)
        self.assertNotIn("python.defaultInterpreterPath", data)
        self.mark_passed()

    def test_sync_vscode_settings_removes_managed_interpreter(self):
        """FT-05: 驗證清理既有 YSCB 託管之 defaultInterpreterPath。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        venv_dir = self.pip_mgr.get_venv_dir("py312")
        os.makedirs(venv_dir, exist_ok=True)

        settings_path = os.path.join(vscode_dir, "settings.json")
        initial_data = {
            "python.defaultInterpreterPath": "./.yscb/.venv/py312/bin/python",
            "_yscb_managed": {
                "defaultInterpreterPath": "./.yscb/.venv/py312/bin/python",
                "extraPaths": ["./.yscb/.venv/py312/lib/python3.12/site-packages"],
            },
        }
        vfs.write_json(settings_path, initial_data)

        self.projector.sync_vscode_settings(self.project_root, py_tag="py312")

        data = vfs.read_json(settings_path)
        self.assertNotIn("python.defaultInterpreterPath", data)
        managed = data.get("_yscb_managed", {})
        self.assertNotIn("defaultInterpreterPath", managed)
        self.mark_passed()

    def test_sync_vscode_settings_preserves_user_custom_interpreter(self):
        """FT-06 (EC-03): 驗證保留使用者自訂直譯器路徑。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        venv_dir = self.pip_mgr.get_venv_dir("py312")
        os.makedirs(venv_dir, exist_ok=True)

        settings_path = os.path.join(vscode_dir, "settings.json")
        custom_interp = "/usr/local/bin/my_custom_python"
        initial_data = {
            "python.defaultInterpreterPath": custom_interp,
            "_yscb_managed": {
                "extraPaths": [],
            },
        }
        vfs.write_json(settings_path, initial_data)

        self.projector.sync_vscode_settings(self.project_root, py_tag="py312")

        data = vfs.read_json(settings_path)
        self.assertEqual(data.get("python.defaultInterpreterPath"), custom_interp)
        self.mark_passed()

    def test_sync_vscode_settings_preserves_user_project_venv_interpreter(self):
        """FT-06b (EC-03): 使用者專案自有 .venv（非 YSCB 私有微環境）之直譯器不得被誤判為託管值刪除。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        os.makedirs(self.pip_mgr.get_venv_dir("py312"), exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        user_interp = "./.venv/bin/python"
        vfs.write_json(settings_path, {"python.defaultInterpreterPath": user_interp})

        self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        self.assertEqual(vfs.read_json(settings_path).get("python.defaultInterpreterPath"), user_interp)

        self.projector.revert_vscode_settings(self.project_root)
        self.assertEqual(vfs.read_json(settings_path).get("python.defaultInterpreterPath"), user_interp)
        self.mark_passed()

    def test_sync_vscode_settings_removes_foreign_platform_managed_interpreter(self):
        """FT-05b: 他平台寫入且無 _yscb_managed 記錄之 YSCB 微環境直譯器路徑 (Scripts/python.exe 或 bin/python) 亦被清理。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        os.makedirs(self.pip_mgr.get_venv_dir("py312"), exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        for foreign in ("./.yscb/.venv/py312/Scripts/python.exe", ".\\.yscb\\.venv\\py312\\Scripts\\python.exe", "./.yscb/.venv/py312/bin/python"):
            vfs.write_json(settings_path, {"python.defaultInterpreterPath": foreign})
            self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
            self.assertNotIn("python.defaultInterpreterPath", vfs.read_json(settings_path), foreign)
        self.mark_passed()

    def test_sync_vscode_settings_zero_touch(self):
        """FT-07 (EC-04): 驗證內容相同時略過寫盤 (Zero-Touch)。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        venv_dir = self.pip_mgr.get_venv_dir("py312")
        os.makedirs(venv_dir, exist_ok=True)

        # 首次同步
        self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        settings_path = os.path.join(vscode_dir, "settings.json")
        first_mtime = os.stat(settings_path).st_mtime_ns

        # 再次同步，應被 Zero-Touch 攔截跳過寫入
        self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        second_mtime = os.stat(settings_path).st_mtime_ns
        self.assertEqual(first_mtime, second_mtime)
        self.mark_passed()

    def test_rev01_vfs_write_text_keeps_lf(self):
        """REV-01: vfs.write_text / write_json 以 LF 原樣寫出，不轉譯為 CRLF；顯式 \\r\\n 原樣保留。"""
        target = os.path.join(self.temp_dir, "lf_check.txt")
        vfs.write_text(target, "a\nb\n")
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"a\nb\n")
        vfs.write_text(target, "x\r\ny\n")
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"x\r\ny\n")
        json_target = os.path.join(self.temp_dir, "lf_check.json")
        vfs.write_json(json_target, {"k": [1, 2]})
        with open(json_target, "rb") as f:
            self.assertNotIn(b"\r\n", f.read())
        self.mark_passed()

    def test_rev02_jsonc_settings_not_overwritten(self):
        """REV-02: settings.json 含註解 (JSONC) 而解析失敗時，略過同步且檔案位元組完全不變。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        os.makedirs(self.pip_mgr.get_venv_dir("py312"), exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        original = b'{\n  // user comment\n  "editor.tabSize": 4,\n}\n'
        with open(settings_path, "wb") as f:
            f.write(original)

        self.assertFalse(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        with open(settings_path, "rb") as f:
            self.assertEqual(f.read(), original)
        self.mark_passed()

    def test_ide_projector_skip_when_no_vscode(self):
        """FT-06: Verify IdeProjector silently skips when project://.vscode does not exist."""
        proj_root = os.path.join(self.temp_dir, "no_vscode_project")
        os.makedirs(proj_root, exist_ok=True)

        self.assertFalse(self.projector.is_vscode_configured(proj_root))
        result = self.projector.sync_vscode_settings(proj_root)
        self.assertFalse(result)
        self.assertFalse(os.path.exists(os.path.join(proj_root, ".vscode")))
        self.mark_passed()

    def test_ide_projector_soft_merge_and_revert(self):
        """FT-07: Verify explicit _yscb_managed marking and reversible soft-merge."""
        proj_root = os.path.join(self.temp_dir, "vscode_soft_merge_project")
        vscode_dir = os.path.join(proj_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)

        settings_path = os.path.join(vscode_dir, "settings.json")
        initial_settings = {
            "custom.user.setting": True,
            "python.analysis.extraPaths": ["/opt/custom/lib"],
        }
        vfs.write_json(settings_path, initial_settings)

        self.assertTrue(self.projector.is_vscode_configured(proj_root))
        site_pkg = self.pip_mgr.get_site_packages_dir()
        os.makedirs(site_pkg, exist_ok=True)

        ok = self.projector.sync_vscode_settings(proj_root, extra_paths=["./source/core"])
        self.assertTrue(ok)

        updated = vfs.read_json(settings_path)
        self.assertIn("_yscb_managed", updated)
        self.assertTrue(updated["custom.user.setting"])
        self.assertIn("/opt/custom/lib", updated["python.analysis.extraPaths"])
        self.assertIn("./source/core", updated["python.analysis.extraPaths"])

        rev_ok = self.projector.revert_vscode_settings(proj_root)
        self.assertTrue(rev_ok)

        reverted = vfs.read_json(settings_path)
        self.assertNotIn("_yscb_managed", reverted)
        self.assertTrue(reverted["custom.user.setting"])
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["/opt/custom/lib"])
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

