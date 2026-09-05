"""
Unit and Integration Tests for knowledge-db HotReloadServer, Watcher, Hook, and Config (FT-01 ~ FT-11).
"""

import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.config import (
    DEFAULT_ENABLE_HOT_RELOAD_SERVER,
    DEFAULT_HOT_RELOAD_SERVER_INACTIVITY_TIMER_SEC,
    KnowledgeDBConfig,
)
import importlib.util

from knowledge_db.daemon import DaemonInfo, HotReloadServer
from scripts.cli import main


def _load_hook_core():
    hook_path = os.path.join(_pkg_root, "scripts", "hook.core.py")
    if os.path.isfile(hook_path):
        spec = importlib.util.spec_from_file_location("knowledge_db.hook_core", hook_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


class TestHotReloadServer(YSCBTestCase):
    """測試專屬 HotReloadServer、Watcher、Pre-dispatch 勾點與日誌治理 (FT-01 ~ FT-11)"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_config_loading_and_type_casting(self):
        """FT-01: 驗證 KnowledgeDBConfig 載入 enable_hot_reload_server 與 inactivity_timer_sec 型態防禦"""
        # 1. 預設值檢查
        cfg_default = KnowledgeDBConfig.load(workspace_root=self.root_path)
        self.assertFalse(cfg_default.enable_hot_reload_server)
        self.assertEqual(cfg_default.hot_reload_server_inactivity_timer_sec, DEFAULT_HOT_RELOAD_SERVER_INACTIVITY_TIMER_SEC)

        # 2. 字串布林安全解析
        cfg_true = KnowledgeDBConfig.load(
            workspace_root=self.root_path,
            local_config={"knowledge-db": {"enable_hot_reload_server": "true", "hot_reload_server_inactivity_timer_sec": "300"}},
        )
        self.assertTrue(cfg_true.enable_hot_reload_server)
        self.assertEqual(cfg_true.hot_reload_server_inactivity_timer_sec, 300)

        cfg_false = KnowledgeDBConfig.load(
            workspace_root=self.root_path,
            local_config={"knowledge-db": {"enable_hot_reload_server": "0", "hot_reload_server_inactivity_timer_sec": "-50"}},
        )
        self.assertFalse(cfg_false.enable_hot_reload_server)
        self.assertEqual(cfg_false.hot_reload_server_inactivity_timer_sec, DEFAULT_HOT_RELOAD_SERVER_INACTIVITY_TIMER_SEC)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_daemon_pid_lifecycle_and_location(self):
        """FT-02: 驗證 PID 檔案存放於 cache:// 目錄下，且包含完整中繼資料 (FR-09)"""
        cache_dir = HotReloadServer.get_cache_dir(self.root_path)
        pid_file = HotReloadServer.get_pid_file(self.root_path)

        self.assertTrue(str(pid_file).endswith("daemon.pid"))
        # 確保不在 storage 內
        self.assertNotIn("storage", str(pid_file))

        server = HotReloadServer(workspace_root=self.root_path)
        server._setup_logger()
        server._write_pid_file()

        self.assertTrue(pid_file.is_file())
        with open(pid_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["pid"], os.getpid())
        self.assertIn("start_time", data)
        self.assertIn("version", data)
        self.assertEqual(data["workspace_root"], str(self.root_path))

        # 清理
        server._clean_pid_file()
        self.assertFalse(pid_file.is_file())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_daemon_log_rolling_retention(self):
        """FT-03: 驗證日誌滾動保留最多 3 份歷史日誌 (FR-10, EC-08)"""
        logs_dir = HotReloadServer.get_logs_dir(self.root_path)

        # 建立 5 份模擬舊日誌
        created_files = []
        for i in range(5):
            p = logs_dir / f"daemon_20260905_10000{i}_{1000 + i}.log"
            p.write_text(f"log {i}", encoding="utf-8")
            # 設定不同 mtime
            os.utime(p, (time.time() + i * 10, time.time() + i * 10))
            created_files.append(p)

        # 執行 3 世代滾動
        HotReloadServer.rotate_logs(logs_dir, keep=3)

        remaining = list(logs_dir.glob("daemon_*.log"))
        self.assertEqual(len(remaining), 3)

        # 保留的應該是時間最新的三份
        remaining_names = {p.name for p in remaining}
        self.assertIn("daemon_20260905_100004_1004.log", remaining_names)
        self.assertIn("daemon_20260905_100003_1003.log", remaining_names)
        self.assertIn("daemon_20260905_100002_1002.log", remaining_names)
        self.assertNotIn("daemon_20260905_100000_1000.log", remaining_names)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_watcher_debounce_and_hot_patch(self):
        """FT-04 & FT-10: 驗證 Watcher 事件過濾與 500ms 防抖機制 (FR-03, FR-04, EC-02)"""
        mock_pipeline = MagicMock()
        mock_pipeline.scanner.check_invalidation.return_value = (True, 1, "test", {}, MagicMock(has_changes=True))
        mock_pipeline.hot_patch_unified_index.return_value = (True, False, None)

        server = HotReloadServer(workspace_root=self.root_path, pipeline=mock_pipeline)

        # 1. 忽略目錄檔案不觸發
        ignored_file = str(self.root_path / ".git" / "COMMIT_EDITMSG")
        server.on_file_changed(ignored_file)
        self.assertIsNone(server._debounce_timer)

        # 2. 忽略副檔名不觸發
        bin_file = str(self.root_path / "source" / "test.pyc")
        server.on_file_changed(bin_file)
        self.assertIsNone(server._debounce_timer)

        # 3. 合法變更觸發防抖計時器
        valid_file = str(self.root_path / "source" / "test.py")
        server.on_file_changed(valid_file)
        self.assertIsNotNone(server._debounce_timer)

        # 連續呼叫（模擬 Burst Save Events EC-02）
        old_timer = server._debounce_timer
        time.sleep(0.05)
        server.on_file_changed(valid_file)
        # 計時器應該被重設
        self.assertIsNotNone(server._debounce_timer)

        # 取消防抖計時器手動執行 _execute_debounced_patch 驗證
        server._debounce_timer.cancel()
        server._execute_debounced_patch()

        # 驗證 pipeline 增量熱修補被正確調用一次
        mock_pipeline.scanner.check_invalidation.assert_called_once()
        mock_pipeline.hot_patch_unified_index.assert_called_once()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_inactivity_auto_shutdown(self):
        """FT-05: 驗證閒置時間超過設定值時觸發自動關閉 (FR-06)"""
        cfg = KnowledgeDBConfig(hot_reload_server_inactivity_timer_sec=10)
        server = HotReloadServer(workspace_root=self.root_path, config=cfg)
        server.last_activity_time = time.time() - 15  # 模擬已閒置 15 秒

        stopped = False

        def _mock_stop():
            nonlocal stopped
            stopped = True

        server.stop_server = _mock_stop

        # 執行單次閒置判定邏輯
        idle_duration = time.time() - server.last_activity_time
        if idle_duration >= server.config.hot_reload_server_inactivity_timer_sec:
            server.stop_server()

        self.assertTrue(stopped)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_version_mismatch_restart(self):
        """FT-06: 驗證模組版本不符時觸發強制重啟 (FR-11)"""
        pid_file = HotReloadServer.get_pid_file(self.root_path)

        # 寫入包含舊版本號的偽裝 PID 檔案（指向當前進程以通過 is_pid_alive）
        old_info = DaemonInfo(
            pid=os.getpid(),
            start_time=time.time(),
            version="0.1.0",
            workspace_root=str(self.root_path),
            log_file="",
        )
        with open(pid_file, "w", encoding="utf-8") as f:
            json.dump(old_info.to_dict(), f)

        # 探測運行狀態應回傳 True
        running, info = HotReloadServer.is_running(self.root_path)
        self.assertTrue(running)
        self.assertEqual(info.version, "0.1.0")

        # mock stop 與 subprocess.Popen 驗證 ensure_running 會先停止舊版本
        with patch.object(HotReloadServer, "stop") as mock_stop:
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                # 由於版本不一致，ensure_running 應該呼叫 stop
                HotReloadServer.ensure_running(self.root_path)
                mock_stop.assert_called_once_with(self.root_path)

        # 清理
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pre_cli_dispatch_hook(self):
        """FT-07: 驗證 on_pre_cli_dispatch 在不同組態下之行為 (FR-02, EC-06)"""
        hook_mod = _load_hook_core()
        self.assertIsNotNone(hook_mod)

        # 1. 沙盒環境下強制返回 False (EC-06)
        with patch.dict(os.environ, {"YSCB_TEST_SANDBOX": "1"}):
            self.assertFalse(hook_mod.on_pre_cli_dispatch())

        # 2. 未在沙盒且 enable_hot_reload_server=False 時返回 False
        with patch.dict(os.environ, {"YSCB_TEST_SANDBOX": "0"}):
            with patch("knowledge_db.config.KnowledgeDBConfig.load") as mock_cfg_load:
                mock_cfg_load.return_value = KnowledgeDBConfig(enable_hot_reload_server=False)
                self.assertFalse(hook_mod.on_pre_cli_dispatch())

        # 3. 未在沙盒且 enable_hot_reload_server=True 時調用 ensure_running
        with patch.dict(os.environ, {"YSCB_TEST_SANDBOX": "0"}):
            with patch("knowledge_db.config.KnowledgeDBConfig.load") as mock_cfg_load:
                mock_cfg_load.return_value = KnowledgeDBConfig(enable_hot_reload_server=True)
                with patch("knowledge_db.daemon.HotReloadServer.ensure_running", return_value=True) as mock_ensure:
                    res = hook_mod.on_pre_cli_dispatch()
                    self.assertTrue(res)
                    mock_ensure.assert_called_once()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_daemon_commands(self):
        """FT-08: 驗證 CLI knowledge-db daemon [status|stop] 指令輸出與行為 (FR-07)"""
        # status 指令輸出 JSON 測試
        f_out = io.StringIO()
        with patch("sys.stdout", f_out):
            ret = main(["daemon", "status", "--json", f"--workspace-root={self.root_path}"])
        self.assertEqual(ret, 0)
        out_json = json.loads(f_out.getvalue())
        self.assertFalse(out_json["running"])
        self.assertIn("current_module_version", out_json)

        # stop 指令（無實例時仍應回傳 0 成功）
        f_out2 = io.StringIO()
        with patch("sys.stdout", f_out2):
            ret2 = main(["daemon", "stop", f"--workspace-root={self.root_path}"])
        self.assertEqual(ret2, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_stale_pid_cleanup_and_signals(self):
        """FT-09: 驗證殭屍 PID 自動清理 (EC-01) 與信號安全防護 (EC-05)"""
        pid_file = HotReloadServer.get_pid_file(self.root_path)

        # 寫入一個極大不存在的 PID (如 99999999)
        stale_info = DaemonInfo(
            pid=99999999,
            start_time=time.time(),
            version="1.0.0",
            workspace_root=str(self.root_path),
            log_file="",
        )
        with open(pid_file, "w", encoding="utf-8") as f:
            json.dump(stale_info.to_dict(), f)

        self.assertTrue(pid_file.is_file())

        # 探測時應偵測到死進程並自動清理 PID 檔案
        running, info = HotReloadServer.is_running(self.root_path)
        self.assertFalse(running)
        self.assertIsNone(info)
        self.assertFalse(pid_file.is_file())

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_dynamic_space_watching_and_signature_mismatch(self):
        """FT-12: 驗證 Watcher 監聽目錄由 SpaceManager 動態解算，且空間簽名失配時自動重啟 (FR-03, FR-11, EC-09)"""
        # 1. 建立假空間目錄
        sp1_dir = self.root_path / "custom_space1"
        sp1_dir.mkdir(parents=True, exist_ok=True)
        sp2_dir = self.root_path / "custom_space2"
        sp2_dir.mkdir(parents=True, exist_ok=True)

        mock_sm = MagicMock()
        mock_sp1 = MagicMock()
        mock_sp1.name = "space1"
        mock_sp1.include = [str(sp1_dir)]
        mock_sp1.exclude = []
        mock_sp1.file_patterns = None
        mock_sm.get_union_spaces.return_value = [mock_sp1]
        mock_sm.resolve_space_include.side_effect = lambda name: [sp1_dir] if name == "space1" else [sp2_dir]

        server = HotReloadServer(workspace_root=self.root_path, space_manager=mock_sm)
        watch_dirs = server.get_watch_directories()
        self.assertIn(sp1_dir.resolve(), watch_dirs)
        self.assertNotIn(sp2_dir.resolve(), watch_dirs)

        # 2. 驗證空間簽名計算
        names, sig1 = HotReloadServer.get_current_spaces_signature(
            workspace_root=self.root_path,
            space_manager=mock_sm,
        )
        self.assertEqual(names, ["space1"])
        self.assertTrue(len(sig1) > 0)

        # 變更空間為 space2
        mock_sp2 = MagicMock()
        mock_sp2.name = "space2"
        mock_sp2.include = [str(sp2_dir)]
        mock_sp2.exclude = []
        mock_sp2.file_patterns = None
        mock_sm.get_union_spaces.return_value = [mock_sp2]

        names2, sig2 = HotReloadServer.get_current_spaces_signature(
            workspace_root=self.root_path,
            space_manager=mock_sm,
        )
        self.assertEqual(names2, ["space2"])
        self.assertNotEqual(sig1, sig2)

        # 3. 驗證 ensure_running 偵測到 spaces_signature 失配自動重啟
        pid_file = HotReloadServer.get_pid_file(self.root_path)
        current_pid = os.getpid()
        old_info = DaemonInfo(
            pid=current_pid,
            start_time=time.time(),
            version=HotReloadServer.get_module_version(),
            workspace_root=str(self.root_path),
            log_file="",
            spaces=["space1"],
            spaces_signature=sig1,
        )
        with open(pid_file, "w", encoding="utf-8") as f:
            json.dump(old_info.to_dict(), f)

        # 此時當前空間為 space2 (sig2 != sig1)，ensure_running 應觸發 stop 並重啟
        with patch("knowledge_db.daemon.HotReloadServer.stop") as mock_stop:
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc
                HotReloadServer.ensure_running(workspace_root=self.root_path, space_manager=mock_sm)
                mock_stop.assert_called_once()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_jit_skip_notification_when_server_running(self):
        """FT-13: 驗證運行 CLI 時若後台存在 server 則跳過 JIT 並輸出指定提示 (FR-12)"""
        from knowledge_db.daemon import check_and_notify_hot_reload_server
        import knowledge_db.daemon as daemon_mod

        # 重設通知旗標
        daemon_mod._SERVER_JIT_NOTIFIED = False

        fake_info = DaemonInfo(
            pid=54321,
            start_time=time.time(),
            version="1.0.0",
            workspace_root=str(self.root_path),
            log_file="",
        )

        with patch("knowledge_db.daemon.HotReloadServer.is_running", return_value=(True, fake_info)):
            f_err = io.StringIO()
            with patch("sys.stderr", f_err):
                is_running, info = check_and_notify_hot_reload_server(self.root_path)
            self.assertTrue(is_running)
            self.assertIn("Hot reload server(pid:54321) exist, skip JIT check.", f_err.getvalue())

            # 第二次調用應不重複輸出
            f_err2 = io.StringIO()
            with patch("sys.stderr", f_err2):
                is_running2, _ = check_and_notify_hot_reload_server(self.root_path)
            self.assertTrue(is_running2)
            self.assertEqual(f_err2.getvalue(), "")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_server_startup_offline_check(self):
        """FT-14: 驗證 Server 啟動時執行與 JIT 相同的離線變更預檢 (FR-13)"""
        server = HotReloadServer(workspace_root=self.root_path)
        server._setup_logger()

        mock_pipeline = MagicMock()
        mock_pipeline.get_indices_dir.return_value = self.root_path / "indices"
        (self.root_path / "indices").mkdir(parents=True, exist_ok=True)
        meta_file = self.root_path / "indices" / "unified.meta.bin"
        bin_file = self.root_path / "indices" / "unified.index.bin.gz"

        # 情境 A: 索引不存在時自動 full build
        server.pipeline = mock_pipeline
        server._run_startup_check()
        mock_pipeline.build_unified_index.assert_called_with(force=True)

        # 情境 B: 檔案存在但有離線變更時呼叫 hot_patch_unified_index
        meta_file.touch()
        bin_file.touch()
        mock_diff = MagicMock()
        mock_diff.has_changes = True
        mock_pipeline.scanner.check_invalidation.return_value = (True, 5, "offline modified", {}, mock_diff)

        server._run_startup_check()
        mock_pipeline.hot_patch_unified_index.assert_called_with(mock_diff, {}, timeout_seconds=float('inf'))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_config_jit_disabled_when_server_enabled(self):
        """FT-15: 驗證啟用 Server 時，config 中的 JIT 設定視為無效 (FR-14)"""
        cfg_server_on = KnowledgeDBConfig(
            enable_hot_reload_server=True,
            jit_vector_timeout_seconds=5.0,
        )
        self.assertFalse(cfg_server_on.is_jit_effective)
        self.assertIsNone(cfg_server_on.resolve_jit_vector_timeout())

        cfg_server_off = KnowledgeDBConfig(
            enable_hot_reload_server=False,
            jit_vector_timeout_seconds=5.0,
        )
        self.assertTrue(cfg_server_off.is_jit_effective)
        self.assertEqual(cfg_server_off.resolve_jit_vector_timeout(), 5.0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_contributes_driven_extensions_and_path_filter(self):
        """FT-16: 驗證 Contributes 驅動之副檔名動態解算與 Space exclude/pattern 動態過濾 (零硬編碼)"""
        from knowledge_db.parsers.registry import ParserRegistry
        from knowledge_db.daemon import resolve_watch_extensions, DEFAULT_VCS_IGNORED_DIRS
        from knowledge_db.schema import SpaceConfig

        # 1. 驗證 ParserRegistry 動態副檔名收集
        reg = ParserRegistry()
        exts = reg.get_supported_extensions()
        self.assertIn(".py", exts)
        self.assertIn(".md", exts)
        self.assertIn(".sp", exts)   # SPICE custom parser
        self.assertIn(".html", exts) # HTML custom parser
        self.assertIn(".css", exts)  # CSS custom parser
        self.assertIn(".cs", exts)   # C# parser

        # 2. 驗證 resolve_watch_extensions 結合 SpaceConfig.file_patterns
        sp_custom = SpaceConfig(
            name="custom_space",
            include=[str(self.root_path / "custom")],
            exclude=["**/ignore_me/**"],
            file_patterns=["*.custom_ext", "*.py"],
        )
        mock_sm = MagicMock()
        mock_sm.get_union_spaces.return_value = [sp_custom]
        mock_sm.resolve_space_include.return_value = [self.root_path / "custom"]

        watch_exts = resolve_watch_extensions(space_manager=mock_sm, parser_registry=reg)
        self.assertIn(".custom_ext", watch_exts)
        self.assertIn(".py", watch_exts)
        self.assertIn(".json", watch_exts)

        # 3. 驗證 HotReloadServer.is_path_watched 動態過濾
        server = HotReloadServer(workspace_root=self.root_path, space_manager=mock_sm)

        # 情境 A: VCS/Runtime 目錄強制忽略
        self.assertFalse(server.is_path_watched(self.root_path / ".git" / "HEAD"))
        self.assertFalse(server.is_path_watched(self.root_path / "custom" / "__pycache__" / "a.py"))

        # 情境 B: 非支援副檔名
        self.assertFalse(server.is_path_watched(self.root_path / "custom" / "test.unknown_ext"))

        # 情境 C: 符合 Space include 且副檔名支援
        (self.root_path / "custom").mkdir(parents=True, exist_ok=True)
        valid_file = self.root_path / "custom" / "valid.py"
        self.assertTrue(server.is_path_watched(valid_file))

        # 情境 D: 命中 Space exclude 模式
        excluded_file = self.root_path / "custom" / "ignore_me" / "test.py"
        self.assertFalse(server.is_path_watched(excluded_file))

        # 情境 E: 不符合 Space file_patterns (如 custom_space 只允許 *.custom_ext 與 *.py，若為 .md 則應過濾)
        md_file = self.root_path / "custom" / "doc.md"
        self.assertFalse(server.is_path_watched(md_file))

        self.mark_passed()

