"""
Official test suite for core.contributes.ContributesAggregator.
"""
from dev.testing import YSCBTestCase
from core.contributes import ContributesAggregator
from core import uri

class TestCoreContributes(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.aggregator = ContributesAggregator()

    def test_scan_and_inject_execution(self):
        """Verify scan_and_inject outputs to cache space and leaves config space clean."""
        res = self.aggregator.scan_and_inject(clean=True)
        self.assertTrue(isinstance(res, dict))
        
        # Verify cache file exists for core
        self.assertTrue(uri.exists("cache.root://core/contributes.merged.json"))
        # Verify config directory is NOT polluted with merged artifact
        self.assertFalse(uri.exists("config.root://core/contributes.merged.json"))
        self.assertFalse(uri.exists("config.root://dev/contributes.merged.json"))
        self.mark_passed()

    def test_deep_merge_dictionary_and_lists(self):
        """Verify recursive cascade deep merge logic."""
        base = {"schemes": ["a", "b"], "opts": {"timeout": 10, "debug": False}}
        overlay = {"schemes": ["b", "c"], "opts": {"debug": True, "extra": "yes"}}
        self.aggregator._deep_merge(base, overlay)
        
        self.assertEqual(base["schemes"], ["a", "b", "c"])
        self.assertEqual(base["opts"]["timeout"], 10)
        self.assertEqual(base["opts"]["debug"], True)
        self.assertEqual(base["opts"]["extra"], "yes")
        self.mark_passed()
