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

    def test_core_1_2_7_x_migration_local_config_and_gitignore_dynamic(self):
        """驗證 core 1.2.7.x 遷移腳本對 config*.local.json 與 .cache/core/gitignore_dynamic.json 的無損冪等搬移與合併。"""
        import importlib.util
        import shutil
        import tempfile

        mig_script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts",
            "migrations",
            "1.2.7.x.py",
        )
        self.assertTrue(os.path.isfile(mig_script_path))
        spec = importlib.util.spec_from_file_location("_core_mig_1_2_7_x", mig_script_path)
        self.assertIsNotNone(spec)
        mig_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig_mod)

        tmp_yscb = tempfile.mkdtemp(prefix="test_core_127_mig_")
        try:
            # 1. 準備舊版 config/<mod>/config.local.json (含直接搬移與目標已存在時的覆寫合併)
            os.makedirs(os.path.join(tmp_yscb, "config", "core"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, ".config.local", "core"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, "config", "server"), exist_ok=True)

            with open(os.path.join(tmp_yscb, "config", "core", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"locale": ["en"], "custom_flag": True}, f)
            with open(os.path.join(tmp_yscb, ".config.local", "core", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"locale": ["zh"], "seeded_only": 1}, f)
            with open(os.path.join(tmp_yscb, "config", "server", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"port": 9999}, f)

            # 2. 準備舊版 .cache/core/gitignore_dynamic.json (測試新路徑不存在時直接搬移)
            legacy_gi_dir = os.path.join(tmp_yscb, ".cache", "core")
            storage_local_core = os.path.join(tmp_yscb, ".storage.local", "core")
            os.makedirs(legacy_gi_dir, exist_ok=True)
            legacy_gi_file = os.path.join(legacy_gi_dir, "gitignore_dynamic.json")
            target_gi_file = os.path.join(storage_local_core, "gitignore_dynamic.json")

            with open(legacy_gi_file, "w", encoding="utf-8") as f:
                json.dump({"agents-workflow": ["/.agents/skills/"]}, f)

            ctx = {
                "yscb_dir": tmp_yscb,
                "storage_local_dir": storage_local_core,
            }
            self.assertTrue(mig_mod.migrate(ctx))

            # 驗證 config*.local.json 已搬移且舊檔已清除
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "core", "config.local.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "server", "config.local.json")))
            with open(os.path.join(tmp_yscb, ".config.local", "core", "config.local.json"), "r", encoding="utf-8") as f:
                merged_core_cfg = json.load(f)
            self.assertEqual(merged_core_cfg["locale"], ["en"])
            self.assertTrue(merged_core_cfg["custom_flag"])
            self.assertEqual(merged_core_cfg["seeded_only"], 1)

            with open(os.path.join(tmp_yscb, ".config.local", "server", "config.local.json"), "r", encoding="utf-8") as f:
                server_cfg = json.load(f)
            self.assertEqual(server_cfg["port"], 9999)

            # 驗證 gitignore_dynamic.json 已搬移至 .storage.local/core/ 且舊檔已刪除
            self.assertFalse(os.path.exists(legacy_gi_file))
            self.assertTrue(os.path.isfile(target_gi_file))
            with open(target_gi_file, "r", encoding="utf-8") as f:
                gi_data = json.load(f)
            self.assertEqual(gi_data, {"agents-workflow": ["/.agents/skills/"]})

            # 3. 驗證當新路徑已存在且舊路徑也有殘留檔時，合併字典鍵值並刪除舊檔
            with open(target_gi_file, "w", encoding="utf-8") as f:
                json.dump({"agents-workflow": ["/.agents/new/"], "vscode-support": ["/.vscode/schemas/"]}, f)
            with open(legacy_gi_file, "w", encoding="utf-8") as f:
                json.dump({"agents-workflow": ["/.agents/skills/"], "legacy-mod": ["/legacy/"]}, f)

            self.assertTrue(mig_mod.migrate(ctx))
            self.assertFalse(os.path.exists(legacy_gi_file))
            with open(target_gi_file, "r", encoding="utf-8") as f:
                merged_gi = json.load(f)
            self.assertEqual(merged_gi["vscode-support"], ["/.vscode/schemas/"])
            self.assertEqual(merged_gi["legacy-mod"], ["/legacy/"])
            self.assertEqual(merged_gi["agents-workflow"], ["/.agents/new/", "/.agents/skills/"])

            # 4. 再次執行維持冪等
            self.assertTrue(mig_mod.migrate(ctx))
        finally:
            shutil.rmtree(tmp_yscb, ignore_errors=True)
        self.mark_passed()

if __name__ == "__main__":
    unittest.main()
