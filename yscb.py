"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & CLI Router.
100% Python Standard Library, Zero Third-Party Dependency.
"""

from typing import List, Optional, Dict, Any, Tuple
import sys
import os
import json
import urllib.request
import subprocess
import shutil
import ast
import zipfile
import tempfile

CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/release"
CORE_COMMANDS: set = {
    "install",
    "update",
    "remove",
    "list",
    "status",
    "rollback",
    "reload"
}


def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    剛性組態載入 (Rigid Configuration Loader - Zero Speculation).
    僅探測指定目錄或當前目錄同層之 yscb.config.json，徹底杜絕向上爬樹導致的沙盒逃逸與環境污染。
    """
    curr = os.path.abspath(start_dir or os.getcwd())
    cfg_path = os.path.join(curr, CONFIG_FILENAME)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return cfg_path, json.load(f)
        except Exception:
            return cfg_path, None
    return None, None


def save_config(config_path: str, data: Dict[str, Any]) -> None:
    tmp_path = config_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, config_path)


def _generate_internal_gitignore(yscb_dir: str) -> None:
    """Generates yscb://.gitignore ensuring zero pollution to user project root."""
    gi_path = os.path.join(yscb_dir, ".gitignore")
    content = (
        "# YS-Codebase Autonomous Internal Ignore Rules\n"
        "/build/\n"
        "/.mirror/\n"
        "/.temp/\n"
        "/.snapshots/\n"
        "/.cache/\n"
        "*.local.json\n"
        "__pycache__/\n"
        "*.pyc\n"
    )
    try:
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


def _fetch_and_extract_zip(source_url_or_path: str, dest_dir: str) -> None:
    """
    Fetches a module zip (from local path or remote URL) and extracts cleanly to dest_dir.
    Purges any config.*.json templates from dest_dir to maintain pure code.
    """
    os.makedirs(dest_dir, exist_ok=True)
    
    if source_url_or_path.startswith(("http://", "https://")):
        # Remote HTTP Download
        req = urllib.request.Request(source_url_or_path, headers={"User-Agent": "yscb-host/2.0"})
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
            tmp_path = tmp_f.name
            
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(tmp_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                    
            if not zipfile.is_zipfile(tmp_path):
                raise RuntimeError(f"Downloaded payload from '{source_url_or_path}' is not a valid zip file.")
                
            with zipfile.ZipFile(tmp_path, "r") as zf:
                if zf.testzip() is not None:
                    raise RuntimeError(f"Corrupted zip archive from '{source_url_or_path}'.")
                zf.extractall(dest_dir)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    else:
        # Local path
        p_abs = os.path.abspath(source_url_or_path)
        if os.path.isfile(p_abs) and (p_abs.endswith(".zip") or zipfile.is_zipfile(p_abs)):
            with zipfile.ZipFile(p_abs, "r") as zf:
                zf.extractall(dest_dir)
        elif os.path.isdir(p_abs):
            for item in os.listdir(p_abs):
                s = os.path.join(p_abs, item)
                d = os.path.join(dest_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
        else:
            raise FileNotFoundError(f"Source package not found at '{source_url_or_path}'.")

    # Purge config.*.json templates from extracted runtime directory
    for cfg_tpl in ("config.project.json", "config.local.json"):
        tpl_p = os.path.join(dest_dir, cfg_tpl)
        if os.path.isfile(tpl_p):
            try:
                os.remove(tpl_p)
            except Exception:
                pass


def cmd_init(argv: List[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print("[yscb] Usage: python yscb.py init <yscbRoot> [--provider=<source>]")
        return 1

    yscb_root_arg = argv[0]
    provider_arg = DEFAULT_PROVIDER_URL
    for arg in argv[1:]:
        if arg.startswith("--provider="):
            provider_arg = arg.split("=", 1)[1].strip("\"'")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(script_dir, CONFIG_FILENAME)

    if os.path.isfile(cfg_path):
        _, existing_cfg = load_config(script_dir)
        if existing_cfg and existing_cfg.get("yscb_root"):
            print(f"[yscb] Error: Environment already initialized with yscb_root='{existing_cfg['yscb_root']}'.")
            return 1

    yscb_abs = os.path.normpath(os.path.join(script_dir, yscb_root_arg))
    os.makedirs(yscb_abs, exist_ok=True)
    os.makedirs(os.path.join(yscb_abs, "modules"), exist_ok=True)
    os.makedirs(os.path.join(yscb_abs, ".mirror"), exist_ok=True)

    # Generate yscb://.gitignore autonomously
    _generate_internal_gitignore(yscb_abs)

    init_cfg = {
        "yscb_root": yscb_root_arg,
        "default_provider": provider_arg,
        "installed_modules": {}
    }

    core_mirror_dir = os.path.join(yscb_abs, ".mirror", "core")
    os.makedirs(core_mirror_dir, exist_ok=True)
    core_module = os.path.join(yscb_abs, "modules", "core")

    # Case A: Local directory provider
    p_abs = os.path.abspath(provider_arg) if not provider_arg.startswith(("http://", "https://", "file://")) else None
    if p_abs and os.path.isdir(p_abs):
        # Check for single zip or unpacked directory in local provider
        local_zip_candidates = [
            os.path.join(p_abs, "core", "1.0.0.0.zip"),
            os.path.join(p_abs, "core", "1.0.0.build.zip"),
            os.path.join(p_abs, "release", "core", "1.0.0.0.zip"),
            os.path.join(p_abs, "build", "core", "1.0.0.build.zip")
        ]
        found_zip = next((z for z in local_zip_candidates if os.path.isfile(z)), None)
        c_ver = "1.0.0.0"
        
        if found_zip:
            print(f"[yscb] Bootstrapping 'core' infrastructure module from local zip: {found_zip}")
            _fetch_and_extract_zip(found_zip, core_module)
            # Read version
            mf_path = os.path.join(core_module, "manifest.json")
            if os.path.isfile(mf_path):
                try:
                    with open(mf_path, "r", encoding="utf-8") as f:
                        c_ver = json.load(f).get("version", c_ver)
                except Exception:
                    pass
            mirror_zip = os.path.join(core_mirror_dir, f"{c_ver}.zip")
            shutil.copy2(found_zip, mirror_zip)
        else:
            local_dir_candidates = [
                os.path.join(p_abs, "core", "1.0.0.0"),
                os.path.join(p_abs, "core"),
                os.path.join(p_abs, "build", "core"),
                p_abs if os.path.isfile(os.path.join(p_abs, "manifest.json")) else None
            ]
            found_dir = next((d for d in local_dir_candidates if d and os.path.isdir(d) and os.path.isfile(os.path.join(d, "manifest.json"))), None)
            if not found_dir:
                print(f"[yscb] Error: Cannot find 'core' package or zip in local provider '{provider_arg}'.")
                return 1
            print(f"[yscb] Bootstrapping 'core' infrastructure module from local directory: {found_dir}")
            _fetch_and_extract_zip(found_dir, core_module)
            mf_path = os.path.join(core_module, "manifest.json")
            if os.path.isfile(mf_path):
                try:
                    with open(mf_path, "r", encoding="utf-8") as f:
                        c_ver = json.load(f).get("version", c_ver)
                except Exception:
                    pass
            # Package into mirror zip
            mirror_zip = os.path.join(core_mirror_dir, f"{c_ver}.zip")
            with zipfile.ZipFile(mirror_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(found_dir):
                    for f in files:
                        f_p = os.path.join(root, f)
                        arc = os.path.relpath(f_p, found_dir).replace("\\", "/")
                        zf.write(f_p, arcname=arc)
                
        init_cfg["installed_modules"]["core"] = {
            "version": c_ver,
            "installed_at": "init",
            "provider": provider_arg,
            "description": "Core Infrastructure Module"
        }

    # Case B: Remote URL provider (HTTP/HTTPS)
    elif provider_arg.startswith(("http://", "https://", "file://")):
        print(f"[yscb] Bootstrapping 'core' infrastructure module from remote gateway: {provider_arg}")
        try:
            # 1. Check core/index.json to determine target version
            target_version = "1.0.0.0"
            index_url = provider_arg.rstrip("/") + "/core/index.json"
            try:
                req_idx = urllib.request.Request(index_url, headers={"User-Agent": "yscb-host/2.0"})
                with urllib.request.urlopen(req_idx, timeout=10) as resp:
                    idx_data = json.loads(resp.read().decode("utf-8"))
                vers = idx_data.get("versions", [])
                if vers:
                    target_version = vers[-1]
            except Exception:
                pass

            # 2. Download core/<target_version>.zip and save to .mirror/core/<ver>.zip
            remote_zip_url = provider_arg.rstrip("/") + f"/core/{target_version}.zip"
            print(f"[yscb] Downloading '{remote_zip_url}'...")
            
            mirror_zip = os.path.join(core_mirror_dir, f"{target_version}.zip")
            req = urllib.request.Request(remote_zip_url, headers={"User-Agent": "yscb-host/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(mirror_zip, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                    
            # 3. Extract to modules/core/
            _fetch_and_extract_zip(mirror_zip, core_module)

            init_cfg["installed_modules"]["core"] = {
                "version": target_version,
                "installed_at": "init",
                "provider": provider_arg,
                "description": "Core Infrastructure Module"
            }
        except Exception as e:
            print(f"[yscb] Error: Failed to bootstrap 'core' module from remote provider '{provider_arg}': {e}")
            return 1
    else:
        print(f"[yscb] Error: Invalid provider '{provider_arg}'. Must be an existing local directory or valid URL.")
        return 1

    save_config(cfg_path, init_cfg)
    print(f"[yscb] Successfully initialized environment at '{yscb_root_arg}'.")

    # Initial reload
    core_cli = os.path.join(yscb_abs, "modules", "core", "scripts", "cli.py")
    if os.path.isfile(core_cli):
        print("[yscb] Triggering initial core reload...")
        return dispatch_module("core", ["reload"])

    return 0


def cmd_self_update(argv: List[str]) -> int:
    provider = DEFAULT_PROVIDER_URL
    for arg in argv:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1].strip("\"'")

    target_url = provider.rstrip("/") + "/yscb.py" if (not provider.endswith(".py") and not os.path.isfile(provider)) else provider
    print(f"[yscb] Checking for latest yscb.py from: {target_url}")

    current_file = os.path.abspath(__file__)
    tmp_file = current_file + ".tmp"
    bak_file = current_file + ".bak"

    try:
        if os.path.isfile(target_url):
            with open(target_url, "r", encoding="utf-8") as f:
                content = f.read()
        elif target_url.startswith("file://"):
            file_path = urllib.request.url2pathname(target_url[7:])
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            req = urllib.request.Request(target_url, headers={"User-Agent": "yscb-host/2.0"})
            if "127.0.0.1" in target_url or "localhost" in target_url:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
            else:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[yscb] Error: Failed to download update from {target_url}: {e}")
        return 1

    try:
        ast.parse(content, filename="yscb.py")
    except SyntaxError as e:
        print(f"[yscb] Error: Downloaded script has invalid Python syntax: {e}")
        return 1

    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(content)
        shutil.copyfile(current_file, bak_file)
        os.replace(tmp_file, current_file)
        print(f"[yscb] yscb.py updated successfully (backup saved at {os.path.basename(bak_file)}).")
        return 0
    except Exception as e:
        print(f"[yscb] Error: Failed to replace script: {e}")
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        return 1


def dispatch_module(module_name: str, args: List[str]) -> int:
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg:
        print("[yscb] Error: Environment not initialized. Please run 'python yscb.py init <yscbRoot>' first.")
        return 1

    base_dir = os.path.dirname(cfg_path)
    yscb_root = cfg["yscb_root"]
    target_cli = os.path.normpath(os.path.join(base_dir, yscb_root, "modules", module_name, "scripts", "cli.py"))

    if not os.path.isfile(target_cli):
        print(f"[yscb] Error: Module '{module_name}' is not installed or missing 'scripts/cli.py'.")
        print(f"       Expected path: {target_cli}")
        return 1

    env = dict(os.environ)
    env["YSCB_HOST_DIR"] = base_dir

    try:
        res = subprocess.run([sys.executable, target_cli, *args], env=env)
        return res.returncode
    except Exception as e:
        print(f"[yscb] Error executing module '{module_name}': {e}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print("YS-Codebase Ultra-Thin Single-File Host Bootstrapper")
        print("Usage:")
        print("  python yscb.py init <yscbRoot> [--provider=<source>]   Initialize environment")
        print("  python yscb.py self-update [--provider=<source>]       Update yscb.py host script")
        print("  python yscb.py <install|update|remove|list|status|rollback|reload> [...]")
        print("  python yscb.py <module_name> <command> [args...]")
        return 0

    cmd = argv[0]
    if cmd == "init":
        return cmd_init(argv[1:])
    elif cmd == "self-update":
        return cmd_self_update(argv[1:])
    elif cmd in CORE_COMMANDS:
        return dispatch_module("core", argv)
    elif cmd == "core":
        return dispatch_module("core", argv[1:])
    else:
        return dispatch_module(cmd, argv[1:])


if __name__ == "__main__":
    sys.exit(main())
