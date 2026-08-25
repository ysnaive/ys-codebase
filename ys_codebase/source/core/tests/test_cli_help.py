"""
CLI Help, Banner Formatting and Spelling Suggestion Unit Tests.
100% Python Standard Library.
"""
import unittest
import io
import sys
import os
import importlib.util
from contextlib import redirect_stdout, redirect_stderr
from core import uri


def _load_yscb_module():
    host_d, _ = uri._get_host_config()
    candidates = [
        os.path.join(host_d, "yscb.py"),
        os.path.join(uri._get_yscb_root(), "yscb.py"),
        os.path.join(os.path.dirname(uri._get_yscb_root()), "yscb.py"),
        os.path.abspath("yscb.py")
    ]
    for c in candidates:
        if os.path.isfile(c):
            spec = importlib.util.spec_from_file_location("yscb", c)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    raise FileNotFoundError("Cannot locate yscb.py host script")


yscb = _load_yscb_module()


class TestCLIHelpAndUX(unittest.TestCase):
    def test_global_help_output_structure(self):
        """FT-02: Verifies that _print_global_help outputs Banner, Usage, Core & Module commands."""
        f = io.StringIO()
        with redirect_stdout(f):
            yscb._print_global_help()
        out = f.getvalue()
        
        # Assertions for Banner & Sections
        self.assertIn("YS-Codebase - Ultra-Thin Modular Microkernel CLI", out)
        self.assertIn("USAGE:", out)
        self.assertIn("CORE COMMANDS:", out)
        self.assertIn("MODULE COMMANDS:", out)
        self.assertIn("GLOBAL OPTIONS:", out)
        
        # Assertions for Core Commands (including init)
        self.assertIn("init <root>", out)
        self.assertIn("install <module>", out)
        self.assertIn("status", out)
        self.assertIn("reload", out)
        self.assertIn("rollback", out)

    def test_spelling_suggestion_algorithm(self):
        """FT-04: Verifies difflib-based intelligent spelling suggestion."""
        known = ["init", "install", "update", "remove", "list", "status", "rollback", "reload", "dev"]
        
        # Close typos
        self.assertEqual(yscb._suggest_command("relod", known), "reload")
        self.assertEqual(yscb._suggest_command("stauts", known), "status")
        self.assertEqual(yscb._suggest_command("instll", known), "install")
        self.assertEqual(yscb._suggest_command("updat", known), "update")
        
        # Far-off strings (no match)
        self.assertIsNone(yscb._suggest_command("completely_unrelated_xyz", known))

    def test_unknown_command_dispatch_with_suggestion(self):
        """ET-02: Verifies error message and suggestion on unknown command execution."""
        f_err = io.StringIO()
        with redirect_stdout(f_err):
            code = yscb.dispatch_module("relod", [])
        self.assertEqual(code, 1)
        err_out = f_err.getvalue()
        self.assertIn("Error: Unknown command or module 'relod'", err_out)
        self.assertIn("Did you mean 'reload'?", err_out)


if __name__ == "__main__":
    unittest.main()
