"""
Official test suite for dev.checker.Checker and module compliance validation.
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import types
from typing import Any, Dict, List, Optional
from unittest.mock import patch
from dev.testing import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.checker import Checker, CheckReport, CheckIssue, CheckSeverity, discover_source_modules
from core import uri


@require(Requirement.LOGIC)
class TestDevChecker(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.checker = Checker()
        self._created_mods: List[str] = []

    def tearDown(self):
        for mod_dir in self._created_mods:
            if os.path.exists(mod_dir):
                shutil.rmtree(mod_dir, ignore_errors=True)
        src_root = uri.resolve("module.source://")
        if os.path.isdir(src_root):
            for item in os.listdir(src_root):
                if item.startswith("mock_"):
                    shutil.rmtree(os.path.join(src_root, item), ignore_errors=True)
        super().tearDown()

    def _make_mod(
        self,
        name: str,
        version: str = "1.0.0.0",
        deps: Any = None,
        files: Optional[Dict[str, str]] = None,
        remove_paths: Optional[List[str]] = None,
    ) -> str:
        mod_dir = self.create_mock_source_module(name, version=version, deps=deps, files=files)
        self._created_mods.append(mod_dir)
        for rel_p in (remove_paths or []):
            target = os.path.join(mod_dir, rel_p)
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                os.remove(target)
        return mod_dir

    def test_check_core_module_passes(self):
        """Verify checking 'core' module returns True with 0 FAIL errors."""
        report = self.checker.check_module("core")
        self.assertTrue(report.passed, f"Core check failed with errors: {report.errors}")
        self.assertFalse(report.has_fails)
        self.mark_passed()

    def test_check_dev_module_passes(self):
        """Verify checking 'dev' module returns True with 0 FAIL errors."""
        report = self.checker.check_module("dev")
        self.assertTrue(report.passed, f"Dev check failed with errors: {report.errors}")
        self.assertFalse(report.has_fails)
        self.mark_passed()

    def test_check_all_passes(self):
        """Verify check_all succeeds with passed == True across all production source modules."""
        reports = self.checker.check_all()
        for mod, report in reports.items():
            self.assertTrue(report.passed, f"Module '{mod}' failed check: {report.errors}")
            self.assertFalse(report.has_fails)
        self.mark_passed()

    def test_check_nonexistent_module_and_discover_source_modules(self):
        """Verify check_module on nonexistent module fails with directive and discover_source_modules filters properly."""
        rep = self.checker.check_module("mock_nonexistent_xyz")
        self.assertFalse(rep.passed)
        self.assertTrue(rep.has_fails)
        self.assertTrue(any("Module source not found" in e for e in rep.errors))
        self.assertIsNotNone(rep.agent_directive)

        all_mods = discover_source_modules()
        self.assertIn("core", all_mods)
        self.assertIn("dev", all_mods)
        self.assertEqual(discover_source_modules(target="dev:TestDevChecker"), ["dev"])
        self.assertEqual(discover_source_modules(target="mock_nonexistent_xyz"), [])

        no_mf_dir = os.path.join(uri.resolve("module.source://"), "mock_no_mf_mod")
        os.makedirs(no_mf_dir, exist_ok=True)
        self._created_mods.append(no_mf_dir)
        self.assertEqual(discover_source_modules(target="mock_no_mf_mod", require_manifest=True), [])
        self.assertEqual(discover_source_modules(target="mock_no_mf_mod", require_manifest=False), ["mock_no_mf_mod"])
        self.mark_passed()

    def test_manifest_missing_core_dependency(self):
        """Verify missing 'core' in dependencies triggers FAIL and attaches agent_directive."""
        self._make_mod(
            "mock_missing_core_mod",
            files={
                "manifest.json": '{"name": "mock_missing_core_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": []}'
            },
        )
        report = self.checker.check_module("mock_missing_core_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("must explicitly declare 'core'" in e for e in report.errors))
        self.assertTrue(any("[Agent Directive]" in e and "yscb-module-dev" in e for e in report.errors))
        self.assertIsNotNone(report.agent_directive)
        self.assertIn("[Agent Directive]", report.agent_directive)
        self.assertIn("yscb-module-dev", report.format_report())
        self.assertIn("agent_directive", report.to_dict())
        self.mark_passed()

    def test_core_injection_missing_warn(self):
        """Verify missing contributes/core.json triggers WARN without blocking pass."""
        self._make_mod("mock_missing_core_json_mod", remove_paths=["contributes/core.json"])
        report = self.checker.check_module("mock_missing_core_json_mod")
        self.assertTrue(report.passed)
        self.assertFalse(report.has_fails)
        self.assertTrue(report.has_warns)
        self.assertTrue(any("lacks 'contributes/core.json'" in w for w in report.warnings))
        self.mark_passed()

    def test_zero_probing_detected(self):
        """Verify 'module.source://' access in business code triggers FAIL."""
        self._make_mod(
            "mock_probing_mod",
            files={"mock_pkg/logic.py": 'src = "module.source://other_mod/foo"\n'},
        )
        report = self.checker.check_module("mock_probing_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("Zero Probing violation" in e for e in report.errors))
        self.mark_passed()

    def test_scattered_config_template_detected(self):
        """Verify scattered config.*.json at module root triggers FAIL."""
        self._make_mod(
            "mock_scattered_cfg_mod",
            files={"config.project.json": '{"foo": "bar"}'},
        )
        report = self.checker.check_module("mock_scattered_cfg_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("Scattered config template found at module root" in e for e in report.errors))
        self.mark_passed()

    def test_antipattern_direct_config_and_contributes(self):
        """Verify direct access to 'config.project.json' or 'contributes.merged.json' triggers FAIL."""
        self._make_mod(
            "mock_direct_cfg_mod",
            files={
                "mock_pkg/bad_cfg.py": 'CFG_FILE = "config.project.json"\n',
                "mock_pkg/bad_contrib.py": 'MERGED = "contributes.merged.json"\n',
            },
        )
        report = self.checker.check_module("mock_direct_cfg_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("Reinventing the wheel: direct access to 'config.project.json'" in e for e in report.errors))
        self.assertTrue(any("Direct contributes probing: access to 'contributes.merged.json'" in e for e in report.errors))
        self.mark_passed()

    def test_syntax_error_handled_gracefully(self):
        """Verify SyntaxError in .py file is safely captured as FAIL without crashing."""
        self._make_mod(
            "mock_syntax_err_mod",
            files={"broken.py": "def syntax_error_here(\n"},
        )
        report = self.checker.check_module("mock_syntax_err_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("SyntaxError in broken.py" in e for e in report.errors))
        self.mark_passed()

    def test_raw_unittest_testcase_detected(self):
        """Verify test class directly subclassing unittest.TestCase is caught as FAIL."""
        self._make_mod(
            "mock_raw_testcase_mod",
            files={"tests/test_bad.py": "import unittest\nclass TestBad(unittest.TestCase):\n    def test_foo(self): pass\n"},
        )
        report = self.checker.check_module("mock_raw_testcase_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("Security Guard: Test class 'TestBad'" in e for e in report.errors))
        self.mark_passed()

    def test_logic_plus_isolated_sandbox_warning(self):
        """Verify test method marked with both LOGIC and ISOLATED_SANDBOX triggers WARN."""
        self._make_mod(
            "mock_logic_iso_mod",
            files={
                "tests/test_sample.py": (
                    "from dev.testing import YSCBTestCase, require, Requirement\n"
                    "class TestSample(YSCBTestCase):\n"
                    "    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)\n"
                    "    def test_overkill(self):\n"
                    "        self.mark_passed()\n"
                )
            },
        )
        report = self.checker.check_module("mock_logic_iso_mod")
        self.assertTrue(report.passed)
        self.assertFalse(report.has_fails)
        self.assertTrue(report.has_warns)
        self.assertTrue(any("marked with both 'LOGIC' and 'ISOLATED_SANDBOX'" in w for w in report.warnings))
        self.mark_passed()

    def test_valid_optional_manifest(self):
        """Verify valid optional field in manifest.json passes check_module."""
        self._make_mod(
            "mock_valid_opt_mod",
            files={
                "manifest.json": json.dumps(
                    {
                        "name": "mock_valid_opt_mod",
                        "version": "1.0.0.0",
                        "entry": "scripts/cli.py",
                        "dependencies": ["core"],
                        "optional": {
                            "server": {
                                "version": ">=1.0.0",
                                "hint": "Background service support",
                            }
                        },
                    }
                )
            },
        )
        report = self.checker.check_module("mock_valid_opt_mod")
        self.assertTrue(report.passed, f"Expected pass, got errors: {report.errors}")
        self.assertFalse(report.has_fails)
        self.mark_passed()

    def test_invalid_optional_manifest(self):
        """Verify malformed optional field in manifest.json (missing hint) triggers FAIL."""
        self._make_mod(
            "mock_invalid_opt_mod",
            files={
                "manifest.json": json.dumps(
                    {
                        "name": "mock_invalid_opt_mod",
                        "version": "1.0.0.0",
                        "entry": "scripts/cli.py",
                        "dependencies": ["core"],
                        "optional": {"server": {"version": ">=1.0.0"}},
                    }
                )
            },
        )
        report = self.checker.check_module("mock_invalid_opt_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("missing non-empty string 'hint'" in e for e in report.errors))
        self.mark_passed()

    def test_contributes_manifest_check(self):
        """Verify missing contributes/_manifest.md fails, and legacy contributes.format.md emits WARN."""
        mod_dir = self._make_mod("mock_contrib_manifest_mod", remove_paths=["contributes/_manifest.md"])

        report = self.checker.check_module("mock_contrib_manifest_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("lacks 'contributes/_manifest.md'" in e for e in report.errors))

        with open(os.path.join(mod_dir, "contributes", "_manifest.md"), "w", encoding="utf-8") as f:
            f.write("# Manifest\n")
        with open(os.path.join(mod_dir, "contributes.format.md"), "w", encoding="utf-8") as f:
            f.write("# Legacy\n")

        report2 = self.checker.check_module("mock_contrib_manifest_mod")
        self.assertTrue(report2.passed)
        self.assertFalse(report2.has_fails)
        self.assertTrue(report2.has_warns)
        self.assertTrue(any("Legacy 'contributes.format.md' detected" in w for w in report2.warnings))
        self.mark_passed()

    def test_test_method_mark_passed_and_none_exemption(self):
        """Verify test method without self.mark_passed() emits WARN, while @require(Requirement.NONE) is exempted."""
        mod_dir = self._make_mod(
            "mock_mark_pass_mod",
            files={
                "tests/test_missing.py": (
                    "from dev.testing.case import YSCBTestCase\n"
                    "class TestMissingPass(YSCBTestCase):\n"
                    "    def test_without_mark(self):\n"
                    "        self.assertTrue(True)\n"
                )
            },
        )
        report = self.checker.check_module("mock_mark_pass_mod")
        self.assertTrue(report.passed)
        self.assertFalse(report.has_fails)
        self.assertTrue(report.has_warns)
        self.assertTrue(any("lacks 'self.mark_passed()'" in w for w in report.warnings))

        with open(os.path.join(mod_dir, "tests", "test_missing.py"), "w", encoding="utf-8") as f:
            f.write(
                "from dev.testing import YSCBTestCase, require, Requirement\n"
                "class TestExemptedPass(YSCBTestCase):\n"
                "    @require(Requirement.NONE)\n"
                "    def test_exempt_without_mark(self):\n"
                "        self.assertTrue(True)\n"
            )
        report2 = self.checker.check_module("mock_mark_pass_mod")
        self.assertTrue(report2.passed)
        self.assertFalse(report2.has_fails)
        self.assertFalse(report2.has_warns, f"Expected @require(Requirement.NONE) to exempt warning, got: {report2.warnings}")
        self.mark_passed()

    def test_sandbox_hook_compliance(self):
        """Verify hook.*.py parameter count, top-level statement prohibition, and syntax error handling."""
        mod_dir = self._make_mod(
            "mock_hook_compliance_mod",
            files={
                "scripts/hook.dev.py": "def on_test_setup():\n    pass\n",
                "scripts/hook.core.py": "def on_reload():\n    pass\n",
            },
        )
        report = self.checker.check_module("mock_hook_compliance_mod")
        self.assertFalse(report.passed)
        self.assertTrue(report.has_fails)
        self.assertTrue(any("on_test_setup" in e and "must accept at least 1 parameter" in e for e in report.errors))
        self.assertTrue(any("on_reload" in e and "must accept at least 1 parameter" in e for e in report.errors))

        os.remove(os.path.join(mod_dir, "scripts", "hook.core.py"))
        with open(os.path.join(mod_dir, "scripts", "hook.dev.py"), "w", encoding="utf-8") as f:
            f.write("def on_test_setup(context):\n    pass\n1 + 1\n")
        report2 = self.checker.check_module("mock_hook_compliance_mod")
        self.assertFalse(report2.passed)
        self.assertTrue(report2.has_fails)
        self.assertTrue(any("Forbidden top-level statement" in e for e in report2.errors))

        with open(os.path.join(mod_dir, "scripts", "hook.dev.py"), "w", encoding="utf-8") as f:
            f.write("def broken_hook(:\n")
        report3 = self.checker.check_module("mock_hook_compliance_mod")
        self.assertFalse(report3.passed)
        self.assertTrue(report3.has_fails)
        self.assertTrue(any("SyntaxError in scripts/hook.dev.py" in e for e in report3.errors))
        self.mark_passed()

    def test_docs_path_pollution_warn(self):
        """Verify docs/ containing hardcoded project://source/ emits WARN."""
        self._make_mod(
            "mock_docs_pollution_mod",
            files={"docs/dev_guide.md": "# Dev Guide\nEdit files in project://source/mock_docs_pollution_mod/ to start.\n"},
        )
        report = self.checker.check_module("mock_docs_pollution_mod")
        self.assertTrue(report.passed)
        self.assertFalse(report.has_fails)
        self.assertTrue(report.has_warns)
        self.assertTrue(any("Documentation path pollution" in w for w in report.warnings))
        self.mark_passed()

    def test_configurable_naming_check(self):
        """Verify non-standard filename under configurable/ emits WARN."""
        self._make_mod(
            "mock_cfg_naming_mod",
            files={"configurable/custom_template.json": '{"key": "value"}\n'},
        )
        report = self.checker.check_module("mock_cfg_naming_mod")
        self.assertTrue(report.passed)
        self.assertFalse(report.has_fails)
        self.assertTrue(report.has_warns)
        self.assertTrue(any("Non-standard configuration template naming" in w for w in report.warnings))
        self.mark_passed()

    def test_format_and_configurable_json_errors_and_junk_files(self):
        """Verify invalid JSON in contributes/_format.json and configurable/, and leftover junk file warnings."""
        mod_dir = self._make_mod(
            "mock_json_junk_mod",
            files={
                "contributes/_format.json": "{bad_format_json",
                "configurable/config.project.json": "{bad_cfg_json",
                "leftover.tmp": "scratch",
            },
        )
        rep1 = self.checker.check_module("mock_json_junk_mod")
        self.assertFalse(rep1.passed)
        self.assertTrue(rep1.has_fails)
        self.assertTrue(any("Syntax error in 'contributes/_format.json'" in e for e in rep1.errors))
        self.assertTrue(any("Invalid JSON in 'configurable/config.project.json'" in e for e in rep1.errors))
        self.assertTrue(any("Found leftover temporary/junk file: 'leftover.tmp'" in w for w in rep1.warnings))

        os.remove(os.path.join(mod_dir, "contributes", "_format.json"))
        with open(os.path.join(mod_dir, "configurable", "config.project.json"), "w", encoding="utf-8") as f:
            f.write('{"valid": true}\n')
        rep2 = self.checker.check_module("mock_json_junk_mod")
        self.assertTrue(rep2.passed)
        self.assertFalse(rep2.has_fails)
        self.assertTrue(rep2.has_warns)
        self.assertTrue(any("leftover.tmp" in w for w in rep2.warnings))
        self.mark_passed()

    def test_manifest_onboarding_validation(self):
        """Verify manifest.json onboarding field passes when valid string list and fails when empty/invalid."""
        mod_dir = self._make_mod(
            "mock_onboarding_mod",
            files={
                "manifest.json": (
                    '{"name": "mock_onboarding_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", '
                    '"dependencies": ["core"], "onboarding": ["Step 1: python yscb.py status"]}'
                )
            },
        )
        report_ok = self.checker.check_module("mock_onboarding_mod")
        self.assertTrue(report_ok.passed, f"Expected pass, got: {report_ok.errors}")
        self.assertFalse(report_ok.has_fails)

        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(
                '{"name": "mock_onboarding_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", '
                '"dependencies": ["core"], "onboarding": [""]}'
            )
        report_bad = self.checker.check_module("mock_onboarding_mod")
        self.assertFalse(report_bad.passed)
        self.assertTrue(report_bad.has_fails)
        self.assertTrue(any("'onboarding' field in manifest.json" in e for e in report_bad.errors))
        self.mark_passed()

    def test_checker_cli_compliance_and_candidates(self):
        """Verify CLI compliance candidates accept full function name or primary group function name."""
        mod_dir = self._make_mod(
            "mock_cli_cand_mod",
            files={
                "contributes/core.json": '{"commands": {"cmd": {"sub": {"description": "sub group", "cmd": {"run": {"description": "test"}}}}}}',
                "scripts/cli.py": 'from core.guard import guard_dispatch\ndef sub_run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n',
            },
        )
        rep1 = self.checker.check_module("mock_cli_cand_mod")
        self.assertTrue(rep1.passed, f"sub_run should pass: {rep1.errors}")

        with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write('from core.guard import guard_dispatch\ndef sub(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
        rep2 = self.checker.check_module("mock_cli_cand_mod")
        self.assertTrue(rep2.passed, f"sub should pass: {rep2.errors}")

        with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write('from core.guard import guard_dispatch\ndef run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
        rep3 = self.checker.check_module("mock_cli_cand_mod")
        self.assertFalse(rep3.passed)
        self.assertTrue(any("Missing required command handler functions" in e for e in rep3.errors))

        with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write('from core.guard import guard_dispatch\ndef cmd_sub_run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
        rep4 = self.checker.check_module("mock_cli_cand_mod")
        self.assertFalse(rep4.passed)
        self.assertTrue(any("Missing required command handler functions" in e for e in rep4.errors))
        self.mark_passed()

    def test_checker_cli_forbidden_constructs(self):
        """Verify forbidden main function, if __name__ == '__main__', and top-level expressions fail compliance."""
        mod_dir = self._make_mod(
            "mock_cli_forbidden_mod",
            files={"scripts/cli.py": "def hello(cmd_bags):\n    return 0\ndef main():\n    pass\n"},
        )
        rep1 = self.checker.check_module("mock_cli_forbidden_mod")
        self.assertFalse(rep1.passed)
        self.assertTrue(any("Forbidden function 'main'" in e for e in rep1.errors))

        with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write('def hello(cmd_bags):\n    return 0\nif __name__ == "__main__":\n    pass\n')
        rep2 = self.checker.check_module("mock_cli_forbidden_mod")
        self.assertFalse(rep2.passed)
        self.assertTrue(any('Forbidden \'if __name__ == "__main__":\'' in e for e in rep2.errors))

        with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write('def hello(cmd_bags):\n    return 0\nprint("side-effect")\n')
        rep3 = self.checker.check_module("mock_cli_forbidden_mod")
        self.assertFalse(rep3.passed)
        self.assertTrue(any("top-level expression" in e for e in rep3.errors))
        self.mark_passed()

    def test_checker_pip_dependencies_format(self):
        """Validate manifest.json pip_dependencies structure."""
        mod_dir = self._make_mod(
            "mock_pip_dep_mod",
            files={
                "manifest.json": '{"name": "mock_pip_dep_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"], "pip_dependencies": ["bad_list"]}'
            },
        )
        rep1 = self.checker.check_module("mock_pip_dep_mod")
        self.assertFalse(rep1.passed)
        self.assertTrue(any("must be an object" in e or "must be a dictionary" in e for e in rep1.errors))

        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "mock_pip_dep_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"], "pip_dependencies": {"pkg": 123}}')
        rep2 = self.checker.check_module("mock_pip_dep_mod")
        self.assertFalse(rep2.passed)
        self.assertTrue(any("Invalid version specification" in e for e in rep2.errors))
        self.mark_passed()

    def test_checker_runtime_isolation_guardrails_a_to_f(self):
        """Verify _SourceGuardrailVisitor enforces A1~F13, scoped import alias resolution, and reflection defense."""
        mod_dir = self._make_mod(
            "mock_guardrail_mod",
            files={
                "mock_guardrail_mod/bad_io.py": (
                    "import logging\n"
                    "import pprint as pp\n"
                    "import sys as s\n"
                    "def run():\n"
                    "    print('hi')\n"
                    "    pp.pprint({'a': 1})\n"
                    "    s.stdout.write('x')\n"
                    "    logging.info('msg')\n"
                    "    input('prompt')\n"
                    "    s.stdin.readline()\n"
                ),
                "mock_guardrail_mod/bad_proc.py": (
                    "import os as _os\n"
                    "import sys\n"
                    "import signal as sig\n"
                    "from pathlib import Path as P\n"
                    "def run():\n"
                    "    sys.exit(1)\n"
                    "    _os.chdir('/tmp')\n"
                    "    P.cwd()\n"
                    "    _os.environ['X'] = '1'\n"
                    "    _os.putenv('Y', '2')\n"
                    "    sig.signal(1, lambda a, b: None)\n"
                    "    getattr(_os, 'environ')\n"
                ),
                "mock_guardrail_mod/bad_state.py": (
                    "from dataclasses import dataclass\n"
                    "from typing import ClassVar, Dict\n"
                    "MUT_LIST = []\n"
                    "MUT_NONE = None\n"
                    "UNPACK_A, UNPACK_B = [], {}\n"
                    "@dataclass\n"
                    "class UnfrozenBox:\n"
                    "    val: int = 1\n"
                    "@dataclass(frozen=True)\n"
                    "class FrozenWithMutableClassVar:\n"
                    "    shared_cv: ClassVar[Dict[str, int]] = {}\n"
                    "    untyped_mut = []\n"
                    "class MutableClass:\n"
                    "    shared = {}\n"
                    "def fn(items=[]):\n"
                    "    global MUT_NONE\n"
                    "    globals()['MUT_NONE'] = 1\n"
                ),
                "mock_guardrail_mod/bad_dyn_fs_thread.py": (
                    "import os\n"
                    "import importlib\n"
                    "import subprocess as sp\n"
                    "import urllib.request as ureq\n"
                    "from threading import Thread as T\n"
                    "from importlib.util import spec_from_file_location as sffl\n"
                    "from pathlib import Path\n"
                    "import sys\n"
                    "def run(p: Path):\n"
                    "    sys.modules['x'] = None\n"
                    "    sys.argv.append('--bad')\n"
                    "    sys.argv[0] = 'x'\n"
                    "    importlib.reload(os)\n"
                    "    sffl('x', '/tmp/x.py')\n"
                    "    eval('1+1')\n"
                    "    os.rename('a', 'b')\n"
                    "    p.rename('c')\n"
                    "    sp.run(['echo', 'hi'])\n"
                    "    sp.run(['echo', 'hi'], timeout=None)\n"
                    "    sp.run('echo hi', timeout=5, shell=True)\n"
                    "    ureq.urlopen('https://example.com')\n"
                    "    os.system('ls')\n"
                    "    T(target=lambda: None)\n"
                ),
                "scripts/hook.core.py": (
                    "BAD_HOOK_STATE = []\n"
                    "def on_reload(**kwargs):\n"
                    "    pass\n"
                ),
            },
        )
        rep = self.checker.check_module("mock_guardrail_mod")
        self.assertFalse(rep.passed)
        err_text = "\n".join(rep.errors)
        for expected_tag in (
            "[A1]",
            "[A2]",
            "[B3]",
            "[B4]",
            "[B5]",
            "[B6]",
            "[C7]",
            "[C8]",
            "[C9]",
            "[D10]",
            "[D11]",
            "[E12]",
            "[F13]",
        ):
            self.assertIn(expected_tag, err_text, f"Missing expected guardrail tag {expected_tag} in:\n{err_text}")
        self.assertIn("core.context.get_virtual_cwd()", err_text)
        self.assertIn("Forbidden 'sys.argv' mutation", err_text)
        self.assertIn("Forbidden direct mutation of 'sys.argv'", err_text)
        self.assertIn("Forbidden unmanaged module reload", err_text)
        self.assertIn("Forbidden 'shell=True' in subprocess call", err_text)
        self.assertIn("Network call 'urllib.request.urlopen()'", err_text)
        self.assertIn("Hook function 'on_reload' in scripts/hook.core.py:2 must accept at least 1 parameter", err_text)

        issue_lines = {(i.file_path, i.line_number) for i in rep.issues if i.severity == CheckSeverity.FAIL}
        self.assertIn(("mock_guardrail_mod/bad_io.py", 5), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_proc.py", 7), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_state.py", 5), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_state.py", 11), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_state.py", 12), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 11), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 13), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 17), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 19), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 20), issue_lines)
        self.assertIn(("mock_guardrail_mod/bad_dyn_fs_thread.py", 21), issue_lines)

        for bad_f in ("bad_io.py", "bad_proc.py", "bad_state.py", "bad_dyn_fs_thread.py"):
            os.remove(os.path.join(mod_dir, "mock_guardrail_mod", bad_f))
        os.remove(os.path.join(mod_dir, "scripts", "hook.core.py"))

        with open(os.path.join(mod_dir, "mock_guardrail_mod", "clean.py"), "w", encoding="utf-8") as f:
            f.write(
                "from dataclasses import dataclass\n"
                "from enum import Enum\n"
                "import subprocess\n"
                "import urllib.request\n"
                "IMMUTABLE = ('a', 'b')\n"
                "try:\n"
                "    import non_existent_opt_pkg\n"
                "except ImportError:\n"
                "    non_existent_opt_pkg = None\n"
                "class Color(Enum):\n"
                "    RED = 'red'\n"
                "class BranchNode:\n"
                "    def rename(self, new_name: str) -> str:\n"
                "        return new_name\n"
                "@dataclass(frozen=True)\n"
                "class FrozenCfg:\n"
                "    name: str = 'ok'\n"
                "def local_alias_scope():\n"
                "    import math as P\n"
                "    return P.floor(1.5)\n"
                "def safe_run(items=None):\n"
                "    node = BranchNode()\n"
                "    node.rename('main')\n"
                "    subprocess.run(['echo', 'ok'], timeout=5)\n"
                "    urllib.request.urlopen('https://example.com', timeout=5)\n"
                "    return items or []\n"
            )
        with open(os.path.join(mod_dir, "scripts", "hook.core.py"), "w", encoding="utf-8") as f:
            f.write(
                "SAFE_CONST = 'v1'\n"
                "def on_reload(ctx=None, /):\n"
                "    return True\n"
            )
        rep_clean = self.checker.check_module("mock_guardrail_mod")
        self.assertTrue(rep_clean.passed, f"Expected clean module to pass, got: {rep_clean.errors}")
        self.assertFalse(rep_clean.has_fails)
        self.mark_passed()

    def test_checker_core_injection_format_priority(self):
        """Verify _check_core_injection prioritizes module.source://<target>/contributes/_format.json."""
        self._make_mod(
            "mock_target_mod",
            files={
                "contributes/_format.json": json.dumps(
                    {
                        "custom_pt": {
                            "description": "Custom point",
                            "format": {"custom_token": "str!"},
                        }
                    }
                )
            },
        )
        self._make_mod(
            "mock_donor_mod",
            files={"contributes/mock_target_mod.json": '{"custom_pt": {"wrong_field": 123}}'},
        )
        rep = self.checker.check_module("mock_donor_mod")
        self.assertFalse(rep.passed)
        self.assertTrue(rep.has_fails)
        self.assertTrue(any("Schema violation in 'contributes/mock_target_mod.json'" in e for e in rep.errors))
        self.mark_passed()

    def test_checker_locales_contract_validation(self):
        """Verify dev check validates 'locales' definition contract, orphan keys, and placeholder integrity."""
        mod_dir = self._make_mod(
            "mock_locale_check_mod",
            deps={"core": ">=1.1.0"},
            files={
                "scripts/cli.py": "def hello(cmd_bags):\n    return 0\n",
                "locales/definition.json": json.dumps(
                    {
                        "cli.msg": {
                            "description": "CLI message with count",
                            "placeholders": ["count"],
                        }
                    }
                ),
                "locales/zh-TW.json": json.dumps(
                    {
                        "cli.msg": "Missing placeholder string",
                        "cli.orphan": "Orphan key",
                    }
                ),
                "contributes/core.json": json.dumps(
                    {
                        "locales": {
                            "definition": "locales/definition.json",
                            "zh-TW": "locales/zh-TW.json",
                        }
                    }
                ),
            },
        )
        rep_fail = self.checker.check_module("mock_locale_check_mod")
        self.assertFalse(rep_fail.passed)
        err_str = "\n".join(rep_fail.errors)
        self.assertIn("Placeholder contract mismatch for 'cli.msg'", err_str)
        self.assertIn("Orphan locale key 'cli.orphan'", err_str)
        self.assertIn("requires 'core' >= 1.2.0 in 'manifest.json' dependencies", err_str)

        with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "mock_locale_check_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": {"core": ">=1.2.0"}}')
        with open(os.path.join(mod_dir, "locales", "zh-TW.json"), "w", encoding="utf-8") as f:
            json.dump({"cli.msg": "Total {count} items"}, f)

        rep_ok = self.checker.check_module("mock_locale_check_mod")
        self.assertTrue(rep_ok.passed, f"Expected pass, got errors: {rep_ok.errors}")
        self.assertFalse(rep_ok.has_fails)
        self.mark_passed()

    def test_checker_package_dunder_version_mismatch_detected(self):
        """Verify Checker detects mismatch between package __init__.py __version__ and manifest.json version."""
        mod_dir = self._make_mod(
            "mock_ver_mismatch_mod",
            version="1.2.0.0",
            files={"mock_ver_mismatch_mod/__init__.py": '__version__ = "1.3.0.0"\n'},
        )
        rep_fail = self.checker.check_module("mock_ver_mismatch_mod")
        self.assertFalse(rep_fail.passed)
        self.assertIn("Package __version__ mismatch", "\n".join(rep_fail.errors))

        with open(os.path.join(mod_dir, "mock_ver_mismatch_mod", "__init__.py"), "w", encoding="utf-8") as f:
            f.write('__version__ = "1.2.0.0"\n')
        rep_ok = self.checker.check_module("mock_ver_mismatch_mod")
        self.assertTrue(rep_ok.passed, f"Expected pass, got: {rep_ok.errors}")
        self.assertFalse(rep_ok.has_fails)
        self.mark_passed()

    def test_checker_bare_except_emits_antipattern_warning(self):
        """Verify Checker.check_module emits a WARN (ANTIPATTERN) when a source file contains a bare 'except:' clause."""
        self._make_mod(
            "mock_bare_except_mod",
            files={
                "mock_bare_except_mod/bad_mod.py": (
                    "def risky():\n"
                    "    try:\n"
                    "        return 1 / 0\n"
                    "    except:\n"
                    "        return 0\n"
                )
            },
        )
        rep = self.checker.check_module("mock_bare_except_mod")
        self.assertTrue(rep.passed, f"Expected pass with WARN, got errors: {rep.errors}")
        self.assertFalse(rep.has_fails)
        self.assertTrue(rep.has_warns)
        self.assertEqual(rep.status, CheckSeverity.WARN)
        bare_warns = [
            i
            for i in rep.issues
            if i.severity == CheckSeverity.WARN
            and i.category == "ANTIPATTERN"
            and "Bare 'except:' clause detected" in i.message
        ]
        self.assertEqual(len(bare_warns), 1)
        self.assertEqual(bare_warns[0].file_path, "mock_bare_except_mod/bad_mod.py")
        self.assertEqual(bare_warns[0].line_number, 4)
        self.mark_passed()

    def test_checker_forbids_non_core_sys_path_mutation(self):
        """Verify Checker rejects direct sys.path mutations in non-core source files while allowing read-only access and test files."""
        mod_dir = self._make_mod(
            "mock_syspath_mod",
            files={
                "scripts/cli.py": (
                    "import sys\n"
                    "def hello(cmd_bags):\n"
                    "    snap = list(sys.path)\n"
                    "    return 0 if snap is not None else 1\n"
                ),
                "mock_syspath_mod/__init__.py": '__version__ = "1.0.0.0"\n',
                "tests/test_dummy.py": (
                    "import sys\n"
                    "from dev.testing.case import YSCBTestCase\n"
                    "from dev.testing.requirement import require, Requirement\n"
                    "sys.path.insert(0, '/tmp')\n"
                    "@require(Requirement.LOGIC)\n"
                    "class TestDummy(YSCBTestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.mark_passed()\n"
                ),
            },
        )
        rep_clean = self.checker.check_module("mock_syspath_mod")
        self.assertTrue(rep_clean.passed, f"Expected clean module to pass, got: {rep_clean.errors}")
        self.assertFalse(rep_clean.has_fails)

        with open(os.path.join(mod_dir, "mock_syspath_mod", "violator.py"), "w", encoding="utf-8") as f:
            f.write(
                "import sys as s\n"
                "from sys import path as sp\n"
                "def bad():\n"
                "    s.path.insert(0, '/bad')\n"
                "    sp.append('/bad2')\n"
                "    s.path[:] = []\n"
                "    del s.path[0]\n"
            )
        rep_bad = self.checker.check_module("mock_syspath_mod")
        self.assertFalse(rep_bad.passed)
        fail_msgs = [
            i.message
            for i in rep_bad.issues
            if i.severity == CheckSeverity.FAIL and "Forbidden direct sys.path mutation" in i.message
        ]
        self.assertEqual(len(fail_msgs), 4)
        self.mark_passed()

    def test_cli_check_command_modes(self):
        """Verify scripts/cli.py check command in single-module, --all, and --json modes."""
        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_check_modes", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        buf_single = io.StringIO()
        with patch("sys.stdout", buf_single):
            rc1 = cli_mod.check(["dev", "--json"])
        self.assertEqual(rc1, 0)
        parsed_single = json.loads(buf_single.getvalue())
        self.assertEqual(parsed_single.get("module"), "dev")
        self.assertTrue(parsed_single.get("passed"))

        buf_all = io.StringIO()
        with patch("sys.stdout", buf_all):
            rc2 = cli_mod.check(["--all", "--json"])
        self.assertEqual(rc2, 0)
        parsed_all = json.loads(buf_all.getvalue())
        self.assertIn("core", parsed_all)
        self.assertIn("dev", parsed_all)

        buf_text = io.StringIO()
        with patch("sys.stdout", buf_text):
            rc3 = cli_mod.check(["dev"])
        self.assertEqual(rc3, 0)
        self.assertIn("Status  : PASSED", buf_text.getvalue())

        self._make_mod("mock_cli_chk_fail", remove_paths=["manifest.json"])
        buf_fail = io.StringIO()
        with patch("sys.stdout", buf_fail):
            rc4 = cli_mod.check(["mock_cli_chk_fail"])
        self.assertEqual(rc4, 1)
        self.assertIn("FAILED (Release Blocked)", buf_fail.getvalue())
        self.mark_passed()

    def test_checker_defaultdict_classvar_and_context_cache(self):
        """Verify DefaultDict in _MUTABLE_TYPE_NAMES and Checker AST/JSON cache reuse across repeated check_module runs."""
        from dev.checker import _MUTABLE_TYPE_NAMES

        self.assertIn("DefaultDict", _MUTABLE_TYPE_NAMES)
        self.assertNotIn(" DefaultDict", _MUTABLE_TYPE_NAMES)

        rep1 = self.checker.check_module("dev")
        self.assertTrue(rep1.passed)
        self.assertGreater(len(self.checker._parsed_py_cache), 0)
        self.assertGreater(len(self.checker._json_cache), 0)

        rep2 = self.checker.check_module("dev")
        self.assertTrue(rep2.passed)
        self.assertEqual(len(rep1.issues), len(rep2.issues))
        self.mark_passed()
