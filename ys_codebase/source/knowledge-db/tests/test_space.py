"""
Unit Tests for knowledge-db SpaceManager, Dual-Track Aggregation, Priority Resolution, and Computed Token Providers.
Unified Suite consolidating test_space.py and test_providers.py.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.exceptions import InvalidSpaceConfigError, SpaceNotFoundError
from knowledge_db.providers import get_knowledge_db_spaces
from knowledge_db.space import SpaceManager


class TestSpaceManager(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_04_dual_track_aggregation_and_priority(self):
        """FT-04: 驗證 SpaceManager Contributes 體系與 Project contribute.json 優先權覆蓋"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cfg_dir = temp_path / "config"
            cfg_dir.mkdir(parents=True)

            mock_contributes = {
                "spaces": {
                    "mod_space": {
                        "description": "模組注入空間",
                        "include": [str(temp_path / "mod_src")],
                        "file_patterns": ["*.py"],
                        "origin": "module:donor_mod",
                    },
                    "shared_space": {
                        "description": "Contributed 版本",
                        "include": [str(temp_path / "contrib_shared")],
                        "origin": "module:donor_mod",
                    },
                },
                "thesaurus": [["同義詞A", "syn_a"]],
            }

            proj_contribute = {
                "spaces": {
                    "proj_space": {
                        "description": "專案注入空間",
                        "include": [str(temp_path / "proj_src")],
                    },
                    "shared_space": {
                        "description": "Project contribute.json 覆蓋版本",
                        "include": [str(temp_path / "proj_shared")],
                    },
                },
                "thesaurus": [["同義詞B", "syn_b"]],
            }
            with open(cfg_dir / "contribute.json", "w", encoding="utf-8") as f:
                json.dump(proj_contribute, f)

            sm = SpaceManager(config_dir=cfg_dir, contributes_data=mock_contributes)
            spaces = sm.load_spaces()

            self.assertIn("mod_space", spaces)
            self.assertIn("proj_space", spaces)
            self.assertIn("shared_space", spaces)
            self.assertEqual(spaces["shared_space"].description, "Project contribute.json 覆蓋版本")

            thesaurus = sm.load_thesaurus()
            self.assertEqual(len(thesaurus), 2)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_union_spaces_and_uri_resolution(self):
        """FT-05: 驗證全空間聯集 (Union Scope) 與 resolve_space_include 路徑解算"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir1 = temp_path / "src1"
            src_dir1.mkdir(parents=True)
            src_dir2 = temp_path / "src2"
            src_dir2.mkdir(parents=True)

            mock_contributes = {
                "spaces": {
                    "space_a": {
                        "include": [str(src_dir1)],
                    },
                    "space_b": {
                        "include": [str(src_dir2)],
                    },
                }
            }

            sm = SpaceManager(contributes_data=mock_contributes)
            union_spaces = sm.get_union_spaces()
            self.assertEqual(len(union_spaces), 2)
            space_names = [s.name for s in union_spaces]
            self.assertIn("space_a", space_names)
            self.assertIn("space_b", space_names)

            paths = sm.resolve_space_include("space_a")
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0], src_dir1.resolve())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_space_not_found_error(self):
        """ET-02: 驗證查詢未註冊空間拋出 SpaceNotFoundError (EC-08)"""
        sm = SpaceManager(contributes_data={"spaces": {}})
        with self.assertRaises(SpaceNotFoundError) as ctx:
            sm.get_space("non_existent_space")
        self.assertIn("non_existent_space", str(ctx.exception))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_invalid_source_path_warning_and_skip(self):
        """ET-03: 驗證包含不存在之來源路徑時安全略過且不中斷 (EC-02)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            valid_dir = temp_path / "valid_src"
            valid_dir.mkdir(parents=True)
            invalid_dir = temp_path / "missing_dir_12345"

            mock_contributes = {
                "spaces": {
                    "mixed_space": {
                        "include": [str(valid_dir), str(invalid_dir)],
                    }
                }
            }

            sm = SpaceManager(contributes_data=mock_contributes)
            resolved = sm.resolve_space_include("mixed_space")
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0], valid_dir.resolve())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_11_cache_storage_root_resolution(self):
        """FT-11: 驗證 SpaceManager 顯式指定 storage_dir 或有效 URI 正確解算"""
        with tempfile.TemporaryDirectory() as temp_dir:
            sm = SpaceManager(storage_dir=temp_dir, contributes_data={"spaces": {}})
            self.assertEqual(sm.storage_dir, Path(temp_dir).resolve())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_04_zero_fallback_cache_root_guardrail(self):
        """ET-04: 驗證無 core 且未指定 storage_dir 時拋出 InvalidSpaceConfigError (零 Fallback 鐵律)"""
        import knowledge_db.space as space_mod
        orig_resolver = space_mod._safe_resolve_uri
        try:
            space_mod._safe_resolve_uri = lambda uri_str: None
            sm = SpaceManager(contributes_data={"spaces": {}})
            with self.assertRaises(InvalidSpaceConfigError):
                _ = sm.storage_dir
        finally:
            space_mod._safe_resolve_uri = orig_resolver

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sub_06_empty_configurable_contribute_defaults(self):
        """SUB-06: 驗證 knowledge-db 模組內建 configurable/contribute.json 預設為空 spaces"""
        cfg_template = Path(_pkg_root) / "configurable" / "contribute.json"
        self.assertTrue(cfg_template.exists(), f"Configurable template {cfg_template} must exist")
        with open(cfg_template, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("spaces"), {}, "Configurable template must have empty spaces dict by default")

        self.mark_passed()


class TestKnowledgeDBProviders(YSCBTestCase):
    """驗證 Token Providers 與空間速查表輸出"""

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

        mgr = SpaceManager(contributes_data=mock_contributes)
        output = get_knowledge_db_spaces()
        self.assertIn("| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |", output)
        self.assertIn("| :--- | :--- | :--- | :--- |", output)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_get_knowledge_db_spaces_empty_fallback(self):
        """FT-02: 驗證無任何空間時之安全降級輸出"""
        mgr = SpaceManager(contributes_data={"spaces": {}})
        spaces = mgr.load_spaces()
        self.assertEqual(len(spaces), 0)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
