"""
YSCBTestCase base test fixture for YS-Codebase test suites.
Provides automated full-fidelity virtual sandbox lifecycle, environment rollback, and assertion helpers.
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
from dev.testing.requirement import Requirement
from dev.testing.sandbox import SandboxContext, SandboxProvisioner

class SecurityError(RuntimeError):
    """Raised when tests are executed in an insecure or forbidden host environment."""
    pass

class YSCBTestCase(unittest.TestCase):
    """
    YS-Codebase Core Test Fixture (Full-Fidelity Virtual Sandbox on cache://dev/sandbox/<uuid>).
    Supports shared class-level sandbox by default and per-method isolated sandbox via @require(Requirement.ISOLATED_SANDBOX).
    """
    ctx: SandboxContext
    sandbox_id: str
    sandbox_uri: str
    sandbox_dir: str
    sandbox_host_dir: str
    sandbox_project_dir: str
    sandbox_provider_dir: str
    
    _shared_sandbox_ctx: Optional[SandboxContext] = None
    _is_isolated_sandbox: bool = False
    _test_passed: bool
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    @classmethod
    def cleanup_shared_sandbox(cls) -> None:
        """Session-level teardown: cleanup shared sandbox when test suite finishes."""
        if YSCBTestCase._shared_sandbox_ctx is not None:
            keep_all = os.environ.get("YSCB_TEST_KEEP_SANDBOX", "0") == "1"
            if not keep_all:
                SandboxProvisioner.cleanup_sandbox(YSCBTestCase._shared_sandbox_ctx.sandbox_dir, force=True)
            YSCBTestCase._shared_sandbox_ctx = None

    @classmethod
    def tearDownClass(cls) -> None:
        """Class-level teardown: defensive fallback (no-op in session-level mode)."""
        pass

    def setUp(self) -> None:
        """Test setup: create or reuse virtual environment and backup environment."""
        # Gate 3: Intercept insecure host direct execution
        if os.environ.get("YSCB_TEST_SANDBOX") != "1":
            raise SecurityError(
                "[dev:test] Security Guard Blocked: Running tests directly on the host workspace is strictly forbidden to prevent environment contamination. "
                "Please use 'python yscb.py dev test <module>' or execute within an authenticated YSCB virtual sandbox."
            )

        self._test_passed = False
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)

        # Determine if current test method requires ISOLATED_SANDBOX
        method_name = getattr(self, "_testMethodName", "")
        method = getattr(self, method_name, None)
        req = getattr(method, "__requirement__", None) if method else None
        if req is None:
            req = getattr(self.__class__, "__requirement__", None)

        req_val = req.value if hasattr(req, "value") else (int(req) if req is not None else 0)
        if req and bool(req_val & Requirement.ISOLATED_SANDBOX.value):
            self._is_isolated_sandbox = True
            self.ctx = SandboxProvisioner.create_sandbox()
        else:
            self._is_isolated_sandbox = False
            if YSCBTestCase._shared_sandbox_ctx is None:
                if os.environ.get("YSCB_TEST_SANDBOX") == "1":
                    curr_cwd = os.getcwd()
                    sb_dir = os.path.dirname(curr_cwd) if os.path.basename(curr_cwd) == "host_env" else curr_cwd
                    YSCBTestCase._shared_sandbox_ctx = SandboxContext(sb_dir)
                else:
                    YSCBTestCase._shared_sandbox_ctx = SandboxProvisioner.create_sandbox()
            self.ctx = YSCBTestCase._shared_sandbox_ctx

        self.sandbox_dir = self.ctx.sandbox_dir
        self.sandbox_host_dir = self.ctx.host_dir
        self.sandbox_project_dir = self.ctx.project_dir
        self.sandbox_provider_dir = self.ctx.provider_dir
        self.sandbox_id = os.path.basename(self.sandbox_dir)
        self.sandbox_uri = f"cache://dev/sandbox/{self.sandbox_id}"

    def tearDown(self) -> None:
        """Test teardown: restore environment and cleanup isolated sandbox according to policy."""
        sys.path[:] = self._orig_sys_path
        os.environ.clear()
        os.environ.update(self._orig_env)
        
        keep_all = os.environ.get("YSCB_TEST_KEEP_SANDBOX", "0") == "1"
        if self._is_isolated_sandbox:
            if self._test_passed and not keep_all:
                SandboxProvisioner.cleanup_sandbox(self.sandbox_dir, force=True)
            else:
                if not self._test_passed:
                    print(f"\n[Test Failed] Dedicated virtual sandbox preserved at: {self.sandbox_dir}")
                elif keep_all:
                    print(f"\n[Sandbox Kept] Dedicated virtual sandbox preserved at: {self.sandbox_dir}")
        else:
            if not self._test_passed:
                print(f"\n[Test Failed] Shared virtual sandbox preserved at: {self.sandbox_dir}")
            elif keep_all:
                print(f"\n[Sandbox Kept] Shared virtual sandbox preserved at: {self.sandbox_dir}")

    def mark_passed(self) -> None:
        """Mark that current test method executed to completion successfully."""
        self._test_passed = True

    def create_mock_package(
        self,
        name: str,
        version: str = "1.0.0",
        deps: Optional[Dict[str, str]] = None,
        description: str = "Mock Package for Testing"
    ) -> str:
        """Helper to dynamically generate a mock package in sandbox mock_provider."""
        return self.ctx.create_mock_package(name, version, deps, description)

    def create_mock_source_module(
        self,
        name: str = "mock_source_pkg",
        version: str = "1.0.0.0",
        deps: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Creates a valid mock source module in the sandbox's source/<name> directory
        with standard manifest.json and boilerplate entry points.
        Returns the resolved source directory path.
        """
        src_root = uri.resolve("module.source://")
        src_dir = os.path.join(src_root, name)
        os.makedirs(src_dir, exist_ok=True)
        if deps is None:
            deps = {"core": ">=1.0.0"} if name != "core" else {}

        manifest = {
            "name": name,
            "version": version,
            "description": f"Mock Source Module {name}",
            "dependencies": deps,
            "entry": "scripts/cli.py"
        }
        with open(os.path.join(src_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

            
        scripts_dir = os.path.join(src_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        cli_content = files.get("scripts/cli.py") if files and "scripts/cli.py" in files else (
            "def main():\n    pass\n"
        )
        with open(os.path.join(scripts_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write(cli_content)

        tests_dir = os.path.join(src_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        with open(os.path.join(tests_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write('"""Mock test package."""\n')
        with open(os.path.join(tests_dir, "test_dummy.py"), "w", encoding="utf-8") as f:
            f.write("from dev.testing.case import YSCBTestCase\nclass DummyMockTest(YSCBTestCase):\n    def test_mock_pass(self): pass\n")

        if files:
            for rel_p, content in files.items():
                if rel_p in ("manifest.json", "scripts/cli.py", "tests/__init__.py", "tests/test_dummy.py"):
                    continue
                full_p = os.path.join(src_dir, rel_p)
                os.makedirs(os.path.dirname(full_p), exist_ok=True)
                with open(full_p, "w", encoding="utf-8") as f:
                    f.write(content)
                    
        return src_dir

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
        """Execute yscb host CLI in subprocess with isolated sandbox working directory (default: sandbox_host_dir)."""
        work_dir = cwd or self.sandbox_host_dir
        
        # Prefer yscb.py inside the sandbox host_dir, fallback to parent
        sandbox_yscb = os.path.join(self.sandbox_host_dir, "yscb.py")
        if os.path.isfile(sandbox_yscb):
            yscb_script = sandbox_yscb
        else:
            yscb_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "yscb.py"))
            if not os.path.isfile(yscb_script):
                yscb_script = "yscb.py"

        cmd = [sys.executable, yscb_script] + args
        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        if env:
            p_env.update(env)
        res = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=p_env
        )
        return res.returncode, res.stdout, res.stderr
