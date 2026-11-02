"""
Cross-File Call Topology Linker (`TopologyLinker`) and Polymorphic Contract Expander (`expand_contract_symbol_ids`).
- `_by_fqn: Dict[str, List[UnifiedSymbol]]` preserves all method overloads sharing the same FQN
  instead of overwriting earlier overloads.
- Supports parameter-count matching when resolving overloaded call sites and links overload groups cleanly.
"""

from collections import defaultdict
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .graph import CallGraphIndex
from .schema import SymbolCallSite, SymbolKind, UnifiedSymbol

logger = logging.getLogger("ast.linker")


def _extract_param_count_from_signature(signature: str) -> Optional[int]:
    """Extract parameter count from a declaration signature `(...)`."""
    if not signature or "(" not in signature or ")" not in signature:
        return None
    start = signature.find("(")
    end = signature.rfind(")")
    if end <= start:
        return None
    inner = signature[start + 1 : end].strip()
    if not inner:
        return 0
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    if parts and parts[0].split()[0] in ("self", "cls", "this"):
        parts = parts[1:]
    return len(parts)


class TopologyLinker:
    """
    4-Tier Cross-File Symbol Call Topology Disambiguation Linker.
    Preserves all method overloads per FQN in `self._by_fqn: Dict[str, List[UnifiedSymbol]]`.
    """

    def __init__(
        self,
        symbols_map: Union[Dict[str, UnifiedSymbol], Iterable[UnifiedSymbol]],
        file_imports: Optional[Dict[str, Dict[str, str]]] = None,
    ):
        if isinstance(symbols_map, dict):
            self.symbols_map: Dict[str, UnifiedSymbol] = symbols_map
        else:
            self.symbols_map = {s.id: s for s in symbols_map}
        self.file_imports: Dict[str, Dict[str, str]] = file_imports or {}

        self._by_file: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_name: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_space_name: Dict[str, Dict[str, List[UnifiedSymbol]]] = defaultdict(lambda: defaultdict(list))
        self._by_file_name: Dict[Tuple[str, str], List[UnifiedSymbol]] = defaultdict(list)
        self._by_fqn: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_parent_id: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._class_bases: Dict[str, Set[str]] = defaultdict(set)
        self._class_fields: Dict[str, Dict[str, str]] = defaultdict(dict)

        self._reindex()

    def _reindex(self) -> None:
        self._by_file.clear()
        self._by_name.clear()
        self._by_space_name.clear()
        self._by_file_name.clear()
        self._by_fqn.clear()
        self._by_parent_id.clear()
        self._class_bases.clear()
        self._class_fields.clear()

        for _, sym in self.symbols_map.items():
            norm_path = sym.file_path.replace("\\", "/").lower()
            self._by_file[norm_path].append(sym)
            self._by_name[sym.name].append(sym)
            self._by_file_name[(norm_path, sym.name)].append(sym)

            if sym.fqn:
                fqn_low = sym.fqn.lower()
                if sym not in self._by_fqn[fqn_low]:
                    self._by_fqn[fqn_low].append(sym)
                if sym.fqn != fqn_low and sym not in self._by_fqn[sym.fqn]:
                    self._by_fqn[sym.fqn].append(sym)

            if sym.parent_id:
                self._by_parent_id[sym.parent_id].append(sym)

            short_name = sym.metadata.get("short_name") or (
                re.split(r"[.:]+", sym.name)[-1] if ("." in sym.name or "::" in sym.name) else sym.name
            )
            parent_scope = sym.metadata.get("parent_scope") or ""

            base_types = sym.metadata.get("base_types")
            if base_types and isinstance(base_types, (list, tuple)):
                for bt in base_types:
                    if bt:
                        self._class_bases[short_name].add(str(bt))

            field_types = sym.metadata.get("field_types")
            if field_types and isinstance(field_types, dict):
                for fn, ft in field_types.items():
                    if fn and ft:
                        self._class_fields[short_name][str(fn)] = str(ft)

            alias_keys: List[str] = []
            if short_name and short_name != sym.name:
                alias_keys.append(short_name)
            if parent_scope and short_name:
                scoped_key = f"{parent_scope}.{short_name}"
                if scoped_key != sym.name and scoped_key not in alias_keys:
                    alias_keys.append(scoped_key)

            for key in alias_keys:
                self._by_name[key].append(sym)
                self._by_file_name[(norm_path, key)].append(sym)

            for sp in sym.spaces or ["project"]:
                self._by_space_name[sp][sym.name].append(sym)
                for key in alias_keys:
                    self._by_space_name[sp][key].append(sym)

    @staticmethod
    def _select_best_overload(
        candidates: List[UnifiedSymbol],
        arg_count: Optional[int] = None,
    ) -> Optional[UnifiedSymbol]:
        if not candidates:
            return None
        if len(candidates) == 1 or arg_count is None:
            return candidates[0]
        for cand in candidates:
            if _extract_param_count_from_signature(cand.signature) == arg_count:
                return cand
        return candidates[0]

    def find_caller_symbol_id(self, file_path: str, caller_member_name: str) -> Optional[str]:
        norm_path = file_path.replace("\\", "/").lower()
        candidates = self._by_file.get(norm_path, [])
        if not candidates:
            return None

        if caller_member_name and caller_member_name != "<module>":
            for sym in candidates:
                if sym.name == caller_member_name:
                    return sym.id
                if sym.name.endswith(f".{caller_member_name}") or caller_member_name.endswith(f".{sym.name}"):
                    return sym.id

        return candidates[0].id if candidates else None

    def _get_caller_class_name(self, site: SymbolCallSite) -> str:
        caller_id = site.caller_symbol_id or self.find_caller_symbol_id(site.file_path, site.caller_member_name)
        if caller_id and caller_id in self.symbols_map:
            caller_sym = self.symbols_map[caller_id]
            if caller_sym.kind in ("class", "struct", "interface"):
                return caller_sym.metadata.get("short_name") or re.split(r"[.:]+", caller_sym.name)[-1]
            parent_scope = caller_sym.metadata.get("parent_scope")
            if parent_scope:
                return str(parent_scope)
            if caller_sym.parent_id and caller_sym.parent_id in self.symbols_map:
                parent_sym = self.symbols_map[caller_sym.parent_id]
                if parent_sym.kind in ("class", "struct", "interface"):
                    return parent_sym.metadata.get("short_name") or re.split(r"[.:]+", parent_sym.name)[-1]

        if site.caller_member_name and site.caller_member_name != "<module>" and "." in site.caller_member_name:
            parts = site.caller_member_name.split(".")
            return parts[-2] if len(parts) >= 2 else parts[0]
        return ""

    def _get_ancestor_classes(self, class_name: str) -> List[str]:
        if not class_name:
            return []
        visited: List[str] = []
        queue: List[str] = list(self._class_bases.get(class_name, []))
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.append(curr)
                for nxt in self._class_bases.get(curr, []):
                    if nxt not in visited:
                        queue.append(nxt)
        return visited

    def _resolve_in_class_or_bases(
        self,
        class_name: str,
        callee: str,
        norm_path: str,
        space_name: str,
        bases_only: bool = False,
        arg_count: Optional[int] = None,
    ) -> Optional[str]:
        if not class_name:
            return None

        target_classes = (
            self._get_ancestor_classes(class_name)
            if bases_only
            else ([class_name] + self._get_ancestor_classes(class_name))
        )
        for cls_name in target_classes:
            scoped_target = f"{cls_name}.{callee}"
            local_matches = self._by_file_name.get((norm_path, scoped_target), [])
            if local_matches:
                chosen = self._select_best_overload(local_matches, arg_count=arg_count)
                return chosen.id if chosen else None
            if space_name and space_name in self._by_space_name:
                space_matches = self._by_space_name[space_name].get(scoped_target, [])
                if space_matches:
                    chosen = self._select_best_overload(space_matches, arg_count=arg_count)
                    return chosen.id if chosen else None
            global_matches = self._by_name.get(scoped_target, [])
            if global_matches:
                chosen = self._select_best_overload(global_matches, arg_count=arg_count)
                return chosen.id if chosen else None
        return None

    def _resolve_self_or_cls_call(
        self,
        site: SymbolCallSite,
        prefix: str,
        callee: str,
        norm_path: str,
        space_name: str,
        arg_count: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        if prefix in ("self", "cls", "base", "super"):
            caller_class = self._get_caller_class_name(site)
            is_base_call = prefix in ("base", "super")
            resolved_id = self._resolve_in_class_or_bases(
                caller_class, callee, norm_path, space_name, bases_only=is_base_call, arg_count=arg_count
            )
            if resolved_id:
                return True, resolved_id

            caller_id = site.caller_symbol_id
            if caller_id and caller_id in self.symbols_map:
                caller_sym = self.symbols_map[caller_id]
                parent_key = caller_sym.parent_id or caller_id
                sib_matches = [
                    s
                    for s in self._by_parent_id.get(parent_key, [])
                    if s.name == callee or s.name.endswith(f".{callee}")
                ]
                if sib_matches:
                    chosen = self._select_best_overload(sib_matches, arg_count=arg_count)
                    return True, chosen.id if chosen else None
            return True, None

        if not prefix:
            caller_class = self._get_caller_class_name(site)
            if caller_class:
                resolved_id = self._resolve_in_class_or_bases(
                    caller_class, callee, norm_path, space_name, arg_count=arg_count
                )
                if resolved_id:
                    return True, resolved_id

            local_matches = self._by_file_name.get((norm_path, callee), [])
            if local_matches:
                if len(local_matches) == 1:
                    m = local_matches[0]
                    m_parent = m.metadata.get("parent_scope") or ""
                    if not m_parent or m_parent == caller_class or m.kind in ("function", "class", "struct", "interface"):
                        return True, m.id
                else:
                    filtered = [
                        m
                        for m in local_matches
                        if m.kind in ("function", "class", "struct", "interface")
                        or (caller_class and m.metadata.get("parent_scope") == caller_class)
                    ]
                    if filtered:
                        chosen = self._select_best_overload(filtered, arg_count=arg_count)
                        return True, chosen.id if chosen else None

        return False, None

    def _resolve_imported_module_call(
        self,
        prefix: str,
        callee: str,
        imports: Dict[str, str],
        arg_count: Optional[int] = None,
    ) -> Optional[str]:
        if prefix and prefix in imports:
            imported_target = imports[prefix]
            target_class = imported_target.split(".")[-1]
            target_fqn = f"{imported_target.lower()}.{callee.lower()}"
            if target_fqn in self._by_fqn and self._by_fqn[target_fqn]:
                chosen = self._select_best_overload(self._by_fqn[target_fqn], arg_count=arg_count)
                if chosen:
                    return chosen.id

            matches = self._by_name.get(f"{target_class}.{callee}", [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target, arg_count=arg_count)
                if best:
                    return best.id

        if not prefix and callee in imports:
            imported_target = imports[callee]
            imp_low = imported_target.lower()
            if imp_low in self._by_fqn and self._by_fqn[imp_low]:
                chosen = self._select_best_overload(self._by_fqn[imp_low], arg_count=arg_count)
                if chosen:
                    return chosen.id

            target_short = imported_target.split(".")[-1]
            matches = self._by_name.get(target_short, [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target, arg_count=arg_count)
                if best:
                    return best.id
        return None

    def _resolve_field_type(self, class_name: str, field_name: str) -> Optional[str]:
        if not class_name or not field_name:
            return None
        for cls_name in [class_name] + self._get_ancestor_classes(class_name):
            fields = self._class_fields.get(cls_name)
            if fields and field_name in fields:
                return fields[field_name]
        return None

    def _resolve_same_file_or_global_call(
        self,
        site: SymbolCallSite,
        prefix: str,
        callee: str,
        norm_path: str,
        space_name: str,
        imports: Dict[str, str],
        arg_count: Optional[int] = None,
    ) -> Optional[str]:
        prefix_tail = prefix.split(".")[-1] if "." in prefix else prefix
        caller_class = self._get_caller_class_name(site)

        if prefix and caller_class:
            field_type = self._resolve_field_type(caller_class, prefix_tail)
            if field_type:
                resolved_field_id = self._resolve_in_class_or_bases(
                    field_type, callee, norm_path, space_name, arg_count=arg_count
                )
                if resolved_field_id:
                    return resolved_field_id

        if space_name and space_name in self._by_space_name:
            if prefix:
                space_matches = list(self._by_space_name[space_name].get(f"{prefix}.{callee}", []))
                if not space_matches and prefix_tail != prefix:
                    space_matches = list(self._by_space_name[space_name].get(f"{prefix_tail}.{callee}", []))
                if space_matches:
                    if len(space_matches) == 1:
                        return space_matches[0].id
                    best = self._score_candidates(space_matches, prefix, callee, arg_count=arg_count)
                    if best:
                        return best.id
                else:
                    local_candidates = [
                        c
                        for c in self._by_file_name.get((norm_path, callee), [])
                        if not caller_class or (c.metadata.get("parent_scope") or "").lower() != caller_class.lower()
                    ]
                    if len(local_candidates) == 1:
                        return local_candidates[0].id

                    candidates = list(self._by_space_name[space_name].get(callee, []))
                    if imports:
                        imported_classes = {target.split(".")[-1].lower() for target in imports.values()}
                        imported_matches = [
                            c
                            for c in candidates
                            if any(cls in c.name.lower() or (c.fqn and cls in c.fqn.lower()) for cls in imported_classes)
                        ]
                        if len(imported_matches) == 1:
                            return imported_matches[0].id
                        elif len(imported_matches) > 1:
                            best = self._score_candidates(imported_matches, prefix, callee, arg_count=arg_count)
                            if best:
                                return best.id

                    if len(candidates) == 1:
                        c = candidates[0]
                        c_path = c.file_path.replace("\\", "/").lower()
                        c_parent = (c.metadata.get("parent_scope") or "").lower()
                        if c_path == norm_path and (not caller_class or c_parent != caller_class.lower()):
                            return c.id
                        best = self._score_candidates(candidates, prefix, callee, arg_count=arg_count)
                        if best:
                            return best.id
                    elif len(candidates) > 1:
                        best = self._score_candidates(
                            candidates, prefix, callee, caller_class=caller_class, norm_path=norm_path, arg_count=arg_count
                        )
                        if best:
                            return best.id

        if not prefix:
            return None

        global_matches = list(self._by_name.get(f"{prefix}.{callee}", []))
        if not global_matches and prefix_tail != prefix:
            global_matches = list(self._by_name.get(f"{prefix_tail}.{callee}", []))
        if global_matches:
            if len(global_matches) == 1:
                return global_matches[0].id
            best = self._score_candidates(global_matches, prefix, callee, arg_count=arg_count)
            if best:
                return best.id
        else:
            candidates = list(self._by_name.get(callee, []))
            if imports:
                imported_classes = {target.split(".")[-1].lower() for target in imports.values()}
                imported_matches = [
                    c
                    for c in candidates
                    if any(cls in c.name.lower() or (c.fqn and cls in c.fqn.lower()) for cls in imported_classes)
                ]
                if len(imported_matches) == 1:
                    return imported_matches[0].id
                elif len(imported_matches) > 1:
                    best = self._score_candidates(imported_matches, prefix, callee, arg_count=arg_count)
                    if best:
                        return best.id

            if len(candidates) == 1:
                c = candidates[0]
                c_path = c.file_path.replace("\\", "/").lower()
                c_parent = (c.metadata.get("parent_scope") or "").lower()
                if c_path == norm_path and (not caller_class or c_parent != caller_class.lower()):
                    return c.id
                best = self._score_candidates(candidates, prefix, callee, arg_count=arg_count)
                if best:
                    return best.id
            elif len(candidates) > 1:
                best = self._score_candidates(candidates, prefix, callee, arg_count=arg_count)
                if best:
                    return best.id

        return None

    def get_overloads_by_fqn(self, fqn: str) -> List[UnifiedSymbol]:
        """Return all method/symbol overloads matching `fqn` (case-insensitive or exact)."""
        if not fqn:
            return []
        norm = fqn.strip()
        if norm in self._by_fqn and self._by_fqn[norm]:
            return list(self._by_fqn[norm])
        low = norm.lower()
        if low in self._by_fqn and self._by_fqn[low]:
            return list(self._by_fqn[low])
        return []

    def resolve_call_site(
        self,
        site: SymbolCallSite,
        file_imports: Optional[Dict[str, str]] = None,
        arg_count: Optional[int] = None,
    ) -> Optional[str]:
        """Resolve `site` using the 4-tier disambiguation cascade and return target `callee_symbol_id`."""
        norm_raw = site.file_path.replace("\\", "/")
        imports = file_imports or self.file_imports.get(norm_raw, self.file_imports.get(site.file_path, {}))
        norm_path = norm_raw.lower()
        callee = site.callee_name
        prefix = site.context_prefix.strip()
        space_name = site.space

        if "(" in callee and arg_count is None:
            arg_count = _extract_param_count_from_signature(callee)
            callee = callee.split("(", 1)[0].strip()

        handled, tier1_id = self._resolve_self_or_cls_call(
            site, prefix, callee, norm_path, space_name, arg_count=arg_count
        )
        if handled:
            return tier1_id

        tier2_id = self._resolve_imported_module_call(prefix, callee, imports, arg_count=arg_count)
        if tier2_id:
            return tier2_id

        return self._resolve_same_file_or_global_call(
            site, prefix, callee, norm_path, space_name, imports, arg_count=arg_count
        )

    def _pick_best_by_import_path(
        self,
        matches: List[UnifiedSymbol],
        imported_path: str,
        arg_count: Optional[int] = None,
    ) -> Optional[UnifiedSymbol]:
        imp_parts = imported_path.replace(".", "/").lower().split("/")
        filtered: List[UnifiedSymbol] = []
        for m in matches:
            m_path = m.file_path.replace("\\", "/").lower()
            if any(part in m_path for part in imp_parts if len(part) > 2):
                filtered.append(m)
            elif m.fqn and imported_path.lower() in m.fqn.lower():
                filtered.append(m)
        pool = filtered if filtered else matches
        return self._select_best_overload(pool, arg_count=arg_count)

    def _score_candidates(
        self,
        candidates: List[UnifiedSymbol],
        prefix: str,
        callee: str,
        caller_class: str = "",
        norm_path: str = "",
        arg_count: Optional[int] = None,
    ) -> Optional[UnifiedSymbol]:
        if not candidates:
            return None

        prefix_clean = prefix.lower()
        prefix_tail = prefix_clean.split(".")[-1] if "." in prefix_clean else prefix_clean
        caller_cls_low = caller_class.lower() if caller_class else ""
        scored: List[Tuple[float, UnifiedSymbol]] = []

        for sym in candidates:
            score = 0.0
            sym_kind = sym.kind.value if isinstance(sym.kind, SymbolKind) else str(sym.kind)
            parent_cls = (sym.metadata.get("parent_scope") or "").lower()
            name_parts = [p.lower() for p in re.split(r"[.:]+", sym.name)[:-1]]
            if parent_cls and parent_cls not in name_parts:
                name_parts.append(parent_cls)

            if sym_kind in ("method", "constructor", "property") or name_parts:
                for cls_part in name_parts:
                    if not cls_part:
                        continue
                    if prefix_tail == cls_part or prefix_clean == cls_part:
                        score += 15.0
                    elif len(prefix_tail) >= 3 and len(cls_part) >= 3 and (
                        cls_part in prefix_clean
                        or prefix_tail in cls_part
                        or any(len(seg) >= 3 and seg in cls_part for seg in prefix_tail.split("_"))
                    ):
                        score += 10.0

                if not prefix_clean and caller_cls_low and parent_cls == caller_cls_low:
                    score += 8.0
                if norm_path and sym.file_path.replace("\\", "/").lower() == norm_path:
                    if not prefix_clean or not caller_cls_low or parent_cls != caller_cls_low:
                        score += 5.0
            elif sym_kind == SymbolKind.FUNCTION.value and not prefix_clean:
                score += 5.0

            if arg_count is not None and _extract_param_count_from_signature(sym.signature) == arg_count:
                score += 4.0

            scored.append((score, sym))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] > 0.0 else None

    def link_call_sites(
        self,
        call_sites: List[SymbolCallSite],
        imports_map: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[Tuple[str, str, SymbolCallSite]]:
        """Resolve a batch of `SymbolCallSite` instances and return `[(caller_id, callee_id, bound_site), ...]`."""
        all_imports = imports_map or {}
        edges: List[Tuple[str, str, SymbolCallSite]] = []

        for site in call_sites:
            norm_path = site.file_path.replace("\\", "/")
            file_imports = all_imports.get(norm_path, all_imports.get(site.file_path, {}))

            caller_id = site.caller_symbol_id or self.find_caller_symbol_id(site.file_path, site.caller_member_name)
            if not caller_id:
                continue

            callee_id = self.resolve_call_site(site, file_imports)
            if not callee_id:
                continue

            if caller_id == callee_id:
                caller_sym = self.symbols_map.get(caller_id)
                caller_kind = (
                    caller_sym.kind.value
                    if caller_sym and isinstance(caller_sym.kind, SymbolKind)
                    else (str(caller_sym.kind) if caller_sym else "")
                )
                if caller_kind not in ("function", "method", "constructor"):
                    continue

            bound_site = SymbolCallSite(
                callee_name=site.callee_name,
                line_number=site.line_number,
                caller_symbol_id=caller_id,
                caller_member_name=site.caller_member_name,
                context_prefix=site.context_prefix,
                file_path=site.file_path,
                space=site.space,
            )
            edges.append((caller_id, callee_id, bound_site))

        return edges

    def build_graph(
        self,
        call_sites: Optional[List[SymbolCallSite]] = None,
        imports_map: Optional[Dict[str, Dict[str, str]]] = None,
        graph: Optional[CallGraphIndex] = None,
    ) -> CallGraphIndex:
        """Build a `CallGraphIndex` from `call_sites` and `imports_map`."""
        if graph is None:
            graph = CallGraphIndex()
        if call_sites:
            for caller_id, callee_id, site in self.link_call_sites(call_sites, imports_map):
                graph.add_edge(caller_id, callee_id, site)
        return graph


def expand_contract_symbol_ids(
    symbols_map: Union[Dict[str, UnifiedSymbol], Any],
    target_sym: Union[UnifiedSymbol, List[UnifiedSymbol]],
) -> List[str]:
    """
    Bidirectional interface/base-class and derived-class method contract expansion.
    Accepts either a `Dict[str, UnifiedSymbol]` (or an object with `.symbols` dict) and
    either a single `UnifiedSymbol` or a `List[UnifiedSymbol]` (such as an overload group).
    """
    if hasattr(symbols_map, "symbols") and isinstance(symbols_map.symbols, dict):
        sym_dict: Dict[str, UnifiedSymbol] = symbols_map.symbols
    elif isinstance(symbols_map, dict):
        sym_dict = symbols_map
    else:
        return []

    targets = [target_sym] if isinstance(target_sym, UnifiedSymbol) else list(target_sym)
    if not targets:
        return []

    result_ids: List[str] = []
    seen_ids: Set[str] = set()

    def _add(sid: str) -> None:
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            result_ids.append(sid)

    for t in targets:
        _add(t.id)

    class_bases: Dict[str, Set[str]] = defaultdict(set)
    base_derived: Dict[str, Set[str]] = defaultdict(set)
    for sym in sym_dict.values():
        if not sym.metadata:
            continue
        b_types = sym.metadata.get("base_types")
        if b_types and isinstance(b_types, (list, tuple)):
            cls_short = sym.metadata.get("short_name") or re.split(r"[.:]+", sym.name)[-1]
            for bt in b_types:
                if bt:
                    class_bases[cls_short].add(str(bt))
                    base_derived[str(bt)].add(cls_short)

    for t in targets:
        kind_str = t.kind.value if hasattr(t.kind, "value") else str(t.kind)
        if kind_str not in ("method", "function", "property"):
            continue

        parent_cls = (t.metadata.get("parent_scope") or "") if t.metadata else ""
        if not parent_cls and ("." in t.name or "::" in t.name):
            parent_cls = re.split(r"[.:]+", t.name)[-2]
        short_name = (
            (t.metadata.get("short_name") if t.metadata else None)
            or (re.split(r"[.:]+", t.name)[-1] if ("." in t.name or "::" in t.name) else t.name)
        )
        if not parent_cls or not short_name:
            continue

        related_classes: Set[str] = {parent_cls}
        up_queue = list(class_bases.get(parent_cls, []))
        while up_queue:
            curr = up_queue.pop(0)
            if curr not in related_classes:
                related_classes.add(curr)
                up_queue.extend(class_bases.get(curr, []))

        down_queue = list(base_derived.get(parent_cls, []))
        while down_queue:
            curr = down_queue.pop(0)
            if curr not in related_classes:
                related_classes.add(curr)
                down_queue.extend(base_derived.get(curr, []))

        if len(related_classes) <= 1:
            continue

        for sym in sym_dict.values():
            if sym.id in seen_ids or not sym.metadata:
                continue
            s_parent = sym.metadata.get("parent_scope") or ""
            s_short = sym.metadata.get("short_name") or re.split(r"[.:]+", sym.name)[-1]
            if s_short == short_name and s_parent in related_classes:
                _add(sym.id)

    return result_ids


__all__ = [
    "TopologyLinker",
    "expand_contract_symbol_ids",
]
