"""
Unit and edge-case tests for module:gdrive-support atomic API, config, and sandbox transport.

100% locked to LocalSandboxTransport, config.py, and local CLI/SDK logic.
No external Google Drive API calls or user credentials are required or tested here.
"""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

_test_dir = Path(__file__).resolve().parent
_pkg_root = _test_dir.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from core.commands import CmdBags, CmdOption
from dev.testing import YSCBTestCase
from dev.testing.requirement import Requirement, require

from gdrive_support import (
    GDriveConfig,
    GDriveConfigError,
    GDriveFileNotFoundError,
    GDrivePathError,
    GDriveUnsupportedMimeError,
    LocalSandboxTransport,
    collect_space_local_files,
    collect_space_local_files_with_stat,
    is_sensitive_credential_path,
    load_gdrive_config,
)

_cli_spec = importlib.util.spec_from_file_location(
    "_gdrive_support_cli", _pkg_root / "scripts" / "cli.py"
)
assert _cli_spec is not None and _cli_spec.loader is not None
cli = importlib.util.module_from_spec(_cli_spec)
_cli_spec.loader.exec_module(cli)


class _FakeFileSpaceManager:
    """Deterministic fake FileSpaceManager simulating single-root inc_root stripping."""

    def __init__(self, files_by_space):
        self._files_by_space = files_by_space

    def iter_space_files(self, space_name):
        return iter(self._files_by_space.get(space_name, []))


class TestGDriveAtomicApiAndConfig(YSCBTestCase):
    """Test suite for config.py, LocalSandboxTransport, and atomic CLI commands."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp_root = Path(tempfile.mkdtemp(prefix="yscb_gdrive_sub01_")).resolve()
        self.proj_dir = self.tmp_root / "project"
        self.sandbox_dir = self.tmp_root / "sandbox_cloud"
        self.proj_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_default_config_and_lazy_sdk_exports(self) -> None:
        """Verify default configuration enforces repo_sync.enable=False, auto_sync=False, and active_branch='main'."""
        cfg = load_gdrive_config(
            config_override={
                "repo_sync": {"enable": False, "auto_sync": False},
                "credentials_uri": "",
                "token_uri": "",
            },
            project_root=self.proj_dir,
            space_include_roots={},
        )
        default_dataclass_cfg = GDriveConfig()
        self.assertEqual(
            default_dataclass_cfg.credentials_uri,
            "config.local://gdrive-support/credentials.json",
        )
        self.assertEqual(
            default_dataclass_cfg.token_uri,
            "config.local://gdrive-support/token.json",
        )
        self.assertEqual(
            cfg.credentials_uri,
            "config.local://gdrive-support/credentials.json",
        )
        self.assertEqual(
            cfg.token_uri,
            "config.local://gdrive-support/token.json",
        )
        self.assertFalse(cfg.repo_sync_enabled)
        self.assertEqual(cfg.repo_sync_root, "repo")
        self.assertIsNotNone(cfg.repo_sync)
        self.assertFalse(cfg.repo_sync.enable)
        self.assertEqual(cfg.repo_sync.repo_sync_root, "repo")
        self.assertFalse(cfg.auto_sync)
        self.assertEqual(cfg.active_branch, "main")
        self.assertFalse(cfg.pull_delete_default)
        self.assertFalse(cfg.push_delete_default)
        self.assertEqual(cfg.sync_spaces, ())

        # Even if sync_spaces or auto_sync are configured, when repo_sync.enable is False they remain inactive
        docs_dir = self.proj_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        cfg_disabled = load_gdrive_config(
            config_override={
                "repo_sync": {"enable": False, "auto_sync": True},
                "sync_spaces": [{"space": "docs"}],
            },
            project_root=self.proj_dir,
            space_include_roots={"docs": [docs_dir]},
        )
        self.assertFalse(cfg_disabled.repo_sync_enabled)
        self.assertFalse(cfg_disabled.auto_sync)
        self.assertEqual(cfg_disabled.sync_spaces, ())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_space_normalization_and_longest_prefix_mapping(self) -> None:
        """Verify single-root file-space path normalization and bidirectional longest-prefix mapping when repo_sync.enable=True."""
        docs_dir = self.proj_dir / "docs"
        src_core = self.proj_dir / "ys_codebase" / "source" / "core"
        src_core_sub = src_core / "sub"
        docs_dir.mkdir(parents=True, exist_ok=True)
        src_core_sub.mkdir(parents=True, exist_ok=True)

        readme_f = docs_dir / "README.md"
        readme_f.write_text("# Docs\n", encoding="utf-8")
        core_f = src_core / "uri.py"
        core_f.write_text("x = 1\n", encoding="utf-8")
        sub_f = src_core_sub / "deep.py"
        sub_f.write_text("y = 2\n", encoding="utf-8")

        space_roots = {
            "docs": [docs_dir],
            "source": [self.proj_dir / "ys_codebase" / "source"],
        }
        cfg = load_gdrive_config(
            config_override={
                "repo_sync": {"enable": True, "active_branch": "main"},
                "sync_spaces": [
                    {"space": "docs"},
                    {
                        "space": "source",
                        "mapping": [
                            {"local": "ys_codebase/source/core", "remote": "code/core"},
                            {
                                "local": "ys_codebase/source/core/sub",
                                "remote": "code/special_sub",
                            },
                        ],
                    },
                ],
            },
            project_root=self.proj_dir,
            space_include_roots=space_roots,
        )
        self.assertTrue(cfg.repo_sync_enabled)
        self.assertEqual(len(cfg.sync_spaces), 2)
        docs_spec, src_spec = cfg.sync_spaces[0], cfg.sync_spaces[1]

        # Simulate FileSpaceManager returning inc_root-relative "README.md" for single-root "docs"
        fake_mgr = _FakeFileSpaceManager(
            {
                "docs": [("README.md", readme_f, docs_dir)],
                "source": [
                    ("core/uri.py", core_f, space_roots["source"][0]),
                    ("core/sub/deep.py", sub_f, space_roots["source"][0]),
                ],
            }
        )
        docs_mapped = collect_space_local_files(
            docs_spec, project_root=self.proj_dir, file_space_manager=fake_mgr
        )
        self.assertEqual(docs_mapped, {"docs/README.md": readme_f.resolve()})

        src_mapped = collect_space_local_files(
            src_spec, project_root=self.proj_dir, file_space_manager=fake_mgr
        )
        self.assertEqual(
            src_mapped,
            {
                "code/core/uri.py": core_f.resolve(),
                "code/special_sub/deep.py": sub_f.resolve(),
            },
        )
        self.assertEqual(
            src_spec.remote_to_local_rel("code/special_sub/deep.py"),
            "ys_codebase/source/core/sub/deep.py",
        )
        self.assertEqual(
            src_spec.remote_to_local_rel("code/core/uri.py"),
            "ys_codebase/source/core/uri.py",
        )

        # Verify fallback vs iter_space_files_with_stat delegation
        fallback_with_stat = collect_space_local_files_with_stat(
            docs_spec, project_root=self.proj_dir, file_space_manager=fake_mgr
        )
        self.assertEqual(
            fallback_with_stat,
            {"docs/README.md": (readme_f.resolve(), None, None)},
        )

        class _StatFakeFileSpaceManager:
            def iter_space_files_with_stat(self, space_name):
                if space_name == "docs":
                    yield ("README.md", readme_f, docs_dir, 123456789, 123456789, 7)

        stat_with_stat = collect_space_local_files_with_stat(
            docs_spec,
            project_root=self.proj_dir,
            file_space_manager=_StatFakeFileSpaceManager(),
        )
        self.assertEqual(
            stat_with_stat,
            {"docs/README.md": (readme_f, 123456789, 7)},
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_sandbox_transport_atomic_operations_and_shortcuts(self) -> None:
        """Verify LocalSandboxTransport upload, in-place PATCH, shortcut target resolution, and trash."""
        transport = LocalSandboxTransport(self.sandbox_dir)
        src_bin = self.proj_dir / "sample.xlsx"
        original_bytes = b"PK\x03\x04binary_excel_payload_v1"
        src_bin.write_bytes(original_bytes)

        uploaded = transport.upload_file(src_bin, "main/reports/sample.xlsx")
        self.assertFalse(uploaded.is_dir)
        self.assertEqual(uploaded.rel_path, "main/reports/sample.xlsx")
        self.assertEqual(uploaded.size, len(original_bytes))
        first_fid = uploaded.file_id

        # Create a shortcut in branch v1.0 pointing to main/reports/sample.xlsx
        sc_entry = transport.create_shortcut(first_fid, "v1.0/reports/sample.xlsx")
        self.assertTrue(sc_entry.is_shortcut)
        self.assertEqual(sc_entry.target_file_id, first_fid)
        self.assertFalse(sc_entry.dangling_shortcut)
        self.assertEqual(sc_entry.md5, uploaded.md5)
        self.assertEqual(sc_entry.size, len(original_bytes))

        # Download through shortcut preserves exact bytes
        dl_target = self.proj_dir / "downloaded_via_shortcut.xlsx"
        transport.download_file("v1.0/reports/sample.xlsx", dl_target)
        self.assertEqual(dl_target.read_bytes(), original_bytes)

        # In-place update keeps the same file_id
        updated_bytes = b"PK\x03\x04binary_excel_payload_v2_longer"
        src_bin.write_bytes(updated_bytes)
        patched = transport.upload_file(
            src_bin, "main/reports/sample.xlsx", in_place_file_id=first_fid
        )
        self.assertEqual(patched.file_id, first_fid)
        self.assertEqual(patched.size, len(updated_bytes))

        # Move to .trash/ via trash_file
        self.assertTrue(transport.trash_file("v1.0/reports/sample.xlsx"))
        self.assertIsNone(transport.get_entry("v1.0/reports/sample.xlsx"))
        trash_items = transport.list_files(".trash")
        self.assertEqual(len(trash_items), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_cli_atomic_commands_roundtrip(self) -> None:
        """Verify CLI status, mkdir, put, ls, shortcut, get, and rm commands against sandbox."""
        local_src = self.proj_dir / "note.md"
        local_src.write_text("Hello Atomic CLI\n", encoding="utf-8")
        local_dst = self.proj_dir / "note_pulled.md"
        sbx = self.sandbox_dir.as_posix()

        def _opts(**kw):
            return {k: CmdOption(name=k, params=v) for k, v in kw.items()}

        # 1. mkdir
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.mkdir(
                CmdBags(
                    raw_cmd="mkdir",
                    command="mkdir",
                    args=["main/docs"],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc, 0)
        mkdir_out = json.loads(buf.getvalue())
        self.assertEqual(mkdir_out["remote_path"], "main/docs")

        # 2. put
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.put(
                CmdBags(
                    raw_cmd="put",
                    command="put",
                    args=[local_src.as_posix(), "main/docs/note.md"],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc, 0)
        put_out = json.loads(buf.getvalue())
        fid = put_out["entry"]["file_id"]

        # 3. shortcut
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.shortcut(
                CmdBags(
                    raw_cmd="shortcut",
                    command="shortcut",
                    args=[fid, "v1.0/docs/note.md"],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc, 0)

        # 4. ls --recursive
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.ls(
                CmdBags(
                    raw_cmd="ls",
                    command="ls",
                    args=[],
                    options=_opts(**{"sandbox-dir": sbx, "recursive": True, "json": True}),
                )
            )
        self.assertEqual(rc, 0)
        ls_out = json.loads(buf.getvalue())
        rel_paths = [e["rel_path"] for e in ls_out["entries"]]
        self.assertIn("main/docs/note.md", rel_paths)
        self.assertIn("v1.0/docs/note.md", rel_paths)

        # 5. get via shortcut
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.get(
                CmdBags(
                    raw_cmd="get",
                    command="get",
                    args=["v1.0/docs/note.md", local_dst.as_posix()],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc, 0)
        self.assertEqual(local_dst.read_text(encoding="utf-8"), "Hello Atomic CLI\n")

        # 6. rm
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.rm(
                CmdBags(
                    raw_cmd="rm",
                    command="rm",
                    args=["v1.0/docs/note.md"],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc, 0)

        # 7. Credential leak guard: put must refuse to upload credentials.json or token.json
        cred_file = self.proj_dir / "credentials.json"
        cred_file.write_text('{"installed": {"client_secret": "GOCSPX-secret"}}', encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_cred = cli.put(
                CmdBags(
                    raw_cmd="put",
                    command="put",
                    args=[cred_file.as_posix(), "leaked_credentials.json"],
                    options=_opts(**{"sandbox-dir": sbx, "json": True}),
                )
            )
        self.assertEqual(rc_cred, 1)
        self.assertIn("Refusing to upload sensitive credential", buf.getvalue())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_01_mapping_outside_space_include_raises_config_error(self) -> None:
        """Verify mapping.local outside the registered file-space include root raises GDriveConfigError."""
        docs_dir = self.proj_dir / "docs"
        secret_dir = self.proj_dir / "secrets"
        docs_dir.mkdir(parents=True, exist_ok=True)
        secret_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(GDriveConfigError) as ctx:
            load_gdrive_config(
                config_override={
                    "repo_sync": {"enable": True},
                    "sync_spaces": [
                        {
                            "space": "docs",
                            "mapping": [{"local": "secrets", "remote": "leaked"}],
                        }
                    ],
                },
                project_root=self.proj_dir,
                space_include_roots={"docs": [docs_dir]},
            )
        self.assertIn("outside the include roots", str(ctx.exception))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_02_unsupported_google_workspace_mime_skipped_and_blocked(self) -> None:
        """Verify cloud-native Google Workspace MIME items are marked SKIPPED_UNSUPPORTED_MIME and blocked on download."""
        transport = LocalSandboxTransport(self.sandbox_dir)
        transport.inject_virtual_entry(
            "main/OnlineDoc",
            mime_type="application/vnd.google-apps.document",
            file_id="gdoc_native_1",
        )
        entries = transport.list_files("main")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].skipped_reason, "SKIPPED_UNSUPPORTED_MIME")

        with self.assertRaises(GDriveUnsupportedMimeError):
            transport.download_file("main/OnlineDoc", self.proj_dir / "out.md")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_03_dangling_shortcut_and_folder_shortcut_rejection(self) -> None:
        """Verify dangling shortcuts are flagged and creating a shortcut to a folder is rejected."""
        transport = LocalSandboxTransport(self.sandbox_dir)
        folder_entry = transport.mkdir("main/sub")
        with self.assertRaises(GDrivePathError):
            transport.create_shortcut(folder_entry.file_id, "v1.0/sub_sc")

        sc = transport.create_shortcut("non_existent_fid_999", "v1.0/broken_link.txt")
        self.assertTrue(sc.dangling_shortcut)
        self.assertEqual(sc.skipped_reason, "DANGLING_SHORTCUT")

        with self.assertRaises(GDriveFileNotFoundError):
            transport.download_file("v1.0/broken_link.txt", self.proj_dir / "broken.txt")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et_04_path_traversal_and_duplicate_same_name_deduplication(self) -> None:
        """Verify '../' traversal is rejected and duplicate same-name remote entries auto-deduplicate to .trash/."""
        transport = LocalSandboxTransport(self.sandbox_dir)
        with self.assertRaises(GDrivePathError):
            transport.list_files("../escape")

        f_path = self.sandbox_dir / "main" / "dup.txt"
        f_path.parent.mkdir(parents=True, exist_ok=True)
        f_path.write_text("latest content", encoding="utf-8")

        transport.inject_virtual_entry(
            "main/dup.txt",
            mime_type="text/plain",
            file_id="older_dup_id",
            mtime_ns=100,
        )
        transport.inject_virtual_entry(
            "main/dup.txt",
            mime_type="text/plain",
            file_id="newer_dup_id",
            mtime_ns=9999999999999999999,
        )

        listed = transport.list_files("main")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].file_id, "newer_dup_id")

        trashed = transport.list_files(".trash")
        self.assertTrue(any(e.file_id == "older_dup_id" for e in trashed))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_google_drive_api_transport_folder_cache_and_scanned_prefix(self) -> None:
        """Verify GoogleDriveApiTransport caches folder IDs across mkdir/list_files and skips redundant get_entry after recursive scan."""
        from gdrive_support.transport import FOLDER_MIME_TYPE, GoogleDriveApiTransport

        cfg = load_gdrive_config(
            config_override={"root_folder_id": "root_123"},
            project_root=self.proj_dir,
            space_include_roots={},
        )
        transport = GoogleDriveApiTransport(cfg)

        list_calls = []
        post_calls = []

        def _fake_list_children(folder_id: str):
            list_calls.append(folder_id)
            if folder_id == "root_123":
                return [{"id": "fid_repo", "name": "repo", "mimeType": FOLDER_MIME_TYPE, "parents": ["root_123"]}]
            if folder_id == "fid_repo":
                return [{"id": "fid_main", "name": "main", "mimeType": FOLDER_MIME_TYPE, "parents": ["fid_repo"]}]
            if folder_id == "fid_main":
                return [{"id": "fid_docs", "name": "docs", "mimeType": FOLDER_MIME_TYPE, "parents": ["fid_main"]}]
            return []

        def _fake_request_json(method, url, body=None, headers=None):
            post_calls.append((method, url))
            return {
                "id": f"uploaded_{len(post_calls)}",
                "name": "file.md",
                "mimeType": "text/markdown",
                "size": 5,
                "md5Checksum": "abc",
                "parents": ["fid_docs"],
            }

        transport._list_children_raw = _fake_list_children
        transport._request_json = _fake_request_json

        # 1. Recursive scan of repo/main populates _folder_cache and _scanned_prefixes
        entries = transport.list_files("repo/main", recursive=True)
        self.assertEqual(len(entries), 1)
        self.assertIn("repo/main/docs", transport._folder_cache)
        initial_list_count = len(list_calls)

        # 2. Uploading two files into repo/main/docs hits _folder_cache (0 list calls) and skips get_entry
        f1 = self.proj_dir / "a.md"
        f2 = self.proj_dir / "b.md"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")

        u1 = transport.upload_file(f1, "repo/main/docs/a.md")
        u2 = transport.upload_file(f2, "repo/main/docs/b.md")
        self.assertEqual(u1.file_id, "uploaded_1")
        self.assertEqual(u2.file_id, "uploaded_2")
        self.assertEqual(len(list_calls), initial_list_count)

        # 3. Trashing a cached folder invalidates its cache entry
        transport.trash_file("repo/main/docs")
        self.assertNotIn("repo/main/docs", transport._folder_cache)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_06_sensitive_credential_paths_and_migration_1_0_1_x(self) -> None:
        """Verify is_sensitive_credential_path guards .config.local/.storage.local and 1.0.1.x.py idempotently migrates assets."""
        self.assertTrue(
            is_sensitive_credential_path(
                self.proj_dir / "ys_codebase" / ".config.local" / "gdrive-support" / "custom.json",
                self.proj_dir,
            )
        )
        self.assertTrue(
            is_sensitive_credential_path(
                self.proj_dir / "ys_codebase" / ".storage.local" / "gdrive-support" / "sync_state.json",
                self.proj_dir,
            )
        )
        self.assertTrue(
            is_sensitive_credential_path(
                self.proj_dir / "ys_codebase" / "config" / "gdrive-support" / "credentials.json",
                self.proj_dir,
            )
        )
        self.assertFalse(
            is_sensitive_credential_path(
                self.proj_dir / "ys_codebase" / "config" / "gdrive-support" / "config.project.json",
                self.proj_dir,
            )
        )
        self.assertFalse(
            is_sensitive_credential_path(
                self.proj_dir / "docs" / "README.md",
                self.proj_dir,
            )
        )

        mig_spec = importlib.util.spec_from_file_location(
            "_gdrive_mig_1_0_1_x",
            _pkg_root / "scripts" / "migrations" / "1.0.1.x.py",
        )
        assert mig_spec is not None and mig_spec.loader is not None
        mig_mod = importlib.util.module_from_spec(mig_spec)
        mig_spec.loader.exec_module(mig_mod)

        yscb_dir = self.tmp_root / "ys_codebase"
        cfg_dir = yscb_dir / "config" / "gdrive-support"
        cfg_local_dir = yscb_dir / ".config.local" / "gdrive-support"
        storage_local_dir = yscb_dir / ".storage.local" / "gdrive-support"
        cache_dir = yscb_dir / ".cache" / "gdrive-support"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        (cfg_dir / "credentials.json").write_text('{"installed":{"client_id":"cid"}}', encoding="utf-8")
        (cache_dir / "token.json").write_text('{"refresh_token":"rtok"}', encoding="utf-8")
        (cache_dir / "sync_state.json").write_text('{"branches":{"main":{}}}', encoding="utf-8")
        (cache_dir / "readme_sync_state.json").write_text('{"states":{"root":true}}', encoding="utf-8")
        (cfg_dir / "config.project.json").write_text(
            json.dumps(
                {
                    "root_folder_id": "folder_1",
                    "credentials_uri": "config://gdrive-support/credentials.json",
                    "token_uri": "cache://gdrive-support/token.json",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        ctx = {
            "host_dir": self.tmp_root.as_posix(),
            "yscb_dir": yscb_dir.as_posix(),
            "config_dir": cfg_dir.as_posix(),
            "config_local_dir": cfg_local_dir.as_posix(),
            "storage_dir": (yscb_dir / "storage" / "gdrive-support").as_posix(),
            "storage_local_dir": storage_local_dir.as_posix(),
            "old_version": "1.0.0.0",
            "target_version": "1.0.1.0",
        }
        self.assertTrue(mig_mod.migrate(ctx))

        self.assertFalse((cfg_dir / "credentials.json").exists())
        self.assertFalse((cache_dir / "token.json").exists())
        self.assertFalse((cache_dir / "sync_state.json").exists())
        self.assertFalse((cache_dir / "readme_sync_state.json").exists())

        self.assertEqual(
            (cfg_local_dir / "credentials.json").read_text(encoding="utf-8"),
            '{"installed":{"client_id":"cid"}}',
        )
        self.assertEqual(
            (cfg_local_dir / "token.json").read_text(encoding="utf-8"),
            '{"refresh_token":"rtok"}',
        )
        self.assertEqual(
            (storage_local_dir / "sync_state.json").read_text(encoding="utf-8"),
            '{"branches":{"main":{}}}',
        )
        self.assertEqual(
            (storage_local_dir / "readme_sync_state.json").read_text(encoding="utf-8"),
            '{"states":{"root":true}}',
        )

        upgraded_cfg = json.loads((cfg_dir / "config.project.json").read_text(encoding="utf-8"))
        self.assertEqual(
            upgraded_cfg["credentials_uri"],
            "config.local://gdrive-support/credentials.json",
        )
        self.assertEqual(
            upgraded_cfg["token_uri"],
            "config.local://gdrive-support/token.json",
        )

        # Verify idempotency when target files already exist and stale legacy files reappear
        (cfg_dir / "credentials.json").write_text('{"stale":true}', encoding="utf-8")
        (cache_dir / "sync_state.json").write_text('{"stale":true}', encoding="utf-8")
        self.assertTrue(mig_mod.migrate(ctx))
        self.assertFalse((cfg_dir / "credentials.json").exists())
        self.assertFalse((cache_dir / "sync_state.json").exists())
        self.assertEqual(
            (cfg_local_dir / "credentials.json").read_text(encoding="utf-8"),
            '{"installed":{"client_id":"cid"}}',
        )
        self.assertEqual(
            (storage_local_dir / "sync_state.json").read_text(encoding="utf-8"),
            '{"branches":{"main":{}}}',
        )
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
