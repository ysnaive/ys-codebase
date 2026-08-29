"""
Unit Tests for knowledge-db Multi-Language Parsers and ParserRegistry.
"""

import os
from pathlib import Path
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.parsers import (
    BaseParser,
    CppParser,
    CSharpParser,
    MarkdownParser,
    ParserRegistry,
    PythonParser,
)
from knowledge_db.schema import LanguageType, SymbolKind, UnifiedSymbol


class TestParsers(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_01_parser_registry_dispatch_and_priority(self):
        """FT-01: 驗證 ParserRegistry 動態註冊、副檔名分發與優先權 (EC-02)"""
        registry = ParserRegistry(register_defaults=True)

        # 1. 預設解析器匹配
        py_parser = registry.get_parser("module.py")
        self.assertIsInstance(py_parser, PythonParser)

        md_parser = registry.get_parser("docs/README.md")
        self.assertIsInstance(md_parser, MarkdownParser)

        cpp_parser = registry.get_parser("src/engine.hpp")
        self.assertIsInstance(cpp_parser, CppParser)

        cs_parser = registry.get_parser("Models/User.cs")
        self.assertIsInstance(cs_parser, CSharpParser)

        # 2. 未知副檔名安全回傳 None 與空符號清單 (EC-02)
        unknown_parser = registry.get_parser("data.xyz_unknown")
        self.assertIsNone(unknown_parser)
        symbols = registry.parse_file("data.xyz", "some content", "test_space")
        self.assertEqual(symbols, [])

        # 3. 自訂解析器優先權覆蓋
        class CustomPythonParser(BaseParser):
            def can_parse(self, file_path):
                return str(file_path).endswith(".py")

            def parse(self, file_path, content, space):
                return []

        custom = CustomPythonParser()
        registry.register_parser(custom, priority=200)
        self.assertEqual(registry.get_parser("test.py"), custom)

    @require(Requirement.LOGIC)
    def test_ft_02_python_parser_ast_extraction(self):
        """FT-02: 驗證 PythonParser AST 語法樹類別、函式、成員、簽名與 Docstring 提取"""
        parser = PythonParser()
        code = '''"""Module docstring"""
from typing import Optional

class BaseEngine:
    """基礎引擎類別"""
    engine_version: str = "1.0.0"

    def __init__(self, name: str = "default"):
        """初始化"""
        self.name = name

    async def execute_task(self, task_id: int) -> bool:
        """非同步執行任務"""
        return True

def standalone_func(x: int, y: int = 10) -> int:
    """獨立計算函式"""
    return x + y
'''
        symbols = parser.parse("source/engine.py", code, "test_space")
        sym_map = {s.name: s for s in symbols}
        self.assertEqual(len(symbols), 4)  # BaseEngine 類別, __init__, execute_task 與 standalone_func 函式

        # 類別驗證
        self.assertIn("BaseEngine", sym_map)
        cls_sym = sym_map["BaseEngine"]
        self.assertEqual(cls_sym.name, "BaseEngine")
        self.assertEqual(cls_sym.kind, SymbolKind.CLASS.value)
        self.assertEqual(cls_sym.language, LanguageType.PYTHON.value)
        self.assertEqual(cls_sym.docstring, "基礎引擎類別")
        self.assertEqual(len(cls_sym.members), 3)  # engine_version, __init__, execute_task

        init_mem = [m for m in cls_sym.members if m.name == "__init__"][0]
        self.assertEqual(init_mem.docstring, "初始化")

        exec_mem = [m for m in cls_sym.members if m.name == "execute_task"][0]
        self.assertIn("async def execute_task", exec_mem.signature)
        self.assertEqual(exec_mem.visibility, "public")

        # 獨立方法符號驗證 (FR-01)
        self.assertIn("BaseEngine.__init__", sym_map)
        self.assertIn("BaseEngine.execute_task", sym_map)

        # 獨立函式驗證
        self.assertIn("standalone_func", sym_map)
        func_sym = sym_map["standalone_func"]
        self.assertEqual(func_sym.name, "standalone_func")
        self.assertEqual(func_sym.kind, SymbolKind.FUNCTION.value)
        self.assertEqual(func_sym.docstring, "獨立計算函式")
        self.assertIn("def standalone_func", func_sym.signature)

    @require(Requirement.LOGIC)
    def test_ft_03_python_parser_syntax_error_resilience(self):
        """FT-03: 驗證 PythonParser 面對語法錯誤時安全降級不崩潰 (EC-01)"""
        parser = PythonParser()
        broken_code = "def broken_func( this is invalid python syntax {;;"
        symbols = parser.parse("source/broken.py", broken_code, "test_space")
        self.assertEqual(symbols, [])

    @require(Requirement.LOGIC)
    def test_ft_04_markdown_parser_headings_and_tables(self):
        """FT-04: 驗證 MarkdownParser 標題階層、表格與段落摘要提取 (EC-03)"""
        parser = MarkdownParser()
        doc = """# 主標題 H1

這是 H1 的段落內容介紹。

## 次標題 H2

| 欄位A | 欄位B | 欄位C |
| :--- | :---: | ---: |
| 值1  | 值2  | 值3  |
| 值4  | 值5  | 值6  |

### 小節標題 H3

這裡是 H3 的詳細技術細節。
"""
        symbols = parser.parse("docs/guide.md", doc, "test_space")
        self.assertGreaterEqual(len(symbols), 3)

        h1_sym = [s for s in symbols if s.kind == SymbolKind.DOC_HEADING_1.value][0]
        self.assertEqual(h1_sym.name, "主標題 H1")
        self.assertIn("這是 H1 的段落內容介紹", h1_sym.docstring)

        table_sym = [s for s in symbols if s.kind == SymbolKind.DOC_TABLE.value][0]
        self.assertIn("欄位A", table_sym.name)
        self.assertIn("值1", table_sym.docstring)

        # 測試無標題檔案降級 (EC-03)
        no_heading_doc = "純純的一段文字段落，沒有任何 markdown 標題。\n第二行內容。"
        fallback_syms = parser.parse("notes.txt", no_heading_doc, "test_space")
        self.assertEqual(len(fallback_syms), 1)
        self.assertEqual(fallback_syms[0].kind, SymbolKind.DOC_SECTION.value)

    @require(Requirement.LOGIC)
    def test_ft_05_cpp_parser_classes_and_macros(self):
        """FT-05: 驗證 CppParser 類別、巨集、列舉與 Doxygen 註解提取"""
        parser = CppParser()
        cpp_code = """
/// PID 控制器計算巨集
#define PID_CALC(p, i, d) ((p) * 1.0f + (i) * 0.1f)

enum class ControllerState {
    IDLE,
    RUNNING,
    ERROR
};

/// 核心控制器類別
class PIDController : public BaseController {
public:
    /// 重設控制器內部狀態
    void Reset();
};
"""
        symbols = parser.parse("src/controller.hpp", cpp_code, "test_space")
        self.assertGreaterEqual(len(symbols), 3)

        macro_sym = [s for s in symbols if s.kind == SymbolKind.MACRO.value][0]
        self.assertEqual(macro_sym.name, "PID_CALC")
        self.assertEqual(macro_sym.docstring, "PID 控制器計算巨集")

        cls_sym = [s for s in symbols if s.kind == SymbolKind.CLASS.value][0]
        self.assertEqual(cls_sym.name, "PIDController")
        self.assertEqual(cls_sym.docstring, "核心控制器類別")

        enum_sym = [s for s in symbols if s.kind == SymbolKind.ENUM.value][0]
        self.assertEqual(enum_sym.name, "ControllerState")

    @require(Requirement.LOGIC)
    def test_ft_06_csharp_parser_classes_and_xml_doc(self):
        """FT-06: 驗證 CSharpParser 命名空間、類別、介面與 XML Doc 提取"""
        parser = CSharpParser()
        cs_code = """
namespace App.Services {
    /// <summary>
    /// 使用者管理服務介面
    /// </summary>
    public interface IUserService {
        void CreateUser(string name);
    }

    /// <summary>
    /// 使用者服務實作類別
    /// </summary>
    public class UserService : IUserService {
        public string ServiceName { get; set; }

        public void CreateUser(string name) {
        }
    }
}
"""
        symbols = parser.parse("Services/UserService.cs", cs_code, "test_space")
        self.assertGreaterEqual(len(symbols), 2)

        iface_sym = [s for s in symbols if s.kind == SymbolKind.INTERFACE.value][0]
        self.assertEqual(iface_sym.name, "App.Services.IUserService")
        self.assertEqual(iface_sym.docstring, "使用者管理服務介面")

        cls_sym = [s for s in symbols if s.kind == SymbolKind.CLASS.value][0]
        self.assertEqual(cls_sym.name, "App.Services.UserService")
        self.assertEqual(cls_sym.docstring, "使用者服務實作類別")
