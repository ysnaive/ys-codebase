"""
Subsystem tests for GrammarProvisioner stderr isolation & negative cache (`ast_engine.provisioner`),
ASTEngine JIT incremental hot-patching (`ast_engine.engine`), and `scripts/hook.file-space.py` event bridge.
"""

import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)

from ast_engine.engine import ASTEngine
from ast_engine.provisioner import GrammarProvisioner
from dev.testing import Requirement, YSCBTestCase, require


class TestProvisionerAndJit(YSCBTestCase):
    """Tests for GrammarProvisioner stderr redirection, offline negative cache, JIT sync, and file-space hook."""

    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_jit_test_"))
        self.storage_dir = self.temp_dir / ".ast_cache"
        GrammarProvisioner.reset_cache()

    def tearDown(self):
        GrammarProvisioner.reset_cache()
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_provisioner_stderr_redirection_and_negative_cache(self):
        """FT-01: Verify GrammarProvisioner redirects pip subprocess output to sys.stderr and caches failed packages in _FAILED_PACKAGES."""
        run_calls = []

        def fake_subprocess_run(cmd, **kwargs):
            run_calls.append((cmd, kwargs))
            # Verify stdout and stderr are both strictly bound to sys.stderr
            self.assertIs(kwargs.get("stdout"), sys.stderr)
            self.assertIs(kwargs.get("stderr"), sys.stderr)
            return subprocess.CompletedProcess(cmd, returncode=1)

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        with patch("ast_engine.provisioner.subprocess.run", side_effect=fake_subprocess_run):
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

                # Second call must hit _FAILED_PACKAGES negative cache without spawning subprocess again
                lang2 = GrammarProvisioner.load_language(
                    lang_key="fake_lang",
                    module_name="tree_sitter_nonexistent_xyz",
                    auto_install_pkg="tree-sitter-nonexistent-xyz",
                    attempt_auto_install=True,
                )
                self.assertIsNone(lang2)
                self.assertEqual(len(run_calls), 1)

        # stdout must remain 100% clean (0 bytes written)
        self.assertEqual(stdout_capture.getvalue(), "")
        self.assertIn("[ast:warn]", stderr_capture.getvalue())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_ast_engine_jit_sync_hot_patch_and_external_edge_preservation(self):
        """FT-02: Verify ASTEngine.ensure_jit_synced builds index, hot-patches C# partial changes, preserves incoming edges, and increments ast_generation."""
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

        # Verify initial callers of BillingService.Charge include ProcessCheckout
        callers_initial = engine.callers("BillingService.Charge")
        caller_names_initial = {c["name"].split(".")[-1] for c in callers_initial.get("callers", [])}
        self.assertIn("ProcessCheckout", caller_names_initial)

        # Modify part1 and delete part2 to trigger incremental hot_patch_index
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

        # Verify deleted part2 member 'Refund' is purged from surviving BillingService partial class
        billing_cls = next((s for s in snap2.symbols.values() if s.kind == "class" and s.fqn == "App.Services.BillingService"), None)
        self.assertIsNotNone(billing_cls)
        surviving_members = {m.name for m in billing_cls.members}
        self.assertIn("Charge", surviving_members)
        self.assertIn("ValidateReceipt", surviving_members)
        self.assertNotIn("Refund", surviving_members)

        # Verify external incoming edge from untouched CheckoutController.ProcessCheckout -> BillingService.Charge is preserved
        callers_after = engine.callers("BillingService.Charge")
        caller_names_after = {c["name"].split(".")[-1] for c in callers_after.get("callers", [])}
        self.assertIn("ProcessCheckout", caller_names_after)

        # Verify status() and clean()
        st = engine.status()
        self.assertTrue(st["snapshot_exists"])
        self.assertEqual(st["ast_generation"], 2)

        clean_res = engine.clean()
        self.assertTrue(len(clean_res["removed"]) >= 1)
        self.assertFalse(engine.status()["snapshot_exists"])
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_file_space_hook_handles_events_and_graceful_errors(self):
        """ET-01: Verify scripts/hook.file-space.py on_file_space_changed updates index and handles empty/invalid payloads safely."""
        hook_path = Path(_AST_ROOT) / "scripts" / "hook.file-space.py"
        spec = importlib.util.spec_from_file_location("ast_hook_file_space", str(hook_path))
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)

        # Empty diff should return skipped safely
        res_empty = hook_mod.on_file_space_changed(diff_detail={})
        self.assertEqual(res_empty.get("status"), "skipped")

        # Valid diff with patched ASTEngine should invoke hot_patch_index and return updated status
        proj_dir = self.temp_dir / "hook_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "mod.py").write_text("def hello():\n    return 42\n", encoding="utf-8")

        engine = ASTEngine(project_root=proj_dir, storage_dir=self.storage_dir)
        engine.ensure_jit_synced(force=True)

        with patch("ast_engine.engine.ASTEngine", return_value=engine):
            res_ok = hook_mod.on_file_space_changed(
                space_name="default",
                diff_detail={"modified": ["mod.py"]},
            )
            self.assertEqual(res_ok.get("status"), "updated")
            self.assertTrue(res_ok.get("ast_generation", 0) >= 2)
        self.mark_passed()
