"""
Unit and Edge Case Tests for knowledge-db Web Parsers (JsTsParser, HtmlParser, CssParser).
"""

import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.parsers import (
    CssParser,
    HtmlParser,
    JsTsParser,
    ParserRegistry,
)
from knowledge_db.schema import LanguageType, SymbolKind


class TestWebParsers(YSCBTestCase):
    """JavaScript/TypeScript, HTML, CSS 解譯器功能與邊界測試套件。"""

    def setUp(self):
        super().setUp()
        self.js_ts_parser = JsTsParser()
        self.html_parser = HtmlParser()
        self.css_parser = CssParser()

    # =========================================================================
    # FT: 功能需求測試 (Functional Tests)
    # =========================================================================

    @require(Requirement.LOGIC)
    def test_ft_01_language_type_enum(self):
        """FT-01: 驗證 LanguageType 包含 Web 語言列舉 (FR-01)"""
        self.assertEqual(LanguageType.JAVASCRIPT.value, "javascript")
        self.assertEqual(LanguageType.TYPESCRIPT.value, "typescript")
        self.assertEqual(LanguageType.HTML.value, "html")
        self.assertEqual(LanguageType.CSS.value, "css")

    @require(Requirement.LOGIC)
    def test_ft_02_js_ts_parser(self):
        """FT-02: 驗證 JsTsParser 提取類別、介面、型別、函式、箭頭函式、方法與 JSDoc (FR-02)"""
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

        # 檢驗 UserService 之 class 與內部 method
        user_service = next(s for s in symbols if s.name == "UserService")
        self.assertEqual(user_service.kind, SymbolKind.CLASS.value)
        self.assertEqual(user_service.language, LanguageType.TYPESCRIPT.value)
        self.assertIn("User Data Model", user_service.docstring)
        member_names = {m.name for m in user_service.members}
        self.assertIn("getUser", member_names)

    @require(Requirement.LOGIC)
    def test_ft_03_html_parser(self):
        """FT-03: 驗證 HtmlParser 提取 title, h1~h6, id 選擇器元素, 語意區塊與 HTML 註解 (FR-03)"""
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

        # 檢核 Title Symbol
        title_sym = next(s for s in symbols if s.name == "My Web Dashboard")
        self.assertEqual(title_sym.kind, SymbolKind.DOC_HEADING_1.value)
        self.assertEqual(title_sym.language, LanguageType.HTML.value)
        self.assertIn("Main Web Page Title", title_sym.docstring)

    @require(Requirement.LOGIC)
    def test_ft_04_css_parser(self):
        """FT-04: 驗證 CssParser 提取 Class/ID 選擇器、CSS/SASS/LESS 變數與 @keyframes (FR-04)"""
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

        # 檢核 Class Selector Symbol
        card_sym = next(s for s in symbols if s.name == ".card-container")
        self.assertEqual(card_sym.kind, SymbolKind.CLASS.value)
        self.assertEqual(card_sym.language, LanguageType.CSS.value)
        self.assertIn("Card Component Styles", card_sym.docstring)

    @require(Requirement.LOGIC)
    def test_ft_05_parser_registry_integration(self):
        """FT-05: 驗證 ParserRegistry 動態分發與 Web 解析器整合 (FR-05)"""
        registry = ParserRegistry(register_defaults=True)

        self.assertIsInstance(registry.get_parser("index.ts"), JsTsParser)
        self.assertIsInstance(registry.get_parser("page.html"), HtmlParser)
        self.assertIsInstance(registry.get_parser("style.scss"), CssParser)

        ts_symbols = registry.parse_file("test.ts", "class TestClass {}", "reg_space")
        self.assertEqual(len(ts_symbols), 1)
        self.assertEqual(ts_symbols[0].name, "TestClass")
        self.assertEqual(ts_symbols[0].language, LanguageType.TYPESCRIPT.value)

    # =========================================================================
    # ET: 邊界與異常防禦測試 (Edge Case Tests)
    # =========================================================================

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
