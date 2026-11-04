"""
Unit and boundary tests for `module:vscode-support` (`SettingsProjector`, `SchemaCompiler`, CLI, and lifecycle hooks).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from core import uri, vfs
from core.context import ExecutionContext
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from vscode_support.projector import SettingsProjector
from vscode_support.schema_compiler import SchemaCompiler


@require(Requirement.ENV)
class TestVSCodeSupport(YSCBTestCase):
    """驗證 `module:vscode-support` 之設定投影、穩定連結、單檔 Schema 編譯與完全可逆還原。"""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_vscode_support_")
        self.project_root = os.path.join(self.temp_dir, "project")
        self.yscb_dir = os.path.join(self.project_root, ".yscb")
        os.makedirs(self.project_root, exist_ok=True)
        os.makedirs(self.yscb_dir, exist_ok=True)
        self.projector = SettingsProjector(yscb_dir=self.yscb_dir)
        self.compiler = self.projector.schema_compiler
        self.pip_mgr = self.projector.pip_mgr

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_ft_01_auto_create_vscode_dir_and_stable_site_packages_link(self) -> None:
        """自動建立 project://.vscode/ 並恆定寫入 current-site-packages 穩定連結路徑。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        self.assertFalse(os.path.exists(vscode_dir))

        ok = self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        self.assertTrue(ok)
        self.assertTrue(os.path.isdir(vscode_dir))

        settings_path = os.path.join(vscode_dir, "settings.json")
        data = vfs.read_json(settings_path)
        extra = data.get("python.analysis.extraPaths", [])
        self.assertEqual(extra, ["./.yscb/.venv/current-site-packages"])

        # 切換 Python 版本 py311 -> settings.json 的 extraPaths 仍維持不變
        self.projector.sync_vscode_settings(self.project_root, py_tag="py311")
        data_after = vfs.read_json(settings_path)
        self.assertEqual(data_after.get("python.analysis.extraPaths"), ["./.yscb/.venv/current-site-packages"])

        self.mark_passed()

    def test_ft_02_stable_path_preserved_when_symlink_unsupported(self) -> None:
        """當受限容器檔案系統 (如 virtiofs) 不支援建立 Symlink 時，extraPaths 仍維持 current-site-packages 零變動。"""
        with patch.object(self.projector, "ensure_stable_site_packages_link", return_value=None):
            ok = self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
            self.assertTrue(ok)
            settings_path = os.path.join(self.project_root, ".vscode", "settings.json")
            data = vfs.read_json(settings_path)
            extra = data.get("python.analysis.extraPaths", [])
            self.assertEqual(extra, ["./.yscb/.venv/current-site-packages"])
        self.mark_passed()

    def test_ft_03_schema_compiler_contributes_and_recursive_types(self) -> None:
        """驗證 _format.json 轉譯為 Draft-07 Schema（含自遞迴 $CommandNode、萬用鍵 *、float default 與外層包裹相容）。"""
        fmt_data = {
            "_types": {
                "CommandNode": {
                    "description": "str!",
                    "tier": "enum(safe, conditional, gated)? = conditional",
                    "weight": "float? = 1.5",
                    "offset": "int? = -1",
                    "tags": "list[str]! | extend",
                    "cmd": {
                        "*": "$CommandNode",
                    },
                }
            },
            "commands": {
                "description": "CLI commands tree",
                "merge": "merge",
                "format": {
                    "module_alias": "list[str]?",
                    "cmd": {
                        "*": "$CommandNode",
                    },
                },
            },
            "locales": {
                "description": "Locale map",
                "format": {
                    "definition": "path! @desc(語意契約檔相對路徑 (必填))",
                    "*": "str!",
                },
            },
        }
        schema = self.compiler.compile_contributes_schema("demo-mod", fmt_data)
        self.assertEqual(schema["$schema"], "http://json-schema.org/draft-07/schema#")
        self.assertIn("CommandNode", schema["$defs"])
        cmd_node_def = schema["$defs"]["CommandNode"]
        self.assertIn("description", cmd_node_def["required"])
        self.assertIn("tags", cmd_node_def["required"])
        self.assertEqual(cmd_node_def["properties"]["tier"]["enum"], ["safe", "conditional", "gated"])
        self.assertEqual(cmd_node_def["properties"]["tier"]["default"], "conditional")
        self.assertEqual(cmd_node_def["properties"]["weight"]["type"], "number")
        self.assertEqual(cmd_node_def["properties"]["weight"]["default"], 1.5)
        self.assertEqual(cmd_node_def["properties"]["offset"]["type"], "integer")
        self.assertEqual(cmd_node_def["properties"]["offset"]["default"], -1)
        self.assertEqual(cmd_node_def["properties"]["cmd"]["additionalProperties"], {"$ref": "#/$defs/CommandNode"})

        # 驗證固定鍵 + "*" 混合字典與 path 型別 defaultSnippets 與 @desc(...) 說明
        locales_prop = schema["properties"]["locales"]
        self.assertEqual(locales_prop["required"], ["definition"])
        self.assertEqual(locales_prop["additionalProperties"], {"type": "string"})
        self.assertEqual(locales_prop["properties"]["definition"]["description"], "語意契約檔相對路徑 (必填)")
        self.assertIn("語意契約檔相對路徑 (必填)", locales_prop["properties"]["definition"]["markdownDescription"])
        self.assertIn("defaultSnippets", locales_prop["properties"]["definition"])
        snippet_labels = [s["label"] for s in locales_prop["properties"]["definition"]["defaultSnippets"]]
        self.assertIn("project://", snippet_labels)
        self.assertIn("config://", snippet_labels)
        self.assertIn("config.local://", snippet_labels)
        self.assertIn("storage.local://", snippet_labels)

        # 驗證支援外層包裹 {"demo-mod": { ... }}
        self.assertIn("demo-mod", schema["properties"])
        self.assertIn("commands", schema["properties"]["demo-mod"]["properties"])
        self.mark_passed()

    def test_ft_04_schema_compiler_config_from_mirror_zip_and_orphan_cleanup(self) -> None:
        """驗證自 module.mirror:// 讀取 configurable/config.project.json 推導 Schema 並自動清理孤兒 Schema。"""
        mirror_mod_dir = os.path.join(self.yscb_dir, ".mirror", "sample-mod")
        os.makedirs(mirror_mod_dir, exist_ok=True)
        zip_path = os.path.join(mirror_mod_dir, "1.0.0.0.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(
                "configurable/config.project.json",
                json.dumps(
                    {
                        "project_root": "!undefined",
                        "enable_feature": True,
                        "timeout_ms": 3000,
                        "ratio": 0.75,
                        "tags": ["a", "b"],
                    }
                ),
            )

        tpl = self.compiler._load_module_config_template("sample-mod")
        self.assertIsNotNone(tpl)
        cfg_schema = self.compiler.compile_config_schema("sample-mod", tpl or {})
        self.assertEqual(cfg_schema["required"], ["project_root"])
        self.assertEqual(cfg_schema["properties"]["project_root"]["not"], {"const": "!undefined"})
        self.assertEqual(cfg_schema["properties"]["enable_feature"], {"type": "boolean", "default": True})
        self.assertEqual(cfg_schema["properties"]["timeout_ms"], {"type": "integer", "default": 3000})
        self.assertEqual(cfg_schema["properties"]["ratio"], {"type": "number", "default": 0.75})

        # 驗證 configurable/_format.json 同構 DSL 編譯 (含 uri! 與 @desc(...))
        cfg_fmt = {
            "paths": {
                "plans": "uri! @desc(活躍計畫目錄路徑)",
                "roadmap": "uri? = project://plans/roadmap @desc(路線圖目錄路徑)",
            },
            "enable_agents_md": "bool? = true @desc(是否生成 AGENTS.md)",
        }
        fmt_cfg_schema = self.compiler.compile_config_schema("sample-mod", template_data=tpl, fmt_data=cfg_fmt)
        self.assertFalse(fmt_cfg_schema["additionalProperties"])
        self.assertEqual(fmt_cfg_schema["properties"]["enable_agents_md"]["description"], "是否生成 AGENTS.md")
        self.assertEqual(fmt_cfg_schema["properties"]["paths"]["required"], ["plans"])
        self.assertEqual(
            fmt_cfg_schema["properties"]["paths"]["properties"]["plans"]["description"],
            "活躍計畫目錄路徑",
        )
        self.assertIn("defaultSnippets", fmt_cfg_schema["properties"]["paths"]["properties"]["plans"])

        # 預先放一個孤兒 Schema 檔案與舊版子目錄 .gitignore，驗證 sync_all_schemas 會自動刪除它們
        orphan_dir = os.path.join(self.project_root, ".vscode", "schemas", "contributes")
        os.makedirs(orphan_dir, exist_ok=True)
        orphan_file = os.path.join(orphan_dir, "non_existent_orphan_mod.schema.json")
        vfs.write_json(orphan_file, {"type": "object"})
        self.assertTrue(os.path.isfile(orphan_file))

        gi_file = os.path.join(self.project_root, ".vscode", "schemas", ".gitignore")
        vfs.write_text(gi_file, "*\n")
        self.assertTrue(os.path.isfile(gi_file))

        bindings = self.compiler.sync_all_schemas(self.project_root)
        self.assertFalse(os.path.exists(orphan_file))
        self.assertTrue(len(bindings) >= 2)
        self.assertFalse(os.path.exists(gi_file))
        self.mark_passed()

    def test_ft_05_soft_merge_preserves_user_settings_and_revert_cleans_all(self) -> None:
        """驗證保留使用者自訂 extraPaths、interpreter 與 json.schemas，且 revert 100% 乾淨還原。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")

        user_custom_schema = {"fileMatch": ["my.custom.json"], "url": "./my.schema.json"}
        initial_settings = {
            "editor.tabSize": 2,
            "python.defaultInterpreterPath": "./.venv/bin/python",
            "python.analysis.extraPaths": ["./custom_src"],
            "json.schemas": [user_custom_schema],
        }
        vfs.write_json(settings_path, initial_settings)

        ok = self.projector.sync_vscode_settings(self.project_root, extra_paths=["./extra_mod"], py_tag="py312")
        self.assertTrue(ok)

        merged = vfs.read_json(settings_path)
        self.assertEqual(merged.get("editor.tabSize"), 2)
        self.assertEqual(merged.get("python.defaultInterpreterPath"), "./.venv/bin/python")
        self.assertIn("./custom_src", merged.get("python.analysis.extraPaths", []))
        self.assertIn("./extra_mod", merged.get("python.analysis.extraPaths", []))
        self.assertIn(user_custom_schema, merged.get("json.schemas", []))
        self.assertTrue(len(merged.get("json.schemas", [])) > 1)
        self.assertIn("_yscb_managed", merged)

        # Zero-Touch 測試：再次同步時不變更 mtime
        mtime_1 = os.stat(settings_path).st_mtime_ns
        self.projector.sync_vscode_settings(self.project_root, extra_paths=["./extra_mod"], py_tag="py312")
        mtime_2 = os.stat(settings_path).st_mtime_ns
        self.assertEqual(mtime_1, mtime_2)

        # 執行 revert：必須 100% 還原至 initial_settings 且刪除 .vscode/schemas/ 與穩定連結
        rev_ok = self.projector.revert_vscode_settings(self.project_root)
        self.assertTrue(rev_ok)
        reverted = vfs.read_json(settings_path)
        self.assertNotIn("_yscb_managed", reverted)
        self.assertEqual(reverted.get("editor.tabSize"), 2)
        self.assertEqual(reverted.get("python.defaultInterpreterPath"), "./.venv/bin/python")
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["./custom_src"])
        self.assertEqual(reverted.get("json.schemas"), [user_custom_schema])
        self.assertFalse(os.path.exists(os.path.join(vscode_dir, "schemas")))
        self.assertFalse(os.path.lexists(self.projector.get_stable_link_path()))
        self.mark_passed()

    def test_et_01_jsonc_settings_preserved_and_hook_lifecycle(self) -> None:
        """驗證含註解與尾隨逗號之 JSONC settings.json 自動備份 .bak 並平滑軟合併，且不可恢復之損毀語法不覆寫原檔。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        bak_path = settings_path + ".bak"
        raw_jsonc = b'{\n  // user comment\n  "editor.tabSize": 4,\n  "custom.url": "https://example.com//not-a-comment",\n}\n'
        with open(settings_path, "wb") as f:
            f.write(raw_jsonc)

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        self.assertTrue(os.path.isfile(bak_path))
        with open(bak_path, "rb") as f:
            self.assertEqual(f.read(), raw_jsonc)
        merged = vfs.read_json(settings_path)
        self.assertEqual(merged.get("editor.tabSize"), 4)
        self.assertEqual(merged.get("custom.url"), "https://example.com//not-a-comment")
        self.assertIn("_yscb_managed", merged)

        # 不可恢復之損毀語法：備份至 .bak 且回傳 False 不覆寫原檔
        corrupt_bytes = b'{\n  "broken": [1, 2\n'
        with open(settings_path, "wb") as f:
            f.write(corrupt_bytes)
        self.assertFalse(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        with open(settings_path, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)
        with open(bak_path, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)

        # 測試 hook.core.py 之 on_remove 僅在移除目標含 vscode-support 時觸發 revert
        import importlib.util

        hook_path = os.path.join(str(_pkg_root), "scripts", "hook.core.py")
        spec = importlib.util.spec_from_file_location("_test_vsc_hook", hook_path)
        self.assertIsNotNone(spec)
        hook_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(hook_mod)  # type: ignore[union-attr]

        # 移除其他模組時應回傳 False 不觸發 revert
        ctx_other = ExecutionContext("core", "remove", ["other-module"])
        self.assertFalse(hook_mod.on_remove(ctx_other))
        self.mark_passed()

    def test_ft_06_cli_status_sync_revert_commands(self) -> None:
        """驗證 scripts/cli.py 之 status / sync / revert (含 --json) 入口與合約。"""
        import importlib.util
        import io
        from contextlib import redirect_stdout

        cli_path = os.path.join(str(_pkg_root), "scripts", "cli.py")
        spec = importlib.util.spec_from_file_location("_test_vsc_cli", cli_path)
        self.assertIsNotNone(spec)
        cli_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(cli_mod)  # type: ignore[union-attr]

        with patch("core.uri.resolve", return_value=self.project_root), patch(
            "vscode_support.projector.SettingsProjector",
            side_effect=lambda *a, **kw: SettingsProjector(yscb_dir=self.yscb_dir),
        ):
            buf_sync = io.StringIO()
            with redirect_stdout(buf_sync):
                rc_sync = cli_mod.sync(["--json"])
            self.assertEqual(rc_sync, 0)
            sync_payload = json.loads(buf_sync.getvalue())
            self.assertTrue(sync_payload.get("synced"))
            self.assertTrue(sync_payload.get("settings_managed"))

            buf_status = io.StringIO()
            with redirect_stdout(buf_status):
                rc_status = cli_mod.status(["--json"])
            self.assertEqual(rc_status, 0)
            status_payload = json.loads(buf_status.getvalue())
            self.assertTrue(status_payload.get("vscode_dir_exists"))
            self.assertTrue(status_payload.get("managed_schema_count", 0) >= 2)

            buf_rev = io.StringIO()
            with redirect_stdout(buf_rev):
                rc_rev = cli_mod.revert(["--json"])
            self.assertEqual(rc_rev, 0)
            rev_payload = json.loads(buf_rev.getvalue())
            self.assertTrue(rev_payload.get("reverted"))

        self.mark_passed()

    def test_ft_07_module_and_source_extra_paths_projection_and_revert(self) -> None:
        """驗證自動投影已安裝模組 (.modules/<mod>) 與源碼 (source/<mod>) 至 extraPaths，動態調整 analysisExclude 並支援 100% 乾淨還原。"""
        mods_dir = os.path.join(self.yscb_dir, ".modules")
        src_dir = os.path.join(self.yscb_dir, "source")
        os.makedirs(os.path.join(mods_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(mods_dir, "ast"), exist_ok=True)
        os.makedirs(os.path.join(mods_dir, "file-space"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "ast"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "knowledge-db"), exist_ok=True)

        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        vfs.write_json(settings_path, {"python.analysis.extraPaths": ["./user_custom"]})

        # Case 1: 同時包含 .modules/<mod> 與 source/<mod> 時，同名模組優先取 source/<mod>，且因含 .modules/ 故省略 **/.modules/** 排除
        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        merged = vfs.read_json(settings_path)
        self.assertEqual(
            merged.get("python.analysis.extraPaths"),
            [
                "./user_custom",
                "./.yscb/.venv/current-site-packages",
                "./.yscb/.modules/core",
                "./.yscb/source/ast",
                "./.yscb/.modules/file-space",
                "./.yscb/source/knowledge-db",
            ],
        )
        self.assertNotIn("**/.modules/**", merged.get("python.analysis.exclude", []))
        self.assertIn("**/.config.local/**", merged.get("python.analysis.exclude", []))
        self.assertIn("**/.storage.local/**", merged.get("python.analysis.exclude", []))

        # Case 2: 若所有模組皆有對應 source/<mod>，extraPaths 全部指向 source/<mod> 且恢復 **/.modules/** 排除
        os.makedirs(os.path.join(src_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "file-space"), exist_ok=True)
        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        merged_all_src = vfs.read_json(settings_path)
        self.assertEqual(
            merged_all_src.get("python.analysis.extraPaths"),
            [
                "./user_custom",
                "./.yscb/.venv/current-site-packages",
                "./.yscb/source/core",
                "./.yscb/source/ast",
                "./.yscb/source/file-space",
                "./.yscb/source/knowledge-db",
            ],
        )
        self.assertIn("**/.modules/**", merged_all_src.get("python.analysis.exclude", []))

        # Case 3: revert_vscode_settings 必須 100% 乾淨還原為僅保留 ./user_custom
        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        reverted = vfs.read_json(settings_path)
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["./user_custom"])
        self.assertNotIn("_yscb_managed", reverted)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

