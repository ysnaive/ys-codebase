"""
Unit and edge-case tests for Single-Pass `FileSymbolGraph` caching, $O(|\\text{Dirty}|)$ hot-patching,
L0 stateless single-file primitives (`parse_file`, `outline`, `slice_part`),
L1 workspace graph primitives (`get_workspace_graph`, `resolve`, `select_nodes`, `traverse_edges`),
and CLI `slice` / `traverse` subcommands (`scripts/cli.py`).
"""

import json
from pathlib import Path
import shutil
import sys
import tempfile

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from ast_engine.engine import ASTEngine
from ast_engine.exceptions import ASTError
from ast_engine.schema import FileSymbolGraph, WorkspaceSymbolGraph
from core.space import ScanDiffDetail
from scripts.cli import dispatch_cli
from tests import ASTTestCase, Requirement, require


class TestL0L1PrimitivesAndCache(ASTTestCase):
    """Test suite for R03 (`sub_03_l0_l1_primitives_cache_and_kdb_migration`)."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_sub03_"))
        self.project_root = self.tmp_dir / "proj"
        self.storage_dir = self.tmp_dir / "storage"
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    def _create_sample_workspace(self) -> ASTEngine:
        src_dir = self.project_root / "pkg"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "__init__.py").write_text("", encoding="utf-8")
        (src_dir / "base.py").write_text(
            'class BaseWorker:\n'
            '    """Base worker docstring (基底說明)."""\n'
            '    def execute(self, payload: str) -> int:\n'
            '        """Run base task."""\n'
            '        return len(payload)\n',
            encoding="utf-8",
        )
        (src_dir / "impl.py").write_text(
            'from .base import BaseWorker\n\n'
            'class ConcreteWorker(BaseWorker):\n'
            '    """Concrete worker implementation."""\n'
            '    def run_all(self, item: str) -> int:\n'
            '        """Invoke inherited execute."""\n'
            '        return self.execute(item)\n',
            encoding="utf-8",
        )
        (self.project_root / "README.md").write_text(
            "# Architecture Guide\n\n"
            "See [ConcreteWorker](pkg/impl.py#ConcreteWorker) and `ConcreteWorker.run_all`.\n",
            encoding="utf-8",
        )
        return ASTEngine(
            project_root=self.project_root,
            storage_dir=self.storage_dir,
            custom_spaces={
                "project": {
                    "entries": [str(self.project_root)],
                    "include": ["**/*.py", "**/*.md", "**/*.cs"],
                }
            },
        )

    @require(Requirement.LOGIC)
    def test_ft01_single_pass_file_graph_cache_and_persistence(self) -> None:
        """FT-01 & EC-04: Verify `build_index` caches `FileSymbolGraph` and `WorkspaceSymbolGraph` and persists/reloads cleanly."""
        engine = self._create_sample_workspace()
        snap = engine.build_index(allow_parallel=False)

        self.assertGreaterEqual(len(snap.file_graphs), 3)
        self.assertIn("pkg/base.py", snap.file_graphs)
        self.assertIn("pkg/impl.py", snap.file_graphs)
        self.assertIsInstance(snap.file_graphs["pkg/base.py"], FileSymbolGraph)

        ws_graph = engine.get_workspace_graph(auto_sync=False)
        self.assertIsInstance(ws_graph, WorkspaceSymbolGraph)
        self.assertGreaterEqual(len(ws_graph.nodes_by_id), 4)
        self.assertTrue(any(e.edge_kind == "inherits" and e.resolution_status == "resolved" for e in ws_graph.resolved_edges))

        # Reload into a fresh ASTEngine instance from disk binary caches
        engine_reloaded = ASTEngine(
            project_root=self.project_root,
            storage_dir=self.storage_dir,
            custom_spaces={
                "project": {
                    "entries": [str(self.project_root)],
                    "include": ["**/*.py", "**/*.md", "**/*.cs"],
                }
            },
        )
        snap_reloaded = engine_reloaded.get_snapshot(auto_sync=False)
        ws_reloaded = engine_reloaded.get_workspace_graph(auto_sync=False)
        self.assertEqual(set(snap_reloaded.file_graphs.keys()), set(snap.file_graphs.keys()))
        self.assertEqual(set(ws_reloaded.nodes_by_id.keys()), set(ws_graph.nodes_by_id.keys()))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft02_hot_patch_dirty_file_graphs_and_partial_classes(self) -> None:
        """FT-02: Verify $O(|Dirty|)$ hot_patch_index updates `file_graphs`, `WorkspaceSymbolGraph`, and C# partial symbols."""
        engine = self._create_sample_workspace()
        cs_a = self.project_root / "pkg" / "PartA.cs"
        cs_b = self.project_root / "pkg" / "PartB.cs"
        cs_a.write_text("public partial class OrderService { public void Create() {} }\n", encoding="utf-8")
        cs_b.write_text("public partial class OrderService { public void Cancel() {} }\n", encoding="utf-8")

        snap1 = engine.build_index(allow_parallel=False)
        gen1 = snap1.ast_generation
        self.assertIn("pkg/PartA.cs", snap1.file_graphs)
        self.assertIn("pkg/PartB.cs", snap1.file_graphs)

        # Modify PartB.cs and add a new method in impl.py
        cs_b.write_text("public partial class OrderService { public void Refund() {} }\n", encoding="utf-8")
        (self.project_root / "pkg" / "impl.py").write_text(
            "from .base import BaseWorker\n\n"
            "class ConcreteWorker(BaseWorker):\n"
            "    def run_all(self, item: str) -> int:\n"
            "        return self.execute(item)\n"
            "    def extra_step(self) -> bool:\n"
            "        return True\n",
            encoding="utf-8",
        )
        diff = ScanDiffDetail(added=set(), modified={"pkg/PartB.cs", "pkg/impl.py"}, deleted=set())
        snap2 = engine.hot_patch_index(diff)
        self.assertEqual(snap2.ast_generation, gen1 + 1)
        ws2 = engine.get_workspace_graph(auto_sync=False)
        node_names = {n.name for n in ws2.nodes_by_id.values()}
        self.assertIn("Refund", node_names)
        self.assertIn("extra_step", node_names)
        self.assertNotIn("Cancel", node_names)

        # Delete PartB.cs and verify eviction
        cs_b.unlink()
        diff_del = ScanDiffDetail(added=set(), modified=set(), deleted={"pkg/PartB.cs"})
        snap3 = engine.hot_patch_index(diff_del)
        self.assertNotIn("pkg/PartB.cs", snap3.file_graphs)
        ws3 = engine.get_workspace_graph(auto_sync=False)
        self.assertNotIn("Refund", {n.name for n in ws3.nodes_by_id.values()})
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft03_l0_stateless_primitives_parse_file_and_slice_part(self) -> None:
        """FT-03, EC-01, EC-02: Verify L0 `parse_file` (stateless/zero-index) and `slice_part` (UTF-8 byte slicing & error guards)."""
        engine = self._create_sample_workspace()

        # 1. Stateless parse_file with in-memory content must not create disk index files
        inline_code = (
            'def compute_metrics(alpha: int, beta: str = "預設值") -> str:\n'
            '    """計算指標說明文檔."""\n'
            '    return f"{beta}:{alpha}"\n'
        )
        fg = engine.parse_file("virtual/inline.py", content=inline_code)
        self.assertIsInstance(fg, FileSymbolGraph)
        self.assertFalse(engine.symbols_index_path.exists())
        self.assertEqual(len(fg.root_nodes), 1)
        fn_node = fg.root_nodes[0]
        self.assertEqual(fn_node.name, "compute_metrics")

        # 2. Lossless UTF-8 byte slicing via SymbolNode and file_bytes
        self.assertEqual(engine.slice_part(fn_node, part="name", file_bytes=inline_code), "compute_metrics")
        self.assertIn("alpha: int", engine.slice_part(fn_node, part="parameters", file_bytes=inline_code))
        self.assertIn("預設值", engine.slice_part(fn_node, part="parameters", file_bytes=inline_code))
        self.assertIn("計算指標說明文檔", engine.slice_part(fn_node, part="doc", file_bytes=inline_code))
        self.assertIn("return", engine.slice_part(fn_node, part="body", file_bytes=inline_code))
        self.assertTrue(engine.slice_part(fn_node, part="signature", file_bytes=inline_code).startswith("def compute_metrics"))
        self.assertEqual(engine.slice_part(fn_node, part="outer", file_bytes=inline_code).strip(), inline_code.strip())

        # 3. Slicing by selector string across workspace files (including multi-byte UTF-8 docstring)
        base_doc = engine.slice_part("BaseWorker", part="doc")
        self.assertIn("基底說明", base_doc)
        exec_sig = engine.slice_part("BaseWorker.execute", part="signature")
        self.assertIn("def execute(self, payload: str)", exec_sig)

        # 4. EC-01 & EC-02: Missing optional slot returns "", invalid part or unknown symbol raises ASTError
        var_fg = engine.parse_file("virtual/vars.py", content="MAX_COUNT = 42\n")
        if var_fg.root_nodes:
            self.assertEqual(engine.slice_part(var_fg.root_nodes[0], part="doc", file_bytes="MAX_COUNT = 42\n"), "")
        with self.assertRaises(ASTError):
            engine.slice_part(fn_node, part="invalid_slot", file_bytes=inline_code)
        with self.assertRaises(ASTError):
            engine.slice_part("NonExistentSymbolXYZ", part="outer")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft04_l1_workspace_primitives_resolve_select_and_traverse(self) -> None:
        """FT-04 & EC-03: Verify L1 `resolve`, `select_nodes`, and `traverse_edges` across code and doc edges."""
        engine = self._create_sample_workspace()

        # 1. resolve with kinds filter
        res_cls = engine.resolve("ConcreteWorker", kinds=["class"])
        self.assertEqual(res_cls.status, "matched")
        self.assertEqual(res_cls.targets[0].name, "ConcreteWorker")

        res_mismatch = engine.resolve("ConcreteWorker", kinds=["function"])
        self.assertEqual(res_mismatch.status, "not_found")

        # 2. select_nodes with orthogonal filters
        class_nodes = engine.select_nodes(kinds=["class"], visibility="public")
        class_names = {n.name for n in class_nodes}
        self.assertIn("BaseWorker", class_names)
        self.assertIn("ConcreteWorker", class_names)

        md_nodes = engine.select_nodes(ftypes=["md"])
        self.assertTrue(any("Architecture Guide" in n.name for n in md_nodes))

        # 3. traverse_edges: outgoing `inherits` from ConcreteWorker -> BaseWorker
        inh_out = engine.traverse_edges("ConcreteWorker", edge_kinds=["inherits"], direction="out", depth=1)
        self.assertEqual(inh_out["total_reached_nodes"], 1)
        self.assertEqual(inh_out["layers"][1][0].name, "BaseWorker")

        # 4. traverse_edges: incoming `documents` to ConcreteWorker from README.md heading
        doc_in = engine.traverse_edges("ConcreteWorker", edge_kinds=["documents"], direction="in", depth=1)
        self.assertGreaterEqual(doc_in["total_reached_nodes"], 1)
        self.assertTrue(any(n.file_path.endswith("README.md") for n in doc_in["layers"][1]))

        # 5. traverse_edges: outgoing `calls` from ConcreteWorker.run_all -> BaseWorker.execute (via Pass 3 inheritance DAG)
        calls_out = engine.traverse_edges("ConcreteWorker.run_all", edge_kinds=["calls"], direction="out", depth=1)
        self.assertEqual(calls_out["total_reached_nodes"], 1)
        self.assertEqual(calls_out["layers"][1][0].name, "execute")

        # 6. EC-03: depth=0 and invalid direction guard
        zero_res = engine.traverse_edges("ConcreteWorker", depth=0)
        self.assertEqual(zero_res["total_reached_nodes"], 0)
        self.assertEqual(zero_res["layers"], {})
        with self.assertRaises(ASTError):
            engine.traverse_edges("ConcreteWorker", direction="diagonal")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft05_cli_slice_and_traverse_commands(self) -> None:
        """FT-05: Verify CLI `slice` and `traverse` dispatch and JSON output contracts."""
        from unittest.mock import patch

        engine = self._create_sample_workspace()
        engine.build_index(allow_parallel=False)

        captured_out = []
        with patch("scripts.cli._get_engine", return_value=engine), patch(
            "scripts.cli._log_cli", side_effect=lambda msg, **kw: captured_out.append(str(msg))
        ):
            rc_slice = dispatch_cli(
                {
                    "slice": {
                        "args": ["BaseWorker.execute"],
                        "options": {"part": ["signature"], "json": True},
                    }
                }
            )
            self.assertEqual(rc_slice, 0)
            slice_payload = json.loads(captured_out[-1])
            self.assertEqual(slice_payload["status"], "matched")
            self.assertEqual(slice_payload["part"], "signature")
            self.assertIn("def execute", slice_payload["content"])

            rc_trav = dispatch_cli(
                {
                    "traverse": {
                        "args": ["ConcreteWorker"],
                        "options": {"kind": ["inherits"], "direction": ["out"], "depth": ["1"], "json": True},
                    }
                }
            )
            self.assertEqual(rc_trav, 0)
            trav_payload = json.loads(captured_out[-1])
            self.assertEqual(trav_payload["status"], "matched")
            self.assertEqual(trav_payload["total_reached_nodes"], 1)
            self.assertEqual(trav_payload["layers"]["1"][0]["name"], "BaseWorker")
        self.mark_passed()
