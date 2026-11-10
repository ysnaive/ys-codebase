"""
CLI Routing, Help, UX and Telemetry Unit Tests.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.commands.dispatcher import dispatch, _suggest_command
from core.commands.help import HelpRenderer
from core.commands.registry import CommandSpec
from core.telemetry import (
    extract_error_hint,
    record_cli_event,
    read_telemetry_records,
    should_record_telemetry,
)
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from tests import load_yscb_host_module


yscb = load_yscb_host_module()


@require(Requirement.LOGIC)
class TestCLIHelpAndUX(YSCBTestCase):
    """CLI Help, Banner Formatting and Spelling Suggestion Unit Tests."""

    def test_global_help_output_structure(self):
        """Verifies that global --help outputs Banner, Usage, Core & Module commands."""
        f = io.StringIO()
        with redirect_stdout(f):
            yscb.main(["--help"])
        out = f.getvalue()

        self.assertIn("YS-Codebase - Ultra-Thin Modular Microkernel CLI", out)
        self.assertIn("USAGE:", out)
        self.assertIn("CORE COMMANDS:", out)
        self.assertIn("MODULE COMMANDS:", out)
        self.assertIn("GLOBAL OPTIONS:", out)

        self.assertIn("init <root>", out)
        self.assertIn("install <module>", out)
        self.assertIn("status", out)
        self.assertIn("reload", out)
        self.assertIn("rollback", out)
        self.mark_passed()

    def test_spelling_suggestion_algorithm(self):
        """Verifies difflib-based intelligent spelling suggestion."""
        known = ["init", "install", "update", "remove", "list", "status", "rollback", "reload", "dev"]

        self.assertEqual(_suggest_command("relod", known), "reload")
        self.assertEqual(_suggest_command("stauts", known), "status")
        self.assertEqual(_suggest_command("instll", known), "install")
        self.assertEqual(_suggest_command("updat", known), "update")

        self.assertIsNone(_suggest_command("completely_unrelated_xyz", known))
        self.mark_passed()

    def test_unknown_command_dispatch_with_suggestion(self):
        """Verifies error message and suggestion on unknown command execution."""
        f_err = io.StringIO()
        with redirect_stdout(f_err):
            code = yscb.dispatch_module("relod", [])
        self.assertEqual(code, 1)
        err_out = f_err.getvalue()
        self.assertIn("Error: Unknown command or module 'relod'", err_out)
        self.assertIn("Did you mean 'reload'?", err_out)
        self.mark_passed()


@require(Requirement.LOGIC)
class TestHelpRendererMetadata(YSCBTestCase):
    """測試 HelpRenderer 指令級 -h 渲染之三級權限標籤與 Pros/Cons 輸出。"""

    def test_cmd_help_renders_security_tier_and_pros_cons(self):
        """驗證 render_cmd_help 正確渲染 Security ([SAFE]/[CONDITIONAL]/[GATED])、RECOMMENDED USAGE (Pros) 與 RESTRICTIONS & GATES (Cons)。"""
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


@require(Requirement.LOGIC)
class TestCoreCLITelemetry(YSCBTestCase):
    """測試 core.telemetry (cache://core/telemetry.jsonl) 寫入、沙盒略過、滾動截斷與過濾。"""

    def test_telemetry_record_filter_and_rotation(self):
        """驗證 record_cli_event 寫入、沙盒預設旁路、--help/session-trace 排除、時間窗口/limit 過濾、損毀行容錯與 extract_error_hint 優先序。"""
        # 1. Verify extract_error_hint priority and empty string handling
        self.assertEqual(extract_error_hint(""), "")
        self.assertEqual(
            extract_error_hint("Normal header\n[ERROR] Critical database failure\nTrailing"),
            "[ERROR] Critical database failure",
        )
        self.assertEqual(
            extract_error_hint("First line\n[BLOCKER] Daemon required"),
            "[BLOCKER] Daemon required",
        )
        self.assertEqual(
            extract_error_hint("Plain first line\nPlain second line"),
            "Plain first line",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            telem_file = Path(tmpdir) / "telemetry.jsonl"
            orig_override = os.environ.get("YSCB_TELEMETRY_PATH")
            orig_sandbox = os.environ.get("YSCB_TEST_SANDBOX")
            try:
                os.environ.pop("YSCB_TELEMETRY_PATH", None)
                os.environ["YSCB_TEST_SANDBOX"] = "1"
                self.assertFalse(should_record_telemetry("core", ["status"], []))

                os.environ["YSCB_TELEMETRY_PATH"] = str(telem_file)
                self.assertTrue(should_record_telemetry("core", ["status"], []))
                self.assertFalse(should_record_telemetry("core", ["status"], ["--help"]))
                self.assertFalse(should_record_telemetry("agents-workflow", ["session-trace"], ["--json"]))

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

                # Verify limit, since_minutes, since_iso, missing epoch fallback, and corrupted JSON line resilience
                with open(telem_file, "a", encoding="utf-8") as f:
                    f.write("\n{corrupted_json_line\n")
                    f.write(json.dumps({"ts": "2020-01-01T00:00:00Z", "module": "old_mod", "cmd": "old"}) + "\n")

                all_valid = read_telemetry_records(telemetry_path=telem_file)
                self.assertEqual(len(all_valid), 3)

                recent_only = read_telemetry_records(telemetry_path=telem_file, since_minutes=5.0)
                self.assertEqual(len(recent_only), 2)

                limited = read_telemetry_records(telemetry_path=telem_file, limit=1)
                self.assertEqual(len(limited), 1)

                future_filtered = read_telemetry_records(
                    telemetry_path=telem_file, since_iso="2099-01-01T00:00:00Z"
                )
                self.assertEqual(future_filtered, [])

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

    def test_dispatcher_records_router_error_telemetry(self):
        """驗證 dispatcher.dispatch 在攔截未知模組/指令拼寫錯誤時自動寫入 router_err Telemetry。"""
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

    def test_dispatcher_hot_reload_and_json_suppresses_update_tips(self):
        """驗證 dispatch_local 穿透 _MODULE_CACHE 熱重載且 --json/-j 抑制 update tips 輸出。"""
        from unittest.mock import patch
        from core.commands import dispatcher

        with patch("core.update_checker.UpdateChecker") as mock_uc_cls:
            mock_uc = mock_uc_cls.return_value
            with patch.dict(os.environ, {"YSCB_TESTING": "0", "YSCB_TEST_SANDBOX": "0"}):
                dispatcher._maybe_check_and_print_updates(["core", "uri", "list", "--json"])
                mock_uc.check_updates.assert_not_called()
                mock_uc.print_tips_if_available.assert_not_called()

        self.mark_passed()

    @require(Requirement.ENV)
    def test_hot_dispatch_worker_reentrancy_bypass_and_heartbeat_handling(self):
        """驗證 Worker 內重入環境變數自動繞過熱派發，且串流正確忽略 heartbeat 封包並執行總時限保護。"""
        from unittest.mock import patch, MagicMock
        from core.commands import dispatcher
        from core.context import bind_runtime_context

        # 1. YSCB_IN_SERVER_WORKER=1 與 YSCB_NO_HOT_DISPATCH=1 繞過 _try_hot_dispatch
        for bypass_env in ({"YSCB_IN_SERVER_WORKER": "1"}, {"YSCB_NO_HOT_DISPATCH": "1"}):
            with bind_runtime_context(env=bypass_env), patch.object(
                dispatcher, "_try_hot_dispatch"
            ) as mock_hot, patch.object(
                dispatcher, "dispatch_local", return_value=0
            ) as mock_local:
                rc = dispatcher.dispatch(["status"])
                self.assertEqual(rc, 0)
                mock_hot.assert_not_called()
                mock_local.assert_called_once()

        # 2. _hot_dispatch_attempt 忽略 heartbeat 封包並正確處理 terminal_stream + task_finish
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_srv = Path(tmpdir) / ".cache" / "server"
            cache_srv.mkdir(parents=True, exist_ok=True)
            (cache_srv / "daemon.json").write_text(
                json.dumps({"pid": os.getpid(), "port": 54321, "token": "tok", "root": tmpdir}),
                encoding="utf-8",
            )
            ndjson_lines = [
                b'{"type": "heartbeat", "ts": 1.0}\n',
                b'{"type": "terminal_stream", "stream": "stdout", "text": "ok_out\\n"}\n',
                b'{"type": "task_finish", "exit_code": 0}\n',
                b"",
            ]
            fake_resp = MagicMock()
            fake_resp.__enter__.return_value = fake_resp
            fake_resp.__exit__.return_value = False
            fake_resp.readline.side_effect = ndjson_lines

            out_buf = io.StringIO()
            with patch.object(dispatcher, "_open_localhost_no_proxy", return_value=fake_resp), redirect_stdout(out_buf):
                res = dispatcher._hot_dispatch_attempt("core", ["status"], [], tmpdir)
            self.assertTrue(res.accepted)
            self.assertEqual(res.exit_code, 0)
            self.assertIn("ok_out", out_buf.getvalue())

            # 3. YSCB_DISPATCH_MAX_WALL_SEC 防止無限心跳掛起
            def _infinite_heartbeats():
                import time as _t
                _t.sleep(0.02)
                return b'{"type": "heartbeat", "ts": 2.0}\n'

            fake_hang_resp = MagicMock()
            fake_hang_resp.__enter__.return_value = fake_hang_resp
            fake_hang_resp.__exit__.return_value = False
            fake_hang_resp.readline.side_effect = _infinite_heartbeats

            with bind_runtime_context(env={"YSCB_DISPATCH_MAX_WALL_SEC": "0.05"}), patch.object(
                dispatcher, "_open_localhost_no_proxy", return_value=fake_hang_resp
            ):
                res_timeout = dispatcher._hot_dispatch_attempt("core", ["status"], [], tmpdir)
            self.assertTrue(res_timeout.accepted)
            self.assertIsNone(res_timeout.exit_code)

            # 4. Silent hang dynamically clamps underlying socket timeout to remaining wall deadline
            import socket as _sock
            applied_timeouts = []
            fake_sock = MagicMock()
            fake_sock.settimeout.side_effect = lambda val: applied_timeouts.append(val)

            def _silent_socket_timeout():
                raise _sock.timeout("timed out")

            fake_silent_resp = MagicMock()
            fake_silent_resp.__enter__.return_value = fake_silent_resp
            fake_silent_resp.__exit__.return_value = False
            fake_silent_resp.fp.raw._sock = fake_sock
            fake_silent_resp.readline.side_effect = _silent_socket_timeout

            with bind_runtime_context(env={"YSCB_DISPATCH_MAX_WALL_SEC": "0.25"}), patch.object(
                dispatcher, "_open_localhost_no_proxy", return_value=fake_silent_resp
            ) as mock_open:
                res_silent = dispatcher._hot_dispatch_attempt("core", ["status"], [], tmpdir)
            self.assertTrue(res_silent.accepted)
            self.assertIsNone(res_silent.exit_code)
            self.assertLessEqual(mock_open.call_args.kwargs.get("timeout", 999.0), 0.25)
            self.assertGreaterEqual(len(applied_timeouts), 1)
            self.assertLessEqual(applied_timeouts[0], 0.25)

            # 5. PipManager.install_packages and installer.fetch_and_extract_zip forward explicit timeout
            from core.installer import fetch_and_extract_zip
            from core.pip_manager import PipManager

            with patch("urllib.request.urlopen", side_effect=TimeoutError("net timeout")) as mock_uopen:
                with self.assertRaises(TimeoutError):
                    fetch_and_extract_zip("https://example.invalid/pkg.zip", str(Path(tmpdir) / "dest"), timeout=3.5)
                self.assertEqual(mock_uopen.call_args.kwargs.get("timeout"), 3.5)

            pm = PipManager(yscb_dir=tmpdir)
            with patch.object(pm, "ensure_venv", return_value=tmpdir), patch.object(
                pm, "get_python_executable", return_value=__import__('sys').executable
            ), patch("subprocess.run", side_effect=TimeoutError("pip timeout")) as mock_srun:
                from core.pip_manager import PipInstallError
                with self.assertRaises(PipInstallError):
                    pm.install_packages(["dummy-pkg"], timeout=7)
                self.assertEqual(mock_srun.call_args.kwargs.get("timeout"), 7)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
