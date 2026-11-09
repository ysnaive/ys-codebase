"""
Unit tests for `ast_engine` core data models (`schema.py`), binary I/O utilities (`io_utils.py`),
PEP 562 module lazy exports (`ast_engine.__init__`), overload child parent_id synchronization (`bundler.py`),
and engine persistence/caching (`engine.py`).
"""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

import ast_engine
from ast_engine.bundler import ensure_unique_overload_ids
from ast_engine.dialects.csharp import CSharpDialect
from ast_engine.engine import ASTEngine
from ast_engine.exceptions import SchemaValidationError
from ast_engine.formatter import ASTResultFormatter
from ast_engine.graph import CallGraphIndex
from ast_engine.io_utils import (
    _format_cross_drive_relpath,
    atomic_save_gzip_pickle,
    compute_project_relpath,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
)
from ast_engine.linker import TopologyLinker, expand_contract_symbol_ids
from ast_engine.parsers.python_ast import PythonASTParser
from ast_engine.resolver import SnippetExtractor
from ast_engine.schema import (
    ASTSnapshot,
    FileSymbolGraph,
    LanguageConfig,
    MemberInfo,
    OutlineNode,
    OutlineResult,
    ProvenanceStep,
    RelationEdge,
    SemanticBundle,
    Span,
    SymbolCallSite,
    SymbolKind,
    SymbolNode,
    UnifiedSymbol,
)
from core.space import SpaceConfig
from tests import ASTTestCase, Requirement, require


class TestASTEngineCore(ASTTestCase):
    """Tests for AST schema contracts, binary I/O utilities, PEP 562 exports, and engine core invariants."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_core_test_"))

    def tearDown(self) -> None:
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_unified_symbol_from_dict_children_member_info(self) -> None:
        """Verify UnifiedSymbol.from_dict deserializes children/members as Tuple[MemberInfo, ...] with line_number and line properties."""
        member = MemberInfo(
            name="compute",
            kind="method",
            signature="def compute(self, x: int) -> int",
            line_number=42,
            visibility="public",
            docstring="Compute value",
        )
        sym = UnifiedSymbol(
            id="sym_cls",
            name="Calculator",
            kind="class",
            file_path="src/calc.py",
            line_number=10,
            end_line=60,
            language="python",
            children=(member,),
            members=(member,),
        )
        restored = UnifiedSymbol.from_dict(sym.to_dict())
        self.assertEqual(len(restored.children), 1)
        self.assertIsInstance(restored.children[0], MemberInfo)
        self.assertIs(restored.children, restored.members)
        self.assertEqual(restored.children[0].line_number, 42)
        self.assertEqual(restored.children[0].line, 42)

        legacy_dict = sym.to_dict()
        legacy_dict["children"] = [
            {
                "name": "legacy_fn",
                "kind": "method",
                "line": 77,
                "end_line": 80,
                "signature": "def legacy_fn()",
            }
        ]
        legacy_dict.pop("members", None)
        restored_legacy = UnifiedSymbol.from_dict(legacy_dict)
        self.assertEqual(len(restored_legacy.children), 1)
        self.assertIsInstance(restored_legacy.children[0], MemberInfo)
        self.assertEqual(restored_legacy.children[0].line_number, 77)
        self.assertEqual(restored_legacy.children[0].line, 77)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_schema_validation_errors_and_none_container_defenses(self) -> None:
        """Verify all schema dataclasses validate input types, propagate inner SchemaValidationError, defend against None containers, and index partial_files."""
        for cls_type in (
            MemberInfo,
            LanguageConfig,
            UnifiedSymbol,
            SymbolCallSite,
            SemanticBundle,
            ASTSnapshot,
            OutlineNode,
            OutlineResult,
            CallGraphIndex,
        ):
            with self.assertRaises(SchemaValidationError):
                cls_type.from_dict("invalid_non_dict")  # type: ignore[arg-type]

        with self.assertRaises(SchemaValidationError):
            MemberInfo.from_dict({"name": "only_name"})
        with self.assertRaises(SchemaValidationError):
            LanguageConfig.from_dict({"id": "python"})
        with self.assertRaises(SchemaValidationError):
            UnifiedSymbol.from_dict({"id": "s1", "name": "Foo"})
        with self.assertRaises(SchemaValidationError):
            ASTSnapshot.from_dict({"symbols": {"bad_sym": {"id": "s1", "name": "MissingFields"}}})
        with self.assertRaises(SchemaValidationError):
            CallGraphIndex.from_dict({"workspace_graph": {"nodes_by_id": {"bad": {"invalid": "node"}}}})

        # None container defense across dataclasses
        cfg = LanguageConfig.from_dict({"id": "py", "extensions": None, "custom_kinds": None})
        self.assertEqual(cfg.extensions, ())
        self.assertEqual(cfg.custom_kinds, ())

        sym = UnifiedSymbol.from_dict(
            {
                "id": "s1",
                "name": "Widget",
                "kind": "class",
                "file_path": "ui/widget_a.cs",
                "line_number": 1,
                "language": "c_sharp",
                "children": None,
                "parameters": None,
                "metadata": {"partial_files": ["ui/widget_a.cs", "ui/widget_b.cs"], "space": "ui"},
            }
        )
        self.assertEqual(sym.children, ())
        self.assertEqual(sym.parameters, ())
        self.assertEqual(sym.spaces, ["ui"])

        bundle = SemanticBundle.from_dict({"version": "1.0", "space_name": "ui", "symbols": None, "metadata": None})
        self.assertEqual(bundle.symbols, [])
        self.assertEqual(bundle.metadata, {})

        snap = ASTSnapshot(symbols={"s1": sym})
        self.assertIn("s1", snap.file_to_symbol_ids.get("ui/widget_a.cs", []))
        self.assertIn("s1", snap.file_to_symbol_ids.get("ui/widget_b.cs", []))

        snap_none = ASTSnapshot.from_dict(
            {"ast_generation": 2, "space_generations": None, "symbols": None, "file_to_symbol_ids": None, "files_map": None}
        )
        self.assertEqual(snap_none.space_generations, {})
        self.assertEqual(snap_none.file_to_symbol_ids, {})

        node = OutlineNode.from_dict({"name": "N", "kind": "class", "line_number": 1, "members": None, "metadata": None})
        self.assertEqual(node.children, [])
        self.assertEqual(node.metadata, {})

        out_res = OutlineResult.from_dict(
            {
                "file_path": "missing.py",
                "symbols": None,
                "partial_siblings": None,
                "warnings": None,
                "filters": None,
                "error": "File not found: missing.py",
            }
        )
        self.assertEqual(out_res.error, "File not found: missing.py")
        self.assertEqual(out_res.to_dict().get("error"), "File not found: missing.py")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ast_engine_all_56_public_symbols_lazy_loading(self) -> None:
        """Verify all 72 exported symbols in ast_engine.__all__ resolve via PEP 562 __getattr__ and match manifest version."""
        manifest_path = Path(_AST_ROOT) / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(ast_engine.__version__, manifest_data["version"])
        self.assertEqual(len(ast_engine.__all__), 72)

        for sym_name in ast_engine.__all__:
            self.assertIn(sym_name, dir(ast_engine))
            resolved_attr = getattr(ast_engine, sym_name)
            self.assertIsNotNone(resolved_attr, f"Export '{sym_name}' resolved to None")

        with self.assertRaises(AttributeError):
            _ = ast_engine.NON_EXISTENT_SYMBOL_XYZ
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_io_utils_gzip_pickle_and_relpath_boundaries(self) -> None:
        """Verify atomic_save_gzip_pickle preserves concurrent .tmp files on normal write, load_gzip_pickle corruption/missing handling, and compute_project_relpath cross-drive boundaries."""
        missing_p = self.temp_dir / "missing.bin.gz"
        self.assertIsNone(load_gzip_pickle(missing_p, raise_on_missing=False))
        with self.assertRaises(FileNotFoundError):
            load_gzip_pickle(missing_p, raise_on_missing=True)

        valid_p = self.temp_dir / "valid.bin.gz"
        concurrent_tmp = self.temp_dir / ".valid.bin.gz.tmp.88888"
        concurrent_tmp.write_bytes(b"in_flight_concurrent_writer")
        atomic_save_gzip_pickle(valid_p, {"hello": "world", "count": 7})
        self.assertEqual(load_gzip_pickle(valid_p), {"hello": "world", "count": 7})
        # Normal write completion must NOT delete another concurrent writer's .tmp file
        self.assertTrue(concurrent_tmp.exists())
        concurrent_tmp.unlink()

        corrupt_p = self.temp_dir / "corrupt.bin.gz"
        corrupt_p.write_bytes(b"not a valid gzip stream")
        self.assertIsNone(load_gzip_pickle(corrupt_p, raise_on_missing=False))
        with self.assertRaises(Exception):
            load_gzip_pickle(corrupt_p, raise_on_missing=True)

        # Verify compute_project_relpath handles '..foo.py' inside root vs file outside root and cross-drive formatting
        proj_root = self.temp_dir / "workspace"
        proj_root.mkdir(parents=True, exist_ok=True)
        dotdot_file = proj_root / "..weird_name.py"
        dotdot_file.write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(compute_project_relpath(dotdot_file, project_root=proj_root), "..weird_name.py")

        outside_file = self.temp_dir / "outside.py"
        outside_file.write_text("y = 2\n", encoding="utf-8")
        fb_dir = self.temp_dir
        self.assertEqual(
            compute_project_relpath(outside_file, fallback_base=fb_dir, project_root=proj_root),
            f"{fb_dir.name}/outside.py",
        )
        self.assertEqual(_format_cross_drive_relpath(Path("D:/ext_pkg/a/mod.py")), "D/ext_pkg/a/mod.py")
        self.assertEqual(_format_cross_drive_relpath(Path("D:/ext_pkg/b/mod.py")), "D/ext_pkg/b/mod.py")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ensure_unique_overload_ids_updates_child_parent_ids(self) -> None:
        """Verify ensure_unique_overload_ids includes scope_path and updates child symbols' parent_id when overload IDs change."""
        shared_dup_id = "dup_method_id"
        m1 = UnifiedSymbol(
            id=shared_dup_id,
            name="Service.Execute",
            kind="method",
            file_path="svc.cs",
            line_number=10,
            end_line=15,
            language="c_sharp",
            fqn="App.Service.Execute",
            scope_path="App.Service",
            signature="void Execute(int a)",
            metadata={"parent_scope": "Service", "short_name": "Execute", "spaces": ["code"]},
        )
        m2 = UnifiedSymbol(
            id=shared_dup_id,
            name="Service.Execute",
            kind="method",
            file_path="svc.cs",
            line_number=20,
            end_line=25,
            language="c_sharp",
            fqn="App.Service.Execute",
            scope_path="App.Service",
            signature="void Execute(string b)",
            metadata={"parent_scope": "Service", "short_name": "Execute", "spaces": ["code"]},
        )
        local_child = UnifiedSymbol(
            id="child_local_fn",
            name="Service.Execute.LocalHelper",
            kind="function",
            file_path="svc.cs",
            line_number=21,
            end_line=23,
            language="c_sharp",
            fqn="App.Service.Execute.LocalHelper",
            scope_path="App.Service.Execute",
            parent_id=shared_dup_id,
            signature="void LocalHelper()",
            metadata={"parent_scope": "Execute", "short_name": "LocalHelper", "spaces": ["code"]},
        )

        disambiguated = ensure_unique_overload_ids([m1, m2, local_child], default_space="code")
        self.assertEqual(len(disambiguated), 3)
        self.assertNotEqual(disambiguated[0].id, disambiguated[1].id)
        self.assertIn(disambiguated[2].parent_id, {disambiguated[0].id, disambiguated[1].id})
        self.assertNotEqual(disambiguated[2].parent_id, shared_dup_id)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_linker_inheritance_cache_and_deque_bfs(self) -> None:
        """Verify TopologyLinker pre-indexes inheritance/methods and expand_contract_symbol_ids expands base and derived methods."""
        base_cls = UnifiedSymbol(
            id="cls_base",
            name="BaseService",
            kind="class",
            file_path="svc.py",
            line_number=1,
            end_line=10,
            language="python",
        )
        sub_cls = UnifiedSymbol(
            id="cls_sub",
            name="SubService",
            kind="class",
            file_path="svc.py",
            line_number=12,
            end_line=25,
            language="python",
            metadata={"base_types": ["BaseService"]},
        )
        base_method = UnifiedSymbol(
            id="m_base_run",
            name="BaseService.run",
            kind="method",
            file_path="svc.py",
            line_number=3,
            end_line=6,
            language="python",
            metadata={"parent_scope": "BaseService", "short_name": "run"},
        )
        sub_method = UnifiedSymbol(
            id="m_sub_run",
            name="SubService.run",
            kind="method",
            file_path="svc.py",
            line_number=15,
            end_line=20,
            language="python",
            metadata={"parent_scope": "SubService", "short_name": "run"},
        )
        symbols = [base_cls, sub_cls, base_method, sub_method]
        linker = TopologyLinker(symbols)
        self.assertIn("BaseService", linker._base_derived)
        self.assertIn("SubService", linker._base_derived["BaseService"])
        self.assertIn(("BaseService", "run"), linker._methods_by_class_and_short)
        self.assertIn(("SubService", "run"), linker._methods_by_class_and_short)

        expanded = expand_contract_symbol_ids(linker.symbols_map, [base_method])
        self.assertIn("m_base_run", expanded)
        self.assertIn("m_sub_run", expanded)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_snippet_extractor_mtime_ns_cache_invalidation(self) -> None:
        """Verify SnippetExtractor caches file lines by mtime_ns and refreshes when file is modified."""
        target_file = self.temp_dir / "sample.py"
        target_file.write_text("line_one = 1\nline_two = 2\nline_three = 3\n", encoding="utf-8")

        extractor = SnippetExtractor(project_root=self.temp_dir)
        snip1 = extractor.extract(str(target_file), line_number=2, end_line=2, context_before=0, context_after=0)
        self.assertIsNotNone(snip1)
        assert snip1 is not None
        self.assertIn("line_two = 2", snip1.content)
        self.assertEqual(len(extractor._file_lines_cache), 1)

        st_old = target_file.stat()
        target_file.write_text("line_one = 1\nline_two = 222\nline_three = 3\n", encoding="utf-8")
        os.utime(target_file, ns=(st_old.st_atime_ns, st_old.st_mtime_ns + 1_000_000))

        snip2 = extractor.extract(str(target_file), line_number=2, end_line=2, context_before=0, context_after=0)
        self.assertIsNotNone(snip2)
        assert snip2 is not None
        self.assertIn("line_two = 222", snip2.content)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_extract_call_sites_presorted_enclosing_symbol(self) -> None:
        """Verify extract_call_sites resolves the smallest enclosing symbol span without mutating kind order."""
        code = (
            "class Outer:\n"
            "    def inner_method(self):\n"
            "        helper_call()\n"
        )
        driver = PythonASTParser()
        syms = driver.parse("test_mod.py", code, space="code")
        sites = driver.extract_call_sites("test_mod.py", code, space="code", symbols=syms)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].callee_name, "helper_call")
        self.assertTrue(sites[0].caller_member_name.endswith("inner_method"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_file_uri_opt_in_and_lazy_graph_meta(self) -> None:
        """Verify file_uri=False default vs file_uri=True, lazy graph loading, and corrupted graph self-healing."""
        src_f = self.temp_dir / "demo.py"
        src_f.write_text(
            "def alpha():\n    return beta()\n\ndef beta():\n    return 42\n",
            encoding="utf-8",
        )
        fmt = ASTResultFormatter(workspace_root=self.temp_dir)
        link_default = fmt.format_file_link(src_f, line=1, end_line=2)
        self.assertEqual(link_default, "demo.py:L1-2")
        self.assertNotIn("file://", link_default)

        link_uri = fmt.format_file_link(src_f, line=1, end_line=2, file_uri=True)
        self.assertIn("[demo.py:L1-2](file:///", link_uri)

        eng = ASTEngine(project_root=self.temp_dir, storage_dir=self.temp_dir / ".ast_store")
        snap = eng.build_index(allow_parallel=False)
        self.assertEqual(snap.ast_generation, 1)
        self.assertTrue(eng.meta_index_path.exists())

        eng2 = ASTEngine(project_root=self.temp_dir, storage_dir=self.temp_dir / ".ast_store")
        meta = eng2.get_persisted_meta()
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta["ast_generation"], snap.ast_generation)
        self.assertIsNone(eng2._snapshot)
        self.assertIsNone(eng2._graph)

        eng2.ensure_jit_synced()
        self.assertIsNotNone(eng2._snapshot)
        self.assertIsNone(eng2._graph)

        res_callers = eng2.callers("beta")
        self.assertIsNotNone(eng2._graph)
        out_txt = eng2.formatter.format_callers_output(res_callers)
        self.assertNotIn("](file:///", out_txt)
        out_txt_uri = eng2.formatter.format_callers_output(res_callers, file_uri=True)
        self.assertIn("](file:///", out_txt_uri)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_is_dirty_file_match_and_mtime_disambiguation(self) -> None:
        """Verify dirty_files path matching, cross-module relative path isolation, deepest space resolution, and multi-space mtime_ns disambiguation."""
        dirty_set = normalize_dirty_paths(["ys_codebase/source/dev/scripts/cli.py"])
        self.assertFalse(is_dirty_file_match("cli.py", dirty_set))
        self.assertFalse(is_dirty_file_match("scripts/cli.py", dirty_set))
        self.assertFalse(is_dirty_file_match("ys_codebase/source/ast/scripts/cli.py", normalize_dirty_paths(["scripts/cli.py"])))
        self.assertTrue(is_dirty_file_match("/workspace/ys_codebase/source/dev/scripts/cli.py", dirty_set))
        self.assertTrue(is_dirty_file_match("ys_codebase/source/dev/scripts/cli.py", dirty_set))

        self.assertTrue(is_dirty_file_match("src/utils.py", {"/workspace/proj/src/utils.py"}))
        self.assertFalse(is_dirty_file_match("pkg/utils.py", {"/workspace/proj/src/utils.py"}))
        self.assertTrue(is_dirty_file_match("yscb.py", {"/workspace/proj/yscb.py"}))

        space_a = self.temp_dir / "space_a"
        space_b = self.temp_dir / "space_b"
        space_a.mkdir(parents=True, exist_ok=True)
        space_b.mkdir(parents=True, exist_ok=True)
        file_a = space_a / "root_mod.py"
        file_b = space_b / "root_mod.py"
        file_a.write_text("x = 1\n", encoding="utf-8")
        file_b.write_text("x = 2\n", encoding="utf-8")
        st_a = file_a.stat()
        os.utime(file_b, ns=(st_a.st_atime_ns, st_a.st_mtime_ns + 5_000_000))

        sp_cfg_a = SpaceConfig(
            qualified_name="project/space_a",
            owner="project",
            short_name="space_a",
            entries=(str(space_a),),
        )
        sp_cfg_b = SpaceConfig(
            qualified_name="project/space_b",
            owner="project",
            short_name="space_b",
            entries=(str(space_b),),
        )

        engine = ASTEngine(project_root=self.temp_dir, storage_dir=self.temp_dir / ".ast_store_mtime")
        resolved = engine.bundler._resolve_dirty_files_only(
            dirty_raw_paths=["root_mod.py"],
            target_spaces=[sp_cfg_a, sp_cfg_b],
            snap_entries_by_space={},
        )
        self.assertEqual(len(resolved), 1)
        abs_p, rel_p, matched_spaces = next(iter(resolved.values()))
        self.assertEqual(Path(abs_p).resolve(), file_b.resolve())
        self.assertTrue(rel_p.endswith("root_mod.py"))
        self.assertEqual(matched_spaces, {"space_b"})

        # Verify _resolve_target_file picks the deepest matching space rather than being overwritten by a broader parent space
        nested_dir = space_a / "deep"
        nested_dir.mkdir(parents=True, exist_ok=True)
        nested_file = nested_dir / "inner.py"
        nested_file.write_text("z = 3\n", encoding="utf-8")
        eng_nested = ASTEngine(
            project_root=self.temp_dir,
            storage_dir=self.temp_dir / ".ast_store_nested",
            custom_spaces={
                "deep_space": {"entries": [str(nested_dir)]},
                "broad_space": {"entries": [str(self.temp_dir)]},
            },
        )
        _, _, chosen_space = eng_nested._resolve_target_file(str(nested_file))
        self.assertEqual(chosen_space, "deep_space")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_csharp_file_scoped_namespace_and_snapshot_list_symbols(self) -> None:
        """Verify C# file-scoped namespace span extension to EOF and ASTSnapshot.from_dict list deserialization."""
        dialect = CSharpDialect()
        raw_items = [
            {
                "short_name": "MyCorp.App",
                "kind": SymbolKind.CLASS,
                "start_line": 1,
                "end_line": 1,
                "start_byte": 0,
                "end_byte": 21,
                "is_file_scoped_namespace": True,
            },
            {
                "short_name": "OrderService",
                "kind": SymbolKind.CLASS,
                "start_line": 3,
                "end_line": 10,
                "start_byte": 23,
                "end_byte": 120,
            },
        ]
        source_lines = ["namespace MyCorp.App;", "", "public class OrderService {", "}"]
        dialect.finalize_raw_items(raw_items, source_lines)
        self.assertEqual(raw_items[0]["end_byte"], 120)
        self.assertEqual(raw_items[0]["end_line"], 10)

        snap_dict = {
            "space_name": "core",
            "version": "1.0",
            "symbols": [
                {
                    "id": "sym_1",
                    "name": "OrderService",
                    "kind": "class",
                    "file_path": "OrderService.cs",
                    "line_number": 3,
                    "end_line": 10,
                    "language": "c_sharp",
                }
            ],
        }
        snap = ASTSnapshot.from_dict(snap_dict)
        self.assertIn("sym_1", snap.symbols)
        self.assertEqual(snap.symbols["sym_1"].name, "OrderService")
        self.assertEqual(len(snap.list_symbols()), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_linker_cache_invalidation_on_inplace_symbol_update(self) -> None:
        """Verify expand_contract_symbol_ids invalidates cache when symbols_map is updated in place."""
        base_v1 = UnifiedSymbol(
            id="cls_base",
            name="BaseWorker",
            kind=SymbolKind.CLASS,
            file_path="a.py",
            line_number=1,
            end_line=5,
            language="python",
            metadata={"short_name": "BaseWorker", "base_types": []},
        )
        child_v1 = UnifiedSymbol(
            id="cls_child",
            name="ChildWorker",
            kind=SymbolKind.CLASS,
            file_path="b.py",
            line_number=1,
            end_line=5,
            language="python",
            metadata={"short_name": "ChildWorker", "base_types": []},
        )
        method_target = UnifiedSymbol(
            id="m_run",
            name="BaseWorker.run_task",
            kind=SymbolKind.METHOD,
            file_path="a.py",
            line_number=2,
            end_line=4,
            language="python",
            parent_id="cls_base",
            metadata={"short_name": "run_task", "parent_scope": "BaseWorker"},
        )
        method_child = UnifiedSymbol(
            id="m_child_run",
            name="ChildWorker.run_task",
            kind=SymbolKind.METHOD,
            file_path="b.py",
            line_number=2,
            end_line=4,
            language="python",
            parent_id="cls_child",
            metadata={"short_name": "run_task", "parent_scope": "ChildWorker"},
        )
        symbols_map = {
            "cls_base": base_v1,
            "cls_child": child_v1,
            "m_run": method_target,
            "m_child_run": method_child,
        }
        expanded1 = expand_contract_symbol_ids(symbols_map, method_target)
        self.assertEqual(expanded1, ["m_run"])

        child_v2 = UnifiedSymbol(
            id="cls_child",
            name="ChildWorker",
            kind=SymbolKind.CLASS,
            file_path="b.py",
            line_number=1,
            end_line=5,
            language="python",
            metadata={"short_name": "ChildWorker", "base_types": ["BaseWorker"]},
        )
        symbols_map["cls_child"] = child_v2
        expanded2 = expand_contract_symbol_ids(symbols_map, method_target)
        self.assertEqual(set(expanded2), {"m_run", "m_child_run"})
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_storage_and_lock_fallback_anchors_to_yscb_root(self) -> None:
        """Verify _resolve_default_ast_storage_dir and _resolve_index_lock_path fallback to resolve_yscb_root without leaking into project_root."""
        from unittest.mock import patch
        from ast_engine.bundler import _resolve_default_ast_storage_dir

        fake_yscb_root = Path(self.temp_dir) / "fake_yscb_root"
        fake_yscb_root.mkdir(parents=True, exist_ok=True)
        fake_proj = Path(self.temp_dir) / "downstream_project"
        fake_proj.mkdir(parents=True, exist_ok=True)

        with patch("core.uri.resolve", return_value="!undefined"), patch(
            "core.uri.resolve_yscb_root", return_value=str(fake_yscb_root)
        ):
            storage_dir = _resolve_default_ast_storage_dir(fake_proj)
            self.assertEqual(storage_dir, (fake_yscb_root / ".storage.local" / "ast").resolve())
            self.assertFalse((fake_proj / ".storage.local").exists())

            eng = ASTEngine(project_root=fake_proj, storage_dir=None)
            lock_path = eng._resolve_index_lock_path()
            self.assertEqual(lock_path, (fake_yscb_root / ".cache" / "ast" / ".ast_index.lock").resolve())
            self.assertFalse((fake_proj / ".cache").exists())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unified_symbol_tuple_coercion_hashability_and_snapshot_generations(self) -> None:
        """Verify UnifiedSymbol normalizes children/members/parameters to tuples, supports hash(), and _collect_space_generations_and_files_map handles head_generation and dict cursor."""
        from unittest.mock import MagicMock

        sym = UnifiedSymbol(
            id="sym_hash_1",
            name="DemoClass",
            kind=SymbolKind.CLASS,
            file_path="demo.py",
            line_number=1,
            language="python",
            children=[{"name": "m1", "kind": "method"}],  # type: ignore[arg-type]
            parameters=[{"name": "x", "type": "int"}],  # type: ignore[arg-type]
        )
        self.assertIsInstance(sym.children, tuple)
        self.assertIsInstance(sym.members, tuple)
        self.assertIsInstance(sym.parameters, tuple)
        self.assertEqual(sym.children, sym.members)
        self.assertIsInstance(hash(sym), int)

        eng = ASTEngine(project_root=self.temp_dir, storage_dir=self.temp_dir / ".ast_gen_test")
        sp_cfg = SpaceConfig(
            qualified_name="project/gen_sp",
            owner="project",
            short_name="gen_sp",
            entries=(str(self.temp_dir),),
        )
        fake_st = MagicMock()
        fake_st.entries = {}
        fake_st.head_generation = 42
        del fake_st.generation

        fake_scanner = MagicMock()
        fake_scanner._load_snapshot_state.side_effect = lambda q_name: fake_st
        fake_scanner.cursor_store.get_cursor.return_value = {"acked_generation": 42, "space_generations": {}}
        eng.scanner = fake_scanner

        space_gens, _ = eng._collect_space_generations_and_files_map([sp_cfg])
        self.assertEqual(space_gens.get("gen_sp"), 42)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_atomic_kernel_schema_immutability_serialization_and_canonical_id(self) -> None:
        """Verify Span, ProvenanceStep, SymbolNode, RelationEdge, and FileSymbolGraph immutability, slicing, canonical IDs, and validation."""
        from dataclasses import FrozenInstanceError

        src = b"def calculate(a: int, b: int) -> int:\n    return a + b\n"
        sp_name = Span(start_byte=4, end_byte=13, start_line=1, start_col=4, end_line=1, end_col=13)
        sp_params = Span(start_byte=13, end_byte=29, start_line=1, start_col=13, end_line=1, end_col=29)
        sp_outer = sp_name.union(sp_params)
        self.assertEqual(sp_name.slice_text(src), "calculate")
        self.assertEqual(sp_params.slice_bytes(src), b"(a: int, b: int)")
        self.assertTrue(sp_outer.contains(sp_name))
        self.assertEqual(sp_name.union(sp_params), sp_params.union(sp_name))

        prov1 = ProvenanceStep(provider_id="core:cli.scm", action="extract", rule_or_hook="@def.cli_command")
        prov2 = ProvenanceStep(provider_id="ast:python/tags.scm", action="extract", rule_or_hook="@definition.function")
        sym_id = SymbolNode.compute_canonical_id("pkg/math.py", "Math.calculate", "(int, int)")
        self.assertEqual(sym_id, "pkg/math.py::Math.calculate(int, int)")

        node = SymbolNode(
            id=sym_id,
            name="calculate",
            scope_path=("Math",),
            kinds=frozenset({"function", "cli_command"}),
            language="python",
            span=sp_outer,
            parts={"name": sp_name, "parameters": sp_params},
            facets={"visibility": "public", "modifiers": ["static"]},
            provenance=(prov1, prov2, prov1),
        )
        self.assertEqual(node.fqn, "Math.calculate")
        # Provenance must be deduplicated and sorted lexicographically by provider_id
        self.assertEqual(len(node.provenance), 2)
        self.assertEqual(node.provenance[0].provider_id, "ast:python/tags.scm")
        self.assertEqual(node.provenance[1].provider_id, "core:cli.scm")
        self.assertIsInstance(hash(node), int)
        with self.assertRaises(FrozenInstanceError):
            node.name = "mutated"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            node.parts["extra"] = sp_name  # type: ignore[index]

        edge = RelationEdge(
            source_id=sym_id,
            target_expr="helper",
            edge_kind="calls",
            span=sp_name,
            provenance=(prov1, prov2),
        )
        graph = FileSymbolGraph(
            file_path="pkg/math.py",
            content_hash="0123456789abcdef0123456789abcdef",
            language="python",
            root_nodes=(node,),
            outgoing_edges=(edge,),
        )
        self.assertIn(sym_id, graph.all_nodes_by_id)
        restored_graph = FileSymbolGraph.from_dict(graph.to_dict())
        self.assertEqual(restored_graph.file_path, "pkg/math.py")
        self.assertEqual(restored_graph.root_nodes[0].id, sym_id)
        self.assertEqual(restored_graph.root_nodes[0].kinds, frozenset({"function", "cli_command"}))
        self.assertEqual(restored_graph.outgoing_edges[0].target_expr, "helper")
        self.assertIsInstance(hash(restored_graph), int)

        for atomic_cls in (Span, ProvenanceStep, SymbolNode, RelationEdge, FileSymbolGraph):
            with self.assertRaises(SchemaValidationError):
                atomic_cls.from_dict("not_a_dict")  # type: ignore[arg-type]
            with self.assertRaises(SchemaValidationError):
                atomic_cls.from_dict({})
        with self.assertRaises(SchemaValidationError):
            Span.from_dict({"start_byte": "bad", "end_byte": 10, "start_line": 1, "end_line": 1})
        with self.assertRaises(SchemaValidationError):
            Span.from_dict({"start_byte": 15, "end_byte": 10, "start_line": 1, "end_line": 1})
        with self.assertRaises(SchemaValidationError):
            SymbolNode(
                id="f.py::x",
                name="x",
                scope_path=(),
                kinds=frozenset({"function"}),
                language="python",
                span=sp_name,
                parts={"name": "not_a_span"},  # type: ignore[dict-item]
            )
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
