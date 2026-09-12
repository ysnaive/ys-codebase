"""
Unit tests for Core Platform SDK (core.platform).
Covers process primitives (spawn_detached, is_process_alive, kill_process_tree)
and cross-platform inter-process file locks (InterProcessLock).
"""

import os
import sys
import tempfile
import time
import unittest

from dev.testing.case import YSCBTestCase
from core.platform import (
    spawn_detached,
    is_process_alive,
    kill_process_tree,
    InterProcessLock,
    LockAcquisitionError,
)


class TestCorePlatform(YSCBTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = os.path.join(self.temp_dir.name, "test.lock")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spawn_and_liveness_and_kill(self):
        """FT-01 & FT-02: spawn_detached starts background process, is_process_alive detects it, kill_process_tree terminates it."""
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        pid = spawn_detached(cmd)
        self.assertGreater(pid, 0)
        self.assertTrue(is_process_alive(pid))

        # Kill the spawned process tree
        killed = kill_process_tree(pid, timeout_sec=2.0)
        self.assertTrue(killed)
        self.assertFalse(is_process_alive(pid))
        self.mark_passed()

    def test_is_process_alive_invalid(self):
        """FT-01: Invalid or non-existent PID returns False."""
        self.assertFalse(is_process_alive(0))
        self.assertFalse(is_process_alive(-1))
        self.assertFalse(is_process_alive(99999999))
        self.mark_passed()

    def test_inter_process_lock_mutual_exclusion(self):
        """FT-03: InterProcessLock prevents concurrent acquisition on the same file."""
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
        """FT-03: InterProcessLock context manager auto acquires and releases."""
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
        """FT-03: ensure_private_venv injects site-packages and resolves host_venv.pth."""
        from core.platform import ensure_private_venv
        import platform

        tag = f"py{sys.version_info.major}{sys.version_info.minor}"
        sys_name = platform.system()
        sub = (
            os.path.join(".venv", tag, "Lib", "site-packages")
            if sys_name == "Windows"
            else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
        )
        fake_site = os.path.join(self.temp_dir.name, sub)
        os.makedirs(fake_site, exist_ok=True)

        extra_pth_target = os.path.join(self.temp_dir.name, "extra_lib")
        os.makedirs(extra_pth_target, exist_ok=True)
        pth_file = os.path.join(fake_site, "host_venv.pth")
        with open(pth_file, "w", encoding="utf-8") as f:
            f.write(extra_pth_target + "\n")

        ensure_private_venv(self.temp_dir.name)
        self.assertIn(fake_site, sys.path)
        self.assertIn(extra_pth_target, sys.path)

        # Cleanup sys.path to avoid pollution
        if fake_site in sys.path:
            sys.path.remove(fake_site)
        if extra_pth_target in sys.path:
            sys.path.remove(extra_pth_target)
        self.mark_passed()

    def test_set_process_title(self):
        """FT-04: set_process_title runs cross-platform without raising exceptions."""
        from core.platform import set_process_title
        # Should execute cleanly without raising any exceptions
        result = set_process_title("yscb test runner")
        self.assertIsInstance(result, bool)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
