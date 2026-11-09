"""
Base abstract parser (`BaseParser`) and peer `SymbolProcessor` contract for module:ast.
"""

from abc import ABC, abstractmethod
import bisect
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple, Union

from ..schema import (
    FileImportTable,
    FileSymbolGraph,
    MemberInfo,
    ProvenanceStep,
    RelationEdge,
    Span,
    SymbolCallSite,
    SymbolNode,
    UnifiedSymbol,
)

_PARTIAL_SIG_RE = re.compile(r"\bpartial\s+(?:class|struct|interface|record)\b")


def is_partial_declaration(
    kind_or_kinds: Union[str, FrozenSet[str], Set[str], Tuple[str, ...]],
    signature: str = "",
    facets_or_meta: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Check whether a symbol or node declaration is a C# `partial class/struct/interface/record`."""
    type_container_kinds = {"class", "struct", "interface"}
    if isinstance(kind_or_kinds, str):
        if kind_or_kinds not in type_container_kinds:
            return False
    else:
        if not (set(kind_or_kinds) & type_container_kinds):
            return False
    if facets_or_meta:
        if facets_or_meta.get("is_partial"):
            return True
        mods = facets_or_meta.get("modifiers")
        if isinstance(mods, (list, tuple, set, frozenset)) and "partial" in mods:
            return True
        if not signature:
            signature = str(facets_or_meta.get("signature") or "")
    if signature and _PARTIAL_SIG_RE.search(signature):
        return True
    return False


class SymbolProcessor:
    """
    Peer symbol and relation edge processor injected via `contributes.ast.languages[*].processors`.
    Transforms or enriches `FileSymbolGraph` nodes and edges and appends a deterministic
    `ProvenanceStep(action="refine")` record.
    """

    provider_id: str = "ast:default_processor"

    def refine_node(
        self,
        node: SymbolNode,
        source_bytes: bytes,
    ) -> SymbolNode:
        """Refine a single `SymbolNode` (and optionally its children) in a file symbol graph."""
        return node

    def refine_edge(
        self,
        edge: RelationEdge,
        source_bytes: bytes,
    ) -> RelationEdge:
        """Refine a single `RelationEdge` in a file symbol graph."""
        return edge

    def refine_file_graph(
        self,
        graph: FileSymbolGraph,
        source_bytes: bytes,
    ) -> FileSymbolGraph:
        """Apply `refine_node` recursively across `root_nodes` and `refine_edge` across `outgoing_edges`."""

        def _walk_refine(nodes: Tuple[SymbolNode, ...]) -> Tuple[SymbolNode, ...]:
            out_nodes: List[SymbolNode] = []
            for n in nodes:
                refined_children = _walk_refine(n.children) if n.children else ()
                candidate = (
                    SymbolNode(
                        id=n.id,
                        name=n.name,
                        scope_path=n.scope_path,
                        kinds=n.kinds,
                        language=n.language,
                        span=n.span,
                        parts=n.parts,
                        facets=n.facets,
                        children=refined_children,
                        provenance=n.provenance,
                    )
                    if refined_children != n.children
                    else n
                )
                refined = self.refine_node(candidate, source_bytes)
                out_nodes.append(refined)
            return tuple(out_nodes)

        new_roots = _walk_refine(graph.root_nodes)
        new_edges = tuple(self.refine_edge(e, source_bytes) for e in graph.outgoing_edges)
        if new_roots == graph.root_nodes and new_edges == graph.outgoing_edges:
            return graph
        return FileSymbolGraph(
            file_path=graph.file_path,
            content_hash=graph.content_hash,
            language=graph.language,
            root_nodes=new_roots,
            outgoing_edges=new_edges,
        )


class ModulePathResolver:
    """
    Peer module import path resolver injected via `contributes.ast.languages[*].module_resolver`.
    Resolves an import `target_expr` from `importing_file` into a target workspace file path,
    target `SymbolNode.id` tuple, and whether the import refers to an external stdlib/third-party package.
    """

    provider_id: str = "ast:default_module_resolver"

    def resolve_import(
        self,
        importing_file: str,
        target_expr: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]:
        """
        Return `(resolved_file_path, resolved_symbol_ids, is_external)`.
        Default base implementation returns `(None, (), True)`.
        """
        return None, (), True


class EdgeRefiner:
    """
    Peer workspace relation edge refiner injected via `contributes.ast.languages[*].edge_refiners`.
    Allows external high-precision analyzers (e.g. `symtable`, type checkers, SCIP) to converge
    `ambiguous` or `unresolved` edges into `resolved` and append a `ProvenanceStep(action="refine")`.
    """

    provider_id: str = "ast:default_edge_refiner"

    def refine_workspace_edges(
        self,
        edges: Tuple[RelationEdge, ...],
        nodes_by_id: Mapping[str, SymbolNode],
        file_import_tables: Mapping[str, FileImportTable],
    ) -> Tuple[RelationEdge, ...]:
        """Refine a sequence of cross-file `RelationEdge` instances after Pass 4."""
        return edges


def compute_content_hash(content_bytes: bytes) -> str:
    """Compute a 32-char hex Blake2b digest (16-byte digest_size) aligned with `core.space.hasher`."""
    return hashlib.blake2b(content_bytes, digest_size=16).hexdigest()


def build_line_byte_offsets(content_bytes: bytes) -> Tuple[int, ...]:
    """Return 0-based byte start offsets for each 1-based line in `content_bytes`."""
    offsets: List[int] = [0]
    pos = 0
    n = len(content_bytes)
    while pos < n:
        nl = content_bytes.find(b"\n", pos)
        if nl == -1:
            break
        offsets.append(nl + 1)
        pos = nl + 1
    return tuple(offsets)


def _byte_offset_to_line_col(
    byte_offset: int,
    line_offsets: Tuple[int, ...],
    content_bytes: bytes,
) -> Tuple[int, int]:
    """Convert a 0-based byte offset into a `(1-based line, 0-based UTF-8 char column)` pair."""
    if not line_offsets:
        return 1, 0
    clamped = max(0, min(byte_offset, len(content_bytes)))
    line_idx = max(0, bisect.bisect_right(line_offsets, clamped) - 1)
    line_start = line_offsets[line_idx]
    char_col = len(content_bytes[line_start:clamped].decode("utf-8", errors="replace"))
    return line_idx + 1, char_col


def span_from_lines(
    start_line: int,
    end_line: int,
    line_offsets: Tuple[int, ...],
    total_bytes: int,
    content_bytes: Optional[bytes] = None,
) -> Span:
    """Construct a `Span` covering 1-based `[start_line, end_line]` using `line_offsets`."""
    if not line_offsets:
        return Span(start_byte=0, end_byte=0, start_line=1, start_col=0, end_line=1, end_col=0)
    total_lines = len(line_offsets)
    s_ln = max(1, min(start_line, total_lines))
    e_ln = max(s_ln, min(end_line, total_lines))
    s_byte = line_offsets[s_ln - 1]
    e_byte = line_offsets[e_ln] if e_ln < total_lines else total_bytes
    if content_bytes is not None:
        e_col = len(content_bytes[line_offsets[e_ln - 1] : e_byte].decode("utf-8", errors="replace"))
    else:
        e_col = max(0, e_byte - line_offsets[e_ln - 1])
    return Span(
        start_byte=s_byte,
        end_byte=e_byte,
        start_line=s_ln,
        start_col=0,
        end_line=e_ln,
        end_col=e_col,
    )


def _build_legacy_parts_spans(
    outer_span: Span,
    short_name: str,
    signature: str,
    docstring: str,
    return_type: str,
    content_bytes: bytes,
    line_offsets: Tuple[int, ...],
) -> Dict[str, Span]:
    """Compute structural `parts` spans (`name`, `signature`, `doc`, `body`, `return_type`) for a legacy symbol."""
    parts: Dict[str, Span] = {}
    total_bytes = len(content_bytes)
    if not line_offsets or outer_span.end_byte <= outer_span.start_byte:
        parts["name"] = outer_span
        return parts

    first_ln_idx = max(0, min(outer_span.start_line - 1, len(line_offsets) - 1))
    first_ln_sb = line_offsets[first_ln_idx]
    first_ln_eb = line_offsets[first_ln_idx + 1] if (first_ln_idx + 1) < len(line_offsets) else total_bytes
    first_ln_raw = content_bytes[first_ln_sb:first_ln_eb]
    first_ln_trimmed = first_ln_raw.rstrip(b" \t\r\n")
    first_ln_trim_eb = first_ln_sb + len(first_ln_trimmed)

    # 1. `name` span: locate `short_name` inside the first line or outer_span
    name_b = short_name.encode("utf-8", errors="replace") if short_name else b""
    name_pos = -1
    search_base = first_ln_sb
    if name_b:
        name_pos = first_ln_raw.find(name_b)
        if name_pos == -1:
            search_base = outer_span.start_byte
            name_pos = content_bytes[outer_span.start_byte : outer_span.end_byte].find(name_b)
    if name_b and name_pos != -1:
        n_sb = search_base + name_pos
        n_eb = n_sb + len(name_b)
        n_sl, n_sc = _byte_offset_to_line_col(n_sb, line_offsets, content_bytes)
        n_el, n_ec = _byte_offset_to_line_col(n_eb, line_offsets, content_bytes)
        parts["name"] = Span(
            start_byte=n_sb,
            end_byte=n_eb,
            start_line=n_sl,
            start_col=n_sc,
            end_line=n_el,
            end_col=n_ec,
        )
    else:
        n_eb = max(first_ln_sb, first_ln_trim_eb)
        _, n_ec = _byte_offset_to_line_col(n_eb, line_offsets, content_bytes)
        parts["name"] = Span(
            start_byte=first_ln_sb,
            end_byte=n_eb,
            start_line=outer_span.start_line,
            start_col=0,
            end_line=outer_span.start_line,
            end_col=n_ec,
        )

    # 2. `signature` span
    sig_b = (signature or "").strip().encode("utf-8", errors="replace")
    sig_pos = content_bytes[outer_span.start_byte : outer_span.end_byte].find(sig_b) if sig_b else -1
    if sig_b and sig_pos != -1:
        s_sb = outer_span.start_byte + sig_pos
        s_eb = s_sb + len(sig_b)
        s_sl, s_sc = _byte_offset_to_line_col(s_sb, line_offsets, content_bytes)
        s_el, s_ec = _byte_offset_to_line_col(s_eb, line_offsets, content_bytes)
        parts["signature"] = Span(
            start_byte=s_sb,
            end_byte=s_eb,
            start_line=s_sl,
            start_col=s_sc,
            end_line=s_el,
            end_col=s_ec,
        )
        if "(" in signature and ")" in signature:
            lpar = sig_b.find(b"(")
            rpar = sig_b.rfind(b")")
            if lpar != -1 and rpar != -1 and rpar >= lpar:
                p_sb = s_sb + lpar
                p_eb = s_sb + rpar + 1
                p_sl, p_sc = _byte_offset_to_line_col(p_sb, line_offsets, content_bytes)
                p_el, p_ec = _byte_offset_to_line_col(p_eb, line_offsets, content_bytes)
                parts["parameters"] = Span(
                    start_byte=p_sb,
                    end_byte=p_eb,
                    start_line=p_sl,
                    start_col=p_sc,
                    end_line=p_el,
                    end_col=p_ec,
                )
    elif first_ln_trim_eb > first_ln_sb:
        sig_clean = first_ln_trimmed.rstrip(b":{;")
        s_eb = first_ln_sb + len(sig_clean)
        if s_eb > first_ln_sb:
            _, s_ec = _byte_offset_to_line_col(s_eb, line_offsets, content_bytes)
            parts["signature"] = Span(
                start_byte=first_ln_sb,
                end_byte=s_eb,
                start_line=outer_span.start_line,
                start_col=0,
                end_line=outer_span.start_line,
                end_col=s_ec,
            )

    # 3. `return_type` span
    if return_type:
        rt_b = return_type.strip().encode("utf-8", errors="replace")
        rt_pos = first_ln_raw.find(rt_b)
        if rt_pos != -1:
            r_sb = first_ln_sb + rt_pos
            r_eb = r_sb + len(rt_b)
            r_sl, r_sc = _byte_offset_to_line_col(r_sb, line_offsets, content_bytes)
            r_el, r_ec = _byte_offset_to_line_col(r_eb, line_offsets, content_bytes)
            parts["return_type"] = Span(
                start_byte=r_sb,
                end_byte=r_eb,
                start_line=r_sl,
                start_col=r_sc,
                end_line=r_el,
                end_col=r_ec,
            )

    # 4. `doc` span
    if docstring:
        doc_b = docstring.strip().encode("utf-8", errors="replace")
        doc_pos = content_bytes[outer_span.start_byte : outer_span.end_byte].find(doc_b)
        if doc_pos != -1:
            d_sb = outer_span.start_byte + doc_pos
            d_eb = d_sb + len(doc_b)
            d_sl, d_sc = _byte_offset_to_line_col(d_sb, line_offsets, content_bytes)
            d_el, d_ec = _byte_offset_to_line_col(d_eb, line_offsets, content_bytes)
            parts["doc"] = Span(
                start_byte=d_sb,
                end_byte=d_eb,
                start_line=d_sl,
                start_col=d_sc,
                end_line=d_el,
                end_col=d_ec,
            )
        elif outer_span.start_byte > 0:
            prev_pos = content_bytes[: outer_span.start_byte].rfind(doc_b)
            if prev_pos != -1:
                d_sb = prev_pos
                d_eb = d_sb + len(doc_b)
                d_sl, d_sc = _byte_offset_to_line_col(d_sb, line_offsets, content_bytes)
                d_el, d_ec = _byte_offset_to_line_col(d_eb, line_offsets, content_bytes)
                parts["doc"] = Span(
                    start_byte=d_sb,
                    end_byte=d_eb,
                    start_line=d_sl,
                    start_col=d_sc,
                    end_line=d_el,
                    end_col=d_ec,
                )

    # 5. `body` span
    if outer_span.end_line > outer_span.start_line and (first_ln_idx + 1) < len(line_offsets):
        b_sb = line_offsets[first_ln_idx + 1]
        if b_sb < outer_span.end_byte:
            b_sl, b_sc = _byte_offset_to_line_col(b_sb, line_offsets, content_bytes)
            b_el, b_ec = _byte_offset_to_line_col(outer_span.end_byte, line_offsets, content_bytes)
            parts["body"] = Span(
                start_byte=b_sb,
                end_byte=outer_span.end_byte,
                start_line=b_sl,
                start_col=b_sc,
                end_line=b_el,
                end_col=b_ec,
            )

    return parts


def convert_legacy_symbols_to_file_graph(
    file_path: str,
    content: str,
    language: str,
    provider_id: str,
    symbols: List[UnifiedSymbol],
    call_sites: Optional[List[SymbolCallSite]] = None,
    imports: Optional[Dict[str, str]] = None,
) -> FileSymbolGraph:
    """Bridge legacy `UnifiedSymbol` / `SymbolCallSite` / `imports` into an immutable `FileSymbolGraph`."""
    norm_path = str(file_path).replace("\\", "/")
    content_bytes = (content or "").encode("utf-8", errors="replace")
    c_hash = compute_content_hash(content_bytes)
    line_offsets = build_line_byte_offsets(content_bytes)
    total_bytes = len(content_bytes)
    prov = (ProvenanceStep(provider_id=provider_id, action="extract", rule_or_hook="parse"),)

    sym_by_id: Dict[str, UnifiedSymbol] = {s.id: s for s in symbols if s.id}
    children_syms_by_parent: Dict[str, List[UnifiedSymbol]] = {}
    top_syms: List[UnifiedSymbol] = []
    for sym in symbols:
        if sym.parent_id and sym.parent_id in sym_by_id:
            children_syms_by_parent.setdefault(sym.parent_id, []).append(sym)
        else:
            top_syms.append(sym)

    fqn_counts: Dict[str, int] = {}
    for sym in symbols:
        meta = sym.metadata or {}
        raw_scope = meta.get("scope_path")
        if isinstance(raw_scope, (list, tuple)):
            scope_tup = tuple(str(x) for x in raw_scope if str(x))
        elif sym.scope_path:
            scope_tup = tuple(s for s in sym.scope_path.split(".") if s)
        else:
            scope_tup = ()
        short_name = str(meta.get("short_name") or sym.name.split(".")[-1] or sym.name)
        fqn_str = sym.fqn or (".".join((*scope_tup, short_name)) if scope_tup else short_name)
        fqn_counts[fqn_str] = fqn_counts.get(fqn_str, 0) + 1

    nodes_by_legacy_id: Dict[str, SymbolNode] = {}
    used_canonical_ids: Set[str] = set()

    def _build_node_recursive(sym: UnifiedSymbol) -> SymbolNode:
        meta = sym.metadata or {}
        if "start_byte" in meta and "end_byte" in meta:
            s_byte = int(meta["start_byte"])
            e_byte = int(meta["end_byte"])
            s_ln, s_col = _byte_offset_to_line_col(s_byte, line_offsets, content_bytes)
            e_ln, e_col = _byte_offset_to_line_col(e_byte, line_offsets, content_bytes)
            sp = Span(
                start_byte=s_byte,
                end_byte=e_byte,
                start_line=max(1, sym.line_number or s_ln),
                start_col=s_col,
                end_line=max(sym.line_number or s_ln, sym.end_line or e_ln),
                end_col=e_col,
            )
        else:
            sp = span_from_lines(
                sym.line_number,
                sym.end_line or sym.line_number,
                line_offsets,
                total_bytes,
                content_bytes=content_bytes,
            )

        raw_scope = meta.get("scope_path")
        if isinstance(raw_scope, (list, tuple)):
            scope_tup = tuple(str(x) for x in raw_scope if str(x))
        elif sym.scope_path:
            scope_tup = tuple(s for s in sym.scope_path.split(".") if s)
        else:
            scope_tup = ()

        short_name = str(meta.get("short_name") or sym.name.split(".")[-1] or sym.name)
        fqn_str = sym.fqn or (".".join((*scope_tup, short_name)) if scope_tup else short_name)
        overload_sfx = ""
        if fqn_counts.get(fqn_str, 0) > 1:
            if sym.kind in ("method", "function", "constructor") and "(" in (sym.signature or ""):
                lpar = sym.signature.find("(")
                rpar = sym.signature.rfind(")")
                if lpar != -1 and rpar != -1 and rpar >= lpar:
                    overload_sfx = f"({' '.join(sym.signature[lpar + 1 : rpar].split())})"
            if not overload_sfx:
                overload_sfx = f"L{sym.line_number}"
        canonical_id = SymbolNode.compute_canonical_id(norm_path, fqn_str, overload_suffix=overload_sfx)
        if canonical_id in used_canonical_ids:
            canonical_id = SymbolNode.compute_canonical_id(
                norm_path, fqn_str, overload_suffix=f"L{sym.line_number}_{len(used_canonical_ids)}"
            )
        used_canonical_ids.add(canonical_id)

        child_nodes: List[SymbolNode] = []
        seen_child_names_lines: Set[Tuple[str, int]] = set()
        for ch_sym in children_syms_by_parent.get(sym.id, ()):
            ch_node = _build_node_recursive(ch_sym)
            child_nodes.append(ch_node)
            seen_child_names_lines.add((ch_node.name, ch_node.span.start_line))

        for m in sym.children:
            if isinstance(m, MemberInfo):
                if (m.name, m.line_number) in seen_child_names_lines or any(
                    cn.name == m.name and m.kind in cn.kinds for cn in child_nodes
                ):
                    continue
                m_span = span_from_lines(
                    m.line_number,
                    m.line_number,
                    line_offsets,
                    total_bytes,
                    content_bytes=content_bytes,
                )
                m_scope = (*scope_tup, short_name)
                m_fqn = m.fqn or ".".join((*m_scope, m.name))
                m_id = SymbolNode.compute_canonical_id(norm_path, m_fqn)
                if m_id in used_canonical_ids:
                    m_id = SymbolNode.compute_canonical_id(norm_path, m_fqn, overload_suffix=f"L{m.line_number}")
                used_canonical_ids.add(m_id)
                m_parts = _build_legacy_parts_spans(
                    outer_span=m_span,
                    short_name=m.name,
                    signature=m.signature,
                    docstring=m.docstring,
                    return_type=m.return_type,
                    content_bytes=content_bytes,
                    line_offsets=line_offsets,
                )
                child_nodes.append(
                    SymbolNode(
                        id=m_id,
                        name=m.name,
                        scope_path=m_scope,
                        kinds=frozenset({m.kind}),
                        language=sym.language or language,
                        span=m_span,
                        parts=m_parts,
                        facets={
                            "visibility": m.visibility,
                            "is_static": m.is_static,
                            "signature": m.signature,
                            "docstring": m.docstring,
                            "return_type": m.return_type,
                        },
                        children=(),
                        provenance=prov,
                    )
                )

        child_nodes.sort(key=lambda c: (c.span.start_byte, c.name))

        facets_dict: Dict[str, Any] = {
            "visibility": sym.visibility,
            "signature": sym.signature,
            "docstring": sym.docstring,
            "return_type": sym.return_type,
        }
        if meta.get("is_static"):
            facets_dict["is_static"] = True
        if is_partial_declaration(sym.kind, sym.signature, meta):
            facets_dict["is_partial"] = True
        if meta.get("base_types"):
            facets_dict["base_types"] = tuple(meta["base_types"])
        if meta.get("field_types") and isinstance(meta["field_types"], Mapping):
            facets_dict["field_types"] = dict(meta["field_types"])

        node_parts = _build_legacy_parts_spans(
            outer_span=sp,
            short_name=short_name,
            signature=sym.signature,
            docstring=sym.docstring,
            return_type=sym.return_type,
            content_bytes=content_bytes,
            line_offsets=line_offsets,
        )

        node = SymbolNode(
            id=canonical_id,
            name=short_name,
            scope_path=scope_tup,
            kinds=frozenset({sym.kind}),
            language=sym.language or language,
            span=sp,
            parts=node_parts,
            facets=facets_dict,
            children=tuple(child_nodes),
            provenance=prov,
        )
        nodes_by_legacy_id[sym.id] = node
        return node

    root_nodes = [_build_node_recursive(sym) for sym in top_syms]

    edges: List[RelationEdge] = []
    file_root_id = f"{norm_path}::<module>"
    for sym in symbols:
        node = nodes_by_legacy_id.get(sym.id)
        if node is None:
            continue
        for bt in (sym.metadata or {}).get("base_types") or ():
            bt_str = str(bt).strip()
            if not bt_str:
                continue
            short_b = bt_str.split(".")[-1].split("::")[-1].strip()
            edge_k = (
                "implements"
                if (len(short_b) >= 2 and short_b[0] == "I" and short_b[1].isupper())
                else "inherits"
            )
            edges.append(
                RelationEdge(
                    source_id=node.id,
                    target_expr=bt_str,
                    edge_kind=edge_k,
                    span=node.span,
                    provenance=prov,
                )
            )

    if imports:
        for alias, target_mod in imports.items():
            alias_str = str(alias).strip()
            target_str = str(target_mod or alias).strip()
            if not target_str:
                continue
            if alias_str.startswith("*:") or alias_str == "*":
                expr = f"*={target_str}"
            elif alias_str.startswith("export*:"):
                expr = f"export*={target_str}"
            elif alias_str and alias_str != target_str:
                expr = f"{alias_str}={target_str}"
            else:
                expr = target_str
            edges.append(
                RelationEdge(
                    source_id=file_root_id,
                    target_expr=expr,
                    edge_kind="imports",
                    span=Span(start_byte=0, end_byte=0, start_line=1, start_col=0, end_line=1, end_col=0),
                    provenance=prov,
                )
            )
    if call_sites:
        for cs in call_sites:
            src_node = nodes_by_legacy_id.get(cs.caller_symbol_id)
            src_id = src_node.id if src_node is not None else file_root_id
            expr = f"{cs.context_prefix}.{cs.callee_name}" if cs.context_prefix else cs.callee_name
            cs_span = span_from_lines(
                cs.line_number,
                cs.line_number,
                line_offsets,
                total_bytes,
                content_bytes=content_bytes,
            )
            edges.append(
                RelationEdge(
                    source_id=src_id,
                    target_expr=expr,
                    edge_kind="calls",
                    span=cs_span,
                    provenance=prov,
                )
            )

    return FileSymbolGraph(
        file_path=norm_path,
        content_hash=c_hash,
        language=language,
        root_nodes=tuple(root_nodes),
        outgoing_edges=tuple(edges),
    )


class BaseParser(ABC):
    """Multi-language AST symbol parser abstract interface."""

    SUPPORTED_EXTENSIONS: Any = frozenset()
    SPACES: Tuple[str, ...] = ()

    @abstractmethod
    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """Return True if this parser supports parsing `file_path`."""

    @abstractmethod
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """Parse `content` of `file_path` in `space` and return a list of UnifiedSymbol instances."""

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """Extract symbol call sites from `content`."""
        return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """Extract file-level import/include alias mappings from `content`."""
        return {}

    def extract_file_graph(
        self,
        file_path: str,
        content: str,
        *,
        space: str = "unified",
    ) -> FileSymbolGraph:
        """Extract an immutable `FileSymbolGraph` in a single logical pass and cache derived artifacts."""
        norm_path = str(file_path).replace("\\", "/")
        syms = self.parse(file_path=norm_path, content=content, space=space)
        calls = self.extract_call_sites(file_path=norm_path, content=content, space=space, symbols=syms)
        imps = self.extract_imports(file_path=norm_path, content=content)
        lang = syms[0].language if syms else getattr(self, "language_name", self.__class__.__name__.lower())
        if lang.endswith("parser"):
            lang = lang[: -len("parser")]
        prov_id = f"ast:{self.__class__.__name__}"
        fg = convert_legacy_symbols_to_file_graph(
            file_path=norm_path,
            content=content,
            language=lang,
            provider_id=prov_id,
            symbols=syms,
            call_sites=calls,
            imports=imps,
        )
        self._last_base_extract_cache = (
            norm_path,
            len(content),
            id(content),
            content,
            space,
            syms,
            calls,
            dict(imps or {}),
            fg,
        )
        return fg
