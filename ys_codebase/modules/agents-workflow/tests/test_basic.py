"""
Basic test for agents-workflow.
"""
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestBasic(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_sample(self):
        self.assertTrue(True)
        self.mark_passed()

if __name__ == "__main__":
    import unittest
    unittest.main()
