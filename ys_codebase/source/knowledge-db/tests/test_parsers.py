"""
Unit and Integration Tests for knowledge-db Multi-Language AST Parsers and ParserRegistry.
Unified Suite consolidating test_parsers.py, test_spice_parser.py, and test_web_parsers.py.
"""

import os
from pathlib import Path
import sys
import unittest

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
    CssParser,
    HtmlParser,
    JsTsParser,
    MarkdownParser,
    ParserRegistry,
    PythonParser,
    SpiceParser,
)
from knowledge_db.schema import LanguageType, SymbolKind, UnifiedSymbol


class TestParsers(YSCBTestCase):
    """多語言語意解析器 (Python, C/C++, C#, Markdown) 與 ParserRegistry 整合單元測試。"""

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

        self.mark_passed()

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
        self.assertEqual(len(symbols), 4)

        # 類別驗證
        self.assertIn("BaseEngine", sym_map)
        cls_sym = sym_map["BaseEngine"]
        self.assertEqual(cls_sym.name, "BaseEngine")
        self.assertEqual(cls_sym.kind, SymbolKind.CLASS.value)
        self.assertEqual(cls_sym.language, LanguageType.PYTHON.value)
        self.assertEqual(cls_sym.docstring, "基礎引擎類別")
        self.assertEqual(len(cls_sym.members), 3)

        init_mem = [m for m in cls_sym.members if m.name == "__init__"][0]
        self.assertEqual(init_mem.docstring, "初始化")

        exec_mem = [m for m in cls_sym.members if m.name == "execute_task"][0]
        self.assertIn("async def execute_task", exec_mem.signature)
        self.assertEqual(exec_mem.visibility, "public")

        # 獨立方法符號驗證
        self.assertIn("BaseEngine.__init__", sym_map)
        self.assertIn("BaseEngine.execute_task", sym_map)

        # 獨立函式驗證
        self.assertIn("standalone_func", sym_map)
        func_sym = sym_map["standalone_func"]
        self.assertEqual(func_sym.name, "standalone_func")
        self.assertEqual(func_sym.kind, SymbolKind.FUNCTION.value)
        self.assertEqual(func_sym.docstring, "獨立計算函式")
        self.assertIn("def standalone_func", func_sym.signature)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_python_parser_syntax_error_resilience(self):
        """FT-03: 驗證 PythonParser 面對語法錯誤時安全降級不崩潰 (EC-01)"""
        parser = PythonParser()
        broken_code = "def broken_func( this is invalid python syntax {;;"
        symbols = parser.parse("source/broken.py", broken_code, "test_space")
        self.assertEqual(symbols, [])

        self.mark_passed()

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

        # 測試無標題檔案降級
        no_heading_doc = "純純的一段文字段落，沒有任何 markdown 標題。\n第二行內容。"
        fallback_syms = parser.parse("notes.txt", no_heading_doc, "test_space")
        self.assertEqual(len(fallback_syms), 1)
        self.assertEqual(fallback_syms[0].kind, SymbolKind.DOC_SECTION.value)

        self.mark_passed()

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

        self.mark_passed()

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

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cpp_multiline_signature_and_scope(self):
        """驗證 C++ 多行簽名累積狀態機、Namespace 堆疊與 Class 作用域。"""
        parser = CppParser()
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
        symbols = parser.parse("src/renderer.h", code, space="test")
        sym_map = {s.name: s for s in symbols}

        self.assertIn("Engine::Rendering::Renderer", sym_map)
        cls_sym = sym_map["Engine::Rendering::Renderer"]
        self.assertEqual(cls_sym.kind, SymbolKind.CLASS.value)

        self.assertIn("Engine::Rendering::Renderer::Initialize", sym_map)
        init_m = sym_map["Engine::Rendering::Renderer::Initialize"]
        self.assertEqual(init_m.kind, SymbolKind.METHOD.value)
        self.assertEqual(init_m.metadata.get("parent_scope"), "Renderer")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_csharp_and_markdown_end_line_coordinates(self):
        """驗證 C# 與 Markdown end_line 邊界座標精確性。"""
        cs_parser = CSharpParser()
        cs_code = '''
namespace Game.Core {
    public class PlayerController {
        public void Move(float x, float y) {}
    }
}
'''
        cs_symbols = cs_parser.parse("src/Player.cs", cs_code, space="test")
        for s in cs_symbols:
            self.assertGreaterEqual(s.end_line, s.line_number)

        md_parser = MarkdownParser()
        doc = '''# Introduction
This is an intro paragraph.

## Features
- Feature 1
'''
        md_symbols = md_parser.parse("docs/guide.md", doc, space="test")
        intro = [s for s in md_symbols if s.name == "Introduction"][0]
        self.assertEqual(intro.line_number, 1)
        self.assertGreaterEqual(intro.end_line, 2)

        self.mark_passed()


class TestSpiceParser(YSCBTestCase):
    """SPICE 網表解析器 (SpiceParser) 完整功能與邊界測試套件。"""

    def setUp(self):
        super().setUp()
        self.parser = SpiceParser()

    @require(Requirement.LOGIC)
    def test_ft_01_can_parse_extensions(self):
        """FT-01: 驗證 can_parse 支援 .cir, .sp, .spice, .net, .cdl 及其大小寫變形"""
        valid_files = [
            "circuit.cir",
            "netlist.sp",
            "models.SPICE",
            "top.Net",
            "layout.CDL",
            "path/to/subckt.cir",
        ]
        for f in valid_files:
            self.assertTrue(self.parser.can_parse(f), f"Expected True for {f}")

        invalid_files = [
            "code.py",
            "doc.md",
            "header.h",
            "data.json",
            "circuit.v",
            "",
        ]
        for f in invalid_files:
            self.assertFalse(self.parser.can_parse(f), f"Expected False for {f}")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_line_continuation_and_docstring(self):
        """FT-02: 驗證 Stage 1 行聚合器正確合併 '+' 接續行並提取 Docstring"""
        content = """* Standard CMOS Inverter
* High speed version with parameterized widths
.SUBCKT INV_X1 IN OUT VDD VSS
+ PARAMS: WP=2u
+ WN=1u L=0.18u
M1 OUT IN VDD VDD PMOS W={WP} L={L}
M2 OUT IN VSS VSS NMOS W={WN} L={L}
.ENDS INV_X1
"""
        symbols = self.parser.parse("inverter.cir", content, "spice_space")
        self.assertEqual(len(symbols), 1)
        inv = symbols[0]

        self.assertEqual(inv.name, "INV_X1")
        self.assertEqual(inv.kind, SymbolKind.CLASS.value)
        self.assertEqual(inv.language, LanguageType.SPICE.value)
        self.assertEqual(inv.line_number, 3)
        self.assertEqual(inv.end_line, 8)
        self.assertIn("Standard CMOS Inverter", inv.docstring)
        self.assertIn("High speed version", inv.docstring)
        self.assertIn("PARAMS: WP=2u WN=1u L=0.18u", inv.signature)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_dot_commands_extraction(self):
        """FT-03: 驗證 .subckt, .model, .param, .include, .lib, .global 點指令符號提取"""
        content = """* Global Models and Directives
.INCLUDE "tsmc18.lib"
.LIB "corners.lib" TT
.GLOBAL VDD VSS CLK
.PARAM VDD_VAL=1.8V VSS_VAL=0V TEMP_NOM=27

* NMOS Standard Model
.MODEL NMOS_18 NMOS (LEVEL=1 VTO=0.7 KP=1e-4)

* PMOS Standard Model
.MODEL PMOS_18 PMOS (LEVEL=1 VTO=-0.7 KP=4e-5)
"""
        symbols = self.parser.parse("top.sp", content, "top_space")

        names = {s.name for s in symbols}
        self.assertIn("tsmc18.lib", names)
        self.assertIn("corners.lib", names)
        self.assertIn("VDD", names)
        self.assertIn("VSS", names)
        self.assertIn("CLK", names)
        self.assertIn("VDD_VAL", names)
        self.assertIn("VSS_VAL", names)
        self.assertIn("TEMP_NOM", names)
        self.assertIn("NMOS_18", names)
        self.assertIn("PMOS_18", names)

        nmos = next(s for s in symbols if s.name == "NMOS_18")
        self.assertEqual(nmos.kind, SymbolKind.STRUCT.value)
        self.assertEqual(nmos.language, LanguageType.SPICE.value)
        self.assertIn("NMOS Standard Model", nmos.docstring)

        param_vdd = next(s for s in symbols if s.name == "VDD_VAL")
        self.assertEqual(param_vdd.kind, SymbolKind.VARIABLE.value)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_subckt_members_and_instances(self):
        """FT-04: 驗證子電路內部 members 與頂層 X 實例提取"""
        content = """* NAND2 Gate Definition
.SUBCKT NAND2_X1 A B Y VDD VSS
.PARAM WP=2u WN=1u
.MODEL LOCAL_DIO D (IS=1e-14)
MP1 Y A VDD VDD PMOS W=WP L=0.18u
MP2 Y B VDD VDD PMOS W=WP L=0.18u
MN1 Y A MID VSS NMOS W=WN L=0.18u
MN2 MID B VSS VSS NMOS W=WN L=0.18u
X_DECAP VDD VSS CAP_DECAP
.ENDS NAND2_X1

* Top level circuit instantiations
X_GATE_1 IN1 IN2 OUT VDD VSS NAND2_X1
X_GATE_2 OUT IN3 FINAL VDD VSS NAND2_X1
V_VDD VDD 0 DC 1.8V
"""
        symbols = self.parser.parse("nand_tree.cir", content, "nand_space")

        top_names = {s.name for s in symbols}
        self.assertIn("NAND2_X1", top_names)
        self.assertIn("X_GATE_1", top_names)
        self.assertIn("X_GATE_2", top_names)
        self.assertIn("V_VDD", top_names)

        nand_sym = next(s for s in symbols if s.name == "NAND2_X1")
        member_names = {m.name for m in nand_sym.members}
        self.assertIn("WP", member_names)
        self.assertIn("LOCAL_DIO", member_names)
        self.assertIn("MP1", member_names)
        self.assertIn("MP2", member_names)
        self.assertIn("MN1", member_names)
        self.assertIn("MN2", member_names)
        self.assertIn("X_DECAP", member_names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_registry_integration(self):
        """FT-05: 驗證 ParserRegistry 動態分發與 SPICE 符號解析整合"""
        registry = ParserRegistry(register_defaults=True)
        p = registry.get_parser("circuit.cdl")
        self.assertIsInstance(p, SpiceParser)

        content = ".SUBCKT BUFFER_X2 IN OUT VDD VSS\n.ENDS BUFFER_X2\n"
        symbols = registry.parse_file("circuit.cdl", content, "proj_space")
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0].name, "BUFFER_X2")
        self.assertEqual(symbols[0].language, LanguageType.SPICE.value)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_continuation_with_comments_and_blank_lines(self):
        """ET-01: 驗證跨多行 '+' 接續夾雜空行與行尾註解之穩定合併"""
        content = """* Multi-line parameterized amplifier
.SUBCKT OPAMP_DIFF INP INN OUT
+ VDD ; Power positive
+ VSS $ Power negative
+ PARAMS: GAIN='100k'
+ GBW='10MEG' ; 10MHz GBW
M1 OUT INP VDD VDD PMOS
.ENDS OPAMP_DIFF
"""
        symbols = self.parser.parse("opamp.cir", content, "diff_space")
        self.assertEqual(len(symbols), 1)
        opamp = symbols[0]
        self.assertEqual(opamp.name, "OPAMP_DIFF")
        self.assertEqual(opamp.line_number, 2)
        self.assertEqual(opamp.end_line, 8)
        self.assertIn("PARAMS: GAIN='100k' GBW='10MEG'", opamp.signature)
        self.assertNotIn("Power positive", opamp.signature)
        self.assertNotIn("Power negative", opamp.signature)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_unclosed_subcircuit_fallback(self):
        """ET-02: 驗證未閉合 .subckt 網表自動防禦封裝至檔案末端"""
        content = """* Incomplete Subcircuit (Truncated)
.SUBCKT BROKEN_SUBCKT A B Y
M1 Y A VDD VDD PMOS
M2 Y B VSS VSS NMOS
"""
        symbols = self.parser.parse("broken.cir", content, "broken_space")
        self.assertEqual(len(symbols), 1)
        broken = symbols[0]
        self.assertEqual(broken.name, "BROKEN_SUBCKT")
        self.assertEqual(broken.line_number, 2)
        self.assertEqual(broken.end_line, 4)
        self.assertTrue(broken.metadata.get("unclosed"))
        self.assertEqual(len(broken.members), 2)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_mixed_dialect_comments_and_case(self):
        """ET-03: 驗證混合方言註解 (*, ;, $) 與大小寫混雜關鍵字之正規化"""
        content = """* Mixed Dialect Netlist
.subckt MixedGate_X1 in out vdd vss ; ngspice style
.Param R_VAL = 10k $ HSPICE comment
.model Diode_Mod D (Is=1e-15)
R1 in mid {R_VAL} ; inline comment
X_inner mid out Inverter_Core $ HSPICE comment
.Ends MixedGate_X1
"""
        symbols = self.parser.parse("mixed.sp", content, "mixed_space")
        self.assertEqual(len(symbols), 1)
        mg = symbols[0]
        self.assertEqual(mg.name, "MixedGate_X1")
        self.assertEqual(mg.kind, SymbolKind.CLASS.value)

        member_names = {m.name for m in mg.members}
        self.assertIn("R_VAL", member_names)
        self.assertIn("Diode_Mod", member_names)
        self.assertIn("R1", member_names)
        self.assertIn("X_inner", member_names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_04_empty_and_comment_only_files(self):
        """ET-04: 驗證空檔案、首行標題或純註解網表回傳空清單 []"""
        self.assertEqual(self.parser.parse("empty.cir", "", "empty_space"), [])
        self.assertEqual(self.parser.parse("blank.cir", "   \n\t\n  ", "blank_space"), [])

        comment_only = """* Title: Inverter Testbench
* Author: Circuit Designer
* Date: 2026-08-29
* Description: Only comment lines in this file.
"""
        self.assertEqual(self.parser.parse("comments.cir", comment_only, "comment_space"), [])

        self.mark_passed()


class TestWebParsers(YSCBTestCase):
    """JavaScript/TypeScript, HTML, CSS 解譯器功能與邊界測試套件。"""

    def setUp(self):
        super().setUp()
        self.js_ts_parser = JsTsParser()
        self.html_parser = HtmlParser()
        self.css_parser = CssParser()

    @require(Requirement.LOGIC)
    def test_ft_01_language_type_enum(self):
        """FT-01: 驗證 LanguageType 包含 Web 語言列舉"""
        self.assertEqual(LanguageType.JAVASCRIPT.value, "javascript")
        self.assertEqual(LanguageType.TYPESCRIPT.value, "typescript")
        self.assertEqual(LanguageType.HTML.value, "html")
        self.assertEqual(LanguageType.CSS.value, "css")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_js_ts_parser(self):
        """FT-02: 驗證 JsTsParser 提取類別、介面、型別、函式、箭頭函式、方法與 JSDoc"""
        valid_exts = ["app.js", "comp.jsx", "index.ts", "widget.tsx", "module.mjs", "config.cjs"]
        for f in valid_exts:
            self.assertTrue(self.js_ts_parser.can_parse(f))

        ts_content = """/**
 * UserService Interface
 */
export interface IUserService {
  getUser(id: string): User;
}

/**
 * User Data Model
 */
export class UserService extends BaseService implements IUserService {
  /**
   * Fetch user by ID
   */
  async getUser(id: string): Promise<User> {
    return fetchUser(id);
  }
}

export type UserID = string;

export enum UserRole {
  ADMIN = "admin",
  USER = "user"
}

/**
 * Global helper function
 */
export async function fetchUser(id: string) {
  return {};
}

export const processUser = (u: any) => {
  return u;
};
"""
        symbols = self.js_ts_parser.parse("user.ts", ts_content, "web_space")
        names = {s.name for s in symbols}
        self.assertIn("IUserService", names)
        self.assertIn("UserService", names)
        self.assertIn("UserID", names)
        self.assertIn("UserRole", names)
        self.assertIn("fetchUser", names)
        self.assertIn("processUser", names)

        user_service = next(s for s in symbols if s.name == "UserService")
        self.assertEqual(user_service.kind, SymbolKind.CLASS.value)
        self.assertEqual(user_service.language, LanguageType.TYPESCRIPT.value)
        self.assertIn("User Data Model", user_service.docstring)
        member_names = {m.name for m in user_service.members}
        self.assertIn("getUser", member_names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_html_parser(self):
        """FT-03: 驗證 HtmlParser 提取 title, h1~h6, id 選擇器元素, 語意區塊與 HTML 註解"""
        self.assertTrue(self.html_parser.can_parse("index.html"))
        self.assertTrue(self.html_parser.can_parse("page.htm"))

        html_content = """<!DOCTYPE html>
<html>
<head>
    <!-- Main Web Page Title -->
    <title>My Web Dashboard</title>
</head>
<body>
    <!-- Header Component -->
    <header id="main-header">
        <h1>Dashboard Title</h1>
    </header>

    <!-- Main Content Area -->
    <main id="app-content">
        <h2>Analytics Overview</h2>
        <section id="chart-section">
            <h3>Revenue Chart</h3>
        </section>
    </main>
</body>
</html>
"""
        symbols = self.html_parser.parse("index.html", html_content, "html_space")
        names = {s.name for s in symbols}
        self.assertIn("My Web Dashboard", names)
        self.assertIn("Dashboard Title", names)
        self.assertIn("#main-header", names)
        self.assertIn("#app-content", names)
        self.assertIn("Analytics Overview", names)
        self.assertIn("#chart-section", names)
        self.assertIn("Revenue Chart", names)

        title_sym = next(s for s in symbols if s.name == "My Web Dashboard")
        self.assertEqual(title_sym.kind, SymbolKind.DOC_HEADING_1.value)
        self.assertEqual(title_sym.language, LanguageType.HTML.value)
        self.assertIn("Main Web Page Title", title_sym.docstring)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_css_parser(self):
        """FT-04: 驗證 CssParser 提取 Class/ID 選擇器、CSS/SASS/LESS 變數與 @keyframes"""
        self.assertTrue(self.css_parser.can_parse("styles.css"))
        self.assertTrue(self.css_parser.can_parse("main.scss"))
        self.assertTrue(self.css_parser.can_parse("theme.less"))

        css_content = """/* Primary Theme Variables */
:root {
  --primary-color: #007bff;
  --secondary-color: #6c757d;
}

$sass-bg: #f8f9fa;
@less-font: 14px;

/* Card Component Styles */
.card-container {
  display: flex;
}

#main-sidebar {
  width: 250px;
}

/* Slide in animation */
@keyframes slideIn {
  from { transform: translateX(-100%); }
  to { transform: translateX(0); }
}
"""
        symbols = self.css_parser.parse("styles.css", css_content, "css_space")
        names = {s.name for s in symbols}
        self.assertIn("--primary-color", names)
        self.assertIn("--secondary-color", names)
        self.assertIn("$sass-bg", names)
        self.assertIn("@less-font", names)
        self.assertIn(".card-container", names)
        self.assertIn("#main-sidebar", names)
        self.assertIn("@keyframes slideIn", names)

        card_sym = next(s for s in symbols if s.name == ".card-container")
        self.assertEqual(card_sym.kind, SymbolKind.CLASS.value)
        self.assertEqual(card_sym.language, LanguageType.CSS.value)
        self.assertIn("Card Component Styles", card_sym.docstring)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_parser_registry_integration(self):
        """FT-05: 驗證 ParserRegistry 動態分發與 Web 解析器整合"""
        registry = ParserRegistry(register_defaults=True)

        self.assertIsInstance(registry.get_parser("index.ts"), JsTsParser)
        self.assertIsInstance(registry.get_parser("page.html"), HtmlParser)
        self.assertIsInstance(registry.get_parser("style.scss"), CssParser)

        ts_symbols = registry.parse_file("test.ts", "class TestClass {}", "reg_space")
        self.assertEqual(len(ts_symbols), 1)
        self.assertEqual(ts_symbols[0].name, "TestClass")
        self.assertEqual(ts_symbols[0].language, LanguageType.TYPESCRIPT.value)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_js_template_literals_edge_case(self):
        """ET-01: 驗證 JsTsParser 防範多行樣板字串 (`` `...` ``) 內之關鍵字干擾 (EC-01)"""
        content = """
const codeSnippet = `
class FakeClass {
  function fakeFunc() {}
}
`;

export class RealClass {
  realMethod() {}
}
"""
        symbols = self.js_ts_parser.parse("template.js", content, "js_space")
        names = {s.name for s in symbols}
        self.assertIn("RealClass", names)
        self.assertNotIn("FakeClass", names)
        self.assertNotIn("fakeFunc", names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_tsx_generics_edge_case(self):
        """ET-02: 驗證 TSX / JSX 標籤與 TS 泛型 `<T>` 混淆防禦 (EC-02)"""
        content = """
export function GenericComp<T extends object>(props: T) {
  return <div className="box">Content</div>;
}
"""
        symbols = self.js_ts_parser.parse("comp.tsx", content, "tsx_space")
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0].name, "GenericComp")
        self.assertEqual(symbols[0].kind, SymbolKind.FUNCTION.value)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_html_malformed_edge_case(self):
        """ET-03: 驗證 HtmlParser 對自閉合標籤與缺損標籤之容錯性 (EC-03)"""
        content = """
<img src="logo.png" alt="logo">
<br>
<input type="text" id="username-input">
<div id="unclosed-div">
  <h1>Valid Heading
"""
        symbols = self.html_parser.parse("malformed.html", content, "html_space")
        names = {s.name for s in symbols}
        self.assertIn("#username-input", names)
        self.assertIn("Valid Heading", names)
        self.assertIn("#unclosed-div", names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_04_css_nested_media_edge_case(self):
        """ET-04: 驗證 CssParser 對 @media 媒體查詢與深層 SCSS 選擇器之正確提取 (EC-04)"""
        content = """
@media (max-width: 768px) {
  .responsive-btn {
    padding: 10px;
  }
}

#top-nav {
  .nav-item {
    color: red;
  }
}
"""
        symbols = self.css_parser.parse("responsive.scss", content, "css_space")
        names = {s.name for s in symbols}
        self.assertIn(".responsive-btn", names)
        self.assertIn("#top-nav", names)
        self.assertIn(".nav-item", names)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
