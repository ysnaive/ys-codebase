"""
Unit tests for core.contributes global help dynamic aggregator.
"""
import io
import sys
from dev.testing import YSCBTestCase, require, Requirement
from core.contributes import print_global_help


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestContributesHelp(YSCBTestCase):
    def test_print_global_help(self):
        """FT-03: Verify print_global_help formats core and module commands cleanly."""
        captured = io.StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = captured
            ret = print_global_help()
        finally:
            sys.stdout = orig_stdout

        self.assertEqual(ret, 0)
        out = captured.getvalue()

        # Core commands check
        self.assertIn("CORE COMMANDS:", out)
        self.assertIn("init <root>", out)
        self.assertIn("restore [--force]", out)
        self.assertIn("install <module>", out)
        self.assertIn("list", out)
        self.assertIn("reload", out)

        # Module commands check
        self.assertIn("MODULE COMMANDS:", out)
        self.assertIn("GLOBAL OPTIONS:", out)
        self.assertIn("-h, --help", out)
        self.mark_passed()
