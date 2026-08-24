"""
AtomicEngine for YS-Codebase microkernel.
Executes 12 atomic operations: INIT, DOWNLOAD, DELETE, REGISTER, UNREGISTER,
SOLVE_DEPS, PREPARE, RELOAD, FETCH, SNAPSHOT, RESTORE_SNAPSHOT, DISPATCH_CLI.
"""
import os
import sys
import json
import time
import shutil
import urllib.request
import importlib.util
from typing import Dict, Any, List, Optional, Tuple, Set

from core import uri
from core.uri import ExecutionContext
from core.contributes import ContributesAggregator

class AtomicEngine:
    """Microkernel Atomic Operations Engine."""
    
    def __init__(self) -> None:
        self.contributes_aggregator = ContributesAggregator()

    def _get_config(self) -> Tuple[str, Dict[str, Any]]:
        host_dir, _ = uri._find_host_config()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        if not os.path.isfile(cfg_path):
            raise FileNotFoundError(f"yscb.config.json not found at '{cfg_path}'. Please run init first.")
        with open(cfg_path, "r", encoding="utf-8") as f:
            return cfg_path, json.load(f)

    def _save_config(self, config_data: Dict[str, Any]) -> None:
        host_dir, _ = uri._find_host_config()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        uri.write_json(cfg_path, config_data, indent=2)

    def act_init(self, yscb_root: str, default_provider: str = "./ys_codebase/build") -> None:
        try:
            host_dir, _ = uri._find_host_config()
        except Exception:
            host_dir = uri.get_host_dir() or os.path.dirname(uri._get_yscb_root())
            
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        if not os.path.isfile(cfg_path):
            cfg_data = {
                "yscb_root": yscb_root,
                "default_provider": default_provider,
                "installed_modules": {}
            }
            uri.write_json(cfg_path, cfg_data, indent=2)
        
        # Ensure directories
        for sub in ["modules", "build", ".mirror", ".snapshots", ".temp", ".cache", "config", "source"]:
            uri.makedirs(f"yscb://{sub}", exist_ok=True)
            
        # Seed core default config if not exists
        core_cfg_uri = "config.root://core/config.project.json"
        if not uri.exists(core_cfg_uri):
            uri.write_json(core_cfg_uri, {"project_root": "!undefined"}, indent=2)

    def act_fetch(self, provider_url: str, relative_path: str) -> Tuple[bool, Any]:
        """Fetch package or file from local or remote provider channel."""
        # 1. Local filesystem channel
        if os.path.isdir(provider_url) or not (provider_url.startswith("http://") or provider_url.startswith("https://")):
            local_p = os.path.join(provider_url, relative_path)
            if os.path.isfile(local_p):
                if local_p.endswith(".json"):
                    with open(local_p, "r", encoding="utf-8") as f:
                        return True, json.load(f)
                else:
                    with open(local_p, "r", encoding="utf-8") as f:
                        return True, f.read()
            return False, f"Local path not found: {local_p}"
            
        # 2. Remote HTTP/HTTPS channel
        url = f"{provider_url.rstrip('/')}/{relative_path.lstrip('/')}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yscb-engine/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
                if relative_path.endswith(".json"):
                    return True, json.loads(content)
                return True, content
        except Exception as e:
            return False, str(e)

    def act_lock(self, operation: str, timeout: float = 10.0) -> None:
        """
        Acquire inter-process lock on temp://.yscb.lock.
        Supports 10s auto-healing on crashed/stale processes.
        """
        lock_uri = "temp://.yscb.lock"
        lock_path = uri.resolve(lock_uri)
        uri.makedirs("temp://", exist_ok=True)
        
        now = time.time()
        if os.path.exists(lock_path):
            try:
                with open(lock_path, "r", encoding="utf-8") as f:
                    lock_info = json.load(f)
                lock_time = lock_info.get("timestamp", 0)
                if now - lock_time > timeout:
                    # Stale lock detected, auto-heal
                    os.remove(lock_path)
            except Exception:
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "timestamp": now, "operation": operation}, f)
        except FileExistsError:
            raise BlockingIOError(f"Another yscb process is currently holding the lock for operation '{operation}'.")

    def act_unlock(self, operation: str) -> None:
        """Release inter-process lock on temp://.yscb.lock."""
        lock_uri = "temp://.yscb.lock"
        if uri.exists(lock_uri):
            try:
                uri.remove(lock_uri)
            except Exception:
                pass

    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
        dest_mirror_uri = f"mirror://{module_name}/{version}/"
        if uri.exists(dest_mirror_uri):
            uri.rmtree(dest_mirror_uri)
        uri.makedirs(dest_mirror_uri)
        
        # 1. Check if local provider directory
        local_src = os.path.join(provider_url, module_name, version)
        if not os.path.isdir(local_src):
            local_src = os.path.join(provider_url, module_name)
        if not os.path.isdir(local_src):
            local_src = os.path.join(provider_url, "build", module_name, version)
        if not os.path.isdir(local_src):
            local_src = os.path.join(provider_url, "build", module_name)
        if os.path.isdir(local_src):
            uri.copy(local_src, dest_mirror_uri)
            return dest_mirror_uri
            
        # 2. Remote HTTP/Git Download
        ok, res = self.act_fetch(provider_url, f"{module_name}/{version}/index.json")
        if not ok:
            ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if not ok:
            ok, res = self.act_fetch(provider_url, f"{module_name}/{version}/manifest.json")
            
        if ok and isinstance(res, dict):
            # If provider declares files list in index.json
            files_list = res.get("files")
            if files_list and isinstance(files_list, list):
                for rel_f in files_list:
                    f_ok, f_content = self.act_fetch(provider_url, f"{module_name}/{version}/{rel_f}")
                    if not f_ok:
                        f_ok, f_content = self.act_fetch(provider_url, f"{module_name}/{rel_f}")
                    if f_ok:
                        out_uri = f"{dest_mirror_uri}/{rel_f}"
                        if isinstance(f_content, (dict, list)):
                            uri.write_json(out_uri, f_content)
                        else:
                            uri.write_text(out_uri, str(f_content))
                    else:
                        uri.rmtree(dest_mirror_uri)
                        raise RuntimeError(f"Failed to fetch file '{rel_f}' for module '{module_name}@{version}' from provider.")
                return dest_mirror_uri
            else:
                # Direct manifest
                uri.write_json(f"{dest_mirror_uri}/manifest.json", res)
                return dest_mirror_uri

        if not uri.exists(f"{dest_mirror_uri}/manifest.json"):
            raise FileNotFoundError(f"Cannot find package '{module_name}@{version}' from provider '{provider_url}'.")
        return dest_mirror_uri

    def act_delete(self, module_name: str, version: Optional[str] = None) -> None:
        if version:
            uri.rmtree(f"mirror://{module_name}/{version}/")
        else:
            uri.rmtree(f"mirror://{module_name}/")

    def act_register(self, module_name: str, version: str, provider: str, description: str = "") -> None:
        cfg_uri, cfg = self._get_config()
        if "installed_modules" not in cfg:
            cfg["installed_modules"] = {}
        cfg["installed_modules"][module_name] = {
            "version": version,
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": provider,
            "description": description or f"Module {module_name}"
        }
        self._save_config(cfg)

    def act_unregister(self, module_name: str) -> None:
        cfg_uri, cfg = self._get_config()
        if "installed_modules" in cfg and module_name in cfg["installed_modules"]:
            del cfg["installed_modules"][module_name]
            self._save_config(cfg)

    def _parse_dependencies(self, raw_deps: Any) -> Dict[str, str]:
        """
        Parses dependencies from manifest supporting both dict and list schemas.
        e.g. {"core": ">=1.0.0"} or ["core >=1.0.0", "dev"]
        """
        parsed: Dict[str, str] = {}
        if isinstance(raw_deps, dict):
            for k, v in raw_deps.items():
                parsed[k] = str(v) if v else "*"
        elif isinstance(raw_deps, list):
            for item in raw_deps:
                if isinstance(item, str):
                    parts = item.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        parsed[parts[0]] = parts[1]
                    elif len(parts) == 1:
                        parsed[parts[0]] = "*"
        return parsed

    def _get_module_manifest_from_provider_or_local(self, module_name: str, provider_url: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Helper to load manifest for dependency solving."""
        # 1. Try local mirror first
        if version and uri.exists(f"mirror://{module_name}/{version}/manifest.json"):
            return uri.read_json(f"mirror://{module_name}/{version}/manifest.json")
        # 2. Try installed
        if uri.exists(f"module.root://{module_name}/manifest.json"):
            return uri.read_json(f"module.root://{module_name}/manifest.json")
        # 3. Try provider
        cand_dirs = [
            os.path.join(provider_url, module_name),
            os.path.join(provider_url, "build", module_name)
        ]
        for c_dir in cand_dirs:
            if os.path.isdir(c_dir):
                # Check exact version dir
                if version and os.path.isfile(os.path.join(c_dir, version, "manifest.json")):
                    with open(os.path.join(c_dir, version, "manifest.json"), "r", encoding="utf-8") as f:
                        return json.load(f)
                # Check root manifest
                if os.path.isfile(os.path.join(c_dir, "manifest.json")):
                    with open(os.path.join(c_dir, "manifest.json"), "r", encoding="utf-8") as f:
                        return json.load(f)
                # Scan subdirectories for highest/matching version
                sub_vers = [v for v in os.listdir(c_dir) if os.path.isfile(os.path.join(c_dir, v, "manifest.json"))]
                if sub_vers:
                    latest = sorted(sub_vers)[-1]
                    with open(os.path.join(c_dir, latest, "manifest.json"), "r", encoding="utf-8") as f:
                        return json.load(f)
        return {"name": module_name, "version": version or "1.0.0", "dependencies": {}}

    def act_solve_deps(
        self, 
        target_module: str, 
        version_constraint: Optional[str], 
        provider_url: str
    ) -> List[Tuple[str, str]]:
        """
        Recursively resolves dependency topology with cycle detection.
        Returns ordered installation list: [(dep_1, ver_1), ..., (target, target_ver)]
        """
        target_ver = version_constraint or "1.0.0"
        ordered_list: List[Tuple[str, str]] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def _solve(mod_name: str, ver_req: str):
            if mod_name in visiting:
                raise ValueError(f"Circular dependency detected in module dependencies: '{mod_name}' is required by another module in the call chain.")
            if mod_name in visited:
                return
                
            visiting.add(mod_name)
            manifest = self._get_module_manifest_from_provider_or_local(mod_name, provider_url, ver_req)
            raw_deps = manifest.get("dependencies", {})
            parsed_deps = self._parse_dependencies(raw_deps)
            
            for dep_name, dep_ver in parsed_deps.items():
                if dep_name != "core":  # core is infrastructure baseline
                    _solve(dep_name, dep_ver)
                    
            visiting.remove(mod_name)
            visited.add(mod_name)
            resolved_ver = manifest.get("version", ver_req or "1.0.0")
            ordered_list.append((mod_name, resolved_ver))

        _solve(target_module, target_ver)
        return ordered_list

    def act_prepare(self, target_list: List[Tuple[str, str]], provider_url: str, force: bool = False) -> None:
        for mod, ver in target_list:
            mirror_manifest = f"mirror://{mod}/{ver}/manifest.json"
            if force or not uri.exists(mirror_manifest):
                self.act_download(mod, ver, provider_url)

    def _deep_infill_dict(self, base: Dict[str, Any], template: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Recursively in-fills missing keys from template into base dictionary.
        Existing keys and user-defined values in base are 100% preserved.
        """
        changed = False
        result = dict(base)
        for k, v in template.items():
            if k not in result:
                result[k] = v
                changed = True
            elif isinstance(result[k], dict) and isinstance(v, dict):
                sub_res, sub_changed = self._deep_infill_dict(result[k], v)
                result[k] = sub_res
                if sub_changed:
                    changed = True
        return result, changed

    def _seed_or_update_config(self, module_name: str, template_dir_or_uri: str) -> None:
        """
        Auto-seeds default config.project.json / config.local.json if missing,
        or recursively in-fills missing keys if already exists.
        """
        target_cfg_dir = f"config.root://{module_name}"
        uri.makedirs(target_cfg_dir, exist_ok=True)
        
        for cfg_filename in ["config.project.json", "config.local.json"]:
            tpl_uri = f"{template_dir_or_uri}/{cfg_filename}"
            if uri.exists(tpl_uri):
                target_uri = f"{target_cfg_dir}/{cfg_filename}"
                tpl_data = uri.read_json(tpl_uri)
                if not uri.exists(target_uri):
                    # New seed
                    uri.write_json(target_uri, tpl_data, indent=2)
                else:
                    # Existing: recursive in-fill
                    try:
                        curr_data = uri.read_json(target_uri)
                        if isinstance(curr_data, dict) and isinstance(tpl_data, dict):
                            merged_data, changed = self._deep_infill_dict(curr_data, tpl_data)
                            if changed:
                                uri.write_json(target_uri, merged_data, indent=2)
                    except Exception:
                        pass

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        cfg_path, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        
        if clean_stage:
            uri.makedirs("module.root://")
            # 1. Clean materialization from mirror
            existing = uri.listdir("module.root://")
            for item in existing:
                if item not in installed:
                    uri.rmtree(f"module.root://{item}")
            
            for mod, meta in installed.items():
                ver = meta.get("version", "1.0.0")
                src_mirror = f"mirror://{mod}/{ver}/"
                dst_mod = f"module.root://{mod}/"
                if uri.exists(src_mirror):
                    uri.rmtree(dst_mod)
                    uri.copy(src_mirror, dst_mod)
                    # Automatically seed / in-fill module config
                    self._seed_or_update_config(mod, src_mirror)
                elif not uri.exists(dst_mod):
                    # Ensure minimal valid module
                    uri.makedirs(dst_mod)
                    uri.write_json(f"{dst_mod}/manifest.json", {"name": mod, "version": ver})

        if inject_stage:
            # 2. Contributes injection & events
            self.contributes_aggregator.scan_and_inject(clean=True)
            self.act_broadcast_event("core", "on_reload", ExecutionContext("core", "reload", []))

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        host_dir, _ = uri._find_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        uri.makedirs(snap_dir)
        if os.path.isfile(host_cfg):
            uri.copy(host_cfg, f"{snap_dir}/yscb.config.json")
        return snapshot_id

    def act_restore_snapshot(self, snapshot_id: str) -> None:
        host_dir, _ = uri._find_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snap_dir = f"snapshot://{snapshot_id}"
        snap_cfg = f"{snap_dir}/yscb.config.json"
        if not uri.exists(snap_cfg):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' does not exist.")
        uri.copy(snap_cfg, host_cfg)
        self.act_reload(clean_stage=True, inject_stage=True)

    def act_broadcast_event(
        self, 
        emit_module: str, 
        event_name: str, 
        context: Optional[ExecutionContext] = None
    ) -> Dict[str, Any]:
        """
        Broadcasts lifecycle events to all installed modules by scanning module.root://{mod}/scripts/hook.{emit_module}.py.
        Provides try-except exception isolation.
        """
        results = {}
        if not uri.exists("module.root://"):
            return results
            
        ctx = context or ExecutionContext(emit_module, event_name, [])
        for mod in uri.listdir("module.root://"):
            hook_file_uri = f"module.root://{mod}/scripts/hook.{emit_module}.py"
            if uri.exists(hook_file_uri):
                hook_real_path = uri.resolve(hook_file_uri)
                mod_key = f"_yscb_hook_{mod}_{emit_module}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_key, hook_real_path)
                    if spec and spec.loader:
                        hook_mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_key] = hook_mod
                        spec.loader.exec_module(hook_mod)
                        if hasattr(hook_mod, event_name):
                            handler_fn = getattr(hook_mod, event_name)
                            if callable(handler_fn):
                                handler_fn(ctx)
                                results[mod] = "success"
                except Exception as e:
                    results[mod] = f"warning: {e}"
                    print(f"[core:events] Warning: Hook '{mod}:hook.{emit_module}.py' failed on '{event_name}': {e}", file=sys.stderr)
        return results
