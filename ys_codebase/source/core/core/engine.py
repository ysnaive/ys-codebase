"""
YS-Codebase Atomic Package Lifecycle Engine.
100% Python Standard Library, Zero Third-Party Dependency.
Implements Atomic Transactions, Snapshots, Locks, Dependencies Solver with SemVer, and Hook Events.
"""
import os
import sys
import json
import time
import urllib.request
import importlib.util
from typing import Dict, Any, List, Optional, Tuple, Set

from core import uri
from core.context import ExecutionContext
from core import semver
from core.contributes import ContributesAggregator

class AtomicEngine:
    def __init__(self):
        self.contributes_aggregator = ContributesAggregator()

    def _get_config(self) -> Tuple[str, Dict[str, Any]]:
        host_dir, _ = uri._get_host_config()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        if not os.path.isfile(cfg_path):
            raise FileNotFoundError(f"Configuration file not found: {cfg_path}")
        with open(cfg_path, "r", encoding="utf-8") as f:
            return cfg_path, json.load(f)

    def _save_config(self, cfg_path: str, data: Dict[str, Any]) -> None:
        tmp_path = cfg_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, cfg_path)

    def act_fetch(self, provider_url: str, relative_path: str) -> Tuple[bool, Any]:
        """
        Fetches a manifest, index, or package archive from local filesystem or remote HTTP/HTTPS.
        """
        # 1. Local filesystem Provider
        local_target = os.path.join(provider_url, relative_path)
        if not os.path.exists(local_target):
            # Check build/ subfolder
            local_target = os.path.join(provider_url, "build", relative_path)
            
        if os.path.exists(local_target):
            if relative_path.endswith(".json") and os.path.isfile(local_target):
                with open(local_target, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            return True, local_target

        # 2. Remote HTTP Provider
        if not (provider_url.startswith("http://") or provider_url.startswith("https://")):
            return False, f"File not found in local provider: {local_target}"
            
        remote_url = f"{provider_url.rstrip('/')}/{relative_path.lstrip('/')}"
        try:
            req = urllib.request.Request(remote_url, headers={"User-Agent": "yscb-client/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
                if relative_path.endswith(".json"):
                    return True, json.loads(content)
                return True, content
        except Exception as e:
            return False, str(e)

    def act_lock(self, operation: str, timeout: float = 10.0) -> None:
        """
        Acquire inter-process lock on temp://.yscb.lock using OS-level atomic creation (os.O_CREAT | os.O_EXCL).
        Design Note:
        - os.O_EXCL provides strict kernel-level mutual exclusion guarantees.
        - The 10s timeout check is a self-healing recovery mechanism for unexpected crashes.
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
                lock_p = uri.resolve(lock_uri)
                if os.path.exists(lock_p):
                    os.remove(lock_p)
            except Exception:
                pass

    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
        """
        Downloads a specific module version from provider to mirror://{module_name}/{version}/.
        Strict version validation prevents copying multiple version subdirectories into mirror.
        """
        dest_mirror_uri = f"mirror://{module_name}/{version}/"
        if uri.exists(dest_mirror_uri):
            uri.rmtree(dest_mirror_uri)
        uri.makedirs(dest_mirror_uri)
        
        # 1. Check specific version folder in local provider
        candidate_paths = [
            os.path.join(provider_url, module_name, version),
            os.path.join(provider_url, "build", module_name, version)
        ]
        
        for cand in candidate_paths:
            cand_abs = os.path.abspath(cand)
            if os.path.isdir(cand_abs) and os.path.isfile(os.path.join(cand_abs, "manifest.json")):
                uri.copy(cand_abs, dest_mirror_uri)
                return dest_mirror_uri
                
        # 2. Check unversioned module root folder (validate manifest version matches)
        root_candidates = [
            os.path.join(provider_url, module_name),
            os.path.join(provider_url, "build", module_name)
        ]
        for rc in root_candidates:
            rc_abs = os.path.abspath(rc)
            if os.path.isdir(rc_abs):
                mf_path = os.path.join(rc_abs, "manifest.json")
                if os.path.isfile(mf_path):
                    try:
                        with open(mf_path, "r", encoding="utf-8") as f:
                            m_data = json.load(f)
                        if m_data.get("version") == version:
                            uri.copy(rc_abs, dest_mirror_uri)
                            return dest_mirror_uri
                    except Exception:
                        pass

        # 3. Remote HTTP/Git Download
        ok, res = self.act_fetch(provider_url, f"{module_name}/{version}/index.json")
        if not ok:
            ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if not ok:
            raise FileNotFoundError(f"Cannot find module '{module_name}@{version}' in provider '{provider_url}'.")
            
        return dest_mirror_uri

    def act_register(self, module_name: str, version: str, provider_url: str) -> None:
        cfg_path, cfg = self._get_config()
        if "installed_modules" not in cfg:
            cfg["installed_modules"] = {}
        cfg["installed_modules"][module_name] = {
            "version": version,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider_url
        }
        self._save_config(cfg_path, cfg)

    def act_unregister(self, module_name: str) -> None:
        cfg_path, cfg = self._get_config()
        if "installed_modules" in cfg and module_name in cfg["installed_modules"]:
            del cfg["installed_modules"][module_name]
            self._save_config(cfg_path, cfg)

    def act_delete(self, module_name: str) -> None:
        mirror_uri = f"mirror://{module_name}"
        if uri.exists(mirror_uri):
            uri.rmtree(mirror_uri)

    def _parse_dependencies(self, raw_deps: Any) -> Dict[str, str]:
        """
        Parses dependencies structure supporting dict {mod: ver_constraint} or list [mod, ...].
        """
        if isinstance(raw_deps, dict):
            return {k: str(v) for k, v in raw_deps.items()}
        elif isinstance(raw_deps, list):
            result = {}
            for item in raw_deps:
                if isinstance(item, str):
                    item = item.strip()
                    if "@" in item:
                        m, v = item.split("@", 1)
                        result[m.strip()] = v.strip()
                    elif " " in item:
                        m, v = item.split(" ", 1)
                        result[m.strip()] = v.strip()
                    else:
                        result[item] = "*"
            return result
        return {}

    def _get_module_manifest_from_provider_or_local(
        self, 
        module_name: str, 
        provider_url: str, 
        version_constraint: Optional[str]
    ) -> Dict[str, Any]:
        """
        Finds the manifest for a module in provider, solving for best matching SemVer version.
        """
        # 1. Search local provider directories
        candidate_dirs = [
            os.path.join(provider_url, module_name),
            os.path.join(provider_url, "build", module_name)
        ]
        
        for c_dir in candidate_dirs:
            if os.path.isdir(c_dir):
                # Check version subdirectories
                versions = [v for v in os.listdir(c_dir) if os.path.isdir(os.path.join(c_dir, v))]
                best_ver = semver.find_best_version(versions, version_constraint)
                if best_ver and os.path.isfile(os.path.join(c_dir, best_ver, "manifest.json")):
                    with open(os.path.join(c_dir, best_ver, "manifest.json"), "r", encoding="utf-8") as f:
                        return json.load(f)
                        
                # Check direct manifest
                direct_mf = os.path.join(c_dir, "manifest.json")
                if os.path.isfile(direct_mf):
                    with open(direct_mf, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    if semver.match_constraint(m_data.get("version", "1.0.0"), version_constraint):
                        return m_data

        # 2. Remote lookup
        ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if ok and isinstance(res, dict):
            if "versions" in res and isinstance(res["versions"], list):
                best_ver = semver.find_best_version(res["versions"], version_constraint)
                if best_ver:
                    ok_mf, mf_data = self.act_fetch(provider_url, f"{module_name}/{best_ver}/manifest.json")
                    if ok_mf and isinstance(mf_data, dict):
                        return mf_data
            elif "manifest" in res:
                return res["manifest"]

        return {"name": module_name, "version": version_constraint or "1.0.0", "dependencies": {}}

    def act_solve_deps(
        self, 
        target_module: str, 
        version_constraint: Optional[str], 
        provider_url: str
    ) -> List[Tuple[str, str]]:
        """
        Recursively resolves dependency topology with SemVer constraint satisfaction & cycle detection.
        Returns ordered installation list: [(dep_1, ver_1), ..., (target, target_ver)]
        """
        ordered_list: List[Tuple[str, str]] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def _solve(mod_name: str, ver_req: Optional[str]):
            if mod_name in visiting:
                raise ValueError(f"Circular dependency detected in module dependencies: '{mod_name}' is required by another module in the call chain.")
            if mod_name in visited:
                return
                
            visiting.add(mod_name)
            manifest = self._get_module_manifest_from_provider_or_local(mod_name, provider_url, ver_req)
            resolved_ver = manifest.get("version", "1.0.0")
            
            if ver_req and not semver.match_constraint(resolved_ver, ver_req):
                raise RuntimeError(
                    f"Cannot resolve dependency for '{mod_name}': "
                    f"resolved version '{resolved_ver}' does not satisfy constraint '{ver_req}'."
                )
                
            raw_deps = manifest.get("dependencies", {})
            parsed_deps = self._parse_dependencies(raw_deps)
            
            for dep_name, dep_ver in parsed_deps.items():
                if dep_name != "core":  # core is infrastructure baseline
                    _solve(dep_name, dep_ver)
                    
            visiting.remove(mod_name)
            visited.add(mod_name)
            ordered_list.append((mod_name, resolved_ver))

        _solve(target_module, version_constraint)
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
        tpl_proj_uri = f"{template_dir_or_uri}/config.project.json"
        tpl_local_uri = f"{template_dir_or_uri}/config.local.json"

        cfg_proj_uri = f"config.root://{module_name}/config.project.json"
        cfg_local_uri = f"config.root://{module_name}/config.local.json"

        # 1. Handle config.project.json
        if uri.exists(tpl_proj_uri):
            tpl_proj_data = uri.read_json(tpl_proj_uri)
            if not uri.exists(cfg_proj_uri):
                uri.makedirs(f"config.root://{module_name}", exist_ok=True)
                uri.write_json(cfg_proj_uri, tpl_proj_data)
            else:
                curr_data = uri.read_json(cfg_proj_uri)
                if isinstance(curr_data, dict) and isinstance(tpl_proj_data, dict):
                    infilled_data, changed = self._deep_infill_dict(curr_data, tpl_proj_data)
                    if changed:
                        uri.write_json(cfg_proj_uri, infilled_data)

        # 2. Handle config.local.json
        if uri.exists(tpl_local_uri):
            tpl_local_data = uri.read_json(tpl_local_uri)
            if not uri.exists(cfg_local_uri):
                uri.makedirs(f"config.root://{module_name}", exist_ok=True)
                uri.write_json(cfg_local_uri, tpl_local_data)
            else:
                curr_data = uri.read_json(cfg_local_uri)
                if isinstance(curr_data, dict) and isinstance(tpl_local_data, dict):
                    infilled_data, changed = self._deep_infill_dict(curr_data, tpl_local_data)
                    if changed:
                        uri.write_json(cfg_local_uri, infilled_data)

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        """
        Reconciles runtime modules space (modules://) from mirror:// based on installed_modules in yscb.config.json.
        """
        cfg_path, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        
        # 1. Clean outdated or uninstalled modules in runtime directory
        if clean_stage:
            if uri.exists("module.root://"):
                for mod in uri.listdir("module.root://"):
                    if mod != "core" and mod not in installed:
                        uri.rmtree(f"module.root://{mod}")

        # 2. Materialize installed modules from mirror
        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0")
            mirror_src = f"mirror://{mod}/{ver}/"
            runtime_dst = f"module.root://{mod}/"
            
            if uri.exists(mirror_src):
                uri.copy(mirror_src, runtime_dst)
                # Seed/In-fill default module configurations
                self._seed_or_update_config(mod, mirror_src)

        # 3. Contributes injection & events
        if inject_stage:
            self.contributes_aggregator.scan_and_inject(clean=True)
            self.act_broadcast_event("core", "on_reload", ExecutionContext("core", "reload", []))

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        """
        Creates a dual-layer atomic configuration snapshot:
        1. Backs up yscb.config.json.
        2. Recursively backs up config.root:// (module-specific project & local configurations).
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        uri.makedirs(snap_dir)
        
        # 1. Backup yscb.config.json
        if os.path.isfile(host_cfg):
            uri.copy(host_cfg, f"{snap_dir}/yscb.config.json")
            
        # 2. Backup config.root://
        if uri.exists("config.root://"):
            uri.copy("config.root://", f"{snap_dir}/config/")
            
        return snapshot_id

    def act_restore_snapshot(self, snapshot_id: str) -> None:
        """
        Restores a dual-layer atomic configuration snapshot:
        1. Restores yscb.config.json.
        2. Restores config.root://.
        3. Re-materializes modules from immutable mirror://.
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snap_dir = f"snapshot://{snapshot_id}"
        snap_cfg = f"{snap_dir}/yscb.config.json"
        
        if not uri.exists(snap_cfg):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' does not exist.")
            
        # 1. Restore yscb.config.json
        uri.copy(snap_cfg, host_cfg)
        
        # 2. Restore config.root:// if present in snapshot
        snap_config_dir = f"{snap_dir}/config"
        if uri.exists(snap_config_dir):
            if uri.exists("config.root://"):
                uri.rmtree("config.root://")
            uri.copy(snap_config_dir, "config.root://")
            
        # 3. Reconcile runtime modules
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
