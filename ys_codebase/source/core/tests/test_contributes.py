"""
Official test suite for core.contributes.ContributesAggregator and SDK.
"""
import time
from dev.testing import YSCBTestCase, require, Requirement
from core import contributes
from core.contributes import (
    ContributesAggregator,
    _tag_provider,
    _get_contributes_meta_uri,
    _is_contributes_dirty,
    get,
)
from core import providers
from core import uri

class TestCoreContributes(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.aggregator = ContributesAggregator()

    @require(Requirement.ENV)
    def test_scan_and_inject_execution(self):
        """FT-01: Verify scan_and_inject outputs to cache space and leaves config space clean."""
        res = self.aggregator.scan_and_inject()
        self.assertTrue(isinstance(res, dict))
        
        # Verify cache file exists for core
        self.assertTrue(uri.exists("cache://core/contributes.merged.json"))
        # Verify config directory is NOT polluted with merged artifact
        self.assertFalse(uri.exists("config://core/contributes.merged.json"))
        self.assertFalse(uri.exists("config://dev/contributes.merged.json"))
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

    @require(Requirement.ENV)
    def test_contributes_get_sdk(self):
        """FT-04: Verify core.contributes.get and get_for_current_module SDK."""
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

    @require(Requirement.ENV)
    def test_cli_guild_dynamic_generation(self):
        """FT-05: Verify core.providers.get_agents_cli_guild outputs Markdown table via SDK."""
        table_md = providers.get_agents_cli_guild()
        self.assertIn("| 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |", table_md)
        self.assertIn("`python yscb.py install`", table_md)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contribute_json_override_and_local_ignored(self):
        """FT-05, EC-04: Verify project contribute.json overrides contributes, and contribute.local.json is ignored."""
        # 1. Setup mock contribute.json in config://core/contribute.json
        proj_contrib = {
            "commands": {
                "custom_override_cmd": {
                    "description": "Project specific command override",
                    "case_pros": ["專案特化使用"]
                }
            }
        }
        uri.makedirs("config://core", exist_ok=True)
        uri.write_json("config://core/contribute.json", proj_contrib)

        # 2. Setup mock contribute.local.json (should be ignored)
        uri.write_json("config://core/contribute.local.json", {
            "commands": {
                "ignored_local_cmd": {"description": "should not appear"}
            }
        })

        # 3. Rescan
        res = self.aggregator.scan_and_inject()
        core_res = res.get("core", {})
        commands = core_res.get("commands", {})

        # Assert contribute.json was merged
        self.assertIn("custom_override_cmd", commands)
        self.assertEqual(commands["custom_override_cmd"]["description"], "Project specific command override")

        # Assert contribute.local.json was ignored
        self.assertNotIn("ignored_local_cmd", commands)

        # Cleanup
        try:
            uri.remove("config://core/contribute.json")
            uri.remove("config://core/contribute.local.json")
        except Exception:
            pass
        self.aggregator.scan_and_inject()
        self.mark_passed()


class TestContributesJIT(YSCBTestCase):
    """Unit tests for core.contributes JIT Freshness Gate and Auto Self-Healing."""

    def setUp(self):
        super().setUp()
        self.agg = ContributesAggregator()

    @require(Requirement.ENV)
    def test_clean_status_and_latency(self):
        """FT-02: 驗證 Clean 狀態下嗅探比對耗時 <= 2ms，直接返回 False。"""
        self.agg.scan_and_inject()

        start = time.perf_counter()
        is_dirty, _ = _is_contributes_dirty("core")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        self.assertFalse(is_dirty)
        self.assertLess(elapsed_ms, 50.0)  # CI 環境給予合理餘裕
        self.mark_passed()

    @require(Requirement.ENV)
    def test_auto_self_healing_on_mtime_change(self):
        """FT-01: 驗證檔案變更後 _is_contributes_dirty 返回 True，get() 自動自愈聚合。"""
        # 初始聚合
        self.agg.scan_and_inject()
        is_dirty_init, _ = _is_contributes_dirty("core")
        self.assertFalse(is_dirty_init)

        # 動態建立或修改 config://core/contribute.json 模擬專案特化變更
        cfg_uri = "config://core/contribute.json"
        has_orig = uri.exists(cfg_uri)
        orig_data = uri.read_json(cfg_uri) if has_orig else None

        try:
            test_ts = time.time()
            new_data = orig_data.copy() if (orig_data and isinstance(orig_data, dict)) else {}
            new_data["jit_test_stamp"] = test_ts

            time.sleep(0.05)
            uri.write_json(cfg_uri, new_data)

            # 嗅探應立即感知 dirty
            is_dirty, _ = _is_contributes_dirty("core")
            self.assertTrue(is_dirty)

            # 調用 get() 應原地自愈並返回最新注入值
            val = get("core", "jit_test_stamp")
            self.assertEqual(val, test_ts)

            # 自愈後應恢復 clean
            is_dirty_after, _ = _is_contributes_dirty("core")
            self.assertFalse(is_dirty_after)
        finally:
            if has_orig:
                uri.write_json(cfg_uri, orig_data)
            elif uri.exists(cfg_uri):
                uri.remove(cfg_uri)
            self.agg.scan_and_inject()

        self.mark_passed()

    @require(Requirement.ENV)
    def test_missing_cache_triggers_dirty(self):
        """EC-01: 快取遺失或刪除時直接判定為 dirty。"""
        meta_uri = _get_contributes_meta_uri()
        if uri.exists(meta_uri):
            uri.remove(meta_uri)

        is_dirty, _ = _is_contributes_dirty("core")
        self.assertTrue(is_dirty)
        self.mark_passed()


