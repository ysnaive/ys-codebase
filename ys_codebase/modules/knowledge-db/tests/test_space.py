"""
Unit Tests for knowledge-db SpaceManager, Dual-Track Aggregation, and Priority Resolution.
"""

import json
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
from knowledge_db.exceptions import SpaceNotFoundError
from knowledge_db.space import SpaceManager


class TestSpaceManager(YSCBTestCase):
    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_04_dual_track_aggregation_and_priority(self):
        """FT-04: 驗證 SpaceManager 雙軌聚合與 Local > Project > Contributed 優先權覆蓋 (EC-07)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cfg_dir = temp_path / "config"
            cfg_dir.mkdir(parents=True)

            # 1. 模擬 Contributed 空間
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

            # 2. 模擬 Project Config
            proj_config = {
                "spaces": {
                    "proj_space": {
                        "description": "專案組態空間",
                        "include": [str(temp_path / "proj_src")],
                    },
                    "shared_space": {
                        "description": "Project 覆蓋版本",
                        "include": [str(temp_path / "proj_shared")],
                    },
                },
                "thesaurus": [["同義詞B", "syn_b"]],
            }
            with open(cfg_dir / "config.project.json", "w", encoding="utf-8") as f:
                json.dump(proj_config, f)

            # 3. 模擬 Local Config (覆蓋 shared_space)
            local_config = {
                "spaces": {
                    "shared_space": {
                        "description": "Local 最終覆蓋版本",
                        "include": [str(temp_path / "local_shared")],
                    }
                }
            }
            with open(cfg_dir / "config.local.json", "w", encoding="utf-8") as f:
                json.dump(local_config, f)

            sm = SpaceManager(config_dir=cfg_dir, contributes_data=mock_contributes)
            spaces = sm.load_spaces()

            # 驗證所有空間均存在
            self.assertIn("mod_space", spaces)
            self.assertIn("proj_space", spaces)
            self.assertIn("shared_space", spaces)

            # 驗證優先權: shared_space 應為 Local 覆蓋
            self.assertEqual(spaces["shared_space"].description, "Local 最終覆蓋版本")
            self.assertEqual(spaces["shared_space"].origin, "local")

            # 驗證 Thesaurus 聚合
            thesaurus = sm.load_thesaurus()
            self.assertEqual(len(thesaurus), 2)

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
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

            # 解算路徑
            paths = sm.resolve_space_include("space_a")
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0], src_dir1.resolve())

    @require(Requirement.LOGIC)
    def test_et_02_space_not_found_error(self):
        """ET-02: 驗證查詢未註冊空間拋出 SpaceNotFoundError (EC-08)"""
        sm = SpaceManager(contributes_data={"spaces": {}})
        with self.assertRaises(SpaceNotFoundError) as ctx:
            sm.get_space("non_existent_space")
        self.assertIn("non_existent_space", str(ctx.exception))

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
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

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_ft_11_cache_storage_root_resolution(self):
        """FT-11: 驗證 SpaceManager 預設儲存目錄指向 cache://knowledge-db/ (.cache/knowledge-db/)"""
        sm = SpaceManager(contributes_data={"spaces": {}})
        storage_root = sm.storage_dir
        self.assertTrue(
            ".cache" in str(storage_root) or "cache" in str(storage_root),
            f"Storage root '{storage_root}' should point to cache directory."
        )
