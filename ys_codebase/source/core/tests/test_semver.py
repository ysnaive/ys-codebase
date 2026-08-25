"""
Unit tests for core.semver (SemVer 2.0.0 parsing, comparison and constraint solver).
"""
import unittest
from core import semver

class SemVerCoreTest(unittest.TestCase):
    def test_parse_valid_semver(self):
        v = semver.parse_semver("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertEqual(v.prerelease, "")
        self.assertEqual(str(v), "1.2.3")

        v_pre = semver.parse_semver("2.0.0-beta.1")
        self.assertEqual(v_pre.major, 2)
        self.assertEqual(v_pre.minor, 0)
        self.assertEqual(v_pre.patch, 0)
        self.assertEqual(v_pre.prerelease, "beta.1")
        self.assertEqual(str(v_pre), "2.0.0-beta.1")

    def test_parse_malformed_semver_raises_value_error(self):
        malformed = ["1.0", "v1.x.y", "invalid", "", "1.2.3.4", "1.a.3"]
        for bad in malformed:
            with self.assertRaises(ValueError, msg=f"Should raise on '{bad}'"):
                semver.parse_semver(bad)

    def test_numerical_ordering_and_comparison(self):
        # 1.10.0 MUST be greater than 1.9.0 (Resolves classic string sort bug)
        self.assertEqual(semver.compare_semver("1.10.0", "1.9.0"), 1)
        self.assertEqual(semver.compare_semver("1.9.0", "1.10.0"), -1)
        self.assertEqual(semver.compare_semver("1.10.0", "1.10.0"), 0)

        # Standard SemVer 2.0.0: release is greater than prerelease
        self.assertEqual(semver.compare_semver("1.0.0", "1.0.0-beta"), 1)
        self.assertEqual(semver.compare_semver("1.0.0-alpha", "1.0.0-beta"), -1)
        self.assertEqual(semver.compare_semver("1.0.0-beta.2", "1.0.0-beta.10"), -1)

    def test_sorted_list_with_semver(self):
        versions = ["1.8.0", "1.10.0", "1.9.0", "2.0.0", "1.9.1", "1.10.0-rc.1"]
        best = semver.find_best_version(versions)
        self.assertEqual(best, "2.0.0")

        # Range filter without 2.0.0
        v_sub = ["1.8.0", "1.10.0", "1.9.0"]
        self.assertEqual(semver.find_best_version(v_sub), "1.10.0")

    def test_constraint_matching(self):
        # Greater than / equal
        self.assertTrue(semver.match_constraint("1.10.0", ">=1.0.0"))
        self.assertTrue(semver.match_constraint("1.0.0", ">=1.0.0"))
        self.assertFalse(semver.match_constraint("0.9.0", ">=1.0.0"))

        # Strict greater / less
        self.assertTrue(semver.match_constraint("1.0.1", ">1.0.0"))
        self.assertFalse(semver.match_constraint("1.0.0", ">1.0.0"))
        self.assertTrue(semver.match_constraint("0.9.9", "<1.0.0"))
        self.assertFalse(semver.match_constraint("1.0.0", "<1.0.0"))

        # Equal / Wildcard
        self.assertTrue(semver.match_constraint("1.2.3", "==1.2.3"))
        self.assertTrue(semver.match_constraint("1.2.3", "1.2.3"))
        self.assertTrue(semver.match_constraint("1.2.3", "*"))
        self.assertTrue(semver.match_constraint("1.2.3", None))

        # Compatible release ~=
        self.assertTrue(semver.match_constraint("1.2.5", "~=1.2.0"))
        self.assertFalse(semver.match_constraint("2.0.0", "~=1.2.0"))

    def test_find_best_version_with_constraints(self):
        versions = ["1.0.0", "1.5.0", "1.9.0", "1.10.0", "2.0.0", "2.1.0"]
        self.assertEqual(semver.find_best_version(versions, "<2.0.0"), "1.10.0")
        self.assertEqual(semver.find_best_version(versions, ">=1.5.0, <2.0.0"), "1.10.0")
        self.assertEqual(semver.find_best_version(versions, ">=3.0.0"), None)

if __name__ == "__main__":
    unittest.main()
