"""
Subsystem tests for DialectAdapter hierarchy (`ast_engine.dialects`) and ParserRegistry / parsers (`ast_engine.parsers`).
"""

import io
import logging
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

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
)
from ast_engine.schema import SymbolKind
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
        py_syms = py_ast_parser.parse(
            "mod.py",
            "class Greeter(BaseGreeter):\n"
            "    def greet(\n"
            "        self,\n"
            "        who: str,\n"
            "    ) -> str:\n"
            "        super().greet(who)\n"
            "        return who\n",
            space="code",
        )
        greet_sym = next((s for s in py_syms if s.kind == "method" and s.name.endswith("greet")), None)
        self.assertIsNotNone(greet_sym)
        assert greet_sym is not None
        self.assertIn("who: str", greet_sym.signature)
        py_calls = py_ast_parser.extract_call_sites(
            "mod.py",
            "class Greeter(BaseGreeter):\n    def greet(self, who: str) -> str:\n        super().greet(who)\n",
            space="code",
            symbols=py_syms,
        )
        greet_call = next((c for c in py_calls if c.callee_name == "greet"), None)
        self.assertIsNotNone(greet_call)
        self.assertEqual(greet_call.context_prefix, "base")

        # MarkdownParser: fenced code block comments and pipe tables inside fences must be ignored
        md_parser = MarkdownParser()
        md_content = (
            "# System Architecture\n"
            "Overview referencing `OrderService.SubmitOrder()` and [OrderService](Services/OrderService.cs#L4).\n\n"
            "```python\n"
            "# Not A Heading Inside Code Block\n"
            "| Fake | Table |\n"
            "| --- | --- |\n"
            "```\n\n"
            "| Component | Role |\n"
            "| --- | --- |\n"
            "| AST | Parser |\n"
        )
        md_syms = md_parser.parse("docs/ARCH.md", md_content, space="docs")
        heading_names = [s.name for s in md_syms if s.kind.startswith("doc_heading")]
        self.assertEqual(heading_names, ["System Architecture"])
        table_syms = [s for s in md_syms if s.kind == SymbolKind.DOC_TABLE.value]
        self.assertEqual(len(table_syms), 1)
        md_calls = md_parser.extract_call_sites("docs/ARCH.md", md_content, space="docs")
        self.assertTrue(any(c.callee_name == "SubmitOrder" for c in md_calls))
        self.assertTrue(any(c.callee_name == "OrderService" for c in md_calls))

        # SpiceParser: .SUBCKT, X instances, and .INCLUDE imports
        spice_parser = SpiceParser()
        spice_content = (
            "* CMOS Inverter Subcircuit\n"
            ".INCLUDE 'models/cmos.lib'\n"
            ".SUBCKT INV in out vdd vss\n"
            ".PARAM wp=2u wn=1u\n"
            "MP1 out in vdd vdd PMOS W=wp L=0.18u\n"
            "MN1 out in vss vss NMOS W=wn L=0.18u\n"
            ".ENDS INV\n"
            "XINV1 clk clk_b vdd vss INV\n"
        )
        spice_syms = spice_parser.parse("circuits/inv.sp", spice_content, space="eda")
        subckt = next((s for s in spice_syms if s.name == "INV" and s.kind == "class"), None)
        self.assertIsNotNone(subckt)
        spice_calls = spice_parser.extract_call_sites("circuits/inv.sp", spice_content, space="eda")
        self.assertTrue(any(c.callee_name == "INV" for c in spice_calls))
        inc_sym = next((s for s in spice_syms if "cmos.lib" in s.name), None)
        self.assertIsNotNone(inc_sym)

        # HtmlParser: inline trailing comment on the same line as heading/element must not skip the line
        html_parser = HtmlParser()
        html_syms = html_parser.parse(
            "ui/index.html",
            "<html><head><title>Dashboard</title></head>"
            "<body><h1 id='main-title'>Welcome</h1> <!-- inline comment -->\n"
            "<main>Content</main></body></html>",
            space="web",
        )
        self.assertTrue(any(s.name == "Dashboard" for s in html_syms))
        self.assertTrue(any(s.name == "Welcome" for s in html_syms))
        self.assertTrue(any("#main-title" in s.name for s in html_syms))

        # CssParser: inline trailing comment on selector line must not skip the selector
        css_parser = CssParser()
        css_syms = css_parser.parse(
            "ui/styles.css",
            ":root {\n"
            "  --primary-color: #336699; /* brand color */\n"
            "}\n"
            ".btn-primary { /* button rule */\n"
            "  color: var(--primary-color);\n"
            "}\n",
            space="web",
        )
        self.assertTrue(any(s.name == "--primary-color" for s in css_syms))
        self.assertTrue(any(s.name == ".btn-primary" for s in css_syms))
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
