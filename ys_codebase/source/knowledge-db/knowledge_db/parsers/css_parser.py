"""
knowledge-db CSS / SCSS / LESS 語意解析器 (CssParser)
"""

import logging
import re
from pathlib import Path
from typing import List, Set, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.css")

CLASS_SELECTOR_PATTERN = re.compile(r"^\s*\.([a-zA-Z0-9_-]+)(?:\s*,\s*\.[a-zA-Z0-9_-]+)*\s*\{")
ID_SELECTOR_PATTERN = re.compile(r"^\s*#([a-zA-Z0-9_-]+)(?:\s*,\s*#[a-zA-Z0-9_-]+)*\s*\{")
KEYFRAMES_PATTERN = re.compile(r"^\s*@(?:-webkit-|-moz-)?keyframes\s+([a-zA-Z0-9_-]+)")
CSS_VAR_PATTERN = re.compile(r"^\s*(--[a-zA-Z0-9_-]+)\s*:")
SASS_VAR_PATTERN = re.compile(r"^\s*\$([a-zA-Z0-9_-]+)\s*:")
LESS_VAR_PATTERN = re.compile(r"^\s*@([a-zA-Z0-9_-]+)\s*:")


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
        members=[],
        metadata={"space": space, "spaces": [space]},
    )


class CssParser(BaseParser):
    """CSS / SCSS / LESS Class/ID 選擇器、CSS/SASS/LESS 變數與 @keyframes 解析器"""

    SUPPORTED_EXTENSIONS: Set[str] = {".css", ".scss", ".less"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        css_comments: List[str] = []
        in_comment = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if "/*" in stripped:
                in_comment = True
                comment_part = stripped.split("/*", 1)[1]
                if "*/" in comment_part:
                    comment_text = comment_part.split("*/", 1)[0].strip()
                    if comment_text:
                        css_comments.append(comment_text)
                    in_comment = False
                    continue
                else:
                    if comment_part.strip():
                        css_comments.append(comment_part.strip())
                    continue

            if in_comment:
                if "*/" in stripped:
                    comment_text = stripped.split("*/", 1)[0].strip()
                    if comment_text:
                        css_comments.append(comment_text)
                    in_comment = False
                else:
                    if stripped:
                        css_comments.append(stripped)
                continue

            if not stripped:
                continue

            docstring = "\n".join(css_comments) if css_comments else ""

            # 1. Keyframes (@keyframes name)
            kf_match = KEYFRAMES_PATTERN.match(stripped)
            if kf_match:
                kf_name = kf_match.group(1)
                symbols.append(_make_symbol(
                    name=f"@keyframes {kf_name}",
                    kind=SymbolKind.FUNCTION.value,
                    language=LanguageType.CSS.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=f"@keyframes {kf_name}",
                    docstring=docstring,
                ))
                css_comments = []
                continue

            # 2. Class Selector (.className)
            class_match = CLASS_SELECTOR_PATTERN.match(stripped)
            if class_match:
                c_name = class_match.group(1)
                symbols.append(_make_symbol(
                    name=f".{c_name}",
                    kind=SymbolKind.CLASS.value,
                    language=LanguageType.CSS.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=f".{c_name} {{",
                    docstring=docstring,
                ))
                css_comments = []
                continue

            # 3. ID Selector (#idName)
            id_match = ID_SELECTOR_PATTERN.match(stripped)
            if id_match:
                id_name = id_match.group(1)
                symbols.append(_make_symbol(
                    name=f"#{id_name}",
                    kind=SymbolKind.STRUCT.value,
                    language=LanguageType.CSS.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=f"#{id_name} {{",
                    docstring=docstring,
                ))
                css_comments = []
                continue

            # 4. CSS Custom Variable (--var-name)
            css_var_match = CSS_VAR_PATTERN.match(stripped)
            if css_var_match:
                v_name = css_var_match.group(1)
                symbols.append(_make_symbol(
                    name=v_name,
                    kind=SymbolKind.VARIABLE.value,
                    language=LanguageType.CSS.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=stripped,
                    docstring=docstring,
                ))
                css_comments = []
                continue

            # 5. SASS Variable ($var-name)
            sass_var_match = SASS_VAR_PATTERN.match(stripped)
            if sass_var_match:
                v_name = f"${sass_var_match.group(1)}"
                symbols.append(_make_symbol(
                    name=v_name,
                    kind=SymbolKind.VARIABLE.value,
                    language=LanguageType.CSS.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=stripped,
                    docstring=docstring,
                ))
                css_comments = []
                continue

            # 6. LESS Variable (@var-name) - 忽略 @import, @media
            if not stripped.startswith("@import") and not stripped.startswith("@media") and not stripped.startswith("@supports"):
                less_var_match = LESS_VAR_PATTERN.match(stripped)
                if less_var_match:
                    v_name = f"@{less_var_match.group(1)}"
                    symbols.append(_make_symbol(
                        name=v_name,
                        kind=SymbolKind.VARIABLE.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=stripped,
                        docstring=docstring,
                    ))
                    css_comments = []
                    continue

            if not stripped.startswith("/*"):
                css_comments = []

        return symbols
