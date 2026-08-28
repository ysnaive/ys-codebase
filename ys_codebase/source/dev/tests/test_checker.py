import os
import shutil
from dev.testing import YSCBTestCase
from dev.testing.requirement import require, Requirement
from dev.checker import Checker
from core import uri

class TestDevChecker(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.checker = Checker()

    def test_check_core_module_passes(self):
        """Verify checking 'core' module returns True with 0 errors."""
        passed, errors = self.checker.check_module("core")
        self.assertTrue(passed, f"Core check failed with errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.mark_passed()

    def test_check_dev_module_passes(self):
        """Verify checking 'dev' module returns True with 0 errors."""
        passed, errors = self.checker.check_module("dev")
        self.assertTrue(passed, f"Dev check failed with errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.mark_passed()

    def test_check_all_passes(self):
        """Verify check_all succeeds across source/."""
        res = self.checker.check_all()
        for mod, (passed, errors) in res.items():
            self.assertTrue(passed, f"Module '{mod}' failed check: {errors}")
        self.mark_passed()

    def test_dev_contributes_and_standards_exist(self):
        """Verify dev/contributes/agents-workflow.json exists and DevEngineeringStandards.md exists."""
        contrib_uri = "module.source://dev/contributes/agents-workflow.json"
        self.assertTrue(uri.exists(contrib_uri))
        c_data = uri.read_json(contrib_uri)
        inserts = c_data.get("insert", [])
        self.assertTrue(any(item.get("token") == "WORKFLOW_SOP_STANDARDS" for item in inserts))

        # Check asset file content
        std_p = uri.resolve("module.source://dev/assets/standards/DevEngineeringStandards.md")
        self.assertTrue(uri.exists("module.source://dev/assets/standards/DevEngineeringStandards.md"))
        with open(std_p, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("YS-Codebase 模組開發專案特化工程規範", content)
        self.assertIn("嚴禁 Agent 主動發布與覆蓋宿主安裝", content)
        self.mark_passed()


    @require(Requirement.LOGIC)
    def test_checker_detects_raw_unittest_testcase(self):
        """FT-05: Verify Checker detects test classes directly subclassing unittest.TestCase."""
        import shutil
        src_root = uri.resolve("module.source://")
        tmp_mod_dir = os.path.join(src_root, "mock_bad_mod")
        try:
            os.makedirs(os.path.join(tmp_mod_dir, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(tmp_mod_dir, "tests"), exist_ok=True)
            
            with open(os.path.join(tmp_mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"name": "mock_bad_mod", "version": "1.0.0.0", "entry": "scripts/cli.py"}')
            with open(os.path.join(tmp_mod_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
                f.write('def main(): pass')
            with open(os.path.join(tmp_mod_dir, "tests", "test_bad.py"), "w", encoding="utf-8") as f:
                f.write('import unittest\nclass TestBad(unittest.TestCase):\n    def test_foo(self): pass\n')
                
            passed, errors = self.checker.check_module("mock_bad_mod")
            self.assertFalse(passed)
            self.assertTrue(any("Security Guard: Test class 'TestBad'" in e for e in errors))
            self.mark_passed()
        finally:
            if os.path.exists(tmp_mod_dir):
                shutil.rmtree(tmp_mod_dir, ignore_errors=True)

