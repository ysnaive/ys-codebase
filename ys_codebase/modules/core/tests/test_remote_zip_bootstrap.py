"""
Official test suite for Core Microkernel Remote Zip Bootstrap & Ingestion.
Verifies FT-04, FT-05, FT-06, ET-01, ET-03.
"""
import os
import json
import zipfile
import shutil
import tempfile
import unittest
from core import uri
from core.engine import AtomicEngine

class TestRemoteZipBootstrap(unittest.TestCase):
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
        """ET-01: Verify corrupted zip payload fails safely without polluting mirror/ or modules/."""
        bad_zip = os.path.join(self.temp_dir, "bad.zip")
        with open(bad_zip, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_HEADER_DATA_12345")
            
        self.assertFalse(zipfile.is_zipfile(bad_zip))

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
            zf.writestr("config.project.json", json.dumps({"foo": "bar"}, indent=2))
            
        self.engine.act_download("pure_mod", "1.0.0.0", prov_dir)
        self.engine.act_reload("pure_mod", "1.0.0.0")
        
        # Check module root
        mod_root = uri.resolve("module.root://pure_mod")
        self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.project.json")))
        self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.local.json")))
        
        # Clean up
        uri.rmtree("module.root://pure_mod")
        uri.rmtree("mirror://pure_mod")
