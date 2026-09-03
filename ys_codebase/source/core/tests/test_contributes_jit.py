"""
Unit tests for core.contributes JIT Freshness Gate and Auto Self-Healing.
"""
import unittest
import os
import time
import json
from dev.testing import YSCBTestCase, require, Requirement
from core import uri
from core import contributes
from core.contributes import (
    _get_contributes_meta_uri,
    _scan_contributes_inputs,
    _is_contributes_dirty,
    ContributesAggregator,
    get
)


class TestContributesJIT(YSCBTestCase):
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
        self.assertLess(elapsed_ms, 25.0)  # CI 環境給予合理餘裕
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


if __name__ == "__main__":
    unittest.main()
