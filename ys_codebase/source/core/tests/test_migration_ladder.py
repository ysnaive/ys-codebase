"""
Unit tests for Incremental Migration Ladder Subsystem and Major Boundary Lock.
"""
import json
import os
import shutil
import tempfile
import unittest

from core import uri, vfs
from core.engine import AtomicEngine
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from tests import load_core_migration_module


@require(Requirement.ENV)
class TestMigrationLadder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()
        self.test_mod = "test_mod_mig"
        self.mig_dir = uri.resolve(f"module://{self.test_mod}/scripts/migrations")
        os.makedirs(self.mig_dir, exist_ok=True)

    def tearDown(self):
        mod_uri = f"module://{self.test_mod}"
        if vfs.exists(mod_uri):
            vfs.rmtree(mod_uri)
        super().tearDown()

    def test_migration_ladder_step_through(self):
        """驗證 1.1 與 1.3 遷移腳本實質依序被呼叫、驗證 ctx 欄位與軌跡，且跨大版本安全略過。"""
        script_11 = (
            "import os, json\n"
            "def migrate(ctx):\n"
            "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
            "    p = os.path.join(ctx['storage_dir'], 'mig_trace.json')\n"
            "    if os.path.isfile(p):\n"
            "        with open(p, 'r', encoding='utf-8') as f:\n"
            "            data = json.load(f)\n"
            "    else:\n"
            "        data = []\n"
            "    data.append([ctx['old_version'], ctx['target_version'], '1.1'])\n"
            "    with open(p, 'w', encoding='utf-8') as f:\n"
            "        json.dump(data, f)\n"
            "    return True\n"
        )
        script_13 = (
            "import os, json\n"
            "def migrate(ctx):\n"
            "    os.makedirs(ctx['storage_dir'], exist_ok=True)\n"
            "    p = os.path.join(ctx['storage_dir'], 'mig_trace.json')\n"
            "    if os.path.isfile(p):\n"
            "        with open(p, 'r', encoding='utf-8') as f:\n"
            "            data = json.load(f)\n"
            "    else:\n"
            "        data = []\n"
            "    data.append([ctx['old_version'], ctx['target_version'], '1.3'])\n"
            "    with open(p, 'w', encoding='utf-8') as f:\n"
            "        json.dump(data, f)\n"
            "    return True\n"
        )

        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(script_11)
        with open(os.path.join(self.mig_dir, "1.3.x.py"), "w", encoding="utf-8") as f:
            f.write(script_13)

        storage_dir = uri.resolve(f"storage://{self.test_mod}")
        trace_path = os.path.join(storage_dir, "mig_trace.json")
        try:
            res = self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.3.0.0")
            self.assertTrue(res)
            self.assertTrue(os.path.isfile(trace_path))
            with open(trace_path, "r", encoding="utf-8") as f:
                records = json.load(f)
            self.assertEqual([r[2] for r in records], ["1.1", "1.3"])
            self.assertEqual(records[0][0], "1.0.0.0")
            self.assertEqual(records[0][1], "1.3.0.0")

            os.remove(trace_path)
            res_major = self.engine.act_migrate(self.test_mod, "1.0.0.0", "2.0.0.0")
            self.assertTrue(res_major)
            self.assertFalse(os.path.isfile(trace_path))
        finally:
            if vfs.exists(f"storage://{self.test_mod}"):
                vfs.rmtree(f"storage://{self.test_mod}")
        self.mark_passed()

    def test_migration_script_failure_raises_runtime_error(self):
        """驗證遷移腳本回傳 False 時 act_migrate 拋出 RuntimeError。"""
        failing_script = "def migrate(ctx):\n    return False\n"
        with open(os.path.join(self.mig_dir, "1.1.x.py"), "w", encoding="utf-8") as f:
            f.write(failing_script)

        with self.assertRaises(RuntimeError):
            self.engine.act_migrate(self.test_mod, "1.0.0.0", "1.1.0.0")
        self.mark_passed()

    def test_core_1_2_7_x_migration_local_config_and_gitignore_dynamic(self):
        """驗證 core 1.2.7.x 遷移腳本對 config*.local.json（含子設定檔、損壞 JSON 容錯與空目錄清理）與 gitignore_dynamic.json 的無損冪等搬移與合併。"""
        mig_mod = load_core_migration_module("1.2.7.x.py")

        tmp_yscb = tempfile.mkdtemp(prefix="test_core_127_mig_")
        try:
            # 1. 準備舊版 config/<mod>/config*.local.json（含 config.sub.local.json 萬用字元匹配與 config.project.json 保留）
            os.makedirs(os.path.join(tmp_yscb, "config", "core"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, ".config.local", "core"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, "config", "server"), exist_ok=True)

            with open(os.path.join(tmp_yscb, "config", "core", "config.project.json"), "w", encoding="utf-8") as f:
                json.dump({"project_root": "./"}, f)
            with open(os.path.join(tmp_yscb, "config", "core", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"locale": ["en"], "custom_flag": True}, f)
            with open(os.path.join(tmp_yscb, "config", "core", "config.sub.local.json"), "w", encoding="utf-8") as f:
                json.dump({"sub_flag": 42}, f)
            with open(os.path.join(tmp_yscb, ".config.local", "core", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"locale": ["zh"], "seeded_only": 1}, f)
            with open(os.path.join(tmp_yscb, "config", "server", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"port": 9999}, f)

            # 2. 準備舊版 .cache/core/gitignore_dynamic.json，並測試省略 storage_local_dir 時之預設路徑推導
            legacy_gi_dir = os.path.join(tmp_yscb, ".cache", "core")
            storage_local_core = os.path.join(tmp_yscb, ".storage.local", "core")
            os.makedirs(legacy_gi_dir, exist_ok=True)
            legacy_gi_file = os.path.join(legacy_gi_dir, "gitignore_dynamic.json")
            target_gi_file = os.path.join(storage_local_core, "gitignore_dynamic.json")

            with open(legacy_gi_file, "w", encoding="utf-8") as f:
                json.dump({"agents-workflow": ["/.agents/skills/"]}, f)

            self.assertTrue(mig_mod.migrate({"yscb_dir": tmp_yscb}))

            # 驗證 config*.local.json 已搬移且舊檔已清除；server 因僅含 config.local.json 搬移後空目錄自動清理，core 因含 config.project.json 保留目錄
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "core", "config.local.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "core", "config.sub.local.json")))
            self.assertTrue(os.path.isdir(os.path.join(tmp_yscb, "config", "core")))
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "server")))

            with open(os.path.join(tmp_yscb, ".config.local", "core", "config.local.json"), "r", encoding="utf-8") as f:
                merged_core_cfg = json.load(f)
            self.assertEqual(merged_core_cfg["locale"], ["en"])
            self.assertTrue(merged_core_cfg["custom_flag"])
            self.assertEqual(merged_core_cfg["seeded_only"], 1)

            with open(os.path.join(tmp_yscb, ".config.local", "core", "config.sub.local.json"), "r", encoding="utf-8") as f:
                sub_cfg = json.load(f)
            self.assertEqual(sub_cfg["sub_flag"], 42)

            with open(os.path.join(tmp_yscb, ".config.local", "server", "config.local.json"), "r", encoding="utf-8") as f:
                server_cfg = json.load(f)
            self.assertEqual(server_cfg["port"], 9999)

            self.assertFalse(os.path.exists(legacy_gi_file))
            self.assertTrue(os.path.isfile(target_gi_file))
            with open(target_gi_file, "r", encoding="utf-8") as f:
                gi_data = json.load(f)
            self.assertEqual(gi_data, {"agents-workflow": ["/.agents/skills/"]})

            # 3. 驗證損壞 JSON 雙向容錯：(a) 目標損壞但舊檔有效 -> 以舊檔覆寫修復並刪除舊檔；(b) 舊檔損壞但目標有效 -> 保留目標並刪除損壞舊檔
            os.makedirs(os.path.join(tmp_yscb, "config", "corrupt_dst_mod"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, ".config.local", "corrupt_dst_mod"), exist_ok=True)
            with open(os.path.join(tmp_yscb, "config", "corrupt_dst_mod", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"recovered": True}, f)
            with open(os.path.join(tmp_yscb, ".config.local", "corrupt_dst_mod", "config.local.json"), "w", encoding="utf-8") as f:
                f.write("{corrupted target json")

            os.makedirs(os.path.join(tmp_yscb, "config", "corrupt_src_mod"), exist_ok=True)
            os.makedirs(os.path.join(tmp_yscb, ".config.local", "corrupt_src_mod"), exist_ok=True)
            with open(os.path.join(tmp_yscb, "config", "corrupt_src_mod", "config.local.json"), "w", encoding="utf-8") as f:
                f.write("{corrupted legacy json")
            with open(os.path.join(tmp_yscb, ".config.local", "corrupt_src_mod", "config.local.json"), "w", encoding="utf-8") as f:
                json.dump({"intact": 123}, f)

            # 4. 驗證 gitignore_dynamic.json 列表與字典深層合併
            with open(target_gi_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "agents-workflow": ["/.agents/new/"],
                        "vscode-support": ["/.vscode/schemas/"],
                        "dict-mod": {"a": 1, "b": 2},
                    },
                    f,
                )
            with open(legacy_gi_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "agents-workflow": ["/.agents/skills/"],
                        "legacy-mod": ["/legacy/"],
                        "dict-mod": {"b": 99, "c": 3},
                    },
                    f,
                )

            ctx = {"yscb_dir": tmp_yscb, "storage_local_dir": storage_local_core}
            self.assertTrue(mig_mod.migrate(ctx))

            with open(os.path.join(tmp_yscb, ".config.local", "corrupt_dst_mod", "config.local.json"), "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"recovered": True})
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "corrupt_dst_mod")))

            with open(os.path.join(tmp_yscb, ".config.local", "corrupt_src_mod", "config.local.json"), "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"intact": 123})
            self.assertFalse(os.path.exists(os.path.join(tmp_yscb, "config", "corrupt_src_mod")))

            self.assertFalse(os.path.exists(legacy_gi_file))
            with open(target_gi_file, "r", encoding="utf-8") as f:
                merged_gi = json.load(f)
            self.assertEqual(merged_gi["vscode-support"], ["/.vscode/schemas/"])
            self.assertEqual(merged_gi["legacy-mod"], ["/legacy/"])
            self.assertEqual(merged_gi["agents-workflow"], ["/.agents/new/", "/.agents/skills/"])
            self.assertEqual(merged_gi["dict-mod"], {"a": 1, "b": 2, "c": 3})

            # 5. 再次執行維持冪等
            self.assertTrue(mig_mod.migrate(ctx))
        finally:
            shutil.rmtree(tmp_yscb, ignore_errors=True)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
