"""
Unit tests for core.semver (Four-Segment SemVer Parser, Comparator, Constraint Solver and Version Bumper).
"""
import unittest
from core import semver
from core.semver import (
    VersionTuple,
    parse_semver,
    compare_semver,
    match_constraint,
    find_best_version,
    bump_version
)
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement


class SemVerCoreTest(YSCBTestCase):
    """標準四段式語意版本 (Major.Minor.Patch.Revision) 與約束解析單元測試。"""

    def test_parse_valid_semver(self):
        # 標準四段式
        v4 = parse_semver("1.2.3.4")
        self.assertEqual(v4.major, 1)
        self.assertEqual(v4.minor, 2)
        self.assertEqual(v4.patch, 3)
        self.assertEqual(v4.revision, 4)
        self.assertEqual(str(v4), "1.2.3.4")

        # 三段式正規化 (預設補 0)
        v3 = parse_semver("1.2.3")
        self.assertEqual(v3.major, 1)
        self.assertEqual(v3.minor, 2)
        self.assertEqual(v3.patch, 3)
        self.assertEqual(v3.revision, 0)
        self.assertEqual(str(v3), "1.2.3.0")

        # Prerelease 標籤
        v_pre = parse_semver("2.0.0-beta.1")
        self.assertEqual(v_pre.major, 2)
        self.assertEqual(v_pre.minor, 0)
        self.assertEqual(v_pre.patch, 0)
        self.assertEqual(v_pre.prerelease, "beta.1")

    def test_parse_semver_build_tag(self):
        # 本地開發包 .build 標籤
        v_build = parse_semver("1.0.1.build")
        self.assertEqual(v_build.major, 1)
        self.assertEqual(v_build.minor, 0)
        self.assertEqual(v_build.patch, 1)
        self.assertEqual(v_build.revision, "build")
        self.assertTrue(v_build.is_build)

    def test_parse_malformed_semver_raises_value_error(self):
        malformed = ["1.0", "v1.x.y", "invalid", "", "1.2.3.4.5", "1.a.3"]
        for bad in malformed:
            with self.assertRaises(ValueError, msg=f"Should raise on '{bad}'"):
                parse_semver(bad)

    def test_numerical_ordering_and_comparison(self):
        # 1.10.0 MUST be greater than 1.9.0 (消滅字串排序缺陷)
        self.assertEqual(compare_semver("1.10.0.0", "1.9.0.0"), 1)
        self.assertEqual(compare_semver("1.9.0.0", "1.10.0.0"), -1)
        self.assertEqual(compare_semver("1.10.0.0", "1.10.0.0"), 0)

        # Major 優先級
        self.assertEqual(compare_semver("2.0.0.0", "1.99.99.99"), 1)

        # Revision 數值比較
        self.assertEqual(compare_semver("1.0.0.2", "1.0.0.1"), 1)
        self.assertEqual(compare_semver("1.0.0.1", "1.0.0.2"), -1)
        self.assertEqual(compare_semver("1.0.0.1", "1.0.0.1"), 0)

        # 數值 Revision 高於 'build'
        self.assertEqual(compare_semver("1.0.0.0", "1.0.0.build"), 1)

        # 正式版高於 Prerelease
        self.assertEqual(compare_semver("1.0.0", "1.0.0-beta"), 1)
        self.assertEqual(compare_semver("1.0.0-alpha", "1.0.0-beta"), -1)

    def test_bump_version(self):
        # Major 升級 (重置 minor, patch, revision)
        self.assertEqual(bump_version("1.2.3.4", "major"), "2.0.0.0")
        # Minor 升級 (重置 patch, revision)
        self.assertEqual(bump_version("1.2.3.4", "minor"), "1.3.0.0")
        # Patch 升級 (重置 revision)
        self.assertEqual(bump_version("1.2.3.4", "patch"), "1.2.4.0")
        # Revision 升級 (日常微調)
        self.assertEqual(bump_version("1.2.3.4", "revision"), "1.2.3.5")

    def test_sorted_list_and_find_best(self):
        versions = ["1.8.0.0", "1.10.0.0", "1.9.0.0", "2.0.0.0", "1.9.1.0"]
        best = find_best_version(versions)
        self.assertEqual(best, "2.0.0.0")

        # 限制條件範圍過濾
        self.assertEqual(find_best_version(versions, "<2.0.0.0"), "1.10.0.0")
        self.assertEqual(find_best_version(versions, ">=1.9.0.0, <2.0.0.0"), "1.10.0.0")
        self.assertEqual(find_best_version(versions, ">=3.0.0.0"), None)

    def test_constraint_matching(self):
        # 大於 / 等於
        self.assertTrue(match_constraint("1.10.0.0", ">=1.0.0"))
        self.assertTrue(match_constraint("1.0.0.0", ">=1.0.0"))
        self.assertFalse(match_constraint("0.9.0.0", ">=1.0.0"))

        # 嚴格大於 / 小於
        self.assertTrue(match_constraint("1.0.1.0", ">1.0.0"))
        self.assertFalse(match_constraint("1.0.0.0", ">1.0.0"))
        self.assertTrue(match_constraint("0.9.9.0", "<1.0.0"))
        self.assertFalse(match_constraint("1.0.0.0", "<1.0.0"))

        # 等於與萬用字元
        self.assertTrue(match_constraint("1.2.3.0", "==1.2.3.0"))
        self.assertTrue(match_constraint("1.2.3.0", "1.2.3.0"))
        self.assertTrue(match_constraint("1.2.3.0", "*"))
        self.assertTrue(match_constraint("1.2.3.0", None))

        # 相容版本 ~=
        self.assertTrue(match_constraint("1.2.5.0", "~=1.2.0"))
        self.assertFalse(match_constraint("2.0.0.0", "~=1.2.0"))


if __name__ == "__main__":
    unittest.main()
