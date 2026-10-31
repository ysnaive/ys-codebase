"""
knowledge-db 跨檔案符號拓撲消歧鏈接器 (TopologyLinker)
結合 Universal AST FQN、階層父子作用域與 Import 映射表，執行四階精確消歧並杜絕幽靈關聯 (Ghost Edges)。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import defaultdict
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from .schema import SymbolCallSite, SymbolKind, UnifiedSymbol

logger = logging.getLogger("knowledge-db.linker")


class TopologyLinker:
    """
    跨檔案符號調用拓撲消歧鏈接器
    結合 AST 調用點、檔頭 Import 映射表、FQN 與全域符號池，執行四階消歧並產出精確調用邊。
    """

    def __init__(
        self,
        symbols_map: Dict[str, UnifiedSymbol],
    ):
        self.symbols_map = symbols_map

        self._by_file: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_name: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._by_space_name: Dict[str, Dict[str, List[UnifiedSymbol]]] = defaultdict(lambda: defaultdict(list))
        self._by_file_name: Dict[Tuple[str, str], List[UnifiedSymbol]] = defaultdict(list)
        self._by_fqn: Dict[str, UnifiedSymbol] = {}
        self._by_parent_id: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        self._class_bases: Dict[str, Set[str]] = defaultdict(set)

        self._reindex()

    def _reindex(self) -> None:
        """建立內部多維查找與 FQN 索引"""
        self._by_file.clear()
        self._by_name.clear()
        self._by_space_name.clear()
        self._by_file_name.clear()
        self._by_fqn.clear()
        self._by_parent_id.clear()
        self._class_bases.clear()

        for _, sym in self.symbols_map.items():
            norm_path = sym.file_path.replace("\\", "/").lower()
            self._by_file[norm_path].append(sym)
            self._by_name[sym.name].append(sym)
            self._by_file_name[(norm_path, sym.name)].append(sym)

            if sym.fqn:
                self._by_fqn[sym.fqn.lower()] = sym

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

            for sp in sym.spaces:
                self._by_space_name[sp][sym.name].append(sym)
                for key in alias_keys:
                    self._by_space_name[sp][key].append(sym)

    def find_caller_symbol_id(self, file_path: str, caller_member_name: str) -> Optional[str]:
        """定位調用點所屬之 caller UnifiedSymbol ID"""
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
        """解析調用點所屬之類別短名 (支援多段命名空間下之類別成員)"""
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
        """BFS 取得類別之所有繼承基底類別與實作介面名稱清單"""
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
    ) -> Optional[str]:
        """於指定類別、partial 同名類別或其繼承基底類別中尋找方法"""
        if not class_name:
            return None

        target_classes = self._get_ancestor_classes(class_name) if bases_only else ([class_name] + self._get_ancestor_classes(class_name))
        for cls_name in target_classes:
            scoped_target = f"{cls_name}.{callee}"
            local_matches = self._by_file_name.get((norm_path, scoped_target), [])
            if local_matches:
                return local_matches[0].id
            if space_name and space_name in self._by_space_name:
                space_matches = self._by_space_name[space_name].get(scoped_target, [])
                if space_matches:
                    return space_matches[0].id
            global_matches = self._by_name.get(scoped_target, [])
            if global_matches:
                return global_matches[0].id
        return None

    def _resolve_self_or_cls_call(
        self, site: SymbolCallSite, prefix: str, callee: str, norm_path: str, space_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Tier 1：檔內 / 類別內作用域自省 (Self / Class / Implicit this / Base Scope)"""
        if prefix in ("self", "cls", "base", "super"):
            caller_class = self._get_caller_class_name(site)
            is_base_call = prefix in ("base", "super")
            resolved_id = self._resolve_in_class_or_bases(
                caller_class, callee, norm_path, space_name, bases_only=is_base_call
            )
            if resolved_id:
                return True, resolved_id

            caller_id = site.caller_symbol_id
            if caller_id and caller_id in self.symbols_map:
                caller_sym = self.symbols_map[caller_id]
                parent_key = caller_sym.parent_id or caller_id
                for s in self._by_parent_id.get(parent_key, []):
                    if s.name == callee or s.name.endswith(f".{callee}"):
                        return True, s.id
            return True, None

        if not prefix:
            caller_class = self._get_caller_class_name(site)
            if caller_class:
                resolved_id = self._resolve_in_class_or_bases(caller_class, callee, norm_path, space_name)
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
                    for m in local_matches:
                        if m.kind in ("function", "class", "struct", "interface") or (
                            caller_class and m.metadata.get("parent_scope") == caller_class
                        ):
                            return True, m.id

        return False, None

    def _resolve_imported_module_call(
        self, prefix: str, callee: str, imports: Dict[str, str]
    ) -> Optional[str]:
        """Tier 2：檔頭 Import 映射表精準匹配 (Explicit Imports & FQN)"""
        if prefix and prefix in imports:
            imported_target = imports[prefix]
            target_class = imported_target.split(".")[-1]
            target_fqn = f"{imported_target.lower()}.{callee.lower()}"
            if target_fqn in self._by_fqn:
                return self._by_fqn[target_fqn].id

            matches = self._by_name.get(f"{target_class}.{callee}", [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target)
                if best:
                    return best.id

        if not prefix and callee in imports:
            imported_target = imports[callee]
            if imported_target.lower() in self._by_fqn:
                return self._by_fqn[imported_target.lower()].id

            target_short = imported_target.split(".")[-1]
            matches = self._by_name.get(target_short, [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target)
                if best:
                    return best.id
        return None

    def _resolve_same_file_or_global_call(
        self,
        site: SymbolCallSite,
        prefix: str,
        callee: str,
        norm_path: str,
        space_name: str,
        imports: Dict[str, str],
    ) -> Optional[str]:
        """Tier 3 & Tier 4：同語意空間優先匹配與全庫上下文打分"""
        prefix_tail = prefix.split(".")[-1] if "." in prefix else prefix
        if space_name and space_name in self._by_space_name:
            if prefix:
                space_matches = list(self._by_space_name[space_name].get(f"{prefix}.{callee}", []))
                if not space_matches and prefix_tail != prefix:
                    space_matches = list(self._by_space_name[space_name].get(f"{prefix_tail}.{callee}", []))
                if space_matches:
                    if len(space_matches) == 1:
                        return space_matches[0].id
                    best = self._score_candidates(space_matches, prefix, callee)
                    if best:
                        return best.id
                else:
                    caller_class = self._get_caller_class_name(site)
                    if caller_class:
                        same_cls_id = self._resolve_in_class_or_bases(caller_class, callee, norm_path, space_name)
                        if same_cls_id:
                            return same_cls_id

                    local_candidates = list(self._by_file_name.get((norm_path, callee), []))
                    if len(local_candidates) == 1:
                        return local_candidates[0].id

                    candidates = list(self._by_space_name[space_name].get(callee, []))
                    if imports:
                        imported_classes = {target.split(".")[-1].lower() for target in imports.values()}
                        imported_matches = [
                            c for c in candidates
                            if any(cls in c.name.lower() or (c.fqn and cls in c.fqn.lower()) for cls in imported_classes)
                        ]
                        if len(imported_matches) == 1:
                            return imported_matches[0].id
                        elif len(imported_matches) > 1:
                            best = self._score_candidates(imported_matches, prefix, callee)
                            if best:
                                return best.id

                    if len(candidates) == 1:
                        return candidates[0].id
                    elif len(candidates) > 1:
                        best = self._score_candidates(candidates, prefix, callee, caller_class=caller_class, norm_path=norm_path)
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
            best = self._score_candidates(global_matches, prefix, callee)
            if best:
                return best.id
        else:
            candidates = list(self._by_name.get(callee, []))
            if imports:
                imported_classes = {target.split(".")[-1].lower() for target in imports.values()}
                imported_matches = [
                    c for c in candidates
                    if any(cls in c.name.lower() or (c.fqn and cls in c.fqn.lower()) for cls in imported_classes)
                ]
                if len(imported_matches) == 1:
                    return imported_matches[0].id
                elif len(imported_matches) > 1:
                    best = self._score_candidates(imported_matches, prefix, callee)
                    if best:
                        return best.id

            if len(candidates) == 1:
                return candidates[0].id
            elif len(candidates) > 1:
                best = self._score_candidates(candidates, prefix, callee)
                if best:
                    return best.id

        return None

    def resolve_call_site(
        self,
        site: SymbolCallSite,
        file_imports: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """依四階消歧演算法 (4-Tier Disambiguation Cascade) 定位目標 callee_symbol_id。"""
        imports = file_imports or {}
        norm_path = site.file_path.replace("\\", "/").lower()
        callee = site.callee_name
        prefix = site.context_prefix.strip()
        space_name = site.space

        handled, tier1_id = self._resolve_self_or_cls_call(site, prefix, callee, norm_path, space_name)
        if handled:
            return tier1_id

        tier2_id = self._resolve_imported_module_call(prefix, callee, imports)
        if tier2_id:
            return tier2_id

        return self._resolve_same_file_or_global_call(site, prefix, callee, norm_path, space_name, imports)

    def _pick_best_by_import_path(self, matches: List[UnifiedSymbol], imported_path: str) -> Optional[UnifiedSymbol]:
        """依據 import 路徑特徵選擇最吻合的符號"""
        imp_parts = imported_path.replace(".", "/").lower().split("/")
        for m in matches:
            m_path = m.file_path.replace("\\", "/").lower()
            if any(part in m_path for part in imp_parts if len(part) > 2):
                return m
            if m.fqn and imported_path.lower() in m.fqn.lower():
                return m
        return matches[0] if matches else None

    def _score_candidates(
        self,
        candidates: List[UnifiedSymbol],
        prefix: str,
        callee: str,
        caller_class: str = "",
        norm_path: str = "",
    ) -> Optional[UnifiedSymbol]:
        """評分多個同名候選符號"""
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
                    elif cls_part in prefix_clean or prefix_tail in cls_part:
                        score += 10.0

                if caller_cls_low and parent_cls == caller_cls_low:
                    score += 8.0
                if norm_path and sym.file_path.replace("\\", "/").lower() == norm_path:
                    score += 5.0
            elif sym_kind == SymbolKind.FUNCTION.value and not prefix_clean:
                score += 5.0

            scored.append((score, sym))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] > 0.0 else None

    def link_call_sites(
        self,
        call_sites: List[SymbolCallSite],
        imports_map: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[Tuple[str, str, SymbolCallSite]]:
        """批次解析調用點清單，回傳 [(caller_symbol_id, callee_symbol_id, site), ...]"""
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
