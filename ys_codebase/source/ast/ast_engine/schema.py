"""
Core data structures, enums, and schema models for module:ast (ast_engine).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .exceptions import SchemaValidationError


@dataclass(frozen=True)
class Span:
    """Exact physical source range supporting O(1) byte slicing and 1-based line/0-based col indexing."""

    start_byte: int
    end_byte: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def contains(self, other: "Span") -> bool:
        """Return True if this Span physically encloses `other`."""
        return self.start_byte <= other.start_byte and other.end_byte <= self.end_byte

    def union(self, other: "Span") -> "Span":
        """Compute the bounding-box Span union of `self` and `other` (commutative)."""
        if self.start_byte < other.start_byte:
            sb, sl, sc = self.start_byte, self.start_line, self.start_col
        elif other.start_byte < self.start_byte:
            sb, sl, sc = other.start_byte, other.start_line, other.start_col
        else:
            sb = self.start_byte
            sl = min(self.start_line, other.start_line)
            sc = min(self.start_col, other.start_col) if self.start_line == other.start_line else (
                self.start_col if self.start_line < other.start_line else other.start_col
            )

        if self.end_byte > other.end_byte:
            eb, el, ec = self.end_byte, self.end_line, self.end_col
        elif other.end_byte > self.end_byte:
            eb, el, ec = other.end_byte, other.end_line, other.end_col
        else:
            eb = self.end_byte
            el = max(self.end_line, other.end_line)
            ec = max(self.end_col, other.end_col) if self.end_line == other.end_line else (
                self.end_col if self.end_line > other.end_line else other.end_col
            )

        return Span(
            start_byte=sb,
            end_byte=eb,
            start_line=sl,
            start_col=sc,
            end_line=el,
            end_col=ec,
        )

    def slice_bytes(self, source_bytes: bytes) -> bytes:
        """Perform O(1) lossless byte slice from `source_bytes`."""
        sb = max(0, min(self.start_byte, len(source_bytes)))
        eb = max(sb, min(self.end_byte, len(source_bytes)))
        return source_bytes[sb:eb]

    def slice_text(self, source_bytes: bytes, encoding: str = "utf-8") -> str:
        """Perform O(1) lossless UTF-8 text slice from `source_bytes`."""
        return self.slice_bytes(source_bytes).decode(encoding, errors="replace")

    def to_dict(self) -> Dict[str, int]:
        return {
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Span":
        if not isinstance(data, dict):
            raise SchemaValidationError("Span data must be a dict.")
        for req in ("start_byte", "end_byte", "start_line", "end_line"):
            if req not in data:
                raise SchemaValidationError(f"Span missing required field '{req}'.")
        try:
            sb = int(data["start_byte"])
            eb = int(data["end_byte"])
            sl = int(data["start_line"])
            sc = int(data.get("start_col", 0))
            el = int(data["end_line"])
            ec = int(data.get("end_col", 0))
        except (ValueError, TypeError) as exc:
            raise SchemaValidationError(f"Span coordinate fields must be integers: {exc}") from exc
        if sb < 0 or eb < sb or sl < 1 or el < sl or sc < 0 or ec < 0:
            raise SchemaValidationError(f"Invalid Span coordinates: start_byte={sb}, end_byte={eb}, start_line={sl}, end_line={el}.")
        return cls(
            start_byte=sb,
            end_byte=eb,
            start_line=sl,
            start_col=sc,
            end_line=el,
            end_col=ec,
        )


@dataclass(frozen=True)
class ProvenanceStep:
    """Immutable provenance audit entry recording a rule extraction or processor refinement."""

    provider_id: str
    action: str
    rule_or_hook: str
    detail: Optional[str] = None

    def sort_key(self) -> Tuple[str, str, str, str]:
        """Return deterministic lexicographical sort key for commutative ordering."""
        return (self.provider_id, self.action, self.rule_or_hook, self.detail or "")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "provider_id": self.provider_id,
            "action": self.action,
            "rule_or_hook": self.rule_or_hook,
        }
        if self.detail is not None:
            d["detail"] = self.detail
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceStep":
        if not isinstance(data, dict):
            raise SchemaValidationError("ProvenanceStep data must be a dict.")
        for req in ("provider_id", "action", "rule_or_hook"):
            if req not in data:
                raise SchemaValidationError(f"ProvenanceStep missing required field '{req}'.")
        det = data.get("detail")
        return cls(
            provider_id=str(data["provider_id"]),
            action=str(data["action"]),
            rule_or_hook=str(data["rule_or_hook"]),
            detail=str(det) if det is not None else None,
        )


def _freeze_facets_dict(raw_facets: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Normalize a facets mapping into an immutable MappingProxyType."""
    if not raw_facets or not isinstance(raw_facets, Mapping):
        return MappingProxyType({})
    normalized: Dict[str, Any] = {}
    for k, v in raw_facets.items():
        key_str = str(k)
        if isinstance(v, list):
            normalized[key_str] = tuple(
                dict(x) if isinstance(x, Mapping) else x for x in v
            )
        elif isinstance(v, set):
            normalized[key_str] = frozenset(v)
        elif isinstance(v, Mapping) and not isinstance(v, MappingProxyType):
            normalized[key_str] = MappingProxyType(dict(v))
        else:
            normalized[key_str] = v
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class SymbolNode:
    """Single recursive isomorphic AST symbol node with multi-kinds, lossless part spans, and provenance."""

    id: str
    name: str
    scope_path: Tuple[str, ...]
    kinds: FrozenSet[str]
    language: str
    span: Span
    parts: Mapping[str, Span] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    facets: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    children: Tuple["SymbolNode", ...] = field(default=(), hash=False)
    provenance: Tuple[ProvenanceStep, ...] = field(default=(), hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_path", tuple(str(s) for s in (self.scope_path or ())))
        object.__setattr__(
            self,
            "kinds",
            frozenset(str(k) for k in (self.kinds or ()) if str(k)),
        )
        raw_parts = self.parts
        if isinstance(raw_parts, Mapping):
            parts_clean: Dict[str, Span] = {}
            for k, v in raw_parts.items():
                if isinstance(v, Span):
                    parts_clean[str(k)] = v
                elif isinstance(v, dict):
                    parts_clean[str(k)] = Span.from_dict(v)
                else:
                    raise SchemaValidationError(f"SymbolNode.parts['{k}'] must be a Span or dict, got {type(v).__name__}.")
            object.__setattr__(self, "parts", MappingProxyType(parts_clean))
        elif raw_parts is None:
            object.__setattr__(self, "parts", MappingProxyType({}))
        else:
            raise SchemaValidationError(f"SymbolNode.parts must be a Mapping, got {type(raw_parts).__name__}.")

        object.__setattr__(self, "facets", _freeze_facets_dict(self.facets))
        object.__setattr__(self, "children", tuple(self.children) if self.children else ())
        if self.provenance:
            dedup_prov = sorted(set(self.provenance), key=lambda p: p.sort_key())
            object.__setattr__(self, "provenance", tuple(dedup_prov))
        else:
            object.__setattr__(self, "provenance", ())

    @property
    def fqn(self) -> str:
        """Render the fully-qualified name using `facets.get('scope_separator', '.')`."""
        sep = str(self.facets.get("scope_separator", ".")) if isinstance(self.facets, Mapping) else "."
        if self.scope_path:
            return sep.join((*self.scope_path, self.name))
        return self.name

    @staticmethod
    def compute_canonical_id(
        file_path: str,
        fqn: str,
        overload_suffix: str = "",
    ) -> str:
        """Compute canonical space-agnostic and line-agnostic URI `{canonical_path}::{fqn}[({overload})]`."""
        norm_path = str(file_path).replace("\\", "/").strip()
        base_id = f"{norm_path}::{fqn}"
        if overload_suffix:
            suffix_clean = overload_suffix.strip()
            if not suffix_clean.startswith("("):
                suffix_clean = f"({suffix_clean})"
            return f"{base_id}{suffix_clean}"
        return base_id

    def to_dict(self) -> Dict[str, Any]:
        facets_out: Dict[str, Any] = {}
        for k, v in self.facets.items():
            if isinstance(v, (tuple, frozenset, set)):
                facets_out[k] = list(v)
            elif isinstance(v, Mapping):
                facets_out[k] = dict(v)
            else:
                facets_out[k] = v
        return {
            "id": self.id,
            "name": self.name,
            "scope_path": list(self.scope_path),
            "kinds": sorted(self.kinds),
            "language": self.language,
            "span": self.span.to_dict(),
            "parts": {k: v.to_dict() for k, v in self.parts.items()},
            "facets": facets_out,
            "children": [c.to_dict() for c in self.children],
            "provenance": [p.to_dict() for p in self.provenance],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolNode":
        if not isinstance(data, dict):
            raise SchemaValidationError("SymbolNode data must be a dict.")
        for req in ("id", "name", "kinds", "language", "span"):
            if req not in data:
                raise SchemaValidationError(f"SymbolNode missing required field '{req}'.")
        raw_span = data["span"]
        span_obj = raw_span if isinstance(raw_span, Span) else Span.from_dict(raw_span)
        raw_scope = data.get("scope_path") or ()
        scope_tup = tuple(str(s) for s in raw_scope) if isinstance(raw_scope, (list, tuple)) else ()
        raw_kinds = data.get("kinds") or ()
        kinds_set = frozenset(str(k) for k in raw_kinds) if isinstance(raw_kinds, (list, tuple, set, frozenset)) else frozenset()
        raw_parts = data.get("parts") or {}
        parts_map: Dict[str, Span] = {}
        if isinstance(raw_parts, Mapping):
            for pk, pv in raw_parts.items():
                parts_map[str(pk)] = pv if isinstance(pv, Span) else Span.from_dict(pv)
        raw_facets = data.get("facets") or {}
        facets_map = dict(raw_facets) if isinstance(raw_facets, Mapping) else {}
        raw_children = data.get("children") or ()
        children_tup = tuple(
            c if isinstance(c, SymbolNode) else cls.from_dict(c)
            for c in (raw_children if isinstance(raw_children, (list, tuple)) else ())
        )
        raw_prov = data.get("provenance") or ()
        prov_tup = tuple(
            p if isinstance(p, ProvenanceStep) else ProvenanceStep.from_dict(p)
            for p in (raw_prov if isinstance(raw_prov, (list, tuple)) else ())
        )
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            scope_path=scope_tup,
            kinds=kinds_set,
            language=str(data["language"]),
            span=span_obj,
            parts=parts_map,
            facets=facets_map,
            children=children_tup,
            provenance=prov_tup,
        )


@dataclass(frozen=True)
class RelationEdge:
    """Directed semantic relation edge (imports, inherits, implements, calls, references, documents)."""

    source_id: str
    target_expr: str
    edge_kind: str
    span: Span
    resolution_status: str = "unresolved"
    resolved_target_ids: Tuple[str, ...] = ()
    provenance: Tuple[ProvenanceStep, ...] = field(default=(), hash=False)

    def __post_init__(self) -> None:
        valid_statuses = ("unresolved", "resolved", "overload_group", "ambiguous", "external")
        if self.resolution_status not in valid_statuses:
            raise SchemaValidationError(
                f"Invalid RelationEdge resolution_status '{self.resolution_status}'. Expected one of {valid_statuses}."
            )
        object.__setattr__(
            self,
            "resolved_target_ids",
            tuple(str(tid) for tid in (self.resolved_target_ids or ())),
        )
        if self.provenance:
            dedup_prov = sorted(set(self.provenance), key=lambda p: p.sort_key())
            object.__setattr__(self, "provenance", tuple(dedup_prov))
        else:
            object.__setattr__(self, "provenance", ())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_expr": self.target_expr,
            "edge_kind": self.edge_kind,
            "span": self.span.to_dict(),
            "resolution_status": self.resolution_status,
            "resolved_target_ids": list(self.resolved_target_ids),
            "provenance": [p.to_dict() for p in self.provenance],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationEdge":
        if not isinstance(data, dict):
            raise SchemaValidationError("RelationEdge data must be a dict.")
        for req in ("source_id", "target_expr", "edge_kind", "span"):
            if req not in data:
                raise SchemaValidationError(f"RelationEdge missing required field '{req}'.")
        raw_span = data["span"]
        span_obj = raw_span if isinstance(raw_span, Span) else Span.from_dict(raw_span)
        raw_targets = data.get("resolved_target_ids") or ()
        targets_tup = tuple(str(t) for t in raw_targets) if isinstance(raw_targets, (list, tuple)) else ()
        raw_prov = data.get("provenance") or ()
        prov_tup = tuple(
            p if isinstance(p, ProvenanceStep) else ProvenanceStep.from_dict(p)
            for p in (raw_prov if isinstance(raw_prov, (list, tuple)) else ())
        )
        return cls(
            source_id=str(data["source_id"]),
            target_expr=str(data["target_expr"]),
            edge_kind=str(data["edge_kind"]),
            span=span_obj,
            resolution_status=str(data.get("resolution_status") or "unresolved"),
            resolved_target_ids=targets_tup,
            provenance=prov_tup,
        )


@dataclass(frozen=True)
class FileSymbolGraph:
    """Immutable single-file AST symbol subgraph extracted in a single pass."""

    file_path: str
    content_hash: str
    language: str
    root_nodes: Tuple[SymbolNode, ...] = field(default=(), hash=False)
    all_nodes_by_id: Mapping[str, SymbolNode] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    outgoing_edges: Tuple[RelationEdge, ...] = field(default=(), hash=False)

    def __post_init__(self) -> None:
        roots_tup = tuple(self.root_nodes) if self.root_nodes else ()
        object.__setattr__(self, "root_nodes", roots_tup)
        object.__setattr__(self, "outgoing_edges", tuple(self.outgoing_edges) if self.outgoing_edges else ())

        index_map: Dict[str, SymbolNode] = {}
        if isinstance(self.all_nodes_by_id, Mapping) and self.all_nodes_by_id:
            for k, v in self.all_nodes_by_id.items():
                if isinstance(v, SymbolNode):
                    index_map[str(k)] = v

        def _walk_nodes(nodes: Tuple[SymbolNode, ...]) -> None:
            for n in nodes:
                index_map[n.id] = n
                if n.children:
                    _walk_nodes(n.children)

        if roots_tup:
            _walk_nodes(roots_tup)
        object.__setattr__(self, "all_nodes_by_id", MappingProxyType(index_map))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "language": self.language,
            "root_nodes": [n.to_dict() for n in self.root_nodes],
            "all_nodes_by_id": {nid: n.to_dict() for nid, n in self.all_nodes_by_id.items()},
            "outgoing_edges": [e.to_dict() for e in self.outgoing_edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileSymbolGraph":
        if not isinstance(data, dict):
            raise SchemaValidationError("FileSymbolGraph data must be a dict.")
        for req in ("file_path", "content_hash", "language"):
            if req not in data:
                raise SchemaValidationError(f"FileSymbolGraph missing required field '{req}'.")
        raw_roots = data.get("root_nodes") or ()
        roots_tup = tuple(
            n if isinstance(n, SymbolNode) else SymbolNode.from_dict(n)
            for n in (raw_roots if isinstance(raw_roots, (list, tuple)) else ())
        )
        raw_all = data.get("all_nodes_by_id") or {}
        all_map: Dict[str, SymbolNode] = {}
        if isinstance(raw_all, Mapping):
            for k, v in raw_all.items():
                all_map[str(k)] = v if isinstance(v, SymbolNode) else SymbolNode.from_dict(v)
        raw_edges = data.get("outgoing_edges") or ()
        edges_tup = tuple(
            e if isinstance(e, RelationEdge) else RelationEdge.from_dict(e)
            for e in (raw_edges if isinstance(raw_edges, (list, tuple)) else ())
        )
        return cls(
            file_path=str(data["file_path"]),
            content_hash=str(data["content_hash"]),
            language=str(data["language"]),
            root_nodes=roots_tup,
            all_nodes_by_id=all_map,
            outgoing_edges=edges_tup,
        )


@dataclass(frozen=True)
class FileImportBinding:
    """Deterministic single import alias binding resolved in Pass 2."""

    local_alias: str
    target_expr: str
    resolved_file_path: Optional[str] = None
    resolved_symbol_ids: Tuple[str, ...] = ()
    is_wildcard: bool = False
    is_external: bool = False
    is_reexport: bool = False

    def __post_init__(self) -> None:
        if not self.local_alias or not self.target_expr:
            raise SchemaValidationError("FileImportBinding requires non-empty 'local_alias' and 'target_expr'.")
        object.__setattr__(
            self,
            "resolved_symbol_ids",
            tuple(str(sid) for sid in (self.resolved_symbol_ids or ())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "local_alias": self.local_alias,
            "target_expr": self.target_expr,
            "resolved_file_path": self.resolved_file_path,
            "resolved_symbol_ids": list(self.resolved_symbol_ids),
            "is_wildcard": self.is_wildcard,
            "is_external": self.is_external,
            "is_reexport": self.is_reexport,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileImportBinding":
        if not isinstance(data, dict):
            raise SchemaValidationError("FileImportBinding data must be a dict.")
        for req in ("local_alias", "target_expr"):
            if req not in data:
                raise SchemaValidationError(f"FileImportBinding missing required field '{req}'.")
        raw_sids = data.get("resolved_symbol_ids") or ()
        sids_tup = tuple(str(s) for s in raw_sids) if isinstance(raw_sids, (list, tuple)) else ()
        return cls(
            local_alias=str(data["local_alias"]),
            target_expr=str(data["target_expr"]),
            resolved_file_path=str(data["resolved_file_path"]) if data.get("resolved_file_path") is not None else None,
            resolved_symbol_ids=sids_tup,
            is_wildcard=bool(data.get("is_wildcard", False)),
            is_external=bool(data.get("is_external", False)),
            is_reexport=bool(data.get("is_reexport", False)),
        )


@dataclass(frozen=True)
class FileImportTable:
    """Per-file deterministic import binding table built during Pass 2."""

    file_path: str
    bindings: Mapping[str, FileImportBinding] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    exported_symbols: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.file_path:
            raise SchemaValidationError("FileImportTable requires non-empty 'file_path'.")
        norm_bindings: Dict[str, FileImportBinding] = {}
        if isinstance(self.bindings, Mapping):
            for k, v in self.bindings.items():
                norm_bindings[str(k)] = v if isinstance(v, FileImportBinding) else FileImportBinding.from_dict(v)
        object.__setattr__(self, "bindings", MappingProxyType(norm_bindings))
        object.__setattr__(
            self,
            "exported_symbols",
            frozenset(str(s) for s in (self.exported_symbols or ())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "bindings": {k: v.to_dict() for k, v in self.bindings.items()},
            "exported_symbols": sorted(self.exported_symbols),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileImportTable":
        if not isinstance(data, dict):
            raise SchemaValidationError("FileImportTable data must be a dict.")
        if "file_path" not in data:
            raise SchemaValidationError("FileImportTable missing required field 'file_path'.")
        raw_bindings = data.get("bindings") or {}
        b_map: Dict[str, FileImportBinding] = {}
        if isinstance(raw_bindings, Mapping):
            for k, v in raw_bindings.items():
                b_map[str(k)] = v if isinstance(v, FileImportBinding) else FileImportBinding.from_dict(v)
        raw_exports = data.get("exported_symbols") or ()
        exports_set = frozenset(str(s) for s in raw_exports) if isinstance(raw_exports, (list, tuple, set, frozenset)) else frozenset()
        return cls(
            file_path=str(data["file_path"]),
            bindings=b_map,
            exported_symbols=exports_set,
        )


@dataclass(frozen=True)
class WorkspaceSymbolGraph:
    """Immutable cross-file semantic symbol graph assembled by the 4-Pass deterministic linker."""

    file_graphs: Mapping[str, FileSymbolGraph] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    nodes_by_id: Mapping[str, SymbolNode] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    resolved_edges: Tuple[RelationEdge, ...] = field(default=(), hash=False)
    outgoing_edges_by_source: Mapping[str, Tuple[RelationEdge, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    incoming_edges_by_target: Mapping[str, Tuple[RelationEdge, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    file_import_tables: Mapping[str, FileImportTable] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    folded_symbol_groups: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    type_bases_by_id: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    type_derived_by_id: Mapping[str, Tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}), hash=False)
    field_types_by_class_id: Mapping[str, Mapping[str, str]] = field(default_factory=lambda: MappingProxyType({}), hash=False)

    def __post_init__(self) -> None:
        fg_map: Dict[str, FileSymbolGraph] = {}
        if isinstance(self.file_graphs, Mapping):
            for k, v in self.file_graphs.items():
                fg_map[str(k)] = v if isinstance(v, FileSymbolGraph) else FileSymbolGraph.from_dict(v)
        object.__setattr__(self, "file_graphs", MappingProxyType(fg_map))

        nodes_map: Dict[str, SymbolNode] = {}
        if isinstance(self.nodes_by_id, Mapping) and self.nodes_by_id:
            for k, v in self.nodes_by_id.items():
                nodes_map[str(k)] = v if isinstance(v, SymbolNode) else SymbolNode.from_dict(v)
        else:
            for fg in fg_map.values():
                for nid, n in fg.all_nodes_by_id.items():
                    nodes_map[nid] = n
        object.__setattr__(self, "nodes_by_id", MappingProxyType(nodes_map))

        edges_tup = tuple(
            e if isinstance(e, RelationEdge) else RelationEdge.from_dict(e)
            for e in (self.resolved_edges or ())
        )
        object.__setattr__(self, "resolved_edges", edges_tup)

        out_map: Dict[str, List[RelationEdge]] = {}
        in_map: Dict[str, List[RelationEdge]] = {}
        for edge in edges_tup:
            out_map.setdefault(edge.source_id, []).append(edge)
            for tid in edge.resolved_target_ids:
                in_map.setdefault(tid, []).append(edge)

        if isinstance(self.outgoing_edges_by_source, Mapping) and self.outgoing_edges_by_source and not edges_tup:
            for k, v in self.outgoing_edges_by_source.items():
                out_map[str(k)] = [e if isinstance(e, RelationEdge) else RelationEdge.from_dict(e) for e in (v or ())]
        if isinstance(self.incoming_edges_by_target, Mapping) and self.incoming_edges_by_target and not edges_tup:
            for k, v in self.incoming_edges_by_target.items():
                in_map[str(k)] = [e if isinstance(e, RelationEdge) else RelationEdge.from_dict(e) for e in (v or ())]

        object.__setattr__(
            self,
            "outgoing_edges_by_source",
            MappingProxyType({k: tuple(v) for k, v in out_map.items()}),
        )
        object.__setattr__(
            self,
            "incoming_edges_by_target",
            MappingProxyType({k: tuple(v) for k, v in in_map.items()}),
        )

        imp_map: Dict[str, FileImportTable] = {}
        if isinstance(self.file_import_tables, Mapping):
            for k, v in self.file_import_tables.items():
                imp_map[str(k)] = v if isinstance(v, FileImportTable) else FileImportTable.from_dict(v)
        object.__setattr__(self, "file_import_tables", MappingProxyType(imp_map))

        fold_map: Dict[str, Tuple[str, ...]] = {}
        if isinstance(self.folded_symbol_groups, Mapping):
            for k, v in self.folded_symbol_groups.items():
                fold_map[str(k)] = tuple(str(x) for x in (v or ()))
        object.__setattr__(self, "folded_symbol_groups", MappingProxyType(fold_map))

        bases_map: Dict[str, Tuple[str, ...]] = {}
        if isinstance(self.type_bases_by_id, Mapping):
            for k, v in self.type_bases_by_id.items():
                bases_map[str(k)] = tuple(str(x) for x in (v or ()))
        object.__setattr__(self, "type_bases_by_id", MappingProxyType(bases_map))

        derived_map: Dict[str, Tuple[str, ...]] = {}
        if isinstance(self.type_derived_by_id, Mapping):
            for k, v in self.type_derived_by_id.items():
                derived_map[str(k)] = tuple(str(x) for x in (v or ()))
        object.__setattr__(self, "type_derived_by_id", MappingProxyType(derived_map))

        ft_map: Dict[str, Mapping[str, str]] = {}
        if isinstance(self.field_types_by_class_id, Mapping):
            for k, v in self.field_types_by_class_id.items():
                if isinstance(v, Mapping):
                    ft_map[str(k)] = MappingProxyType({str(fn): str(ft) for fn, ft in v.items()})
        object.__setattr__(self, "field_types_by_class_id", MappingProxyType(ft_map))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_graphs": {k: v.to_dict() for k, v in self.file_graphs.items()},
            "nodes_by_id": {k: v.to_dict() for k, v in self.nodes_by_id.items()},
            "resolved_edges": [e.to_dict() for e in self.resolved_edges],
            "file_import_tables": {k: v.to_dict() for k, v in self.file_import_tables.items()},
            "folded_symbol_groups": {k: list(v) for k, v in self.folded_symbol_groups.items()},
            "type_bases_by_id": {k: list(v) for k, v in self.type_bases_by_id.items()},
            "type_derived_by_id": {k: list(v) for k, v in self.type_derived_by_id.items()},
            "field_types_by_class_id": {k: dict(v) for k, v in self.field_types_by_class_id.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceSymbolGraph":
        if not isinstance(data, dict):
            raise SchemaValidationError("WorkspaceSymbolGraph data must be a dict.")
        return cls(
            file_graphs=data.get("file_graphs") or {},
            nodes_by_id=data.get("nodes_by_id") or {},
            resolved_edges=tuple(data.get("resolved_edges") or ()),
            file_import_tables=data.get("file_import_tables") or {},
            folded_symbol_groups=data.get("folded_symbol_groups") or {},
            type_bases_by_id=data.get("type_bases_by_id") or {},
            type_derived_by_id=data.get("type_derived_by_id") or {},
            field_types_by_class_id=data.get("field_types_by_class_id") or {},
        )


class SymbolKind(str, Enum):
    # Code symbols
    CLASS = "class"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE_ALIAS = "type_alias"
    MACRO = "macro"
    VARIABLE = "variable"
    CONSTANT = "constant"

    # Document symbols
    DOC_HEADING_1 = "doc_heading_1"
    DOC_HEADING_2 = "doc_heading_2"
    DOC_HEADING_3 = "doc_heading_3"
    DOC_HEADING_4 = "doc_heading_4"
    DOC_TABLE = "doc_table"
    DOC_SECTION = "doc_section"


class LanguageType(str, Enum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    SPICE = "spice"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MemberInfo:
    name: str
    kind: str
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    line_number: int = 0
    is_static: bool = False
    fqn: str = ""
    parent_id: str = ""
    return_type: str = ""
    parameters: Tuple[Dict[str, str], ...] = field(default=(), hash=False)

    @property
    def line(self) -> int:
        return self.line_number

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "docstring": self.docstring,
            "visibility": self.visibility,
            "line_number": self.line_number,
            "is_static": self.is_static,
        }
        if self.fqn:
            d["fqn"] = self.fqn
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.return_type:
            d["return_type"] = self.return_type
        if self.parameters:
            d["parameters"] = [dict(p) for p in self.parameters]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemberInfo":
        if not isinstance(data, dict):
            raise SchemaValidationError("MemberInfo data must be a dict.")
        if "name" not in data or "kind" not in data:
            raise SchemaValidationError("MemberInfo requires 'name' and 'kind'.")
        params_raw = data.get("parameters") or []
        params = tuple(dict(p) for p in params_raw if isinstance(p, dict)) if isinstance(params_raw, (list, tuple)) else ()
        raw_ln = data.get("line_number")
        if raw_ln is None:
            raw_ln = data.get("line")
        return cls(
            name=str(data["name"]),
            kind=str(data["kind"]),
            signature=str(data.get("signature") or ""),
            docstring=str(data.get("docstring") or ""),
            visibility=str(data.get("visibility") or "public"),
            line_number=int(raw_ln or 0),
            is_static=bool(data.get("is_static", False)),
            fqn=str(data.get("fqn") or ""),
            parent_id=str(data.get("parent_id") or ""),
            return_type=str(data.get("return_type") or ""),
            parameters=params,
        )


@dataclass(frozen=True)
class LanguageConfig:
    """Language declaration model for contributes.ast.languages."""

    id: str
    name: str
    extensions: Tuple[str, ...]
    mode: str = "tree_sitter"  # "tree_sitter" | "custom"
    grammar: Optional[str] = None
    query_file: Optional[str] = None
    query_files: Tuple[str, ...] = ()
    spaces: Tuple[str, ...] = ()
    processors: Tuple[str, ...] = ()
    receiver_aliases: Mapping[str, Tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({}), hash=False
    )
    symbol_folding: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), hash=False
    )
    module_resolver: Optional[str] = None
    edge_refiners: Tuple[str, ...] = ()
    parser_entry: Optional[str] = None
    custom_kinds: Tuple[Dict[str, str], ...] = field(default=(), hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extensions", tuple(str(e) for e in (self.extensions or ())))
        q_files: List[str] = []
        if self.query_file:
            q_files.append(str(self.query_file))
        for qf in (self.query_files or ()):
            qf_str = str(qf)
            if qf_str and qf_str not in q_files:
                q_files.append(qf_str)
        object.__setattr__(self, "query_files", tuple(q_files))
        object.__setattr__(self, "spaces", tuple(str(s) for s in (self.spaces or ()) if str(s).strip()))
        object.__setattr__(self, "processors", tuple(str(p) for p in (self.processors or ()) if str(p).strip()))
        norm_aliases: Dict[str, Tuple[str, ...]] = {}
        if isinstance(self.receiver_aliases, Mapping):
            for k, v in self.receiver_aliases.items():
                if isinstance(v, (list, tuple, set, frozenset)):
                    norm_aliases[str(k)] = tuple(str(a).strip() for a in v if str(a).strip())
        object.__setattr__(self, "receiver_aliases", MappingProxyType(norm_aliases))
        object.__setattr__(self, "symbol_folding", _freeze_facets_dict(self.symbol_folding))
        object.__setattr__(
            self,
            "module_resolver",
            str(self.module_resolver).strip() if self.module_resolver and str(self.module_resolver).strip() else None,
        )
        object.__setattr__(
            self,
            "edge_refiners",
            tuple(str(r).strip() for r in (self.edge_refiners or ()) if str(r).strip()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "extensions": list(self.extensions),
            "mode": self.mode,
            "grammar": self.grammar,
            "query_file": self.query_file,
            "query_files": list(self.query_files),
            "spaces": list(self.spaces),
            "processors": list(self.processors),
            "receiver_aliases": {k: list(v) for k, v in self.receiver_aliases.items()},
            "symbol_folding": {
                k: list(v) if isinstance(v, tuple) else v
                for k, v in self.symbol_folding.items()
            },
            "module_resolver": self.module_resolver,
            "edge_refiners": list(self.edge_refiners),
            "parser_entry": self.parser_entry,
            "custom_kinds": [dict(k) for k in self.custom_kinds],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LanguageConfig":
        if not isinstance(data, dict):
            raise SchemaValidationError("LanguageConfig data must be a dict.")
        if "id" not in data or "extensions" not in data:
            raise SchemaValidationError("LanguageConfig requires 'id' and 'extensions'.")
        raw_exts = data.get("extensions") or []
        raw_kinds = data.get("custom_kinds") or []
        raw_qfiles = data.get("query_files") or []
        raw_spaces = data.get("spaces") or []
        raw_procs = data.get("processors") or []
        raw_aliases = data.get("receiver_aliases")
        raw_folding = data.get("symbol_folding")
        raw_refiners = data.get("edge_refiners") or []
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            extensions=tuple(str(e) for e in raw_exts) if isinstance(raw_exts, (list, tuple, set)) else (),
            mode=str(data.get("mode") or "tree_sitter"),
            grammar=data.get("grammar"),
            query_file=data.get("query_file"),
            query_files=tuple(str(q) for q in raw_qfiles) if isinstance(raw_qfiles, (list, tuple, set)) else (),
            spaces=tuple(str(s) for s in raw_spaces) if isinstance(raw_spaces, (list, tuple, set)) else (),
            processors=tuple(str(p) for p in raw_procs) if isinstance(raw_procs, (list, tuple, set)) else (),
            receiver_aliases=raw_aliases if isinstance(raw_aliases, Mapping) else {},
            symbol_folding=raw_folding if isinstance(raw_folding, Mapping) else {},
            module_resolver=data.get("module_resolver"),
            edge_refiners=tuple(str(r) for r in raw_refiners) if isinstance(raw_refiners, (list, tuple, set)) else (),
            parser_entry=data.get("parser_entry"),
            custom_kinds=tuple(dict(k) for k in raw_kinds if isinstance(k, dict)) if isinstance(raw_kinds, (list, tuple)) else (),
        )


@dataclass(frozen=True)
class UnifiedSymbol:
    """Hierarchical code and document symbol model."""

    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    language: str
    docstring: str = ""
    signature: str = ""
    end_line: int = 0
    fqn: str = ""
    scope_path: str = ""
    parent_id: Optional[str] = None
    children: Tuple[Any, ...] = field(default=(), hash=False)
    parameters: Tuple[Dict[str, Any], ...] = field(default=(), hash=False)
    return_type: str = ""
    search_payload: str = ""
    visibility: str = "public"
    members: Tuple[Any, ...] = field(default=(), hash=False)
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        children_tup = tuple(self.children) if self.children else ()
        members_tup = tuple(self.members) if self.members else ()
        if not children_tup and members_tup:
            children_tup = members_tup
        elif not members_tup and children_tup:
            members_tup = children_tup
        object.__setattr__(self, "children", children_tup)
        object.__setattr__(self, "members", members_tup)
        object.__setattr__(self, "parameters", tuple(self.parameters) if self.parameters else ())

    @property
    def spaces(self) -> List[str]:
        """Return the list of workspace names associated with this symbol."""
        sp = self.metadata.get("spaces", [])
        if isinstance(sp, list):
            return sp
        if isinstance(sp, str) and sp:
            return [sp]
        return []

    @classmethod
    def compute_id(
        cls,
        space: str,
        file_path: str,
        name: str,
        kind: str,
        line_number: int,
        signature_hint: str = "",
    ) -> str:
        """Compute deterministic SHA1 identifier for a symbol."""
        normalized_path = file_path.replace("\\", "/")
        raw = f"{space}:{normalized_path}:{name}:{kind}:{line_number}"
        if signature_hint:
            raw = f"{raw}:{signature_hint}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        meta = dict(self.metadata)
        if "_own_members" in meta and isinstance(meta["_own_members"], (list, tuple)):
            meta["_own_members"] = [
                m.to_dict() if hasattr(m, "to_dict") else m
                for m in meta["_own_members"]
            ]
        if "space" in meta:
            single_sp = meta.pop("space")
            if "spaces" not in meta and single_sp:
                meta["spaces"] = [single_sp]
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "language": self.language,
            "docstring": self.docstring,
            "signature": self.signature,
            "fqn": self.fqn,
            "scope_path": self.scope_path,
            "parent_id": self.parent_id,
            "children": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.children],
            "parameters": [dict(p) for p in self.parameters],
            "return_type": self.return_type,
            "search_payload": self.search_payload,
            "visibility": self.visibility,
            "metadata": meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol":
        if not isinstance(data, dict):
            raise SchemaValidationError("UnifiedSymbol data must be a dict.")
        required = ["id", "name", "kind", "file_path", "line_number", "language"]
        for key in required:
            if key not in data:
                raise SchemaValidationError(f"UnifiedSymbol missing required field '{key}'.")

        def _coerce_member_list(raw_list: Any) -> List[MemberInfo]:
            out: List[MemberInfo] = []
            if not isinstance(raw_list, (list, tuple)):
                return out
            for m in raw_list:
                if isinstance(m, MemberInfo):
                    out.append(m)
                elif isinstance(m, cls):
                    out.append(
                        MemberInfo(
                            name=m.name,
                            kind=m.kind,
                            signature=m.signature,
                            docstring=m.docstring,
                            visibility=m.visibility,
                            line_number=m.line_number,
                            is_static=bool((m.metadata or {}).get("is_static", False)),
                            fqn=m.fqn,
                            parent_id=m.parent_id or "",
                            return_type=m.return_type,
                            parameters=m.parameters,
                        )
                    )
                elif isinstance(m, dict):
                    if "name" in m and "kind" in m:
                        meta_d = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                        p_raw = m.get("parameters") or []
                        p_tup = tuple(dict(p) for p in p_raw if isinstance(p, dict)) if isinstance(p_raw, (list, tuple)) else ()
                        m_ln = m.get("line_number")
                        if m_ln is None:
                            m_ln = m.get("line")
                        out.append(
                            MemberInfo(
                                name=str(m["name"]),
                                kind=str(m["kind"]),
                                signature=str(m.get("signature") or ""),
                                docstring=str(m.get("docstring") or ""),
                                visibility=str(m.get("visibility") or "public"),
                                line_number=int(m_ln or 0),
                                is_static=bool(m.get("is_static", meta_d.get("is_static", False))),
                                fqn=str(m.get("fqn") or ""),
                                parent_id=str(m.get("parent_id") or ""),
                                return_type=str(m.get("return_type") or ""),
                                parameters=p_tup,
                            )
                        )
            return out

        children_raw = data.get("children") or []
        members_raw = data.get("members")
        children_list = _coerce_member_list(children_raw)
        children_tuple: Tuple[MemberInfo, ...] = tuple(children_list)
        if members_raw is None or members_raw == children_raw:
            members_tuple: Tuple[MemberInfo, ...] = children_tuple
        else:
            members_list = _coerce_member_list(members_raw)
            members_tuple = children_tuple if members_list == children_list else tuple(members_list)

        params_raw = data.get("parameters") or []
        parameters = tuple(dict(p) for p in params_raw if isinstance(p, dict)) if isinstance(params_raw, (list, tuple)) else ()
        raw_metadata = data.get("metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        if "_own_members" in metadata and isinstance(metadata["_own_members"], (list, tuple)):
            metadata["_own_members"] = [
                MemberInfo.from_dict(m) if isinstance(m, dict) else m
                for m in metadata["_own_members"]
            ]
        if "space" in metadata:
            single_sp = metadata.pop("space")
            if "spaces" not in metadata and single_sp:
                metadata["spaces"] = [single_sp]

        line_num = int(data["line_number"] or 0)
        raw_end = data.get("end_line")
        end_ln = int(raw_end if raw_end is not None else line_num)

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            kind=str(data["kind"]),
            file_path=str(data["file_path"]),
            line_number=line_num,
            end_line=end_ln,
            language=str(data["language"]),
            docstring=str(data.get("docstring") or ""),
            signature=str(data.get("signature") or ""),
            fqn=str(data.get("fqn") or ""),
            scope_path=str(data.get("scope_path") or ""),
            parent_id=data.get("parent_id"),
            children=children_tuple,
            parameters=parameters,
            return_type=str(data.get("return_type") or ""),
            search_payload=str(data.get("search_payload") or ""),
            visibility=str(data.get("visibility") or "public"),
            members=members_tuple,
            metadata=metadata,
        )


@dataclass(frozen=True)
class SymbolCallSite:
    """Immutable value object representing a call expression site."""

    callee_name: str
    line_number: int
    caller_symbol_id: str = ""
    caller_member_name: str = ""
    context_prefix: str = ""
    file_path: str = ""
    space: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "callee_name": self.callee_name,
            "line_number": self.line_number,
            "caller_symbol_id": self.caller_symbol_id,
            "caller_member_name": self.caller_member_name,
            "context_prefix": self.context_prefix,
            "file_path": self.file_path,
            "space": self.space,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolCallSite":
        if not isinstance(data, dict):
            raise SchemaValidationError("SymbolCallSite data must be a dict.")
        return cls(
            callee_name=str(data.get("callee_name") or ""),
            line_number=int(data.get("line_number") or 0),
            caller_symbol_id=str(data.get("caller_symbol_id") or ""),
            caller_member_name=str(data.get("caller_member_name") or ""),
            context_prefix=str(data.get("context_prefix") or ""),
            file_path=str(data.get("file_path") or ""),
            space=str(data.get("space") or ""),
        )


@dataclass(frozen=True)
class SemanticBundle:
    """Self-contained semantic symbol bundle for a workspace or union of workspaces."""

    version: str
    space_name: str
    created_at: str
    symbols: List[UnifiedSymbol] = field(default_factory=list, hash=False)
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "space_name": self.space_name,
            "created_at": self.created_at,
            "symbol_count": len(self.symbols),
            "symbols": [s.to_dict() for s in self.symbols],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticBundle":
        if not isinstance(data, dict):
            raise SchemaValidationError("SemanticBundle data must be a dictionary.")

        version = str(data.get("version") or "1.0.0")
        space_name = str(data.get("space_name") or "unknown")
        created_at = str(data.get("created_at") or datetime.now(timezone.utc).isoformat())

        symbols_raw = data.get("symbols") or []
        symbols = [
            UnifiedSymbol.from_dict(s) if isinstance(s, dict) else s
            for s in (symbols_raw if isinstance(symbols_raw, (list, tuple)) else [])
        ]
        raw_meta = data.get("metadata")
        metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        return cls(
            version=version,
            space_name=space_name,
            created_at=created_at,
            symbols=symbols,
            metadata=metadata,
        )


class ASTSnapshot:
    """Single-Parse Symbol Sharing snapshot persisted at `ast.storage://indices/unified.symbols.bin.gz`."""

    def __init__(
        self,
        ast_generation: int = 0,
        space_generations: Optional[Dict[str, int]] = None,
        symbols: Any = None,
        file_to_symbol_ids: Optional[Dict[str, List[str]]] = None,
        files_map: Optional[Dict[str, List[str]]] = None,
        created_at: float = 0.0,
    ) -> None:
        self.ast_generation: int = ast_generation
        self.space_generations: Dict[str, int] = dict(space_generations) if space_generations is not None else {}
        self.symbols: Any = symbols if symbols is not None else {}
        self.file_to_symbol_ids: Dict[str, List[str]] = (
            dict(file_to_symbol_ids) if file_to_symbol_ids is not None else {}
        )
        self.files_map: Dict[str, List[str]] = dict(files_map) if files_map is not None else {}
        self.created_at: float = created_at
        self.__post_init__()

    def __post_init__(self) -> None:
        if isinstance(self.symbols, (list, tuple, set)):
            self.symbols = {s.id: s for s in self.symbols}
        if not self.file_to_symbol_ids and isinstance(self.symbols, dict) and self.symbols:
            mapping: Dict[str, List[str]] = {}
            for sid, sym in self.symbols.items():
                lst = mapping.setdefault(sym.file_path, [])
                if sid not in lst:
                    lst.append(sid)
                for pf in (sym.metadata or {}).get("partial_files") or []:
                    pf_lst = mapping.setdefault(str(pf), [])
                    if sid not in pf_lst:
                        pf_lst.append(sid)
            self.file_to_symbol_ids = mapping

    def list_symbols(self) -> List[UnifiedSymbol]:
        """Return all symbols in the snapshot as a list."""
        if isinstance(self.symbols, dict):
            return list(self.symbols.values())
        return list(self.symbols)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ast_generation": self.ast_generation,
            "space_generations": dict(self.space_generations),
            "symbols": {
                sid: (sym.to_dict() if hasattr(sym, "to_dict") else sym)
                for sid, sym in self.symbols.items()
            },
            "file_to_symbol_ids": {k: list(v) for k, v in self.file_to_symbol_ids.items()},
            "files_map": {k: list(v) for k, v in self.files_map.items()},
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ASTSnapshot":
        if not isinstance(data, dict):
            raise SchemaValidationError("ASTSnapshot data must be a dictionary.")
        raw_syms = data.get("symbols") or {}
        symbols: Dict[str, UnifiedSymbol] = {}
        if isinstance(raw_syms, dict):
            for sid, s_val in raw_syms.items():
                if isinstance(s_val, UnifiedSymbol):
                    symbols[str(sid)] = s_val
                elif isinstance(s_val, dict):
                    symbols[str(sid)] = UnifiedSymbol.from_dict(s_val)
        elif isinstance(raw_syms, (list, tuple, set)):
            for item in raw_syms:
                if isinstance(item, UnifiedSymbol):
                    if item.id:
                        symbols[str(item.id)] = item
                elif isinstance(item, dict):
                    sym_obj = UnifiedSymbol.from_dict(item)
                    if sym_obj.id:
                        symbols[str(sym_obj.id)] = sym_obj
        raw_space_gens = data.get("space_generations")
        space_gens_dict = raw_space_gens if isinstance(raw_space_gens, dict) else {}
        raw_f2s = data.get("file_to_symbol_ids")
        f2s_dict = raw_f2s if isinstance(raw_f2s, dict) else {}
        raw_fmap = data.get("files_map")
        fmap_dict = raw_fmap if isinstance(raw_fmap, dict) else {}
        return cls(
            ast_generation=int(data.get("ast_generation") or 0),
            space_generations={str(k): int(v) for k, v in space_gens_dict.items() if v is not None},
            symbols=symbols,
            file_to_symbol_ids={
                str(k): [str(x) for x in v]
                for k, v in f2s_dict.items()
                if isinstance(v, (list, tuple))
            },
            files_map={
                str(k): [str(x) for x in v]
                for k, v in fmap_dict.items()
                if isinstance(v, (list, tuple))
            },
            created_at=float(data.get("created_at") or 0.0),
        )


@dataclass(frozen=True)
class OutlineNode:
    """Hierarchical symbol outline node for a single file."""

    name: str
    kind: str
    line_number: int
    end_line: int = 0
    signature: str = ""
    visibility: str = "public"
    docstring: str = ""
    fqn: str = ""
    is_partial: bool = False
    is_static: bool = False
    children: List[Any] = field(default_factory=list, hash=False)
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)

    def to_dict(self) -> Dict[str, Any]:
        children_serialized = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.children]
        return {
            "name": self.name,
            "kind": self.kind,
            "line_number": self.line_number,
            "end_line": self.end_line or self.line_number,
            "signature": self.signature,
            "visibility": self.visibility,
            "docstring": self.docstring,
            "fqn": self.fqn,
            "is_partial": self.is_partial,
            "is_static": self.is_static,
            "members": children_serialized,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutlineNode":
        if not isinstance(data, dict):
            raise SchemaValidationError("OutlineNode data must be a dictionary.")
        raw_children = data.get("members") or data.get("children") or []
        children = [
            cls.from_dict(c) if isinstance(c, dict) and "line_number" in c else c
            for c in (raw_children if isinstance(raw_children, (list, tuple)) else [])
        ]
        raw_meta = data.get("metadata")
        metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        line_num = int(data.get("line_number") or 0)
        raw_end = data.get("end_line")
        end_ln = int(raw_end if raw_end is not None else line_num)
        return cls(
            name=str(data.get("name") or ""),
            kind=str(data.get("kind") or ""),
            line_number=line_num,
            end_line=end_ln,
            signature=str(data.get("signature") or ""),
            visibility=str(data.get("visibility") or "public"),
            docstring=str(data.get("docstring") or ""),
            fqn=str(data.get("fqn") or ""),
            is_partial=bool(data.get("is_partial", False)),
            is_static=bool(data.get("is_static", False)),
            children=children,
            metadata=metadata,
        )


@dataclass(frozen=True)
class OutlineResult:
    """Structured result for `yscb ast outline <file>`."""

    file_path: str
    language: str = "unknown"
    merged: bool = False
    symbols: List[Dict[str, Any]] = field(default_factory=list, hash=False)
    partial_siblings: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict, hash=False)
    warnings: List[str] = field(default_factory=list, hash=False)
    filters: Dict[str, Any] = field(default_factory=dict, hash=False)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "file_path": self.file_path,
            "language": self.language,
            "merged": self.merged,
            "symbols": [
                s.to_dict() if hasattr(s, "to_dict") else dict(s)
                for s in self.symbols
            ],
            "partial_siblings": {
                str(fqn): [
                    sib.to_dict() if hasattr(sib, "to_dict") else dict(sib)
                    for sib in sib_list
                ]
                for fqn, sib_list in self.partial_siblings.items()
            },
            "warnings": list(self.warnings),
        }
        if self.filters:
            out["filters"] = dict(self.filters)
        if self.error is not None:
            out["error"] = self.error
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutlineResult":
        if not isinstance(data, dict):
            raise SchemaValidationError("OutlineResult data must be a dictionary.")
        raw_symbols = data.get("symbols") or []
        raw_siblings = data.get("partial_siblings")
        siblings_dict = raw_siblings if isinstance(raw_siblings, dict) else {}
        raw_warnings = data.get("warnings") or []
        raw_filters = data.get("filters")
        filters = dict(raw_filters) if isinstance(raw_filters, dict) else {}
        err_val = data.get("error")
        return cls(
            file_path=str(data.get("file_path") or ""),
            language=str(data.get("language") or "unknown"),
            merged=bool(data.get("merged", False)),
            symbols=[
                dict(s) if isinstance(s, dict) else s
                for s in (raw_symbols if isinstance(raw_symbols, (list, tuple)) else [])
            ],
            partial_siblings={
                str(k): [dict(x) if isinstance(x, dict) else x for x in v]
                for k, v in siblings_dict.items()
                if isinstance(v, (list, tuple))
            },
            warnings=[str(w) for w in (raw_warnings if isinstance(raw_warnings, (list, tuple)) else [])],
            filters=filters,
            error=str(err_val) if err_val is not None else None,
        )


__all__ = (
    "Span",
    "ProvenanceStep",
    "SymbolNode",
    "RelationEdge",
    "FileSymbolGraph",
    "FileImportBinding",
    "FileImportTable",
    "WorkspaceSymbolGraph",
    "SymbolKind",
    "LanguageType",
    "MemberInfo",
    "LanguageConfig",
    "UnifiedSymbol",
    "SymbolCallSite",
    "SemanticBundle",
    "ASTSnapshot",
    "OutlineNode",
    "OutlineResult",
)
