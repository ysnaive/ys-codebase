"""
knowledge-db 解析器深度與原子 Item 化單元測試 (test_parsers_deep.py)
驗證 FT-01, FT-02, FT-03, FT-04
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.parsers.cpp_parser import CppParser
from knowledge_db.parsers.csharp_parser import CSharpParser
from knowledge_db.parsers.markdown_parser import MarkdownParser
from knowledge_db.parsers.python_parser import PythonParser
from knowledge_db.schema import LanguageType, SymbolKind


class TestPythonParserDeep(YSCBTestCase):
    """FT-01: Python 解析器方法物化與精確 end_line 測試"""

    def setUp(self):
        super().setUp()
        self.parser = PythonParser()

    @require(Requirement.LOGIC)
    def test_python_methods_promoted_to_symbols(self):
        code = '''
class ServiceRegistry:
    """服務註冊中心"""

    def __init__(self, name: str):
        self.name = name

    def register(self, service_id: str, handler: callable) -> bool:
        """註冊服務處理器"""
        return True

def standalone_func(x: int) -> int:
    """頂層獨立函式"""
    return x * 2
'''
        symbols = self.parser.parse("src/service.py", code, space="test")
        sym_map = {s.name: s for s in symbols}

        # 1. 類別符號存在
        self.assertIn("ServiceRegistry", sym_map)
        cls_sym = sym_map["ServiceRegistry"]
        self.assertEqual(cls_sym.kind, SymbolKind.CLASS.value)
        self.assertEqual(cls_sym.line_number, 2)
        self.assertGreaterEqual(cls_sym.end_line, 10)

        # 2. 類別方法提升為一級 UnifiedSymbol (FR-01)
        self.assertIn("ServiceRegistry.__init__", sym_map)
        init_sym = sym_map["ServiceRegistry.__init__"]
        self.assertEqual(init_sym.kind, SymbolKind.METHOD.value)
        self.assertEqual(init_sym.line_number, 5)
        self.assertGreaterEqual(init_sym.end_line, 6)
        self.assertEqual(init_sym.metadata.get("parent_scope"), "ServiceRegistry")

        self.assertIn("ServiceRegistry.register", sym_map)
        reg_sym = sym_map["ServiceRegistry.register"]
        self.assertEqual(reg_sym.kind, SymbolKind.METHOD.value)
        self.assertEqual(reg_sym.line_number, 8)
        self.assertGreaterEqual(reg_sym.end_line, 10)
        self.assertIn("service_id", reg_sym.signature)

        # 3. 頂層函式
        self.assertIn("standalone_func", sym_map)
        fn_sym = sym_map["standalone_func"]
        self.assertEqual(fn_sym.kind, SymbolKind.FUNCTION.value)
        self.assertEqual(fn_sym.line_number, 12)
        self.assertGreaterEqual(fn_sym.end_line, 14)


class TestCppParserDeep(YSCBTestCase):
    """FT-02 & FT-03: C++ 多行簽名累積狀態機、Namespace 堆疊與 Class 作用域"""

    def setUp(self):
        super().setUp()
        self.parser = CppParser()

    @require(Requirement.LOGIC)
    def test_cpp_multiline_signature(self):
        code = '''
#include <iostream>

EntityComponent* GetOrCreateComponent(
    EntityId id,
    ComponentType type,
    bool createIfMissing = true
);

void NormalFunc(int x);
'''
        symbols = self.parser.parse("src/component.cpp", code, space="test")
        sym_map = {s.name: s for s in symbols}

        self.assertIn("GetOrCreateComponent", sym_map)
        multi_sym = sym_map["GetOrCreateComponent"]
        self.assertEqual(multi_sym.kind, SymbolKind.FUNCTION.value)
        self.assertEqual(multi_sym.line_number, 4)
        self.assertEqual(multi_sym.end_line, 8)
        self.assertIn("EntityId id", multi_sym.signature)
        self.assertIn("bool createIfMissing = true", multi_sym.signature)

        self.assertIn("NormalFunc", sym_map)

    @require(Requirement.LOGIC)
    def test_cpp_namespace_and_class_scope(self):
        code = '''
namespace Engine {
namespace Rendering {

class Renderer {
public:
    virtual void Initialize(
        int width,
        int height
    ) override;

    void Shutdown();
};

} // namespace Rendering
} // namespace Engine
'''
        symbols = self.parser.parse("src/renderer.h", code, space="test")
        sym_map = {s.name: s for s in symbols}

        # 1. 完整 Qualified Class Name
        self.assertIn("Engine::Rendering::Renderer", sym_map)
        cls_sym = sym_map["Engine::Rendering::Renderer"]
        self.assertEqual(cls_sym.kind, SymbolKind.CLASS.value)

        # 2. 類別成員方法正確識別為 METHOD 並帶出 Qualified Name
        self.assertIn("Engine::Rendering::Renderer::Initialize", sym_map)
        init_m = sym_map["Engine::Rendering::Renderer::Initialize"]
        self.assertEqual(init_m.kind, SymbolKind.METHOD.value)
        self.assertEqual(init_m.metadata.get("parent_scope"), "Renderer")
        self.assertEqual(init_m.line_number, 7)
        self.assertEqual(init_m.end_line, 10)

        self.assertIn("Engine::Rendering::Renderer::Shutdown", sym_map)
        shut_m = sym_map["Engine::Rendering::Renderer::Shutdown"]
        self.assertEqual(shut_m.kind, SymbolKind.METHOD.value)


class TestCSharpAndMarkdownParser(YSCBTestCase):
    """FT-04: C# 與 Markdown end_line 邊界座標測試"""

    @require(Requirement.LOGIC)
    def test_csharp_end_line(self):
        parser = CSharpParser()
        code = '''
namespace Game.Core
{
    public class PlayerController
    {
        public int Health { get; set; }

        public void Move(float x, float y)
        {
            // move logic
        }
    }
}
'''
        symbols = parser.parse("src/Player.cs", code, space="test")
        self.assertTrue(len(symbols) >= 3)
        for s in symbols:
            self.assertGreaterEqual(s.end_line, s.line_number)

    @require(Requirement.LOGIC)
    def test_markdown_end_line(self):
        parser = MarkdownParser()
        doc = '''# Introduction
This is an intro paragraph.
Line 2 of intro.

## Features
- Feature 1
- Feature 2

| Col 1 | Col 2 |
| ----- | ----- |
| A     | B     |
'''
        symbols = parser.parse("docs/guide.md", doc, space="test")
        sym_map = {s.name: s for s in symbols}

        self.assertIn("Introduction", sym_map)
        intro = sym_map["Introduction"]
        self.assertEqual(intro.line_number, 1)
        self.assertEqual(intro.end_line, 4)

        self.assertIn("Features", sym_map)
        feat = sym_map["Features"]
        self.assertEqual(feat.line_number, 5)
        self.assertGreaterEqual(feat.end_line, 8)
