"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & Dual-Channel Router.
100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import List, Optional, Dict, Any, Tuple
import sys, os, json, urllib.request, subprocess, shutil, zipfile, tempfile, difflib, importlib.util, platform

CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release"
INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="

CORE_COMMANDS: set = {
    "install", "update", "remove", "list", "status",
    "rollback", "reload", "restore", "bootstrap", "uri", "config", "event", "help"
}


def _ensure_private_venv_path(yscb_dir: str) -> None:
    """極速探測 (<0.05ms) 私有微環境 site-packages 並安全插入 sys.path。"""
    tag, sys_name = f"py{sys.version_info.major}{sys.version_info.minor}", platform.system()
    sub = os.path.join(".venv", tag, "Lib", "site-packages") if sys_name == "Windows" else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    site_pkg = os.path.join(yscb_dir, sub)
    if os.path.isdir(site_pkg) and site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)
        pth = os.path.join(site_pkg, "host_venv.pth")
        if os.path.isfile(pth):
            try:
                for line in open(pth, "r", encoding="utf-8", errors="ignore"):
                    t = line.strip()
                    if t and os.path.isdir(t) and t not in sys.path: sys.path.insert(0, t)
            except Exception: pass


def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """剛性組態載入：僅探測當前目錄同層之 yscb.config.json。"""
    cfg_path = os.path.join(os.path.abspath(start_dir or os.getcwd()), CONFIG_FILENAME)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f: return cfg_path, json.load(f)
        except Exception: return cfg_path, None
    return None, None


def _extract_safe_zip(zip_path: str, dest_dir: str) -> None:
    dest_abs = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for m in zf.infolist():
            tgt = os.path.abspath(os.path.join(dest_abs, m.filename))
            if not tgt.startswith(dest_abs + os.sep) and tgt != dest_abs:
                raise RuntimeError(f"Zip Slip vulnerability detected: '{m.filename}'")
        zf.extractall(dest_dir)


def _fetch_and_extract_zip(source: str, dest_dir: str) -> None:
    """自舉提取壓縮包至 dest_dir，嚴防 Zip Slip。"""
    os.makedirs(dest_dir, exist_ok=True)
    if source.startswith(("http://", "https://")):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f: tmp_p = tmp_f.name
        try:
            req = urllib.request.Request(source, headers={"User-Agent": "yscb-host/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_p, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
            _extract_safe_zip(tmp_p, dest_dir)
        finally:
            if os.path.exists(tmp_p):
                try: os.remove(tmp_p)
                except Exception: pass
    elif os.path.isdir(source):
        shutil.copytree(source, dest_dir, dirs_exist_ok=True)
    elif zipfile.is_zipfile(source):
        _extract_safe_zip(source, dest_dir)


def cmd_init(argv: List[str]) -> int:
    """極簡自舉：初始化工作區並解壓 core 模組。"""
    provider = DEFAULT_PROVIDER_URL
    clean_argv = [a for a in argv if not a.startswith("--provider=")]
    for a in argv:
        if a.startswith("--provider="): provider = a.split("=", 1)[1].strip("\"'")
    yscb_root = clean_argv[0] if clean_argv else "."
    base_dir, cfg_path = os.path.abspath(os.getcwd()), os.path.join(os.path.abspath(os.getcwd()), CONFIG_FILENAME)
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    if os.path.exists(cfg_path):
        print(f"[yscb] Error: Configuration already exists at '{cfg_path}'."); return 1
    os.makedirs(os.path.join(yscb_abs, ".mirror", "core"), exist_ok=True)
    candidates = [os.path.join(provider, "core", "1.0.0.0.zip"), os.path.join(provider, "release", "core", "1.0.0.0.zip"), os.path.join(provider, "core")]
    source = next((c for c in candidates if os.path.exists(c)), None) if os.path.isdir(provider) else (provider.rstrip("/") + "/core/1.0.0.0.zip" if provider.startswith(("http://", "https://")) else None)
    if not source:
        print(f"[yscb] Error: Cannot locate core package in provider '{provider}'."); return 1
    print(f"[yscb] Initializing environment at '{yscb_root}'...")
    _fetch_and_extract_zip(source, os.path.join(yscb_abs, ".modules", "core"))
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"yscb_root": yscb_root, "default_provider": provider, "installed_modules": {"core": {"version": "1.0.0.0", "installed_at": "init", "provider": provider}}}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[yscb] Successfully initialized. Triggering initial reload...")
    return dispatch_module("core", ["reload"])


def _try_hot_dispatch(module_name: str, args: List[str], base_dir: str, yscb_root: str) -> Optional[int]:
    """管道 B：透過 Localhost HTTP 將指令熱派發至常駐 Server。"""
    if module_name == "server": return None
    cfg_file = os.path.join(base_dir, yscb_root, "config", "server", "config.project.json")
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                if json.load(f).get("enable") is False: return None
        except Exception: pass
    state_file = os.path.join(base_dir, yscb_root, ".cache", "server", "daemon.json")
    if not os.path.isfile(state_file): return None
    try:
        with open(state_file, "r", encoding="utf-8") as f: state = json.load(f)
        port, token = state.get("port"), state.get("token")
        yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
        url, headers = f"http://127.0.0.1:{port}/api/dispatch", {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps({"module": module_name, "args": args, "cwd": os.getcwd(), "yscb_root": state.get("root", yscb_abs)}).encode("utf-8"), headers=headers, method="POST")
        exit_code = 0
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            buf = ""
            while True:
                chunk = resp.read(1024)
                if not chunk: break
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if not line.strip(): continue
                    pkt = json.loads(line)
                    if pkt.get("type") == "terminal_stream":
                        out = sys.stderr if pkt.get("stream") == "stderr" else sys.stdout
                        out.write(pkt.get("text", "")); out.flush()
                    elif pkt.get("type") == "task_finish":
                        return pkt.get("exit_code", 0)
        return exit_code
    except Exception: return None


def _maybe_auto_spawn_server(base_dir: str, yscb_root: str) -> None:
    """在背景非同步按需拉起 Server 守護進程。"""
    if os.path.isfile(os.path.join(base_dir, yscb_root, ".cache", "server", "daemon.json")): return
    if not os.path.isdir(os.path.join(base_dir, yscb_root, ".modules", "server")): return
    cfg_file = os.path.join(base_dir, yscb_root, "config", "server", "config.project.json")
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                if json.load(f).get("enable") is False: return
        except Exception: pass
    try:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) if sys.platform == "win32" else 0
        subprocess.Popen([sys.executable, sys.argv[0], "server", "start", "--daemon"], cwd=base_dir, creationflags=flags,
                         start_new_session=(sys.platform != "win32"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, close_fds=True)
    except Exception: pass


def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """模糊拼寫建議。"""
    matches = difflib.get_close_matches(unknown_cmd, candidate_pool, n=1, cutoff=0.5)
    return matches[0] if matches else None


def _print_global_help() -> int:
    return dispatch_module("core", ["help"])


def _generate_internal_gitignore(yscb_dir: str) -> None:
    _ensure_private_venv_path(yscb_dir)
    p = os.path.join(yscb_dir, ".modules", "core")
    if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)
    try:
        from core.installer import generate_internal_gitignore; generate_internal_gitignore(yscb_dir)
    except Exception: pass


def _restore_module_package(base_dir: str, yscb_root: str, module_name: str, version: str, provider_arg: str, dest_dir: str, mirror_dir: str) -> bool:
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    _ensure_private_venv_path(yscb_abs)
    p = os.path.join(yscb_abs, ".modules", "core")
    if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)
    from core.installer import Installer
    return Installer()._restore_module_package(base_dir, yscb_root, module_name, version, provider_arg, dest_dir, mirror_dir)


def cmd_restore(argv: List[str]) -> int:
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg: return 1
    base_dir, yscb_root = os.path.dirname(cfg_path), cfg["yscb_root"]
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    _generate_internal_gitignore(yscb_abs)
    installed = cfg.get("installed_modules", {})
    if not installed: return 0
    if os.path.isfile(os.path.join(yscb_abs, ".modules", "core", "scripts", "cli.py")):
        return dispatch_module("core", ["restore"] + argv)
    mods_dir, mirror_dir, force, failed = os.path.join(yscb_abs, ".modules"), os.path.join(yscb_abs, ".mirror"), "--force" in argv, []
    for mod, info in sorted(installed.items(), key=lambda x: (0 if x[0] == "core" else 1, x[0])):
        ver = info.get("version", "1.0.0.0") if isinstance(info, dict) else "1.0.0.0"
        prov = info.get("provider", DEFAULT_PROVIDER_URL) if isinstance(info, dict) else DEFAULT_PROVIDER_URL
        dest = os.path.join(mods_dir, mod)
        if not force and os.path.isdir(dest) and os.path.isfile(os.path.join(dest, "manifest.json")): continue
        if not _restore_module_package(base_dir, yscb_root, mod, ver, prov, dest, os.path.join(mirror_dir, mod)): failed.append(mod)
    return 0 if not failed else 1


def cmd_event(argv: List[str]) -> int:
    return dispatch_module("core", ["event"] + argv)


def _ensure_jit_lifecycle_pre(cmd: str) -> None:
    if cmd not in ("init", "self-update", "restore", "bootstrap"):
        try:
            from core import events; events.broadcast("pre_cli_dispatch", emit_module="core")
        except Exception: pass


def _ensure_jit_lifecycle_post(cmd: str, exit_code: int = 0) -> None:
    if cmd not in ("init", "self-update", "restore", "bootstrap"):
        try:
            from core import events; events.broadcast("post_cli_dispatch", emit_module="core")
        except Exception: pass


def _is_modules_dirty(base_dir: str, yscb_root: str, installed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not installed: return False, []
    mod_d = os.path.join(base_dir, yscb_root, ".modules")
    if not os.path.isdir(mod_d): return True, list(installed.keys())
    dirty = [m for m, i in installed.items() if not os.path.isdir(os.path.join(mod_d, m)) or not os.path.isfile(os.path.join(mod_d, m, "manifest.json")) or (isinstance(i, dict) and i.get("version") and json.load(open(os.path.join(mod_d, m, "manifest.json"), "r", encoding="utf-8")).get("version") != i.get("version"))]
    return bool(dirty), dirty


def dispatch_module(module_name: str, args: List[str]) -> int:
    """雙管道路由分派：熱派發優先，連線失敗透明降級至本地冷啟動。"""
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg:
        print("[yscb] Error: Environment not initialized. Please run 'python yscb.py init <yscbRoot>' first."); return 1
    base_dir, yscb_abs = os.path.dirname(cfg_path), os.path.normpath(os.path.join(os.path.dirname(cfg_path), cfg["yscb_root"]))

    hot_res = _try_hot_dispatch(module_name, args, base_dir, cfg["yscb_root"])
    if hot_res is not None: return hot_res

    if module_name != "server": _maybe_auto_spawn_server(base_dir, cfg["yscb_root"])

    _ensure_private_venv_path(yscb_abs)
    target_cli = os.path.normpath(os.path.join(yscb_abs, ".modules", module_name, "scripts", "cli.py"))
    if not os.path.isfile(target_cli):
        known = ["init", "restore", "bootstrap"] + list(CORE_COMMANDS)
        mod_dir = os.path.join(yscb_abs, ".modules")
        if os.path.isdir(mod_dir):
            known.extend([d for d in os.listdir(mod_dir) if os.path.isdir(os.path.join(mod_dir, d)) and d != "core"])
        sugg = _suggest_command(module_name, known)
        print(f"[yscb] Error: Unknown command or module '{module_name}'.")
        if sugg: print(f"       Did you mean '{sugg}'?")
        print("       Run 'python yscb.py --help' for available commands."); return 1

    for p in [os.path.join(yscb_abs, ".modules", "core"), os.path.dirname(os.path.dirname(target_cli))]:
        if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)

    os.environ["YSCB_HOST_DIR"], os.environ["YSCB_HOST_DISPATCH_TOKEN"], os.environ["PYTHONUNBUFFERED"] = base_dir, "yscb_auth_dispatch", "1"
    orig_argv = list(sys.argv)
    try:
        sys.argv = [target_cli] + args
        spec = importlib.util.spec_from_file_location(f"yscb_mod_{module_name.replace('-', '_')}_cli", target_cli)
        if spec is None or spec.loader is None: raise ImportError(f"Cannot load spec from {target_cli}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, "process", getattr(mod, "main", None))
        if callable(fn):
            res = fn(args)
            return int(res) if res is not None else 0
        raise AttributeError(f"Module '{module_name}' CLI does not define 'process(args)' entrypoint.")
    except SystemExit as se:
        return se.code if isinstance(se.code, int) else (0 if se.code is None else 1)
    except Exception as e:
        print(f"[yscb] Error executing module '{module_name}': {e}"); return 1
    finally:
        sys.argv = orig_argv


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True); sys.stderr.reconfigure(line_buffering=True)
        except Exception: pass
    if argv is None: argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"): return _print_global_help()
    cmd = argv[0]
    _ensure_jit_lifecycle_pre(cmd)
    ret = cmd_init(argv[1:]) if cmd == "init" else (cmd_event(argv[1:]) if cmd == "event" else (dispatch_module("core", argv) if cmd in CORE_COMMANDS else (dispatch_module("core", argv[1:]) if cmd == "core" else dispatch_module(cmd, argv[1:]))))
    _ensure_jit_lifecycle_post(cmd, ret)
    return ret


if __name__ == "__main__":
    sys.exit(main())
