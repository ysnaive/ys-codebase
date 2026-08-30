"""
knowledge-db JavaScript / TypeScript 語意解析器 (JsTsParser)
"""

import logging
import re
from pathlib import Path
from typing import List, Set, Union

from ..schema import LanguageType, MemberInfo, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.js_ts")

CLASS_PATTERN = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_$]+)(?:\s+extends\s+([A-Za-z0-9_$.<>\s]+))?(?:\s+implements\s+([A-Za-z0-9_$.<>\s,]+))?"
)
INTERFACE_PATTERN = re.compile(
    r"^(?:export\s+)?interface\s+([A-Za-z0-9_$]+)(?:<[^>]+>)?(?:\s+extends\s+([A-Za-z0-9_$.<>\s,]+))?"
)
TYPE_ALIAS_PATTERN = re.compile(
    r"^(?:export\s+)?type\s+([A-Za-z0-9_$]+)(?:<[^>]+>)?\s*="
)
ENUM_PATTERN = re.compile(
    r"^(?:export\s+)?(?:const\s+)?enum\s+([A-Za-z0-9_$]+)"
)
FUNC_PATTERN = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*(?:\*\s*)?([A-Za-z0-9_$]+)?\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
)
ARROW_FUNC_PATTERN = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:<[^>]*>)?\s*(?:\(([^)]*)\)|[A-Za-z0-9_$]+)\s*=>"
)
METHOD_PATTERN = re.compile(
    r"^(?:public|private|protected|static|readonly|async|get|set|\*)*\s*([A-Za-z0-9_$]+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
)

KEYWORDS_NOT_METHODS = {
    "if", "else", "for", "while", "do", "switch", "case", "catch",
    "constructor", "return", "throw", "import", "export", "typeof", "instanceof"
}


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
    members: list = None,
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
        members=members or [],
        metadata={"space": space, "spaces": [space]},
    )


class JsTsParser(BaseParser):
    """JavaScript / TypeScript 類別、介面、型別別名、列舉、函式、箭頭函式與方法解譯器"""

    SUPPORTED_EXTENSIONS: Set[str] = {
        ".js", ".jsx", ".mjs", ".cjs",
        ".ts", ".tsx", ".mts", ".cts"
    }

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        ext = Path(file_path).suffix.lower()
        lang = (
            LanguageType.TYPESCRIPT
            if ext in {".ts", ".tsx", ".mts", ".cts"}
            else LanguageType.JAVASCRIPT
        )

        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        jsdoc_lines: List[str] = []
        in_jsdoc = False
        in_template_literal = False

        scope_stack: List[dict] = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            backtick_count = stripped.count("`")
            if backtick_count % 2 != 0:
                in_template_literal = not in_template_literal

            if in_template_literal and not stripped.endswith("`"):
                continue

            if stripped.startswith("/**"):
                in_jsdoc = True
                jsdoc_lines = []
                cleaned = stripped.lstrip("/*").strip()
                if cleaned and not cleaned.startswith("*"):
                    jsdoc_lines.append(cleaned)
                continue

            if in_jsdoc:
                if "*/" in stripped:
                    cleaned = stripped.split("*/")[0].strip().lstrip("*").strip()
                    if cleaned:
                        jsdoc_lines.append(cleaned)
                    in_jsdoc = False
                else:
                    cleaned = stripped.lstrip("*").strip()
                    if cleaned:
                        jsdoc_lines.append(cleaned)
                continue

            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            docstring = "\n".join(jsdoc_lines) if jsdoc_lines else ""

            open_braces = stripped.count("{")
            close_braces = stripped.count("}")

            # 1. Class
            class_match = CLASS_PATTERN.match(stripped)
            if class_match:
                c_name = class_match.group(1)
                extends_name = class_match.group(2)
                sig = f"class {c_name}"
                if extends_name:
                    sig += f" extends {extends_name.strip()}"

                class_sym = _make_symbol(
                    name=c_name,
                    kind=SymbolKind.CLASS.value,
                    language=lang.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=sig,
                    docstring=docstring,
                )
                symbols.append(class_sym)
                jsdoc_lines = []

                if open_braces > close_braces:
                    scope_stack.append({
                        "symbol": class_sym,
                        "brace_depth": 1,
                        "members": []
                    })
                continue

            # 2. Interface (TS)
            if lang == LanguageType.TYPESCRIPT:
                if_match = INTERFACE_PATTERN.match(stripped)
                if if_match:
                    i_name = if_match.group(1)
                    extends_name = if_match.group(2)
                    sig = f"interface {i_name}"
                    if extends_name:
                        sig += f" extends {extends_name.strip()}"

                    if_sym = _make_symbol(
                        name=i_name,
                        kind=SymbolKind.INTERFACE.value,
                        language=lang.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=sig,
                        docstring=docstring,
                    )
                    symbols.append(if_sym)
                    jsdoc_lines = []
                    continue

                # Type Alias
                ta_match = TYPE_ALIAS_PATTERN.match(stripped)
                if ta_match:
                    t_name = ta_match.group(1)
                    symbols.append(_make_symbol(
                        name=t_name,
                        kind=SymbolKind.TYPE_ALIAS.value,
                        language=lang.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f"type {t_name}",
                        docstring=docstring,
                    ))
                    jsdoc_lines = []
                    continue

                # Enum
                enum_match = ENUM_PATTERN.match(stripped)
                if enum_match:
                    e_name = enum_match.group(1)
                    symbols.append(_make_symbol(
                        name=e_name,
                        kind=SymbolKind.ENUM.value,
                        language=lang.value,
                        space=space,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        signature=f"enum {e_name}",
                        docstring=docstring,
                    ))
                    jsdoc_lines = []
                    continue

            # 3. Top-Level Function
            func_match = FUNC_PATTERN.match(stripped)
            if func_match and func_match.group(1):
                f_name = func_match.group(1)
                f_args = func_match.group(2) or ""
                symbols.append(_make_symbol(
                    name=f_name,
                    kind=SymbolKind.FUNCTION.value,
                    language=lang.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=f"function {f_name}({f_args})",
                    docstring=docstring,
                ))
                jsdoc_lines = []
                continue

            # 4. Arrow / Const Function
            arrow_match = ARROW_FUNC_PATTERN.match(stripped)
            if arrow_match:
                af_name = arrow_match.group(1)
                af_args = arrow_match.group(2) or ""
                symbols.append(_make_symbol(
                    name=af_name,
                    kind=SymbolKind.FUNCTION.value,
                    language=lang.value,
                    space=space,
                    file_path=normalized_path,
                    line_number=i,
                    end_line=i,
                    signature=f"const {af_name} = ({af_args}) => ...",
                    docstring=docstring,
                ))
                jsdoc_lines = []
                continue

            # 5. Class Method inside class scope
            if scope_stack:
                method_match = METHOD_PATTERN.match(stripped)
                if method_match:
                    m_name = method_match.group(1)
                    m_args = method_match.group(2) or ""
                    if m_name not in KEYWORDS_NOT_METHODS:
                        top_scope = scope_stack[-1]
                        member_info = MemberInfo(
                            name=m_name,
                            kind=SymbolKind.METHOD.value,
                            signature=f"{m_name}({m_args})",
                            docstring=docstring,
                            line_number=i,
                        )
                        top_scope["members"].append(member_info)
                        jsdoc_lines = []

            # 調整作用域大括弧深度
            if scope_stack:
                top_scope = scope_stack[-1]
                net_change = open_braces - close_braces
                top_scope["brace_depth"] += net_change
                if top_scope["brace_depth"] <= 0:
                    old_sym = top_scope["symbol"]
                    idx = symbols.index(old_sym)
                    updated_sym = _make_symbol(
                        name=old_sym.name,
                        kind=old_sym.kind,
                        language=old_sym.language,
                        space=space,
                        file_path=old_sym.file_path,
                        line_number=old_sym.line_number,
                        end_line=i,
                        signature=old_sym.signature,
                        docstring=old_sym.docstring,
                        members=top_scope["members"],
                    )
                    symbols[idx] = updated_sym
                    scope_stack.pop()

            if not stripped.startswith("/*") and not stripped.startswith("*"):
                jsdoc_lines = []

        return symbols
