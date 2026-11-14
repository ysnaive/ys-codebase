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
import threading
from unittest.mock import patch

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if "tests" in sys.modules and getattr(sys.modules["tests"], "__file__", None) != str(Path(_TESTS_DIR) / "__init__.py"):
    del sys.modules["tests"]

from core.commands import CmdBags
from core.space import SpaceConfig
from ast_engine.bundler import _normalize_space_dirty_paths, restore_unaggregated_partial_symbol
from ast_engine.engine import ASTEngine
from ast_engine.io_utils import atomic_save_gzip_pickle
from ast_engine.provisioner import GrammarProvisioner
from ast_engine.schema import MemberInfo, UnifiedSymbol
from tests import ASTTestCase, Requirement, load_ast_script, require


class TestProvisionerAndJit(ASTTestCase):
    """Tests for GrammarProvisioner, JIT hot-patching, CLI commands, and lifecycle hooks."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_jit_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"
        self._neg_cache_patcher = patch.object(
            GrammarProvisioner,
            "_neg_cache_path",
            return_value=str(self.temp_dir / "provision_failed.json"),
        )
        self._neg_cache_patcher.start()
        GrammarProvisioner.reset_cache()

    def tearDown(self) -> None:
        GrammarProvisioner.reset_cache()
        if hasattr(self, "_neg_cache_patcher"):
            self._neg_cache_patcher.stop()
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
                self.assertIn("tree-sitter-nonexistent-xyz", GrammarProvisioner.get_failed_packages())

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
        """Verify ASTEngine.ensure_jit_synced builds index, hot-patches C# partial changes (including surviving sibling call relinking), preserves incoming edges, and increments ast_generation."""
        proj_dir = self.temp_dir / "project"
        svc_dir = proj_dir / "Services"
        svc_dir.mkdir(parents=True, exist_ok=True)

        part1 = svc_dir / "Billing.Part1.cs"
        part2 = svc_dir / "Billing.Part2.cs"
        helper_file = svc_dir / "ReceiptValidator.cs"
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
            "        public void Refund(int amount) {\n"
            "            _validator.Verify(amount);\n"
            "        }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        helper_file.write_text(
            "namespace App.Services {\n"
            "    public class ReceiptValidator {\n"
            "        public void Verify(int amount) {}\n"
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

        # Hot-patch Part1.cs to add `_validator` field while Part2.cs (surviving sibling) is unmodified:
        # Part2.cs's `_validator.Verify(amount)` call must be re-linked using the newly aggregated field type!
        part1.write_text(
            "namespace App.Services {\n"
            "    public partial class BillingService {\n"
            "        private ReceiptValidator _validator;\n"
            "        public void Charge(int amount) {}\n"
            "        public void ValidateReceipt() {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        snap_sib = engine.hot_patch_index(
            {
                "spaces": {
                    "default": {
                        "added": [],
                        "modified": ["Services/Billing.Part1.cs"],
                        "deleted": [],
                    }
                }
            }
        )
        self.assertEqual(snap_sib.ast_generation, 2)
        verify_callers = engine.callers("ReceiptValidator.Verify")
        verify_caller_names = {c["name"].split(".")[-1] for c in verify_callers.get("callers", [])}
        self.assertIn("Refund", verify_caller_names)

        # Now delete Part2.cs and verify eviction + surviving Part1 members
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
        self.assertEqual(snap2.ast_generation, 3)

        billing_cls = next((s for s in snap2.symbols.values() if s.kind == "class" and s.fqn == "App.Services.BillingService"), None)
        self.assertIsNotNone(billing_cls)
        assert billing_cls is not None
        surviving_members = {m.name for m in billing_cls.members}
        self.assertEqual(surviving_members, {"_validator", "Charge", "ValidateReceipt"})

        callers_after = engine.callers("BillingService.Charge")
        caller_names_after = {c["name"].split(".")[-1] for c in callers_after.get("callers", [])}
        self.assertIn("ProcessCheckout", caller_names_after)

        st = engine.status()
        self.assertTrue(st["snapshot_exists"])
        self.assertEqual(st["ast_generation"], 3)

        clean_res = engine.clean()
        self.assertEqual(len(clean_res["removed"]), 3)
        self.assertFalse(engine.status()["snapshot_exists"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_file_space_hook_lifecycle_and_generation_fallback(self) -> None:
        """Verify scripts/hook.core.py handles non-target space ignore, non-parseable dirty file skip, persisted generation fallback, rebuilt/patched/noop paths, and declarative space registration."""
        hook_mod = load_ast_script("scripts/hook.core.py", "ast_hook_core")

        res_empty = hook_mod.on_file_space_changed(diff_detail={})
        self.assertEqual(res_empty.get("status"), "skipped")

        proj_dir = self.temp_dir / "hook_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        mod_file = proj_dir / "mod.py"
        mod_file.write_text("def hello():\n    return 42\n", encoding="utf-8")

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        # Verify declarative register_spaces / get_target_spaces SDK
        self.assertIn("project/default", engine.get_target_spaces())
        engine.register_spaces(["default"])
        self.assertIn("project/default", engine.get_target_spaces())

        res_cloud = hook_mod.on_file_space_changed(
            engine=engine,
            space_name="cloud",
            diff_detail={"modified": ["a.py"]},
        )
        self.assertEqual(res_cloud.get("status"), "noop")

        broadcast_events = []

        with patch("core.events.broadcast", side_effect=lambda ev, payload, **kw: broadcast_events.append((ev, payload))):
            # 1. Initial event with no existing snapshot -> status == "rebuilt"
            res_rebuilt = hook_mod.on_file_space_changed(
                context={"engine": engine, "space_name": "default", "diff_summary": {"added": 1}},
            )
            self.assertEqual(res_rebuilt.get("status"), "rebuilt")
            self.assertEqual(res_rebuilt.get("ast_generation"), 1)
            self.assertEqual(len(broadcast_events), 1)

            # 2. Fresh cold engine (engine._snapshot is None): non-target space ("cloud") should read persisted generation (1)
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

            # 4. Non-parseable file change (.json) -> status == "noop" without incrementing ast_generation
            (proj_dir / "settings.json").write_text('{"debug": true}\n', encoding="utf-8")
            res_non_parseable = hook_mod.on_file_space_changed(context={"engine": engine, "space_name": "default"})
            self.assertEqual(res_non_parseable.get("status"), "noop")
            self.assertEqual(res_non_parseable.get("ast_generation"), 2)

            # 5. No changes -> status == "noop"
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

        # Verify scripts/hook.core.py _resolve_consume_diff does NOT wipe UNIFIED_KEY (None) cursor after single-space consume
        from contextlib import contextmanager

        ack_records = []

        class _FakeDiff:
            has_changes = False
            to_generation = 3

        class _FakeScanner:
            @contextmanager
            def consume_diff(self, space_name, **_kw):
                yield _FakeDiff()

            def ack(self, space_query, **kwargs):
                ack_records.append((space_query, kwargs))

        class _FakeEng:
            scanner = _FakeScanner()

        hook_core = load_ast_script("scripts/hook.core.py", "ast_hook_core")
        with hook_core._resolve_consume_diff(_FakeEng(), space_name="project/default", consumer_id="ast"):
            pass
        self.assertNotIn((None, {"consumer_id": "ast"}), ack_records)

        # Verify SemanticBundler transient caches are cleared after build_index and hot_patch_index
        self.assertEqual(len(engine.bundler._file_symbols_cache), 0)
        self.assertEqual(len(engine.bundler._file_call_sites_cache), 0)
        self.assertEqual(len(engine.bundler._file_imports_cache), 0)
        self.assertEqual(len(engine.bundler._last_bundle_unique_files), 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_transactional_cursor_rollback_partial_immutability_and_multi_root_disambiguation(self) -> None:
        """Verify cursor rollback on hot_patch failure, partial symbol restoration immutability, multi-root dirty path disambiguation, and tmp cleanup."""
        # 1. Partial symbol restoration returns deep-copied structures without mutating original
        orig_member = MemberInfo(name="Save", kind="method", signature="public void Save()", line_number=10)
        partial_sym = UnifiedSymbol(
            id="p1",
            name="User",
            kind="class",
            file_path="src/User.Part1.cs",
            line_number=1,
            language="c_sharp",
            fqn="App.User",
            members=(orig_member,),
            metadata={
                "is_partial": True,
                "base_types": ["IEntity"],
                "field_types": {"_id": "string"},
                "_own_members": [orig_member],
                "_own_base_types": ["IEntity"],
                "_own_field_types": {"_id": "string"},
                "partial_files": ["src/User.Part1.cs", "src/User.Part2.cs"],
            },
        )
        restored = restore_unaggregated_partial_symbol(partial_sym)
        restored.metadata["base_types"].append("MutatedBase")
        restored.metadata["field_types"]["_extra"] = "int"
        self.assertEqual(partial_sym.metadata["base_types"], ["IEntity"])
        self.assertEqual(partial_sym.metadata["field_types"], {"_id": "string"})
        self.assertIn("partial_files", partial_sym.metadata)
        self.assertNotIn("partial_files", restored.metadata)

        # 2. Multi-root subdirectory path disambiguation by mtime and known_indexed_files for deleted paths
        root_a = self.temp_dir / "multi_a"
        root_b = self.temp_dir / "multi_b"
        (root_a / "sub").mkdir(parents=True, exist_ok=True)
        (root_b / "sub").mkdir(parents=True, exist_ok=True)
        file_a = root_a / "sub" / "mod.py"
        file_b = root_b / "sub" / "mod.py"
        file_a.write_text("x = 1\n", encoding="utf-8")
        file_b.write_text("x = 2\n", encoding="utf-8")
        import os

        os.utime(file_a, ns=(1_000_000_000, 1_000_000_000))
        os.utime(file_b, ns=(2_000_000_000, 2_000_000_000))

        sp_cfg = SpaceConfig(
            qualified_name="project/multi",
            short_name="multi",
            owner="project",
            entries=(str(root_a), str(root_b)),
        )
        expanded_mod = _normalize_space_dirty_paths(
            ["sub/mod.py"],
            [sp_cfg],
            prefer_missing=False,
        )
        self.assertIn(str(file_b.resolve()).replace("\\", "/"), expanded_mod)
        self.assertNotIn(str(file_a.resolve()).replace("\\", "/"), expanded_mod)

        file_a.unlink()
        file_b.unlink()
        expanded_del = _normalize_space_dirty_paths(
            ["sub/mod.py"],
            [sp_cfg],
            prefer_missing=True,
            known_indexed_files={str(file_a.resolve()).replace("\\", "/")},
        )
        self.assertIn(str(file_a.resolve()).replace("\\", "/"), expanded_del)
        self.assertNotIn(str(file_b.resolve()).replace("\\", "/"), expanded_del)

        # 3. Transactional cursor rollback in ensure_jit_synced when hot_patch_index fails
        proj_dir = self.temp_dir / "tx_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        mod_f = proj_dir / "svc.py"
        mod_f.write_text("def step_one() -> int:\n    return 1\n", encoding="utf-8")
        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir / "tx_store")
        engine.ensure_jit_synced(force=True)

        mod_f.write_text("def step_one() -> int:\n    return 2\n\ndef step_two() -> int:\n    return step_one()\n", encoding="utf-8")
        with patch.object(engine, "hot_patch_index", side_effect=RuntimeError("Simulated hot_patch crash")):
            engine.ensure_jit_synced()

        # Because hot_patch_index raised inside the ExitStack, the cursor was NOT committed,
        # so the next ensure_jit_synced() still sees the pending diff and hot-patches `step_two`!
        snap_recovered = engine.ensure_jit_synced()
        self.assertIn("step_two", {s.name for s in snap_recovered.symbols.values()})

        # 4. atomic_save_gzip_pickle cleans up temporary .tmp files on write failure
        bad_target = self.temp_dir / "clean_tmp_dir" / "test.bin.gz"
        bad_target.parent.mkdir(parents=True, exist_ok=True)
        (bad_target.parent / f".{bad_target.name}.tmp.99999").write_bytes(b"stale")
        with patch("ast_engine.io_utils.write_bytes", side_effect=RuntimeError("Simulated write error")):
            with self.assertRaises(RuntimeError):
                atomic_save_gzip_pickle(bad_target, {"k": "v"})
        leftover_tmps = list(bad_target.parent.glob("*.tmp"))
        self.assertEqual(leftover_tmps, [])

        # 5. GrammarProvisioner single-flight _INFLIGHT_EVENTS deduplication across concurrent threads
        install_calls = []
        start_bar = threading.Barrier(2)
        entered_install = threading.Event()

        def slow_install(pkg_name: str, **kwargs) -> bool:
            install_calls.append(pkg_name)
            entered_install.set()
            threading.Event().wait(timeout=0.02)
            return False

        GrammarProvisioner.reset_cache()
        with patch.object(GrammarProvisioner, "_try_pip_install", side_effect=slow_install):
            results = [None, None]

            def worker(idx: int) -> None:
                try:
                    start_bar.wait(timeout=1.0)
                except Exception:
                    pass
                if idx == 1:
                    entered_install.wait(timeout=1.0)
                results[idx] = GrammarProvisioner.load_language(
                    lang_key="concurrent_lang",
                    module_name="tree_sitter_concurrent_nonexistent",
                    auto_install_pkg="tree-sitter-concurrent-nonexistent",
                    attempt_auto_install=True,
                )

            t1 = threading.Thread(target=worker, args=(0,))
            t2 = threading.Thread(target=worker, args=(1,))
            t1.start()
            t2.start()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)

        self.assertEqual(len(install_calls), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention(self) -> None:
        """Verify status() O(1) meta fast path, non-blocking partial outline(), bundler extension pre-filtering, and hook worker delegation."""
        from core.platform.lock import InterProcessLock

        proj_dir = self.temp_dir / "lock_free_proj"
        ui_dir = proj_dir / "UI"
        ui_dir.mkdir(parents=True, exist_ok=True)

        core_cs = ui_dir / "Panel.Core.cs"
        events_cs = ui_dir / "Panel.Events.cs"
        non_code_json = ui_dir / "settings.json"
        non_code_uxml = ui_dir / "Panel.uxml"

        core_cs.write_text(
            "namespace UI {\n"
            "    public partial class Panel {\n"
            "        public void Open() { Helper(); }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        events_cs.write_text(
            "namespace UI {\n"
            "    public partial class Panel {\n"
            "        private void Helper() {}\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        non_code_json.write_text('{"theme": "dark"}\n', encoding="utf-8")
        non_code_uxml.write_text("<ui:UXML />\n", encoding="utf-8")

        engine = ASTEngine(
            project_root=proj_dir,
            storage_dir=self.storage_dir / "lock_free_store",
            custom_spaces={
                "default": SpaceConfig(
                    qualified_name="project/default",
                    owner="project",
                    short_name="default",
                    entries=(str(proj_dir),),
                )
            },
        )
        snap = engine.build_index(allow_parallel=False)
        self.assertEqual(len(snap.file_graphs), 2)
        self.assertNotIn("UI/settings.json", snap.file_graphs)
        self.assertNotIn("UI/Panel.uxml", snap.file_graphs)

        meta = engine.get_persisted_meta()
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertIn("total_edges", meta)
        self.assertIn("space_symbol_counts", meta)
        self.assertEqual(meta["total_files"], 2)

        # Clear in-memory caches so status() and get_persisted_meta() read from unified.meta.json
        engine._snapshot = None
        engine._graph = None

        locked_evt = threading.Event()
        release_evt = threading.Event()

        def hold_locks() -> None:
            lock_file = str(engine._resolve_index_lock_path())
            with engine._lock, InterProcessLock(lock_file, timeout=5.0):
                locked_evt.set()
                release_evt.wait(timeout=5.0)

        holder = threading.Thread(target=hold_locks, daemon=True)
        holder.start()
        self.assertTrue(locked_evt.wait(timeout=2.0))
        try:
            st_all = engine.status()
            self.assertTrue(st_all["index_exists"])
            self.assertEqual(st_all["total_files"], 2)
            self.assertGreaterEqual(st_all["total_symbols"], 2)

            st_sp = engine.status(space="default")
            self.assertEqual(st_sp["total_files"], 2)
            self.assertGreaterEqual(st_sp["total_symbols"], 2)

            # Single-file outline with merged=False must not block even when engine._lock is held
            out_single = engine.outline(str(core_cs), merged=False)
            self.assertFalse(out_single["merged"])
            self.assertEqual(len(out_single["symbols"]), 1)
        finally:
            release_evt.set()
            holder.join(timeout=2.0)

        # Verify hook.core.py delegates to active in-process KnowledgeDBServiceWorker when engine is not explicitly passed
        hook_mod = load_ast_script("scripts/hook.core.py", "ast_hook_core_delegate_test")
        notified = []

        from core.context import get_runtime_context

        class _DummyWorker:
            def is_alive(self) -> bool:
                return True

            def notify_space_changed(self) -> None:
                notified.append(True)

        ctx = get_runtime_context()
        prev_mem = ctx.get_module_state("knowledge_db.service.mem_state")
        ctx.set_module_state("knowledge_db.service.mem_state", {"active_worker": _DummyWorker()})
        try:
            with patch("ast_engine.engine.get_engine", return_value=engine):
                res_delegated = hook_mod.on_file_space_changed(context={"space_name": "default"})
                self.assertEqual(res_delegated["status"], "noop")
                self.assertEqual(len(notified), 1)
        finally:
            ctx.set_module_state("knowledge_db.service.mem_state", prev_mem)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_slice_part_single_file_o1_fast_path_progress_and_nonblocking_status(self) -> None:
        """
        Verify:
        1. `ASTEngine.slice_part("<rel_path>::<fqn>")` and `slice_part(UnifiedSymbol)` execute in O(1) single-file
           `parse_file()` mode without calling `get_workspace_graph()`.
        2. C++ double-colon namespace selectors (`Physics::Solver::step`) gracefully fall back to workspace graph resolution.
        3. `build_index(force=True)` with `YSCB_FORCE_PROGRESS=1` emits `[ast]` progress to `stderr` while keeping `stdout` empty.
        4. `ASTEngine.status()` reports `building_in_progress=True` non-blockingly when `_lock` is held, and clears stale
           in-memory cache when `.bin.gz` is externally deleted.
        """
        import contextlib
        import io
        import time
        from core.context import bind_runtime_context

        ws_root = Path(self.temp_dir) / "ws_slice_fast"
        pkg_dir = ws_root / "pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        py_file = pkg_dir / "service.py"
        py_file.write_text(
            "class OrderProcessor:\n"
            "    def compute_total(self, qty: int, price: int) -> int:\n"
            "        return qty * price\n",
            encoding="utf-8",
        )
        cpp_file = pkg_dir / "solver.cpp"
        cpp_file.write_text(
            "namespace Physics {\n"
            "class Solver {\n"
            "public:\n"
            "    int step(int dt) { return dt + 1; }\n"
            "};\n"
            "}\n",
            encoding="utf-8",
        )

        sp = SpaceConfig(
            qualified_name="project/fast_ast",
            owner="project",
            short_name="fast_ast",
            entries=(str(ws_root),),
        )
        storage_dir = Path(self.temp_dir) / "storage_slice_fast"
        engine = ASTEngine(
            storage_dir=storage_dir,
            project_root=ws_root,
            contributes_data={"spaces": {"fast_ast": sp}},
        )

        # 1. O(1) single-file fast path for "<rel_path>::<fqn>" without building workspace graph
        with patch.object(
            engine,
            "get_workspace_graph",
            side_effect=AssertionError("get_workspace_graph must not be invoked for <rel_path>::<fqn>"),
        ):
            res_fast = engine.slice_part("pkg/service.py::OrderProcessor.compute_total", part="outer")
            self.assertIn("return qty * price", res_fast)

            # Also verify UnifiedSymbol direct input takes O(1) single-file fast path
            from ast_engine import UnifiedSymbol

            usym = UnifiedSymbol(
                id="pkg/service.py::OrderProcessor.compute_total",
                name="compute_total",
                fqn="OrderProcessor.compute_total",
                kind="method",
                file_path="pkg/service.py",
                line_number=2,
                end_line=3,
                language="python",
            )
            res_usym = engine.slice_part(usym, part="outer")
            self.assertIn("return qty * price", res_usym)

        # 2. C++ double-colon selector ("Physics::Solver::step") where "Physics" is NOT a file falls back to workspace graph
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with bind_runtime_context(env={"YSCB_FORCE_PROGRESS": "1"}), contextlib.redirect_stdout(
            out_buf
        ), contextlib.redirect_stderr(err_buf):
            engine.build_index()
        self.assertEqual(out_buf.getvalue(), "")
        self.assertIn("[ast]", err_buf.getvalue())

        from ast_engine.exceptions import ASTError

        res_cpp = engine.slice_part("Physics::Solver::step", part="outer")
        self.assertIn("return dt + 1;", res_cpp)

        # Non-file "::" selector must fall back to workspace graph (raising ASTError, never FileNotFoundError)
        with self.assertRaises(ASTError):
            engine.slice_part("NonExistentNamespace::MissingSymbol", part="outer")

        # 3. Non-blocking status() while engine._lock is held by another thread
        lock_held = threading.Event()
        release_evt = threading.Event()

        def _hold_ast_lock() -> None:
            with engine._lock:
                lock_held.set()
                release_evt.wait(timeout=3.0)

        holder = threading.Thread(target=_hold_ast_lock, daemon=True)
        holder.start()
        try:
            self.assertTrue(lock_held.wait(timeout=2.0))
            t0 = time.perf_counter()
            st_busy = engine.status()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.assertTrue(st_busy["building_in_progress"])
            self.assertLess(elapsed_ms, 50.0)
        finally:
            release_evt.set()
            holder.join(timeout=2.0)

        # 4. clean() preserves monotonic ast_generation floor across rebuilds, and hot_patch_index lazily hydrates workspace_graph on callers()
        gen_before_clean = engine.status()["ast_generation"]
        engine.clean()
        st_cleaned = engine.status()
        self.assertFalse(st_cleaned["index_exists"])
        self.assertEqual(st_cleaned["total_symbols"], 0)
        rebuilt_snap = engine.build_index()
        self.assertGreater(rebuilt_snap.ast_generation, gen_before_clean)
        engine.hot_patch_index(["pkg/service.py"])
        self.assertIsNone(engine._graph.workspace_graph)
        callers_res = engine.callers("OrderProcessor.compute_total", snippet=False)
        self.assertIsNotNone(engine._graph.workspace_graph)
        self.assertIn("total_callers", callers_res)

        # 5. CRLF + multi-byte UTF-8 lossless byte coordinate alignment across parse_file, workspace_graph, and slice_part
        crlf_file = pkg_dir / "crlf_order.py"
        crlf_file.write_bytes(
            b"# \xe8\xa8\x82\xe5\x96\xae\xe6\xa8\xa1\xe7\xb5\x84 line 1\r\n"
            b"# line 2\r\n"
            b"# line 3\r\n"
            b"class CrlfHandler:\r\n"
            b"    def process_order(self, order_id: int) -> bool:\r\n"
            b"        return order_id > 0\r\n"
        )
        engine.build_index()
        crlf_node = engine.parse_file("pkg/crlf_order.py").all_nodes_by_id["pkg/crlf_order.py::CrlfHandler.process_order"]
        sliced_crlf = engine.slice_part(crlf_node, part="outer")
        self.assertTrue(sliced_crlf.strip().startswith("def process_order(self, order_id: int) -> bool:"))
        self.assertTrue(sliced_crlf.strip().endswith("return order_id > 0"))
        sliced_fast_crlf = engine.slice_part("pkg/crlf_order.py::CrlfHandler.process_order", part="outer")
        self.assertEqual(sliced_crlf, sliced_fast_crlf)

        # 6. Default _custom_storage_dir=False ensure_jit_synced() & targeted clean(space=...) never raise AttributeError on space_manager/space_registry
        self.assertIs(engine.bundler.space_registry, engine.bundler.space_manager)
        engine._custom_storage_dir = False
        try:
            synced_snap = engine.ensure_jit_synced()
            self.assertIsNotNone(synced_snap)
            cleaned_targeted = engine.clean(space="project/default")
            self.assertEqual(cleaned_targeted["status"], "cleaned")
        finally:
            engine._custom_storage_dir = True
        self.mark_passed()

    @require(Requirement.ENV)
    def test_provisioner_cross_process_lock_timeout_and_persisted_negative_cache(self) -> None:
        """Verify GrammarProvisioner blocks/times out on real cross-process InterProcessLock contention and persists offline failure TTL."""
        from core import uri
        import os
        import time

        GrammarProvisioner.reset_cache()
        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode=1)

        stderr_buf = io.StringIO()
        yscb_root = uri.resolve_yscb_root()
        lock_dir = os.path.join(yscb_root, ".venv")
        os.makedirs(lock_dir, exist_ok=True)
        lock_path = os.path.join(lock_dir, ".pip_install.lock")
        ready_file = self.temp_dir / "lock_held.ready"

        holder_code = (
            "import sys, time\n"
            "from pathlib import Path\n"
            f"sys.path[:0] = {sys.path!r}\n"
            "from core.platform.lock import InterProcessLock\n"
            f"lk = InterProcessLock({lock_path!r})\n"
            "assert lk.acquire(blocking=True, timeout_sec=5.0)\n"
            f"Path({str(ready_file)!r}).write_text('1', encoding='utf-8')\n"
            "time.sleep(2.0)\n"
            "lk.release()\n"
        )
        holder_proc = subprocess.Popen([sys.executable, "-c", holder_code])
        try:
            deadline = time.monotonic() + 5.0
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready_file.exists())

            with patch("ast_engine.provisioner.subprocess.run", side_effect=fake_run), patch.object(
                sys, "stderr", stderr_buf
            ):
                res_locked = GrammarProvisioner._try_pip_install(
                    "tree-sitter-contended-pkg",
                    "tree_sitter_contended_pkg",
                    lock_timeout_sec=0.12,
                )
                self.assertFalse(res_locked)
                self.assertEqual(len(run_calls), 0)
        finally:
            holder_proc.terminate()
            holder_proc.wait(timeout=3.0)

        with patch("ast_engine.provisioner.subprocess.run", side_effect=fake_run), patch.object(
            sys, "stderr", stderr_buf
        ):
            res1 = GrammarProvisioner._try_pip_install("tree-sitter-offline-ttl-pkg", "tree_sitter_offline_ttl_pkg")
            self.assertFalse(res1)
            self.assertEqual(len(run_calls), 1)
            self.assertTrue(GrammarProvisioner._is_persisted_failed("tree-sitter-offline-ttl-pkg"))

            GrammarProvisioner.get_failed_packages().clear()
            res2 = GrammarProvisioner._try_pip_install("tree-sitter-offline-ttl-pkg", "tree_sitter_offline_ttl_pkg")
            self.assertFalse(res2)
            self.assertEqual(len(run_calls), 1)

        GrammarProvisioner.reset_cache()
        self.assertFalse(GrammarProvisioner._is_persisted_failed("tree-sitter-offline-ttl-pkg"))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_workspace_graph_hydration_meta_sync_cow_concurrency_and_deleted_callee_safety(self) -> None:
        """Verify hydrated workspace_graph updates unified.meta.json, concurrent status() during hot_patch_index never hits RuntimeError, deleted callees do not phantom-relink, and nested spaces isolate dirty paths."""
        import time

        proj_dir = self.temp_dir / "cow_proj"
        pkg_dir = proj_dir / "pkg"
        nested_mod_dir = proj_dir / "space_a" / "mod"
        root_mod_dir = proj_dir / "mod"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        nested_mod_dir.mkdir(parents=True, exist_ok=True)
        root_mod_dir.mkdir(parents=True, exist_ok=True)

        helper_py = pkg_dir / "helper.py"
        unrelated_py = pkg_dir / "unrelated.py"
        caller_py = pkg_dir / "caller.py"
        nested_init = nested_mod_dir / "__init__.py"
        root_init = root_mod_dir / "__init__.py"

        helper_py.write_text(
            "class Helper:\n"
            "    def unique_target_fn(self, x: int) -> int:\n"
            "        return x * 2\n",
            encoding="utf-8",
        )
        unrelated_py.write_text(
            "class UnrelatedBox:\n"
            "    def unique_target_fn(self, x: int) -> int:\n"
            "        return x + 999\n",
            encoding="utf-8",
        )
        caller_py.write_text(
            "from pkg.helper import Helper\n"
            "def run_job() -> int:\n"
            "    h = Helper()\n"
            "    return h.unique_target_fn(21)\n",
            encoding="utf-8",
        )
        nested_init.write_text("class SpaceANestedMod:\n    pass\n", encoding="utf-8")
        root_init.write_text("class RootModSurvivor:\n    pass\n", encoding="utf-8")

        sp_root = SpaceConfig(
            qualified_name="project/cow_space",
            owner="project",
            short_name="cow_space",
            entries=(proj_dir.as_posix(),),
        )
        sp_nested = SpaceConfig(
            qualified_name="project/nested_a",
            owner="project",
            short_name="nested_a",
            entries=((proj_dir / "space_a").as_posix(),),
        )
        engine = ASTEngine(
            project_root=proj_dir,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"cow_space": sp_root, "nested_a": sp_nested}},
        )
        snap0 = engine.build_index()
        orig_syms_keys = set(snap0.symbols.keys())

        # 1. Concurrent lock-free status(space=...) readers during repeated hot_patch_index must never raise RuntimeError
        reader_errors = []
        stop_readers = threading.Event()

        def _status_reader() -> None:
            while not stop_readers.is_set():
                try:
                    st = engine.status(space="cow_space")
                    assert isinstance(st.get("total_symbols"), int)
                except Exception as exc:
                    reader_errors.append(exc)

        r_thread = threading.Thread(target=_status_reader, daemon=True)
        r_thread.start()
        try:
            for step_i in range(4):
                caller_py.write_text(
                    "from pkg.helper import Helper\n"
                    f"def run_job() -> int:\n    h = Helper()\n    return h.unique_target_fn({step_i})\n"
                    f"def extra_{step_i}() -> int:\n    return {step_i}\n",
                    encoding="utf-8",
                )
                snap_step = engine.hot_patch_index([caller_py.as_posix()])
                self.assertIsNot(snap0, snap_step)
        finally:
            stop_readers.set()
            r_thread.join(timeout=2.0)
        self.assertEqual(reader_errors, [])
        self.assertEqual(set(snap0.symbols.keys()), orig_syms_keys)
        self.assertIsNone(engine._graph.workspace_graph)

        # 2. First callers() hydrates workspace_graph AND updates unified.meta.json so fresh cold ASTEngine.status() hits O(1) meta fast-path without unpickling
        res_callers = engine.callers("Helper.unique_target_fn", snippet=False)
        self.assertGreaterEqual(res_callers["total_callers"], 1)

        engine_cold = ASTEngine(
            project_root=proj_dir,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"cow_space": sp_root, "nested_a": sp_nested}},
        )
        meta_now = engine_cold.get_persisted_meta()
        self.assertIsNotNone(meta_now)
        with patch("ast_engine.engine.load_gzip_pickle", side_effect=AssertionError("status() must not unpickle")):
            st_fast = engine_cold.status()
            self.assertTrue(st_fast["index_exists"])

        # 3. Deleting pkg/helper.py (defining unique_target_fn) must NOT phantom-relink run_job -> UnrelatedBox.unique_target_fn
        helper_py.unlink()
        from core.space import ScanDiffDetail
        engine.hot_patch_index(ScanDiffDetail(added=set(), modified=set(), deleted={"pkg/helper.py"}))
        unrelated_sym = next(s for s in engine._snapshot.symbols.values() if "UnrelatedBox.unique_target_fn" in (s.fqn or s.name))
        preds = list(engine._graph.graph.predecessors(unrelated_sym.id)) if engine._graph.graph.has_node(unrelated_sym.id) else []
        self.assertEqual(preds, [])

        # 3b. Querying callers(..., space='cow_space') must NOT treat sibling space 'nested_a' as stale or evict SpaceANestedMod!
        # Also verify non-parseable dirty file (.txt) does not trigger unnecessary hot_patch_index!
        non_code_txt = proj_dir / "notes.txt"
        non_code_txt.write_text("plain text change\n", encoding="utf-8")
        gen_before_scoped_q = engine._snapshot.ast_generation
        _ = engine.callers("RootModSurvivor", space="cow_space")
        self.assertEqual(engine._snapshot.ast_generation, gen_before_scoped_q)
        self.assertIn("SpaceANestedMod", {s.name for s in engine._snapshot.symbols.values()})

        # 4. Deleting space_a/mod/__init__.py via absolute path must NOT evict root mod/__init__.py (RootModSurvivor)
        nested_init.unlink()
        engine.hot_patch_index(ScanDiffDetail(added=set(), modified=set(), deleted={nested_init.as_posix()}))
        rem_names = {s.name for s in engine._snapshot.symbols.values()}
        self.assertNotIn("SpaceANestedMod", rem_names)
        self.assertIn("RootModSurvivor", rem_names)

        # 5. Stale config_hash triggers rebuild on ensure_jit_synced()
        with engine_cold._lock:
            engine_cold._ensure_loaded_from_disk()
            assert engine_cold._snapshot is not None
            gen_prev = engine_cold._snapshot.ast_generation
            engine_cold._snapshot.config_hash = "stale_hash_0000"
        rebuilt = engine_cold.ensure_jit_synced(allow_parallel=False)
        self.assertGreater(rebuilt.ast_generation, gen_prev)
        self.assertNotEqual(rebuilt.config_hash, "stale_hash_0000")

        # 6. Verify CallGraphIndex.clone_shallow isolates edge call_sites lists & preserves ast_generation
        from ast_engine.graph import CallGraphIndex
        from ast_engine.schema import SymbolCallSite

        g_orig = CallGraphIndex(ast_generation=7)
        site1 = SymbolCallSite(callee_name="b", line_number=1, caller_symbol_id="a", file_path="x.py")
        site2 = SymbolCallSite(callee_name="b", line_number=9, caller_symbol_id="a", file_path="x.py")
        g_orig.add_edge("a", "b", site1)
        g_clone = g_orig.clone_shallow()
        g_clone.add_edge("a", "b", site2)
        self.assertEqual(len(g_orig.get_call_sites("a", "b")), 1)
        self.assertEqual(len(g_clone.get_call_sites("a", "b")), 2)
        self.assertEqual(g_clone.ast_generation, 7)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_concurrent_callers_outline_and_worker_hook_no_deadlock(self) -> None:
        """Verify concurrent callers/outline, TreeSitter driver parsing, and worker-mode hook callbacks never deadlock."""
        from core.context import bind_runtime_context

        proj_dir = self.temp_dir / "conc_ast_proj"
        pkg_dir = proj_dir / "pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        helper_py = pkg_dir / "helper.py"
        caller_py = pkg_dir / "caller.py"
        helper_py.write_text("def target_fn(v: int) -> int:\n    return v + 1\n", encoding="utf-8")
        caller_py.write_text(
            "from pkg.helper import target_fn\n\ndef entry_fn(x: int) -> int:\n    return target_fn(x)\n",
            encoding="utf-8",
        )
        sp_cfg = SpaceConfig(
            qualified_name="project/conc_ast",
            owner="project",
            short_name="conc_ast",
            entries=(str(proj_dir),),
        )
        engine = ASTEngine(
            project_root=proj_dir,
            storage_dir=self.storage_dir,
            contributes_data={"spaces": {"conc_ast": sp_cfg}},
        )
        engine.build_index(allow_parallel=False)

        # In WarmWorker mode, file-space change broadcasts must not block waiting on engine._lock.
        hook_mod = load_ast_script("scripts/hook.core.py", "ast_hook_core_conc_test")
        hook_result = {}
        with engine._lock:
            with patch("ast_engine.engine.get_engine", return_value=engine), bind_runtime_context(
                env={"YSCB_IN_SERVER_WORKER": "1"}
            ):
                th_hook = threading.Thread(
                    target=lambda: hook_result.update(hook_mod.on_file_space_changed(spaces=["conc_ast"])),
                    daemon=True,
                )
                th_hook.start()
                th_hook.join(timeout=2.0)
                self.assertFalse(th_hook.is_alive())
        self.assertEqual(hook_result.get("status"), "noop")

        py_driver = engine.parser_registry.get_parser(str(helper_py))
        errors: list = []

        def _callers_worker() -> None:
            try:
                for step in range(8):
                    caller_py.write_text(
                        "from pkg.helper import target_fn\n\n"
                        f"def entry_fn(x: int) -> int:\n    return target_fn(x + {step})\n",
                        encoding="utf-8",
                    )
                    res = engine.callers("target_fn", snippet=False)
                    self.assertGreaterEqual(res["total_callers"], 1)
            except Exception as exc:
                errors.append(exc)

        def _outline_and_parse_worker() -> None:
            try:
                src_text = helper_py.read_text(encoding="utf-8")
                for _ in range(15):
                    out = engine.outline("pkg/helper.py")
                    self.assertGreaterEqual(len(out.get("symbols", [])), 1)
                    if py_driver is not None:
                        syms = py_driver.parse(str(helper_py), src_text, "conc_ast")
                        self.assertGreaterEqual(len(syms), 1)
                        _ = py_driver.extract_call_sites(str(helper_py), src_text, "conc_ast", symbols=syms)
                        _ = py_driver.extract_file_graph(file_path=str(helper_py), content=src_text, space="conc_ast")
            except Exception as exc:
                errors.append(exc)

        workers = [
            threading.Thread(target=_callers_worker, daemon=True),
            threading.Thread(target=_outline_and_parse_worker, daemon=True),
            threading.Thread(target=_outline_and_parse_worker, daemon=True),
        ]
        for th in workers:
            th.start()
        for th in workers:
            th.join(timeout=10.0)
            self.assertFalse(th.is_alive())
        self.assertEqual(errors, [])
        self.mark_passed()
