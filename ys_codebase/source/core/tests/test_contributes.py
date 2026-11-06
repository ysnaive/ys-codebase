"""
Official test suite for core.contributes.ContributesAggregator and SDK.
"""
import os
import time
from unittest.mock import patch

from dev.testing import YSCBTestCase, require, Requirement
from core import contributes, uri, vfs
from core.contributes import (
    ContributesAggregator,
    _deep_merge,
    _tag_provider,
    _get_contributes_meta_uri,
    _is_contributes_dirty,
    get,
)


def _bump_mtime(file_uri: str, delta_sec: float = 2.0) -> None:
    prev_re = getattr(uri._URI_REENTRANCY, "active", False)
    uri._URI_REENTRANCY.active = True
    try:
        abs_p = uri.resolve(file_uri, interactive=False)
    finally:
        uri._URI_REENTRANCY.active = prev_re
    st = os.stat(abs_p)
    os.utime(abs_p, (st.st_atime, st.st_mtime + delta_sec))
    contributes._LAST_CLEAN_SCAN_TS.clear()


@require(Requirement.ENV)
class TestCoreContributes(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.aggregator = ContributesAggregator()

    def test_scan_and_inject_execution(self):
        """Verify scan_and_inject outputs to cache space and leaves config space clean."""
        res = self.aggregator.scan_and_inject()
        self.assertIsInstance(res, dict)
        self.assertIn("core", res)

        self.assertTrue(vfs.exists("cache://core/contributes.merged.json"))
        self.assertFalse(vfs.exists("config://core/contributes.merged.json"))
        self.assertFalse(vfs.exists("config://dev/contributes.merged.json"))
        self.mark_passed()

    def test_deep_merge_dictionary_and_lists(self):
        """Verify recursive cascade deep merge logic and container isolation."""
        base = {"schemes": ["a", "b"], "items": [{"id": 1}], "opts": {"timeout": 10, "debug": False}}
        overlay_item = {"id": 2}
        overlay = {"schemes": ["b", "c"], "items": [overlay_item], "opts": {"debug": True, "extra": "yes"}}
        _deep_merge(base, overlay)

        self.assertEqual(base["schemes"], ["a", "b", "c"])
        self.assertEqual(base["opts"]["timeout"], 10)
        self.assertEqual(base["opts"]["debug"], True)
        self.assertEqual(base["opts"]["extra"], "yes")

        overlay_item["id"] = 999
        self.assertEqual(base["items"], [{"id": 1}, {"id": 2}])
        self.mark_passed()

    def test_provider_tagging(self):
        """Verify __provider__ and __providers__ auto-injection and explicit preservation."""
        raw_items = [
            {"name": "cmd1", "desc": "Command 1"},
            {"name": "cmd2", "desc": "Command 2", "__provider__": "custom_donor"}
        ]
        tagged = _tag_provider(raw_items, "my_module")
        self.assertEqual(tagged[0]["__provider__"], "my_module")
        self.assertEqual(tagged[0]["__providers__"], ["my_module"])
        self.assertEqual(tagged[1]["__provider__"], "custom_donor")
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

        docs_entry = merged["spaces"]["docs"]
        self.assertEqual(docs_entry["include"], ["a/docs", "b/docs"])
        self.assertEqual(docs_entry["file_patterns"], ["*.rst"])
        self.assertEqual(docs_entry["description"], "from mod_a")
        self.assertEqual(docs_entry["__providers__"], ["mod_a", "mod_b"])
        self.assertEqual(docs_entry["__provider__"], "mod_b")

        single_entry = merged["unique_point"]["singleton"]
        self.assertEqual(single_entry["description"], "owned by mod_a")
        self.assertEqual(single_entry["include"], ["a/single"])
        self.assertEqual(single_entry["__providers__"], ["mod_a"])

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

        rep_entry = merged["replace_point"]["item"]
        self.assertNotIn("description", rep_entry)
        self.assertNotIn("file_patterns", rep_entry)
        self.assertEqual(rep_entry["include"], ["b/new"])
        self.assertEqual(rep_entry["__providers__"], ["mod_a", "mod_b"])
        self.mark_passed()

    def test_contributes_get_sdk(self):
        """Verify core.contributes.get SDK."""
        core_data = contributes.get("core")
        self.assertIsInstance(core_data, dict)
        self.assertIn("commands", core_data)

        schemes = contributes.get("core", "uri_schemes", default=[])
        self.assertIsInstance(schemes, list)

        with uri.module_scope("core"):
            mod_data = contributes.get(uri.get_module_context())
            self.assertEqual(mod_data, core_data)
        self.mark_passed()

    def test_contribute_json_override_and_local_ignored(self):
        """Verify project contribute.json overrides contributes, and contribute.local.json is ignored."""
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
            vfs.write_json("config://core/contribute.json", proj_contrib)
            vfs.write_json("config://core/contribute.local.json", {
                "commands": {
                    "ignored_local_cmd": {"description": "should not appear"}
                }
            })

            res = self.aggregator.scan_and_inject()
            core_res = res.get("core", {})
            commands = core_res.get("commands", {})

            self.assertIn("custom_override_cmd", commands)
            self.assertEqual(commands["custom_override_cmd"]["description"], "Project specific command override")
            self.assertNotIn("ignored_local_cmd", commands)
        finally:
            for u in ("config://core/contribute.json", "config://core/contribute.local.json"):
                vfs.remove(u, missing_ok=True)
            self.aggregator.scan_and_inject()
        self.mark_passed()


@require(Requirement.ENV)
class TestContributesJIT(YSCBTestCase):
    """Unit tests for core.contributes JIT Freshness Gate and Auto Self-Healing."""

    def setUp(self):
        super().setUp()
        self.agg = ContributesAggregator()

    def test_clean_status_and_latency(self):
        """驗證 Clean 狀態下嗅探比對耗時直接返回 False。"""
        self.agg.scan_and_inject()

        start = time.perf_counter()
        is_dirty, _ = _is_contributes_dirty("core")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        self.assertFalse(is_dirty)
        self.assertLess(elapsed_ms, 200.0)
        self.mark_passed()

    def test_auto_self_healing_on_mtime_change(self):
        """驗證檔案變更後 _is_contributes_dirty 返回 True，get() 自動自愈聚合。"""
        self.agg.scan_and_inject()
        is_dirty_init, _ = _is_contributes_dirty("core")
        self.assertFalse(is_dirty_init)

        cfg_uri = "config://core/contribute.json"
        has_orig = vfs.exists(cfg_uri)
        orig_data = vfs.read_json(cfg_uri) if has_orig else None

        try:
            test_ts = time.time()
            new_data = orig_data.copy() if (orig_data and isinstance(orig_data, dict)) else {}
            new_data["jit_test_stamp"] = test_ts

            vfs.write_json(cfg_uri, new_data)
            _bump_mtime(cfg_uri, 2.0)

            is_dirty, _ = _is_contributes_dirty("core")
            self.assertTrue(is_dirty)

            val = get("core", "jit_test_stamp")
            self.assertEqual(val, test_ts)

            is_dirty_after, _ = _is_contributes_dirty("core")
            self.assertFalse(is_dirty_after)
        finally:
            if has_orig:
                vfs.write_json(cfg_uri, orig_data)
            else:
                vfs.remove(cfg_uri, missing_ok=True)
            self.agg.scan_and_inject()

        self.mark_passed()

    def test_missing_cache_triggers_dirty(self):
        """驗證快取遺失或刪除時直接判定為 dirty。"""
        meta_uri = _get_contributes_meta_uri()
        if vfs.exists(meta_uri):
            vfs.remove(meta_uri)

        is_dirty, _ = _is_contributes_dirty("core")
        self.assertTrue(is_dirty)
        self.mark_passed()

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
            vfs.write_json(cfg_uri, new_data)
            _bump_mtime(cfg_uri, 2.0)

            resolved = uri.resolve("custom.jittest://sub", interactive=False)
            self.assertTrue(resolved.replace("\\", "/").endswith(".cache/jittest/sub"))

            uri._URI_REENTRANCY.active = True
            try:
                reentrant_res = uri._get_merged_uri_schemes(uri.resolve_yscb_root())
                self.assertIsInstance(reentrant_res, (list, dict))
            finally:
                uri._URI_REENTRANCY.active = False
        finally:
            if has_orig:
                vfs.write_json(cfg_uri, orig_data)
            else:
                vfs.remove(cfg_uri, missing_ok=True)
            self.agg.scan_and_inject()
            uri._SCHEMES_CACHE.clear()

        self.mark_passed()

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

            vfs.write_json(loc_uri, {"custom.greeting": "Hello v2 with updated length"})
            _bump_mtime(loc_uri, 2.0)
            is_dirty_after, _ = _is_contributes_dirty("core")
            self.assertTrue(is_dirty_after)
        finally:
            vfs.remove(loc_uri, missing_ok=True)
            if has_orig:
                vfs.write_json(cfg_uri, orig_data)
            else:
                vfs.remove(cfg_uri, missing_ok=True)
            self.agg.scan_and_inject()

        self.mark_passed()

    def test_in_memory_cache_and_invalidation(self):
        """驗證 contributes.get() 於時窗內連續呼叫 10 次僅觸發 1 次輸入掃描，且 invalidate_cache() / scan_and_inject() 立即刷新快取。"""
        self.agg.scan_and_inject()
        contributes.invalidate_cache()

        orig_scan = contributes._scan_contributes_inputs
        with patch("core.contributes._scan_contributes_inputs", wraps=orig_scan) as mock_scan:
            results = [contributes.get("core", "commands") for _ in range(10)]
            self.assertEqual(mock_scan.call_count, 1)
            for r in results:
                self.assertIsInstance(r, dict)
                self.assertEqual(r, results[0])

            contributes.invalidate_cache("core")
            after_inv = contributes.get("core", "commands")
            self.assertEqual(mock_scan.call_count, 2)
            self.assertEqual(after_inv, results[0])

        merged_uri = "cache://core/contributes.merged.json"
        if vfs.exists(merged_uri):
            vfs.remove(merged_uri)
        repaired = contributes.get("core", "commands")
        self.assertIsInstance(repaired, dict)
        self.assertTrue(vfs.exists(merged_uri))

        snap_inputs = contributes._scan_contributes_inputs()
        host_cfg_abs = uri.resolve("yscb.host://yscb.config.json", interactive=False)
        if os.path.isfile(host_cfg_abs):
            self.assertIn(os.path.abspath(host_cfg_abs), snap_inputs)
        self.mark_passed()
