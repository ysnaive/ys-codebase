"""
Unit tests for agents-workflow JIT Release Target Synchronization.
Covers FT-03, ET-05.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.publisher import ensure_jit_release, ReleasePublisher
from dev.testing.case import YSCBTestCase


class TestJITRelease(YSCBTestCase):
    def test_ft_03_ensure_jit_release_clean(self):
        """FT-03: 驗證當來源特徵未改變 (Clean) 時，ensure_jit_release 順暢返回且不報錯。"""
        with patch.object(ReleasePublisher, "release_all", return_value={"success": True, "short_circuited": True, "written_count": 0}):
            result = ensure_jit_release()
            # Clean 時未產生實質寫入
            self.assertFalse(result)
            self.mark_passed()

    def test_ft_03_ensure_jit_release_dirty_triggers_materialize(self):
        """FT-03: 驗證當指紋不一致時，ensure_jit_release 觸發 release 並返回 True。"""
        with patch.object(ReleasePublisher, "release_all", return_value={"success": True, "short_circuited": False, "written_count": 3}):
            result = ensure_jit_release()
            self.assertTrue(result)
            self.mark_passed()

    def test_et_05_ensure_jit_release_exception_safety(self):
        """ET-05: 驗證當 release 過程遭遇任何異常時，ensure_jit_release 安全捕獲返回 False，不中斷 CLI。"""
        with patch.object(ReleasePublisher, "release_all", side_effect=PermissionError("File locked")):
            result = ensure_jit_release()
            self.assertFalse(result)
            self.mark_passed()

    def test_agents_workflow_hook_jit_release(self):
        """FT-04: 驗證 hook.core.py 之 on_pre_cli_dispatch 呼叫 ensure_jit_release。"""
        import importlib.util
        hook_path = os.path.join(_pkg_root, "scripts", "hook.core.py")
        self.assertTrue(os.path.isfile(hook_path), "hook.core.py does not exist")
        spec = importlib.util.spec_from_file_location("aw_hook_core", hook_path)
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)
        self.assertTrue(hasattr(hook_mod, "on_pre_cli_dispatch"))

        with patch("agents_workflow.publisher.ensure_jit_release", return_value=True):
            res = hook_mod.on_pre_cli_dispatch()
            self.assertTrue(res)

        with patch("agents_workflow.publisher.ensure_jit_release", return_value=False):
            res = hook_mod.on_pre_cli_dispatch()
            self.assertFalse(res)
        self.mark_passed()

    def test_agents_workflow_cli_adhoc_removal(self):
        """FT-05: 驗證 agents-workflow/scripts/cli.py 已徹底移除 Ad-hoc ensure_jit_release 調用。"""
        cli_path = os.path.join(_pkg_root, "scripts", "cli.py")
        with open(cli_path, "r", encoding="utf-8") as f:
            cli_code = f.read()
        self.assertNotIn("ensure_jit_release()", cli_code, "cli.py still contains ad-hoc ensure_jit_release call")
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
