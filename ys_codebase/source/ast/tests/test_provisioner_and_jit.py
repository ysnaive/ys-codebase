"""
Subsystem tests for GrammarProvisioner stderr isolation & negative cache (`ast_engine.provisioner`),
ASTEngine JIT incremental hot-patching (`ast_engine.engine`), CLI commands (`scripts/cli.py`),
and lifecycle hooks (`scripts/hook.core.py`, `scripts/hook.dev.py`, `scripts/migrations/1.0.1.x.py`).
"""

import io
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from core.commands import CmdBags
from ast_engine.engine import ASTEngine
from ast_engine.provisioner import GrammarProvisioner
from tests import ASTTestCase, Requirement, load_ast_script, require


class TestProvisionerAndJit(ASTTestCase):
    """Tests for GrammarProvisioner, JIT hot-patching, CLI commands, and lifecycle hooks."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_jit_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"

    def tearDown(self) -> None:
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_provisioner_stderr_redirection_negative_cache_and_outline_warnings(self) -> None:
        """Verify GrammarProvisioner redirects pip output to sys.stderr, caches failed packages, and records outline warnings."""
        run_calls = []

        def fake_subprocess_run(cmd, **kwargs):
            run_calls.append((cmd, kwargs))
            self.assertIs(kwargs.get("stdout"), sys.stderr)
            self.assertIs(kwargs.get("stderr"), sys.stderr)
            return subprocess.CompletedProcess(cmd, returncode=1)

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        prov_logger = logging.getLogger("ast.provisioner")

        with patch("ast_engine.provisioner.subprocess.run", side_effect=fake_subprocess_run), patch.object(
            prov_logger, "warning"
        ):
            with patch.object(sys, "stdout", stdout_capture), patch.object(sys, "stderr", stderr_capture):
                lang1 = GrammarProvisioner.load_language(
                    lang_key="fake_lang",
                    module_name="tree_sitter_nonexistent_xyz",
                    auto_install_pkg="tree-sitter-nonexistent-xyz",
                    attempt_auto_install=True,
                )
                self.assertIsNone(lang1)
                self.assertEqual(len(run_calls), 1)
                self.assertIn("tree-sitter-nonexistent-xyz", GrammarProvisioner._FAILED_PACKAGES)

                # Clear warnings, then verify cached negative hit still populates warnings without re-running pip
                GrammarProvisioner.get_warnings(clear=True)
                lang2 = GrammarProvisioner.load_language(
                    lang_key="fake_lang",
                    module_name="tree_sitter_nonexistent_xyz",
                    auto_install_pkg="tree-sitter-nonexistent-xyz",
                    attempt_auto_install=True,
                )
                self.assertIsNone(lang2)
                self.assertEqual(len(run_calls), 1)
                self.assertEqual(len(GrammarProvisioner.get_warnings()), 1)

        self.assertEqual(stdout_capture.getvalue(), "")
        self.assertIn("[ast:warn]", stderr_capture.getvalue())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ast_engine_jit_sync_hot_patch_and_external_edge_preservation(self) -> None:
        """Verify ASTEngine.ensure_jit_synced builds index, hot-patches C# partial changes, preserves incoming edges, and increments ast_generation."""
        proj_dir = self.temp_dir / "project"
        svc_dir = proj_dir / "Services"
        svc_dir.mkdir(parents=True, exist_ok=True)

        part1 = svc_dir / "Billing.Part1.cs"
        part2 = svc_dir / "Billing.Part2.cs"
        caller_file = svc_dir / "CheckoutController.cs"

        part1.write_text(
            "namespace App.Services {\n"
            "    public partial class BillingService {\n"
            "        public void Charge(int amount) {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        part2.write_text(
            "namespace App.Services {\n"
            "    public partial class BillingService {\n"
            "        public void Refund(int amount) {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        caller_file.write_text(
            "namespace App.Services {\n"
            "    public class CheckoutController {\n"
            "        private BillingService _billing;\n"
            "        public void ProcessCheckout() {\n"
            "            _billing.Charge(100);\n"
            "        }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        snap1 = engine.ensure_jit_synced(force=True)
        self.assertEqual(snap1.ast_generation, 1)

        callers_initial = engine.callers("BillingService.Charge")
        caller_names_initial = {c["name"].split(".")[-1] for c in callers_initial.get("callers", [])}
        self.assertIn("ProcessCheckout", caller_names_initial)

        part1.write_text(
            "namespace App.Services {\n"
            "    public partial class BillingService {\n"
            "        public void Charge(int amount) {}\n"
            "        public void ValidateReceipt() {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        part2.unlink()

        diff_detail = {
            "spaces": {
                "default": {
                    "added": [],
                    "modified": ["Services/Billing.Part1.cs"],
                    "deleted": ["Services/Billing.Part2.cs"],
                }
            }
        }
        snap2 = engine.hot_patch_index(diff_detail)
        self.assertEqual(snap2.ast_generation, 2)

        billing_cls = next((s for s in snap2.symbols.values() if s.kind == "class" and s.fqn == "App.Services.BillingService"), None)
        self.assertIsNotNone(billing_cls)
        assert billing_cls is not None
        surviving_members = {m.name for m in billing_cls.members}
        self.assertEqual(surviving_members, {"Charge", "ValidateReceipt"})

        callers_after = engine.callers("BillingService.Charge")
        caller_names_after = {c["name"].split(".")[-1] for c in callers_after.get("callers", [])}
        self.assertIn("ProcessCheckout", caller_names_after)

        st = engine.status()
        self.assertTrue(st["snapshot_exists"])
        self.assertEqual(st["ast_generation"], 2)

        clean_res = engine.clean()
        self.assertEqual(len(clean_res["removed"]), 4)
        self.assertFalse(engine.status()["snapshot_exists"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_file_space_hook_lifecycle_and_generation_fallback(self) -> None:
        """Verify scripts/hook.core.py handles cloud ignore, persisted generation fallback, rebuilt/patched/noop paths, and broadcast."""
        hook_mod = load_ast_script("scripts/hook.core.py", "ast_hook_core")

        res_empty = hook_mod.on_file_space_changed(diff_detail={})
        self.assertEqual(res_empty.get("status"), "skipped")

        res_cloud = hook_mod.on_file_space_changed(space_name="cloud", diff_detail={"modified": ["a.py"]})
        self.assertEqual(res_cloud.get("status"), "noop")

        proj_dir = self.temp_dir / "hook_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        mod_file = proj_dir / "mod.py"
        mod_file.write_text("def hello():\n    return 42\n", encoding="utf-8")

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        broadcast_events = []

        with patch("core.events.broadcast", side_effect=lambda ev, payload, **kw: broadcast_events.append((ev, payload))):
            # 1. Initial event with no existing snapshot -> status == "rebuilt"
            res_rebuilt = hook_mod.on_file_space_changed(
                context={"engine": engine, "space_name": "default", "diff_summary": {"added": 1}},
            )
            self.assertEqual(res_rebuilt.get("status"), "rebuilt")
            self.assertEqual(res_rebuilt.get("ast_generation"), 1)
            self.assertEqual(len(broadcast_events), 1)

            # 2. Fresh cold engine (engine._snapshot is None): cloud space should read persisted generation (1)
            cold_engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
            self.assertIsNone(cold_engine._snapshot)
            res_cold_noop = hook_mod.on_file_space_changed(context={"engine": cold_engine, "space_name": "cloud"})
            self.assertEqual(res_cold_noop.get("status"), "noop")
            self.assertEqual(res_cold_noop.get("ast_generation"), 1)

            # 3. Modify file -> status == "patched"
            mod_file.write_text("def hello():\n    return 99\n\ndef world():\n    return hello()\n", encoding="utf-8")
            res_patched = hook_mod.on_file_space_changed(context={"engine": engine, "space_name": "default"})
            self.assertEqual(res_patched.get("status"), "patched")
            self.assertEqual(res_patched.get("ast_generation"), 2)

            # 4. No changes -> status == "noop"
            res_noop = hook_mod.on_file_space_changed(context={"engine": engine, "space_name": "default"})
            self.assertEqual(res_noop.get("status"), "noop")
            self.assertEqual(res_noop.get("ast_generation"), 2)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_commands_and_space_separated_options(self) -> None:
        """Verify scripts/cli.py _normalize_bags space-separated options and all 6 CLI commands with isolated ASTEngine."""
        cli_mod = load_ast_script("scripts/cli.py", "ast_cli_module")

        bags = cli_mod._normalize_bags(["Window.Open", "--space", "code", "--depth", "3", "--limit", "5", "--json"], "impact")
        self.assertEqual(bags.args, ["Window.Open"])
        self.assertEqual(bags.get_option_value("space"), "code")
        self.assertEqual(bags.get_option_value("depth"), "3")
        self.assertEqual(bags.get_option_value("limit"), "5")
        self.assertTrue(bags.has_option("json"))

        proj_dir = self.temp_dir / "cli_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        py_f = proj_dir / "app.py"
        py_f.write_text(
            "def core_work() -> int:\n    return 1\n\ndef entry_point() -> int:\n    return core_work()\n",
            encoding="utf-8",
        )
        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir / "cli_store")

        with patch.object(cli_mod, "guard_dispatch", return_value=None), patch.object(
            cli_mod, "_get_engine", return_value=engine
        ):
            out_buf = io.StringIO()
            err_buf = io.StringIO()
            with patch.object(sys, "stdout", out_buf), patch.object(sys, "stderr", err_buf):
                rc_ok = cli_mod.outline([str(py_f), "--json"])
            self.assertEqual(rc_ok, 0)
            parsed_outline = json.loads(out_buf.getvalue())
            self.assertEqual(len(parsed_outline["symbols"]), 2)

            # Missing file must return exit code 1 and preserve error in JSON
            out_missing = io.StringIO()
            with patch.object(sys, "stdout", out_missing), patch.object(sys, "stderr", err_buf):
                rc_err = cli_mod.outline([str(proj_dir / "missing.py"), "--json"])
            self.assertEqual(rc_err, 1)
            self.assertIn("error", json.loads(out_missing.getvalue()))

            # callers, callees, impact, status, clean via dispatch_cli
            for cmd_name, cmd_args in (
                ("callers", ["core_work", "--json"]),
                ("callees", ["entry_point", "--json"]),
                ("impact", ["core_work", "--depth", "2", "--json"]),
                ("status", ["--json"]),
                ("clean", ["--json"]),
            ):
                buf = io.StringIO()
                cmd_bag = cli_mod._normalize_bags(cmd_args, cmd_name)
                with patch.object(sys, "stdout", buf), patch.object(sys, "stderr", err_buf):
                    rc = cli_mod.dispatch_cli(CmdBags(raw_cmd="", command=cmd_name, args=cmd_bag.args, options=cmd_bag.options))
                self.assertEqual(rc, 0)
                self.assertTrue(buf.getvalue().strip().startswith("{"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_dev_and_migration_script_idempotency(self) -> None:
        """Verify scripts/hook.dev.py ignore patterns and scripts/migrations/1.0.1.x.py non-lock migration and idempotency."""
        dev_hook = load_ast_script("scripts/hook.dev.py", "ast_hook_dev")
        sb_root = self.temp_dir / "dev_sb"
        dev_hook.on_test_setup({"sandbox_dir": str(sb_root)})
        self.assertTrue((sb_root / ".storage.local" / "ast" / "indices").is_dir())
        self.assertTrue((sb_root / ".storage.local" / "ast" / "bundles").is_dir())
        self.assertTrue((sb_root / ".cache" / "ast").is_dir())
        dev_hook.on_test_teardown({"sandbox_dir": str(sb_root)})

        mig_mod = load_ast_script("scripts/migrations/1.0.1.x.py", "ast_mig_101x")
        fake_yscb = self.temp_dir / "yscb_root"
        legacy_indices = fake_yscb / ".cache" / "ast" / "indices"
        legacy_bundles = fake_yscb / ".cache" / "ast" / "bundles"
        legacy_indices.mkdir(parents=True, exist_ok=True)
        legacy_bundles.mkdir(parents=True, exist_ok=True)

        (legacy_indices / "unified.symbols.bin.gz").write_bytes(b"sym_data")
        (legacy_indices / ".index.lock").write_text("lock", encoding="utf-8")
        (legacy_bundles / "default.bundle.json").write_text("{}", encoding="utf-8")

        target_storage = fake_yscb / ".storage.local" / "ast"
        ctx = {"yscb_dir": str(fake_yscb), "storage_local_dir": str(target_storage)}
        self.assertTrue(mig_mod.migrate(ctx))

        self.assertTrue((target_storage / "indices" / "unified.symbols.bin.gz").is_file())
        self.assertTrue((target_storage / "bundles" / "default.bundle.json").is_file())
        self.assertFalse((target_storage / "indices" / ".index.lock").exists())
        self.assertTrue((legacy_indices / ".index.lock").is_file())

        # Second execution must be idempotent
        self.assertTrue(mig_mod.migrate(ctx))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_single_file_hot_patch_zero_full_tree_walks_and_cached_call_sites(self) -> None:
        """Verify single-file hot_patch_index with _cursor_already_consumed=True executes 0 iter_space_files walks and reuses cached call sites."""
        proj_dir = self.temp_dir / "perf_proj"
        src_dir = proj_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        f1 = src_dir / "alpha.py"
        f2 = src_dir / "beta.py"
        f1.write_text(
            "import os\n\ndef compute_alpha(x: int) -> int:\n    return x + 1\n",
            encoding="utf-8",
        )
        f2.write_text(
            "from src.alpha import compute_alpha\n\ndef run_beta() -> int:\n    return compute_alpha(10)\n",
            encoding="utf-8",
        )

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)

        bundle = engine.bundler.bundle_union(allow_parallel=False)
        self.assertEqual(len(bundle.symbols), 2)
        self.assertEqual(len(engine.bundler._file_call_sites_cache), 2)
        self.assertEqual(len(engine.bundler._file_imports_cache), 2)

        with patch.object(
            engine.bundler.parser_registry,
            "extract_call_sites",
            side_effect=AssertionError("extract_call_sites should not be re-invoked on cache hit"),
        ), patch.object(
            engine.bundler.parser_registry,
            "extract_imports",
            side_effect=AssertionError("extract_imports should not be re-invoked on cache hit"),
        ):
            sites, imps = engine.bundler.extract_all_call_sites_and_imports()
            self.assertTrue(any(s.callee_name == "compute_alpha" for s in sites))
            self.assertEqual(len(imps), 2)

        snap1 = engine.ensure_jit_synced(force=True)
        self.assertEqual(snap1.ast_generation, 1)

        f1.write_text(
            "import os\n\ndef compute_alpha(x: int) -> int:\n    return x + 2\n\ndef extra_helper() -> int:\n    return compute_alpha(5)\n",
            encoding="utf-8",
        )

        with patch.object(
            engine.space_manager,
            "iter_space_files",
            side_effect=AssertionError("Full-tree walk iter_space_files must not be called during single-file hot_patch_index"),
        ), patch.object(
            engine,
            "_consume_space_diff",
            side_effect=AssertionError("_consume_space_diff must not be called when _cursor_already_consumed=True"),
        ):
            snap2 = engine.hot_patch_index(
                {"modified": ["src/alpha.py"]},
                _cursor_already_consumed=True,
            )

        self.assertEqual(snap2.ast_generation, 2)
        sym_names = {s.name for s in snap2.symbols.values()}
        self.assertIn("extra_helper", sym_names)

        callers_res = engine.callers("compute_alpha")
        caller_names = {c["name"] for c in callers_res.get("callers", [])}
        self.assertIn("run_beta", caller_names)
        self.assertIn("extra_helper", caller_names)
        self.mark_passed()
