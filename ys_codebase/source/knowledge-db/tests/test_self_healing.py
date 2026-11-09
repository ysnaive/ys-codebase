"""
Unit and Integration Tests for Knowledge-DB Stage 1 Vector Eviction Self-Healing
and Cross-Space Same-Basename Dirty File Isolation.
"""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from core.space import SpaceConfig
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.embedding import format_symbol_embedding_text
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.io_utils import is_dirty_file_match, normalize_dirty_paths
from tests import write_text_and_advance_mtime


class TestKnowledgeDBSelfHealing(YSCBTestCase):
    """Tests for Stage 1 old vector eviction and cross-space path normalization."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_kdb_self_healing_"))
        self.proj_root = self.tmp_dir / "project"
        self.storage_dir = self.tmp_dir / "storage"
        self.proj_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_stage1_skip_vectors_evicts_old_vectors_for_same_line_edits(self) -> None:
        """
        Verify that when a symbol's body/docstring changes without changing its start line_number
        (so UnifiedSymbol.compute_id remains identical), hot_patch_unified_index(skip_vectors=True)
        evicts old_doc_ids from VectorIndex so Stage 2 sync_vector_deficit_step recomputes its vector.
        """
        src_dir = self.proj_root / "src"
        src_dir.mkdir(parents=True)
        target_py = src_dir / "worker.py"
        target_py.write_text(
            "def process_task(x: int) -> int:\n"
            "    '''Original docstring alpha'''\n"
            "    return x + 1\n",
            encoding="utf-8",
        )

        sp = SpaceConfig(
            qualified_name="project/source",
            owner="project",
            short_name="source",
            entries=(src_dir.as_posix(),),
        )
        engine = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"source": sp}},
            embedding_mock_mode=True,
        )

        idx = engine.build_unified_index(force=True)
        sym_before = next(s for s in idx.symbols.values() if s.name == "process_task")
        sym_id = sym_before.id

        vec_idx_before = engine.pipeline.hybrid_engine.vector_index
        self.assertIn(sym_id, vec_idx_before.doc_ids)
        pos_before = vec_idx_before.doc_ids.index(sym_id)
        vec_before = vec_idx_before.vectors[pos_before].copy()

        # Modify docstring/signature on the exact same start line (line 1) -> compute_id stays identical!
        write_text_and_advance_mtime(
            target_py,
            "def process_task(x: int, y: int = 0) -> int:\n"
            "    '''Updated docstring beta with completely new semantics'''\n"
            "    return x + y + 100\n",
        )

        with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_res:
            self.assertTrue(diff_res.has_changes)
            patch_res = engine.pipeline.hot_patch_unified_index(
                diff_res.detail, skip_vectors=True
            )
            self.assertTrue(patch_res.success)

        sym_after = next(
            s
            for s in engine.pipeline.unified_index.symbols.values()
            if s.name == "process_task"
        )
        # Symbol ID must remain stable for call graph continuity
        self.assertEqual(sym_after.id, sym_id)
        self.assertIn("Updated docstring beta", sym_after.docstring)

        # Stage 1 skip_vectors=True must have evicted sym_id from VectorIndex!
        deficit = engine.pipeline.get_vector_deficit_info()
        self.assertGreaterEqual(deficit["missing_count"], 1)
        self.assertNotIn(sym_id, engine.pipeline.hybrid_engine.vector_index.doc_ids)

        # Stage 2 micro-batch deficit sync must now detect and re-embed sym_id
        sync_res = engine.sync_vector_deficit_step(batch_size=32)
        self.assertGreaterEqual(sync_res["embedded_in_step"], 1)
        self.assertEqual(sync_res["remaining"], 0)

        vec_idx_after = engine.pipeline.hybrid_engine.vector_index
        self.assertIn(sym_id, vec_idx_after.doc_ids)
        pos_after = vec_idx_after.doc_ids.index(sym_id)
        vec_after = vec_idx_after.vectors[pos_after]

        expected_new_vec = engine.embedding_service.embed_texts(
            [format_symbol_embedding_text(sym_after)]
        )[0]
        self.assertFalse(np.allclose(vec_before, vec_after))
        np.testing.assert_allclose(vec_after, expected_new_vec, rtol=1e-5, atol=1e-6)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cross_space_same_filename_isolation(self) -> None:
        """
        Verify that modifying or deleting a top-level file (without '/') or nested relative path
        in one space does not falsely match or evict same-named files in other spaces/modules.
        """
        # 1. Direct unit test of is_dirty_file_match without '/' wildcarding subdirectories
        dirty_norm = normalize_dirty_paths(["README.md"])
        self.assertTrue(is_dirty_file_match("README.md", dirty_norm))
        self.assertFalse(is_dirty_file_match("space_a/README.md", dirty_norm))
        self.assertFalse(is_dirty_file_match("space_b/sub/README.md", dirty_norm))

        # 1b. Cross-module relative path with '/' must NOT suffix-match other modules' relative paths
        dirty_rel_cli = normalize_dirty_paths(["scripts/cli.py"])
        self.assertTrue(is_dirty_file_match("scripts/cli.py", dirty_rel_cli))
        self.assertTrue(is_dirty_file_match("/workspace/mod_a/scripts/cli.py", dirty_rel_cli))
        self.assertFalse(is_dirty_file_match("ys_codebase/source/server/scripts/cli.py", dirty_rel_cli))

        # 2. Multi-space integration test with top-level __init__.py in two separate spaces
        mod_a_dir = self.proj_root / "mod_a"
        mod_b_dir = self.proj_root / "mod_b"
        mod_a_dir.mkdir(parents=True)
        mod_b_dir.mkdir(parents=True)

        init_a = mod_a_dir / "__init__.py"
        init_b = mod_b_dir / "__init__.py"
        init_a.write_text("class ModAInitSymbol:\n    pass\n", encoding="utf-8")
        init_b.write_text("class ModBInitSymbol:\n    pass\n", encoding="utf-8")

        sp_a = SpaceConfig(
            qualified_name="project/space_a",
            owner="project",
            short_name="space_a",
            entries=(mod_a_dir.as_posix(),),
        )
        sp_b = SpaceConfig(
            qualified_name="project/space_b",
            owner="project",
            short_name="space_b",
            entries=(mod_b_dir.as_posix(),),
        )

        engine = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={
                "spaces": {
                    "space_a": sp_a,
                    "space_b": sp_b,
                }
            },
            embedding_mock_mode=True,
        )

        engine.build_unified_index(force=True)
        orig_b_sym = next(
            s for s in engine.pipeline.ast_engine._snapshot.symbols.values()
            if s.name == "ModBInitSymbol"
        )

        # Modify only mod_a/__init__.py (which yields rel_path="mod_a/__init__.py" in space_a)
        write_text_and_advance_mtime(init_a, "class ModAInitUpdated:\n    pass\n")
        with engine.scanner.consume_diff(
            "space_a", consumer_id="knowledge-db"
        ) as diff_a:
            self.assertEqual(diff_a.modified, ["mod_a/__init__.py"])
            res = engine.pipeline.hot_patch_unified_index(diff_a.detail)
            self.assertTrue(res.success)

        # ModBInitSymbol must remain untouched (same object identity in ASTSnapshot & InvertedIndex)
        # and SemanticBundler transient cache must be released after build/hot-patch!
        self.assertEqual(len(engine.bundler._file_symbols_cache), 0)
        cur_b_sym = next(
            s for s in engine.pipeline.unified_index.symbols.values()
            if s.name == "ModBInitSymbol"
        )
        self.assertIs(cur_b_sym, orig_b_sym)
        sym_names = {s.name for s in engine.pipeline.unified_index.symbols.values()}
        self.assertIn("ModBInitSymbol", sym_names)
        self.assertIn("ModAInitUpdated", sym_names)
        self.assertNotIn("ModAInitSymbol", sym_names)

        # Delete mod_a/__init__.py -> ModBInitSymbol in space_b must NOT be evicted!
        init_a.unlink()
        with engine.scanner.consume_diff(
            "space_a", consumer_id="knowledge-db"
        ) as diff_del:
            self.assertEqual(diff_del.deleted, ["mod_a/__init__.py"])
            res_del = engine.pipeline.hot_patch_unified_index(diff_del.detail)
            self.assertTrue(res_del.success)

        sym_names_after = {
            s.name for s in engine.pipeline.unified_index.symbols.values()
        }
        self.assertNotIn("ModAInitUpdated", sym_names_after)
        self.assertIn("ModBInitSymbol", sym_names_after)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
