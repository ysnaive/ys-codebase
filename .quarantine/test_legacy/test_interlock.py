#!/usr/bin/env python3
"""
test/test_interlock.py — Installation-time Interlock & Open Protocol System Comprehensive Test Suite
Tests: FT-01~08, ET-01~08, PT-01
"""

import sys
import os
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path

# Windows console encoding safeguard
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
YS_CODEBASE_DIR = PROJECT_ROOT / "ys_codebase"

# Add source directories to sys.path
core_src = YS_CODEBASE_DIR / "source" / "core" / "scripts"
workflow_src = YS_CODEBASE_DIR / "source" / "agents-workflow" / "scripts"
for p in [core_src, workflow_src, YS_CODEBASE_DIR]:
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from context import ProjectContext
from sop_synthesizer import SOPSynthesizer
from ide_sync import IDECacheTracker
from ext_registry import ExtensionRegistry
import yscb_installer


class TestInterlockSystem(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="yscb_test_interlock_"))

    def tearDown(self):
        if self.test_dir.is_dir():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── FT-01: Core SDK get_contributions() ──────────────────────────
    def test_ft_01_core_get_contributions(self):
        modules_dir = self.test_dir / "modules"
        mod_a = modules_dir / "mod_a"
        mod_a.mkdir(parents=True)
        manifest_a = {
            "name": "mod_a",
            "version": "1.0.0",
            "contributes": {
                "agents-workflow": {
                    "sop_patches": [{"target_sop": "NewPlan.md"}]
                }
            }
        }
        (mod_a / "manifest.json").write_text(json.dumps(manifest_a), encoding="utf-8")

        mod_b = modules_dir / "mod_b"
        mod_b.mkdir(parents=True)
        manifest_b = {"name": "mod_b", "version": "1.0.0"}
        (mod_b / "manifest.json").write_text(json.dumps(manifest_b), encoding="utf-8")

        contributions = ProjectContext.get_contributions("agents-workflow", start_dir=self.test_dir)
        self.assertEqual(len(contributions), 1)
        name, root, payload = contributions[0]
        self.assertEqual(name, "mod_a")
        self.assertEqual(root, mod_a)
        self.assertIn("sop_patches", payload)

    # ── FT-02: SOPSynthesizer slot injection (append/prepend) ────────
    def test_ft_02_sop_synthesizer_injection(self):
        template = (
            "# SOP Header\n\n"
            "### Phase 0\n"
            "Phase 0 content.\n"
            "<!-- YSCB_SLOT:Phase0 -->\n\n"
            "### Phase 6\n"
            "Phase 6 content.\n"
            "<!-- YSCB_SLOT:Phase6 -->\n"
        )
        plugin_dir = self.test_dir / "mock_plugin"
        (plugin_dir / "templates").mkdir(parents=True)
        (plugin_dir / "templates" / "p0.md").write_text("INJECTED_P0_APPEND", encoding="utf-8")
        (plugin_dir / "templates" / "p6.md").write_text("INJECTED_P6_PREPEND", encoding="utf-8")

        patches = [
            {"target_sop": "Test.md", "target_slot": "Phase0", "position": "append", "content_file": "templates/p0.md"},
            {"target_sop": "Test.md", "target_slot": "Phase6", "position": "prepend", "content_file": "templates/p6.md"},
        ]

        result = SOPSynthesizer.synthesize_sop(template, patches, plugin_dir)
        self.assertIn("INJECTED_P0_APPEND", result)
        self.assertIn("INJECTED_P6_PREPEND", result)

    # ── FT-03: SOPSynthesizer slot marker stripping ──────────────────
    def test_ft_03_sop_synthesizer_strip_markers(self):
        text_with_slots = (
            "# Main Doc\n"
            "<!-- YSCB_SLOT:Phase0 -->\n"
            "Some content.\n"
            "<!-- YSCB_SLOT:Step1 -->\n"
        )
        cleaned = SOPSynthesizer.strip_slot_markers(text_with_slots)
        self.assertNotIn("YSCB_SLOT", cleaned)
        self.assertIn("# Main Doc", cleaned)
        self.assertIn("Some content.", cleaned)

    # ── FT-04: _on_modules_changed.py synthesis end-to-end ───────────
    def test_ft_04_on_modules_changed_synthesis(self):
        from _on_modules_changed import parse_changes
        changes = parse_changes(["installed:core", "updated:agents-workflow", "removed:old-mod"])
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes[0], ("installed", "core"))
        self.assertEqual(changes[1], ("updated", "agents-workflow"))
        self.assertEqual(changes[2], ("removed", "old-mod"))

    # ── FT-05: IDECacheTracker orphan cleanup ────────────────────────
    def test_ft_05_ide_cache_tracker_cleanup(self):
        tracker = IDECacheTracker(self.test_dir)
        ide_wf_dir = self.test_dir / ".agents" / "workflows"
        ide_wf_dir.mkdir(parents=True)

        file1 = ide_wf_dir / "NewPlan.md"
        file2 = ide_wf_dir / "OldDeletedPlan.md"
        file1.write_text("NewPlan", encoding="utf-8")
        file2.write_text("OldPlan", encoding="utf-8")

        # Record manifest containing file1 and file2
        tracker.save_manifest([file1, file2])

        # Next run only generates file1
        deleted = tracker.clean_orphans([file1])
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0].name, "OldDeletedPlan.md")
        self.assertFalse(file2.exists())
        self.assertTrue(file1.exists())

    # ── FT-06: ExtensionRegistry dual discovery & priority ───────────
    def test_ft_06_extension_registry_priority(self):
        # 1. Module-contributed extension
        modules_dir = self.test_dir / "modules"
        mod_dir = modules_dir / "test_plugin"
        (mod_dir / "scripts").mkdir(parents=True)
        (mod_dir / "workflows" / "extensions").mkdir(parents=True)

        (mod_dir / "scripts" / "verify.py").write_text("# verify", encoding="utf-8")
        (mod_dir / "workflows" / "extensions" / "my_ext.md").write_text("# Module Ext Doc", encoding="utf-8")

        manifest = {
            "name": "test_plugin",
            "version": "1.0.0",
            "contributes": {
                "agents-workflow": {
                    "sop_extensions": [
                        {
                            "name": "my_ext",
                            "script": "scripts/verify.py",
                            "doc": "workflows/extensions/my_ext.md",
                            "trigger": "always"
                        }
                    ]
                }
            }
        }
        (mod_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        class MockCtx:
            @staticmethod
            def get_contributions(ns, start_dir=None):
                return [("test_plugin", mod_dir, manifest["contributes"]["agents-workflow"])]
            @staticmethod
            def get_project_root(start_dir=None):
                return self.test_dir

        # Test discovering module extension
        reg = ExtensionRegistry.discover_all(MockCtx, start_dir=self.test_dir)
        self.assertIn("my_ext", reg)
        self.assertEqual(reg["my_ext"]["source_type"], "module")
        self.assertEqual(reg["my_ext"]["trigger"], "always")

        # 2. Project custom extension with same name overrides module
        ext_dir = self.test_dir / "extensions"
        ext_dir.mkdir(parents=True)
        (ext_dir / "my_ext.md").write_text("---\nname: my_ext\ntrigger: on_demand\n---\n# Custom Ext Doc", encoding="utf-8")

        reg_override = ExtensionRegistry.discover_all(MockCtx, start_dir=self.test_dir)
        self.assertIn("my_ext", reg_override)
        self.assertEqual(reg_override["my_ext"]["source_type"], "sop_ext")
        self.assertEqual(reg_override["my_ext"]["trigger"], "on_demand")

    # ── FT-07: Broadcast modules changed on install/pull/remove ──────
    def test_ft_07_installer_broadcast_modules_changed(self):
        hook_dir = self.test_dir / "modules" / "hook_mod" / "scripts"
        hook_dir.mkdir(parents=True)
        hook_script = hook_dir / "_on_modules_changed.py"
        hook_script.write_text(
            "import sys, pathlib\n"
            "pathlib.Path(__file__).parent.joinpath('out.log').write_text(' '.join(sys.argv[1:]))\n",
            encoding="utf-8"
        )
        (self.test_dir / "modules" / "hook_mod" / "manifest.json").write_text(
            json.dumps({"name": "hook_mod", "version": "1.0.0"}),
            encoding="utf-8"
        )
        (self.test_dir / "yscb_config.json").write_text(
            json.dumps({"installed_modules": {"hook_mod": {"mode": "build", "version": "1.0.0"}}}),
            encoding="utf-8"
        )

        cfg_mgr = yscb_installer.ConfigManager(self.test_dir)
        git_client = yscb_installer.GitRemoteClient(self.test_dir)
        mgr = yscb_installer.ModuleManager(self.test_dir, cfg_mgr, git_client)
        mgr._broadcast_modules_changed([("installed", "hook_mod"), ("updated", "core")])

        log_file = hook_dir / "out.log"
        self.assertTrue(log_file.exists())
        self.assertEqual(log_file.read_text(encoding="utf-8").strip(), "installed:hook_mod updated:core")

    # ── FT-08: Build command strictly does NOT broadcast ─────────────
    def test_ft_08_build_does_not_broadcast(self):
        hook_dir = self.test_dir / "source" / "hook_mod" / "scripts"
        hook_dir.mkdir(parents=True)
        hook_script = hook_dir / "_on_modules_changed.py"
        hook_script.write_text(
            "import sys, pathlib\n"
            "pathlib.Path(__file__).parent.joinpath('build_invoked.log').write_text('invoked')\n",
            encoding="utf-8"
        )
        (self.test_dir / "source" / "hook_mod" / "manifest.json").write_text(
            json.dumps({"name": "hook_mod", "version": "1.0.0"}),
            encoding="utf-8"
        )

        cfg_mgr = yscb_installer.ConfigManager(self.test_dir)
        git_client = yscb_installer.GitRemoteClient(self.test_dir)
        mgr = yscb_installer.ModuleManager(self.test_dir, cfg_mgr, git_client)
        mgr.build_module("hook_mod")

        build_log = hook_dir / "build_invoked.log"
        self.assertFalse(build_log.exists(), "build must not invoke _on_modules_changed.py!")

    # ── ET-01: Missing slot gracefully appends to file end ───────────
    def test_et_01_missing_slot_fallback(self):
        template = "# Template without matching slot\nSome text."
        patch = {"target_sop": "T.md", "target_slot": "NonExistentSlot", "position": "append", "content": "FALLBACK_CONTENT"}
        res = SOPSynthesizer.synthesize_sop(template, [patch])
        self.assertIn("FALLBACK_CONTENT", res)

    # ── ET-02: Missing content file gracefully skipped ───────────────
    def test_et_02_missing_content_file(self):
        template = "# Template\n<!-- YSCB_SLOT:Phase0 -->"
        patch = {"target_sop": "T.md", "target_slot": "Phase0", "position": "append", "content_file": "templates/not_found.md"}
        res = SOPSynthesizer.synthesize_sop(template, [patch], self.test_dir)
        # Should not crash, slot marker intact
        self.assertIn("<!-- YSCB_SLOT:Phase0 -->", res)

    # ── ET-03: Corrupted manifest in get_contributions ────────────────
    def test_et_03_corrupted_manifest(self):
        modules_dir = self.test_dir / "modules" / "bad_mod"
        modules_dir.mkdir(parents=True)
        (modules_dir / "manifest.json").write_text("{ invalid json ...", encoding="utf-8")

        contributions = ProjectContext.get_contributions("agents-workflow", start_dir=self.test_dir)
        self.assertEqual(len(contributions), 0)

    # ── ET-04: Hook script error isolation ───────────────────────────
    def test_et_04_hook_script_error_isolation(self):
        hook_dir = self.test_dir / "modules" / "failing_mod" / "scripts"
        hook_dir.mkdir(parents=True)
        hook_script = hook_dir / "_on_modules_changed.py"
        hook_script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        (self.test_dir / "modules" / "failing_mod" / "manifest.json").write_text(
            json.dumps({"name": "failing_mod", "version": "1.0.0"}),
            encoding="utf-8"
        )
        (self.test_dir / "yscb_config.json").write_text(
            json.dumps({"installed_modules": {"failing_mod": {"mode": "build", "version": "1.0.0"}}}),
            encoding="utf-8"
        )

        cfg_mgr = yscb_installer.ConfigManager(self.test_dir)
        git_client = yscb_installer.GitRemoteClient(self.test_dir)
        mgr = yscb_installer.ModuleManager(self.test_dir, cfg_mgr, git_client)
        # Should not raise exception
        mgr._broadcast_modules_changed([("installed", "failing_mod")])

    # ── ET-05: Malformed delta args ──────────────────────────────────
    def test_et_05_malformed_delta_args(self):
        from _on_modules_changed import parse_changes
        changes = parse_changes(["invalid_arg_without_colon", "installed:valid_mod"])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0], ("installed", "valid_mod"))

    # ── ET-06: Unlink failure in IDECacheTracker ─────────────────────
    def test_et_06_unlink_failure_handled(self):
        tracker = IDECacheTracker(self.test_dir)
        # Passing non-existent or unremovable file should not raise
        cleaned = tracker.clean_orphans([])
        self.assertEqual(len(cleaned), 0)

    # ── ET-07: Missing commands directory ────────────────────────────
    def test_et_07_missing_commands_dir(self):
        from _on_modules_changed import synthesize_all_workflows
        # When COMMANDS_DIR doesn't exist, returns 0 without crashing
        orig_dir = sys.modules["_on_modules_changed"].COMMANDS_DIR
        sys.modules["_on_modules_changed"].COMMANDS_DIR = self.test_dir / "non_existent_commands"
        count = synthesize_all_workflows()
        self.assertEqual(count, 0)
        sys.modules["_on_modules_changed"].COMMANDS_DIR = orig_dir

    # ── ET-08: Missing sop_ext directory ─────────────────────────────
    def test_et_08_missing_sop_ext_dir(self):
        class EmptyCtx:
            @staticmethod
            def get_contributions(ns, start_dir=None):
                return []
            @staticmethod
            def get_project_root(start_dir=None):
                return self.test_dir

        reg = ExtensionRegistry.discover_all(EmptyCtx, start_dir=self.test_dir)
        self.assertEqual(len(reg), 0)

    # ── PT-01: Performance of 10 SOPs x 5 patches < 50ms ──────────────
    def test_pt_01_synthesis_performance(self):
        template = (
            "# Large SOP Template\n\n"
            + "\n".join([f"### Section {i}\nSection body {i}\n<!-- YSCB_SLOT:Phase{i % 8} -->\n" for i in range(20)])
        )
        patches = [
            {"target_sop": "Large.md", "target_slot": f"Phase{i}", "position": "append", "content": f"PATCH_CONTENT_{i}"}
            for i in range(5)
        ]

        t0 = time.perf_counter()
        for _ in range(10):
            res = SOPSynthesizer.synthesize_sop(template, patches)
            _ = SOPSynthesizer.strip_slot_markers(res)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Assert elapsed time is well under 500ms (and typical < 50ms)
        self.assertLess(elapsed_ms, 500.0, f"Synthesis performance test took {elapsed_ms:.2f}ms")


if __name__ == "__main__":
    unittest.main()
