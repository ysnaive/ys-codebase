"""
Standalone Markdown parser (`MarkdownParser`) for module:ast.
Supports ATX/Setext headings, pipe tables, section docstrings, and markdown reference call sites.
"""

from pathlib import Path
import re
from typing import Dict, FrozenSet, List, Optional, Tuple, Union

from ..dialects.markdown import MarkdownDialect
from ..schema import (
    FileSymbolGraph,
    LanguageType,
    ProvenanceStep,
    RelationEdge,
    Span,
    SymbolCallSite,
    SymbolKind,
    SymbolNode,
    UnifiedSymbol,
)
from .base import BaseParser, build_line_byte_offsets, compute_content_hash, span_from_lines

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_MD_LINK_DOC_RE = re.compile(r"\[([^\]]+)\]\((?:file:///)?([^)\s]+)\)")
_MD_BACKTICK_DOC_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*)(?:\([^`]*\))?`")


class MarkdownParser(BaseParser):
    """Markdown heading, table, and reference parser."""

    SUPPORTED_EXTENSIONS: FrozenSet[str] = frozenset({".md", ".markdown"})

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
        symbols: List[UnifiedSymbol] = []
        raw_headings: List[Dict[str, Union[int, str]]] = []

        active_fence: Optional[str] = None
        for idx, line in enumerate(lines, start=1):
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

        # Extract pipe tables (ignoring fenced code blocks)
        in_table = False
        table_start = 0
        table_lines: List[str] = []
        active_fence = None

        def _flush_table(end_idx: int) -> None:
            nonlocal in_table, table_lines
            if in_table and len(table_lines) >= 2:
                t_name = f"Table: {table_lines[0].strip('|').strip()[:50]}"
                t_doc = "\n".join(table_lines)
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
                        end_line=end_idx,
                        language=LanguageType.MARKDOWN.value,
                        docstring=t_doc,
                        signature="markdown_table",
                        fqn=t_name,
                        search_payload=f"{t_name} {t_doc}".strip(),
                        metadata={"short_name": t_name, "end_line": end_idx},
                    )
                )
            in_table = False
            table_lines = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            fm = _FENCE_RE.match(stripped)
            if fm:
                _flush_table(idx - 1)
                fence_marker = fm.group(1)
                if active_fence is None:
                    active_fence = fence_marker
                elif stripped.startswith(active_fence[0] * len(active_fence)):
                    active_fence = None
                continue
            if active_fence is not None:
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    in_table = True
                    table_start = idx
                    table_lines = [stripped]
                else:
                    table_lines.append(stripped)
            else:
                _flush_table(idx - 1)

        _flush_table(len(lines))

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

    def extract_file_graph(
        self,
        file_path: str,
        content: str,
        *,
        space: str = "unified",
    ) -> FileSymbolGraph:
        normalized_path = str(file_path).replace("\\", "/")
        content_bytes = (content or "").encode("utf-8", errors="replace")
        c_hash = compute_content_hash(content_bytes)
        if not content or not content.strip():
            return FileSymbolGraph(
                file_path=normalized_path,
                content_hash=c_hash,
                language=LanguageType.MARKDOWN.value,
            )

        base_graph = super().extract_file_graph(file_path=normalized_path, content=content, space=space)
        line_offsets = build_line_byte_offsets(content_bytes)
        total_bytes = len(content_bytes)
        file_root_id = f"{normalized_path}::<module>"
        doc_prov = (ProvenanceStep(provider_id="ast:MarkdownParser", action="extract", rule_or_hook="@edge.documents"),)

        # Map line ranges to heading SymbolNode IDs
        heading_nodes = sorted(
            base_graph.all_nodes_by_id.values(),
            key=lambda n: (n.span.end_line - n.span.start_line, n.span.start_line),
        )

        def _enclosing_doc_node_id(line_no: int) -> str:
            for hn in heading_nodes:
                if hn.span.start_line <= line_no <= hn.span.end_line:
                    return hn.id
            return file_root_id

        edges: List[RelationEdge] = list(base_graph.outgoing_edges)
        seen_doc_edges = {
            (e.source_id, e.target_expr, e.edge_kind, e.span.start_line)
            for e in edges
        }

        active_fence: Optional[str] = None
        for idx, line in enumerate(content.splitlines(), start=1):
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

            src_id = _enclosing_doc_node_id(idx)
            ln_span = span_from_lines(idx, idx, line_offsets, total_bytes)

            for m_link in _MD_LINK_DOC_RE.finditer(line):
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

                dkey = (src_id, doc_expr, "documents", idx)
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

            for m_bt in _MD_BACKTICK_DOC_RE.finditer(line):
                bt_sym = m_bt.group(1).strip()
                dkey = (src_id, bt_sym, "documents", idx)
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

        return FileSymbolGraph(
            file_path=base_graph.file_path,
            content_hash=base_graph.content_hash,
            language=base_graph.language,
            root_nodes=base_graph.root_nodes,
            outgoing_edges=tuple(edges),
        )
