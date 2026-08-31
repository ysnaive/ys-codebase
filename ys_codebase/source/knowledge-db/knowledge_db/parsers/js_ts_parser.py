"""
knowledge-db JavaScript / TypeScript 語意解析器 (JsTsParser)
"""

import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple, Union

from ..schema import LanguageType, MemberInfo, SymbolCallSite, SymbolKind, UnifiedSymbol
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

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """提取 JS/TS 檔頭 import / require 映射表"""
        imports: Dict[str, str] = {}
        for line in content.splitlines():
            stripped = line.strip()

            # 1. import { a, b as c } from 'path'
            imp_named_m = re.match(r"^import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", stripped)
            if imp_named_m:
                named_part = imp_named_m.group(1)
                mod_path = imp_named_m.group(2)
                for item in named_part.split(","):
                    item = item.strip()
                    if " as " in item:
                        orig, alias = item.split(" as ", 1)
                        imports[alias.strip()] = f"{mod_path}.{orig.strip()}"
                    elif item:
                        imports[item] = f"{mod_path}.{item}"
                continue

            # 2. import * as Foo from 'path'
            imp_all_m = re.match(r"^import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s+from\s+['\"]([^'\"]+)['\"]", stripped)
            if imp_all_m:
                imports[imp_all_m.group(1)] = imp_all_m.group(2)
                continue

            # 3. import Foo from 'path'
            imp_def_m = re.match(r"^import\s+([A-Za-z0-9_$]+)\s+from\s+['\"]([^'\"]+)['\"]", stripped)
            if imp_def_m:
                imports[imp_def_m.group(1)] = imp_def_m.group(2)
                continue

            # 4. const { a, b: c } = require('path')
            req_named_m = re.match(r"^(?:const|let|var)\s+\{([^}]+)\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)", stripped)
            if req_named_m:
                named_part = req_named_m.group(1)
                mod_path = req_named_m.group(2)
                for item in named_part.split(","):
                    item = item.strip()
                    if ":" in item:
                        orig, alias = item.split(":", 1)
                        imports[alias.strip()] = f"{mod_path}.{orig.strip()}"
                    elif item:
                        imports[item] = f"{mod_path}.{item}"
                continue

            # 5. const Foo = require('path')
            req_def_m = re.match(r"^(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)", stripped)
            if req_def_m:
                imports[req_def_m.group(1)] = req_def_m.group(2)

        return imports

    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        """提取 JS/TS 原始碼中的函式/方法調用點"""
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        call_sites: List[SymbolCallSite] = []

        class_stack: List[Tuple[str, int]] = []
        func_stack: List[Tuple[str, int]] = []
        current_brace_depth = 0

        js_call_re = re.compile(r'(?:(?:\b([A-Za-z0-9_$]+)\s*\.)|\b)\b([A-Za-z0-9_$]+)\s*\(')
        keywords = {
            "if", "for", "while", "switch", "catch", "return", "throw", "typeof",
            "instanceof", "import", "require", "function", "constructor", "class",
            "interface", "type", "enum", "export", "default", "new", "await", "async",
            "yield", "super", "delete", "void", "in", "of", "get", "set"
        }

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue

            open_b = line.count("{")
            close_b = line.count("}")

            # 類別進入
            cls_m = CLASS_PATTERN.match(stripped)
            if cls_m and not stripped.endswith(";"):
                c_name = cls_m.group(1)
                class_stack.append((c_name, current_brace_depth + (1 if open_b > 0 else 0)))

            # 函式與方法進入
            fn_m = FUNC_PATTERN.match(stripped) or ARROW_FUNC_PATTERN.match(stripped)
            m_m = METHOD_PATTERN.match(stripped)
            if fn_m and "{" in stripped:
                f_name = fn_m.group(1) or "<anonymous>"
                func_stack.append((f_name, current_brace_depth + 1))
            elif m_m and "{" in stripped and m_m.group(1) not in KEYWORDS_NOT_METHODS:
                m_name = m_m.group(1)
                func_stack.append((m_name, current_brace_depth + 1))

            curr_class = class_stack[-1][0] if class_stack else ""
            curr_func = func_stack[-1][0] if func_stack else ""
            if curr_class and curr_func:
                curr_caller = f"{curr_class}.{curr_func}"
            elif curr_class:
                curr_caller = curr_class
            elif curr_func:
                curr_caller = curr_func
            else:
                curr_caller = "<module>"

            # 提取調用點
            if not cls_m:
                for match in js_call_re.finditer(line):
                    prefix = match.group(1) or ""
                    callee = match.group(2)

                    if callee in keywords or prefix in keywords:
                        continue

                    norm_prefix = "self" if prefix == "this" else prefix

                    call_sites.append(
                        SymbolCallSite(
                            callee_name=callee,
                            line_number=i,
                            caller_member_name=curr_caller,
                            context_prefix=norm_prefix,
                            file_path=normalized_path,
                            space=space,
                        )
                    )

            current_brace_depth += (open_b - close_b)

            while class_stack and current_brace_depth < class_stack[-1][1]:
                class_stack.pop()
            while func_stack and current_brace_depth < func_stack[-1][1]:
                func_stack.pop()

        return call_sites

