"""
CSS / SCSS / LESS semantic parser (`CssParser`) for module:ast.
"""

import logging
from pathlib import Path
import re
from typing import List, Set, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("ast.parsers.css")

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
        children=(),
        metadata={"spaces": [space]},
    )


class CssParser(BaseParser):
    """CSS / SCSS / LESS class/ID selectors, CSS/SASS/LESS variables, and @keyframes parser."""

    SUPPORTED_EXTENSIONS: Set[str] = {".css", ".scss", ".sass", ".less"}

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

            if in_comment:
                if "*/" in stripped:
                    comment_text, after_close = stripped.split("*/", 1)
                    if comment_text.strip():
                        css_comments.append(comment_text.strip())
                    in_comment = False
                    stripped = after_close.strip()
                    if not stripped:
                        continue
                else:
                    if stripped:
                        css_comments.append(stripped)
                    continue

            if "/*" in stripped:
                before_comment, comment_part = stripped.split("/*", 1)
                if not before_comment.strip():
                    if "*/" in comment_part:
                        comment_text, after_close = comment_part.split("*/", 1)
                        if comment_text.strip():
                            css_comments.append(comment_text.strip())
                        in_comment = False
                        stripped = after_close.strip()
                        if not stripped:
                            continue
                    else:
                        in_comment = True
                        if comment_part.strip():
                            css_comments.append(comment_part.strip())
                        continue
                else:
                    while "/*" in stripped:
                        b_part, c_part = stripped.split("/*", 1)
                        if "*/" in c_part:
                            _, rest_part = c_part.split("*/", 1)
                            stripped = f"{b_part.rstrip()} {rest_part.lstrip()}".strip()
                        else:
                            in_comment = True
                            stripped = b_part.strip()
                            break
                    if not stripped:
                        continue

            if not stripped:
                continue

            docstring = "\n".join(css_comments) if css_comments else ""

            kf_match = KEYFRAMES_PATTERN.match(stripped)
            if kf_match:
                kf_name = kf_match.group(1)
                symbols.append(
                    _make_symbol(
                        name=f"@keyframes {kf_name}",
                        kind=SymbolKind.FUNCTION.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f"@keyframes {kf_name}",
                        docstring=docstring,
                    )
                )
                css_comments = []
                continue

            class_match = CLASS_SELECTOR_PATTERN.match(stripped)
            if class_match:
                c_name = class_match.group(1)
                symbols.append(
                    _make_symbol(
                        name=f".{c_name}",
                        kind=SymbolKind.CLASS.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f".{c_name} {{",
                        docstring=docstring,
                    )
                )
                css_comments = []
                continue

            id_match = ID_SELECTOR_PATTERN.match(stripped)
            if id_match:
                id_name = id_match.group(1)
                symbols.append(
                    _make_symbol(
                        name=f"#{id_name}",
                        kind=SymbolKind.STRUCT.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f"#{id_name} {{",
                        docstring=docstring,
                    )
                )
                css_comments = []
                continue

            css_var_match = CSS_VAR_PATTERN.match(stripped)
            if css_var_match:
                v_name = css_var_match.group(1)
                symbols.append(
                    _make_symbol(
                        name=v_name,
                        kind=SymbolKind.VARIABLE.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=stripped,
                        docstring=docstring,
                    )
                )
                css_comments = []
                continue

            sass_var_match = SASS_VAR_PATTERN.match(stripped)
            if sass_var_match:
                v_name = f"${sass_var_match.group(1)}"
                symbols.append(
                    _make_symbol(
                        name=v_name,
                        kind=SymbolKind.VARIABLE.value,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=stripped,
                        docstring=docstring,
                    )
                )
                css_comments = []
                continue

            if (
                not stripped.startswith("@import")
                and not stripped.startswith("@media")
                and not stripped.startswith("@supports")
            ):
                less_var_match = LESS_VAR_PATTERN.match(stripped)
                if less_var_match:
                    v_name = f"@{less_var_match.group(1)}"
                    symbols.append(
                        _make_symbol(
                            name=v_name,
                            kind=SymbolKind.VARIABLE.value,
                            language=LanguageType.CSS.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=stripped,
                            docstring=docstring,
                        )
                    )
                    css_comments = []
                    continue

            if not stripped.startswith("/*"):
                css_comments = []

        return symbols
