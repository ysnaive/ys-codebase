"""
YSCBTestCase base test fixture for YS-Codebase test suites.
Provides automated sandbox lifecycle, environment rollback, and assertion helpers.
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import unittest
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple, Iterator
from core import uri

class YSCBTestCase(unittest.TestCase):
    """
    YS-Codebase Core Test Fixture (Inspired by uitk.net UIToolkitTestFixture).
    """
    sandbox_dir: str
    _test_passed: bool
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    def setUp(self) -> None:
        """Test setup: create isolated sandbox and backup environment."""
        self._test_passed = False
        self.sandbox_dir = tempfile.mkdtemp(prefix="yscb_test_")
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)

    def tearDown(self) -> None:
        """Test teardown: restore environment and enforce Preserve-on-Failure policy."""
        sys.path[:] = self._orig_sys_path
        os.environ.clear()
        os.environ.update(self._orig_env)
        
        keep_all = os.environ.get("YSCB_TEST_KEEP_SANDBOX", "0") == "1"
        if self._test_passed and not keep_all:
            if os.path.exists(self.sandbox_dir):
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
        else:
            if not self._test_passed:
                print(f"\n[Test Failed] Sandbox preserved at: {self.sandbox_dir}")
            elif keep_all:
                print(f"\n[Sandbox Kept] Sandbox preserved at: {self.sandbox_dir}")

    def mark_passed(self) -> None:
        """Mark that current test method executed to completion successfully."""
        self._test_passed = True

    def assertSuccess(self, returncode: int, msg: str = "") -> None:
        """Assert command exit code is 0."""
        self.assertEqual(returncode, 0, msg or f"Expected exit code 0, got {returncode}")

    def assertFailed(self, returncode: int, msg: str = "") -> None:
        """Assert command exit code is non-zero."""
        self.assertNotEqual(returncode, 0, msg or "Expected non-zero exit code, got 0")

    def assertInOutput(self, expected: str, actual: str, msg: str = "") -> None:
        """Assert terminal output contains expected substring."""
        self.assertIn(expected, actual, msg or f"Expected '{expected}' in output: {actual}")

    def assertFileExists(self, path_or_uri: str, msg: str = "") -> None:
        """Assert physical file or semantic URI exists."""
        real_path = uri.resolve(path_or_uri) if ("://" in str(path_or_uri)) else path_or_uri
        self.assertTrue(os.path.exists(real_path), msg or f"File not found: {path_or_uri}")

    def assertJsonEquals(self, expected: Dict[str, Any], path_or_uri: str, msg: str = "") -> None:
        """Read JSON file from path/URI and assert contents equal expected dict."""
        self.assertFileExists(path_or_uri, msg)
        real_path = uri.resolve(path_or_uri) if ("://" in str(path_or_uri)) else path_or_uri
        with open(real_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, expected, msg or f"JSON mismatch at {path_or_uri}")

    @contextmanager
    def assertExecutionTime(self, max_seconds: float) -> Iterator[None]:
        """Assert code block execution duration does not exceed max_seconds."""
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.assertLessEqual(elapsed, max_seconds, f"Execution took {elapsed:.4f}s > {max_seconds:.4f}s")

    def run_cli(self, args: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        """Execute yscb host CLI in subprocess with isolated sandbox working directory."""
        work_dir = cwd or self.sandbox_dir
        curr = os.path.abspath(os.getcwd())
        candidates = [
            os.path.join(curr, "yscb.py"),
            os.path.join(curr, "..", "yscb.py"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "yscb.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "yscb.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "yscb.py"))
        ]
        yscb_script = None
        for c in candidates:
            if os.path.isfile(c):
                yscb_script = c
                break
        if not yscb_script:
            yscb_script = "yscb.py"

        cmd = [sys.executable, yscb_script] + args
        p_env = dict(os.environ)
        if env:
            p_env.update(env)
        res = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, env=p_env)
        return res.returncode, res.stdout, res.stderr
