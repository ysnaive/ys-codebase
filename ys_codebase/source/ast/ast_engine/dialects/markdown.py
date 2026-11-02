"""
Markdown dialect adapter for module:ast.
Handles heading levels, tables, section docstring slicing, fallback section creation, and markdown link/backtick references.
"""

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from ..schema import SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import DialectAdapter


class MarkdownDialect(DialectAdapter):
    language = "markdown"
    scope_separator = "."
    supports_partial_aggregation = False

    def post_process_raw_item(self, item: Dict[str, Any], def_node: Any) -> None:
        def_kind = item.get("kind", "")
        name = item.get("short_name", "")
        if def_kind == "heading":
            node_text = def_node.text.decode("utf-8", errors="replace").lstrip()
            level = len(node_text) - len(node_text.lstrip("#")) if node_text.startswith("#") else 1
            kind_map = {
                1: SymbolKind.DOC_HEADING_1.value,
                2: SymbolKind.DOC_HEADING_2.value,
                3: SymbolKind.DOC_HEADING_3.value,
                4: SymbolKind.DOC_HEADING_4.value,
            }
            item["kind"] = kind_map.get(level, SymbolKind.DOC_HEADING_4.value)
            item["signature"] = f"{'#' * level} {name}"
        elif def_kind == "table":
            item["kind"] = SymbolKind.DOC_TABLE.value
            table_first_line = def_node.text.decode("utf-8", errors="replace").splitlines()[0]
            item["short_name"] = f"Table: {table_first_line.strip('|').strip()[:50]}"
            item["signature"] = "markdown_table"
            item["docstring"] = def_node.text.decode("utf-8", errors="replace").strip()

    def finalize_raw_items(self, raw_items: List[Dict[str, Any]], lines: List[str]) -> List[Dict[str, Any]]:
        if not raw_items:
            return raw_items
        raw_items.sort(key=lambda x: x["start_line"])
        for idx, item in enumerate(raw_items):
            if str(item["kind"]).startswith("doc_heading") and not item["docstring"]:
                s_ln = item["start_line"]
                e_ln = raw_items[idx + 1]["start_line"] - 1 if idx + 1 < len(raw_items) else len(lines)
                item["docstring"] = "\n".join(lines[s_ln:e_ln]).strip()
                item["end_line"] = max(e_ln, s_ln)
        return raw_items

    def fallback_symbols(self, normalized_path: str, lines: List[str], space: str) -> List[UnifiedSymbol]:
        if not lines:
            return []
        non_empty = [l for l in lines if l.strip()]
        sec_name = non_empty[0][:60] if non_empty else os.path.basename(normalized_path)
        doc = "\n".join(lines[:200]).strip()
        total_lines = len(lines)
        sym_id = UnifiedSymbol.compute_id(
            space=space,
            file_path=normalized_path,
            name=sec_name,
            kind=SymbolKind.DOC_SECTION.value,
            line_number=1,
        )
        return [
            UnifiedSymbol(
                id=sym_id,
                name=sec_name,
                kind=SymbolKind.DOC_SECTION.value,
                file_path=normalized_path,
                line_number=1,
                end_line=total_lines,
                language="markdown",
                docstring=doc,
                signature="markdown_section",
                children=(),
                members=(),
                metadata={"fallback": True, "end_line": total_lines},
            )
        ]

    def extract_custom_call_sites(
        self,
        normalized_path: str,
        content: str,
        space: str,
    ) -> Optional[List[SymbolCallSite]]:
        call_sites: List[SymbolCallSite] = []
        link_re = re.compile(r"\[`?([A-Za-z0-9_$.]+)`?\]\((?:file:///)?([^)#\s]+)(?:#L?\d+(?:-\d+)?)?\)")
        code_re = re.compile(r"`([A-Za-z0-9_$]+\.[A-Za-z0-9_$]+)(?:\([^`]*\))?`")
        current_heading = "<document>"
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        for i, line in enumerate(content.splitlines(), start=1):
            hm = heading_re.match(line.strip())
            if hm:
                current_heading = hm.group(2).strip()
                continue
            for m in link_re.finditer(line):
                sym_str = m.group(1)
                prefix, callee = (
                    (sym_str.rsplit(".", 1)[0], sym_str.rsplit(".", 1)[1])
                    if "." in sym_str
                    else ("", sym_str)
                )
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
            for m in code_re.finditer(line):
                sym_str = m.group(1)
                prefix, callee = sym_str.rsplit(".", 1)
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

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        link_re = re.compile(r"\[([^\]]+)\]\(([^)#\s]+)(?:#[^)]*)?\)")
        for match in link_re.finditer(source_text):
            text = match.group(1).strip()
            target = match.group(2).strip()
            if not target.startswith(("http://", "https://", "mailto:")):
                stem = Path(target).stem
                imports[text] = target
                imports[stem] = target
                imports[target] = target
        return imports
