"""
Unit and boundary tests for `module:vscode-support` (`SettingsProjector`, `SchemaCompiler`, CLI, and lifecycle hooks).
"""

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

import vscode_support
from core import vfs
from core.commands import CmdBags, CmdOption
from core.context import ExecutionContext
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from vscode_support import schema_compiler as schema_compiler_mod
from vscode_support.projector import SettingsProjector, strip_jsonc
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

    def _load_script_module(self, script_name: str, mod_alias: str) -> Any:
        """動態載入 `scripts/` 目錄下之腳本模組供測試調用。"""
        script_path = os.path.join(str(_pkg_root), "scripts", script_name)
        spec = importlib.util.spec_from_file_location(mod_alias, script_path)
        self.assertIsNotNone(spec)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _write_settings(self, content: Any) -> str:
        """建立 `.vscode/settings.json` 並寫入字典、字串或原始位元組。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        settings_path = os.path.join(vscode_dir, "settings.json")
        if isinstance(content, dict):
            vfs.write_json(settings_path, content)
        elif isinstance(content, bytes):
            with open(settings_path, "wb") as f:
                f.write(content)
        else:
            vfs.write_text(settings_path, str(content), encoding="utf-8")
        return settings_path

    def _read_settings(self) -> Dict[str, Any]:
        """讀取 `.vscode/settings.json` 解析後之字典內容。"""
        settings_path = os.path.join(self.project_root, ".vscode", "settings.json")
        return vfs.read_json(settings_path)

    def test_package_lazy_loading_and_module_exports(self) -> None:
        """驗證 `vscode_support/__init__.py` PEP 562 延遲載入、`__dir__` 與未知屬性 `AttributeError`。"""
        target_keys = ("SettingsProjector", "SchemaCompiler", "projector", "schema_compiler")
        saved: Dict[str, Any] = {}
        for key in target_keys:
            if key in vscode_support.__dict__:
                saved[key] = vscode_support.__dict__.pop(key)
        try:
            self.assertIs(vscode_support.SettingsProjector, SettingsProjector)
            self.assertIs(vscode_support.SchemaCompiler, SchemaCompiler)
            self.assertIs(vscode_support.projector.SettingsProjector, SettingsProjector)
            self.assertIs(vscode_support.schema_compiler.SchemaCompiler, SchemaCompiler)
            exported = dir(vscode_support)
            for item in vscode_support.__all__:
                self.assertIn(item, exported)
            with self.assertRaises(AttributeError):
                _ = vscode_support.non_existent_attr_for_test
        finally:
            vscode_support.__dict__.update(saved)
        self.mark_passed()

    def test_auto_create_vscode_dir_and_stable_site_packages_link(self) -> None:
        """自動建立 `project://.vscode/`、各版本 `site-packages` 實體目錄與 `current-site-packages` 穩定連結目標切換。"""
        vscode_dir = os.path.join(self.project_root, ".vscode")
        link_path = self.projector.get_stable_link_path()
        self.assertFalse(os.path.exists(vscode_dir))

        ok = self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
        self.assertTrue(ok)
        self.assertTrue(os.path.isdir(vscode_dir))
        site_py312 = self.pip_mgr.get_site_packages_dir("py312")
        self.assertTrue(os.path.isdir(site_py312))
        if os.path.lexists(link_path):
            self.assertEqual(
                os.path.normcase(os.path.realpath(link_path)),
                os.path.normcase(os.path.realpath(site_py312)),
            )

        data = self._read_settings()
        self.assertEqual(data.get("python.analysis.extraPaths", []), ["./.yscb/.venv/current-site-packages"])

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py311"))
        site_py311 = self.pip_mgr.get_site_packages_dir("py311")
        self.assertTrue(os.path.isdir(site_py311))
        if os.path.lexists(link_path):
            self.assertEqual(
                os.path.normcase(os.path.realpath(link_path)),
                os.path.normcase(os.path.realpath(site_py311)),
            )
        data_after = self._read_settings()
        self.assertEqual(data_after.get("python.analysis.extraPaths"), ["./.yscb/.venv/current-site-packages"])
        self.mark_passed()

    def test_stable_path_preserved_when_symlink_unsupported(self) -> None:
        """當受限檔案系統不支援建立 Symlink 時，`extraPaths` 仍維持 `current-site-packages` 零變動。"""
        with patch.object(self.projector, "ensure_stable_site_packages_link", return_value=None):
            ok = self.projector.sync_vscode_settings(self.project_root, py_tag="py312")
            self.assertTrue(ok)
            data = self._read_settings()
            self.assertEqual(data.get("python.analysis.extraPaths", []), ["./.yscb/.venv/current-site-packages"])
        self.mark_passed()

    def test_schema_compiler_contributes_and_composite_types(self) -> None:
        """驗證 `_format.json` 轉譯為 Draft-07 Schema（含自遞迴 `$CommandNode`、`list[int]`、`dict[str]`、陣列節點與外層包裹）。"""
        fmt_data = {
            "_types": {
                "CommandNode": {
                    "description": "str!",
                    "tier": "enum(safe, conditional, gated)? = conditional",
                    "weight": "float? = 1.5",
                    "offset": "int? = -1",
                    "tags": "list[str]! | extend",
                    "retries": "list[int]?",
                    "labels": "dict[str, str]?",
                    "extra_meta": "any?",
                    "cmd": {"*": "$CommandNode"},
                }
            },
            "commands": {
                "description": "CLI commands tree",
                "merge": "merge",
                "format": {
                    "module_alias": "list[str]?",
                    "matrix": ["int!"],
                    "empty_arr": [],
                    "cmd": {"*": "$CommandNode"},
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
        self.assertEqual(cmd_node_def["properties"]["retries"], {"type": "array", "items": {"type": "integer"}})
        self.assertEqual(
            cmd_node_def["properties"]["labels"],
            {"type": "object", "additionalProperties": {"type": "string"}},
        )
        self.assertEqual(cmd_node_def["properties"]["extra_meta"], {})
        self.assertEqual(cmd_node_def["properties"]["cmd"]["additionalProperties"], {"$ref": "#/$defs/CommandNode"})

        commands_prop = schema["properties"]["commands"]
        self.assertEqual(commands_prop["properties"]["matrix"], {"type": "array", "items": {"type": "integer"}})
        self.assertEqual(commands_prop["properties"]["empty_arr"], {"type": "array", "items": {}})

        locales_prop = schema["properties"]["locales"]
        self.assertEqual(locales_prop["required"], ["definition"])
        self.assertEqual(locales_prop["additionalProperties"], {"type": "string"})
        self.assertEqual(locales_prop["properties"]["definition"]["description"], "語意契約檔相對路徑 (必填)")
        self.assertIn("語意契約檔相對路徑 (必填)", locales_prop["properties"]["definition"]["markdownDescription"])
        self.assertIn("defaultSnippets", locales_prop["properties"]["definition"])
        snippet_labels = [s["label"] for s in locales_prop["properties"]["definition"]["defaultSnippets"]]
        for expected_scheme in ("project://", "config://", "config.local://", "storage.local://"):
            self.assertIn(expected_scheme, snippet_labels)

        self.assertIn("demo-mod", schema["properties"])
        self.assertIn("commands", schema["properties"]["demo-mod"]["properties"])
        self.mark_passed()

    def test_schema_compiler_config_from_mirror_zip_and_orphan_cleanup(self) -> None:
        """驗證自 `module.mirror://` 讀取組態模板推導 Schema、清理孤兒 Schema 並精確斷言綁定數量。"""
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

        cfg_fmt = {
            "_types": {"EndpointCfg": {"url": "uri!"}},
            "paths": {
                "plans": "uri! @desc(活躍計畫目錄路徑)",
                "roadmap": "uri? = project://plans/roadmap @desc(路線圖目錄路徑)",
            },
            "endpoint": {"description": "遠端端點設定", "format": "$EndpointCfg"},
            "enable_agents_md": "bool? = true @desc(是否生成 AGENTS.md)",
        }
        fmt_cfg_schema = self.compiler.compile_config_schema("sample-mod", template_data=tpl, fmt_data=cfg_fmt)
        self.assertFalse(fmt_cfg_schema["additionalProperties"])
        self.assertIn("EndpointCfg", fmt_cfg_schema["$defs"])
        self.assertEqual(fmt_cfg_schema["properties"]["enable_agents_md"]["description"], "是否生成 AGENTS.md")
        self.assertEqual(fmt_cfg_schema["properties"]["paths"]["required"], ["plans"])
        self.assertEqual(fmt_cfg_schema["properties"]["paths"]["properties"]["plans"]["description"], "活躍計畫目錄路徑")
        self.assertIn("defaultSnippets", fmt_cfg_schema["properties"]["paths"]["properties"]["plans"])

        orphan_dir = os.path.join(self.project_root, ".vscode", "schemas", "contributes")
        os.makedirs(orphan_dir, exist_ok=True)
        orphan_file = os.path.join(orphan_dir, "non_existent_orphan_mod.schema.json")
        vfs.write_json(orphan_file, {"type": "object"})
        self.assertTrue(os.path.isfile(orphan_file))

        gi_file = os.path.join(self.project_root, ".vscode", "schemas", ".gitignore")
        vfs.write_text(gi_file, "*\n")
        self.assertTrue(os.path.isfile(gi_file))

        with patch.object(self.compiler, "_discover_installed_modules", return_value=["sample-mod"]), patch.object(
            schema_compiler_mod.contributes, "get", return_value={}
        ):
            bindings = self.compiler.sync_all_schemas(self.project_root)

        self.assertFalse(os.path.exists(orphan_file))
        self.assertFalse(os.path.exists(gi_file))
        self.assertEqual(len(bindings), 3)
        schemas_root = os.path.join(self.project_root, ".vscode", "schemas")
        self.assertTrue(os.path.isfile(os.path.join(schemas_root, "config", "sample-mod.schema.json")))
        self.assertTrue(os.path.isfile(os.path.join(schemas_root, "meta", "format-meta.schema.json")))
        self.assertTrue(os.path.isfile(os.path.join(schemas_root, "meta", "manifest.schema.json")))
        self.mark_passed()

    def test_contributed_json_schemas_extension_point_branches(self) -> None:
        """驗證 `vscode-support.json_schemas` 擴充點之 `static_file`、`contributes_format` 與 `configurable_template` 分支。"""
        custom_rules = {
            "__provider__": "vscode-support",
            "custom-static": {
                "file_match": ["**/custom.static.json"],
                "schema_source": "static_file",
                "schema_path": "./meta/format-meta.schema.json",
            },
            "custom-contrib": {
                "file_match": ["**/custom.contrib.json"],
                "schema_source": "contributes_format",
                "schema_path": "core",
            },
            "custom-config": {
                "file_match": ["**/custom.config.json"],
                "schema_source": "configurable_template",
                "schema_path": "",
            },
        }
        with patch.object(self.compiler, "_discover_installed_modules", return_value=[]), patch.object(
            schema_compiler_mod.contributes,
            "get",
            side_effect=lambda mod, key: custom_rules if (mod, key) == ("vscode-support", "json_schemas") else [],
        ):
            bindings = self.compiler.sync_all_schemas(self.project_root)

        self.assertEqual(len(bindings), 3)
        urls = {b["url"]: b["fileMatch"] for b in bindings}
        self.assertEqual(urls.get("./.vscode/schemas/meta/format-meta.schema.json"), ["**/custom.static.json"])
        self.assertEqual(urls.get("./.vscode/schemas/contributes/core.schema.json"), ["**/custom.contrib.json"])
        self.assertEqual(urls.get("./.vscode/schemas/config/custom-config.schema.json"), ["**/custom.config.json"])
        self.mark_passed()

    def test_semver_mirror_zip_selection_and_uri_snippet_caching(self) -> None:
        """驗證 `_select_latest_mirror_zip` 四段式 SemVer 排序（`1.0.0.10 > 1.0.0.2`）與 `sync_all_schemas` 內 URI snippets 快取。"""
        mirror_mod_dir = os.path.join(self.yscb_dir, ".mirror", "semver-mod")
        os.makedirs(mirror_mod_dir, exist_ok=True)
        os.makedirs(os.path.join(self.yscb_dir, ".modules", "semver-mod"), exist_ok=True)

        zip_v2 = os.path.join(mirror_mod_dir, "1.0.0.2.zip")
        with zipfile.ZipFile(zip_v2, "w") as zf:
            zf.writestr("configurable/_format.json", json.dumps({"old_v2_key": "str = 'v2'"}))

        zip_v10 = os.path.join(mirror_mod_dir, "1.0.0.10.zip")
        with zipfile.ZipFile(zip_v10, "w") as zf:
            zf.writestr("configurable/_format.json", json.dumps({"new_v10_key": "str = 'v10'"}))

        zip_non_semver = os.path.join(mirror_mod_dir, "legacy_snapshot.zip")
        with zipfile.ZipFile(zip_non_semver, "w") as zf:
            zf.writestr("configurable/_format.json", json.dumps({"legacy_key": "str"}))

        selected_zip = self.compiler._select_latest_mirror_zip(mirror_mod_dir)
        self.assertIsNotNone(selected_zip)
        self.assertTrue(str(selected_zip).endswith("1.0.0.10.zip"))

        loaded_fmt = self.compiler._load_module_config_format("semver-mod")
        self.assertIsNotNone(loaded_fmt)
        self.assertIn("new_v10_key", loaded_fmt or {})
        self.assertNotIn("old_v2_key", loaded_fmt or {})

        snippet_call_count = {"n": 0}
        orig_contributes_get = schema_compiler_mod.contributes.get

        def _counting_contributes_get(mod: str, key: str) -> Any:
            if mod == "core" and key == "uri_schemes":
                snippet_call_count["n"] += 1
            return orig_contributes_get(mod, key)

        with patch.object(schema_compiler_mod.contributes, "get", side_effect=_counting_contributes_get):
            self.compiler.sync_all_schemas(self.project_root)
            self.assertEqual(snippet_call_count["n"], 1)
            self.assertIsNone(self.compiler._cached_uri_snippets)
        self.mark_passed()

    def test_soft_merge_preserves_user_settings_and_revert_cleans_all(self) -> None:
        """驗證保留使用者自訂 `extraPaths`、`interpreter` 與 `json.schemas`，且 `revert` 100% 乾淨還原（含移除 `python.analysis.exclude` 與空排除字典）。"""
        user_custom_schema = {"fileMatch": ["my.custom.json"], "url": "./my.schema.json"}
        initial_settings = {
            "editor.tabSize": 2,
            "python.defaultInterpreterPath": "./.venv/bin/python",
            "python.analysis.extraPaths": ["./custom_src"],
            "json.schemas": [user_custom_schema],
        }
        settings_path = self._write_settings(initial_settings)

        with patch.object(self.compiler, "_discover_installed_modules", return_value=[]), patch.object(
            schema_compiler_mod.contributes, "get", return_value={}
        ):
            ok = self.projector.sync_vscode_settings(self.project_root, extra_paths=["./extra_mod"], py_tag="py312")
            self.assertTrue(ok)

            merged = self._read_settings()
            self.assertEqual(merged.get("editor.tabSize"), 2)
            self.assertEqual(merged.get("python.defaultInterpreterPath"), "./.venv/bin/python")
            self.assertIn("./custom_src", merged.get("python.analysis.extraPaths", []))
            self.assertIn("./extra_mod", merged.get("python.analysis.extraPaths", []))
            self.assertIn(user_custom_schema, merged.get("json.schemas", []))
            self.assertEqual(len(merged.get("json.schemas", [])), 3)
            self.assertIn("python.analysis.exclude", merged)
            self.assertIn("files.watcherExclude", merged)
            self.assertIn("search.exclude", merged)
            self.assertIn("_yscb_managed", merged)

            mtime_1 = os.stat(settings_path).st_mtime_ns
            self.projector.sync_vscode_settings(self.project_root, extra_paths=["./extra_mod"], py_tag="py312")
            mtime_2 = os.stat(settings_path).st_mtime_ns
            self.assertEqual(mtime_1, mtime_2)

        rev_ok = self.projector.revert_vscode_settings(self.project_root)
        self.assertTrue(rev_ok)
        reverted = self._read_settings()
        for removed_key in (
            "_yscb_managed",
            "python.analysis.exclude",
            "files.watcherExclude",
            "search.exclude",
            "files.exclude",
        ):
            self.assertNotIn(removed_key, reverted)
        self.assertEqual(reverted.get("editor.tabSize"), 2)
        self.assertEqual(reverted.get("python.defaultInterpreterPath"), "./.venv/bin/python")
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["./custom_src"])
        self.assertEqual(reverted.get("json.schemas"), [user_custom_schema])
        self.assertFalse(os.path.exists(os.path.join(self.project_root, ".vscode", "schemas")))
        self.assertFalse(os.path.lexists(self.projector.get_stable_link_path()))
        self.mark_passed()

    def test_legacy_venv_extra_paths_and_managed_interpreter_upgrade_cleanup(self) -> None:
        """驗證舊版 YSCB `.venv/py3XX/.../site-packages` 路徑與託管直譯器於同步及還原時自動升級清理。"""
        legacy_settings = {
            "python.defaultInterpreterPath": "./.yscb/.venv/py310/bin/python",
            "python.analysis.extraPaths": ["./.yscb/.venv/py310/lib/python3.10/site-packages", "./keep_me"],
        }
        self._write_settings(legacy_settings)

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312", compile_schemas=False))
        synced = self._read_settings()
        self.assertNotIn("python.defaultInterpreterPath", synced)
        self.assertEqual(
            synced.get("python.analysis.extraPaths"),
            ["./keep_me", "./.yscb/.venv/current-site-packages"],
        )

        synced["python.defaultInterpreterPath"] = "./.yscb/.venv/py311/bin/python"
        synced["python.analysis.extraPaths"].append("./.yscb/.venv/py311/lib/python3.11/site-packages")
        self._write_settings(synced)

        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        reverted = self._read_settings()
        self.assertNotIn("python.defaultInterpreterPath", reverted)
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["./keep_me"])
        self.mark_passed()

    def test_jsonc_comments_trailing_commas_and_non_dict_guards(self) -> None:
        """驗證多行區塊註解、連續尾隨逗號、損毀語法備份與非 dict 設定檔之安全防護。"""
        raw_multiline_jsonc = (
            "{\n"
            "  /* multi-line\n"
            "     block comment */\n"
            '  "editor.tabSize": 4,\n'
            '  "custom.url": "https://example.com//not-a-comment/*still-string*/",\n'
            '  "arr": [1, 2,, ],\n'
            "}\n"
        )
        parsed_stripped = json.loads(strip_jsonc(raw_multiline_jsonc))
        self.assertEqual(parsed_stripped["editor.tabSize"], 4)
        self.assertEqual(parsed_stripped["arr"], [1, 2])

        raw_bytes = raw_multiline_jsonc.encode("utf-8")
        settings_path = self._write_settings(raw_bytes)
        bak_path = settings_path + ".bak"

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312", compile_schemas=False))
        self.assertTrue(os.path.isfile(bak_path))
        with open(bak_path, "rb") as f:
            self.assertEqual(f.read(), raw_bytes)
        merged = self._read_settings()
        self.assertEqual(merged.get("editor.tabSize"), 4)
        self.assertEqual(merged.get("custom.url"), "https://example.com//not-a-comment/*still-string*/")
        self.assertIn("_yscb_managed", merged)

        corrupt_bytes = b'{\n  "broken": [1, 2\n'
        self._write_settings(corrupt_bytes)
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            self.assertFalse(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        self.assertIn("unrecoverable JSON syntax errors", stderr_buf.getvalue())
        with open(settings_path, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)
        with open(bak_path, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)

        list_json_bytes = b'["not", "a", "dict"]\n'
        self._write_settings(list_json_bytes)
        stderr_list_buf = io.StringIO()
        with redirect_stderr(stderr_list_buf):
            self.assertFalse(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        self.assertEqual(stderr_list_buf.getvalue(), "")
        self.assertFalse(self.projector.revert_vscode_settings(self.project_root))
        with open(settings_path, "rb") as f:
            self.assertEqual(f.read(), list_json_bytes)

        list_jsonc_bytes = b'// comment on non-dict jsonc\n["not", "a", "dict",]\n'
        self._write_settings(list_jsonc_bytes)
        stderr_jsonc_list_buf = io.StringIO()
        with redirect_stderr(stderr_jsonc_list_buf):
            self.assertFalse(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        self.assertEqual(stderr_jsonc_list_buf.getvalue(), "")
        with open(bak_path, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)
        self.mark_passed()

    def test_status_jsonc_and_broken_symlink_detection(self) -> None:
        """驗證 `get_status` 支援讀取 JSONC `settings.json` 並確定性檢測損毀之穩定連結。"""
        jsonc_managed = (
            '{\n  // JSONC managed settings\n  "_yscb_managed": {\n'
            '    "extraPaths": ["./.yscb/source/core"],\n'
            '    "jsonSchemas": ["./.vscode/schemas/meta/manifest.schema.json"],\n'
            "  },\n}\n"
        )
        self._write_settings(jsonc_managed)
        st_info = self.projector.get_status(self.project_root)
        self.assertTrue(st_info["vscode_dir_exists"])
        self.assertTrue(st_info["settings_managed"])
        self.assertEqual(st_info["managed_extra_paths"], ["./.yscb/source/core"])
        self.assertEqual(st_info["managed_schema_count"], 1)

        link_path = self.projector.get_stable_link_path()
        os.makedirs(os.path.dirname(link_path), exist_ok=True)
        if os.path.lexists(link_path):
            self.projector.remove_stable_site_packages_link()
        non_existent_target = os.path.join(self.yscb_dir, ".venv", "missing_target_dir")

        symlink_created = False
        try:
            os.symlink(non_existent_target, link_path)
            symlink_created = True
        except (OSError, NotImplementedError):
            symlink_created = False

        try:
            if symlink_created:
                st_broken = self.projector.get_status(self.project_root)
            else:
                orig_lexists, orig_isdir = os.path.lexists, os.path.isdir
                with patch(
                    "os.path.lexists", side_effect=lambda p: True if p == link_path else orig_lexists(p)
                ), patch(
                    "os.path.isdir",
                    side_effect=lambda p: False if p in (link_path, non_existent_target) else orig_isdir(p),
                ):
                    st_broken = self.projector.get_status(self.project_root)
            self.assertFalse(st_broken["stable_link_active"])
            self.assertTrue(st_broken["vscode_dir_exists"])
        finally:
            if os.path.lexists(link_path):
                self.projector.remove_stable_site_packages_link()
        self.mark_passed()

    def test_module_and_source_extra_paths_projection_and_revert(self) -> None:
        """驗證自動投影 `.modules/<mod>` 與 `source/<mod>` 至 `extraPaths`、動態調整 `analysisExclude` 並乾淨還原。"""
        mods_dir = os.path.join(self.yscb_dir, ".modules")
        src_dir = os.path.join(self.yscb_dir, "source")
        for rel_d in (
            os.path.join(mods_dir, "core"),
            os.path.join(mods_dir, "ast"),
            os.path.join(mods_dir, "file-space"),
            os.path.join(src_dir, "ast"),
            os.path.join(src_dir, "knowledge-db"),
        ):
            os.makedirs(rel_d, exist_ok=True)

        self._write_settings({"python.analysis.extraPaths": ["./user_custom"]})

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        merged = self._read_settings()
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

        os.makedirs(os.path.join(src_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "file-space"), exist_ok=True)
        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312"))
        merged_all_src = self._read_settings()
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

        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        reverted = self._read_settings()
        self.assertEqual(reverted.get("python.analysis.extraPaths"), ["./user_custom"])
        self.assertNotIn("python.analysis.exclude", reverted)
        self.assertNotIn("_yscb_managed", reverted)
        self.mark_passed()

    def test_revert_side_effects_deferred_until_valid_managed_settings(self) -> None:
        """驗證 `revert_vscode_settings` 先確認 `_yscb_managed` 存在後才刪除 `schemas/` 與穩定連結。"""
        schemas_dir = os.path.join(self.project_root, ".vscode", "schemas")
        os.makedirs(schemas_dir, exist_ok=True)
        dummy_schema = os.path.join(schemas_dir, "user_kept.schema.json")
        vfs.write_json(dummy_schema, {"type": "object"})
        self.projector.ensure_stable_site_packages_link(py_tag="py312")

        # 1. settings.json 不存在時，不應刪除 schemas_dir
        self.assertFalse(self.projector.revert_vscode_settings(self.project_root))
        self.assertTrue(os.path.isfile(dummy_schema))

        # 2. settings.json 語法損毀時，不應刪除 schemas_dir
        self._write_settings(b'{"corrupt": [1, 2')
        self.assertFalse(self.projector.revert_vscode_settings(self.project_root))
        self.assertTrue(os.path.isfile(dummy_schema))

        # 3. settings.json 合法但無 _yscb_managed 時，不應刪除 schemas_dir
        self._write_settings({"editor.tabSize": 4})
        self.assertFalse(self.projector.revert_vscode_settings(self.project_root))
        self.assertTrue(os.path.isfile(dummy_schema))

        # 4. settings.json 含 _yscb_managed 時，正常執行清理
        self._write_settings({"editor.tabSize": 4, "_yscb_managed": {"extraPaths": []}})
        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        self.assertFalse(os.path.exists(schemas_dir))
        self.assertFalse(os.path.lexists(self.projector.get_stable_link_path()))
        self.mark_passed()

    def test_malformed_yscb_managed_subfields_defensive_fallback(self) -> None:
        """驗證 `_yscb_managed` 子欄位被改為非預期型別（int/None/str）時不拋出 `TypeError` 並安全回退。"""
        self._write_settings(
            {
                "editor.tabSize": 2,
                "_yscb_managed": {
                    "extraPaths": 123,
                    "excludes": None,
                    "analysisExclude": 456,
                    "jsonSchemas": "not-a-list",
                },
            }
        )
        status_info = self.projector.get_status(self.project_root)
        self.assertTrue(status_info["settings_managed"])
        self.assertEqual(status_info["managed_extra_paths"], [])
        self.assertEqual(status_info["managed_schemas"], [])

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312", compile_schemas=False))
        repaired = self._read_settings()
        self.assertIsInstance(repaired["_yscb_managed"]["extraPaths"], list)
        self.assertIsInstance(repaired["_yscb_managed"]["excludes"], dict)
        self.assertIsInstance(repaired["_yscb_managed"]["analysisExclude"], list)

        repaired["_yscb_managed"] = {
            "extraPaths": None,
            "excludes": 789,
            "analysisExclude": "invalid",
            "jsonSchemas": 0,
        }
        self._write_settings(repaired)
        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        after_revert = self._read_settings()
        self.assertNotIn("_yscb_managed", after_revert)
        self.mark_passed()

    def test_exclude_keys_diff_cleanup_and_user_analysis_exclude_preservation(self) -> None:
        """驗證舊版 `excludes` 差集清理，以及使用者預先配置之 `python.analysis.exclude` 於同步與還原後完整保留。"""
        self._write_settings(
            {
                "python.analysis.exclude": ["**/user_vendor/**", "**/.venv/**"],
            }
        )
        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312", compile_schemas=False))
        synced_1 = self._read_settings()
        self.assertIn("**/user_vendor/**", synced_1["python.analysis.exclude"])
        self.assertIn("**/.venv/**", synced_1["python.analysis.exclude"])
        self.assertNotIn("**/user_vendor/**", synced_1["_yscb_managed"]["analysisExclude"])
        self.assertNotIn("**/.venv/**", synced_1["_yscb_managed"]["analysisExclude"])

        # 模擬舊版殘留之 exclude section 與舊 pattern
        synced_1["legacy.exclude"] = {"**/.old_venv/**": True}
        synced_1["files.exclude"]["**/.legacy_venv"] = True
        synced_1["_yscb_managed"]["excludes"]["legacy.exclude"] = "**/.old_venv/**"
        synced_1["_yscb_managed"]["excludes"]["files.exclude"] = "**/.legacy_venv"
        self._write_settings(synced_1)

        self.assertTrue(self.projector.sync_vscode_settings(self.project_root, py_tag="py312", compile_schemas=False))
        synced_2 = self._read_settings()
        self.assertNotIn("legacy.exclude", synced_2)
        self.assertNotIn("legacy.exclude", synced_2["_yscb_managed"]["excludes"])
        self.assertNotIn("**/.legacy_venv", synced_2.get("files.exclude", {}))
        self.assertEqual(synced_2["_yscb_managed"]["excludes"].get("files.exclude"), "**/.venv")
        self.assertNotIn("**/.venv/**", synced_2["_yscb_managed"]["analysisExclude"])

        self.assertTrue(self.projector.revert_vscode_settings(self.project_root))
        reverted = self._read_settings()
        self.assertEqual(reverted.get("python.analysis.exclude"), ["**/user_vendor/**", "**/.venv/**"])
        self.mark_passed()

    def test_schema_compiler_leaf_key_optional_description_and_local_modules_discovery(self) -> None:
        """驗證子鍵名路徑推導隔離、省略 `description` 之規則字典識別，以及 `self.yscb_dir/.modules` 本地模組探測與 VFS fallback。"""
        inferred = self.compiler._infer_value_schema(
            {
                "paths": {
                    "timeout": "30s",
                    "enabled_name": "default_profile",
                    "output_dir": "build_out",
                }
            }
        )
        paths_props = inferred["properties"]["paths"]["properties"]
        self.assertNotIn("defaultSnippets", paths_props["timeout"])
        self.assertNotIn("defaultSnippets", paths_props["enabled_name"])
        self.assertIn("defaultSnippets", paths_props["output_dir"])

        cfg_schema = self.compiler.compile_config_schema(
            "rule-mod",
            fmt_data={
                "_types": {"TargetSpec": {"host": "str!"}},
                "endpoint": {"format": "$TargetSpec"},
                "mode": {"format": "str!", "merge": "replace"},
                "nested_literal": {"format": "str!", "extra_count": "int? = 1"},
            },
        )
        self.assertEqual(cfg_schema["properties"]["endpoint"], {"$ref": "#/$defs/TargetSpec"})
        self.assertEqual(cfg_schema["properties"]["mode"], {"type": "string"})
        self.assertIn("mode", cfg_schema.get("required", []))
        self.assertEqual(cfg_schema["properties"]["nested_literal"]["type"], "object")
        self.assertIn("format", cfg_schema["properties"]["nested_literal"]["properties"])
        self.assertIn("extra_count", cfg_schema["properties"]["nested_literal"]["properties"])

        # 於 self.yscb_dir/.modules 建立本地模組並驗證不依賴全域 module:// 即可探測與編譯
        local_mod_dir = os.path.join(self.yscb_dir, ".modules", "local-mod")
        os.makedirs(os.path.join(local_mod_dir, "contributes"), exist_ok=True)
        os.makedirs(os.path.join(local_mod_dir, "configurable"), exist_ok=True)
        vfs.write_json(
            os.path.join(local_mod_dir, "contributes", "_format.json"),
            {"hooks": {"format": {"*": "str!"}}},
        )
        vfs.write_json(
            os.path.join(local_mod_dir, "configurable", "_format.json"),
            {"api_token": {"format": "str!"}},
        )

        orig_vfs_exists = vfs.exists
        with patch.object(
            vfs,
            "exists",
            side_effect=lambda p: False if str(p).startswith("module://") else orig_vfs_exists(p),
        ), patch.object(schema_compiler_mod.contributes, "get", return_value={}):
            discovered = self.compiler._discover_installed_modules()
            self.assertIn("local-mod", discovered)
            loaded_cfg_fmt = self.compiler._load_module_config_format("local-mod")
            self.assertEqual(loaded_cfg_fmt, {"api_token": {"format": "str!"}})
            bindings = self.compiler.sync_all_schemas(self.project_root)

        urls = {b["url"] for b in bindings}
        self.assertIn("./.vscode/schemas/contributes/local-mod.schema.json", urls)
        self.assertIn("./.vscode/schemas/config/local-mod.schema.json", urls)
        self.mark_passed()

    def test_cli_commands_json_and_human_modes_and_normalize_bags(self) -> None:
        """驗證 `scripts/cli.py` 之 `_normalize_bags`、`status`、`sync`、`revert`（JSON 與人類可讀模式）。"""
        cli_mod = self._load_script_module("cli.py", "_test_vsc_cli")

        existing_bags = CmdBags(raw_cmd="sync", command="sync", args=["a"], options={"json": CmdOption("json", True)})
        self.assertIs(cli_mod._normalize_bags(existing_bags, "sync"), existing_bags)

        parsed_bags = cli_mod._normalize_bags(["pos_arg", "--format=pretty", "--json", "-v"], "status")
        self.assertEqual(parsed_bags.args, ["pos_arg"])
        self.assertEqual(parsed_bags.options["format"].params, "pretty")
        self.assertTrue(parsed_bags.options["json"].params)
        self.assertTrue(parsed_bags.options["v"].params)

        fallback_bags = cli_mod._normalize_bags(None, "revert")
        self.assertEqual(fallback_bags.command, "revert")
        self.assertEqual(fallback_bags.args, [])

        with patch("core.uri.resolve", return_value=self.project_root), patch(
            "vscode_support.projector.SettingsProjector",
            side_effect=lambda *a, **kw: SettingsProjector(yscb_dir=self.yscb_dir),
        ), patch.object(SchemaCompiler, "_discover_installed_modules", return_value=[]), patch.object(
            schema_compiler_mod.contributes, "get", return_value={}
        ):
            buf_sync = io.StringIO()
            with redirect_stdout(buf_sync):
                self.assertEqual(cli_mod.sync(["--json"]), 0)
            sync_payload = json.loads(buf_sync.getvalue())
            self.assertTrue(sync_payload.get("synced"))
            self.assertTrue(sync_payload.get("settings_managed"))

            buf_status = io.StringIO()
            with redirect_stdout(buf_status):
                self.assertEqual(cli_mod.status(["--json"]), 0)
            status_payload = json.loads(buf_status.getvalue())
            self.assertTrue(status_payload.get("vscode_dir_exists"))
            self.assertEqual(status_payload.get("managed_schema_count"), 2)

            buf_rev = io.StringIO()
            with redirect_stdout(buf_rev):
                self.assertEqual(cli_mod.revert(["--json"]), 0)
            self.assertTrue(json.loads(buf_rev.getvalue()).get("reverted"))

            buf_human_sync = io.StringIO()
            with redirect_stdout(buf_human_sync):
                self.assertEqual(cli_mod.sync([]), 0)
            self.assertIn("Synced .vscode/settings.json", buf_human_sync.getvalue())

            buf_human_status = io.StringIO()
            with redirect_stdout(buf_human_status):
                self.assertEqual(cli_mod.status([]), 0)
            self.assertIn("YS-Codebase VS Code Workspace Support Status", buf_human_status.getvalue())
            self.assertIn("Managed Schemas     : 2 schema(s)", buf_human_status.getvalue())

            buf_human_rev = io.StringIO()
            with redirect_stdout(buf_human_rev):
                self.assertEqual(cli_mod.revert([]), 0)
            self.assertIn("Reverted YSCB managed VS Code settings", buf_human_rev.getvalue())

            buf_human_rev_noop = io.StringIO()
            with redirect_stdout(buf_human_rev_noop):
                self.assertEqual(cli_mod.revert([]), 0)
            self.assertIn("No active _yscb_managed settings found to revert", buf_human_rev_noop.getvalue())

            # Verify CLI revert returns exit code 1 when settings.json has unrecoverable syntax error or write failure
            settings_path = os.path.join(self.project_root, ".vscode", "settings.json")
            vfs.write_text(settings_path, "{broken_json_for_revert", encoding="utf-8", atomic=True)
            buf_rev_err_json = io.StringIO()
            with redirect_stdout(buf_rev_err_json):
                self.assertEqual(cli_mod.revert(["--json"]), 1)
            err_payload = json.loads(buf_rev_err_json.getvalue())
            self.assertFalse(err_payload.get("reverted"))
            self.assertIn("Failed to read or parse", err_payload.get("error", ""))

            buf_rev_err_human = io.StringIO()
            with redirect_stderr(buf_rev_err_human):
                self.assertEqual(cli_mod.revert([]), 1)
            self.assertIn("Failed to read or parse", buf_rev_err_human.getvalue())
            self._write_settings({"editor.tabSize": 4})

        missing_root = os.path.join(self.temp_dir, "non_existent_proj")
        with patch("core.uri.resolve", return_value=missing_root), patch(
            "vscode_support.projector.SettingsProjector",
            side_effect=lambda *a, **kw: SettingsProjector(yscb_dir=self.yscb_dir),
        ):
            buf_err = io.StringIO()
            with redirect_stderr(buf_err):
                self.assertEqual(cli_mod.sync([]), 1)
            self.assertIn("Failed or skipped syncing VS Code settings", buf_err.getvalue())
        self.mark_passed()

    def test_core_hook_real_lifecycle_and_error_guards(self) -> None:
        """真實執行 `hook.core.py` 之 `on_env_synced`、`on_reload` 與 `on_remove`（含別名 `vsc`）及空路徑/例外防護。"""
        hook_mod = self._load_script_module("hook.core.py", "_test_vsc_hook_core")

        self.assertFalse(hook_mod.on_remove(None))
        self.assertFalse(hook_mod.on_remove(ExecutionContext("core", "remove", None)))  # type: ignore[arg-type]
        self.assertFalse(hook_mod.on_remove(ExecutionContext("core", "remove", ["other-module"])))

        settings_path = os.path.join(self.project_root, ".vscode", "settings.json")
        schemas_dir = os.path.join(self.project_root, ".vscode", "schemas")
        orig_resolve = hook_mod.uri.resolve

        with patch.object(
            hook_mod.uri,
            "resolve",
            side_effect=lambda u, interactive=False: self.project_root
            if u == "project://"
            else orig_resolve(u, interactive=interactive),
        ), patch("core.uri.resolve_yscb_root", return_value=self.yscb_dir), patch.object(
            SchemaCompiler, "_discover_installed_modules", return_value=[]
        ), patch.object(
            schema_compiler_mod.contributes, "get", return_value={}
        ):
            self.assertTrue(hook_mod.on_env_synced())
            self.assertTrue(os.path.isfile(settings_path))
            self.assertTrue(os.path.isdir(schemas_dir))
            self.assertIn("_yscb_managed", self._read_settings())

            self.assertTrue(hook_mod.on_remove(ExecutionContext("core", "remove", ["vsc"])))
            self.assertNotIn("_yscb_managed", self._read_settings())
            self.assertFalse(os.path.exists(schemas_dir))

            self.assertTrue(hook_mod.on_reload())
            self.assertTrue(os.path.isdir(schemas_dir))
            self.assertIn("_yscb_managed", self._read_settings())

            self.assertTrue(hook_mod.on_remove(ExecutionContext("core", "remove", ["vscode-support"])))
            self.assertNotIn("_yscb_managed", self._read_settings())
            self.assertFalse(os.path.exists(schemas_dir))

        with patch.object(hook_mod.uri, "resolve", return_value=""):
            self.assertFalse(hook_mod.on_env_synced())
            self.assertFalse(hook_mod.on_remove(ExecutionContext("core", "remove", ["vsc"])))

        with patch.object(hook_mod.uri, "resolve", side_effect=RuntimeError("simulated resolve failure")):
            stderr_sync = io.StringIO()
            with redirect_stderr(stderr_sync):
                self.assertFalse(hook_mod.on_env_synced())
            self.assertIn("Warning: Failed to sync VS Code workspace", stderr_sync.getvalue())

            stderr_rem = io.StringIO()
            with redirect_stderr(stderr_rem):
                self.assertFalse(hook_mod.on_remove(ExecutionContext("core", "remove", ["vscode-support"])))
            self.assertIn("Warning: Failed during on_remove revert", stderr_rem.getvalue())

        registered_spaces: Dict[str, Any] = {}

        class _DummyRegistry:
            def register_space(self, name: str, cfg: Dict[str, Any]) -> None:
                registered_spaces[name] = cfg

        self.assertFalse(hook_mod.on_register_file_spaces(None))
        self.assertTrue(hook_mod.on_register_file_spaces({"registry": _DummyRegistry()}))
        self.assertIn("vscode-support/gitignore", registered_spaces)
        self.assertEqual(
            registered_spaces["vscode-support/gitignore"].get("include"),
            ["project://.vscode/schemas/"],
        )

        self.assertEqual(
            SettingsProjector._translate_exclude_to_vscode_glob("yscb://.modules/**"),
            "**/.modules/**",
        )
        self.assertEqual(
            SettingsProjector._translate_exclude_to_vscode_glob("__pycache__"),
            "**/__pycache__/**",
        )
        self.assertIsNone(SettingsProjector._translate_exclude_to_vscode_glob("*.pyc"))
        resolved_excl = self.projector._resolve_workspace_exclude_patterns(self.project_root)
        self.assertIn("**/.cache/**", resolved_excl)
        self.assertIn("**/.venv/**", resolved_excl)

        self.mark_passed()

    def test_dev_hook_sandbox_setup_and_teardown_logging(self) -> None:
        """驗證 `scripts/hook.dev.py` 之 `on_test_setup` 與 `on_test_teardown` 除錯日誌記錄。"""
        dev_hook = self._load_script_module("hook.dev.py", "_test_vsc_hook_dev")
        with patch.object(dev_hook, "log_debug") as mock_log_debug:
            dev_hook.on_test_setup(context={"suite": "unit"})
            dev_hook.on_test_teardown(context={"suite": "unit"})
        joined_logs = "\n".join(str(c.args[0]) for c in mock_log_debug.call_args_list)
        self.assertIn("[hook.dev] Setup vscode-support sandbox:", joined_logs)
        self.assertIn("[hook.dev] Teardown vscode-support sandbox:", joined_logs)
        self.mark_passed()


    def test_workspace_exclude_patterns_hook_dedup_and_mirror_zip_schema_bundle(self) -> None:
        """驗證 `_resolve_workspace_exclude_patterns` 納入 `core.space` 轉譯規則、`hook.core.py` 同狀態去重與 `$ref` 描述保留。"""
        from core.context import bind_runtime_context

        resolved = self.projector._resolve_workspace_exclude_patterns(self.project_root, include_all=False)
        self.assertIn("**/__pycache__/**", resolved)
        self.assertIn("**/.pytest_cache/**", resolved)

        # Verify $ref preserves description, markdownDescription, and default when specified
        schema_with_ref_meta = self.compiler.compile_config_schema(
            "ref-meta-mod",
            fmt_data={
                "_types": {"SubCfg": {"host": "str!"}},
                "primary": {
                    "description": "Primary endpoint reference",
                    "format": "$SubCfg",
                    "default": {"host": "localhost"},
                },
            },
        )
        primary_prop = schema_with_ref_meta["properties"]["primary"]
        self.assertEqual(primary_prop["$ref"], "#/$defs/SubCfg")
        self.assertEqual(primary_prop["description"], "Primary endpoint reference")
        self.assertIn("Primary endpoint reference", primary_prop["markdownDescription"])
        self.assertEqual(primary_prop["default"], {"host": "localhost"})

        # Verify hook.core.py deduplicates back-to-back on_reload and on_env_synced within same RuntimeContext
        hook_mod = self._load_script_module("hook.core.py", "_test_vsc_hook_dedup")
        orig_resolve = hook_mod.uri.resolve
        sync_calls = {"count": 0}
        orig_sync = SettingsProjector.sync_vscode_settings

        def _counting_sync(proj_self, proj_root, *args, **kwargs):
            sync_calls["count"] += 1
            return orig_sync(proj_self, proj_root, *args, **kwargs)

        with bind_runtime_context(virtual_cwd=self.project_root, host_dir=self.project_root, yscb_dir=self.yscb_dir):
            with patch.object(
                hook_mod.uri,
                "resolve",
                side_effect=lambda u, interactive=False: self.project_root
                if u == "project://"
                else orig_resolve(u, interactive=interactive),
            ), patch("core.uri.resolve_yscb_root", return_value=self.yscb_dir), patch.object(
                SchemaCompiler, "_discover_installed_modules", return_value=[]
            ), patch.object(
                schema_compiler_mod.contributes, "get", return_value={}
            ), patch.object(
                SettingsProjector, "sync_vscode_settings", _counting_sync
            ):
                self.assertTrue(hook_mod.on_reload())
                self.assertTrue(hook_mod.on_env_synced())
                self.assertEqual(sync_calls["count"], 1)

        # Verify on_register_file_spaces skips duplicate registration when space already exists in _spaces
        class _DedupRegistry:
            def __init__(self) -> None:
                self._spaces: Dict[str, Any] = {}
                self.calls = 0

            def register_space(self, name: str, cfg: Dict[str, Any]) -> None:
                self.calls += 1
                self._spaces[name] = cfg

        dedup_reg = _DedupRegistry()
        self.assertTrue(hook_mod.on_register_file_spaces({"registry": dedup_reg}))
        self.assertTrue(hook_mod.on_register_file_spaces({"registry": dedup_reg}))
        self.assertEqual(dedup_reg.calls, 1)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
