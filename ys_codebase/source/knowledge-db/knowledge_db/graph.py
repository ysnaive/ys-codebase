"""
knowledge-db 雙向符號調用圖譜索引與影響面分析引擎 (CallGraphIndex)
100% 採用 networkx.DiGraph 工業級有向圖模型與 Gzip Protocol 5 二進位快取
"""

from collections import defaultdict, deque
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx

from .exceptions import SchemaValidationError
from .io_utils import atomic_save_gzip_pickle, load_gzip_pickle
from .schema import SymbolCallSite

logger = logging.getLogger("knowledge-db.graph")


class CallGraphIndex:
    """
    雙向調用圖譜索引
    以 networkx.DiGraph 為核心資料模型，管理符號調用邊 (Caller -> Callee)，
    支援高精度多階影響面分析 (query_impact) 與 JIT 增量熱重載修補。
    """

    def __init__(self, graph: Optional[nx.DiGraph] = None):
        self._graph: nx.DiGraph = graph if graph is not None else nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        """存取底層 NetworkX DiGraph 物件"""
        return self._graph

    def add_edge(
        self,
        caller_symbol_id: str,
        callee_symbol_id: str,
        call_site: Optional[SymbolCallSite] = None,
    ) -> None:
        """建立 caller -> callee 雙向調用邊"""
        if not caller_symbol_id or not callee_symbol_id:
            return

        u = str(caller_symbol_id)
        v = str(callee_symbol_id)

        if not self._graph.has_edge(u, v):
            self._graph.add_edge(u, v, call_sites=[])
        if call_site is not None:
            self._graph[u][v]["call_sites"].append(call_site)

    def remove_symbol_edges(self, symbol_ids: Set[str]) -> None:
        """拔除指定 symbol_ids 所屬之所有出入度邊與調用點"""
        if not symbol_ids:
            return
        for sid in symbol_ids:
            if self._graph.has_node(sid):
                self._graph.remove_node(sid)

    def get_callers(self, symbol_id: str) -> List[str]:
        """取得目標符號的直接上游調用者 (Caller) symbol_id 清單"""
        if not symbol_id or not self._graph.has_node(symbol_id):
            return []
        return sorted(list(self._graph.predecessors(symbol_id)))

    def get_callees(self, symbol_id: str) -> List[str]:
        """取得目標符號內部直接調用的下游被調用者 (Callee) symbol_id 清單"""
        if not symbol_id or not self._graph.has_node(symbol_id):
            return []
        return sorted(list(self._graph.successors(symbol_id)))

    def get_call_sites(self, caller_id: str, callee_id: Optional[str] = None) -> List[SymbolCallSite]:
        """取得指定調用者與被調用者之間的調用點清單"""
        if not caller_id:
            return []
        if callee_id is not None:
            if self._graph.has_edge(caller_id, callee_id):
                return list(self._graph[caller_id][callee_id].get("call_sites", []))
            return []

        sites: List[SymbolCallSite] = []
        if self._graph.has_node(caller_id):
            for _, v in self._graph.out_edges(caller_id):
                sites.extend(self._graph[caller_id][v].get("call_sites", []))
        return sites

    def query_impact(self, target_symbol_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """基於 NetworkX 有向圖逆向走訪分析重構影響面擴散拓撲 (具備 visited 剪枝循環防護)"""
        if not target_symbol_id or not self._graph.has_node(target_symbol_id):
            return {
                "target_id": target_symbol_id,
                "max_depth": max_depth,
                "layers": {},
                "call_chains": {},
                "total_impacted_symbols": 0,
            }

        visited: Set[str] = {target_symbol_id}
        layers: Dict[int, List[str]] = {}
        call_chains: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        queue: deque = deque([(target_symbol_id, 0)])

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue

            next_depth = depth + 1
            for caller in self.get_callers(curr):
                call_chains[caller].append((caller, curr))
                if caller not in visited:
                    visited.add(caller)
                    if next_depth not in layers:
                        layers[next_depth] = []
                    layers[next_depth].append(caller)
                    queue.append((caller, next_depth))

        total_impacted = sum(len(items) for items in layers.values())
        return {
            "target_id": target_symbol_id,
            "max_depth": max_depth,
            "layers": layers,
            "call_chains": dict(call_chains),
            "total_impacted_symbols": total_impacted,
        }

    def get_external_incoming_edges(
        self,
        target_symbol_ids: Set[str],
    ) -> List[Tuple[str, str, Optional[SymbolCallSite]]]:
        """
        獲取外部符號指向指定目標符號集合的所有入度調用邊與調用點。
        排除 target_symbol_ids 內部的自我調用邊。
        :return: (caller_id, old_callee_id, call_site) 清單
        """
        if not target_symbol_ids:
            return []

        results: List[Tuple[str, str, Optional[SymbolCallSite]]] = []
        for target_id in target_symbol_ids:
            if self._graph.has_node(target_id):
                for caller_id in self._graph.predecessors(target_id):
                    if caller_id not in target_symbol_ids:
                        sites = self._graph[caller_id][target_id].get("call_sites", [])
                        if sites:
                            for s in sites:
                                results.append((caller_id, target_id, s))
                        else:
                            results.append((caller_id, target_id, None))
        return results

    def patch_incremental(
        self,
        new_edges: List[Tuple[str, str, SymbolCallSite]],
        old_symbol_ids: Set[str],
    ) -> None:
        """差量修補調用圖譜 (拔除舊符號出入度邊並重新注入 new_edges，移除未使用參數 dirty_file_paths M-10)"""
        if old_symbol_ids:
            self.remove_symbol_edges(old_symbol_ids)
        for caller_id, callee_id, site in new_edges:
            self.add_edge(caller_id, callee_id, site)

    def to_dict(self) -> Dict[str, Any]:
        """序列化圖譜為字典格式"""
        nodes_list = list(self._graph.nodes())
        id_to_int = {sid: i for i, sid in enumerate(nodes_list)}

        forward_graph: Dict[str, List[int]] = {}
        reverse_graph: Dict[str, List[int]] = {}
        call_sites_map: Dict[str, List[Dict[str, Any]]] = {}

        for u in nodes_list:
            u_int = id_to_int[u]
            succs = list(self._graph.successors(u))
            if succs:
                forward_graph[str(u_int)] = [id_to_int[v] for v in succs if v in id_to_int]

            preds = list(self._graph.predecessors(u))
            if preds:
                reverse_graph[str(u_int)] = [id_to_int[p] for p in preds if p in id_to_int]

        for u, v in self._graph.edges():
            if u in id_to_int and v in id_to_int:
                sites = self._graph[u][v].get("call_sites", [])
                if sites:
                    key = f"{id_to_int[u]}:{id_to_int[v]}"
                    call_sites_map[key] = [s.to_dict() for s in sites]

        return {
            "int_to_id": nodes_list,
            "forward_graph": forward_graph,
            "reverse_graph": reverse_graph,
            "call_sites_map": call_sites_map,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallGraphIndex":
        """反序列化圖譜字典"""
        if not isinstance(data, dict):
            raise SchemaValidationError("CallGraphIndex data must be a dictionary.")

        idx = cls()
        int_to_id: List[str] = list(data.get("int_to_id", []))
        raw_fwd = data.get("forward_graph", {})
        raw_sites = data.get("call_sites_map", {})

        parsed_sites: Dict[Tuple[int, int], List[SymbolCallSite]] = defaultdict(list)
        for key_str, sites in raw_sites.items():
            if ":" in key_str:
                u_s, v_s = key_str.split(":", 1)
                u_int, v_int = int(u_s), int(v_s)
                parsed_sites[(u_int, v_int)] = [
                    SymbolCallSite.from_dict(s) if isinstance(s, dict) else s
                    for s in sites
                ]

        for u_str, vs in raw_fwd.items():
            u_int = int(u_str)
            if u_int < len(int_to_id):
                u_id = int_to_id[u_int]
                for v_int in vs:
                    if v_int < len(int_to_id):
                        v_id = int_to_id[v_int]
                        sites_for_edge = parsed_sites.get((u_int, v_int), [])
                        if sites_for_edge:
                            for s in sites_for_edge:
                                idx.add_edge(u_id, v_id, s)
                        else:
                            idx.add_edge(u_id, v_id, None)

        return idx

    def save_binary(self, path: Union[str, Path], compresslevel: int = 1) -> None:
        """使用 io_utils 原子持久化二進位圖索引"""
        atomic_save_gzip_pickle(path, self.to_dict(), compresslevel=compresslevel)

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "CallGraphIndex":
        """自二進位 Gzip 快取反序列化 CallGraphIndex"""
        data = load_gzip_pickle(path, raise_on_missing=True)
        return cls.from_dict(data)
