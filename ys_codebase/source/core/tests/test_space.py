"""
Unit and boundary tests for the `core.space` atomic engine and L0 CLI (`file-space` / `fs`).
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import core
from core import uri, vfs
from core.commands import dispatcher
from core.commands.bags import CmdBags, CmdOption
from core.space import (
    BinarySnapshotManager,
    FileFingerprint,
    HashPolicy,
    SnapshotState,
    SpaceConfig,
    SpaceCycleError,
    SpaceError,
    SpaceNotFoundError,
    SpaceRegistry,
    SpaceScanner,
    ack,
    broadcast_file_space_changed,
    clean,
    clear_subscribers,
    compute_file_hash,
    consume_diff,
    define_ephemeral_space,
    diff,
    get_active_watcher,
    get_default_registry,
    get_default_scanner,
    hash_space_or_path,
    hash_target,
    is_watcher_active,
    iter_space_files,
    match_path,
    merkle_root,
    notify_subscribers,
    patch_files,
    read_watcher_state,
    refresh,
    register_active_watcher,
    remove_watcher_state,
    reset_cursor,
    reset_default_instances,
    resolve_file_path,
    resolve_watcher_dirty_path,
    resolve_watcher_state_path,
    scan,
    snapshot,
    status,
    subscribe,
    write_watcher_state,
)
from core.validator import ContributesValidator
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from tests import load_core_cli_module


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestCoreSpaceAtomicEngine(YSCBTestCase):
    """Verify `core.space` schema, `<owner>/<name>` registry, presets, three-coordinate matcher, scandir walker, hasher, and L0 CLI."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_core_space_"))
        self.proj_root = self.temp_dir / "workspace"
        self.yscb_root = self.proj_root / "ys_codebase"
        self.proj_root.mkdir(parents=True, exist_ok=True)
        self.yscb_root.mkdir(parents=True, exist_ok=True)

        # Write minimal yscb.config.json and config/core/config.project.json for uri.host_scope
        vfs.write_json(str(self.proj_root / "yscb.config.json"), {"yscb_dir": "./ys_codebase"})
        cfg_core_dir = self.yscb_root / "config" / "core"
        cfg_core_dir.mkdir(parents=True, exist_ok=True)
        vfs.write_json(str(cfg_core_dir / "config.project.json"), {"project_root": "./"})

    def tearDown(self) -> None:
        clear_subscribers()
        register_active_watcher(None)
        reset_default_instances()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def _write_module_core_contrib(self, mod_name: str, payload: dict) -> Path:
        c_dir = self.yscb_root / ".modules" / mod_name / "contributes"
        c_dir.mkdir(parents=True, exist_ok=True)
        c_file = c_dir / "core.json"
        vfs.write_json(str(c_file), payload)
        return c_file

    def _write_project_core_contrib(self, payload: dict) -> Path:
        c_dir = self.yscb_root / "config" / "core"
        c_dir.mkdir(parents=True, exist_ok=True)
        c_file = c_dir / "contribute.json"
        vfs.write_json(str(c_file), payload)
        return c_file

    def test_schema_validation_and_default_include_exclude_priority(self) -> None:
        """Verify `_format.json` schema validation for unified `spaces`, rule-only space (`entries=()`, `compose=()`), and symmetric `CompiledRuleSet`."""
        self.assertIn("space", core.__all__)
        self.assertIs(core.space.SpaceRegistry, SpaceRegistry)
        self.assertFalse(hasattr(core.space, "PresetConfig"))
        self.assertFalse(hasattr(core.space, "GitignoreEvaluator"))

        fmt_path = Path(uri.resolve("module.source://core/contributes/_format.json"))
        fmt_schema = vfs.read_json(str(fmt_path))
        meta_res = ContributesValidator.validate_format_schema(fmt_schema)
        self.assertTrue(meta_res.is_valid, meta_res.format_report())

        valid_payload = {
            "spaces": {
                "py-only": {
                    "description": "Python files only (pure rule space)",
                    "include": ["*.py"],
                    "exclude": ["*_pb2.py"],
                },
                "code": {
                    "description": "Code space",
                    "entries": ["project://src"],
                    "presets": ["py-only", "!gitignore"],
                    "hash_policy": "adaptive",
                    "large_file_threshold_mb": 15,
                    "follow_symlinks": False,
                },
                "pure_composite": {
                    "description": "Pure compose space without entries",
                    "compose": ["code", "!gitignore"],
                },
            },
        }
        val_res = ContributesValidator.validate(
            "core", valid_payload, donor_mod="test_mod", format_schema=fmt_schema
        )
        self.assertTrue(val_res.is_valid, val_res.format_report())

        # Negative validation: invalid hash_policy
        bad_payload = {
            "spaces": {
                "broken": {
                    "entries": ["project://src"],
                    "hash_policy": "invalid_policy",
                }
            }
        }
        bad_res = ContributesValidator.validate(
            "core", bad_payload, donor_mod="test_mod", format_schema=fmt_schema
        )
        self.assertFalse(bad_res.is_valid)

        # Pure rule-template SpaceConfig (entries=() and compose=()) is valid and evaluates to empty set
        empty_cfg = SpaceConfig(
            qualified_name="project/rule_template",
            owner="project",
            short_name="rule_template",
            entries=(),
            compose=(),
            include=("*.py",),
        )
        self.assertEqual(empty_cfg.entries, ())
        self.assertEqual(empty_cfg.compose, ())

        # SpaceConfig invalid hash_policy and threshold raises SpaceError
        with self.assertRaises(SpaceError):
            SpaceConfig(
                qualified_name="project/bad",
                owner="project",
                short_name="bad",
                entries=("src",),
                hash_policy="not_a_policy",  # type: ignore[arg-type]
            )
        with self.assertRaises(SpaceError):
            SpaceConfig(
                qualified_name="project/bad_thresh",
                owner="project",
                short_name="bad_thresh",
                entries=("src",),
                large_file_threshold_mb=0,
            )

        # Default include=["*"] and symmetric CompiledRuleSet (dir prefix & segment matching in both include & exclude)
        src_dir = self.proj_root / "src"
        sub_dir = src_dir / "nested_dir"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "keep.py").write_text("print(1)\n", encoding="utf-8")
        (src_dir / "secret.py").write_text("print(2)\n", encoding="utf-8")
        (sub_dir / "inside.txt").write_text("inside\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/rule_only": {
                    "include": ["*.py"],
                },
                "project/app": {
                    "entries": ["src"],
                    "include": ["*.py", "nested_dir/"],
                    "exclude": ["secret.py"],
                },
                "project/all_files": {
                    "entries": ["src"],
                },
            },
        )
        all_cfg = reg.resolve_spaces("project/all_files")[0]
        self.assertEqual([r.raw_pattern for r in all_cfg.effective_include], ["*"])
        self.assertEqual(reg.iter_space_files("project/rule_only"), [])
        m_rule_only = reg.match_path(src_dir / "keep.py", "project/rule_only")
        self.assertFalse(m_rule_only.matched)
        self.assertEqual(m_rule_only.details[0].reason, "outside_entries")

        matched_files = [f.rel_path for f in reg.iter_space_files("project/app")]
        self.assertEqual(matched_files, ["src/keep.py", "src/nested_dir/inside.txt"])
        self.mark_passed()

    def test_namespace_isolation_and_short_name_union_addressing(self) -> None:
        """Verify `<owner>/<name>` isolation, `/<short-name>` synthetic space generation, and short-name union without cross-contamination."""
        docs_mod_a = self.proj_root / "docs_a"
        docs_proj = self.proj_root / "docs_proj"
        docs_mod_a.mkdir(parents=True, exist_ok=True)
        docs_proj.mkdir(parents=True, exist_ok=True)

        (docs_mod_a / "guide.md").write_text("# A Guide\n", encoding="utf-8")
        (docs_mod_a / "draft.tmp").write_text("temp\n", encoding="utf-8")
        (docs_proj / "readme.md").write_text("# Proj Readme\n", encoding="utf-8")
        (docs_proj / "notes.txt").write_text("notes\n", encoding="utf-8")

        self._write_module_core_contrib(
            "mod_a",
            {
                "spaces": {
                    "ignore_rules": {"exclude": ["*.tmp"]},
                    "docs": {
                        "description": "Module A docs",
                        "entries": ["project://docs_a"],
                        "presets": ["mod_a/ignore_rules"],
                        "include": ["*.md", "*.tmp"],
                    },
                },
            },
        )
        self._write_project_core_contrib(
            {
                "spaces": {
                    "ignore_rules": {"exclude": ["*.bak"]},
                    "docs": {
                        "description": "Project docs",
                        "entries": ["project://docs_proj", "project://docs_a/guide.md"],
                        "include": ["*.md"],
                    },
                },
            }
        )

        reg = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)

        # 1. Qualified lookup returns isolated single definition
        mod_a_spaces = reg.resolve_spaces("mod_a/docs")
        self.assertEqual(len(mod_a_spaces), 1)
        self.assertEqual(mod_a_spaces[0].owner, "mod_a")
        self.assertEqual(mod_a_spaces[0].description, "Module A docs")

        proj_spaces = reg.resolve_spaces("project/docs")
        self.assertEqual(len(proj_spaces), 1)
        self.assertEqual(proj_spaces[0].owner, "project")

        # 2. Synthetic `/<short-name>` space is automatically created and composed of `<owner>/<short-name>`
        synth_spaces = reg.resolve_spaces("/docs")
        self.assertEqual(len(synth_spaces), 1)
        self.assertEqual(synth_spaces[0].qualified_name, "/docs")
        self.assertEqual(synth_spaces[0].owner, "")
        self.assertEqual(synth_spaces[0].entries, ())
        self.assertEqual(synth_spaces[0].compose, ("mod_a/docs", "project/docs"))

        # Short-name lookup `<short-name>` returns the synthesized union space `/docs` composed of concrete definitions
        union_spaces = reg.resolve_spaces("docs")
        self.assertEqual([s.qualified_name for s in union_spaces], ["/docs"])
        self.assertEqual(list(union_spaces[0].compose), ["mod_a/docs", "project/docs"])

        # 3. Union traversal deduplicates overlapping physical file `docs_a/guide.md` and records both matched_spaces
        for q_str in ("docs", "/docs"):
            union_files = reg.iter_space_files(q_str)
            by_rel = {f.rel_path: f for f in union_files}
            self.assertEqual(sorted(by_rel.keys()), ["docs_a/guide.md", "docs_proj/readme.md"])
            self.assertEqual(
                by_rel["docs_a/guide.md"].matched_spaces,
                ("mod_a/docs", "project/docs"),
            )
            self.assertEqual(
                by_rel["docs_proj/readme.md"].matched_spaces,
                ("project/docs",),
            )
        self.mark_passed()

    def test_presets_rule_reference_negated_preset_and_subtree_pruning(self) -> None:
        """Verify `presets` rule pulling, `!<space>` inverted exclusion, and local subtree pruning invariant (`EC-03`)."""
        logs_dir = self.proj_root / "logs"
        venv_dir = logs_dir / ".venv" / "lib"
        build_dir = logs_dir / "build" / "sub"
        venv_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)

        (logs_dir / "app.py").write_text("x = 1\n", encoding="utf-8")
        (logs_dir / "debug.log").write_text("debug\n", encoding="utf-8")
        (logs_dir / "important.log").write_text("important\n", encoding="utf-8")
        (venv_dir / "pkg.py").write_text("pkg = 1\n", encoding="utf-8")
        (build_dir / "drop.txt").write_text("drop\n", encoding="utf-8")
        (logs_dir / "build" / "keep.txt").write_text("keep\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "core/gitignore": {
                    "entries": ["project://"],
                    "include": ["*.log", ".venv/**", "build/**"],
                    "exclude": ["important.log", "build/keep.txt"],
                    "watch": False,
                },
                "project/no_gitignore": {
                    "entries": ["logs"],
                    "presets": ["missing_preset_name"],
                },
                "project/with_neg_gitignore": {
                    "entries": ["logs"],
                    "presets": ["!core/gitignore"],
                },
            },
        )

        # 1. Unresolved preset recorded without crash
        no_gi_cfg = reg.resolve_spaces("project/no_gitignore")[0]
        self.assertEqual(no_gi_cfg.unresolved_presets, ("missing_preset_name",))
        no_gi_files = [f.rel_path for f in reg.iter_space_files("project/no_gitignore")]
        self.assertIn("logs/debug.log", no_gi_files)
        self.assertIn("logs/.venv/lib/pkg.py", no_gi_files)

        # 2. `!core/gitignore` excludes files matching `gitignore.include` unless exempted by `gitignore.exclude`,
        #    and prunes `.venv` subtree at os.scandir level while entering `build` to keep `build/keep.txt` (EC-03).
        scandir_calls: list[str] = []
        real_scandir = os.scandir

        def _spy_scandir(path):
            scandir_calls.append(Path(path).as_posix())
            return real_scandir(path)

        with patch("core.space.registry.os.scandir", side_effect=_spy_scandir):
            with_gi_files = [f.rel_path for f in reg.iter_space_files("project/with_neg_gitignore")]

        self.assertEqual(
            with_gi_files,
            ["logs/app.py", "logs/build/keep.txt", "logs/important.log"],
        )
        for called_p in scandir_calls:
            self.assertNotIn(".venv", called_p)
        self.assertTrue(any(called_p.endswith("/logs/build") for called_p in scandir_calls))
        self.mark_passed()

    def test_three_coordinate_rules_and_single_point_match_explain(self) -> None:
        """Verify Coordinate 1 (URI), Coordinate 2 (project_rel & entry_rel), and Coordinate 3 (name/segment) + `match_path`."""
        pkg_dir = self.yscb_root / "source" / "core" / "subpkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        py_file = pkg_dir / "engine.py"
        py_file.write_text("x = 1\n", encoding="utf-8")

        cache_dir = self.yscb_root / ".cache" / "temp"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_py = cache_dir / "cached.py"
        cached_py.write_text("y = 2\n", encoding="utf-8")

        archived_dir = self.proj_root / "plans" / "archived"
        archived_dir.mkdir(parents=True, exist_ok=True)
        archived_md = archived_dir / "old.md"
        archived_md.write_text("# old\n", encoding="utf-8")

        active_dir = self.proj_root / "plans" / "active"
        active_dir.mkdir(parents=True, exist_ok=True)
        active_md = active_dir / "spec.md"
        active_md.write_text("# spec\n", encoding="utf-8")
        pycache_file = active_dir / "__pycache__" / "mod.pyc"
        pycache_file.parent.mkdir(parents=True, exist_ok=True)
        pycache_file.write_bytes(b"00")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "core/std_ignore": {
                    "exclude": [
                        "yscb://.cache/**",       # Coordinate 1: Semantic URI prefix
                        "plans/archived/**",      # Coordinate 2: Relative to project://
                        "subpkg/ignored_*.py",    # Coordinate 2: Relative to entry (module.source://core)
                        "__pycache__",            # Coordinate 3: Segment name without '/'
                    ]
                },
                "core/workspace": {
                    "entries": [
                        "project://plans",
                        "yscb://source/core",
                        "yscb://.cache",
                    ],
                    "presets": ["core/std_ignore"],
                    "include": ["*.py", "*.md"],
                },
            },
        )

        ignored_entry_rel = pkg_dir / "ignored_helper.py"
        ignored_entry_rel.write_text("z = 3\n", encoding="utf-8")

        # 1. Positive match via entry_rel / extension
        m_ok = match_path(py_file, "core/workspace", registry=reg)
        self.assertTrue(m_ok.matched)
        self.assertEqual(m_ok.matched_spaces, ("core/workspace",))
        self.assertEqual(m_ok.details[0].reason, "included")
        self.assertEqual(m_ok.details[0].include_rule, "*.py")

        # 2. Excluded by Coordinate 1 (URI rule: yscb://.cache/**)
        m_uri_ex = reg.match_path(cached_py, "core/workspace")
        self.assertFalse(m_uri_ex.matched)
        self.assertEqual(m_uri_ex.details[0].reason, "excluded")
        self.assertEqual(m_uri_ex.details[0].exclude_rule, "yscb://.cache/**")
        self.assertEqual(m_uri_ex.details[0].exclude_source, "preset:core/std_ignore")

        # 3. Excluded by Coordinate 2 (project_rel rule: plans/archived/**)
        m_proj_rel = reg.match_path(archived_md, "core/workspace")
        self.assertFalse(m_proj_rel.matched)
        self.assertEqual(m_proj_rel.details[0].exclude_rule, "plans/archived/**")

        # 4. Excluded by Coordinate 2 (entry_rel rule: subpkg/ignored_*.py relative to yscb://source/core)
        m_entry_rel = reg.match_path(ignored_entry_rel, "core/workspace")
        self.assertFalse(m_entry_rel.matched)
        self.assertEqual(m_entry_rel.details[0].exclude_rule, "subpkg/ignored_*.py")

        # 5. Excluded by Coordinate 3 (directory segment name: __pycache__)
        m_seg = reg.match_path(pycache_file, "core/workspace")
        self.assertFalse(m_seg.matched)
        self.assertEqual(m_seg.details[0].exclude_rule, "__pycache__")

        # 6. Path outside all entries
        outside_file = self.temp_dir / "outside.py"
        outside_file.write_text("pass\n", encoding="utf-8")
        m_out = reg.match_path(outside_file, "core/workspace")
        self.assertFalse(m_out.matched)
        self.assertEqual(m_out.details[0].reason, "outside_entries")
        self.mark_passed()

    def test_scandir_directory_pruning_and_edge_cases(self) -> None:
        """Verify `os.scandir` directory pruning skips excluded subtrees (0 inner scandirs) and handles missing/external/symlink entries."""
        root_entry = self.proj_root / "app"
        pruned_dir = root_entry / "node_modules" / "deep_pkg"
        pruned_dir.mkdir(parents=True, exist_ok=True)
        (pruned_dir / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
        (root_entry / "main.py").write_text("print('ok')\n", encoding="utf-8")

        # External entry outside project_root
        ext_dir = self.temp_dir / "external_shared"
        ext_dir.mkdir(parents=True, exist_ok=True)
        (ext_dir / "shared.py").write_text("SHARED = True\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/pruned": {
                    "entries": [
                        "project://app",
                        "project://non_existent_dir",  # missing entry on disk
                        ext_dir.as_posix(),            # entry outside project://
                    ],
                    "exclude": ["node_modules"],
                }
            },
        )

        # Spy on os.scandir to prove `node_modules` is never entered
        scandir_calls: list[str] = []
        real_scandir = os.scandir

        def _spy_scandir(path):
            scandir_calls.append(Path(path).as_posix())
            return real_scandir(path)

        with patch("core.space.registry.os.scandir", side_effect=_spy_scandir):
            files = iter_space_files("project/pruned", registry=reg)

        rel_paths = [f.rel_path for f in files]
        self.assertEqual(rel_paths, ["app/main.py", "external_shared/shared.py"])
        for called_p in scandir_calls:
            self.assertNotIn("node_modules", called_p)

        # Verify diagnostics on resolved_entries (exists: false)
        space_dict = reg.resolve_spaces("project/pruned")[0].to_dict(self.proj_root)
        by_entry = {e["entry"]: e for e in space_dict["resolved_entries"]}
        self.assertFalse(by_entry["project://non_existent_dir"]["exists"])
        self.assertTrue(by_entry["project://app"]["exists"])

        # Verify symlink loop and broken symlink safety when follow_symlinks=True
        sym_root = self.proj_root / "sym_space"
        sym_root.mkdir(parents=True, exist_ok=True)
        (sym_root / "real.txt").write_text("hello\n", encoding="utf-8")
        loop_link = sym_root / "loop_self"
        broken_link = sym_root / "broken_target"
        symlinks_supported = True
        try:
            os.symlink(str(sym_root), str(loop_link))
            os.symlink(str(sym_root / "does_not_exist.txt"), str(broken_link))
        except (OSError, NotImplementedError):
            symlinks_supported = False

        if symlinks_supported:
            sym_reg = SpaceRegistry(
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
                raw_spaces={
                    "project/sym": {
                        "entries": ["sym_space"],
                        "follow_symlinks": True,
                    }
                },
            )
            sym_files = sym_reg.iter_space_files("project/sym")
            self.assertEqual([f.rel_path for f in sym_files], ["sym_space/real.txt"])
        self.mark_passed()

    def test_atomic_hasher_policies_and_merkle_root_determinism(self) -> None:
        """Verify `stat_only`, `full_hash`, and `adaptive` (sparse sample) hashing and deterministic `merkle_root`."""
        data_dir = self.proj_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        small_f = data_dir / "small.txt"
        small_f.write_text("deterministic payload\n", encoding="utf-8")

        # Create a 2MB file to trigger adaptive sparse sampling when large_file_threshold_mb=1
        large_f = data_dir / "large.bin"
        large_f.write_bytes(b"A" * (64 * 1024) + b"B" * (2 * 1024 * 1024))

        h_stat = compute_file_hash(small_f, policy=HashPolicy.STAT_ONLY)
        self.assertTrue(h_stat.startswith("stat:"))

        h_full = compute_file_hash(small_f, policy=HashPolicy.FULL_HASH)
        self.assertEqual(len(h_full), 32)  # 16-byte Blake2b hex digest

        h_large_adaptive = compute_file_hash(
            large_f, policy=HashPolicy.ADAPTIVE, large_file_threshold_mb=1
        )
        self.assertTrue(h_large_adaptive.startswith("sample2b:"))

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/data_space": {
                    "entries": ["data"],
                    "hash_policy": "adaptive",
                    "large_file_threshold_mb": 1,
                }
            },
        )

        res1 = hash_target(reg, "project/data_space")
        res2 = hash_space_or_path("project/data_space", registry=reg)
        self.assertEqual(res1.file_count, 2)
        self.assertEqual(res1.merkle_root, res2.merkle_root)
        self.assertEqual(len(res1.merkle_root), 32)

        # Single-file target hashing via hash_target
        single_res = hash_target(reg, str(small_f), policy="full_hash")
        self.assertEqual(single_res.target_type, "file")
        self.assertEqual(single_res.file_count, 1)
        self.assertEqual(single_res.files[0].content_hash, h_full)

        # Negative test: unknown space or file raises SpaceNotFoundError
        with self.assertRaises(SpaceNotFoundError):
            hash_target(reg, "unknown_owner/no_such_space")
        with self.assertRaises(SpaceError):
            compute_file_hash(small_f, policy="invalid_policy_name")
        self.mark_passed()

    def test_l0_cli_dual_routing_and_commands(self) -> None:
        """Verify `core file-space <subcmd>` and `fs <subcmd>` L0 CLI handlers, `--json` output, unknown-space exit code 1, and `dispatcher.py` external module coexistence."""
        src_dir = self.proj_root / "cli_src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "hello.py").write_text("print('hi')\n", encoding="utf-8")

        self._write_project_core_contrib(
            {
                "spaces": {
                    "cli_preset": {
                        "description": "CLI test preset space",
                        "exclude": ["*.tmp"],
                    },
                    "cli_space": {
                        "description": "CLI test space",
                        "entries": ["project://cli_src"],
                        "presets": ["project/cli_preset"],
                        "include": ["*.py"],
                    },
                },
            }
        )

        cli_mod = load_core_cli_module()

        with uri.host_scope(str(self.proj_root), str(self.yscb_root)):
            # 1. `fs spaces --json` and `file_space_spaces`
            buf_spaces = io.StringIO()
            with redirect_stdout(buf_spaces):
                rc = cli_mod.fs_spaces(
                    CmdBags(
                        raw_cmd="fs spaces cli_space --json",
                        command="fs_spaces",
                        args=["cli_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc, 0)
            spaces_json = json.loads(buf_spaces.getvalue())
            self.assertEqual(spaces_json["status"], "ok")
            self.assertEqual(spaces_json["count"], 1)
            self.assertIn(spaces_json["spaces"][0]["qualified_name"], ("/cli_space", "project/cli_space"))

            # Human-readable spaces output
            buf_spaces_txt = io.StringIO()
            with redirect_stdout(buf_spaces_txt):
                rc_txt = cli_mod.file_space(
                    CmdBags(
                        raw_cmd="file-space spaces",
                        command="file_space",
                        args=["spaces"],
                        options={},
                    )
                )
            self.assertEqual(rc_txt, 0)
            self.assertIn("project/cli_space", buf_spaces_txt.getvalue())

            # 2. Verify `fs_presets` and `file_space_presets` are removed from CLI module
            self.assertFalse(hasattr(cli_mod, "fs_presets"))
            self.assertFalse(hasattr(cli_mod, "file_space_presets"))

            # 3. `fs match --json`
            buf_match = io.StringIO()
            with redirect_stdout(buf_match):
                rc_m = cli_mod.file_space_match(
                    CmdBags(
                        raw_cmd="file-space match cli_src/hello.py cli_space --json",
                        command="file_space_match",
                        args=["cli_src/hello.py", "cli_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_m, 0)
            match_json = json.loads(buf_match.getvalue())
            self.assertTrue(match_json["matched"])
            self.assertEqual(match_json["matched_spaces"], ["project/cli_space"])

            # 4. `fs ls --json`
            buf_ls = io.StringIO()
            with redirect_stdout(buf_ls):
                rc_ls = cli_mod.fs_ls(
                    CmdBags(
                        raw_cmd="fs ls cli_space --json",
                        command="fs_ls",
                        args=["cli_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_ls, 0)
            ls_json = json.loads(buf_ls.getvalue())
            self.assertEqual(ls_json["count"], 1)
            self.assertEqual(ls_json["files"][0]["rel_path"], "cli_src/hello.py")

            # 5. `fs hash --json`
            buf_hash = io.StringIO()
            with redirect_stdout(buf_hash):
                rc_h = cli_mod.fs_hash(
                    CmdBags(
                        raw_cmd="fs hash cli_space --json",
                        command="fs_hash",
                        args=["cli_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_h, 0)
            hash_json = json.loads(buf_hash.getvalue())
            self.assertEqual(hash_json["file_count"], 1)
            self.assertTrue(len(hash_json["merkle_root"]) == 32)

            # 6. Unknown space returns exit code 1 in both JSON and human modes
            buf_err_json = io.StringIO()
            with redirect_stdout(buf_err_json):
                rc_err_j = cli_mod.fs_ls(
                    CmdBags(
                        raw_cmd="fs ls non_existent_space --json",
                        command="fs_ls",
                        args=["non_existent_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_err_j, 1)
            err_payload = json.loads(buf_err_json.getvalue())
            self.assertEqual(err_payload["status"], "error")
            self.assertEqual(err_payload["error_type"], "SpaceNotFoundError")

            buf_err_txt = io.StringIO()
            with redirect_stderr(buf_err_txt):
                rc_err_t = cli_mod.fs_ls(
                    CmdBags(
                        raw_cmd="fs ls non_existent_space",
                        command="fs_ls",
                        args=["non_existent_space"],
                        options={},
                    )
                )
            self.assertEqual(rc_err_t, 1)
            self.assertIn("not registered", buf_err_txt.getvalue())

        # 7. Verify dispatcher routes both top-level `file-space` and `fs` directly to `core`
        dispatcher.clear_cache()
        try:
            core_src_contrib = Path(uri.resolve("module.source://core/contributes/core.json"))
            self._write_module_core_contrib("core", vfs.read_json(str(core_src_contrib)))
            with uri.host_scope(str(self.proj_root), str(self.yscb_root)):
                with (
                    patch("core.commands.dispatcher._try_hot_dispatch", return_value=None),
                    patch("core.commands.dispatcher.dispatch_local", return_value=0) as mock_dl,
                ):
                    rc1 = dispatcher.dispatch(["file-space", "status"])
                    self.assertEqual(rc1, 0)
                    self.assertEqual(mock_dl.call_args[1]["module_name"], "core")
                    self.assertEqual(mock_dl.call_args[1]["cmd_name"], ["file-space", "status"])

                    # Explicit `core file-space spaces` routes to `core`
                    rc2 = dispatcher.dispatch(["core", "file-space", "spaces"])
                    self.assertEqual(rc2, 0)
                    self.assertEqual(mock_dl.call_args[1]["module_name"], "core")
                    self.assertEqual(mock_dl.call_args[1]["cmd_name"], ["file-space", "spaces"])

                    # Top-level `fs spaces` routes directly to `core`
                    rc3 = dispatcher.dispatch(["fs", "spaces"])
                    self.assertEqual(rc3, 0)
                    self.assertEqual(mock_dl.call_args[1]["module_name"], "core")
                    self.assertEqual(mock_dl.call_args[1]["cmd_name"], ["fs", "spaces"])
        finally:
            dispatcher.clear_cache()
        self.mark_passed()

    def test_compose_algebra_set_difference_and_cycle_detection(self) -> None:
        """Verify `compose` absolute file-set union (no secondary parent filtering), `!<space>` file-set difference, and `SpaceCycleError`."""
        dir_a = self.proj_root / "mod_a"
        dir_b = self.temp_dir / "ext_mod_b" / "nested"
        dir_own = self.proj_root / "own_dir"
        dir_a.mkdir(parents=True, exist_ok=True)
        dir_b.mkdir(parents=True, exist_ok=True)
        dir_own.mkdir(parents=True, exist_ok=True)

        (dir_a / "a_code.py").write_text("a = 1\n", encoding="utf-8")
        (dir_a / "a_doc.md").write_text("# doc a\n", encoding="utf-8")
        (dir_b / "b_code.py").write_text("b = 2\n", encoding="utf-8")
        (dir_b / "b_secret.py").write_text("secret = 3\n", encoding="utf-8")
        (dir_own / "own_note.txt").write_text("note\n", encoding="utf-8")
        (dir_own / "own_code.py").write_text("own = 4\n", encoding="utf-8")

        ext_entry_root = self.temp_dir / "ext_mod_b"

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "mod_a/base": {
                    "entries": ["project://mod_a"],
                    "include": ["*.py", "*.md"],
                },
                "mod_b/ext": {
                    "entries": [ext_entry_root.as_posix()],
                    "include": ["*.py"],
                },
                "mod_b/secrets": {
                    "entries": [ext_entry_root.as_posix()],
                    "include": ["nested/b_secret.py"],
                },
                "project/union_all": {
                    "compose": ["mod_a/base", "mod_b/ext", "!mod_b/secrets", "missing/non_existent"],
                    "entries": ["project://own_dir"],
                    "include": ["*.txt"],  # Only filters own_dir (does NOT filter composed mod_a/base or mod_b/ext)
                },
            },
        )

        # 1. Verify unresolved_compose diagnostics
        union_cfg = reg.resolve_spaces("project/union_all")[0]
        self.assertEqual(union_cfg.unresolved_compose, ("missing/non_existent",))

        # 2. Verify `project/union_all`: parent `include: ["*.txt"]` filters only `own_dir` (`own_note.txt` kept, `own_code.py` dropped),
        #    while composed `mod_a/base` and `mod_b/ext` keep their `.py`/`.md` files and `!mod_b/secrets` subtracts `b_secret.py`.
        union_files = reg.iter_space_files("project/union_all")
        union_rels = [f.rel_path for f in union_files]
        self.assertEqual(
            union_rels,
            [
                "ext_mod_b/nested/b_code.py",
                "mod_a/a_code.py",
                "mod_a/a_doc.md",
                "own_dir/own_note.txt",
            ],
        )

        # 3. Verify `collect_all_entry_paths` expands only positive `compose` (ignores `!mod_b/secrets`)
        entry_paths = reg.collect_all_entry_paths("project/union_all")
        self.assertIn(dir_a.resolve(), [p.resolve() for p in entry_paths])
        self.assertIn(dir_own.resolve(), [p.resolve() for p in entry_paths])

        # 4. Verify `match_path` provenance on composed space and negative `!compose`
        m_inc = reg.match_path(dir_b / "b_code.py", "project/union_all")
        self.assertTrue(m_inc.matched)
        self.assertIn("compose:mod_b/ext", m_inc.details[0].matched_entry or "")

        m_exc = reg.match_path(dir_b / "b_secret.py", "project/union_all")
        self.assertFalse(m_exc.matched)

        # 5. Verify direct and indirect cycle detection (both `compose` and `presets`) raises SpaceCycleError
        cycle_reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/c1": {"compose": ["project/c2"]},
                "project/c2": {"compose": ["project/c1"]},
            },
        )
        with self.assertRaises(SpaceCycleError):
            cycle_reg.iter_space_files("project/c1")
        with self.assertRaises(SpaceCycleError):
            cycle_reg.match_path(dir_a / "a_code.py", "project/c1")

        with self.assertRaises(SpaceCycleError):
            SpaceRegistry(
                project_root=self.proj_root,
                yscb_dir=self.yscb_root,
                raw_spaces={
                    "project/p1": {"presets": ["project/p2"]},
                    "project/p2": {"presets": ["!project/p1"]},
                },
            )
        self.mark_passed()

    def test_resolve_file_path_four_stage_injection_and_runtime_register_space(self) -> None:
        """Verify `resolve_file_path`, four-stage rule union (`[*] ∪ [*.py] = [*]`), `__unknown__` default owner, and `register_space`/`unregister_space`."""
        nav_dir = self.proj_root / "nav"
        nav_dir.mkdir(parents=True, exist_ok=True)
        f_ok = nav_dir / "valid.py"
        f_ex = nav_dir / "ignored.tmp"
        f_md = nav_dir / "readme.md"
        f_ok.write_text("ok = True\n", encoding="utf-8")
        f_ex.write_text("tmp\n", encoding="utf-8")
        f_md.write_text("# doc\n", encoding="utf-8")

        ext_dir = self.temp_dir / "ext_lib"
        ext_dir.mkdir(parents=True, exist_ok=True)
        f_ext = ext_dir / "util.py"
        f_ext.write_text("util = 1\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/nav_space": {
                    "entries": ["project://nav", ext_dir.as_posix()],
                    "include": ["*.py"],
                    "exclude": ["*.tmp"],
                }
            },
        )

        # 1. resolve_file_path resolves project-relative and external-entry relative paths
        resolved_ok = resolve_file_path("nav/valid.py", "project/nav_space", registry=reg)
        self.assertIsNotNone(resolved_ok)
        self.assertEqual(resolved_ok.resolve(), f_ok.resolve())

        resolved_ext = reg.resolve_file_path("ext_lib/util.py", "project/nav_space")
        self.assertIsNotNone(resolved_ext)
        self.assertEqual(resolved_ext.resolve(), f_ext.resolve())

        self.assertIsNone(reg.resolve_file_path("nav/ignored.tmp", "project/nav_space"))
        self.assertIsNone(reg.resolve_file_path("nav/missing.py", "project/nav_space"))

        # 2. Runtime `register_space` without `<owner>/` defaults to `__unknown__/<short-name>`
        #    (`define_ephemeral_space` forwards to `register_space`)
        dyn_cfg = define_ephemeral_space(
            "temp_view",
            {"entries": ["project://nav"], "include": ["*.py"]},
            registry=reg,
        )
        self.assertEqual(dyn_cfg.qualified_name, "__unknown__/temp_view")
        self.assertEqual(dyn_cfg.owner, "__unknown__")
        self.assertFalse(hasattr(dyn_cfg, "is_ephemeral"))

        # 3. Rule-level absolute union on the same `<owner>/<short-name>`:
        #    injecting `include: ["*"]` into `project/nav_space` makes `[*] ∪ [*.py] = [*]` while uniting `exclude`
        reg.register_space(
            "project/nav_space",
            {"include": ["*"], "exclude": ["util.py"]},
        )
        merged_nav = reg.resolve_spaces("project/nav_space")[0]
        self.assertEqual(merged_nav.include, ("*",))
        self.assertEqual(merged_nav.exclude, ("*.tmp", "util.py"))
        nav_rels = [f.rel_path for f in reg.iter_space_files("project/nav_space")]
        self.assertIn("nav/readme.md", nav_rels)
        self.assertNotIn("ext_lib/util.py", nav_rels)

        # 4. `unregister_space` removes runtime-injected space
        self.assertTrue(reg.unregister_space("__unknown__/temp_view"))
        with self.assertRaises(SpaceNotFoundError):
            reg.resolve_spaces("__unknown__/temp_view")
        self.mark_passed()

    def test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors(self) -> None:
        """Verify `YFP2` binary snapshot, corruption recovery, `patch_files` multi-space deletion, and `consume_diff` rollback/commit."""
        work_dir = self.proj_root / "pkg"
        work_dir.mkdir(parents=True, exist_ok=True)
        f1 = work_dir / "a.py"
        f2 = work_dir / "b.py"
        f1.write_text("v = 1\n", encoding="utf-8")
        f2.write_text("v = 2\n", encoding="utf-8")

        ext_dir = self.temp_dir / "ext_data"
        ext_dir.mkdir(parents=True, exist_ok=True)
        f_ext = ext_dir / "ext.py"
        f_ext.write_text("ext = 10\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "mod_x/code": {
                    "entries": ["project://pkg"],
                    "include": ["*.py"],
                },
                "project/code": {
                    "entries": [ext_dir.as_posix()],
                    "include": ["*.py"],
                },
            },
        )
        storage_dir = self.yscb_root / ".storage.local" / "core" / "space"
        scanner = SpaceScanner(registry=reg, storage_root=storage_dir)

        # 1. Initial scan (generation 0 -> 1) and 100% Merkle root parity with hash_target
        s_res1 = scan("code", scanner=scanner)
        self.assertEqual(s_res1.from_generation, 0)
        self.assertEqual(s_res1.to_generation, 1)
        self.assertEqual(s_res1.added_count, 3)

        h_res = hash_target(reg, "code")
        self.assertEqual(s_res1.merkle_root, h_res.merkle_root)
        self.assertEqual(merkle_root("code", scanner=scanner), h_res.merkle_root)

        # 2. Second scan with no changes keeps generation 1
        s_res2 = refresh("code", scanner=scanner)
        self.assertEqual(s_res2.to_generation, 1)
        self.assertFalse(s_res2.detail.has_changes)

        # 3. Transactional `consume_diff`: exception inside `with` block preserves cursor at 0
        with self.assertRaises(RuntimeError):
            with consume_diff("code", consumer_id="indexer", scanner=scanner) as d_fail:
                self.assertEqual(d_fail.added_count, 3)
                raise RuntimeError("Simulated indexing failure")

        d_retry = diff("code", consumer_id="indexer", auto_refresh=False, scanner=scanner)
        self.assertEqual(d_retry.from_generation, 0)
        self.assertEqual(d_retry.added_count, 3)

        # Normal exit advances cursor to generation 1
        with consume_diff("code", consumer_id="indexer", auto_refresh=False, scanner=scanner) as d_ok:
            self.assertEqual(d_ok.to_generation, 1)

        d_after_ack = diff("code", consumer_id="indexer", auto_refresh=False, scanner=scanner)
        self.assertEqual(d_after_ack.from_generation, 1)
        self.assertFalse(d_after_ack.detail.has_changes)

        # 4. `patch_files`: modify `f1`, delete external `f_ext`, and add `f3` without full tree walk
        f1.write_text("v = 100\n", encoding="utf-8")
        f_ext.unlink()
        f3 = work_dir / "c.py"
        f3.write_text("v = 3\n", encoding="utf-8")

        patched_state = patch_files("code", [f1, f_ext, f3], scanner=scanner)
        self.assertEqual(patched_state.head_generation, 2)
        active_snaps = snapshot("code", scanner=scanner)
        self.assertEqual(sorted(active_snaps.keys()), ["pkg/a.py", "pkg/b.py", "pkg/c.py"])

        # Consumer `indexer` sees exact delta from gen 1 -> gen 2
        d_gen2 = diff("code", consumer_id="indexer", auto_refresh=False, scanner=scanner)
        self.assertEqual(d_gen2.from_generation, 1)
        self.assertEqual(d_gen2.to_generation, 2)
        self.assertEqual(d_gen2.detail.added, {"pkg/c.py"})
        self.assertEqual(d_gen2.detail.modified, {"pkg/a.py"})
        self.assertEqual(d_gen2.detail.deleted, {"ext_data/ext.py"})

        # 5. YFP2 binary corruption recovery (checksum mismatch -> safe fallback to gen 0 and self-heal)
        snap_file = scanner._snapshot_path("code")
        self.assertTrue(snap_file.is_file())
        raw_bytes = snap_file.read_bytes()
        snap_file.write_bytes(raw_bytes[:-1] + bytes([raw_bytes[-1] ^ 0xFF]))

        corrupted_load = BinarySnapshotManager().load_state(snap_file)
        self.assertEqual(corrupted_load.head_generation, 0)

        healed_res = scanner.scan("code")
        self.assertEqual(healed_res.to_generation, 1)
        self.assertEqual(healed_res.added_count, 3)

        # 6. `status`, `ack`, `reset_cursor`, and `clean`
        ack("code", consumer_id="indexer", scanner=scanner)
        st_info = status("code", scanner=scanner)
        self.assertEqual(st_info["status"], "ok")
        reset_cursor("code", consumer_id="indexer", scanner=scanner)
        clean_res = clean("code", scanner=scanner)
        self.assertEqual(clean_res["status"], "ok")
        self.assertFalse(snap_file.exists())
        self.mark_passed()

    def test_composite_cli_status_scan_diff_clean(self) -> None:
        """Verify CLI subcommands `status`, `scan`, `diff --consumer --ack`, and `clean` on both `file-space` and `fs`."""
        cli_dir = self.proj_root / "composite_cli"
        cli_dir.mkdir(parents=True, exist_ok=True)
        f_a = cli_dir / "item.py"
        f_a.write_text("x = 1\n", encoding="utf-8")

        self._write_project_core_contrib(
            {
                "spaces": {
                    "comp_space": {
                        "description": "Composite CLI test space",
                        "entries": ["project://composite_cli"],
                        "include": ["*.py"],
                    }
                }
            }
        )

        cli_mod = load_core_cli_module()

        with uri.host_scope(str(self.proj_root), str(self.yscb_root)):
            # 1. `fs scan comp_space --json`
            buf_scan = io.StringIO()
            with redirect_stdout(buf_scan):
                rc_s = cli_mod.fs_scan(
                    CmdBags(
                        raw_cmd="fs scan comp_space --json",
                        command="fs_scan",
                        args=["comp_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_s, 0)
            scan_data = json.loads(buf_scan.getvalue())
            self.assertEqual(scan_data["status"], "ok")
            self.assertEqual(scan_data["to_generation"], 1)
            self.assertEqual(scan_data["added_count"], 1)

            # 2. `fs diff comp_space --consumer=c1 --ack --json`
            buf_diff = io.StringIO()
            with redirect_stdout(buf_diff):
                rc_d = cli_mod.file_space_diff(
                    CmdBags(
                        raw_cmd="file-space diff comp_space --consumer=c1 --ack --json",
                        command="file_space_diff",
                        args=["comp_space"],
                        options={
                            "consumer": CmdOption(name="consumer", params={"id": "c1"}),
                            "ack": CmdOption(name="ack", params=True),
                            "json": CmdOption(name="json", params=True),
                        },
                    )
                )
            self.assertEqual(rc_d, 0)
            diff_data = json.loads(buf_diff.getvalue())
            self.assertTrue(diff_data["acked"])
            self.assertEqual(diff_data["acked_generation"], 1)
            self.assertEqual(diff_data["added_count"], 1)

            # Subsequent diff for c1 has 0 changes
            buf_diff2 = io.StringIO()
            with redirect_stdout(buf_diff2):
                rc_d2 = cli_mod.fs(
                    CmdBags(
                        raw_cmd="fs diff comp_space --consumer=c1 --json",
                        command="fs",
                        args=["diff", "comp_space"],
                        options={
                            "consumer": CmdOption(name="consumer", params={"id": "c1"}),
                            "json": CmdOption(name="json", params=True),
                        },
                    )
                )
            self.assertEqual(rc_d2, 0)
            diff_data2 = json.loads(buf_diff2.getvalue())
            self.assertFalse(diff_data2["has_changes"])

            # 3. `fs status comp_space --json`
            buf_stat = io.StringIO()
            with redirect_stdout(buf_stat):
                rc_st = cli_mod.fs_status(
                    CmdBags(
                        raw_cmd="fs status comp_space --json",
                        command="fs_status",
                        args=["comp_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_st, 0)
            stat_data = json.loads(buf_stat.getvalue())
            self.assertEqual(stat_data["status"], "ok")
            self.assertEqual(stat_data["space_count"], 1)

            # 4. `fs clean comp_space --json`
            buf_clean = io.StringIO()
            with redirect_stdout(buf_clean):
                rc_cl = cli_mod.file_space_clean(
                    CmdBags(
                        raw_cmd="file-space clean comp_space --json",
                        command="file_space_clean",
                        args=["comp_space"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_cl, 0)
            clean_data = json.loads(buf_clean.getvalue())
            self.assertEqual(clean_data["status"], "ok")
            self.assertTrue(len(clean_data["removed_snapshots"]) >= 1)

            # 5. Verify OptionResolver orthogonal groups: `--space` and `--consumer` can be used together
            from core.commands.registry import CommandsRegistry
            from core.commands.resolver import OptionResolver

            core_contrib_path = Path(__file__).resolve().parents[1] / "contributes" / "core.json"
            core_contrib_data = json.loads(core_contrib_path.read_text(encoding="utf-8"))
            cmd_reg = CommandsRegistry()
            cmd_reg.register_module("core", core_contrib_data.get("commands", {}))

            for cmd_path in ("file-space diff", "fs diff", "file-space clean", "fs clean"):
                spec = cmd_reg.get_command("core", cmd_path)
                self.assertIsNotNone(spec)
                pos_args, opts = OptionResolver.resolve(
                    spec, ["--space", "comp_space", "--consumer", "c1", "--json"]
                )
                self.assertEqual(pos_args, [])
                self.assertEqual(opts["space"].params, "comp_space")
                self.assertEqual(opts["consumer"].params, "c1")
                self.assertTrue(opts["json"].params)
        self.mark_passed()

    def test_watch_default_ephemeral_shared_registry_and_watcher_coordination(self) -> None:
        """
        Verify `[P00:DR-02]` & `[P00:DR-03]`:
        - Static spaces and `define_ephemeral_space` default to `watch=True` (with `watch=False` override).
        - Process-level shared `get_default_registry` / `get_default_scanner` persist ephemeral spaces across top-level calls.
        - `subscribe` dual-track filtering (`source` vs `core/source`), `broadcast_file_space_changed` (`emit_module='core'`),
          `watcher_state.json` / `.watcher_dirty` beacons, and `sync_dependent_snapshots` propagation.
        """
        skills_dir = self.proj_root / ".agents" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text("# Skill v1\n", encoding="utf-8")

        src_dir = self.proj_root / "src_mod"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / "main.py"
        src_file.write_text("x = 1\n", encoding="utf-8")

        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "workspace": {
                        "entries": ["project://"],
                        "include": ["*"],
                        "exclude": ["yscb://.modules/**", "yscb://.storage.local/**", "yscb://.cache/**", "__pycache__"],
                        "watch": True,
                    },
                    "gitignore": {
                        "entries": ["project://"],
                        "include": ["yscb://.modules/", "yscb://.venv/"],
                        "watch": False,
                    },
                    "source": {
                        "entries": ["project://src_mod"],
                        "include": ["*.py"],
                    },
                    "unwatched": {
                        "entries": ["project://src_mod"],
                        "include": ["*.py"],
                        "watch": False,
                    },
                }
            },
        )
        # Create a module hook in .modules/mock_hook/scripts/hook.core.py for Stage 3 on_register_file_spaces
        hook_dir = self.yscb_root / ".modules" / "mock_hook" / "scripts"
        hook_dir.mkdir(parents=True, exist_ok=True)
        (hook_dir / "hook.core.py").write_text(
            "def on_register_file_spaces(ctx):\n"
            "    reg = ctx.get('registry') if isinstance(ctx, dict) else getattr(ctx, 'registry', None)\n"
            "    if reg is not None:\n"
            "        reg.register_space('mock_hook/dynamic_hook', {'entries': ['project://src_mod'], 'include': ['*.py'], 'watch': False})\n",
            encoding="utf-8",
        )
        self._write_project_core_contrib(
            {
                "spaces": {
                    "bundle": {
                        "compose": ["core/source"],
                    }
                }
            }
        )

        # 1. Verify static space `watch=True` default, `gitignore` (`watch=False`), and Stage 3 `on_register_file_spaces`
        reg = get_default_registry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        src_cfg = reg.resolve_spaces("core/source")[0]
        unw_cfg = reg.resolve_spaces("core/unwatched")[0]
        gi_cfg = reg.resolve_spaces("core/gitignore")[0]
        hook_cfg = reg.resolve_spaces("mock_hook/dynamic_hook")[0]
        self.assertTrue(src_cfg.watch)
        self.assertFalse(unw_cfg.watch)
        self.assertFalse(gi_cfg.watch)
        self.assertEqual(hook_cfg.owner, "mock_hook")

        # Verify default `resolve_spaces(None)` resolves to `/workspace` ceiling
        default_spaces = reg.resolve_spaces(None)
        self.assertTrue(any(s.short_name == "workspace" for s in default_spaces))

        # 2. Verify top-level `define_ephemeral_space("yscb-skills", ...)` forwards to `register_space`,
        #    defaults to `watch=True`, notifies active watcher, and is visible to top-level `scan` / `consume_diff`
        synced_calls: list = []

        class _DummyWatcher:
            def is_alive(self) -> bool:
                return True

            def sync_watched_directories(self) -> None:
                synced_calls.append("synced")

            def flush_space_now(self, space_query=None):
                synced_calls.append(("flushed", space_query))
                return None

        register_active_watcher(_DummyWatcher())
        ephem_cfg = define_ephemeral_space(
            "yscb-skills",
            {"entries": ["project://.agents/skills"], "include": ["*.md"]},
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
        )
        self.assertTrue(ephem_cfg.watch)
        self.assertEqual(ephem_cfg.qualified_name, "__unknown__/yscb-skills")
        self.assertIn("synced", synced_calls)

        # Override `watch=False` on runtime-registered space does not trigger sync
        synced_calls.clear()
        ephem_nowatch = define_ephemeral_space(
            "yscb-temp",
            {"entries": ["project://.agents/skills"]},
            watch=False,
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
        )
        self.assertFalse(ephem_nowatch.watch)
        self.assertEqual(synced_calls, [])

        # Top-level `consume_diff` on `yscb-skills` shares default registry & scanner
        with consume_diff(
            "yscb-skills",
            consumer_id="wf_agent",
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
        ) as d_ephem:
            self.assertTrue(d_ephem.has_changes)
            self.assertEqual(d_ephem.added, [".agents/skills/SKILL.md"])
            self.assertIn(("flushed", "yscb-skills"), synced_calls)

        # Reloading default registry preserves active runtime-injected spaces
        reg.reload()
        self.assertEqual(
            reg.resolve_spaces("__unknown__/yscb-skills")[0].qualified_name,
            "__unknown__/yscb-skills",
        )
        register_active_watcher(None)

        # 3. Verify `subscribe` dual-track filtering and `broadcast_file_space_changed` (`emit_module="core"`)
        received_events: list = []
        unsub_short = subscribe(
            lambda sp, df: received_events.append(("short", sp, df.to_generation)),
            spaces=["source"],
        )
        unsub_qual = subscribe(
            lambda sp, df: received_events.append(("qual", sp, df.to_generation)),
            spaces=["core/source"],
        )
        unsub_other = subscribe(
            lambda sp, df: received_events.append(("other", sp, df.to_generation)),
            spaces=["other/space"],
        )

        sc = get_default_scanner(project_root=self.proj_root, yscb_dir=self.yscb_root)
        d_src = sc.scan("core/source")
        notify_subscribers("core/source", d_src)
        self.assertEqual(
            received_events,
            [("short", "core/source", 1), ("qual", "core/source", 1)],
        )
        unsub_short()
        unsub_qual()
        unsub_other()

        with patch("core.events.broadcast") as mock_bcast:
            payload = broadcast_file_space_changed("core/source", d_src)
            self.assertEqual(payload["space_name"], "core/source")
            self.assertEqual(payload["short_name"], "source")
            self.assertEqual(payload["spaces"], ["core/source", "source"])
            self.assertEqual(payload["added"], ["src_mod/main.py"])
            mock_bcast.assert_called_once_with(
                "on_file_space_changed", payload, emit_module="core"
            )

        # 4. Verify `sync_dependent_snapshots` updates existing short-name union (`source`),
        #    composite parent (`project/bundle`), and unified (`__all__`) snapshots
        sc.scan("source")
        sc.scan("project/bundle")
        sc.scan(None)  # initializes __all__

        src_file.write_text("x = 2\n", encoding="utf-8")
        patched = sc.patch_files("core/source", [src_file])
        self.assertEqual(patched.head_generation, 2)
        self.assertIsNotNone(patched.last_diff)
        self.assertEqual(patched.last_diff.modified, ["src_mod/main.py"])

        synced_deps = sc.sync_dependent_snapshots("core/source", [src_file])
        self.assertIn("source", synced_deps)
        self.assertIn("project/bundle", synced_deps)
        self.assertIn("__all__", synced_deps)
        self.assertEqual(synced_deps["source"].to_generation, 2)
        self.assertEqual(synced_deps["project/bundle"].to_generation, 2)

        # 5. Verify `watcher_state.json` and `.watcher_dirty` beacons in `cache://core/space`
        state_p = write_watcher_state(
            watched_spaces=["core/source"],
            watchdog_running=True,
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
        )
        self.assertEqual(
            state_p,
            resolve_watcher_state_path(self.proj_root, self.yscb_root),
        )
        self.assertTrue(
            is_watcher_active("core/source", registry=reg, state_file=state_p)
        )
        self.assertTrue(
            is_watcher_active("source", registry=reg, state_file=state_p)
        )
        self.assertFalse(
            is_watcher_active("core/unwatched", registry=reg, state_file=state_p)
        )

        # Dead PID in watcher_state.json returns False
        vfs.write_json(
            str(state_p),
            {
                "pid": 99999999,
                "watchdog_running": True,
                "watched_spaces": ["core/source"],
                "updated_at": 1.0,
            },
        )
        self.assertFalse(
            is_watcher_active("core/source", registry=reg, state_file=state_p)
        )
        remove_watcher_state(state_file=state_p)
        self.assertIsNone(read_watcher_state(state_file=state_p))

        # `.watcher_dirty` marker triggers auto-scan even when `auto_refresh=False`
        src_file.write_text("x = 3\n", encoding="utf-8")
        sc.mark_watcher_dirty(True)
        self.assertTrue(sc.has_watcher_dirty_marker())
        self.assertTrue(
            resolve_watcher_dirty_path(self.proj_root, self.yscb_root).is_file()
        )
        d_dirty = sc.diff("core/source", consumer_id="c_dirty", auto_refresh=False)
        self.assertEqual(d_dirty.to_generation, 3)
        sc.mark_watcher_dirty(False)
        self.assertFalse(sc.has_watcher_dirty_marker())

        # 6. Verify `ScanDiffDetail.dirty_files` excludes `deleted`, `providers` tables, and `1.2.7.x.py` config migration
        from core.space.providers import (
            get_knowledge_db_spaces,
            get_registered_file_spaces_table,
        )
        from core.space.scanner import ScanDiffDetail
        import importlib.util

        detail_check = ScanDiffDetail(
            added={"a.py"}, modified={"b.py"}, deleted={"c.py"}
        )
        self.assertEqual(detail_check.dirty_files, {"a.py", "b.py"})
        self.assertNotIn("c.py", detail_check.dirty_files)

        tbl_reg = get_registered_file_spaces_table(
            context={"project_root": str(self.proj_root), "yscb_dir": str(self.yscb_root)}
        )
        self.assertIn("`core/source`", tbl_reg)
        tbl_kdb = get_knowledge_db_spaces(
            context={"project_root": str(self.proj_root), "yscb_dir": str(self.yscb_root)}
        )
        self.assertIn("`core/source`", tbl_kdb)

        # Positive + negative space_weights filtering under explicit context (verifies host_scope signature & isolation)
        kdb_cfg_file = self.yscb_root / "config" / "knowledge-db" / "contribute.json"
        kdb_cfg_file.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(str(kdb_cfg_file), {"space_weights": {"core/source": 1.0}})
        try:
            tbl_filtered = get_knowledge_db_spaces(
                context={"project_root": str(self.proj_root), "yscb_dir": str(self.yscb_root)}
            )
            self.assertIn("`core/source`", tbl_filtered)
            self.assertNotIn("`core/unwatched`", tbl_filtered)
        finally:
            vfs.remove(str(kdb_cfg_file), missing_ok=True)

        # Test `1.2.7.x.py` migration of `config/file-space/contribute.json` -> `config/core/contribute.json`
        legacy_fs_cfg = self.yscb_root / "config" / "file-space" / "contribute.json"
        legacy_fs_cfg.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(
            str(legacy_fs_cfg),
            {
                "spaces": {
                    "migrated_src": {
                        "description": "Migrated legacy space",
                        "include": ["project://src"],
                        "file_patterns": ["*.py"],
                        "exclude": ["__pycache__"],
                        "watch": True,
                    }
                }
            },
        )
        mig_script_path = Path(
            uri.resolve("module.source://core/scripts/migrations/1.2.7.x.py")
        )
        spec = importlib.util.spec_from_file_location("_test_core_mig_127", mig_script_path)
        self.assertIsNotNone(spec)
        mig_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mig_mod)  # type: ignore[union-attr]
        self.assertTrue(mig_mod.migrate({"yscb_dir": str(self.yscb_root)}))
        self.assertFalse(legacy_fs_cfg.exists())
        migrated_core_cfg = vfs.read_json(
            str(self.yscb_root / "config" / "core" / "contribute.json")
        )
        self.assertEqual(
            migrated_core_cfg["spaces"]["migrated_src"]["entries"], ["project://src"]
        )
        self.assertEqual(
            migrated_core_cfg["spaces"]["migrated_src"]["include"], ["*.py"]
        )
        self.mark_passed()


    def test_pre_1970_negative_mtime_clamping_batch_walk_session_and_128_migration(self) -> None:
        """
        Verify:
        1. Files with negative pre-1970 `st_mtime_ns` are clamped to `0` in `SpaceRegistry` and `SpaceScanner.patch_files`
           so subsequent scans hit Stage 1 without infinite Stage 2 re-hashing.
        2. `SpaceRegistry.batch_walk_session()` deduplicates walks across composed/synthetic spaces.
        3. `1.2.8.x.py` migration removes legacy `file-space` residual entries from `yscb.config.json` and runtime directories.
        """
        import importlib.util

        src_dir = self.proj_root / "epoch_src"
        src_dir.mkdir(parents=True, exist_ok=True)
        old_file = src_dir / "ancient.py"
        old_file.write_text("x = 1969\n", encoding="utf-8")
        try:
            os.utime(old_file, ns=(-86_400_000_000_000, -86_400_000_000_000))
        except OSError:
            pass

        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "epoch_code": {
                        "entries": ["project://epoch_src"],
                        "include": ["*.py"],
                        "watch": True,
                    },
                    "epoch_bundle": {
                        "compose": ["core/epoch_code"],
                        "watch": True,
                    },
                }
            },
        )
        reg = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        sc = SpaceScanner(registry=reg)

        with reg.batch_walk_session():
            entries_1 = reg.iter_space_files("core/epoch_code")
            entries_2 = reg.iter_space_files("core/epoch_bundle")
            self.assertEqual(len(entries_1), 1)
            self.assertEqual(entries_1[0].mtime_ns, max(0, entries_1[0].mtime_ns))
            self.assertGreaterEqual(entries_1[0].mtime_ns, 0)
            self.assertEqual(len(entries_2), 1)

        r1 = sc.scan("core/epoch_code")
        self.assertEqual(r1.added_count, 1)
        r2 = sc.scan("core/epoch_code")
        self.assertEqual(r2.added_count, 0)
        self.assertEqual(r2.modified_count, 0)
        self.assertEqual(r2.unchanged_count, 1)

        patched = sc.patch_files("core/epoch_code", [old_file])
        self.assertGreaterEqual(patched.entries["epoch_src/ancient.py"].mtime_ns, 0)

        # Verify 1.2.8.x.py migration cleans up residual file-space entries and directories
        cfg_file = self.proj_root / "yscb.config.json"
        cfg_data = vfs.read_json(str(cfg_file))
        cfg_data.setdefault("installed_modules", {})["file-space"] = {"version": "1.0.0.0"}
        vfs.write_json(str(cfg_file), cfg_data)

        for rel_d in (".modules/file-space", ".mirror/file-space", ".cache/file-space", ".storage.local/file-space", ".config.local/file-space"):
            d_p = self.yscb_root / rel_d
            d_p.mkdir(parents=True, exist_ok=True)
            (d_p / "dummy.txt").write_text("residual", encoding="utf-8")

        mig_128_path = Path(uri.resolve("module.source://core/scripts/migrations/1.2.8.x.py"))
        spec = importlib.util.spec_from_file_location("_test_core_mig_128", mig_128_path)
        self.assertIsNotNone(spec)
        mig_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mig_mod)  # type: ignore[union-attr]
        self.assertTrue(mig_mod.migrate({"host_dir": str(self.proj_root), "yscb_dir": str(self.yscb_root)}))

        updated_cfg = vfs.read_json(str(cfg_file))
        self.assertNotIn("file-space", updated_cfg.get("installed_modules", {}))
        for rel_d in (".modules/file-space", ".mirror/file-space", ".cache/file-space", ".storage.local/file-space", ".config.local/file-space"):
            self.assertFalse((self.yscb_root / rel_d).exists())

        self.mark_passed()

    def test_binary_snapshot_load_summary_and_get_snapshot_summary(self) -> None:
        """Verify `BinarySnapshotManager.load_summary` and `SpaceScanner.get_snapshot_summary` match `load_state` active counts and reject corrupted payloads."""
        sum_dir = self.proj_root / "sum_src"
        sum_dir.mkdir(parents=True, exist_ok=True)
        f1 = sum_dir / "one.py"
        f2 = sum_dir / "two.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")

        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "sum_code": {
                        "entries": ["project://sum_src"],
                        "include": ["*.py"],
                        "watch": True,
                    }
                }
            },
        )
        reg = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        sc = SpaceScanner(registry=reg)
        sc.scan("core/sum_code")

        # Delete f2 so snapshot contains 1 active file + 1 tombstone (is_deleted=True)
        f2.unlink()
        sc.scan("core/sum_code")

        snap_path = sc._snapshot_path("core/sum_code")
        full_state = sc._snapshot_mgr.load_state(snap_path)
        expected_active = sum(1 for e in full_state.entries.values() if not e.is_deleted)
        self.assertEqual(expected_active, 1)
        self.assertGreaterEqual(len(full_state.entries), 2)

        # Cold disk summary path (evict in-memory snapshot cache first)
        sc._snapshot_mem_cache.clear()
        h_gen, m_root, c_hash, act_cnt = sc.get_snapshot_summary("core/sum_code")
        self.assertEqual(h_gen, full_state.head_generation)
        self.assertEqual(m_root, full_state.merkle_root)
        self.assertEqual(c_hash, full_state.config_hash)
        self.assertEqual(act_cnt, 1)

        # Warm memory cache path
        sc._load_snapshot_state("core/sum_code")
        self.assertEqual(
            sc.get_snapshot_summary("core/sum_code"),
            (full_state.head_generation, full_state.merkle_root, full_state.config_hash, 1),
        )

        # Corrupted checksum falls back cleanly to (0, "", "", 0)
        corrupt_snap = self.proj_root / "corrupt.snap"
        raw = bytearray(snap_path.read_bytes())
        raw[-1] ^= 0xFF
        corrupt_snap.write_bytes(bytes(raw))
        self.assertEqual(sc._snapshot_mgr.load_summary(corrupt_snap), (0, "", "", 0))
        self.mark_passed()


    def test_scanner_diff_config_hash_change_emits_excluded_files_as_deleted(self) -> None:
        """Verify `SpaceScanner.diff()` emits newly excluded files in `deleted` when `config_hash` changes after `from_gen > 0`."""
        cfg_dir = self.proj_root / "cfg_src"
        vendor_dir = cfg_dir / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        keep_f = cfg_dir / "keep.py"
        drop_f = vendor_dir / "drop.py"
        keep_f.write_text("KEEP = 1\n", encoding="utf-8")
        drop_f.write_text("DROP = 2\n", encoding="utf-8")

        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "cfg_space": {
                        "entries": ["project://cfg_src"],
                        "include": ["*.py"],
                        "exclude": [],
                    }
                }
            },
        )
        reg1 = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        sc1 = SpaceScanner(registry=reg1)
        sc1.scan("core/cfg_space")
        sc1.ack("core/cfg_space", consumer_id="ast")

        # Update space exclude rules so vendor/drop.py becomes excluded (config_hash changes)
        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "cfg_space": {
                        "entries": ["project://cfg_src"],
                        "include": ["*.py"],
                        "exclude": ["vendor"],
                    }
                }
            },
        )
        reg2 = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        sc2 = SpaceScanner(registry=reg2)
        diff_res = sc2.diff("core/cfg_space", consumer_id="ast", auto_refresh=True)
        self.assertTrue(diff_res.has_changes)
        self.assertTrue(any(p.endswith("vendor/drop.py") for p in diff_res.deleted), diff_res.deleted)
        self.assertFalse(any(p.endswith("keep.py") for p in diff_res.deleted), diff_res.deleted)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cursor_store_isolated_consumer_locks_and_tombstone_prune_concurrency(self) -> None:
        """Verify distinct consumer batch locks and tombstone pruning execute concurrently without AB-BA deadlock."""
        import threading

        conc_dir = self.proj_root / "conc_src"
        conc_dir.mkdir(parents=True, exist_ok=True)
        keep_f = conc_dir / "keep.py"
        del_f = conc_dir / "gone.py"
        keep_f.write_text("VAL = 0\n", encoding="utf-8")
        del_f.write_text("GONE = 1\n", encoding="utf-8")

        self._write_module_core_contrib(
            "core",
            {
                "spaces": {
                    "conc_sp": {
                        "entries": ["project://conc_src"],
                        "include": ["*.py"],
                        "exclude": [],
                    }
                }
            },
        )
        reg = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_root)
        sc = SpaceScanner(registry=reg)
        sc.scan("core/conc_sp")
        del_f.unlink()
        sc.scan("core/conc_sp")

        for i in range(66):
            keep_f.write_text(f"VAL = {i + 1}\n", encoding="utf-8")
            sc.patch_files("core/conc_sp", [keep_f])

        kdb_entered = threading.Event()
        ast_done_while_kdb_held = threading.Event()
        errors: list = []

        def _kdb_holder() -> None:
            try:
                with sc.cursor_store.batch_cursor_updates("knowledge-db"):
                    kdb_entered.set()
                    self.assertTrue(ast_done_while_kdb_held.wait(timeout=3.0))
                    sc.cursor_store.set_cursor("core/conc_sp", "knowledge-db", 10)
            except Exception as exc:
                errors.append(exc)

        def _ast_worker() -> None:
            try:
                self.assertTrue(kdb_entered.wait(timeout=3.0))
                with sc.cursor_store.batch_cursor_updates("ast"):
                    sc.cursor_store.set_cursor("core/conc_sp", "ast", 10)
                ast_done_while_kdb_held.set()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_kdb_holder, daemon=True)
        t2 = threading.Thread(target=_ast_worker, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=4.0)
        t2.join(timeout=4.0)
        self.assertEqual(errors, [])
        self.assertTrue(ast_done_while_kdb_held.is_set())

        def _scanner_worker() -> None:
            try:
                for step in range(15):
                    keep_f.write_text(f"VAL = {100 + step}\n", encoding="utf-8")
                    sc.patch_files("core/conc_sp", [keep_f])
            except Exception as exc:
                errors.append(exc)

        def _cursor_spammer(cid: str) -> None:
            try:
                for step in range(25):
                    with sc.cursor_store.batch_cursor_updates(cid):
                        sc.cursor_store.set_cursor("core/conc_sp", cid, 20 + step)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_scanner_worker, daemon=True),
            threading.Thread(target=_cursor_spammer, args=("knowledge-db",), daemon=True),
            threading.Thread(target=_cursor_spammer, args=("ast",), daemon=True),
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5.0)
            self.assertFalse(th.is_alive())
        self.assertEqual(errors, [])
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
