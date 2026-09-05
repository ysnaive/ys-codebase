"""
knowledge-db 雙向符號調用圖譜索引與影響面分析引擎 (CallGraphIndex)
採用 networkx.DiGraph 工業級有向圖模型與 Gzip Protocol 5 二進位快取
"""

from collections import defaultdict, deque
import gzip
import logging
import os
from pathlib import Path
import pickle
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import networkx as nx
except ImportError:
    nx = None

from .exceptions import KnowledgeDBError, SchemaValidationError
from .schema import SymbolCallSite

logger = logging.getLogger("knowledge-db.graph")


class CallGraphIndex:
    """
    雙向調用圖譜索引
    以 networkx.DiGraph 為核心資料模型，管理符號調用邊 (Caller ➔ Callee)，
    支援高精度多階影響面分析 (query_impact) 與 JIT 增量熱重載修補。
    """

    def __init__(self, graph: Optional[Any] = None):
        if nx is not None:
            self._graph = graph if graph is not None else nx.DiGraph()
        else:
            # 純原生 Python 降級相容圖
            self._graph = None
            self._forward: Dict[str, Set[str]] = defaultdict(set)
            self._reverse: Dict[str, Set[str]] = defaultdict(set)
            self._sites: Dict[Tuple[str, str], List[SymbolCallSite]] = defaultdict(list)

    @property
    def graph(self) -> Any:
        """存取底層 NetworkX DiGraph 物件"""
        return self._graph

    def add_edge(
        self,
        caller_symbol_id: str,
        callee_symbol_id: str,
        call_site: Optional[SymbolCallSite] = None,
    ) -> None:
        """建立 caller ➔ callee 雙向調用邊"""
        if not caller_symbol_id or not callee_symbol_id:
            return

        u = str(caller_symbol_id)
        v = str(callee_symbol_id)

        if self._graph is not None:
            if not self._graph.has_edge(u, v):
                self._graph.add_edge(u, v, call_sites=[])
            if call_site is not None:
                self._graph[u][v]["call_sites"].append(call_site)
        else:
            self._forward[u].add(v)
            self._reverse[v].add(u)
            if call_site is not None:
                self._sites[(u, v)].append(call_site)

    def remove_symbol_edges(self, symbol_ids: Set[str]) -> None:
        """拔除指定 symbol_ids 所屬之所有出入度邊與調用點"""
        if not symbol_ids:
            return

        if self._graph is not None:
            for sid in symbol_ids:
                if self._graph.has_node(sid):
                    self._graph.remove_node(sid)
        else:
            for sid in symbol_ids:
                # 拔除出度邊
                callees = list(self._forward.pop(sid, set()))
                for v in callees:
                    if v in self._reverse:
                        self._reverse[v].discard(sid)
                        if not self._reverse[v]:
                            del self._reverse[v]
                    self._sites.pop((sid, v), None)

                # 拔除入度邊
                callers = list(self._reverse.pop(sid, set()))
                for c in callers:
                    if c in self._forward:
                        self._forward[c].discard(sid)
                        if not self._forward[c]:
                            del self._forward[c]
                    self._sites.pop((c, sid), None)

    def get_callers(self, symbol_id: str) -> List[str]:
        """取得目標符號的直接上游調用者 (Caller) symbol_id 清單"""
        if not symbol_id:
            return []

        if self._graph is not None:
            if self._graph.has_node(symbol_id):
                return sorted(list(self._graph.predecessors(symbol_id)))
            return []
        else:
            return sorted(list(self._reverse.get(symbol_id, set())))

    def get_callees(self, symbol_id: str) -> List[str]:
        """取得目標符號內部直接調用的下游被調用者 (Callee) symbol_id 清單"""
        if not symbol_id:
            return []

        if self._graph is not None:
            if self._graph.has_node(symbol_id):
                return sorted(list(self._graph.successors(symbol_id)))
            return []
        else:
            return sorted(list(self._forward.get(symbol_id, set())))

    def get_call_sites(self, caller_id: str, callee_id: Optional[str] = None) -> List[SymbolCallSite]:
        """取得指定調用者與被調用者之間的調用點清單"""
        if not caller_id:
            return []

        if self._graph is not None:
            if callee_id is not None:
                if self._graph.has_edge(caller_id, callee_id):
                    return list(self._graph[caller_id][callee_id].get("call_sites", []))
                return []
            else:
                sites: List[SymbolCallSite] = []
                if self._graph.has_node(caller_id):
                    for _, v in self._graph.out_edges(caller_id):
                        sites.extend(self._graph[caller_id][v].get("call_sites", []))
                return sites
        else:
            if callee_id is not None:
                return list(self._sites.get((caller_id, callee_id), []))
            else:
                sites = []
                for (u, v), s_list in self._sites.items():
                    if u == caller_id:
                        sites.extend(s_list)
                return sites

    def query_impact(self, target_symbol_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        基於 NetworkX 有向圖逆向走訪分析重構影響面擴散拓撲 (具備 visited 剪枝循環防護)
        """
        if not target_symbol_id:
            return {
                "target_id": target_symbol_id,
                "max_depth": max_depth,
                "layers": {},
                "call_chains": {},
                "total_impacted_symbols": 0,
            }

        has_node = (self._graph.has_node(target_symbol_id)) if self._graph is not None else (target_symbol_id in self._reverse or target_symbol_id in self._forward)
        if not has_node:
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
            callers = self.get_callers(curr)

            for caller in callers:
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

    def patch_incremental(
        self,
        dirty_file_paths: Set[str],
        new_edges: List[Tuple[str, str, SymbolCallSite]],
        old_symbol_ids: Set[str],
    ) -> None:
        """
        差量修補調用圖譜 (拔除 dirty 檔案舊邊並重新注入 new_edges)
        """
        # 1. 拔除舊符號的出入度邊
        if old_symbol_ids:
            self.remove_symbol_edges(old_symbol_ids)

        # 2. 注入新邊
        for caller_id, callee_id, site in new_edges:
            self.add_edge(caller_id, callee_id, site)

    def to_dict(self) -> Dict[str, Any]:
        """序列化圖譜為向後相容字典格式"""
        if self._graph is not None:
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
        else:
            all_ids = sorted(list(set(self._forward.keys()) | set(self._reverse.keys())))
            id_to_int = {sid: i for i, sid in enumerate(all_ids)}
            return {
                "int_to_id": all_ids,
                "forward_graph": {
                    str(id_to_int[u]): [id_to_int[v] for v in vs if v in id_to_int]
                    for u, vs in self._forward.items() if u in id_to_int
                },
                "reverse_graph": {
                    str(id_to_int[v]): [id_to_int[u] for u in us if u in id_to_int]
                    for v, us in self._reverse.items() if v in id_to_int
                },
                "call_sites_map": {
                    f"{id_to_int[u]}:{id_to_int[v]}": [s.to_dict() for s in sites]
                    for (u, v), sites in self._sites.items() if u in id_to_int and v in id_to_int
                },
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

        # 先解析所有調用點
        parsed_sites: Dict[Tuple[int, int], List[SymbolCallSite]] = defaultdict(list)
        for key_str, sites in raw_sites.items():
            if ":" in key_str:
                u_s, v_s = key_str.split(":", 1)
                u_int, v_int = int(u_s), int(v_s)
                parsed_sites[(u_int, v_int)] = [
                    SymbolCallSite.from_dict(s) if isinstance(s, dict) else s
                    for s in sites
                ]

        # 建立邊
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
        """使用 Pickle (Protocol 5) + Gzip 原子持久化二進位圖索引"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()
        pkl_bytes = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        compressed_bytes = gzip.compress(pkl_bytes, compresslevel=compresslevel)

        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(compressed_bytes)

        os.replace(str(tmp_path), str(out_path))
        logger.debug(f"Saved binary call graph index to: {out_path} ({len(compressed_bytes)} bytes)")

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "CallGraphIndex":
        """自二進位 Gzip 快取反序列化 CallGraphIndex"""
        in_path = Path(path)
        if not in_path.exists():
            raise FileNotFoundError(f"Binary call graph index cache not found: {in_path}")

        with open(in_path, "rb") as f:
            compressed_bytes = f.read()

        pkl_bytes = gzip.decompress(compressed_bytes)
        data = pickle.loads(pkl_bytes)
        return cls.from_dict(data)
