"""
Comprehensive unit and integration test suite for YSCB Microkernel Event Pipeline.
"""
import importlib.util
import io
import os
import time
from contextlib import redirect_stdout
from unittest.mock import patch

from dev.testing import YSCBTestCase, require, Requirement
from core.commands import dispatcher
from core.commands.dispatcher import _ensure_hooks
from core.engine import AtomicEngine
from core.installer import Installer
from core.uri import ExecutionContext
from core import uri, vfs, events
import yscb


@require(Requirement.ENV)
class TestEventsPipeline(YSCBTestCase):
    """Event pipeline verification suite."""

    def test_core_events_broadcast_basic(self):
        """驗證 core.events.broadcast 成功尋址 module://{mod}/scripts/hook.{Sender}.py 並執行 on_{event} / {event} 函式及非 core 發送者尋址。"""
        mod_scripts = "module://mock_listener/scripts"
        vfs.makedirs(mod_scripts)
        flag_file = "module://mock_listener/event.flag"
        resolved_flag = uri.resolve(flag_file).replace("\\", "/")

        hook_code = f"""
def on_pre_cli_dispatch(ctx):
    with open("{resolved_flag}", "w", encoding="utf-8") as f:
        f.write("DISPATCHED:" + ctx.command)
    return "ok"

def custom_event(ctx):
    return "custom_ok"
"""
        dev_hook_code = f"""
def on_test_event(ctx):
    with open("{resolved_flag}", "w", encoding="utf-8") as f:
        f.write("DEV_EVENT:" + ctx.command)
    return "dev_ok"
"""
        try:
            vfs.write_text(f"{mod_scripts}/hook.core.py", hook_code)
            vfs.write_text(f"{mod_scripts}/hook.dev.py", dev_hook_code)

            ctx = ExecutionContext("core", "agents-workflow", ["status"])
            res = events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")

            self.assertEqual(res.get("mock_listener"), "ok")
            self.assertTrue(vfs.exists(flag_file))
            self.assertEqual(vfs.read_text(flag_file), "DISPATCHED:agents-workflow")

            # Verify event name already prefixed with 'on_' is not duplicated to 'on_on_...'
            res_prefixed = events.broadcast("on_pre_cli_dispatch", context=ctx, emit_module="core")
            self.assertEqual(res_prefixed.get("mock_listener"), "ok")

            # Test non-on_ prefix matching
            res_custom = events.broadcast("custom_event", context=ctx, emit_module="core")
            self.assertEqual(res_custom.get("mock_listener"), "custom_ok")

            # Verify non-core sender (emit_module="dev") addresses hook.dev.py
            dev_ctx = ExecutionContext("dev", "test_cmd", ["arg1"])
            res_dev = events.broadcast("on_test_event", context=dev_ctx, emit_module="dev")
            self.assertEqual(res_dev.get("mock_listener"), "dev_ok")
            self.assertEqual(vfs.read_text(flag_file), "DEV_EVENT:test_cmd")
        finally:
            if vfs.exists("module://mock_listener"):
                vfs.rmtree("module://mock_listener")
        self.mark_passed()

    def test_engine_decoupling_and_installer_events(self):
        """驗證 installer/engine 內部正常調用 core.events.broadcast。"""
        engine = AtomicEngine()

        with patch("core.events.broadcast", return_value={"mock": "success"}) as mock_bc:
            with patch.object(engine, "act_snapshot", return_value="test_snap"), \
                 patch.object(engine.contributes_aggregator, "scan_and_inject", return_value={}), \
                 patch.object(engine, "act_deploy_configs_from_modules", return_value=True), \
                 patch.object(engine, "_get_config", return_value=("/path/cfg", {"installed_modules": {}})):
                engine.act_reload(clean_stage=False, inject_stage=True)
            self.assertIn("on_reload", [c.args[0] for c in mock_bc.call_args_list if c.args])

        installer = Installer()
        with patch("core.events.broadcast", return_value={"mock": "success"}) as mock_bc:
            with patch.object(installer.engine, "_get_config", return_value=("/path/cfg", {"installed_modules": {"mock_mod": {}}})), \
                 patch.object(installer.engine, "act_snapshot", return_value="snap"), \
                 patch.object(installer.engine, "act_unregister", return_value=True), \
                 patch.object(installer.engine, "act_delete", return_value=True), \
                 patch.object(installer.engine, "act_reload", return_value=True), \
                 patch.object(installer, "sync_pip_dependencies", return_value=None):
                installer.cmd_remove("mock_mod", clean=True, purge=True, force=True)
            self.assertIn("on_remove", [c.args[0] for c in mock_bc.call_args_list if c.args])

        self.mark_passed()

    def test_yscb_host_lifecycle_pipeline(self):
        """驗證 core.commands.dispatcher 分發命令時生命週期 pre/post 廣播。"""
        with patch("core.events.broadcast") as mock_broadcast:
            dispatcher._ensure_hooks("pre_cli_dispatch")
            mock_broadcast.assert_called_with("pre_cli_dispatch", emit_module="core", verbose=False)

            mock_broadcast.reset_mock()
            dispatcher._ensure_hooks("post_cli_dispatch")
            mock_broadcast.assert_called_with("post_cli_dispatch", emit_module="core", verbose=False)

        self.mark_passed()

    def test_event_list_cli(self):
        """驗證 python yscb.py event list 能正確聚合各模組之 contributes.events 中繼資料並格式化輸出。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = yscb.main(["event", "list"])

        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("YS-Codebase - Ecosystem Event Registry", output)
        self.assertIn("pre_cli_dispatch", output)
        self.assertIn("post_cli_dispatch", output)
        self.mark_passed()

    def test_contributes_jit_coordination(self):
        """驗證 core.contributes JIT 快照自癒與生命週期管線協同工作正常。"""
        events_dict = events.get_contributed_events()
        self.assertIsInstance(events_dict, dict)
        self.assertIn("core", events_dict)
        core_events = [e["name"] for e in events_dict["core"]]
        self.assertIn("pre_cli_dispatch", core_events)
        self.assertIn("post_cli_dispatch", core_events)
        self.assertIn("on_reload", core_events)
        self.assertNotIn("__provider__", core_events)
        self.assertNotIn("__providers__", core_events)
        self.mark_passed()

    def test_hook_missing_graceful_skip(self):
        """驗證缺少 hook.<Sender>.py 或未宣告對應事件處理常式之模組安全略過，不拋出任何例外。"""
        mod_scripts = "module://mock_empty/scripts"
        vfs.makedirs(mod_scripts)
        try:
            vfs.write_text(f"{mod_scripts}/hook.other.py", "def on_event(ctx): pass\n")

            res = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertNotIn("mock_empty", res)

            vfs.write_text(f"{mod_scripts}/hook.core.py", "def other_unrelated_func(): pass\n")
            res2 = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertNotIn("mock_empty", res2)
        finally:
            if vfs.exists("module://mock_empty"):
                vfs.rmtree("module://mock_empty")
        self.mark_passed()

    def test_hook_exception_isolation(self):
        """驗證特定模組 Hook 內部拋出例外時，事件總線捕獲並記錄警告，絕不阻斷主流程。"""
        mod_scripts = "module://mock_crasher/scripts"
        vfs.makedirs(mod_scripts)
        try:
            vfs.write_text(
                f"{mod_scripts}/hook.core.py",
                "def on_pre_cli_dispatch(ctx):\n    raise ZeroDivisionError('Hook crashed')\n"
            )

            res = events.broadcast("pre_cli_dispatch", emit_module="core")
            self.assertIn("mock_crasher", res)
            self.assertTrue(str(res["mock_crasher"]).startswith("warning:"))
            self.assertIn("Hook crashed", str(res["mock_crasher"]))
        finally:
            if vfs.exists("module://mock_crasher"):
                vfs.rmtree("module://mock_crasher")
        self.mark_passed()

    def test_bootstrap_commands_short_circuit(self):
        """驗證執行 init、self-update 等宿主自舉指令時直接於 yscb.main 攔截，不觸發 core.events 廣播。"""
        with patch("core.events.broadcast") as mock_bc, \
             patch("yscb.cmd_init", return_value=0) as mock_init, \
             patch("yscb.cmd_self_update", return_value=0) as mock_su:
            self.assertEqual(yscb.main(["init"]), 0)
            self.assertEqual(yscb.main(["self-update"]), 0)
            mock_init.assert_called_once_with([])
            mock_su.assert_called_once_with([])
            mock_bc.assert_not_called()

        self.mark_passed()

    @require(Requirement.PERF)
    def test_clean_state_performance_benchmark(self):
        """驗證 Clean 狀態下 pre_cli_dispatch 事件廣播耗時 <= 15ms。"""
        ctx = ExecutionContext("core", "list", [])

        events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")

        start = time.perf_counter()
        iterations = 20
        for _ in range(iterations):
            events.broadcast("pre_cli_dispatch", context=ctx, emit_module="core")
        elapsed_total = time.perf_counter() - start
        avg_ms = (elapsed_total / iterations) * 1000.0

        self.assertLess(avg_ms, 15.0, f"Average latency {avg_ms:.2f}ms exceeds 15ms limit!")
        self.mark_passed()

    def test_event_list_empty_contributes_resilience(self):
        """驗證未定義 events contribute 節點之模組容錯，以及 get_contributed_events 過濾 __provider__ / __providers__ 與事件去重。"""
        with patch("core.contributes.get", return_value=[]):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        with patch("core.contributes.get", return_value=None):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        with patch("core.contributes.get", side_effect=RuntimeError("contributes missing")):
            res = events.get_contributed_events()
            self.assertEqual(res, {})

        # Verify __provider__ and __providers__ metadata keys are filtered out and duplicate events are deduplicated
        tagged_dict_payload = {
            "__provider__": "core",
            "__providers__": ["core"],
            "on_reload": {"description": "Reload hook", "__provider__": "core", "__providers__": ["core"]},
        }
        with patch("core.contributes.get", return_value=tagged_dict_payload):
            res_dict = events.get_contributed_events()
            self.assertIn("core", res_dict)
            names = [e["name"] for e in res_dict["core"]]
            self.assertEqual(names, ["on_reload"])
            self.assertNotIn("__provider__", names)
            self.assertNotIn("__providers__", names)

        tagged_list_payload = [
            {"name": "on_reload", "description": "Reload hook", "__provider__": "core", "__providers__": ["core"]},
            {"name": "on_reload", "description": "Duplicate reload hook", "__provider__": "core"},
            {"name": "__providers__", "description": "Meta key should be filtered", "__provider__": "core"},
        ]
        with patch("core.contributes.get", return_value=tagged_list_payload):
            res_list = events.get_contributed_events()
            self.assertIn("core", res_list)
            names_list = [e["name"] for e in res_list["core"]]
            self.assertEqual(names_list, ["on_reload"])

        self.mark_passed()

    def test_core_dev_hook_setup_and_teardown(self):
        """驗證 scripts/hook.dev.py 之 on_test_setup 與 on_test_teardown 行為與容錯。"""
        hook_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "hook.dev.py")
        spec = importlib.util.spec_from_file_location("_test_core_hook_dev", hook_path)
        self.assertIsNotNone(spec)
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)

        recorded = []

        class MockCtx:
            def set_module_config(self, mod_name, cfg_file, data):
                recorded.append((mod_name, cfg_file, data))

        hook_mod.on_test_setup(MockCtx())
        self.assertEqual(
            recorded,
            [("core", "config.project.json", {"project_root": "../mock_downstream_project"})],
        )

        # Plain object without set_module_config is safely ignored
        self.assertIsNone(hook_mod.on_test_setup(object()))
        self.assertIsNone(hook_mod.on_test_teardown(object()))
        self.mark_passed()

    def test_hook_observability_execution_and_traceback(self):
        """驗證 verbose 模式下 Hook 執行輸出與異常 Traceback 輸出，且一般模式保持乾淨。"""
        mod_scripts = "module://mock_obs/scripts"
        vfs.makedirs(mod_scripts, exist_ok=True)

        hook_code = (
            "def on_test_event(ctx):\n"
            "    return 'result_ok'\n\n"
            "def on_fail_event(ctx):\n"
            "    raise ValueError('Simulated hook failure for observability')\n"
        )
        vfs.write_text(f"{mod_scripts}/hook.core.py", hook_code)

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
            self.assertIn("Simulated hook failure for observability", str(res_err.get("mock_obs")))
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
            if vfs.exists("module://mock_obs"):
                vfs.rmtree("module://mock_obs")

        self.mark_passed()
