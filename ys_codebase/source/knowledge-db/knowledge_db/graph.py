"""
knowledge-db 雙向符號調用圖譜索引與影響面分析引擎 (CallGraphIndex)
採用整數池化 (Integer Pool)、雙向稀疏鄰接表與 Gzip Protocol 5 二進位快取
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import defaultdict, deque
import gzip
import logging
import os
from pathlib import Path
import pickle
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .exceptions import KnowledgeDBError, SchemaValidationError
from .schema import SymbolCallSite

logger = logging.getLogger("knowledge-db.graph")


class CallGraphIndex:
    """
    雙向調用圖譜索引
    管理符號調用邊 (Caller ⇄ Callee)，支援多階影響面分析與 JIT 增量熱重載修補。
    """

    def __init__(self):
        self.id_to_int: Dict[str, int] = {}
        self.int_to_id: List[str] = []
        self.forward_graph: Dict[int, Set[int]] = defaultdict(set)  # caller -> {callee}
        self.reverse_graph: Dict[int, Set[int]] = defaultdict(set)  # callee -> {caller}
        self.call_sites_map: Dict[Tuple[int, int], List[SymbolCallSite]] = defaultdict(list)

    def get_or_register_id(self, symbol_id: str) -> int:
        """獲取或註冊 symbol_id 之整數標識符 (Integer Pool)"""
        if symbol_id not in self.id_to_int:
            new_int = len(self.int_to_id)
            self.id_to_int[symbol_id] = new_int
            self.int_to_id.append(symbol_id)
            return new_int
        return self.id_to_int[symbol_id]

    def get_id(self, int_val: int) -> Optional[str]:
        """由整數還原 symbol_id"""
        if 0 <= int_val < len(self.int_to_id):
            return self.int_to_id[int_val]
        return None

    def add_edge(
        self,
        caller_symbol_id: str,
        callee_symbol_id: str,
        call_site: Optional[SymbolCallSite] = None,
    ) -> None:
        """建立 caller ➔ callee 雙向調用邊"""
        if not caller_symbol_id or not callee_symbol_id:
            return

        u = self.get_or_register_id(caller_symbol_id)
        v = self.get_or_register_id(callee_symbol_id)

        self.forward_graph[u].add(v)
        self.reverse_graph[v].add(u)

        if call_site is not None:
            self.call_sites_map[(u, v)].append(call_site)

    def remove_symbol_edges(self, symbol_ids: Set[str]) -> None:
        """
        拔除指定 symbol_ids 所屬之所有出入度邊與調用點
        """
        int_ids = {self.id_to_int[sid] for sid in symbol_ids if sid in self.id_to_int}
        if not int_ids:
            return

        for u in int_ids:
            # 1. 拔除 u 作為 caller 的所有出度邊
            callees = list(self.forward_graph.get(u, []))
            for v in callees:
                if v in self.reverse_graph and u in self.reverse_graph[v]:
                    self.reverse_graph[v].discard(u)
                    if not self.reverse_graph[v]:
                        del self.reverse_graph[v]
                self.call_sites_map.pop((u, v), None)
            self.forward_graph.pop(u, None)

            # 2. 拔除 u 作為 callee 的所有入度邊
            callers = list(self.reverse_graph.get(u, []))
            for c in callers:
                if c in self.forward_graph and u in self.forward_graph[c]:
                    self.forward_graph[c].discard(u)
                    if not self.forward_graph[c]:
                        del self.forward_graph[c]
                self.call_sites_map.pop((c, u), None)
            self.reverse_graph.pop(u, None)

    def get_callers(self, symbol_id: str) -> List[str]:
        """取得目標符號的直接上游調用者 symbol_id 清單"""
        if symbol_id not in self.id_to_int:
            return []
        v = self.id_to_int[symbol_id]
        caller_ints = self.reverse_graph.get(v, set())
        return [self.int_to_id[u] for u in caller_ints if u < len(self.int_to_id)]

    def get_callees(self, symbol_id: str) -> List[str]:
        """取得目標符號內部直接調用的下游被調用者 symbol_id 清單"""
        if symbol_id not in self.id_to_int:
            return []
        u = self.id_to_int[symbol_id]
        callee_ints = self.forward_graph.get(u, set())
        return [self.int_to_id[v] for v in callee_ints if v < len(self.int_to_id)]

    def get_call_sites(self, caller_id: str, callee_id: Optional[str] = None) -> List[SymbolCallSite]:
        """取得指定調用者與被調用者之間的調用點清單"""
        if caller_id not in self.id_to_int:
            return []
        u = self.id_to_int[caller_id]

        if callee_id is not None:
            if callee_id not in self.id_to_int:
                return []
            v = self.id_to_int[callee_id]
            return list(self.call_sites_map.get((u, v), []))
        else:
            # 取得 caller 的所有調用點
            res: List[SymbolCallSite] = []
            for (c, v), sites in self.call_sites_map.items():
                if c == u:
                    res.extend(sites)
            return res

    def query_impact(self, target_symbol_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        使用廣度優先走訪 (BFS) 分析重構影響面擴散拓撲 (具備 visited_set 循環防護)
        """
        if target_symbol_id not in self.id_to_int:
            return {
                "target_id": target_symbol_id,
                "max_depth": max_depth,
                "layers": {},
                "call_chains": {},
                "total_impacted_symbols": 0,
            }

        start_v = self.id_to_int[target_symbol_id]
        visited: Set[int] = {start_v}
        layers: Dict[int, List[str]] = {}
        call_chains: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        queue: deque = deque([(start_v, 0)])  # (current_node, current_depth)

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue

            next_depth = depth + 1
            callers = self.reverse_graph.get(curr, set())

            for caller in callers:
                caller_sid = self.int_to_id[caller]
                curr_sid = self.int_to_id[curr]
                call_chains[caller_sid].append((caller_sid, curr_sid))

                if caller not in visited:
                    visited.add(caller)
                    if next_depth not in layers:
                        layers[next_depth] = []
                    layers[next_depth].append(caller_sid)
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
        """序列化圖譜為字典格式"""
        serialized_sites = {}
        for (u, v), sites in self.call_sites_map.items():
            key = f"{u}:{v}"
            serialized_sites[key] = [s.to_dict() for s in sites]

        return {
            "int_to_id": self.int_to_id,
            "forward_graph": {str(u): list(vs) for u, vs in self.forward_graph.items()},
            "reverse_graph": {str(v): list(us) for v, us in self.reverse_graph.items()},
            "call_sites_map": serialized_sites,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallGraphIndex":
        """反序列化圖譜字典"""
        if not isinstance(data, dict):
            raise SchemaValidationError("CallGraphIndex data must be a dictionary.")

        idx = cls()
        idx.int_to_id = list(data.get("int_to_id", []))
        idx.id_to_int = {sid: i for i, sid in enumerate(idx.int_to_id)}

        raw_fwd = data.get("forward_graph", {})
        for u_str, vs in raw_fwd.items():
            idx.forward_graph[int(u_str)] = set(vs)

        raw_rev = data.get("reverse_graph", {})
        for v_str, us in raw_rev.items():
            idx.reverse_graph[int(v_str)] = set(us)

        raw_sites = data.get("call_sites_map", {})
        for key_str, sites in raw_sites.items():
            if ":" in key_str:
                u_s, v_s = key_str.split(":", 1)
                idx.call_sites_map[(int(u_s), int(v_s))] = [
                    SymbolCallSite.from_dict(s) if isinstance(s, dict) else s
                    for s in sites
                ]

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
