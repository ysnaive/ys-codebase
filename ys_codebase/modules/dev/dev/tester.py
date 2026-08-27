"""
CLI Command dispatcher for 'dev test', 'dev op-mksb', and 'dev op-test'.
"""
import os
import sys
import time
import unittest
import subprocess
from typing import List, Dict, Any, Optional
from dev.testing.runner import TestDiscovery, TestRunner, ASCIIReportFormatter, get_test_category
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
        print("Classification & Targeting Options:")
        print("  --logical        Run only unit / pure logical tests")
        print("  --env            Run environment / inter-module / DI tests")
        print("  --workflow       Run multi-step composite workflow / E2E tests (default excluded)")
        print("  --perf, --stress Run performance / stress benchmark tests (default excluded)")
        print("  --all-types      Run tests across all categories (logic + env + workflow + perf)")
        print("  --type=<type>    Filter test type (logic | env | workflow | perf | all)")
        print("  --target=<mod:[case][.method]>  Pinpoint specific module, test case or method")
        print("General Options:")
        print("  --all            Run tests across all modules in source/")
        print("  --no-build       Skip automatic pre-build step and test existing build packages")
        print("  --contract-only  Run only universal standard contract tests")
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
        target: Optional[str] = None
        contract_only: bool = False
        verbose: bool = False
        keep_sandbox: bool = False

        VALID_TYPES = {"logic", "logical", "env", "host_cli", "workflow", "perf", "performance", "stress", "all", "all_types", "all-types"}

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
            elif arg == "--logical":
                test_type = "logic"
            elif arg == "--env":
                test_type = "env"
            elif arg == "--workflow":
                test_type = "workflow"
            elif arg in ("--perf", "--performance", "--stress"):
                test_type = "perf"
            elif arg == "--all-types":
                test_type = "all"
            elif arg.startswith("--type="):
                test_type = arg.split("=", 1)[1].strip()
            elif arg.startswith("--target="):
                target = arg.split("=", 1)[1].strip()
            elif arg == "--target":
                if i + 1 < len(argv):
                    target = argv[i + 1]
                    i += 1
            elif arg.startswith("-k="):
                pattern = arg.split("=", 1)[1].strip()
            elif arg == "-k":
                if i + 1 < len(argv):
                    pattern = argv[i + 1]
                    i += 1
            elif not arg.startswith("-"):
                target_mod = arg
            i += 1

        if target and not target_mod:
            target_mod = target.split(":", 1)[0]

        if not target_mod and not run_all and not target:
            self._print_usage()
            return 1

        if test_type and test_type.lower().replace("-", "_") not in {t.replace("-", "_") for t in VALID_TYPES}:
            print(f"[dev:test] Error: Invalid test type '{test_type}'. Valid types: logic, env, workflow, perf, all")
            return 1

        modules = TestDiscovery.discover_modules(target_mod)
        if not modules:
            if target_mod:
                print(f"[dev:test] Error: Module '{target_mod}' not found in source/.")
            else:
                print("[dev:test] No modules found in source/.")
            return 1

        # Determine filter mode string for report metadata
        if test_type:
            tt = test_type.lower().replace("-", "_")
            if tt in ("all", "all_types"):
                filter_mode = "ALL Types"
            else:
                filter_mode = f"[{test_type.upper()}]"
        else:
            filter_mode = "Default (LOGIC + ENV)"

        target_scope = target if target else (target_mod if target_mod and not run_all else "All")

        runner = TestRunner(verbose=verbose, keep_sandbox=keep_sandbox)
        report_data: Dict[str, Any] = {
            "filter_mode": filter_mode,
            "target_scope": target_scope,
            "no_build": "--no-build" in argv,
            "modules": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration": 0.0,
            "failures_list": []
        }

        sandbox_id = os.environ.get("YSCB_SANDBOX_ID", "sandbox")
        start_time = time.perf_counter()
        all_passed = True

        for mod_name in modules:
            if not verbose:
                print(f"[dev:test] {mod_name} begin test in {sandbox_id}", flush=True)
            mod_start = time.perf_counter()
            suite, contract_total, custom_total = TestDiscovery.build_suite_for_module(
                mod_name,
                test_type=test_type,
                pattern=pattern,
                target=target,
                contract_only=contract_only
            )
            
            result, captured_output = runner.run_suite(suite)
            mod_duration = time.perf_counter() - mod_start
            if not verbose:
                print(f"[dev:test] {mod_name} test finish in ({mod_duration:.2f}s)", flush=True)
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

            # Taxonomy breakdown for custom passed tests
            logic_passed = 0
            env_passed = 0
            workflow_passed = 0
            perf_passed = 0
            
            failed_test_objs = set(c for c, _ in result.failures + result.errors)
            skipped_test_objs = set(c for c, _ in result.skipped)
            
            def _tally_custom(node: Any):
                nonlocal logic_passed, env_passed, workflow_passed, perf_passed
                if isinstance(node, unittest.TestSuite):
                    for sub in node:
                        _tally_custom(sub)
                elif isinstance(node, unittest.TestCase):
                    if "Contract" in node.__class__.__name__:
                        return
                    if node not in failed_test_objs and node not in skipped_test_objs:
                        cat = get_test_category(node)
                        if cat == "logic":
                            logic_passed += 1
                        elif cat == "env":
                            env_passed += 1
                        elif cat == "workflow":
                            workflow_passed += 1
                        elif cat == "perf":
                            perf_passed += 1
            _tally_custom(suite)

            err_msgs = []
            for test_case, tb in result.failures:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "AssertionError"
                loc = ""
                for l in reversed(tb.strip().splitlines()):
                    if "File " in l and ", line " in l:
                        loc = l.strip()
                        break
                cls_name = test_case.__class__.__name__
                m_name = getattr(test_case, "_testMethodName", "")
                rerun_target = f"python yscb.py dev test --target={mod_name}:{cls_name}.{m_name}" if m_name else f"python yscb.py dev test --target={mod_name}:{cls_name}"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": f"{cls_name}.{m_name}" if m_name else str(test_case),
                    "type": "FAIL",
                    "message": last_line,
                    "location": loc,
                    "rerun": rerun_target,
                    "captured_output": captured_output
                })
            for test_case, tb in result.errors:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "Error"
                loc = ""
                for l in reversed(tb.strip().splitlines()):
                    if "File " in l and ", line " in l:
                        loc = l.strip()
                        break
                cls_name = test_case.__class__.__name__
                m_name = getattr(test_case, "_testMethodName", "")
                rerun_target = f"python yscb.py dev test --target={mod_name}:{cls_name}.{m_name}" if m_name else f"python yscb.py dev test --target={mod_name}:{cls_name}"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": f"{cls_name}.{m_name}" if m_name else str(test_case),
                    "type": "ERROR",
                    "message": last_line,
                    "location": loc,
                    "rerun": rerun_target,
                    "captured_output": captured_output
                })

            mod_info = {
                "name": mod_name,
                "passed": mod_failed == 0,
                "duration": mod_duration,
                "contract_total": contract_total,
                "contract_passed": contract_passed,
                "custom_total": custom_total,
                "custom_passed": custom_passed,
                "logic_passed": logic_passed,
                "env_passed": env_passed,
                "workflow_passed": workflow_passed,
                "perf_passed": perf_passed,
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
        is_nested = os.environ.get("YSCB_NESTED_TEST") == "1"
        keep_sandbox = "--keep-sandbox" in argv
        no_build = "--no-build" in argv
        clean_argv = [a for a in argv if a != "--no-build"]
        
        # 1. Automatic pre-test Hermetic Dev Build (unless --no-build)
        if not no_build:
            if not is_nested:
                print("[dev:test] Pre-building modules for test execution...", flush=True)
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
        sandbox_idx = int(os.environ.get("YSCB_SANDBOX_INDEX", "1"))
        sandbox_display_id = f"sandbox {sandbox_idx}"
        host_dir = ctx.host_dir
        if not is_nested:
            print(f'[dev:test] Create {sandbox_display_id} at: "{sandbox_dir}"', flush=True)
        
        # 3. Invoke dev op-test inside sandbox
        sandbox_yscb = os.path.join(host_dir, "yscb.py")
        op_test_args = [a for a in clean_argv if a != "test"]
        cmd = [sys.executable, sandbox_yscb, "dev", "op-test"] + op_test_args
        
        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        p_env["YSCB_SANDBOX_ID"] = sandbox_display_id
        try:
            res = subprocess.run(
                cmd,
                cwd=host_dir,
                env=p_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            ret_code = res.returncode
            if not is_nested:
                if res.stdout:
                    print(res.stdout, end="", flush=True)
                if res.stderr:
                    print(res.stderr, end="", file=sys.stderr, flush=True)
        except Exception as e:
            if not is_nested:
                print(f"[dev:test] Subprocess execution error: {e}", file=sys.stderr)
            ret_code = 1
            
        # 4. Teardown policy
        if ret_code == 0 and not keep_sandbox:
            if not is_nested:
                print(f"[dev:test] Cleaned up {sandbox_display_id}", flush=True)
            if "--all" in clean_argv:
                SandboxProvisioner.cleanup_all_sandboxes()
            else:
                SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            if not is_nested:
                if ret_code != 0:
                    print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}")
                else:
                    print(f"[dev:test] Sandbox preserved at: {sandbox_dir}")
                
        return ret_code
