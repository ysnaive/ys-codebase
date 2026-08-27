"""
CLI Command dispatcher for 'dev test', 'dev op-mksb', and 'dev op-test'.
"""
import os
import sys
import time
import subprocess
from typing import List, Dict, Any, Optional
from dev.testing.runner import TestDiscovery, TestRunner, ASCIIReportFormatter
from dev.testing.sandbox import SandboxProvisioner, SandboxContext

class Tester:
    def __init__(self):
        pass

    def run(self, argv: List[str]) -> int:
        if not argv:
            self._print_usage()
            return 1
            
        subcmd = argv[0]
        sub_argv = argv[1:]
        
        if subcmd == "op-mksb":
            return self._run_op_mksb(sub_argv)
        elif subcmd == "op-test":
            return self._run_op_test(sub_argv)
        elif subcmd == "test":
            return self._run_test(sub_argv)
        else:
            # Invoked as Tester.run(["core", ...]) or with arguments directly
            return self._run_test(argv)

    def _print_usage(self) -> None:
        print("[dev:test] Usage: python yscb.py dev test [module_name | --all] [options]")
        print("Subcommands / Modes:")
        print("  dev test [mod | --all]     High-level E2E: Auto build -> Provision sandbox -> Run tests -> Teardown")
        print("  dev op-mksb [--dir=<path>] Atomic primitive: Provision isolated virtual sandbox")
        print("  dev op-test [mod | --all]  Atomic primitive: Run in-place test execution without sandboxing")
        print("Options:")
        print("  --all            Run tests across all modules in source/")
        print("  --no-build       Skip automatic pre-build step and test existing build packages")
        print("  --contract-only  Run only universal standard contract tests")
        print("  --type=<type>    Filter test type (logic | host_cli | network)")
        print("  -k <pattern>     Run only tests matching pattern")
        print("  --verbose, -v    Verbose output with full tracebacks")
        print("  --keep-sandbox   Preserve sandbox directories on success")

    def _run_op_mksb(self, argv: List[str]) -> int:
        target_dir = None
        for a in argv:
            if a.startswith("--dir="):
                target_dir = a.split("=", 1)[1].strip('\"\'')
        ctx = SandboxProvisioner.create_sandbox(target_dir=target_dir)
        print(f"[dev:op-mksb] Sandbox successfully created at: {ctx.sandbox_dir}")
        print(f"  |- Host workspace : {ctx.host_dir}")
        print(f"  |- Project root   : {ctx.project_dir}")
        print(f"  \\- Mock provider  : {ctx.provider_dir}")
        return 0

    def _run_op_test(self, argv: List[str]) -> int:
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
            self._print_usage()
            return 1

        if test_type and test_type.lower() not in ("logic", "host_cli", "network"):
            print(f"[dev:test] Error: Invalid test type '{test_type}'. Valid types: logic, host_cli, network")
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
            "duration": 0.0,
            "failures_list": []
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

            # Accurate classification based on TestCase class name
            contract_failed = sum(1 for c, _ in result.failures + result.errors if "Contract" in c.__class__.__name__)
            custom_failed = mod_failed - contract_failed

            contract_skipped = sum(1 for c, _ in result.skipped if "Contract" in c.__class__.__name__)
            custom_skipped = mod_skipped - contract_skipped

            contract_passed = max(0, contract_total - contract_failed - contract_skipped)
            custom_passed = max(0, custom_total - custom_failed - custom_skipped)

            err_msgs = []
            for test_case, tb in result.failures:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "AssertionError"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": str(test_case),
                    "type": "FAIL",
                    "message": last_line
                })
            for test_case, tb in result.errors:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "Error"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": str(test_case),
                    "type": "ERROR",
                    "message": last_line
                })

            mod_info = {
                "name": mod_name,
                "passed": mod_failed == 0,
                "contract_total": contract_total,
                "contract_passed": contract_passed,
                "custom_total": custom_total,
                "custom_passed": custom_passed,
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

    def _run_test(self, argv: List[str]) -> int:
        """High-level facade: auto dev build -> op-mksb -> run op-test in sandbox -> cleanup"""
        keep_sandbox = "--keep-sandbox" in argv
        no_build = "--no-build" in argv
        clean_argv = [a for a in argv if a != "--no-build"]
        
        # 1. Automatic pre-test Hermetic Dev Build (unless --no-build)
        if not no_build:
            from dev.builder import Builder
            builder = Builder()
            target_mod = next((a for a in clean_argv if not a.startswith("-") and a != "test"), None)
            if target_mod and target_mod != "--all":
                ok, msg = builder.build_module(target_mod)
                if not ok:
                    print(f"[dev:test] Pre-build failed for module '{target_mod}':\n  {msg}", file=sys.stderr)
                    return 1
            else:
                results = builder.build_all()
                for m_name, (ok, msg) in results.items():
                    if not ok:
                        print(f"[dev:test] Pre-build failed for module '{m_name}':\n  {msg}", file=sys.stderr)
                        return 1
        
        # 2. Provision virtual sandbox (resolves from build:// -> mirror:// -> provider)
        ctx = SandboxProvisioner.create_sandbox()
        sandbox_dir = ctx.sandbox_dir
        host_dir = ctx.host_dir
        
        # 3. Invoke dev op-test inside sandbox
        sandbox_yscb = os.path.join(host_dir, "yscb.py")
        op_test_args = [a for a in clean_argv if a != "test"]
        cmd = [sys.executable, sandbox_yscb, "dev", "op-test"] + op_test_args
        
        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        try:
            res = subprocess.run(cmd, cwd=host_dir, env=p_env)
            ret_code = res.returncode
        except Exception as e:
            print(f"[dev:test] Subprocess execution error: {e}")
            ret_code = 1
            
        # 4. Teardown policy
        if ret_code == 0 and not keep_sandbox:
            if "--all" in clean_argv:
                SandboxProvisioner.cleanup_all_sandboxes()
            else:
                SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            if ret_code != 0:
                print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}")
            else:
                print(f"[dev:test] Sandbox preserved at: {sandbox_dir}")
                
        return ret_code
