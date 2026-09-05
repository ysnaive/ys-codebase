"""
knowledge-db parsers package
"""

from .base import BaseParser
from .registry import (
    CppParser,
    CSharpParser,
    JsTsParser,
    LanguageRegistry,
    MarkdownParser,
    ParserRegistry,
    PythonParser,
)
from .spice_parser import LogicalLine, SpiceParser
from .treesitter import TreeSitterDriver

try:
    from .html_parser import HtmlParser
except ImportError:
    HtmlParser = None

try:
    from .css_parser import CssParser
except ImportError:
    CssParser = None

__all__ = [
    "BaseParser",
    "TreeSitterDriver",
    "ParserRegistry",
    "LanguageRegistry",
    "PythonParser",
    "MarkdownParser",
    "CppParser",
    "CSharpParser",
    "JsTsParser",
    "SpiceParser",
    "LogicalLine",
    "HtmlParser",
    "CssParser",
]
