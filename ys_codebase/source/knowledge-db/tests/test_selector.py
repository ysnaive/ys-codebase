"""
Unit tests for AST SymbolSelector (FR-04, EC-02).
"""

import os
import sys
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.schema import LanguageType, SymbolKind, UnifiedSymbol
from knowledge_db.selector import ParsedSelector, SymbolSelector


class TestSymbolSelector(YSCBTestCase):
    """
    全方位 AST 符號結構化選擇器單元測試套件
    """

    @require(Requirement.LOGIC)
    def test_selector_parsing_simple(self):
        """FT-04.1: 驗證純識別符與階層點分隔解析"""
        sel = SymbolSelector.parse("my_func")
        self.assertEqual(sel.identifier, "my_func")
        self.assertIsNone(sel.scope)
        self.assertIsNone(sel.target_kinds)
        self.assertFalse(sel.is_callable)

        sel_scoped = SymbolSelector.parse("MyClass.method_a")
        self.assertEqual(sel_scoped.identifier, "method_a")
        self.assertEqual(sel_scoped.scope, "MyClass")
        self.assertFalse(sel_scoped.is_callable)

        sel_nested = SymbolSelector.parse("pkg.module.MyClass.method_a")
        self.assertEqual(sel_nested.identifier, "method_a")
        self.assertEqual(sel_nested.scope, "pkg.module.MyClass")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_selector_parsing_callable(self):
        """FT-04.2: 驗證調用限定標記 `()` 解析"""
        sel = SymbolSelector.parse("run()")
        self.assertEqual(sel.identifier, "run")
        self.assertTrue(sel.is_callable)

        sel_scoped = SymbolSelector.parse("Worker.run()")
        self.assertEqual(sel_scoped.identifier, "run")
        self.assertEqual(sel_scoped.scope, "Worker")
        self.assertTrue(sel_scoped.is_callable)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_selector_parsing_kind_prefixes(self):
        """FT-04.3: 驗證 class, struct, interface, enum, fn 等類型前綴解析"""
        sel_class = SymbolSelector.parse("class Foo")
        self.assertEqual(sel_class.identifier, "Foo")
        self.assertEqual(sel_class.target_kinds, {"class"})
        self.assertFalse(sel_class.is_callable)

        sel_struct = SymbolSelector.parse("struct Point")
        self.assertEqual(sel_struct.identifier, "Point")
        self.assertEqual(sel_struct.target_kinds, {"struct"})

        sel_interface = SymbolSelector.parse("interface IService")
        self.assertEqual(sel_interface.identifier, "IService")
        self.assertEqual(sel_interface.target_kinds, {"interface"})

        sel_enum = SymbolSelector.parse("enum Color")
        self.assertEqual(sel_enum.identifier, "Color")
        self.assertEqual(sel_enum.target_kinds, {"enum"})

        sel_fn = SymbolSelector.parse("fn parse()")
        self.assertEqual(sel_fn.identifier, "parse")
        self.assertIn("function", sel_fn.target_kinds)
        self.assertTrue(sel_fn.is_callable)

        sel_def = SymbolSelector.parse("def setup")
        self.assertEqual(sel_def.identifier, "setup")
        self.assertIn("function", sel_def.target_kinds)

        sel_type = SymbolSelector.parse("type ID")
        self.assertEqual(sel_type.identifier, "ID")
        self.assertEqual(sel_type.target_kinds, {"type_alias"})

        sel_const = SymbolSelector.parse("const MAX_SIZE")
        self.assertEqual(sel_const.identifier, "MAX_SIZE")
        self.assertEqual(sel_const.target_kinds, {"constant"})

        sel_var = SymbolSelector.parse("var counter")
        self.assertEqual(sel_var.identifier, "counter")
        self.assertEqual(sel_var.target_kinds, {"variable"})

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_selector_combined_syntax(self):
        """FT-04.4: 驗證正交複合語法解析 (e.g. class Foo.bar(), struct Point.x)"""
        sel_method = SymbolSelector.parse("class Foo.bar()")
        self.assertEqual(sel_method.identifier, "bar")
        self.assertEqual(sel_method.scope, "Foo")
        self.assertEqual(sel_method.target_kinds, {"class"})
        self.assertTrue(sel_method.is_callable)

        sel_member = SymbolSelector.parse("struct Point.x")
        self.assertEqual(sel_member.identifier, "x")
        self.assertEqual(sel_member.scope, "Point")
        self.assertEqual(sel_member.target_kinds, {"struct"})

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_selector_matching_and_filtering(self):
        """FT-05: 驗證 SelectorMatcher 精準比對與符號過濾"""
        sym_class = UnifiedSymbol(
            id="c1",
            name="Engine",
            kind=SymbolKind.CLASS.value,
            file_path="src/engine.py",
            line_number=1,
            language=LanguageType.PYTHON.value,
            fqn="pkg.src.engine.Engine",
        )
        sym_func = UnifiedSymbol(
            id="f1",
            name="setup",
            kind=SymbolKind.FUNCTION.value,
            file_path="src/engine.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            fqn="pkg.src.engine.setup",
        )
        sym_method = UnifiedSymbol(
            id="m1",
            name="Engine.setup",
            kind=SymbolKind.METHOD.value,
            file_path="src/engine.py",
            line_number=20,
            language=LanguageType.PYTHON.value,
            fqn="pkg.src.engine.Engine.setup",
            parent_id="c1",
        )
        sym_var = UnifiedSymbol(
            id="v1",
            name="setup",
            kind=SymbolKind.VARIABLE.value,
            file_path="src/engine.py",
            line_number=30,
            language=LanguageType.PYTHON.value,
            fqn="pkg.src.engine.setup",
        )

        pool = [sym_class, sym_func, sym_method, sym_var]

        # 1. 搜尋 'class Engine' -> 僅匹配 sym_class
        matches = SymbolSelector.find_matches("class Engine", pool)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "c1")

        # 2. 搜尋 'Engine.setup()' -> 僅匹配 sym_method
        matches = SymbolSelector.find_matches("Engine.setup()", pool)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "m1")

        # 3. 搜尋 'fn setup()' -> 匹配 sym_func 與 sym_method (皆為 callable)，不包含 sym_var
        matches = SymbolSelector.find_matches("fn setup()", pool)
        matched_ids = {m.id for m in matches}
        self.assertIn("f1", matched_ids)
        self.assertIn("m1", matched_ids)
        self.assertNotIn("v1", matched_ids)

        # 4. 搜尋 'var setup' -> 僅匹配 sym_var
        matches = SymbolSelector.find_matches("var setup", pool)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "v1")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_invalid_syntax_graceful_fallback(self):
        """ET-01: 邊界測試 - 空字串或非正規語法安全回退不崩潰"""
        sel_empty = SymbolSelector.parse("")
        self.assertEqual(sel_empty.identifier, "")

        sel_weird = SymbolSelector.parse("class Foo...bar()()()")
        self.assertIsNotNone(sel_weird)
        self.assertTrue(sel_weird.is_callable)

        # 比對空符號池
        matches = SymbolSelector.find_matches("not_found", [])
        self.assertEqual(matches, [])

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
