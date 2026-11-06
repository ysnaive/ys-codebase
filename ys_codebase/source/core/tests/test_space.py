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
    HashPolicy,
    PresetConfig,
    SpaceConfig,
    SpaceError,
    SpaceNotFoundError,
    SpaceRegistry,
    compute_file_hash,
    hash_space_or_path,
    hash_target,
    iter_space_files,
    match_path,
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
        """Verify `_format.json` schema validation for `presets`/`spaces` and default `include=['*']` with `exclude > include`."""
        self.assertIn("space", core.__all__)
        self.assertIs(core.space.SpaceRegistry, SpaceRegistry)

        fmt_path = Path(uri.resolve("module.source://core/contributes/_format.json"))
        fmt_schema = vfs.read_json(str(fmt_path))
        meta_res = ContributesValidator.validate_format_schema(fmt_schema)
        self.assertTrue(meta_res.is_valid, meta_res.format_report())

        valid_payload = {
            "presets": {
                "py-only": {
                    "description": "Python files only",
                    "include": ["*.py"],
                    "exclude": ["*_pb2.py"],
                }
            },
            "spaces": {
                "code": {
                    "description": "Code space",
                    "entries": ["project://src"],
                    "presets": ["py-only", "@gitignore"],
                    "hash_policy": "adaptive",
                    "large_file_threshold_mb": 15,
                    "follow_symlinks": False,
                }
            },
        }
        val_res = ContributesValidator.validate(
            "core", valid_payload, donor_mod="test_mod", format_schema=fmt_schema
        )
        self.assertTrue(val_res.is_valid, val_res.format_report())

        # Negative validation: invalid hash_policy and missing required entries
        bad_payload = {
            "spaces": {
                "broken": {
                    "hash_policy": "invalid_policy",
                }
            }
        }
        bad_res = ContributesValidator.validate(
            "core", bad_payload, donor_mod="test_mod", format_schema=fmt_schema
        )
        self.assertFalse(bad_res.is_valid)

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

        # Default include=["*"] and exclude priority over include
        src_dir = self.proj_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "keep.py").write_text("print(1)\n", encoding="utf-8")
        (src_dir / "secret.py").write_text("print(2)\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/app": {
                    "entries": ["src"],
                    "include": ["*.py"],
                    "exclude": ["secret.py"],
                },
                "project/all_files": {
                    "entries": ["src"],
                },
            },
        )
        all_cfg = reg.resolve_spaces("project/all_files")[0]
        self.assertEqual([r.raw_pattern for r in all_cfg.effective_include], ["*"])

        matched_files = [f.rel_path for f in reg.iter_space_files("project/app")]
        self.assertEqual(matched_files, ["src/keep.py"])
        self.mark_passed()

    def test_namespace_isolation_and_short_name_union_addressing(self) -> None:
        """Verify `<owner>/<name>` isolation and `<name>` short-name union without cross-contamination."""
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
                "presets": {
                    "ignore_rules": {"exclude": ["*.tmp"]},
                },
                "spaces": {
                    "docs": {
                        "description": "Module A docs",
                        "entries": ["project://docs_a"],
                        "presets": ["mod_a/ignore_rules"],
                        "include": ["*.md", "*.tmp"],
                    }
                },
            },
        )
        self._write_project_core_contrib(
            {
                "presets": {
                    "ignore_rules": {"exclude": ["*.bak"]},
                },
                "spaces": {
                    "docs": {
                        "description": "Project docs",
                        "entries": ["project://docs_proj", "project://docs_a/guide.md"],
                        "include": ["*.md"],
                    }
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

        # 2. Short-name lookup returns deterministic union (module before project)
        union_spaces = reg.resolve_spaces("docs")
        self.assertEqual([s.qualified_name for s in union_spaces], ["mod_a/docs", "project/docs"])

        # 3. Union traversal deduplicates overlapping physical file `docs_a/guide.md` and records both matched_spaces
        union_files = reg.iter_space_files("docs")
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

    def test_explicit_presets_and_builtin_gitignore_evaluation(self) -> None:
        """Verify explicit preset expansion, unresolved preset warning, and `@gitignore` with `!` exemptions."""
        (self.proj_root / ".gitignore").write_text(
            "# Root comment\n"
            "\n"
            "*.log\n"
            "!important.log\n"
            "ignored_dir/\n",
            encoding="utf-8",
        )
        logs_dir = self.proj_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "debug.log").write_text("debug\n", encoding="utf-8")
        (logs_dir / "important.log").write_text("important\n", encoding="utf-8")
        (logs_dir / "override.log").write_text("override\n", encoding="utf-8")

        ignored_sub = logs_dir / "ignored_dir"
        ignored_sub.mkdir(parents=True, exist_ok=True)
        (ignored_sub / "inside.txt").write_text("inside\n", encoding="utf-8")

        reg = SpaceRegistry(
            project_root=self.proj_root,
            yscb_dir=self.yscb_root,
            raw_spaces={
                "project/no_gitignore": {
                    "entries": ["logs"],
                    "presets": ["missing_preset_name"],
                },
                "project/with_gitignore": {
                    "entries": ["logs"],
                    "presets": ["@gitignore"],
                    "exclude": ["override.log"],
                },
            },
        )

        # Space without @gitignore is completely unaffected by .gitignore; unresolved preset is recorded without crash
        no_gi_cfg = reg.resolve_spaces("project/no_gitignore")[0]
        self.assertEqual(no_gi_cfg.unresolved_presets, ("missing_preset_name",))
        no_gi_files = [f.rel_path for f in reg.iter_space_files("project/no_gitignore")]
        self.assertIn("logs/debug.log", no_gi_files)
        self.assertIn("logs/ignored_dir/inside.txt", no_gi_files)

        # Space with @gitignore excludes debug.log & ignored_dir/, exempts !important.log,
        # while space-level explicit exclude ("override.log") still wins
        with_gi_files = [f.rel_path for f in reg.iter_space_files("project/with_gitignore")]
        self.assertEqual(with_gi_files, ["logs/important.log"])

        # Inspect builtin @gitignore preset via resolve_presets("@gitignore")
        gi_presets = reg.resolve_presets("@gitignore")
        self.assertEqual(len(gi_presets), 1)
        self.assertEqual(gi_presets[0].qualified_name, "@gitignore")
        self.assertIn("*.log", gi_presets[0].exclude)
        self.assertIn("!important.log", gi_presets[0].exclude)
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
            raw_presets={
                "core/std_ignore": {
                    "exclude": [
                        "yscb://.cache/**",       # Coordinate 1: Semantic URI prefix
                        "plans/archived/**",      # Coordinate 2: Relative to project://
                        "subpkg/ignored_*.py",    # Coordinate 2: Relative to entry (module.source://core)
                        "__pycache__",            # Coordinate 3: Segment name without '/'
                    ]
                }
            },
            raw_spaces={
                "core/workspace": {
                    "entries": [
                        "project://plans",
                        "yscb://source/core",
                        "yscb://.cache",
                    ],
                    "presets": ["core/std_ignore"],
                    "include": ["*.py", "*.md"],
                }
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
                "presets": {
                    "cli_preset": {
                        "description": "CLI test preset",
                        "exclude": ["*.tmp"],
                    }
                },
                "spaces": {
                    "cli_space": {
                        "description": "CLI test space",
                        "entries": ["project://cli_src"],
                        "presets": ["project/cli_preset"],
                        "include": ["*.py"],
                    }
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
            self.assertEqual(spaces_json["spaces"][0]["qualified_name"], "project/cli_space")

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

            # 2. `fs presets --json`
            buf_presets = io.StringIO()
            with redirect_stdout(buf_presets):
                rc_p = cli_mod.fs_presets(
                    CmdBags(
                        raw_cmd="fs presets cli_preset --json",
                        command="fs_presets",
                        args=["cli_preset"],
                        options={"json": CmdOption(name="json", params=True)},
                    )
                )
            self.assertEqual(rc_p, 0)
            presets_json = json.loads(buf_presets.getvalue())
            self.assertEqual(presets_json["presets"][0]["qualified_name"], "project/cli_preset")

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

        # 7. Verify dispatcher top-level collision avoidance when external `file-space` module is installed
        dispatcher.clear_cache()
        try:
            core_src_contrib = Path(uri.resolve("module.source://core/contributes/core.json"))
            self._write_module_core_contrib("core", vfs.read_json(str(core_src_contrib)))
            self._write_module_core_contrib(
                "file-space",
                {
                    "commands": {
                        "description": "Legacy external file-space module",
                        "cmd": {
                            "status": {
                                "description": "Legacy status",
                                "tier": "safe",
                                "server_compatible": False,
                            }
                        },
                    }
                },
            )
            with uri.host_scope(str(self.proj_root), str(self.yscb_root)):
                with (
                    patch("core.commands.dispatcher._try_hot_dispatch", return_value=None),
                    patch("core.commands.dispatcher.dispatch_local", return_value=0) as mock_dl,
                ):
                    # Top-level `file-space status` without `core` prefix yields to installed external `file-space` module
                    rc1 = dispatcher.dispatch(["file-space", "status"])
                    self.assertEqual(rc1, 0)
                    self.assertEqual(mock_dl.call_args[1]["module_name"], "file-space")

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


if __name__ == "__main__":
    unittest.main()
