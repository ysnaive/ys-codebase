"""
knowledge-db Markdown 文檔語意解析器
"""

import logging
import os
from pathlib import Path
import re
from typing import List, Optional, Set, Union

from ..schema import LanguageType, SymbolKind, UnifiedSymbol
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

        def _flush_heading():
            nonlocal current_heading_node, body_lines
            if current_heading_node is not None:
                doc = "\n".join(body_lines).strip()
                # 限制 docstring 長度至合理大小 (例如 4000 字元)
                if len(doc) > 4000:
                    doc = doc[:4000] + "... (truncated)"

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=current_heading_node["name"],
                    kind=current_heading_node["kind"],
                    line_number=current_heading_node["lineno"],
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=current_heading_node["name"],
                        kind=current_heading_node["kind"],
                        file_path=normalized_path,
                        line_number=current_heading_node["lineno"],
                        language=LanguageType.MARKDOWN.value,
                        docstring=doc,
                        signature=f"{'#' * current_heading_node['level']} {current_heading_node['name']}",
                        members=[],
                        metadata={"level": current_heading_node["level"]},
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
                        language=LanguageType.MARKDOWN.value,
                        docstring=t_doc,
                        signature="markdown_table",
                        members=[],
                        metadata={"row_count": len(table_lines)},
                    )
                )
            in_table = False
            table_lines = []

        for i, line in enumerate(lines, start=1):
            # 檢查是否為 Heading
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                _flush_table()
                _flush_heading()

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
        _flush_heading()

        # 2. 若完全無 Heading 標題 (EC-03: 降級為 DOC_SECTION)
        if not symbols and lines:
            non_empty_lines = [l for l in lines if l.strip()]
            sec_name = non_empty_lines[0][:60] if non_empty_lines else os.path.basename(normalized_path)
            full_doc = "\n".join(lines[:200]).strip()
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
                    language=LanguageType.MARKDOWN.value,
                    docstring=full_doc,
                    signature="markdown_section",
                    members=[],
                    metadata={"fallback": True},
                )
            )

        return symbols
