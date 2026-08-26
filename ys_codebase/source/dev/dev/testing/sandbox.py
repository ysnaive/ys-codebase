"""
Full-fidelity virtual sandbox provisioner and context manager for YS-Codebase testing.
"""
import os
import sys
import json
import uuid
import shutil
import zipfile
import importlib.util
from typing import Dict, Any, Optional, List, Tuple
from core import uri

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
    def create_sandbox(target_dir: Optional[str] = None, copy_source: bool = True) -> SandboxContext:
        """
        Builds a full-fidelity micro virtual environment:
        1. Creates mock_downstream_project/, host_env/, mock_provider/
        2. Configures host_env/yscb.config.json (yscb_root="./engine", default_provider=...)
        3. Ingests source/ into host_env/engine/source/
        4. Copies host runner yscb.py into host_env/
        5. Dispatches scripts/hook.dev.py : on_test_setup(context)
        """
        if not target_dir:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            sandbox_id = f"sandbox_{ts}"
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
        if uri.exists("module://"):
            host_modules_dir = uri.resolve("module://")
            if os.path.isdir(host_modules_dir):
                sandbox_modules_dir = os.path.join(ctx.engine_dir, "modules")
                os.makedirs(sandbox_modules_dir, exist_ok=True)
                for mod_name in sorted(os.listdir(host_modules_dir)):
                    mod_src_path = os.path.join(host_modules_dir, mod_name)
                    if os.path.isdir(mod_src_path):
                        dest_mod = os.path.join(sandbox_modules_dir, mod_name)
                        if os.path.exists(dest_mod):
                            shutil.rmtree(dest_mod)
                        shutil.copytree(mod_src_path, dest_mod, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

                        # Dynamically read manifest version from real source/modules
                        mod_ver = "1.0.0"
                        mod_desc = f"Standard host module {mod_name}"
                        mf_path = os.path.join(mod_src_path, "manifest.json")
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
                            "installed_at": "host_inherited",
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

        # 4. Dispatch on_test_setup hooks across both sandbox source/ and modules/
        SandboxProvisioner._dispatch_test_hooks(ctx, "on_test_setup")

        return ctx

    @staticmethod
    def cleanup_sandbox(sandbox_dir: str, force: bool = False) -> bool:
        """Tears down the virtual sandbox safely."""
        if not os.path.exists(sandbox_dir):
            return True
        try:
            ctx = SandboxContext(sandbox_dir)
            SandboxProvisioner._dispatch_test_hooks(ctx, "on_test_teardown")
            shutil.rmtree(sandbox_dir)
            return True
        except Exception as e:
            if not force:
                print(f"[dev:sandbox] Warning: Failed to clean sandbox '{sandbox_dir}': {e}", file=sys.stderr)
            return False

    @staticmethod
    def _dispatch_test_hooks(ctx: SandboxContext, hook_name: str) -> None:
        """Scans sandbox engine source/ and modules/ for scripts/hook.dev.py and invokes hook_name."""
        scanned_roots = [
            os.path.join(ctx.engine_dir, "source"),
            os.path.join(ctx.engine_dir, "modules")
        ]
        executed_hooks = set()
        for root in scanned_roots:
            if not os.path.isdir(root):
                continue
            for mod_name in sorted(os.listdir(root)):
                if mod_name in executed_hooks:
                    continue
                hook_file = os.path.join(root, mod_name, "scripts", "hook.dev.py")
                if os.path.isfile(hook_file):
                    executed_hooks.add(mod_name)
                    try:
                        spec = importlib.util.spec_from_file_location(f"{mod_name}_hook_dev", hook_file)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                            fn = getattr(mod, hook_name, None)
                            if callable(fn):
                                fn(ctx)
                    except Exception as e:
                        print(f"[dev:sandbox] Warning: Hook '{mod_name}:scripts/hook.dev.py:{hook_name}' failed: {e}", file=sys.stderr)
