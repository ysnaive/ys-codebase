"""
knowledge-db C/C++ 語意解析器 (基於正則、多行累積狀態機與作用域堆疊)
"""

import logging
import os
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple, Union

from ..schema import LanguageType, MemberInfo, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.cpp")

# Regex patterns for C/C++
NAMESPACE_PATTERN = re.compile(r"^\s*namespace\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)")
CLASS_STRUCT_PATTERN = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct)\s+(?:[A-Z_a-z]\w*_API\s+)?([A-Za-z_]\w*)(?:\s*:\s*([^{;]+))?\s*\{?"
)
ENUM_PATTERN = re.compile(r"^\s*(?:enum(?:\s+class)?)\s+([A-Za-z_]\w*)")
MACRO_PATTERN = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?:\(([^)]*)\))?")
FUNC_HEADER_CANDIDATE = re.compile(
    r"^\s*(?:(?:virtual|static|inline|explicit|const|constexpr|friend)\s+)*"
    r"([\w_]+(?:::[\w_]+)*(?:<[^>]+>)?[\w\s\*&]*)\s+"
    r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\("
)
FUNC_PATTERN = re.compile(
    r"^\s*(?:(?:virtual|static|inline|explicit|const|constexpr|friend)\s+)*"
    r"([\w_]+(?:::[\w_]+)*(?:<[^>]+>)?[\w\s\*&]*)\s+"
    r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\(([\s\S]*?)\)\s*(?:const)?\s*(?:override|final|noexcept)?\s*(?:\{|;|=|(?:\s*$))"
)

MAX_SIGNATURE_LINES = 30


class CppParser(BaseParser):
    """C/C++ 類別、結構、列舉、函式、方法與巨集語意解析器 (支援多行簽名狀態機與作用域堆疊)"""

    SUPPORTED_EXTENSIONS: Set[str] = {".cpp", ".hpp", ".h", ".c", ".cc", ".cxx", ".hxx"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        pending_comments: List[str] = []

        # 作用域追蹤堆疊: (name, enter_depth)
        namespace_stack: List[Tuple[str, int]] = []
        class_stack: List[Tuple[str, int]] = []
        pending_class: Optional[str] = None
        pending_namespace: Optional[str] = None
        current_brace_depth = 0

        # 多行函式簽名累積緩衝區
        accumulating_func: bool = False
        func_start_line: int = 0
        func_buffer: List[str] = []
        func_doc: str = ""

        def get_current_namespace() -> str:
            if not namespace_stack:
                return ""
            return "::".join(ns[0] for ns in namespace_stack)

        def get_current_class() -> Optional[str]:
            if not class_stack:
                return None
            return class_stack[-1][0]

        def qualify_name(name: str) -> str:
            ns = get_current_namespace()
            if ns and not name.startswith(ns):
                return f"{ns}::{name}"
            return name

        i = 0
        num_lines = len(lines)

        while i < num_lines:
            line_idx = i + 1
            line = lines[i]
            stripped = line.strip()
            i += 1

            # 收集單行註解 (/// 或 //)
            if stripped.startswith("///") or stripped.startswith("//"):
                c_text = stripped.lstrip("/").strip()
                if c_text:
                    pending_comments.append(c_text)
                continue

            # 忽略純空白行 (保留註解給下一行)
            if not stripped:
                continue

            open_b = line.count("{")
            close_b = line.count("}")

            # 處理 pending class 或 pending namespace 進入
            if open_b > 0:
                if pending_namespace is not None:
                    namespace_stack.append((pending_namespace, current_brace_depth + 1))
                    pending_namespace = None
                if pending_class is not None:
                    class_stack.append((pending_class, current_brace_depth + 1))
                    pending_class = None

            # 1. 檢查多行函式累積狀態機
            if accumulating_func:
                func_buffer.append(stripped)
                combined = " ".join(func_buffer)
                is_closed = (")" in stripped and any(c in stripped for c in (";", "{", "="))) or (
                    ")" in combined and (combined.endswith(";") or combined.endswith("{") or "= 0" in combined or stripped.endswith("override;") or stripped.endswith("override") or stripped.endswith("final;"))
                )

                if is_closed:
                    func_match = FUNC_PATTERN.match(combined)
                    if func_match:
                        ret_type = func_match.group(1).strip()
                        raw_f_name = func_match.group(2).strip()
                        f_args = " ".join(func_match.group(3).split()).strip()

                        if raw_f_name not in {"if", "while", "for", "switch", "catch", "return"}:
                            curr_cls = get_current_class()
                            if curr_cls:
                                kind = SymbolKind.METHOD.value
                                full_name = qualify_name(f"{curr_cls}::{raw_f_name}" if "::" not in raw_f_name else raw_f_name)
                                parent_scope = curr_cls
                            else:
                                kind = SymbolKind.FUNCTION.value
                                full_name = qualify_name(raw_f_name)
                                parent_scope = ""

                            sig = f"{ret_type} {raw_f_name}({f_args})"
                            sym_id = UnifiedSymbol.compute_id(
                                space=space,
                                file_path=normalized_path,
                                name=full_name,
                                kind=kind,
                                line_number=func_start_line,
                            )
                            symbols.append(
                                UnifiedSymbol(
                                    id=sym_id,
                                    name=full_name,
                                    kind=kind,
                                    file_path=normalized_path,
                                    line_number=func_start_line,
                                    end_line=line_idx,
                                    language=LanguageType.CPP.value,
                                    docstring=func_doc,
                                    signature=sig,
                                    members=[],
                                    metadata={
                                        "parent_scope": parent_scope,
                                        "return_type": ret_type,
                                        "end_line": line_idx,
                                    },
                                )
                            )

                    # 結束累積並重置
                    accumulating_func = False
                    func_buffer = []
                    func_doc = ""
                elif len(func_buffer) > MAX_SIGNATURE_LINES:
                    # 超限熔斷保護 (EC-03)
                    accumulating_func = False
                    func_buffer = []
                    func_doc = ""

                # 更新括號計數
                current_brace_depth += (open_b - close_b)
                while namespace_stack and current_brace_depth < namespace_stack[-1][1]:
                    namespace_stack.pop()
                while class_stack and current_brace_depth < class_stack[-1][1]:
                    class_stack.pop()
                continue

            # 2. 檢查 Macro (#define)
            macro_match = MACRO_PATTERN.match(stripped)
            if macro_match:
                m_name = macro_match.group(1)
                m_args = macro_match.group(2)
                sig = f"#define {m_name}({m_args})" if m_args is not None else f"#define {m_name}"
                doc = "\n".join(pending_comments).strip()
                pending_comments = []

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=m_name,
                    kind=SymbolKind.MACRO.value,
                    line_number=line_idx,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=m_name,
                        kind=SymbolKind.MACRO.value,
                        file_path=normalized_path,
                        line_number=line_idx,
                        end_line=line_idx,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={"is_macro": True, "end_line": line_idx},
                    )
                )
                current_brace_depth += (open_b - close_b)
                continue

            # 3. 檢查 Namespace
            ns_match = NAMESPACE_PATTERN.match(stripped)
            if ns_match:
                ns_name = ns_match.group(1)
                pending_comments = []
                if "{" in stripped:
                    namespace_stack.append((ns_name, current_brace_depth + 1))
                else:
                    pending_namespace = ns_name
                current_brace_depth += (open_b - close_b)
                continue

            # 4. 檢查 Class / Struct
            class_match = CLASS_STRUCT_PATTERN.match(stripped)
            if class_match and not stripped.startswith("typedef"):
                c_name = class_match.group(1)
                bases_raw = class_match.group(2)
                kind = SymbolKind.STRUCT.value if "struct" in stripped[:10] else SymbolKind.CLASS.value
                sig = f"{kind} {c_name}"
                if bases_raw:
                    sig += f" : {bases_raw.strip()}"
                doc = "\n".join(pending_comments).strip()
                pending_comments = []

                full_name = qualify_name(c_name)
                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=full_name,
                    kind=kind,
                    line_number=line_idx,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=full_name,
                        kind=kind,
                        file_path=normalized_path,
                        line_number=line_idx,
                        end_line=line_idx,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={
                            "bases": bases_raw.strip() if bases_raw else "",
                            "namespace": get_current_namespace(),
                            "end_line": line_idx,
                        },
                    )
                )

                if "{" in stripped:
                    class_stack.append((c_name, current_brace_depth + 1))
                else:
                    pending_class = c_name
                current_brace_depth += (open_b - close_b)
                continue

            # 5. 檢查 Enum
            enum_match = ENUM_PATTERN.match(stripped)
            if enum_match:
                e_name = enum_match.group(1)
                doc = "\n".join(pending_comments).strip()
                pending_comments = []

                full_name = qualify_name(e_name)
                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=full_name,
                    kind=SymbolKind.ENUM.value,
                    line_number=line_idx,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=full_name,
                        kind=SymbolKind.ENUM.value,
                        file_path=normalized_path,
                        line_number=line_idx,
                        end_line=line_idx,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=f"enum {e_name}",
                        members=[],
                        metadata={"namespace": get_current_namespace(), "end_line": line_idx},
                    )
                )
                current_brace_depth += (open_b - close_b)
                continue

            # 6. 檢查單行或啟動多行 Function / Method
            func_match = FUNC_PATTERN.match(stripped)
            if func_match and not stripped.startswith("typedef"):
                ret_type = func_match.group(1).strip()
                raw_f_name = func_match.group(2).strip()
                f_args = " ".join(func_match.group(3).split()).strip()

                if raw_f_name not in {"if", "while", "for", "switch", "catch", "return"}:
                    curr_cls = get_current_class()
                    if curr_cls:
                        kind = SymbolKind.METHOD.value
                        full_name = qualify_name(f"{curr_cls}::{raw_f_name}" if "::" not in raw_f_name else raw_f_name)
                        parent_scope = curr_cls
                    else:
                        kind = SymbolKind.FUNCTION.value
                        full_name = qualify_name(raw_f_name)
                        parent_scope = ""

                    sig = f"{ret_type} {raw_f_name}({f_args})"
                    doc = "\n".join(pending_comments).strip()
                    pending_comments = []

                    sym_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=full_name,
                        kind=kind,
                        line_number=line_idx,
                    )
                    symbols.append(
                        UnifiedSymbol(
                            id=sym_id,
                            name=full_name,
                            kind=kind,
                            file_path=normalized_path,
                            line_number=line_idx,
                            end_line=line_idx,
                            language=LanguageType.CPP.value,
                            docstring=doc,
                            signature=sig,
                            members=[],
                            metadata={
                                "parent_scope": parent_scope,
                                "return_type": ret_type,
                                "end_line": line_idx,
                            },
                        )
                    )
                    current_brace_depth += (open_b - close_b)
                    continue
            elif FUNC_HEADER_CANDIDATE.match(stripped) and not stripped.startswith("typedef"):
                # 命中跨行函式宣告開頭，啟動狀態機
                accumulating_func = True
                func_start_line = line_idx
                func_buffer = [stripped]
                func_doc = "\n".join(pending_comments).strip()
                pending_comments = []
                current_brace_depth += (open_b - close_b)
                continue

            # 7. 更新一般括號深度
            current_brace_depth += (open_b - close_b)

            while namespace_stack and current_brace_depth < namespace_stack[-1][1]:
                namespace_stack.pop()
            while class_stack and current_brace_depth < class_stack[-1][1]:
                class_stack.pop()

            # 若此行不是符號且不是註解，清除累積註解
            if not stripped.startswith("/*") and not stripped.startswith("*"):
                pending_comments = []

        return symbols
