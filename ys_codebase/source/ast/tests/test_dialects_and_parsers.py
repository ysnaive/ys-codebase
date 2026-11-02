"""
Subsystem tests for DialectAdapter hierarchy (`ast_engine.dialects`) and ParserRegistry / parsers (`ast_engine.parsers`).
"""

import os
from pathlib import Path
import sys

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)

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
from dev.testing import Requirement, YSCBTestCase, require


class TestDialectsAndParsers(YSCBTestCase):
    """Tests for DialectAdapter language specialization, TreeSitterDriver, domain parsers, and ParserRegistry."""

    @require(Requirement.LOGIC)
    def test_ft_01_dialect_factory_and_language_properties(self):
        """FT-01: Verify get_dialect() returns specialized DialectAdapter subclasses with expected separators and flags."""
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
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_dialect_visibility_and_imports_extraction(self):
        """FT-02: Verify Python, C#, C++, and JS/TS dialect visibility rules and import extraction."""
        py_dialect = PythonDialect()
        self.assertEqual(py_dialect.extract_visibility(None, short_name="public_fn", kind="method"), "public")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="_protected_fn", kind="method"), "protected")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="__private_fn", kind="method"), "private")
        self.assertEqual(py_dialect.extract_visibility(None, short_name="__init__", kind="method"), "public")

        py_imports = py_dialect.extract_imports(
            "import os, sys as system_mod\nfrom core.uri import resolve as uri_resolve, join\n"
        )
        self.assertEqual(py_imports.get("os"), "os")
        self.assertEqual(py_imports.get("system_mod"), "sys")
        self.assertEqual(py_imports.get("uri_resolve"), "core.uri.resolve")
        self.assertEqual(py_imports.get("join"), "core.uri.join")

        cs_dialect = CSharpDialect()
        self.assertEqual(cs_dialect.extract_visibility(None, parent_kind="interface", kind="method"), "public")
        self.assertEqual(cs_dialect.extract_visibility(None, parent_kind="class", kind="method"), "private")
        cs_imports = cs_dialect.extract_imports(
            "using System.Collections.Generic;\nusing WindowAlias = MyCompany.UI.Window;\n"
        )
        self.assertEqual(cs_imports.get("System.Collections.Generic"), "System.Collections.Generic")
        self.assertEqual(cs_imports.get("WindowAlias"), "MyCompany.UI.Window")

        js_dialect = JavaScriptDialect()
        self.assertEqual(js_dialect.extract_visibility(None, short_name="#secretField", kind="property"), "private")
        js_imports = js_dialect.extract_imports(
            "import { render as renderDom, Component } from './ui';\nconst { readFile } = require('fs');\n"
        )
        self.assertEqual(js_imports.get("renderDom"), "./ui.render")
        self.assertEqual(js_imports.get("Component"), "./ui.Component")
        self.assertEqual(js_imports.get("readFile"), "fs.readFile")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_treesitter_driver_python_csharp_cpp_parsing(self):
        """FT-03: Verify TreeSitterDriver parses Python, C#, and C++ source code with zero-if-elif dialect dispatch."""
        registry = ParserRegistry(register_defaults=True)

        # Python parsing
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
        self.assertTrue(len(py_symbols) > 0)
        calc_cls = next((s for s in py_symbols if s.name.endswith("Calculator") and s.kind == "class"), None)
        self.assertIsNotNone(calc_cls)
        member_names = {m.name: m.visibility for m in calc_cls.members}
        self.assertEqual(member_names.get("add"), "public")
        self.assertEqual(member_names.get("_helper"), "protected")

        py_calls = registry.extract_call_sites("pkg/calc.py", py_code, space="code", symbols=py_symbols)
        self.assertTrue(any(c.callee_name == "add" for c in py_calls))

        # C# parsing
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
        self.assertEqual(order_cls.fqn, "MyApp.Services.OrderService")
        self.assertTrue(order_cls.metadata.get("is_partial"))
        self.assertIn("IOrderService", order_cls.metadata.get("base_types", []))
        self.assertEqual(order_cls.metadata.get("field_types", {}).get("_logger"), "ILogger")

        cs_calls = registry.extract_call_sites("Services/OrderService.cs", cs_code, space="code", symbols=cs_symbols)
        log_call = next((c for c in cs_calls if c.callee_name == "LogInfo"), None)
        self.assertIsNotNone(log_call)
        self.assertEqual(log_call.context_prefix, "_logger")

        # C++ parsing
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
        self.assertEqual(renderer_cls.fqn, "Engine::Renderer")
        cpp_members = {m.name: m.visibility for m in renderer_cls.members}
        self.assertEqual(cpp_members.get("DrawFrame"), "public")
        self.assertEqual(cpp_members.get("m_frameCount"), "private")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_domain_and_standalone_parsers(self):
        """FT-04: Verify PythonASTParser, MarkdownParser, SpiceParser, HtmlParser, and CssParser."""
        # PythonASTParser standalone
        py_ast_parser = PythonASTParser()
        self.assertTrue(py_ast_parser.can_parse("mod.py"))
        py_syms = py_ast_parser.parse(
            "mod.py",
            "class Greeter:\n    def greet(self, who: str) -> str:\n        return who\n",
            space="code",
        )
        self.assertTrue(any(s.name == "Greeter" and s.kind == "class" for s in py_syms))

        # MarkdownParser standalone
        md_parser = MarkdownParser()
        md_content = (
            "# System Architecture\n"
            "Overview referencing `OrderService.SubmitOrder()` and [OrderService](Services/OrderService.cs#L4).\n\n"
            "| Component | Role |\n"
            "| --- | --- |\n"
            "| AST | Parser |\n"
        )
        md_syms = md_parser.parse("docs/ARCH.md", md_content, space="docs")
        self.assertTrue(any(s.kind == SymbolKind.DOC_HEADING_1.value and s.name == "System Architecture" for s in md_syms))
        self.assertTrue(any(s.kind == SymbolKind.DOC_TABLE.value for s in md_syms))
        md_calls = md_parser.extract_call_sites("docs/ARCH.md", md_content, space="docs")
        self.assertTrue(any(c.callee_name == "SubmitOrder" for c in md_calls))
        self.assertTrue(any(c.callee_name == "OrderService" for c in md_calls))

        # SpiceParser
        spice_parser = SpiceParser()
        spice_content = (
            "* CMOS Inverter Subcircuit\n"
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

        # HtmlParser & CssParser
        html_parser = HtmlParser()
        html_syms = html_parser.parse(
            "ui/index.html",
            "<html><head><title>Dashboard</title></head><body><h1 id='main-title'>Welcome</h1><main>Content</main></body></html>",
            space="web",
        )
        self.assertTrue(any(s.name == "Dashboard" for s in html_syms))
        self.assertTrue(any("#main-title" in s.name for s in html_syms))

        css_parser = CssParser()
        css_syms = css_parser.parse(
            "ui/styles.css",
            ":root {\n  --primary-color: #336699;\n}\n.btn-primary {\n  color: var(--primary-color);\n}\n",
            space="web",
        )
        self.assertTrue(any(s.name == "--primary-color" for s in css_syms))
        self.assertTrue(any(s.name == ".btn-primary" for s in css_syms))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_parser_registry_custom_contributes_and_invalid_inputs(self):
        """ET-01: Verify ParserRegistry handles custom contributes_data overrides and gracefully handles malformed/invalid entries."""
        custom_contributes = {
            "languages": {
                "spice": {
                    "id": "spice",
                    "name": "Custom SPICE",
                    "extensions": [".sp", ".custom_spice"],
                    "mode": "custom",
                    "parser_entry": "ast_engine.parsers.spice_parser:SpiceParser",
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
        registry = ParserRegistry(register_defaults=True, contributes_data=custom_contributes)
        self.assertIn(".custom_spice", registry.get_supported_extensions())
        self.assertIn("broken_custom", registry.load_errors)

        # Parsing a file with .custom_spice extension should succeed via SpiceParser
        syms = registry.parse_file("test.custom_spice", ".SUBCKT AMP inp inn out\n.ENDS AMP\n", space="eda")
        self.assertEqual(len(syms), 1)
        self.assertEqual(syms[0].name, "AMP")

        # Parsing an unsupported extension or broken syntax should return empty list without crashing
        self.assertEqual(registry.parse_file("unknown.xyz", "random text", space="code"), [])
        py_ast_parser = PythonASTParser()
        self.assertEqual(py_ast_parser.parse("bad.py", "def broken_syntax(:\n", space="code"), [])
        self.mark_passed()
