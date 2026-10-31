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
                f.write('def hello(cmd_bags):\n    return 0\n')

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
                f.write('def hello(cmd_bags):\n    return 0\n')

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
                f.write('def hello(cmd_bags):\n    return 0\n')
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
                f.write('def hello(cmd_bags):\n    return 0\n')
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
                f.write('def hello(cmd_bags):\n    return 0\n')
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
                f.write('def hello(cmd_bags):\n    return 0\n')

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
                f.write('def hello(cmd_bags):\n    return 0\n')
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
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "tests", "test_bad.py"), "w", encoding="utf-8") as f:
                f.write('import unittest\nclass TestBad(unittest.TestCase):\n    def test_foo(self): pass\n')

            report = self.checker.check_module("mock_et02_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("Security Guard: Test class 'TestBad'" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft07_logic_plus_isolated_sandbox_warning(self):
        """FT-07: Verify test method marked with both LOGIC and ISOLATED_SANDBOX triggers [WARN]."""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft07_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "tests"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft07_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "tests", "test_sample.py"), "w", encoding="utf-8") as f:
                f.write(
                    'from dev.testing import YSCBTestCase, require, Requirement\n'
                    'class TestSample(YSCBTestCase):\n'
                    '    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)\n'
                    '    def test_overkill(self):\n'
                    '        pass\n'
                )

            report = self.checker.check_module("mock_ft07_mod")
            self.assertTrue(report.passed)  # Warning does not block pass
            self.assertTrue(report.has_warns)
            self.assertTrue(any("marked with both 'LOGIC' and 'ISOLATED_SANDBOX'" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_valid_optional_manifest(self):
        """FT-03: 驗證合法的 optional 欄位通過 check_module 檢驗"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_valid_opt_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{\n'
                    '  "name": "mock_valid_opt_mod",\n'
                    '  "version": "1.0.0.0",\n'
                    '  "entry": "scripts/cli.py",\n'
                    '  "dependencies": ["core"],\n'
                    '  "optional": {\n'
                    '    "server": {\n'
                    '      "version": ">=1.0.0",\n'
                    '      "hint": "提供常駐背景服務"\n'
                    '    }\n'
                    '  }\n'
                    '}\n'
                )
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')

            report = self.checker.check_module("mock_valid_opt_mod")
            self.assertTrue(report.passed, f"Expected pass, got errors: {report.errors}")
            self.assertFalse(report.has_fails)
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_invalid_optional_manifest(self):
        """FT-04: 驗證不合規的 optional 結構 (非 dict、缺 hint 等) 被精確攔截 [FAIL]"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_invalid_opt_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{\n'
                    '  "name": "mock_invalid_opt_mod",\n'
                    '  "version": "1.0.0.0",\n'
                    '  "entry": "scripts/cli.py",\n'
                    '  "dependencies": ["core"],\n'
                    '  "optional": {\n'
                    '    "server": {\n'
                    '      "version": ">=1.0.0"\n'
                    '    }\n'
                    '  }\n'
                    '}\n'
                )
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')

            report = self.checker.check_module("mock_invalid_opt_mod")
            self.assertFalse(report.passed)
            self.assertTrue(report.has_fails)
            self.assertTrue(any("missing non-empty string 'hint'" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft10_contributes_manifest_check(self):
        """FT-10: 驗證 contributes/ 缺少 _manifest.md 時判定 FAIL，存在 legacy format 時判定 WARN"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft10_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "contributes"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft10_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')

            # 1. 缺少 _manifest.md 應觸發 FAIL
            report = self.checker.check_module("mock_ft10_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("lacks 'contributes/_manifest.md'" in e for e in report.errors))

            # 2. 補上 _manifest.md 並加入舊版 contributes.format.md
            with open(os.path.join(tmp_mod_dir, "contributes", "_manifest.md"), "w", encoding="utf-8") as f:
                f.write("# Manifest\n")
            with open(os.path.join(tmp_mod_dir, "contributes.format.md"), "w", encoding="utf-8") as f:
                f.write("# Legacy\n")

            report2 = self.checker.check_module("mock_ft10_mod")
            self.assertTrue(report2.passed)
            self.assertTrue(any("Legacy 'contributes.format.md' detected" in w for w in report2.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft11_test_method_mark_passed_warn(self):
        """FT-11: 驗證測試方法體未呼叫 self.mark_passed() 時觸發 WARN 提示"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft11_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "tests"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft11_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "tests", "test_missing.py"), "w", encoding="utf-8") as f:
                f.write(
                    'from dev.testing.case import YSCBTestCase\n'
                    'class TestMissingPass(YSCBTestCase):\n'
                    '    def test_without_mark(self):\n'
                    '        self.assertTrue(True)\n'
                )

            report = self.checker.check_module("mock_ft11_mod")
            self.assertTrue(report.has_warns)
            self.assertTrue(any("lacks 'self.mark_passed()'" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft12_sandbox_hook_compliance(self):
        """FT-12: 驗證 hook.dev.py 函式缺少參數或頂層存在執行語句時判定 FAIL"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft12_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft12_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "scripts", "hook.dev.py"), "w", encoding="utf-8") as f:
                f.write('def on_test_setup():\n    pass\n')

            report = self.checker.check_module("mock_ft12_mod")
            self.assertFalse(report.passed)
            self.assertTrue(any("must accept at least 1 parameter" in e for e in report.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft13_docs_path_pollution_warn(self):
        """FT-13: 驗證 docs/ 第三方文檔出現 project://source/ 硬編碼時觸發 WARN"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft13_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "docs"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft13_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "docs", "dev_guide.md"), "w", encoding="utf-8") as f:
                f.write('# Dev Guide\nEdit files in project://source/mock_ft13_mod/ to start.\n')

            report = self.checker.check_module("mock_ft13_mod")
            self.assertTrue(report.has_warns)
            self.assertTrue(any("Documentation path pollution" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft14_configurable_naming_check(self):
        """FT-14: 驗證 configurable/ 內包含非 config.*.json 命名之檔案時觸發 WARN"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft14_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "configurable"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_ft14_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "configurable", "custom_template.json"), "w", encoding="utf-8") as f:
                f.write('{"key": "value"}\n')

            report = self.checker.check_module("mock_ft14_mod")
            self.assertTrue(report.has_warns)
            self.assertTrue(any("Non-standard configuration template naming" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_ft15_manifest_onboarding_validation(self):
        """FT-05, EC-02: 驗證 manifest.json 中 onboarding 欄位合法通過，非字串陣列則觸發 FAIL"""
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_ft15_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')

            # 1. Valid onboarding list of non-empty strings -> PASS
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{"name": "mock_ft15_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", '
                    '"dependencies": ["core"], "onboarding": ["Step 1: python yscb.py status"]}'
                )
            report_ok = self.checker.check_module("mock_ft15_mod")
            self.assertTrue(report_ok.passed, f"Expected pass, got: {report_ok.errors}")

            # 2. Invalid onboarding (not a list of non-empty strings) -> FAIL
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{"name": "mock_ft15_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", '
                    '"dependencies": ["core"], "onboarding": [""]}'
                )
            report_bad = self.checker.check_module("mock_ft15_mod")
            self.assertFalse(report_bad.passed)
            self.assertTrue(any("'onboarding' field in manifest.json" in e for e in report_bad.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_checker_cli_compliance_and_candidates(self):
        """FT-05 & [P00:DR-01]: Verify CLI compliance candidates = {full_fn, primary_fn}."""
        src_root = uri.resolve("module.source://")
        tmp_dir = os.path.join(src_root, "mock_cli_cand_mod")
        try:
            os.makedirs(os.path.join(tmp_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_dir, "contributes"), exist_ok=True)
            with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_cli_cand_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}')
            with open(os.path.join(tmp_dir, "contributes", "_manifest.md"), "w", encoding="utf-8") as f:
                f.write("# Manifest\n")
            with open(os.path.join(tmp_dir, "contributes", "core.json"), "w", encoding="utf-8") as f:
                f.write('{"commands": {"cmd": {"sub": {"description": "sub group", "cmd": {"run": {"description": "test"}}}}}}')

            # 1. Full function name sub_run passes
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('from core.guard import guard_dispatch\ndef sub_run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
            rep1 = self.checker.check_module("mock_cli_cand_mod")
            self.assertTrue(rep1.passed, f"sub_run should pass: {rep1.errors}")

            # 2. Primary function name sub passes
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('from core.guard import guard_dispatch\ndef sub(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
            rep2 = self.checker.check_module("mock_cli_cand_mod")
            self.assertTrue(rep2.passed, f"sub should pass: {rep2.errors}")

            # 3. Invalid candidate cmd_sub_run or run alone fails
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('from core.guard import guard_dispatch\ndef run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
            rep3 = self.checker.check_module("mock_cli_cand_mod")
            self.assertFalse(rep3.passed)
            self.assertTrue(any("Missing required command handler functions" in e for e in rep3.errors))

            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('from core.guard import guard_dispatch\ndef cmd_sub_run(cmd_bags):\n    guard_dispatch("mock_cli_cand_mod")\n    return 0\n')
            rep4 = self.checker.check_module("mock_cli_cand_mod")
            self.assertFalse(rep4.passed)
            self.assertTrue(any("Missing required command handler functions" in e for e in rep4.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_checker_cli_forbidden_constructs(self):
        """FT-07: Forbidden main and if __name__ == '__main__' fail compliance."""
        src_root = uri.resolve("module.source://")
        tmp_dir = os.path.join(src_root, "mock_cli_forbidden_mod")
        try:
            os.makedirs(os.path.join(tmp_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_cli_forbidden_mod", "version": "1.0.0.0", "entry": "scripts/cli.py"}')

            # 1. Main function forbidden
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\ndef main():\n    pass\n')
            rep1 = self.checker.check_module("mock_cli_forbidden_mod")
            self.assertFalse(rep1.passed)
            self.assertTrue(any("Forbidden function 'main'" in e for e in rep1.errors))

            # 2. If name == main forbidden
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\nif __name__ == "__main__":\n    pass\n')
            rep2 = self.checker.check_module("mock_cli_forbidden_mod")
            self.assertFalse(rep2.passed)
            self.assertTrue(any("Forbidden 'if __name__ == \"__main__\":'" in e for e in rep2.errors))

            # 3. Invalid top-level expression
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\nprint("side-effect")\n')
            rep3 = self.checker.check_module("mock_cli_forbidden_mod")
            self.assertFalse(rep3.passed)
            self.assertTrue(any("top-level expression" in e for e in rep3.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_checker_pip_dependencies_format(self):
        """FT-08: Validate manifest.json pip_dependencies structure."""
        src_root = uri.resolve("module.source://")
        tmp_dir = os.path.join(src_root, "mock_pip_dep_mod")
        try:
            os.makedirs(os.path.join(tmp_dir, "scripts"), exist_ok=True)
            with open(os.path.join(tmp_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')

            # 1. Non-dict pip_dependencies fails
            with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_pip_dep_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "pip_dependencies": ["bad_list"]}')
            rep1 = self.checker.check_module("mock_pip_dep_mod")
            self.assertFalse(rep1.passed)
            self.assertTrue(any("must be an object" in e or "must be a dictionary" in e for e in rep1.errors))

            # 2. Non-string spec fails
            with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_pip_dep_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "pip_dependencies": {"pkg": 123}}')
            rep2 = self.checker.check_module("mock_pip_dep_mod")
            self.assertFalse(rep2.passed)
            self.assertTrue(any("Invalid version specification" in e for e in rep2.errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_checker_custom_rules_dispatch_and_isolation(self):
        """FR-04, EC-06, [P00:DR-02]: Custom rules support code.func://, isolate sys.path, convert error to WARN."""
        import sys
        import types
        from unittest.mock import patch
        from dev.checker import CheckReport, CheckSeverity, CheckIssue

        rep = CheckReport("mock_target")
        # Test 1: Exception in custom rule converts to WARN
        with patch("core.contributes.get", return_value=[{"checker_func": "non_existent_pkg.checker.non_existent_func"}]):
            orig_path = list(sys.path)
            self.checker._check_custom_rules("mock_target", "/dummy", rep)
            self.assertEqual(sys.path, orig_path)
            self.assertTrue(rep.has_warns)
            self.assertTrue(any("Failed to execute custom rule" in w for w in rep.warnings))

        # Test 2: Invalid code.func:// URI converts to WARN
        rep2 = CheckReport("mock_target")
        with patch("core.contributes.get", return_value=[{"checker_func": "code.func://bad_uri"}]):
            self.checker._check_custom_rules("mock_target", "/dummy", rep2)
            self.assertTrue(rep2.has_warns)
            self.assertTrue(any("Failed to parse custom check URI" in w for w in rep2.warnings))

        # Test 3: Working custom rule via mod:func and code.func://
        dummy_mod = types.ModuleType("mock_donor_rule_pkg")
        def custom_rule_fn(mod_name, mod_dir, report):
            report.issues.append(CheckIssue(CheckSeverity.WARN, "CUSTOM", f"Custom rule fired for {mod_name}"))
        dummy_mod.custom_rule_fn = custom_rule_fn
        sys.modules["mock_donor_rule_pkg"] = dummy_mod
        try:
            rep3 = CheckReport("mock_target")
            with patch("core.contributes.get", return_value=[
                {"checker_func": "mock_donor_rule_pkg:custom_rule_fn", "_contribute_by": "core"},
                {"checker_func": "code.func://core/mock_donor_rule_pkg.py:custom_rule_fn"},
            ]):
                orig_path3 = list(sys.path)
                self.checker._check_custom_rules("mock_target", "/dummy", rep3)
                self.assertEqual(sys.path, orig_path3)
                self.assertFalse(any("module.source://" in p or "/source" in p for p in sys.path if p not in orig_path3))
                custom_msgs = [i.message for i in rep3.issues if i.category == "CUSTOM"]
                self.assertEqual(len(custom_msgs), 2)
        finally:
            sys.modules.pop("mock_donor_rule_pkg", None)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_checker_core_injection_format_priority(self):
        """FR-04: _check_core_injection prioritizes module.source://<target>/contributes/_format.json."""
        import json
        src_root = uri.resolve("module.source://")
        donor_dir = os.path.join(src_root, "mock_donor_mod")
        target_dir = os.path.join(src_root, "mock_target_mod")
        try:
            os.makedirs(os.path.join(donor_dir, "contributes"), exist_ok=True)
            os.makedirs(os.path.join(donor_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(target_dir, "contributes"), exist_ok=True)
            os.makedirs(os.path.join(target_dir, "scripts"), exist_ok=True)

            with open(os.path.join(donor_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_donor_mod", "version": "1.0.0.0", "entry": "scripts/cli.py"}')
            with open(os.path.join(donor_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(donor_dir, "contributes", "_manifest.md"), "w", encoding="utf-8") as f:
                f.write('# Donor Manifest\n')

            # Target defines source format schema requiring "custom_token": "str!"
            target_fmt = {
                "custom_pt": {
                    "description": "Custom point",
                    "format": {
                        "custom_token": "str!"
                    }
                }
            }
            with open(os.path.join(target_dir, "contributes", "_format.json"), "w", encoding="utf-8") as f:
                json.dump(target_fmt, f)

            # Donor contributes invalid data to target (missing custom_token)
            with open(os.path.join(donor_dir, "contributes", "mock_target_mod.json"), "w", encoding="utf-8") as f:
                f.write('{"custom_pt": {"wrong_field": 123}}')

            rep = self.checker.check_module("mock_donor_mod")
            # Should detect schema violation using target's source _format.json!
            self.assertFalse(rep.passed)
            self.assertTrue(any("Schema violation in 'contributes/mock_target_mod.json'" in e for e in rep.errors))
            self.mark_passed()
        finally:
            if os.path.exists(donor_dir):
                shutil.rmtree(donor_dir, ignore_errors=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)

    @require(Requirement.LOGIC)
    def test_checker_locales_contract_validation(self):
        """FR-05, EC-04: dev check validates 'locales' definition contract, orphan keys, and placeholder integrity."""
        import json
        src_root = uri.resolve("module.source://")
        mod_dir = os.path.join(src_root, "mock_locale_check_mod")
        try:
            os.makedirs(os.path.join(mod_dir, "contributes"), exist_ok=True)
            os.makedirs(os.path.join(mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(mod_dir, "locales"), exist_ok=True)

            with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_locale_check_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": {"core": ">=1.1.0"}}')
            with open(os.path.join(mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def hello(cmd_bags):\n    return 0\n')
            with open(os.path.join(mod_dir, "contributes", "_manifest.md"), "w", encoding="utf-8") as f:
                f.write('# Locale Test Manifest\n')

            with open(os.path.join(mod_dir, "locales", "definition.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "cli.msg": {
                        "description": "CLI message with count",
                        "placeholders": ["count"]
                    }
                }, f)

            # 1. Invalid locale file: orphan key + missing placeholder + core dependency < 1.2.0
            with open(os.path.join(mod_dir, "locales", "zh-TW.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "cli.msg": "沒有佔位符的字串",
                    "cli.orphan": "孤兒鍵"
                }, f)

            with open(os.path.join(mod_dir, "contributes", "core.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "locales": {
                        "definition": "locales/definition.json",
                        "zh-TW": "locales/zh-TW.json"
                    }
                }, f)

            rep_fail = self.checker.check_module("mock_locale_check_mod")
            self.assertFalse(rep_fail.passed)
            err_str = "\n".join(rep_fail.errors)
            self.assertIn("Placeholder contract mismatch for 'cli.msg'", err_str)
            self.assertIn("Orphan locale key 'cli.orphan'", err_str)
            self.assertIn("requires 'core' >= 1.2.0 in 'manifest.json' dependencies", err_str)

            # 2. Fix locale file and update dependencies.core >= 1.2.0 -> passes!
            with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_locale_check_mod", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": {"core": ">=1.2.0"}}')
            with open(os.path.join(mod_dir, "locales", "zh-TW.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "cli.msg": "共 {count} 筆結果"
                }, f)

            rep_ok = self.checker.check_module("mock_locale_check_mod")
            self.assertTrue(rep_ok.passed, f"Expected pass, got errors: {rep_ok.errors}")
            self.mark_passed()
        finally:
            if os.path.exists(mod_dir):
                shutil.rmtree(mod_dir, ignore_errors=True)



