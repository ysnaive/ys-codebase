"""
Official test suite for dev.scaffold.Scaffolder.
"""
import os
from dev.testing import YSCBTestCase, require, Requirement
from dev.scaffold import Scaffolder
from dev.checker import Checker
from core import uri

@require(Requirement.ENV)
class TestDevScaffolder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.scaffolder = Scaffolder()

    def test_create_module_creates_all_templates(self):
        """Verify create_module produces manifest, cli.py, __init__.py, .yscbignore and passes Checker."""
        mod_name = "test_mod_scaffold_x"
        try:
            ok, msg = self.scaffolder.create_module(mod_name, desc="Unit test module")
            self.assertTrue(ok, f"Scaffold failed: {msg}")
            
            src_uri = f"module.source://{mod_name}"
            self.assertTrue(uri.exists(f"{src_uri}/manifest.json"))
            self.assertTrue(uri.exists(f"{src_uri}/scripts/cli.py"))
            self.assertTrue(uri.exists(f"{src_uri}/{mod_name}/__init__.py"))
            self.assertTrue(uri.exists(f"{src_uri}/.yscbignore"))
            self.assertTrue(uri.exists(f"{src_uri}/contributes/_format.json"))
            self.assertTrue(uri.exists(f"{src_uri}/contributes/_manifest.md"))
            self.assertTrue(uri.exists(f"{src_uri}/contributes/core.json"))

            # Verify __init__.py does not contain literal backslash-n
            init_content = uri.read_text(f"{src_uri}/tests/__init__.py")
            self.assertNotIn("\\n", init_content)
            self.assertIn("Test package.", init_content)

            # Verify test_basic.py invokes hello
            test_basic_content = uri.read_text(f"{src_uri}/tests/test_basic.py")
            self.assertIn("cli.hello(bags)", test_basic_content)
            self.assertIn("self.mark_passed()", test_basic_content)

            # Verify scaffolded module passes checker with 0 errors
            checker = Checker()
            report = checker.check_module(mod_name)
            self.assertTrue(report.passed, f"Scaffolded module failed check: {report.errors}")
        finally:
            uri.rmtree(f"module.source://{mod_name}")
        self.mark_passed()

    def test_create_duplicate_module_rejected(self):
        """Verify scaffolding over existing module fails."""
        mod_name = "test_mod_dup"
        try:
            self.scaffolder.create_module(mod_name)
            # Second attempt must fail
            ok2, msg2 = self.scaffolder.create_module(mod_name)
            self.assertFalse(ok2)
            self.assertIn("already exists", msg2)
        finally:
            uri.rmtree(f"module.source://{mod_name}")
        self.mark_passed()

    def test_scaffold_cli_format(self):
        """FT-04: Verify scaffolded scripts/cli.py conforms to hello(cmd_bags) and guard_dispatch."""
        mod_name = "test_mod_scaffold_fmt"
        try:
            ok, msg = self.scaffolder.create_module(mod_name)
            self.assertTrue(ok, f"Scaffold failed: {msg}")

            src_uri = f"module.source://{mod_name}"
            cli_content = uri.read_text(f"{src_uri}/scripts/cli.py")

            self.assertIn("def hello(cmd_bags: Any) -> int:", cli_content)
            self.assertIn('guard_dispatch("test_mod_scaffold_fmt")', cli_content)
            self.assertNotIn("def main(", cli_content)
            self.assertNotIn("__main__", cli_content)
            self.assertNotIn("def process(args", cli_content)
        finally:
            uri.rmtree(f"module.source://{mod_name}")
        self.mark_passed()
