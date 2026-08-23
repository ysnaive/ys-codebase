#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test/test_semver.py — SemVer 2.0.0 與 VersionConstraint 單元測試套件
"""

import sys
import unittest
from pathlib import Path

# 載入 core scripts
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SOURCE_CORE_SCRIPTS = PROJECT_ROOT / "ys_codebase" / "source" / "core" / "scripts"
if str(SOURCE_CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SOURCE_CORE_SCRIPTS))

from semver import SemVer, VersionConstraint


class TestSemVer(unittest.TestCase):
    def test_basic_parsing(self):
        v = SemVer("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertIsNone(v.prerelease)
        self.assertIsNone(v.build)
        self.assertEqual(str(v), "1.2.3")

    def test_tolerant_and_prerelease(self):
        v1 = SemVer("v2.0.0-alpha.1+20260823")
        self.assertEqual(v1.major, 2)
        self.assertEqual(v1.minor, 0)
        self.assertEqual(v1.patch, 0)
        self.assertEqual(v1.prerelease, "alpha.1")
        self.assertEqual(v1.build, "20260823")

        # 短版本寬容解析
        v2 = SemVer("1.0")
        self.assertEqual(str(v2), "1.0.0")

    def test_comparisons(self):
        self.assertTrue(SemVer("1.0.0") < SemVer("2.0.0"))
        self.assertTrue(SemVer("1.2.0") < SemVer("1.3.0"))
        self.assertTrue(SemVer("1.2.3") < SemVer("1.2.4"))
        self.assertTrue(SemVer("1.0.0-alpha") < SemVer("1.0.0"))
        self.assertTrue(SemVer("1.0.0-alpha.1") < SemVer("1.0.0-alpha.2"))
        self.assertTrue(SemVer("1.0.0-alpha.1") < SemVer("1.0.0-beta"))
        self.assertEqual(SemVer("1.0.0"), SemVer("1.0.0"))
        # Build metadata does not affect precedence
        self.assertEqual(SemVer("1.0.0+build1"), SemVer("1.0.0+build2"))
        self.assertTrue(SemVer("2.0.0") >= SemVer("1.9.9"))
        self.assertTrue(SemVer("1.0.0") <= SemVer("1.0.0"))

    def test_bump(self):
        v = SemVer("1.2.3-alpha+build")
        self.assertEqual(str(v.bump_patch()), "1.2.4")
        self.assertEqual(str(v.bump_minor()), "1.3.0")
        self.assertEqual(str(v.bump_major()), "2.0.0")
        self.assertEqual(str(v.bump("patch")), "1.2.4")
        self.assertEqual(str(v.bump("minor")), "1.3.0")
        self.assertEqual(str(v.bump("major")), "2.0.0")


class TestVersionConstraint(unittest.TestCase):
    def test_wildcard(self):
        vc = VersionConstraint("*")
        self.assertTrue(vc.matches("1.0.0"))
        self.assertTrue(vc.matches("2.5.9"))

    def test_range_constraints(self):
        vc = VersionConstraint(">=1.0.0, <2.0.0")
        self.assertTrue(vc.matches("1.0.0"))
        self.assertTrue(vc.matches("1.9.9"))
        self.assertFalse(vc.matches("0.9.9"))
        self.assertFalse(vc.matches("2.0.0"))

    def test_caret_constraint(self):
        vc = VersionConstraint("^1.2.3")
        self.assertTrue(vc.matches("1.2.3"))
        self.assertTrue(vc.matches("1.9.0"))
        self.assertFalse(vc.matches("1.2.2"))
        self.assertFalse(vc.matches("2.0.0"))

        vc_zero = VersionConstraint("^0.2.3")
        self.assertTrue(vc_zero.matches("0.2.3"))
        self.assertTrue(vc_zero.matches("0.2.9"))
        self.assertFalse(vc_zero.matches("0.3.0"))

    def test_tilde_constraint(self):
        vc = VersionConstraint("~1.2.3")
        self.assertTrue(vc.matches("1.2.3"))
        self.assertTrue(vc.matches("1.2.9"))
        self.assertFalse(vc.matches("1.3.0"))
        self.assertFalse(vc.matches("1.2.2"))

    def test_parse_dependency_spec(self):
        name, vc = VersionConstraint.parse_dependency_spec("core >= 2.0.0")
        self.assertEqual(name, "core")
        self.assertTrue(vc.matches("2.0.0"))
        self.assertFalse(vc.matches("1.9.0"))

        name2, vc2 = VersionConstraint.parse_dependency_spec("agents-workflow ^1.0.0")
        self.assertEqual(name2, "agents-workflow")
        self.assertTrue(vc2.matches("1.5.0"))
        self.assertFalse(vc2.matches("2.0.0"))

        name3, vc3 = VersionConstraint.parse_dependency_spec("core")
        self.assertEqual(name3, "core")
        self.assertTrue(vc3.matches("99.0.0"))


if __name__ == "__main__":
    unittest.main()
