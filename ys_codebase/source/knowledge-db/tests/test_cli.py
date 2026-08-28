"""
Unit Tests for knowledge-db CLI Router and Development Hooks.
"""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from scripts.cli import main

# 動態加載 hook.dev.py
_hook_path = os.path.join(_pkg_root, "scripts", "hook.dev.py")
_spec = importlib.util.spec_from_file_location("hook_dev", _hook_path)
_hook_dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook_dev)


class TestCLI(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_cli_all_commands(self):
        """FT-07: 驗證 CLI 6 大子指令路由與執行 (status, scan, bundle, index, search, clean)"""
        # 1. 說明指令
        self.assertEqual(main([]), 0)
        self.assertEqual(main(["--help"]), 0)

        # 2. status 指令
        self.assertEqual(main(["status"]), 0)

        # 3. scan 指令
        self.assertEqual(main(["scan", "--all"]), 0)

        # 4. bundle 指令
        self.assertEqual(main(["bundle", "--all"]), 0)

        # 5. index 指令
        self.assertEqual(main(["index", "--all"]), 0)

        # 6. search 指令
        self.assertEqual(main(["search", "PIDController"]), 0)
        # 空檢索參數防禦
        self.assertEqual(main(["search"]), 1)

        # 7. clean 指令
        self.assertEqual(main(["clean", "--all"]), 0)

        # 8. 未知指令 (EC-06)
        self.assertEqual(main(["unknown_cmd_xyz"]), 1)

    @require(Requirement.LOGIC)
    def test_hook_lifecycle(self):
        """FT-08: 驗證 hook.dev.py 測試前置與後置鉤子正常執行"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _hook_dev.on_test_setup(temp_dir)
            indices_dir = Path(temp_dir) / ".cache" / "knowledge-db" / "indices"
            self.assertTrue(indices_dir.exists())

            _hook_dev.on_test_teardown(temp_dir)
