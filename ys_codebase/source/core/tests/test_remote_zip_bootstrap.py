"""
Official test suite for Core Microkernel Remote Zip Bootstrap & Ingestion.
Verifies FT-04, FT-05, FT-06, ET-01, ET-03.
"""
import os
import json
import zipfile
import shutil
import tempfile
from core import uri
from core.engine import AtomicEngine
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
import yscb as yscb_mod

@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
class TestRemoteZipBootstrap(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.engine = AtomicEngine()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def _create_dummy_zip(self, name: str, version: str) -> str:
        """Creates a standalone valid module zip archive."""
        zip_path = os.path.join(self.temp_dir, f"{name}-{version}.zip")
        manifest = {
            "name": name,
            "version": version,
            "description": f"Dummy {name}",
            "entry": "scripts/cli.py",
            "dependencies": {}
        }
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("scripts/cli.py", "def main(): return 0\n")
            zf.writestr("config.project.json", json.dumps({"test_key": "val"}, indent=2))
        return zip_path

    def test_corrupted_zip_fails_safely(self):
        """T-01 實質化：驗證損毀 Zip 傳入 fetch_and_extract_zip 及 engine.act_download 必定拋出 RuntimeError 且不殘留損毀檔案。"""
        from unittest.mock import patch, MagicMock
        from core.installer import fetch_and_extract_zip

        bad_zip = os.path.join(self.temp_dir, "bad.zip")
        with open(bad_zip, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_HEADER_DATA_12345")

        self.assertFalse(zipfile.is_zipfile(bad_zip))
        dest = os.path.join(self.temp_dir, "corrupted_extract")
        with self.assertRaises(RuntimeError):
            fetch_and_extract_zip(bad_zip, dest)

        # 亦驗證透過 HTTP Provider 下載損毀 Zip 時 engine.act_download 攔截並拋出 RuntimeError，且 mirror 不殘留
        class CorruptedResp:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"CORRUPTED_NON_ZIP_BYTES_PAYLOAD"

        with patch("urllib.request.urlopen", return_value=CorruptedResp()):
            with self.assertRaises(RuntimeError):
                self.engine.act_download("corrupt_mod", "1.0.0.0", "https://example.com/release")

        self.assertFalse(uri.exists("module.mirror://corrupt_mod/1.0.0.0.zip"))
        self.mark_passed()


    def test_local_provider_isomorphic_zip_ingestion(self):
        """FT-05 & ET-03: Verify downloading and ingesting module from local zip provider."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        os.makedirs(os.path.join(prov_dir, "mock_mod"), exist_ok=True)
        
        zip_path = os.path.join(prov_dir, "mock_mod", "1.0.0.0.zip")
        manifest = {
            "name": "mock_mod",
            "version": "1.0.0.0",
            "description": "Mock Mod",
            "entry": "scripts/cli.py"
        }
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("scripts/cli.py", "def main(): return 0\n")
            
        idx_path = os.path.join(prov_dir, "mock_mod", "index.json")
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump({"name": "mock_mod", "versions": ["1.0.0.0"]}, f, indent=2)

        # Ingest into mirror using act_download (single-file zip)
        dest_mirror = self.engine.act_download("mock_mod", "1.0.0.0", prov_dir)
        self.assertTrue(uri.exists(dest_mirror))
        real_zip = uri.resolve(dest_mirror)
        with zipfile.ZipFile(real_zip, "r") as zf:
            self.assertIn("manifest.json", zf.namelist())
            self.assertIn("scripts/cli.py", zf.namelist())
        self.mark_passed()

    def test_modules_pure_code_after_reload(self):
        """FT-06: Verify config.*.json templates are stripped from modules/ upon reload."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        os.makedirs(os.path.join(prov_dir, "pure_mod"), exist_ok=True)
        zip_path = os.path.join(prov_dir, "pure_mod", "1.0.0.0.zip")
        manifest = {
            "name": "pure_mod",
            "version": "1.0.0.0",
            "entry": "scripts/cli.py"
        }
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("scripts/cli.py", "def main(): return 0\n")
            zf.writestr("configurable/config.project.json", json.dumps({"foo": "bar"}, indent=2))
            
        self.engine.act_download("pure_mod", "1.0.0.0", prov_dir)
        self.engine.act_register("pure_mod", "1.0.0.0", prov_dir)
        self.engine.act_reload()
        
        # Check module root
        mod_root = uri.resolve("module://pure_mod")
        self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.project.json")))
        self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.local.json")))
        self.assertFalse(os.path.isdir(os.path.join(mod_root, "configurable")))
        self.mark_passed()

        
        # Clean up
        self.engine.act_unregister("pure_mod")
        uri.rmtree("module://pure_mod")
        uri.rmtree("module.mirror://pure_mod")

    def test_zip_slip_vulnerability_blocked_on_reload(self):
        """Security: Verify malicious Zip with path traversal (Zip Slip) is blocked on reload."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        os.makedirs(os.path.join(prov_dir, "evil_mod"), exist_ok=True)
        zip_path = os.path.join(prov_dir, "evil_mod", "1.0.0.0.zip")
        
        # Create malicious zip with ../../ path traversal
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "evil_mod", "version": "1.0.0.0"}, indent=2))
            zf.writestr("../../evil_escape.txt", "MALICIOUS PAYLOAD OUTSIDE DESTINATION")
            
        self.engine.act_download("evil_mod", "1.0.0.0", prov_dir)
        self.engine.act_register("evil_mod", "1.0.0.0", prov_dir)
        
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.engine.act_reload()
            self.assertIn("Zip Slip vulnerability detected", str(ctx.exception))
        finally:
            self.engine.act_unregister("evil_mod")
            uri.rmtree("module.mirror://evil_mod")
        self.mark_passed()

    def test_zip_slip_blocked_on_host_fetch_and_extract(self):
        """Security: Verify yscb._fetch_and_extract_zip blocks Zip Slip."""
        self.assertIsNotNone(yscb_mod)
        zip_path = os.path.join(self.temp_dir, "evil_host.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "evil_host"}, indent=2))
            zf.writestr("../../evil_host_escape.txt", "MALICIOUS")
            
        target_dir = os.path.join(self.temp_dir, "dest_host")
        with self.assertRaises(RuntimeError) as ctx:
            yscb_mod._fetch_and_extract_zip(zip_path, target_dir)
            
        self.assertIn("Zip Slip vulnerability detected", str(ctx.exception))

        # Test invalid source raises FileNotFoundError (FR-07)
        with self.assertRaises(FileNotFoundError):
            yscb_mod._fetch_and_extract_zip("non_existent_source_12345.xyz", target_dir)

        self.mark_passed()

    def test_installer_onboarding_guide_output(self):
        """FT-04, EC-01: Verify Installer._print_onboarding_guide outputs Next Steps when onboarding is defined."""
        import io
        from contextlib import redirect_stdout
        from core.installer import Installer

        inst = Installer()
        mod_name = "mock_onboard_mod"
        mod_dir = uri.resolve(f"module://{mod_name}")
        os.makedirs(mod_dir, exist_ok=True)
        try:
            with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "name": mod_name,
                        "version": "1.0.0.0",
                        "entry": "scripts/cli.py",
                        "dependencies": {"core": ">=1.0.0"},
                        "onboarding": [
                            "Run init: python yscb.py mock_onboard_mod init",
                            "Check status: python yscb.py mock_onboard_mod status",
                        ],
                    },
                    f,
                )
            with open(os.path.join(mod_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("# Mock Onboard README\n")

            buf = io.StringIO()
            with redirect_stdout(buf):
                inst._print_onboarding_guide(mod_name)
            out = buf.getvalue()
            self.assertIn(f"[*] Next Steps for '{mod_name}':", out)
            self.assertIn("1. Run init: python yscb.py mock_onboard_mod init", out)
            self.assertIn(f".modules/{mod_name}/README.md", out)

            # EC-01: Module without onboarding field produces no output
            with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"name": mod_name, "version": "1.0.0.0"}, f)
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                inst._print_onboarding_guide(mod_name)
            self.assertEqual(buf2.getvalue(), "")
        finally:
            if os.path.exists(mod_dir):
                shutil.rmtree(mod_dir, ignore_errors=True)
        self.mark_passed()
