"""
HTML semantic parser (`HtmlParser`) for module:ast.
"""

from pathlib import Path
import re
from types import MappingProxyType
from typing import Dict, FrozenSet, List, Mapping, Tuple, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
from .base import BaseParser

TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)(?:</title>|$)", re.IGNORECASE | re.DOTALL)
HEADING_PATTERN = re.compile(r"<h([1-6])[^>]*>(.*?)(?:</h\1>|$)", re.IGNORECASE | re.DOTALL)
ID_ELEMENT_PATTERN = re.compile(r'<([a-zA-Z0-9-]+)[^>]*\bid=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
SEMANTIC_TAG_PATTERN = re.compile(r"<([a-zA-Z0-9-]+)(?:\s[^>]*)?>", re.IGNORECASE)

SEMANTIC_TAGS: FrozenSet[str] = frozenset({
    "main", "header", "footer", "section", "article",
    "template", "dialog", "nav", "aside",
})

HEADING_KIND_MAP: Mapping[str, str] = MappingProxyType({
    "1": SymbolKind.DOC_HEADING_1.value,
    "2": SymbolKind.DOC_HEADING_2.value,
    "3": SymbolKind.DOC_HEADING_3.value,
    "4": SymbolKind.DOC_HEADING_4.value,
    "5": SymbolKind.DOC_HEADING_4.value,
    "6": SymbolKind.DOC_HEADING_4.value,
})


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
    signature_hint: str = "",
) -> UnifiedSymbol:
    sym_id = UnifiedSymbol.compute_id(
        space=space,
        file_path=file_path,
        name=name,
        kind=kind,
        line_number=line_number,
        signature_hint=signature_hint,
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

    SUPPORTED_EXTENSIONS: FrozenSet[str] = frozenset({".html", ".htm"})

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []
        seen_line_keys: Dict[Tuple[str, str, int], int] = {}

        def _next_hint(name_val: str, kind_val: str, ln_val: int) -> str:
            key = (name_val, kind_val, ln_val)
            cnt = seen_line_keys.get(key, 0)
            seen_line_keys[key] = cnt + 1
            return f"occ_{cnt}" if cnt > 0 else ""

        html_comments: List[str] = []
        in_comment = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if in_comment:
                if "-->" in stripped:
                    comment_text, after_close = stripped.split("-->", 1)
                    if comment_text.strip():
                        html_comments.append(comment_text.strip())
                    in_comment = False
                    stripped = after_close.strip()
                    if not stripped:
                        continue
                else:
                    if stripped:
                        html_comments.append(stripped)
                    continue

            if "<!--" in stripped:
                code_segments: List[str] = []
                rem = stripped
                while "<!--" in rem:
                    b_part, c_part = rem.split("<!--", 1)
                    if b_part.strip():
                        code_segments.append(b_part.strip())
                    if "-->" in c_part:
                        comment_body, rem = c_part.split("-->", 1)
                        if not code_segments and comment_body.strip():
                            html_comments.append(comment_body.strip())
                        rem = rem.strip()
                    else:
                        in_comment = True
                        if not code_segments and c_part.strip():
                            html_comments.append(c_part.strip())
                        rem = ""
                        break
                if rem.strip():
                    code_segments.append(rem.strip())
                stripped = " ".join(code_segments).strip()
                if not stripped:
                    continue

            if not stripped:
                continue

            docstring = "\n".join(html_comments) if html_comments else ""

            for title_match in TITLE_PATTERN.finditer(stripped):
                t_text = _clean_html_text(title_match.group(1))
                if t_text:
                    k_val = SymbolKind.DOC_HEADING_1.value
                    symbols.append(
                        _make_symbol(
                            name=t_text,
                            kind=k_val,
                            language=LanguageType.HTML.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=f"<title>{t_text}</title>",
                            docstring=docstring,
                            signature_hint=_next_hint(t_text, k_val, i),
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
                            signature_hint=_next_hint(h_text, kind_val, i),
                        )
                    )
                    html_comments = []

            for id_match in ID_ELEMENT_PATTERN.finditer(stripped):
                tag_name = id_match.group(1).lower()
                id_val = id_match.group(2)
                s_name = f"#{id_val}"
                k_val = SymbolKind.DOC_SECTION.value
                symbols.append(
                    _make_symbol(
                        name=s_name,
                        kind=k_val,
                        language=LanguageType.HTML.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f'<{tag_name} id="{id_val}">',
                        docstring=docstring,
                        signature_hint=_next_hint(s_name, k_val, i),
                    )
                )
                html_comments = []

            for tag_match in SEMANTIC_TAG_PATTERN.finditer(stripped):
                tag_name = tag_match.group(1).lower()
                if tag_name in SEMANTIC_TAGS:
                    s_name = f"<{tag_name}>"
                    k_val = SymbolKind.DOC_SECTION.value
                    symbols.append(
                        _make_symbol(
                            name=s_name,
                            kind=k_val,
                            language=LanguageType.HTML.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=f"<{tag_name}>",
                            docstring=docstring,
                            signature_hint=_next_hint(s_name, k_val, i),
                        )
                    )
                    html_comments = []
                    continue

            if not stripped.startswith("<!--") and not stripped.startswith("*"):
                html_comments = []

        return symbols
