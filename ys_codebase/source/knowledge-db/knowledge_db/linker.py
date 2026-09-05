"""
knowledge-db 跨檔案符號拓撲消歧鏈接器 (TopologyLinker)
結合 Universal AST FQN、階層父子作用域與 Import 映射表，執行四階精確消歧並杜絕幽靈關聯 (Ghost Edges)。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import defaultdict
import logging
from pathlib import Path
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

        self._reindex()

    def _reindex(self) -> None:
        """建立內部多維查找與 FQN 索引"""
        self._by_file.clear()
        self._by_name.clear()
        self._by_space_name.clear()
        self._by_file_name.clear()
        self._by_fqn.clear()
        self._by_parent_id.clear()

        for sym_id, sym in self.symbols_map.items():
            norm_path = sym.file_path.replace("\\", "/").lower()
            self._by_file[norm_path].append(sym)
            self._by_name[sym.name].append(sym)
            self._by_file_name[(norm_path, sym.name)].append(sym)

            if sym.fqn:
                self._by_fqn[sym.fqn.lower()] = sym

            if sym.parent_id:
                self._by_parent_id[sym.parent_id].append(sym)

            # 亦索引類別名稱與方法短名
            if "." in sym.name:
                short_name = sym.name.split(".")[-1]
                self._by_name[short_name].append(sym)

            for sp in sym.spaces:
                self._by_space_name[sp][sym.name].append(sym)
                if "." in sym.name:
                    short_name = sym.name.split(".")[-1]
                    self._by_space_name[sp][short_name].append(sym)

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

        # =========================================================================
        # Tier 1: 檔內 / 類別內作用域自省 (Self / Class / Parent Scope)
        # =========================================================================
        if prefix in ("self", "cls"):
            # 1.1 若為 self/cls，優先在呼叫者所屬類別內部尋找同名方法
            if site.caller_member_name and "." in site.caller_member_name:
                class_name = site.caller_member_name.split(".")[0]
                target_full_name = f"{class_name}.{callee}"
                local_matches = self._by_file_name.get((norm_path, target_full_name), [])
                if local_matches:
                    return local_matches[0].id

            # 1.2 檢查 caller 的 parent_id 作用域
            caller_id = site.caller_symbol_id
            if caller_id and caller_id in self.symbols_map:
                caller_sym = self.symbols_map[caller_id]
                parent_key = caller_sym.parent_id or caller_id
                siblings = self._by_parent_id.get(parent_key, [])
                for s in siblings:
                    if s.name == callee or s.name.endswith(f".{callee}"):
                        return s.id

            # 若為 self/cls 且同類別/同檔未找到，不應跨檔案擴散
            return None

        if not prefix:
            # 1.3 尋找同檔案內的函式、類別或頂層定義
            local_matches = self._by_file_name.get((norm_path, callee), [])
            if local_matches:
                return local_matches[0].id

        # =========================================================================
        # Tier 2: 檔頭 Import 映射表精準匹配 (Explicit Imports & FQN)
        # =========================================================================
        if prefix and prefix in imports:
            # 情況 A: 前綴是導入的類別或別名 (例如 from foo import InvertedIndex ➔ InvertedIndex.load_binary)
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
            # 情況 B: 直接導入的函式或類別 (例如 from foo import act_search ➔ act_search())
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
        space_name = site.space
        if space_name and space_name in self._by_space_name:
            if prefix:
                space_matches = list(self._by_space_name[space_name].get(f"{prefix}.{callee}", []))
                if space_matches:
                    if len(space_matches) == 1:
                        return space_matches[0].id
                    best = self._score_candidates(space_matches, prefix, callee)
                    if best:
                        return best.id
                else:
                    # 若 prefix 是實例變數 (如 self.index)，在空間內查找候選
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
                        best = self._score_candidates(candidates, prefix, callee)
                        if best:
                            return best.id

        # =========================================================================
        # Tier 4: 全庫上下文打分 (嚴格過濾以杜絕幽靈關聯)
        # =========================================================================
        # 關鍵守門：若無前綴 (裸調用) 且無 Import 映射且非同檔定義，嚴禁跨檔盲連！
        if not prefix:
            return None

        global_matches = list(self._by_name.get(f"{prefix}.{callee}", []))
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
    ) -> Optional[UnifiedSymbol]:
        """評分多個同名候選符號"""
        if not candidates:
            return None

        prefix_clean = prefix.lower()
        scored: List[Tuple[float, UnifiedSymbol]] = []

        for sym in candidates:
            score = 0.0
            # 1. 若符號為 Method 且 prefix 包含類別名
            sym_kind = sym.kind.value if isinstance(sym.kind, SymbolKind) else str(sym.kind)
            if sym_kind == SymbolKind.METHOD.value and "." in sym.name:
                cls_part = sym.name.split(".")[0].lower()
                if prefix_clean and (prefix_clean == cls_part or cls_part in prefix_clean or prefix_clean in cls_part):
                    score += 10.0
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
            if callee_id and caller_id != callee_id:
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
