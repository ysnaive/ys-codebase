"""
Unit tests for NetworkX CallGraphIndex, TopologyLinker FQN disambiguation, and Multi-language Protocol.
"""

import os
from pathlib import Path
import sys
import tempfile
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.graph import CallGraphIndex
from knowledge_db.linker import TopologyLinker
from knowledge_db.protocol import (
    LanguageTopologyProtocol,
    TopologyProtocolRegistry,
    TreeSitterTopologyAdapter,
)
from knowledge_db.schema import (
    LanguageType,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
)


class TestNetworkXCallGraphAndLinker(YSCBTestCase):
    """
    NetworkX 調用圖譜與拓撲消歧測試套件
    """

    @require(Requirement.LOGIC)
    def test_add_and_query_edges(self):
        """FT-01: 驗證 NetworkX DiGraph 圖建立邊與雙向查詢 callers / callees"""
        graph = CallGraphIndex()
        site1 = SymbolCallSite(callee_name="b", line_number=10, caller_symbol_id="sym_a")
        site2 = SymbolCallSite(callee_name="c", line_number=20, caller_symbol_id="sym_b")

        graph.add_edge("sym_a", "sym_b", site1)
        graph.add_edge("sym_b", "sym_c", site2)

        self.assertEqual(graph.get_callers("sym_b"), ["sym_a"])
        self.assertEqual(graph.get_callees("sym_b"), ["sym_c"])
        self.assertEqual(graph.get_callers("sym_c"), ["sym_b"])
        self.assertEqual(graph.get_callees("sym_a"), ["sym_b"])

        sites = graph.get_call_sites("sym_a", "sym_b")
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].line_number, 10)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_query_impact_layers(self):
        """FT-02: 驗證多階影響面分析 (query_impact) 精確層級與調用鏈"""
        graph = CallGraphIndex()
        # 鏈條: A ➔ B ➔ Target, C ➔ Target, D ➔ A
        graph.add_edge("A", "B")
        graph.add_edge("B", "Target")
        graph.add_edge("C", "Target")
        graph.add_edge("D", "A")

        impact = graph.query_impact("Target", max_depth=3)
        self.assertEqual(impact["target_id"], "Target")

        # Layer 1: 直接調用 Target 的有 B 和 C
        self.assertEqual(set(impact["layers"].get(1, [])), {"B", "C"})

        # Layer 2: 調用 B 的有 A
        self.assertEqual(set(impact["layers"].get(2, [])), {"A"})

        # Layer 3: 調用 A 的有 D
        self.assertEqual(set(impact["layers"].get(3, [])), {"D"})

        self.assertEqual(impact["total_impacted_symbols"], 4)
        self.assertIn("Target", [edge[1] for edge in impact["call_chains"]["B"]])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cyclic_graph_resilience(self):
        """FT-03 / EC-01: 驗證循環調用圖譜 (A ➔ B ➔ C ➔ A) 走訪不陷入死循環且正確剪枝"""
        graph = CallGraphIndex()
        graph.add_edge("A", "B")
        graph.add_edge("B", "C")
        graph.add_edge("C", "A")

        impact = graph.query_impact("A", max_depth=5)
        self.assertEqual(impact["target_id"], "A")
        # 直接前驅是 C，間接前驅是 B
        self.assertEqual(set(impact["layers"].get(1, [])), {"C"})
        self.assertEqual(set(impact["layers"].get(2, [])), {"B"})
        # 循環回 A 時被 visited 剪枝，不再產生 Layer 3
        self.assertNotIn(3, impact["layers"])
        self.assertEqual(impact["total_impacted_symbols"], 2)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_fqn_disambiguation_eliminates_ghosts(self):
        """FT-06: 驗證基於 FQN 與 Import 作用域消歧，徹底杜絕跨檔案同名幽靈關聯"""
        sym_file_a_run = UnifiedSymbol(
            id="sym_a_run",
            name="run",
            kind=SymbolKind.FUNCTION.value,
            file_path="src/service_a.py",
            line_number=5,
            language=LanguageType.PYTHON.value,
            fqn="service_a.run",
            metadata={"space": "main"},
        )
        sym_file_b_run = UnifiedSymbol(
            id="sym_b_run",
            name="run",
            kind=SymbolKind.FUNCTION.value,
            file_path="src/service_b.py",
            line_number=5,
            language=LanguageType.PYTHON.value,
            fqn="service_b.run",
            metadata={"space": "main"},
        )
        sym_caller = UnifiedSymbol(
            id="sym_caller",
            name="execute",
            kind=SymbolKind.FUNCTION.value,
            file_path="src/caller.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            fqn="caller.execute",
            metadata={"space": "main"},
        )

        symbols_map = {
            sym_file_a_run.id: sym_file_a_run,
            sym_file_b_run.id: sym_file_b_run,
            sym_caller.id: sym_caller,
        }
        linker = TopologyLinker(symbols_map=symbols_map)

        # 案例 1: caller.py 內調用 naked 'run()'，但並未 import 任何 service (典型幽靈調用)
        naked_site = SymbolCallSite(
            callee_name="run",
            line_number=11,
            caller_member_name="execute",
            caller_symbol_id="sym_caller",
            context_prefix="",
            file_path="src/caller.py",
            space="main",
        )
        # 舊實作會隨意連到 service_a.run 或 service_b.run；新實作應嚴格判定為 None (杜絕幽靈關聯)
        resolved_naked = linker.resolve_call_site(naked_site, file_imports={})
        self.assertIsNone(resolved_naked)

        # 案例 2: caller.py 顯式 import 'from service_b import run'
        imported_site = SymbolCallSite(
            callee_name="run",
            line_number=12,
            caller_member_name="execute",
            caller_symbol_id="sym_caller",
            context_prefix="",
            file_path="src/caller.py",
            space="main",
        )
        resolved_imported = linker.resolve_call_site(imported_site, file_imports={"run": "service_b.run"})
        self.assertEqual(resolved_imported, sym_file_b_run.id)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_topology_protocol_interface(self):
        """FT-07: 驗證多語言調用拓撲協議與適配器介面合規性"""
        class MockDriver:
            def extract_call_sites(self, file_path, content, space):
                return [SymbolCallSite(callee_name="mock_call", line_number=1, file_path=file_path)]

            def extract_imports(self, file_path, content):
                return {"foo": "bar"}

        adapter = TreeSitterTopologyAdapter(MockDriver())
        self.assertIsInstance(adapter, LanguageTopologyProtocol)

        sites = adapter.extract_call_sites("test.ts", "foo()", "main")
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].callee_name, "mock_call")

        imports = adapter.extract_imports("test.ts", "import foo from bar")
        self.assertEqual(imports, {"foo": "bar"})

        # 驗證 Registry
        TopologyProtocolRegistry.register("typescript", adapter)
        self.assertTrue(TopologyProtocolRegistry.has("typescript"))
        self.assertEqual(TopologyProtocolRegistry.get("typescript"), adapter)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_serialization_roundtrip(self):
        """FT-08: 驗證 Gzip Protocol 5 二進位快取持久化與字典反序列化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "test_graph.bin.gz"

            graph = CallGraphIndex()
            site = SymbolCallSite(callee_name="method_x", line_number=42, file_path="src/test.py")
            graph.add_edge("node_a", "node_b", site)

            graph.save_binary(cache_file)
            self.assertTrue(cache_file.exists())

            loaded = CallGraphIndex.load_binary(cache_file)
            self.assertEqual(loaded.get_callers("node_b"), ["node_a"])
            self.assertEqual(loaded.get_callees("node_a"), ["node_b"])

            sites = loaded.get_call_sites("node_a", "node_b")
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0].line_number, 42)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_isolated_node_queries(self):
        """ET-02 / EC-04: 邊界測試 - 孤立節點與空圖查詢安全性"""
        graph = CallGraphIndex()

        self.assertEqual(graph.get_callers("non_existent"), [])
        self.assertEqual(graph.get_callees("non_existent"), [])
        self.assertEqual(graph.get_call_sites("non_existent"), [])

        impact = graph.query_impact("non_existent")
        self.assertEqual(impact["total_impacted_symbols"], 0)
        self.assertEqual(impact["layers"], {})

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
