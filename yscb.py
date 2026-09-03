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
import runpy

CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release"
CORE_COMMANDS: set = {
    "install",
    "update",
    "remove",
    "list",
    "status",
    "rollback",
    "reload",
    "uri",
    "config"
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
                dest_dir_abs = os.path.abspath(dest_dir)
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_dir_abs, member.filename))
                    if not target_path.startswith(dest_dir_abs + os.sep) and target_path != dest_dir_abs:
                        raise RuntimeError(f"Zip Slip vulnerability detected: '{member.filename}' attempts to extract outside destination '{dest_dir}'.")
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
                dest_dir_abs = os.path.abspath(dest_dir)
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_dir_abs, member.filename))
                    if not target_path.startswith(dest_dir_abs + os.sep) and target_path != dest_dir_abs:
                        raise RuntimeError(f"Zip Slip vulnerability detected: '{member.filename}' attempts to extract outside destination '{dest_dir}'.")
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


import difflib


def _get_installed_module_commands(base_dir: str, yscb_root: str) -> Dict[str, Dict[str, str]]:
    """Scans installed modules in modules/ to summarize contributed CLI commands."""
    summary: Dict[str, Dict[str, str]] = {}
    modules_dir = os.path.normpath(os.path.join(base_dir, yscb_root, "modules"))
    if not os.path.isdir(modules_dir):
        return summary

    for mod_name in sorted(os.listdir(modules_dir)):
        if mod_name == "core":
            continue
        mod_p = os.path.join(modules_dir, mod_name)
        if not os.path.isdir(mod_p):
            continue
        mf_path = os.path.join(mod_p, "manifest.json")
        if not os.path.isfile(mf_path):
            continue
        try:
            with open(mf_path, "r", encoding="utf-8") as f:
                mf_data = json.load(f)
            mod_desc = mf_data.get("description", f"{mod_name} module")
            contrib = mf_data.get("contributes", {})
            c_core = contrib.get("core", {}) if isinstance(contrib, dict) else {}
            cmds = c_core.get("commands", {}) if isinstance(c_core, dict) else {}
            if cmds and isinstance(cmds, dict):
                sub_map = {}
                for cmd, val in cmds.items():
                    if isinstance(val, dict):
                        sub_map[cmd] = val.get("description", "")
                    elif isinstance(val, str):
                        sub_map[cmd] = val
                summary[mod_name] = sub_map
            else:
                summary[mod_name] = {
                    "run": mod_desc
                }
        except Exception:
            pass
    return summary


def _print_global_help() -> None:
    """Outputs standardized, beautifully structured YSCB CLI help."""
    print("=" * 70)
    print("  YS-Codebase - Ultra-Thin Modular Microkernel CLI (v2.0)")
    print("=" * 70)
    print("\nUSAGE:")
    print("  python yscb.py <command> [options]")
    print("  python yscb.py <module> <command> [options]")
    
    print("\nCORE COMMANDS:")
    core_docs = [
        ("init <root> [--provider=<url>]", "Initialize a new YSCB workspace"),
        ("self-update [--provider=<url>]", "Update yscb.py host bootstrapper script"),
        ("install <module>[@<version>]", "Install a module from provider"),
        ("update [<module>]", "Update installed module(s) to latest version"),
        ("remove <module> [--force]", "Remove an installed module from environment"),
        ("list", "List all installed modules, versions and providers"),
        ("status", "Health check and runtime diagnostic report"),
        ("reload", "Reconcile and refresh runtime environment"),
        ("rollback", "Revert environment to the previous snapshot state"),
    ]
    for cmd, desc in core_docs:
        print(f"  {cmd:<35} {desc}")

    print("\nMODULE COMMANDS:")
    cfg_path, cfg = load_config()
    if cfg_path and cfg and "yscb_root" in cfg:
        mod_cmds = _get_installed_module_commands(os.path.dirname(cfg_path), cfg["yscb_root"])
        if mod_cmds:
            for mod_name, cmds in mod_cmds.items():
                print(f"  [{mod_name}]")
                for subcmd, desc in cmds.items():
                    full_cmd = f"  {mod_name} {subcmd}"
                    print(f"  {full_cmd:<33} {desc}")
        else:
            print("  (No additional module commands available. Use 'install <module>' to add capabilities.)")
    else:
        print("  (Environment not initialized. Run 'init <root>' to enable module commands.)")

    print("\nGLOBAL OPTIONS:")
    print("  -h, --help                          Show this help message and exit")
    print("=" * 70)


def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """Uses difflib to find the closest matching command or module name."""
    matches = difflib.get_close_matches(unknown_cmd, candidate_pool, n=1, cutoff=0.5)
    return matches[0] if matches else None


def dispatch_module(module_name: str, args: List[str]) -> int:
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg:
        print("[yscb] Error: Environment not initialized. Please run 'python yscb.py init <yscbRoot>' first.")
        return 1

    base_dir = os.path.dirname(cfg_path)
    yscb_root = cfg["yscb_root"]
    target_cli = os.path.normpath(os.path.join(base_dir, yscb_root, "modules", module_name, "scripts", "cli.py"))

    if not os.path.isfile(target_cli):
        # Unknown module / command -> trigger intelligent spelling suggestion
        known_cmds = ["init", "self-update"] + list(CORE_COMMANDS)
        modules_dir = os.path.normpath(os.path.join(base_dir, yscb_root, "modules"))
        if os.path.isdir(modules_dir):
            known_cmds.extend([d for d in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, d)) and d != "core"])
        
        suggestion = _suggest_command(module_name, known_cmds)
        print(f"[yscb] Error: Unknown command or module '{module_name}'.")
        if suggestion:
            print(f"       Did you mean '{suggestion}'?")
        print("       Run 'python yscb.py --help' for available commands.")
        return 1

    os.environ["YSCB_HOST_DIR"] = base_dir
    os.environ["PYTHONUNBUFFERED"] = "1"

    orig_argv = list(sys.argv)
    try:
        sys.argv = [target_cli] + args
        runpy.run_path(target_cli, run_name="__main__")
        return 0
    except SystemExit as se:
        if se.code is None:
            return 0
        if isinstance(se.code, int):
            return se.code
        print(se.code)
        return 1
    except Exception as e:
        print(f"[yscb] Error executing module '{module_name}': {e}")
        return 1
    finally:
        sys.argv = orig_argv


def _check_and_show_update_tips() -> None:
    """非阻塞檢查並顯示模組更新提示 (從 cache://core/update_check.json 讀取)。"""
    if os.environ.get("YSCB_NO_UPDATE_CHECK") == "1":
        return
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg:
        return
    base_dir = os.path.dirname(cfg_path)
    cache_file = os.path.join(base_dir, cfg["yscb_root"], ".cache", "core", "update_check.json")
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            updates = data.get("updates", {})
            tips = []
            if isinstance(updates, dict):
                for mod, info in updates.items():
                    if isinstance(info, dict) and info.get("has_update"):
                        cur_v = info.get("current_version", "")
                        lat_v = info.get("latest_version", "")
                        tips.append(
                            f"💡 提示: 模組 '{mod}' 有新版本可用 (當前: v{cur_v}, 最新: v{lat_v})。"
                            f" 可執行 'python yscb.py update {mod}' 進行升級。"
                        )
            if tips:
                print("\n" + "\n".join(tips))
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_global_help()
        return 0

    cmd = argv[0]
    ret = 0
    if cmd == "init":
        ret = cmd_init(argv[1:])
    elif cmd == "self-update":
        ret = cmd_self_update(argv[1:])
    elif cmd in CORE_COMMANDS:
        ret = dispatch_module("core", argv)
    elif cmd == "core":
        ret = dispatch_module("core", argv[1:])
    else:
        ret = dispatch_module(cmd, argv[1:])

    if ret == 0 and cmd not in ("update", "init", "self-update"):
        _check_and_show_update_tips()

    return ret


if __name__ == "__main__":
    sys.exit(main())
