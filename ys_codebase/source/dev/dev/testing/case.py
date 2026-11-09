"""
YSCBTestCase base test fixture for YS-Codebase test suites.
Provides automated full-fidelity virtual sandbox lifecycle, environment rollback, and assertion helpers.
"""
import os
import sys
import json
import time
import unittest
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple, Iterator
from core import uri, vfs
from core.context import get_env, get_runtime_context, get_virtual_cwd, invalidate_cell_state
from core.log import log
from dev.testing.requirement import Requirement
from dev.testing.sandbox import SandboxContext, SandboxProvisioner


def _is_keep_sandbox_enabled() -> bool:
    return bool(
        get_runtime_context().get_module_state("dev.testing.keep_sandbox")
        or get_env("YSCB_TEST_KEEP_SANDBOX", "0") == "1"
    )


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

    _is_isolated_sandbox: bool = False
    _test_passed: bool
    _has_exception: bool = False
    _execution_status: str = "UNKNOWN"
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    @staticmethod
    def _get_shared_sandbox_ctx() -> Optional[SandboxContext]:
        return get_runtime_context().get_module_state("dev.testing.shared_sandbox_ctx")

    @staticmethod
    def _set_shared_sandbox_ctx(ctx: Optional[SandboxContext]) -> None:
        get_runtime_context().set_module_state("dev.testing.shared_sandbox_ctx", ctx)

    @property
    def execution_status(self) -> str:
        """Current test execution status: 'PASSED', 'FAILED', or 'UNKNOWN'."""
        return self._execution_status

    @classmethod
    def cleanup_shared_sandbox(cls) -> None:
        """Session-level teardown: cleanup shared sandbox when test suite finishes."""
        ctx = cls._get_shared_sandbox_ctx()
        if ctx is not None:
            cls._set_shared_sandbox_ctx(None)
            is_harness_managed = os.environ.get("YSCB_TEST_SANDBOX") == "1"
            keep_all = _is_keep_sandbox_enabled()
            if not keep_all and not is_harness_managed:
                SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True)

    def _callTestMethod(self, method: Any) -> Any:
        """Wrap test method execution to reliably capture unhandled exceptions and per-test output slice."""
        active_cap = get_runtime_context().get_module_state("dev.testing.active_capturer")
        start_offsets = active_cap.snapshot_offsets() if active_cap is not None else None
        try:
            return super()._callTestMethod(method)
        except BaseException:
            self._has_exception = True
            self._execution_status = "FAILED"
            raise
        finally:
            if active_cap is not None and start_offsets is not None:
                self._yscb_captured_output = active_cap.get_slice(start_offsets)

    def _restore_saved_env(self) -> None:
        from core.platform import restore_process_env_and_cwd, restore_sys_path

        restore_sys_path(self._orig_sys_path)
        restore_process_env_and_cwd(self._orig_env, getattr(self, "_orig_cwd", None))
        uri.set_host_dir(getattr(self, "_orig_uri_host", None))
        uri.set_yscb_root(getattr(self, "_orig_uri_yscb", None))
        uri.set_module_context(getattr(self, "_orig_uri_mod", None))
        invalidate_cell_state()

    def setUp(self) -> None:
        """Test setup: create or reuse virtual environment and backup environment."""
        if os.environ.get("YSCB_TEST_SANDBOX") != "1":
            raise SecurityError(
                "[dev:test] Security Guard Blocked: Running tests directly on the host workspace is strictly forbidden to prevent environment contamination. "
                "Please use 'python yscb.py dev test <module>' or execute within an authenticated YSCB virtual sandbox."
            )

        self._test_passed = False
        self._has_exception = False
        self._execution_status = "UNKNOWN"
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)
        self._orig_cwd = str(get_virtual_cwd())
        self._orig_uri_host = uri.get_host_dir()
        self._orig_uri_yscb = uri.get_yscb_root()
        self._orig_uri_mod = uri.get_module_context()

        method_name = getattr(self, "_testMethodName", "")
        method = getattr(self, method_name, None)
        method_req = getattr(method, "__requirement__", None) if method else None
        class_req = getattr(self.__class__, "__requirement__", None)

        method_val = (method_req.value if hasattr(method_req, "value") else int(method_req)) if method_req is not None else 0
        class_val = (class_req.value if hasattr(class_req, "value") else int(class_req)) if class_req is not None else 0
        effective_val = method_val if method_req is not None else class_val

        created_isolated_ctx: Optional[SandboxContext] = None
        try:
            if bool((method_val | class_val) & Requirement.NETWORK.value):
                from dev.testing import requirement as _req_mod
                if not _req_mod.is_network_available():
                    raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")

            if bool(effective_val & Requirement.ISOLATED_SANDBOX.value):
                self._is_isolated_sandbox = True
                created_isolated_ctx = SandboxProvisioner.create_sandbox()
                self.ctx = created_isolated_ctx
            else:
                self._is_isolated_sandbox = False
                env_sb = os.environ.get("YSCB_SANDBOX_DIR")
                env_sb_valid = bool(env_sb and os.path.isdir(env_sb) and os.path.isdir(os.path.join(env_sb, "host_env")))
                shared_ctx = YSCBTestCase._get_shared_sandbox_ctx()
                if (
                    shared_ctx is None
                    or not os.path.isdir(shared_ctx.host_dir)
                    or (
                        env_sb_valid
                        and env_sb is not None
                        and os.path.normcase(os.path.realpath(os.path.abspath(getattr(shared_ctx, "root_dir", shared_ctx.sandbox_dir))))
                        != os.path.normcase(os.path.realpath(os.path.abspath(env_sb)))
                    )
                ):
                    sb_dir = None
                    if env_sb_valid and env_sb:
                        sb_dir = os.path.abspath(env_sb)
                    else:
                        curr = os.path.abspath(str(get_virtual_cwd()))
                        while curr and curr != os.path.dirname(curr):
                            if (
                                (os.path.basename(curr).startswith("sandbox_") and os.path.isdir(os.path.join(curr, "host_env")))
                                or (os.path.isdir(os.path.join(curr, "host_env")) and os.path.isdir(os.path.join(curr, "mock_provider")))
                            ):
                                sb_dir = curr
                                break
                            curr = os.path.dirname(curr)
                    if not sb_dir or not os.path.isdir(os.path.join(sb_dir, "host_env")):
                        raise SecurityError(
                            f"[dev:test] Security Guard Blocked: Unable to resolve an authentic virtual sandbox directory from '{get_virtual_cwd()}'. "
                            "Running tests directly on the host workspace is strictly forbidden to prevent environment contamination."
                        )
                    shared_ctx = SandboxContext(sb_dir)
                    YSCBTestCase._set_shared_sandbox_ctx(shared_ctx)
                self.ctx = shared_ctx

            self.sandbox_dir = self.ctx.sandbox_dir
            self.sandbox_host_dir = self.ctx.host_dir
            self.sandbox_project_dir = self.ctx.project_dir
            self.sandbox_provider_dir = self.ctx.provider_dir
            self.sandbox_id = os.path.basename(self.sandbox_dir)
            self.sandbox_uri = f"cache://dev/sandbox/{self.sandbox_id}"
        except BaseException:
            self._restore_saved_env()
            if created_isolated_ctx is not None:
                SandboxProvisioner.cleanup_sandbox(created_isolated_ctx.sandbox_dir, force=True)
            raise

    def tearDown(self) -> None:
        """Test teardown: restore environment and classify execution status (Passed / Failed / Unknown)."""
        self._restore_saved_env()

        if self._has_exception:
            self._execution_status = "FAILED"
        elif self._test_passed:
            self._execution_status = "PASSED"
        else:
            self._execution_status = "UNKNOWN"

        keep_all = _is_keep_sandbox_enabled()
        if self._is_isolated_sandbox:
            if self._execution_status in ("PASSED", "UNKNOWN") and not keep_all:
                SandboxProvisioner.cleanup_sandbox(self.sandbox_dir, force=True)
            elif self._execution_status == "FAILED":
                log(f"\n[Test Failed] Dedicated virtual sandbox preserved at: {self.sandbox_dir}")
            elif keep_all:
                log(f"\n[Sandbox Kept] Dedicated virtual sandbox preserved at: {self.sandbox_dir}")
        else:
            if self._execution_status == "FAILED":
                log(f"\n[Test Failed] Shared virtual sandbox preserved at: {self.sandbox_dir}")
            elif keep_all and self._execution_status != "UNKNOWN":
                log(f"\n[Sandbox Kept] Shared virtual sandbox preserved at: {self.sandbox_dir}")

    def mark_passed(self) -> None:
        """Mark that current test method executed to completion successfully."""
        self._test_passed = True
        self._execution_status = "PASSED"

    def create_mock_package(
        self,
        name: str,
        version: str = "1.0.0.0",
        deps: Optional[Dict[str, str]] = None,
        description: str = "Mock Package for Testing",
    ) -> str:
        """Helper to dynamically generate a mock package in sandbox mock_provider."""
        return self.ctx.create_mock_package(name, version, deps, description)

    def create_mock_source_module(
        self,
        name: str = "mock_source_pkg",
        version: str = "1.0.0.0",
        deps: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Creates a valid mock source module in the sandbox's source/<name> directory
        with standard manifest.json and boilerplate entry points.
        Returns the resolved source directory path.
        """
        src_dir = os.path.join(uri.resolve("module.source://"), name)
        if deps is None:
            deps = {"core": ">=1.0.0"} if name != "core" else {}

        default_files: Dict[str, str] = {
            "manifest.json": json.dumps(
                {
                    "name": name,
                    "version": version,
                    "description": f"Mock Source Module {name}",
                    "dependencies": deps,
                    "entry": "scripts/cli.py",
                },
                indent=2,
            ),
            "scripts/cli.py": (
                f"from typing import Any\nfrom core.guard import guard_dispatch\nfrom core.commands import CmdBags\n\n"
                f"def hello(cmd_bags: Any) -> int:\n    guard_dispatch('{name}')\n    return 0\n"
            ),
            "contributes/_manifest.md": f"# {name} Contributes Manifest\n\n## 1. Commands\n- hello\n",
            "contributes/core.json": json.dumps(
                {
                    "commands": {
                        "description": f"Mock Source Module {name}",
                        "cmd": {
                            "hello": {
                                "description": f"Say hello from {name}",
                                "tier": "safe",
                                "server_compatible": True,
                            }
                        },
                    }
                },
                indent=2,
            ),
            "tests/__init__.py": '"""Mock test package."""\n',
            "tests/test_dummy.py": (
                "from dev.testing.case import YSCBTestCase\n"
                "class DummyMockTest(YSCBTestCase):\n"
                "    def test_mock_pass(self):\n"
                "        self.mark_passed()\n"
            ),
        }
        if files:
            default_files.update(files)

        for rel_p, content in default_files.items():
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
        self.assertTrue(vfs.exists(path_or_uri), msg or f"File not found: {path_or_uri}")

    def assertJsonEquals(self, expected: Dict[str, Any], path_or_uri: str, msg: str = "") -> None:
        """Read JSON file from path/URI and assert contents equal expected dict."""
        self.assertFileExists(path_or_uri, msg)
        try:
            data = vfs.read_json(path_or_uri)
        except Exception:
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

    def run_cli(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
    ) -> Tuple[int, str, str]:
        """Execute yscb host CLI in subprocess with isolated sandbox working directory and process-tree timeout protection."""
        work_dir = cwd or self.sandbox_host_dir

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
        from dev.testing.runner import run_subprocess_with_tree_timeout

        return run_subprocess_with_tree_timeout(
            cmd,
            timeout_sec=timeout,
            cwd=work_dir,
            env=p_env,
        )
