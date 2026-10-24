"""
Comprehensive unit and integration test suite for YSCB Microkernel Event Pipeline.
Covers FT-01, FT-02, FT-03, FT-07, FT-08, ET-01, ET-02, ET-03, ET-04, ET-05.
"""
import os
import sys
import time
import io
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

from dev.testing import YSCBTestCase, require, Requirement
from core.engine import AtomicEngine
from core.uri import ExecutionContext
from core import uri, events


class TestEventsPipeline(YSCBTestCase):
    """Event pipeline verification suite."""

    def test_core_events_broadcast_basic(self):
        """FT-01: 驗證 core.events.broadcast 成功尋址 module://{mod}/scripts/hook.{Sender}.py 並執行 on_{event} / {event} 函式。"""
        mod_scripts = "module://mock_listener/scripts"
        uri.makedirs(mod_scripts)
        flag_file = "module://mock_listener/event.flag"
        resolved_flag = uri.resolve(flag_file).replace("\\", "/")
        
        hook_code = f"""
def on_pre_cli_dispatch(ctx):
    with open("{resolved_flag}", "w") as f:
        f.write("DISPATCHED:" + ctx.command)
    return "ok"

def custom_event(ctx):
    return "custom_ok"
"""
        try:
            uri.write_text(f"{mod_scripts}/hook.core.py", hook_code)

            ctx = ExecutionContext("core", "agents-workflow", ["status"])
            res = events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")

            self.assertEqual(res.get("mock_listener"), "ok")
            self.assertTrue(uri.exists(flag_file))
            self.assertEqual(uri.read_text(flag_file), "DISPATCHED:agents-workflow")

            # Test non-on_ prefix matching
            res_custom = events.broadcast("custom_event", context=ctx, emit_module="core")
            self.assertEqual(res_custom.get("mock_listener"), "custom_ok")
        finally:
            if uri.exists("module://mock_listener"):
                uri.rmtree("module://mock_listener")
        self.mark_passed()

    def test_engine_decoupling_and_installer_events(self):
        """FT-02: 驗證 installer/engine 內部正常調用 core.events.broadcast。"""
        engine = AtomicEngine()

        # 1. 驗證 engine.act_reload 調用 events.broadcast("on_reload", ...)
        with patch("core.events.broadcast", return_value={"mock": "success"}) as mock_bc:
            with patch.object(engine, "act_snapshot", return_value="test_snap"), \
                 patch.object(engine.contributes_aggregator, "scan_and_inject", return_value={}), \
                 patch.object(engine, "act_deploy_configs_from_modules", return_value=True), \
                 patch.object(engine, "_get_config", return_value=("/path/cfg", {"installed_modules": {}})):
                engine.act_reload(clean_stage=False, inject_stage=True)
            self.assertTrue(any(call.args and call.args[0] == "on_reload" for call in mock_bc.call_args_list))

        # 2. 驗證 installer.py 調用 events.broadcast("on_remove", ...)
        from core.installer import Installer
        installer = Installer()
        with patch("core.events.broadcast", return_value={"mock": "success"}) as mock_bc:
            with patch.object(installer.engine, "_get_config", return_value=("/path/cfg", {"installed_modules": {"mock_mod": {}}})), \
                 patch.object(installer.engine, "act_snapshot", return_value="snap"), \
                 patch.object(installer.engine, "act_unregister", return_value=True), \
                 patch.object(installer.engine, "act_delete", return_value=True), \
                 patch.object(installer.engine, "act_reload", return_value=True), \
                 patch.object(installer, "sync_pip_dependencies", return_value=None):
                installer.cmd_remove("mock_mod", clean=True, purge=True, force=True)
            self.assertTrue(any(call.args and call.args[0] == "on_remove" for call in mock_bc.call_args_list))

        self.mark_passed()

    def test_yscb_host_lifecycle_pipeline(self):
        """FT-03: 驗證 yscb.py 分發命令時生命週期 pre/post 廣播與跳過自舉命令。"""
        import yscb
        self.assertTrue(hasattr(yscb, "_ensure_jit_lifecycle_pre"))
        self.assertTrue(hasattr(yscb, "_ensure_jit_lifecycle_post"))

        with patch("core.events.broadcast") as mock_broadcast:
            # 正常命令觸發 pre/post 廣播
            yscb._ensure_jit_lifecycle_pre("agents-workflow")
            mock_broadcast.assert_called_with("pre_cli_dispatch", emit_module="core")

            mock_broadcast.reset_mock()
            yscb._ensure_jit_lifecycle_post("agents-workflow", 0)
            mock_broadcast.assert_called_with("post_cli_dispatch", emit_module="core")

        self.mark_passed()

    def test_event_list_cli(self):
        """FT-07: 驗證 python yscb.py event list 能正確聚合各模組之 contributes.events 中繼資料並格式化輸出。"""
        import yscb
        self.assertTrue(hasattr(yscb, "cmd_event"))

        # Test cmd_event list output
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = yscb.cmd_event(["list"])

        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("YS-Codebase - Ecosystem Event Registry", output)
        self.assertIn("pre_cli_dispatch", output)
        self.assertIn("post_cli_dispatch", output)
        self.mark_passed()

    def test_contributes_jit_coordination(self):
        """FT-08: 驗證 core.contributes JIT 快照自癒與生命週期管線協同工作正常。"""
        from core import contributes
        events_dict = events.get_contributed_events()
        self.assertIsInstance(events_dict, dict)
        self.assertIn("core", events_dict)
        core_events = [e["name"] for e in events_dict["core"]]
        self.assertIn("pre_cli_dispatch", core_events)
        self.assertIn("post_cli_dispatch", core_events)
        self.assertIn("on_reload", core_events)
        self.mark_passed()

    def test_hook_missing_graceful_skip(self):
        """ET-01: 驗證缺少 hook.<Sender>.py 或未宣告對應事件處理常式之模組安全略過，不拋出任何例外。"""
        mod_scripts = "module://mock_empty/scripts"
        uri.makedirs(mod_scripts)
        try:
            # hook.other.py exists, but not hook.core.py
            uri.write_text(f"{mod_scripts}/hook.other.py", "def on_event(ctx): pass\n")

            res = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertNotIn("mock_empty", res)

            # hook.core.py exists but does not implement pre_cli_dispatch
            uri.write_text(f"{mod_scripts}/hook.core.py", "def other_unrelated_func(): pass\n")
            res2 = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertNotIn("mock_empty", res2)
        finally:
            if uri.exists("module://mock_empty"):
                uri.rmtree("module://mock_empty")
        self.mark_passed()

    def test_hook_exception_isolation(self):
        """ET-02: 驗證特定模組 Hook 內部拋出例外時，事件總線捕獲並記錄警告，絕不阻斷主流程。"""
        mod_scripts = "module://mock_crasher/scripts"
        uri.makedirs(mod_scripts)
        try:
            uri.write_text(
                f"{mod_scripts}/hook.core.py",
                "def on_pre_cli_dispatch(ctx):\n    raise ZeroDivisionError('Hook crashed')\n"
            )

            res = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertIn("mock_crasher", res)
            self.assertTrue(str(res["mock_crasher"]).startswith("warning:"))
        finally:
            if uri.exists("module://mock_crasher"):
                uri.rmtree("module://mock_crasher")
        self.mark_passed()

    def test_bootstrap_commands_short_circuit(self):
        """ET-03: 驗證執行 init、restore、bootstrap 等自舉指令時自動短路跳過前置廣播。"""
        import yscb
        for b_cmd in ["init", "restore", "bootstrap", "self-update"]:
            with patch("core.events.broadcast") as mock_bc:
                yscb._ensure_jit_lifecycle_pre(b_cmd)
                mock_bc.assert_not_called()

                yscb._ensure_jit_lifecycle_post(b_cmd, 0)
                mock_bc.assert_not_called()

        self.mark_passed()

    @require(Requirement.PERF)
    def test_clean_state_performance_benchmark(self):
        """ET-04: 驗證 Clean 狀態下 pre_cli_dispatch 事件廣播耗時 <= 15ms。"""
        ctx = ExecutionContext("core", "list", [])

        # Warm-up once
        events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")

        # Benchmark 20 iterations
        start = time.perf_counter()
        iterations = 20
        for _ in range(iterations):
            events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")
        elapsed_total = time.perf_counter() - start
        avg_ms = (elapsed_total / iterations) * 1000.0

        # Assert clean state latency <= 15ms (accommodates Windows / CI scheduling jitter)
        self.assertLess(avg_ms, 15.0, f"Average latency {avg_ms:.2f}ms exceeds 15ms limit!")
        self.mark_passed()

    def test_event_list_empty_contributes_resilience(self):
        """ET-05: 驗證未定義 events contribute 節點之模組在執行 event list 時優雅容錯不拋異常。"""
        with patch("core.contributes.get", return_value=[]):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        with patch("core.contributes.get", return_value=None):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        with patch("core.contributes.get", side_effect=RuntimeError("contributes missing")):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        self.mark_passed()

    def test_hook_observability_execution_and_traceback(self):
        """FT-02: 驗證 verbose 模式下 Hook 執行輸出與異常 Traceback 輸出，且一般模式保持乾淨。"""
        from core.commands.dispatcher import _ensure_hooks
        mod_scripts = "module://mock_obs/scripts"
        uri.makedirs(mod_scripts, exist_ok=True)

        hook_code = (
            "def on_test_event(ctx):\n"
            "    return 'result_ok'\n\n"
            "def on_fail_event(ctx):\n"
            "    raise ValueError('Simulated hook failure for observability')\n"
        )
        uri.write_text(f"{mod_scripts}/hook.core.py", hook_code)

        ctx = ExecutionContext("core", "test_cmd", [])

        try:
            buf_quiet = io.StringIO()
            with patch("sys.stderr", buf_quiet):
                res_quiet = events.broadcast("test_event", context=ctx, emit_module="core", verbose=False)
            self.assertEqual(res_quiet.get("mock_obs"), "result_ok")
            self.assertEqual(buf_quiet.getvalue(), "")

            buf_verbose = io.StringIO()
            with patch("sys.stderr", buf_verbose):
                res_verbose = events.broadcast("test_event", context=ctx, emit_module="core", verbose=True)
            self.assertEqual(res_verbose.get("mock_obs"), "result_ok")
            verbose_out = buf_verbose.getvalue()
            self.assertIn("[core:events] Hook 'mock_obs:hook.core.py' executed 'test_event' -> result_ok", verbose_out)

            buf_env = io.StringIO()
            with patch.dict(os.environ, {"YSCB_VERBOSE": "1"}):
                with patch("sys.stderr", buf_env):
                    res_env = events.broadcast("test_event", context=ctx, emit_module="core")
            self.assertEqual(res_env.get("mock_obs"), "result_ok")
            self.assertIn("[core:events] Hook 'mock_obs:hook.core.py' executed 'test_event' -> result_ok", buf_env.getvalue())

            buf_err = io.StringIO()
            with patch("sys.stderr", buf_err):
                res_err = events.broadcast("fail_event", context=ctx, emit_module="core", verbose=True)
            self.assertTrue(str(res_err.get("mock_obs")).startswith("warning:"))
            err_out = buf_err.getvalue()
            self.assertIn("Warning: Hook 'mock_obs:hook.core.py' failed on 'fail_event'", err_out)
            self.assertIn("Traceback (most recent call last):", err_out)
            self.assertIn("Simulated hook failure for observability", err_out)

            buf_disp = io.StringIO()
            with patch("sys.stderr", buf_disp):
                disp_res = _ensure_hooks("test_event", verbose=True)
            self.assertEqual(disp_res.get("mock_obs"), "result_ok")
            self.assertIn("[core:dispatcher] Hooks for 'test_event' completed:", buf_disp.getvalue())
        finally:
            if uri.exists("module://mock_obs"):
                uri.rmtree("module://mock_obs")

        self.mark_passed()

