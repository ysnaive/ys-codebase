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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')

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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
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
                f.write('def process(args):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "docs", "dev_guild.md"), "w", encoding="utf-8") as f:
                f.write('# Dev Guild\nEdit files in project://source/mock_ft13_mod/ to start.\n')

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
                f.write('def process(args):\n    return 0\n')
            with open(os.path.join(tmp_mod_dir, "configurable", "custom_template.json"), "w", encoding="utf-8") as f:
                f.write('{"key": "value"}\n')

            report = self.checker.check_module("mock_ft14_mod")
            self.assertTrue(report.has_warns)
            self.assertTrue(any("Non-standard configuration template naming" in w for w in report.warnings))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)


