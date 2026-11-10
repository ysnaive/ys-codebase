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


    @require(Requirement.LOGIC)
    def test_vector_text_hash_line_shift_reuse_and_ghost_posting_prevention(self) -> None:
        """Verify line-shifted unchanged functions reuse existing vectors with 0 embed_texts calls and generation-guarded symbol alignment purges old BM25 postings."""
        src_dir = self.proj_root / "shift_src"
        src_dir.mkdir(parents=True)
        target_py = src_dir / "service.py"
        target_py.write_text(
            "def alpha_fn(x: int) -> int:\n"
            '    """UniqueLegacyTokenXyz initial alpha logic"""\n'
            "    return x + 1\n\n"
            "def beta_fn(y: int) -> int:\n"
            '    """Stable beta docstring"""\n'
            "    return y * 2\n",
            encoding="utf-8",
        )
        sp = SpaceConfig(
            qualified_name="project/shift_space",
            owner="project",
            short_name="shift_space",
            entries=(src_dir.as_posix(),),
        )
        engine = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"shift_space": sp}},
            embedding_mock_mode=True,
        )
        idx0 = engine.build_unified_index(force=True)
        old_ids = set(idx0.symbols.keys())

        embed_calls = []
        orig_embed = engine.embedding_service.embed_texts

        def _spy_embed(texts, *args, **kwargs):
            embed_calls.append(list(texts))
            return orig_embed(texts, *args, **kwargs)

        engine.embedding_service.embed_texts = _spy_embed
        try:
            write_text_and_advance_mtime(
                target_py,
                "# header 1\n# header 2\n# header 3\n# header 4\n"
                "def alpha_fn(x: int) -> int:\n"
                '    """UniqueLegacyTokenXyz initial alpha logic"""\n'
                "    return x + 1\n\n"
                "def beta_fn(y: int) -> int:\n"
                '    """Stable beta docstring"""\n'
                "    return y * 2\n",
            )
            with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_shift:
                self.assertTrue(diff_shift.has_changes)
                res_shift = engine.pipeline.hot_patch_unified_index(diff_shift.detail, skip_vectors=False)
                self.assertTrue(res_shift.success)
            self.assertEqual(len(embed_calls), 0)
            new_ids = set(engine.pipeline.unified_index.symbols.keys())
            self.assertNotEqual(old_ids, new_ids)
            self.assertEqual(set(engine.pipeline.hybrid_engine.vector_index.doc_ids), new_ids)
        finally:
            engine.embedding_service.embed_texts = orig_embed

        write_text_and_advance_mtime(
            target_py,
            "# header 1\n# header 2\n# header 3\n# header 4\n"
            "def alpha_fn(x: int) -> int:\n"
            '    """ModernReplacementTokenAbc updated alpha logic"""\n'
            "    return x + 99\n\n"
            "def beta_fn(y: int) -> int:\n"
            '    """Stable beta docstring"""\n'
            "    return y * 2\n",
        )
        engine.ast_engine.ensure_jit_synced(allow_parallel=False)
        engine.pipeline._align_index_symbols_with_ast_snapshot(engine.pipeline.unified_index)
        with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_mod:
            res_mod = engine.pipeline.hot_patch_unified_index(diff_mod.detail, skip_vectors=False)
            self.assertTrue(res_mod.success)

        ghost_hits = engine.pipeline.search("UniqueLegacyTokenXyz", lexical_only=True, aggregate=False)
        self.assertEqual(len(ghost_hits), 0)
        fresh_hits = engine.pipeline.search("ModernReplacementTokenAbc", lexical_only=False, aggregate=False)
        self.assertGreaterEqual(len(fresh_hits), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_reconfigure_noop_yielded_degradation_and_config_hash_sync(self) -> None:
        """Verify reconfigure_model no-op fast return, yielded_to_foreground partial-vector BM25 degradation, and space_weights config_hash invalidation."""
        from knowledge_db.service import clear_worker_state, write_worker_state

        src_dir = self.proj_root / "cfg_kdb_src"
        src_dir.mkdir(parents=True)
        (src_dir / "mod.py").write_text(
            "def compute_metric(v: float) -> float:\n"
            '    """Compute deterministic metric score"""\n'
            "    return v * 1.5\n",
            encoding="utf-8",
        )
        sp = SpaceConfig(
            qualified_name="project/cfg_kdb",
            owner="project",
            short_name="cfg_kdb",
            entries=(src_dir.as_posix(),),
        )
        engine = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"cfg_kdb": sp}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)

        import threading
        import time

        lock_ready = threading.Event()
        release_lock = threading.Event()

        def _hold_init_lock() -> None:
            with engine.embedding_service._init_lock:
                lock_ready.set()
                release_lock.wait(timeout=3.0)

        bg = threading.Thread(target=_hold_init_lock, daemon=True)
        bg.start()
        try:
            self.assertTrue(lock_ready.wait(timeout=2.0))
            t0 = time.perf_counter()
            engine.embedding_service.reconfigure_model(
                engine.embedding_service.model_name,
                engine.embedding_service.max_threads,
                engine.embedding_service.enable_vector_search,
            )
            self.assertLess(time.perf_counter() - t0, 0.2)
        finally:
            release_lock.set()
            bg.join(timeout=2.0)

        sym_id = next(iter(engine.pipeline.unified_index.symbols.keys()))
        engine.pipeline.hybrid_engine.vector_index.patch_incremental(
            removed_doc_ids={sym_id},
            new_doc_ids=[],
            new_vectors=None,
        )
        import contextlib
        import io

        indices_dir = engine.pipeline.get_indices_dir()
        write_worker_state(indices_dir, worker_running=True, busy=False, phase="yielded_to_foreground")
        err_degraded = io.StringIO()
        with contextlib.redirect_stderr(err_degraded):
            hits_deg = engine.pipeline.search("compute_metric", lexical_only=False, aggregate=False)
        self.assertGreaterEqual(len(hits_deg), 1)
        self.assertIn("已暫時降級為純 BM25 搜尋", err_degraded.getvalue())

        engine.sync_vector_deficit_step(batch_size=32)
        clear_worker_state(indices_dir)
        err_restored = io.StringIO()
        with contextlib.redirect_stderr(err_restored):
            hits_ok = engine.pipeline.search("compute_metric", lexical_only=False, aggregate=False)
        self.assertGreaterEqual(len(hits_ok), 1)
        self.assertNotIn("已暫時降級為純 BM25 搜尋", err_restored.getvalue())

        self.assertFalse(engine.pipeline._has_pending_space_changes())
        engine.space_weights = {"cfg_kdb": 3.0}
        self.assertTrue(engine.pipeline._has_pending_space_changes())
        engine.pipeline.sync_incremental_changes(skip_vectors=False)
        self.assertFalse(engine.pipeline._has_pending_space_changes())
        self.mark_passed()


    @require(Requirement.LOGIC)
    def test_legacy_vector_hash_backfill_unlocked_onnx_inference_and_concurrent_cow_search(self) -> None:
        """Verify legacy VectorIndex without doc_text_hashes backfills smoothly, hot_patch_unified_index releases _index_lock during ONNX embed_texts, and concurrent searches never hit RuntimeError."""
        import threading
        from core.space import ScanDiffDetail

        root_mod = self.proj_root / "mod"
        nested_mod = self.proj_root / "space_a" / "mod"
        root_mod.mkdir(parents=True)
        nested_mod.mkdir(parents=True)
        root_py = root_mod / "__init__.py"
        nested_py = nested_mod / "__init__.py"
        root_py.write_text(
            "def root_survivor_fn() -> int:\n"
            '    """Root module survivor docstring"""\n'
            "    return 7\n",
            encoding="utf-8",
        )
        nested_py.write_text(
            "def nested_target_fn() -> int:\n"
            '    """OriginalLegacyBodyAlpha"""\n'
            "    return 1\n",
            encoding="utf-8",
        )
        sp_root = SpaceConfig(
            qualified_name="project/root_sp",
            owner="project",
            short_name="root_sp",
            entries=(self.proj_root.as_posix(),),
        )
        sp_nested = SpaceConfig(
            qualified_name="project/nested_sp",
            owner="project",
            short_name="nested_sp",
            entries=((self.proj_root / "space_a").as_posix(),),
        )
        engine = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"root_sp": sp_root, "nested_sp": sp_nested}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)

        # 1. Simulate legacy unified.vectors.bin.gz on disk with empty doc_text_hashes={}
        vec_file = engine.pipeline.get_indices_dir() / "unified.vectors.bin.gz"
        engine.pipeline.hybrid_engine.vector_index.doc_text_hashes.clear()
        engine.pipeline.hybrid_engine.vector_index.save_binary(vec_file)

        engine2 = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"root_sp": sp_root, "nested_sp": sp_nested}},
            embedding_mock_mode=True,
        )
        engine2.pipeline._ensure_indices_loaded(load_vectors=True, force_reload=True)
        self.assertGreaterEqual(len(engine2.pipeline.hybrid_engine.vector_index.doc_text_hashes), 2)
        self.assertFalse(engine2.pipeline._vector_index_dirty)

        # 2. Prove _index_lock is NOT held while embed_texts runs during hot_patch_unified_index, AND concurrent searches never raise RuntimeError
        embed_entered = threading.Event()
        allow_embed_finish = threading.Event()
        lock_acquired_by_fg = []
        search_errors = []
        orig_embed = engine2.embedding_service.embed_texts

        def _slow_embed(texts, *args, **kwargs):
            embed_entered.set()
            allow_embed_finish.wait(timeout=3.0)
            return orig_embed(texts, *args, **kwargs)

        engine2.embedding_service.embed_texts = _slow_embed
        write_text_and_advance_mtime(
            nested_py,
            "def nested_target_fn() -> int:\n"
            '    """UpdatedConcurrentBodyOmega"""\n'
            "    return 2\n",
        )

        patch_errors = []

        def _bg_patch() -> None:
            try:
                with engine2.scanner.consume_diff("nested_sp", consumer_id="knowledge-db") as diff_n:
                    res = engine2.pipeline.hot_patch_unified_index(diff_n.detail, skip_vectors=False)
                    if not res.success:
                        patch_errors.append("hot_patch_unified_index returned False")
            except Exception as bg_exc:
                patch_errors.append(bg_exc)

        patch_t = threading.Thread(target=_bg_patch, daemon=True)
        patch_t.start()
        try:
            self.assertTrue(embed_entered.wait(timeout=3.0))
            # Foreground thread must be able to acquire _index_lock non-blockingly AND execute lexical search while ONNX embed_texts is in flight!
            got_lock = engine2.pipeline._index_lock.acquire(blocking=False)
            if got_lock:
                engine2.pipeline._index_lock.release()
            lock_acquired_by_fg.append(got_lock)
            try:
                hits_during = engine2.pipeline.search("root_survivor_fn", lexical_only=True, aggregate=False)
                self.assertGreaterEqual(len(hits_during), 1)
            except Exception as s_exc:
                search_errors.append(s_exc)
        finally:
            allow_embed_finish.set()
            patch_t.join(timeout=3.0)
            engine2.embedding_service.embed_texts = orig_embed

        self.assertEqual(lock_acquired_by_fg, [True])
        self.assertEqual(patch_errors, [])
        self.assertEqual(search_errors, [])

        # 2b. Verify concurrent foreground search during unlocked ONNX inference did NOT clobber working_idx or disk snapshot!
        hits_updated_mem = engine2.pipeline.search("UpdatedConcurrentBodyOmega", lexical_only=False, aggregate=False)
        self.assertTrue(any(h.symbol.name == "nested_target_fn" for h in hits_updated_mem))
        engine_cold_verify = KnowledgeEngine(
            project_root=self.proj_root,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"root_sp": sp_root, "nested_sp": sp_nested}},
            embedding_mock_mode=True,
        )
        hits_updated_disk = engine_cold_verify.pipeline.search(
            "UpdatedConcurrentBodyOmega", lexical_only=True, aggregate=False
        )
        self.assertTrue(any(h.symbol.name == "nested_target_fn" for h in hits_updated_disk))
        del hits_updated_disk
        del engine_cold_verify

        # 2c. Verify Posting._tables_ref decouples InvertedIndex so old CoW InvertedIndex is immediately garbage-collected!
        import gc
        import weakref

        old_idx_ref = weakref.ref(engine2.pipeline._unified_index)
        write_text_and_advance_mtime(
            nested_py,
            "def nested_target_fn() -> int:\n"
            '    """UpdatedConcurrentBodyGamma"""\n'
            "    return 3\n",
        )
        with engine2.scanner.consume_diff("nested_sp", consumer_id="knowledge-db") as diff_g:
            res_g = engine2.pipeline.hot_patch_unified_index(diff_g.detail, skip_vectors=False)
            self.assertTrue(res_g.success)
        gc.collect()
        self.assertIsNone(old_idx_ref())

        # 2d. Verify probe timeout fuse (>10 new symbols with tiny timeout_seconds) evicts stale same-line vector of nested_target_fn!
        old_nested_doc_id = next(
            did for did, s in engine2.pipeline.unified_index.symbols.items() if s.name == "nested_target_fn"
        )
        self.assertIn(old_nested_doc_id, engine2.pipeline.hybrid_engine.vector_index.doc_ids)
        many_fns = [
            "def nested_target_fn() -> int:\n"
            '    """CompletelyRewrittenFuseTarget"""\n'
            "    return 99\n"
        ] + [f"def extra_fuse_sym_{k}() -> int:\n    return {k}\n" for k in range(12)]
        write_text_and_advance_mtime(nested_py, "\n".join(many_fns))
        orig_probe = engine2.embedding_service.embed_texts_probe
        try:
            engine2.embedding_service.embed_texts_probe = lambda texts, total_count=0: (
                orig_probe(texts, total_count=total_count)[0],
                999.0,
            )
            with engine2.scanner.consume_diff("nested_sp", consumer_id="knowledge-db") as diff_fuse:
                res_fuse = engine2.pipeline.hot_patch_unified_index(
                    diff_fuse.detail, timeout_seconds=0.05, skip_vectors=False
                )
                self.assertTrue(res_fuse.success)
                self.assertTrue(res_fuse.vector_degraded)
        finally:
            engine2.embedding_service.embed_texts_probe = orig_probe
        self.assertNotIn(old_nested_doc_id, engine2.pipeline.hybrid_engine.vector_index.doc_ids)

        # 3. Deleting space_a/mod/__init__.py via absolute path must NOT evict root mod/__init__.py (root_survivor_fn)
        nested_py.unlink()
        res_del = engine2.pipeline.hot_patch_unified_index(
            ScanDiffDetail(added=set(), modified=set(), deleted={nested_py.as_posix()}),
            skip_vectors=False,
        )
        self.assertTrue(res_del.success)
        rem_syms = {s.name for s in engine2.pipeline.unified_index.symbols.values()}
        self.assertNotIn("nested_target_fn", rem_syms)
        self.assertIn("root_survivor_fn", rem_syms)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
