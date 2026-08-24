"""
Core Package Management Installer Subcommands (install, update, remove, list, status, rollback, reload).
"""
import os
import sys
from typing import Optional, List
from core import uri
from core.engine import AtomicEngine

class Installer:
    def __init__(self):
        self.engine = AtomicEngine()

    def cmd_install(self, module_name: str, version: Optional[str] = None, provider: Optional[str] = None) -> int:
        if not module_name:
            print("[core:install] Error: Module name is required.")
            return 1
        
        provider_url = provider or "default"
        target_ver = version or "1.0.0"
        
        print(f"[core:install] Resolving dependencies for '{module_name}'...")
        snap_id = self.engine.act_snapshot(f"pre_install_{module_name}")
        
        try:
            targets = self.engine.act_solve_deps(module_name, target_ver, provider_url)
            self.engine.act_prepare(targets, provider_url)
            for mod, ver in targets:
                self.engine.act_register(mod, ver, provider_url)
            self.engine.act_reload(clean_stage=True, inject_stage=True)
            print(f"[core:install] Successfully installed '{module_name}@{target_ver}'.")
            return 0
        except Exception as e:
            print(f"[core:install] Error during install: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int:
        provider_url = provider or "default"
        cfg_uri, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        targets = [module_name] if module_name else list(installed.keys())
        if not targets:
            print("[core:update] No modules installed to update.")
            return 0
            
        print(f"[core:update] Updating modules: {', '.join(targets)}...")
        self.engine.act_snapshot("pre_update")
        
        for mod in targets:
            ver = "1.1.0"
            self.engine.act_prepare([(mod, ver)], provider_url)
            self.engine.act_register(mod, ver, provider_url)
            
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        print(f"[core:update] Update completed successfully.")
        return 0

    def cmd_remove(self, module_name: str, clean: bool = False) -> int:
        if not module_name:
            print("[core:remove] Error: Module name is required.")
            return 1
            
        cfg_uri, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        if module_name not in installed:
            print(f"[core:remove] Module '{module_name}' is not currently installed.")
            return 1
            
        if module_name == "core":
            print("[core:remove] Error: Cannot remove 'core' infrastructure module.")
            return 1
            
        print(f"[core:remove] Removing module '{module_name}'...")
        self.engine.act_snapshot(f"pre_remove_{module_name}")
        self.engine.act_unregister(module_name)
        if clean:
            self.engine.act_delete(module_name)
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        print(f"[core:remove] Module '{module_name}' removed successfully.")
        return 0

    def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int:
        cfg_uri, cfg = self.engine._get_config()
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
        cfg_uri, cfg = self.engine._get_config()
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
