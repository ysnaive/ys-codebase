"""
Base abstract parser (`BaseParser`) and peer `SymbolProcessor` contract for module:ast.
"""

from abc import ABC, abstractmethod
import hashlib
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

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


def span_from_lines(
    start_line: int,
    end_line: int,
    line_offsets: Tuple[int, ...],
    total_bytes: int,
) -> Span:
    """Construct a `Span` covering 1-based `[start_line, end_line]` using `line_offsets`."""
    if not line_offsets:
        return Span(start_byte=0, end_byte=0, start_line=1, start_col=0, end_line=1, end_col=0)
    total_lines = len(line_offsets)
    s_ln = max(1, min(start_line, total_lines))
    e_ln = max(s_ln, min(end_line, total_lines))
    s_byte = line_offsets[s_ln - 1]
    e_byte = line_offsets[e_ln] if e_ln < total_lines else total_bytes
    e_col = max(0, e_byte - line_offsets[e_ln - 1])
    return Span(
        start_byte=s_byte,
        end_byte=e_byte,
        start_line=s_ln,
        start_col=0,
        end_line=e_ln,
        end_col=e_col,
    )


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

    nodes_by_legacy_id: Dict[str, SymbolNode] = {}
    root_nodes: List[SymbolNode] = []

    for sym in symbols:
        meta = sym.metadata or {}
        if "start_byte" in meta and "end_byte" in meta:
            s_byte = int(meta["start_byte"])
            e_byte = int(meta["end_byte"])
            sp = Span(
                start_byte=s_byte,
                end_byte=e_byte,
                start_line=max(1, sym.line_number),
                start_col=0,
                end_line=max(sym.line_number, sym.end_line or sym.line_number),
                end_col=0,
            )
        else:
            sp = span_from_lines(
                sym.line_number,
                sym.end_line or sym.line_number,
                line_offsets,
                total_bytes,
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
        canonical_id = SymbolNode.compute_canonical_id(norm_path, fqn_str)

        child_nodes: List[SymbolNode] = []
        for m in sym.children:
            if isinstance(m, MemberInfo):
                m_span = span_from_lines(m.line_number, m.line_number, line_offsets, total_bytes)
                m_scope = (*scope_tup, short_name)
                m_fqn = m.fqn or ".".join((*m_scope, m.name))
                m_id = SymbolNode.compute_canonical_id(norm_path, m_fqn)
                child_nodes.append(
                    SymbolNode(
                        id=m_id,
                        name=m.name,
                        scope_path=m_scope,
                        kinds=frozenset({m.kind}),
                        language=sym.language or language,
                        span=m_span,
                        parts={"name": m_span},
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

        facets_dict: Dict[str, Any] = {
            "visibility": sym.visibility,
            "signature": sym.signature,
            "docstring": sym.docstring,
            "return_type": sym.return_type,
        }
        if meta.get("is_static"):
            facets_dict["is_static"] = True
        if meta.get("is_partial"):
            facets_dict["is_partial"] = True
        if meta.get("base_types"):
            facets_dict["base_types"] = tuple(meta["base_types"])

        node = SymbolNode(
            id=canonical_id,
            name=short_name,
            scope_path=scope_tup,
            kinds=frozenset({sym.kind}),
            language=sym.language or language,
            span=sp,
            parts={"name": sp},
            facets=facets_dict,
            children=tuple(child_nodes),
            provenance=prov,
        )
        nodes_by_legacy_id[sym.id] = node
        root_nodes.append(node)

    edges: List[RelationEdge] = []
    file_root_id = f"{norm_path}::<module>"
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
            cs_span = span_from_lines(cs.line_number, cs.line_number, line_offsets, total_bytes)
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
        """Extract an immutable `FileSymbolGraph` in a single logical pass."""
        syms = self.parse(file_path=file_path, content=content, space=space)
        calls = self.extract_call_sites(file_path=file_path, content=content, space=space, symbols=syms)
        imps = self.extract_imports(file_path=file_path, content=content)
        lang = syms[0].language if syms else getattr(self, "language_name", self.__class__.__name__.lower())
        prov_id = f"ast:{self.__class__.__name__}"
        return convert_legacy_symbols_to_file_graph(
            file_path=file_path,
            content=content,
            language=lang,
            provider_id=prov_id,
            symbols=syms,
            call_sites=calls,
            imports=imps,
        )
