"""
Deterministic Symbol Resolver (`DeterministicSymbolResolver`), Structured `SymbolSelector`,
and Call Topology Query Engine (`query_callers`, `query_callees`, `query_impact`).
- Zero BM25 dependency: 3-tier deterministic lookup (`SymbolSelector`, exact FQN / suffix / short name, case-insensitive).
- Supports parameter signature filtering in `SymbolSelector` (e.g. `Window.Open(string, int)` or `Window.Open()`).
- Same-Parent Overload Grouping: when a query without parameter types matches multiple methods on the SAME
  parent type `(tuple(sorted(sym.spaces)), parent_fqn_or_scope, short_name)`, returns `status="overload_group"`
  with `targets=[all overloads]` and unions callers/callees/impact across the overload group.
- Cross-Parent Ambiguity Guard: when a query matches symbols across DIFFERENT parent types
  (e.g. `UI.Window.Open` vs `IO.File.Open`), returns `status="ambiguous"` with `candidates=[...]`.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple, Union

from core.context import (
    cell_span,
    get_or_compute_epoch_state,
    get_virtual_cwd,
)

from .exceptions import ASTError
from .graph import CallGraphIndex
from .linker import _compute_symbols_map_fingerprint, expand_contract_symbol_ids
from .schema import (
    RelationEdge,
    SymbolCallSite,
    SymbolKind,
    SymbolNode,
    UnifiedSymbol,
    WorkspaceSymbolGraph,
)

KIND_PREFIX_MAP: Mapping[str, FrozenSet[str]] = MappingProxyType({
    "class": frozenset({SymbolKind.CLASS.value}),
    "cls": frozenset({SymbolKind.CLASS.value}),
    "struct": frozenset({SymbolKind.STRUCT.value}),
    "interface": frozenset({SymbolKind.INTERFACE.value}),
    "iface": frozenset({SymbolKind.INTERFACE.value}),
    "enum": frozenset({SymbolKind.ENUM.value}),
    "fn": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "func": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "def": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "function": frozenset({SymbolKind.FUNCTION.value, SymbolKind.METHOD.value}),
    "method": frozenset({SymbolKind.METHOD.value}),
    "meth": frozenset({SymbolKind.METHOD.value}),
    "type": frozenset({SymbolKind.TYPE_ALIAS.value}),
    "typedef": frozenset({SymbolKind.TYPE_ALIAS.value}),
    "const": frozenset({SymbolKind.CONSTANT.value}),
    "constant": frozenset({SymbolKind.CONSTANT.value}),
    "var": frozenset({SymbolKind.VARIABLE.value}),
    "variable": frozenset({SymbolKind.VARIABLE.value}),
    "let": frozenset({SymbolKind.VARIABLE.value}),
    "macro": frozenset({SymbolKind.MACRO.value}),
    "doc": frozenset({
        SymbolKind.DOC_HEADING_1.value,
        SymbolKind.DOC_HEADING_2.value,
        SymbolKind.DOC_HEADING_3.value,
        SymbolKind.DOC_HEADING_4.value,
        SymbolKind.DOC_SECTION.value,
    }),
    "h1": frozenset({SymbolKind.DOC_HEADING_1.value}),
    "h2": frozenset({SymbolKind.DOC_HEADING_2.value}),
    "h3": frozenset({SymbolKind.DOC_HEADING_3.value}),
    "h4": frozenset({SymbolKind.DOC_HEADING_4.value}),
})

CALLABLE_KINDS: FrozenSet[str] = frozenset({
    SymbolKind.FUNCTION.value,
    SymbolKind.METHOD.value,
    "function",
    "method",
    "constructor",
})


def _split_top_level_comma(text: str, track_angles: bool = True) -> List[str]:
    """Split `text` by top-level commas while ignoring commas inside quotes, `<...>`, `(...)`, `[...]`, or `{...}`."""
    if not text:
        return []
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    in_quote: Optional[str] = None
    escaped = False
    open_chars = "<([{" if track_angles else "([{"
    close_chars = ">)]}" if track_angles else ")]}"
    for ch in text:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if in_quote:
            if ch == in_quote:
                in_quote = None
            current.append(ch)
            continue
        if ch in ("'", '"', "`"):
            in_quote = ch
            current.append(ch)
        elif ch in open_chars:
            depth += 1
            current.append(ch)
        elif ch in close_chars:
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            tok = "".join(current).strip()
            if tok:
                parts.append(tok)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _strip_angle_brackets(text: str) -> str:
    """Remove balanced `<...>` generic/template argument blocks from a symbol path."""
    if "<" not in text:
        return text
    out: List[str] = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth > 0:
                depth -= 1
            else:
                out.append(ch)
        elif depth == 0:
            out.append(ch)
    return "".join(out).strip()


def extract_signature_params(signature: str) -> List[str]:
    """Extract parameter declarations inside `(...)` of a symbol signature."""
    if not signature or "(" not in signature or ")" not in signature:
        return []
    start = signature.find("(")
    depth = 0
    end = -1
    in_quote: Optional[str] = None
    escaped = False
    for idx in range(start, len(signature)):
        ch = signature[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"', "`"):
            in_quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = idx
                break
    if end <= start:
        return []
    inner = signature[start + 1 : end].strip()
    if not inner:
        return []

    params = _split_top_level_comma(inner)
    if params:
        head_part = params[0].split(":", 1)[0].strip()
        first_tok = head_part.split()[0] if head_part else ""
        if first_tok in ("self", "cls", "this"):
            params = params[1:]
    params = [p for p in params if p not in ("/", "*")]
    return params


@dataclass(frozen=True)
class ParsedSelector:
    """
    Structured symbol selector supporting `[kind] [scope.]name[(param_types...)]`.
    """

    raw_query: str
    identifier: str
    scope: Optional[str] = None
    target_kinds: Optional[Set[str]] = None
    is_callable: bool = False
    param_types: Optional[Tuple[str, ...]] = None

    def matches_params(self, sym: UnifiedSymbol) -> bool:
        """
        Check if `sym.signature` matches explicit `param_types`:
        - If `param_types` is `None`: no parameter list was specified (or empty `()` callable marker).
        - If `param_types` has tokens (e.g. `("string", "int")`): parameter count and per-slot type/token must match.
        """
        if not self.param_types:
            return True

        sig_params = extract_signature_params(sym.signature or "")
        if len(sig_params) != len(self.param_types):
            return False

        for q_tok, s_param in zip(self.param_types, sig_params):
            q_low = q_tok.lower().strip()
            s_low = s_param.lower().split("=", 1)[0].strip()
            if q_low not in s_low:
                return False
        return True

    def matches(self, sym: UnifiedSymbol, case_sensitive: bool = False) -> bool:
        """Verify whether `sym` satisfies kind, callable, identifier, scope, and parameter constraints."""
        sym_kind = sym.kind.value if isinstance(sym.kind, SymbolKind) else str(sym.kind)

        if self.target_kinds and sym_kind not in self.target_kinds:
            return False

        if self.is_callable and sym_kind not in CALLABLE_KINDS:
            return False

        if self.param_types and not self.matches_params(sym):
            return False

        ident_cmp = self.identifier if case_sensitive else self.identifier.lower()
        sym_name_cmp = sym.name if case_sensitive else sym.name.lower()
        raw_short = (sym.metadata.get("short_name") or "") if sym.metadata else ""
        meta_short = raw_short if case_sensitive else raw_short.lower()

        name_matched = False
        if sym_name_cmp == ident_cmp or (meta_short and meta_short == ident_cmp):
            name_matched = True
        elif "." in sym.name or "::" in sym.name:
            short_seg = re.split(r"[.:]+", sym.name)[-1]
            short_cmp = short_seg if case_sensitive else short_seg.lower()
            if short_cmp == ident_cmp:
                name_matched = True

        if not name_matched:
            return False

        if self.scope:
            scope_norm = self.scope.replace("::", ".")
            scope_cmp = scope_norm if case_sensitive else scope_norm.lower()
            scope_matched = False

            raw_parent = (sym.metadata.get("parent_scope") or "").replace("::", ".") if sym.metadata else ""
            meta_parent = raw_parent if case_sensitive else raw_parent.lower()
            if meta_parent and (meta_parent == scope_cmp or scope_cmp.endswith(f".{meta_parent}") or meta_parent.endswith(f".{scope_cmp}")):
                scope_matched = True

            if not scope_matched and ("." in sym.name or "::" in sym.name):
                sym_parts = re.split(r"[.:]+", sym.name)
                sym_prefix = ".".join(sym_parts[:-1])
                sym_prefix_cmp = sym_prefix if case_sensitive else sym_prefix.lower()
                if sym_prefix_cmp == scope_cmp or sym_prefix_cmp.endswith(f".{scope_cmp}"):
                    scope_matched = True

            if not scope_matched and sym.parent_id:
                parent_id_clean = sym.parent_id.replace("\\", "/").split("/")[-1]
                parent_id_cmp = parent_id_clean if case_sensitive else parent_id_clean.lower()
                if (
                    parent_id_cmp == scope_cmp
                    or parent_id_cmp.endswith(f":{scope_cmp}")
                    or parent_id_cmp.endswith(f".{scope_cmp}")
                ):
                    scope_matched = True

            if not scope_matched and sym.fqn:
                fqn_norm = sym.fqn.replace("::", ".")
                fqn_parts = fqn_norm.split(".")
                if len(fqn_parts) >= 2:
                    fqn_prefix = ".".join(fqn_parts[:-1])
                    fqn_prefix_cmp = fqn_prefix if case_sensitive else fqn_prefix.lower()
                    direct_parent = fqn_parts[-2]
                    if fqn_prefix_cmp == scope_cmp or fqn_prefix_cmp.endswith(f".{scope_cmp}"):
                        scope_matched = True
                    elif direct_parent == self.scope:
                        scope_matched = True
                    elif not case_sensitive and direct_parent.lower() == scope_cmp and sym_kind != SymbolKind.FUNCTION.value:
                        scope_matched = True

            if not scope_matched:
                return False

        return True


class SymbolSelector:
    """
    Parser and matcher for structured AST symbol selectors:
    `[<kind_prefix>\\s+][<scope>.]<identifier>[(<param_types...>)]`
    """

    _PATTERN = re.compile(
        r"^(?:(?P<kind>[a-zA-Z0-9_-]+)\s+)?"
        r"(?:(?P<scope>[a-zA-Z0-9_$:./]+)(?:\.|::))?"
        r"(?P<name>[a-zA-Z0-9_$~]+)"
        r"(?:\((?P<params>.*)\))?$",
        re.IGNORECASE,
    )

    @classmethod
    def parse(cls, expr: str) -> ParsedSelector:
        clean_expr = (expr or "").strip()
        if not clean_expr:
            return ParsedSelector(raw_query="", identifier="")

        m = cls._PATTERN.match(clean_expr)
        if not m:
            work_expr = clean_expr
            fallback_kinds: Optional[Set[str]] = None
            ws_parts = work_expr.split(None, 1)
            if len(ws_parts) == 2 and ws_parts[0].lower() in KIND_PREFIX_MAP:
                fallback_kinds = KIND_PREFIX_MAP.get(ws_parts[0].lower())
                work_expr = ws_parts[1].strip()

            p_start = -1
            if work_expr.endswith(")") and "(" in work_expr:
                angle_depth = 0
                for idx, ch in enumerate(work_expr):
                    if ch == "<":
                        angle_depth += 1
                    elif ch == ">":
                        angle_depth = max(0, angle_depth - 1)
                    elif ch == "(" and angle_depth == 0:
                        p_start = idx
                        break

            is_call = p_start >= 0
            params_tuple: Optional[Tuple[str, ...]] = None
            if is_call:
                base = work_expr[:p_start].strip()
                p_inner = work_expr[p_start + 1 : -1].strip()
                if p_inner:
                    params_tuple = tuple(_split_top_level_comma(p_inner))
            else:
                base = work_expr

            base_stripped = _strip_angle_brackets(base)
            scope = None
            norm_base = base_stripped.replace("::", ".")
            if "." in norm_base:
                parts = [p for p in norm_base.split(".") if p]
                if len(parts) >= 2:
                    scope = ".".join(parts[:-1])
                    name = parts[-1]
                else:
                    name = parts[0] if parts else base_stripped
            else:
                name = base_stripped

            is_callable_fb = is_call or bool(fallback_kinds and fallback_kinds.issubset(CALLABLE_KINDS))
            return ParsedSelector(
                raw_query=clean_expr,
                identifier=name,
                scope=scope,
                target_kinds=fallback_kinds,
                is_callable=is_callable_fb,
                param_types=params_tuple,
            )

        kind_str = m.group("kind")
        scope_str = m.group("scope")
        name_str = m.group("name")
        params_raw = m.group("params")

        target_kinds: Optional[Set[str]] = None
        if kind_str:
            target_kinds = KIND_PREFIX_MAP.get(kind_str.lower())

        has_parens = params_raw is not None
        param_types: Optional[Tuple[str, ...]] = None
        if params_raw is not None and params_raw.strip():
            param_types = tuple(_split_top_level_comma(params_raw))

        is_callable = has_parens
        if target_kinds and target_kinds.issubset(CALLABLE_KINDS):
            is_callable = True

        return ParsedSelector(
            raw_query=clean_expr,
            identifier=name_str,
            scope=scope_str,
            target_kinds=target_kinds,
            is_callable=is_callable,
            param_types=param_types,
        )


def get_symbol_parent_fqn(sym: UnifiedSymbol) -> str:
    """Extract canonical parent FQN or scope of `sym` for overload grouping."""
    if sym.fqn and ("." in sym.fqn or "::" in sym.fqn):
        norm_fqn = sym.fqn.replace("::", ".")
        return norm_fqn.rsplit(".", 1)[0]
    if sym.scope_path:
        return sym.scope_path.replace("::", ".")
    meta = sym.metadata or {}
    if meta.get("parent_scope"):
        return str(meta["parent_scope"]).replace("::", ".")
    if "." in sym.name or "::" in sym.name:
        return sym.name.replace("::", ".").rsplit(".", 1)[0]
    return ""


@dataclass(frozen=True)
class SymbolResolutionResult:
    """
    Deterministic resolution result:
    - `status`: `"matched"` | `"overload_group"` | `"ambiguous"` | `"not_found"`
    - `targets`: `[sym]` for `"matched"`, `[sym1, sym2, ...]` for `"overload_group"`, `[]` for `"ambiguous"` / `"not_found"`
    - `candidates`: list of candidate dicts when `status == "ambiguous"` (or overload group descriptors)
    - `query`: original query string
    """

    status: str
    targets: List[UnifiedSymbol] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    query: str = ""

    @property
    def target_symbol(self) -> Optional[UnifiedSymbol]:
        return self.targets[0] if self.targets else None

    @property
    def overloads(self) -> List[UnifiedSymbol]:
        return list(self.targets)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "targets": [t.to_dict() for t in self.targets],
            "candidates": list(self.candidates),
        }


class DeterministicSymbolResolver:
    """
    100% BM25-free deterministic symbol resolver.
    """

    def __init__(self, symbols: Union[Dict[str, UnifiedSymbol], Iterable[UnifiedSymbol], Any]) -> None:
        if hasattr(symbols, "symbols"):
            raw = symbols.symbols
            self.symbols_map: Dict[str, UnifiedSymbol] = raw if isinstance(raw, dict) else {s.id: s for s in raw}
        elif isinstance(symbols, dict):
            self.symbols_map = symbols
        else:
            self.symbols_map = {s.id: s for s in symbols}
        self._by_ident_lower: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self.by_file_index: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._build_ident_index()

    def _build_ident_index(self) -> None:
        self._by_ident_lower.clear()
        self.by_file_index.clear()
        for sym in self.symbols_map.values():
            self.by_file_index[sym.file_path.replace("\\", "/")].append(sym)
            keys: Set[str] = set()
            if sym.name:
                keys.add(sym.name.lower())
                if "." in sym.name or "::" in sym.name:
                    keys.add(re.split(r"[.:]+", sym.name)[-1].lower())
            raw_short = (sym.metadata.get("short_name") or "") if sym.metadata else ""
            if raw_short:
                keys.add(str(raw_short).lower())
            for k in keys:
                if k:
                    self._by_ident_lower[k].append(sym)

    @staticmethod
    def normalize_ftypes(ftypes: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
        if not ftypes:
            return None
        raw = [ftypes] if isinstance(ftypes, str) else list(ftypes)
        norm: List[str] = []
        for item in raw:
            for part in str(item).split(","):
                p = part.strip().lstrip(".").lower()
                if p and p not in norm:
                    norm.append(p)
        return norm or None

    @staticmethod
    def is_doc_symbol(sym: UnifiedSymbol) -> bool:
        lang = (sym.language or "").lower()
        kind_str = sym.kind.value if hasattr(sym.kind, "value") else str(sym.kind)
        return lang == "markdown" or kind_str.startswith("doc_")

    @classmethod
    def matches_topology_filter(cls, sym: UnifiedSymbol, norm_ftypes: Optional[List[str]]) -> bool:
        if not norm_ftypes:
            return not cls.is_doc_symbol(sym)
        ext = Path(sym.file_path).suffix.lstrip(".").lower()
        allowed = set(norm_ftypes)
        if "md" in allowed or "markdown" in allowed:
            allowed.update({"md", "markdown"})
        return ext in allowed

    @staticmethod
    def _candidate_dict(sym: UnifiedSymbol) -> Dict[str, Any]:
        return {
            "id": sym.id,
            "name": sym.name,
            "fqn": sym.fqn or sym.name,
            "kind": sym.kind,
            "signature": sym.signature,
            "file_path": sym.file_path,
            "line_number": sym.line_number,
            "end_line": sym.end_line,
            "end_line_number": sym.end_line,
            "space": sym.spaces[0] if sym.spaces else "project",
        }

    def _classify_candidates(
        self,
        matched: List[UnifiedSymbol],
        query: str,
    ) -> SymbolResolutionResult:
        if not matched:
            return SymbolResolutionResult(status="not_found", targets=[], candidates=[], query=query)

        dedup_map: Dict[str, UnifiedSymbol] = {}
        for s in matched:
            dedup_map[s.id] = s
        deduped = sorted(dedup_map.values(), key=lambda s: (s.file_path, s.line_number, s.id))

        if len(deduped) > 1 and query.strip().endswith("()"):
            zero_param = [
                s for s in deduped if len(extract_signature_params(s.signature or "")) == 0
            ]
            if zero_param:
                deduped = zero_param

        if len(deduped) == 1:
            return SymbolResolutionResult(status="matched", targets=deduped, candidates=[], query=query)

        # Group by C# partial type identity `(spaces, kind, fqn)`
        partial_type_groups: Set[Tuple[Tuple[str, ...], str, str]] = set()
        # Group by parent type identity `(spaces, parent_fqn_or_scope, short_name)`
        parent_overload_groups: Set[Tuple[Tuple[str, ...], str, str]] = set()

        for sym in deduped:
            sp_tuple = tuple(sorted(sym.spaces or ["project"]))
            short_n = (sym.metadata or {}).get("short_name") or re.split(r"[.:]+", sym.name)[-1]
            parent_fqn = get_symbol_parent_fqn(sym)
            parent_overload_groups.add((sp_tuple, parent_fqn, short_n))
            partial_type_groups.add((sp_tuple, sym.kind, sym.fqn or sym.name))

        # 1. C# partial class siblings of the exact same type
        if len(partial_type_groups) == 1 and all((s.metadata or {}).get("is_partial") for s in deduped):
            primary = next((s for s in deduped if (s.metadata or {}).get("is_primary_partial")), deduped[0])
            return SymbolResolutionResult(status="matched", targets=[primary], candidates=[], query=query)

        # 2. Same-Parent Method Overloads (`(spaces, parent_fqn, short_name)` is identical)
        if len(parent_overload_groups) == 1:
            only_group = next(iter(parent_overload_groups))
            parent_fqn = only_group[1]
            files_set = {s.file_path for s in deduped}
            if parent_fqn or len(files_set) == 1:
                return SymbolResolutionResult(
                    status="overload_group",
                    targets=deduped,
                    candidates=[self._candidate_dict(s) for s in deduped],
                    query=query,
                )

        # 3. Cross-Parent Ambiguity (e.g. `UI.Window.Open` vs `IO.File.Open`)
        return SymbolResolutionResult(
            status="ambiguous",
            targets=[],
            candidates=[self._candidate_dict(s) for s in deduped],
            query=query,
        )

    def resolve(
        self,
        query: str,
        space: Optional[Union[str, List[str]]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        kinds: Optional[Union[str, Iterable[str]]] = None,
    ) -> SymbolResolutionResult:
        """
        Deterministically resolve `query` across `self.symbols_map`:
        Tier 1: Exact case-sensitive `SymbolSelector` / FQN / suffix / short-name match.
        Tier 2: Case-insensitive `SymbolSelector` / FQN / suffix / short-name match.
        """
        query_clean = (query or "").strip()
        if not query_clean or not self.symbols_map:
            return SymbolResolutionResult(status="not_found", query=query_clean)

        space_set: Optional[Set[str]] = None
        if space:
            if isinstance(space, str):
                space_set = {s.strip() for s in space.split(",") if s.strip()}
            else:
                space_set = {str(s).strip() for s in space if str(s).strip()}

        kind_set: Optional[Set[str]] = None
        if kinds:
            if isinstance(kinds, str):
                kind_set = {k.strip().lower() for k in kinds.split(",") if k.strip()}
            else:
                kind_set = {str(k).strip().lower() for k in kinds if str(k).strip()}

        parsed = SymbolSelector.parse(query_clean)
        if not parsed.identifier:
            return SymbolResolutionResult(status="not_found", query=query_clean)

        norm_ftypes = self.normalize_ftypes(ftypes)
        ident_candidates = self._by_ident_lower.get(parsed.identifier.lower())
        if ident_candidates is None:
            self._build_ident_index()
            ident_candidates = self._by_ident_lower.get(parsed.identifier.lower(), [])

        all_space_pool = [
            sym
            for sym in ident_candidates
            if (not space_set or bool(set(sym.spaces or ["project"]).intersection(space_set)))
            and (not kind_set or str(sym.kind).lower() in kind_set)
        ]
        filtered_pool = [sym for sym in all_space_pool if self.matches_topology_filter(sym, norm_ftypes)]
        pool = filtered_pool if (filtered_pool or norm_ftypes) else all_space_pool
        if not pool:
            return SymbolResolutionResult(status="not_found", query=query_clean)

        # Tier 1: Case-sensitive exact FQN, scoped selector, or short-name match
        cs_matches = [sym for sym in pool if parsed.matches(sym, case_sensitive=True)]
        if cs_matches:
            # If query specified a full FQN and some matches have exact FQN == query, prioritize them
            if parsed.scope:
                target_fqn = f"{parsed.scope}.{parsed.identifier}".replace("::", ".")
                exact_fqn = [
                    s
                    for s in cs_matches
                    if (s.fqn or s.name).replace("::", ".") == target_fqn
                ]
                if exact_fqn:
                    return self._classify_candidates(exact_fqn, query_clean)
            return self._classify_candidates(cs_matches, query_clean)

        # Tier 2: Case-insensitive match
        ci_matches = [sym for sym in pool if parsed.matches(sym, case_sensitive=False)]
        if ci_matches:
            if parsed.scope:
                target_fqn_low = f"{parsed.scope}.{parsed.identifier}".replace("::", ".").lower()
                exact_fqn_ci = [
                    s
                    for s in ci_matches
                    if (s.fqn or s.name).replace("::", ".").lower() == target_fqn_low
                ]
                if exact_fqn_ci:
                    return self._classify_candidates(exact_fqn_ci, query_clean)
            return self._classify_candidates(ci_matches, query_clean)

        return SymbolResolutionResult(status="not_found", query=query_clean)


@dataclass(frozen=True)
class CodeSnippet:
    """Extracted source code slice with line numbers and docstring summary."""

    file_path: str
    target_line: int
    start_line: int
    end_line: int
    lines: List[Tuple[int, str]] = field(default_factory=list)
    docstring_summary: str = ""

    @property
    def content(self) -> str:
        return "\n".join(txt for _, txt in self.lines)

    def get_raw_code(self) -> str:
        return self.content

    def get_lines(self, max_lines: Optional[int] = None) -> List[Tuple[int, str]]:
        if max_lines is not None and max_lines > 0:
            return self.lines[:max_lines]
        return list(self.lines)

    def format_text(self, prefix: str = "      ", max_lines: Optional[int] = None) -> str:
        effective = self.get_lines(max_lines)
        if not effective:
            return ""
        max_ln = max(ln for ln, _ in effective)
        width = max(len(str(max_ln)), 3)
        out = []
        for ln, code in effective:
            mark = ">" if ln == self.target_line else " "
            out.append(f"{prefix}{mark} {ln:{width}d} | {code}")
        return "\n".join(out)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "target_line": self.target_line,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "lines": [[ln, txt] for ln, txt in self.lines],
            "docstring_summary": self.docstring_summary,
        }


class SnippetExtractor:
    """Source code snippet extractor supporting workspace-relative and URI paths."""

    def __init__(self, space_manager: Optional[Any] = None, project_root: Optional[Path] = None) -> None:
        self.space_manager = space_manager
        self.project_root = Path(project_root).resolve() if project_root else None
        self._file_lines_cache: Dict[str, Tuple[int, List[str]]] = {}
        self._lock = threading.RLock()

    def _resolve_abs_path(self, file_path: str) -> Optional[Path]:
        if not file_path:
            return None
        raw = str(file_path).replace("\\", "/")
        if "://" in raw:
            try:
                from core import uri

                res = uri.resolve(raw, interactive=False)
                if res and Path(str(res)).is_file():
                    return Path(str(res)).resolve()
            except Exception:
                pass
            _, raw = raw.split("://", 1)
            raw = raw.lstrip("/")

        p = Path(raw)
        if p.is_absolute() and p.is_file():
            return p

        roots: List[Path] = []
        if self.project_root:
            roots.append(self.project_root)
        if self.space_manager is not None:
            proj_r = getattr(self.space_manager, "project_root", None)
            if proj_r:
                roots.append(Path(proj_r).resolve())
            try:
                if hasattr(self.space_manager, "resolve_file_path"):
                    resolved_sp = self.space_manager.resolve_file_path(raw)
                    if resolved_sp and Path(resolved_sp).is_file():
                        return Path(resolved_sp).resolve()
                if hasattr(self.space_manager, "collect_all_entry_paths"):
                    for inc in self.space_manager.collect_all_entry_paths():
                        roots.append(Path(inc).resolve())
            except Exception:
                pass
        try:
            from core import uri

            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                roots.append(Path(str(p_res)).resolve())
        except Exception:
            pass
        roots.append(Path(get_virtual_cwd()).resolve())

        for r in roots:
            cand = r / raw
            if cand.is_file():
                return cand.resolve()
        return None

    def extract(
        self,
        file_path: str,
        line_number: int,
        end_line: Optional[int] = None,
        context_before: int = 2,
        context_after: int = 5,
        docstring: str = "",
    ) -> Optional[CodeSnippet]:
        real_path = self._resolve_abs_path(file_path)
        if not real_path:
            return None
        try:
            cache_key = str(real_path)
            st_mtime_ns = real_path.stat().st_mtime_ns
            with self._lock:
                cached_entry = self._file_lines_cache.get(cache_key)
                if cached_entry is not None and cached_entry[0] == st_mtime_ns:
                    all_lines = cached_entry[1]
                else:
                    all_lines = real_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if cache_key not in self._file_lines_cache and len(self._file_lines_cache) >= 32:
                        oldest_key = next(iter(self._file_lines_cache))
                        del self._file_lines_cache[oldest_key]
                    self._file_lines_cache[cache_key] = (st_mtime_ns, all_lines)
            if not all_lines:
                return None
            total = len(all_lines)
            target_ln = max(1, min(line_number, total))
            start_ln = max(1, target_ln - context_before)
            if end_line and end_line > target_ln:
                stop_ln = min(total, min(end_line, target_ln + 25))
            else:
                stop_ln = min(total, target_ln + context_after)

            sliced = [(i, all_lines[i - 1]) for i in range(start_ln, stop_ln + 1)]
            doc_sum = docstring.strip().splitlines()[0] if (docstring and docstring.strip()) else ""
            return CodeSnippet(
                file_path=file_path,
                target_line=target_ln,
                start_line=start_ln,
                end_line=stop_ln,
                lines=sliced,
                docstring_summary=doc_sum,
            )
        except Exception:
            return None


def _resolve_with_ftype_fallback(
    resolver: DeterministicSymbolResolver,
    target_query: str,
    space: Optional[Union[str, List[str]]],
    norm_ftypes: Optional[List[str]],
) -> SymbolResolutionResult:
    if norm_ftypes and not all(ft in ("md", "markdown") for ft in norm_ftypes):
        res = resolver.resolve(target_query, space=space, ftypes=norm_ftypes)
        if res.status == "not_found":
            res = resolver.resolve(target_query, space=space)
    else:
        res = resolver.resolve(target_query, space=space)
        if res.status == "not_found" and norm_ftypes:
            res = resolver.resolve(target_query, space=space, ftypes=norm_ftypes)
    return res


def _coerce_symbols_dict(symbols_input: Any) -> Dict[str, UnifiedSymbol]:
    if hasattr(symbols_input, "symbols"):
        raw = symbols_input.symbols
        return raw if isinstance(raw, dict) else {s.id: s for s in raw}
    if isinstance(symbols_input, dict):
        return symbols_input
    return {s.id: s for s in symbols_input}


def _get_or_create_resolver_with_fp(
    symbols_map: Dict[str, UnifiedSymbol],
) -> Tuple[DeterministicSymbolResolver, int]:
    current_fp = _compute_symbols_map_fingerprint(symbols_map)
    resolver = get_or_compute_epoch_state(
        "ast.resolver.last_cache",
        epoch_fn=lambda: (id(symbols_map), len(symbols_map), current_fp),
        builder_fn=lambda: DeterministicSymbolResolver(symbols_map),
    )
    return resolver, current_fp


def _get_or_create_resolver(symbols_map: Dict[str, UnifiedSymbol]) -> DeterministicSymbolResolver:
    return _get_or_create_resolver_with_fp(symbols_map)[0]


def _extract_workspace_graph(graph: Any) -> Optional[WorkspaceSymbolGraph]:
    if isinstance(graph, WorkspaceSymbolGraph):
        return graph
    ws = getattr(graph, "workspace_graph", None)
    return ws if isinstance(ws, WorkspaceSymbolGraph) else None


def _map_symbol_to_ws_node_ids(
    ws_graph: WorkspaceSymbolGraph,
    sym: Optional[UnifiedSymbol],
    sym_id: str,
) -> List[str]:
    out: List[str] = []
    if sym_id in ws_graph.nodes_by_id:
        out.append(sym_id)
    if sym is not None:
        norm_p = sym.file_path.replace("\\", "/")
        cid = SymbolNode.compute_canonical_id(norm_p, sym.fqn or sym.name)
        if cid in ws_graph.nodes_by_id and cid not in out:
            out.append(cid)
        fg = ws_graph.file_graphs.get(norm_p)
        if fg is not None:
            short_n = (sym.metadata or {}).get("short_name") or sym.name.split(".")[-1]
            target_fqn = sym.fqn or sym.name
            for cand in fg.all_nodes_by_id.values():
                if cand.span.start_line == sym.line_number and (cand.fqn == target_fqn or cand.name == short_n):
                    if cand.id not in out:
                        out.append(cand.id)
    return out


def _map_ws_node_id_to_unified_id(
    ws_graph: WorkspaceSymbolGraph,
    nid: str,
    symbols_map: Dict[str, UnifiedSymbol],
    by_file_index: Dict[str, List[UnifiedSymbol]],
) -> Optional[str]:
    if nid in symbols_map:
        return nid
    node = ws_graph.nodes_by_id.get(nid)
    if node is None:
        return None
    norm_p = node.file_path.replace("\\", "/")
    file_syms = by_file_index.get(norm_p, ())
    for s in file_syms:
        if s.line_number == node.span.start_line and (
            (s.fqn or s.name) == node.fqn or s.name.split(".")[-1] == node.name
        ):
            return s.id
    for s in file_syms:
        if (s.fqn or s.name) == node.fqn or s.name.split(".")[-1] == node.name:
            return s.id
    return None


def _resolve_topology_query_context(
    target_query: str,
    symbols_input: Union[Dict[str, UnifiedSymbol], Any],
    space: Optional[Union[str, List[str]]],
    ftypes: Optional[Union[str, List[str]]],
    empty_extra_fields: Dict[str, Any],
) -> Tuple[Dict[str, UnifiedSymbol], DeterministicSymbolResolver, Optional[List[str]], SymbolResolutionResult, Optional[Dict[str, Any]], int]:
    """Resolve target query and build early-return payload if status is `not_found` or `ambiguous`."""
    with cell_span("ast.resolve"):
        symbols_map = _coerce_symbols_dict(symbols_input)
        resolver, current_fp = _get_or_create_resolver_with_fp(symbols_map)
        norm_ftypes = resolver.normalize_ftypes(ftypes)
        res = _resolve_with_ftype_fallback(resolver, target_query, space, norm_ftypes)

        if res.status in ("not_found", "ambiguous"):
            is_ambig = res.status == "ambiguous"
            early_payload: Dict[str, Any] = {
                "status": res.status,
                "resolution_status": res.status,
                "ambiguous": is_ambig,
                "query": target_query,
                "target_query": target_query,
                "target": None,
                "target_symbol": None,
                "overloads": [],
                **empty_extra_fields,
                "candidates": res.candidates if is_ambig else [],
            }
            return symbols_map, resolver, norm_ftypes, res, early_payload, current_fp

        return symbols_map, resolver, norm_ftypes, res, None, current_fp


def query_callers(
    target_query: str,
    symbols_map: Union[Dict[str, UnifiedSymbol], Any],
    graph: Union[CallGraphIndex, WorkspaceSymbolGraph],
    space: Optional[Union[str, List[str]]] = None,
    ftypes: Optional[Union[str, List[str]]] = None,
    snippet: bool = True,
    snippet_extractor: Optional[SnippetExtractor] = None,
) -> Dict[str, Any]:
    """
    Query upstream callers for `target_query`.
    - When `status` is `"matched"` or `"overload_group"`, unions callers across all target overloads
      and returns `"overloads": [t.to_dict() for t in res.targets]`.
    - When `status` is `"ambiguous"`, returns `"status": "ambiguous"`, `"ambiguous": True`, and `"candidates"`.
    """
    symbols_map, resolver, norm_ftypes, res, early_payload, current_fp = _resolve_topology_query_context(
        target_query=target_query,
        symbols_input=symbols_map,
        space=space,
        ftypes=ftypes,
        empty_extra_fields={"callers": [], "total_callers": 0},
    )
    if early_payload is not None:
        return early_payload

    ws_graph = _extract_workspace_graph(graph)
    target_ids = expand_contract_symbol_ids(symbols_map, res.targets, precomputed_fingerprint=current_fp)
    if ws_graph is not None:
        for ws_tid in expand_contract_symbol_ids(ws_graph, res.targets):
            if ws_tid in symbols_map and ws_tid not in target_ids:
                target_ids.append(ws_tid)
    caller_sites_map: Dict[str, List[Any]] = defaultdict(list)
    caller_order: List[str] = []

    if hasattr(graph, "get_callers"):
        for tid in target_ids:
            for cid in graph.get_callers(tid):
                if cid not in caller_sites_map:
                    caller_order.append(cid)
                for s in graph.get_call_sites(cid, tid):
                    if s not in caller_sites_map[cid]:
                        caller_sites_map[cid].append(s)

    if ws_graph is not None:
        by_file_idx = resolver.by_file_index
        ws_target_nids: List[str] = []
        for tid in target_ids:
            for wnid in _map_symbol_to_ws_node_ids(ws_graph, symbols_map.get(tid), tid):
                if wnid not in ws_target_nids:
                    ws_target_nids.append(wnid)
        for wnid in ws_target_nids:
            for ed in ws_graph.incoming_edges_by_target.get(wnid, ()):
                if ed.edge_kind != "calls" or ed.resolution_status not in ("resolved", "overload_group"):
                    continue
                caller_uid = _map_ws_node_id_to_unified_id(ws_graph, ed.source_id, symbols_map, by_file_idx)
                if not caller_uid or caller_uid not in symbols_map:
                    continue
                caller_sym = symbols_map[caller_uid]
                if caller_uid not in caller_sites_map:
                    caller_order.append(caller_uid)
                synth_site = SymbolCallSite(
                    callee_name=ed.target_expr.split(".")[-1],
                    line_number=ed.span.start_line,
                    caller_symbol_id=caller_uid,
                    caller_member_name=caller_sym.name,
                    context_prefix=".".join(ed.target_expr.split(".")[:-1]) if "." in ed.target_expr else "",
                    file_path=caller_sym.file_path,
                    space=caller_sym.spaces[0] if caller_sym.spaces else "project",
                )
                if not any(
                    getattr(ex_s, "line_number", None) == synth_site.line_number
                    for ex_s in caller_sites_map[caller_uid]
                ):
                    caller_sites_map[caller_uid].append(synth_site)

    extractor = snippet_extractor or SnippetExtractor()
    callers_detail: List[Dict[str, Any]] = []

    for cid in caller_order:
        caller_sym = symbols_map.get(cid)
        if not caller_sym or not resolver.matches_topology_filter(caller_sym, norm_ftypes):
            continue

        sites = caller_sites_map[cid]
        code_snip = None
        if snippet:
            target_ln = sites[0].line_number if sites else caller_sym.line_number
            code_snip = extractor.extract(
                file_path=caller_sym.file_path,
                line_number=target_ln,
                context_before=2,
                context_after=5,
                docstring=caller_sym.docstring,
            )

        callers_detail.append(
            {
                "id": caller_sym.id,
                "name": caller_sym.name,
                "fqn": caller_sym.fqn or caller_sym.name,
                "kind": caller_sym.kind,
                "file_path": caller_sym.file_path,
                "line_number": caller_sym.line_number,
                "signature": caller_sym.signature,
                "symbol": caller_sym,
                "call_sites": [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in sites],
                "code_snippet": code_snip,
                "snippet": code_snip.to_dict() if code_snip else None,
            }
        )

    primary_sym = res.targets[0]
    return {
        "status": res.status,
        "resolution_status": res.status,
        "ambiguous": False,
        "query": target_query,
        "target_query": target_query,
        "target": primary_sym.to_dict(),
        "target_symbol": primary_sym,
        "overloads": [t.to_dict() for t in res.targets],
        "overload_symbols": list(res.targets),
        "callers": callers_detail,
        "total_callers": len(callers_detail),
        "candidates": [],
    }


def query_callees(
    target_query: str,
    symbols_map: Union[Dict[str, UnifiedSymbol], Any],
    graph: Union[CallGraphIndex, WorkspaceSymbolGraph],
    space: Optional[Union[str, List[str]]] = None,
    ftypes: Optional[Union[str, List[str]]] = None,
    snippet: bool = True,
    snippet_extractor: Optional[SnippetExtractor] = None,
) -> Dict[str, Any]:
    """
    Query downstream callees for `target_query` (unions callees across all overloads when `status == "overload_group"`).
    """
    symbols_map, resolver, norm_ftypes, res, early_payload, _ = _resolve_topology_query_context(
        target_query=target_query,
        symbols_input=symbols_map,
        space=space,
        ftypes=ftypes,
        empty_extra_fields={"callees": [], "total_callees": 0},
    )
    if early_payload is not None:
        return early_payload

    callee_sites_map: Dict[str, List[Any]] = defaultdict(list)
    callee_order: List[str] = []

    if hasattr(graph, "get_callees"):
        for caller_sym in res.targets:
            for cid in graph.get_callees(caller_sym.id):
                if cid not in callee_sites_map:
                    callee_order.append(cid)
                for s in graph.get_call_sites(caller_sym.id, cid):
                    if s not in callee_sites_map[cid]:
                        callee_sites_map[cid].append(s)

    ws_graph = _extract_workspace_graph(graph)
    if ws_graph is not None:
        by_file_idx = resolver.by_file_index
        for caller_sym in res.targets:
            for wnid in _map_symbol_to_ws_node_ids(ws_graph, caller_sym, caller_sym.id):
                for ed in ws_graph.outgoing_edges_by_source.get(wnid, ()):
                    if ed.edge_kind != "calls" or ed.resolution_status not in ("resolved", "overload_group"):
                        continue
                    for tid_ws in ed.resolved_target_ids:
                        callee_uid = _map_ws_node_id_to_unified_id(ws_graph, tid_ws, symbols_map, by_file_idx)
                        if not callee_uid or callee_uid not in symbols_map:
                            continue
                        if callee_uid not in callee_sites_map:
                            callee_order.append(callee_uid)
                        synth_site = SymbolCallSite(
                            callee_name=ed.target_expr.split(".")[-1],
                            line_number=ed.span.start_line,
                            caller_symbol_id=caller_sym.id,
                            caller_member_name=caller_sym.name,
                            context_prefix=".".join(ed.target_expr.split(".")[:-1]) if "." in ed.target_expr else "",
                            file_path=caller_sym.file_path,
                            space=caller_sym.spaces[0] if caller_sym.spaces else "project",
                        )
                        if not any(
                            getattr(ex_s, "line_number", None) == synth_site.line_number
                            for ex_s in callee_sites_map[callee_uid]
                        ):
                            callee_sites_map[callee_uid].append(synth_site)

    extractor = snippet_extractor or SnippetExtractor()
    callees_detail: List[Dict[str, Any]] = []

    for cid in callee_order:
        callee_sym = symbols_map.get(cid)
        if not callee_sym or not resolver.matches_topology_filter(callee_sym, norm_ftypes):
            continue

        sites = callee_sites_map[cid]
        code_snip = None
        if snippet:
            code_snip = extractor.extract(
                file_path=callee_sym.file_path,
                line_number=callee_sym.line_number,
                end_line=callee_sym.end_line,
                context_before=2,
                context_after=6,
                docstring=callee_sym.docstring,
            )

        callees_detail.append(
            {
                "id": callee_sym.id,
                "name": callee_sym.name,
                "fqn": callee_sym.fqn or callee_sym.name,
                "kind": callee_sym.kind,
                "file_path": callee_sym.file_path,
                "line_number": callee_sym.line_number,
                "signature": callee_sym.signature,
                "symbol": callee_sym,
                "call_sites": [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in sites],
                "code_snippet": code_snip,
                "snippet": code_snip.to_dict() if code_snip else None,
            }
        )

    primary_sym = res.targets[0]
    return {
        "status": res.status,
        "resolution_status": res.status,
        "ambiguous": False,
        "query": target_query,
        "target_query": target_query,
        "target": primary_sym.to_dict(),
        "target_symbol": primary_sym,
        "overloads": [t.to_dict() for t in res.targets],
        "overload_symbols": list(res.targets),
        "callees": callees_detail,
        "total_callees": len(callees_detail),
        "candidates": [],
    }


def query_impact(
    target_query: str,
    symbols_map: Union[Dict[str, UnifiedSymbol], Any],
    graph: Union[CallGraphIndex, WorkspaceSymbolGraph],
    depth: int = 2,
    space: Optional[Union[str, List[str]]] = None,
    ftypes: Optional[Union[str, List[str]]] = None,
    max_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Analyze N-hop reverse BFS blast radius for `target_query` (supporting `overload_group` and `ambiguous` guard).
    """
    if max_depth is not None:
        depth = max_depth
    symbols_map, resolver, norm_ftypes, res, early_payload, current_fp = _resolve_topology_query_context(
        target_query=target_query,
        symbols_input=symbols_map,
        space=space,
        ftypes=ftypes,
        empty_extra_fields={
            "depth": depth,
            "max_depth": depth,
            "layers": {},
            "affected_files": [],
            "total_impacted_symbols": 0,
            "total_affected_symbols": 0,
            "total_impacted_files": 0,
        },
    )
    if early_payload is not None:
        return early_payload

    ws_graph = _extract_workspace_graph(graph)
    target_ids = expand_contract_symbol_ids(symbols_map, res.targets, precomputed_fingerprint=current_fp)
    if ws_graph is not None:
        for ws_tid in expand_contract_symbol_ids(ws_graph, res.targets):
            if ws_tid in symbols_map and ws_tid not in target_ids:
                target_ids.append(ws_tid)
    merged_layers_ids: Dict[int, List[str]] = defaultdict(list)
    merged_chains: Dict[str, List[Tuple[str, str]]] = {}
    seen_impacted_ids: Set[str] = set(target_ids)

    if hasattr(graph, "query_impact"):
        for tid in target_ids:
            impact_raw = graph.query_impact(tid, max_depth=depth)
            for d, sids in impact_raw.get("layers", {}).items():
                for sid in sids:
                    if sid not in seen_impacted_ids:
                        seen_impacted_ids.add(sid)
                        merged_layers_ids[d].append(sid)
            for k, chain in impact_raw.get("call_chains", {}).items():
                if k not in merged_chains:
                    merged_chains[k] = chain

    if ws_graph is not None:
        by_file_idx = resolver.by_file_index
        seed_ws_ids: List[str] = []
        for tid in target_ids:
            for wnid in _map_symbol_to_ws_node_ids(ws_graph, symbols_map.get(tid), tid):
                if wnid not in seed_ws_ids:
                    seed_ws_ids.append(wnid)
        if seed_ws_ids:
            trav = traverse_workspace_edges(
                ws_graph,
                seed_ws_ids,
                edge_kinds=("calls",),
                direction="in",
                depth=depth,
                status_filter=("resolved", "overload_group"),
            )
            for d, nodes in trav.get("layers", {}).items():
                for n in nodes:
                    uid = _map_ws_node_id_to_unified_id(ws_graph, n.id, symbols_map, by_file_idx)
                    if uid and uid not in seen_impacted_ids:
                        seen_impacted_ids.add(uid)
                        merged_layers_ids[d].append(uid)

    layers_detail: Dict[int, List[UnifiedSymbol]] = {}
    all_files: Set[str] = set()
    total_symbols = 0

    for d, sids in sorted(merged_layers_ids.items()):
        layer_syms: List[UnifiedSymbol] = []
        for sid in sids:
            sym = symbols_map.get(sid)
            if sym and resolver.matches_topology_filter(sym, norm_ftypes):
                layer_syms.append(sym)
                all_files.add(sym.file_path)
                total_symbols += 1
        if layer_syms:
            layers_detail[d] = layer_syms

    filtered_chains = {
        k: v
        for k, v in merged_chains.items()
        if any(s.id == k for syms in layers_detail.values() for s in syms)
    }

    primary_sym = res.targets[0]
    return {
        "status": res.status,
        "resolution_status": res.status,
        "ambiguous": False,
        "query": target_query,
        "target_query": target_query,
        "depth": depth,
        "max_depth": depth,
        "target": primary_sym.to_dict(),
        "target_symbol": primary_sym,
        "overloads": [t.to_dict() for t in res.targets],
        "overload_symbols": list(res.targets),
        "layers": layers_detail,
        "call_chains": filtered_chains,
        "affected_files": sorted(all_files),
        "total_impacted_symbols": total_symbols,
        "total_affected_symbols": total_symbols,
        "total_impacted_files": len(all_files),
        "candidates": [],
    }


DEFAULT_TRAVERSE_STATUS_FILTER: FrozenSet[str] = frozenset({"resolved", "overload_group", "ambiguous"})


def _normalize_str_set(val: Optional[Union[str, Iterable[str]]]) -> Optional[Set[str]]:
    if val is None:
        return None
    if isinstance(val, str):
        items = {s.strip() for s in val.split(",") if s.strip()}
    else:
        items = {str(s).strip() for s in val if str(s).strip()}
    return items or None


def select_workspace_nodes(
    workspace_graph: WorkspaceSymbolGraph,
    *,
    spaces: Optional[Union[str, Iterable[str]]] = None,
    kinds: Optional[Union[str, Iterable[str]]] = None,
    visibility: Optional[Union[str, Iterable[str]]] = None,
    facets: Optional[Mapping[str, Any]] = None,
    ftypes: Optional[Union[str, Iterable[str]]] = None,
    symbols_map: Optional[Mapping[str, UnifiedSymbol]] = None,
) -> Tuple[SymbolNode, ...]:
    """
    L1 Primitive: Batch filter `SymbolNode` instances across `workspace_graph` by orthogonal criteria
    (`spaces`, `kinds`, `visibility`, `facets`, `ftypes`).
    """
    space_set = _normalize_str_set(spaces)
    kind_set = {k.lower() for k in (_normalize_str_set(kinds) or set())} or None
    vis_set = {v.lower() for v in (_normalize_str_set(visibility) or set())} or None
    ftype_set = {ft.lstrip(".").lower() for ft in (_normalize_str_set(ftypes) or set())} or None

    file_spaces_map: Dict[str, Set[str]] = defaultdict(set)
    if symbols_map:
        for sym in symbols_map.values():
            if sym.file_path and sym.spaces:
                file_spaces_map[sym.file_path].update(sym.spaces)

    matched: List[SymbolNode] = []
    for node in workspace_graph.nodes_by_id.values():
        if kind_set:
            node_kinds_low = {k.lower() for k in node.kinds}
            if not (node_kinds_low & kind_set):
                continue
        if vis_set:
            n_vis = str(node.facets.get("visibility") or "public").lower()
            if "non-private" in vis_set or "non_private" in vis_set or "api" in vis_set:
                if n_vis == "private" and n_vis not in vis_set:
                    continue
            elif n_vis not in vis_set:
                continue
        if ftype_set:
            f_path = node.file_path
            ext = Path(f_path).suffix.lstrip(".").lower()
            lang_low = (node.language or "").lower()
            if ext not in ftype_set and lang_low not in ftype_set:
                continue
        if space_set:
            f_path = node.file_path
            node_sp = set(file_spaces_map.get(f_path, set()))
            raw_f_sp = node.facets.get("spaces")
            if isinstance(raw_f_sp, (list, tuple, set, frozenset)):
                node_sp.update(str(x) for x in raw_f_sp)
            if not node_sp:
                node_sp.add("project")
            if not (node_sp & space_set):
                continue
        if facets:
            facets_ok = True
            for fk, fv in facets.items():
                actual = node.facets.get(fk)
                if isinstance(fv, (set, frozenset, list, tuple)):
                    if isinstance(actual, (set, frozenset, list, tuple)):
                        if not (set(actual) & set(fv)):
                            facets_ok = False
                            break
                    elif actual not in fv:
                        facets_ok = False
                        break
                elif actual != fv:
                    facets_ok = False
                    break
            if not facets_ok:
                continue
        matched.append(node)

    matched.sort(key=lambda n: (n.file_path, n.span.start_byte, n.name))
    return tuple(matched)


def traverse_workspace_edges(
    workspace_graph: WorkspaceSymbolGraph,
    seed_ids: Union[str, Iterable[str]],
    *,
    edge_kinds: Optional[Union[str, Iterable[str]]] = None,
    direction: str = "out",
    depth: int = 1,
    status_filter: Optional[Union[str, Iterable[str]]] = None,
) -> Dict[str, Any]:
    """
    L1 Primitive: General directed BFS graph traversal across `workspace_graph` supporting arbitrary `edge_kinds`
    (`calls`, `inherits`, `implements`, `imports`, `references`, `documents`, `merges_with`, `declares`),
    direction (`"out"` | `"in"` | `"both"`), multi-hop `depth`, and `status_filter`.
    """
    dir_norm = str(direction or "out").strip().lower()
    if dir_norm not in ("out", "in", "both"):
        raise ASTError(f"Invalid traversal direction: {direction!r} (expected 'out', 'in', or 'both')")

    if isinstance(seed_ids, str):
        raw_seeds = [seed_ids] if seed_ids.strip() else []
    else:
        raw_seeds = [str(s).strip() for s in seed_ids if str(s).strip()]

    valid_seeds: List[str] = []
    for sid in raw_seeds:
        if sid in workspace_graph.nodes_by_id and sid not in valid_seeds:
            valid_seeds.append(sid)

    kind_filter = _normalize_str_set(edge_kinds)
    eff_status = _normalize_str_set(status_filter) or set(DEFAULT_TRAVERSE_STATUS_FILTER)

    if not valid_seeds or depth <= 0:
        return {
            "seed_ids": tuple(valid_seeds),
            "seed_nodes": tuple(workspace_graph.nodes_by_id[s] for s in valid_seeds),
            "direction": dir_norm,
            "depth": max(0, int(depth)),
            "edge_kinds": tuple(sorted(kind_filter)) if kind_filter else (),
            "status_filter": tuple(sorted(eff_status)),
            "layers": {},
            "edges": (),
            "ambiguous_edges": (),
            "total_reached_nodes": 0,
        }

    from collections import deque

    visited: Set[str] = set(valid_seeds)
    layers: Dict[int, List[SymbolNode]] = {}
    traversed_edges: List[RelationEdge] = []
    ambiguous_edges: List[RelationEdge] = []
    seen_edge_keys: Set[Tuple[str, str, str, int, int]] = set()
    queue: deque = deque((sid, 0) for sid in valid_seeds)

    while queue:
        curr_id, curr_d = queue.popleft()
        if curr_d >= depth:
            continue
        next_d = curr_d + 1
        candidate_edges: List[Tuple[RelationEdge, str]] = []

        if dir_norm in ("out", "both"):
            for ed in workspace_graph.outgoing_edges_by_source.get(curr_id, ()):
                if kind_filter and ed.edge_kind not in kind_filter:
                    continue
                if ed.resolution_status not in eff_status:
                    continue
                for tid in ed.resolved_target_ids:
                    candidate_edges.append((ed, tid))

        if dir_norm in ("in", "both"):
            for ed in workspace_graph.incoming_edges_by_target.get(curr_id, ()):
                if kind_filter and ed.edge_kind not in kind_filter:
                    continue
                if ed.resolution_status not in eff_status:
                    continue
                candidate_edges.append((ed, ed.source_id))

        for ed, neighbor_id in candidate_edges:
            ekey = (ed.source_id, ed.target_expr, ed.edge_kind, ed.span.start_byte, ed.span.end_byte)
            if ekey not in seen_edge_keys:
                seen_edge_keys.add(ekey)
                traversed_edges.append(ed)
                if ed.resolution_status == "ambiguous":
                    ambiguous_edges.append(ed)
            if neighbor_id not in visited and neighbor_id in workspace_graph.nodes_by_id:
                visited.add(neighbor_id)
                layers.setdefault(next_d, []).append(workspace_graph.nodes_by_id[neighbor_id])
                queue.append((neighbor_id, next_d))

    frozen_layers = {d: tuple(nodes) for d, nodes in sorted(layers.items())}
    total_reached = sum(len(nds) for nds in frozen_layers.values())
    return {
        "seed_ids": tuple(valid_seeds),
        "seed_nodes": tuple(workspace_graph.nodes_by_id[s] for s in valid_seeds),
        "direction": dir_norm,
        "depth": int(depth),
        "edge_kinds": tuple(sorted(kind_filter)) if kind_filter else (),
        "status_filter": tuple(sorted(eff_status)),
        "layers": frozen_layers,
        "edges": tuple(traversed_edges),
        "ambiguous_edges": tuple(ambiguous_edges),
        "total_reached_nodes": total_reached,
    }


__all__ = [
    "CALLABLE_KINDS",
    "CodeSnippet",
    "DEFAULT_TRAVERSE_STATUS_FILTER",
    "DeterministicSymbolResolver",
    "KIND_PREFIX_MAP",
    "ParsedSelector",
    "SnippetExtractor",
    "SymbolResolutionResult",
    "SymbolSelector",
    "_split_top_level_comma",
    "extract_signature_params",
    "get_symbol_parent_fqn",
    "query_callees",
    "query_callers",
    "query_impact",
    "select_workspace_nodes",
    "traverse_workspace_edges",
]
