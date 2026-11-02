"""
HTML semantic parser (`HtmlParser`) for module:ast.
"""

import logging
from pathlib import Path
import re
from typing import List, Set, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("ast.parsers.html")

TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
HEADING_PATTERN = re.compile(r"<h([1-6])[^>]*>(.*?)(?:</h\1>|$)", re.IGNORECASE | re.DOTALL)
ID_ELEMENT_PATTERN = re.compile(r'<([a-zA-Z0-9-]+)[^>]*\bid=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
SEMANTIC_TAG_PATTERN = re.compile(r"<([a-zA-Z0-9-]+)[^>]*>", re.IGNORECASE)

SEMANTIC_TAGS = {
    "main", "header", "footer", "section", "article",
    "template", "dialog", "nav", "aside",
}

HEADING_KIND_MAP = {
    "1": SymbolKind.DOC_HEADING_1.value,
    "2": SymbolKind.DOC_HEADING_2.value,
    "3": SymbolKind.DOC_HEADING_3.value,
    "4": SymbolKind.DOC_HEADING_4.value,
    "5": SymbolKind.DOC_HEADING_4.value,
    "6": SymbolKind.DOC_HEADING_4.value,
}


def _clean_html_text(raw_html: str) -> str:
    """Strip inline HTML tags to obtain plain text."""
    cleaned = re.sub(r"<[^>]+>", "", raw_html)
    return " ".join(cleaned.split())


def _make_symbol(
    name: str,
    kind: str,
    language: str,
    space: str,
    file_path: str,
    line_number: int,
    end_line: int,
    signature: str,
    docstring: str = "",
) -> UnifiedSymbol:
    sym_id = UnifiedSymbol.compute_id(
        space=space,
        file_path=file_path,
        name=name,
        kind=kind,
        line_number=line_number,
    )
    return UnifiedSymbol(
        id=sym_id,
        name=name,
        kind=kind,
        file_path=file_path,
        line_number=line_number,
        end_line=end_line,
        language=language,
        docstring=docstring,
        signature=signature,
        children=(),
        metadata={"spaces": [space]},
    )


class HtmlParser(BaseParser):
    """HTML title, h1-h6 headings, ID elements, and HTML5 semantic sections parser."""

    SUPPORTED_EXTENSIONS: Set[str] = {".html", ".htm"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        html_comments: List[str] = []
        in_comment = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if "<!--" in stripped:
                in_comment = True
                comment_part = stripped.split("<!--", 1)[1]
                if "-->" in comment_part:
                    comment_text = comment_part.split("-->", 1)[0].strip()
                    if comment_text:
                        html_comments.append(comment_text)
                    in_comment = False
                    continue
                else:
                    if comment_part.strip():
                        html_comments.append(comment_part.strip())
                    continue

            if in_comment:
                if "-->" in stripped:
                    comment_text = stripped.split("-->", 1)[0].strip()
                    if comment_text:
                        html_comments.append(comment_text)
                    in_comment = False
                else:
                    if stripped:
                        html_comments.append(stripped)
                continue

            if not stripped:
                continue

            docstring = "\n".join(html_comments) if html_comments else ""

            for title_match in TITLE_PATTERN.finditer(stripped):
                t_text = _clean_html_text(title_match.group(1))
                if t_text:
                    symbols.append(
                        _make_symbol(
                            name=t_text,
                            kind=SymbolKind.DOC_HEADING_1.value,
                            language=LanguageType.HTML.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=f"<title>{t_text}</title>",
                            docstring=docstring,
                        )
                    )
                    html_comments = []

            for heading_match in HEADING_PATTERN.finditer(stripped):
                h_level = heading_match.group(1)
                h_text = _clean_html_text(heading_match.group(2))
                if h_text:
                    kind_val = HEADING_KIND_MAP.get(h_level, SymbolKind.DOC_HEADING_1.value)
                    symbols.append(
                        _make_symbol(
                            name=h_text,
                            kind=kind_val,
                            language=LanguageType.HTML.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=f"<h{h_level}>{h_text}</h{h_level}>",
                            docstring=docstring,
                        )
                    )
                    html_comments = []

            for id_match in ID_ELEMENT_PATTERN.finditer(stripped):
                tag_name = id_match.group(1).lower()
                id_val = id_match.group(2)
                symbols.append(
                    _make_symbol(
                        name=f"#{id_val}",
                        kind=SymbolKind.DOC_SECTION.value,
                        language=LanguageType.HTML.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f'<{tag_name} id="{id_val}">',
                        docstring=docstring,
                    )
                )
                html_comments = []

            for tag_match in SEMANTIC_TAG_PATTERN.finditer(stripped):
                tag_name = tag_match.group(1).lower()
                if tag_name in SEMANTIC_TAGS:
                    symbols.append(
                        _make_symbol(
                            name=f"<{tag_name}>",
                            kind=SymbolKind.DOC_SECTION.value,
                            language=LanguageType.HTML.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=f"<{tag_name}>",
                            docstring=docstring,
                        )
                    )
                    html_comments = []
                    continue

            if not stripped.startswith("<!--") and not stripped.startswith("*"):
                html_comments = []

        return symbols
