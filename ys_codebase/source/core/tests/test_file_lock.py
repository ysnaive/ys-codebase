"""
Tests for `core.file_lock` Declarative Read-Only File Lock SDK,
`/readonly` SpaceRegistry aggregation, `core.vfs` transparent write-before-unlock
and write-after-relock tunneling, `writable_scope` re-entrancy, `core file-lock` CLI,
and 5-module cross-module integration (`FT-01` ~ `FT-06`, `EC-01` ~ `EC-05`, `NFR-01` ~ `NFR-03`).
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from unittest.mock import patch

from core import events, file_lock, uri, vfs
from core.commands import CmdBags, CmdOption
from core.context import bind_runtime_context, get_runtime_context, reset_runtime_context
from core.space.registry import SpaceRegistry, get_default_registry, reset_default_registry
from core.vfs.os_backend import atomic_swap_directory
from dev.testing import Requirement, YSCBTestCase, require


@require(Requirement.LOGIC)
class TestDeclarativeReadonlyFileLock(YSCBTestCase):
    """Comprehensive verification for `2026_11_10_0025_declarative_readonly_file_lock_sdk` (FT-01 ~ FT-06)."""

    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_core_file_lock_")
        self.proj_root = Path(self.temp_dir) / "workspace"
        self.yscb_dir = self.proj_root / ".yscb"
        self.modules_dir = self.yscb_dir / ".modules"
        self.mirror_dir = self.yscb_dir / ".mirror"
        self.snapshots_dir = self.yscb_dir / ".snapshots"
        self.schemas_dir = self.proj_root / ".vscode" / "schemas"
        self.plans_dir = self.proj_root / "plans"
        self.archived_dir = self.plans_dir / "archived"
        self.roadmap_dir = self.plans_dir / "roadmap"
        self.agents_dir = self.proj_root / ".agents"

        for d in (
            self.modules_dir / "core" / "contributes",
            self.modules_dir / "vscode-support" / "contributes",
            self.modules_dir / "agents-workflow" / "contributes",
            self.mirror_dir / "core",
            self.snapshots_dir / "snap_1",
            self.schemas_dir / "meta",
            self.plans_dir / "2026_11_10_0001_demo",
            self.archived_dir / "2026" / "11" / "2026_11_01_0001_old",
            self.roadmap_dir,
            self.agents_dir / ".yscb",
            self.agents_dir / "skills" / "auto",
            self.proj_root / "src",
        ):
            d.mkdir(parents=True, exist_ok=True)

        # Write minimal host yscb.config.json and module contributes/core.json
        (self.proj_root / "yscb.config.json").write_text(
            json.dumps({
                "yscb_root": "./.yscb",
                "installed_modules": {
                    "core": {"version": "1.0.0.0"},
                    "vscode-support": {"version": "1.0.0.0"},
                    "agents-workflow": {"version": "1.0.0.0"},
                },
            }),
            encoding="utf-8",
        )
        real_fmt = Path(__file__).resolve().parents[1] / "contributes" / "_format.json"
        (self.modules_dir / "core" / "contributes" / "_format.json").write_text(
            real_fmt.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (self.yscb_dir / "config" / "core").mkdir(parents=True, exist_ok=True)
        (self.yscb_dir / "config" / "core" / "config.project.json").write_text(
            json.dumps({"project_root": "./"}), encoding="utf-8"
        )
        (self.modules_dir / "core" / "contributes" / "core.json").write_text(
            json.dumps({
                "uri_schemes": [
                    {"token": "project", "type": "const", "value": "{yscb_host}"},
                    {"token": "yscb", "type": "const", "value": "{yscb_root}"},
                    {"token": "module", "type": "const", "value": "yscb://.modules/"},
                    {"token": "module.mirror", "type": "const", "value": "yscb://.mirror/"},
                    {"token": "snapshot", "type": "const", "value": "yscb://.snapshots/"},
                ],
                "spaces": {
                    "workspace": {
                        "description": "Workspace root",
                        "entries": ["project://"],
                        "include": ["*"],
                        "exclude": ["yscb://.modules/**"],
                        "watch": True,
                    },
                    "readonly": {
                        "description": "Core readonly space",
                        "entries": ["module://", "module.mirror://", "snapshot://"],
                        "include": ["*"],
                        "exclude": ["**/__pycache__/**", "__pycache__", "*.pyc", "*.pyo", "*.pyd"],
                        "watch": False,
                    },
                },
            }),
            encoding="utf-8",
        )
        (self.modules_dir / "vscode-support" / "contributes" / "core.json").write_text(
            json.dumps({
                "spaces": {
                    "readonly": {
                        "description": "VS Code schemas readonly space",
                        "entries": ["project://.vscode/schemas"],
                        "include": ["*"],
                        "watch": False,
                    }
                }
            }),
            encoding="utf-8",
        )
        (self.modules_dir / "agents-workflow" / "contributes" / "core.json").write_text(
            json.dumps({
                "uri_schemes": [
                    {"token": "workflow.plans", "type": "const", "value": "project://plans"},
                    {"token": "workflow.archived", "type": "const", "value": "project://plans/archived"},
                    {"token": "workflow.roadmap", "type": "const", "value": "project://plans/roadmap"},
                ],
                "spaces": {
                    "readonly": {
                        "description": "Agent workflow static readonly space",
                        "entries": ["workflow.plans://", "workflow.archived://", "workflow.roadmap://"],
                        "include": [
                            "workflow.plans://**/changelog.md",
                            "workflow.archived://**",
                            "workflow.roadmap://TODO.md",
                        ],
                        "watch": False,
                    }
                },
            }),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        reset_default_registry()
        reset_runtime_context()
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            vfs.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_ft01_space_registry_readonly_union_and_wildcard_isolation(self) -> None:
        """
        FT-01: Verify `SpaceRegistry` synthesizes `/readonly` across `core/readonly`,
        `vscode-support/readonly`, and `agents-workflow/readonly` with `collapse_wildcard=False`,
        `watch=False`, exclusion from `resolve_spaces("")`/`resolve_spaces("*")`, and
        `register_space(..., replace=True)` dynamic replacement without stale rule accumulation.
        """
        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
        ):
            uri.invalidate_uri_cache()
            reg = SpaceRegistry(project_root=self.proj_root, yscb_dir=self.yscb_dir)
            reg.register_space(
                "agents-workflow/readonly",
                {
                    "entries": ["project://.agents", "project://.claude"],
                    "include": [
                        "/.agents/.yscb/",
                        "/.agents/skills/auto/SKILL.md",
                        "/.claude/old_skill.md",
                    ],
                    "watch": False,
                },
                replace=True,
            )
            # Re-register with replace=True removing /.claude/old_skill.md
            reg.register_space(
                "agents-workflow/readonly",
                {
                    "entries": ["project://.agents"],
                    "include": ["/.agents/.yscb/", "/.agents/skills/auto/SKILL.md"],
                    "watch": False,
                },
                replace=True,
            )
            aw_ro = reg.resolve_spaces("agents-workflow/readonly")[0]
            self.assertNotIn("/.claude/old_skill.md", aw_ro.include)
            # Static rules from contributes/core.json must still be preserved after replace=True
            self.assertIn("workflow.roadmap://TODO.md", aw_ro.include)

            self.assertTrue(reg.has_space("/readonly"))
            ro_union = reg.resolve_spaces("/readonly")[0]
            self.assertFalse(ro_union.watch)

            # Default resolve_spaces("") and resolve_spaces("*") must exclude /readonly and */readonly
            default_names = {s.qualified_name for s in reg.resolve_spaces("")}
            wildcard_names = {s.qualified_name for s in reg.resolve_spaces("*")}
            self.assertFalse(
                any(n == "/readonly" or n.endswith("/readonly") for n in default_names | wildcard_names)
            )

            # Protected targets must match /readonly
            mod_file = self.modules_dir / "core" / "sample.py"
            mirror_zip = self.mirror_dir / "core" / "1.0.0.0.zip"
            snap_file = self.snapshots_dir / "snap_1" / "yscb.config.json"
            schema_file = self.schemas_dir / "meta" / "manifest.schema.json"
            changelog_file = self.plans_dir / "2026_11_10_0001_demo" / "changelog.md"
            archived_file = self.archived_dir / "2026" / "11" / "2026_11_01_0001_old" / "P00_discuss.md"
            todo_file = self.roadmap_dir / "TODO.md"
            agent_skill = self.agents_dir / "skills" / "auto" / "SKILL.md"
            agent_yscb = self.agents_dir / ".yscb" / "rule.md"

            for p in (
                mod_file,
                mirror_zip,
                snap_file,
                schema_file,
                changelog_file,
                archived_file,
                todo_file,
                agent_skill,
                agent_yscb,
            ):
                p.write_text("protected", encoding="utf-8")
                m_res = reg.match_path(p, "/readonly", is_dir=False)
                self.assertTrue(m_res.matched, f"Expected {p} to match /readonly")
                self.assertTrue(reg.is_path_matched_fast(p, "/readonly", is_dir=False))

            # Unprotected targets must NOT match /readonly
            user_src = self.proj_root / "src" / "main.py"
            active_plan_p00 = self.plans_dir / "2026_11_10_0001_demo" / "P00_discuss.md"
            roadmap_proposal = self.roadmap_dir / "my_feature.md"
            agents_md = self.proj_root / "AGENTS.md"
            pyc_file = self.modules_dir / "core" / "__pycache__" / "sample.cpython-312.pyc"
            pyc_file.parent.mkdir(parents=True, exist_ok=True)

            for p in (user_src, active_plan_p00, roadmap_proposal, agents_md, pyc_file):
                p.write_text("editable", encoding="utf-8")
                m_res = reg.match_path(p, "/readonly", is_dir=False)
                self.assertFalse(m_res.matched, f"Expected {p} NOT to match /readonly")
                self.assertFalse(reg.is_path_matched_fast(p, "/readonly", is_dir=False))

            # Frozen dataclass check (NFR-01)
            info = file_lock.inspect_path(mod_file, root_dir=self.proj_root)
            with self.assertRaises(FrozenInstanceError):
                info.is_protected = False  # type: ignore[misc]
        self.mark_passed()

    def test_ft02_apply_strip_lock_bits_exec_preserve_symlink_and_nt_branch(self) -> None:
        """
        FT-02: Verify `apply_lock_bits`, `strip_lock_bits`, `is_file_readonly`, `sync`,
        executable bit preservation (`0o555` on POSIX), symlink skip (`EC-04`),
        `already_locked_count` zero-write short-circuit (`NFR-02`), and simulated Windows
        `os.name == "nt"` permission bit branch (`AUD-04`).
        """
        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
        ):
            uri.invalidate_uri_cache()
            reset_default_registry()
            script_file = self.modules_dir / "core" / "run.sh"
            script_file.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
            if os.name != "nt":
                os.chmod(script_file, 0o755)

            pyc_dir = self.modules_dir / "core" / "__pycache__"
            pyc_dir.mkdir(parents=True, exist_ok=True)
            pyc_file = pyc_dir / "run.cpython-312.pyc"
            pyc_file.write_bytes(b"bytecode")

            outside_target = self.proj_root / "src" / "outside.txt"
            outside_target.write_text("outside", encoding="utf-8")
            sym_link = self.modules_dir / "core" / "link_outside.txt"
            try:
                os.symlink(outside_target, sym_link)
                has_symlink = True
            except OSError:
                has_symlink = False

            # First sync locks script_file, skips pyc_file and sym_link
            res1 = file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertGreaterEqual(res1.locked_count, 1)
            self.assertEqual(res1.already_locked_count, 0)
            self.assertTrue(file_lock.is_file_readonly(script_file))
            self.assertFalse(file_lock.is_file_readonly(pyc_file))

            # Verify directory itself remains writable so Python can create new .pyc files inside __pycache__ (EC-02)
            new_pyc = pyc_dir / "dynamic_new.cpython-312.pyc"
            new_pyc.write_bytes(b"new_bytecode")
            self.assertTrue(new_pyc.is_file())

            if os.name != "nt":
                mode_locked = stat.S_IMODE(os.stat(script_file).st_mode)
                self.assertEqual(mode_locked & 0o111, 0o111, "Execute bits must be preserved when locked")
                self.assertEqual(mode_locked & 0o222, 0, "Write bits must be stripped when locked")

            if has_symlink:
                self.assertFalse(file_lock.is_file_readonly(outside_target))
                self.assertFalse(file_lock.apply_lock_bits(sym_link))
                self.assertFalse(file_lock.strip_lock_bits(sym_link))

            # Second sync hits already_locked_count without re-chmoding
            res2 = file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertEqual(res2.locked_count, 0)
            self.assertGreaterEqual(res2.already_locked_count, 1)

            if has_symlink:
                dir_sym = self.proj_root / "src" / "link_to_schemas"
                os.symlink(self.schemas_dir, dir_sym)
                (self.schemas_dir / "meta" / "manifest.schema.json").write_text("{}", encoding="utf-8")
                self.assertFalse(
                    file_lock.is_protected(dir_sym / "meta" / "manifest.schema.json", root_dir=self.proj_root),
                    "Directory symlink inside unprotected workspace area must not match /readonly when follow_symlinks=False",
                )

            # Unlock restores owner write bit while preserving execute bit
            u_res = file_lock.unlock_path(script_file, root_dir=self.proj_root)
            self.assertEqual(u_res.unlocked_count, 1)
            self.assertFalse(file_lock.is_file_readonly(script_file))

            # Simulated Windows ("nt") branch verification
            nt_file = self.proj_root / "src" / "nt_sim.txt"
            nt_file.write_text("nt branch test", encoding="utf-8")
            with patch.object(file_lock.os, "name", "nt"):
                self.assertFalse(file_lock.is_file_readonly(nt_file))
                self.assertTrue(file_lock.apply_lock_bits(nt_file))
                self.assertTrue(file_lock.is_file_readonly(nt_file))
                # Second call hits already_locked on nt branch
                self.assertEqual(file_lock._apply_lock_bits_state(str(nt_file)), "already_locked")
                info_nt = file_lock.inspect_path(nt_file, root_dir=self.proj_root)
                self.assertTrue(info_nt.is_readonly)
                # Strip lock bits on file and directory under nt branch
                self.assertTrue(file_lock.strip_lock_bits(nt_file))
                self.assertFalse(file_lock.is_file_readonly(nt_file))
                self.assertEqual(file_lock._strip_lock_bits_state(str(nt_file)), "already_unlocked")
                self.assertTrue(file_lock.strip_lock_bits(nt_file.parent))
        self.mark_passed()

    def test_ft03_vfs_transparent_tunneling_move_swap_and_ec01_reentrancy(self) -> None:
        """
        FT-03 & EC-01: Verify that once a file in `/readonly` is locked:
        - Direct `open(path, "w")` raises `PermissionError`.
        - `vfs.write_text` (atomic=True & atomic=False), `vfs.write_bytes`, `vfs.atomic_write`,
          `vfs.copy` (single file & directory `_safe_copytree`), `vfs.move` (into & out of `/readonly`),
          `vfs.open(path, "w")` (including `mode="x"` exception rollback), and `atomic_swap_directory`
          transparently unlock before write and reconcile lock bits afterward (`AUD-04`).
        - Re-entrancy flag `tls.in_lock_op = True` and `SpaceRegistry` failure degrade safely (`AUD-03`).
        """
        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
        ):
            uri.invalidate_uri_cache()
            reset_default_registry()
            todo_path = self.roadmap_dir / "TODO.md"
            todo_path.write_text("# Initial TODO\n", encoding="utf-8")
            file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertTrue(file_lock.is_file_readonly(todo_path))

            if hasattr(os, "geteuid") and os.geteuid() != 0:
                with self.assertRaises(PermissionError):
                    with open(todo_path, "w", encoding="utf-8") as f:
                        f.write("unauthorized direct write")

            # 1. vfs.write_text (atomic=True & atomic=False)
            vfs.write_text(str(todo_path), "# Updated via atomic write_text\n", atomic=True)
            self.assertEqual(vfs.read_text(str(todo_path)), "# Updated via atomic write_text\n")
            self.assertTrue(file_lock.is_file_readonly(todo_path))

            vfs.write_text(str(todo_path), "# Updated via non-atomic write_text\n", atomic=False)
            self.assertEqual(vfs.read_text(str(todo_path)), "# Updated via non-atomic write_text\n")
            self.assertTrue(file_lock.is_file_readonly(todo_path))

            # 2. vfs.write_bytes (atomic=False)
            vfs.write_bytes(str(todo_path), b"# Updated via write_bytes\n", atomic=False)
            self.assertTrue(file_lock.is_file_readonly(todo_path))

            # 3. vfs.open(path, "w") & mode="x" failure rollback
            with vfs.open(str(todo_path), "w", encoding="utf-8") as vf:
                vf.write("# Updated via VFS.open\n")
            self.assertEqual(vfs.read_text(str(todo_path)), "# Updated via VFS.open\n")
            self.assertTrue(file_lock.is_file_readonly(todo_path))

            with self.assertRaises(FileExistsError):
                vfs.open(str(todo_path), "x", encoding="utf-8")
            self.assertTrue(
                file_lock.is_file_readonly(todo_path),
                "Failed VFS.open('x') on existing file must preserve read-only lock",
            )

            # 4. Single-file & directory vfs.copy to unprotected area strips lock bits
            unprotected_copy = self.proj_root / "src" / "todo_copy.md"
            vfs.copy(str(todo_path), str(unprotected_copy))
            self.assertFalse(file_lock.is_file_readonly(unprotected_copy))

            unprotected_dir_copy = self.proj_root / "src" / "schemas_copy"
            (self.schemas_dir / "meta" / "manifest.schema.json").write_text("{}", encoding="utf-8")
            file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertTrue(file_lock.is_file_readonly(self.schemas_dir / "meta" / "manifest.schema.json"))
            vfs.copy(str(self.schemas_dir), str(unprotected_dir_copy))
            self.assertFalse(
                file_lock.is_file_readonly(unprotected_dir_copy / "meta" / "manifest.schema.json"),
                "_safe_copytree to unprotected directory must strip read-only bits",
            )

            # 5. vfs.move into /readonly locks destination; vfs.move out of /readonly strips lock bits
            stage_src = self.proj_root / "src" / "staged_changelog.md"
            stage_src.write_text("# Staged Changelog\n", encoding="utf-8")
            cl_dest = self.plans_dir / "2026_11_10_0001_demo" / "changelog.md"
            vfs.move(str(stage_src), str(cl_dest))
            self.assertTrue(file_lock.is_file_readonly(cl_dest))

            moved_out = self.proj_root / "src" / "moved_out_changelog.md"
            vfs.move(str(cl_dest), str(moved_out))
            self.assertFalse(
                file_lock.is_file_readonly(moved_out),
                "Moving a locked file out of /readonly must strip read-only lock bits",
            )

            with self.assertRaises(LookupError):
                vfs.open(str(todo_path), "w", encoding="invalid_codec_xyz")
            self.assertTrue(
                file_lock.is_file_readonly(todo_path),
                "Failed VFS.open('w') must restore read-only lock on exception",
            )

            # Directory vfs.move out of /readonly strips lock bits on child files
            dir_move_src = self.schemas_dir / "move_sub"
            dir_move_src.mkdir(parents=True, exist_ok=True)
            (dir_move_src / "locked_child.json").write_text("{}", encoding="utf-8")
            file_lock.apply_lock_bits(dir_move_src / "locked_child.json")
            self.assertTrue(file_lock.is_file_readonly(dir_move_src / "locked_child.json"))
            dir_move_dst = self.proj_root / "src" / "moved_sub_out"
            vfs.move(str(dir_move_src), str(dir_move_dst))
            self.assertFalse(
                file_lock.is_file_readonly(dir_move_dst / "locked_child.json"),
                "Moving a directory out of /readonly must strip lock bits on child files",
            )

            # Ancestor directory symlink alias parity (simulating macOS /var -> /private/var)
            alias_parent = Path(self.temp_dir) / "var_alias_parent"
            try:
                os.symlink(self.proj_root, alias_parent)
                has_dir_alias = True
            except OSError:
                has_dir_alias = False
            if has_dir_alias:
                with bind_runtime_context(
                    virtual_cwd=alias_parent,
                    host_dir=alias_parent,
                    yscb_dir=alias_parent / ".yscb",
                ):
                    uri.invalidate_uri_cache()
                    reset_default_registry()
                    resolved_real_todo = (alias_parent / "plans" / "roadmap" / "TODO.md").resolve()
                    self.assertTrue(file_lock.is_protected(resolved_real_todo))
                    with file_lock.writable_scope(alias_parent / "plans" / "roadmap" / "TODO.md"):
                        vfs.write_text(str(resolved_real_todo), "# Alias scope test\n", atomic=True)
                        self.assertFalse(file_lock.is_file_readonly(resolved_real_todo))
                    self.assertTrue(file_lock.is_file_readonly(resolved_real_todo))
                uri.invalidate_uri_cache()
                reset_default_registry()

            # 6. atomic_swap_directory into /readonly
            target_mod_dir = self.modules_dir / "sample_swap"
            target_mod_dir.mkdir(parents=True, exist_ok=True)
            old_mod_f = target_mod_dir / "old.py"
            old_mod_f.write_text("old = 1\n", encoding="utf-8")
            file_lock.apply_lock_bits(old_mod_f)
            self.assertTrue(file_lock.is_file_readonly(old_mod_f))

            staging_mod_dir = self.modules_dir / ".staging_sample_swap_test"
            staging_mod_dir.mkdir(parents=True, exist_ok=True)
            new_mod_f = staging_mod_dir / "new.py"
            new_mod_f.write_text("new = 2\n", encoding="utf-8")
            atomic_swap_directory(str(staging_mod_dir), str(target_mod_dir))
            self.assertFalse((target_mod_dir / "old.py").exists())
            self.assertTrue((target_mod_dir / "new.py").is_file())
            self.assertTrue(file_lock.is_file_readonly(target_mod_dir / "new.py"))
            self.assertFalse(staging_mod_dir.exists())

            # 6b. Directory fallback chmod & vfs.copy over existing locked directory preserve S_IXUSR (0o700)
            from core.vfs.os_backend import _strip_lock_bits_safe, robust_rmtree

            ro_sub_dir = self.modules_dir / "sample_ro_dir" / "sub"
            ro_sub_dir.mkdir(parents=True, exist_ok=True)
            ro_sub_file = ro_sub_dir / "__init__.py"
            ro_sub_file.write_text("x = 1\n", encoding="utf-8")
            file_lock.apply_lock_bits(ro_sub_file)
            if os.name != "nt":
                os.chmod(ro_sub_dir, 0o600)
                with patch("core.file_lock.strip_lock_bits", side_effect=RuntimeError("fallback check")):
                    _strip_lock_bits_safe(str(ro_sub_dir))
                dir_mode = stat.S_IMODE(os.lstat(ro_sub_dir).st_mode)
                self.assertEqual(dir_mode & 0o700, 0o700)
            robust_rmtree(str(self.modules_dir / "sample_ro_dir"))
            self.assertFalse((self.modules_dir / "sample_ro_dir").exists())

            # 7. EC-01: Re-entrancy guard (tls.in_lock_op = True) and SpaceRegistry failure fallback
            tls = get_runtime_context().file_lock_tls
            tls.in_lock_op = True
            try:
                self.assertFalse(file_lock.is_protected(todo_path, root_dir=self.proj_root))
                self.assertFalse(file_lock.inspect_path(todo_path, root_dir=self.proj_root).is_protected)
                self.assertFalse(file_lock.relock_if_protected(todo_path, root_dir=self.proj_root))
                re_sync = file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
                self.assertEqual(re_sync.scanned_count, 0)
                self.assertTrue(tls.in_lock_op)
            finally:
                tls.in_lock_op = False

            with patch(
                "core.space.registry.get_default_registry",
                side_effect=RuntimeError("simulated registry failure"),
            ):
                self.assertFalse(file_lock.is_protected(todo_path, root_dir=self.proj_root))
                self.assertFalse(file_lock.inspect_path(todo_path, root_dir=self.proj_root).is_protected)
                err_sync = file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
                self.assertEqual(err_sync.error_count, 1)
                self.assertFalse(getattr(tls, "in_lock_op", False))
        self.mark_passed()

    def test_ft04_writable_scope_file_and_directory_nested_reentrancy(self) -> None:
        """
        FT-04 & EC-03: Verify `with file_lock.writable_scope(path):` supports:
        - Single-file nested re-entrancy and exception recovery.
        - Directory-level `with file_lock.writable_scope(dir_path):` batch unlock, continuous VFS
          writes & new file creation inside the directory without premature relocking, and
          batch relocking upon exit (`AUD-02`).
        """
        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
        ):
            uri.invalidate_uri_cache()
            reset_default_registry()
            cl_path = self.plans_dir / "2026_11_10_0001_demo" / "changelog.md"
            cl_path.write_text("# Changelog\n", encoding="utf-8")
            file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertTrue(file_lock.is_file_readonly(cl_path))

            with file_lock.writable_scope(cl_path, root_dir=self.proj_root):
                self.assertFalse(file_lock.is_file_readonly(cl_path))
                with file_lock.writable_scope(cl_path, root_dir=self.proj_root):
                    vfs.write_text(str(cl_path), "# Step 1\n", atomic=True)
                    self.assertFalse(file_lock.is_file_readonly(cl_path))
                self.assertFalse(file_lock.is_file_readonly(cl_path))
                with open(cl_path, "a", encoding="utf-8") as f:
                    f.write("- Entry 2\n")

            self.assertTrue(file_lock.is_file_readonly(cl_path))

            # Exception recovery check
            with self.assertRaises(RuntimeError):
                with file_lock.writable_scope(cl_path, root_dir=self.proj_root):
                    self.assertFalse(file_lock.is_file_readonly(cl_path))
                    raise RuntimeError("simulated failure inside writable_scope")
            self.assertTrue(file_lock.is_file_readonly(cl_path))

            # Directory-level writable_scope check
            mod_dir = self.modules_dir / "core"
            f1 = mod_dir / "a.py"
            f2 = mod_dir / "sub" / "b.py"
            f2.parent.mkdir(parents=True, exist_ok=True)
            f1.write_text("a = 1\n", encoding="utf-8")
            f2.write_text("b = 1\n", encoding="utf-8")
            file_lock.sync("/readonly", root_dir=self.proj_root, emit_event=False)
            self.assertTrue(file_lock.is_file_readonly(f1))
            self.assertTrue(file_lock.is_file_readonly(f2))

            f3 = mod_dir / "sub" / "c_new.py"
            with file_lock.writable_scope(mod_dir, root_dir=self.proj_root):
                self.assertFalse(file_lock.is_file_readonly(f1))
                self.assertFalse(file_lock.is_file_readonly(f2))
                vfs.write_text(str(f1), "a = 2\n", atomic=True)
                vfs.write_text(str(f2), "b = 2\n", atomic=False)
                vfs.write_text(str(f3), "c = 3\n", atomic=True)
                self.assertFalse(file_lock.is_file_readonly(f1))
                self.assertFalse(file_lock.is_file_readonly(f2))
                self.assertFalse(file_lock.is_file_readonly(f3))
                with open(f1, "a", encoding="utf-8") as raw_f:
                    raw_f.write("# appended\n")

            self.assertTrue(file_lock.is_file_readonly(f1))
            self.assertTrue(file_lock.is_file_readonly(f2))
            self.assertTrue(file_lock.is_file_readonly(f3))
        self.mark_passed()

    def test_ft05_cli_file_lock_commands_json_human_output_and_event(self) -> None:
        """
        FT-05: Verify `yscb core file-lock <status|sync|lock|unlock> [target] [--json]`
        CLI handlers in both `--json` and human-readable modes, space-level `unlock_path("/readonly")`,
        `lock_path(..., force=True)`, and `on_file_lock_synced` event broadcasting.
        """
        from core.loader import load_module_from_path

        cli_path = Path(__file__).resolve().parents[1] / "scripts" / "cli.py"
        core_cli = load_module_from_path("_yscb_mod_test_core_cli_fl", cli_path)

        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
            env={"YSCB_GUARD_TOKEN": "1"},
        ):
            uri.invalidate_uri_cache()
            reset_default_registry()
            mod_f = self.modules_dir / "core" / "mod_a.py"
            mod_f.write_text("x = 1\n", encoding="utf-8")

            # 1. sync --json & event broadcast verification
            with patch.object(events, "broadcast") as mock_bcast:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = core_cli.file_lock(
                        CmdBags(
                            raw_cmd=["file-lock", "sync", "--json"],
                            command="file-lock",
                            args=["sync"],
                            options={"json": CmdOption(name="json")},
                        )
                    )
                self.assertEqual(rc, 0)
                sync_data = json.loads(buf.getvalue())
                self.assertEqual(sync_data["target_space"], "/readonly")
                self.assertTrue(file_lock.is_file_readonly(mod_f))
                self.assertTrue(
                    any(call.args and call.args[0] == "on_file_lock_synced" for call in mock_bcast.call_args_list)
                )

            # 2. status --json (space mode) & status /readonly (PERF-005 regression check: no double count)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = core_cli.file_lock_status(
                    CmdBags(
                        raw_cmd=["status", "--json"],
                        command="status",
                        args=[],
                        options={"json": CmdOption(name="json")},
                    )
                )
            self.assertEqual(rc, 0)
            st_data = json.loads(buf.getvalue())
            self.assertEqual(st_data["mode"], "space")
            self.assertTrue(st_data["in_sync"])
            st_explicit = file_lock.status("/readonly", root_dir=self.proj_root)
            self.assertEqual(st_explicit["total_files"], st_data["total_files"])

            # 3. status <path> --json (path mode)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = core_cli.file_lock_status(
                    CmdBags(
                        raw_cmd=["status", str(mod_f), "--json"],
                        command="status",
                        args=[str(mod_f)],
                        options={"json": CmdOption(name="json")},
                    )
                )
            self.assertEqual(rc, 0)
            p_data = json.loads(buf.getvalue())
            self.assertEqual(p_data["mode"], "path")
            self.assertTrue(p_data["is_protected"])
            self.assertTrue(p_data["is_readonly"])

            # 4. Human-readable CLI outputs & space-level unlock/lock
            human_buf = io.StringIO()
            with redirect_stdout(human_buf):
                self.assertEqual(core_cli.file_lock(CmdBags(raw_cmd=["file-lock", "status"], command="file-lock", args=["status"], options={})), 0)
                self.assertEqual(core_cli.file_lock(CmdBags(raw_cmd=["file-lock", "status", str(mod_f)], command="file-lock", args=["status", str(mod_f)], options={})), 0)
                self.assertEqual(core_cli.file_lock(CmdBags(raw_cmd=["file-lock", "unlock"], command="file-lock", args=["unlock"], options={})), 0)
                self.assertFalse(file_lock.is_file_readonly(mod_f))
                self.assertEqual(core_cli.file_lock(CmdBags(raw_cmd=["file-lock", "lock", "core"], command="file-lock", args=["lock", "core"], options={})), 0)
                self.assertTrue(file_lock.is_file_readonly(mod_f))
                self.assertEqual(core_cli.file_lock(CmdBags(raw_cmd=["file-lock", "sync"], command="file-lock", args=["sync"], options={})), 0)
            human_out = human_buf.getvalue()
            self.assertIn("Declarative Read-Only File Lock Status", human_out)
            self.assertIn("File Lock Path Diagnostic", human_out)

            # Force lock on unprotected file & unknown subcommand
            unprot_f = self.proj_root / "src" / "custom.txt"
            unprot_f.write_text("custom", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    core_cli.file_lock_lock(
                        CmdBags(
                            raw_cmd=["lock", str(unprot_f), "--force"],
                            command="lock",
                            args=[str(unprot_f)],
                            options={"force": CmdOption(name="force")},
                        )
                    ),
                    0,
                )
            self.assertTrue(file_lock.is_file_readonly(unprot_f))

            json_u_buf = io.StringIO()
            with redirect_stdout(json_u_buf):
                self.assertEqual(
                    core_cli.file_lock_unlock(
                        CmdBags(
                            raw_cmd=["unlock", str(mod_f), "--json"],
                            command="unlock",
                            args=[str(mod_f)],
                            options={"json": CmdOption(name="json")},
                        )
                    ),
                    0,
                )
            self.assertEqual(json.loads(json_u_buf.getvalue())["unlocked_count"], 1)

            json_l_buf = io.StringIO()
            with redirect_stdout(json_l_buf):
                self.assertEqual(
                    core_cli.file_lock_lock(
                        CmdBags(
                            raw_cmd=["lock", str(mod_f), "--json"],
                            command="lock",
                            args=[str(mod_f)],
                            options={"json": CmdOption(name="json")},
                        )
                    ),
                    0,
                )
            self.assertEqual(json.loads(json_l_buf.getvalue())["locked_count"], 1)

            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                self.assertEqual(
                    core_cli.file_lock(
                        CmdBags(raw_cmd=["file-lock", "invalid-sub"], command="file-lock", args=["invalid-sub"], options={})
                    ),
                    1,
                )
            self.assertIn("Unknown subcommand", err_buf.getvalue())
        self.mark_passed()

    def test_ft06_cross_module_readonly_integration_and_ec05_bit_stripping(self) -> None:
        """
        FT-06 & EC-05 (`AUD-01`): Explicit end-to-end verification across `gdrive-support`,
        `vscode-support`, and `agents-workflow` when operating on read-only (`0o444`) files:
        1. `gdrive-support`: `_create_conflict_backup` and `LocalSandboxTransport.upload_file`
           strip read-only bits on `.conflict.*.bak` and simulated remote files.
        2. `vscode-support`: `SchemaCompiler.sync_all_schemas` locks compiled `.schema.json`
           files and cleanly removes locked orphan `.schema.json` files.
        3. `agents-workflow`: `PlanArchiver.archive_plan` locks archived plan files, and
           `TodoManager.add_todo` updates a locked `TODO.md` and preserves its lock.
        """
        import sys
        from core.platform.venv import ensure_installed_modules_path, restore_sys_path

        source_root = Path(__file__).resolve().parents[2]
        extra_paths = [
            str(source_root / "gdrive-support"),
            str(source_root / "vscode-support"),
            str(source_root / "agents-workflow"),
        ]
        orig_sys_path = list(sys.path)
        ensure_installed_modules_path(extra_paths=extra_paths)
        from agents_workflow.plans.archiver import PlanArchiver
        from agents_workflow.roadmap import TodoManager
        from gdrive_support.coordinator import _create_conflict_backup
        from gdrive_support.sandbox_transport import LocalSandboxTransport
        from vscode_support.schema_compiler import SchemaCompiler

        with bind_runtime_context(
            virtual_cwd=self.proj_root,
            host_dir=self.proj_root,
            yscb_dir=self.yscb_dir,
        ):
            uri.invalidate_uri_cache()
            reset_default_registry()

            # 1. EC-05: gdrive-support conflict backup & sandbox_transport upload from a locked source file
            locked_src = self.roadmap_dir / "TODO.md"
            locked_src.write_text("# Locked Source\n", encoding="utf-8")
            file_lock.apply_lock_bits(locked_src)
            self.assertTrue(file_lock.is_file_readonly(locked_src))

            bak_path = _create_conflict_backup(locked_src)
            self.assertTrue(bak_path.is_file())
            self.assertFalse(
                file_lock.is_file_readonly(bak_path),
                "Conflict backup (.conflict.*.bak) must be writable for user conflict resolution",
            )
            with open(bak_path, "a", encoding="utf-8") as bf:
                bf.write("user resolved line\n")

            sbx_remote_root = self.proj_root / "gdrive_sbx"
            transport = LocalSandboxTransport(sbx_remote_root)
            transport.upload_file(locked_src, "repo_sync/main/plans/roadmap/TODO.md")
            remote_phys = sbx_remote_root / "repo_sync" / "main" / "plans" / "roadmap" / "TODO.md"
            self.assertTrue(remote_phys.is_file())
            self.assertFalse(
                file_lock.is_file_readonly(remote_phys),
                "Sandbox remote backing file must be stripped of read-only lock bits",
            )
            # Re-uploading over the existing sandbox remote file must also succeed without PermissionError
            transport.upload_file(locked_src, "repo_sync/main/plans/roadmap/TODO.md")

            # 2. vscode-support: SchemaCompiler locks schemas and deletes locked orphan schemas
            orphan_schema = self.schemas_dir / "contributes" / "orphan_mod.schema.json"
            orphan_schema.parent.mkdir(parents=True, exist_ok=True)
            orphan_schema.write_text("{}", encoding="utf-8")
            file_lock.apply_lock_bits(orphan_schema)
            self.assertTrue(file_lock.is_file_readonly(orphan_schema))

            compiler = SchemaCompiler(yscb_dir=str(self.yscb_dir))
            compiler.sync_all_schemas(str(self.proj_root))
            self.assertFalse(orphan_schema.exists(), "Locked orphan schema must be removed via VFS")
            meta_schema = self.schemas_dir / "meta" / "manifest.schema.json"
            self.assertTrue(meta_schema.is_file())
            self.assertTrue(file_lock.is_file_readonly(meta_schema))

            # 3. agents-workflow: TodoManager updates locked TODO.md and keeps it locked; PlanArchiver locks archived plan
            todo_mgr = TodoManager(roadmap_dir=self.roadmap_dir, plans_dir=self.plans_dir)
            todo_res = todo_mgr.add_todo(title="Verify locked TODO tunnel", scope="core", note="FT-06")
            self.assertEqual(todo_res.todo_id, "TODO-01")
            self.assertTrue(file_lock.is_file_readonly(self.roadmap_dir / "TODO.md"))

            plan_name = "2026_11_10_0001_demo"
            plan_dir = self.plans_dir / plan_name
            (plan_dir / "P00_discuss.md").write_text(
                "# P00\n> 功能名稱：demo\n> 建立日期：2026-11-10\n> 狀態：Completed\n> 模型：Test\n",
                encoding="utf-8",
            )
            archiver = PlanArchiver(
                plans_dir=self.plans_dir,
                archive_dir=self.archived_dir,
                project_root=self.proj_root,
            )
            arch_res = archiver.archive_plan(plan_name, force=True)
            self.assertTrue(arch_res["success"])
            archived_p00 = Path(arch_res["dest_path"]) / "P00_discuss.md"
            self.assertTrue(archived_p00.is_file())
            self.assertTrue(file_lock.is_file_readonly(archived_p00))
        restore_sys_path(orig_sys_path)
        self.mark_passed()
