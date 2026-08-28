"""
knowledge-db C/C++ 語意解析器 (基於正則與語意狀態機)
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
CLASS_STRUCT_PATTERN = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct)\s+(?:[A-Z_a-z]\w*_API\s+)?([A-Za-z_]\w*)(?:\s*:\s*([^{;]+))?\s*\{?"
)
ENUM_PATTERN = re.compile(r"^\s*(?:enum(?:\s+class)?)\s+([A-Za-z_]\w*)")
MACRO_PATTERN = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?:\(([^)]*)\))?")
FUNC_PATTERN = re.compile(
    r"^\s*(?:(?:virtual|static|inline|explicit|const|constexpr|friend)\s+)*"
    r"([\w_]+(?:::[\w_]+)*(?:<[^>]+>)?[\w\s\*&]*)\s+"
    r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\(([^)]*)\)\s*(?:const)?\s*(?:override|final|noexcept)?\s*(?:\{|;|=)"
)


class CppParser(BaseParser):
    """C/C++ 類別、結構、列舉、函式與巨集語意解析器"""

    SUPPORTED_EXTENSIONS: Set[str] = {".cpp", ".hpp", ".h", ".c", ".cc", ".cxx", ".hxx"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        pending_comments: List[str] = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # 收集單行註解 (/// 或 //)
            if stripped.startswith("///") or stripped.startswith("//"):
                c_text = stripped.lstrip("/").strip()
                if c_text:
                    pending_comments.append(c_text)
                continue

            # 忽略純空白行 (保留註解給下一行)
            if not stripped:
                continue

            # 1. 檢查 Macro (#define)
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
                    line_number=i,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=m_name,
                        kind=SymbolKind.MACRO.value,
                        file_path=normalized_path,
                        line_number=i,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={"is_macro": True},
                    )
                )
                continue

            # 2. 檢查 Class / Struct
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

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=c_name,
                    kind=kind,
                    line_number=i,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=c_name,
                        kind=kind,
                        file_path=normalized_path,
                        line_number=i,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={"bases": bases_raw.strip() if bases_raw else ""},
                    )
                )
                continue

            # 3. 檢查 Enum
            enum_match = ENUM_PATTERN.match(stripped)
            if enum_match:
                e_name = enum_match.group(1)
                doc = "\n".join(pending_comments).strip()
                pending_comments = []

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=e_name,
                    kind=SymbolKind.ENUM.value,
                    line_number=i,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=e_name,
                        kind=SymbolKind.ENUM.value,
                        file_path=normalized_path,
                        line_number=i,
                        language=LanguageType.CPP.value,
                        docstring=doc,
                        signature=f"enum {e_name}",
                        members=[],
                    )
                )
                continue

            # 4. 檢查 Function
            func_match = FUNC_PATTERN.match(stripped)
            if func_match:
                ret_type = func_match.group(1).strip()
                f_name = func_match.group(2).strip()
                f_args = func_match.group(3).strip()
                # 排除 if, while, for, switch, return
                if f_name not in {"if", "while", "for", "switch", "catch", "return"}:
                    sig = f"{ret_type} {f_name}({f_args})"
                    doc = "\n".join(pending_comments).strip()
                    pending_comments = []

                    sym_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=f_name,
                        kind=SymbolKind.FUNCTION.value,
                        line_number=i,
                    )
                    symbols.append(
                        UnifiedSymbol(
                            id=sym_id,
                            name=f_name,
                            kind=SymbolKind.FUNCTION.value,
                            file_path=normalized_path,
                            line_number=i,
                            language=LanguageType.CPP.value,
                            docstring=doc,
                            signature=sig,
                            members=[],
                        )
                    )
                    continue

            # 若此行不是符號且不是註解，清除累積註解
            if not stripped.startswith("/*") and not stripped.startswith("*"):
                pending_comments = []

        return symbols
