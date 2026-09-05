"""
Unit and Integration Tests for Knowledge-DB NetworkX CallGraphIndex, TopologyLinker, and Multi-language Protocols.
Unified Suite consolidating test_networkx_graph.py and test_call_graph.py.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.graph import CallGraphIndex
from knowledge_db.linker import TopologyLinker
from knowledge_db.parsers import (
    CppParser,
    CSharpParser,
    JsTsParser,
    MarkdownParser,
    PythonParser,
)
from knowledge_db.protocol import (
    LanguageTopologyProtocol,
    TopologyProtocolRegistry,
    TreeSitterTopologyAdapter,
)
from knowledge_db.schema import (
    CallGraphNode,
    LanguageType,
    SpaceConfig,
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


class TestCallGraphAndReferenceIndex(YSCBTestCase):
    """
    調用圖譜與引用拓撲完整測試套件
    """

    @require(Requirement.LOGIC)
    def test_ft_01_schema_call_site_models(self):
        """FT-01: 驗證 SymbolCallSite 與 CallGraphNode 模型與序列化"""
        site = SymbolCallSite(
            callee_name="load_binary",
            line_number=42,
            caller_symbol_id="caller_123",
            caller_member_name="KnowledgeEngine.build",
            context_prefix="InvertedIndex",
            file_path="src/engine.py",
            space="project",
        )
        d = site.to_dict()
        self.assertEqual(d["callee_name"], "load_binary")
        self.assertEqual(d["line_number"], 42)
        self.assertEqual(d["context_prefix"], "InvertedIndex")

        restored_site = SymbolCallSite.from_dict(d)
        self.assertEqual(restored_site, site)

        node = CallGraphNode(
            symbol_id="sym_1",
            callers={"caller_a", "caller_b"},
            callees={"callee_c"},
            call_sites=[site],
        )
        node_d = node.to_dict()
        self.assertIn("caller_a", node_d["callers"])
        self.assertEqual(len(node_d["call_sites"]), 1)

        restored_node = CallGraphNode.from_dict(node_d)
        self.assertEqual(restored_node.symbol_id, "sym_1")
        self.assertEqual(restored_node.callers, {"caller_a", "caller_b"})

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_python_parser_call_sites_and_imports(self):
        """FT-02: 驗證 PythonParser 萃取調用點、作用域與 Import 表"""
        code = """
from knowledge_db.retrieval import InvertedIndex as LocalIndex
import os.path

class MyEngine:
    def __init__(self):
        self.setup()

    def setup(self):
        self._init_cache()

    def _init_cache(self):
        idx = LocalIndex.load_binary("cache.bin")
        p = os.path.join("a", "b")

def top_level_func():
    engine = MyEngine()
    engine.setup()
"""
        parser = PythonParser()
        symbols = parser.parse(file_path="src/my_engine.py", content=code, space="main")
        self.assertTrue(len(symbols) >= 3)

        call_sites = parser.extract_call_sites(file_path="src/my_engine.py", content=code, space="main")
        imports = parser.extract_imports(file_path="src/my_engine.py", content=code)

        # 驗證 Import 表
        self.assertEqual(imports.get("LocalIndex"), "knowledge_db.retrieval.InvertedIndex")
        self.assertEqual(imports.get("os.path"), "os.path")

        # 驗證調用點
        callees = [cs.callee_name for cs in call_sites]
        self.assertIn("setup", callees)
        self.assertIn("_init_cache", callees)
        self.assertIn("load_binary", callees)

        # 驗證作用域記錄
        load_bin_site = next(cs for cs in call_sites if cs.callee_name == "load_binary")
        self.assertEqual(load_bin_site.caller_member_name, "MyEngine._init_cache")
        self.assertEqual(load_bin_site.context_prefix, "LocalIndex")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_topology_linker_four_tier_cascade(self):
        """FT-03: 驗證 TopologyLinker 四階消歧鏈接演算法"""
        sym_engine_setup = UnifiedSymbol(
            id="sym_engine_setup",
            name="MyEngine.setup",
            kind=SymbolKind.METHOD.value,
            file_path="src/my_engine.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            metadata={"space": "main"},
        )
        sym_engine_init = UnifiedSymbol(
            id="sym_engine_init",
            name="MyEngine._init_cache",
            kind=SymbolKind.METHOD.value,
            file_path="src/my_engine.py",
            line_number=15,
            language=LanguageType.PYTHON.value,
            metadata={"space": "main"},
        )
        sym_index_load = UnifiedSymbol(
            id="sym_index_load",
            name="InvertedIndex.load_binary",
            kind=SymbolKind.METHOD.value,
            file_path="src/retrieval.py",
            line_number=50,
            language=LanguageType.PYTHON.value,
            metadata={"space": "main"},
        )

        symbols_map = {
            sym_engine_setup.id: sym_engine_setup,
            sym_engine_init.id: sym_engine_init,
            sym_index_load.id: sym_index_load,
        }

        linker = TopologyLinker(symbols_map=symbols_map)

        # 1. Tier 1 測試: self._init_cache
        site_tier1 = SymbolCallSite(
            callee_name="_init_cache",
            line_number=11,
            caller_member_name="MyEngine.setup",
            context_prefix="self",
            file_path="src/my_engine.py",
            space="main",
        )
        target_id1 = linker.resolve_call_site(site_tier1, file_imports={})
        self.assertEqual(target_id1, sym_engine_init.id)

        # 2. Tier 2 測試: LocalIndex.load_binary (透過 import LocalIndex 映射到 InvertedIndex)
        site_tier2 = SymbolCallSite(
            callee_name="load_binary",
            line_number=16,
            caller_member_name="MyEngine._init_cache",
            context_prefix="LocalIndex",
            file_path="src/my_engine.py",
            space="main",
        )
        imports = {"LocalIndex": "knowledge_db.retrieval.InvertedIndex"}
        target_id2 = linker.resolve_call_site(site_tier2, file_imports=imports)
        self.assertEqual(target_id2, sym_index_load.id)

        # 3. 批次鏈接
        edges = linker.link_call_sites([site_tier1, site_tier2], imports_map={"src/my_engine.py": imports})
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[0][0], sym_engine_setup.id)
        self.assertEqual(edges[0][1], sym_engine_init.id)
        self.assertEqual(edges[1][0], sym_engine_init.id)
        self.assertEqual(edges[1][1], sym_index_load.id)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_call_graph_index_bidirectional(self):
        """FT-04: 驗證 CallGraphIndex 雙向鄰接表與查詢"""
        graph = CallGraphIndex()
        site1 = SymbolCallSite(callee_name="b", line_number=10, caller_symbol_id="A")
        site2 = SymbolCallSite(callee_name="c", line_number=20, caller_symbol_id="B")

        graph.add_edge("A", "B", site1)
        graph.add_edge("B", "C", site2)

        # 驗證 callers 與 callees
        self.assertEqual(graph.get_callers("B"), ["A"])
        self.assertEqual(graph.get_callees("B"), ["C"])
        self.assertEqual(graph.get_callers("C"), ["B"])
        self.assertEqual(graph.get_callees("A"), ["B"])

        # 驗證調用點查詢
        sites = graph.get_call_sites("A", "B")
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].line_number, 10)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_call_graph_impact_and_cycle_protection(self):
        """FT-05: 驗證 query_impact 影響面分析與循環調用防護 (EC-02)"""
        graph = CallGraphIndex()
        # 構造循環: A ➔ B ➔ C ➔ A, 且 D ➔ B
        graph.add_edge("A", "B")
        graph.add_edge("B", "C")
        graph.add_edge("C", "A")
        graph.add_edge("D", "B")

        # 查詢改動 B 的影響面 (誰依賴 B? ➔ 直接: A, D; 間接: C)
        impact = graph.query_impact("B", max_depth=3)
        self.assertEqual(impact["target_id"], "B")
        self.assertEqual(set(impact["layers"].get(1, [])), {"A", "D"})
        self.assertIn("C", impact["layers"].get(2, []))
        self.assertEqual(impact["total_impacted_symbols"], 3)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_06_call_graph_binary_cache_and_incremental_patch(self):
        """FT-06: 驗證 CallGraphIndex Protocol 5 Gzip 快取持久化與 patch_incremental 差量修補"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "graph.bin.gz"

            graph = CallGraphIndex()
            site_a_b = SymbolCallSite(callee_name="b", line_number=10, file_path="src/a.py")
            site_b_c = SymbolCallSite(callee_name="c", line_number=20, file_path="src/b.py")
            graph.add_edge("A", "B", site_a_b)
            graph.add_edge("B", "C", site_b_c)

            # 1. 持久化與還原
            graph.save_binary(cache_file)
            self.assertTrue(cache_file.exists())

            restored = CallGraphIndex.load_binary(cache_file)
            self.assertEqual(restored.get_callers("B"), ["A"])
            self.assertEqual(restored.get_callees("B"), ["C"])

            # 2. 增量修補: a.py 被修改，A 不再調用 B，改為 A 調用 C
            new_site = SymbolCallSite(callee_name="c", line_number=12, file_path="src/a.py")
            restored.patch_incremental(
                dirty_file_paths={"src/a.py"},
                new_edges=[("A", "C", new_site)],
                old_symbol_ids={"A"},
            )

            self.assertEqual(restored.get_callers("B"), [])
            self.assertEqual(set(restored.get_callees("A")), {"C"})
            self.assertEqual(set(restored.get_callers("C")), {"A", "B"})

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_07_engine_call_graph_queries_and_cli(self):
        """FT-07: 驗證 KnowledgeEngine 端到端 callers/callees/impact 查詢與 RFC 8089 輸出格式"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            # 檔案 1: retrieval.py
            (src_dir / "retrieval.py").write_text(
                """
class InvertedIndex:
    def load_binary(self, path: str):
        return True

    def patch_incremental(self):
        return True
""",
                encoding="utf-8",
            )

            # 檔案 2: engine.py
            (src_dir / "engine.py").write_text(
                """
from retrieval import InvertedIndex

class KnowledgeEngine:
    def __init__(self):
        self.index = InvertedIndex()

    def build_unified_index(self):
        self.index.load_binary("cache.bin")

    def hot_patch(self):
        self.index.patch_incremental()
""",
                encoding="utf-8",
            )

            sp = SpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
            )

            # 1. 執行 callers 查詢 (誰調用了 InvertedIndex.load_binary?)
            callers_res = engine.act_callers("InvertedIndex.load_binary", snippet=True)
            self.assertEqual(callers_res["total_callers"], 1)
            caller_sym = callers_res["callers"][0]["symbol"]
            self.assertEqual(caller_sym.name, "KnowledgeEngine.build_unified_index")

            # 驗證輸出格式包含 RFC 8089 Markdown 連結
            callers_out = engine.format_callers_output(callers_res)
            self.assertIn("file:///", callers_out)
            self.assertIn("KnowledgeEngine.build_unified_index", callers_out)

            # 2. 執行 callees 查詢 (KnowledgeEngine.hot_patch 調用了誰?)
            callees_res = engine.act_callees("KnowledgeEngine.hot_patch", snippet=True)
            self.assertEqual(callees_res["total_callees"], 1)
            callee_sym = callees_res["callees"][0]["symbol"]
            self.assertEqual(callee_sym.name, "InvertedIndex.patch_incremental")

            callees_out = engine.format_callees_output(callees_res)
            self.assertIn("InvertedIndex.patch_incremental", callees_out)

            # 3. 執行 impact 查詢 (改動 InvertedIndex.load_binary 的影響半徑)
            impact_res = engine.act_impact("InvertedIndex.load_binary", depth=2)
            self.assertEqual(impact_res["total_impacted_symbols"], 1)
            impact_out = engine.format_impact_output(impact_res)
            self.assertIn("1 階直接影響", impact_out)
            self.assertIn("KnowledgeEngine.build_unified_index", impact_out)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_dynamic_calls_and_error_handling(self):
        """ET-01: 邊界測試 - 動態屬性調用、語法錯誤與無 Import 多型方法安全降級"""
        parser = PythonParser()
        broken_code = "def syntax_error( self. {"
        symbols = parser.parse(file_path="src/broken.py", content=broken_code, space="main")
        self.assertEqual(symbols, [])

        call_sites = parser.extract_call_sites(file_path="src/broken.py", content=broken_code, space="main")
        self.assertEqual(call_sites, [])

        # 動態 getattr 與深層屬性鏈測試
        dyn_code = """
def dynamic_test(obj):
    fn = getattr(obj, 'act')
    fn()
    a.b.c.deep_call()
"""
        dyn_sites = parser.extract_call_sites(file_path="src/dyn.py", content=dyn_code, space="main")
        callee_names = [cs.callee_name for cs in dyn_sites]
        self.assertIn("deep_call", callee_names)

        # 鏈接器對未定義符號回傳 None，不崩潰
        linker = TopologyLinker(symbols_map={})
        res = linker.resolve_call_site(dyn_sites[0])
        self.assertIsNone(res)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_space_isolation_for_same_symbol(self):
        """ET-02: 邊界測試 - 跨空間同名符號 Tier 3 空間優先隔離綁定"""
        sym_space_a = UnifiedSymbol(
            id="sym_a_run",
            name="Worker.run",
            kind=SymbolKind.METHOD.value,
            file_path="space_a/worker.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            metadata={"space": "space_a", "spaces": ["space_a"]},
        )
        sym_space_b = UnifiedSymbol(
            id="sym_b_run",
            name="Worker.run",
            kind=SymbolKind.METHOD.value,
            file_path="space_b/worker.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            metadata={"space": "space_b", "spaces": ["space_b"]},
        )

        symbols_map = {
            sym_space_a.id: sym_space_a,
            sym_space_b.id: sym_space_b,
        }
        linker = TopologyLinker(symbols_map=symbols_map)

        # 呼叫源位於 space_a
        site_in_a = SymbolCallSite(
            callee_name="run",
            line_number=5,
            context_prefix="Worker",
            file_path="space_a/caller.py",
            space="space_a",
        )
        target = linker.resolve_call_site(site_in_a)
        self.assertEqual(target, sym_space_a.id)

        # 呼叫源位於 space_b
        site_in_b = SymbolCallSite(
            callee_name="run",
            line_number=5,
            context_prefix="Worker",
            file_path="space_b/caller.py",
            space="space_b",
        )
        target_b = linker.resolve_call_site(site_in_b)
        self.assertEqual(target_b, sym_space_b.id)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pt_01_call_graph_performance_and_memory(self):
        """PT-01: 效能測試 - 500 個節點與 2000 條調用邊在 Gzip 下體積 < 150KB，查詢延遲 < 10ms"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "large_graph.bin.gz"

            graph = CallGraphIndex()
            # 建立 500 個符號與 2000 條隨機邊
            for i in range(500):
                for j in range(1, 5):
                    target_idx = (i + j * 7) % 500
                    site = SymbolCallSite(
                        callee_name=f"method_{target_idx}",
                        line_number=100 + j,
                        file_path=f"src/module_{i // 10}.py",
                    )
                    graph.add_edge(f"Symbol_{i}", f"Symbol_{target_idx}", site)

            # 驗證序列化
            graph.save_binary(cache_file, compresslevel=1)
            file_size_kb = cache_file.stat().st_size / 1024
            self.assertLess(file_size_kb, 150.0, f"Graph cache size {file_size_kb:.2f} KB exceeds 150 KB")

            # 驗證載入延遲
            t0 = time.perf_counter()
            restored = CallGraphIndex.load_binary(cache_file)
            load_elapsed_ms = (time.perf_counter() - t0) * 1000
            self.assertLess(load_elapsed_ms, 50.0, f"Graph load time {load_elapsed_ms:.2f} ms exceeds 50 ms")

            # 驗證查詢延遲
            t1 = time.perf_counter()
            for _ in range(100):
                restored.query_impact("Symbol_42", max_depth=3)
            query_avg_ms = ((time.perf_counter() - t1) / 100) * 1000
            self.assertLess(query_avg_ms, 10.0, f"Average impact query time {query_avg_ms:.2f} ms exceeds 10 ms")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_08_cpp_parser_call_sites_and_imports(self):
        """FT-08: 驗證 CppParser 提取 #include, using 與方法調用點"""
        code = """
#include <iostream>
#include "retrieval.h"
using namespace Core::Utils;
using MathAlias = Math::Calculator;

class Engine {
public:
    void Run() {
        this->Init();
        retrieval::load_binary("path");
        MathAlias::Compute();
    }
    void Init() {}
};
"""
        parser = CppParser()
        imports = parser.extract_imports("src/engine.cpp", code)
        self.assertEqual(imports.get("retrieval"), "retrieval.h")
        self.assertEqual(imports.get("Utils"), "Core::Utils")
        self.assertEqual(imports.get("MathAlias"), "Math::Calculator")

        sites = parser.extract_call_sites("src/engine.cpp", code, "main")
        callees = [s.callee_name for s in sites]
        self.assertIn("Init", callees)
        self.assertIn("load_binary", callees)
        self.assertIn("Compute", callees)

        init_site = next(s for s in sites if s.callee_name == "Init")
        self.assertEqual(init_site.caller_member_name, "Engine.Run")
        self.assertEqual(init_site.context_prefix, "self")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_09_csharp_parser_call_sites_and_imports(self):
        """FT-09: 驗證 CSharpParser 提取 using 與方法調用點"""
        code = """
using System.Text;
using MyMath = System.Math;

namespace App {
    public class Controller {
        public void Process() {
            this.Validate();
            MyMath.Abs(-5);
        }
        private void Validate() {}
    }
}
"""
        parser = CSharpParser()
        imports = parser.extract_imports("src/Controller.cs", code)
        self.assertEqual(imports.get("Text"), "System.Text")
        self.assertEqual(imports.get("MyMath"), "System.Math")

        sites = parser.extract_call_sites("src/Controller.cs", code, "main")
        callees = [s.callee_name for s in sites]
        self.assertIn("Validate", callees)
        self.assertIn("Abs", callees)

        val_site = next(s for s in sites if s.callee_name == "Validate")
        self.assertEqual(val_site.caller_member_name, "Controller.Process")
        self.assertEqual(val_site.context_prefix, "self")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_10_js_ts_parser_call_sites_and_imports(self):
        """FT-10: 驗證 JsTsParser 提取 import / require 與方法調用點"""
        code = """
import { loadBinary as loadBin, InvertedIndex } from './retrieval';
import Utils from './utils';
const { helper } = require('./helper');

class AppService {
    start() {
        this.init();
        loadBin("cache.bin");
        Utils.format();
    }
    init() {}
}
"""
        parser = JsTsParser()
        imports = parser.extract_imports("src/app.ts", code)
        self.assertEqual(imports.get("loadBin"), "./retrieval.loadBinary")
        self.assertEqual(imports.get("InvertedIndex"), "./retrieval.InvertedIndex")
        self.assertEqual(imports.get("Utils"), "./utils")
        self.assertEqual(imports.get("helper"), "./helper.helper")

        sites = parser.extract_call_sites("src/app.ts", code, "main")
        callees = [s.callee_name for s in sites]
        self.assertIn("init", callees)
        self.assertIn("loadBin", callees)
        self.assertIn("format", callees)

        init_site = next(s for s in sites if s.callee_name == "init")
        self.assertEqual(init_site.caller_member_name, "AppService.start")
        self.assertEqual(init_site.context_prefix, "self")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_11_markdown_parser_call_sites_and_imports(self):
        """FT-11: 驗證 MarkdownParser 提取文檔超連結與符號引用點"""
        doc = """
# API Documentation

## Usage
Refer to [Architecture Guide](architecture.md) and [`KnowledgeEngine.build`](engine.py#L123).
You can also call `InvertedIndex.load_binary` to reload cache.
"""
        parser = MarkdownParser()
        imports = parser.extract_imports("docs/api.md", doc)
        self.assertEqual(imports.get("Architecture Guide"), "architecture.md")

        sites = parser.extract_call_sites("docs/api.md", doc, "docs")
        callees = [s.callee_name for s in sites]
        self.assertIn("build", callees)
        self.assertIn("load_binary", callees)

        build_site = next(s for s in sites if s.callee_name == "build")
        self.assertEqual(build_site.caller_member_name, "Usage")
        self.assertEqual(build_site.context_prefix, "KnowledgeEngine")

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
