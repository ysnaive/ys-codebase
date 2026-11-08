"""
Core data structures, enums, and schema models for module:ast (ast_engine).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import SchemaValidationError


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
    parameters: Tuple[Dict[str, str], ...] = ()

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
    parser_entry: Optional[str] = None
    custom_kinds: Tuple[Dict[str, str], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "extensions": list(self.extensions),
            "mode": self.mode,
            "grammar": self.grammar,
            "query_file": self.query_file,
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
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            extensions=tuple(str(e) for e in raw_exts) if isinstance(raw_exts, (list, tuple, set)) else (),
            mode=str(data.get("mode") or "tree_sitter"),
            grammar=data.get("grammar"),
            query_file=data.get("query_file"),
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
    children: Tuple[Any, ...] = ()
    parameters: Tuple[Dict[str, Any], ...] = ()
    return_type: str = ""
    search_payload: str = ""
    visibility: str = "public"
    members: Tuple[Any, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.children and self.members:
            object.__setattr__(self, "children", tuple(self.members))
        elif not self.members and self.children:
            object.__setattr__(self, "members", tuple(self.children))

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
    symbols: List[UnifiedSymbol] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

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
    children: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

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
    symbols: List[Dict[str, Any]] = field(default_factory=list)
    partial_siblings: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
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


__all__ = [
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
]
