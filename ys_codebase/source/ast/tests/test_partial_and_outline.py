"""
Subsystem tests for C# partial symbol two-tier aggregation (`ast_engine.bundler`) and single-file / merged outline (`ast_engine.engine`).
"""

from pathlib import Path
import shutil
import sys
import tempfile

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)

from ast_engine.bundler import (
    SemanticBundler,
    aggregate_partial_symbols,
    restore_unaggregated_partial_symbol,
)
from ast_engine.engine import ASTEngine
from ast_engine.formatter import ASTResultFormatter
from ast_engine.parsers import ParserRegistry
from dev.testing import Requirement, YSCBTestCase, require


class TestPartialAndOutline(YSCBTestCase):
    """Tests for C# partial class/struct/interface two-tier state preservation, restoration, and outline views."""

    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_partial_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"

    def tearDown(self):
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_csharp_partial_two_tier_aggregation_and_restoration(self):
        """FT-01: Verify aggregate_partial_symbols merges members across parts while preserving _own_members and supporting restoration."""
        registry = ParserRegistry(register_defaults=True)
        part_a_code = (
            "namespace UI.Controls {\n"
            "    public partial class Window : Control {\n"
            "        private int _width;\n"
            "        public void Open(string title) {}\n"
            "    }\n"
            "}\n"
        )
        part_b_code = (
            "namespace UI.Controls {\n"
            "    public partial class Window : IDisposable {\n"
            "        private bool _disposed;\n"
            "        public void Dispose() {}\n"
            "    }\n"
            "}\n"
        )
        syms_a = registry.parse_file("UI/Window.Core.cs", part_a_code, space="ui")
        syms_b = registry.parse_file("UI/Window.Lifecycle.cs", part_b_code, space="ui")
        for s in syms_a + syms_b:
            s.metadata["spaces"] = ["ui"]

        aggregated = aggregate_partial_symbols(syms_a + syms_b)
        win_classes = [s for s in aggregated if s.kind == "class" and s.fqn == "UI.Controls.Window"]
        self.assertEqual(len(win_classes), 2)

        win_core = next(s for s in win_classes if s.file_path == "UI/Window.Core.cs")
        win_life = next(s for s in win_classes if s.file_path == "UI/Window.Lifecycle.cs")

        # Aggregated members contain both Open and Dispose
        merged_member_names = {m.name for m in win_core.members}
        self.assertIn("Open", merged_member_names)
        self.assertIn("Dispose", merged_member_names)
        self.assertIn("_width", merged_member_names)
        self.assertIn("_disposed", merged_member_names)

        # Merged base_types and field_types
        self.assertIn("Control", win_core.metadata.get("base_types", []))
        self.assertIn("IDisposable", win_core.metadata.get("base_types", []))
        self.assertEqual(win_core.metadata.get("field_types", {}).get("_width"), "int")
        self.assertEqual(win_core.metadata.get("field_types", {}).get("_disposed"), "bool")

        # _own_members strictly preserves physical single-file members
        own_core_names = {m.name for m in win_core.metadata.get("_own_members", ())}
        self.assertEqual(own_core_names, {"_width", "Open"})
        own_life_names = {m.name for m in win_life.metadata.get("_own_members", ())}
        self.assertEqual(own_life_names, {"_disposed", "Dispose"})

        # Restoring win_core drops the deleted sibling's members/base_types/field_types
        restored_core = restore_unaggregated_partial_symbol(win_core)
        restored_member_names = {m.name for m in restored_core.members}
        self.assertEqual(restored_member_names, {"_width", "Open"})
        self.assertEqual(restored_core.metadata.get("base_types"), ["Control"])
        self.assertEqual(restored_core.metadata.get("field_types"), {"_width": "int"})

        # Re-aggregating a single surviving partial class degenerates cleanly to its own members
        re_agg = aggregate_partial_symbols([restored_core])
        self.assertEqual(len(re_agg), 1)
        self.assertEqual({m.name for m in re_agg[0].members}, {"_width", "Open"})
        self.assertEqual(re_agg[0].metadata.get("partial_files"), ["UI/Window.Core.cs"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_outline_single_file_default_vs_merged_partial_siblings(self):
        """FT-02: Verify ASTEngine.outline() defaults to physical file members with partial_siblings and merges when merged=True."""
        proj_dir = self.temp_dir / "project"
        ui_dir = proj_dir / "UI"
        ui_dir.mkdir(parents=True, exist_ok=True)

        core_file = ui_dir / "Window.Core.cs"
        events_file = ui_dir / "Window.Events.cs"
        core_file.write_text(
            "namespace UI {\n"
            "    public partial class Window {\n"
            "        public void Render() {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        events_file.write_text(
            "namespace UI {\n"
            "    public partial class Window {\n"
            "        public void OnClick() {}\n"
            "        public void OnResize() {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        engine.ensure_jit_synced(force=True)

        # Default outline (merged=False): only physical file members + partial_siblings metadata
        outline_default = engine.outline(str(core_file), merged=False)
        self.assertFalse(outline_default["merged"])
        win_sym_default = next(
            (s for s in outline_default["symbols"] if s["kind"] == "class" and s["fqn"] == "UI.Window"),
            None,
        )
        self.assertIsNotNone(win_sym_default)
        default_member_names = {m["name"] for m in win_sym_default["members"]}
        self.assertEqual(default_member_names, {"Render"})
        self.assertNotIn("OnClick", default_member_names)

        # Partial siblings must list Window.Events.cs with its own member count (2)
        siblings = outline_default.get("partial_siblings", {}).get("UI.Window", [])
        self.assertEqual(len(siblings), 1)
        self.assertTrue(siblings[0]["file_path"].endswith("UI/Window.Events.cs"))
        self.assertEqual(siblings[0]["member_count"], 2)

        # Formatted output includes [Partial Siblings] hint
        formatted_default = ASTResultFormatter().format_outline_output(outline_default, as_json=False)
        self.assertIn("[Partial Siblings]", formatted_default)
        self.assertIn("Window.Events.cs", formatted_default)

        # Merged outline (merged=True): includes members across all partial files
        outline_merged = engine.outline(str(core_file), merged=True)
        self.assertTrue(outline_merged["merged"])
        win_sym_merged = next(
            (s for s in outline_merged["symbols"] if s["kind"] == "class" and s["fqn"] == "UI.Window"),
            None,
        )
        self.assertIsNotNone(win_sym_merged)
        merged_member_names = {m["name"] for m in win_sym_merged["members"]}
        self.assertEqual(merged_member_names, {"Render", "OnClick", "OnResize"})
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_outline_orthogonal_filters_visibility_binding_and_member_kind(self):
        """FT-03: Verify ASTEngine.outline() orthogonal filtering across visibility, binding, and member_kind."""
        proj_dir = self.temp_dir / "filter_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        py_file = proj_dir / "service.py"
        py_file.write_text(
            "class AuthService:\n"
            "    def __init__(self):\n"
            "        self.token = 'abc'\n"
            "        self._secret = 'xyz'\n"
            "\n"
            "    def login(self, user: str) -> bool:\n"
            "        return True\n"
            "\n"
            "    def _hash_password(self, pwd: str) -> str:\n"
            "        return pwd\n"
            "\n"
            "    @staticmethod\n"
            "    def verify_signature(sig: str) -> bool:\n"
            "        return True\n"
            "\n"
            "    @staticmethod\n"
            "    def _internal_helper() -> None:\n"
            "        pass\n"
            "\n"
            "    @staticmethod\n"
            "    def __secret_static() -> None:\n"
            "        pass\n",
            encoding="utf-8",
        )

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)

        # 1. --public --methods: should keep AuthService container with __init__, login, verify_signature (no _hash_password, _internal_helper, __secret_static, or fields)
        res_pub_methods = engine.outline(
            str(py_file), visibility="public", member_kind="methods"
        )
        self.assertEqual(
            res_pub_methods.get("filters"),
            {"visibility": "public", "member_kind": "methods"},
        )
        cls_node = res_pub_methods["symbols"][0]
        self.assertEqual(cls_node["name"], "AuthService")
        pub_method_names = {m["name"] for m in cls_node["members"]}
        self.assertEqual(pub_method_names, {"__init__", "login", "verify_signature"})

        # 2. --protected --static: only _internal_helper
        res_prot_static = engine.outline(
            str(py_file), visibility="protected", binding="static"
        )
        cls_node_ps = res_prot_static["symbols"][0]
        prot_static_names = {m["name"] for m in cls_node_ps["members"]}
        self.assertEqual(prot_static_names, {"_internal_helper"})
        self.assertTrue(cls_node_ps["members"][0]["is_static"])

        # 2b. --private --static: only __secret_static
        res_priv_static = engine.outline(
            str(py_file), visibility="private", binding="static"
        )
        cls_node_pvs = res_priv_static["symbols"][0]
        priv_static_names = {m["name"] for m in cls_node_pvs["members"]}
        self.assertEqual(priv_static_names, {"__secret_static"})

        # 3. --non-static --methods --public: __init__ and login (excludes static verify_signature)
        res_inst_pub = engine.outline(
            str(py_file),
            visibility="public",
            binding="non-static",
            member_kind="methods",
        )
        cls_node_ip = res_inst_pub["symbols"][0]
        inst_pub_names = {m["name"] for m in cls_node_ip["members"]}
        self.assertEqual(inst_pub_names, {"__init__", "login"})

        # 4. --fields: only token and _secret
        res_fields = engine.outline(str(py_file), member_kind="fields")
        cls_node_f = res_fields["symbols"][0]
        field_names = {m["name"] for m in cls_node_f["members"]}
        self.assertEqual(field_names, {"token", "_secret"})

        # 5. --types: keeps AuthService class container with members folded (empty)
        res_types = engine.outline(str(py_file), member_kind="types")
        self.assertEqual(len(res_types["symbols"]), 1)
        self.assertEqual(res_types["symbols"][0]["name"], "AuthService")
        self.assertEqual(res_types["symbols"][0]["members"], [])

        # Verify formatted output shows [static] badge and filters summary
        formatted = ASTResultFormatter().format_outline_output(res_priv_static, as_json=False)
        self.assertIn("[static]", formatted)
        self.assertIn("filters: visibility=private, binding=static", formatted)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_outline_missing_file_returns_structured_error(self):
        """ET-01: Verify ASTEngine.outline() on a non-existent file returns structured error without crashing."""
        engine = ASTEngine(project_root=self.temp_dir, storage_dir=self.storage_dir)
        res = engine.outline(str(self.temp_dir / "non_existent_file.cs"), merged=False)
        self.assertEqual(res.get("symbols"), [])
        self.assertIn("error", res)
        self.assertIn("File not found", res["error"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_ast_engine_pep562_lazy_exports_and_version(self):
        """FR-03, NFR-02: Verify ast_engine PEP 562 lazy attribute loading and __version__ consistency."""
        import json
        import ast_engine

        mf_path = Path(__file__).resolve().parent.parent / "manifest.json"
        mf_data = json.loads(mf_path.read_text(encoding="utf-8"))
        self.assertEqual(ast_engine.__version__, mf_data["version"])
        for sym_name in ("ASTEngine", "ASTSnapshot", "CallGraphIndex", "SemanticBundler"):
            self.assertIn(sym_name, dir(ast_engine))
            self.assertIsNotNone(getattr(ast_engine, sym_name))
        with self.assertRaises(AttributeError):
            _ = ast_engine.NON_EXISTENT_SYMBOL_XYZ
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_overload_members_retention_and_dirty_file_match(self):
        """FR-04, EC-04 (AUD-08, AUD-09, AUD-14): Verify C# overloaded methods are retained in class members and is_dirty_file_match avoids basename false positives."""
        from ast_engine.io_utils import is_dirty_file_match, normalize_dirty_paths

        dirty_set = normalize_dirty_paths(["ys_codebase/source/dev/scripts/cli.py"])
        self.assertFalse(is_dirty_file_match("cli.py", dirty_set))
        self.assertTrue(is_dirty_file_match("source/dev/scripts/cli.py", dirty_set))
        self.assertTrue(is_dirty_file_match("ys_codebase/source/dev/scripts/cli.py", dirty_set))

        proj_dir = self.temp_dir / "overload_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        cs_file = proj_dir / "MathOps.cs"
        cs_file.write_text(
            "namespace Calc {\n"
            "    public class MathOps {\n"
            "        public int Add(int a, int b) { return a + b; }\n"
            "        public double Add(double a, double b) { return a + b; }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        engine.ensure_jit_synced(force=True)
        outline_res = engine.outline(str(cs_file), merged=False)
        cls_sym = next((s for s in outline_res["symbols"] if s["kind"] == "class"), None)
        if cls_sym is not None:
            add_members = [m for m in cls_sym["members"] if m["name"] == "Add"]
            self.assertEqual(len(add_members), 2)
        self.mark_passed()

