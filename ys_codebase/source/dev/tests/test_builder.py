"""
Official test suite for dev.builder.Builder with Full Zip Single-File packaging.
Uses mock modules to eliminate side-effects and official module coupling.
"""
import importlib.util
import os
import shutil
import zipfile
from unittest.mock import patch
from dev.testing import YSCBTestCase, require, Requirement
from dev.builder import Builder, compute_file_sha256, _create_module_archive_atomic
from core import uri, vfs


@require(Requirement.ENV)
class TestDevBuilder(YSCBTestCase):

    def setUp(self):
        super().setUp()
        self.builder = Builder()

    def tearDown(self):
        for scheme in ("module.source://", "module.build://", "module.release://"):
            if vfs.exists(scheme):
                root = uri.resolve(scheme)
                if os.path.isdir(root):
                    for item in os.listdir(root):
                        if item.startswith("mock_"):
                            shutil.rmtree(os.path.join(root, item), ignore_errors=True)
        super().tearDown()

    def test_clean_build_mock_module(self):
        """Verify dev build of mock module outputs to <ver>.build.zip and retains tests/."""
        self.create_mock_source_module("mock_bld_pkg", "1.2.3.4")
        passed, msg = self.builder.build_module("mock_bld_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")
        zip_uri = "module.build://mock_bld_pkg/1.2.3.build.zip"
        self.assertTrue(vfs.exists(zip_uri))

        real_zip = uri.resolve(zip_uri)
        with zipfile.ZipFile(real_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            self.assertIn("scripts/cli.py", namelist)
            self.assertTrue(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_package_release_excludes_tests(self):
        """Verify package_release of mock module outputs pure release zip excluding tests/."""
        self.create_mock_source_module("mock_rel_pkg", "2.0.0.1")
        passed, msg = self.builder.build_module("mock_rel_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")
        self.assertTrue(vfs.exists("module.build://mock_rel_pkg/2.0.0.build.zip"))

        ok_rel, msg_rel = self.builder.package_release("mock_rel_pkg", "2.0.0.1")
        self.assertTrue(ok_rel, f"Release packager failed: {msg_rel}")
        rel_zip_uri = "module.release://mock_rel_pkg/2.0.0.1.zip"
        self.assertTrue(vfs.exists(rel_zip_uri))

        real_rel_zip = uri.resolve(rel_zip_uri)
        with zipfile.ZipFile(real_rel_zip, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            self.assertFalse(any(f.startswith("tests/") for f in namelist))
        self.mark_passed()

    def test_package_release_respects_custom_yscbignore(self):
        """Verify .yscbignore custom patterns and comments are honored during package_release."""
        self.create_mock_source_module(
            "mock_ignore_pkg",
            "1.0.0.0",
            files={
                ".yscbignore": "# Custom ignore rules\nignored_dir/\n*.secret.txt\n",
                "ignored_dir/hidden.py": "HIDDEN = True\n",
                "top.secret.txt": "classified\n",
                "kept_notes.txt": "public notes\n",
            },
        )
        ok, msg = self.builder.package_release("mock_ignore_pkg", "1.0.0.0")
        self.assertTrue(ok, f"package_release failed: {msg}")
        rel_zip = uri.resolve("module.release://mock_ignore_pkg/1.0.0.0.zip")
        with zipfile.ZipFile(rel_zip, "r") as zf:
            names = zf.namelist()
            self.assertIn("kept_notes.txt", names)
            self.assertNotIn("top.secret.txt", names)
            self.assertNotIn(".yscbignore", names)
            self.assertFalse(any(n.startswith("ignored_dir/") for n in names))
        self.mark_passed()

    def test_build_and_package_nonexistent_or_noncompliant_module(self):
        """Verify build_module and package_release reject nonexistent or check-failing modules."""
        ok_b, msg_b = self.builder.build_module("mock_nonexistent_mod")
        self.assertFalse(ok_b)
        self.assertIn("Source module not found", msg_b)

        ok_p, msg_p = self.builder.package_release("mock_nonexistent_mod", "1.0.0.0")
        self.assertFalse(ok_p)
        self.assertIn("Source module not found", msg_p)

        self.create_mock_source_module(
            "mock_noncompliant_mod",
            "1.0.0.0",
            files={
                "manifest.json": '{"name": "mismatched_name", "version": "1.0.0.0", "entry": "scripts/cli.py", "dependencies": ["core"]}'
            },
        )
        ok_bad, msg_bad = self.builder.build_module("mock_noncompliant_mod")
        self.assertFalse(ok_bad)
        self.assertIn("Check failed for module 'mock_noncompliant_mod'", msg_bad)
        self.mark_passed()

    def test_revision_purge_deletes_old_zip(self):
        """Verify 3-Revision sliding window and cross-triplet convergence on mock module."""
        rel_uri = "module.release://mock_purge_pkg"
        if vfs.exists(rel_uri):
            shutil.rmtree(uri.resolve(rel_uri), ignore_errors=True)
        self.create_mock_source_module("mock_purge_pkg", "1.0.0.1")
        self.builder.package_release("mock_purge_pkg", "1.0.0.1")
        self.builder.package_release("mock_purge_pkg", "1.0.0.2")
        self.builder.package_release("mock_purge_pkg", "1.0.0.3")

        zip_1 = uri.resolve("module.release://mock_purge_pkg/1.0.0.1.zip")
        zip_2 = uri.resolve("module.release://mock_purge_pkg/1.0.0.2.zip")
        zip_3 = uri.resolve("module.release://mock_purge_pkg/1.0.0.3.zip")
        self.assertTrue(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))

        ok4, msg4 = self.builder.package_release("mock_purge_pkg", "1.0.0.4")
        self.assertTrue(ok4, f"Package 1.0.0.4 failed: {msg4}")
        zip_4 = uri.resolve("module.release://mock_purge_pkg/1.0.0.4.zip")
        self.assertTrue(os.path.isfile(zip_4))
        self.assertFalse(os.path.isfile(zip_1))
        self.assertTrue(os.path.isfile(zip_2))
        self.assertTrue(os.path.isfile(zip_3))

        self.builder.package_release("mock_purge_pkg", "1.0.1.0")
        self.assertFalse(os.path.isfile(zip_2))
        self.assertFalse(os.path.isfile(zip_3))
        self.assertTrue(os.path.isfile(zip_4))
        self.assertTrue(os.path.isfile(uri.resolve("module.release://mock_purge_pkg/1.0.1.0.zip")))

        idx = vfs.read_json("module.release://mock_purge_pkg/index.json")
        self.assertEqual(idx.get("versions", []), ["1.0.0.4", "1.0.1.0"])
        releases_ledger = idx.get("releases", {})
        self.assertEqual(releases_ledger.get("1.0.0.1", {}).get("status"), "pruned")
        self.assertEqual(releases_ledger.get("1.0.0.2", {}).get("status"), "pruned")
        self.assertEqual(releases_ledger.get("1.0.0.3", {}).get("status"), "pruned")
        self.assertEqual(releases_ledger.get("1.0.0.4", {}).get("status"), "active")
        self.assertEqual(releases_ledger.get("1.0.1.0", {}).get("status"), "active")
        self.mark_passed()

    def test_builder_generates_and_updates_index_json(self):
        """Verify builder automatically creates and updates build/{module}/index.json."""
        self.create_mock_source_module("mock_idx_pkg", "3.1.2.0")
        passed, msg = self.builder.build_module("mock_idx_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")

        index_uri = "module.build://mock_idx_pkg/index.json"
        self.assertTrue(vfs.exists(index_uri))
        index_data = vfs.read_json(index_uri)
        self.assertEqual(index_data.get("name"), "mock_idx_pkg")
        self.assertIn("3.1.2.build", index_data.get("versions", []))
        self.mark_passed()

    def test_build_module_clean_flag_behavior(self):
        """Verify build_module respects clean flag (clean=False preserves files, clean=True clears)."""
        self.create_mock_source_module("mock_clean_pkg", "1.0.0.0")
        passed, msg = self.builder.build_module("mock_clean_pkg", clean=True)
        self.assertTrue(passed, f"Build failed: {msg}")

        bld_dir = uri.resolve("module.build://mock_clean_pkg")
        extra_file = os.path.join(bld_dir, "custom_preserved.txt")
        with open(extra_file, "w", encoding="utf-8") as f:
            f.write("preserve me")

        passed2, msg2 = self.builder.build_module("mock_clean_pkg", clean=False)
        self.assertTrue(passed2, f"Build failed: {msg2}")
        self.assertTrue(os.path.isfile(extra_file), "Expected extra_file to be preserved when clean=False")

        passed3, msg3 = self.builder.build_module("mock_clean_pkg", clean=True)
        self.assertTrue(passed3, f"Build failed: {msg3}")
        self.assertFalse(os.path.isfile(extra_file), "Expected extra_file to be wiped when clean=True")
        self.mark_passed()

    def test_deterministic_zip_packaging_and_release_sha256_index(self):
        """Verify deterministic zip packaging across repeated builds and CRLF vs LF inputs, and sha256 in release index.json."""
        self.create_mock_source_module("mock_det_pkg", "1.0.0.1")
        src_dir = uri.resolve("module.source://mock_det_pkg")
        cli_file = os.path.join(src_dir, "scripts", "cli.py")
        readme_file = os.path.join(src_dir, "README.md")

        with open(cli_file, "wb") as f:
            f.write(b"def hello(cmd_bags):\n    return 0\n")
        with open(readme_file, "wb") as f:
            f.write(b"# Mock Module\nLine 2\n")

        ok1, msg1 = self.builder.package_release("mock_det_pkg", "1.0.0.1")
        self.assertTrue(ok1, f"Package 1 failed: {msg1}")
        rel_zip = uri.resolve("module.release://mock_det_pkg/1.0.0.1.zip")
        sha_lf_1 = compute_file_sha256(rel_zip)

        os.utime(cli_file, (1600000000, 1600000000))
        os.utime(readme_file, (1600000100, 1600000100))
        ok2, msg2 = self.builder.package_release("mock_det_pkg", "1.0.0.1")
        self.assertTrue(ok2, f"Package 2 failed: {msg2}")
        sha_lf_2 = compute_file_sha256(rel_zip)
        self.assertEqual(sha_lf_1, sha_lf_2)

        with open(cli_file, "wb") as f:
            f.write(b"def hello(cmd_bags):\r\n    return 0\r\n")
        with open(readme_file, "wb") as f:
            f.write(b"# Mock Module\r\nLine 2\r\n")
        ok3, msg3 = self.builder.package_release("mock_det_pkg", "1.0.0.1")
        self.assertTrue(ok3, f"Package 3 failed: {msg3}")
        sha_crlf = compute_file_sha256(rel_zip)
        self.assertEqual(sha_lf_1, sha_crlf)

        with zipfile.ZipFile(rel_zip, "r") as zf:
            infolist = zf.infolist()
            self.assertEqual([zi.filename for zi in infolist], sorted(zi.filename for zi in infolist))
            for zi in infolist:
                self.assertEqual(zi.date_time, (2020, 1, 1, 0, 0, 0))
                self.assertEqual(zi.external_attr, (0o644 & 0xFFFF) << 16)

        idx = vfs.read_json("module.release://mock_det_pkg/index.json")
        rel_meta = idx.get("releases", {}).get("1.0.0.1", {})
        self.assertEqual(rel_meta.get("sha256"), sha_lf_1)
        self.mark_passed()

    def test_archive_non_utf8_text_fallback_and_binary_preservation(self):
        """Verify non-UTF8 .txt bytes fall back to raw payload and .bin CRLF bytes are preserved untouched."""
        self.create_mock_source_module("mock_bin_pkg", "1.0.0.0")
        src_dir = uri.resolve("module.source://mock_bin_pkg")
        raw_non_utf8 = b"\xff\xfe\xfa\r\n"
        raw_binary = b"line1\r\nline2\x00\xff"
        with open(os.path.join(src_dir, "latin_raw.txt"), "wb") as f:
            f.write(raw_non_utf8)
        with open(os.path.join(src_dir, "payload.bin"), "wb") as f:
            f.write(raw_binary)

        ok, msg = self.builder.package_release("mock_bin_pkg", "1.0.0.0")
        self.assertTrue(ok, f"Package failed: {msg}")
        rel_zip = uri.resolve("module.release://mock_bin_pkg/1.0.0.0.zip")
        with zipfile.ZipFile(rel_zip, "r") as zf:
            self.assertEqual(zf.read("latin_raw.txt"), raw_non_utf8)
            self.assertEqual(zf.read("payload.bin"), raw_binary)
        self.mark_passed()

    def test_atomic_archive_replaces_without_pre_remove(self):
        """Verify _create_module_archive_atomic overwrites existing archive via os.replace without pre-removing target_zip_path."""
        self.create_mock_source_module("mock_det_pkg", "1.0.0.1")
        src_dir = uri.resolve("module.source://mock_det_pkg")
        out_dir = uri.resolve("module.build://mock_det_pkg")
        os.makedirs(out_dir, exist_ok=True)
        target_zip = os.path.join(out_dir, "atomic_test.zip")
        with open(target_zip, "wb") as f:
            f.write(b"old_zip_bytes")

        orig_remove = os.remove
        removed_paths = []

        def spy_remove(p):
            removed_paths.append(os.path.abspath(p))
            return orig_remove(p)

        with patch("os.remove", side_effect=spy_remove):
            cnt = _create_module_archive_atomic(
                source_dir=src_dir,
                target_zip_path=target_zip,
                ignores=[],
                manifest_data={"name": "mock_det_pkg", "version": "1.0.0.1"},
                target_version="1.0.0.1",
            )
        self.assertGreater(cnt, 0)
        self.assertTrue(os.path.isfile(target_zip))
        self.assertNotIn(os.path.abspath(target_zip), removed_paths)
        self.mark_passed()

    def test_build_all_and_cli_build_commands(self):
        """Verify Builder.build_all and scripts/cli.py build single-module and --all modes."""
        self.create_mock_source_module("mock_cli_bld_pkg", "1.0.0.0")
        all_res = self.builder.build_all(clean=True)
        self.assertIn("mock_cli_bld_pkg", all_res)
        self.assertTrue(all_res["mock_cli_bld_pkg"][0])

        cli_path = uri.resolve("module.source://dev/scripts/cli.py")
        spec = importlib.util.spec_from_file_location("dev_cli_builder_test", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_mod)

        self.assertEqual(cli_mod.build(["mock_cli_bld_pkg"]), 0)
        self.assertEqual(cli_mod.build(["mock_nonexistent_cli_pkg"]), 1)
        self.assertEqual(cli_mod.build(["--all"]), 0)
        self.mark_passed()
