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
from typing import Dict, Any, Optional, List, Tuple
from core import uri, events, PipManager

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
        description: str = "Mock Package for Testing"
    ) -> str:
        """Create a valid versioned mock package inside sandbox mock_provider (both unpacked & zip)."""
        pkg_ver_dir = os.path.join(self.provider_dir, name, version)
        os.makedirs(os.path.join(pkg_ver_dir, "scripts"), exist_ok=True)
        
        manifest = {
            "name": name,
            "version": version,
            "description": description,
            "entry": "scripts/cli.py",
            "dependencies": deps or {}
        }
        with open(os.path.join(pkg_ver_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            
        cli_content = f"#!/usr/bin/env python3\ndef main(argv):\n    print(f'[{name}] Running mock cli with args: {{argv}}')\n    return 0\n"
        with open(os.path.join(pkg_ver_dir, "scripts", "cli.py"), "w", encoding="utf-8") as f:
            f.write(cli_content)

        # Create single-file zip in provider_dir/<name>/<version>.zip
        zip_path = os.path.join(self.provider_dir, name, f"{version}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(pkg_ver_dir):
                rel = os.path.relpath(root, pkg_ver_dir)
                for f in files:
                    arc = f if rel == "." else os.path.join(rel, f).replace("\\", "/")
                    zf.write(os.path.join(root, f), arcname=arc)

        # Update module index.json
        mod_index_path = os.path.join(self.provider_dir, name, "index.json")
        versions = [version]
        if os.path.isfile(mod_index_path):
            try:
                with open(mod_index_path, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                existing_v = v_data.get("versions", [])
                if version not in existing_v:
                    existing_v.append(version)
                versions = sorted(existing_v)
            except Exception:
                pass
        with open(mod_index_path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "description": description, "versions": versions}, f, indent=2)

        return pkg_ver_dir


class SandboxProvisioner:
    """Sandbox environment lifecycle manager and provisioner (dev op-mksb engine)."""

    @staticmethod
    def prune_sandboxes(
        max_keep: int = 3,
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None
    ) -> int:
        """
        Removes oldest sandbox_* directories under cache://dev/sandbox/ when count exceeds max_keep.

        Args:
            max_keep: Maximum number of newest sandboxes to retain (default: 3).
            sandbox_parent_dir: Optional parent directory to prune. Defaults to cache://dev/sandbox/.
            exclude: Optional list of directory names or paths to exclude from deletion.

        Returns:
            int: Number of deleted sandboxes.
        """
        try:
            if sandbox_parent_dir:
                sandbox_parent = sandbox_parent_dir
            else:
                if not uri.exists("cache://dev/sandbox/"):
                    return 0
                sandbox_parent = uri.resolve("cache://dev/sandbox/")

            if not os.path.isdir(sandbox_parent):
                return 0

            exclude_set = set(exclude or [])
            entries = [
                d for d in os.listdir(sandbox_parent)
                if d.startswith("sandbox_")
                and os.path.isdir(os.path.join(sandbox_parent, d))
                and d not in exclude_set
                and os.path.join(sandbox_parent, d) not in exclude_set
            ]
            entries.sort()

            if len(entries) <= max_keep:
                return 0

            num_to_delete = len(entries) - max_keep
            to_delete = entries[:num_to_delete]
            deleted_count = 0
            for item in to_delete:
                full_p = os.path.join(sandbox_parent, item)
                if SandboxProvisioner.cleanup_sandbox(full_p, force=True):
                    deleted_count += 1
            return deleted_count
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed during prune_sandboxes: {e}", file=sys.stderr)
            return 0

    @staticmethod
    def cleanup_all_sandboxes(
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        is_harness_cleanup: bool = True
    ) -> int:
        """
        Removes all sandbox_* directories under cache://dev/sandbox/.

        Args:
            sandbox_parent_dir: Optional parent directory to clean. Defaults to cache://dev/sandbox/.
            exclude: Optional list of directory names or paths to exclude from deletion.
            is_harness_cleanup: Whether cleanup is initiated by test harness runner.

        Returns:
            int: Number of deleted sandboxes.
        """
        try:
            if sandbox_parent_dir:
                sandbox_parent = sandbox_parent_dir
            else:
                if not uri.exists("cache://dev/sandbox/"):
                    return 0
                sandbox_parent = uri.resolve("cache://dev/sandbox/")

            if not os.path.isdir(sandbox_parent):
                return 0

            exclude_set = set(exclude or [])
            entries = [
                d for d in os.listdir(sandbox_parent)
                if d.startswith("sandbox_")
                and os.path.isdir(os.path.join(sandbox_parent, d))
                and d not in exclude_set
                and os.path.join(sandbox_parent, d) not in exclude_set
            ]
            deleted_count = 0
            for item in entries:
                full_p = os.path.join(sandbox_parent, item)
                if SandboxProvisioner.cleanup_sandbox(full_p, force=True, is_harness_cleanup=is_harness_cleanup):
                    deleted_count += 1
            return deleted_count
        except Exception as e:
            print(f"[dev:sandbox] Warning: Failed during cleanup_all_sandboxes: {e}", file=sys.stderr)
            return 0

    @staticmethod
    def adapt_build_pip_dependencies(
        target_modules: Optional[List[str]] = None,
        quiet: bool = False
    ) -> List[str]:
        """
        在建置虛擬基環境之前，掃描當前 build 版（module.build://）或 source 模組中的
        manifest.json 之 pip_dependencies 宣告，調用 core.PipManager 於宿主微環境完成靜默物化。

        Args:
            target_modules: 可選，指定模組名稱清單。為 None 或包含 '--all' 時掃描全數。
            quiet: 是否靜默執行。

        Returns:
            List[str]: 本次已適配/物化之 pip 規格字串清單。
        """
        scan_modules: List[str] = []
        if target_modules is not None and "--all" not in target_modules:
            scan_modules = [m for m in target_modules if m and not m.startswith("-")]
        else:
            cand_modules = set()
            if uri.exists("module.build://"):
                b_dir = uri.resolve("module.build://")
                if os.path.isdir(b_dir):
                    for m in os.listdir(b_dir):
                        if os.path.isdir(os.path.join(b_dir, m)):
                            cand_modules.add(m)
            if uri.exists("module.source://"):
                s_dir = uri.resolve("module.source://")
                if os.path.isdir(s_dir):
                    for m in os.listdir(s_dir):
                        if os.path.isdir(os.path.join(s_dir, m)):
                            cand_modules.add(m)
            scan_modules = sorted(cand_modules)

        all_specs: List[str] = []
        for mod_name in scan_modules:
            m_data = None
            if uri.exists("module.build://"):
                mod_b_dir = os.path.join(uri.resolve("module.build://"), mod_name)
                if os.path.isdir(mod_b_dir):
                    zips = [f for f in os.listdir(mod_b_dir) if f.endswith(".zip")]
                    if zips:
                        latest_zip = os.path.join(mod_b_dir, sorted(zips)[-1])
                        try:
                            with zipfile.ZipFile(latest_zip, "r") as zf:
                                if "manifest.json" in zf.namelist():
                                    with zf.open("manifest.json") as mf:
                                        m_data = json.load(mf)
                        except Exception:
                            pass

            if m_data is None:
                src_uri = f"module.source://{mod_name}"
                if uri.exists(src_uri):
                    src_manifest = os.path.join(uri.resolve(src_uri), "manifest.json")
                    if os.path.isfile(src_manifest):
                        try:
                            with open(src_manifest, "r", encoding="utf-8") as f:
                                m_data = json.load(f)
                        except Exception:
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
            yscb_d = uri._get_yscb_root()
            pm = PipManager(yscb_d)
            pm.install_packages(deduped)

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
            if getattr(e, "errno", None) == 2:  # ENOENT: target already gone
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
                # Broken symlink on virtiofs mount, clean it up safely and fall through to .pth fallback
                try:
                    if os.path.islink(sandbox_venv_dir):
                        os.unlink(sandbox_venv_dir)
                except Exception:
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
    def create_sandbox(target_dir: Optional[str] = None, copy_source: bool = True, target_modules: Optional[List[str]] = None) -> SandboxContext:
        """
        Builds a full-fidelity micro virtual environment:
        1. Adapts build pip dependencies into host venv
        2. Creates mock_downstream_project/, host_env/, mock_provider/
        3. Configures host_env/yscb.config.json (yscb_root="./engine", default_provider=...)
        4. Ingests source/ into host_env/engine/source/
        5. Projects host venv into sandbox engine/.venv
        6. Copies host runner yscb.py into host_env/
        7. Dispatches scripts/hook.dev.py : on_test_setup(context)
        """
        # Materialize pip dependencies from build/source manifests (host environment only)
        if os.environ.get("YSCB_TEST_SANDBOX") != "1":
            SandboxProvisioner.adapt_build_pip_dependencies(target_modules=target_modules, quiet=True)

        if not target_dir:
            from datetime import datetime
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            unique_hex = uuid.uuid4().hex[:6]
            sandbox_id = f"sandbox_{ts}_{unique_hex}"
            target_dir = uri.resolve(f"cache://dev/sandbox/{sandbox_id}")
            
        ctx = SandboxContext(target_dir)
        for d in [ctx.sandbox_dir, ctx.project_dir, ctx.host_dir, ctx.engine_dir, ctx.provider_dir]:
            os.makedirs(d, exist_ok=True)

        # 1. Load host config template and inherit installed modules
        prov_uri = f"file:///{ctx.provider_dir.replace(os.sep, '/')}"
        host_config = {
            "yscb_root": "./engine",
            "default_provider": prov_uri,
            "installed_modules": {}
        }
        
        # Ingest installed host modules and config
        sandbox_modules_dir = os.path.join(ctx.engine_dir, ".modules")
        os.makedirs(sandbox_modules_dir, exist_ok=True)
        cand_host_modules = []
        if uri.exists("module.root://"):
            cand_host_modules.append(uri.resolve("module.root://"))
        if uri.exists("module://"):
            cand_host_modules.append(uri.resolve("module://"))
        yscb_d = uri._get_yscb_root()
        cand_host_modules.append(os.path.join(yscb_d, ".modules"))
        cand_host_modules.append(os.path.join(yscb_d, "modules"))

        for host_modules_dir in cand_host_modules:
            if os.path.isdir(host_modules_dir):
                for mod_name in sorted(os.listdir(host_modules_dir)):
                    mod_src_path = os.path.join(host_modules_dir, mod_name)
                    if os.path.isdir(mod_src_path):
                        dest_mod = os.path.join(sandbox_modules_dir, mod_name)
                        if not os.path.exists(dest_mod):
                            shutil.copytree(mod_src_path, dest_mod, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        # Overlay freshly built packages from module.build:// (dev build)
        if uri.exists("module.build://"):
            build_root_dir = uri.resolve("module.build://")
            if os.path.isdir(build_root_dir):
                for mod_name in sorted(os.listdir(build_root_dir)):
                    mod_b_dir = os.path.join(build_root_dir, mod_name)
                    if os.path.isdir(mod_b_dir):
                        zips = [f for f in os.listdir(mod_b_dir) if f.endswith(".zip")]
                        if zips:
                            latest_zip = os.path.join(mod_b_dir, sorted(zips)[-1])
                            dest_mod = os.path.join(sandbox_modules_dir, mod_name)
                            if os.path.exists(dest_mod):
                                shutil.rmtree(dest_mod)
                            os.makedirs(dest_mod, exist_ok=True)
                            with zipfile.ZipFile(latest_zip, "r") as zf:
                                zf.extractall(dest_mod)

        # Register all provisioned modules into sandbox host_config
        for mod_name in sorted(os.listdir(sandbox_modules_dir)):
            dest_mod = os.path.join(sandbox_modules_dir, mod_name)
            if os.path.isdir(dest_mod):
                mod_ver = "1.0.0"
                mod_desc = f"Standard host module {mod_name}"
                mf_path = os.path.join(dest_mod, "manifest.json")
                if os.path.isfile(mf_path):
                    try:
                        with open(mf_path, "r", encoding="utf-8") as mf_f:
                            mf_d = json.load(mf_f)
                        mod_ver = mf_d.get("version", mod_ver)
                        mod_desc = mf_d.get("description", mod_desc)
                    except Exception:
                        pass
                host_config["installed_modules"][mod_name] = {
                    "version": mod_ver,
                    "installed_at": "sandbox_provisioned",
                    "provider": prov_uri,
                    "description": mod_desc
                }

        # Write finalized host yscb.config.json
        with open(os.path.join(ctx.host_dir, "yscb.config.json"), "w", encoding="utf-8") as f:
            json.dump(host_config, f, indent=2)


        # 2. Copy host bootstrapper script yscb.py with rigid self-location
        host_d, _ = uri._get_host_config()
        curr_yscb = os.path.join(host_d, "yscb.py")
        if not os.path.isfile(curr_yscb):
            yscb_d = uri._get_yscb_root()
            curr_yscb = os.path.join(yscb_d, "yscb.py")
        if not os.path.isfile(curr_yscb):
            curr_yscb = os.path.abspath("yscb.py")
            
        if os.path.isfile(curr_yscb):
            shutil.copy2(curr_yscb, os.path.join(ctx.host_dir, "yscb.py"))
        else:
            raise FileNotFoundError(f"Host bootstrapper 'yscb.py' not found at '{curr_yscb}'.")

        # 3. Copy source tree if requested
        if copy_source:
            if uri.exists("module.source://"):
                curr_source = uri.resolve("module.source://")
                if os.path.isdir(curr_source):
                    dest_source = os.path.join(ctx.engine_dir, "source")
                    if os.path.exists(dest_source):
                        shutil.rmtree(dest_source)
                    shutil.copytree(curr_source, dest_source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        # 4. Project host venv into sandbox engine/.venv
        host_d, _ = uri._get_host_config()
        host_yscb_d = uri._get_yscb_root()
        cand_host_venv = host_yscb_d if os.path.exists(os.path.join(host_yscb_d, ".venv")) else host_d
        SandboxProvisioner._project_venv(cand_host_venv, ctx.engine_dir)

        # 5. Dispatch on_test_setup hooks across both sandbox source/ and modules/
        scanned_roots = [
            os.path.join(ctx.engine_dir, "source"),
            os.path.join(ctx.engine_dir, ".modules")
        ]
        with uri.host_scope(ctx.host_dir), uri.yscb_scope(ctx.engine_dir):
            events.broadcast("on_test_setup", context=ctx, emit_module="dev", search_roots=scanned_roots)

        return ctx

    @staticmethod
    def cleanup_sandbox(sandbox_dir: str, force: bool = False, is_harness_cleanup: bool = False) -> bool:
        """Tears down the virtual sandbox safely with active running sandbox guardrail."""
        if not os.path.exists(sandbox_dir):
            return True

        # Guardrail: protect active harness sandbox from accidental child test case deletion
        if not is_harness_cleanup and os.environ.get("YSCB_TEST_SANDBOX") == "1":
            target_abs = os.path.abspath(sandbox_dir)
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
                os.path.join(ctx.engine_dir, ".modules")
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
