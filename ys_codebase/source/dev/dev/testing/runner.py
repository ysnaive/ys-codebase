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
        contract_count = contract_suite.countTestCases()
        master_suite.addTests(contract_suite)

        # Phase 2: Custom Tests in source/<mod>/tests/
        custom_count = 0
        if not contract_only:
            src_real = uri.resolve(f"module.source.root://{module_name}")
            tests_dir = os.path.join(src_real, "tests")
            if os.path.isdir(tests_dir):
                # Clear cached 'tests' namespace in sys.modules to prevent cross-module test collisions
                for mod_k in list(sys.modules.keys()):
                    if mod_k == "tests" or mod_k.startswith("tests."):
                        del sys.modules[mod_k]
                        
                loader = unittest.TestLoader()
                # Ensure src_real is in sys.path so modules can import themselves
                if src_real not in sys.path:
                    sys.path.insert(0, src_real)
                discovered = loader.discover(start_dir=tests_dir, pattern="test_*.py", top_level_dir=src_real)
                
                # Apply filter if pattern specified
                if pattern:
                    filtered_suite = unittest.TestSuite()
                    for test_group in discovered:
                        for test in test_group:
                            if hasattr(test, "_testMethodName") and pattern.lower() in test._testMethodName.lower():
                                filtered_suite.addTest(test)
                            elif hasattr(test, "_tests"):
                                for sub_test in test:
                                    if hasattr(sub_test, "_testMethodName") and pattern.lower() in sub_test._testMethodName.lower():
                                        filtered_suite.addTest(sub_test)
                    discovered = filtered_suite
                
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
