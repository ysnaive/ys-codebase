"""
CSS / SCSS / LESS semantic parser (`CssParser`) for module:ast.
"""

from pathlib import Path
import re
from typing import Dict, FrozenSet, List, Tuple, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
from .base import BaseParser

CLASS_SELECTOR_PATTERN = re.compile(r"^\s*\.([a-zA-Z0-9_-]+)(?:\s*,\s*\.[a-zA-Z0-9_-]+)*\s*(?:\{|$)")
ID_SELECTOR_PATTERN = re.compile(r"^\s*#([a-zA-Z0-9_-]+)(?:\s*,\s*#[a-zA-Z0-9_-]+)*\s*(?:\{|$)")
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


class CssParser(BaseParser):
    """CSS / SCSS / LESS class/ID selectors, CSS/SASS/LESS variables, and @keyframes parser."""

    SUPPORTED_EXTENSIONS: FrozenSet[str] = frozenset({".css", ".scss", ".sass", ".less"})

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
                code_segments: List[str] = []
                rem = stripped
                while "/*" in rem:
                    b_part, c_part = rem.split("/*", 1)
                    if b_part.strip():
                        code_segments.append(b_part.strip())
                    if "*/" in c_part:
                        comment_body, rem = c_part.split("*/", 1)
                        if not code_segments and comment_body.strip():
                            css_comments.append(comment_body.strip())
                        rem = rem.strip()
                    else:
                        in_comment = True
                        if not code_segments and c_part.strip():
                            css_comments.append(c_part.strip())
                        rem = ""
                        break
                if rem.strip():
                    code_segments.append(rem.strip())
                stripped = " ".join(code_segments).strip()
                if not stripped:
                    continue

            if not stripped:
                continue

            docstring = "\n".join(css_comments) if css_comments else ""

            kf_match = KEYFRAMES_PATTERN.match(stripped)
            if kf_match:
                kf_name = kf_match.group(1)
                s_name = f"@keyframes {kf_name}"
                k_val = SymbolKind.FUNCTION.value
                symbols.append(
                    _make_symbol(
                        name=s_name,
                        kind=k_val,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=s_name,
                        docstring=docstring,
                        signature_hint=_next_hint(s_name, k_val, i),
                    )
                )
                css_comments = []
                continue

            class_match = CLASS_SELECTOR_PATTERN.match(stripped)
            if class_match:
                c_name = class_match.group(1)
                s_name = f".{c_name}"
                k_val = SymbolKind.CLASS.value
                symbols.append(
                    _make_symbol(
                        name=s_name,
                        kind=k_val,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f".{c_name} {{",
                        docstring=docstring,
                        signature_hint=_next_hint(s_name, k_val, i),
                    )
                )
                css_comments = []
                continue

            id_match = ID_SELECTOR_PATTERN.match(stripped)
            if id_match:
                id_name = id_match.group(1)
                s_name = f"#{id_name}"
                k_val = SymbolKind.STRUCT.value
                symbols.append(
                    _make_symbol(
                        name=s_name,
                        kind=k_val,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f"#{id_name} {{",
                        docstring=docstring,
                        signature_hint=_next_hint(s_name, k_val, i),
                    )
                )
                css_comments = []
                continue

            css_var_match = CSS_VAR_PATTERN.match(stripped)
            if css_var_match:
                v_name = css_var_match.group(1)
                k_val = SymbolKind.VARIABLE.value
                symbols.append(
                    _make_symbol(
                        name=v_name,
                        kind=k_val,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=stripped,
                        docstring=docstring,
                        signature_hint=_next_hint(v_name, k_val, i),
                    )
                )
                css_comments = []
                continue

            sass_var_match = SASS_VAR_PATTERN.match(stripped)
            if sass_var_match:
                v_name = f"${sass_var_match.group(1)}"
                k_val = SymbolKind.VARIABLE.value
                symbols.append(
                    _make_symbol(
                        name=v_name,
                        kind=k_val,
                        language=LanguageType.CSS.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=stripped,
                        docstring=docstring,
                        signature_hint=_next_hint(v_name, k_val, i),
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
                    k_val = SymbolKind.VARIABLE.value
                    symbols.append(
                        _make_symbol(
                            name=v_name,
                            kind=k_val,
                            language=LanguageType.CSS.value,
                            space=space,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            signature=stripped,
                            docstring=docstring,
                            signature_hint=_next_hint(v_name, k_val, i),
                        )
                    )
                    css_comments = []
                    continue

            if not stripped.startswith("/*"):
                css_comments = []

        return symbols
