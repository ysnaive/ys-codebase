"""
Core Package Management Installer Subcommands (install, update, remove, list, status, rollback, reload).
Includes Major Boundary Lock & Incremental Migration Trigger.
"""
import os
import sys
from typing import Optional, List
from core import uri
from core.context import ExecutionContext
from core.engine import AtomicEngine
from core import semver

class Installer:
    def __init__(self):
        self.engine = AtomicEngine()

    def cmd_install(self, module_name: str, version: Optional[str] = None, provider: Optional[str] = None, force: bool = False) -> int:
        if not module_name:
            print("[core:install] Error: Module name is required.")
            return 1
        
        cfg_path, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            print("[core:install] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1
            
        target_ver = semver.normalize_version(version) if version else "1.0.0.0"
        
        print(f"[core:install] Resolving dependencies for '{module_name}'...")
        snap_id = self.engine.act_snapshot(f"pre_install_{module_name}")
        
        installed = cfg.get("installed_modules", {})
        old_ver = installed.get(module_name, {}).get("version", "0.0.0.0")

        try:
            self.engine.act_lock("install")
            targets = self.engine.act_solve_deps(module_name, target_ver, provider_url)
            self.engine.act_prepare(targets, provider_url, force=force)
            for mod, ver in targets:
                self.engine.act_register(mod, ver, provider_url)
            self.engine.act_reload(clean_stage=True, inject_stage=True)
            
            # Execute migration if upgrading
            if old_ver != "0.0.0.0" and semver.compare_semver(target_ver, old_ver) > 0:
                print(f"[core:install] Running migration ladder for '{module_name}' ({old_ver} -> {target_ver})...")
                self.engine.act_migrate(module_name, old_ver, target_ver)
                
            self.engine.act_broadcast_event("core", "on_installed", ExecutionContext("core", "install", [module_name, target_ver]))
            self.engine.act_unlock("install")
            print(f"[core:install] Successfully installed '{module_name}@{target_ver}'.")
            return 0
        except Exception as e:
            self.engine.act_unlock("install")
            print(f"[core:install] Error during install: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int:
        cfg_path, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            print("[core:update] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1
            
        installed = cfg.get("installed_modules", {})
        
        targets = [module_name] if module_name else list(installed.keys())
        if not targets:
            print("[core:update] No modules installed to update.")
            return 0
            
        print(f"[core:update] Checking updates for modules: {', '.join(targets)} (Major Lock active)...")
        snap_id = self.engine.act_snapshot("pre_update")
        
        updated_any = False
        try:
            self.engine.act_lock("update")
            for mod in targets:
                cur_ver = installed.get(mod, {}).get("version", "1.0.0.0")
                cur_t = semver.parse_semver(cur_ver)
                # Major Boundary Lock: constrain update within same major (e.g. ^1.0.0.0)
                major_constraint = f"^{cur_t.major}.{cur_t.minor}.{cur_t.patch}"
                latest_ver = cur_ver
                
                # Check available versions in release/ & provider
                candidate_dirs = [
                    os.path.join(provider_url, "release", mod),
                    os.path.join(provider_url, mod),
                    os.path.join(provider_url, "build", mod)
                ]
                
                found_versions: List[str] = []
                for c_dir in candidate_dirs:
                    if os.path.isdir(c_dir):
                        found_versions.extend([v for v in os.listdir(c_dir) if os.path.isdir(os.path.join(c_dir, v))])
                
                if not found_versions:
                    # Remote lookup
                    ok, res = self.engine.act_fetch(provider_url, f"{mod}/index.json")
                    if ok and isinstance(res, dict) and "versions" in res:
                        found_versions = res["versions"]
                        
                best_v = semver.find_best_version(found_versions, major_constraint)
                if best_v:
                    latest_ver = best_v

                if semver.compare_semver(latest_ver, cur_ver) > 0:
                    print(f"[core:update] Updating '{mod}' from {cur_ver} -> {latest_ver}...")
                    self.engine.act_prepare([(mod, latest_ver)], provider_url, force=True)
                    self.engine.act_register(mod, latest_ver, provider_url)
                    # Run migration ladder
                    self.engine.act_migrate(mod, cur_ver, latest_ver)
                    updated_any = True
                else:
                    print(f"[core:update] Module '{mod}' is already up-to-date (v{cur_ver}).")
            
            if updated_any:
                self.engine.act_reload(clean_stage=True, inject_stage=True)
                self.engine.act_broadcast_event("core", "on_update", ExecutionContext("core", "update", targets))
                print(f"[core:update] Update completed successfully.")
            self.engine.act_unlock("update")
            return 0
        except Exception as e:
            self.engine.act_unlock("update")
            print(f"[core:update] Error during update: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_remove(self, module_name: str, clean: bool = False, force: bool = False) -> int:
        if not module_name:
            print("[core:remove] Error: Module name is required.")
            return 1
            
        cfg_path, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        if module_name not in installed:
            print(f"[core:remove] Module '{module_name}' is not currently installed.")
            return 1
            
        if module_name == "core":
            print("[core:remove] Error: Cannot remove 'core' infrastructure module.")
            return 1
            
        dependents: List[str] = []
        for other_mod in installed.keys():
            if other_mod == module_name:
                continue
            manifest_uri = f"module.root://{other_mod}/manifest.json"
            if uri.exists(manifest_uri):
                try:
                    m_data = uri.read_json(manifest_uri)
                    deps = self.engine._parse_dependencies(m_data.get("dependencies", {}))
                    if module_name in deps:
                        dependents.append(other_mod)
                except Exception:
                    pass
                    
        if dependents:
            if not force:
                print(f"[core:remove] Error: Cannot remove '{module_name}' because it is required by: {', '.join(dependents)}. Use --force to override.")
                return 1
            else:
                print(f"[core:remove] Warning: Force removing '{module_name}' required by: {', '.join(dependents)}.")
            
        print(f"[core:remove] Removing module '{module_name}'...")
        self.engine.act_broadcast_event("core", "on_remove", ExecutionContext("core", "remove", [module_name]))
        self.engine.act_snapshot(f"pre_remove_{module_name}")
        self.engine.act_unregister(module_name)
        if clean:
            self.engine.act_delete(module_name)
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        print(f"[core:remove] Module '{module_name}' removed successfully.")
        return 0

    def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int:
        cfg_path, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        print("-" * 65)
        print(f"{'Module Name':<20} {'Version':<10} {'Provider':<15} {'Status':<15}")
        print("-" * 65)
        
        if not installed:
            print("  (No modules installed)")
        else:
            for mod, meta in installed.items():
                ver = meta.get("version", "unknown")
                prov = meta.get("provider", "local")
                status = "Installed" if uri.exists(f"module.root://{mod}") else "Missing files"
                print(f"{mod:<20} {ver:<10} {prov:<15} {status:<15}")
        print("-" * 65)
        return 0

    def cmd_status(self) -> int:
        cfg_path, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        print("=" * 60)
        print("YS-Codebase Core Health Diagnostic Report")
        print("=" * 60)
        print(f"YS-Codebase Root : {cfg.get('yscb_root', 'unknown')}")
        print(f"Total Modules    : {len(installed)}")
        
        healthy = True
        for mod, meta in installed.items():
            mod_exists = uri.exists(f"module.root://{mod}/manifest.json")
            cli_exists = uri.exists(f"module.root://{mod}/scripts/cli.py")
            if not mod_exists or not cli_exists:
                healthy = False
                print(f"  [!] {mod}: Incomplete (manifest={mod_exists}, cli={cli_exists})")
            else:
                print(f"  [*] {mod}@{meta.get('version')}: Healthy")
                
        print("-" * 60)
        print(f"Overall Status   : {'HEALTHY (100% Ready)' if healthy else 'DEGRADED (Run reload)'}")
        print("=" * 60)
        return 0 if healthy else 1

    def cmd_rollback(self, target: Optional[str] = None) -> int:
        if not uri.exists("snapshot://"):
            print("[core:rollback] No snapshots found.")
            return 1
            
        snaps = sorted(uri.listdir("snapshot://"))
        if not snaps:
            print("[core:rollback] No snapshots available.")
            return 1
            
        target_snap = target or snaps[-1]
        print(f"[core:rollback] Rolling back to snapshot '{target_snap}'...")
        try:
            self.engine.act_restore_snapshot(target_snap)
            print(f"[core:rollback] Successfully restored to '{target_snap}'.")
            return 0
        except Exception as e:
            print(f"[core:rollback] Rollback failed: {e}")
            return 1

    def cmd_reload(self) -> int:
        print("[core:reload] Reconciling runtime modules from mirror...")
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        print("[core:reload] Runtime environment reconciled and refreshed successfully.")
        return 0
