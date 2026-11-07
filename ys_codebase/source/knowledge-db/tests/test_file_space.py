"""
Unit Tests for knowledge-db Space Integration, Space Weights, and Computed Token Providers.
"""

import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from core.space import SpaceConfig, SpaceNotFoundError
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
import knowledge_db
from knowledge_db.config import KnowledgeDBConfig, resolve_threads
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.exceptions import InvalidConfigError
import knowledge_db.providers as kdb_prov
from knowledge_db.providers import get_knowledge_db_spaces
from knowledge_db.schema import validate_space_weights


class TestSpaceIntegrationAndWeights(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_dual_track_aggregation_and_priority(self):
        """驗證 KnowledgeEngine 雙軌空間配置聚合、Project contribute.json 優先權覆寫與權重載入"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cfg_dir = temp_path / "config"
            cfg_dir.mkdir(parents=True)
            mod_src = temp_path / "mod_src"
            proj_src = temp_path / "proj_src"
            contrib_shared = temp_path / "contrib_shared"
            proj_shared = temp_path / "proj_shared"
            for d in (mod_src, proj_src, contrib_shared, proj_shared):
                d.mkdir(parents=True)

            (mod_src / "mod.py").write_text(
                "class AlphaModUnique: pass\n", encoding="utf-8"
            )
            (proj_src / "proj.py").write_text(
                "class BetaProjUnique: pass\n", encoding="utf-8"
            )
            (contrib_shared / "old.py").write_text(
                "class GammaOldSharedUnique: pass\n", encoding="utf-8"
            )
            (proj_shared / "new.py").write_text(
                "class DeltaNewSharedUnique: pass\n", encoding="utf-8"
            )

            mock_contributes = {
                "spaces": {
                    "mod_space": {
                        "description": "模組注入空間",
                        "include": [str(mod_src)],
                        "file_patterns": ["*.py"],
                        "origin": "module:donor_mod",
                    },
                    "shared_space": {
                        "description": "Contributed 版本",
                        "include": [str(contrib_shared)],
                        "origin": "module:donor_mod",
                    },
                },
            }

            proj_contribute = {
                "spaces": {
                    "proj_space": {
                        "description": "專案注入空間",
                        "include": [str(proj_src)],
                    },
                    "shared_space": {
                        "description": "Project contribute.json 覆蓋版本",
                        "include": [str(proj_shared)],
                        "override_mode": "replace",
                    },
                },
                "space_weights": {
                    "mod_space": 1.0,
                    "proj_space": 1.2,
                    "shared_space": 1.5,
                },
            }
            with open(cfg_dir / "contribute.json", "w", encoding="utf-8") as f:
                json.dump(proj_contribute, f)

            engine = KnowledgeEngine(
                project_root=temp_path,
                storage_dir=temp_path / "storage",
                config_dir=cfg_dir,
                contributes_data=mock_contributes,
                embedding_mock_mode=True,
            )
            indexed_spaces = engine.get_indexed_spaces()

            self.assertIn("mod_space", indexed_spaces)
            self.assertIn("proj_space", indexed_spaces)
            self.assertIn("shared_space", indexed_spaces)
            self.assertEqual(
                indexed_spaces["shared_space"].description,
                "Project contribute.json 覆蓋版本",
            )
            self.assertAlmostEqual(engine.get_space_weight("shared_space"), 1.5)

            engine.build_unified_index(force=True)
            self.assertEqual(
                len(
                    engine.search(
                        "DeltaNewSharedUnique",
                        space="shared_space",
                        lexical_only=True,
                        auto_rebuild=False,
                    )
                ),
                1,
            )
            self.assertEqual(
                len(
                    engine.search(
                        "BetaProjUnique",
                        space="proj_space",
                        lexical_only=True,
                        auto_rebuild=False,
                    )
                ),
                1,
            )

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_union_spaces_and_uri_resolution(self):
        """驗證 KnowledgeEngine 全空間聯集索引與跨空間獨立檢索"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir1 = temp_path / "src1"
            src_dir1.mkdir(parents=True)
            src_dir2 = temp_path / "src2"
            src_dir2.mkdir(parents=True)

            (src_dir1 / "alpha.py").write_text(
                "class SpaceAlphaNode:\n    pass\n", encoding="utf-8"
            )
            (src_dir2 / "beta.py").write_text(
                "class SpaceBetaNode:\n    pass\n", encoding="utf-8"
            )

            mock_contributes = {
                "spaces": {
                    "space_a": {"include": [str(src_dir1)]},
                    "space_b": {"include": [str(src_dir2)]},
                },
                "space_weights": {"space_a": 1.0, "space_b": 1.1},
            }

            engine = KnowledgeEngine(
                project_root=temp_path,
                storage_dir=temp_path / "storage",
                contributes_data=mock_contributes,
                embedding_mock_mode=True,
            )
            idx = engine.build_unified_index(force=True)
            self.assertEqual(
                set(engine.get_indexed_spaces().keys()), {"space_a", "space_b"}
            )
            self.assertGreaterEqual(idx.doc_count, 2)

            hits_a = engine.search(
                "SpaceAlphaNode", space="space_a", auto_rebuild=False
            )
            self.assertEqual(len(hits_a), 1)
            self.assertEqual(hits_a[0].spaces, ["space_a"])

            hits_b = engine.search(
                "SpaceBetaNode", space="space_b", auto_rebuild=False
            )
            self.assertEqual(len(hits_b), 1)
            self.assertEqual(hits_b[0].spaces, ["space_b"])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_space_not_found_error(self):
        """驗證透過 KnowledgeEngine 查詢或打包未註冊空間時拋出 SpaceNotFoundError"""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(
                storage_dir=Path(temp_dir) / "storage",
                contributes_data={"spaces": {}},
                embedding_mock_mode=True,
            )
            with self.assertRaises(SpaceNotFoundError) as ctx:
                engine.status(space="non_existent_space")
            self.assertIn("non_existent_space", str(ctx.exception))

            with self.assertRaises(SpaceNotFoundError):
                engine.bundle(space="non_existent_space")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_invalid_source_path_warning_and_skip(self):
        """驗證空間包含不存在之來源路徑時，KnowledgeEngine 安全略過並正常完成有效路徑索引"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            valid_dir = temp_path / "valid_src"
            valid_dir.mkdir(parents=True)
            (valid_dir / "valid_mod.py").write_text(
                "def valid_entry_point():\n    return True\n", encoding="utf-8"
            )
            invalid_dir = temp_path / "missing_dir_12345"

            mock_contributes = {
                "spaces": {
                    "mixed_space": {
                        "include": [str(valid_dir), str(invalid_dir)],
                    }
                },
                "space_weights": {"mixed_space": 1.0},
            }

            engine = KnowledgeEngine(
                project_root=temp_path,
                storage_dir=temp_path / "storage",
                contributes_data=mock_contributes,
                embedding_mock_mode=True,
            )
            idx = engine.build_unified_index(force=True)
            self.assertGreaterEqual(idx.doc_count, 1)
            hits = engine.search(
                "valid_entry_point", space="mixed_space", auto_rebuild=False
            )
            self.assertEqual(len(hits), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_storage_dir_decoupling(self):
        """驗證 KnowledgeEngine.storage_dir 與 SpaceScanner.storage_root 物理隔離解耦"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            kdb_storage = temp_path / "knowledge_cache"
            engine = KnowledgeEngine(
                storage_dir=kdb_storage, contributes_data={"spaces": {}}
            )
            self.assertEqual(engine.storage_dir, kdb_storage.resolve())
            self.assertNotEqual(engine.storage_dir, engine.scanner.storage_root)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_empty_configurable_contribute_defaults(self):
        """驗證 knowledge-db 模組已移除 contributes/knowledge-db.json，且 _format.json 僅保留 space_weights"""
        mod_contrib = Path(_pkg_root) / "contributes" / "knowledge-db.json"
        self.assertFalse(mod_contrib.exists())

        fmt_path = Path(_pkg_root) / "contributes" / "_format.json"
        with open(fmt_path, "r", encoding="utf-8") as f:
            fmt_data = json.load(f)
        self.assertIn("space_weights", fmt_data)
        self.assertNotIn("languages", fmt_data)
        self.assertNotIn("spaces", fmt_data)
        self.assertNotIn("FileSpaceDef", fmt_data.get("_types", {}))
        self.assertNotIn("LanguageDef", fmt_data.get("_types", {}))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_configurable_config_templates_exist(self):
        """驗證 knowledge-db 模組預設組態整合至 configurable/config.project.json"""
        proj_tpl = Path(_pkg_root) / "configurable" / "config.project.json"
        local_tpl = Path(_pkg_root) / "configurable" / "config.local.json"

        self.assertTrue(proj_tpl.exists(), f"Configurable template {proj_tpl} must exist")
        self.assertFalse(
            local_tpl.exists(),
            f"Configurable template {local_tpl} must NOT exist (shadowing prevention)",
        )

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
    def test_knowledgedb_config_purity(self):
        """驗證 KnowledgeDBConfig 維持純粹性與 resolve_threads 唯一真理"""
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
            project_config={
                "knowledge-db": {
                    "enable_hot_reload_server": True,
                    "jit_vector_timeout_ms": 8000,
                }
            }
        )
        self.assertFalse(hasattr(loaded, "enable_hot_reload_server"))
        self.assertEqual(loaded.jit_vector_timeout_ms, 8000)
        self.assertEqual(loaded.jit_vector_timeout_seconds, 8.0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_space_weight_schema_and_validation(self):
        """驗證 SpaceConfig 與 space_weights 預設值、覆寫與 <= 0 阻斷"""
        sp_default = SpaceConfig(
            qualified_name="project/source",
            owner="project",
            short_name="source",
            entries=("src/",),
        )
        self.assertEqual(sp_default.short_name, "source")

        valid_weights = validate_space_weights({"docs": 1.2, "plans": 0.85})
        self.assertAlmostEqual(valid_weights["docs"], 1.2)
        self.assertAlmostEqual(valid_weights["plans"], 0.85)

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

    @require(Requirement.LOGIC)
    def test_opt_in_space_weights_excludes_unweighted_spaces(self):
        """驗證未於 space_weights 宣告權重之空間不會納入 KnowledgeEngine 索引、status() 與檢索結果"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            indexed_dir = temp_path / "indexed_src"
            cloud_dir = temp_path / "cloud_mirror"
            indexed_dir.mkdir(parents=True)
            cloud_dir.mkdir(parents=True)

            (indexed_dir / "core_logic.py").write_text(
                "def calculate_quantum_score():\n    return 42\n",
                encoding="utf-8",
            )
            (cloud_dir / "cloud_only_doc.py").write_text(
                "def secret_cloud_sync_marker():\n    return 99\n",
                encoding="utf-8",
            )

            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                project_root=temp_path,
                contributes_data={
                    "spaces": {
                        "source": {
                            "description": "受索引源碼空間",
                            "include": [str(indexed_dir)],
                            "file_patterns": ["*.py"],
                        },
                        "cloud": {
                            "description": "純雲端同步空間（未配置 weight）",
                            "include": [str(cloud_dir), str(indexed_dir)],
                            "file_patterns": ["*.py"],
                        },
                    },
                    "space_weights": {
                        "source": 1.0,
                    },
                },
            )

            self.assertEqual(
                {sp.short_name for sp in engine.space_manager.list_spaces()},
                {"source", "cloud"},
            )
            self.assertEqual(set(engine.get_indexed_spaces().keys()), {"source"})
            self.assertEqual(engine.get_all_space_weights(), {"source": 1.0})

            st = engine.status()
            self.assertEqual(st["total_spaces"], 1)
            self.assertIn("source", st["spaces"])
            self.assertNotIn("cloud", st["spaces"])

            idx = engine.build_unified_index(force=True)
            indexed_names = {sym.name for sym in idx.symbols.values()}
            self.assertIn("calculate_quantum_score", indexed_names)
            self.assertNotIn("secret_cloud_sync_marker", indexed_names)
            for sym in idx.symbols.values():
                self.assertNotIn("cloud", sym.spaces)

            hits_source = engine.search("calculate_quantum_score", lexical_only=True)
            self.assertEqual(len(hits_source), 1)
            self.assertEqual(hits_source[0].spaces, ["source"])

            hits_cloud = engine.search("secret_cloud_sync_marker", lexical_only=True)
            self.assertEqual(len(hits_cloud), 0)

        self.mark_passed()


class TestKnowledgeDBProviders(YSCBTestCase):
    """驗證 Token Providers 與空間速查表輸出"""

    @require(Requirement.LOGIC)
    def test_get_knowledge_db_spaces_output_format(self):
        """驗證 get_knowledge_db_spaces 產出正確的 Markdown 空間速查表格"""
        mock_spaces = [
            SpaceConfig(
                qualified_name="alpha/alpha_space",
                owner="alpha",
                short_name="alpha_space",
                description="Alpha 領域空間",
                entries=("module://alpha/docs",),
            ),
            SpaceConfig(
                qualified_name="beta/beta_space",
                owner="beta",
                short_name="beta_space",
                description="Beta 核心源碼空間",
                entries=("module://beta/src",),
            ),
        ]

        with patch("core.space.providers._resolve_registry_from_context") as mock_res:
            mock_res.return_value.list_spaces.return_value = mock_spaces

            output = get_knowledge_db_spaces()
            self.assertIn(
                "| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |",
                output,
            )
            self.assertIn("`alpha_space`", output)
            self.assertIn("`beta_space`", output)
            self.assertIn("Alpha 領域空間", output)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_get_knowledge_db_spaces_empty_fallback(self):
        """驗證無任何空間時之安全降級輸出"""
        with patch("core.space.providers._resolve_registry_from_context") as mock_res:
            mock_res.return_value.list_spaces.return_value = []

            output = get_knowledge_db_spaces()
            self.assertIn("*(目前無已註冊空間)*", output)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_providers_and_lazy_init_without_networkx_or_fastembed(self):
        """驗證 knowledge_db.providers 於阻斷 networkx/fastembed 時正常運作、恢復模組狀態並覆蓋頂層 __getattr__/__dir__"""
        mf_path = Path(_pkg_root) / "manifest.json"
        mf_data = json.loads(mf_path.read_text(encoding="utf-8"))
        self.assertEqual(knowledge_db.__version__, mf_data["version"])

        mock_spaces = [
            SpaceConfig(
                qualified_name="project/source",
                owner="project",
                short_name="source",
                description="No-networkx test space",
                entries=("project://src",),
            )
        ]
        try:
            with patch.dict(sys.modules, {"networkx": None, "fastembed": None}):
                importlib.reload(kdb_prov)
                with patch("core.space.providers._resolve_registry_from_context") as mock_res:
                    mock_res.return_value.list_spaces.return_value = mock_spaces
                    table = kdb_prov.get_knowledge_db_spaces()
                    self.assertIn("`source`", table)
                    self.assertIn("No-networkx test space", table)
        finally:
            importlib.reload(kdb_prov)

        # 補測 knowledge_db.__dir__ 與 __getattr__ 未知屬性 AttributeError
        exported = dir(knowledge_db)
        self.assertIn("KnowledgeEngine", exported)
        self.assertIn("InvertedIndex", exported)
        self.assertIs(getattr(knowledge_db, "KnowledgeEngine"), KnowledgeEngine)
        with self.assertRaises(AttributeError):
            _ = getattr(knowledge_db, "NonExistentSymbolXYZ_999")

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
