"""
Unit Tests for Server Module Configuration & Console Override Logic.
Covers default configuration values, type defense, CLI console/daemon overrides,
CLI lifecycle guards, and activity keepalive probing.
"""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
_cli_path = os.path.join(_pkg_root, "scripts", "cli.py")

_spec = importlib.util.spec_from_file_location("server_cli", _cli_path)
_server_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server_cli)

_resolve_enable_console = _server_cli._resolve_enable_console

from dev.testing.case import YSCBTestCase
from server import service as server_service
from server.config import (
    DEFAULT_IDLE_TIMEOUT_SEC,
    DEFAULT_STRICT_HOT_DISPATCH,
    DEFAULT_WORKER_ALIVE_TIMEOUT_SEC,
    ServerConfig,
    _parse_bool,
    _parse_float,
)


class TestServerConfig(YSCBTestCase):
    """Server 組態與 Console 啟動模式測試套件"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.cache_dir = os.path.join(self.root_dir, ".cache", "server")
        os.makedirs(self.cache_dir, exist_ok=True)
        server_service._LAST_TOUCH_TS = 0.0
        server_service._LAST_TOUCH_BY_ROOT.clear()

    def tearDown(self):
        self.doCleanups()
        server_service._LAST_TOUCH_TS = 0.0
        server_service._LAST_TOUCH_BY_ROOT.clear()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_default_config(self):
        """驗證 ServerConfig 預設值為 enable=True, enable_console=False 與 TTL=1800.0"""
        cfg = ServerConfig()
        self.assertTrue(cfg.enable)
        self.assertFalse(cfg.enable_console)
        self.assertEqual(cfg.idle_timeout_sec, 1800.0)
        self.assertEqual(cfg.strict_hot_dispatch, DEFAULT_STRICT_HOT_DISPATCH)
        self.assertEqual(cfg.worker_alive_timeout_sec, DEFAULT_WORKER_ALIVE_TIMEOUT_SEC)

        # 自 load() 預設無設定時載入
        with patch("core.config.get_all", return_value={}):
            loaded = ServerConfig.load()
            self.assertTrue(loaded.enable)
            self.assertFalse(loaded.enable_console)
            self.assertEqual(loaded.idle_timeout_sec, 1800.0)

        self.mark_passed()

    def test_config_override_and_type_defense(self):
        """驗證 ServerConfig 支援字典覆蓋、寬鬆布林轉型與非法數值回退預設值"""
        # 1. 字典直接覆蓋
        cfg1 = ServerConfig.load(override_dict={"enable_console": True, "idle_timeout_sec": 300.0})
        self.assertTrue(cfg1.enable_console)
        self.assertEqual(cfg1.idle_timeout_sec, 300.0)

        # 2. 字串防禦轉型 ("true", "1", "yes", "on")
        for truthy in ("true", "True", "1", "yes", "on"):
            cfg_t = ServerConfig.load(override_dict={"enable_console": truthy})
            self.assertTrue(cfg_t.enable_console)

        # 3. 偽值轉型 ("false", "0", "no", "off")
        for falsy in ("false", "False", "0", "no", "off"):
            cfg_f = ServerConfig.load(override_dict={"enable_console": falsy})
            self.assertFalse(cfg_f.enable_console)

        # 4. 數值與未知字串布林轉型、非法型別或 None 回退預設值
        self.assertTrue(_parse_bool(1, default=False))
        self.assertFalse(_parse_bool(0, default=True))
        self.assertFalse(_parse_bool(0.0, default=True))
        self.assertTrue(_parse_bool("unknown_flag", default=True))
        self.assertFalse(_parse_bool("unknown_flag", default=False))

        cfg_none = ServerConfig.load(override_dict={"enable_console": None})
        self.assertFalse(cfg_none.enable_console)

        cfg_invalid = ServerConfig.load(override_dict={"enable_console": [1, 2, 3]})
        self.assertFalse(cfg_invalid.enable_console)

        # 5. idle_timeout_sec 與 worker_alive_timeout_sec 非法值、bool、NaN、inf 或越界值回退預設值
        for bad_ttl in ("not-a-float", None, [1, 2], True, False, float("nan"), "nan", float("inf"), "-inf", -1.0, "-5"):
            cfg_bad_ttl = ServerConfig.load(override_dict={"idle_timeout_sec": bad_ttl})
            self.assertEqual(cfg_bad_ttl.idle_timeout_sec, DEFAULT_IDLE_TIMEOUT_SEC)

        cfg_zero_ttl = ServerConfig.load(override_dict={"idle_timeout_sec": 0})
        self.assertEqual(cfg_zero_ttl.idle_timeout_sec, 0.0)

        for bad_alive in ("not-a-float", None, 0, -5.0, True, False, float("nan"), "nan", float("inf"), "-inf"):
            cfg_bad_alive = ServerConfig.load(override_dict={"worker_alive_timeout_sec": bad_alive})
            self.assertEqual(cfg_bad_alive.worker_alive_timeout_sec, DEFAULT_WORKER_ALIVE_TIMEOUT_SEC)

        self.assertEqual(_parse_float(True, 10.0), 10.0)
        self.assertEqual(_parse_float(float("nan"), 10.0), 10.0)
        self.assertEqual(_parse_float(float("inf"), 10.0), 10.0)
        self.assertEqual(_parse_float(-0.1, 10.0, allow_zero=True), 10.0)
        self.assertEqual(_parse_float(0.0, 10.0, allow_zero=False), 10.0)

        cfg_alive_ok = ServerConfig.load(override_dict={"worker_alive_timeout_sec": "12.5", "strict_hot_dispatch": "yes"})
        self.assertEqual(cfg_alive_ok.worker_alive_timeout_sec, 12.5)
        self.assertTrue(cfg_alive_ok.strict_hot_dispatch)

        # 6. core.config 整合讀取與異常防禦回退
        with patch("core.config.get_all", return_value={"enable_console": True, "idle_timeout_sec": 60.0}):
            cfg_core = ServerConfig.load()
            self.assertTrue(cfg_core.enable_console)
            self.assertEqual(cfg_core.idle_timeout_sec, 60.0)

        with patch("core.config.get_all", side_effect=ValueError("corrupted config")):
            cfg_err = ServerConfig.load()
            self.assertTrue(cfg_err.enable)
            self.assertEqual(cfg_err.idle_timeout_sec, DEFAULT_IDLE_TIMEOUT_SEC)

        self.mark_passed()

    def test_cli_console_override(self):
        """驗證 CLI --console 具備最高優先權 (強制前台 Console，覆蓋 config False 與 --daemon)"""
        # config 為 False，CLI --console 為 True
        res = _resolve_enable_console(console_arg=True, daemon_arg=None, config_val=False)
        self.assertTrue(res)

        # config 為 True，CLI --console 為 True
        res2 = _resolve_enable_console(console_arg=True, daemon_arg=None, config_val=True)
        self.assertTrue(res2)

        # 同時傳入 console_arg=True 與 daemon_arg=True 時，console_arg 優先
        self.assertIs(_resolve_enable_console(console_arg=True, daemon_arg=True, config_val=False), True)

        self.mark_passed()

    def test_cli_daemon_override(self):
        """驗證 CLI --daemon 具備優先權 (強制背景脫鉤，覆蓋 config True)"""
        # config 為 True，CLI --daemon 為 True
        res = _resolve_enable_console(console_arg=None, daemon_arg=True, config_val=True)
        self.assertFalse(res)

        # config 為 False，CLI --daemon 為 True
        res2 = _resolve_enable_console(console_arg=None, daemon_arg=True, config_val=False)
        self.assertFalse(res2)

        self.mark_passed()

    def test_config_fallback_when_no_cli_args(self):
        """驗證無 CLI 參數時 (None, None)，精確回退至 config 設定值"""
        self.assertFalse(_resolve_enable_console(console_arg=None, daemon_arg=None, config_val=False))
        self.assertTrue(_resolve_enable_console(console_arg=None, daemon_arg=None, config_val=True))

        self.mark_passed()

    def test_cli_and_http_bad_request_guard(self):
        """驗證無效或負數 TTL 阻斷啟動，以及當 Server 停用時拒絕啟動"""
        from core.commands import CmdBags, CmdOption

        with patch.object(_server_cli, "guard_dispatch"), \
             patch.object(_server_cli, "_get_yscb_root", return_value=self.root_dir):
            # 1. 負數與非數值 TTL 阻斷
            for bad_ttl in ("-10", "not_a_number"):
                bags_bad = CmdBags(
                    raw_cmd="server start",
                    command="start",
                    args=[],
                    options={"ttl": CmdOption("ttl", bad_ttl)},
                )
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err_buf:
                    res_bad = _server_cli.start(bags_bad)
                self.assertEqual(res_bad, 1)
                self.assertIn("Invalid TTL value", err_buf.getvalue())

            # 2. Server 停用時阻斷
            with patch.object(_server_cli, "read_daemon_state", return_value=None), \
                 patch("server.config.ServerConfig.load", return_value=ServerConfig(enable=False)), \
                 redirect_stdout(io.StringIO()) as out_buf, redirect_stderr(io.StringIO()):
                bags = CmdBags(raw_cmd="server start", command="start", args=[], options={})
                code = _server_cli.start(bags)
                self.assertEqual(code, 1)
                self.assertIn("disabled in configuration", out_buf.getvalue())

        self.mark_passed()

    def test_server_reload_syncs_config_and_events_declared(self):
        """驗證 contributes/core.json 聲明 events 且 CLI 四大指令合約與邊界分支健全"""
        from core import vfs
        from core.commands import CmdBags, CmdOption
        from server.master import ServerDaemonState

        # 1. 驗證 contributes/core.json 聲明 events
        contrib = vfs.read_json("module.source://server/contributes/core.json")
        events_list = contrib.get("events", [])
        declared_events = {k for item in events_list if isinstance(item, dict) for k in item}
        self.assertIn("server_worker_warming", declared_events)
        self.assertIn("server_worker_ready", declared_events)

        with patch.object(_server_cli, "guard_dispatch"), \
             patch.object(_server_cli, "_get_yscb_root", return_value=self.root_dir):
            # 2. 驗證 stop / status / reload 在未運行時的優雅處理
            with patch.object(_server_cli, "read_daemon_state", return_value=None), \
                 patch("server.config.ServerConfig.load", return_value=ServerConfig(enable=True)), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(_server_cli.stop(CmdBags(raw_cmd="server stop", command="stop")), 0)
                self.assertEqual(_server_cli.status(CmdBags(raw_cmd="server status", command="status")), 0)
                self.assertEqual(_server_cli.reload(CmdBags(raw_cmd="server reload", command="reload")), 1)

            # 3. 驗證 status 在設定停用時輸出 Disabled
            with patch.object(_server_cli, "read_daemon_state", return_value=None), \
                 patch("server.config.ServerConfig.load", return_value=ServerConfig(enable=False)), \
                 redirect_stdout(io.StringIO()) as out_disabled:
                self.assertEqual(_server_cli.status(CmdBags(raw_cmd="server status", command="status")), 0)
                self.assertIn("Status: Disabled", out_disabled.getvalue())

            # 4. 驗證運行中狀態下 start / status / reload 邊界
            fake_state = ServerDaemonState(
                pid=os.getpid(),
                worker_pid=os.getpid(),
                port=59998,
                token="tok",
                root=self.root_dir,
                start_time=1700000000.0,
                idle_timeout_sec=300.0,
            )
            with patch.object(_server_cli, "read_daemon_state", return_value=fake_state), \
                 patch.object(_server_cli, "is_process_alive", return_value=True):
                # start: 已在運行時回傳 0 並印出狀態橫幅
                with patch.object(_server_cli, "_http_request", return_value=None), \
                     redirect_stdout(io.StringIO()) as out_already:
                    self.assertEqual(_server_cli.start(CmdBags(raw_cmd="server start", command="start")), 0)
                    self.assertIn("already running", out_already.getvalue())

                # status: 進程存活但 HTTP 無回應時回傳 1
                with patch.object(_server_cli, "_http_request", return_value=None), \
                     redirect_stdout(io.StringIO()) as out_unresp:
                    self.assertEqual(_server_cli.status(CmdBags(raw_cmd="server status", command="status")), 1)
                    self.assertIn("HTTP not responding", out_unresp.getvalue())

                # reload: 成功回傳新 Worker PID 時為 0，失敗時為 1
                with patch.object(_server_cli, "_http_request", return_value={"new_worker_pid": 54321}), \
                     redirect_stdout(io.StringIO()) as out_reload_ok:
                    self.assertEqual(_server_cli.reload(CmdBags(raw_cmd="server reload", command="reload")), 0)
                    self.assertIn("54321", out_reload_ok.getvalue())

                with patch.object(_server_cli, "_http_request", return_value=None), \
                     redirect_stdout(io.StringIO()) as out_reload_fail:
                    self.assertEqual(_server_cli.reload(CmdBags(raw_cmd="server reload", command="reload")), 1)
                    self.assertIn("failed or timed out", out_reload_fail.getvalue())

            # 5. 驗證 start --console 前台模式委派 MasterSupervisor.start(foreground=True)
            mock_sup = MagicMock()
            with patch.object(_server_cli, "read_daemon_state", return_value=None), \
                 patch("server.config.ServerConfig.load", return_value=ServerConfig(enable=True)), \
                 patch.object(_server_cli, "MasterSupervisor", return_value=mock_sup) as mock_sup_cls, \
                 redirect_stdout(io.StringIO()):
                console_bags = CmdBags(
                    raw_cmd="server start --console",
                    command="start",
                    args=[],
                    options={"console": CmdOption("console", True), "ttl": CmdOption("ttl", "120")},
                )
                self.assertEqual(_server_cli.start(console_bags), 0)
                mock_sup_cls.assert_called_once_with(yscb_root=self.root_dir, idle_timeout_sec=120.0)
                mock_sup.start.assert_called_once_with(foreground=True)

        self.mark_passed()

    def test_auto_spawn_config(self):
        """驗證 ServerConfig.auto_spawn 預設為 True，並支援覆蓋與防禦解析"""
        # 1. 預設值為 True
        cfg_def = ServerConfig()
        self.assertTrue(cfg_def.auto_spawn)

        # 2. override_dict 支援自訂
        cfg_false = ServerConfig.load(override_dict={"auto_spawn": False})
        self.assertFalse(cfg_false.auto_spawn)

        cfg_str_false = ServerConfig.load(override_dict={"auto_spawn": "false"})
        self.assertFalse(cfg_str_false.auto_spawn)

        cfg_true = ServerConfig.load(override_dict={"auto_spawn": "true"})
        self.assertTrue(cfg_true.auto_spawn)

        self.mark_passed()

    def test_touch_activity_probe_sdk(self):
        """驗證 server.touch_activity 探針 SDK 與 MasterSupervisor /api/touch 刷新閒置計時器，且顯式與隱式 yscb_root 共享節流視窗"""
        from server import touch_activity
        from server.master import MasterSupervisor, _create_http_server

        tmp_dir = tempfile.mkdtemp(prefix="yscb_srv_touch_")
        try:
            sup = MasterSupervisor(yscb_root=tmp_dir, idle_timeout_sec=1800.0, enable_watcher=False)
            self.addCleanup(sup.logger.archive_and_close)
            self.addCleanup(sup.stop)
            sup._last_active_time = 100.0
            httpd = _create_http_server(sup)
            sup.port = httpd.server_address[1]
            sup._write_state()
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                ok = touch_activity(yscb_root=tmp_dir, source="unit_test", force=True)
                self.assertTrue(ok)
                self.assertGreater(sup._last_active_time, 1000.0)

                # Implicit yscb_root=None resolving to the same tmp_dir shares the 1.0s throttle window
                with patch("server.service._resolve_service_root", return_value=tmp_dir), \
                     patch("urllib.request.urlopen") as mock_urlopen:
                    self.assertTrue(touch_activity(yscb_root=None, source="unit_test_implicit", force=False))
                    mock_urlopen.assert_not_called()
            finally:
                httpd.shutdown()
                httpd.server_close()
                sup.stop()
                sup.logger.archive_and_close()
        finally:
            server_service._LAST_TOUCH_TS = 0.0
            server_service._LAST_TOUCH_BY_ROOT.clear()
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
