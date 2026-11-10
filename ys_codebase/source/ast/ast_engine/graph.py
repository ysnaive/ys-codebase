"""
Bidirectional Call Graph Index & Impact Analysis Engine (`CallGraphIndex`) for `module:ast`.
Uses `networkx.DiGraph` and Gzip Pickle Protocol 5 persistence (`unified.graph.bin.gz`).
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Set, Tuple, Union

if TYPE_CHECKING:
    import networkx as nx

from .exceptions import ASTIndexNotFoundError, SchemaValidationError
from .io_utils import atomic_save_gzip_pickle, load_gzip_pickle
from .schema import FileSymbolGraph, SymbolCallSite, WorkspaceSymbolGraph


class _StdlibDiGraph:
    """Zero-dependency pure-Python directed graph compatible with networkx.DiGraph API."""

    def __init__(self) -> None:
        self._adj: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._pred: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def add_node(self, node: str) -> None:
        if node not in self._adj:
            self._adj[node] = {}
            self._pred[node] = {}

    def has_node(self, node: str) -> bool:
        return node in self._adj

    def remove_node(self, node: str) -> None:
        if node not in self._adj:
            return
        for v in list(self._adj[node].keys()):
            self._pred.get(v, {}).pop(node, None)
        for u in list(self._pred[node].keys()):
            self._adj.get(u, {}).pop(node, None)
        del self._adj[node]
        del self._pred[node]

    def has_edge(self, u: str, v: str) -> bool:
        return u in self._adj and v in self._adj[u]

    def add_edge(self, u: str, v: str, **attrs: Any) -> None:
        self.add_node(u)
        self.add_node(v)
        if v not in self._adj[u]:
            edge_data = dict(attrs)
            self._adj[u][v] = edge_data
            self._pred[v][u] = edge_data
        else:
            self._adj[u][v].update(attrs)

    def __getitem__(self, u: str) -> Dict[str, Dict[str, Any]]:
        return self._adj[u]

    def predecessors(self, node: str) -> List[str]:
        return list(self._pred.get(node, {}).keys())

    def successors(self, node: str) -> List[str]:
        return list(self._adj.get(node, {}).keys())

    def out_edges(self, node: Optional[str] = None) -> List[Tuple[str, str]]:
        if node is not None:
            return [(node, v) for v in self._adj.get(node, {}).keys()]
        return [(u, v) for u, nbrs in self._adj.items() for v in nbrs.keys()]

    def in_edges(self, node: Optional[str] = None) -> List[Tuple[str, str]]:
        if node is not None:
            return [(u, node) for u in self._pred.get(node, {}).keys()]
        return [(u, v) for u, nbrs in self._adj.items() for v in nbrs.keys()]

    def nodes(self) -> List[str]:
        return list(self._adj.keys())

    def edges(self) -> List[Tuple[str, str]]:
        return [(u, v) for u, nbrs in self._adj.items() for v in nbrs.keys()]

    def number_of_nodes(self) -> int:
        return len(self._adj)

    def number_of_edges(self) -> int:
        return sum(len(nbrs) for nbrs in self._adj.values())

    def copy(self) -> "_StdlibDiGraph":
        cloned = _StdlibDiGraph()
        for u, nbrs in self._adj.items():
            cloned.add_node(u)
            for v, attrs in nbrs.items():
                copied_attrs = {
                    k: (list(val) if isinstance(val, list) else val)
                    for k, val in attrs.items()
                }
                cloned.add_edge(u, v, **copied_attrs)
        return cloned


class CallGraphIndex:
    """
    Bidirectional call graph index backed by `networkx.DiGraph` and optional `WorkspaceSymbolGraph`.
    Manages caller -> callee directed edges, call site coordinates, multi-hop impact analysis,
    and incremental hot-patching with external incoming edge preservation.
    """

    def __init__(
        self,
        graph: Optional[nx.DiGraph] = None,
        workspace_graph: Optional[WorkspaceSymbolGraph] = None,
        ast_generation: int = 0,
    ):
        if graph is None:
            try:
                import networkx as nx

                graph = nx.DiGraph()
            except ImportError:
                graph = _StdlibDiGraph()
        self._graph: nx.DiGraph = graph
        self._workspace_graph: Optional[WorkspaceSymbolGraph] = workspace_graph
        self.ast_generation: int = int(ast_generation or 0)

    def clone_shallow(self) -> "CallGraphIndex":
        """Return a Copy-on-Write clone of `CallGraphIndex` with independent edge `call_sites` lists so lock-free readers never observe mid-patch mutations."""
        copied_g = self._graph.copy() if hasattr(self._graph, "copy") else None
        if copied_g is not None and hasattr(copied_g, "edges"):
            try:
                for u, v in list(copied_g.edges()):
                    edge_attrs = copied_g[u][v]
                    if "call_sites" in edge_attrs and isinstance(edge_attrs["call_sites"], list):
                        edge_attrs["call_sites"] = list(edge_attrs["call_sites"])
            except Exception:
                pass
        return CallGraphIndex(graph=copied_g, workspace_graph=None, ast_generation=self.ast_generation)

    @property
    def graph(self) -> nx.DiGraph:
        """Access underlying `networkx.DiGraph`."""
        return self._graph

    @property
    def workspace_graph(self) -> Optional[WorkspaceSymbolGraph]:
        """Access associated immutable `WorkspaceSymbolGraph` (if built via 4-Pass Linker)."""
        return self._workspace_graph

    @workspace_graph.setter
    def workspace_graph(self, val: Optional[WorkspaceSymbolGraph]) -> None:
        self._workspace_graph = val

    def attach_file_graphs(self, file_graphs: Optional[Mapping[str, FileSymbolGraph]]) -> None:
        """Hydrate `_workspace_graph` with `file_graphs` from `ASTSnapshot` when loaded from slim binary."""
        if self._workspace_graph is not None and file_graphs:
            self._workspace_graph = self._workspace_graph.with_file_graphs(file_graphs)

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

    def to_dict(self, include_file_graphs: bool = False) -> Dict[str, Any]:
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

        out: Dict[str, Any] = {
            "ast_generation": int(self.ast_generation),
            "int_to_id": nodes_list,
            "forward_graph": forward_graph,
            "reverse_graph": reverse_graph,
            "call_sites_map": call_sites_map,
        }
        if self._workspace_graph is not None:
            out["workspace_graph"] = self._workspace_graph.to_dict(include_file_graphs=include_file_graphs)
        return out

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        file_graphs: Optional[Mapping[str, FileSymbolGraph]] = None,
    ) -> "CallGraphIndex":
        if not isinstance(data, dict):
            raise SchemaValidationError("CallGraphIndex data must be a dictionary.")

        ws_graph: Optional[WorkspaceSymbolGraph] = None
        raw_ws = data.get("workspace_graph")
        if isinstance(raw_ws, WorkspaceSymbolGraph):
            ws_graph = raw_ws.with_file_graphs(file_graphs) if file_graphs else raw_ws
        elif isinstance(raw_ws, dict):
            try:
                ws_graph = WorkspaceSymbolGraph.from_dict(raw_ws, file_graphs=file_graphs)
            except SchemaValidationError:
                raise
            except Exception:
                ws_graph = None

        idx = cls(workspace_graph=ws_graph, ast_generation=int(data.get("ast_generation", 0) or 0))
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
        atomic_save_gzip_pickle(path, self.to_dict(include_file_graphs=False), compresslevel=compresslevel)

    @classmethod
    def load_binary(
        cls,
        path: Union[str, Path],
        file_graphs: Optional[Mapping[str, FileSymbolGraph]] = None,
    ) -> "CallGraphIndex":
        try:
            data = load_gzip_pickle(path, raise_on_missing=True)
        except FileNotFoundError as exc:
            raise ASTIndexNotFoundError(str(exc)) from exc
        return cls.from_dict(data, file_graphs=file_graphs)


__all__ = ["CallGraphIndex"]
