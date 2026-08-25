"""
Test discovery, execution engine and ASCII report formatter for YS-Codebase.
"""
import os
import sys
import time
import unittest
from io import StringIO
from typing import List, Dict, Any, Optional, Tuple
from core import uri
from dev.testing.contract import make_contract_suite
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement

def filter_suite(
    suite: unittest.TestSuite,
    pattern: Optional[str] = None,
    test_type: Optional[str] = None
) -> unittest.TestSuite:
    """
    Recursively filter test cases within a TestSuite tree by pattern and requirement test_type.
    """
    filtered = unittest.TestSuite()
    
    def _matches(test_case: unittest.TestCase) -> bool:
        method_name = getattr(test_case, "_testMethodName", "")
        # 1. Pattern filter (case-insensitive substring match)
        if pattern and pattern.lower() not in method_name.lower():
            return False
            
        # 2. Type filter against @require(Requirement)
        if test_type:
            tt = test_type.lower()
            method = getattr(test_case, method_name, None)
            req = getattr(method, "__requirement__", None) if method else None
            
            if tt == "logic":
                # Logic tests must not require HOST_CLI or NETWORK
                if req and (Requirement.HOST_CLI in req or Requirement.NETWORK in req):
                    return False
            elif tt == "host_cli":
                if not req or (Requirement.HOST_CLI not in req):
                    return False
            elif tt == "network":
                if not req or (Requirement.NETWORK not in req):
                    return False
            else:
                return False
        return True

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
        source_root_uri = "module.source.root://"
        if not uri.exists(source_root_uri):
            return []
        source_real = uri.resolve(source_root_uri)
        if target:
            mod_path = os.path.join(source_real, target)
            if os.path.isdir(mod_path) and os.path.isfile(os.path.join(mod_path, "manifest.json")):
                return [target]
            return []
        modules = []
        for item in sorted(os.listdir(source_real)):
            mod_path = os.path.join(source_real, item)
            if os.path.isdir(mod_path) and os.path.isfile(os.path.join(mod_path, "manifest.json")):
                modules.append(item)
        return modules

    @staticmethod
    def build_suite_for_module(
        module_name: str,
        test_type: Optional[str] = None,
        pattern: Optional[str] = None,
        contract_only: bool = False
    ) -> Tuple[unittest.TestSuite, int, int]:
        """
        Builds a two-phase test suite for module:
        Phase 1: Universal Auto-Contract Suite
        Phase 2: Custom tests in source/<mod>/tests/ (if present and not contract_only)
        Returns (suite, contract_count, custom_count)
        """
        master_suite = unittest.TestSuite()
        
        # Phase 1: Universal Auto-Contract Suite
        contract_suite = make_contract_suite(module_name)
        if pattern or test_type:
            contract_suite = filter_suite(contract_suite, pattern=pattern, test_type=test_type)
        contract_count = contract_suite.countTestCases()
        master_suite.addTests(contract_suite)

        # Phase 2: Custom Tests in source/<mod>/tests/
        custom_count = 0
        if not contract_only:
            src_real = uri.resolve(f"module.source.root://{module_name}")
            tests_dir = os.path.join(src_real, "tests")
            if os.path.isdir(tests_dir):
                # 1. Clear cached 'tests' and module namespace in sys.modules to prevent stale module cache
                for mod_k in list(sys.modules.keys()):
                    if mod_k == "tests" or mod_k.startswith("tests.") or mod_k == module_name or mod_k.startswith(f"{module_name}."):
                        del sys.modules[mod_k]
                        
                # 2. Clean other module source directories from sys.path to avoid module name shadowing
                try:
                    src_root = uri.resolve("module.source.root://")
                    sys.path[:] = [p for p in sys.path if not (p.startswith(src_root) and p != src_real)]
                except Exception:
                    pass

                # 3. Ensure current src_real is strictly at sys.path[0]
                if src_real in sys.path:
                    sys.path.remove(src_real)
                sys.path.insert(0, src_real)

                # Ensure tests/ directory has __init__.py for discover stability
                init_py = os.path.join(tests_dir, "__init__.py")
                if not os.path.isfile(init_py):
                    try:
                        with open(init_py, "w", encoding="utf-8") as f:
                            f.write('"""Test package auto-infill."""\n')
                    except Exception:
                        pass

                loader = unittest.TestLoader()
                discovered = loader.discover(start_dir=tests_dir, pattern="test_*.py", top_level_dir=src_real)
                
                # Apply recursive pattern & type filter
                if pattern or test_type:
                    discovered = filter_suite(discovered, pattern=pattern, test_type=test_type)
                
                custom_count = discovered.countTestCases()
                master_suite.addTests(discovered)

        return master_suite, contract_count, custom_count


class ASCIIReportFormatter:
    @staticmethod
    def format_summary(report_data: Dict[str, Any]) -> str:
        lines = [
            "=" * 70,
            "YS-Codebase Test Execution Diagnostic Report",
            "=" * 70,
        ]
        
        for mod_info in report_data.get("modules", []):
            mod_name = mod_info["name"]
            status_str = "[PASS]" if mod_info["passed"] else "[FAIL]"
            lines.append(f"[*] Module: {mod_name:<20} {status_str:>40}")
            lines.append(f"    |-- [Contract] Auto-Contract Suite ... ({mod_info['contract_passed']}/{mod_info['contract_total']})")
            if mod_info["custom_total"] > 0:
                lines.append(f"    \\-- [Custom]   Custom Tests ........... ({mod_info['custom_passed']}/{mod_info['custom_total']})")
            else:
                lines.append(f"    \\-- [Custom]   Custom Tests ........... (No custom tests)")
            
            if mod_info.get("errors"):
                for err in mod_info["errors"]:
                    lines.append(f"        [!] ERROR: {err}")
        
        # Dedicated Failure / Error Detailed List Block
        failures_list = report_data.get("failures_list", [])
        if failures_list:
            lines.append("-" * 70)
            lines.append("FAILED / ERROR TEST CASES LIST:")
            for item in failures_list:
                m_tag = f"[{item.get('module', 'unknown')}]"
                t_type = item.get('type', 'FAIL')
                t_name = item.get('test', 'unknown')
                t_msg = item.get('message', '')
                lines.append(f"  [!] {m_tag:<10} {t_type:<8} {t_name}")
                if t_msg:
                    lines.append(f"      └── {t_msg}")
        
        lines.append("-" * 70)
        total = report_data.get("total", 0)
        passed = report_data.get("passed", 0)
        failed = report_data.get("failed", 0)
        skipped = report_data.get("skipped", 0)
        duration = report_data.get("duration", 0.0)
        overall = "PASSED (100% Ready)" if failed == 0 else "FAILED"
        lines.append(f"Summary : {total} Total, {passed} Passed, {failed} Failed, {skipped} Skipped ({duration:.3f}s)")
        lines.append(f"Status  : {overall}")
        lines.append("=" * 70)
        return "\n".join(lines)


class TestRunner:
    def __init__(self, verbose: bool = False, keep_sandbox: bool = False):
        self.verbose = verbose
        self.keep_sandbox = keep_sandbox

    def run_suite(self, suite: unittest.TestSuite) -> unittest.TestResult:
        if self.keep_sandbox:
            os.environ["YSCB_TEST_KEEP_SANDBOX"] = "1"
        else:
            os.environ.pop("YSCB_TEST_KEEP_SANDBOX", None)
            
        stream = sys.stdout if self.verbose else StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=2 if self.verbose else 0)
        return runner.run(suite)
