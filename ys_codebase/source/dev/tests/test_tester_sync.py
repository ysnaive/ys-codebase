"""
Unit tests for dev.tester --sync and post-test direct install guidance.
Covers FT-05.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO
from dev.testing import YSCBTestCase
from dev.tester import Tester


class TestTesterSync(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.tester = Tester()

    def test_ft_05_handle_post_test_sync_with_sync_flag(self):
        """FT-05: 驗證當 sync_requested=True 時，自動呼叫 subprocess.run 執行 install <mod>@build。"""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data='{"installed_modules": {"dev": {"version": "1.0.0.0"}}}')), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_sub:
            
            output_io = StringIO()
            with patch("sys.stdout", output_io):
                self.tester._handle_post_test_sync(["dev"], sync_requested=True)

            # 驗證有呼叫 subprocess 執行 install dev@build
            mock_sub.assert_called_once()
            args = mock_sub.call_args[0][0]
            self.assertIn("install", args)
            self.assertIn("dev@build", args)
            self.assertIn("--force", args)
            self.mark_passed()

    def test_ft_05_handle_post_test_sync_prompt_only(self):
        """FT-05: 驗證當 sync_requested=False 時，不呼叫 install，而是輸出友善提示。"""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data='{"installed_modules": {"dev": {"version": "1.0.0.0"}}}')), \
             patch("subprocess.run") as mock_sub:
            
            output_io = StringIO()
            with patch("sys.stdout", output_io):
                self.tester._handle_post_test_sync(["dev"], sync_requested=False)

            mock_sub.assert_not_called()
            output = output_io.getvalue()
            self.assertIn("install dev@build", output)
            self.mark_passed()


if __name__ == "__main__":
    unittest.main()
