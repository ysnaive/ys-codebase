"""
Full-fidelity virtual sandbox provisioner and context manager for YS-Codebase testing.
"""
import os
import sys
import json
import uuid
import shutil
import zipfile
import platform
import stat
import threading
import functools
from datetime import datetime
from typing import Dict, Any, Optional, List
from core import uri, vfs, semver, events, PipManager
from dev.checker import discover_source_modules


class SandboxContext:
    """Sandbox operational context facade passed to module test hooks."""
    def __init__(self, sandbox_dir: str):
        self.sandbox_dir = os.path.abspath(sandbox_dir)
        self.host_dir = os.path.join(self.sandbox_dir, "host_env")
        self.engine_dir = os.path.join(self.host_dir, "engine")
        self.project_dir = os.path.join(self.sandbox_dir, "mock_downstream_project")
        self.provider_dir = os.path.join(self.sandbox_dir, "mock_provider")

    def set_module_config(self, module_name: str, config_filename: str, data: Dict[str, Any]) -> str:
        """Safely write configuration into host engine's config/{module}/{config_filename}."""
        cfg_dir = os.path.join(self.engine_dir, "config", module_name)
        os.makedirs(cfg_dir, exist_ok=True)
        target_path = os.path.join(cfg_dir, config_filename)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return target_path

    def create_mock_package(
        self,
        name: str,
        version: str = "1.0.0.0",
        deps: Optional[Dict[str, str]] = None,
        description: str = "Mock Package for Testing",
    ) -> str:
        """Create a valid versioned mock package inside sandbox mock_provider (both unpacked & zip)."""
        pkg_ver_dir = os.path.join(self.provider_dir, name, version)
        os.makedirs(os.path.join(pkg_ver_dir, "scripts"), exist_ok=True)

        manifest = {
            "name": name,
            "version": version,
            "description": description,
            "entry": "scripts/cli.py",
            "dependencies": deps or {},
        }
        with open(os.path.join(pkg_ver_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        cli_content = f'''"""
CLI Entry point for mock module {name}.
"""
from typing import Any
from core.guard import guard_dispatch
from core.commands import CmdBags


def hello(cmd_bags: Any) -> int:
    guard_dispatch("{name}")
    print(f"[{name}] Running mock cli hello")
    return 0
'''
        with open(os.path.join(pkg_ver_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write(cli_content)

        contrib_dir = os.path.join(pkg_ver_dir, "contributes")
        os.makedirs(contrib_dir, exist_ok=True)
        manifest_md = f"# {name} Contributes Manifest\n\n## 1. Commands\n- hello\n"
        with open(os.path.join(contrib_dir, "_manifest.md"), "w", encoding="utf-8") as f:
            f.write(manifest_md)
        core_json = {
            "commands": {
                "description": description,
                "cmd": {
                    "hello": {
                        "description": f"Say hello from {name}",
                        "tier": "safe",
                        "server_compatible": True,
                    }
                },
            }
        }
        with open(os.path.join(contrib_dir, "core.json"), "w", encoding="utf-8") as f:
            json.dump(core_json, f, indent=2)

        zip_path = os.path.join(self.provider_dir, name, f"{version}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(pkg_ver_dir):
                rel = os.path.relpath(root, pkg_ver_dir)
                for f in files:
                    arc = f if rel == "." else os.path.join(rel, f).replace("\\", "/")
                    zf.write(os.path.join(root, f), arcname=arc)

        mod_index_path = os.path.join(self.provider_dir, name, "index.json")
        versions = [version]
        if os.path.isfile(mod_index_path):
            try:
                with open(mod_index_path, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                existing_v = v_data.get("versions", [])
                if version not in existing_v:
                    existing_v.append(version)
                versions = sorted(
                    existing_v,
                    key=functools.cmp_to_key(lambda a, b: semver.compare_semver(semver.parse_semver(a), semver.parse_semver(b))),
                )
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        with open(mod_index_path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "description": description, "versions": versions}, f, indent=2)

        return pkg_ver_dir


class SandboxProvisioner:
    """Sandbox environment lifecycle manager and provisioner (dev op-mksb engine)."""
    _ACTIVE_SANDBOXES = set()
    _SANDBOX_LOCK = threading.RLock()
    _PIP_LOCK = threading.Lock()
    _ADAPTED_SPECS = set()

    @staticmethod
    def _sort_zip_filenames_by_semver(filenames: List[str]) -> List[str]:
        """依 SemVer 排序 zip 檔名（如 1.10.0.build.zip > 1.9.0.build.zip）。"""
        def _extract_ver(fname: str) -> semver.VersionTuple:
            base = fname[:-4]
            if base.endswith(".build"):
                base = base[:-6]
            try:
                return semver.parse_semver(base)
            except ValueError:
                return semver.parse_semver("0.0.0.0")

        def _cmp(f1: str, f2: str) -> int:
            v1 = _extract_ver(f1)
            v2 = _extract_ver(f2)
            res = semver.compare_semver(v1, v2)
            if res != 0:
                return res
            return 1 if f1 > f2 else (-1 if f1 < f2 else 0)

        return sorted(filenames, key=functools.cmp_to_key(_cmp))

    @staticmethod
    def _find_latest_build_zip(mod_name: str) -> Optional[str]:
        """Locate the latest SemVer-sorted .zip package under module.build://<mod_name>."""
        if not vfs.exists("module.build://"):
            return None
        mod_b_dir = os.path.join(uri.resolve("module.build://"), mod_name)
        if not os.path.isdir(mod_b_dir):
            return None
        zips = [f for f in os.listdir(mod_b_dir) if f.endswith(".zip")]
        if not zips:
            return None
        sorted_zips = SandboxProvisioner._sort_zip_filenames_by_semver(zips)
        return os.path.join(mod_b_dir, sorted_zips[-1])

    @staticmethod
    def _sweep_sandboxes(
        max_keep: Optional[int] = None,
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        is_harness_cleanup: bool = False,
    ) -> int:
        """Shared underlying sweep logic for prune_sandboxes and cleanup_all_sandboxes."""
        with SandboxProvisioner._SANDBOX_LOCK:
            if sandbox_parent_dir:
                sandbox_parent = sandbox_parent_dir
            else:
                if not vfs.exists("cache://dev/sandbox/"):
                    return 0
                sandbox_parent = uri.resolve("cache://dev/sandbox/")

            if not os.path.isdir(sandbox_parent):
                return 0

            exclude_set = set(exclude or [])
            for active_p in list(SandboxProvisioner._ACTIVE_SANDBOXES):
                exclude_set.add(active_p)
                exclude_set.add(os.path.basename(active_p))
            if max_keep is not None:
                active_sb_env = os.environ.get("YSCB_SANDBOX_DIR")
                if active_sb_env:
                    exclude_set.add(os.path.abspath(active_sb_env))
                    exclude_set.add(os.path.basename(os.path.abspath(active_sb_env)))

            entries = sorted(
                d for d in os.listdir(sandbox_parent)
                if d.startswith("sandbox_")
                and os.path.isdir(os.path.join(sandbox_parent, d))
                and d not in exclude_set
                and os.path.join(sandbox_parent, d) not in exclude_set
            )

            if max_keep is not None:
                if len(entries) <= max_keep:
                    return 0
                entries = entries[:len(entries) - max_keep]

            deleted_count = 0
            for item in entries:
                full_p = os.path.join(sandbox_parent, item)
                if SandboxProvisioner.cleanup_sandbox(full_p, force=True, is_harness_cleanup=is_harness_cleanup):
                    deleted_count += 1
            return deleted_count

    @staticmethod
    def prune_sandboxes(
        max_keep: int = 3,
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> int:
        """Removes oldest sandbox_* directories under cache://dev/sandbox/ when count exceeds max_keep."""
        try:
            return SandboxProvisioner._sweep_sandboxes(
                max_keep=max_keep,
                sandbox_parent_dir=sandbox_parent_dir,
                exclude=exclude,
                is_harness_cleanup=False,
            )
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed during prune_sandboxes: {e}", file=sys.stderr)
            return 0

    @staticmethod
    def cleanup_all_sandboxes(
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        is_harness_cleanup: bool = True,
    ) -> int:
        """Removes all sandbox_* directories under cache://dev/sandbox/ with full thread-lock protection."""
        try:
            return SandboxProvisioner._sweep_sandboxes(
                max_keep=None,
                sandbox_parent_dir=sandbox_parent_dir,
                exclude=exclude,
                is_harness_cleanup=is_harness_cleanup,
            )
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed during cleanup_all_sandboxes: {e}", file=sys.stderr)
            return 0

    @staticmethod
    def adapt_build_pip_dependencies(
        target_modules: Optional[List[str]] = None,
    ) -> List[str]:
        """
        在建置虛擬基環境之前，掃描當前 build 版（module.build://）或 source 模組中的
        manifest.json 之 pip_dependencies 宣告，調用 core.PipManager 於宿主微環境完成靜默物化。
        """
        scan_modules: List[str] = []
        if target_modules is not None and "--all" not in target_modules:
            scan_modules = [m for m in target_modules if m and not m.startswith("-")]
        else:
            cand_modules = set(discover_source_modules(require_manifest=False))
            if vfs.exists("module.build://"):
                b_dir = uri.resolve("module.build://")
                if os.path.isdir(b_dir):
                    for m in os.listdir(b_dir):
                        if os.path.isdir(os.path.join(b_dir, m)):
                            cand_modules.add(m)
            scan_modules = sorted(cand_modules)

        all_specs: List[str] = []
        for mod_name in scan_modules:
            m_data = None
            latest_zip = SandboxProvisioner._find_latest_build_zip(mod_name)
            if latest_zip:
                try:
                    with zipfile.ZipFile(latest_zip, "r") as zf:
                        if "manifest.json" in zf.namelist():
                            with zf.open("manifest.json") as mf:
                                m_data = json.load(mf)
                except (zipfile.BadZipFile, OSError, json.JSONDecodeError):
                    pass

            if m_data is None:
                src_uri = f"module.source://{mod_name}"
                if vfs.exists(src_uri):
                    src_manifest = os.path.join(uri.resolve(src_uri), "manifest.json")
                    if os.path.isfile(src_manifest):
                        try:
                            with open(src_manifest, "r", encoding="utf-8") as f:
                                m_data = json.load(f)
                        except (OSError, json.JSONDecodeError):
                            pass

            if m_data and "pip_dependencies" in m_data:
                parsed = PipManager.parse_pip_dependencies(m_data.get("pip_dependencies"))
                all_specs.extend(parsed)

        seen = set()
        deduped: List[str] = []
        for spec in all_specs:
            if spec not in seen:
                seen.add(spec)
                deduped.append(spec)

        if deduped:
            with SandboxProvisioner._PIP_LOCK:
                to_install = [s for s in deduped if s not in SandboxProvisioner._ADAPTED_SPECS]
                if to_install:
                    yscb_d = uri.resolve("yscb://")
                    pm = PipManager(yscb_d)
                    pm.install_packages(to_install)
                    SandboxProvisioner._ADAPTED_SPECS.update(to_install)

        return deduped

    @staticmethod
    def _unlink_projected_venv(sandbox_engine_dir: str) -> None:
        """Safely unlinks/removes Junction or Symlink for sandbox engine/.venv without affecting host."""
        sandbox_venv = os.path.join(sandbox_engine_dir, ".venv")
        if not os.path.lexists(sandbox_venv):
            return
        try:
            if os.path.islink(sandbox_venv):
                os.unlink(sandbox_venv)
                return
            if platform.system() == "Windows":
                st = os.lstat(sandbox_venv)
                if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    os.rmdir(sandbox_venv)
                    return
        except (FileNotFoundError, OSError) as e:
            if getattr(e, "errno", None) == 2:
                return
            print(f"[dev:sandbox] Warning: Failed to unlink projected venv: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed to unlink projected venv: {e}", file=sys.stderr)

    @staticmethod
    def _project_venv(host_yscb_dir: str, sandbox_engine_dir: str) -> bool:
        """
        跨平台零拷貝投影宿主微環境至沙盒 engine/.venv。
        Windows: 優先調用 _winapi.CreateJunction。
        POSIX: 優先調用 os.symlink。
        降級兜底: 若引發 OSError，建立輕量 site-packages 並寫入 host_venv.pth。
        """
        host_venv_dir = os.path.join(host_yscb_dir, ".venv")
        if not os.path.exists(host_venv_dir):
            return False
        real_host_venv_dir = os.path.realpath(host_venv_dir)
        if os.path.exists(real_host_venv_dir):
            host_venv_dir = real_host_venv_dir

        sandbox_venv_dir = os.path.join(sandbox_engine_dir, ".venv")
        if os.path.lexists(sandbox_venv_dir):
            SandboxProvisioner._unlink_projected_venv(sandbox_engine_dir)
            if os.path.exists(sandbox_venv_dir):
                shutil.rmtree(sandbox_venv_dir, ignore_errors=True)

        if platform.system() == "Windows":
            try:
                import _winapi
                _winapi.CreateJunction(os.path.abspath(host_venv_dir), os.path.abspath(sandbox_venv_dir))
                return True
            except OSError:
                pass
        else:
            try:
                os.symlink(os.path.abspath(host_venv_dir), os.path.abspath(sandbox_venv_dir), target_is_directory=True)
                if os.path.exists(sandbox_venv_dir):
                    return True
                try:
                    if os.path.islink(sandbox_venv_dir):
                        os.unlink(sandbox_venv_dir)
                except OSError:
                    pass
            except OSError:
                pass

        try:
            pm_host = PipManager(host_yscb_dir)
            host_site_pkg = pm_host.get_site_packages_dir()

            pm_sb = PipManager(sandbox_engine_dir)
            sb_site_pkg = pm_sb.get_site_packages_dir()
            os.makedirs(sb_site_pkg, exist_ok=True)

            pth_file = os.path.join(sb_site_pkg, "host_venv.pth")
            with open(pth_file, "w", encoding="utf-8") as f:
                f.write(host_site_pkg + "\n")
            return True
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed to project venv with .pth fallback: {e}", file=sys.stderr)
            return False

    @staticmethod
    def _allocate_sandbox_root(target_dir: Optional[str]) -> SandboxContext:
        with SandboxProvisioner._SANDBOX_LOCK:
            if not target_dir:
                if os.environ.get("YSCB_TEST_SANDBOX") != "1":
                    SandboxProvisioner.prune_sandboxes(max_keep=8)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                unique_hex = uuid.uuid4().hex[:6]
                sandbox_id = f"sandbox_{ts}_{unique_hex}"
                target_dir = uri.resolve(f"cache://dev/sandbox/{sandbox_id}")

            SandboxProvisioner._ACTIVE_SANDBOXES.add(os.path.abspath(target_dir))
            ctx = SandboxContext(target_dir)
            for d in (ctx.sandbox_dir, ctx.project_dir, ctx.host_dir, ctx.engine_dir, ctx.provider_dir):
                os.makedirs(d, exist_ok=True)
            return ctx

    @staticmethod
    def _deploy_target_and_dependency_modules(ctx: SandboxContext, copy_source: bool) -> Dict[str, Any]:
        prov_uri = f"file:///{ctx.provider_dir.replace(os.sep, '/')}"
        host_config: Dict[str, Any] = {
            "yscb_root": "./engine",
            "default_provider": prov_uri,
            "installed_modules": {},
        }

        sandbox_modules_dir = os.path.join(ctx.engine_dir, ".modules")
        os.makedirs(sandbox_modules_dir, exist_ok=True)
        cand_host_modules = []
        if vfs.exists("module://"):
            cand_host_modules.append(uri.resolve("module://"))
        yscb_d = uri.resolve("yscb://")
        cand_host_modules.append(os.path.join(yscb_d, ".modules"))
        cand_host_modules.append(os.path.join(yscb_d, "modules"))

        for host_modules_dir in cand_host_modules:
            if os.path.isdir(host_modules_dir):
                for mod_name in sorted(os.listdir(host_modules_dir)):
                    if mod_name.startswith("."):
                        continue
                    mod_src_path = os.path.join(host_modules_dir, mod_name)
                    if os.path.isdir(mod_src_path):
                        dest_mod = os.path.join(sandbox_modules_dir, mod_name)
                        if not os.path.exists(dest_mod):
                            shutil.copytree(mod_src_path, dest_mod, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        if vfs.exists("module.build://"):
            build_root_dir = uri.resolve("module.build://")
            if os.path.isdir(build_root_dir):
                for mod_name in sorted(os.listdir(build_root_dir)):
                    if mod_name.startswith(".") or mod_name.startswith("mock_"):
                        continue
                    latest_zip = SandboxProvisioner._find_latest_build_zip(mod_name)
                    if latest_zip:
                        dest_mod = os.path.join(sandbox_modules_dir, mod_name)
                        if os.path.exists(dest_mod):
                            shutil.rmtree(dest_mod)
                        os.makedirs(dest_mod, exist_ok=True)
                        try:
                            with zipfile.ZipFile(latest_zip, "r") as zf:
                                zf.extractall(dest_mod)
                        except (zipfile.BadZipFile, OSError):
                            pass

        for mod_name in sorted(os.listdir(sandbox_modules_dir)):
            if mod_name.startswith("."):
                continue
            dest_mod = os.path.join(sandbox_modules_dir, mod_name)
            if os.path.isdir(dest_mod):
                mod_ver = "1.0.0.0"
                mod_desc = f"Standard host module {mod_name}"
                mf_path = os.path.join(dest_mod, "manifest.json")
                if os.path.isfile(mf_path):
                    try:
                        with open(mf_path, "r", encoding="utf-8") as mf_f:
                            mf_d = json.load(mf_f)
                        mod_ver = mf_d.get("version", mod_ver)
                        mod_desc = mf_d.get("description", mod_desc)
                    except (OSError, json.JSONDecodeError):
                        pass
                host_config["installed_modules"][mod_name] = {
                    "version": mod_ver,
                    "installed_at": "sandbox_provisioned",
                    "provider": prov_uri,
                    "description": mod_desc,
                }

        if copy_source and vfs.exists("module.source://"):
            curr_source = uri.resolve("module.source://")
            if os.path.isdir(curr_source):
                dest_source = os.path.join(ctx.engine_dir, "source")
                if os.path.exists(dest_source):
                    shutil.rmtree(dest_source)
                shutil.copytree(curr_source, dest_source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        return host_config

    @staticmethod
    def _provision_core_and_config(ctx: SandboxContext, host_config: Dict[str, Any]) -> None:
        with open(os.path.join(ctx.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(host_config, f, indent=2)

        host_d = uri.resolve("yscb.host://")
        curr_yscb = os.path.join(host_d, "yscb.py")
        if not os.path.isfile(curr_yscb):
            yscb_d = uri.resolve("yscb://")
            curr_yscb = os.path.join(yscb_d, "yscb.py")
        if not os.path.isfile(curr_yscb):
            curr_yscb = os.path.abspath("yscb.py")

        if os.path.isfile(curr_yscb):
            shutil.copy2(curr_yscb, os.path.join(ctx.host_dir, "yscb.py"))
        else:
            raise FileNotFoundError(f"Host bootstrapper 'yscb.py' not found at '{curr_yscb}'.")

    @staticmethod
    def _link_virtual_environment(ctx: SandboxContext) -> None:
        host_d = uri.resolve("yscb.host://")
        host_yscb_d = uri.resolve("yscb://")
        cand_host_venv = host_yscb_d if os.path.exists(os.path.join(host_yscb_d, ".venv")) else host_d
        SandboxProvisioner._project_venv(cand_host_venv, ctx.engine_dir)

        scanned_roots = [
            os.path.join(ctx.engine_dir, "source"),
            os.path.join(ctx.engine_dir, ".modules"),
        ]
        with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):
            events.broadcast("on_test_setup", context=ctx, emit_module="dev", search_roots=scanned_roots)

    @staticmethod
    def create_sandbox(
        target_dir: Optional[str] = None,
        copy_source: bool = True,
        target_modules: Optional[List[str]] = None,
    ) -> SandboxContext:
        """
        Builds a full-fidelity micro virtual environment with rollback protection:
        1. Adapts build pip dependencies into host venv
        2. Allocates sandbox directories and registers in _ACTIVE_SANDBOXES
        3. Deploys target/dependency modules and source tree
        4. Writes host_env/yscb.config.json and copies yscb.py
        5. Projects host venv and dispatches on_test_setup hooks
        """
        if os.environ.get("YSCB_TEST_SANDBOX") != "1":
            SandboxProvisioner.adapt_build_pip_dependencies(target_modules=target_modules)

        ctx = SandboxProvisioner._allocate_sandbox_root(target_dir)
        try:
            host_config = SandboxProvisioner._deploy_target_and_dependency_modules(ctx, copy_source)
            SandboxProvisioner._provision_core_and_config(ctx, host_config)
            SandboxProvisioner._link_virtual_environment(ctx)
            return ctx
        except BaseException:
            SandboxProvisioner.cleanup_sandbox(ctx.sandbox_dir, force=True, is_harness_cleanup=True)
            raise

    @staticmethod
    def cleanup_sandbox(sandbox_dir: str, force: bool = False, is_harness_cleanup: bool = False) -> bool:
        """Tears down the virtual sandbox safely with active running sandbox guardrail."""
        with SandboxProvisioner._SANDBOX_LOCK:
            target_abs = os.path.abspath(sandbox_dir)
            SandboxProvisioner._ACTIVE_SANDBOXES.discard(target_abs)
            if not os.path.exists(sandbox_dir):
                return True

            if not is_harness_cleanup and os.environ.get("YSCB_TEST_SANDBOX") == "1":
                active_sb = os.environ.get("YSCB_SANDBOX_DIR")
                if active_sb and os.path.abspath(active_sb) == target_abs:
                    return True
                curr_cwd = os.path.abspath(os.getcwd())
                if curr_cwd == target_abs or curr_cwd.startswith(target_abs + os.sep):
                    return True

            try:
                ctx = SandboxContext(sandbox_dir)
                scanned_roots = [
                    os.path.join(ctx.engine_dir, "source"),
                    os.path.join(ctx.engine_dir, ".modules"),
                ]
                with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):
                    events.broadcast("on_test_teardown", context=ctx, emit_module="dev", search_roots=scanned_roots)
                SandboxProvisioner._unlink_projected_venv(ctx.engine_dir)
                shutil.rmtree(sandbox_dir)
                return True
            except Exception as e:
                if not force:
                    print(f"[dev:sandbox] Warning: Failed to clean sandbox '{sandbox_dir}': {e}", file=sys.stderr)
                return False
