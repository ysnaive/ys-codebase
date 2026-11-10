"""
Cross-File Call Topology Linker (`TopologyLinker`) and Polymorphic Contract Expander (`expand_contract_symbol_ids`).
- `_by_fqn: Dict[str, List[UnifiedSymbol]]` preserves all method overloads sharing the same FQN
  instead of overwriting earlier overloads.
- Supports parameter-count matching when resolving overloaded call sites and links overload groups cleanly.
"""

from collections import defaultdict, deque
import posixpath
import re
import threading
from types import MappingProxyType
from typing import Any, Callable, Deque, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple, Union

from core.context import check_task_cancelled, get_runtime_context
from core.log import log_warn

from .graph import CallGraphIndex
from .parsers.base import EdgeRefiner, ModulePathResolver, is_partial_declaration
from .schema import (
    FileImportBinding,
    FileImportTable,
    FileSymbolGraph,
    LanguageConfig,
    ProvenanceStep,
    RelationEdge,
    SymbolCallSite,
    SymbolKind,
    SymbolNode,
    UnifiedSymbol,
    WorkspaceSymbolGraph,
)

_LINKER_CACHE_LOCK = threading.RLock()


def _create_default_linker_cache() -> Dict[str, Any]:
    return {
        "symbols_map_id": None,
        "symbols_count": 0,
        "symbols_fingerprint": 0,
        "class_bases": None,
        "base_derived": None,
        "methods_by_class_and_short": None,
    }


def _get_last_linker_cache() -> Dict[str, Any]:
    return get_runtime_context().get_module_state("ast.linker.last_cache", _create_default_linker_cache)


def get_last_linker_cache() -> Dict[str, Any]:
    """Return the active linker cache dictionary in the current runtime context."""
    return _get_last_linker_cache()


def reset_linker_cache() -> None:
    """Reset the active linker cache dictionary in the current runtime context."""
    cache = _get_last_linker_cache()
    with _LINKER_CACHE_LOCK:
        cache.clear()
        cache.update(_create_default_linker_cache())


def _compute_symbols_map_fingerprint(symbols_map: Dict[str, UnifiedSymbol]) -> int:
    """Compute a lightweight structural fingerprint of `symbols_map` so in-place hot-patches invalidate cache."""
    acc = len(symbols_map)
    for sid, sym in symbols_map.items():
        acc ^= hash((sid, id(sym), getattr(sym, "signature", ""), getattr(sym, "line_number", getattr(sym, "start_line", 0))))
    return acc


def _extract_param_count_from_signature(signature: str) -> Optional[int]:
    """Extract parameter count from a declaration signature `(...)`."""
    if not signature or "(" not in signature or ")" not in signature:
        return None
    from .resolver import extract_signature_params

    start = signature.find("(")
    depth = 0
    end = -1
    for idx in range(start, len(signature)):
        ch = signature[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = idx
                break
    if end <= start:
        return None
    return len(extract_signature_params(signature))


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
        self._by_short_name: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_module_suffix: Dict[str, Set[str]] = defaultdict(set)
        self._by_space_name: Dict[str, Dict[str, List[UnifiedSymbol]]] = defaultdict(lambda: defaultdict(list))
        self._by_file_name: Dict[Tuple[str, str], List[UnifiedSymbol]] = defaultdict(list)
        self._by_fqn: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_parent_id: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._class_bases: Dict[str, Set[str]] = defaultdict(set)
        self._base_derived: Dict[str, Set[str]] = defaultdict(set)
        self._methods_by_class_and_short: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        self._class_fields: Dict[str, Dict[str, str]] = defaultdict(dict)

        self._reindex()

    def _reindex(self) -> None:
        self._by_file.clear()
        self._by_name.clear()
        self._by_short_name.clear()
        self._by_module_suffix.clear()
        self._by_space_name.clear()
        self._by_file_name.clear()
        self._by_fqn.clear()
        self._by_parent_id.clear()
        self._class_bases.clear()
        self._base_derived.clear()
        self._methods_by_class_and_short.clear()
        self._class_fields.clear()

        seen_fqn_ids: Dict[str, Set[str]] = defaultdict(set)

        for _, sym in self.symbols_map.items():
            norm_path = sym.file_path.replace("\\", "/").lower()
            self._by_file[norm_path].append(sym)
            self._by_name[sym.name].append(sym)
            self._by_file_name[(norm_path, sym.name)].append(sym)

            path_no_ext = norm_path.rsplit(".", 1)[0] if "." in norm_path else norm_path
            for seg in path_no_ext.split("/"):
                if len(seg) > 2:
                    self._by_module_suffix[seg].add(sym.id)

            if sym.fqn:
                fqn_low = sym.fqn.lower()
                if sym.id not in seen_fqn_ids[fqn_low]:
                    seen_fqn_ids[fqn_low].add(sym.id)
                    self._by_fqn[fqn_low].append(sym)
                if sym.fqn != fqn_low and sym.id not in seen_fqn_ids[sym.fqn]:
                    seen_fqn_ids[sym.fqn].add(sym.id)
                    self._by_fqn[sym.fqn].append(sym)
                for fqn_seg in re.split(r"[.:]+", fqn_low):
                    if len(fqn_seg) > 2:
                        self._by_module_suffix[fqn_seg].add(sym.id)

            if sym.parent_id:
                self._by_parent_id[sym.parent_id].append(sym)

            short_name = sym.metadata.get("short_name") or (
                re.split(r"[.:]+", sym.name)[-1] if ("." in sym.name or "::" in sym.name) else sym.name
            )
            if short_name:
                self._by_short_name[str(short_name).lower()].append(sym)
                self._by_file_name[(norm_path, str(short_name))].append(sym)
            parent_scope = sym.metadata.get("parent_scope") or ""

            if parent_scope and short_name:
                self._methods_by_class_and_short[(str(parent_scope), str(short_name))].append(sym.id)

            base_types = sym.metadata.get("base_types")
            if base_types and isinstance(base_types, (list, tuple)):
                for bt in base_types:
                    if bt:
                        bt_str = str(bt)
                        self._class_bases[short_name].add(bt_str)
                        self._base_derived[bt_str].add(short_name)
                        if "." in bt_str or "::" in bt_str:
                            bt_short = re.split(r"[.:]+", bt_str)[-1].strip()
                            if bt_short:
                                self._class_bases[short_name].add(bt_short)
                                self._base_derived[bt_short].add(short_name)

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

        fp = _compute_symbols_map_fingerprint(self.symbols_map)
        last_cache = _get_last_linker_cache()
        with _LINKER_CACHE_LOCK:
            last_cache["symbols_map_id"] = id(self.symbols_map)
            last_cache["symbols_count"] = len(self.symbols_map)
            last_cache["symbols_fingerprint"] = fp
            last_cache["class_bases"] = self._class_bases
            last_cache["base_derived"] = self._base_derived
            last_cache["methods_by_class_and_short"] = self._methods_by_class_and_short

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
        if caller_member_name and caller_member_name != "<module>":
            direct = self._by_file_name.get((norm_path, caller_member_name))
            if direct:
                return direct[0].id
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
        queue: Deque[str] = deque(self._class_bases.get(class_name, ()))
        while queue:
            curr = queue.popleft()
            if curr not in visited:
                visited.append(curr)
                for nxt in self._class_bases.get(curr, ()):
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
        imp_parts = [p for p in imported_path.replace(".", "/").lower().split("/") if len(p) > 2]
        matched_ids: Set[str] = set()
        for part in imp_parts:
            matched_ids.update(self._by_module_suffix.get(part, ()))
        filtered: List[UnifiedSymbol] = []
        imp_low = imported_path.lower()
        for m in matches:
            if m.id in matched_ids:
                filtered.append(m)
                continue
            m_path = m.file_path.replace("\\", "/").lower()
            if any(part in m_path for part in imp_parts):
                filtered.append(m)
            elif m.fqn and imp_low in m.fqn.lower():
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
        self,
        target_sym: Union[UnifiedSymbol, List[UnifiedSymbol]],
        symbols_map: Optional[Union[Dict[str, UnifiedSymbol], Any]] = None,
    ) -> List[str]:
        """Expand polymorphic contract symbol IDs using pre-indexed inheritance and method maps when possible."""
        return expand_contract_symbol_ids(
            symbols_map=symbols_map if symbols_map is not None else self,
            target_sym=target_sym,
        )


def _expand_contract_from_workspace_graph(
    ws_graph: WorkspaceSymbolGraph,
    target_sym: Union[SymbolNode, UnifiedSymbol, str, Iterable[Union[SymbolNode, UnifiedSymbol, str]]],
) -> List[str]:
    """Expand polymorphic base/derived method contracts using Pass 3 `type_bases_by_id` and `type_derived_by_id`."""
    if isinstance(target_sym, (SymbolNode, UnifiedSymbol, str)):
        raw_targets = [target_sym]
    else:
        raw_targets = list(target_sym)

    target_nodes: List[SymbolNode] = []
    result_ids: List[str] = []
    seen_ids: Set[str] = set()

    def _add_id(sid: str) -> None:
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            result_ids.append(sid)

    for rt in raw_targets:
        if isinstance(rt, SymbolNode):
            _add_id(rt.id)
            target_nodes.append(rt)
        elif isinstance(rt, UnifiedSymbol):
            _add_id(rt.id)
            node = ws_graph.nodes_by_id.get(rt.id)
            if node is None:
                norm_p = rt.file_path.replace("\\", "/")
                cand_id = SymbolNode.compute_canonical_id(norm_p, rt.fqn or rt.name)
                node = ws_graph.nodes_by_id.get(cand_id)
                if node is None:
                    fg = ws_graph.file_graphs.get(norm_p)
                    if fg is not None:
                        target_fqn = rt.fqn or rt.name
                        short_n = (rt.metadata or {}).get("short_name") or rt.name.split(".")[-1]
                        for cand_n in fg.all_nodes_by_id.values():
                            if cand_n.span.start_line == rt.line_number and (
                                cand_n.fqn == target_fqn or cand_n.name == short_n
                            ):
                                node = cand_n
                                break
            if node is not None:
                _add_id(node.id)
                target_nodes.append(node)
        elif isinstance(rt, str):
            _add_id(rt)
            node = ws_graph.nodes_by_id.get(rt)
            if node is not None:
                target_nodes.append(node)

    type_id_by_file_and_scope: Mapping[Tuple[str, Tuple[str, ...]], str] = getattr(
        ws_graph, "_type_id_by_file_and_scope", None
    ) or {}
    members_by_type_id: Mapping[str, Mapping[str, Tuple[str, ...]]] = getattr(
        ws_graph, "_members_by_type_id", None
    ) or {}
    if not type_id_by_file_and_scope and ws_graph.nodes_by_id:
        fallback_scope: Dict[Tuple[str, Tuple[str, ...]], str] = {}
        fallback_members: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        for nid, n in ws_graph.nodes_by_id.items():
            file_p = nid.split("::", 1)[0]
            if n.kinds & {"class", "struct", "interface"}:
                fallback_scope[(file_p, (*n.scope_path, n.name))] = nid
                for ch in n.children:
                    fallback_members[nid][ch.name].append(ch.id)
        type_id_by_file_and_scope = fallback_scope
        members_by_type_id = fallback_members  # type: ignore[assignment]

    for n in target_nodes:
        if n.kinds & {"class", "struct", "interface"}:
            seed_cls: Set[str] = {n.id}
            for grp in ws_graph.folded_symbol_groups.values():
                if n.id in grp:
                    seed_cls.update(grp)
            related_cls: Set[str] = set(seed_cls)
            up_cls: Deque[str] = deque(seed_cls)
            while up_cls:
                curr = up_cls.popleft()
                for base_id in ws_graph.type_bases_by_id.get(curr, ()):
                    if base_id not in related_cls:
                        related_cls.add(base_id)
                        up_cls.append(base_id)
            down_cls: Deque[str] = deque(seed_cls)
            while down_cls:
                curr = down_cls.popleft()
                for der_id in ws_graph.type_derived_by_id.get(curr, ()):
                    if der_id not in related_cls:
                        related_cls.add(der_id)
                        down_cls.append(der_id)
            for r_cid in sorted(related_cls):
                _add_id(r_cid)
            continue
        if not (n.kinds & {"method", "function", "property"}):
            continue
        file_p = n.id.split("::", 1)[0]
        parent_type_id = type_id_by_file_and_scope.get((file_p, n.scope_path))
        if not parent_type_id:
            continue

        # Include folded partial/header siblings of parent_type_id
        seed_types: Set[str] = {parent_type_id}
        for grp in ws_graph.folded_symbol_groups.values():
            if parent_type_id in grp:
                seed_types.update(grp)

        related_type_ids: Set[str] = set(seed_types)
        up_q: Deque[str] = deque(seed_types)
        while up_q:
            curr = up_q.popleft()
            for base_id in ws_graph.type_bases_by_id.get(curr, ()):
                if base_id not in related_type_ids:
                    related_type_ids.add(base_id)
                    up_q.append(base_id)

        down_q: Deque[str] = deque(seed_types)
        while down_q:
            curr = down_q.popleft()
            for der_id in ws_graph.type_derived_by_id.get(curr, ()):
                if der_id not in related_type_ids:
                    related_type_ids.add(der_id)
                    down_q.append(der_id)

        for r_tid in sorted(related_type_ids):
            for m_id in members_by_type_id.get(r_tid, {}).get(n.name, ()):
                _add_id(m_id)

    return result_ids


def expand_contract_symbol_ids(
    symbols_map: Union[Dict[str, UnifiedSymbol], WorkspaceSymbolGraph, Any],
    target_sym: Union[UnifiedSymbol, SymbolNode, str, List[Any]],
    precomputed_fingerprint: Optional[int] = None,
) -> List[str]:
    """
    Bidirectional interface/base-class and derived-class method contract expansion.
    Accepts either a `WorkspaceSymbolGraph`, a `Dict[str, UnifiedSymbol]` (or an object with `.symbols` / `.symbols_map` dict),
    and either a single `SymbolNode`/`UnifiedSymbol` or a list of symbols.
    """
    if isinstance(symbols_map, WorkspaceSymbolGraph):
        return _expand_contract_from_workspace_graph(symbols_map, target_sym)
    if hasattr(symbols_map, "workspace_graph") and isinstance(symbols_map.workspace_graph, WorkspaceSymbolGraph):
        return _expand_contract_from_workspace_graph(symbols_map.workspace_graph, target_sym)

    cached_bases: Optional[Dict[str, Set[str]]] = None
    cached_derived: Optional[Dict[str, Set[str]]] = None
    cached_methods: Optional[Dict[Tuple[str, str], List[str]]] = None

    if isinstance(symbols_map, TopologyLinker):
        sym_dict: Dict[str, UnifiedSymbol] = symbols_map.symbols_map
        cached_bases = symbols_map._class_bases
        cached_derived = symbols_map._base_derived
        cached_methods = symbols_map._methods_by_class_and_short
    elif hasattr(symbols_map, "symbols") and isinstance(symbols_map.symbols, dict):
        sym_dict = symbols_map.symbols
    elif hasattr(symbols_map, "symbols_map") and isinstance(symbols_map.symbols_map, dict):
        sym_dict = symbols_map.symbols_map
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

    current_fp: Optional[int] = precomputed_fingerprint
    last_cache = _get_last_linker_cache()
    if cached_bases is None:
        if current_fp is None:
            current_fp = _compute_symbols_map_fingerprint(sym_dict)
        with _LINKER_CACHE_LOCK:
            if (
                last_cache["symbols_map_id"] == id(sym_dict)
                and last_cache["symbols_count"] == len(sym_dict)
                and last_cache.get("symbols_fingerprint") == current_fp
            ):
                cached_bases = last_cache["class_bases"]
                cached_derived = last_cache["base_derived"]
                cached_methods = last_cache["methods_by_class_and_short"]

    if cached_bases is not None and cached_derived is not None and cached_methods is not None:
        class_bases = cached_bases
        base_derived = cached_derived
        methods_by_class_and_short = cached_methods
    else:
        if current_fp is None:
            current_fp = _compute_symbols_map_fingerprint(sym_dict)
        class_bases = defaultdict(set)
        base_derived = defaultdict(set)
        methods_by_class_and_short = defaultdict(list)
        for sym in sym_dict.values():
            if not sym.metadata:
                continue
            s_short = sym.metadata.get("short_name") or (
                re.split(r"[.:]+", sym.name)[-1] if ("." in sym.name or "::" in sym.name) else sym.name
            )
            s_parent = sym.metadata.get("parent_scope") or ""
            if s_parent and s_short:
                methods_by_class_and_short[(str(s_parent), str(s_short))].append(sym.id)
            b_types = sym.metadata.get("base_types")
            if b_types and isinstance(b_types, (list, tuple)):
                for bt in b_types:
                    if bt:
                        bt_str = str(bt)
                        class_bases[s_short].add(bt_str)
                        base_derived[bt_str].add(s_short)
                        if "." in bt_str or "::" in bt_str:
                            bt_short = re.split(r"[.:]+", bt_str)[-1].strip()
                            if bt_short:
                                class_bases[s_short].add(bt_short)
                                base_derived[bt_short].add(s_short)
        with _LINKER_CACHE_LOCK:
            last_cache["symbols_map_id"] = id(sym_dict)
            last_cache["symbols_count"] = len(sym_dict)
            last_cache["symbols_fingerprint"] = current_fp
            last_cache["class_bases"] = class_bases
            last_cache["base_derived"] = base_derived
            last_cache["methods_by_class_and_short"] = methods_by_class_and_short

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
        up_queue: Deque[str] = deque(class_bases.get(parent_cls, ()))
        while up_queue:
            curr = up_queue.popleft()
            if curr not in related_classes:
                related_classes.add(curr)
                up_queue.extend(class_bases.get(curr, ()))

        down_queue: Deque[str] = deque(base_derived.get(parent_cls, ()))
        while down_queue:
            curr = down_queue.popleft()
            if curr not in related_classes:
                related_classes.add(curr)
                down_queue.extend(base_derived.get(curr, ()))

        if len(related_classes) <= 1:
            continue

        for r_cls in related_classes:
            for sid in methods_by_class_and_short.get((r_cls, short_name), ()):
                _add(sid)

    return result_ids


def _match_symbol_ids_in_file(
    file_nodes: Tuple[SymbolNode, ...],
    symbol_expr: str,
) -> Tuple[str, ...]:
    """Find all `SymbolNode.id` in `file_nodes` matching `symbol_expr` by FQN or short name."""
    if not symbol_expr or not file_nodes:
        return ()
    target = symbol_expr.strip()
    exact_fqn_ids: List[str] = []
    short_ids: List[str] = []
    for n in file_nodes:
        if n.fqn == target:
            exact_fqn_ids.append(n.id)
        if n.name == target:
            short_ids.append(n.id)
    if exact_fqn_ids:
        return tuple(sorted(set(exact_fqn_ids)))
    return tuple(sorted(set(short_ids)))


class DefaultModulePathResolver(ModulePathResolver):
    """
    Built-in multi-language `ModulePathResolver` supporting:
    - Python relative dots (`.utils`, `..pkg.mod`) and package `__init__.py`
    - TypeScript / JavaScript relative paths (`./utils`, `../lib`) and `index.ts` / `index.js`
    - C / C++ `#include "dir/header.h"` suffix resolution
    - C# `using Namespace.Sub` namespace resolution
    - Markdown relative file links and `#anchor` symbol resolution
    """

    provider_id: str = "ast:builtin_module_resolver"

    def resolve_import(
        self,
        importing_file: str,
        target_expr: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]:
        if not target_expr:
            return None, (), True
        expr = target_expr.strip()
        if expr.endswith(".*"):
            expr = expr[:-2].strip()

        norm_importing = importing_file.replace("\\", "/")
        imp_dir = posixpath.dirname(norm_importing)

        # 1. Markdown or URI link with optional `#anchor` (`../engine.py#ASTEngine`)
        if "#" in expr or expr.endswith((".md", ".py", ".ts", ".tsx", ".js", ".cs", ".h", ".hpp", ".c", ".cpp")):
            path_part, anchor = expr.split("#", 1) if "#" in expr else (expr, "")
            cand_rel = posixpath.normpath(posixpath.join(imp_dir, path_part)) if path_part.startswith(".") else path_part.lstrip("/")
            matched_file: Optional[str] = None
            if cand_rel in workspace_files:
                matched_file = cand_rel
            else:
                for wf in sorted(workspace_files):
                    if wf == path_part or wf.endswith(f"/{path_part}") or wf.endswith(f"/{cand_rel}"):
                        matched_file = wf
                        break
            if matched_file is not None:
                sids = _match_symbol_ids_in_file(nodes_by_file.get(matched_file, ()), anchor) if anchor else ()
                return matched_file, sids, False
            return None, (), True

        # 2. Relative path or Python leading-dot import (`.foo`, `..bar.Baz`, `./foo`, `../bar`)
        if expr.startswith("."):
            if expr.startswith(("./", "../")):
                rel_target = posixpath.normpath(posixpath.join(imp_dir, expr))
                return self._resolve_rel_path_or_symbol(rel_target, workspace_files, nodes_by_file)

            # Python leading dots: `.` = current dir, `..` = parent dir
            dot_count = len(expr) - len(expr.lstrip("."))
            rem = expr[dot_count:].strip()
            base_dir = imp_dir
            for _ in range(max(0, dot_count - 1)):
                base_dir = posixpath.dirname(base_dir)
            rel_mod_path = rem.replace(".", "/") if rem else ""
            joined = posixpath.normpath(posixpath.join(base_dir, rel_mod_path)) if rel_mod_path else base_dir
            return self._resolve_rel_path_or_symbol(joined, workspace_files, nodes_by_file)

        # 3. Dotted module/symbol expression (`pkg.mod.ClassName` or `pkg.mod`)
        return self._resolve_dotted_expr(expr, norm_importing, workspace_files, nodes_by_file)

    @staticmethod
    def _probe_module_file(mod_slash: str, workspace_files: FrozenSet[str]) -> Optional[str]:
        """Match a slash-separated module path against `workspace_files`."""
        if not mod_slash or mod_slash == ".":
            return None
        exts = (".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".cs", ".h", ".hpp", ".cpp", ".c", ".md")
        candidates: List[str] = [mod_slash]
        for ext in exts:
            candidates.append(f"{mod_slash}{ext}")
        candidates.append(f"{mod_slash}/__init__.py")
        candidates.append(f"{mod_slash}/index.ts")
        candidates.append(f"{mod_slash}/index.tsx")
        candidates.append(f"{mod_slash}/index.js")

        for cand in candidates:
            if cand in workspace_files:
                return cand
        for cand in candidates:
            suffix = f"/{cand}"
            matches = [wf for wf in workspace_files if wf.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
            if matches:
                return sorted(matches, key=lambda x: (len(x), x))[0]
        return None

    def _resolve_rel_path_or_symbol(
        self,
        rel_slash: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]:
        direct_file = self._probe_module_file(rel_slash, workspace_files)
        if direct_file is not None:
            return direct_file, (), False
        if "/" in rel_slash:
            parent_slash, sym_name = rel_slash.rsplit("/", 1)
            mod_file = self._probe_module_file(parent_slash, workspace_files)
            if mod_file is not None:
                sids = _match_symbol_ids_in_file(nodes_by_file.get(mod_file, ()), sym_name)
                return mod_file, sids, False
        return None, (), False

    def _resolve_dotted_expr(
        self,
        expr: str,
        importing_file: str,
        workspace_files: FrozenSet[str],
        nodes_by_file: Mapping[str, Tuple[SymbolNode, ...]],
    ) -> Tuple[Optional[str], Tuple[str, ...], bool]:
        norm_expr = expr.replace("::", ".")
        slash_full = norm_expr.replace(".", "/")
        imp_dir = posixpath.dirname(importing_file)

        # Try relative to importing file directory first (for same-package imports), then workspace root
        for prefix_dir in ([imp_dir, ""] if imp_dir else [""]):
            cand_slash = posixpath.normpath(posixpath.join(prefix_dir, slash_full)) if prefix_dir else slash_full
            mod_file = self._probe_module_file(cand_slash, workspace_files)
            if mod_file is not None:
                return mod_file, (), False

            if "." in norm_expr:
                mod_part, sym_part = norm_expr.rsplit(".", 1)
                mod_cand = (
                    posixpath.normpath(posixpath.join(prefix_dir, mod_part.replace(".", "/")))
                    if prefix_dir
                    else mod_part.replace(".", "/")
                )
                mod_file = self._probe_module_file(mod_cand, workspace_files)
                if mod_file is not None:
                    sids = _match_symbol_ids_in_file(nodes_by_file.get(mod_file, ()), sym_part)
                    return mod_file, sids, False

        # C# / C++ namespace import fallback: check if any workspace symbol has scope_path matching `norm_expr`
        ns_parts = tuple(p for p in norm_expr.split(".") if p)
        ns_matched_ids: List[str] = []
        ns_files: Set[str] = set()
        for wf, f_nodes in nodes_by_file.items():
            for n in f_nodes:
                if n.scope_path == ns_parts or n.fqn == norm_expr or n.fqn == expr:
                    ns_matched_ids.append(n.id)
                    ns_files.add(wf)
        if ns_matched_ids:
            single_f = sorted(ns_files)[0] if len(ns_files) == 1 else None
            return single_f, tuple(sorted(set(ns_matched_ids))), False

        return None, (), True


class WorkspaceGraphLinker:
    """
    4-Pass Deterministic Cross-File Symbol Linker (`WorkspaceGraphLinker`).
    Assembles single-file `FileSymbolGraph` instances into an immutable `WorkspaceSymbolGraph`
    with zero heuristic fuzzy scoring and full provenance tracking.
    """

    def __init__(
        self,
        file_graphs: Iterable[FileSymbolGraph],
        language_configs: Optional[Mapping[str, LanguageConfig]] = None,
        module_resolvers: Optional[Mapping[str, ModulePathResolver]] = None,
        edge_refiners: Optional[Mapping[str, Tuple[EdgeRefiner, ...]]] = None,
    ) -> None:
        sorted_fgs = sorted(
            (fg for fg in file_graphs if isinstance(fg, FileSymbolGraph)),
            key=lambda g: g.file_path.replace("\\", "/"),
        )
        self._file_graphs: Dict[str, FileSymbolGraph] = {
            fg.file_path.replace("\\", "/"): fg for fg in sorted_fgs
        }
        self._language_configs: Dict[str, LanguageConfig] = dict(language_configs or {})
        self._module_resolvers: Dict[str, ModulePathResolver] = dict(module_resolvers or {})
        self._edge_refiners: Dict[str, Tuple[EdgeRefiner, ...]] = dict(edge_refiners or {})
        self._default_resolver = DefaultModulePathResolver()

        # Pass 1 state
        self._nodes_by_id: Dict[str, SymbolNode] = {}
        self._nodes_by_file: Dict[str, Tuple[SymbolNode, ...]] = {}
        self._by_fqn: Dict[str, List[SymbolNode]] = defaultdict(list)
        self._by_short_name: Dict[str, List[SymbolNode]] = defaultdict(list)
        self._by_file_and_fqn: Dict[Tuple[str, str], List[SymbolNode]] = defaultdict(list)
        self._by_file_and_short: Dict[Tuple[str, str], List[SymbolNode]] = defaultdict(list)
        self._folded_groups: Dict[str, Tuple[str, ...]] = {}
        self._node_to_fold_group: Dict[str, Tuple[str, ...]] = {}
        self._synthetic_edges: List[RelationEdge] = []

        # Pass 2 state
        self._file_import_tables: Dict[str, FileImportTable] = {}
        self._resolved_import_edges: Dict[Tuple[str, int, str], RelationEdge] = {}

        # Pass 3 state
        self._type_bases_by_id: Dict[str, Tuple[str, ...]] = {}
        self._type_derived_by_id: Dict[str, Tuple[str, ...]] = {}
        self._field_types_by_class_id: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._resolved_type_edges: Dict[Tuple[str, int, str], RelationEdge] = {}

    def _get_self_aliases(self, lang: str) -> FrozenSet[str]:
        cfg = self._language_configs.get(lang)
        if cfg and "self_aliases" in cfg.receiver_aliases:
            return frozenset(cfg.receiver_aliases["self_aliases"]) | {"self"}
        defaults = {
            "python": frozenset({"self", "cls"}),
            "c_sharp": frozenset({"this", "self"}),
            "csharp": frozenset({"this", "self"}),
            "cpp": frozenset({"this", "self"}),
            "javascript": frozenset({"this", "self"}),
            "typescript": frozenset({"this", "self"}),
        }
        return defaults.get(lang, frozenset({"self", "this", "cls"}))

    def _get_super_aliases(self, lang: str) -> FrozenSet[str]:
        cfg = self._language_configs.get(lang)
        if cfg and "super_aliases" in cfg.receiver_aliases:
            return frozenset(cfg.receiver_aliases["super_aliases"]) | {"base"}
        defaults = {
            "python": frozenset({"super", "base"}),
            "c_sharp": frozenset({"base"}),
            "csharp": frozenset({"base"}),
            "cpp": frozenset({"__super", "base"}),
            "javascript": frozenset({"super", "base"}),
            "typescript": frozenset({"super", "base"}),
        }
        return defaults.get(lang, frozenset({"super", "base"}))

    def _run_pass1_global_indexing_and_folding(self) -> None:
        """Pass 1: Index all workspace `SymbolNode` instances and build cross-file symbol folding edges."""
        type_container_kinds = ("class", "struct", "interface")
        partial_candidates: Dict[Tuple[str, str, str], List[SymbolNode]] = defaultdict(list)
        header_stem_buckets: Dict[Tuple[str, str], List[SymbolNode]] = defaultdict(list)
        impl_stem_buckets: Dict[Tuple[str, str], List[SymbolNode]] = defaultdict(list)

        for norm_path, fg in self._file_graphs.items():
            ordered_nodes = tuple(
                sorted(fg.all_nodes_by_id.values(), key=lambda n: (n.span.start_byte, n.id))
            )
            self._nodes_by_file[norm_path] = ordered_nodes
            ext = posixpath.splitext(norm_path)[1].lower()
            stem = posixpath.splitext(posixpath.basename(norm_path))[0].lower()

            for node in ordered_nodes:
                self._nodes_by_id[node.id] = node
                self._by_fqn[node.fqn].append(node)
                self._by_short_name[node.name].append(node)
                self._by_file_and_fqn[(norm_path, node.fqn)].append(node)
                self._by_file_and_short[(norm_path, node.name)].append(node)

                t_kind = next((k for k in type_container_kinds if k in node.kinds), None)
                if t_kind is not None:
                    norm_lang = "c_sharp" if node.language in ("c_sharp", "csharp") else node.language
                    if norm_lang == "c_sharp" or is_partial_declaration(node.kinds, "", node.facets):
                        partial_candidates[(norm_lang, t_kind, node.fqn)].append(node)

                if node.language in ("c", "cpp", "typescript"):
                    if ext in (".h", ".hpp", ".hxx", ".hh") or norm_path.endswith(".d.ts"):
                        header_stem_buckets[(stem, node.fqn)].append(node)
                    elif ext in (".c", ".cpp", ".cxx", ".cc", ".ts", ".tsx"):
                        impl_stem_buckets[(stem, node.fqn)].append(node)

        pass1_prov = ProvenanceStep(
            provider_id="ast:WorkspaceGraphLinker",
            action="link",
            rule_or_hook="Pass1:SymbolFolding",
        )

        # 1. Partial class/struct/interface folding (`merges_with`) with same-group contagion and kind isolation
        for (lang, t_kind, fqn), p_nodes in sorted(partial_candidates.items()):
            if len(p_nodes) <= 1 or not any(is_partial_declaration(n.kinds, "", n.facets) for n in p_nodes):
                continue
            unique_ids = tuple(sorted({n.id for n in p_nodes}))
            if len(unique_ids) > 1:
                base_grp_key = f"{lang}::{fqn}"
                grp_key = base_grp_key if base_grp_key not in self._folded_groups else f"{lang}::{t_kind}::{fqn}"
                self._folded_groups[grp_key] = unique_ids
                for uid in unique_ids:
                    self._node_to_fold_group[uid] = unique_ids
                    other_ids = tuple(oid for oid in unique_ids if oid != uid)
                    src_node = self._nodes_by_id[uid]
                    self._synthetic_edges.append(
                        RelationEdge(
                            source_id=uid,
                            target_expr=fqn,
                            edge_kind="merges_with",
                            span=src_node.span,
                            resolution_status="resolved",
                            resolved_target_ids=other_ids,
                            provenance=(*src_node.provenance, pass1_prov),
                        )
                    )

        # 2. Header / Implementation pairing (`declares` / `merges_with`)
        for (stem, fqn), h_nodes in sorted(header_stem_buckets.items()):
            i_nodes = impl_stem_buckets.get((stem, fqn), [])
            if not i_nodes:
                continue
            all_ids = tuple(sorted({n.id for n in (*h_nodes, *i_nodes)}))
            if len(all_ids) > 1:
                grp_key = f"pair:{stem}::{fqn}"
                self._folded_groups[grp_key] = all_ids
                for uid in all_ids:
                    self._node_to_fold_group[uid] = all_ids
                i_ids = tuple(sorted({n.id for n in i_nodes}))
                for hn in h_nodes:
                    self._synthetic_edges.append(
                        RelationEdge(
                            source_id=hn.id,
                            target_expr=fqn,
                            edge_kind="declares",
                            span=hn.span,
                            resolution_status="resolved",
                            resolved_target_ids=i_ids,
                            provenance=(*hn.provenance, pass1_prov),
                        )
                    )

    def _run_pass2_import_resolution(self) -> None:
        """Pass 2: Resolve all `edge_kind == 'imports'` edges and construct per-file `FileImportTable`."""
        workspace_files = frozenset(self._file_graphs.keys())
        raw_bindings_by_file: Dict[str, Dict[str, FileImportBinding]] = defaultdict(dict)
        wildcard_targets_by_file: Dict[str, List[Tuple[str, bool]]] = defaultdict(list)
        exported_by_file: Dict[str, Set[str]] = {}
        edge_key_by_file_alias: Dict[Tuple[str, str], Tuple[str, int, str]] = {}

        for norm_path, fg in self._file_graphs.items():
            exports: Set[str] = set()
            for rn in fg.root_nodes:
                if rn.facets.get("visibility", "public") != "private":
                    exports.add(rn.name)
            exported_by_file[norm_path] = exports

        for norm_path, fg in self._file_graphs.items():
            custom_res = self._module_resolvers.get(fg.language)
            resolver = custom_res if custom_res is not None else self._default_resolver
            res_prov = ProvenanceStep(
                provider_id=getattr(resolver, "provider_id", "ast:builtin_module_resolver"),
                action="link",
                rule_or_hook="Pass2:ImportResolution",
            )

            for idx, edge in enumerate(fg.outgoing_edges):
                if edge.edge_kind != "imports":
                    continue
                raw_expr = edge.target_expr.strip()
                is_reexport = False
                is_wildcard = False
                if raw_expr.startswith("export*="):
                    is_reexport = True
                    is_wildcard = True
                    local_alias = "*"
                    lookup_expr = raw_expr.split("=", 1)[1].strip()
                elif raw_expr.startswith("*="):
                    is_wildcard = True
                    local_alias = "*"
                    lookup_expr = raw_expr.split("=", 1)[1].strip()
                elif "=" in raw_expr:
                    local_alias, lookup_expr = (p.strip() for p in raw_expr.split("=", 1))
                else:
                    lookup_expr = raw_expr
                    if "#" in lookup_expr:
                        local_alias = lookup_expr.split("#", 1)[1].strip() or posixpath.splitext(posixpath.basename(lookup_expr.split("#", 1)[0]))[0]
                    elif "/" in lookup_expr:
                        local_alias = posixpath.splitext(posixpath.basename(lookup_expr))[0]
                    else:
                        local_alias = re.split(r"[.:]+", lookup_expr.lstrip("."))[-1].strip() or lookup_expr

                try:
                    res_file, res_sids, is_ext = resolver.resolve_import(
                        importing_file=norm_path,
                        target_expr=lookup_expr,
                        workspace_files=workspace_files,
                        nodes_by_file=self._nodes_by_file,
                    )
                except Exception as exc:
                    log_warn(
                        f"WorkspaceGraphLinker: ModulePathResolver failed on '{lookup_expr}' in '{norm_path}': {exc}",
                        stream="stderr",
                    )
                    res_file, res_sids, is_ext = self._default_resolver.resolve_import(
                        importing_file=norm_path,
                        target_expr=lookup_expr,
                        workspace_files=workspace_files,
                        nodes_by_file=self._nodes_by_file,
                    )

                # Expand folded group siblings if import resolved to a partial/header symbol
                expanded_sids: List[str] = []
                for sid in res_sids:
                    for g_sid in self._node_to_fold_group.get(sid, (sid,)):
                        if g_sid not in expanded_sids:
                            expanded_sids.append(g_sid)
                final_sids = tuple(expanded_sids)

                if final_sids:
                    status = "resolved" if len(final_sids) == 1 else "overload_group"
                    edge_targets = final_sids
                elif res_file is not None:
                    status = "resolved"
                    file_root_nodes = self._file_graphs[res_file].root_nodes
                    edge_targets = (file_root_nodes[0].id,) if len(file_root_nodes) == 1 else tuple(rn.id for rn in file_root_nodes)
                elif is_ext:
                    status = "external"
                    edge_targets = ()
                else:
                    status = "unresolved"
                    edge_targets = ()

                ekey = (norm_path, idx, edge.target_expr)
                self._resolved_import_edges[ekey] = RelationEdge(
                    source_id=edge.source_id,
                    target_expr=edge.target_expr,
                    edge_kind=edge.edge_kind,
                    span=edge.span,
                    resolution_status=status,
                    resolved_target_ids=edge_targets,
                    provenance=(*edge.provenance, res_prov),
                )

                if is_wildcard and res_file is not None:
                    wildcard_targets_by_file[norm_path].append((res_file, is_reexport))
                elif local_alias:
                    binding = FileImportBinding(
                        local_alias=local_alias,
                        target_expr=lookup_expr,
                        resolved_file_path=res_file,
                        resolved_symbol_ids=final_sids,
                        is_wildcard=is_wildcard,
                        is_external=is_ext,
                        is_reexport=is_reexport,
                    )
                    raw_bindings_by_file[norm_path][local_alias] = binding
                    edge_key_by_file_alias[(norm_path, local_alias)] = ekey
                    # If `norm_path` is an `__init__.py` or `index.ts`, treat explicit bindings as re-exports
                    if posixpath.basename(norm_path) in ("__init__.py", "index.ts", "index.tsx", "index.js"):
                        exported_by_file[norm_path].add(local_alias)

        # Cycle-safe wildcard (`from X import *` / `export * from`) expansion
        for norm_path in self._file_graphs:
            visited_wild: Set[str] = {norm_path}
            queue: Deque[Tuple[str, bool]] = deque(wildcard_targets_by_file.get(norm_path, ()))
            while queue:
                target_f, is_reexp = queue.popleft()
                if target_f in visited_wild or target_f not in self._file_graphs:
                    continue
                visited_wild.add(target_f)
                for rn in self._file_graphs[target_f].root_nodes:
                    if rn.facets.get("visibility", "public") == "private":
                        continue
                    if rn.name not in raw_bindings_by_file[norm_path]:
                        fold_sids = self._node_to_fold_group.get(rn.id, (rn.id,))
                        raw_bindings_by_file[norm_path][rn.name] = FileImportBinding(
                            local_alias=rn.name,
                            target_expr=f"{target_f}::{rn.name}",
                            resolved_file_path=target_f,
                            resolved_symbol_ids=fold_sids,
                            is_wildcard=True,
                            is_external=False,
                            is_reexport=is_reexp,
                        )
                    if is_reexp:
                        exported_by_file[norm_path].add(rn.name)
                for next_f, next_reexp in wildcard_targets_by_file.get(target_f, ()):
                    if next_f not in visited_wild:
                        queue.append((next_f, is_reexp or next_reexp))

        # Bounded fixed-point resolution for multi-hop re-exported symbols (`__init__.py` / `index.ts` barrels)
        for _ in range(8):
            changed = False
            for norm_path in sorted(raw_bindings_by_file.keys()):
                b_dict = raw_bindings_by_file[norm_path]
                for alias_k, b_val in list(b_dict.items()):
                    if not b_val.resolved_symbol_ids and b_val.resolved_file_path:
                        sym_tail = re.split(r"[.:/]+", b_val.target_expr)[-1].strip()
                        target_b_dict = raw_bindings_by_file.get(b_val.resolved_file_path, {})
                        if sym_tail in target_b_dict and target_b_dict[sym_tail].resolved_symbol_ids:
                            re_b = target_b_dict[sym_tail]
                            b_dict[alias_k] = FileImportBinding(
                                local_alias=b_val.local_alias,
                                target_expr=b_val.target_expr,
                                resolved_file_path=re_b.resolved_file_path or b_val.resolved_file_path,
                                resolved_symbol_ids=re_b.resolved_symbol_ids,
                                is_wildcard=b_val.is_wildcard,
                                is_external=False,
                                is_reexport=True,
                            )
                            ekey = edge_key_by_file_alias.get((norm_path, alias_k))
                            if ekey and ekey in self._resolved_import_edges:
                                old_edge = self._resolved_import_edges[ekey]
                                re_status = "resolved" if len(re_b.resolved_symbol_ids) == 1 else "overload_group"
                                self._resolved_import_edges[ekey] = RelationEdge(
                                    source_id=old_edge.source_id,
                                    target_expr=old_edge.target_expr,
                                    edge_kind=old_edge.edge_kind,
                                    span=old_edge.span,
                                    resolution_status=re_status,
                                    resolved_target_ids=re_b.resolved_symbol_ids,
                                    provenance=old_edge.provenance,
                                )
                            changed = True
            if not changed:
                break

        for norm_path in self._file_graphs:
            self._file_import_tables[norm_path] = FileImportTable(
                file_path=norm_path,
                bindings=raw_bindings_by_file.get(norm_path, {}),
                exported_symbols=frozenset(exported_by_file.get(norm_path, set())),
            )

    def _resolve_type_expr_in_file_context(
        self,
        norm_path: str,
        source_node: Optional[SymbolNode],
        type_expr: str,
    ) -> Tuple[str, Tuple[str, ...]]:
        """
        Deterministically resolve a base type or interface expression (`BaseClass` or `pkg.BaseClass`)
        using: ① Lexical enclosing scope -> ③ Pass 2 `FileImportTable` -> ④ Unique workspace FQN/type.
        Returns `(resolution_status, resolved_target_ids)`.
        """
        expr = re.sub(r"<[^>]+>", "", type_expr or "").strip()
        if not expr:
            return "unresolved", ()

        type_kinds = {"class", "struct", "interface", "enum", "type_alias"}
        imp_table = self._file_import_tables.get(norm_path)

        # Tier 1: Same-file lexical scope (walking up source_node.scope_path)
        if source_node is not None and source_node.scope_path:
            sep = str(source_node.facets.get("scope_separator") or ".")
            for depth in range(len(source_node.scope_path), 0, -1):
                cand_fqn = sep.join((*source_node.scope_path[:depth], expr))
                local_cands = [
                    n.id for n in self._by_file_and_fqn.get((norm_path, cand_fqn), ())
                    if (n.kinds & type_kinds) and n.id != source_node.id
                ]
                if local_cands:
                    expanded = self._expand_fold_siblings(local_cands)
                    return ("resolved" if len(expanded) == 1 else "overload_group"), expanded

        same_file_matches = [
            n.id for n in (
                self._by_file_and_fqn.get((norm_path, expr), ())
                or self._by_file_and_short.get((norm_path, expr), ())
            )
            if (n.kinds & type_kinds) and (source_node is None or n.id != source_node.id)
        ]
        if same_file_matches:
            expanded = self._expand_fold_siblings(same_file_matches)
            return ("resolved" if len(expanded) == 1 else "ambiguous"), expanded

        # Tier 3: FileImportTable lookup (`from pkg import Base` or `import pkg; class Sub(pkg.Base)`)
        if imp_table is not None:
            if expr in imp_table.bindings:
                b = imp_table.bindings[expr]
                if b.resolved_symbol_ids:
                    expanded = self._expand_fold_siblings(b.resolved_symbol_ids)
                    return ("resolved" if len(expanded) == 1 else "overload_group"), expanded
                if b.resolved_file_path and b.resolved_file_path in self._nodes_by_file:
                    f_matches = _match_symbol_ids_in_file(self._nodes_by_file[b.resolved_file_path], expr)
                    if f_matches:
                        expanded = self._expand_fold_siblings(f_matches)
                        return ("resolved" if len(expanded) == 1 else "overload_group"), expanded
                if b.is_external:
                    return "external", ()

            if "." in expr or "::" in expr:
                parts = [p for p in re.split(r"[.:]+", expr) if p]
                if len(parts) >= 2 and parts[0] in imp_table.bindings:
                    b_mod = imp_table.bindings[parts[0]]
                    tail_sym = ".".join(parts[1:])
                    if b_mod.resolved_file_path and b_mod.resolved_file_path in self._nodes_by_file:
                        f_matches = _match_symbol_ids_in_file(self._nodes_by_file[b_mod.resolved_file_path], tail_sym)
                        if f_matches:
                            expanded = self._expand_fold_siblings(f_matches)
                            return ("resolved" if len(expanded) == 1 else "overload_group"), expanded
                    if b_mod.is_external:
                        return "external", ()

            # C# / C++ namespace imports (`using Namespace;`)
            ns_cands: List[str] = []
            for b in imp_table.bindings.values():
                if b.resolved_symbol_ids and not b.is_wildcard:
                    for sid in b.resolved_symbol_ids:
                        sn = self._nodes_by_id.get(sid)
                        if sn and sn.name == expr and (sn.kinds & type_kinds):
                            ns_cands.append(sid)
            if ns_cands:
                expanded = self._expand_fold_siblings(ns_cands)
                distinct_fqns = {self._nodes_by_id[i].fqn for i in expanded if i in self._nodes_by_id}
                status = "resolved" if len(distinct_fqns) == 1 else "ambiguous"
                return status, expanded

        # Tier 4: Workspace-unique FQN or short type name
        fqn_matches = [
            n.id for n in self._by_fqn.get(expr, ())
            if (n.kinds & type_kinds) and (source_node is None or n.id != source_node.id)
        ]
        if not fqn_matches and ("." not in expr and "::" not in expr):
            fqn_matches = [
                n.id for n in self._by_short_name.get(expr, ())
                if (n.kinds & type_kinds) and (source_node is None or n.id != source_node.id)
            ]
        if fqn_matches:
            expanded = self._expand_fold_siblings(fqn_matches)
            # Check if all expanded IDs belong to the same folded group or single symbol
            first_grp = set(self._node_to_fold_group.get(expanded[0], (expanded[0],)))
            if set(expanded) <= first_grp:
                return "resolved", expanded
            return "ambiguous", expanded

        return "unresolved", ()

    def _expand_fold_siblings(self, symbol_ids: Iterable[str]) -> Tuple[str, ...]:
        out: List[str] = []
        for sid in symbol_ids:
            for g_sid in self._node_to_fold_group.get(sid, (sid,)):
                if g_sid not in out:
                    out.append(g_sid)
        return tuple(sorted(out))

    def _run_pass3_inheritance_and_type_dag(self) -> None:
        """Pass 3: Resolve `inherits` and `implements` edges using Pass 2 `FileImportTable` and build cycle-free Type DAG."""
        pass3_prov = ProvenanceStep(
            provider_id="ast:WorkspaceGraphLinker",
            action="link",
            rule_or_hook="Pass3:InheritanceDAG",
        )
        raw_bases: Dict[str, List[str]] = defaultdict(list)

        for norm_path, fg in self._file_graphs.items():
            for idx, edge in enumerate(fg.outgoing_edges):
                if edge.edge_kind not in ("inherits", "implements"):
                    continue
                src_node = self._nodes_by_id.get(edge.source_id)
                status, target_ids = self._resolve_type_expr_in_file_context(
                    norm_path=norm_path,
                    source_node=src_node,
                    type_expr=edge.target_expr,
                )
                self._resolved_type_edges[(norm_path, idx, edge.target_expr)] = RelationEdge(
                    source_id=edge.source_id,
                    target_expr=edge.target_expr,
                    edge_kind=edge.edge_kind,
                    span=edge.span,
                    resolution_status=status,
                    resolved_target_ids=target_ids,
                    provenance=(*edge.provenance, pass3_prov),
                )
                if status == "resolved" and target_ids:
                    src_group = self._node_to_fold_group.get(edge.source_id, (edge.source_id,))
                    for s_id in src_group:
                        for t_id in target_ids:
                            if t_id != s_id and t_id not in raw_bases[s_id]:
                                raw_bases[s_id].append(t_id)

        # Cycle-safe DAG pruning: ensure adding `s_id -> b_id` does not create a cycle
        clean_bases: Dict[str, List[str]] = defaultdict(list)
        clean_derived: Dict[str, List[str]] = defaultdict(list)

        def _can_reach(start_id: str, goal_id: str) -> bool:
            if start_id == goal_id:
                return True
            visited: Set[str] = {start_id}
            q: Deque[str] = deque(clean_bases.get(start_id, ()))
            while q:
                curr = q.popleft()
                if curr == goal_id:
                    return True
                if curr not in visited:
                    visited.add(curr)
                    q.extend(clean_bases.get(curr, ()))
            return False

        for s_id in sorted(raw_bases.keys()):
            for b_id in raw_bases[s_id]:
                if not _can_reach(b_id, s_id):
                    clean_bases[s_id].append(b_id)
                    if s_id not in clean_derived[b_id]:
                        clean_derived[b_id].append(s_id)

        self._type_bases_by_id = {k: tuple(v) for k, v in clean_bases.items() if v}
        self._type_derived_by_id = {k: tuple(sorted(v)) for k, v in clean_derived.items() if v}

        # Populate `field_types_by_class_id` (resolving field type names to target type SymbolNode.id when possible)
        for norm_path, fg in self._file_graphs.items():
            for node in fg.all_nodes_by_id.values():
                raw_ft = node.facets.get("field_types")
                if not isinstance(raw_ft, Mapping):
                    continue
                cls_group = self._node_to_fold_group.get(node.id, (node.id,))
                for fn, ft_expr in raw_ft.items():
                    status, t_ids = self._resolve_type_expr_in_file_context(
                        norm_path=norm_path,
                        source_node=node,
                        type_expr=str(ft_expr),
                    )
                    resolved_ft = t_ids[0] if (status == "resolved" and t_ids) else str(ft_expr)
                    for cid in cls_group:
                        self._field_types_by_class_id[cid][str(fn)] = resolved_ft

    def _find_enclosing_type_id(self, norm_path: str, source_node: Optional[SymbolNode]) -> Optional[str]:
        """Return the enclosing `class`/`struct`/`interface` `SymbolNode.id` for `source_node`."""
        if source_node is None:
            return None
        type_kinds = {"class", "struct", "interface"}
        if source_node.kinds & type_kinds:
            return source_node.id
        if not source_node.scope_path:
            return None
        sep = str(source_node.facets.get("scope_separator") or ".")
        for depth in range(len(source_node.scope_path), 0, -1):
            cand_fqn = sep.join(source_node.scope_path[:depth])
            for cand in self._by_file_and_fqn.get((norm_path, cand_fqn), ()):
                if cand.kinds & type_kinds:
                    return cand.id
        return None

    def _get_type_ancestors_dag(self, type_id: str, bases_only: bool = False) -> Tuple[str, ...]:
        """Return cycle-free ordered type group IDs along the Pass 3 inheritance DAG."""
        seed_group = self._node_to_fold_group.get(type_id, (type_id,))
        visited: List[str] = [] if bases_only else list(seed_group)
        seen: Set[str] = set(seed_group)
        q: Deque[str] = deque()
        for sid in seed_group:
            for b_id in self._type_bases_by_id.get(sid, ()):
                if b_id not in seen:
                    seen.add(b_id)
                    visited.append(b_id)
                    q.append(b_id)
        while q:
            curr = q.popleft()
            for b_id in self._type_bases_by_id.get(curr, ()):
                if b_id not in seen:
                    seen.add(b_id)
                    visited.append(b_id)
                    q.append(b_id)
        return tuple(visited)

    def _classify_candidate_nodes(
        self,
        candidates: List[SymbolNode],
        arg_count: Optional[int] = None,
    ) -> Tuple[str, Tuple[str, ...]]:
        """
        Deterministically classify `candidates` into `("resolved" | "overload_group" | "ambiguous", ids)`.
        Never uses fuzzy substring scoring.
        """
        if not candidates:
            return "unresolved", ()
        unique_by_id: Dict[str, SymbolNode] = {c.id: c for c in candidates}
        ordered = [unique_by_id[k] for k in sorted(unique_by_id.keys())]
        if len(ordered) == 1:
            return "resolved", (ordered[0].id,)

        # Check if all candidates belong to the same folded symbol group (e.g., partial class or .h/.cpp pair)
        first_grp = set(self._node_to_fold_group.get(ordered[0].id, (ordered[0].id,)))
        if set(unique_by_id.keys()) <= first_grp:
            return "resolved", tuple(sorted(unique_by_id.keys()))

        # Check if all candidates share the same enclosing scope/file FQN (method overload group)
        parent_keys = {
            (c.id.split("::", 1)[0], c.scope_path, c.name)
            for c in ordered
        }
        # Also allow folded partial class siblings to count as the same overload container
        logical_containers = {
            (c.scope_path, c.name)
            for c in ordered
        }
        if len(parent_keys) == 1 or (
            len(logical_containers) == 1
            and all((c.kinds & {"method", "function", "constructor"}) for c in ordered)
            and len({c.id.split("::", 1)[0] for c in ordered}) == 1
        ):
            if arg_count is not None:
                matched_arity: List[SymbolNode] = []
                for c in ordered:
                    sig = str(c.facets.get("signature") or "")
                    p_cnt = _extract_param_count_from_signature(sig)
                    if p_cnt is not None:
                        # Subtract `self`/`cls` if Python method
                        if c.language == "python" and c.scope_path and ("def " in sig or sig.startswith("(")):
                            if re.search(r"\(\s*(?:self|cls)\b", sig):
                                p_cnt = max(0, p_cnt - 1)
                        if p_cnt == arg_count:
                            matched_arity.append(c)
                if len(matched_arity) == 1:
                    return "resolved", (matched_arity[0].id,)
                if len(matched_arity) > 1:
                    return "overload_group", tuple(c.id for c in matched_arity)
            return "overload_group", tuple(c.id for c in ordered)

        return "ambiguous", tuple(c.id for c in ordered)

    def _lookup_member_in_type_dag(
        self,
        type_id: str,
        member_name: str,
        bases_only: bool = False,
        arg_count: Optional[int] = None,
    ) -> Tuple[str, Tuple[str, ...]]:
        """Search `member_name` along `type_id` and its Pass 3 base DAG in MRO/BFS order."""
        dag_type_ids = self._get_type_ancestors_dag(type_id, bases_only=bases_only)
        for tid in dag_type_ids:
            # Group all folded siblings of `tid` at the same hierarchy level
            level_ids = self._node_to_fold_group.get(tid, (tid,))
            level_matches: List[SymbolNode] = []
            for lid in level_ids:
                tnode = self._nodes_by_id.get(lid)
                if tnode is None:
                    continue
                for ch in tnode.children:
                    if ch.name == member_name:
                        level_matches.append(ch)
            if level_matches:
                return self._classify_candidate_nodes(level_matches, arg_count=arg_count)
        return "unresolved", ()

    @staticmethod
    def _extract_edge_arg_count(edge: RelationEdge) -> Optional[int]:
        for p in edge.provenance:
            if p.detail and p.detail.startswith("arg_count="):
                try:
                    return int(p.detail.split("=", 1)[1])
                except ValueError:
                    pass
        return None

    def _resolve_document_edge(
        self,
        norm_path: str,
        edge: RelationEdge,
    ) -> Tuple[str, Tuple[str, ...]]:
        """Deterministically resolve a Markdown `edge_kind == 'documents'` edge (`path#Symbol` or `Class.method`)."""
        expr = edge.target_expr.strip()
        if not expr:
            return "unresolved", ()
        workspace_files = frozenset(self._file_graphs.keys())
        if "#" in expr or expr.endswith((".md", ".py", ".ts", ".tsx", ".js", ".cs", ".h", ".hpp", ".c", ".cpp")):
            res_file, res_sids, is_ext = self._default_resolver.resolve_import(
                importing_file=norm_path,
                target_expr=expr,
                workspace_files=workspace_files,
                nodes_by_file=self._nodes_by_file,
            )
            if res_sids:
                expanded = self._expand_fold_siblings(res_sids)
                return ("resolved" if len(expanded) == 1 else "overload_group"), expanded
            if res_file is not None and "#" not in expr:
                f_roots = self._file_graphs[res_file].root_nodes
                if f_roots:
                    return "resolved", (f_roots[0].id,)
            if is_ext and "://" in expr:
                return "external", ()
            if "#" in expr:
                return "unresolved", ()

        # Fall through to workspace FQN / short_name lookup
        fqn_cands = list(self._by_fqn.get(expr, ()))
        if fqn_cands:
            return self._classify_candidate_nodes(fqn_cands)
        short_cands = list(self._by_short_name.get(expr, ()))
        if short_cands:
            return self._classify_candidate_nodes(short_cands)
        return "unresolved", ()

    def _resolve_call_or_reference_edge(
        self,
        norm_path: str,
        fg_lang: str,
        edge: RelationEdge,
    ) -> Tuple[str, Tuple[str, ...], str]:
        """
        Execute the 4-Tier Deterministic Scope Cascade for `calls`, `references`, and `documents`:
        Tier 1: Lexical Enclosing Scope
        Tier 2: Enclosing Class & Pass 3 Inheritance DAG (including `receiver_aliases` & field types)
        Tier 3: Pass 2 `FileImportTable`
        Tier 4: Workspace-Unique FQN / Symbol Lookup
        Returns `(resolution_status, resolved_target_ids, matched_tier_rule)`.
        """
        if edge.edge_kind == "documents":
            st, tids = self._resolve_document_edge(norm_path, edge)
            return st, tids, "Pass4:DocumentResolution"

        raw_expr = edge.target_expr.strip()
        if not raw_expr:
            return "unresolved", (), "Pass4:Unresolved"

        arg_count = self._extract_edge_arg_count(edge)
        src_node = self._nodes_by_id.get(edge.source_id)
        enclosing_type_id = self._find_enclosing_type_id(norm_path, src_node)
        self_aliases = self._get_self_aliases(fg_lang)
        super_aliases = self._get_super_aliases(fg_lang)
        imp_table = self._file_import_tables.get(norm_path)

        normalized_expr = raw_expr.replace("::", ".")
        if "." in normalized_expr:
            prefix, member_name = normalized_expr.rsplit(".", 1)
        else:
            prefix, member_name = "", normalized_expr

        # ------------------------------------------------------------------
        # Tier 1: Unqualified Lexical Enclosing Scope
        # ------------------------------------------------------------------
        if not prefix:
            if src_node is not None:
                # 1a. Direct nested children of src_node (e.g. local function inside function)
                direct_children = [ch for ch in src_node.children if ch.name == member_name]
                if direct_children:
                    st, tids = self._classify_candidate_nodes(direct_children, arg_count=arg_count)
                    return st, tids, "Pass4:Tier1_LexicalScope"

                # 1b. Walk outward through enclosing lexical scopes in the same file
                sep = str(src_node.facets.get("scope_separator") or ".")
                for depth in range(len(src_node.scope_path), 0, -1):
                    scope_prefix = src_node.scope_path[:depth]
                    cand_fqn = sep.join((*scope_prefix, member_name))
                    scope_cands = self._by_file_and_fqn.get((norm_path, cand_fqn), [])
                    if scope_cands:
                        st, tids = self._classify_candidate_nodes(scope_cands, arg_count=arg_count)
                        return st, tids, "Pass4:Tier1_LexicalScope"

            # 1c. Top-level module symbols in the same file
            top_cands = [
                n for n in self._by_file_and_fqn.get((norm_path, member_name), ())
                if not n.scope_path
            ]
            if top_cands:
                st, tids = self._classify_candidate_nodes(top_cands, arg_count=arg_count)
                return st, tids, "Pass4:Tier1_LexicalScope"

        # ------------------------------------------------------------------
        # Tier 2: Enclosing Class & Pass 3 Inheritance DAG (`self`, `super`, field types, implicit `this`)
        # ------------------------------------------------------------------
        if enclosing_type_id is not None:
            if prefix in self_aliases or prefix in super_aliases:
                is_super = prefix in super_aliases
                st, tids = self._lookup_member_in_type_dag(
                    type_id=enclosing_type_id,
                    member_name=member_name,
                    bases_only=is_super,
                    arg_count=arg_count,
                )
                if st != "unresolved":
                    return st, tids, "Pass4:Tier2_ClassAndBaseDAG"
                return "unresolved", (), "Pass4:Tier2_ClassAndBaseDAG"

            # Field dispatch: `self.field.method()` or `field.method()`
            field_lookup_name: Optional[str] = None
            first_seg = prefix.split(".", 1)[0] if prefix else ""
            if first_seg in self_aliases and "." in prefix:
                field_lookup_name = prefix.split(".", 1)[1].split(".", 1)[0]
            elif prefix and "." not in prefix:
                field_lookup_name = prefix

            if field_lookup_name:
                for anc_tid in self._get_type_ancestors_dag(enclosing_type_id, bases_only=False):
                    ft_target = self._field_types_by_class_id.get(anc_tid, {}).get(field_lookup_name)
                    if ft_target and ft_target in self._nodes_by_id:
                        st, tids = self._lookup_member_in_type_dag(
                            type_id=ft_target,
                            member_name=member_name,
                            bases_only=False,
                            arg_count=arg_count,
                        )
                        if st != "unresolved":
                            return st, tids, "Pass4:Tier2_ClassAndBaseDAG"

            # Implicit `this` call for unqualified method calls in C# / C++ / Java
            if not prefix and fg_lang in ("c_sharp", "csharp", "cpp"):
                st, tids = self._lookup_member_in_type_dag(
                    type_id=enclosing_type_id,
                    member_name=member_name,
                    bases_only=False,
                    arg_count=arg_count,
                )
                if st != "unresolved":
                    return st, tids, "Pass4:Tier2_ClassAndBaseDAG"

        # Same-file explicit `ClassName.method()`
        if prefix:
            same_file_types = [
                n for n in (
                    self._by_file_and_fqn.get((norm_path, prefix), ())
                    or self._by_file_and_short.get((norm_path, prefix), ())
                )
                if n.kinds & {"class", "struct", "interface", "enum", "namespace", "module"}
            ]
            if len(same_file_types) == 1:
                st, tids = self._lookup_member_in_type_dag(
                    type_id=same_file_types[0].id,
                    member_name=member_name,
                    bases_only=False,
                    arg_count=arg_count,
                )
                if st != "unresolved":
                    return st, tids, "Pass4:Tier2_ClassAndBaseDAG"

        # ------------------------------------------------------------------
        # Tier 3: Pass 2 `FileImportTable`
        # ------------------------------------------------------------------
        if imp_table is not None:
            if not prefix and member_name in imp_table.bindings:
                b = imp_table.bindings[member_name]
                if b.is_external:
                    return "external", (), "Pass4:Tier3_FileImportTable"
                if b.resolved_symbol_ids:
                    cand_nodes = [self._nodes_by_id[i] for i in b.resolved_symbol_ids if i in self._nodes_by_id]
                    st, tids = self._classify_candidate_nodes(cand_nodes, arg_count=arg_count)
                    return st, tids, "Pass4:Tier3_FileImportTable"
                if b.resolved_file_path and b.resolved_file_path in self._nodes_by_file:
                    f_sids = _match_symbol_ids_in_file(self._nodes_by_file[b.resolved_file_path], member_name)
                    if f_sids:
                        cand_nodes = [self._nodes_by_id[i] for i in f_sids if i in self._nodes_by_id]
                        st, tids = self._classify_candidate_nodes(cand_nodes, arg_count=arg_count)
                        return st, tids, "Pass4:Tier3_FileImportTable"

            if prefix:
                root_prefix = prefix.split(".", 1)[0]
                if prefix in imp_table.bindings or root_prefix in imp_table.bindings:
                    b = imp_table.bindings.get(prefix) or imp_table.bindings[root_prefix]
                    if b.is_external:
                        return "external", (), "Pass4:Tier3_FileImportTable"
                    if b.resolved_symbol_ids:
                        for sid in b.resolved_symbol_ids:
                            st, tids = self._lookup_member_in_type_dag(
                                type_id=sid,
                                member_name=member_name,
                                bases_only=False,
                                arg_count=arg_count,
                            )
                            if st != "unresolved":
                                return st, tids, "Pass4:Tier3_FileImportTable"
                    if b.resolved_file_path and b.resolved_file_path in self._nodes_by_file:
                        sub_qual = (
                            f"{prefix.split('.', 1)[1]}.{member_name}"
                            if (prefix != root_prefix and "." in prefix)
                            else member_name
                        )
                        f_sids = _match_symbol_ids_in_file(self._nodes_by_file[b.resolved_file_path], sub_qual)
                        if f_sids:
                            cand_nodes = [self._nodes_by_id[i] for i in f_sids if i in self._nodes_by_id]
                            st, tids = self._classify_candidate_nodes(cand_nodes, arg_count=arg_count)
                            return st, tids, "Pass4:Tier3_FileImportTable"

            # C# / C++ namespace imports (`using Namespace;`)
            for b in imp_table.bindings.values():
                if b.resolved_symbol_ids and not b.is_wildcard:
                    for sid in b.resolved_symbol_ids:
                        sn = self._nodes_by_id.get(sid)
                        if sn is None:
                            continue
                        if not prefix and sn.name == member_name:
                            return "resolved", self._expand_fold_siblings((sid,)), "Pass4:Tier3_FileImportTable"
                        if prefix and sn.name == prefix:
                            st, tids = self._lookup_member_in_type_dag(
                                type_id=sid,
                                member_name=member_name,
                                bases_only=False,
                                arg_count=arg_count,
                            )
                            if st != "unresolved":
                                return st, tids, "Pass4:Tier3_FileImportTable"

        # ------------------------------------------------------------------
        # Tier 4: Workspace-Unique FQN or Receiver-Unkown Ambiguity Detection
        # ------------------------------------------------------------------
        fqn_matches = list(self._by_fqn.get(raw_expr, ())) or list(self._by_fqn.get(normalized_expr, ()))
        if fqn_matches:
            st, tids = self._classify_candidate_nodes(fqn_matches, arg_count=arg_count)
            return st, tids, "Pass4:Tier4_WorkspaceFQN"

        if prefix:
            # Qualified receiver of unknown dynamic type (e.g., `obj.run()`):
            # Check if `prefix` is a known unique type name first
            type_cands = [
                n for n in self._by_short_name.get(prefix, ())
                if n.kinds & {"class", "struct", "interface", "enum"}
            ]
            if len(type_cands) == 1:
                st, tids = self._lookup_member_in_type_dag(
                    type_id=type_cands[0].id,
                    member_name=member_name,
                    bases_only=False,
                    arg_count=arg_count,
                )
                if st != "unresolved":
                    return st, tids, "Pass4:Tier4_WorkspaceFQN"

            # Otherwise, look up all methods matching `member_name` across workspace types
            method_cands = [
                n for n in self._by_short_name.get(member_name, ())
                if n.kinds & {"method", "function", "property"}
            ]
            if len(method_cands) > 1:
                st, tids = self._classify_candidate_nodes(method_cands, arg_count=arg_count)
                return st, tids, "Pass4:Tier4_WorkspaceFQN"
            if len(method_cands) == 1 and prefix in self._by_short_name:
                return "resolved", (method_cands[0].id,), "Pass4:Tier4_WorkspaceFQN"
        else:
            top_global = [
                n for n in self._by_short_name.get(member_name, ())
                if not n.scope_path
            ]
            if top_global:
                st, tids = self._classify_candidate_nodes(top_global, arg_count=arg_count)
                return st, tids, "Pass4:Tier4_WorkspaceFQN"

        return "unresolved", (), "Pass4:Unresolved"

    def link_workspace(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> WorkspaceSymbolGraph:
        """Execute Pass 1 -> Pass 2 -> Pass 3 -> Pass 4 and return an immutable `WorkspaceSymbolGraph`."""
        check_task_cancelled()
        self._run_pass1_global_indexing_and_folding()
        check_task_cancelled()
        self._run_pass2_import_resolution()
        check_task_cancelled()
        self._run_pass3_inheritance_and_type_dag()
        check_task_cancelled()

        all_resolved_edges: List[RelationEdge] = list(self._synthetic_edges)
        total_fgs = len(self._file_graphs)

        for fg_idx, (norm_path, fg) in enumerate(self._file_graphs.items(), start=1):
            if (fg_idx & 15) == 1:
                check_task_cancelled()
            if progress_callback is not None:
                progress_callback(fg_idx, total_fgs)
            file_edges: List[RelationEdge] = []
            for idx, edge in enumerate(fg.outgoing_edges):
                key = (norm_path, idx, edge.target_expr)
                if edge.edge_kind == "imports" and key in self._resolved_import_edges:
                    file_edges.append(self._resolved_import_edges[key])
                elif edge.edge_kind in ("inherits", "implements") and key in self._resolved_type_edges:
                    file_edges.append(self._resolved_type_edges[key])
                else:
                    status, target_ids, tier_rule = self._resolve_call_or_reference_edge(
                        norm_path=norm_path,
                        fg_lang=fg.language,
                        edge=edge,
                    )
                    pass4_prov = ProvenanceStep(
                        provider_id="ast:WorkspaceGraphLinker",
                        action="link",
                        rule_or_hook=tier_rule,
                    )
                    file_edges.append(
                        RelationEdge(
                            source_id=edge.source_id,
                            target_expr=edge.target_expr,
                            edge_kind=edge.edge_kind,
                            span=edge.span,
                            resolution_status=status,
                            resolved_target_ids=target_ids,
                            provenance=(*edge.provenance, pass4_prov),
                        )
                    )

            # Run optional peer EdgeRefiners for this language
            refiners = self._edge_refiners.get(fg.language, ())
            refined_tuple = tuple(file_edges)
            for refiner in refiners:
                try:
                    refined_tuple = tuple(
                        refiner.refine_workspace_edges(
                            edges=refined_tuple,
                            nodes_by_id=MappingProxyType(self._nodes_by_id),
                            file_import_tables=MappingProxyType(self._file_import_tables),
                        )
                    )
                except Exception as exc:
                    log_warn(
                        f"WorkspaceGraphLinker: EdgeRefiner '{getattr(refiner, 'provider_id', refiner)}' failed on '{norm_path}': {exc}",
                        stream="stderr",
                    )
            all_resolved_edges.extend(refined_tuple)

        return WorkspaceSymbolGraph(
            file_graphs=self._file_graphs,
            nodes_by_id=self._nodes_by_id,
            resolved_edges=tuple(all_resolved_edges),
            file_import_tables=self._file_import_tables,
            folded_symbol_groups=self._folded_groups,
            type_bases_by_id=self._type_bases_by_id,
            type_derived_by_id=self._type_derived_by_id,
            field_types_by_class_id=self._field_types_by_class_id,
        )


__all__ = (
    "TopologyLinker",
    "DefaultModulePathResolver",
    "WorkspaceGraphLinker",
    "expand_contract_symbol_ids",
    "get_last_linker_cache",
    "reset_linker_cache",
)
