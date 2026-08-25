"""
YS-Codebase Atomic Package Lifecycle Engine.
100% Python Standard Library, Zero Third-Party Dependency.
Implements:
- 3-Tier Resolution Chain (build:// -> mirror:// -> provider)
- 4-Segment SemVer Dependency Solving
- Dual-Layer Snapshots & Atomic Rollback (modules/, config/, storage/, yscb.config.json)
- Incremental Migration Ladder Subsystem
"""
import os
import sys
import json
import time
import shutil
import zipfile
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
            # Check release/ or build/ subfolder
            local_target_rel = os.path.join(provider_url, "release", relative_path)
            if os.path.exists(local_target_rel):
                local_target = local_target_rel
            else:
                local_target_bld = os.path.join(provider_url, "build", relative_path)
                if os.path.exists(local_target_bld):
                    local_target = local_target_bld
            
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
        Downloads/Materializes a specific module version into module.mirror.root://{module_name}/{version}.zip.
        Enforces 3-Tier Resolution Chain (module.build.root:// -> module.release.root:// -> provider_url).
        """
        dest_mirror_dir = f"module.mirror.root://{module_name}"
        uri.makedirs(dest_mirror_dir)
        dest_zip_uri = f"{dest_mirror_dir}/{version}.zip"
        dest_zip_real = uri.resolve(dest_zip_uri)

        # 1. Tier 1: Check module.build.root:// for single zip
        build_root = f"module.build.root://{module_name}"
        v_tuple = semver.parse_semver(version)
        build_ver_str = f"{v_tuple.major}.{v_tuple.minor}.{v_tuple.patch}.build"
        build_zip_candidates = [
            f"{build_root}/{version}.zip",
            f"{build_root}/{version}.build.zip",
            f"{build_root}/{build_ver_str}.zip",
            f"{build_root}/{build_ver_str}.build.zip",
            f"{build_root}/1.0.0.build.zip"
        ]
        for b_zip in build_zip_candidates:
            if uri.exists(b_zip):
                shutil.copy2(uri.resolve(b_zip), dest_zip_real)
                return dest_zip_uri

        # 2. Tier 2: Check module.release.root:// or local directory provider
        rel_root = f"module.release.root://{module_name}"
        if uri.exists(f"{rel_root}/{version}.zip"):
            shutil.copy2(uri.resolve(f"{rel_root}/{version}.zip"), dest_zip_real)
            return dest_zip_uri

        p_abs = os.path.abspath(provider_url) if not provider_url.startswith(("http://", "https://", "file://")) else None
        if p_abs and os.path.isdir(p_abs):
            zip_candidates = [
                os.path.join(p_abs, module_name, f"{version}.zip"),
                os.path.join(p_abs, "release", module_name, f"{version}.zip"),
                os.path.join(p_abs, "build", module_name, f"{version}.zip"),
                os.path.join(p_abs, "build", module_name, f"{version}.build.zip"),
                os.path.join(p_abs, module_name, f"{version}.build.zip")
            ]
            for z_path in zip_candidates:
                if os.path.isfile(z_path):
                    shutil.copy2(z_path, dest_zip_real)
                    return dest_zip_uri

            # Fallback to packaging local directory if exists (backward compatibility)
            dir_candidates = [
                os.path.join(p_abs, module_name, version),
                os.path.join(p_abs, "release", module_name, version),
                os.path.join(p_abs, module_name)
            ]
            for d_path in dir_candidates:
                if os.path.isdir(d_path) and os.path.isfile(os.path.join(d_path, "manifest.json")):
                    with zipfile.ZipFile(dest_zip_real, "w", zipfile.ZIP_DEFLATED) as zf:
                        for root, _, files in os.walk(d_path):
                            for f in files:
                                f_p = os.path.join(root, f)
                                arc = os.path.relpath(f_p, d_path).replace("\\", "/")
                                zf.write(f_p, arcname=arc)
                    return dest_zip_uri

        # 3. Tier 3: Remote HTTP Provider (Download single-file <version>.zip)
        if not provider_url.startswith(("http://", "https://", "file://")):
            raise FileNotFoundError(f"Cannot find module '{module_name}@{version}' in provider '{provider_url}'.")

        remote_zip_url = provider_url.rstrip("/") + f"/{module_name}/{version}.zip"
        tmp_zip = dest_zip_real + ".tmp"
        try:
            req = urllib.request.Request(remote_zip_url, headers={"User-Agent": "yscb-core/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(tmp_zip, "wb") as f:
                    shutil.copyfileobj(resp, f)
                    
            if not zipfile.is_zipfile(tmp_zip):
                raise RuntimeError(f"Downloaded file from '{remote_zip_url}' is not a valid zip archive.")
                
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                if zf.testzip() is not None:
                    raise RuntimeError(f"Corrupted zip archive from '{remote_zip_url}'.")
                    
            if os.path.exists(dest_zip_real):
                os.remove(dest_zip_real)
            os.replace(tmp_zip, dest_zip_real)
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)

        return dest_zip_uri

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
        # 1. Tier 1: Check build://
        build_root_uri = f"module.build.root://{module_name}"
        if uri.exists(f"{build_root_uri}/index.json"):
            try:
                b_idx = uri.read_json(f"{build_root_uri}/index.json")
                b_versions = b_idx.get("versions", [])
                best_bld = semver.find_best_version(b_versions, version_constraint)
                if best_bld:
                    # Check zip in build root
                    b_zip_uri = f"{build_root_uri}/{best_bld}.zip"
                    if uri.exists(b_zip_uri):
                        with zipfile.ZipFile(uri.resolve(b_zip_uri), "r") as zf:
                            return json.loads(zf.read("manifest.json").decode("utf-8"))
                    if uri.exists(f"{build_root_uri}/{best_bld}/manifest.json"):
                        return uri.read_json(f"{build_root_uri}/{best_bld}/manifest.json")
            except Exception:
                pass

        # 2. Tier 2: Check release/ & local provider zip / index.json
        p_abs = os.path.abspath(provider_url) if not provider_url.startswith(("http://", "https://", "file://")) else None
        if p_abs and os.path.isdir(p_abs):
            candidate_indexes = [
                os.path.join(p_abs, module_name, "index.json"),
                os.path.join(p_abs, "release", module_name, "index.json"),
                os.path.join(p_abs, "build", module_name, "index.json")
            ]
            for idx_p in candidate_indexes:
                if os.path.isfile(idx_p):
                    try:
                        with open(idx_p, "r", encoding="utf-8") as f:
                            idx_data = json.load(f)
                        vers = idx_data.get("versions", [])
                        best_v = semver.find_best_version(vers, version_constraint)
                        if best_v:
                            mod_dir = os.path.dirname(idx_p)
                            zip_p = os.path.join(mod_dir, f"{best_v}.zip")
                            if os.path.isfile(zip_p):
                                with zipfile.ZipFile(zip_p, "r") as zf:
                                    return json.loads(zf.read("manifest.json").decode("utf-8"))
                    except Exception:
                        pass
            # Fallback to local directory scanning
            candidate_dirs = [
                os.path.join(p_abs, "release", module_name),
                os.path.join(p_abs, module_name),
                os.path.join(p_abs, "build", module_name)
            ]
            for c_dir in candidate_dirs:
                if os.path.isdir(c_dir):
                    versions = [v for v in os.listdir(c_dir) if os.path.isdir(os.path.join(c_dir, v))]
                    best_ver = semver.find_best_version(versions, version_constraint)
                    if best_ver and os.path.isfile(os.path.join(c_dir, best_ver, "manifest.json")):
                        with open(os.path.join(c_dir, best_ver, "manifest.json"), "r", encoding="utf-8") as f:
                            return json.load(f)
                    direct_mf = os.path.join(c_dir, "manifest.json")
                    if os.path.isfile(direct_mf):
                        with open(direct_mf, "r", encoding="utf-8") as f:
                            m_data = json.load(f)
                        if semver.match_constraint(m_data.get("version", "1.0.0.0"), version_constraint):
                            return m_data

        # 3. Tier 3: Remote lookup via index.json
        ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if ok and isinstance(res, dict):
            if "versions" in res and isinstance(res["versions"], list):
                best_ver = semver.find_best_version(res["versions"], version_constraint)
                if best_ver:
                    # Return basic manifest metadata
                    return {"name": module_name, "version": best_ver, "dependencies": {}}
            elif "manifest" in res:
                return res["manifest"]

        return {"name": module_name, "version": version_constraint or "1.0.0.0", "dependencies": {}}

    def act_solve_deps(
        self, 
        target_module: str, 
        version_constraint: Optional[str], 
        provider_url: str
    ) -> List[Tuple[str, str]]:
        """
        Recursively resolves dependency topology with 4-segment SemVer constraint satisfaction.
        """
        ordered_list: List[Tuple[str, str]] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def _solve(mod_name: str, ver_req: Optional[str]):
            if mod_name in visiting:
                raise ValueError(f"Circular dependency detected: '{mod_name}' in call chain.")
            if mod_name in visited:
                return
                
            visiting.add(mod_name)
            manifest = self._get_module_manifest_from_provider_or_local(mod_name, provider_url, ver_req)
            resolved_ver = manifest.get("version", "1.0.0.0")
            
            if ver_req and not semver.match_constraint(resolved_ver, ver_req):
                raise RuntimeError(
                    f"Cannot resolve dependency for '{mod_name}': "
                    f"resolved version '{resolved_ver}' does not satisfy constraint '{ver_req}'."
                )
                
            raw_deps = manifest.get("dependencies", {})
            parsed_deps = self._parse_dependencies(raw_deps)
            
            for dep_name, dep_ver in parsed_deps.items():
                if dep_name != "core":
                    _solve(dep_name, dep_ver)
                    
            visiting.remove(mod_name)
            visited.add(mod_name)
            ordered_list.append((mod_name, resolved_ver))

        _solve(target_module, version_constraint)
        return ordered_list

    def act_prepare(self, target_list: List[Tuple[str, str]], provider_url: str, force: bool = False) -> None:
        for mod, ver in target_list:
            mirror_zip = f"mirror://{mod}/{ver}.zip"
            if force or not uri.exists(mirror_zip):
                self.act_download(mod, ver, provider_url)

    def _deep_infill_dict(self, base: Dict[str, Any], template: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
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
        tpl_proj_uri = f"{template_dir_or_uri}/config.project.json"
        tpl_local_uri = f"{template_dir_or_uri}/config.local.json"

        cfg_proj_uri = f"config.root://{module_name}/config.project.json"
        cfg_local_uri = f"config.root://{module_name}/config.local.json"

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

    def act_deploy_configs_from_modules(self) -> None:
        """
        Stage 3 (Atomic Config Deployment & Template Purge):
        Scans all modules in module.root://, infills/deploys configuration to config.root://,
        and unconditionally physically deletes config.*.json template files from modules/ to maintain pure code.
        """
        if not uri.exists("module.root://"):
            return
            
        for mod in uri.listdir("module.root://"):
            mod_real = uri.resolve(f"module.root://{mod}")
            if not os.path.isdir(mod_real):
                continue

        cfg_path, host_cfg = self._get_config()
        installed = host_cfg.get("installed_modules", {})

        for mod in uri.listdir("module.root://"):
            if mod not in installed and mod != "core":
                continue
            
            mod_runtime_dir = f"module.root://{mod}"
            if not uri.isdir(mod_runtime_dir):
                continue
            
            config_templates = [
                f for f in uri.listdir(mod_runtime_dir) 
                if (f.startswith("config.") and f.endswith(".json")) or f == "config.json"
            ]
            
            for tmpl_file in config_templates:
                tmpl_uri = f"{mod_runtime_dir}/{tmpl_file}"
                tmpl_data = uri.read_json(tmpl_uri)
                if not isinstance(tmpl_data, dict):
                    continue

                if tmpl_file == "config.local.json":
                    target_cfg_uri = f"config.root://{mod}/config.local.json"
                elif tmpl_file == "config.project.json":
                    target_cfg_uri = f"config.root://{mod}/config.project.json"
                elif tmpl_file.startswith("config.") and tmpl_file.endswith(".local.json"):
                    sub_name = tmpl_file[len("config."):-len(".local.json")]
                    target_cfg_uri = f"config.root://{mod}/config.{sub_name}.local.json"
                elif tmpl_file.startswith("config.") and tmpl_file.endswith(".project.json"):
                    sub_name = tmpl_file[len("config."):-len(".project.json")]
                    target_cfg_uri = f"config.root://{mod}/config.{sub_name}.project.json"
                else:
                    target_cfg_uri = f"config.root://{mod}/config.project.json"

                target_data = {}
                if uri.exists(target_cfg_uri):
                    try:
                        target_data = uri.read_json(target_cfg_uri)
                    except Exception:
                        target_data = {}

                merged_data, changed = self._deep_infill_dict(target_data, tmpl_data)

                if changed or not uri.exists(target_cfg_uri):
                    uri.makedirs(f"config.root://{mod}", exist_ok=True)
                    uri.write_json(target_cfg_uri, merged_data, indent=2)

                uri.remove(tmpl_uri)

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        """
        4-Stage Atomic Reload Pipeline:
        Stage 1 (自癒拉取) -> Stage 2 (解壓物化) -> Stage 3 (組態治理) -> Stage 4 (依賴注入與事件廣播)
        """
        cfg_path, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        default_prov = cfg.get("default_provider", "")
        
        # Stage 1: 拉取/還原壓縮來源檔 (若 module.mirror.root:// 缺少單檔 zip，自癒補齊)
        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0")
            prov = meta.get("provider") or default_prov
            mirror_zip = f"module.mirror.root://{mod}/{ver}.zip"
            if not uri.exists(mirror_zip):
                try:
                    self.act_download(mod, ver, prov)
                except Exception:
                    pass

        # Stage 2: 解壓並部署至 modules/
        if clean_stage and uri.exists("module.root://"):
            for mod in uri.listdir("module.root://"):
                if mod != "core" and mod not in installed:
                    uri.rmtree(f"module.root://{mod}")

        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0")
            mirror_zip = f"module.mirror.root://{mod}/{ver}.zip"
            runtime_dst = f"module.root://{mod}/"
            real_dst = uri.resolve(runtime_dst)
            
            if uri.exists(mirror_zip):
                real_zip = uri.resolve(mirror_zip)
                if os.path.exists(real_dst):
                    shutil.rmtree(real_dst, ignore_errors=True)
                with zipfile.ZipFile(real_zip, "r") as zf:
                    real_dst_abs = os.path.abspath(real_dst)
                    for member in zf.infolist():
                        target_path = os.path.abspath(os.path.join(real_dst_abs, member.filename))
                        if not target_path.startswith(real_dst_abs + os.sep) and target_path != real_dst_abs:
                            raise RuntimeError(
                                f"Zip Slip vulnerability detected: '{member.filename}' in mirror '{mirror_zip}' "
                                f"attempts to extract outside destination '{real_dst}'."
                            )
                    zf.extractall(real_dst)
            elif uri.exists(f"module.mirror.root://{mod}/{ver}/"):
                mirror_src = f"module.mirror.root://{mod}/{ver}/"
                if os.path.exists(real_dst):
                    shutil.rmtree(real_dst, ignore_errors=True)
                uri.copy(mirror_src, runtime_dst)

        # Stage 3: 掃描並部署組態 (原子提取並無條件清除模板)
        self.act_deploy_configs_from_modules()

        # Stage 4: 依賴注入與事件廣播
        if inject_stage:
            self.contributes_aggregator.scan_and_inject(clean=True)
            self.act_broadcast_event("core", "on_reload", ExecutionContext("core", "reload", []))

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        """
        Creates a full atomic snapshot:
        1. Backs up yscb.config.json.
        2. Backs up config.root:// (config/).
        3. Backs up storage.root:// (storage/).
        4. Backs up module.root:// (modules/).
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        uri.makedirs(snap_dir)
        
        # 1. yscb.config.json
        if os.path.isfile(host_cfg):
            uri.copy(host_cfg, f"{snap_dir}/yscb.config.json")
            
        # 2. config/
        if uri.exists("config.root://"):
            uri.copy("config.root://", f"{snap_dir}/config/")
            
        # 3. storage/
        if uri.exists("storage.root://"):
            uri.copy("storage.root://", f"{snap_dir}/storage/")
            
        # 4. modules/
        if uri.exists("module.root://"):
            uri.copy("module.root://", f"{snap_dir}/modules/")
            
        return snapshot_id

    def act_restore_snapshot(self, snapshot_id: str) -> None:
        """
        Restores a full atomic snapshot:
        1. Restores yscb.config.json.
        2. Restores config/ and storage/.
        3. Restores modules/.
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snap_dir = f"snapshot://{snapshot_id}"
        snap_cfg = f"{snap_dir}/yscb.config.json"
        
        if not uri.exists(snap_cfg):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' does not exist.")
            
        # 1. Restore yscb.config.json
        uri.copy(snap_cfg, host_cfg)
        
        # 2. Restore config/
        snap_config_dir = f"{snap_dir}/config"
        if uri.exists(snap_config_dir):
            if uri.exists("config.root://"):
                uri.rmtree("config.root://")
            uri.copy(snap_config_dir, "config.root://")
            
        # 3. Restore storage/
        snap_storage_dir = f"{snap_dir}/storage"
        if uri.exists(snap_storage_dir):
            if uri.exists("storage.root://"):
                uri.rmtree("storage.root://")
            uri.copy(snap_storage_dir, "storage.root://")
            
        # 4. Restore modules/
        snap_mod_dir = f"{snap_dir}/modules"
        if uri.exists(snap_mod_dir):
            if uri.exists("module.root://"):
                uri.rmtree("module.root://")
            uri.copy(snap_mod_dir, "module.root://")

        self.act_reload(clean_stage=False, inject_stage=True)

    def act_migrate(self, module_name: str, old_version: str, new_version: str) -> bool:
        """
        Executes Incremental Migration Ladder:
        - Evaluates minor version differential: {major}.{minor}.x.py
        - Silently skips non-existent scripts.
        - Raises RuntimeError on script failure to trigger atomic snapshot rollback.
        """
        t_old = semver.parse_semver(old_version)
        t_new = semver.parse_semver(new_version)
        
        # Major breaking upgrade skips migration ladder
        if t_new.major != t_old.major:
            return True
            
        if t_new.minor <= t_old.minor:
            return True
            
        host_dir, yscb_dir = uri._get_host_config()
        storage_dir = uri.resolve(f"storage://{module_name}") if uri.exists(f"storage://{module_name}") else os.path.join(yscb_dir, "storage", module_name)
        
        context = {
            "host_dir": host_dir,
            "storage_dir": storage_dir,
            "old_version": old_version,
            "target_version": new_version
        }
        
        # Step through minor ladder (e.g. 1.0 -> 1.3 calls 1.1.x, 1.2.x, 1.3.x)
        for m in range(t_old.minor + 1, t_new.minor + 1):
            script_rel = f"scripts/migrations/{t_old.major}.{m}.x.py"
            mod_script_uri = f"module.root://{module_name}/{script_rel}"
            
            if uri.exists(mod_script_uri):
                script_real = uri.resolve(mod_script_uri)
                mod_key = f"_yscb_migrate_{module_name}_{t_old.major}_{m}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_key, script_real)
                    if spec and spec.loader:
                        migrate_mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_key] = migrate_mod
                        spec.loader.exec_module(migrate_mod)
                        if hasattr(migrate_mod, "migrate"):
                            res = migrate_mod.migrate(context)
                            if not res:
                                raise RuntimeError(f"Migration script '{script_rel}' returned False.")
                except Exception as e:
                    raise RuntimeError(f"Migration step '{script_rel}' failed for module '{module_name}': {e}")
                    
        return True

    def act_broadcast_event(
        self, 
        emit_module: str, 
        event_name: str, 
        context: Optional[ExecutionContext] = None
    ) -> Dict[str, Any]:
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

    def act_get_installed_commands_summary(self) -> Dict[str, Dict[str, str]]:
        """
        Scans installed modules in module.root:// to summarize contributed CLI commands.
        Returns: { module_name: { command_name: description } }
        """
        summary: Dict[str, Dict[str, str]] = {}
        if not uri.exists("module.root://"):
            return summary
            
        for mod_name in sorted(uri.listdir("module.root://")):
            if mod_name == "core":
                continue
            mf_uri = f"module.root://{mod_name}/manifest.json"
            if not uri.exists(mf_uri):
                continue
            try:
                mf_data = uri.read_json(mf_uri)
                mod_desc = mf_data.get("description", f"{mod_name} module")
                
                contrib = mf_data.get("contributes", {})
                cmds = contrib.get("commands", {})
                if cmds and isinstance(cmds, dict):
                    summary[mod_name] = {cmd: desc for cmd, desc in cmds.items()}
                else:
                    if mod_name == "dev":
                        summary["dev"] = {
                            "create": "Create a new module skeleton",
                            "check": "Validate module structure and manifest compliance",
                            "build": "Build dev package (.build.zip with tests)",
                            "test": "Run module tests inside an isolated sandbox",
                            "release": "Package and release pure module to release/"
                        }
                    else:
                        summary[mod_name] = {
                            "run": mod_desc
                        }
            except Exception:
                pass
                
        return summary
