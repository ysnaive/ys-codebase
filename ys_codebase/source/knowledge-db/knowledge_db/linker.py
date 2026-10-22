"""
knowledge-db 跨檔案符號拓撲消歧鏈接器 (TopologyLinker)
結合 Universal AST FQN、階層父子作用域與 Import 映射表，執行四階精確消歧並杜絕幽靈關聯 (Ghost Edges)。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import defaultdict
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .schema import SymbolCallSite, SymbolKind, UnifiedSymbol
from .tokenizer import CodeTokenizer

logger = logging.getLogger("knowledge-db.linker")


class TopologyLinker:
    """
    跨檔案符號調用拓撲消歧鏈接器
    結合 AST 調用點、檔頭 Import 映射表、FQN 與全域符號池，執行四階消歧並產出精確調用邊。
    """

    def __init__(
        self,
        symbols_map: Dict[str, UnifiedSymbol],
        thesaurus: Optional[Any] = None,
        tokenizer: Optional[CodeTokenizer] = None,
    ):
        self.symbols_map = symbols_map
        self.thesaurus = thesaurus
        self.tokenizer = tokenizer or CodeTokenizer()

        # 預構建高速多維與 FQN 索引
        # 1. file_path (normalized) -> List[UnifiedSymbol]
        self._by_file: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        # 2. name -> List[UnifiedSymbol]
        self._by_name: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        # 3. space -> Dict[name, List[UnifiedSymbol]]
        self._by_space_name: Dict[str, Dict[str, List[UnifiedSymbol]]] = defaultdict(lambda: defaultdict(list))
        # 4. (file_path, name) -> List[UnifiedSymbol]
        self._by_file_name: Dict[Tuple[str, str], List[UnifiedSymbol]] = defaultdict(list)
        # 5. fqn (lowercase) -> UnifiedSymbol
        self._by_fqn: Dict[str, UnifiedSymbol] = {}
        # 6. parent_id -> List[UnifiedSymbol]
        self._by_parent_id: Dict[str, List[UnifiedSymbol]] = defaultdict(list)
        # 7. class_short_name -> Set[base_type_short_name] (繼承與介面映射)
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

        for sym_id, sym in self.symbols_map.items():
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

            # 記錄類別繼承與實作介面關係
            base_types = sym.metadata.get("base_types")
            if base_types and isinstance(base_types, (list, tuple)):
                for bt in base_types:
                    if bt:
                        self._class_bases[short_name].add(str(bt))

            # 索引短名 (short_name) 與雙段類別方法名 (Class.Method)
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
        """
        定位調用點所屬之 caller UnifiedSymbol ID
        """
        norm_path = file_path.replace("\\", "/").lower()
        candidates = self._by_file.get(norm_path, [])
        if not candidates:
            return None

        if caller_member_name and caller_member_name != "<module>":
            for sym in candidates:
                if sym.name == caller_member_name:
                    return sym.id
                # 若為 ClassName.method_name 形式匹配
                if sym.name.endswith(f".{caller_member_name}") or caller_member_name.endswith(f".{sym.name}"):
                    return sym.id

        # 若在頂層或未精準匹配到方法，以第一個頂層符號或檔案首個符號為代表
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
            # 1. 優先同檔案
            local_matches = self._by_file_name.get((norm_path, scoped_target), [])
            if local_matches:
                return local_matches[0].id
            # 2. 次選同語意空間 (支援 partial class 或跨檔案繼承基底類別)
            if space_name and space_name in self._by_space_name:
                space_matches = self._by_space_name[space_name].get(scoped_target, [])
                if space_matches:
                    return space_matches[0].id
            # 3. 全庫明確類別限定名匹配
            global_matches = self._by_name.get(scoped_target, [])
            if global_matches:
                return global_matches[0].id
        return None

    def resolve_call_site(
        self,
        site: SymbolCallSite,
        file_imports: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        依四階消歧演算法 (4-Tier Disambiguation Cascade) 定位目標 callee_symbol_id。
        收緊未明確作用域之裸調用判定，徹底杜絕跨模組幽靈關聯 (Ghost Edges)。
        """
        imports = file_imports or {}
        norm_path = site.file_path.replace("\\", "/").lower()
        callee = site.callee_name
        prefix = site.context_prefix.strip()
        space_name = site.space

        # =========================================================================
        # Tier 1: 檔內 / 類別內作用域自省 (Self / Class / Implicit this / Base Scope)
        # =========================================================================
        if prefix in ("self", "cls", "base", "super"):
            caller_class = self._get_caller_class_name(site)
            is_base_call = prefix in ("base", "super")
            resolved_id = self._resolve_in_class_or_bases(
                caller_class, callee, norm_path, space_name, bases_only=is_base_call
            )
            if resolved_id:
                return resolved_id

            # 檢查 caller 的 parent_id 作用域
            caller_id = site.caller_symbol_id
            if caller_id and caller_id in self.symbols_map:
                caller_sym = self.symbols_map[caller_id]
                parent_key = caller_sym.parent_id or caller_id
                siblings = self._by_parent_id.get(parent_key, [])
                for s in siblings:
                    if s.name == callee or s.name.endswith(f".{callee}"):
                        return s.id

            # 若為 self/cls 且同類別/基底類別未找到，不應跨無關檔案盲目擴散
            return None

        if not prefix:
            # 1.2 隱式 this 調用：若 caller 位於類別內部，優先尋找同類別或繼承基底類別之方法
            caller_class = self._get_caller_class_name(site)
            if caller_class:
                resolved_id = self._resolve_in_class_or_bases(caller_class, callee, norm_path, space_name)
                if resolved_id:
                    return resolved_id

            # 1.3 尋找同檔案內的函式、類別或頂層定義 (僅限頂層符號或同類別符號，避免綁定同檔無關類別之同名方法)
            local_matches = self._by_file_name.get((norm_path, callee), [])
            if local_matches:
                if len(local_matches) == 1:
                    m = local_matches[0]
                    m_parent = m.metadata.get("parent_scope") or ""
                    if not m_parent or m_parent == caller_class or m.kind in ("function", "class", "struct", "interface"):
                        return m.id
                else:
                    for m in local_matches:
                        if m.kind in ("function", "class", "struct", "interface") or (
                            caller_class and m.metadata.get("parent_scope") == caller_class
                        ):
                            return m.id

        # =========================================================================
        # Tier 2: 檔頭 Import 映射表精準匹配 (Explicit Imports & FQN)
        # =========================================================================
        if prefix and prefix in imports:
            # 情況 A: 前綴是導入的類別或別名 (例如 from foo import InvertedIndex -> InvertedIndex.load_binary)
            imported_target = imports[prefix]  # 如 'knowledge_db.retrieval.InvertedIndex'
            target_class = imported_target.split(".")[-1]

            # 2.1 透過 FQN 精確查找
            target_fqn = f"{imported_target.lower()}.{callee.lower()}"
            if target_fqn in self._by_fqn:
                return self._by_fqn[target_fqn].id

            # 2.2 透過 Class.method 匹配
            candidate_method = f"{target_class}.{callee}"
            matches = self._by_name.get(candidate_method, [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target)
                if best:
                    return best.id

        if not prefix and callee in imports:
            # 情況 B: 直接導入的函式或類別 (例如 from foo import act_search -> act_search())
            imported_target = imports[callee]

            # 2.3 透過 FQN 精確查找
            if imported_target.lower() in self._by_fqn:
                return self._by_fqn[imported_target.lower()].id

            target_short = imported_target.split(".")[-1]
            matches = self._by_name.get(target_short, [])
            if matches:
                best = self._pick_best_by_import_path(matches, imported_target)
                if best:
                    return best.id

        # =========================================================================
        # Tier 3: 同語意空間符號優先匹配 (Same-Space Scope)
        # =========================================================================
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
                    # 若 prefix 是實例變數 (如 self.index 或 m_Owner)，優先檢查同類別/同檔案，再於空間內查找候選
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

        # =========================================================================
        # Tier 4: 全庫上下文打分 (嚴格過濾以杜絕幽靈關聯)
        # =========================================================================
        # 關鍵守門：若無前綴 (裸調用) 且無 Import 映射且非同檔定義，嚴禁跨檔盲連！
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
            # 前綴為實例變數 (如 self.index)，比對已匯入類別
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

        # 無法確定唯一目標，標記為未鏈接邊 (EC-03)
        return None

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

            # 1. 若符號為 Method/Constructor/Property 且 prefix 包含類別名或命名空間段
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
            # 2. 函式比對
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
        """
        批次解析調用點清單，回傳 [(caller_symbol_id, callee_symbol_id, site), ...]
        """
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

            # [DR-02] 保留真實程式碼方法/函式之遞迴自調用邊，但阻擋模組/文檔等容器自指雜訊
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
