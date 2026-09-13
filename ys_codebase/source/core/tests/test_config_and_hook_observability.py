"""
Unit and integration tests for Config Hierarchy Shadowing Remediation and Hook Observability.
Covers FT-01 and FT-02 under sub_03_config_hierarchy_and_hook_observability.
"""
import io
import json
import os
import sys
from unittest.mock import patch

from dev.testing.case import YSCBTestCase
from core.engine import AtomicEngine
from core.commands.dispatcher import _ensure_hooks
from core.uri import ExecutionContext
from core import config, events, uri


class TestConfigAndHookObservability(YSCBTestCase):
    """驗證組態階層防遮蔽守門與 Hook 執行可觀測性強化。"""

    def setUp(self):
        super().setUp()
        config.reload()

    def test_config_local_no_unwanted_creation_and_project_hierarchy(self):
        """FT-01: 驗證模組部署時不預設生成空/預設 config.local.json 遮蔽 config.project.json。"""
        mod_name = "test_mod_clean_cfg"
        mod_uri = f"module://{mod_name}"
        uri.makedirs(f"{mod_uri}/configurable", exist_ok=True)

        proj_payload = {
            "setting_a": "value_a",
            "setting_b": 123
        }
        uri.write_json(f"{mod_uri}/configurable/config.project.json", proj_payload, indent=2)

        # 註冊模組並呼叫 engine 部署
        engine = AtomicEngine()
        cfg_path, host_cfg = engine._get_config()
        orig_installed = dict(host_cfg.get("installed_modules", {}))
        host_cfg.setdefault("installed_modules", {})[mod_name] = {"version": "0.1.0"}
        engine._save_config(cfg_path, host_cfg)

        try:
            engine.act_deploy_configs_from_modules()

            cfg_proj_uri = f"config://{mod_name}/config.project.json"
            cfg_local_uri = f"config://{mod_name}/config.local.json"

            # 斷言 project 組態正常物化
            self.assertTrue(uri.exists(cfg_proj_uri), "config.project.json must be materialized!")
            loaded_proj = uri.read_json(cfg_proj_uri)
            self.assertEqual(loaded_proj.get("setting_a"), "value_a")
            self.assertEqual(loaded_proj.get("setting_b"), 123)

            # 剛性斷言：不得生成多餘的 config.local.json 造成未來團隊組態被遮蔽
            self.assertFalse(uri.exists(cfg_local_uri), "config.local.json should NOT be created automatically when empty!")

            # 額外驗證 _seed_or_update_config 遇空 local 模板亦不產生 config.local.json
            tpl_local_uri = f"module://{mod_name}/contributes/config.local.json"
            uri.makedirs(f"module://{mod_name}/contributes", exist_ok=True)
            uri.write_json(tpl_local_uri, {})
            engine._seed_or_update_config(mod_name, f"module://{mod_name}/contributes")
            # 驗證透過 core.config 讀取 project 組態正常生效
            config.reload(mod_name)
            self.assertEqual(config.get(mod_name, "setting_a"), "value_a")
            self.assertEqual(config.get(mod_name, "setting_b"), 123)

            # 驗證若寫入 local 組態，則 local 覆蓋 project
            config.set(mod_name, "setting_a", "local_override_a", local=True)
            self.assertEqual(config.get(mod_name, "setting_a"), "local_override_a")
            self.assertEqual(config.get(mod_name, "setting_b"), 123)
        finally:
            host_cfg["installed_modules"] = orig_installed
            engine._save_config(cfg_path, host_cfg)

        # 清理測試模組與組態
        if uri.exists(f"config://{mod_name}"):
            uri.rmtree(f"config://{mod_name}")
        if uri.exists(mod_uri):
            uri.rmtree(mod_uri)

        self.mark_passed()

    def test_hook_observability_execution_and_traceback(self):
        """FT-02: 驗證 verbose 模式下 Hook 執行輸出與異常 Traceback 輸出，且一般模式保持乾淨。"""
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

        # 1. 驗證 verbose=False (或一般模式) 執行正常 Hook 時 stderr 保持乾淨
        buf_quiet = io.StringIO()
        with patch("sys.stderr", buf_quiet):
            res_quiet = events.broadcast("test_event", context=ctx, emit_module="core", verbose=False)
        self.assertEqual(res_quiet.get("mock_obs"), "result_ok")
        self.assertEqual(buf_quiet.getvalue(), "")

        # 2. 驗證 verbose=True 執行正常 Hook 時 stderr 輸出執行狀態
        buf_verbose = io.StringIO()
        with patch("sys.stderr", buf_verbose):
            res_verbose = events.broadcast("test_event", context=ctx, emit_module="core", verbose=True)
        self.assertEqual(res_verbose.get("mock_obs"), "result_ok")
        verbose_out = buf_verbose.getvalue()
        self.assertIn("[core:events] Hook 'mock_obs:hook.core.py' executed 'test_event' -> result_ok", verbose_out)

        # 3. 驗證環境變數 YSCB_VERBOSE=1 自動生效
        buf_env = io.StringIO()
        with patch.dict(os.environ, {"YSCB_VERBOSE": "1"}):
            with patch("sys.stderr", buf_env):
                res_env = events.broadcast("test_event", context=ctx, emit_module="core")
        self.assertEqual(res_env.get("mock_obs"), "result_ok")
        self.assertIn("[core:events] Hook 'mock_obs:hook.core.py' executed 'test_event' -> result_ok", buf_env.getvalue())

        # 4. 驗證 Hook 失敗時，verbose=True 輸出完整 Traceback
        buf_err = io.StringIO()
        with patch("sys.stderr", buf_err):
            res_err = events.broadcast("fail_event", context=ctx, emit_module="core", verbose=True)
        self.assertTrue(str(res_err.get("mock_obs")).startswith("warning:"))
        err_out = buf_err.getvalue()
        self.assertIn("Warning: Hook 'mock_obs:hook.core.py' failed on 'fail_event'", err_out)
        self.assertIn("Traceback (most recent call last):", err_out)
        self.assertIn("Simulated hook failure for observability", err_out)

        # 5. 驗證 dispatcher._ensure_hooks 正確傳遞並回傳結果字典
        buf_disp = io.StringIO()
        with patch("sys.stderr", buf_disp):
            disp_res = _ensure_hooks("test_event", verbose=True)
        self.assertEqual(disp_res.get("mock_obs"), "result_ok")
        self.assertIn("[core:dispatcher] Hooks for 'test_event' completed:", buf_disp.getvalue())

        # 清理
        uri.rmtree("module://mock_obs")
        self.mark_passed()
