"""
Unit and edge-case tests for the 4-Pass Deterministic Workspace Graph Linker (`linker.py`),
`WorkspaceSymbolGraph` / `FileImportTable` / `FileImportBinding` contracts (`schema.py`),
and language plugin protocols `ModulePathResolver` & `EdgeRefiner` (`parsers/base.py`, `parsers/registry.py`).
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import sys
import tempfile
from types import MappingProxyType
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from ast_engine.exceptions import SchemaValidationError
from ast_engine.linker import DefaultModulePathResolver, WorkspaceGraphLinker, expand_contract_symbol_ids
from ast_engine.parsers.base import EdgeRefiner, ModulePathResolver
from ast_engine.parsers.registry import ParserRegistry
from ast_engine.schema import (
    FileImportBinding,
    FileImportTable,
    FileSymbolGraph,
    ProvenanceStep,
    RelationEdge,
    Span,
    SymbolNode,
    WorkspaceSymbolGraph,
)
from tests import ASTTestCase, Requirement, require


class _CustomEventBusRefiner(EdgeRefiner):
    """Test-only peer EdgeRefiner resolving EventBus.publish_sync to on_sync handler."""

    provider_id = "test:event_bus_refiner"

    def refine_workspace_edges(
        self,
        edges: Tuple[RelationEdge, ...],
        nodes_by_id: Mapping[str, SymbolNode],
        file_import_tables: Mapping[str, FileImportTable],
    ) -> Tuple[RelationEdge, ...]:
        on_sync_ids = tuple(sorted(nid for nid, n in nodes_by_id.items() if n.name == "on_sync"))
        refined: List[RelationEdge] = []
        for edge in edges:
            if edge.target_expr.endswith("publish_sync") and on_sync_ids:
                refined.append(
                    RelationEdge(
                        source_id=edge.source_id,
                        target_expr=edge.target_expr,
                        edge_kind=edge.edge_kind,
                        span=edge.span,
                        resolution_status="resolved",
                        resolved_target_ids=on_sync_ids,
                        provenance=(
                            *edge.provenance,
                            ProvenanceStep(
                                provider_id=self.provider_id,
                                action="refine",
                                rule_or_hook="Peer_EdgeRefiner:event_bus_handler",
                                detail=f"Matched {edge.target_expr} -> {on_sync_ids[0]}",
                            ),
                        ),
                    )
                )
            else:
                refined.append(edge)
        return tuple(refined)


class _CustomPrefixModuleResolver(ModulePathResolver):
    """Test-only ModulePathResolver resolving `@app/<name>.<sym>` to `src/<name>.py`."""

    provider_id = "test:prefix_module_resolver"

    def resolve_import(
        self,
        importing_file: str,
        target_expr: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]:
        if target_expr.startswith("@app/"):
            rest = target_expr[len("@app/"):]
            if "." in rest:
                mod_name, sym_name = rest.split(".", 1)
            else:
                mod_name, sym_name = rest, ""
            candidate = f"src/{mod_name}.py"
            if candidate in workspace_files:
                sids = tuple(
                    n.id for n in nodes_by_file.get(candidate, ()) if not sym_name or n.name == sym_name
                )
                return candidate, sids, False
        return DefaultModulePathResolver().resolve_import(
            importing_file=importing_file,
            target_expr=target_expr,
            workspace_files=workspace_files,
            nodes_by_file=nodes_by_file,
        )


class TestDeterministicLinker(ASTTestCase):
    """Comprehensive tests for `WorkspaceGraphLinker` 4-pass linking and symbol folding."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_linker_test_"))
        self.registry = ParserRegistry()

    def tearDown(self) -> None:
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def _parse_virtual_files(self, files: Dict[str, str]) -> List[FileSymbolGraph]:
        graphs: List[FileSymbolGraph] = []
        for rel_path, content in sorted(files.items()):
            fg = self.registry.extract_file_graph(rel_path, content)
            graphs.append(fg)
        return graphs

    def _link_graphs(
        self,
        file_graphs: List[FileSymbolGraph],
        registry: Optional[ParserRegistry] = None,
    ) -> WorkspaceSymbolGraph:
        reg = registry or self.registry
        linker = WorkspaceGraphLinker(
            file_graphs=file_graphs,
            language_configs=reg.language_configs,
            module_resolvers=reg.module_resolvers,
            edge_refiners=reg.edge_refiners,
        )
        return linker.link_workspace()

    @require(Requirement.LOGIC)
    def test_workspace_symbol_graph_and_import_table_contracts(self) -> None:
        """Verify FileImportBinding, FileImportTable, WorkspaceSymbolGraph immutability, serialization, and negative validation."""
        binding = FileImportBinding(
            local_alias="BaseRunner",
            target_expr="pkg.base.BaseRunner",
            resolved_file_path="pkg/base.py",
            resolved_symbol_ids=("pkg/base.py::BaseRunner",),
            is_wildcard=False,
            is_external=False,
            is_reexport=False,
        )
        with self.assertRaises(FrozenInstanceError):
            binding.local_alias = "Mutated"  # type: ignore[misc]

        table = FileImportTable(
            file_path="pkg/sub.py",
            bindings={"BaseRunner": binding},
            exported_symbols=frozenset({"BaseRunner"}),
        )
        self.assertIsInstance(table.bindings, MappingProxyType)
        with self.assertRaises(TypeError):
            table.bindings["New"] = binding  # type: ignore[index]

        table_rt = FileImportTable.from_dict(table.to_dict())
        self.assertEqual(table_rt.file_path, "pkg/sub.py")
        self.assertEqual(table_rt.bindings["BaseRunner"].resolved_symbol_ids, ("pkg/base.py::BaseRunner",))
        self.assertEqual(table_rt.exported_symbols, frozenset({"BaseRunner"}))

        node = SymbolNode(
            id="pkg/base.py::BaseRunner",
            name="BaseRunner",
            scope_path=(),
            kinds=frozenset({"class"}),
            language="python",
            span=Span(0, 100, 1, 0, 10, 0),
        )
        edge = RelationEdge(
            source_id="pkg/base.py::BaseRunner",
            target_expr="helper",
            edge_kind="calls",
            span=Span(10, 20, 2, 4, 2, 14),
            resolution_status="resolved",
            resolved_target_ids=("pkg/base.py::helper",),
        )
        fg = FileSymbolGraph(
            file_path="pkg/base.py",
            content_hash="0" * 32,
            language="python",
            root_nodes=(node,),
            outgoing_edges=(edge,),
        )
        ws = WorkspaceSymbolGraph(
            file_graphs={"pkg/base.py": fg},
            nodes_by_id={"pkg/base.py::BaseRunner": node},
            resolved_edges=(edge,),
            file_import_tables={"pkg/sub.py": table},
            folded_symbol_groups={"python::BaseRunner": ("pkg/base.py::BaseRunner",)},
            type_bases_by_id={"pkg/sub.py::SubRunner": ("pkg/base.py::BaseRunner",)},
            type_derived_by_id={"pkg/base.py::BaseRunner": ("pkg/sub.py::SubRunner",)},
            field_types_by_class_id={"pkg/sub.py::SubRunner": {"runner": "pkg/base.py::BaseRunner"}},
        )
        self.assertIsInstance(ws.file_graphs, MappingProxyType)
        self.assertIsInstance(ws.field_types_by_class_id["pkg/sub.py::SubRunner"], MappingProxyType)
        with self.assertRaises(TypeError):
            ws.file_graphs["other.py"] = fg  # type: ignore[index]

        ws_rt = WorkspaceSymbolGraph.from_dict(ws.to_dict())
        self.assertEqual(ws_rt.nodes_by_id["pkg/base.py::BaseRunner"].name, "BaseRunner")
        self.assertEqual(
            ws_rt.field_types_by_class_id["pkg/sub.py::SubRunner"]["runner"],
            "pkg/base.py::BaseRunner",
        )
        self.assertEqual(
            ws_rt.incoming_edges_by_target["pkg/base.py::helper"][0].resolved_target_ids,
            ("pkg/base.py::helper",),
        )

        # Negative assertions: invalid resolution_status, empty local_alias, empty file_path
        with self.assertRaises(SchemaValidationError):
            RelationEdge(
                source_id="s1",
                target_expr="fn",
                edge_kind="calls",
                span=Span(0, 1, 1, 0, 1, 1),
                resolution_status="invalid_status",
            )
        with self.assertRaises(SchemaValidationError):
            FileImportBinding(local_alias="", target_expr="pkg.a")
        with self.assertRaises(SchemaValidationError):
            FileImportTable(file_path="")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_language_config_and_plugin_registry_extensions(self) -> None:
        """Verify LanguageConfig fields, custom ModulePathResolver & EdgeRefiner registration, and broken plugin fallback."""
        py_cfg = self.registry.language_configs["python"]
        self.assertIn("self", py_cfg.receiver_aliases.get("self_aliases", ()))
        self.assertIn("super", py_cfg.receiver_aliases.get("super_aliases", ()))

        cs_cfg = self.registry.language_configs["c_sharp"]
        self.assertEqual(cs_cfg.symbol_folding.get("partial_modifier"), "partial")
        self.assertIn("base", cs_cfg.receiver_aliases.get("super_aliases", ()))

        cpp_cfg = self.registry.language_configs["cpp"]
        self.assertIn(".h", cpp_cfg.symbol_folding.get("header_extensions", ()))
        self.assertIn(".cpp", cpp_cfg.symbol_folding.get("impl_extensions", ()))

        # Register a custom language contribution with custom module_resolver, edge_refiners, plus one broken plugin path
        custom_registry = ParserRegistry(
            contributes_data={
                "languages": {
                    "python": {
                        "extensions": [".py"],
                        "mode": "tree_sitter",
                        "grammar": "tree_sitter_python",
                        "query_file": "assets/queries/python.scm",
                        "module_resolver": f"{__name__}:_CustomPrefixModuleResolver",
                        "edge_refiners": [
                            f"{__name__}:_CustomEventBusRefiner",
                            "nonexistent.pkg.module:MissingRefiner",
                        ],
                    }
                }
            }
        )
        self.assertIn("python", custom_registry.module_resolvers)
        self.assertIsInstance(custom_registry.module_resolvers["python"], _CustomPrefixModuleResolver)
        self.assertEqual(len(custom_registry.edge_refiners.get("python", ())), 1)
        self.assertIsInstance(custom_registry.edge_refiners["python"][0], _CustomEventBusRefiner)
        self.assertIn("python:nonexistent.pkg.module:MissingRefiner", custom_registry.load_errors)

        # Verify custom ModulePathResolver + EdgeRefiner work end-to-end inside WorkspaceGraphLinker
        fg_handlers = self.registry.extract_file_graph(
            "src/handlers.py",
            "def on_sync(payload):\n    return payload\n",
        )
        fg_pub_raw = self.registry.extract_file_graph(
            "src/publisher.py",
            "def trigger():\n    EventBus.publish_sync()\n",
        )
        trigger_id = [n.id for n in fg_pub_raw.all_nodes_by_id.values() if n.name == "trigger"][0]
        custom_import_edge = RelationEdge(
            source_id=trigger_id,
            target_expr="on_sync=@app/handlers.on_sync",
            edge_kind="imports",
            span=Span(0, 20, 1, 0, 1, 20),
        )
        fg_pub = FileSymbolGraph(
            file_path=fg_pub_raw.file_path,
            content_hash=fg_pub_raw.content_hash,
            language=fg_pub_raw.language,
            root_nodes=fg_pub_raw.root_nodes,
            outgoing_edges=(*fg_pub_raw.outgoing_edges, custom_import_edge),
        )
        ws = self._link_graphs([fg_handlers, fg_pub], registry=custom_registry)

        pub_table = ws.file_import_tables["src/publisher.py"]
        self.assertEqual(pub_table.bindings["on_sync"].resolved_file_path, "src/handlers.py")
        on_sync_id = [n.id for n in fg_handlers.all_nodes_by_id.values() if n.name == "on_sync"][0]
        self.assertEqual(pub_table.bindings["on_sync"].resolved_symbol_ids, (on_sync_id,))

        trigger_edges = [e for e in ws.outgoing_edges_by_source[trigger_id] if e.edge_kind == "calls"]
        self.assertEqual(len(trigger_edges), 1)
        self.assertEqual(trigger_edges[0].resolution_status, "resolved")
        self.assertEqual(trigger_edges[0].resolved_target_ids, (on_sync_id,))
        self.assertTrue(
            any(p.rule_or_hook == "Peer_EdgeRefiner:event_bus_handler" for p in trigger_edges[0].provenance)
        )

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pass1_symbol_folding_and_pass2_import_table_resolution(self) -> None:
        """Verify Pass 1 C# partial folding (including partial contagion and kind isolation) & C++ header/impl pairing without mutating FileSymbolGraph, and Pass 2 imports."""
        files = {
            # C# partial classes across two files (even if Part2 omits explicit partial modifier, contagion folds same-kind group)
            "src/User.Part1.cs": (
                "namespace App.Domain {\n"
                "    public partial class User {\n"
                "        public void Save() {}\n"
                "    }\n"
                "}\n"
            ),
            "src/User.Part2.cs": (
                "namespace App.Domain {\n"
                "    public class User {\n"
                "        public void Validate() {\n"
                "            this.Save();\n"
                "        }\n"
                "    }\n"
                "    public partial interface User {\n"
                "        void Audit();\n"
                "    }\n"
                "}\n"
            ),
            # C++ .hpp / .cpp declaration/implementation pairing
            "include/engine.hpp": (
                "class Engine {\n"
                "public:\n"
                "    void start();\n"
                "};\n"
            ),
            "src/engine.cpp": (
                '#include "engine.hpp"\n'
                "class Engine {\n"
                "public:\n"
                "    void start() {}\n"
                "};\n"
            ),
            # Python relative import, barrel __init__.py re-export, wildcard import, and external stdlib import
            "pkg/core.py": (
                "class BaseRunner:\n"
                "    def run_task(self):\n"
                "        pass\n"
                "\n"
                "def wild_helper():\n"
                "    pass\n"
            ),
            "pkg/__init__.py": "from .core import BaseRunner\n",
            "pkg/consumer.py": (
                "import os\n"
                "from . import BaseRunner as ExportedRunner\n"
                "from .core import *\n"
                "\n"
                "def execute():\n"
                "    os.getcwd()\n"
                "    wild_helper()\n"
            ),
        }
        file_graphs = self._parse_virtual_files(files)
        orig_edge_counts = {fg.file_path: len(fg.outgoing_edges) for fg in file_graphs}

        ws = self._link_graphs(file_graphs)

        # Verify FileSymbolGraph inputs were NOT mutated
        for fg in file_graphs:
            self.assertEqual(len(fg.outgoing_edges), orig_edge_counts[fg.file_path])

        # 1. C# partial class folding: User.Part1.cs and User.Part2.cs share FQN App.Domain.User (while interface is isolated)
        user_ids = ws.folded_symbol_groups.get("c_sharp::App.Domain.User", ())
        self.assertEqual(len(user_ids), 2)
        for uid in user_ids:
            self.assertIn("class", ws.nodes_by_id[uid].kinds)
            self.assertNotIn("interface", ws.nodes_by_id[uid].kinds)
        primary_user_id = user_ids[0]
        merge_edges = [
            e for e in ws.outgoing_edges_by_source.get(primary_user_id, ()) if e.edge_kind == "merges_with"
        ]
        self.assertEqual(len(merge_edges), 1)
        self.assertEqual(merge_edges[0].resolved_target_ids, (user_ids[1],))
        self.assertTrue(any(p.rule_or_hook == "Pass1:SymbolFolding" for p in merge_edges[0].provenance))

        # Furthermore, `this.Save()` inside User.Part2.cs resolves to `Save()` defined in User.Part1.cs!
        validate_id = [
            nid for nid, n in ws.nodes_by_id.items() if n.name == "Validate" and n.id.startswith("src/User.Part2.cs::")
        ][0]
        save_id = [
            nid for nid, n in ws.nodes_by_id.items() if n.name == "Save" and n.id.startswith("src/User.Part1.cs::")
        ][0]
        validate_calls = [e for e in ws.outgoing_edges_by_source[validate_id] if e.edge_kind == "calls"]
        self.assertEqual(len(validate_calls), 1)
        self.assertEqual(validate_calls[0].resolved_target_ids, (save_id,))

        # 2. C++ .hpp / .cpp pairing: header start() emits declares edge to impl start()
        cpp_start_hdr = [
            nid for nid, n in ws.nodes_by_id.items() if n.name == "start" and nid.startswith("include/engine.hpp::")
        ][0]
        cpp_start_impl = [
            nid for nid, n in ws.nodes_by_id.items() if n.name == "start" and nid.startswith("src/engine.cpp::")
        ][0]
        decl_edges = [
            e for e in ws.outgoing_edges_by_source.get(cpp_start_hdr, ()) if e.edge_kind == "declares"
        ]
        self.assertEqual(len(decl_edges), 1)
        self.assertEqual(decl_edges[0].resolved_target_ids, (cpp_start_impl,))

        # 3. Pass 2 Python barrel re-export, wildcard import, and external stdlib marking
        consumer_table = ws.file_import_tables["pkg/consumer.py"]
        base_runner_id = "pkg/core.py::BaseRunner"
        self.assertEqual(consumer_table.bindings["ExportedRunner"].resolved_symbol_ids, (base_runner_id,))
        self.assertTrue(consumer_table.bindings["ExportedRunner"].is_reexport)
        self.assertTrue(consumer_table.bindings["wild_helper"].is_wildcard)
        self.assertTrue(consumer_table.bindings["os"].is_external)

        exec_id = "pkg/consumer.py::execute"
        exec_calls = {e.target_expr: e for e in ws.outgoing_edges_by_source[exec_id] if e.edge_kind == "calls"}
        self.assertEqual(exec_calls["os.getcwd"].resolution_status, "external")
        self.assertEqual(exec_calls["os.getcwd"].resolved_target_ids, ())
        wild_id = "pkg/core.py::wild_helper"
        self.assertEqual(exec_calls["wild_helper"].resolution_status, "resolved")
        self.assertEqual(exec_calls["wild_helper"].resolved_target_ids, (wild_id,))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pass3_inheritance_dag_and_field_dispatch(self) -> None:
        """Verify Pass 3 import-disambiguated inheritance DAG, cycle-safe pruning, field type dispatch, and expand_contract_symbol_ids."""
        files = {
            "pkg_a/base.py": (
                "class BaseRunner:\n"
                "    def run_job(self):\n"
                "        pass\n"
            ),
            "pkg_b/base.py": (
                "class BaseRunner:\n"
                "    def run_job(self):\n"
                "        pass\n"
            ),
            "pkg_a/worker.py": (
                "from pkg_a.base import BaseRunner\n"
                "\n"
                "class Helper:\n"
                "    def assist(self):\n"
                "        pass\n"
                "\n"
                "class Worker(BaseRunner):\n"
                "    helper: Helper\n"
                "    def execute(self):\n"
                "        self.run_job()\n"
                "        self.helper.assist()\n"
            ),
            # Cyclic inheritance edge case: CycleA(CycleB) and CycleB(CycleA)
            "pkg_a/cyclic.py": (
                "class CycleA(CycleB):\n"
                "    def ping(self):\n"
                "        self.missing_method()\n"
                "\n"
                "class CycleB(CycleA):\n"
                "    pass\n"
            ),
        }
        file_graphs = self._parse_virtual_files(files)
        ws = self._link_graphs(file_graphs)

        base_a_id = "pkg_a/base.py::BaseRunner"
        base_b_id = "pkg_b/base.py::BaseRunner"
        worker_id = "pkg_a/worker.py::Worker"

        # Worker inherits strictly from pkg_a/base.py:BaseRunner (NOT pkg_b/base.py:BaseRunner)
        self.assertEqual(ws.type_bases_by_id[worker_id], (base_a_id,))
        self.assertNotIn(base_b_id, ws.type_bases_by_id[worker_id])
        self.assertEqual(ws.type_derived_by_id[base_a_id], (worker_id,))

        # Verify self.run_job() resolves to pkg_a/base.py:BaseRunner.run_job, and self.helper.assist() resolves to Helper.assist
        exec_id = "pkg_a/worker.py::Worker.execute"
        run_job_a_id = "pkg_a/base.py::BaseRunner.run_job"
        assist_id = "pkg_a/worker.py::Helper.assist"

        exec_calls = {e.target_expr: e for e in ws.outgoing_edges_by_source[exec_id] if e.edge_kind == "calls"}
        self.assertEqual(exec_calls["self.run_job"].resolved_target_ids, (run_job_a_id,))
        self.assertTrue(
            any(p.rule_or_hook == "Pass4:Tier2_ClassAndBaseDAG" for p in exec_calls["self.run_job"].provenance)
        )
        self.assertEqual(exec_calls["self.helper.assist"].resolved_target_ids, (assist_id,))
        self.assertTrue(
            any(p.rule_or_hook == "Pass4:Tier2_ClassAndBaseDAG" for p in exec_calls["self.helper.assist"].provenance)
        )

        # Verify expand_contract_symbol_ids works on WorkspaceSymbolGraph
        expanded = expand_contract_symbol_ids(ws, [base_a_id])
        self.assertIn(base_a_id, expanded)
        self.assertIn(worker_id, expanded)

        # Verify cyclic inheritance terminates cleanly without RecursionError
        ping_id = "pkg_a/cyclic.py::CycleA.ping"
        ping_calls = [e for e in ws.outgoing_edges_by_source[ping_id] if e.edge_kind == "calls"]
        self.assertEqual(len(ping_calls), 1)
        self.assertEqual(ping_calls[0].resolution_status, "unresolved")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pass4_scope_cascade_overloads_ambiguity_markdown_and_determinism(self) -> None:
        """Verify 4-Tier scope cascade, overload arity vs overload_group, duck-typed ambiguous status, Markdown documents edges, and input order independence."""
        files = {
            # C# overload disambiguation by arity vs overload_group
            "src/Calculator.cs": (
                "namespace MathLib {\n"
                "    public class Calculator {\n"
                "        public int Compute(int a) { return a; }\n"
                "        public int Compute(int a, int b) { return a + b; }\n"
                "        public int Merge(int a, int b) { return a; }\n"
                "        public int Merge(string a, string b) { return 0; }\n"
                "        public void Run() {\n"
                "            this.Compute(1, 2);\n"
                "            this.Merge(1, 2);\n"
                "        }\n"
                "    }\n"
                "}\n"
            ),
            # Cross-class duck-typed ambiguity (two classes with `render()` and an untyped receiver `widget.render()`)
            "ui/button.py": (
                "class Button:\n"
                "    def render(self):\n"
                "        pass\n"
            ),
            "ui/modal.py": (
                "class Modal:\n"
                "    def render(self):\n"
                "        pass\n"
            ),
            "ui/screen.py": (
                "def local_helper():\n"
                "    pass\n"
                "\n"
                "def draw_screen(widget):\n"
                "    local_helper()\n"
                "    widget.render()\n"
                "    MathLib.Calculator.Compute(1)\n"
            ),
            # Markdown documentation referencing code symbols
            "docs/guide.md": (
                "# Architecture Guide\n\n"
                "See [Button](../ui/button.py#Button) and `MathLib.Calculator.Compute` for details.\n"
            ),
        }
        file_graphs = self._parse_virtual_files(files)

        ws_forward = self._link_graphs(file_graphs)
        ws_reverse = self._link_graphs(list(reversed(file_graphs)))

        # Input order independence (G([f1, f2, ...]) == G([fn, ..., f1]))
        self.assertEqual(ws_forward.to_dict(), ws_reverse.to_dict())

        # 1. C# overload resolution: Compute(1, 2) has arg_count=2 -> resolves uniquely to Compute(int a, int b)
        # Merge(1, 2) has two 2-arg overloads -> resolution_status == "overload_group" with both IDs sorted
        run_id = [
            nid for nid, n in ws_forward.nodes_by_id.items() if n.name == "Run" and nid.startswith("src/Calculator.cs::")
        ][0]
        run_calls = {
            e.target_expr: e for e in ws_forward.outgoing_edges_by_source[run_id] if e.edge_kind == "calls"
        }

        compute_2arg_id = [
            nid
            for nid, n in ws_forward.nodes_by_id.items()
            if n.name == "Compute" and "int b" in str(n.facets.get("signature", ""))
        ][0]
        self.assertEqual(run_calls["self.Compute"].resolution_status, "resolved")
        self.assertEqual(run_calls["self.Compute"].resolved_target_ids, (compute_2arg_id,))

        merge_ids = tuple(sorted(nid for nid, n in ws_forward.nodes_by_id.items() if n.name == "Merge"))
        self.assertEqual(len(merge_ids), 2)
        self.assertEqual(run_calls["self.Merge"].resolution_status, "overload_group")
        self.assertEqual(run_calls["self.Merge"].resolved_target_ids, merge_ids)

        # 2. Python Tier 1 lexical scope (`local_helper`), Tier 4 FQN (`MathLib.Calculator.Compute`), and ambiguous (`widget.render`)
        draw_id = "ui/screen.py::draw_screen"
        draw_calls = {
            e.target_expr: e for e in ws_forward.outgoing_edges_by_source[draw_id] if e.edge_kind == "calls"
        }

        local_helper_id = "ui/screen.py::local_helper"
        self.assertEqual(draw_calls["local_helper"].resolution_status, "resolved")
        self.assertEqual(draw_calls["local_helper"].resolved_target_ids, (local_helper_id,))
        self.assertTrue(
            any(p.rule_or_hook == "Pass4:Tier1_LexicalScope" for p in draw_calls["local_helper"].provenance)
        )

        render_ids = tuple(sorted(nid for nid, n in ws_forward.nodes_by_id.items() if n.name == "render"))
        self.assertEqual(len(render_ids), 2)
        self.assertEqual(draw_calls["widget.render"].resolution_status, "ambiguous")
        self.assertEqual(draw_calls["widget.render"].resolved_target_ids, render_ids)

        compute_1arg_id = [
            nid
            for nid, n in ws_forward.nodes_by_id.items()
            if n.name == "Compute" and "int b" not in str(n.facets.get("signature", ""))
        ][0]
        self.assertEqual(draw_calls["MathLib.Calculator.Compute"].resolution_status, "resolved")
        self.assertEqual(draw_calls["MathLib.Calculator.Compute"].resolved_target_ids, (compute_1arg_id,))
        self.assertTrue(
            any(p.rule_or_hook == "Pass4:Tier4_WorkspaceFQN" for p in draw_calls["MathLib.Calculator.Compute"].provenance)
        )

        # 3. Markdown `documents` edge linking: `[Button](../ui/button.py#Button)` -> ui/button.py::Button
        heading_id = [nid for nid in ws_forward.nodes_by_id if nid.startswith("docs/guide.md::")][0]
        doc_edges = {
            e.target_expr: e
            for e in ws_forward.outgoing_edges_by_source.get(heading_id, ())
            if e.edge_kind == "documents"
        }
        button_id = "ui/button.py::Button"
        self.assertEqual(doc_edges["../ui/button.py#Button"].resolution_status, "resolved")
        self.assertEqual(doc_edges["../ui/button.py#Button"].resolved_target_ids, (button_id,))
        self.assertEqual(doc_edges["MathLib.Calculator.Compute"].resolution_status, "overload_group")

        self.mark_passed()
