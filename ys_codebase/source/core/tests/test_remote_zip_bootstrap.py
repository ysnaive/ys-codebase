"""
Official test suite for Core Microkernel Remote Zip Bootstrap & Ingestion.
"""
import io
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch

from core import uri, vfs
from core.engine import AtomicEngine, compute_file_sha256, package_local_source_if_exact_match
from core.installer import Installer, fetch_and_extract_zip
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement
from tests import create_provider_release_zip
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

    def test_corrupted_zip_fails_safely(self):
        """驗證損毀 Zip 傳入 fetch_and_extract_zip 及 engine.act_download 必定拋出 RuntimeError 且不殘留損毀檔案。"""
        bad_zip = os.path.join(self.temp_dir, "bad.zip")
        with open(bad_zip, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_HEADER_DATA_12345")

        self.assertFalse(zipfile.is_zipfile(bad_zip))
        dest = os.path.join(self.temp_dir, "corrupted_extract")
        with self.assertRaises(RuntimeError):
            fetch_and_extract_zip(bad_zip, dest)

        class CorruptedResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"CORRUPTED_NON_ZIP_BYTES_PAYLOAD"

        with patch("urllib.request.urlopen", return_value=CorruptedResp()):
            with self.assertRaises(RuntimeError):
                self.engine.act_download("corrupt_mod", "1.0.0.0", "https://example.com/release")

        self.assertFalse(vfs.exists("module.mirror://corrupt_mod/1.0.0.0.zip"))
        self.mark_passed()

    def test_local_provider_isomorphic_zip_ingestion(self):
        """Verify downloading and ingesting module from local zip provider."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        create_provider_release_zip(prov_dir, "mock_mod", "1.0.0.0")

        try:
            dest_mirror = self.engine.act_download("mock_mod", "1.0.0.0", prov_dir)
            self.assertTrue(vfs.exists(dest_mirror))
            real_zip = uri.resolve(dest_mirror)
            with zipfile.ZipFile(real_zip, "r") as zf:
                self.assertIn("manifest.json", zf.namelist())
                self.assertIn("scripts/cli.py", zf.namelist())
        finally:
            if vfs.exists("module.mirror://mock_mod"):
                vfs.rmtree("module.mirror://mock_mod", ignore_errors=True)
        self.mark_passed()

    def test_modules_pure_code_after_reload(self):
        """Verify config.*.json templates are stripped from modules/ upon reload."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        create_provider_release_zip(
            prov_dir,
            "pure_mod",
            "1.0.0.0",
            extra_files={
                "configurable/config.project.json": json.dumps({"foo": "bar"}, indent=2),
            },
        )

        try:
            self.engine.act_download("pure_mod", "1.0.0.0", prov_dir)
            self.engine.act_register("pure_mod", "1.0.0.0", prov_dir)
            self.engine.act_reload()

            mod_root = uri.resolve("module://pure_mod")
            self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.project.json")))
            self.assertFalse(os.path.isfile(os.path.join(mod_root, "config.local.json")))
            self.assertFalse(os.path.isdir(os.path.join(mod_root, "configurable")))
        finally:
            self.engine.act_unregister("pure_mod")
            for u in ("module://pure_mod", "module.mirror://pure_mod", "config://pure_mod"):
                if vfs.exists(u):
                    vfs.rmtree(u, ignore_errors=True)
        self.mark_passed()

    def test_zip_slip_vulnerability_blocked_on_reload(self):
        """Verify malicious Zip with path traversal (Zip Slip) is blocked on reload."""
        prov_dir = os.path.join(self.temp_dir, "provider")
        create_provider_release_zip(
            prov_dir,
            "evil_mod",
            "1.0.0.0",
            extra_files={"../../evil_escape.txt": "MALICIOUS PAYLOAD OUTSIDE DESTINATION"},
        )

        self.engine.act_download("evil_mod", "1.0.0.0", prov_dir)
        self.engine.act_register("evil_mod", "1.0.0.0", prov_dir)

        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.engine.act_reload()
            self.assertIn("Zip Slip vulnerability detected", str(ctx.exception))
        finally:
            self.engine.act_unregister("evil_mod")
            if vfs.exists("module.mirror://evil_mod"):
                vfs.rmtree("module.mirror://evil_mod", ignore_errors=True)
        self.mark_passed()

    def test_zip_slip_blocked_on_host_fetch_and_extract(self):
        """Verify yscb._fetch_and_extract_zip blocks Zip Slip and missing source files."""
        zip_path = os.path.join(self.temp_dir, "evil_host.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"name": "evil_host"}, indent=2))
            zf.writestr("../../evil_host_escape.txt", "MALICIOUS")

        target_dir = os.path.join(self.temp_dir, "dest_host")
        with self.assertRaises(RuntimeError) as ctx:
            yscb_mod._fetch_and_extract_zip(zip_path, target_dir)

        self.assertIn("Zip Slip vulnerability detected", str(ctx.exception))

        with self.assertRaises(FileNotFoundError):
            yscb_mod._fetch_and_extract_zip("non_existent_source_12345.xyz", target_dir)

        self.mark_passed()

    def test_installer_onboarding_guide_output(self):
        """Verify Installer._print_onboarding_guide outputs Next Steps when onboarding is defined."""
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

    def test_sha256_verification_and_deterministic_zip_governance(self):
        """驗證決定性 Zip 打包一致性、SHA-256 缺失/不符攔截、--ignore-sha256 繞過與 @build 豁免。"""
        src_a = os.path.join(self.temp_dir, "det_src_a")
        src_b = os.path.join(self.temp_dir, "det_src_b")
        for s_dir, eol in ((src_a, "\n"), (src_b, "\r\n")):
            os.makedirs(os.path.join(s_dir, "scripts"), exist_ok=True)
            with open(os.path.join(s_dir, "manifest.json"), "wb") as f:
                f.write(f'{{"name": "det_mod", "version": "1.0.0.0", "entry": "scripts/cli.py"}}{eol}'.encode("utf-8"))
            with open(os.path.join(s_dir, "scripts", "cli.py"), "wb") as f:
                f.write(f"def main():{eol}    return 0{eol}".encode("utf-8"))

        zip_eng = os.path.join(self.temp_dir, "det_eng.zip")
        zip_host = os.path.join(self.temp_dir, "det_host.zip")
        self.assertTrue(package_local_source_if_exact_match(src_a, "1.0.0.0", zip_eng))
        self.assertTrue(yscb_mod._package_source_to_zip_if_exact_version(src_b, "1.0.0.0", zip_host))
        self.assertEqual(compute_file_sha256(zip_eng), compute_file_sha256(zip_host))

        prov_dir = os.path.join(self.temp_dir, "sha_prov")
        mod_dir = os.path.join(prov_dir, "sec_mod")
        create_provider_release_zip(prov_dir, "sec_mod", "1.0.0.0", compute_sha256=False)

        try:
            with self.assertRaises(RuntimeError) as ctx_missing:
                self.engine.act_download("sec_mod", "1.0.0.0", prov_dir)
            self.assertIn("Missing SHA-256 checksum", str(ctx_missing.exception))
            self.assertFalse(vfs.exists("module.mirror://sec_mod/1.0.0.0.zip"))

            uri_bypass = self.engine.act_download("sec_mod", "1.0.0.0", prov_dir, ignore_sha256=True)
            self.assertTrue(vfs.exists(uri_bypass))
            vfs.remove(uri_bypass)

            with open(os.path.join(mod_dir, "index.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "name": "sec_mod",
                        "versions": ["1.0.0.0"],
                        "releases": {"1.0.0.0": {"sha256": "0" * 64}},
                    },
                    f,
                )
            with self.assertRaises(RuntimeError) as ctx_mismatch:
                self.engine.act_download("sec_mod", "1.0.0.0", prov_dir)
            self.assertIn("SHA-256 checksum mismatch", str(ctx_mismatch.exception))
            self.assertFalse(vfs.exists("module.mirror://sec_mod/1.0.0.0.zip"))

            bld_dir = os.path.join(prov_dir, "build", "sec_mod")
            os.makedirs(bld_dir, exist_ok=True)
            shutil.copy2(zip_eng, os.path.join(bld_dir, "1.0.0.build.zip"))
            uri_bld = self.engine.act_download("sec_mod", "1.0.0.build", prov_dir, ignore_sha256=False)
            self.assertTrue(vfs.exists(uri_bld))
        finally:
            if vfs.exists("module.mirror://sec_mod"):
                vfs.rmtree("module.mirror://sec_mod", ignore_errors=True)
        self.mark_passed()
