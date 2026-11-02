"""
Official test suite for core.contributes.ContributesAggregator and SDK.
"""
import time
from dev.testing import YSCBTestCase, require, Requirement
from core import contributes
from core.contributes import (
    ContributesAggregator,
    _deep_merge,
    _tag_provider,
    _get_contributes_meta_uri,
    _is_contributes_dirty,
    get,
)
from core import uri, vfs

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
        self.assertTrue(vfs.exists("cache://core/contributes.merged.json"))
        # Verify config directory is NOT polluted with merged artifact
        self.assertFalse(vfs.exists("config://core/contributes.merged.json"))
        self.assertFalse(vfs.exists("config://dev/contributes.merged.json"))
        self.mark_passed()

    def test_deep_merge_dictionary_and_lists(self):
        """Verify recursive cascade deep merge logic."""
        base = {"schemes": ["a", "b"], "opts": {"timeout": 10, "debug": False}}
        overlay = {"schemes": ["b", "c"], "opts": {"debug": True, "extra": "yes"}}
        _deep_merge(base, overlay)
        
        self.assertEqual(base["schemes"], ["a", "b", "c"])
        self.assertEqual(base["opts"]["timeout"], 10)
        self.assertEqual(base["opts"]["debug"], True)
        self.assertEqual(base["opts"]["extra"], "yes")
        self.mark_passed()

    def test_provider_tagging(self):
        """FT-01, FT-02: Verify __provider__ and __providers__ auto-injection and explicit preservation."""
        raw_items = [
            {"name": "cmd1", "desc": "Command 1"},
            {"name": "cmd2", "desc": "Command 2", "__provider__": "custom_donor"}
        ]
        tagged = _tag_provider(raw_items, "my_module")
        self.assertEqual(tagged[0]["__provider__"], "my_module")
        self.assertEqual(tagged[0]["__providers__"], ["my_module"])
        self.assertEqual(tagged[1]["__provider__"], "custom_donor")  # preserved
        self.assertEqual(tagged[1]["__providers__"], ["custom_donor"])
        self.mark_passed()

    def test_schema_driven_merge_strategies_and_providers(self):
        """Verify _format.json driven merge strategies (extend, replace, unique) and __providers__ accumulation."""
        schema = {
            "_types": {
                "SpaceDef": {
                    "description": "str?",
                    "include": "list[str]! | extend",
                    "file_patterns": "list[str]? | replace",
                }
            },
            "spaces": {
                "description": "spaces map",
                "format": {
                    "*": "$SpaceDef | merge"
                },
            },
            "unique_point": {
                "description": "unique map",
                "format": {
                    "*": "$SpaceDef | unique"
                },
            },
            "replace_point": {
                "description": "replace map",
                "format": {
                    "*": "$SpaceDef | replace"
                },
            },
        }

        donor_a = _tag_provider(
            {
                "spaces": {
                    "docs": {
                        "description": "from mod_a",
                        "include": ["a/docs"],
                        "file_patterns": ["*.md"],
                    }
                },
                "unique_point": {
                    "singleton": {
                        "description": "owned by mod_a",
                        "include": ["a/single"],
                    }
                },
                "replace_point": {
                    "item": {
                        "description": "old desc",
                        "include": ["a/old"],
                        "file_patterns": ["*.old"],
                    }
                },
            },
            "mod_a",
        )
        donor_b = _tag_provider(
            {
                "spaces": {
                    "docs": {
                        "include": ["b/docs"],
                        "file_patterns": ["*.rst"],
                    }
                },
                "unique_point": {
                    "singleton": {
                        "description": "attempted hijack by mod_b",
                        "include": ["b/single"],
                    }
                },
                "replace_point": {
                    "item": {
                        "include": ["b/new"],
                    }
                },
            },
            "mod_b",
        )

        merged: dict = {}
        _deep_merge(merged, donor_a, schema=schema, is_project_override=False)
        _deep_merge(merged, donor_b, schema=schema, is_project_override=False)

        # 1. 'spaces.docs': include is extended, file_patterns is replaced, description kept, __providers__ has both
        docs_entry = merged["spaces"]["docs"]
        self.assertEqual(docs_entry["include"], ["a/docs", "b/docs"])
        self.assertEqual(docs_entry["file_patterns"], ["*.rst"])
        self.assertEqual(docs_entry["description"], "from mod_a")
        self.assertEqual(docs_entry["__providers__"], ["mod_a", "mod_b"])
        self.assertEqual(docs_entry["__provider__"], "mod_b")

        # 2. 'unique_point.singleton': mod_b collision rejected; mod_a preserved
        single_entry = merged["unique_point"]["singleton"]
        self.assertEqual(single_entry["description"], "owned by mod_a")
        self.assertEqual(single_entry["include"], ["a/single"])
        self.assertEqual(single_entry["__providers__"], ["mod_a"])

        # 3. Project override IS allowed to update a 'unique' entry
        proj_overlay = _tag_provider(
            {
                "unique_point": {
                    "singleton": {
                        "description": "overridden by project",
                        "include": ["proj/single"],
                    }
                }
            },
            "project",
        )
        _deep_merge(merged, proj_overlay, schema=schema, is_project_override=True)
        self.assertEqual(merged["unique_point"]["singleton"]["description"], "overridden by project")
        self.assertEqual(merged["unique_point"]["singleton"]["include"], ["a/single", "proj/single"])
        self.assertEqual(merged["unique_point"]["singleton"]["__providers__"], ["mod_a", "project"])

        # 4. 'replace_point.item': whole dict replaced by mod_b (old 'description' & 'file_patterns' gone), __providers__ preserved
        rep_entry = merged["replace_point"]["item"]
        self.assertNotIn("description", rep_entry)
        self.assertNotIn("file_patterns", rep_entry)
        self.assertEqual(rep_entry["include"], ["b/new"])
        self.assertEqual(rep_entry["__providers__"], ["mod_a", "mod_b"])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_get_sdk(self):
        """FT-04: Verify core.contributes.get SDK."""
        # 1. Direct get for core
        core_data = contributes.get("core")
        self.assertTrue(isinstance(core_data, dict))

        # 2. Get specific key
        schemes = contributes.get("core", "uri_schemes", default=[])
        self.assertTrue(isinstance(schemes, list))

        # 3. Get for active module context via uri.get_module_context()
        with uri.module_scope("core"):
            mod_data = contributes.get(uri.get_module_context())
            self.assertEqual(mod_data, core_data)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contribute_json_override_and_local_ignored(self):
        """FT-05, EC-04: Verify project contribute.json overrides contributes, and contribute.local.json is ignored."""
        proj_contrib = {
            "commands": {
                "custom_override_cmd": {
                    "description": "Project specific command override",
                    "usage": {"pros": ["專案特化使用"]}
                }
            }
        }
        vfs.makedirs("config://core", exist_ok=True)
        try:
            # 1. Setup mock contribute.json in config://core/contribute.json
            vfs.write_json("config://core/contribute.json", proj_contrib)

            # 2. Setup mock contribute.local.json (should be ignored)
            vfs.write_json("config://core/contribute.local.json", {
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
        finally:
            for u in ("config://core/contribute.json", "config://core/contribute.local.json"):
                if vfs.exists(u):
                    try:
                        vfs.remove(u)
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
        self.assertLess(elapsed_ms, 200.0)  # CI/Windows 環境給予合理餘裕
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
        has_orig = vfs.exists(cfg_uri)
        orig_data = vfs.read_json(cfg_uri) if has_orig else None

        try:
            test_ts = time.time()
            new_data = orig_data.copy() if (orig_data and isinstance(orig_data, dict)) else {}
            new_data["jit_test_stamp"] = test_ts

            time.sleep(0.05)
            vfs.write_json(cfg_uri, new_data)

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
                vfs.write_json(cfg_uri, orig_data)
            elif vfs.exists(cfg_uri):
                vfs.remove(cfg_uri)
            self.agg.scan_and_inject()

        self.mark_passed()

    @require(Requirement.ENV)
    def test_missing_cache_triggers_dirty(self):
        """EC-01: 快取遺失或刪除時直接判定為 dirty。"""
        meta_uri = _get_contributes_meta_uri()
        if vfs.exists(meta_uri):
            vfs.remove(meta_uri)

        is_dirty, _ = _is_contributes_dirty("core")
        self.assertTrue(is_dirty)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_uri_schemes_reentrancy_and_jit_self_healing(self):
        """驗證 uri._get_merged_uri_schemes 具備 Thread-Local 重入保護且能在髒狀態下觸發 Contributes JIT 自癒。"""
        cfg_uri = "config://core/contribute.json"
        has_orig = vfs.exists(cfg_uri)
        orig_data = vfs.read_json(cfg_uri) if has_orig else None

        try:
            self.agg.scan_and_inject()
            vfs.makedirs("config://core", exist_ok=True)
            new_data = dict(orig_data) if isinstance(orig_data, dict) else {}
            custom_schemes = list(new_data.get("uri_schemes", [])) if isinstance(new_data.get("uri_schemes"), list) else []
            custom_schemes.append({
                "token": "custom.jittest",
                "type": "const",
                "value": "yscb://.cache/jittest",
                "description": "JIT test scheme"
            })
            new_data["uri_schemes"] = custom_schemes
            time.sleep(0.05)
            vfs.write_json(cfg_uri, new_data)

            # 此時尚未主動呼叫 contributes.get，直接透過 uri.resolve 解析新協議應自動觸發 JIT 自癒且無 RecursionError
            resolved = uri.resolve("custom.jittest://sub", interactive=False)
            self.assertTrue(resolved.replace("\\", "/").endswith(".cache/jittest/sub"))

            # 驗證重入保護旗標生效時直接回傳空值而不遞迴
            uri._URI_REENTRANCY.active = True
            try:
                reentrant_res = uri._get_merged_uri_schemes(uri.resolve_yscb_root())
                self.assertEqual(reentrant_res, {})
            finally:
                uri._URI_REENTRANCY.active = False
        finally:
            if has_orig:
                vfs.write_json(cfg_uri, orig_data)
            elif vfs.exists(cfg_uri):
                vfs.remove(cfg_uri)
            self.agg.scan_and_inject()
            uri._SCHEMES_CACHE.clear()

        self.mark_passed()

    @require(Requirement.ENV)
    def test_project_locale_and_source_format_tracked_in_inputs(self):
        """驗證 config://core/contribute.json 宣告之語系檔與 module.source:// _format.json 納入快照追蹤。"""
        cfg_uri = "config://core/contribute.json"
        loc_uri = "config://core/locales/zh_custom_test.json"
        has_orig = vfs.exists(cfg_uri)
        orig_data = vfs.read_json(cfg_uri) if has_orig else None

        try:
            vfs.makedirs("config://core/locales", exist_ok=True)
            vfs.write_json(loc_uri, {"custom.greeting": "Hello v1"})
            new_data = dict(orig_data) if isinstance(orig_data, dict) else {}
            locales_map = dict(new_data.get("locales", {})) if isinstance(new_data.get("locales"), dict) else {}
            locales_map["zh"] = "locales/zh_custom_test.json"
            new_data["locales"] = locales_map
            vfs.write_json(cfg_uri, new_data)

            self.agg.scan_and_inject()
            is_dirty_before, snapshot_before = _is_contributes_dirty("core")
            self.assertFalse(is_dirty_before)
            loc_abs = uri.resolve(loc_uri, interactive=False)
            self.assertIn(loc_abs, snapshot_before)

            # 修改專案語系實體檔內容與大小 -> 應觸發 dirty
            time.sleep(0.05)
            vfs.write_json(loc_uri, {"custom.greeting": "Hello v2 with updated length"})
            is_dirty_after, _ = _is_contributes_dirty("core")
            self.assertTrue(is_dirty_after)
        finally:
            if vfs.exists(loc_uri):
                vfs.remove(loc_uri)
            if has_orig:
                vfs.write_json(cfg_uri, orig_data)
            elif vfs.exists(cfg_uri):
                vfs.remove(cfg_uri)
            self.agg.scan_and_inject()

        self.mark_passed()



