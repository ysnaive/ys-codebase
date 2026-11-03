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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .graph import CallGraphIndex
from .linker import expand_contract_symbol_ids
from .schema import SymbolKind, UnifiedSymbol

KIND_PREFIX_MAP: Dict[str, Set[str]] = {
    "class": {SymbolKind.CLASS.value},
    "cls": {SymbolKind.CLASS.value},
    "struct": {SymbolKind.STRUCT.value},
    "interface": {SymbolKind.INTERFACE.value},
    "iface": {SymbolKind.INTERFACE.value},
    "enum": {SymbolKind.ENUM.value},
    "fn": {SymbolKind.FUNCTION.value, SymbolKind.METHOD.value},
    "func": {SymbolKind.FUNCTION.value, SymbolKind.METHOD.value},
    "def": {SymbolKind.FUNCTION.value, SymbolKind.METHOD.value},
    "function": {SymbolKind.FUNCTION.value, SymbolKind.METHOD.value},
    "method": {SymbolKind.METHOD.value},
    "meth": {SymbolKind.METHOD.value},
    "type": {SymbolKind.TYPE_ALIAS.value},
    "typedef": {SymbolKind.TYPE_ALIAS.value},
    "const": {SymbolKind.CONSTANT.value},
    "constant": {SymbolKind.CONSTANT.value},
    "var": {SymbolKind.VARIABLE.value},
    "variable": {SymbolKind.VARIABLE.value},
    "let": {SymbolKind.VARIABLE.value},
    "macro": {SymbolKind.MACRO.value},
    "doc": {
        SymbolKind.DOC_HEADING_1.value,
        SymbolKind.DOC_HEADING_2.value,
        SymbolKind.DOC_HEADING_3.value,
        SymbolKind.DOC_HEADING_4.value,
        SymbolKind.DOC_SECTION.value,
    },
    "h1": {SymbolKind.DOC_HEADING_1.value},
    "h2": {SymbolKind.DOC_HEADING_2.value},
    "h3": {SymbolKind.DOC_HEADING_3.value},
    "h4": {SymbolKind.DOC_HEADING_4.value},
}

CALLABLE_KINDS: Set[str] = {
    SymbolKind.FUNCTION.value,
    SymbolKind.METHOD.value,
    "function",
    "method",
    "constructor",
}


def extract_signature_params(signature: str) -> List[str]:
    """Extract parameter declarations inside `(...)` of a symbol signature."""
    if not signature or "(" not in signature or ")" not in signature:
        return []
    start = signature.find("(")
    end = signature.rfind(")")
    if end <= start:
        return []
    inner = signature[start + 1 : end].strip()
    if not inner:
        return []

    params: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in inner:
        if ch in "<([":
            depth += 1
            current.append(ch)
        elif ch in ">)]":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            tok = "".join(current).strip()
            if tok:
                params.append(tok)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        params.append(tail)

    if params and params[0].split()[0] in ("self", "cls", "this"):
        params = params[1:]
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
            is_call = clean_expr.endswith(")") and "(" in clean_expr
            params_tuple: Optional[Tuple[str, ...]] = None
            if is_call:
                p_start = clean_expr.find("(")
                base = clean_expr[:p_start].strip()
                p_inner = clean_expr[p_start + 1 : -1].strip()
                if p_inner:
                    params_tuple = tuple(p.strip() for p in p_inner.split(",") if p.strip())
            else:
                base = clean_expr

            scope = None
            norm_base = base.replace("::", ".")
            if "." in norm_base:
                parts = norm_base.split(".")
                scope = ".".join(parts[:-1])
                name = parts[-1]
            else:
                name = base
            return ParsedSelector(
                raw_query=clean_expr,
                identifier=name,
                scope=scope,
                is_callable=is_call,
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
            param_types = tuple(p.strip() for p in params_raw.split(",") if p.strip())

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


@dataclass
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

        norm_ftypes = self.normalize_ftypes(ftypes)
        all_space_pool = [
            sym
            for sym in self.symbols_map.values()
            if (not space_set or bool(set(sym.spaces or ["project"]).intersection(space_set)))
        ]
        filtered_pool = [sym for sym in all_space_pool if self.matches_topology_filter(sym, norm_ftypes)]
        pool = filtered_pool if (filtered_pool or norm_ftypes) else all_space_pool
        if not pool:
            return SymbolResolutionResult(status="not_found", query=query_clean)

        parsed = SymbolSelector.parse(query_clean)
        if not parsed.identifier:
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


@dataclass
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
                loaded_spaces = (
                    self.space_manager.get_all_spaces()
                    if hasattr(self.space_manager, "get_all_spaces")
                    else self.space_manager.load_spaces()
                )
                for sp_name in loaded_spaces:
                    for inc in self.space_manager.resolve_space_include(sp_name):
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
        roots.append(Path.cwd().resolve())

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


def _resolve_topology_query_context(
    target_query: str,
    symbols_input: Union[Dict[str, UnifiedSymbol], Any],
    space: Optional[Union[str, List[str]]],
    ftypes: Optional[Union[str, List[str]]],
    empty_extra_fields: Dict[str, Any],
) -> Tuple[Dict[str, UnifiedSymbol], DeterministicSymbolResolver, Optional[List[str]], SymbolResolutionResult, Optional[Dict[str, Any]]]:
    """Resolve target query and build early-return payload if status is `not_found` or `ambiguous`."""
    symbols_map = _coerce_symbols_dict(symbols_input)
    resolver = DeterministicSymbolResolver(symbols_map)
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
        return symbols_map, resolver, norm_ftypes, res, early_payload

    return symbols_map, resolver, norm_ftypes, res, None


def query_callers(
    target_query: str,
    symbols_map: Union[Dict[str, UnifiedSymbol], Any],
    graph: CallGraphIndex,
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
    symbols_map, resolver, norm_ftypes, res, early_payload = _resolve_topology_query_context(
        target_query=target_query,
        symbols_input=symbols_map,
        space=space,
        ftypes=ftypes,
        empty_extra_fields={"callers": [], "total_callers": 0},
    )
    if early_payload is not None:
        return early_payload

    target_ids = expand_contract_symbol_ids(symbols_map, res.targets)
    caller_sites_map: Dict[str, List[Any]] = defaultdict(list)
    caller_order: List[str] = []

    for tid in target_ids:
        for cid in graph.get_callers(tid):
            if cid not in caller_sites_map:
                caller_order.append(cid)
            for s in graph.get_call_sites(cid, tid):
                if s not in caller_sites_map[cid]:
                    caller_sites_map[cid].append(s)

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
    graph: CallGraphIndex,
    space: Optional[Union[str, List[str]]] = None,
    ftypes: Optional[Union[str, List[str]]] = None,
    snippet: bool = True,
    snippet_extractor: Optional[SnippetExtractor] = None,
) -> Dict[str, Any]:
    """
    Query downstream callees for `target_query` (unions callees across all overloads when `status == "overload_group"`).
    """
    symbols_map, resolver, norm_ftypes, res, early_payload = _resolve_topology_query_context(
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

    for caller_sym in res.targets:
        for cid in graph.get_callees(caller_sym.id):
            if cid not in callee_sites_map:
                callee_order.append(cid)
            for s in graph.get_call_sites(caller_sym.id, cid):
                if s not in callee_sites_map[cid]:
                    callee_sites_map[cid].append(s)

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
    graph: CallGraphIndex,
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
    symbols_map, resolver, norm_ftypes, res, early_payload = _resolve_topology_query_context(
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

    target_ids = expand_contract_symbol_ids(symbols_map, res.targets)
    merged_layers_ids: Dict[int, List[str]] = defaultdict(list)
    merged_chains: Dict[str, List[Tuple[str, str]]] = {}
    seen_impacted_ids: Set[str] = set(target_ids)

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


__all__ = [
    "CALLABLE_KINDS",
    "CodeSnippet",
    "DeterministicSymbolResolver",
    "KIND_PREFIX_MAP",
    "ParsedSelector",
    "SnippetExtractor",
    "SymbolResolutionResult",
    "SymbolSelector",
    "extract_signature_params",
    "get_symbol_parent_fqn",
    "query_callees",
    "query_callers",
    "query_impact",
]
