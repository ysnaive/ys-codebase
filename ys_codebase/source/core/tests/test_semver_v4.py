"""
Unit tests for Four-Segment SemVer Parser, Comparator and Constraint Solver.
"""
import unittest
from core import semver
from core.semver import VersionTuple, parse_semver, compare_semver, match_constraint, find_best_version, bump_version

class TestSemverV4(unittest.TestCase):
    def test_parse_semver_four_segments(self):
        v = parse_semver("1.2.3.4")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertEqual(v.revision, 4)
        self.assertEqual(str(v), "1.2.3.4")

    def test_parse_semver_three_segment_normalization(self):
        v = parse_semver("1.0.0")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 0)
        self.assertEqual(v.patch, 0)
        self.assertEqual(v.revision, 0)
        self.assertEqual(str(v), "1.0.0.0")

    def test_parse_semver_build_tag(self):
        v = parse_semver("1.0.1.build")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 0)
        self.assertEqual(v.patch, 1)
        self.assertEqual(v.revision, "build")
        self.assertTrue(v.is_build)

    def test_compare_semver_numerical_precedence(self):
        # 1.10.0 > 1.9.0
        self.assertEqual(compare_semver("1.10.0.0", "1.9.0.0"), 1)
        self.assertEqual(compare_semver("1.9.0.0", "1.10.0.0"), -1)
        # major takes precedence
        self.assertEqual(compare_semver("2.0.0.0", "1.99.99.99"), 1)

    def test_compare_semver_revision_handling(self):
        # revision is compared numerically when same X.Y.Z
        self.assertEqual(compare_semver("1.0.0.2", "1.0.0.1"), 1)
        self.assertEqual(compare_semver("1.0.0.1", "1.0.0.2"), -1)
        self.assertEqual(compare_semver("1.0.0.1", "1.0.0.1"), 0)
        # numeric revision > 'build'
        self.assertEqual(compare_semver("1.0.0.0", "1.0.0.build"), 1)

    def test_bump_version(self):
        # Major
        self.assertEqual(bump_version("1.2.3.4", "major"), "2.0.0.0")
        # Minor
        self.assertEqual(bump_version("1.2.3.4", "minor"), "1.3.0.0")
        # Patch
        self.assertEqual(bump_version("1.2.3.4", "patch"), "1.2.4.0")
        # Revision
        self.assertEqual(bump_version("1.2.3.4", "revision"), "1.2.3.5")

    def test_match_constraint_and_find_best(self):
        versions = ["1.0.0.0", "1.1.0.0", "1.2.0.0", "1.2.0.1", "2.0.0.0"]
        self.assertEqual(find_best_version(versions, ">=1.0.0, <2.0.0"), "1.2.0.1")
        self.assertEqual(find_best_version(versions, "^1.0.0"), "1.2.0.1")
        self.assertEqual(find_best_version(versions, ">=2.0.0"), "2.0.0.0")

if __name__ == "__main__":
    unittest.main()
