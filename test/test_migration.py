#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test/test_migration.py — 鏈式增量遷移 MigrationRunner 單元測試套件
"""

import sys
import unittest
from pathlib import Path

# 載入 core scripts
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SOURCE_CORE_SCRIPTS = PROJECT_ROOT / "ys_codebase" / "source" / "core" / "scripts"
if str(SOURCE_CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SOURCE_CORE_SCRIPTS))

from migration import MigrationRunner


class TestMigrationRunner(unittest.TestCase):
    def test_linear_sequential_execution(self):
        runner = MigrationRunner()
        executed_milestones = []

        @runner.step("1.2.x")
        def step_1_2(root, mod):
            executed_milestones.append("1.2.x")

        @runner.step("1.1.x")
        def step_1_1(root, mod):
            executed_milestones.append("1.1.x")

        @runner.step("2.0.x")
        def step_2_0(root, mod):
            executed_milestones.append("2.0.x")

        # 跨代升級：v1.0.0 -> v1.2.5 (應依序執行 1.1.x 與 1.2.x，不執行 2.0.x)
        res = runner.run("1.0.0", "1.2.5")
        self.assertEqual(res, ["1.1.x", "1.2.x"])
        self.assertEqual(executed_milestones, ["1.1.x", "1.2.x"])

    def test_same_minor_no_migration(self):
        runner = MigrationRunner()
        executed = []

        @runner.step("1.1.x")
        def step_1_1(root, mod):
            executed.append("1.1.x")

        # 同代升級：v1.1.0 -> v1.1.5 (不需遷移)
        res = runner.run("1.1.0", "1.1.5")
        self.assertEqual(res, [])
        self.assertEqual(executed, [])

    def test_exception_propagation(self):
        runner = MigrationRunner()

        @runner.step("1.1.x")
        def failing_step(root, mod):
            raise ValueError("模擬遷移失敗，觸發快照回滾")

        with self.assertRaises(ValueError):
            runner.run("1.0.0", "1.1.0")


if __name__ == "__main__":
    unittest.main()
