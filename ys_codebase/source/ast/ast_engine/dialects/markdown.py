"""
Markdown dialect adapter for module:ast.
Handles heading levels, tables, section docstring slicing, fallback section creation, and markdown link/backtick references.
"""

import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..parsers.base import build_line_byte_offsets, span_from_lines
from ..schema import ProvenanceStep, RelationEdge, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import DialectAdapter

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LINK_CALL_RE = re.compile(r"\[`?([A-Za-z0-9_$.]+)`?\]\((?:file:///)?([^)#\s]+)(?:#L?\d+(?:-\d+)?)?\)")
_CODE_CALL_RE = re.compile(r"`([A-Za-z0-9_$]+\.[A-Za-z0-9_$]+)(?:\([^`]*\))?`")
_IMPORT_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)#\s]+)(?:#[^)]*)?\)")
_MD_LINK_DOC_RE = re.compile(r"\[([^\]]+)\]\((?:file:///)?([^)\s]+)\)")
_MD_BACKTICK_DOC_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*)(?:\([^`]*\))?`")


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
        current_heading = "<document>"
        active_fence: Optional[str] = None
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            fm = _FENCE_RE.match(stripped)
            if fm:
                fence_marker = fm.group(1)
                if active_fence is None:
                    active_fence = fence_marker
                elif stripped.startswith(active_fence[0] * len(active_fence)):
                    active_fence = None
                continue
            if active_fence is not None:
                continue

            hm = _HEADING_RE.match(stripped)
            if hm:
                current_heading = hm.group(2).strip()
                continue
            for m in _LINK_CALL_RE.finditer(line):
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
            for m in _CODE_CALL_RE.finditer(line):
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

    def extract_custom_relation_edges(
        self,
        normalized_path: str,
        content: str,
        content_bytes: bytes,
        enclosing_id_resolver: Callable[[int, int], str],
        provider_id: str = "",
    ) -> List[RelationEdge]:
        if not content:
            return []
        line_offsets = build_line_byte_offsets(content_bytes)
        total_bytes = len(content_bytes)
        eff_prov_id = provider_id or "ast:markdown/default.scm"
        doc_prov = (
            ProvenanceStep(
                provider_id=eff_prov_id,
                action="extract",
                rule_or_hook="@edge.documents",
            ),
        )
        edges: List[RelationEdge] = []
        seen_doc_edges: Set[Tuple[str, str, str, int, int]] = set()
        active_fence: Optional[str] = None
        for idx_ln, line_str in enumerate(content.splitlines(), start=1):
            stripped_ln = line_str.strip()
            fm = _FENCE_RE.match(stripped_ln)
            if fm:
                fence_marker = fm.group(1)
                if active_fence is None:
                    active_fence = fence_marker
                elif stripped_ln.startswith(active_fence[0] * len(active_fence)):
                    active_fence = None
                continue
            if active_fence is not None:
                continue

            ln_span = span_from_lines(idx_ln, idx_ln, line_offsets, total_bytes, content_bytes=content_bytes)
            src_id = enclosing_id_resolver(ln_span.start_byte, idx_ln)

            for m_link in _MD_LINK_DOC_RE.finditer(line_str):
                link_label = m_link.group(1).strip().strip("`")
                link_target = m_link.group(2).strip()
                if link_target.startswith(("http://", "https://", "mailto:")):
                    continue
                if "#" in link_target:
                    path_part, anchor_part = link_target.split("#", 1)
                    if re.match(r"^L?\d+(?:-\d+)?$", anchor_part) and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", link_label):
                        doc_expr = f"{path_part}#{link_label}"
                    else:
                        doc_expr = link_target
                elif re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", link_label) and "." in link_label:
                    doc_expr = f"{link_target}#{link_label}"
                else:
                    doc_expr = link_target
                dkey = (src_id, doc_expr, "documents", ln_span.start_byte, ln_span.end_byte)
                if dkey not in seen_doc_edges:
                    seen_doc_edges.add(dkey)
                    edges.append(
                        RelationEdge(
                            source_id=src_id,
                            target_expr=doc_expr,
                            edge_kind="documents",
                            span=ln_span,
                            provenance=doc_prov,
                        )
                    )
            for m_bt in _MD_BACKTICK_DOC_RE.finditer(line_str):
                bt_sym = m_bt.group(1).strip()
                dkey = (src_id, bt_sym, "documents", ln_span.start_byte, ln_span.end_byte)
                if dkey not in seen_doc_edges:
                    seen_doc_edges.add(dkey)
                    edges.append(
                        RelationEdge(
                            source_id=src_id,
                            target_expr=bt_sym,
                            edge_kind="documents",
                            span=ln_span,
                            provenance=doc_prov,
                        )
                    )
        return edges

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        for match in _IMPORT_LINK_RE.finditer(source_text):
            text = match.group(1).strip()
            target = match.group(2).strip()
            if not target.startswith(("http://", "https://", "mailto:")):
                stem = Path(target).stem
                imports[text] = target
                imports[stem] = target
                imports[target] = target
        return imports
