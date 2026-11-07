"""
Unit tests for Core Platform SDK (core.platform).
Covers process primitives (spawn_detached, is_process_alive, kill_process_tree)
and cross-platform inter-process file locks (InterProcessLock).
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest

from core.platform import (
    InterProcessLock,
    is_process_alive,
    kill_process_tree,
    spawn_detached,
)
from tests import load_yscb_host_module
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.ENV)
class TestCorePlatform(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = os.path.join(self.temp_dir.name, "test.lock")

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    def test_spawn_and_liveness_and_kill(self):
        """spawn_detached starts background process, is_process_alive detects it, kill_process_tree terminates it."""
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        pid = spawn_detached(cmd)
        try:
            self.assertGreater(pid, 0)
            self.assertTrue(is_process_alive(pid))

            # Kill the spawned process tree
            killed = kill_process_tree(pid, timeout_sec=2.0)
            self.assertTrue(killed)
            self.assertFalse(is_process_alive(pid))
        finally:
            if pid > 0 and is_process_alive(pid):
                kill_process_tree(pid, timeout_sec=1.0)
        self.mark_passed()

    def test_is_process_alive_invalid(self):
        """Invalid, boolean, or non-existent PID returns False."""
        self.assertFalse(is_process_alive(0))
        self.assertFalse(is_process_alive(-1))
        self.assertFalse(is_process_alive(99999999))
        self.assertFalse(is_process_alive(True))
        self.assertFalse(is_process_alive(False))
        self.mark_passed()

    def test_inter_process_lock_mutual_exclusion(self):
        """InterProcessLock prevents concurrent acquisition on the same file."""
        lock1 = InterProcessLock(self.lock_path)
        lock2 = InterProcessLock(self.lock_path)

        # Acquire lock1
        self.assertTrue(lock1.acquire(blocking=False))
        self.assertTrue(lock1.is_locked)

        # lock2 should fail non-blocking acquisition
        self.assertFalse(lock2.acquire(blocking=False))
        self.assertFalse(lock2.is_locked)

        # Release lock1
        lock1.release()
        self.assertFalse(lock1.is_locked)

        # lock2 should now succeed
        self.assertTrue(lock2.acquire(blocking=False))
        self.assertTrue(lock2.is_locked)
        lock2.release()
        self.mark_passed()

    def test_inter_process_lock_context_manager(self):
        """InterProcessLock context manager auto acquires and releases."""
        with InterProcessLock(self.lock_path) as lock:
            self.assertTrue(lock.is_locked)
            other_lock = InterProcessLock(self.lock_path)
            self.assertFalse(other_lock.acquire(blocking=False))

        # After exiting context manager, lock is released
        reacquired = InterProcessLock(self.lock_path)
        self.assertTrue(reacquired.acquire(blocking=False))
        reacquired.release()
        self.mark_passed()

    def test_ensure_private_venv(self):
        """ensure_private_venv injects site-packages, filters comments/imports in host_venv.pth, and preserves order."""
        import platform
        from core.platform import ensure_private_venv, restore_sys_path

        tag = f"py{sys.version_info.major}{sys.version_info.minor}"
        sys_name = platform.system()
        sub = (
            os.path.join(".venv", tag, "Lib", "site-packages")
            if sys_name == "Windows"
            else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
        )
        fake_site = os.path.join(self.temp_dir.name, sub)
        os.makedirs(fake_site, exist_ok=True)

        extra_pth_1 = os.path.join(self.temp_dir.name, "extra_lib_1")
        extra_pth_2 = os.path.join(self.temp_dir.name, "extra_lib_2")
        os.makedirs(extra_pth_1, exist_ok=True)
        os.makedirs(extra_pth_2, exist_ok=True)
        pth_file = os.path.join(fake_site, "host_venv.pth")
        with open(pth_file, "w", encoding="utf-8") as f:
            f.write("# comment line\nimport sys\n" + extra_pth_1 + "\n" + extra_pth_2 + "\n")

        snap = list(sys.path)
        try:
            ensure_private_venv(self.temp_dir.name)
            self.assertIn(fake_site, sys.path)
            self.assertIn(extra_pth_1, sys.path)
            self.assertIn(extra_pth_2, sys.path)
            self.assertLess(sys.path.index(fake_site), sys.path.index(extra_pth_1))
            self.assertLess(sys.path.index(extra_pth_1), sys.path.index(extra_pth_2))
        finally:
            restore_sys_path(snap)
        self.mark_passed()

    def test_set_process_title(self):
        """set_process_title runs cross-platform without raising exceptions."""
        from core.platform import set_process_title
        result = set_process_title("yscb test runner")
        self.assertIsInstance(result, bool)
        self.mark_passed()

    def test_can_spawn_background_daemon(self):
        """can_spawn_background_daemon probes environment and caches result."""
        from core.platform import can_spawn_background_daemon

        # 1. Direct call returns bool
        res1 = can_spawn_background_daemon(force_reprobe=True)
        self.assertIsInstance(res1, bool)

        # 2. Cached call returns identical result without reprobing
        res2 = can_spawn_background_daemon(force_reprobe=False)
        self.assertEqual(res1, res2)

        # 3. Environment override YSCB_NO_DAEMON
        old_val = os.environ.get("YSCB_NO_DAEMON")
        try:
            os.environ["YSCB_NO_DAEMON"] = "1"
            res_override = can_spawn_background_daemon(force_reprobe=True)
            self.assertFalse(res_override)
        finally:
            if old_val is not None:
                os.environ["YSCB_NO_DAEMON"] = old_val
            else:
                os.environ.pop("YSCB_NO_DAEMON", None)
            can_spawn_background_daemon(force_reprobe=True)

        self.mark_passed()

    def _dead_pid(self) -> int:
        with subprocess.Popen([sys.executable, "-c", "pass"]) as proc:
            proc.wait()
            return proc.pid

    def test_daemon_probe_reaping_detection(self):
        """EC-05: 未經 clean exit 之 spawn PID 死亡累計 reaped_count，門檻 2 判不可常駐；clean exit 歸零。"""
        from core.platform import daemon_probe

        root = self.temp_dir.name
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))

        daemon_probe.record_spawn(root, self._dead_pid())
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))  # EC-05: 1 次不判定
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))  # 同紀錄不重複累計

        daemon_probe.record_spawn(root, self._dead_pid())
        self.assertTrue(daemon_probe.is_reaping_env(root, daemon_active=False))

        daemon_probe.mark_clean_exit(root)
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))

        # 活躍 daemon 或存活 PID 不累計
        daemon_probe.record_spawn(root, self._dead_pid())
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=True))
        daemon_probe.record_spawn(root, os.getpid())
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))
        self.mark_passed()

    def test_daemon_probe_corrupt_file_and_fingerprint_isolation(self):
        """EC-03 / EC-04: 損壞檔視為無紀錄並可覆寫；不同 env_fingerprint 之紀錄互不污染。"""
        import json
        from unittest.mock import patch
        from core.platform import daemon_probe

        root = self.temp_dir.name
        probe_file = os.path.join(root, daemon_probe.PROBE_REL_PATH)
        os.makedirs(os.path.dirname(probe_file), exist_ok=True)
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertFalse(daemon_probe.is_reaping_env(root, daemon_active=False))
        daemon_probe.record_spawn(root, 123)
        with open(probe_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)[daemon_probe.env_fingerprint()]["pid"], 123)

        with patch.object(daemon_probe, "env_fingerprint", return_value="other-host|win32"):
            daemon_probe.record_spawn(root, self._dead_pid())
            daemon_probe.is_reaping_env(root, daemon_active=False)
            daemon_probe.record_spawn(root, self._dead_pid())
            self.assertTrue(daemon_probe.is_reaping_env(root, daemon_active=False))
        with open(probe_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[daemon_probe.env_fingerprint()]["reaped_count"], 0)
        self.assertEqual(data["other-host|win32"]["reaped_count"], 2)
        self.mark_passed()

    def test_can_spawn_force_and_posix_probe(self):
        """YSCB_FORCE_DAEMON 優先於 YSCB_NO_DAEMON；POSIX 帶 yscb_root 時依實證偵測，未帶時為 True。"""
        from unittest.mock import patch
        from core.platform import can_spawn_background_daemon, daemon_probe

        root = self.temp_dir.name
        clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_FORCE_DAEMON", "YSCB_NO_DAEMON")}
        with patch.dict(os.environ, dict(clean_env, YSCB_FORCE_DAEMON="1", YSCB_NO_DAEMON="1"), clear=True):
            self.assertTrue(can_spawn_background_daemon(force_reprobe=True, yscb_root=root))
        with patch.dict(os.environ, dict(clean_env, YSCB_NO_DAEMON="1"), clear=True):
            self.assertFalse(can_spawn_background_daemon(force_reprobe=True, yscb_root=root))
        if sys.platform != "win32":
            with patch.dict(os.environ, clean_env, clear=True):
                self.assertTrue(can_spawn_background_daemon(yscb_root=root))
                daemon_probe.record_spawn(root, self._dead_pid())
                can_spawn_background_daemon(yscb_root=root)
                daemon_probe.record_spawn(root, self._dead_pid())
                self.assertFalse(can_spawn_background_daemon(yscb_root=root))
                self.assertTrue(can_spawn_background_daemon())
        self.mark_passed()

    @unittest.skipIf(sys.platform == "win32", "POSIX process-group semantics")
    def test_terminate_popen_tree_kills_group_and_escalates(self):
        """terminate_popen_tree 終止整個程序群組（含孫進程），忽略 SIGTERM 時升級 SIGKILL，並由 Popen 回收。"""
        from core.platform import terminate_popen_tree

        code = (
            "import signal, subprocess, sys, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
            "print(c.pid, flush=True); time.sleep(30)"
        )
        proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, start_new_session=True)
        try:
            child_pid = int(proc.stdout.readline().decode().strip())
            self.assertTrue(is_process_alive(child_pid))
            t0 = time.time()
            self.assertTrue(terminate_popen_tree(proc, timeout_sec=0.5))
            self.assertLess(time.time() - t0, 5.0)
            self.assertIsNotNone(proc.returncode)
            deadline = time.time() + 3.0
            import select
            while is_process_alive(child_pid) and time.time() < deadline:
                select.select([], [], [], 0.02)
            self.assertFalse(is_process_alive(child_pid))
            # 已結束之進程再次呼叫直接回傳 True
            self.assertTrue(terminate_popen_tree(proc, timeout_sec=0.5))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        self.mark_passed()

    def test_lock_eexist_retry(self):
        """os.open 遇 FileExistsError 重試（不帶 O_CREAT）後成功；持續失敗拋原例外；其他 errno 不重試。"""
        from unittest.mock import patch

        real_open = os.open
        calls = []

        def flaky_open(path, flags, *args):
            calls.append(flags)
            if len(calls) == 1:
                raise FileExistsError(17, "File exists", path)
            return real_open(path, flags, *args)

        lock = InterProcessLock(self.lock_path)
        with open(self.lock_path, "a", encoding="utf-8"):
            pass
        with patch("core.platform.lock.os.open", side_effect=flaky_open), patch("core.platform.lock.time.sleep"):
            self.assertTrue(lock.acquire(blocking=False))
        lock.release()
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0] & os.O_CREAT)
        self.assertFalse(calls[1] & os.O_CREAT)

        always_err = FileExistsError(17, "File exists", self.lock_path)
        with patch("core.platform.lock.os.open", side_effect=always_err) as mock_open, \
             patch("core.platform.lock.time.sleep"):
            with self.assertRaises(FileExistsError) as ctx:
                InterProcessLock(self.lock_path).acquire(blocking=False)
        self.assertIs(ctx.exception, always_err)
        self.assertEqual(mock_open.call_count, 4)

        with patch("core.platform.lock.os.open", side_effect=PermissionError(13, "denied")) as mock_perm:
            with self.assertRaises(PermissionError):
                InterProcessLock(self.lock_path).acquire(blocking=False)
        self.assertEqual(mock_perm.call_count, 1)
        self.mark_passed()

    def test_daemon_probe_lazy_lock_probe(self):
        """僅於紀錄 pid 已死且無 clean exit 時才探測 daemon 活躍；daemon.json pid 存活優先於 daemon.lock 探測。"""
        import json
        from unittest.mock import patch
        from core.platform import daemon_probe

        root = self.temp_dir.name
        with patch.object(daemon_probe, "is_daemon_lock_held", return_value=False) as mock_lock:
            self.assertFalse(daemon_probe.is_reaping_env(root))  # no record
            daemon_probe.record_spawn(root, os.getpid())
            self.assertFalse(daemon_probe.is_reaping_env(root))  # pid alive
            daemon_probe.mark_clean_exit(root)
            self.assertFalse(daemon_probe.is_reaping_env(root))  # clean exit
            mock_lock.assert_not_called()

            state_file = os.path.join(root, daemon_probe.DAEMON_STATE_REL_PATH)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid()}, f)
            daemon_probe.record_spawn(root, self._dead_pid())
            daemon_probe.is_reaping_env(root)
            mock_lock.assert_not_called()  # daemon.json pid alive short-circuits the lock probe
            os.remove(state_file)

            daemon_probe.record_spawn(root, self._dead_pid())
            daemon_probe.is_reaping_env(root)
            mock_lock.assert_called_once_with(root)
        with open(os.path.join(root, daemon_probe.PROBE_REL_PATH), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)[daemon_probe.env_fingerprint()]["reaped_count"], 1)
        self.mark_passed()

    def test_daemon_probe_bind_master_pid(self):
        """bind_master_pid 將 launcher PID 紀錄改綁 master PID；無紀錄或已 clean_exit 時不動作。"""
        import json
        from core.platform import daemon_probe

        root = self.temp_dir.name
        probe_file = os.path.join(root, daemon_probe.PROBE_REL_PATH)
        daemon_probe.bind_master_pid(root, 222)
        self.assertFalse(os.path.exists(probe_file))

        daemon_probe.record_spawn(root, 111)
        daemon_probe.bind_master_pid(root, 222)
        with open(probe_file, "r", encoding="utf-8") as f:
            entry = json.load(f)[daemon_probe.env_fingerprint()]
        self.assertEqual(entry["pid"], 222)
        self.assertFalse(entry["clean_exit"])

        daemon_probe.mark_clean_exit(root)
        daemon_probe.bind_master_pid(root, 333)
        with open(probe_file, "r", encoding="utf-8") as f:
            entry = json.load(f)[daemon_probe.env_fingerprint()]
        self.assertEqual(entry["pid"], 0)
        self.assertTrue(entry["clean_exit"])
        self.mark_passed()

    def test_parse_simple_semver_prerelease(self):
        """_parse_simple_semver 預發布標籤不污染主版號數字，且預發布版排序低於同版號正式版。"""
        from core import engine, semver

        yscb_mod = load_yscb_host_module()
        parsers = [engine._parse_simple_semver, yscb_mod._parse_simple_semver]

        for parse_fn in parsers:
            rc_ver = parse_fn("1.2.0-rc1")
            rel_ver = parse_fn("1.2.0")
            self.assertLess(rc_ver, rel_ver)
            self.assertEqual(rc_ver[:4], (1, 2, 0, 0))
            self.assertFalse(rc_ver[4])
            self.assertNotEqual(parse_fn("1.0.0-rc1")[:4], parse_fn("1.0.1")[:4])
            self.assertLess(parse_fn("1.0.0-rc1"), parse_fn("1.0.1"))
            self.assertTrue(parse_fn("1.2.0.build")[4])

        vt = semver.parse_semver("1.2.0.0-rc1")
        self.assertEqual((vt.major, vt.minor, vt.patch, vt.revision, vt.prerelease), (1, 2, 0, 0, "rc1"))
        self.assertEqual(semver.compare_semver("1.2.0-rc1", "1.2.0"), -1)
        self.mark_passed()

    def test_try_lock_fd_raises_on_unsupported_errno(self):
        """_try_lock_fd 於鎖競爭 (EAGAIN/EACCES) 回傳 False，於 ENOTSUP/ENOSYS/EBADF 往上拋出 OSError。"""
        import errno
        from unittest.mock import patch

        lock = InterProcessLock(self.lock_path)
        enotsup = getattr(errno, "ENOTSUP", getattr(errno, "EOPNOTSUPP", errno.ENOSYS))
        if sys.platform == "win32":
            with patch("os.lseek", side_effect=OSError(errno.EACCES, "locked")):
                self.assertFalse(lock._try_lock_fd(999))
            with patch("os.lseek", side_effect=OSError(enotsup, "not supported")):
                with self.assertRaises(OSError):
                    lock._try_lock_fd(999)
            with patch("os.lseek", side_effect=OSError(errno.ENOSYS, "function not implemented")):
                with self.assertRaises(OSError):
                    lock._try_lock_fd(999)
        else:
            with patch("fcntl.flock", side_effect=OSError(errno.EAGAIN, "resource temporarily unavailable")):
                self.assertFalse(lock._try_lock_fd(999))
            with patch("fcntl.flock", side_effect=OSError(enotsup, "operation not supported")):
                with self.assertRaises(OSError):
                    lock._try_lock_fd(999)
            with patch("fcntl.flock", side_effect=OSError(errno.ENOSYS, "function not implemented")):
                with self.assertRaises(OSError):
                    lock._try_lock_fd(999)
        self.mark_passed()

    def test_installed_module_roots_and_sys_path_priority(self):
        """Verify list_installed_module_roots and ensure_installed_modules_path ordering, hidden filtering, and performance."""
        from core.platform import (
            ensure_installed_modules_path,
            list_installed_module_roots,
            restore_sys_path,
        )

        root = self.temp_dir.name
        mods_dir = os.path.join(root, ".modules")
        for name in ("core", "ast", "server", "gdrive-support", ".staging_ast_123", ".old_core_456"):
            os.makedirs(os.path.join(mods_dir, name), exist_ok=True)
        with open(os.path.join(mods_dir, "README.txt"), "w", encoding="utf-8") as f:
            f.write("placeholder")

        roots = list_installed_module_roots(yscb_root=root, priority_module="gdrive-support")
        expected = [
            os.path.normpath(os.path.abspath(os.path.join(mods_dir, "gdrive-support"))),
            os.path.normpath(os.path.abspath(os.path.join(mods_dir, "core"))),
            os.path.normpath(os.path.abspath(os.path.join(mods_dir, "ast"))),
            os.path.normpath(os.path.abspath(os.path.join(mods_dir, "server"))),
        ]
        self.assertEqual(roots, expected)

        snap = list(sys.path)
        try:
            extra_dir = os.path.join(root, "custom_hook_root")
            os.makedirs(extra_dir, exist_ok=True)
            t0 = time.perf_counter()
            ensure_installed_modules_path(
                yscb_root=root,
                priority_module="gdrive-support",
                extra_paths=[extra_dir],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.assertLess(elapsed_ms, 50.0)
            self.assertEqual(sys.path[0], os.path.normpath(os.path.abspath(extra_dir)))
            self.assertEqual(sys.path[1], expected[0])
            self.assertEqual(sys.path[2], expected[1])
            for mod_p in expected[2:]:
                self.assertIn(mod_p, sys.path)
        finally:
            restore_sys_path(snap)
        self.mark_passed()

    def test_runtime_pythonpath_subprocess_and_test_source_activation(self):
        """Verify build_runtime_pythonpath source exclusion, init_subprocess_sys_path, and activate_test_module_source_path."""
        from core.platform import (
            activate_test_module_source_path,
            build_runtime_pythonpath,
            ensure_installed_modules_path,
            init_subprocess_sys_path,
            list_module_search_roots,
            restore_sys_path,
        )

        root = self.temp_dir.name
        mods_dir = os.path.join(root, ".modules")
        src_root = os.path.join(root, "source")
        os.makedirs(os.path.join(mods_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(mods_dir, "server"), exist_ok=True)
        os.makedirs(os.path.join(mods_dir, "ast"), exist_ok=True)
        src_ast = os.path.join(src_root, "ast")
        src_kdb = os.path.join(src_root, "knowledge-db")
        os.makedirs(src_ast, exist_ok=True)
        os.makedirs(src_kdb, exist_ok=True)

        search_roots = list_module_search_roots(yscb_root=root, prefer_source=True)
        self.assertEqual(
            search_roots,
            [
                os.path.normpath(os.path.abspath(os.path.join(mods_dir, "core"))),
                os.path.normpath(os.path.abspath(src_ast)),
                os.path.normpath(os.path.abspath(src_kdb)),
                os.path.normpath(os.path.abspath(os.path.join(mods_dir, "server"))),
            ],
        )

        dirty_existing = os.pathsep.join([src_ast, os.path.join(root, "external_lib")])
        py_path = build_runtime_pythonpath(
            yscb_root=root,
            priority_module="server",
            include_host_roots=True,
            existing_pythonpath=dirty_existing,
        )
        entries = py_path.split(os.pathsep)
        self.assertIn(os.path.normpath(os.path.abspath(os.path.join(mods_dir, "server"))), entries)
        self.assertIn(os.path.normpath(os.path.abspath(os.path.join(mods_dir, "core"))), entries)
        for item in entries:
            norm_slash = item.replace("\\", "/")
            self.assertNotIn("/source/", norm_slash)
            self.assertFalse(norm_slash.endswith("/source"))

        snap = list(sys.path)
        try:
            sys.path.insert(0, os.path.normpath(os.path.abspath(src_kdb)))
            pre_activate_snap = activate_test_module_source_path(
                src_real=src_ast,
                src_root=src_root,
                yscb_root=root,
            )
            norm_src_ast = os.path.normpath(os.path.abspath(src_ast))
            norm_src_kdb = os.path.normpath(os.path.abspath(src_kdb))
            self.assertEqual(sys.path[0], norm_src_ast)
            self.assertNotIn(norm_src_kdb, sys.path)

            # Mid-test call to ensure_installed_modules_path must keep pinned src_ast ahead of .modules/*
            ensure_installed_modules_path(yscb_root=root, priority_module="core")
            self.assertEqual(sys.path[0], norm_src_ast)

            restore_sys_path(pre_activate_snap)
            fake_parent_entry = os.path.join(root, "parent_worker_only")
            init_subprocess_sys_path([fake_parent_entry])
            self.assertEqual(sys.path[0], fake_parent_entry)
        finally:
            restore_sys_path(snap)
        self.mark_passed()

    def test_posix_zombie_detection_without_procfs(self):
        """驗證無 /proc 時透過 ps stat 識別殭屍進程為非存活。"""
        from unittest.mock import MagicMock, patch
        import core.platform.process as proc_mod

        if sys.platform != "win32":
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Z+\n"
            with patch("core.platform.process.os.path.exists", return_value=False), \
                 patch("core.platform.process.os.kill", return_value=None), \
                 patch("core.platform.process.subprocess.run", return_value=mock_res):
                self.assertFalse(proc_mod.is_process_alive(99999))
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
