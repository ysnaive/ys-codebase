"""
knowledge-db Markdown 文檔語意解析器
"""

import logging
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Union

from ..schema import LanguageType, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.markdown")

HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$")
TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP_PATTERN = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")


class MarkdownParser(BaseParser):
    """Markdown 標題、表格與區塊文檔語意解析器"""

    SUPPORTED_EXTENSIONS: Set[str] = {".md", ".markdown"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        if not lines:
            return []

        # 1. 狀態機結構掃描
        current_heading_node = None
        heading_level = 0
        body_lines: List[str] = []
        heading_lineno = 1

        in_table = False
        table_lines: List[str] = []
        table_start_lineno = 0

        def _flush_heading(current_end_lineno: Optional[int] = None):
            nonlocal current_heading_node, body_lines
            if current_heading_node is not None:
                doc = "\n".join(body_lines).strip()
                # 限制 docstring 長度至合理大小 (例如 4000 字元)
                if len(doc) > 4000:
                    doc = doc[:4000] + "... (truncated)"

                start_ln = current_heading_node["lineno"]
                end_ln = current_end_lineno if current_end_lineno is not None else (start_ln + max(0, len(body_lines)))

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=current_heading_node["name"],
                    kind=current_heading_node["kind"],
                    line_number=start_ln,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=current_heading_node["name"],
                        kind=current_heading_node["kind"],
                        file_path=normalized_path,
                        line_number=start_ln,
                        end_line=end_ln,
                        language=LanguageType.MARKDOWN.value,
                        docstring=doc,
                        signature=f"{'#' * current_heading_node['level']} {current_heading_node['name']}",
                        members=[],
                        metadata={"level": current_heading_node["level"], "end_line": end_ln},
                    )
                )
                current_heading_node = None
                body_lines = []

        def _flush_table():
            nonlocal in_table, table_lines, table_start_lineno
            if in_table and len(table_lines) >= 2:
                # 提取表頭第一行
                header_row = table_lines[0].strip("|").strip()
                t_name = f"Table: {header_row[:60]}"
                t_doc = "\n".join(table_lines)
                end_ln = table_start_lineno + len(table_lines) - 1
                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=t_name,
                    kind=SymbolKind.DOC_TABLE.value,
                    line_number=table_start_lineno,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=t_name,
                        kind=SymbolKind.DOC_TABLE.value,
                        file_path=normalized_path,
                        line_number=table_start_lineno,
                        end_line=end_ln,
                        language=LanguageType.MARKDOWN.value,
                        docstring=t_doc,
                        signature="markdown_table",
                        members=[],
                        metadata={"row_count": len(table_lines), "end_line": end_ln},
                    )
                )
            in_table = False
            table_lines = []

        for i, line in enumerate(lines, start=1):
            # 檢查是否為 Heading
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                _flush_table()
                _flush_heading(current_end_lineno=i - 1 if i > 1 else 1)

                level = len(heading_match.group(1))
                h_name = heading_match.group(2).strip()

                kind_map = {
                    1: SymbolKind.DOC_HEADING_1.value,
                    2: SymbolKind.DOC_HEADING_2.value,
                    3: SymbolKind.DOC_HEADING_3.value,
                    4: SymbolKind.DOC_HEADING_4.value,
                }
                current_heading_node = {
                    "name": h_name,
                    "kind": kind_map.get(level, SymbolKind.DOC_HEADING_4.value),
                    "level": level,
                    "lineno": i,
                }
                continue

            # 檢查是否為 Table
            if TABLE_ROW_PATTERN.match(line):
                if not in_table:
                    in_table = True
                    table_start_lineno = i
                    table_lines = [line]
                else:
                    table_lines.append(line)
                continue
            else:
                if in_table:
                    _flush_table()

            # 一般正文內容累積
            if current_heading_node is not None:
                body_lines.append(line)

        # 迴圈結束收尾
        _flush_table()
        _flush_heading(current_end_lineno=len(lines))

        # 2. 若完全無 Heading 標題 (EC-03: 降級為 DOC_SECTION)
        if not symbols and lines:
            non_empty_lines = [l for l in lines if l.strip()]
            sec_name = non_empty_lines[0][:60] if non_empty_lines else os.path.basename(normalized_path)
            full_doc = "\n".join(lines[:200]).strip()
            total_ln = len(lines)
            sym_id = UnifiedSymbol.compute_id(
                space=space,
                file_path=normalized_path,
                name=sec_name,
                kind=SymbolKind.DOC_SECTION.value,
                line_number=1,
            )
            symbols.append(
                UnifiedSymbol(
                    id=sym_id,
                    name=sec_name,
                    kind=SymbolKind.DOC_SECTION.value,
                    file_path=normalized_path,
                    line_number=1,
                    end_line=total_ln,
                    language=LanguageType.MARKDOWN.value,
                    docstring=full_doc,
                    signature="markdown_section",
                    members=[],
                    metadata={"fallback": True, "end_line": total_ln},
                )
            )

        return symbols

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """提取 Markdown 內引用的外部文檔與檔案超連結映射表"""
        imports: Dict[str, str] = {}
        # 匹配 [Link Text](target_path.ext)
        link_re = re.compile(r'\[([^\]]+)\]\(([^)#\s]+)(?:#[^)]*)?\)')
        for match in link_re.finditer(content):
            text = match.group(1).strip()
            target = match.group(2).strip()
            if not target.startswith("http://") and not target.startswith("https://") and not target.startswith("mailto:"):
                # 排除純錨點或協定鏈接
                stem = Path(target).stem
                imports[text] = target
                imports[stem] = target
                imports[target] = target

        return imports

    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        """提取 Markdown 內容中引用的符號與程式碼引用點"""
        normalized_path = file_path.replace("\\", "/")
        lines = content.splitlines()
        call_sites: List[SymbolCallSite] = []

        current_heading = "<document>"
        link_sym_re = re.compile(r'\[`?([A-Za-z0-9_$.]+)`?\]\((?:file:///)?([^)#\s]+)(?:#L?(\d+))?\)')
        inline_code_re = re.compile(r'`([A-Za-z0-9_$]+\.[A-Za-z0-9_$]+)(?:\(\))?`')

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            # 更新標題作用域
            h_m = HEADING_PATTERN.match(stripped)
            if h_m:
                current_heading = h_m.group(2).strip()
                continue

            # 1. 顯式 Markdown 超連結符號: [`ClassName.method`](file.py#L123)
            for m in link_sym_re.finditer(line):
                sym_str = m.group(1)
                prefix = ""
                callee = sym_str
                if "." in sym_str:
                    parts = sym_str.split(".")
                    prefix = parts[0]
                    callee = parts[-1]

                call_sites.append(
                    SymbolCallSite(
                        callee_name=callee,
                        line_number=i,
                        caller_member_name=current_heading,
                        context_prefix=prefix,
                        file_path=normalized_path,
                        space=space,
                    )
                )

            # 2. 行內反引號符號參照: `Class.method`
            for m in inline_code_re.finditer(line):
                sym_str = m.group(1)
                parts = sym_str.split(".")
                prefix = parts[0]
                callee = parts[-1]

                call_sites.append(
                    SymbolCallSite(
                        callee_name=callee,
                        line_number=i,
                        caller_member_name=current_heading,
                        context_prefix=prefix,
                        file_path=normalized_path,
                        space=space,
                    )
                )

        return call_sites

