import os
import shutil
from dev.testing import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.checker import Checker, CheckSeverity
from dev.releaser import Releaser
from core import uri

class TestDevChecker(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.checker = Checker()
        self.releaser = Releaser()

    @require(Requirement.LOGIC)
    def test_check_core_module_passes(self):
        """Verify checking 'core' module returns True with 0 FAIL errors."""
        report = self.checker.check_module("core")
        self.assertTrue(report.passed, f"Core check failed with errors: {report.errors}")
        self.assertFalse(report.has_fails)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_check_dev_module_passes(self):
        """Verify checking 'dev' module returns True with 0 FAIL errors."""
        report = self.checker.check_module("dev")
        self.assertTrue(report.passed, f"Dev check failed with errors: {report.errors}")
        self.assertFalse(report.has_fails)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_check_all_passes(self):
        """Verify check_all succeeds with passed == True across all production source modules."""
        reports = self.checker.check_all()
        for mod, report in reports.items():
            self.assertTrue(report.passed, f"Module '{mod}' failed check: {report.errors}")
            self.assertFalse(report.has_fails)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft01_manifest_missing_core_dependency(self):
        """FT-01: Verify missing 'core' in dependencies triggers [FAIL]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft01_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft01_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": []}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')

            report = self.checker.check_module("mock_ft01_mod")
            self.assertFalse(report.passed)
            self.assertTrue(report.has_fails)
            self.assertTrue(any("must explicitly declare 'core'" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft02_core_injection_warn(self):
        """FT-02: Verify missing contributes/core.json triggers [WARN]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft02_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft02_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')

            report = self.checker.check_module("mock_ft02_mod")
            self.assertTrue(report.passed)  # Warn does not fail
            self.assertTrue(report.has_warns)
            self.assertTrue(any("lacks 'contributes/core.json'" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft03_zero_probing_detected(self):
        """FT-03: Verify 'module.source://' access in business code triggers [FAIL]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft03_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "mock_pkg"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft03_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "mock_pkg", "logic.py"), "w", encoding="utf-8") as f:
                f.write('src = "module.source://other_mod/foo"\n')

            report = self.checker.check_module("mock_ft03_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("Zero Probing violation" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft04_scattered_config_template_detected(self):
        """FT-04: Verify scattered config.*.json at module root triggers [FAIL]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft04_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft04_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "config.project.json"), "w", encoding="utf-8") as f:
                f.write('{"foo": "bar"}')

            report = self.checker.check_module("mock_ft04_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("Scattered config template found at module root" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft06_antipattern_direct_config_and_contributes(self):
        """FT-06: Verify direct access to 'config.project.json' or 'contributes.merged.json' triggers [FAIL]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft06_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "mock_pkg"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft06_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "mock_pkg", "bad_cfg.py"), "w", encoding="utf-8") as f:
                f.write('CFG_FILE = "config.project.json"\n')
            with open(os.path.join(tmp_mod_dir, "mock_pkg", "bad_contrib.py"), "w", encoding="utf-8") as f:
                f.write('MERGED = "contributes.merged.json"\n')

            report = self.checker.check_module("mock_ft06_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("Reinventing the wheel: direct access to 'config.project.json'" in e for e in report.errors))
            self.assertTrue(any("Direct contributes probing: access to 'contributes.merged.json'" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft07_release_check_fails_on_blocking_issue(self):
        """FT-07: Verify release_check fails and returns False when module has FAIL issues."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft07_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                # Missing core dependency -> FAIL
                f.write('{"name": "mock_ft07_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": []}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')

            passed, errors = self.releaser.release_check("mock_ft07_mod")
            self.assertFalse(passed)
            self.assertTrue(any("Gate 1 Failed" in e for e in errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_et01_syntax_error_handled_gracefully(self):
        """ET-01: Verify SyntaxError in .py file is safely captured as [FAIL] without crashing."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_et01_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_et01_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "broken.py"), "w", encoding="utf-8") as f:
                f.write('def syntax_error_here(\n')

            report = self.checker.check_module("mock_et01_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("SyntaxError in broken.py" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_et02_raw_unittest_testcase_detected(self):
        """ET-02: Verify test class directly subclassing unittest.TestCase is caught."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_et02_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "tests"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_et02_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "tests", "test_bad.py"), "w", encoding="utf-8") as f:
                f.write('import unittest\nclass TestBad(unittest.TestCase):\n    def test_foo(self): pass\n')

            report = self.checker.check_module("mock_et02_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("Security Guard: Test class 'TestBad'" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)
