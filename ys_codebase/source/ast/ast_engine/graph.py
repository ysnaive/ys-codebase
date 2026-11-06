"""
Bidirectional Call Graph Index & Impact Analysis Engine (`CallGraphIndex`) for `module:ast`.
Uses `networkx.DiGraph` and Gzip Pickle Protocol 5 persistence (`unified.graph.bin.gz`).
"""

from __future__ import annotations

from collections import defaultdict, deque
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union

if TYPE_CHECKING:
    import networkx as nx

from .exceptions import ASTIndexNotFoundError, SchemaValidationError
from .io_utils import atomic_save_gzip_pickle, load_gzip_pickle
from .schema import SymbolCallSite

logger = logging.getLogger("ast.graph")


class CallGraphIndex:
    """
    Bidirectional call graph index backed by `networkx.DiGraph`.
    Manages caller -> callee directed edges, call site coordinates, multi-hop impact analysis,
    and incremental hot-patching with external incoming edge preservation.
    """

    def __init__(self, graph: Optional[nx.DiGraph] = None):
        if graph is None:
            import networkx as nx

            graph = nx.DiGraph()
        self._graph: nx.DiGraph = graph

    @property
    def graph(self) -> nx.DiGraph:
        """Access underlying `networkx.DiGraph`."""
        return self._graph

    def add_edge(
        self,
        caller_symbol_id: str,
        callee_symbol_id: str,
        call_site: Optional[SymbolCallSite] = None,
    ) -> None:
        """Add directed call edge `caller_symbol_id -> callee_symbol_id`."""
        if not caller_symbol_id or not callee_symbol_id:
            return

        u = str(caller_symbol_id)
        v = str(callee_symbol_id)

        if not self._graph.has_edge(u, v):
            self._graph.add_edge(u, v, call_sites=[])
        if call_site is not None:
            if isinstance(call_site, dict):
                call_site = SymbolCallSite.from_dict(call_site)
            existing = self._graph[u][v]["call_sites"]
            if call_site not in existing:
                existing.append(call_site)

    def remove_symbol_edges(self, symbol_ids: Union[str, Set[str], List[str]]) -> None:
        """Remove all incoming and outgoing edges for `symbol_ids`."""
        if not symbol_ids:
            return
        if isinstance(symbol_ids, str):
            symbol_ids = {symbol_ids}
        for sid in symbol_ids:
            if self._graph.has_node(sid):
                self._graph.remove_node(sid)

    def get_callers(self, symbol_id: str) -> List[str]:
        """Return sorted list of direct upstream caller symbol IDs for `symbol_id`."""
        if not symbol_id or not self._graph.has_node(symbol_id):
            return []
        return sorted(list(self._graph.predecessors(symbol_id)))

    def get_callees(self, symbol_id: str) -> List[str]:
        """Return sorted list of direct downstream callee symbol IDs for `symbol_id`."""
        if not symbol_id or not self._graph.has_node(symbol_id):
            return []
        return sorted(list(self._graph.successors(symbol_id)))

    def get_call_sites(self, caller_id: str, callee_id: Optional[str] = None) -> List[SymbolCallSite]:
        """Return `SymbolCallSite` list between `caller_id` and `callee_id`."""
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

    def query_impact(
        self,
        target_symbol_id: Union[str, Set[str], List[str]],
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Reverse BFS impact analysis starting from `target_symbol_id` (single ID or set/list of IDs).
        Returns `{"target_id", "max_depth", "layers": {hop: [symbol_ids]}, "call_chains": {...}, "total_impacted_symbols": int}`.
        """
        if not target_symbol_id:
            return {
                "target_id": target_symbol_id,
                "max_depth": max_depth,
                "layers": {},
                "call_chains": {},
                "total_impacted_symbols": 0,
            }

        if isinstance(target_symbol_id, str):
            seed_ids = [target_symbol_id] if self._graph.has_node(target_symbol_id) else []
        else:
            seed_ids = [sid for sid in target_symbol_id if sid and self._graph.has_node(sid)]

        if not seed_ids:
            return {
                "target_id": target_symbol_id,
                "max_depth": max_depth,
                "layers": {},
                "call_chains": {},
                "total_impacted_symbols": 0,
            }

        visited: Set[str] = set(seed_ids)
        layers: Dict[int, List[str]] = {}
        call_chains: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        queue: deque = deque((sid, 0) for sid in seed_ids)

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue

            next_depth = depth + 1
            for caller in self.get_callers(curr):
                call_chains[caller].append((caller, curr))
                if caller not in visited:
                    visited.add(caller)
                    layers.setdefault(next_depth, []).append(caller)
                    queue.append((caller, next_depth))

        total_impacted = sum(len(items) for items in layers.values())
        return {
            "target_id": target_symbol_id if isinstance(target_symbol_id, str) else list(seed_ids),
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
        Return all incoming edges `(caller_id, old_callee_id, call_site)` from external symbols
        pointing to `target_symbol_ids` (excluding edges where `caller_id` is in `target_symbol_ids`).
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
        new_edges: List[Tuple[str, str, Optional[SymbolCallSite]]],
        old_symbol_ids: Set[str],
    ) -> None:
        """Incrementally patch the call graph by removing `old_symbol_ids` and adding `new_edges`."""
        if old_symbol_ids:
            self.remove_symbol_edges(old_symbol_ids)
        for caller_id, callee_id, site in new_edges:
            self.add_edge(caller_id, callee_id, site)

    def to_dict(self) -> Dict[str, Any]:
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
                    call_sites_map[key] = [
                        s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in sites
                    ]

        return {
            "int_to_id": nodes_list,
            "forward_graph": forward_graph,
            "reverse_graph": reverse_graph,
            "call_sites_map": call_sites_map,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallGraphIndex":
        if not isinstance(data, dict):
            raise SchemaValidationError("CallGraphIndex data must be a dictionary.")

        idx = cls()
        raw_ids = data.get("int_to_id") or []
        int_to_id: List[str] = [str(x) for x in raw_ids] if isinstance(raw_ids, (list, tuple)) else []
        raw_fwd = data.get("forward_graph")
        fwd_dict = raw_fwd if isinstance(raw_fwd, dict) else {}
        raw_sites = data.get("call_sites_map")
        sites_dict = raw_sites if isinstance(raw_sites, dict) else {}

        parsed_sites: Dict[Tuple[int, int], List[SymbolCallSite]] = defaultdict(list)
        for key_str, sites in sites_dict.items():
            if isinstance(key_str, str) and ":" in key_str and isinstance(sites, (list, tuple)):
                u_s, v_s = key_str.split(":", 1)
                try:
                    u_int, v_int = int(u_s), int(v_s)
                except ValueError:
                    continue
                parsed_sites[(u_int, v_int)] = [
                    SymbolCallSite.from_dict(s) if isinstance(s, dict) else s
                    for s in sites
                    if s is not None
                ]

        for u_str, vs in fwd_dict.items():
            if not isinstance(vs, (list, tuple)):
                continue
            try:
                u_int = int(u_str)
            except (ValueError, TypeError):
                continue
            if 0 <= u_int < len(int_to_id):
                u_id = int_to_id[u_int]
                for v_raw in vs:
                    try:
                        v_int = int(v_raw)
                    except (ValueError, TypeError):
                        continue
                    if 0 <= v_int < len(int_to_id):
                        v_id = int_to_id[v_int]
                        sites_for_edge = parsed_sites.get((u_int, v_int), [])
                        if sites_for_edge:
                            for s in sites_for_edge:
                                idx.add_edge(u_id, v_id, s)
                        else:
                            idx.add_edge(u_id, v_id, None)

        return idx

    def save_binary(self, path: Union[str, Path], compresslevel: int = 1) -> None:
        atomic_save_gzip_pickle(path, self.to_dict(), compresslevel=compresslevel)

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "CallGraphIndex":
        try:
            data = load_gzip_pickle(path, raise_on_missing=True)
        except FileNotFoundError as exc:
            raise ASTIndexNotFoundError(str(exc)) from exc
        return cls.from_dict(data)


__all__ = ["CallGraphIndex"]
