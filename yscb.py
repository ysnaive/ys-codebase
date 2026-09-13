"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & Thin Router.
100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import Any, Dict, List, Optional, Tuple
import ast
import difflib
import importlib.util
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile

CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release"
INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="

CORE_COMMANDS: set = {
    "install", "update", "remove", "list", "status",
    "rollback", "reload", "restore", "bootstrap", "uri", "config", "event", "help",
    "self-update"
}

_MODULE_CACHE: Dict[str, Any] = {}


def _ensure_private_venv_path(yscb_dir: str) -> None:
    """極速探測 (<0.05ms) 私有微環境 site-packages 並安全插入 sys.path。"""
    tag, sys_name = f"py{sys.version_info.major}{sys.version_info.minor}", platform.system()
    sub = (
        os.path.join(".venv", tag, "Lib", "site-packages")
        if sys_name == "Windows"
        else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    )
    site_pkg = os.path.join(yscb_dir, sub)
    if os.path.isdir(site_pkg) and site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)
        pth = os.path.join(site_pkg, "host_venv.pth")
        if os.path.isfile(pth):
            try:
                with open(pth, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        t = line.strip()
                        if t and os.path.isdir(t) and t not in sys.path:
                            sys.path.insert(0, t)
            except Exception:
                pass


def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """剛性組態載入：僅探測當前目錄同層之 yscb.config.json。"""
    cfg_path = os.path.join(os.path.abspath(start_dir or os.getcwd()), CONFIG_FILENAME)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return cfg_path, json.load(f)
        except Exception:
            return cfg_path, None
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
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
            tmp_p = tmp_f.name
        try:
            req = urllib.request.Request(source, headers={"User-Agent": "yscb-host/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_p, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
            _extract_safe_zip(tmp_p, dest_dir)
        finally:
            if os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass
    elif os.path.isdir(source):
        shutil.copytree(source, dest_dir, dirs_exist_ok=True)
    elif zipfile.is_zipfile(source):
        _extract_safe_zip(source, dest_dir)


def _resolve_self_update_target_url(provider: str, custom_url: Optional[str] = None) -> str:
    """解算 self-update 目標 URL，智慧錨定至 repo 根目錄之 yscb.py。"""
    if custom_url:
        return custom_url
    p = (provider or DEFAULT_PROVIDER_URL).strip().rstrip("/")
    if p.endswith(".py") or (not p.startswith(("http://", "https://", "file://")) and os.path.isfile(p)):
        return p
    if "/release" in p:
        prefix = p.split("/release")[0]
        return f"{prefix}/yscb.py"
    if not p.startswith(("http://", "https://")):
        parent_candidate = os.path.join(os.path.dirname(p), "yscb.py")
        if os.path.isfile(parent_candidate):
            return parent_candidate
        return os.path.join(p, "yscb.py")
    return f"{p}/yscb.py"


def _render_self_update_help() -> str:
    """渲染 self-update 指令幫助訊息。"""
    lines = [
        "=" * 80,
        "Command: python yscb.py self-update",
        "=" * 80,
        "Description: Upgrade yscb.py host bootstrapper from repository root",
        "Security   : [SAFE] 自主安全 (safe)",
        "Server Mode: [COLD-RUN] Local Cold Run Only",
        "",
        "USAGE:",
        "  python yscb.py self-update [options]",
        "",
        "OPTIONS:",
        "  -- [Group: source]",
        "    --url <target_url>             Custom URL to download yscb.py",
        "",
        "GLOBAL OPTIONS:",
        "  -h, --help                     Show this help message and exit",
        "",
        "RECOMMENDED USAGE (Pros):",
        "  [+] 升級宿主工程起手腳本 yscb.py 至最新版本",
        "=" * 80,
    ]
    return "\n".join(lines)


def cmd_self_update(argv: List[str]) -> int:
    """自遠端 Provider 或指定 URL 更新 yscb.py 本體。"""
    if "-h" in argv or "--help" in argv or (argv and argv[0] == "help"):
        print(_render_self_update_help())
        return 0
    provider = DEFAULT_PROVIDER_URL
    custom_url = None
    for arg in argv:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1].strip("\"'")
        elif arg.startswith("--url="):
            custom_url = arg.split("=", 1)[1].strip("\"'")

    target_url = _resolve_self_update_target_url(provider, custom_url)
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
            while file_path.startswith("//"):
                file_path = file_path[1:]
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
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return 1


def _parse_simple_semver(v_str: str) -> Tuple[int, int, int, int, bool]:
    """輕量 4-tuple semver 解析器：返回 (major, minor, patch, revision, is_build)。"""
    raw = str(v_str).strip()
    is_build = raw == "build" or raw.endswith(".build")
    if raw.endswith(".build"):
        raw = raw[:-6]
    elif raw == "build":
        return (0, 0, 0, 0, True)

    parts: List[int] = []
    for token in raw.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)

    while len(parts) < 4:
        parts.append(0)
    return (parts[0], parts[1], parts[2], parts[3], is_build)


def _discover_latest_core(provider: str) -> Tuple[Optional[str], Optional[str]]:
    """
    動態探測 Provider 中的最新 core 模組。
    返回 (version_str, package_path_or_url)。
    """
    p = (provider or DEFAULT_PROVIDER_URL).strip().rstrip("/")
    # 1. 本地目錄探測
    if not p.startswith(("http://", "https://")):
        cand_dirs = [
            os.path.join(p, "core"),
            os.path.join(p, "release", "core"),
            os.path.join(p),
        ]
        found_versions: Dict[str, str] = {}
        for c_dir in cand_dirs:
            if not os.path.isdir(c_dir):
                continue
            idx_p = os.path.join(c_dir, "index.json")
            if os.path.isfile(idx_p):
                try:
                    with open(idx_p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and isinstance(data.get("versions"), list):
                        for v in data["versions"]:
                            zip_cand = os.path.join(c_dir, f"{v}.zip")
                            if os.path.isfile(zip_cand):
                                found_versions[v] = zip_cand
                except Exception:
                    pass
            for f in os.listdir(c_dir):
                if f.endswith(".zip"):
                    v_name = f[:-4]
                    found_versions[v_name] = os.path.join(c_dir, f)
                elif os.path.isdir(os.path.join(c_dir, f)) and os.path.isfile(os.path.join(c_dir, f, "manifest.json")):
                    try:
                        with open(os.path.join(c_dir, f, "manifest.json"), "r", encoding="utf-8") as mf:
                            m_data = json.load(mf)
                        v_name = m_data.get("version", f)
                        found_versions[v_name] = os.path.join(c_dir, f)
                    except Exception:
                        pass

        if found_versions:
            clean_pairs = []
            for v, path in found_versions.items():
                parsed = _parse_simple_semver(v)
                if not parsed[4]:
                    clean_pairs.append((parsed, v, path))
            if clean_pairs:
                clean_pairs.sort(key=lambda x: x[0], reverse=True)
                return clean_pairs[0][1], clean_pairs[0][2]
            all_pairs = sorted([(_parse_simple_semver(v), v, pth) for v, pth in found_versions.items()], key=lambda x: x[0], reverse=True)
            return all_pairs[0][1], all_pairs[0][2]

        for c_dir in [os.path.join(p, "core"), p]:
            if os.path.isdir(c_dir) and os.path.isfile(os.path.join(c_dir, "manifest.json")):
                try:
                    with open(os.path.join(c_dir, "manifest.json"), "r", encoding="utf-8") as mf:
                        m_data = json.load(mf)
                    return m_data.get("version", "1.0.0.0"), c_dir
                except Exception:
                    return "1.0.0.0", c_dir
        return None, None

    # 2. 遠端 HTTP/HTTPS 探測
    try:
        idx_url = f"{p}/core/index.json"
        req = urllib.request.Request(idx_url, headers={"User-Agent": "yscb-host/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            clean_versions = [v for v in data["versions"] if not _parse_simple_semver(v)[4]]
            if clean_versions:
                best_v = sorted(clean_versions, key=_parse_simple_semver, reverse=True)[0]
                return best_v, f"{p}/core/{best_v}.zip"
    except Exception:
        pass

    return "1.1.0.1", f"{p}/core/1.1.0.1.zip"


def _is_core_healthy(core_module_dir: str) -> Tuple[bool, Optional[str]]:
    """檢測 core 模組安裝是否正常完整。"""
    manifest_path = os.path.join(core_module_dir, "manifest.json")
    if not os.path.isdir(core_module_dir) or not os.path.isfile(manifest_path):
        return False, None
    try:
        with open(manifest_path, "r", encoding="utf-8") as mf:
            data = json.load(mf)
        ver = data.get("version")
        entry = data.get("entry", "scripts/cli.py")
        if not ver or not os.path.isfile(os.path.join(core_module_dir, entry)):
            return False, None
        return True, ver
    except Exception:
        return False, None


def _render_init_help() -> str:
    """渲染 init 指令幫助訊息。"""
    lines = [
        "=" * 80,
        "Command: python yscb.py init",
        "=" * 80,
        "Description: Initialize workspace and unpack core module",
        "Security   : [SAFE] 自主安全 (safe)",
        "Server Mode: [COLD-RUN] Local Cold Run Only",
        "",
        "USAGE:",
        "  python yscb.py init [root] [options]",
        "",
        "ARGUMENTS:",
        "  [root]                         Target directory for YSCB environment (default: .yscb) [optional]",
        "",
        "OPTIONS:",
        "  -- [Group: mode]",
        "    --fix                          Check and repair damaged or missing core module",
        "    --force                        Force re-download and re-unpack core module",
        "  -- [Group: source]",
        "    --provider <url>               Module provider URL or path (alias: -p)",
        "",
        "GLOBAL OPTIONS:",
        "  -h, --help                     Show this help message and exit",
        "",
        "RECOMMENDED USAGE (Pros):",
        "  [+] 初次引入 YSCB 或自癒修復核心運行時環境",
        "=" * 80,
    ]
    return "\n".join(lines)


def cmd_init(argv: List[str]) -> int:
    """唯一入口職責 ①：極簡自舉：初始化工作區或自癒修復並解壓 core 模組。"""
    if "-h" in argv or "--help" in argv or (argv and argv[0] == "help"):
        print(_render_init_help())
        return 0
    is_fix = "--fix" in argv
    is_force = "--force" in argv
    clean_argv = [a for a in argv if a not in ("--fix", "--force") and not a.startswith("--provider=")]
    provider = DEFAULT_PROVIDER_URL
    has_explicit_provider = False
    for a in argv:
        if a.startswith("--provider="):
            provider = a.split("=", 1)[1].strip("\"'")
            has_explicit_provider = True

    base_dir = os.path.abspath(os.getcwd())
    cfg_path = os.path.join(base_dir, CONFIG_FILENAME)
    has_cfg = os.path.isfile(cfg_path)

    if has_cfg:
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[yscb] Error: Configuration at '{cfg_path}' is corrupted: {e}")
            return 1

        cfg_yscb_root = cfg.get("yscb_root", clean_argv[0] if clean_argv else ".yscb")
        cfg_provider = provider if has_explicit_provider else cfg.get("default_provider", provider)
        yscb_abs = os.path.normpath(os.path.join(base_dir, cfg_yscb_root))
        core_module_dir = os.path.join(yscb_abs, ".modules", "core")
        is_healthy, current_ver = _is_core_healthy(core_module_dir)

        if is_fix and is_healthy and not is_force:
            print(f"[yscb] Core module at '{cfg_yscb_root}' is already healthy (core@{current_ver}). No repair needed.")
            return 0

        if is_fix or not is_healthy:
            print(f"[yscb] Repairing core module at '{cfg_yscb_root}' from provider '{cfg_provider}'...")
            ver, source = _discover_latest_core(cfg_provider)
            if not source or not ver:
                print(f"[yscb] Error: Cannot locate core package in provider '{cfg_provider}'.")
                return 1
            os.makedirs(os.path.join(yscb_abs, ".mirror", "core"), exist_ok=True)
            _fetch_and_extract_zip(source, core_module_dir)
            if "installed_modules" not in cfg or not isinstance(cfg["installed_modules"], dict):
                cfg["installed_modules"] = {}
            cfg["installed_modules"]["core"] = {
                "version": ver,
                "installed_at": "fix",
                "provider": cfg_provider,
            }
            cfg["default_provider"] = cfg_provider
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"[yscb] Successfully repaired core (core@{ver}). Triggering initial reload...")
            _ensure_private_venv_path(yscb_abs)
            if core_module_dir not in sys.path:
                sys.path.insert(0, core_module_dir)
            os.environ["YSCB_HOST_DIR"] = base_dir
            os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"
            return dispatch_module("core", ["reload"])
        else:
            print(f"[yscb] Error: Configuration already exists at '{cfg_path}'. Use 'python yscb.py init --fix' to repair or reinstall core.")
            return 1

    # 全新初始化
    yscb_root = clean_argv[0] if clean_argv else ".yscb"
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    print(f"[yscb] Initializing environment at '{yscb_root}'...")
    ver, source = _discover_latest_core(provider)
    if not source or not ver:
        print(f"[yscb] Error: Cannot locate core package in provider '{provider}'.")
        return 1

    os.makedirs(os.path.join(yscb_abs, ".mirror", "core"), exist_ok=True)
    core_module_dir = os.path.join(yscb_abs, ".modules", "core")
    _fetch_and_extract_zip(source, core_module_dir)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "yscb_root": yscb_root,
                "default_provider": provider,
                "installed_modules": {
                    "core": {
                        "version": ver,
                        "installed_at": "init",
                        "provider": provider,
                    }
                },
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.write("\n")
    print(f"[yscb] Successfully initialized (core@{ver}). Triggering initial reload...")
    _ensure_private_venv_path(yscb_abs)
    if core_module_dir not in sys.path:
        sys.path.insert(0, core_module_dir)
    os.environ["YSCB_HOST_DIR"] = base_dir
    os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"
    return dispatch_module("core", ["reload"])


def _generate_internal_gitignore(yscb_dir: str) -> None:
    _ensure_private_venv_path(yscb_dir)
    p = os.path.join(yscb_dir, ".modules", "core")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
    try:
        from core.installer import generate_internal_gitignore
        generate_internal_gitignore(yscb_dir)
    except Exception:
        pass


def _restore_module_package(base_dir: str, yscb_root: str, module_name: str, version: str, provider_arg: str, dest_dir: str, mirror_dir: str) -> bool:
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    _ensure_private_venv_path(yscb_abs)
    p = os.path.join(yscb_abs, ".modules", "core")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
    from core.installer import Installer
    return Installer()._restore_module_package(base_dir, yscb_root, module_name, version, provider_arg, dest_dir, mirror_dir)


def cmd_restore(argv: List[str]) -> int:
    cfg_path, cfg = load_config()
    if not cfg_path or not cfg or "yscb_root" not in cfg:
        return 1
    base_dir, yscb_root = os.path.dirname(cfg_path), cfg["yscb_root"]
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    _generate_internal_gitignore(yscb_abs)
    installed = cfg.get("installed_modules", {})
    if not installed:
        return 0
    if os.path.isfile(os.path.join(yscb_abs, ".modules", "core", "scripts", "cli.py")):
        return dispatch_module("core", ["restore"] + argv)
    mods_dir, mirror_dir, force, failed = os.path.join(yscb_abs, ".modules"), os.path.join(yscb_abs, ".mirror"), "--force" in argv, []
    for mod, info in sorted(installed.items(), key=lambda x: (0 if x[0] == "core" else 1, x[0])):
        ver = info.get("version", "1.0.0.0") if isinstance(info, dict) else "1.0.0.0"
        prov = info.get("provider", DEFAULT_PROVIDER_URL) if isinstance(info, dict) else DEFAULT_PROVIDER_URL
        dest = os.path.join(mods_dir, mod)
        if not force and os.path.isdir(dest) and os.path.isfile(os.path.join(dest, "manifest.json")):
            continue
        if not _restore_module_package(base_dir, yscb_root, mod, ver, prov, dest, os.path.join(mirror_dir, mod)):
            failed.append(mod)
    return 0 if not failed else 1


def cmd_event(argv: List[str]) -> int:
    return dispatch_module("core", ["event"] + argv)


def _ensure_jit_lifecycle_pre(cmd: str) -> None:
    if cmd not in ("init", "self-update", "restore", "bootstrap"):
        try:
            from core import events
            events.broadcast("pre_cli_dispatch", emit_module="core")
        except Exception:
            pass


def _ensure_jit_lifecycle_post(cmd: str, exit_code: int = 0) -> None:
    if cmd not in ("init", "self-update", "restore", "bootstrap"):
        try:
            from core import events
            events.broadcast("post_cli_dispatch", emit_module="core")
        except Exception:
            pass


def _read_module_manifest_version(manifest_path: str) -> Optional[str]:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version") if isinstance(data, dict) else None
    except Exception:
        return None


def _is_modules_dirty(base_dir: str, yscb_root: str, installed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not installed:
        return False, []
    mod_d = os.path.join(base_dir, yscb_root, ".modules")
    if not os.path.isdir(mod_d):
        return True, list(installed.keys())
    dirty = []
    for m, i in installed.items():
        m_dir = os.path.join(mod_d, m)
        mf_file = os.path.join(m_dir, "manifest.json")
        if not os.path.isdir(m_dir) or not os.path.isfile(mf_file):
            dirty.append(m)
        elif isinstance(i, dict) and i.get("version"):
            mf_ver = _read_module_manifest_version(mf_file)
            if mf_ver != i.get("version"):
                dirty.append(m)
    return bool(dirty), dirty


def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """模糊拼寫建議相容函式。"""
    from core.commands.dispatcher import _suggest_command as sc
    return sc(unknown_cmd, candidate_pool)


def _print_global_help() -> int:
    """幫助輸出相容函式。"""
    from core.commands.dispatcher import dispatch
    return dispatch(["--help"])


def dispatch_module(module_name: str, args: List[str]) -> int:
    """模組分派相容函式，全量委派 core.commands.dispatch。"""
    from core.commands.dispatcher import dispatch
    return dispatch([module_name] + args)


def main(argv: Optional[List[str]] = None) -> int:
    """
    YS-Codebase 單一主入口。
    職責：
    1. 執行 init 自舉 (若請求為 init)
    2. 探測注入私有微環境 (.venv) 與工作區環境邊界 (Token)
    3. 全量轉派至 core.commands.dispatch
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    # 1. 唯一入口職責 ①：自舉指令 (init, self-update 為唯二不經由 core 轉發的自舉)
    if argv and argv[0] == "init":
        return cmd_init(argv[1:])
    if argv and argv[0] == "self-update":
        return cmd_self_update(argv[1:])

    # 2. 唯一入口職責 ②：探測私有微環境 (.venv) 與設定安全邊界
    cfg_path, cfg = load_config()
    host_dir = os.path.dirname(cfg_path) if cfg_path else os.getcwd()
    yscb_rel = cfg.get("yscb_root", ".") if cfg else "."
    yscb_abs = os.path.normpath(os.path.join(host_dir, yscb_rel))

    _ensure_private_venv_path(yscb_abs)

    # =========================================================================
    # 🚨 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
    # 本專案嚴格遵循：虛擬機測試 (dev test) -> install @build -> 實機測試 流程。
    # 運行時 (Runtime) 僅允許載入 .modules/ 運行時空間，嚴禁直接運行開發環境 (source/) 程式碼。
    # 絕對禁止對此邏輯進行任何 fallback 至 source/ 或向 sys.path 插入 source/ 空間之刪改！
    # =========================================================================
    core_runtime_dir = os.path.join(yscb_abs, ".modules", "core")
    if os.path.isdir(core_runtime_dir):
        if core_runtime_dir in sys.path:
            sys.path.remove(core_runtime_dir)
        sys.path.insert(0, core_runtime_dir)

    os.environ["YSCB_HOST_DIR"] = host_dir
    os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"
    os.environ["PYTHONUNBUFFERED"] = "1"

    # 3. 轉派 core.commands.dispatch(argv)
    try:
        from core.commands import dispatch
        return dispatch(argv)
    except ImportError as e:
        print(f"[yscb] Error: Environment not initialized or core module missing ({e}). Run 'python yscb.py init' or 'python yscb.py init --fix' first.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
