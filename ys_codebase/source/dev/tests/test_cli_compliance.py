"""
Unit tests for dev.checker CLI compliance AST rules (FT-05 ~ FT-08).
Validates:
- Valid CLI with process(args), no main, pure declarative top-level (PASS)
- Missing process(args) (FAIL)
- Forbidden main function (FAIL)
- Forbidden if __name__ == '__main__': (FAIL)
- Forbidden top-level statements outside func/class (FAIL)
"""

import os
import tempfile
import shutil
from dev.testing import YSCBTestCase
from dev.checker import Checker, CheckReport, CheckSeverity


class TestCLICompliance(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.checker = Checker()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        super().tearDown()

    def _check_code(self, code: str) -> CheckReport:
        cli_p = os.path.join(self.test_dir, "cli.py")
        with open(cli_p, "w", encoding="utf-8") as f:
            f.write(code)
        report = CheckReport(module="test_mod")
        self.checker._check_cli_compliance("test_mod", cli_p, report)
        return report

    def test_checker_cli_pass(self):
        """FT-05: Valid cli.py with process(args), no main, no top-level execution passes."""
        code = '''"""
CLI entry point.
"""
from typing import List
import sys
import os
from core.guard import guard_dispatch

def process(args: List[str]) -> int:
    guard_dispatch("test_mod")
    return 0
'''
        report = self._check_code(code)
        self.assertEqual(report.status, CheckSeverity.PASS, f"Unexpected failures: {report.errors}")
        self.mark_passed()

    def test_checker_missing_process(self):
        """FT-06: Missing process(args) function fails."""
        code = '''"""
CLI entry point.
"""
import sys

def execute(args):
    return 0
'''
        report = self._check_code(code)
        self.assertEqual(report.status, CheckSeverity.FAIL)
        self.assertTrue(any("Missing required entry function 'def process(args)'" in err for err in report.errors))
        self.mark_passed()

    def test_checker_forbidden_main(self):
        """FT-07: Forbidden main function or __main__ block fails."""
        code1 = '''"""
CLI entry point.
"""
from typing import List

def process(args: List[str]) -> int:
    return 0

def main(argv=None):
    return 0
'''
        report1 = self._check_code(code1)
        self.assertEqual(report1.status, CheckSeverity.FAIL)
        self.assertTrue(any("Forbidden function 'main'" in err for err in report1.errors))

        code2 = '''"""
CLI entry point.
"""
from typing import List

def process(args: List[str]) -> int:
    return 0

if __name__ == '__main__':
    pass
'''
        report2 = self._check_code(code2)
        self.assertEqual(report2.status, CheckSeverity.FAIL)
        self.assertTrue(any("Forbidden 'if __name__ == \"__main__\":'" in err for err in report2.errors))
        self.mark_passed()

    def test_checker_toplevel_statements(self):
        """FT-08: Forbidden executable statements outside function/class fail."""
        code = '''"""
CLI entry point.
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
print("Initializing CLI...")

def process(args):
    return 0
'''
        report = self._check_code(code)
        self.assertEqual(report.status, CheckSeverity.FAIL)
        errors_str = " ".join(report.errors)
        self.assertIn("outside function/class", errors_str)
        self.mark_passed()


if __name__ == "__main__":
    import unittest
    unittest.main()
