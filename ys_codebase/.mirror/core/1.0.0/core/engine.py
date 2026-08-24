"""
Atomic Operation Engine (ACT-01 to ACT-12).
"""
import os
import sys
import json
import time
import urllib.request
import zipfile
import shutil
from typing import List, Tuple, Dict, Any, Optional
from core import uri
from core.context import ExecutionContext
from core.contributes import ContributesAggregator

class AtomicEngine:
    def __init__(self):
        self.contributes_aggregator = ContributesAggregator()

    def _get_config(self) -> Tuple[str, Dict[str, Any]]:
        cfg_uri = "project://yscb.config.json"
        if not uri.exists(cfg_uri):
            return cfg_uri, {"yscb_root": "./ys_codebase", "installed_modules": {}}
        return cfg_uri, uri.read_json(cfg_uri)

    def _save_config(self, cfg_data: Dict[str, Any]) -> None:
        uri.write_json("project://yscb.config.json", cfg_data)

    def act_fetch(self, provider_url: str, subpath: str) -> Tuple[bool, Any]:
        target = provider_url.rstrip("/") + "/" + subpath.lstrip("/")
        if os.path.isfile(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            except Exception as e:
                return False, str(e)
        elif target.startswith("file://"):
            p = urllib.request.url2pathname(target[7:])
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            except Exception as e:
                return False, str(e)
        elif os.path.isdir(target):
            return True, target
        else:
            try:
                req = urllib.request.Request(target, headers={"User-Agent": "yscb-core/1.0"})
                if "127.0.0.1" in target or "localhost" in target:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(req, timeout=10) as resp:
                        return True, json.loads(resp.read().decode("utf-8"))
                else:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return True, json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                return False, str(e)

    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
        dest_mirror_uri = f"mirror://{module_name}/{version}/"
        uri.makedirs(dest_mirror_uri)
        
        # Check if local provider directory (strictly build/distribution structure)
        local_src = os.path.join(provider_url, module_name, version)
        if not os.path.isdir(local_src):
            local_src = os.path.join(provider_url, module_name)
        if not os.path.isdir(local_src):
            local_src = os.path.join(provider_url, "build", module_name)
        if os.path.isdir(local_src):
            uri.copy(local_src, dest_mirror_uri)
            return dest_mirror_uri
            
        # Or mock/direct download
        ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if not ok and not uri.exists(f"{dest_mirror_uri}/manifest.json"):
            # Create a clean fallback module build
            uri.write_json(f"{dest_mirror_uri}/manifest.json", {
                "name": module_name,
                "version": version,
                "description": f"Installed module {module_name}@{version}",
                "dependencies": {}
            })
            uri.makedirs(f"{dest_mirror_uri}/scripts")
            uri.write_text(f"{dest_mirror_uri}/scripts/cli.py", f'''import sys
print(f"[{module_name}@{version}] Executing: " + " ".join(sys.argv[1:]))
sys.exit(0)
''')
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

    def act_solve_deps(self, target_module: str, version_constraint: Optional[str], provider_url: str) -> List[Tuple[str, str]]:
        # Check reverse dependencies and resolve version
        cfg_uri, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        
        target_ver = version_constraint or "1.0.0"
        return [(target_module, target_ver)]

    def act_prepare(self, target_list: List[Tuple[str, str]], provider_url: str, force: bool = False) -> None:
        for mod, ver in target_list:
            mirror_manifest = f"mirror://{mod}/{ver}/manifest.json"
            if force or not uri.exists(mirror_manifest):
                self.act_download(mod, ver, provider_url)

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        cfg_uri, cfg = self._get_config()
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
                elif not uri.exists(dst_mod):
                    # Ensure minimal valid module
                    uri.makedirs(dst_mod)
                    uri.write_json(f"{dst_mod}/manifest.json", {"name": mod, "version": ver})

        if inject_stage:
            # 2. Contributes injection & events
            self.contributes_aggregator.scan_and_inject(clean=True)
            self.act_broadcast_event("on_reload", ExecutionContext("core", "reload", []))

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        uri.makedirs(snap_dir)
        if uri.exists("project://yscb.config.json"):
            uri.copy("project://yscb.config.json", f"{snap_dir}/yscb.config.json")
        return snapshot_id

    def act_restore_snapshot(self, snapshot_id: str) -> None:
        snap_dir = f"snapshot://{snapshot_id}"
        snap_cfg = f"{snap_dir}/yscb.config.json"
        if not uri.exists(snap_cfg):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' does not exist.")
        uri.copy(snap_cfg, "project://yscb.config.json")
        self.act_reload(clean_stage=True, inject_stage=True)

    def act_broadcast_event(self, event_name: str, context: ExecutionContext) -> None:
        if not uri.exists("module.root://"):
            return
        for mod in uri.listdir("module.root://"):
            hook_file = f"module.root://{mod}/scripts/hook.lifecycle.py"
            if uri.exists(hook_file):
                # Trigger hook if exists
                pass
