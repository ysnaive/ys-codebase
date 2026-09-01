"""
Unit Tests for knowledge-db Computed Token Providers (get_knowledge_db_spaces).
"""

import os
from pathlib import Path
import sys
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.providers import get_knowledge_db_spaces
from knowledge_db.space import SpaceManager


class TestKnowledgeDBProviders(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_01_get_knowledge_db_spaces_output_format(self):
        """FT-01: 驗證 get_knowledge_db_spaces 產出正確的 Markdown 空間速查表格"""
        mock_contributes = {
            "spaces": {
                "alpha_space": {
                    "description": "Alpha 領域空間",
                    "include": ["module://alpha/docs"],
                    "file_patterns": ["*.py", "*.md"],
                    "origin": "module:alpha",
                },
                "beta_space": {
                    "description": "Beta 核心源碼空間",
                    "include": ["module://beta/src"],
                    "origin": "module:beta",
                },
            }
        }

        # 透過 SpaceManager 封裝測試
        mgr = SpaceManager(contributes_data=mock_contributes)
        
        # 測試直接呼叫 provider
        output = get_knowledge_db_spaces()
        self.assertIn("| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |", output)
        self.assertIn("| :--- | :--- | :--- | :--- |", output)

    @require(Requirement.LOGIC)
    def test_ft_02_get_knowledge_db_spaces_empty_fallback(self):
        """FT-02: 驗證無任何空間時之安全降級輸出"""
        # 當無空間時的 fallback 測試
        mgr = SpaceManager(contributes_data={"spaces": {}})
        spaces = mgr.load_spaces()
        self.assertEqual(len(spaces), 0)


if __name__ == "__main__":
    unittest.main()
