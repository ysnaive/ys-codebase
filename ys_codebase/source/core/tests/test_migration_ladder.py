"""
Unit tests for Incremental Migration Ladder Subsystem and Major Boundary Lock.
"""
import os
import sys
import json
import unittest
from core import uri, vfs
from core.engine import AtomicEngine
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

@require(Requirement.ENV)
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
        if vfs.exists(mod_uri):
            vfs.rmtree(mod_uri)

    def test_migration_ladder_step_through(self):
        """T-01 實質化：驗證 1.1 與 1.3 遷移腳本實質依序被呼叫、驗證 ctx 欄位與軌跡，且跨大版本安全略過。"""
        script_11 = (
            "import os, json\n"
            "def migrate(ctx):\n"
            "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
            "    p = os.path.join(ctx['storage_dir'], 'mig_trace.json')\n"
            "    data = json.load(open(p)) if os.path.isfile(p) else []\n"
            "    data.append([ctx['old_version'], ctx['target_version'], '1.1'])\n"
            "    json.dump(data, open(p, 'w'))\n"
            "    return True\n"
        )
        script_13 = (
            "import os, json\n"
            "def migrate(ctx):\n"
            "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
            "    p = os.path.join(ctx['storage_dir'], 'mig_trace.json')\n"
            "    data = json.load(open(p)) if os.path.isfile(p) else []\n"
            "    data.append([ctx['old_version'], ctx['target_version'], '1.3'])\n"
            "    json.dump(data, open(p, 'w'))\n"
            "    return True\n"
        )

        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(script_11)
        with open(os.path.join(self.mig_dir, "1.3.x.py"), "w", encoding="utf-8") as f:
            f.write(script_13)

        storage_dir = uri.resolve(f"storage://{self.test_mod}")
        trace_path = os.path.join(storage_dir, "mig_trace.json")
        try:
            # 1. Execute migration 1.0.0.0 -> 1.3.0.0 (1.1 & 1.3 executed in order, 1.2 skipped)
            res = self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.3.0.0")
            self.assertTrue(res)
            self.assertTrue(os.path.isfile(trace_path))
            with open(trace_path, "r", encoding="utf-8") as f:
                records = json.load(f)
            self.assertEqual([r[2] for r in records], ["1.1", "1.3"])
            self.assertEqual(records[0][0], "1.0.0.0")
            self.assertEqual(records[0][1], "1.3.0.0")

            # 2. Major version jump (1.0.0.0 -> 2.0.0.0) must NOT trigger 1.x migration scripts
            os.remove(trace_path)
            res_major = self.engine.act_migrate(self.test_mod, "1.0.0.0", "2.0.0.0")
            self.assertTrue(res_major)
            self.assertFalse(os.path.isfile(trace_path))
        finally:
            if vfs.exists(f"storage://{self.test_mod}"):
                vfs.rmtree(f"storage://{self.test_mod}")
        self.mark_passed()


    def test_migration_script_failure_raises_runtime_error(self):
        # Create a failing migration script
        failing_script = "def migrate(ctx):\n    return False\n"
        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(failing_script)

        with self.assertRaises(RuntimeError):
            self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.1.0.0")
        self.mark_passed()

if __name__ == "__main__":
    unittest.main()
