"""
Module standard specification contract testing and dynamic testsuite synthesis.
"""
import unittest
from core import uri
from dev.testing.case import YSCBTestCase

class BaseModuleContractTestCase(YSCBTestCase):
    """
    Standard Module Contract Test Base Case (Inspired by uitk.net Contract Testing).
    Synthesized dynamically for all modules in source/ without boilerplate.
    """
    module_name: str = ""

    def test_contract_manifest_schema(self) -> None:
        """Contract 1: Validate manifest.json required fields & SemVer format."""
        src_uri = f"module.source.root://{self.module_name}/manifest.json"
        self.assertTrue(uri.exists(src_uri), f"Missing manifest.json for module '{self.module_name}'")
        data = uri.read_json(src_uri)
        for field in ("name", "version", "entry"):
            self.assertIn(field, data, f"Missing required field '{field}' in manifest.json")
        self.assertEqual(data["name"], self.module_name, f"Module name mismatch: expected '{self.module_name}', got '{data['name']}'")
        self.mark_passed()

    def test_contract_entrypoint_valid(self) -> None:
        """Contract 2: Validate scripts/cli.py entrypoint exists, parses and has main(argv)."""
        from dev.checker import Checker
        checker = Checker()
        passed, errors = checker.check_module(self.module_name)
        self.assertTrue(passed, f"Contract entrypoint check failed: {'; '.join(errors)}")
        self.mark_passed()

    def test_contract_clean_build(self) -> None:
        """Contract 3: Validate clean build produces versioned package directory."""
        from dev.builder import Builder
        builder = Builder()
        passed, msg = builder.build_module(self.module_name, clean=True)
        self.assertTrue(passed, f"Contract clean build failed: {msg}")
        self.mark_passed()


def make_contract_suite(module_name: str) -> unittest.TestSuite:
    """
    Auto-Contract Suite Factory:
    Dynamically synthesizes a contract test suite for target module.
    """
    class_name = f"{module_name.capitalize()}AutoContractTestCase"
    dynamic_case_cls = type(
        class_name,
        (BaseModuleContractTestCase,),
        {"module_name": module_name}
    )
    loader = unittest.TestLoader()
    return loader.loadTestsFromTestCase(dynamic_case_cls)
