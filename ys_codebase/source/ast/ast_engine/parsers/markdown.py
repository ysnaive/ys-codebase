"""
Standalone Markdown parser (`MarkdownParser`) for module:ast.
Supports ATX/Setext headings, pipe tables, section docstrings, and markdown reference call sites.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Union

from ..dialects.markdown import MarkdownDialect
from ..schema import LanguageType, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import BaseParser


class MarkdownParser(BaseParser):
    """Markdown heading, table, and reference parser."""

    SUPPORTED_EXTENSIONS: Set[str] = {".md", ".markdown"}

    def __init__(self) -> None:
        self._dialect = MarkdownDialect()

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        lines = content.splitlines()
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        symbols: List[UnifiedSymbol] = []
        raw_headings: List[Dict[str, Union[int, str]]] = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            hm = heading_re.match(stripped)
            if hm:
                level = len(hm.group(1))
                title = hm.group(2).strip()
                kind_map = {
                    1: SymbolKind.DOC_HEADING_1.value,
                    2: SymbolKind.DOC_HEADING_2.value,
                    3: SymbolKind.DOC_HEADING_3.value,
                    4: SymbolKind.DOC_HEADING_4.value,
                }
                raw_headings.append({
                    "name": title,
                    "kind": kind_map.get(level, SymbolKind.DOC_HEADING_4.value),
                    "signature": f"{'#' * level} {title}",
                    "line_number": idx,
                })

        for i, h in enumerate(raw_headings):
            start_ln = int(h["line_number"])
            end_ln = int(raw_headings[i + 1]["line_number"]) - 1 if i + 1 < len(raw_headings) else len(lines)
            end_ln = max(start_ln, end_ln)
            doc = "\n".join(lines[start_ln:end_ln]).strip()
            name_str = str(h["name"])
            kind_str = str(h["kind"])
            sig_str = str(h["signature"])
            sym_id = UnifiedSymbol.compute_id(
                space=space,
                file_path=normalized_path,
                name=name_str,
                kind=kind_str,
                line_number=start_ln,
            )
            symbols.append(
                UnifiedSymbol(
                    id=sym_id,
                    name=name_str,
                    kind=kind_str,
                    file_path=normalized_path,
                    line_number=start_ln,
                    end_line=end_ln,
                    language=LanguageType.MARKDOWN.value,
                    docstring=doc,
                    signature=sig_str,
                    fqn=name_str,
                    search_payload=f"{name_str} {doc} {sig_str}".strip(),
                    metadata={"short_name": name_str, "end_line": end_ln},
                )
            )

        # Extract pipe tables
        in_table = False
        table_start = 0
        table_lines: List[str] = []
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    in_table = True
                    table_start = idx
                    table_lines = [stripped]
                else:
                    table_lines.append(stripped)
            else:
                if in_table and len(table_lines) >= 2:
                    t_name = f"Table: {table_lines[0].strip('|').strip()[:50]}"
                    t_doc = "\n".join(table_lines)
                    t_end = idx - 1
                    t_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=t_name,
                        kind=SymbolKind.DOC_TABLE.value,
                        line_number=table_start,
                    )
                    symbols.append(
                        UnifiedSymbol(
                            id=t_id,
                            name=t_name,
                            kind=SymbolKind.DOC_TABLE.value,
                            file_path=normalized_path,
                            line_number=table_start,
                            end_line=t_end,
                            language=LanguageType.MARKDOWN.value,
                            docstring=t_doc,
                            signature="markdown_table",
                            fqn=t_name,
                            search_payload=f"{t_name} {t_doc}".strip(),
                            metadata={"short_name": t_name, "end_line": t_end},
                        )
                    )
                in_table = False
                table_lines = []

        if in_table and len(table_lines) >= 2:
            t_name = f"Table: {table_lines[0].strip('|').strip()[:50]}"
            t_doc = "\n".join(table_lines)
            t_end = len(lines)
            t_id = UnifiedSymbol.compute_id(
                space=space,
                file_path=normalized_path,
                name=t_name,
                kind=SymbolKind.DOC_TABLE.value,
                line_number=table_start,
            )
            symbols.append(
                UnifiedSymbol(
                    id=t_id,
                    name=t_name,
                    kind=SymbolKind.DOC_TABLE.value,
                    file_path=normalized_path,
                    line_number=table_start,
                    end_line=t_end,
                    language=LanguageType.MARKDOWN.value,
                    docstring=t_doc,
                    signature="markdown_table",
                    fqn=t_name,
                    search_payload=f"{t_name} {t_doc}".strip(),
                    metadata={"short_name": t_name, "end_line": t_end},
                )
            )

        if not symbols and lines:
            return self._dialect.fallback_symbols(normalized_path, lines, space)

        symbols.sort(key=lambda s: s.line_number)
        return symbols

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        normalized_path = file_path.replace("\\", "/")
        return self._dialect.extract_custom_call_sites(normalized_path, content, space) or []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        return self._dialect.extract_imports(content, file_path=file_path)
