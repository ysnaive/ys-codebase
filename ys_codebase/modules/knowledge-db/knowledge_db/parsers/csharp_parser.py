"""
knowledge-db C# 語意解析器 (基於正則與 XML Doc 提取器)
"""

import logging
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple, Union

from ..schema import LanguageType, MemberInfo, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.csharp")

TYPE_PATTERN = re.compile(
    r"^\s*(?:(?:public|internal|protected|private|static|abstract|sealed|partial)\s+)*"
    r"(class|interface|struct|enum)\s+([A-Za-z_]\w*)(?:<[^>]+>)?(?:\s*:\s*([^{;]+))?"
)
METHOD_PATTERN = re.compile(
    r"^\s*(?:(?:public|protected|private|internal|static|async|virtual|override|abstract|sealed)\s+)+"
    r"([\w_<>\[\],?]+)\s+([A-Za-z_]\w*)(?:<[^>]+>)?\s*\(([^)]*)\)\s*(?:where\s+.*)?(?:\s*\{|;|\s*=>|\s*$)"
)
PROPERTY_PATTERN = re.compile(
    r"^\s*(?:(?:public|protected|private|internal|static|virtual|override)\s+)+"
    r"([\w_<>\[\],?]+)\s+([A-Za-z_]\w*)\s*\{\s*(?:get|set)"
)
XML_SUMMARY_PATTERN = re.compile(r"///\s*<summary>(.*?)(?:</summary>|$)", re.DOTALL)


class CSharpParser(BaseParser):
    """C# 命名空間、類別、介面、方法與 XML Doc 語意解析器"""

    SUPPORTED_EXTENSIONS: Set[str] = {".cs"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        xml_comments: List[str] = []
        current_namespace = ""

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # 收集 XML 註解 (///)
            if stripped.startswith("///"):
                clean_c = stripped.lstrip("/").strip()
                # 去除 <summary> 標籤
                clean_c = re.sub(r"</?summary>", "", clean_c).strip()
                if clean_c:
                    xml_comments.append(clean_c)
                continue

            if not stripped:
                continue

            # 檢查 namespace
            if stripped.startswith("namespace "):
                ns_match = re.match(r"^namespace\s+([A-Za-z0-9_.]+)", stripped)
                if ns_match:
                    current_namespace = ns_match.group(1)
                continue

            # 1. 檢查 Class / Interface / Struct / Enum
            type_match = TYPE_PATTERN.match(stripped)
            if type_match:
                type_kind = type_match.group(1)
                type_name = type_match.group(2)
                bases = type_match.group(3)

                kind_map = {
                    "class": SymbolKind.CLASS.value,
                    "interface": SymbolKind.INTERFACE.value,
                    "struct": SymbolKind.STRUCT.value,
                    "enum": SymbolKind.ENUM.value,
                }
                kind = kind_map.get(type_kind, SymbolKind.CLASS.value)
                full_name = f"{current_namespace}.{type_name}" if current_namespace else type_name

                sig = f"{type_kind} {type_name}"
                if bases:
                    sig += f" : {bases.strip()}"
                doc = "\n".join(xml_comments).strip()
                xml_comments = []

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=full_name,
                    kind=kind,
                    line_number=i,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=full_name,
                        kind=kind,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        language=LanguageType.CSHARP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={"namespace": current_namespace, "bases": bases.strip() if bases else "", "end_line": i},
                    )
                )
                continue

            # 2. 檢查 Method
            method_match = METHOD_PATTERN.match(stripped)
            if method_match:
                ret_type = method_match.group(1)
                m_name = method_match.group(2)
                m_args = method_match.group(3)

                if m_name not in {"if", "while", "for", "switch", "catch", "using"}:
                    sig = f"{ret_type} {m_name}({m_args})"
                    doc = "\n".join(xml_comments).strip()
                    xml_comments = []

                    sym_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=m_name,
                        kind=SymbolKind.METHOD.value,
                        line_number=i,
                    )
                    symbols.append(
                        UnifiedSymbol(
                            id=sym_id,
                            name=m_name,
                            kind=SymbolKind.METHOD.value,
                            file_path=normalized_path,
                            line_number=i,
                            end_line=i,
                            language=LanguageType.CSHARP.value,
                            docstring=doc,
                            signature=sig,
                            members=[],
                            metadata={"namespace": current_namespace, "end_line": i},
                        )
                    )
                    continue

            # 3. 檢查 Property
            prop_match = PROPERTY_PATTERN.match(stripped)
            if prop_match:
                p_type = prop_match.group(1)
                p_name = prop_match.group(2)
                sig = f"{p_type} {p_name} {{ get; set; }}"
                doc = "\n".join(xml_comments).strip()
                xml_comments = []

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=p_name,
                    kind=SymbolKind.VARIABLE.value,
                    line_number=i,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=p_name,
                        kind=SymbolKind.VARIABLE.value,
                        file_path=normalized_path,
                        line_number=i,
                        end_line=i,
                        language=LanguageType.CSHARP.value,
                        docstring=doc,
                        signature=sig,
                        members=[],
                        metadata={"is_property": True, "namespace": current_namespace, "end_line": i},
                    )
                )
                continue

            if not stripped.startswith("//") and not stripped.startswith("/*"):
                xml_comments = []

        # 完善各符號之 end_line 近似估算 (FR-01, Type 1)
        total_lines = len(lines)
        if symbols:
            symbols.sort(key=lambda s: s.line_number)
            for idx in range(len(symbols)):
                curr = symbols[idx]
                if idx + 1 < len(symbols):
                    next_start = symbols[idx + 1].line_number
                    calc_end = max(curr.line_number, next_start - 1)
                else:
                    calc_end = total_lines
                # 重新建立 UnifiedSymbol 填入精確計算後的 end_line
                symbols[idx] = UnifiedSymbol(
                    id=curr.id,
                    name=curr.name,
                    kind=curr.kind,
                    file_path=curr.file_path,
                    line_number=curr.line_number,
                    end_line=calc_end,
                    language=curr.language,
                    docstring=curr.docstring,
                    signature=curr.signature,
                    members=curr.members,
                    metadata={**curr.metadata, "end_line": calc_end},
                )

        return symbols

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """提取 C# 檔頭 using 命名空間與別名映射表"""
        imports: Dict[str, str] = {}
        for line in content.splitlines():
            stripped = line.strip()
            # 1. using Alias = Target;
            alias_m = re.match(r"^\s*using\s+([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;", stripped)
            if alias_m:
                imports[alias_m.group(1)] = alias_m.group(2)
                continue

            # 2. using static System.Math;
            static_m = re.match(r"^\s*using\s+static\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;", stripped)
            if static_m:
                target = static_m.group(1)
                short_name = target.split(".")[-1]
                imports[short_name] = target
                continue

            # 3. using System.Collections.Generic;
            using_m = re.match(r"^\s*using\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;", stripped)
            if using_m:
                ns = using_m.group(1)
                short_ns = ns.split(".")[-1]
                imports[short_ns] = ns
                imports[ns] = ns

        return imports

    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        """提取 C# 原始碼中的方法調用點"""
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        call_sites: List[SymbolCallSite] = []

        class_stack: List[Tuple[str, int]] = []
        method_stack: List[Tuple[str, int]] = []
        current_brace_depth = 0

        cs_call_re = re.compile(r'(?:(?:\b([A-Za-z_]\w*)\s*\.)|\b)\b([A-Za-z_]\w+)\s*\(')
        keywords = {
            "if", "for", "foreach", "while", "switch", "catch", "return", "typeof",
            "sizeof", "nameof", "lock", "using", "new", "is", "as", "where", "await",
            "class", "interface", "struct", "enum", "public", "private", "protected",
            "internal", "static", "virtual", "override", "async", "get", "set", "throw"
        }

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue

            open_b = line.count("{")
            close_b = line.count("}")

            # 類別進入
            cls_m = TYPE_PATTERN.match(stripped)
            if cls_m and not stripped.endswith(";"):
                c_name = cls_m.group(2)
                class_stack.append((c_name, current_brace_depth + (1 if open_b > 0 else 0)))

            # 方法進入
            m_m = METHOD_PATTERN.match(stripped)
            if m_m and ("{" in stripped or "=>" in stripped):
                m_name = m_m.group(2)
                method_stack.append((m_name, current_brace_depth + 1))

            curr_class = class_stack[-1][0] if class_stack else ""
            curr_method = method_stack[-1][0] if method_stack else ""
            if curr_class and curr_method:
                curr_caller = f"{curr_class}.{curr_method}"
            elif curr_class:
                curr_caller = curr_class
            elif curr_method:
                curr_caller = curr_method
            else:
                curr_caller = "<module>"

            # 提取調用點
            if not cls_m and not (m_m and stripped.endswith("{")):
                for match in cs_call_re.finditer(line):
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
            while method_stack and current_brace_depth < method_stack[-1][1]:
                method_stack.pop()

        return call_sites

