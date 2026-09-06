"""
Basic test for server.
"""
import unittest
from dev.testing.case import YSCBTestCase


class TestBasic(YSCBTestCase):
    def test_sample(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()

