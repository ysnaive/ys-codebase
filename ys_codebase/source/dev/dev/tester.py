"""
CLI Command dispatcher for 'dev test'.
"""
import sys
import time
from typing import List, Dict, Any, Optional
from dev.testing.runner import TestDiscovery, TestRunner, ASCIIReportFormatter

class Tester:
    def __init__(self):
        pass

    def run(self, argv: List[str]) -> int:
        target_mod: Optional[str] = None
        run_all: bool = False
        test_type: Optional[str] = None
        pattern: Optional[str] = None
        contract_only: bool = False
        verbose: bool = False
        keep_sandbox: bool = False

        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg == "--all":
                run_all = True
            elif arg == "--contract-only":
                contract_only = True
            elif arg in ("--verbose", "-v"):
                verbose = True
            elif arg == "--keep-sandbox":
                keep_sandbox = True
            elif arg.startswith("--type="):
                test_type = arg.split("=", 1)[1].strip()
            elif arg.startswith("-k="):
                pattern = arg.split("=", 1)[1].strip()
            elif arg == "-k":
                if i + 1 < len(argv):
                    pattern = argv[i + 1]
                    i += 1
            elif not arg.startswith("-"):
                target_mod = arg
            i += 1

        if not target_mod and not run_all:
            print("[dev:test] Usage: python yscb.py dev test [module_name | --all] [options]")
            print("Options:")
            print("  --all            Run tests across all modules in source/")
            print("  --contract-only  Run only universal standard contract tests")
            print("  --type=<type>    Filter test type (logic | sandbox | host | network)")
            print("  -k <pattern>     Run only tests matching pattern")
            print("  --verbose, -v    Verbose output with full tracebacks")
            print("  --keep-sandbox   Preserve sandbox directories on success")
            return 1

        modules = TestDiscovery.discover_modules(target_mod)
        if not modules:
            if target_mod:
                print(f"[dev:test] Error: Module '{target_mod}' not found in source/.")
            else:
                print("[dev:test] No modules found in source/.")
            return 1

        runner = TestRunner(verbose=verbose, keep_sandbox=keep_sandbox)
        report_data: Dict[str, Any] = {
            "modules": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration": 0.0
        }

        start_time = time.perf_counter()
        all_passed = True

        for mod_name in modules:
            suite, contract_total, custom_total = TestDiscovery.build_suite_for_module(
                mod_name,
                test_type=test_type,
                pattern=pattern,
                contract_only=contract_only
            )
            
            result = runner.run_suite(suite)
            mod_total = result.testsRun
            mod_failed = len(result.failures) + len(result.errors)
            mod_skipped = len(result.skipped)
            mod_passed = mod_total - mod_failed - mod_skipped
            
            if mod_failed > 0:
                all_passed = False

            err_msgs = []
            for test_case, tb in result.failures + result.errors:
                err_msgs.append(f"{test_case}: {tb.strip().splitlines()[-1]}")

            mod_info = {
                "name": mod_name,
                "passed": mod_failed == 0,
                "contract_total": contract_total,
                "contract_passed": contract_total if mod_failed == 0 else max(0, contract_total - mod_failed),
                "custom_total": custom_total,
                "custom_passed": custom_total if mod_failed == 0 else max(0, custom_total - mod_failed),
                "errors": err_msgs
            }
            report_data["modules"].append(mod_info)
            report_data["total"] += mod_total
            report_data["passed"] += mod_passed
            report_data["failed"] += mod_failed
            report_data["skipped"] += mod_skipped

        report_data["duration"] = time.perf_counter() - start_time
        print(ASCIIReportFormatter.format_summary(report_data))
        return 0 if all_passed else 1
