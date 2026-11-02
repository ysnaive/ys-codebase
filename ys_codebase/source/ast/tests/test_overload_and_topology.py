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

from ast_engine.bundler import aggregate_partial_symbols, ensure_unique_overload_ids
from ast_engine.engine import ASTEngine
from ast_engine.formatter import ASTResultFormatter
from ast_engine.graph import CallGraphIndex
from ast_engine.linker import TopologyLinker
from ast_engine.parsers import ParserRegistry
from ast_engine.resolver import (
    DeterministicSymbolResolver,
    SymbolSelector,
    query_callees,
    query_callers,
    query_impact,
)
from ast_engine.schema import ASTSnapshot
from dev.testing import Requirement, YSCBTestCase, require


class TestOverloadAndTopology(YSCBTestCase):
    """Tests for same-type method overloads, cross-type homonym ambiguity, parameter filtering, and topology traversal."""

    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_overload_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"

    def tearDown(self):
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
    def test_ft_01_linker_preserves_all_overloads_in_by_fqn(self):
        """FT-01: Verify TopologyLinker._by_fqn stores List[UnifiedSymbol] and retains all C# method overloads."""
        snapshot, linker, _ = self._build_csharp_overload_fixture()
        overloads = linker.get_overloads_by_fqn("UI.Window.Open")
        self.assertEqual(len(overloads), 2)
        overload_ids = {s.id for s in overloads}
        self.assertEqual(len(overload_ids), 2)
        sigs = [s.signature for s in overloads]
        self.assertTrue(any("string title)" in sig for sig in sigs))
        self.assertTrue(any("int width" in sig for sig in sigs))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_resolver_overload_group_vs_parameter_filtered_match(self):
        """FT-02: Verify DeterministicSymbolResolver groups same-parent overloads as overload_group and filters by parameter types."""
        snapshot, _, graph = self._build_csharp_overload_fixture()
        resolver = DeterministicSymbolResolver(snapshot)

        # Unqualified by parameter list -> hits both overloads under UI.Window -> status == "overload_group"
        res_group = resolver.resolve("Window.Open")
        self.assertEqual(res_group.status, "overload_group")
        self.assertEqual(len(res_group.targets), 2)
        self.assertEqual(len(res_group.overloads), 2)

        # Filtered by 1 parameter `(string)` -> narrows down to single overload -> status == "matched"
        res_one_param = resolver.resolve("Window.Open(string)")
        self.assertEqual(res_one_param.status, "matched")
        self.assertEqual(len(res_one_param.targets), 1)
        self.assertIn("string title)", res_one_param.targets[0].signature)
        self.assertNotIn("int width", res_one_param.targets[0].signature)

        # Filtered by 3 parameters `(string, int, int)` -> narrows down to 3-arg overload -> status == "matched"
        res_three_params = resolver.resolve("Window.Open(string, int, int)")
        self.assertEqual(res_three_params.status, "matched")
        self.assertEqual(len(res_three_params.targets), 1)
        self.assertIn("int width", res_three_params.targets[0].signature)

        # Topology query on overload_group unions callers/callees across all overloads and includes overloads metadata
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
    def test_et_01_resolver_cross_type_homonym_returns_ambiguous_candidates(self):
        """ET-01: Verify querying bare 'Open' across UI.Window.Open and IO.File.Open returns status='ambiguous' with structured candidates."""
        snapshot, _, graph = self._build_csharp_overload_fixture()
        resolver = DeterministicSymbolResolver(snapshot)

        res_ambig = resolver.resolve("Open")
        self.assertEqual(res_ambig.status, "ambiguous")
        self.assertEqual(res_ambig.targets, [])
        self.assertTrue(len(res_ambig.candidates) >= 3)
        candidate_fqns = {c["fqn"] for c in res_ambig.candidates}
        self.assertIn("UI.Window.Open", candidate_fqns)
        self.assertIn("IO.File.Open", candidate_fqns)

        # query_callers / query_impact on ambiguous symbol returns structured candidates without crashing
        callers_ambig = query_callers("Open", snapshot, graph)
        self.assertTrue(callers_ambig.get("ambiguous"))
        self.assertEqual(callers_ambig.get("resolution_status"), "ambiguous")
        self.assertTrue(len(callers_ambig.get("candidates", [])) >= 3)

        impact_ambig = query_impact("Open", snapshot, graph, max_depth=2)
        self.assertTrue(impact_ambig.get("ambiguous"))
        self.assertTrue(len(impact_ambig.get("candidates", [])) >= 3)

        # Formatter renders disambiguation candidates clearly
        formatted_ambig = ASTResultFormatter().format_callers_output(callers_ambig)
        self.assertIn("Ambiguous symbol", formatted_ambig)
        self.assertIn("UI.Window.Open", formatted_ambig)
        self.assertIn("IO.File.Open", formatted_ambig)

        # Non-existent symbol returns status="not_found"
        res_missing = resolver.resolve("NonExistentSymbolXYZ")
        self.assertEqual(res_missing.status, "not_found")
        self.assertEqual(res_missing.targets, [])
        self.mark_passed()
