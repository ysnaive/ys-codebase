"""
Unit Tests for knowledge-db Space Integration, Space Weights, and Computed Token Providers.
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
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.exceptions import InvalidConfigError
from knowledge_db.providers import get_knowledge_db_spaces
from knowledge_db.schema import KnowledgeDBContributes, validate_space_weights
from file_space import InvalidFileSpaceConfigError, FileSpaceConfig, FileSpaceDef, FileSpaceManager, FileSpaceNotFoundError


class TestSpaceIntegrationAndWeights(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_04_dual_track_aggregation_and_priority(self):
        """驗證 FileSpaceManager Contributes 體系與 Project contribute.json 優先權覆蓋"""
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
            }
            with open(cfg_dir / "contribute.json", "w", encoding="utf-8") as f:
                json.dump(proj_contribute, f)

            sm = FileSpaceManager(config_dir=cfg_dir, contributes_data=mock_contributes)
            spaces = sm.load_spaces()

            self.assertIn("mod_space", spaces)
            self.assertIn("proj_space", spaces)
            self.assertIn("shared_space", spaces)
            self.assertEqual(spaces["shared_space"].description, "Project contribute.json 覆蓋版本")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_union_spaces_and_uri_resolution(self):
        """驗證全空間聯集 (Union Scope) 與 resolve_space_include 路徑解算"""
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

            sm = FileSpaceManager(contributes_data=mock_contributes)
            space_names = sm.list_spaces()
            self.assertEqual(len(space_names), 2)
            self.assertIn("space_a", space_names)
            self.assertIn("space_b", space_names)

            paths = sm.resolve_space_include("space_a")
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0], src_dir1.resolve())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_space_not_found_error(self):
        """驗證查詢未註冊空間拋出 FileSpaceNotFoundError"""
        sm = FileSpaceManager(contributes_data={"spaces": {}})
        with self.assertRaises(FileSpaceNotFoundError) as ctx:
            sm.get_space("non_existent_space")
        self.assertIn("non_existent_space", str(ctx.exception))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_invalid_source_path_warning_and_skip(self):
        """驗證包含不存在之來源路徑時安全略過且不中斷"""
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

            sm = FileSpaceManager(contributes_data=mock_contributes)
            resolved = sm.resolve_space_include("mixed_space")
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0], valid_dir.resolve())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_11_storage_dir_decoupling(self):
        """驗證 KnowledgeEngine.storage_dir 與 FileSpaceManager.storage_dir 物理隔離解耦"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            kdb_storage = temp_path / "knowledge_cache"
            engine = KnowledgeEngine(storage_dir=kdb_storage, contributes_data={"spaces": {}})
            self.assertEqual(engine.storage_dir, kdb_storage.resolve())
            self.assertNotEqual(engine.storage_dir, engine.space_manager.storage_dir)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_sub_06_empty_configurable_contribute_defaults(self):
        """驗證 knowledge-db 模組內建 contributes/knowledge-db.json 與 _format.json 契約"""
        mod_contrib = Path(_pkg_root) / "contributes" / "knowledge-db.json"
        self.assertTrue(mod_contrib.exists(), f"Module contributes {mod_contrib} must exist")
        with open(mod_contrib, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("languages", data)

        fmt_path = Path(_pkg_root) / "contributes" / "_format.json"
        with open(fmt_path, "r", encoding="utf-8") as f:
            fmt_data = json.load(f)
        self.assertIn("space_weights", fmt_data)
        self.assertNotIn("spaces", fmt_data)
        self.assertNotIn("FileSpaceDef", fmt_data.get("_types", {}))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_configurable_config_templates_exist(self):
        """驗證 knowledge-db 模組預設組態整合至 configurable/config.project.json"""
        proj_tpl = Path(_pkg_root) / "configurable" / "config.project.json"
        local_tpl = Path(_pkg_root) / "configurable" / "config.local.json"

        self.assertTrue(proj_tpl.exists(), f"Configurable template {proj_tpl} must exist")
        self.assertFalse(local_tpl.exists(), f"Configurable template {local_tpl} must NOT exist (shadowing prevention)")

        with open(proj_tpl, "r", encoding="utf-8") as f:
            proj_data = json.load(f)
        self.assertIn("enable_vector_search", proj_data)
        self.assertIn("embedding_model", proj_data)
        self.assertIn("jit_vector_timeout_ms", proj_data)
        self.assertEqual(proj_data["jit_vector_timeout_ms"], 3000)
        self.assertIn("max_threads", proj_data)
        self.assertNotIn("enable_hot_reload_server", proj_data)
        self.assertNotIn("hot_reload_server_inactivity_timer_sec", proj_data)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_knowledgedb_config_purity(self):
        """驗證 KnowledgeDBConfig 維持純粹性與 resolve_threads 唯一真理"""
        from knowledge_db.config import KnowledgeDBConfig, resolve_threads
        cfg = KnowledgeDBConfig()
        self.assertFalse(hasattr(cfg, "enable_hot_reload_server"))
        self.assertFalse(hasattr(cfg, "hot_reload_server_inactivity_timer_sec"))
        self.assertFalse(hasattr(cfg, "enable_server_console"))
        self.assertFalse(hasattr(cfg, "is_jit_effective"))
        self.assertFalse(hasattr(cfg, "resolve_max_threads"))
        self.assertEqual(cfg.jit_vector_timeout_ms, 3000)
        self.assertEqual(cfg.jit_vector_timeout_seconds, 3.0)

        t_none = resolve_threads(None)
        t_auto = resolve_threads("auto")
        self.assertIsInstance(t_none, int)
        self.assertGreaterEqual(t_none, 1)
        self.assertEqual(t_none, t_auto)
        self.assertEqual(cfg.resolve_threads(None), t_none)
        self.assertEqual(cfg.resolve_threads("auto"), t_auto)
        self.assertEqual(resolve_threads(1), 1)

        loaded = KnowledgeDBConfig.load(
            project_config={"knowledge-db": {"enable_hot_reload_server": True, "jit_vector_timeout_ms": 8000}}
        )
        self.assertFalse(hasattr(loaded, "enable_hot_reload_server"))
        self.assertEqual(loaded.jit_vector_timeout_ms, 8000)
        self.assertEqual(loaded.jit_vector_timeout_seconds, 8.0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_12_space_weight_schema_and_validation(self):
        """驗證 FileSpaceConfig 與 KnowledgeDBContributes.space_weights 預設值、覆寫與 <= 0 阻斷"""
        self.assertIs(FileSpaceDef, FileSpaceConfig)

        sp_default = FileSpaceConfig.from_dict("source", {"include": ["src/"]})
        self.assertEqual(sp_default.weight, 1.0)
        self.assertEqual(sp_default.to_dict()["weight"], 1.0)

        sp_docs = FileSpaceConfig.from_dict("docs", {"include": ["docs/"], "weight": 1.2})
        sp_plans = FileSpaceConfig.from_dict("plans", {"include": ["plans/"], "weight": 0.85})
        self.assertAlmostEqual(sp_docs.weight, 1.2)
        self.assertAlmostEqual(sp_plans.weight, 0.85)

        for invalid_w in (0, 0.0, -0.5, -1, "invalid_float"):
            with self.assertRaises(InvalidConfigError):
                validate_space_weights({"bad_space": invalid_w})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={
                    "spaces": {"docs": {"include": [str(src_dir)], "weight": 1.0}},
                    "space_weights": {"docs": 1.35},
                },
            )
            self.assertAlmostEqual(engine.get_space_weight("docs"), 1.35)
            self.assertAlmostEqual(engine.get_space_weight("unregistered"), 1.0)

        self.mark_passed()


class TestKnowledgeDBProviders(YSCBTestCase):
    """驗證 Token Providers 與空間速查表輸出"""

    @require(Requirement.LOGIC)
    def test_ft_01_get_knowledge_db_spaces_output_format(self):
        """驗證 get_knowledge_db_spaces 產出正確的 Markdown 空間速查表格"""
        from unittest.mock import patch
        mock_spaces = {
            "alpha_space": FileSpaceConfig(
                name="alpha_space",
                description="Alpha 領域空間",
                include=["module://alpha/docs"],
                file_patterns=["*.py", "*.md"],
                origin="module:alpha",
            ),
            "beta_space": FileSpaceConfig(
                name="beta_space",
                description="Beta 核心源碼空間",
                include=["module://beta/src"],
                origin="module:beta",
            ),
        }

        with patch("knowledge_db.providers.FileSpaceManager") as mock_sm_cls:
            mock_sm_inst = mock_sm_cls.return_value
            mock_sm_inst.load_spaces.return_value = mock_spaces

            output = get_knowledge_db_spaces()
            self.assertIn("| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |", output)
            self.assertIn("**`alpha_space`**", output)
            self.assertIn("**`beta_space`**", output)
            self.assertIn("Alpha 領域空間", output)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_get_knowledge_db_spaces_empty_fallback(self):
        """驗證無任何空間時之安全降級輸出"""
        from unittest.mock import patch
        with patch("knowledge_db.providers.FileSpaceManager") as mock_sm_cls:
            mock_sm_inst = mock_sm_cls.return_value
            mock_sm_inst.load_spaces.return_value = {}

            output = get_knowledge_db_spaces()
            self.assertIn("*(目前無已註冊空間)*", output)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
