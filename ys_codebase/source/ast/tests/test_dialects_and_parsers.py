"""
Subsystem tests for DialectAdapter hierarchy (`ast_engine.dialects`) and ParserRegistry / parsers (`ast_engine.parsers`).
"""

import io
import logging
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from ast_engine.dialects import (
    CDialect,
    CppDialect,
    CSharpDialect,
    DialectAdapter,
    JavaScriptDialect,
    MarkdownDialect,
    PythonDialect,
    TypeScriptDialect,
    get_dialect,
    register_dialect,
)
from ast_engine.parsers import (
    CssParser,
    HtmlParser,
    MarkdownParser,
    ParserRegistry,
    PythonASTParser,
    SpiceParser,
    TreeSitterDriver,
)
from ast_engine.schema import LanguageConfig, SymbolKind
from tests import ASTTestCase, Requirement, require


class TestDialectsAndParsers(ASTTestCase):
    """Tests for DialectAdapter language specialization, TreeSitterDriver, domain parsers, and ParserRegistry."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_dialects_test_"))

    def tearDown(self) -> None:
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_dialect_factory_and_language_properties(self) -> None:
        """Verify get_dialect() and register_dialect() return specialized DialectAdapter instances."""
        py_dialect = get_dialect("python")
        cs_dialect = get_dialect("c_sharp")
        cpp_dialect = get_dialect("cpp")
        c_dialect = get_dialect("c")
        js_dialect = get_dialect("javascript")
        ts_dialect = get_dialect("typescript")
        md_dialect = get_dialect("markdown")
        unknown_dialect = get_dialect("nonexistent_lang")

        self.assertIsInstance(py_dialect, PythonDialect)
        self.assertEqual(py_dialect.scope_separator, ".")
        self.assertFalse(py_dialect.supports_partial_aggregation)

        self.assertIsInstance(cs_dialect, CSharpDialect)
        self.assertEqual(cs_dialect.scope_separator, ".")
        self.assertTrue(cs_dialect.supports_partial_aggregation)

        self.assertIsInstance(cpp_dialect, CppDialect)
        self.assertEqual(cpp_dialect.scope_separator, "::")
        self.assertFalse(cpp_dialect.supports_partial_aggregation)

        self.assertIsInstance(c_dialect, CDialect)
        self.assertEqual(c_dialect.scope_separator, "::")

        self.assertIsInstance(js_dialect, JavaScriptDialect)
        self.assertIsInstance(ts_dialect, TypeScriptDialect)
        self.assertIsInstance(md_dialect, MarkdownDialect)
        self.assertIsInstance(unknown_dialect, DialectAdapter)

        class CustomLuaDialect(DialectAdapter):
            language = "lua"
            scope_separator = ":"

        register_dialect("lua", CustomLuaDialect())
        self.assertIsInstance(get_dialect("lua"), CustomLuaDialect)
        self.assertEqual(get_dialect("lua").scope_separator, ":")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dialect_visibility_docstrings_and_imports_extraction(self) -> None:
        """Verify Python, C#, C++, and JS/TS dialect docstring cleaning, visibility rules, out-of-line scopes, and imports."""
        base_adapter = DialectAdapter()
        cleaned_doc = base_adapter.clean_docstring(
            "/// <summary> caches Dictionary<string, int> items </summary>\n# hash line comment\n/* block comment */"
        )
        self.assertIn("Dictionary<string, int>", cleaned_doc)
        self.assertIn("hash line comment", cleaned_doc)
        self.assertNotIn("<summary>", cleaned_doc)

        self.assertEqual(base_adapter.normalize_call_receiver("this._svc?."), "self._svc")
        self.assertEqual(base_adapter.normalize_call_receiver("super()."), "base")
        self.assertEqual(base_adapter.normalize_call_receiver("super()._svc."), "self._svc")
        self.assertEqual(base_adapter.normalize_call_receiver("__super::"), "base")
        self.assertEqual(base_adapter.normalize_call_receiver("__super._svc."), "self._svc")
        self.assertEqual(base_adapter.normalize_call_receiver("base->"), "base")

        py_dialect = PythonDialect()
        self.assertEqual(py_dialect.extract_visibility(None, short_name="public_fn", kind="method"), "public")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="_protected_fn", kind="method"), "protected")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="__private_fn", kind="method"), "private")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="__init__", kind="method"), "public")

        multiline_sig = py_dialect.format_signature(
            first_line="def process(",
            captured_signature="(self, a: int,\n    b: str = 'x')",
            name="process",
            def_kind="method",
        )
        self.assertEqual(multiline_sig, "def process(self, a: int, b: str = 'x')")

        py_imports = py_dialect.extract_imports(
            "import os, sys as system_mod  # trailing comment\n"
            "from core.uri import resolve as uri_resolve, join  # inline comment\n"
            "from pkg.sub import (\n"
            "    Alpha,\n"
            "    Beta as B,  # comment inside parens\n"
            ")\n"
        )
        self.assertEqual(py_imports.get("os"), "os")
        self.assertEqual(py_imports.get("system_mod"), "sys")
        self.assertEqual(py_imports.get("uri_resolve"), "core.uri.resolve")
        self.assertEqual(py_imports.get("join"), "core.uri.join")
        self.assertEqual(py_imports.get("Alpha"), "pkg.sub.Alpha")
        self.assertEqual(py_imports.get("B"), "pkg.sub.Beta")

        cs_dialect = CSharpDialect()
        self.assertEqual(cs_dialect.extract_visibility(None, parent_kind="interface", kind="method"), "public")
        self.assertEqual(cs_dialect.extract_visibility(None, parent_kind="class", kind="method"), "private")
        cs_imports = cs_dialect.extract_imports(
            "using System.Collections.Generic;\n"
            "global using GlobalNs.Services;\n"
            "global using WinAlias = MyCompany.UI.Window;\n"
        )
        self.assertEqual(cs_imports.get("System.Collections.Generic"), "System.Collections.Generic")
        self.assertEqual(cs_imports.get("Services"), "GlobalNs.Services")
        self.assertEqual(cs_imports.get("WinAlias"), "MyCompany.UI.Window")

        cpp_dialect = CppDialect()
        short_n, parent_s, eff_k = cpp_dialect.resolve_out_of_line_scope("Box<T>::resize", "", "function")
        self.assertEqual((short_n, parent_s, eff_k), ("resize", "Box", "method"))
        nested_short, nested_parent, nested_k = cpp_dialect.resolve_out_of_line_scope("Outer::Inner::compute", "", "function")
        self.assertEqual((nested_short, nested_parent, nested_k), ("compute", "Outer::Inner", "method"))

        js_dialect = JavaScriptDialect()
        self.assertEqual(js_dialect.extract_visibility(None, short_name="#secretField", kind="property"), "private")
        js_imports = js_dialect.extract_imports(
            "import { render as renderDom, type Props, Component } from './ui';\n"
            "import type { Config } from './config';\n"
            "import * as Utils from './utils';\n"
            "const { readFile } = require('fs');\n"
        )
        self.assertEqual(js_imports.get("renderDom"), "./ui.render")
        self.assertEqual(js_imports.get("Props"), "./ui.Props")
        self.assertEqual(js_imports.get("Component"), "./ui.Component")
        self.assertEqual(js_imports.get("Config"), "./config.Config")
        self.assertEqual(js_imports.get("Utils"), "./utils")
        self.assertEqual(js_imports.get("readFile"), "fs.readFile")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_treesitter_driver_python_csharp_cpp_parsing(self) -> None:
        """Verify TreeSitterDriver parses Python, C#, and C++ source code with dialect dispatch."""
        registry = ParserRegistry(register_defaults=True)

        py_code = (
            "class Calculator:\n"
            '    """Simple calculator."""\n'
            "    def add(self, a: int, b: int) -> int:\n"
            "        return a + b\n"
            "\n"
            "    def _helper(self) -> None:\n"
            "        self.add(1, 2)\n"
        )
        py_symbols = registry.parse_file("pkg/calc.py", py_code, space="code")
        self.assertEqual(len(py_symbols), 3)
        calc_cls = next((s for s in py_symbols if s.name.endswith("Calculator") and s.kind == "class"), None)
        self.assertIsNotNone(calc_cls)
        assert calc_cls is not None
        member_names = {m.name: m.visibility for m in calc_cls.members}
        self.assertEqual(member_names.get("add"), "public")
        self.assertEqual(member_names.get("_helper"), "protected")

        py_calls = registry.extract_call_sites("pkg/calc.py", py_code, space="code", symbols=py_symbols)
        self.assertTrue(any(c.callee_name == "add" for c in py_calls))

        cs_code = (
            "namespace MyApp.Services {\n"
            "    public partial class OrderService : IOrderService {\n"
            "        private readonly ILogger _logger;\n"
            "        public void SubmitOrder(string orderId) {\n"
            "            _logger.LogInfo(orderId);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        cs_symbols = registry.parse_file("Services/OrderService.cs", cs_code, space="code")
        order_cls = next((s for s in cs_symbols if s.kind == "class" and "OrderService" in s.name), None)
        self.assertIsNotNone(order_cls)
        assert order_cls is not None
        self.assertEqual(order_cls.fqn, "MyApp.Services.OrderService")
        self.assertTrue(order_cls.metadata.get("is_partial"))
        self.assertIn("IOrderService", order_cls.metadata.get("base_types", []))
        self.assertEqual(order_cls.metadata.get("field_types", {}).get("_logger"), "ILogger")

        cs_calls = registry.extract_call_sites("Services/OrderService.cs", cs_code, space="code", symbols=cs_symbols)
        log_call = next((c for c in cs_calls if c.callee_name == "LogInfo"), None)
        self.assertIsNotNone(log_call)
        assert log_call is not None
        self.assertEqual(log_call.context_prefix, "_logger")

        cpp_code = (
            "namespace Engine {\n"
            "    class Renderer {\n"
            "    public:\n"
            "        void DrawFrame(int frameId);\n"
            "    private:\n"
            "        int m_frameCount;\n"
            "    };\n"
            "}\n"
        )
        cpp_symbols = registry.parse_file("src/Renderer.hpp", cpp_code, space="code")
        renderer_cls = next((s for s in cpp_symbols if s.kind == "class" and "Renderer" in s.name), None)
        self.assertIsNotNone(renderer_cls)
        assert renderer_cls is not None
        self.assertEqual(renderer_cls.fqn, "Engine::Renderer")
        cpp_members = {m.name: m.visibility for m in renderer_cls.members}
        self.assertEqual(cpp_members.get("DrawFrame"), "public")
        self.assertEqual(cpp_members.get("m_frameCount"), "private")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_domain_and_standalone_parsers_edge_cases(self) -> None:
        """Verify PythonASTParser, MarkdownParser fenced blocks, SpiceParser, HtmlParser inline comments, and CssParser inline comments."""
        py_ast_parser = PythonASTParser()
        self.assertTrue(py_ast_parser.can_parse("mod.py"))
        py_src = (
            "class Greeter(BaseGreeter):\n"
            "    def __init__(self) -> None:\n"
            "        self.logger: Logger = make_logger()\n"
            "    def greet(\n"
            "        self,\n"
            "        who: str,\n"
            "    ) -> str:\n"
            "        def _format_msg(msg: str) -> str:\n"
            "            return msg.strip()\n"
            "        super().greet(who)\n"
            "        self.logger.client.send(_format_msg(who))\n"
            "        return who\n"
        )
        py_syms = py_ast_parser.parse("mod.py", py_src, space="code")
        greet_sym = next((s for s in py_syms if s.kind == "method" and s.name.endswith("greet")), None)
        self.assertIsNotNone(greet_sym)
        assert greet_sym is not None
        self.assertIn("who: str", greet_sym.signature)
        nested_fn = next((s for s in py_syms if s.fqn == "Greeter.greet._format_msg"), None)
        self.assertIsNotNone(nested_fn)
        greeter_cls = next((s for s in py_syms if s.kind == "class" and s.name == "Greeter"), None)
        self.assertIsNotNone(greeter_cls)
        assert greeter_cls is not None
        self.assertEqual(greeter_cls.metadata.get("field_types", {}).get("logger"), "Logger")

        py_calls = py_ast_parser.extract_call_sites("mod.py", py_src, space="code", symbols=py_syms)
        greet_call = next((c for c in py_calls if c.callee_name == "greet"), None)
        self.assertIsNotNone(greet_call)
        self.assertEqual(greet_call.context_prefix, "base")
        send_call = next((c for c in py_calls if c.callee_name == "send"), None)
        self.assertIsNotNone(send_call)
        assert send_call is not None
        self.assertEqual(send_call.context_prefix, "self.logger.client")

        # MarkdownParser: fenced code block comments, Setext headings, pipe tables, and non-duplicate documents edges
        md_parser = MarkdownParser()
        md_content = (
            "# System Architecture\n"
            "Overview referencing `OrderService.SubmitOrder()` and [OrderService](Services/OrderService.cs#L4).\n\n"
            "Setext Section\n"
            "--------------\n\n"
            "```python\n"
            "# Not A Heading Inside Code Block\n"
            "| Fake | Table |\n"
            "| --- | --- |\n"
            "```\n\n"
            "| Component | Role |\n"
            "| --- | --- |\n"
            "| AST | Parser |\n"
        )
        md_syms = md_parser.parse("docs/overview.md", md_content, space="docs")
        heading_names = [s.name for s in md_syms if s.kind.startswith("doc_heading")]
        self.assertEqual(heading_names, ["System Architecture", "Setext Section"])
        table_syms = [s for s in md_syms if s.kind == SymbolKind.DOC_TABLE.value]
        self.assertEqual(len(table_syms), 1)
        md_calls = md_parser.extract_call_sites("docs/overview.md", md_content, space="docs")
        self.assertTrue(any(c.callee_name == "SubmitOrder" for c in md_calls))
        self.assertTrue(any(c.callee_name == "OrderService" for c in md_calls))
        md_fg = md_parser.extract_file_graph("docs/overview.md", md_content, space="docs")
        self.assertTrue(any(e.edge_kind == "documents" for e in md_fg.outgoing_edges))
        self.assertFalse(any(e.edge_kind == "calls" for e in md_fg.outgoing_edges))

        # SpiceParser: nested and unclosed .SUBCKT, X instances, and .INCLUDE imports
        spice_parser = SpiceParser()
        spice_content = (
            "* CMOS Inverter Subcircuit\n"
            ".INCLUDE 'models/cmos.lib'\n"
            ".SUBCKT INV in out vdd vss\n"
            ".PARAM wp=2u wn=1u\n"
            ".SUBCKT INNER_CELL a b\n"
            "R1 a b 1k\n"
            ".ENDS INNER_CELL\n"
            "MP1 out in vdd vdd PMOS W=wp L=0.18u\n"
            "MN1 out in vss vss NMOS W=wn L=0.18u\n"
            ".ENDS INV\n"
            ".SUBCKT UNCLOSED_SUB p1 p2\n"
            "XINV1 clk clk_b vdd vss INV\n"
        )
        spice_syms = spice_parser.parse("circuits/inv.sp", spice_content, space="eda")
        subckt = next((s for s in spice_syms if s.name == "INV" and s.kind == "class"), None)
        self.assertIsNotNone(subckt)
        inner_sub = next((s for s in spice_syms if s.name == "INNER_CELL" and s.kind == "class"), None)
        self.assertIsNotNone(inner_sub)
        assert inner_sub is not None
        self.assertEqual(inner_sub.fqn, "INV.INNER_CELL")
        unclosed_sub = next((s for s in spice_syms if s.name == "UNCLOSED_SUB"), None)
        self.assertIsNotNone(unclosed_sub)
        spice_calls = spice_parser.extract_call_sites("circuits/inv.sp", spice_content, space="eda")
        self.assertTrue(any(c.callee_name == "INV" for c in spice_calls))
        inc_sym = next((s for s in spice_syms if "cmos.lib" in s.name), None)
        self.assertIsNotNone(inc_sym)

        # HtmlParser: multiple inline comments and unclosed comment handling
        html_parser = HtmlParser()
        html_syms = html_parser.parse(
            "ui/index.html",
            "<html><head><title>Dashboard</title></head>"
            "<body><!-- c1 --> <h1 id='main-title'>Welcome</h1> <!-- c2 -->\n"
            "<main>Content</main><!-- unclosed comment</body></html>",
            space="web",
        )
        self.assertTrue(any(s.name == "Dashboard" for s in html_syms))
        self.assertTrue(any(s.name == "Welcome" for s in html_syms))
        self.assertTrue(any("#main-title" in s.name for s in html_syms))

        # CssParser: multiple inline comments on selector line and unclosed comment handling
        css_parser = CssParser()
        css_syms = css_parser.parse(
            "ui/styles.css",
            ":root {\n"
            "  /* c1 */ --primary-color: #336699; /* c2 */\n"
            "}\n"
            "/* lead */ .btn-primary { /* trail */\n"
            "  color: var(--primary-color);\n"
            "}\n"
            "/* unclosed comment at eof .ignored { }",
            space="web",
        )
        self.assertTrue(any(s.name == "--primary-color" for s in css_syms))
        self.assertTrue(any(s.name == ".btn-primary" for s in css_syms))
        self.assertFalse(any(s.name == ".ignored" for s in css_syms))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_parser_registry_custom_contributes_and_file_entry(self) -> None:
        """Verify ParserRegistry handles custom contributes_data, file path parser_entry loading, and invalid entries silently."""
        custom_parser_file = self.temp_dir / "my_dsl_parser.py"
        custom_parser_file.write_text(
            "from ast_engine.parsers.base import BaseParser\n"
            "from ast_engine.schema import UnifiedSymbol\n"
            "class CustomDslParser(BaseParser):\n"
            "    def can_parse(self, file_path):\n"
            "        return str(file_path).endswith('.dsl')\n"
            "    def parse(self, file_path, content, space):\n"
            "        return [UnifiedSymbol(id='dsl1', name='DslRoot', kind='class', file_path=file_path, line_number=1, language='dsl')]\n",
            encoding="utf-8",
        )

        custom_contributes = {
            "languages": {
                "spice": {
                    "id": "spice",
                    "name": "Custom SPICE",
                    "extensions": [".sp", ".custom_spice"],
                    "mode": "custom",
                    "parser_entry": "ast_engine.parsers.spice_parser:SpiceParser",
                },
                "dsl": {
                    "id": "dsl",
                    "name": "Custom DSL",
                    "extensions": [".dsl"],
                    "mode": "custom",
                    "parser_entry": f"{custom_parser_file}:CustomDslParser",
                },
                "broken_custom": {
                    "id": "broken_custom",
                    "name": "Broken Custom",
                    "extensions": [".broken"],
                    "mode": "custom",
                    "parser_entry": "nonexistent.module.path:MissingParser",
                },
            }
        }
        reg_logger = logging.getLogger("ast.parsers.registry")
        with patch.object(reg_logger, "warning"), patch("sys.stderr", new_callable=io.StringIO):
            registry = ParserRegistry(register_defaults=True, contributes_data=custom_contributes)

        self.assertIn(".custom_spice", registry.get_supported_extensions())
        self.assertIn(".dsl", registry.get_supported_extensions())
        self.assertIn("broken_custom", registry.load_errors)

        syms = registry.parse_file("test.custom_spice", ".SUBCKT AMP inp inn out\n.ENDS AMP\n", space="eda")
        self.assertEqual(len(syms), 1)
        self.assertEqual(syms[0].name, "AMP")

        dsl_syms = registry.parse_file("rules.dsl", "rule main {}", space="code")
        self.assertEqual(len(dsl_syms), 1)
        self.assertEqual(dsl_syms[0].name, "DslRoot")

        self.assertEqual(registry.parse_file("unknown.xyz", "random text", space="code"), [])
        py_ast_parser = PythonASTParser()
        self.assertEqual(py_ast_parser.parse("bad.py", "def broken_syntax(:\n", space="code"), [])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_commutative_multi_scm_merge_recursive_hierarchy_and_space_scoping(self) -> None:
        """Verify peer .scm commutative merging (A U B == B U A), deep recursive hierarchy, SymbolProcessor refinement, and core.space rule scoping."""
        from ast_engine.parsers.base import SymbolProcessor
        from ast_engine.schema import ProvenanceStep, Span, SymbolNode

        # 1. Verify end-to-end commutative merging ($A \cup B = B \cup A$) across real `.scm` files
        tags_scm_path = self.temp_dir / "official_tags.scm"
        tags_scm_path.write_text(
            '(\n'
            '  (comment)+ @doc\n'
            '  .\n'
            '  (function_definition\n'
            '    name: (identifier) @name) @definition.function\n'
            '  (#strip! @doc "^[\\\\s#]+")\n'
            '  (#select-adjacent! @doc @definition.function)\n'
            ')\n'
            '(class_definition name: (identifier) @name) @definition.class\n'
            '(call function: (identifier) @name) @reference.call\n',
            encoding="utf-8",
        )
        domain_scm_path = self.temp_dir / "domain_cli.scm"
        domain_scm_path.write_text(
            '(class_definition name: (identifier) @part.name) @def.actor\n'
            '(function_definition\n'
            '  name: (identifier) @part.name\n'
            '  parameters: (parameters) @part.parameters\n'
            '  body: (block) @part.body @facet.cli_route\n'
            ') @def.cli_command\n',
            encoding="utf-8",
        )
        broken_scm_path = self.temp_dir / "broken_syntax.scm"
        broken_scm_path.write_text("(unclosed_query (identifier) @name", encoding="utf-8")

        sample_py_code = (
            "# Unrelated top header comment\n\n"
            "# Adjacent doc line 1\n"
            "# Adjacent doc line 2\n"
            "def handle_cmd(ctx: Context) -> int:\n"
            "    return run_helper(ctx)\n"
        )
        with patch("sys.stderr", new_callable=io.StringIO) as err_buf:
            driver_ab = TreeSitterDriver(
                LanguageConfig(
                    id="python",
                    name="Python",
                    extensions=(".py",),
                    grammar="tree_sitter_python",
                    query_files=(str(tags_scm_path), str(domain_scm_path), str(broken_scm_path)),
                )
            )
            driver_ba = TreeSitterDriver(
                LanguageConfig(
                    id="python",
                    name="Python",
                    extensions=(".py",),
                    grammar="tree_sitter_python",
                    query_files=(str(domain_scm_path), str(tags_scm_path)),
                )
            )
            self.assertIn("broken_syntax.scm", err_buf.getvalue())

        graph_ab = driver_ab.extract_file_graph("pkg/cli.py", sample_py_code)
        graph_ba = driver_ba.extract_file_graph("pkg/cli.py", sample_py_code)
        self.assertEqual(graph_ab.to_dict(), graph_ba.to_dict())
        self.assertEqual(len(graph_ab.root_nodes), 1)
        merged_fn = graph_ab.root_nodes[0]
        self.assertEqual(merged_fn.name, "handle_cmd")
        self.assertEqual(merged_fn.kinds, frozenset({"function", "cli_command"}))
        self.assertIn("parameters", merged_fn.parts)
        self.assertIn("body", merged_fn.parts)
        self.assertIn("cli_route", merged_fn.facets)
        doc_val = str(merged_fn.facets.get("docstring") or "")
        self.assertIn("Adjacent doc line 1", doc_val)
        self.assertIn("Adjacent doc line 2", doc_val)
        self.assertNotIn("Unrelated top header comment", doc_val)
        self.assertTrue(any(e.edge_kind == "calls" and e.target_expr == "run_helper" for e in graph_ab.outgoing_edges))

        syms_ab = driver_ab.parse("pkg/cli.py", sample_py_code, space="code")
        syms_ba = driver_ba.parse("pkg/cli.py", sample_py_code, space="code")
        self.assertEqual(len(syms_ab), 1)
        self.assertEqual(syms_ab[0].id, syms_ba[0].id)

        # Verify Mapping facets union in _merge_symbol_nodes_commutative
        n_left = SymbolNode(
            id="f.py::Svc",
            name="Svc",
            scope_path=(),
            kinds=frozenset({"class"}),
            language="python",
            span=Span(0, 10, 1, 0, 1, 10),
            facets={"field_types": {"a": "int"}},
        )
        n_right = SymbolNode(
            id="f.py::Svc",
            name="Svc",
            scope_path=(),
            kinds=frozenset({"service"}),
            language="python",
            span=Span(0, 10, 1, 0, 1, 10),
            facets={"field_types": {"b": "str"}},
        )
        merged_lr = ParserRegistry._merge_symbol_nodes_commutative(n_left, n_right)
        merged_rl = ParserRegistry._merge_symbol_nodes_commutative(n_right, n_left)
        self.assertEqual(dict(merged_lr.facets["field_types"]), {"a": "int", "b": "str"})
        self.assertEqual(merged_lr.to_dict(), merged_rl.to_dict())

        # Verify convert_legacy_symbols_to_file_graph builds nested hierarchy, rich parts, and inherits edges
        py_parser = PythonASTParser()
        legacy_fg = py_parser.extract_file_graph(
            file_path="svc/legacy.py",
            content=(
                "class ChildSvc(BaseSvc):\n"
                '    """Doc for ChildSvc."""\n'
                "    def run(self, count: int) -> bool:\n"
                '        """Run doc."""\n'
                "        return True\n"
            ),
            space="code",
        )
        self.assertEqual(len(legacy_fg.root_nodes), 1)
        root_cls = legacy_fg.root_nodes[0]
        self.assertEqual(root_cls.name, "ChildSvc")
        self.assertIn("doc", root_cls.parts)
        self.assertIn("body", root_cls.parts)
        self.assertEqual(len(root_cls.children), 1)
        run_child = root_cls.children[0]
        self.assertEqual(run_child.name, "run")
        self.assertIn("parameters", run_child.parts)
        self.assertIn("return_type", run_child.parts)
        self.assertTrue(any(e.edge_kind == "inherits" and e.target_expr == "BaseSvc" for e in legacy_fg.outgoing_edges))

        # 2. Verify deep recursive hierarchy (>2 levels: OuterClass -> InnerClass -> DeepMethod) and SymbolProcessor refinement
        class CustomMarkerProcessor(SymbolProcessor):
            provider_id = "test:marker_processor"

            def refine_node(self, node: SymbolNode, source_bytes: bytes) -> SymbolNode:
                new_facets = dict(node.facets)
                new_facets["processed_by_marker"] = True
                new_prov = (*node.provenance, ProvenanceStep(provider_id=self.provider_id, action="refine", rule_or_hook="CustomMarkerProcessor"))
                return SymbolNode(
                    id=node.id,
                    name=node.name,
                    scope_path=node.scope_path,
                    kinds=node.kinds,
                    language=node.language,
                    span=node.span,
                    parts=node.parts,
                    facets=new_facets,
                    children=node.children,
                    provenance=new_prov,
                )

        proc_driver = TreeSitterDriver(
            LanguageConfig(id="python", name="Python", extensions=(".py",), grammar="tree_sitter_python", query_file="assets/queries/python.scm"),
            processors=(CustomMarkerProcessor(),),
        )
        py_src = (
            "import os\n"
            "class OuterService(BaseSvc):\n"
            "    class InnerHandler:\n"
            "        def execute_task(self, x: int) -> bool:\n"
            "            return helper_fn(x)\n"
        )
        f_graph = proc_driver.extract_file_graph("svc/nested.py", py_src)
        self.assertEqual(f_graph.file_path, "svc/nested.py")
        self.assertEqual(len(f_graph.root_nodes), 1)
        outer_node = f_graph.root_nodes[0]
        self.assertEqual(outer_node.name, "OuterService")
        self.assertEqual(outer_node.id, "svc/nested.py::OuterService")
        self.assertTrue(outer_node.facets.get("processed_by_marker"))
        self.assertEqual(len(outer_node.children), 1)
        inner_node = outer_node.children[0]
        self.assertEqual(inner_node.name, "InnerHandler")
        self.assertEqual(inner_node.id, "svc/nested.py::OuterService.InnerHandler")
        self.assertEqual(len(inner_node.children), 1)
        deep_method = inner_node.children[0]
        self.assertEqual(deep_method.name, "execute_task")
        self.assertEqual(deep_method.id, "svc/nested.py::OuterService.InnerHandler.execute_task")
        self.assertIn("method", deep_method.kinds)
        self.assertIn(deep_method.id, f_graph.all_nodes_by_id)
        self.assertTrue(any(e.edge_kind == "inherits" and e.target_expr == "BaseSvc" for e in f_graph.outgoing_edges))
        self.assertTrue(any(e.edge_kind == "imports" and e.target_expr == "os" for e in f_graph.outgoing_edges))
        self.assertTrue(any(e.edge_kind == "calls" and e.target_expr == "helper_fn" and e.source_id == deep_method.id for e in f_graph.outgoing_edges))

        # 2b. Verify same-scope C# method overloads receive deterministic parameter-suffix IDs in extract_file_graph
        cs_driver = TreeSitterDriver(
            LanguageConfig(id="c_sharp", name="C#", extensions=(".cs",), grammar="tree_sitter_c_sharp", query_file="assets/queries/c_sharp.scm")
        )
        cs_overload_src = (
            "public class Window {\n"
            "    public void Open(string title) {}\n"
            "    public void Open(string title, int width) {}\n"
            "}\n"
        )
        cs_graph = cs_driver.extract_file_graph("ui/Window.cs", cs_overload_src)
        self.assertEqual(len(cs_graph.root_nodes), 1)
        win_node = cs_graph.root_nodes[0]
        overload_ids = sorted(c.id for c in win_node.children)
        self.assertEqual(
            overload_ids,
            [
                "ui/Window.cs::Window.Open(string title)",
                "ui/Window.cs::Window.Open(string title, int width)",
            ],
        )

        # 2c. Verify broken processor runtime isolation logs warning and preserves extracted graph
        class BrokenRuntimeProcessor(SymbolProcessor):
            provider_id = "test:broken_processor"

            def refine_file_graph(self, graph, source_bytes):
                raise RuntimeError("Simulated processor failure")

        resilient_driver = TreeSitterDriver(
            LanguageConfig(id="python", name="Python", extensions=(".py",), grammar="tree_sitter_python", query_file="assets/queries/python.scm"),
            processors=(BrokenRuntimeProcessor(), CustomMarkerProcessor()),
        )
        with patch("sys.stderr", new_callable=io.StringIO) as proc_err_buf:
            res_graph = resilient_driver.extract_file_graph("svc/nested.py", py_src)
            self.assertIn("Simulated processor failure", proc_err_buf.getvalue())
        self.assertEqual(len(res_graph.root_nodes), 1)
        self.assertTrue(res_graph.root_nodes[0].facets.get("processed_by_marker"))

        # 2d. Verify _extract_call_arg_count handles escaped quotes with commas and `<` comparison operators
        call_b1 = b'foo("a, \\"b, c\\"", x < y, z)'
        self.assertEqual(
            TreeSitterDriver._extract_call_arg_count(
                MagicMock(end_byte=len(call_b1)),
                MagicMock(end_byte=3),
                call_b1,
            ),
            3,
        )
        call_b2 = b"bar(a < b, c > d)"
        self.assertEqual(
            TreeSitterDriver._extract_call_arg_count(
                MagicMock(end_byte=len(call_b2)),
                MagicMock(end_byte=3),
                call_b2,
            ),
            2,
        )

        # 3. Verify `spaces` rule scoping via injected `space_manager` on ParserRegistry
        scoped_parser_file = self.temp_dir / "scoped_json_parser.py"
        scoped_parser_file.write_text(
            "from ast_engine.parsers.base import BaseParser\n"
            "from ast_engine.schema import UnifiedSymbol\n"
            "class ScopedJsonParser(BaseParser):\n"
            "    def can_parse(self, file_path):\n"
            "        return str(file_path).endswith('.json')\n"
            "    def parse(self, file_path, content, space):\n"
            "        return [UnifiedSymbol(id='j1', name='ContributeSpec', kind='class', file_path=file_path, line_number=1, language='json')]\n",
            encoding="utf-8",
        )
        scoped_contributes = {
            "languages": {
                "contributes_json": {
                    "id": "contributes_json",
                    "name": "Contributes JSON",
                    "extensions": [".json"],
                    "spaces": ["core/contributes"],
                    "mode": "custom",
                    "parser_entry": f"{scoped_parser_file}:ScopedJsonParser",
                }
            }
        }
        fake_space_reg = MagicMock()
        fake_space_reg.match_path.side_effect = lambda fp, sp: MagicMock(matched=("contributes/" in str(fp)))
        scoped_reg = ParserRegistry(
            register_defaults=False,
            contributes_data=scoped_contributes,
            space_manager=fake_space_reg,
        )
        matched_g = scoped_reg.extract_file_graph("mod/contributes/ast.json", "{}")
        self.assertEqual(len(matched_g.root_nodes), 1)
        self.assertEqual(matched_g.root_nodes[0].name, "ContributeSpec")

        unmatched_g = scoped_reg.extract_file_graph("mod/package.json", "{}")
        self.assertEqual(len(unmatched_g.root_nodes), 0)
        self.mark_passed()
