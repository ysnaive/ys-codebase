"""
Official test suite for dev.checker.Checker.
"""
from dev.testing import YSCBTestCase
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
        """Verify dev/manifest.json contains contributes['agents-workflow'] and DevEngineeringStandards.md exists."""
        dev_manifest = uri.read_json("module.source://dev/manifest.json")
        self.assertIn("contributes", dev_manifest)
        self.assertIn("agents-workflow", dev_manifest["contributes"])
        inserts = dev_manifest["contributes"]["agents-workflow"].get("insert", [])
        self.assertTrue(any(item.get("token") == "WORKFLOW_SOP_STANDARDS" for item in inserts))

        # Check asset file content
        std_p = uri.resolve("module.source://dev/assets/standards/DevEngineeringStandards.md")
        self.assertTrue(uri.exists("module.source://dev/assets/standards/DevEngineeringStandards.md"))
        with open(std_p, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("YS-Codebase 模組開發專案特化工程規範", content)
        self.assertIn("嚴禁 Agent 主動發布與覆蓋宿主安裝", content)
        self.mark_passed()

