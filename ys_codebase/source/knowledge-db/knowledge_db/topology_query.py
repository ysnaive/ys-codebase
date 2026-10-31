"""
knowledge-db 調用圖拓撲查詢服務 (TopologyQueryService)
自 pipeline.py 獨立剝離：負責符號目標定位、介面契約雙向展開、
上游調用者 (callers)、下游被調用者 (callees) 與多階重構影響面 (impact) 分析。
"""

from collections import defaultdict
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .graph import CallGraphIndex
from .retrieval import BM25Engine, InvertedIndex, QueryFilter, SnippetExtractor
from .schema import UnifiedSymbol


class TopologyQueryService:
    """調用圖拓撲查詢與重構影響面分析服務"""

    def __init__(
        self,
        ensure_index_fn: Callable[[], InvertedIndex],
        get_graph_fn: Callable[[], CallGraphIndex],
        bm25_engine: BM25Engine,
        snippet_extractor: SnippetExtractor,
    ):
        self._ensure_index_fn = ensure_index_fn
        self._get_graph_fn = get_graph_fn
        self.bm25_engine = bm25_engine
        self.snippet_extractor = snippet_extractor

    @staticmethod
    def normalize_ftypes(ftypes: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
        """正規化副檔名篩選清單 (支援逗號分隔或串列)"""
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
        """判定符號是否為非程式碼文檔符號 (Markdown / doc_*)"""
        lang = (sym.language or "").lower()
        kind_str = sym.kind.value if hasattr(sym.kind, "value") else str(sym.kind)
        return lang == "markdown" or kind_str.startswith("doc_")

    @classmethod
    def matches_topology_filter(cls, sym: UnifiedSymbol, norm_ftypes: Optional[List[str]]) -> bool:
        """
        拓撲指令 (callers / callees / impact) 符號篩選守門：
        - 未指定 ftypes 時：預設排除非程式碼文檔符號 (Markdown / doc_*)
        - 顯式指定 ftypes 時：依檔案副檔名嚴格過濾 (如 --ftype=md 僅保留 .md/.markdown)
        """
        if not norm_ftypes:
            return not cls.is_doc_symbol(sym)
        ext = Path(sym.file_path).suffix.lstrip(".").lower()
        allowed = set(norm_ftypes)
        if "md" in allowed or "markdown" in allowed:
            allowed.update({"md", "markdown"})
        return ext in allowed

    def expand_contract_symbol_ids(self, idx: InvertedIndex, target_sym: UnifiedSymbol) -> List[str]:
        """介面/基底類別與實作類別同名方法雙向契約展開"""
        result_ids = [target_sym.id]
        if not idx:
            return result_ids

        kind_str = target_sym.kind.value if hasattr(target_sym.kind, "value") else str(target_sym.kind)
        if kind_str not in ("method", "function", "property"):
            return result_ids

        parent_cls = (target_sym.metadata.get("parent_scope") or "") if target_sym.metadata else ""
        short_name = (
            (target_sym.metadata.get("short_name") if target_sym.metadata else None)
            or (re.split(r"[.:]+", target_sym.name)[-1] if ("." in target_sym.name or "::" in target_sym.name) else target_sym.name)
        )
        if not parent_cls or not short_name:
            return result_ids

        class_bases: Dict[str, Set[str]] = defaultdict(set)
        base_derived: Dict[str, Set[str]] = defaultdict(set)
        for sym in idx.symbols.values():
            if not sym.metadata:
                continue
            b_types = sym.metadata.get("base_types")
            if b_types and isinstance(b_types, (list, tuple)):
                cls_short = sym.metadata.get("short_name") or re.split(r"[.:]+", sym.name)[-1]
                for bt in b_types:
                    if bt:
                        class_bases[cls_short].add(str(bt))
                        base_derived[str(bt)].add(cls_short)

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
            return result_ids

        for sym in idx.symbols.values():
            if sym.id == target_sym.id or not sym.metadata:
                continue
            s_parent = sym.metadata.get("parent_scope") or ""
            s_short = sym.metadata.get("short_name") or ""
            if s_short == short_name and s_parent in related_classes:
                result_ids.append(sym.id)

        return result_ids

    def find_target_symbol(
        self,
        query: str,
        space: Optional[str] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Optional[UnifiedSymbol]:
        """精準透過 SymbolSelector 微型語法或語意定位目標 UnifiedSymbol"""
        idx = self._ensure_index_fn()
        query_clean = query.strip()
        if not query_clean or not idx:
            return None

        norm_ftypes = self.normalize_ftypes(ftypes)
        from .selector import SymbolSelector
        all_space_pool = [sym for sym in idx.symbols.values() if (not space or space in sym.spaces)]
        filtered_pool = [sym for sym in all_space_pool if self.matches_topology_filter(sym, norm_ftypes)]
        pool = filtered_pool if (filtered_pool or norm_ftypes) else all_space_pool

        matches = SymbolSelector.find_matches(query_clean, pool)
        if matches:
            return matches[0]

        candidates: List[UnifiedSymbol] = []
        for sym in pool:
            if sym.name == query_clean:
                return sym
            if sym.name.endswith(f".{query_clean}") or sym.name.endswith(f"::{query_clean}") or query_clean.endswith(f".{sym.name}"):
                candidates.append(sym)

        if candidates:
            return candidates[0]

        flt = QueryFilter(spaces=[space] if space else None, ftypes=norm_ftypes, limit=10)
        raw_results = self.bm25_engine.search(query=query_clean, index=idx, filter_cfg=flt)
        for r in raw_results:
            if self.matches_topology_filter(r.symbol, norm_ftypes):
                return r.symbol
        if raw_results and not norm_ftypes:
            return raw_results[0].symbol

        return None

    def _resolve_target_with_ftype_fallback(
        self,
        target_query: str,
        space: Optional[str],
        norm_ftypes: Optional[List[str]],
    ) -> Optional[UnifiedSymbol]:
        if norm_ftypes and not all(ft in ("md", "markdown") for ft in norm_ftypes):
            target_sym = self.find_target_symbol(target_query, space=space, ftypes=norm_ftypes)
            if not target_sym:
                target_sym = self.find_target_symbol(target_query, space=space)
        else:
            target_sym = self.find_target_symbol(target_query, space=space)
            if not target_sym and norm_ftypes:
                target_sym = self.find_target_symbol(target_query, space=space, ftypes=norm_ftypes)
        return target_sym

    def callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """查詢指定符號之上游調用者清單"""
        idx = self._ensure_index_fn()
        norm_ftypes = self.normalize_ftypes(ftypes)
        target_sym = self._resolve_target_with_ftype_fallback(target_query, space, norm_ftypes)

        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "callers": [],
                "total_callers": 0,
            }

        graph = self._get_graph_fn()
        target_ids = self.expand_contract_symbol_ids(idx, target_sym)

        caller_sites_map: Dict[str, List[Any]] = defaultdict(list)
        caller_order: List[str] = []
        for tid in target_ids:
            for cid in graph.get_callers(tid):
                if cid not in caller_sites_map:
                    caller_order.append(cid)
                for s in graph.get_call_sites(cid, tid):
                    if s not in caller_sites_map[cid]:
                        caller_sites_map[cid].append(s)

        callers_detail = []
        for cid in caller_order:
            caller_sym = idx.get_symbol(cid) if idx else None
            if not caller_sym or not self.matches_topology_filter(caller_sym, norm_ftypes):
                continue

            sites = caller_sites_map[cid]
            code_snip = None
            if snippet:
                target_ln = sites[0].line_number if sites else caller_sym.line_number
                code_snip = self.snippet_extractor.extract(
                    file_path=caller_sym.file_path,
                    line_number=target_ln,
                    context_before=2,
                    context_after=5,
                    docstring=caller_sym.docstring,
                )

            callers_detail.append({
                "symbol": caller_sym,
                "call_sites": [s.to_dict() for s in sites],
                "code_snippet": code_snip,
            })

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "callers": callers_detail,
            "total_callers": len(callers_detail),
        }

    def callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """查詢指定符號內部調用之下游被調用者清單"""
        idx = self._ensure_index_fn()
        norm_ftypes = self.normalize_ftypes(ftypes)
        target_sym = self._resolve_target_with_ftype_fallback(target_query, space, norm_ftypes)

        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "callees": [],
                "total_callees": 0,
            }

        graph = self._get_graph_fn()
        callee_ids = graph.get_callees(target_sym.id)

        callees_detail = []
        for cid in callee_ids:
            callee_sym = idx.get_symbol(cid) if idx else None
            if not callee_sym or not self.matches_topology_filter(callee_sym, norm_ftypes):
                continue

            sites = graph.get_call_sites(target_sym.id, cid)
            code_snip = None
            if snippet:
                code_snip = self.snippet_extractor.extract(
                    file_path=callee_sym.file_path,
                    line_number=callee_sym.line_number,
                    end_line=callee_sym.end_line,
                    context_before=2,
                    context_after=6,
                    docstring=callee_sym.docstring,
                )

            callees_detail.append({
                "symbol": callee_sym,
                "call_sites": [s.to_dict() for s in sites],
                "code_snippet": code_snip,
            })

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "callees": callees_detail,
            "total_callees": len(callees_detail),
        }

    def impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """分析目標符號之重構影響面擴散拓撲 (Blast Radius Analysis)"""
        idx = self._ensure_index_fn()
        norm_ftypes = self.normalize_ftypes(ftypes)
        target_sym = self._resolve_target_with_ftype_fallback(target_query, space, norm_ftypes)

        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "max_depth": depth,
                "layers": {},
                "total_impacted_symbols": 0,
                "total_impacted_files": 0,
            }

        graph = self._get_graph_fn()
        target_ids = self.expand_contract_symbol_ids(idx, target_sym)

        merged_layers_ids: Dict[int, List[str]] = defaultdict(list)
        merged_chains: Dict[str, List[str]] = {}
        seen_impacted_ids: Set[str] = set()

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

        layers_detail = {}
        all_files = set()
        total_symbols = 0

        for d, sids in sorted(merged_layers_ids.items()):
            layer_syms = []
            for sid in sids:
                sym = idx.get_symbol(sid) if idx else None
                if sym and self.matches_topology_filter(sym, norm_ftypes):
                    layer_syms.append(sym)
                    all_files.add(sym.file_path)
                    total_symbols += 1
            if layer_syms:
                layers_detail[d] = layer_syms

        filtered_chains = {
            k: v for k, v in merged_chains.items()
            if any(s.id == k for syms in layers_detail.values() for s in syms)
        }

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "max_depth": depth,
            "layers": layers_detail,
            "call_chains": filtered_chains,
            "total_impacted_symbols": total_symbols,
            "total_impacted_files": len(all_files),
        }
