"""
Unit tests for Incremental Migration Ladder Subsystem and Major Boundary Lock.
"""
import os
import sys
import json
import unittest
from core import uri
from core.engine import AtomicEngine
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

class TestMigrationLadder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()
        self.test_mod = "test_mod_mig"
        self.mig_dir = uri.resolve(f"module://{self.test_mod}/scripts/migrations")
        os.makedirs(self.mig_dir, exist_ok=True)

    def tearDown(self):
        super().tearDown()
        mod_uri = f"module://{self.test_mod}"
        if uri.exists(mod_uri):
            uri.rmtree(mod_uri)

    def test_migration_ladder_step_through(self):
        # Create migration scripts for 1.1 and 1.3 (skip 1.2)
        called = []
        script_11 = "def migrate(ctx):\n    return True\n"
        script_13 = "def migrate(ctx):\n    return True\n"
        
        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(script_11)
        with open(os.path.join(self.mig_dir, "1.3.x.py"), "w", encoding="utf-8") as f:
            f.write(script_13)

        # Execute migration 1.0.0.0 -> 1.3.0.0
        res = self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.3.0.0")
        self.assertTrue(res)

    def test_migration_script_failure_raises_runtime_error(self):
        # Create a failing migration script
        failing_script = "def migrate(ctx):\n    return False\n"
        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(failing_script)

        with self.assertRaises(RuntimeError):
            self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.1.0.0")

if __name__ == "__main__":
    unittest.main()
