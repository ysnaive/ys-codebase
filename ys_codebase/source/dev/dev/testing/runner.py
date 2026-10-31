"""
Test discovery, execution engine and ASCII report formatter for YS-Codebase.
"""
import os
import sys
import unittest
from io import StringIO
from typing import List, Dict, Any, Optional, Tuple
from core import uri, vfs
from dev.checker import discover_source_modules
from dev.testing.contract import make_contract_suite
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement


def filter_suite(
    suite: unittest.TestSuite,
    pattern: Optional[str] = None,
    test_type: Optional[str] = None,
    target: Optional[str] = None,
) -> unittest.TestSuite:
    """
    Recursively filter test cases within a TestSuite tree by pattern, target selector, and 4-tier taxonomy.
    """
    filtered = unittest.TestSuite()

    resolved_types = set()
    if test_type:
        tt = test_type.lower().replace("-", "_")
        if tt in ("logic", "logical"):
            resolved_types = {"logic"}
        elif tt == "env":
            resolved_types = {"env"}
        elif tt == "network":
            resolved_types = {"network"}
        elif tt == "workflow":
            resolved_types = {"workflow"}
        elif tt == "perf":
            resolved_types = {"perf"}
        elif tt in ("all", "all_types"):
            resolved_types = {"logic", "env", "workflow", "perf", "network"}

    if not resolved_types:
        resolved_types = {"logic", "env", "network"}

    def _matches(test_case: unittest.TestCase) -> bool:
        method_name = getattr(test_case, "_testMethodName", "")
        class_name = test_case.__class__.__name__
        module_name = test_case.__class__.__module__
        full_id = f"{module_name}.{class_name}.{method_name}"

        if target:
            t_clean = target.split(":", 1)[1] if ":" in target else target
            t_clean_lower = t_clean.lower()
            if (
                t_clean_lower not in full_id.lower()
                and t_clean_lower not in method_name.lower()
                and t_clean_lower not in class_name.lower()
            ):
                return False
            return True

        if pattern and (pattern.lower() not in method_name.lower() and pattern.lower() not in class_name.lower()):
            return False

        if class_name == "_FailedTest":
            return True

        category = get_test_category(test_case)
        return category in resolved_types

    def _recurse(node: Any) -> None:
        if isinstance(node, unittest.TestSuite):
            for sub in node:
                _recurse(sub)
        elif isinstance(node, unittest.TestCase):
            if _matches(node):
                filtered.addTest(node)

    _recurse(suite)
    return filtered


class TestDiscovery:
    @staticmethod
    def discover_modules(target: Optional[str] = None) -> List[str]:
        return discover_source_modules(target=target, require_manifest=True)

    @staticmethod
    def build_suite_for_module(
        module_name: str,
        test_type: Optional[str] = None,
        pattern: Optional[str] = None,
        target: Optional[str] = None,
        contract_only: bool = False,
    ) -> Tuple[unittest.TestSuite, int, int]:
        """
        Builds a two-phase test suite for module:
        Phase 1: Universal Auto-Contract Suite
        Phase 2: Custom tests in source/<mod>/tests/ (if present and not contract_only)
        Returns (suite, contract_count, custom_count)
        """
        master_suite = unittest.TestSuite()

        contract_suite = make_contract_suite(module_name)
        if pattern or test_type or target:
            contract_suite = filter_suite(contract_suite, pattern=pattern, test_type=test_type, target=target)
        contract_count = contract_suite.countTestCases()
        master_suite.addTests(contract_suite)

        custom_count = 0
        if not contract_only:
            src_real = uri.resolve(f"module.source://{module_name}")
            tests_dir = os.path.join(src_real, "tests")
            if os.path.isdir(tests_dir):
                for mod_k in list(sys.modules.keys()):
                    if mod_k == "tests" or mod_k.startswith("tests.") or mod_k == module_name or mod_k.startswith(f"{module_name}."):
                        del sys.modules[mod_k]

                try:
                    src_root = uri.resolve("module.source://")
                    sys.path[:] = [p for p in sys.path if not (p.startswith(src_root) and p != src_real)]
                except Exception:
                    pass

                if src_real in sys.path:
                    sys.path.remove(src_real)
                sys.path.insert(0, src_real)

                init_py = os.path.join(tests_dir, "__init__.py")
                if not os.path.isfile(init_py):
                    try:
                        with open(init_py, "w", encoding="utf-8") as f:
                            f.write('"""Test package auto-infill."""\n')
                    except OSError:
                        pass

                loader = unittest.TestLoader()
                discovered = loader.discover(start_dir=tests_dir, pattern="test_*.py", top_level_dir=src_real)

                def _validate_test_types(node: Any) -> None:
                    if isinstance(node, unittest.TestSuite):
                        for sub in node:
                            _validate_test_types(sub)
                    elif isinstance(node, unittest.TestCase):
                        if node.__class__.__name__ == "_FailedTest":
                            return
                        mro_names = [b.__name__ for b in node.__class__.__mro__]
                        if "YSCBTestCase" not in mro_names:
                            raise TypeError(
                                f"[dev:test] Security Guard Blocked: Test class '{node.__class__.__name__}' directly subclasses 'unittest.TestCase'. "
                                f"All YSCB tests MUST inherit from 'dev.testing.case.YSCBTestCase' to prevent sandbox leakage."
                            )

                _validate_test_types(discovered)
                discovered = filter_suite(discovered, pattern=pattern, test_type=test_type, target=target)
                custom_count = discovered.countTestCases()
                master_suite.addTests(discovered)

        return master_suite, contract_count, custom_count


def get_test_category(test_case: unittest.TestCase) -> str:
    """Extract semantic category string ('logic', 'env', 'workflow', 'perf', 'network') from TestCase."""
    method_name = getattr(test_case, "_testMethodName", "")
    method = getattr(test_case, method_name, None) if method_name else None
    req = getattr(method, "__requirement__", None) if method else None
    if req is None:
        req = getattr(test_case.__class__, "__requirement__", None)
    if req is None:
        req = getattr(test_case, "__requirement__", None)

    if req is not None:
        req_val = req.value if hasattr(req, "value") else int(req)
        if bool(req_val & Requirement.WORKFLOW.value):
            return "workflow"
        if bool(req_val & Requirement.PERF.value):
            return "perf"
        if bool(req_val & Requirement.ENV.value):
            return "env"
        if bool(req_val & Requirement.NETWORK.value):
            return "network"
        if bool(req_val & Requirement.LOGIC.value):
            return "logic"
    return "logic"


class OutputCapturer:
    """Context manager for buffering stdout and stderr during test execution."""
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._stdout_buf = StringIO()
        self._stderr_buf = StringIO()
        self._orig_stdout: Optional[Any] = None
        self._orig_stderr: Optional[Any] = None

    def __enter__(self) -> "OutputCapturer":
        if self.enabled:
            self._orig_stdout = sys.stdout
            self._orig_stderr = sys.stderr
            sys.stdout = self._stdout_buf
            sys.stderr = self._stderr_buf
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.enabled:
            if self._orig_stdout is not None:
                sys.stdout = self._orig_stdout
            if self._orig_stderr is not None:
                sys.stderr = self._orig_stderr

    def get_output(self) -> str:
        return (self._stdout_buf.getvalue() + self._stderr_buf.getvalue()).strip()


def _format_failure_entries(failures_list: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for item in failures_list:
        m_tag = f"[{item.get('module', 'unknown')}]"
        t_type = item.get("type", "FAIL")
        t_name = item.get("test", "unknown")
        t_msg = item.get("message", "")
        t_loc = item.get("location", "")
        t_re_run = item.get("rerun", "")
        captured = item.get("captured_output", "")

        lines.append(f"  [!] {m_tag:<10} {t_type:<8} {t_name}")
        if t_msg:
            lines.append(f"      |-- Message:  {t_msg}")
        if t_loc:
            lines.append(f"      |-- Location: {t_loc}")
        if captured:
            cap_lines = captured.splitlines()
            if len(cap_lines) > 20:
                cap_snippet = "\n          ".join(cap_lines[:10] + ["... [truncated] ..."] + cap_lines[-5:])
            else:
                cap_snippet = "\n          ".join(cap_lines)
            lines.append(f"      |-- Output:\n          {cap_snippet}")
        if t_re_run:
            lines.append(f"      \\-- Quick Re-run: {t_re_run}")
        else:
            lines.append(f"      \\-- Quick Re-run: python yscb.py dev test --target={item.get('module')}:{t_name}")
    return lines


class ASCIIReportFormatter:
    @staticmethod
    def format_summary(report_data: Dict[str, Any], warnings_count: int = 0) -> str:
        lines = [
            "=" * 70,
            "YS-Codebase Test Execution Diagnostic Report",
            "=" * 70,
        ]

        filter_mode = report_data.get("filter_mode", "Default (LOGIC + ENV)")
        target_scope = report_data.get("target_scope", "All")
        no_build = report_data.get("no_build", False)
        build_str = "No-build (Fast)" if no_build else "Hermetic Build"
        lines.append(f"[*] Mode: {filter_mode} | Target: {target_scope} | Build: {build_str}")
        if warnings_count > 0:
            lines.append(f"[*] Notices: {warnings_count} sandbox warning(s) captured (suppressed, run with --verbose to inspect)")
        lines.append("-" * 70)

        for mod_info in report_data.get("modules", []):
            mod_name = mod_info["name"]
            mod_dur = mod_info.get("duration", 0.0)
            status_str = "[PASS]" if mod_info["passed"] else "[FAIL]"
            header_left = f"[*] Module: {mod_name} ({mod_dur:.2f}s)"
            lines.append(f"{header_left:<50} {status_str:>19}")
            lines.append(f"    |-- [Contract] Auto-Contract Suite ... ({mod_info['contract_passed']}/{mod_info['contract_total']})")

            if mod_info["custom_total"] > 0:
                tax_parts = []
                if mod_info.get("logic_passed", 0) > 0:
                    tax_parts.append(f"Logic: {mod_info['logic_passed']}")
                if mod_info.get("env_passed", 0) > 0:
                    tax_parts.append(f"Env: {mod_info['env_passed']}")
                if mod_info.get("workflow_passed", 0) > 0:
                    tax_parts.append(f"Workflow: {mod_info['workflow_passed']}")
                if mod_info.get("perf_passed", 0) > 0:
                    tax_parts.append(f"Perf: {mod_info['perf_passed']}")
                if mod_info.get("unknown", 0) > 0:
                    tax_parts.append(f"Unknown: {mod_info['unknown']}")
                tax_str = f" [{', '.join(tax_parts)}]" if tax_parts else ""
                lines.append(f"    \\-- [Custom]   Custom Tests ........... ({mod_info['custom_passed']}/{mod_info['custom_total']}){tax_str}")
            else:
                lines.append("    \\-- [Custom]   Custom Tests ........... (No custom tests)")

            if mod_info.get("errors"):
                for err in mod_info["errors"]:
                    lines.append(f"        [!] ERROR: {err}")

        failures_list = report_data.get("failures_list", [])
        if failures_list:
            lines.append("-" * 70)
            lines.append("FAILED / ERROR TEST CASES LIST:")
            lines.extend(_format_failure_entries(failures_list))

        lines.append("-" * 70)
        total = report_data.get("total", 0)
        passed = report_data.get("passed", 0)
        failed = report_data.get("failed", 0)
        unknown = report_data.get("unknown", 0)
        skipped = report_data.get("skipped", 0)
        duration = report_data.get("duration", 0.0)
        overall = "PASSED (100% Ready)" if (failed == 0 and unknown == 0) else "FAILED"
        if unknown > 0:
            lines.append(f"Summary : {total} Total, {passed} Passed, {failed} Failed, {unknown} Unknown, {skipped} Skipped ({duration:.3f}s)")
        else:
            lines.append(f"Summary : {total} Total, {passed} Passed, {failed} Failed, {skipped} Skipped ({duration:.3f}s)")
        lines.append(f"Status  : {overall}")
        lines.append("=" * 70)
        return "\n".join(lines)

    @staticmethod
    def format_throttled(report_data: Dict[str, Any]) -> str:
        """
        將測試報告數據轉換為最大化節省 Token 的節流格式。
        - 全數通過: "Pass: {passed}({pct:.1f}%), Fail: 0, Skip: {skipped}" (有 unknown 時附加 Unknown: {unknown})
        - 存在失敗: 統計首行 + FAILED / ERROR TEST CASES LIST 詳情
        """
        total = report_data.get("total", 0)
        passed = report_data.get("passed", 0)
        failed = report_data.get("failed", 0)
        unknown = report_data.get("unknown", 0)
        skipped = report_data.get("skipped", 0)
        pct = (passed / total * 100.0) if total > 0 else 0.0

        if unknown > 0:
            stat_line = f"Pass: {passed}({pct:.1f}%), Fail: {failed}, Unknown: {unknown}, Skip: {skipped}"
        else:
            stat_line = f"Pass: {passed}({pct:.1f}%), Fail: {failed}, Skip: {skipped}"

        failures_list = report_data.get("failures_list", [])
        if failed == 0 and not failures_list:
            return stat_line

        fail_lines = [stat_line, "", "-" * 70, "FAILED / ERROR TEST CASES LIST:"]
        if failures_list:
            fail_lines.extend(_format_failure_entries(failures_list))
        else:
            for mod_info in report_data.get("modules", []):
                for err in mod_info.get("errors", []):
                    fail_lines.append(f"  [!] [{mod_info.get('name', 'unknown')}] ERROR: {err}")

        fail_lines.append("-" * 70)
        return "\n".join(fail_lines)


class SafeStreamWriter:
    """Stream wrapper that handles Unicode encoding errors gracefully on Windows console."""
    def __init__(self, target: Any):
        self.target = target

    def write(self, s: str) -> None:
        try:
            self.target.write(s)
        except UnicodeEncodeError:
            enc = getattr(self.target, "encoding", None) or "utf-8"
            safe_s = s.encode(enc, errors="replace").decode(enc, errors="replace")
            self.target.write(safe_s)

    def flush(self) -> None:
        try:
            self.target.flush()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self.target, name)


class TestRunner:
    def __init__(self, verbose: bool = False, keep_sandbox: bool = False):
        self.verbose = verbose
        self.keep_sandbox = keep_sandbox

    def run_suite(self, suite: unittest.TestSuite) -> Tuple[unittest.TestResult, str]:
        if self.keep_sandbox:
            os.environ["YSCB_TEST_KEEP_SANDBOX"] = "1"
        else:
            os.environ.pop("YSCB_TEST_KEEP_SANDBOX", None)

        stream = SafeStreamWriter(sys.stdout) if self.verbose else StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=2 if self.verbose else 0)
        capturer = OutputCapturer(enabled=not self.verbose)
        try:
            with capturer:
                result = runner.run(suite)
            return result, capturer.get_output()
        finally:
            try:
                YSCBTestCase.cleanup_shared_sandbox()
            except Exception:
                pass
