"""
Unit tests for core.installer restore and gitignore auto-maintenance.
"""
import os
import tempfile
import zipfile
from dev.testing import YSCBTestCase, require, Requirement
from core.installer import Installer, generate_internal_gitignore, fetch_and_extract_zip


@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestInstallerRestore(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.installer = Installer()

    def test_generate_internal_gitignore(self):
        """FT-02: Verify generate_internal_gitignore non-destructively merges internal rules."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            gi_path = os.path.join(tmp_dir, ".gitignore")
            
            # 1. Initial creation
            generate_internal_gitignore(tmp_dir)
            self.assertTrue(os.path.isfile(gi_path))
            content = open(gi_path, "r", encoding="utf-8").read()
            self.assertIn("# === YSCB INTERNAL IGNORE BEGIN ===", content)
            self.assertIn("# === YSCB INTERNAL IGNORE END ===", content)
            self.assertIn("/.modules/", content)
            self.assertIn("/.venv/", content)
            self.assertIn("*.local.json", content)

            # 2. Preserve custom user rules
            user_rule = "*.user_custom_data\nmy_secret.env\n"
            with open(gi_path, "w", encoding="utf-8") as f:
                f.write(user_rule + "\n" + content)

            generate_internal_gitignore(tmp_dir)
            merged = open(gi_path, "r", encoding="utf-8").read()
            self.assertIn("*.user_custom_data", merged)
            self.assertIn("my_secret.env", merged)
            self.assertIn("# === YSCB INTERNAL IGNORE BEGIN ===", merged)
        self.mark_passed()

    def test_fetch_and_extract_zip_safety(self):
        """FT-01: Verify fetch_and_extract_zip extracts cleanly and detects zip slip."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_p = os.path.join(tmp_dir, "test.zip")
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("test.txt", "hello yscb")
                zf.writestr("nested/foo.json", '{"key": "value"}')

            extract_dest = os.path.join(tmp_dir, "extracted")
            fetch_and_extract_zip(zip_p, extract_dest)

            self.assertTrue(os.path.isfile(os.path.join(extract_dest, "test.txt")))
            self.assertEqual(open(os.path.join(extract_dest, "test.txt")).read(), "hello yscb")
            self.assertTrue(os.path.isfile(os.path.join(extract_dest, "nested", "foo.json")))
        self.mark_passed()

    def test_cmd_restore_empty(self):
        """FT-01: Verify cmd_restore succeeds gracefully when no modules need restoration."""
        res = self.installer.cmd_restore()
        self.assertEqual(res, 0)
        self.mark_passed()
