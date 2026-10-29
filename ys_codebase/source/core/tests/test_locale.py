"""
Official test suite for core.locale engine, multi-layer fallback chains,
recursive proper-noun interpolation, and 'definition' semantic contract validation.
Covers FT-01 ~ FT-05 and ET-01 ~ ET-05.
"""
import json
import os
import shutil
import tempfile

from dev.testing import YSCBTestCase, require, Requirement
from core import contributes
from core import locale
from core import uri
from core.validator import ContributesValidator


class TestCoreLocaleEngine(YSCBTestCase):
    """Unit and integration tests for core.locale."""

    def setUp(self):
        super().setUp()
        locale.clear_cache()
        self.tmp_dir = tempfile.mkdtemp(prefix="yscb_test_locale_")

    def tearDown(self):
        locale.clear_cache()
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().tearDown()

    def _setup_mock_module_locales(
        self,
        mod_dir: str,
        definition_data: dict,
        lang_files: dict,
        decl_override: dict = None,
    ) -> dict:
        """Helper to write contributes/core.json and locales/*.json inside mod_dir."""
        os.makedirs(os.path.join(mod_dir, "contributes"), exist_ok=True)
        os.makedirs(os.path.join(mod_dir, "locales"), exist_ok=True)

        def_path = os.path.join(mod_dir, "locales", "definition.json")
        with open(def_path, "w", encoding="utf-8") as f:
            json.dump(definition_data, f, ensure_ascii=False, indent=2)

        locales_decl = {"definition": "locales/definition.json"}
        for lang_id, l_data in lang_files.items():
            rel_p = f"locales/{lang_id}.json"
            locales_decl[lang_id] = rel_p
            with open(os.path.join(mod_dir, rel_p), "w", encoding="utf-8") as f:
                json.dump(l_data, f, ensure_ascii=False, indent=2)

        if decl_override is not None:
            locales_decl = decl_override

        with open(os.path.join(mod_dir, "contributes", "core.json"), "w", encoding="utf-8") as f:
            json.dump({"locales": locales_decl}, f, ensure_ascii=False, indent=2)

        return locales_decl

    @require(Requirement.ENV)
    def test_ft_01_core_format_schema_accepts_locales_and_rejects_missing_definition(self):
        """FT-01, EC-01: core/contributes/_format.json validates 'locales' requiring 'definition'."""
        fmt = contributes.get_format("core")
        self.assertIsNotNone(fmt)
        self.assertIn("locales", fmt)

        # Valid locales declaration
        valid_payload = {
            "locales": {
                "definition": "locales/definition.json",
                "nouns-antigravity": "locales/nouns-antigravity.json",
                "zh-TW": "locales/zh-TW.json",
                "en": "locales/en.json",
            }
        }
        res_ok = ContributesValidator.validate("core", valid_payload, format_schema=fmt)
        self.assertTrue(res_ok.is_valid, f"Unexpected errors: {res_ok.errors}")

        # Missing required 'definition' field
        invalid_payload = {
            "locales": {
                "zh-TW": "locales/zh-TW.json",
            }
        }
        res_bad = ContributesValidator.validate("core", invalid_payload, format_schema=fmt)
        self.assertFalse(res_bad.is_valid)
        self.assertTrue(any("locales.definition" in e.path and "Missing required" in e.message for e in res_bad.errors))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_ft_02_contributes_aggregator_per_module_locales_buckets(self):
        """FT-02: ContributesAggregator isolates each donor module's locales under locales.__modules__."""
        mod_a_dir = uri.resolve("module://mock_loc_a", interactive=False)
        mod_b_dir = uri.resolve("module://mock_loc_b", interactive=False)
        try:
            self._setup_mock_module_locales(
                mod_a_dir,
                definition_data={"msg.hello": {"description": "Greeting A", "placeholders": ["name"]}},
                lang_files={"en": {"msg.hello": "Hello A {name}"}},
            )
            self._setup_mock_module_locales(
                mod_b_dir,
                definition_data={"msg.hello": {"description": "Greeting B", "placeholders": ["name"]}},
                lang_files={"en": {"msg.hello": "Hello B {name}"}},
            )

            agg = contributes.ContributesAggregator()
            merged = agg.scan_and_inject()
            core_locales = merged.get("core", {}).get("locales", {})
            modules_bucket = core_locales.get("__modules__", {})

            self.assertIn("mock_loc_a", modules_bucket)
            self.assertIn("mock_loc_b", modules_bucket)
            self.assertEqual(modules_bucket["mock_loc_a"]["definition"], "locales/definition.json")
            self.assertEqual(modules_bucket["mock_loc_b"]["definition"], "locales/definition.json")

            # Verify runtime resolution distinguishes mock_loc_a vs mock_loc_b
            self.assertEqual(locale.t("mock_loc_a:msg.hello", chain=["en"], name="World"), "Hello A World")
            self.assertEqual(locale.t("mock_loc_b:msg.hello", chain=["en"], name="World"), "Hello B World")
        finally:
            for d in (mod_a_dir, mod_b_dir):
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
            contributes.ContributesAggregator().scan_and_inject()
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_explicit_fallback_chain_without_implicit_hyphen_splitting(self):
        """FT-03 ([P01:DR-02]): Explicit fallback chain strictly follows declared order with zero implicit '-' splitting."""
        chain = locale.parse_locale_chain("custom-dialect-v1, zh-CHT, zh-TW, en")
        self.assertEqual(chain, ["custom-dialect-v1", "zh-CHT", "zh-TW", "en"])
        # Confirm 'custom', 'custom-dialect', and 'zh' were NOT implicitly inserted!
        self.assertNotIn("custom", chain)
        self.assertNotIn("zh", chain)

        self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "k1": {"description": "Key 1", "placeholders": []},
                "k2": {"description": "Key 2", "placeholders": []},
                "k3": {"description": "Key 3", "placeholders": []},
            },
            lang_files={
                "custom-dialect-v1": {"k1": "from_dialect"},
                "zh-TW": {"k1": "from_zh_tw", "k2": "from_zh_tw_k2"},
                "zh": {"k2": "from_zh_k2", "k3": "from_zh_k3"},
                "en": {"k1": "from_en", "k2": "from_en_k2", "k3": "from_en_k3"},
            },
        )

        # Chain 1: ["custom-dialect-v1", "zh-TW", "en"] (note: "zh" is omitted)
        c1 = ["custom-dialect-v1", "zh-TW", "en"]
        self.assertEqual(locale.t("k1", base_dir=self.tmp_dir, chain=c1), "from_dialect")
        self.assertEqual(locale.t("k2", base_dir=self.tmp_dir, chain=c1), "from_zh_tw_k2")
        # Since "zh" is not in c1 and no auto-parent splitting happens, k3 falls back directly to "en"!
        self.assertEqual(locale.t("k3", base_dir=self.tmp_dir, chain=c1), "from_en_k3")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_two_stage_recursive_noun_interpolation(self):
        """FT-04: Recursive proper-noun interpolation resolves dialect tokens along the same chain."""
        self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "cli.snippet.truncated_hint": {
                    "description": "Truncated snippet hint",
                    "placeholders": ["rem", "start", "end", "tool.read_range"],
                },
                "tool.read_range": {
                    "description": "Host range read tool proper noun",
                    "placeholders": [],
                },
            },
            lang_files={
                "nouns-antigravity": {
                    "tool.read_range": "`read_file` (`StartLine`/`EndLine`)",
                },
                "nouns-claude": {
                    "tool.read_range": "`View` (`offset`/`limit`)",
                },
                "zh-TW": {
                    "cli.snippet.truncated_hint": "... (+{rem} 行已截斷，請使用 {tool.read_range} 讀取第 {start}-{end} 行)",
                    "tool.read_range": "宿主範圍讀檔工具",
                },
                "en": {
                    "cli.snippet.truncated_hint": "... (+{rem} lines truncated, use {tool.read_range} on lines {start}-{end})",
                    "tool.read_range": "host range-read tool",
                },
            },
        )

        # 1. Antigravity dialect + zh-TW
        out_agy = locale.t(
            "cli.snippet.truncated_hint",
            base_dir=self.tmp_dir,
            chain=["nouns-antigravity", "zh-TW", "en"],
            rem=45,
            start=10,
            end=55,
        )
        self.assertEqual(out_agy, "... (+45 行已截斷，請使用 `read_file` (`StartLine`/`EndLine`) 讀取第 10-55 行)")

        # 2. Claude dialect + en
        out_claude = locale.t(
            "cli.snippet.truncated_hint",
            base_dir=self.tmp_dir,
            chain=["nouns-claude", "en"],
            rem=45,
            start=10,
            end=55,
        )
        self.assertEqual(out_claude, "... (+45 lines truncated, use `View` (`offset`/`limit`) on lines 10-55)")

        # 3. Generic fallback (no dialect layer) -> uses zh-TW's generic tool.read_range
        out_generic = locale.t(
            "cli.snippet.truncated_hint",
            base_dir=self.tmp_dir,
            chain=["zh-TW", "en"],
            rem=45,
            start=10,
            end=55,
        )
        self.assertEqual(out_generic, "... (+45 行已截斷，請使用 宿主範圍讀檔工具 讀取第 10-55 行)")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_validate_module_locales_contract_checks(self):
        """FT-05: validate_module_locales detects orphan keys, placeholder mismatches, and bad definitions."""
        # Case 1: Clean valid module
        decl_ok = self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "msg.greet": {"description": "Greet user", "placeholders": ["user", "role"]},
                "role.admin": {"description": "Admin title"},
            },
            lang_files={
                "zh-TW": {"msg.greet": "你好 {user} ({role})", "role.admin": "管理員"},
                "nouns-custom": {"role.admin": "超級管理員"},
            },
        )
        res_ok = locale.validate_module_locales("mock_mod", decl_ok, base_dir=self.tmp_dir)
        self.assertTrue(res_ok.is_valid, f"Expected valid, got: {res_ok.errors}")

        # Case 2: Orphan key + Placeholder mismatch + Missing description
        decl_bad = self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "msg.greet": {"description": "Greet user", "placeholders": ["user", "role"]},
                "bad.def": {"description": ""},
            },
            lang_files={
                "zh-TW": {
                    "msg.greets": "你好 {user} ({role})",  # Orphan typo key
                    "msg.greet": "你好 {user} ({unknown_ph})",  # Missing 'role' & undeclared 'unknown_ph'
                },
            },
        )
        res_bad = locale.validate_module_locales("mock_mod", decl_bad, base_dir=self.tmp_dir)
        self.assertFalse(res_bad.is_valid)
        err_msgs = "\n".join(str(e) for e in res_bad.errors)
        self.assertIn("missing a non-empty string 'description'", err_msgs)
        self.assertIn("Orphan locale key 'msg.greets'", err_msgs)
        self.assertIn("Did you mean 'msg.greet'?", err_msgs)
        self.assertIn("Placeholder contract mismatch for 'msg.greet'", err_msgs)
        self.assertIn("missing required placeholder(s): ['role']", err_msgs)
        self.assertIn("undeclared placeholder(s): ['unknown_ph']", err_msgs)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_cycle_and_max_depth_guard(self):
        """ET-02: Recursive interpolation safely stops on direct/indirect cycles without RecursionError."""
        self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "cycle.a": {"description": "Cycle A", "placeholders": ["cycle.b"]},
                "cycle.b": {"description": "Cycle B", "placeholders": ["cycle.a"]},
            },
            lang_files={
                "en": {
                    "cycle.a": "A->{cycle.b}",
                    "cycle.b": "B->{cycle.a}",
                }
            },
        )
        out = locale.t("cycle.a", base_dir=self.tmp_dir, chain=["en"])
        self.assertEqual(out, "A->B->{cycle.a}")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_escaped_double_braces_and_missing_kwargs_preserved(self):
        """ET-03: Escaped '{{' / '}}' are rendered as literal '{' / '}' and not treated as placeholders."""
        decl = self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "json.hint": {"description": "JSON example with literal braces", "placeholders": ["cmd"]},
            },
            lang_files={
                "en": {
                    "json.hint": "Run {cmd} with payload {{\"status\": \"ok\"}}",
                }
            },
        )
        # Verify extract_placeholders ignores {{"status": "ok"}}
        val_res = locale.validate_module_locales("mock_mod", decl, base_dir=self.tmp_dir)
        self.assertTrue(val_res.is_valid, f"Unexpected validation errors: {val_res.errors}")

        # Verify runtime formatting unescapes double braces and preserves missing kwargs safely
        rendered = locale.t("json.hint", base_dir=self.tmp_dir, chain=["en"], cmd="yscb")
        self.assertEqual(rendered, 'Run yscb with payload {"status": "ok"}')

        rendered_missing = locale.t("json.hint", base_dir=self.tmp_dir, chain=["en"])
        self.assertEqual(rendered_missing, 'Run {cmd} with payload {"status": "ok"}')
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_path_traversal_rejected(self):
        """ET-05: Locale file paths attempting '..' traversal outside module root are rejected."""
        decl = {
            "definition": "../outside_def.json",
            "en": "../../etc/passwd",
        }
        res = locale.validate_module_locales("mock_mod", decl, base_dir=self.tmp_dir)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Path traversal or outside-module path rejected" in e.message for e in res.errors))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_pt_01_lazy_import_and_hot_cache_performance(self):
        """PT-01 (NFR-01, NFR-02): PEP 562 lazy export and <0.5ms hot-path cached resolution."""
        import core
        self.assertIs(core.locale, locale)

        self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "perf.msg": {"description": "Performance benchmark msg", "placeholders": ["v", "noun.item"]},
                "noun.item": {"description": "Item noun", "placeholders": []},
            },
            lang_files={
                "nouns-agy": {"noun.item": "Artifact"},
                "zh-TW": {"perf.msg": "處理 {noun.item}: {v}", "noun.item": "項目"},
            },
        )
        # Warm up cache once
        first = locale.t("perf.msg", base_dir=self.tmp_dir, chain=["nouns-agy", "zh-TW"], v=1)
        self.assertEqual(first, "處理 Artifact: 1")

        # 100 iterations should complete well under 50ms (< 0.5ms per call)
        with self.assertExecutionTime(0.05):
            for i in range(100):
                out = locale.t("perf.msg", base_dir=self.tmp_dir, chain=["nouns-agy", "zh-TW"], v=i)
        self.assertEqual(out, "處理 Artifact: 99")
        self.mark_passed()

    @require(Requirement.LOGIC | Requirement.ENV)
    def test_rev_01_system_primary_locale_detection_and_initial_seeding(self):
        """REV-01: Primary OS language detection (final fallback ['zh']) and initial config.local.json seeding."""
        self.assertEqual(locale.DEFAULT_LOCALE_CHAIN, ["zh"])
        self.assertEqual(locale.detect_system_locale_chain("zh_TW.UTF-8"), ["zh"])
        self.assertEqual(locale.detect_system_locale_chain("zh-Hant-HK"), ["zh"])
        self.assertEqual(locale.detect_system_locale_chain("ja_JP.UTF-8"), ["ja", "zh"])
        self.assertEqual(locale.detect_system_locale_chain("en_US.UTF-8"), ["en", "zh"])
        self.assertEqual(locale.detect_system_locale_chain("C.UTF-8"), ["zh"])
        self.assertEqual(locale.detect_system_locale_chain("POSIX"), ["zh"])
        self.assertEqual(locale.detect_system_locale_chain(""), ["zh"])

        # Verify AtomicEngine._seed_or_update_config seeds fixed default in config.project.json
        # and detected OS primary language in config.local.json on first run without overwriting user edits
        from core.engine import AtomicEngine
        eng = AtomicEngine()
        cfg_proj_path = uri.resolve("config://core/config.project.json", interactive=False)
        cfg_local_path = uri.resolve("config://core/config.local.json", interactive=False)
        tpl_dir = os.path.join(self.tmp_dir, "tpl_core")
        os.makedirs(tpl_dir, exist_ok=True)
        with open(os.path.join(tpl_dir, "config.project.json"), "w", encoding="utf-8") as f:
            json.dump({"project_root": "!undefined", "locale": ["zh"]}, f)

        orig_proj = open(cfg_proj_path, "rb").read() if os.path.exists(cfg_proj_path) else None
        orig_local = open(cfg_local_path, "rb").read() if os.path.exists(cfg_local_path) else None
        old_lc_all = os.environ.get("LC_ALL")
        try:
            if os.path.exists(cfg_local_path):
                os.remove(cfg_local_path)
            os.environ["LC_ALL"] = "ja_JP.UTF-8"
            eng._seed_or_update_config("core", tpl_dir)
            self.assertTrue(os.path.exists(cfg_local_path))
            seeded_local = uri.read_json("config://core/config.local.json")
            self.assertEqual(seeded_local.get("locale"), ["ja", "zh"])

            # Second run must NOT overwrite user-customized config.local.json
            uri.write_json("config://core/config.local.json", {"locale": ["zh"]})
            os.environ["LC_ALL"] = "en_US.UTF-8"
            eng._seed_or_update_config("core", tpl_dir)
            preserved_local = uri.read_json("config://core/config.local.json")
            self.assertEqual(preserved_local.get("locale"), ["zh"])
        finally:
            if old_lc_all is None:
                os.environ.pop("LC_ALL", None)
            else:
                os.environ["LC_ALL"] = old_lc_all
            if orig_proj is not None:
                with open(cfg_proj_path, "wb") as f:
                    f.write(orig_proj)
            if orig_local is not None:
                with open(cfg_local_path, "wb") as f:
                    f.write(orig_local)
            elif os.path.exists(cfg_local_path):
                os.remove(cfg_local_path)
        self.mark_passed()

    @require(Requirement.LOGIC | Requirement.ENV)
    def test_sub02_unqualified_global_lookup_and_host_dialect_sniffing(self):
        """sub_02 (FR-01, FR-02, EC-01, EC-03): Unqualified global lookup and runtime host dialect env sniffing."""
        # 1. Verify detect_active_host_dialect across concurrent AI IDE / CLI environments
        self.assertEqual(locale.detect_active_host_dialect({"CLAUDECODE": "1"}), "nouns-claude")
        self.assertEqual(locale.detect_active_host_dialect({"CLAUDE_CODE_ENTRYPOINT": "cli"}), "nouns-claude")
        self.assertEqual(locale.detect_active_host_dialect({"CODEX_SANDBOX": "seatbelt"}), "nouns-codex")
        self.assertEqual(locale.detect_active_host_dialect({"ANTIGRAVITY_AGENT": "1"}), "nouns-antigravity")
        self.assertIsNone(locale.detect_active_host_dialect({"PATH": "/usr/bin"}))

        # 2. Verify unqualified lookup resolves agent_tool.* from agents-workflow without prefix
        self.assertEqual(
            locale.t("agent_tool.file_read_range", chain=["nouns-antigravity", "zh"]),
            "read_file (StartLine/EndLine)",
        )
        self.assertEqual(
            locale.t("agent_tool.file_read_range", chain=["nouns-claude", "zh"]),
            "Read (offset/limit)",
        )
        self.assertEqual(
            locale.t("agent_tool.file_read_range", chain=["nouns-codex", "zh"]),
            "read_file",
        )
        self.assertEqual(
            locale.t("agent_tool.file_read_range", chain=["zh"]),
            "原生檔案讀取工具（指定起訖行號區段）",
        )

        # 3. Verify Caller-First shadowing (EC-01): local module key overrides global key of the same name
        self._setup_mock_module_locales(
            self.tmp_dir,
            definition_data={
                "agent_tool.file_read_range": {"description": "Local override", "placeholders": []},
                "local.msg": {
                    "description": "Msg using global agent_tool.shell_exec",
                    "placeholders": ["agent_tool.shell_exec"],
                },
            },
            lang_files={
                "zh": {
                    "agent_tool.file_read_range": "本地自訂讀取器",
                    "local.msg": "請透過 {agent_tool.shell_exec} 執行",
                }
            },
        )
        # Local key shadows global 'agent_tool.file_read_range' when resolved from tmp_dir
        self.assertEqual(
            locale.t("agent_tool.file_read_range", base_dir=self.tmp_dir, chain=["nouns-antigravity", "zh"]),
            "本地自訂讀取器",
        )
        # Unqualified '{agent_tool.shell_exec}' inside local.msg falls back to global agents-workflow noun!
        self.assertEqual(
            locale.t("local.msg", base_dir=self.tmp_dir, chain=["nouns-claude", "zh"]),
            "請透過 Bash 執行",
        )
        self.mark_passed()



