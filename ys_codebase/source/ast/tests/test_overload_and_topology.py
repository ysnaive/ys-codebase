"""
Subsystem tests for method overload preservation (`ast_engine.bundler`, `ast_engine.linker`),
deterministic symbol resolution (`ast_engine.resolver`), and bidirectional call graph queries (`ast_engine.graph`).
"""

from pathlib import Path
import shutil
import sys
import tempfile

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from ast_engine.bundler import aggregate_partial_symbols, ensure_unique_overload_ids
from ast_engine.exceptions import ASTIndexNotFoundError
from ast_engine.formatter import ASTResultFormatter
from ast_engine.graph import CallGraphIndex
from ast_engine.linker import TopologyLinker
from ast_engine.parsers import ParserRegistry
from ast_engine.resolver import (
    DeterministicSymbolResolver,
    SnippetExtractor,
    SymbolSelector,
    extract_signature_params,
    query_callees,
    query_callers,
    query_impact,
)
from ast_engine.schema import ASTSnapshot, SymbolCallSite, UnifiedSymbol
from tests import ASTTestCase, Requirement, require


class TestOverloadAndTopology(ASTTestCase):
    """Tests for same-type method overloads, cross-type homonym ambiguity, parameter filtering, and topology traversal."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_overload_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"

    def tearDown(self) -> None:
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def _build_csharp_overload_fixture(self):
        registry = ParserRegistry(register_defaults=True)
        ui_win_code = (
            "namespace UI {\n"
            "    public partial class Window {\n"
            "        public void Open(string title) {\n"
            "            InitCore();\n"
            "        }\n"
            "        public void Open(string title, int width, int height) {\n"
            "            Open(title);\n"
            "            Resize(width, height);\n"
            "        }\n"
            "        private void InitCore() {}\n"
            "        private void Resize(int w, int h) {}\n"
            "    }\n"
            "    public class AppController {\n"
            "        private Window _win;\n"
            "        public void Launch() {\n"
            "            _win.Open(\"Main\", 800, 600);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        io_file_code = (
            "namespace IO {\n"
            "    public class File {\n"
            "        public void Open(string path) {}\n"
            "    }\n"
            "}\n"
        )
        syms_ui = registry.parse_file("UI/Window.cs", ui_win_code, space="code")
        syms_io = registry.parse_file("IO/File.cs", io_file_code, space="code")
        all_syms = ensure_unique_overload_ids(syms_ui + syms_io)
        for s in all_syms:
            s.metadata["spaces"] = ["code"]
        all_syms = aggregate_partial_symbols(all_syms)

        calls_ui = registry.extract_call_sites("UI/Window.cs", ui_win_code, space="code", symbols=syms_ui)
        calls_io = registry.extract_call_sites("IO/File.cs", io_file_code, space="code", symbols=syms_io)
        imports_map = {
            "UI/Window.cs": registry.extract_imports("UI/Window.cs", ui_win_code),
            "IO/File.cs": registry.extract_imports("IO/File.cs", io_file_code),
        }

        linker = TopologyLinker(all_syms, file_imports=imports_map)
        graph = CallGraphIndex()
        for cs in calls_ui + calls_io:
            resolved_id = linker.resolve_call_site(cs)
            if cs.caller_symbol_id and resolved_id and resolved_id != cs.caller_symbol_id:
                graph.add_edge(cs.caller_symbol_id, resolved_id, cs)

        snapshot = ASTSnapshot(
            symbols=all_syms,
            ast_generation=1,
        )
        return snapshot, linker, graph

    @require(Requirement.LOGIC)
    def test_linker_preserves_all_overloads_in_by_fqn(self) -> None:
        """Verify TopologyLinker._by_fqn stores List[UnifiedSymbol] and retains all C# method overloads."""
        _, linker, _ = self._build_csharp_overload_fixture()
        overloads = linker.get_overloads_by_fqn("UI.Window.Open")
        self.assertEqual(len(overloads), 2)
        overload_ids = {s.id for s in overloads}
        self.assertEqual(len(overload_ids), 2)
        sigs = [s.signature for s in overloads]
        self.assertTrue(any("string title)" in sig for sig in sigs))
        self.assertTrue(any("int width" in sig for sig in sigs))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_resolver_overload_group_vs_parameter_filtered_match(self) -> None:
        """Verify DeterministicSymbolResolver groups same-parent overloads as overload_group and filters by parameter types."""
        snapshot, _, graph = self._build_csharp_overload_fixture()
        resolver = DeterministicSymbolResolver(snapshot)

        res_group = resolver.resolve("Window.Open")
        self.assertEqual(res_group.status, "overload_group")
        self.assertEqual(len(res_group.targets), 2)
        self.assertEqual(len(res_group.overloads), 2)

        res_one_param = resolver.resolve("Window.Open(string)")
        self.assertEqual(res_one_param.status, "matched")
        self.assertEqual(len(res_one_param.targets), 1)
        self.assertIn("string title)", res_one_param.targets[0].signature)
        self.assertNotIn("int width", res_one_param.targets[0].signature)

        res_three_params = resolver.resolve("Window.Open(string, int, int)")
        self.assertEqual(res_three_params.status, "matched")
        self.assertEqual(len(res_three_params.targets), 1)
        self.assertIn("int width", res_three_params.targets[0].signature)

        callees_res = query_callees("Window.Open", snapshot, graph)
        self.assertFalse(callees_res.get("ambiguous"))
        self.assertEqual(callees_res.get("resolution_status"), "overload_group")
        self.assertEqual(len(callees_res.get("overloads", [])), 2)
        callee_names = {c["name"].split(".")[-1] for c in callees_res.get("callees", [])}
        self.assertIn("InitCore", callee_names)
        self.assertIn("Resize", callee_names)

        callers_res = query_callers("Window.Open", snapshot, graph)
        caller_names = {c["name"].split(".")[-1] for c in callers_res.get("callers", [])}
        self.assertIn("Launch", caller_names)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_signature_params_generic_commas_and_zero_arg_disambiguation(self) -> None:
        """Verify extract_signature_params handles return-type parens and self: Self, and SymbolSelector disambiguates 0-arg overloads."""
        params_ret_paren = extract_signature_params(
            "def transform(self: Self, items: Dict[str, Tuple[int, str]], flag: bool = True) -> Tuple[int, (str, bool)]"
        )
        self.assertEqual(params_ret_paren, ["items: Dict[str, Tuple[int, str]]", "flag: bool = True"])

        sel_generic = SymbolSelector.parse("fn Map.Get(Dictionary<string, int>, int)")
        self.assertEqual(sel_generic.identifier, "Get")
        self.assertEqual(sel_generic.scope, "Map")
        self.assertEqual(sel_generic.param_types, ("Dictionary<string, int>", "int"))

        sel_zero = SymbolSelector.parse("Window.Open()")
        self.assertTrue(sel_zero.is_callable)
        sel_any = SymbolSelector.parse("Window.Open")
        self.assertIsNone(sel_any.param_types)

        sym_zero = UnifiedSymbol(
            id="win_open_0",
            name="Window.Open",
            kind="method",
            file_path="UI/Window.cs",
            line_number=5,
            end_line=6,
            language="c_sharp",
            fqn="UI.Window.Open",
            signature="public void Open()",
            metadata={"parent_scope": "Window", "short_name": "Open"},
        )
        sym_one = UnifiedSymbol(
            id="win_open_1",
            name="Window.Open",
            kind="method",
            file_path="UI/Window.cs",
            line_number=8,
            end_line=10,
            language="c_sharp",
            fqn="UI.Window.Open",
            signature="public void Open(string title)",
            metadata={"parent_scope": "Window", "short_name": "Open"},
        )
        resolver = DeterministicSymbolResolver(ASTSnapshot(symbols=[sym_zero, sym_one]))
        res_0 = resolver.resolve("Window.Open()")
        self.assertEqual(res_0.status, "matched")
        self.assertEqual(len(res_0.targets), 1)
        self.assertEqual(res_0.targets[0].id, "win_open_0")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_resolver_cross_type_homonym_returns_ambiguous_candidates(self) -> None:
        """Verify querying bare 'Open' across UI.Window.Open and IO.File.Open returns status='ambiguous' with 3 candidates."""
        snapshot, _, graph = self._build_csharp_overload_fixture()
        resolver = DeterministicSymbolResolver(snapshot)

        res_ambig = resolver.resolve("Open")
        self.assertEqual(res_ambig.status, "ambiguous")
        self.assertEqual(res_ambig.targets, [])
        self.assertEqual(len(res_ambig.candidates), 3)
        candidate_fqns = {c["fqn"] for c in res_ambig.candidates}
        self.assertIn("UI.Window.Open", candidate_fqns)
        self.assertIn("IO.File.Open", candidate_fqns)

        callers_ambig = query_callers("Open", snapshot, graph)
        self.assertTrue(callers_ambig.get("ambiguous"))
        self.assertEqual(callers_ambig.get("resolution_status"), "ambiguous")
        self.assertEqual(len(callers_ambig.get("candidates", [])), 3)

        impact_ambig = query_impact("Open", snapshot, graph, max_depth=2)
        self.assertTrue(impact_ambig.get("ambiguous"))
        self.assertEqual(len(impact_ambig.get("candidates", [])), 3)

        formatted_ambig = ASTResultFormatter().format_callers_output(callers_ambig)
        self.assertIn("Ambiguous symbol", formatted_ambig)
        self.assertIn("UI.Window.Open", formatted_ambig)
        self.assertIn("IO.File.Open", formatted_ambig)

        res_missing = resolver.resolve("NonExistentSymbolXYZ")
        self.assertEqual(res_missing.status, "not_found")
        self.assertEqual(res_missing.targets, [])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_deleted_file_orphan_node_eviction_and_binary_roundtrip(self) -> None:
        """Verify CallGraphIndex binary persistence roundtrip, orphan node eviction, SnippetExtractor FIFO eviction, and 4-tier linking."""
        snapshot, _, graph = self._build_csharp_overload_fixture()
        resolver = DeterministicSymbolResolver(snapshot)
        self.assertIn("open", resolver._by_ident_lower)
        self.assertEqual(len(resolver._by_ident_lower["open"]), 3)

        orphan_id = "code:OrphanFile.cs:OrphanFunc"
        graph.add_edge(orphan_id, snapshot.symbols[next(iter(snapshot.symbols))].id)
        self.assertTrue(graph.graph.has_node(orphan_id))
        graph.patch_incremental(new_edges=[], old_symbol_ids={orphan_id})
        self.assertFalse(graph.graph.has_node(orphan_id))

        # Binary save/load roundtrip
        bin_path = self.temp_dir / "graph.bin.gz"
        graph.save_binary(bin_path)
        loaded_graph = CallGraphIndex.load_binary(bin_path)
        self.assertEqual(loaded_graph.graph.number_of_edges(), graph.graph.number_of_edges())

        with self.assertRaises(ASTIndexNotFoundError):
            CallGraphIndex.load_binary(self.temp_dir / "missing_graph.bin.gz")

        # SnippetExtractor 32-file FIFO cache eviction
        extractor = SnippetExtractor(project_root=self.temp_dir)
        for i in range(36):
            f_p = self.temp_dir / f"mod_{i}.py"
            f_p.write_text(f"val = {i}\n", encoding="utf-8")
            extractor.extract(str(f_p), line_number=1, end_line=1)
        self.assertLessEqual(len(extractor._file_lines_cache), 32)

        # 4-Tier TopologyLinker disambiguation (Tier 0 self/base, Tier 1 same-file, Tier 2 import alias, Tier 3 space-unique)
        s_base = UnifiedSymbol(
            id="s_base", name="Base.Init", kind="method", file_path="base.py", line_number=1, language="python",
            fqn="Base.Init", metadata={"parent_scope": "Base", "short_name": "Init", "spaces": ["code"]},
        )
        s_sub_cls = UnifiedSymbol(
            id="s_sub_cls", name="Sub", kind="class", file_path="sub.py", line_number=1, language="python",
            fqn="Sub", metadata={"short_name": "Sub", "base_types": ["Base"], "spaces": ["code"]},
        )
        s_sub_run = UnifiedSymbol(
            id="s_sub_run", name="Sub.Run", kind="method", file_path="sub.py", line_number=2, language="python",
            fqn="Sub.Run", parent_id="s_sub_cls", metadata={"parent_scope": "Sub", "short_name": "Run", "spaces": ["code"]},
        )
        s_ext = UnifiedSymbol(
            id="s_ext", name="compute", kind="function", file_path="pkg/math_utils.py", line_number=1, language="python",
            fqn="pkg.math_utils.compute", metadata={"short_name": "compute", "spaces": ["code"]},
        )
        linker4 = TopologyLinker(
            [s_base, s_sub_cls, s_sub_run, s_ext],
            file_imports={"sub.py": {"calc_alias": "pkg.math_utils.compute"}},
        )
        self.assertEqual(
            linker4.resolve_call_site(
                SymbolCallSite(callee_name="Init", line_number=3, caller_symbol_id="s_sub_run", context_prefix="base", file_path="sub.py", space="code")
            ),
            "s_base",
        )
        self.assertEqual(
            linker4.resolve_call_site(
                SymbolCallSite(callee_name="calc_alias", line_number=4, caller_symbol_id="s_sub_run", file_path="sub.py", space="code")
            ),
            "s_ext",
        )
        self.mark_passed()
