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
        os.path.join(uri.resolve_yscb_root(), "yscb.py"),
        os.path.join(os.path.dirname(uri.resolve_yscb_root()), "yscb.py"),
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


class TestCoreCLITelemetry(YSCBTestCase):
    """測試 core.telemetry (cache://core/telemetry.jsonl) 寫入、沙盒略過、滾動截斷與路由攔截。"""

    @require(Requirement.LOGIC)
    def test_telemetry_record_filter_and_rotation(self):
        """FT-01, ET-03, ET-04: 驗證 record_cli_event 寫入、沙盒預設旁路、--help/session-trace 排除與滾動截斷。"""
        import tempfile
        from pathlib import Path
        from core.telemetry import (
            record_cli_event,
            read_telemetry_records,
            should_record_telemetry,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            telem_file = Path(tmpdir) / "telemetry.jsonl"
            orig_override = os.environ.get("YSCB_TELEMETRY_PATH")
            orig_sandbox = os.environ.get("YSCB_TEST_SANDBOX")
            try:
                # 1. ET-03: 當 YSCB_TEST_SANDBOX=1 且無 YSCB_TELEMETRY_PATH 時預設不記錄
                os.environ.pop("YSCB_TELEMETRY_PATH", None)
                os.environ["YSCB_TEST_SANDBOX"] = "1"
                self.assertFalse(should_record_telemetry("core", ["status"], []))

                # 2. 設定 YSCB_TELEMETRY_PATH 後允許測試環境寫入，但仍排除 --help 與 session-trace
                os.environ["YSCB_TELEMETRY_PATH"] = str(telem_file)
                self.assertTrue(should_record_telemetry("core", ["status"], []))
                self.assertFalse(should_record_telemetry("core", ["status"], ["--help"]))
                self.assertFalse(should_record_telemetry("agents-workflow", ["session-trace"], ["--json"]))

                # 3. FT-01: 寫入正向與失敗紀錄並驗證讀取與 error_hint 擷取
                ok1 = record_cli_event(
                    module_name="knowledge-db",
                    cmd_path=["search"],
                    args=["PlanVerifier", "--json"],
                    exit_code=0,
                    duration_ms=42.5,
                    mode="hot",
                )
                self.assertTrue(ok1)
                ok2 = record_cli_event(
                    module_name="agents-workflow",
                    cmd_path=["plan", "verify"],
                    args=["bad_plan"],
                    exit_code=1,
                    duration_ms=18.2,
                    mode="local",
                    error_hint="Some header\n[FAIL] Missing section ## 1. 功能需求清單\nFooter",
                )
                self.assertTrue(ok2)

                records = read_telemetry_records(telemetry_path=telem_file)
                self.assertEqual(len(records), 2)
                self.assertEqual(records[0]["module"], "knowledge-db")
                self.assertEqual(records[0]["cmd"], "search")
                self.assertEqual(records[0]["mode"], "hot")
                self.assertEqual(records[1]["exit_code"], 1)
                self.assertIn("[FAIL] Missing section", records[1]["error_hint"])

                # 4. ET-04: 超過 max_bytes 時自動滾動截斷並僅保留最後 keep_lines 筆
                for idx in range(10):
                    record_cli_event(
                        module_name="core",
                        cmd_path=["uri", "list"],
                        args=[f"arg_{idx}"],
                        exit_code=0,
                        duration_ms=5.0,
                        max_bytes=300,
                        keep_lines=4,
                    )
                rotated = read_telemetry_records(telemetry_path=telem_file)
                self.assertEqual(len(rotated), 4)
                self.assertEqual(rotated[-1]["args"], ["arg_9"])
            finally:
                if orig_override is None:
                    os.environ.pop("YSCB_TELEMETRY_PATH", None)
                else:
                    os.environ["YSCB_TELEMETRY_PATH"] = orig_override
                if orig_sandbox is None:
                    os.environ.pop("YSCB_TEST_SANDBOX", None)
                else:
                    os.environ["YSCB_TEST_SANDBOX"] = orig_sandbox

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dispatcher_records_router_error_telemetry(self):
        """FT-01: 驗證 dispatcher.dispatch 在攔截未知模組/指令拼寫錯誤時自動寫入 router_err Telemetry。"""
        import tempfile
        from pathlib import Path
        from core.commands.dispatcher import dispatch
        from core.telemetry import read_telemetry_records

        with tempfile.TemporaryDirectory() as tmpdir:
            telem_file = Path(tmpdir) / "router_telemetry.jsonl"
            orig_override = os.environ.get("YSCB_TELEMETRY_PATH")
            try:
                os.environ["YSCB_TELEMETRY_PATH"] = str(telem_file)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = dispatch(["relod"])
                self.assertEqual(rc, 1)
                recs = read_telemetry_records(telemetry_path=telem_file)
                self.assertEqual(len(recs), 1)
                self.assertEqual(recs[0]["mode"], "router_err")
                self.assertEqual(recs[0]["exit_code"], 1)
                self.assertIn("Did you mean 'reload'?", recs[0]["error_hint"])
            finally:
                if orig_override is None:
                    os.environ.pop("YSCB_TELEMETRY_PATH", None)
                else:
                    os.environ["YSCB_TELEMETRY_PATH"] = orig_override

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
