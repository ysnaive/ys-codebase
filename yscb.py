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

CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "./ys_codebase/build"
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

    init_cfg = {
        "yscb_root": yscb_root_arg,
        "default_provider": provider_arg,
        "installed_modules": {}
    }

    # Bootstrap core infrastructure module strictly from provider_arg
    core_mirror = os.path.join(yscb_abs, ".mirror", "core", "1.0.0")
    core_module = os.path.join(yscb_abs, "modules", "core")

    # Case A: Local directory provider
    if os.path.isdir(provider_arg) or os.path.isdir(os.path.abspath(provider_arg)):
        p_abs = os.path.abspath(provider_arg)
        local_candidates = [
            os.path.join(p_abs, "core", "1.0.0"),
            os.path.join(p_abs, "core"),
            os.path.join(p_abs, "build", "core", "1.0.0"),
            os.path.join(p_abs, "build", "core"),
            p_abs if os.path.isfile(os.path.join(p_abs, "manifest.json")) else None
        ]
        found = None
        for cand in local_candidates:
            if cand and os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "manifest.json")):
                found = cand
                break
        if not found:
            print(f"[yscb] Error: Cannot find 'core' module in local provider '{provider_arg}'.")
            return 1
        
        print(f"[yscb] Bootstrapping 'core' infrastructure module from local provider: {found}")
        if os.path.exists(core_mirror):
            shutil.rmtree(core_mirror)
        shutil.copytree(found, core_mirror)
        if os.path.exists(core_module):
            shutil.rmtree(core_module)
        shutil.copytree(found, core_module)
        init_cfg["installed_modules"]["core"] = {
            "version": "1.0.0",
            "installed_at": "init",
            "provider": provider_arg,
            "description": "Core Infrastructure Module"
        }

    # Case B: Remote URL provider
    elif provider_arg.startswith(("http://", "https://", "file://")):
        print(f"[yscb] Bootstrapping 'core' infrastructure module from remote: {provider_arg}")
        try:
            manifest_url = provider_arg.rstrip("/") + "/core/manifest.json"
            req = urllib.request.Request(manifest_url, headers={"User-Agent": "yscb-host/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                m_data = json.loads(resp.read().decode("utf-8"))
            init_cfg["installed_modules"]["core"] = {
                "version": m_data.get("version", "1.0.0"),
                "installed_at": "init",
                "provider": provider_arg,
                "description": m_data.get("description", "Core Infrastructure Module")
            }
        except Exception as e:
            print(f"[yscb] Error: Failed to fetch 'core' module from remote provider '{provider_arg}': {e}")
            return 1
    else:
        print(f"[yscb] Error: Invalid provider '{provider_arg}'. Must be an existing local directory or valid URL.")
        return 1

    save_config(cfg_path, init_cfg)
    print(f"[yscb] Successfully initialized environment at '{yscb_root_arg}'.")

    # If core module exists, run reload to initialize environment
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

    # Inject YSCB_HOST_DIR into environment for deterministic zero-speculation anchoring
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
