"""
Official test suite for dev.scaffold.Scaffolder.
"""
import importlib.util
from unittest.mock import patch
from dev.testing import YSCBTestCase, require, Requirement
from dev.scaffold import Scaffolder
from dev.checker import Checker
from core import uri, vfs


@require(Requirement.ENV)
class TestDevScaffolder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.scaffolder = Scaffolder()

    def test_create_module_creates_all_templates(self):
        """Verify create_module produces manifest, cli.py, __init__.py, .yscbignore and passes Checker."""
        mod_name = "test_mod_scaffold_x"
        try:
            ok, msg = self.scaffolder.create_module(mod_name, description="Unit test module")
            self.assertTrue(ok, f"Scaffold failed: {msg}")

            src_uri = f"module.source://{mod_name}"
            self.assertTrue(vfs.exists(f"{src_uri}/manifest.json"))
            self.assertEqual(vfs.read_json(f"{src_uri}/manifest.json")["dependencies"]["core"], ">=1.2.0")
            self.assertTrue(vfs.exists(f"{src_uri}/scripts/cli.py"))
            self.assertTrue(vfs.exists(f"{src_uri}/{mod_name}/__init__.py"))
            self.assertTrue(vfs.exists(f"{src_uri}/.yscbignore"))
            self.assertTrue(vfs.exists(f"{src_uri}/contributes/_format.json"))
            self.assertTrue(vfs.exists(f"{src_uri}/contributes/_manifest.md"))
            self.assertTrue(vfs.exists(f"{src_uri}/contributes/core.json"))

            init_content = vfs.read_text(f"{src_uri}/tests/__init__.py")
            self.assertNotIn("\\n", init_content)
            self.assertIn("Test package.", init_content)

            test_basic_content = vfs.read_text(f"{src_uri}/tests/test_basic.py")
            self.assertIn("cli.hello(bags)", test_basic_content)
            self.assertIn("self.mark_passed()", test_basic_content)

            checker = Checker()
            report = checker.check_module(mod_name)
            self.assertTrue(report.passed, f"Scaffolded module failed check: {report.errors}")
            self.assertFalse(report.has_warns, f"Scaffolded module produced warnings: {report.warnings}")
        finally:
            vfs.rmtree(f"module.source://{mod_name}")
        self.mark_passed()

    def test_create_duplicate_module_rejected(self):
        """Verify scaffolding over existing module fails, and failed scaffolding rolls back partial directory."""
        mod_name = "test_mod_dup"
        rollback_mod = "test_mod_rollback"
        try:
            ok1, _ = self.scaffolder.create_module(mod_name)
            self.assertTrue(ok1)
            ok2, msg2 = self.scaffolder.create_module(mod_name)
            self.assertFalse(ok2)
            self.assertIn("already exists", msg2)

            with patch("core.vfs.write_text", side_effect=OSError("simulated disk write failure")):
                ok_rb, msg_rb = self.scaffolder.create_module(rollback_mod)
            self.assertFalse(ok_rb)
            self.assertIn("Failed to create module", msg_rb)
            self.assertFalse(vfs.exists(f"module.source://{rollback_mod}"))
        finally:
            vfs.rmtree(f"module.source://{mod_name}")
            vfs.rmtree(f"module.source://{rollback_mod}")
        self.mark_passed()

    def test_scaffold_cli_format(self):
        """Verify scaffolded scripts/cli.py conforms to hello(cmd_bags) and guard_dispatch."""
        mod_name = "test_mod_scaffold_fmt"
        try:
            ok, msg = self.scaffolder.create_module(mod_name)
            self.assertTrue(ok, f"Scaffold failed: {msg}")

            src_uri = f"module.source://{mod_name}"
            cli_content = vfs.read_text(f"{src_uri}/scripts/cli.py")

            self.assertIn("def hello(cmd_bags: Any) -> int:", cli_content)
            self.assertIn('guard_dispatch("test_mod_scaffold_fmt")', cli_content)
            self.assertNotIn("def main(", cli_content)
            self.assertNotIn("__main__", cli_content)
            self.assertNotIn("def process(args", cli_content)
        finally:
            vfs.rmtree(f"module.source://{mod_name}")
        self.mark_passed()

    def test_create_module_invalid_names_and_hyphen_package(self):
        """Verify empty or malformed module names fail, and hyphenated module name normalizes package dir."""
        ok_empty, msg_empty = self.scaffolder.create_module("")
        self.assertFalse(ok_empty)
        self.assertIn("cannot be empty", msg_empty)

        for bad_name in ("-bad_start", "bad/slash", "bad space"):
            ok_bad, msg_bad = self.scaffolder.create_module(bad_name)
            self.assertFalse(ok_bad, f"Expected '{bad_name}' to be rejected")
            self.assertIn("Invalid module name", msg_bad)

        hyphen_mod = "test-hyphen-pkg"
        try:
            ok_h, msg_h = self.scaffolder.create_module(hyphen_mod, description="Hyphenated module")
            self.assertTrue(ok_h, f"Hyphenated module creation failed: {msg_h}")
            self.assertTrue(vfs.exists(f"module.source://{hyphen_mod}/test_hyphen_pkg/__init__.py"))
            report = Checker().check_module(hyphen_mod)
            self.assertTrue(report.passed, f"Hyphenated module failed check: {report.errors}")
            self.assertFalse(report.has_warns, f"Hyphenated module warnings: {report.warnings}")
        finally:
            vfs.rmtree(f"module.source://{hyphen_mod}")
        self.mark_passed()

    def test_cli_create_command(self):
        """Verify scripts/cli.py create command argument handling, quote stripping, and duplicate rejection."""
        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_scaffold_test", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        self.assertEqual(cli_mod.create([]), 1)

        mod_name = "test_cli_create_mod"
        try:
            rc_ok = cli_mod.create([mod_name, '--desc="Custom CLI Module"'])
            self.assertEqual(rc_ok, 0)
            mf = vfs.read_json(f"module.source://{mod_name}/manifest.json")
            self.assertEqual(mf.get("description"), "Custom CLI Module")

            rc_dup = cli_mod.create([mod_name])
            self.assertEqual(rc_dup, 1)
        finally:
            vfs.rmtree(f"module.source://{mod_name}")
        self.mark_passed()
