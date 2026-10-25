"""
CLI Routing, Help, UX and Defensive Guide Unit Tests.
Consolidates previous test_cli_help and test_cli_guide suites.
100% Python Standard Library.
"""
import io
import os
import sys
import unittest
import importlib.util
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from core import uri
from core.commands.help import HelpRenderer
from core.commands.registry import CommandSpec
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


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


class TestCLIHelpAndUX(YSCBTestCase):
    """CLI Help, Banner Formatting and Spelling Suggestion Unit Tests."""

    @require(Requirement.LOGIC)
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
        self.mark_passed()

    @require(Requirement.LOGIC)
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
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_unknown_command_dispatch_with_suggestion(self):
        """ET-02: Verifies error message and suggestion on unknown command execution."""
        f_err = io.StringIO()
        with redirect_stdout(f_err):
            code = yscb.dispatch_module("relod", [])
        self.assertEqual(code, 1)
        err_out = f_err.getvalue()
        self.assertIn("Error: Unknown command or module 'relod'", err_out)
        self.assertIn("Did you mean 'reload'?", err_out)
        self.mark_passed()


class TestHelpRendererMetadata(YSCBTestCase):
    """測試 HelpRenderer 指令級 -h 渲染之三級權限標籤與 Pros/Cons 輸出。"""

    @require(Requirement.LOGIC)
    def test_cmd_help_renders_security_tier_and_pros_cons(self):
        """FT-01: 驗證 render_cmd_help 正確渲染 Security ([SAFE]/[CONDITIONAL]/[GATED])、RECOMMENDED USAGE (Pros) 與 RESTRICTIONS & GATES (Cons)。"""
        spec_safe = CommandSpec(
            name="test",
            description="Run module tests",
            tier="safe",
            server_compatible=True,
            usage_pros=["開發中跑測"],
            usage_cons=["嚴禁手動先 build", "嚴禁跑 --all"],
        )
        out_safe = HelpRenderer.render_cmd_help("dev", "test", spec_safe)
        self.assertIn("Security   : [SAFE] 自主安全 (safe)", out_safe)
        self.assertIn("RECOMMENDED USAGE (Pros):", out_safe)
        self.assertIn("[+] 開發中跑測", out_safe)
        self.assertIn("RESTRICTIONS & GATES (Cons):", out_safe)
        self.assertIn("[-] 嚴禁手動先 build", out_safe)

        spec_gated = CommandSpec(
            name="release",
            description="Release package",
            tier="gated",
            server_compatible=False,
            usage_pros=["正式打包發布"],
            usage_cons=["嚴禁未經指示發布"],
        )
        out_gated = HelpRenderer.render_cmd_help("dev", "release", spec_gated)
        self.assertIn("Security   : [GATED] 授權守門 (gated)", out_gated)
        self.assertIn("[+] 正式打包發布", out_gated)
        self.assertIn("[-] 嚴禁未經指示發布", out_gated)

        spec_cond = CommandSpec(
            name="build",
            description="Build package",
            tier="conditional",
            server_compatible=True,
        )
        out_cond = HelpRenderer.render_cmd_help("dev", "build", spec_cond)
        self.assertIn("Security   : [CONDITIONAL] 階段條件 (conditional)", out_cond)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
