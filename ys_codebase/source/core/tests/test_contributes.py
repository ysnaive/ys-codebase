"""
Official test suite for core.contributes.ContributesAggregator and SDK.
"""
from dev.testing import YSCBTestCase
from core import contributes
from core.contributes import ContributesAggregator, _tag_provider
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

    def test_provider_tagging(self):
        """FT-01, FT-02: Verify __provider__ auto-injection and explicit preservation."""
        raw_items = [
            {"name": "cmd1", "desc": "Command 1"},
            {"name": "cmd2", "desc": "Command 2", "__provider__": "custom_donor"}
        ]
        tagged = _tag_provider(raw_items, "my_module")
        self.assertEqual(tagged[0]["__provider__"], "my_module")
        self.assertEqual(tagged[1]["__provider__"], "custom_donor") # preserved
        self.mark_passed()

    def test_contributes_get_sdk(self):
        """FT-04, FT-05: Verify core.contributes.get and get_for_current_module SDK."""
        # 1. Direct get for core
        core_data = contributes.get("core")
        self.assertTrue(isinstance(core_data, dict))

        # 2. Get specific key
        schemes = contributes.get("core", "uri_schemes", default=[])
        self.assertTrue(isinstance(schemes, list))

        # 3. Get for current module in module_scope
        with uri.module_scope("core"):
            mod_data = contributes.get_for_current_module()
            self.assertEqual(mod_data, core_data)
        self.mark_passed()
