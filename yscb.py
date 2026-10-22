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

__version__: str = "1.1.0.6"
CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release"
DEFAULT_SELF_UPDATE_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py"
INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="

CORE_COMMANDS: set = {
    "install", "update", "remove", "list", "status",
    "rollback", "reload", "restore", "bootstrap", "uri", "config", "event", "help",
    "self-update"
}

_MODULE_CACHE: Dict[str, Any] = {}


def _read_json_dict(path: str) -> Optional[Dict[str, Any]]:
    """安全讀取 JSON 檔案並確保返回 dict，失敗或非 dict 時返回 None。"""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json_lf(path: str, data: Dict[str, Any]) -> None:
    """以 UTF-8 與固定 LF 換行寫入格式化 JSON 檔案。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _normalize_local_path(raw: str, base_dir: Optional[str] = None) -> Optional[str]:
    """將 file:// URI 或本地相對/絕對路徑正規化為本機路徑；若為 HTTP(S) URL 則返回 None。"""
    s = (raw or "").strip()
    if not s or s.startswith(("http://", "https://")):
        return None
    if s.startswith("file://"):
        p = urllib.request.url2pathname(s[7:])
        while p.startswith("//"):
            p = p[1:]
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(base_dir, s)) if (base_dir and not os.path.isabs(s)) else os.path.normpath(s)


def _parse_flag_options(argv: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """統一解析自舉指令之旗標選項 (--fix, --force, --provider/-p, --url) 與位置參數。"""
    pos: List[str] = []
    opts: Dict[str, Any] = {"fix": False, "force": False, "provider": None, "url": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--fix":
            opts["fix"] = True
        elif a == "--force":
            opts["force"] = True
        elif a.startswith("--provider="):
            opts["provider"] = a.split("=", 1)[1].strip("\"'")
        elif a in ("--provider", "-p") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            opts["provider"] = argv[i + 1].strip("\"'")
            i += 1
        elif a.startswith("--url="):
            opts["url"] = a.split("=", 1)[1].strip("\"'")
        elif a == "--url" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            opts["url"] = argv[i + 1].strip("\"'")
            i += 1
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    return pos, opts


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


def _activate_runtime_env(yscb_abs: str, host_dir: Optional[str] = None) -> str:
    """
    統一掛載私有微環境與 .modules/core 運行時空間，並設定宿主安全邊界環境變數。
    [!] 剛性架構約束：僅允許載入 .modules/ 運行時空間，嚴禁直接載入或 fallback 至 source/！
    """
    _ensure_private_venv_path(yscb_abs)
    core_runtime_dir = os.path.join(yscb_abs, ".modules", "core")
    if os.path.isdir(core_runtime_dir):
        if core_runtime_dir in sys.path:
            sys.path.remove(core_runtime_dir)
        sys.path.insert(0, core_runtime_dir)
    if host_dir is not None:
        os.environ["YSCB_HOST_DIR"] = host_dir
        os.environ["YSCB_HOST_DISPATCH_TOKEN"] = "yscb_auth_dispatch"
    return core_runtime_dir


def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """剛性組態載入：僅探測當前目錄同層之 yscb.config.json。"""
    cfg_path = os.path.join(os.path.abspath(start_dir or os.getcwd()), CONFIG_FILENAME)
    if os.path.isfile(cfg_path):
        return cfg_path, _read_json_dict(cfg_path)
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
    elif os.path.isfile(source) and zipfile.is_zipfile(source):
        _extract_safe_zip(source, dest_dir)
    else:
        raise FileNotFoundError(f"[yscb] Error: Package source '{source}' not found or is not a valid zip archive.")


def _resolve_self_update_target_url(provider: Optional[str] = None, custom_url: Optional[str] = None) -> str:
    """解算 self-update 目標 URL：custom_url 優先，否則返回 DEFAULT_SELF_UPDATE_URL。"""
    return custom_url if custom_url else DEFAULT_SELF_UPDATE_URL


def _render_box_help(cmd_title: str, desc: str, usage: str, body_lines: List[str], pros: str) -> str:
    """統一渲染自舉指令 (init / self-update) 80 字元邊框 Help 訊息。"""
    lines = [
        "=" * 80,
        f"Command: {cmd_title}",
        "=" * 80,
        f"Description: {desc}",
        "Security   : [SAFE] 自主安全 (safe)",
        "Server Mode: [COLD-RUN] Local Cold Run Only",
        "",
        "USAGE:",
        f"  {usage}",
        "",
        *body_lines,
        "",
        "GLOBAL OPTIONS:",
        "  -h, --help                     Show this help message and exit",
        "",
        "RECOMMENDED USAGE (Pros):",
        f"  [+] {pros}",
        "=" * 80,
    ]
    return "\n".join(lines)


def _render_self_update_help() -> str:
    """渲染 self-update 指令幫助訊息。"""
    return _render_box_help(
        cmd_title="python yscb.py self-update",
        desc="Upgrade yscb.py host bootstrapper from repository root",
        usage="python yscb.py self-update [options]",
        body_lines=[
            "OPTIONS:",
            "  -- [Group: source]",
            "    --url <target_url>             Custom URL to download yscb.py",
        ],
        pros="升級宿主工程起手腳本 yscb.py 至最新版本",
    )


def cmd_self_update(argv: List[str]) -> int:
    """自遠端 Provider 或指定 URL 更新 yscb.py 本體。"""
    if "-h" in argv or "--help" in argv or (argv and argv[0] == "help"):
        print(_render_self_update_help())
        return 0
    _, opts = _parse_flag_options(argv)
    target_url = _resolve_self_update_target_url(custom_url=opts["url"])
    print(f"[yscb] Checking for latest yscb.py from: {target_url}")

    current_file = os.path.abspath(__file__)
    tmp_file = current_file + ".tmp"
    bak_file = current_file + ".bak"

    try:
        local_target = _normalize_local_path(target_url)
        if local_target and os.path.isfile(local_target):
            with open(local_target, "r", encoding="utf-8") as f:
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
        with open(tmp_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        shutil.copyfile(current_file, bak_file)
        os.replace(tmp_file, current_file)
        print(f"[yscb] yscb.py updated successfully (backup saved at {os.path.basename(bak_file)}).")
        try:
            cfg_path, cfg = load_config()
            host_dir = os.path.dirname(cfg_path) if cfg_path else os.getcwd()
            yscb_rel = cfg.get("yscb_root", ".") if cfg else "."
            _activate_runtime_env(os.path.normpath(os.path.join(host_dir, yscb_rel)))
            from core.update_checker import UpdateChecker
            UpdateChecker().invalidate_cache("yscb.py")
        except Exception:
            pass
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
    返回 (version_str, package_path_or_url)；若找不到或探測失敗則返回 (None, None)，嚴禁偽造預設版本。
    """
    p = (provider or DEFAULT_PROVIDER_URL).strip().rstrip("/")
    # 1. 本地目錄探測
    if not p.startswith(("http://", "https://")):
        cand_dirs = [os.path.join(p, "core"), os.path.join(p, "release", "core"), p]
        found_versions: Dict[str, str] = {}
        for c_dir in cand_dirs:
            if not os.path.isdir(c_dir):
                continue
            idx_data = _read_json_dict(os.path.join(c_dir, "index.json"))
            if idx_data and isinstance(idx_data.get("versions"), list):
                for v in idx_data["versions"]:
                    zip_cand = os.path.join(c_dir, f"{v}.zip")
                    if os.path.isfile(zip_cand):
                        found_versions[v] = zip_cand
            for f in os.listdir(c_dir):
                full_f = os.path.join(c_dir, f)
                if f.endswith(".zip"):
                    found_versions[f[:-4]] = full_f
                elif os.path.isdir(full_f):
                    m_data = _read_json_dict(os.path.join(full_f, "manifest.json"))
                    if m_data and m_data.get("version"):
                        found_versions[str(m_data["version"])] = full_f

        if found_versions:
            clean_pairs = [(_parse_simple_semver(v), v, pth) for v, pth in found_versions.items() if not _parse_simple_semver(v)[4]]
            pool = clean_pairs if clean_pairs else [(_parse_simple_semver(v), v, pth) for v, pth in found_versions.items()]
            pool.sort(key=lambda x: x[0], reverse=True)
            return pool[0][1], pool[0][2]

        for c_dir in (os.path.join(p, "core"), p):
            m_data = _read_json_dict(os.path.join(c_dir, "manifest.json"))
            if m_data and m_data.get("version"):
                return str(m_data["version"]), c_dir
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

    return None, None


def _is_core_healthy(core_module_dir: str) -> Tuple[bool, Optional[str]]:
    """檢測 core 模組安裝是否正常完整。"""
    data = _read_json_dict(os.path.join(core_module_dir, "manifest.json"))
    if not data:
        return False, None
    ver = data.get("version")
    entry = data.get("entry", "scripts/cli.py")
    if not ver or not os.path.isfile(os.path.join(core_module_dir, entry)):
        return False, None
    return True, str(ver)


def _render_init_help() -> str:
    """渲染 init 指令幫助訊息。"""
    return _render_box_help(
        cmd_title="python yscb.py init",
        desc="Initialize workspace and unpack core module",
        usage="python yscb.py init [root] [options]",
        body_lines=[
            "ARGUMENTS:",
            "  [root]                         Target directory for YSCB environment (default: .yscb) [optional]",
            "",
            "OPTIONS:",
            "  -- [Group: mode]",
            "    --fix                          Check and repair damaged or missing core module",
            "    --force                        Force re-download and re-unpack core module",
            "  -- [Group: source]",
            "    --provider <url>               Module provider URL or path (alias: -p)",
        ],
        pros="初次引入 YSCB 或自癒修復核心運行時環境",
    )


def cmd_init(argv: List[str]) -> int:
    """唯一入口職責 ①：極簡自舉：初始化工作區或自癒修復並解壓 core 模組。"""
    if "-h" in argv or "--help" in argv or (argv and argv[0] == "help"):
        print(_render_init_help())
        return 0
    clean_argv, opts = _parse_flag_options(argv)
    is_fix, is_force = opts["fix"], opts["force"]
    explicit_prov = opts["provider"]

    base_dir = os.path.abspath(os.getcwd())
    cfg_path = os.path.join(base_dir, CONFIG_FILENAME)
    has_cfg = os.path.isfile(cfg_path)

    if has_cfg:
        cfg = _read_json_dict(cfg_path)
        if cfg is None:
            print(f"[yscb] Error: Configuration at '{cfg_path}' is corrupted.")
            return 1

        yscb_root = cfg.get("yscb_root", clean_argv[0] if clean_argv else ".yscb")
        target_prov = explicit_prov if explicit_prov else cfg.get("default_provider", DEFAULT_PROVIDER_URL)
        yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
        core_module_dir = os.path.join(yscb_abs, ".modules", "core")
        is_healthy, current_ver = _is_core_healthy(core_module_dir)

        if is_fix and is_healthy and not is_force:
            print(f"[yscb] Core module at '{yscb_root}' is already healthy (core@{current_ver}). No repair needed.")
            return 0
        if not is_fix and is_healthy:
            print(f"[yscb] Error: Configuration already exists at '{cfg_path}'. Use 'python yscb.py init --fix' to repair or reinstall core.")
            return 1
        print(f"[yscb] Repairing core module at '{yscb_root}' from provider '{target_prov}'...")
        action_tag = "fix"
    else:
        yscb_root = clean_argv[0] if clean_argv else ".yscb"
        target_prov = explicit_prov or DEFAULT_PROVIDER_URL
        yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
        core_module_dir = os.path.join(yscb_abs, ".modules", "core")
        cfg = {"yscb_root": yscb_root, "default_provider": target_prov, "installed_modules": {}}
        print(f"[yscb] Initializing environment at '{yscb_root}'...")
        action_tag = "init"

    ver, source = _discover_latest_core(target_prov)
    if not source or not ver:
        print(f"[yscb] Error: Cannot locate core package in provider '{target_prov}'.")
        return 1

    os.makedirs(os.path.join(yscb_abs, ".mirror", "core"), exist_ok=True)
    _fetch_and_extract_zip(source, core_module_dir)
    if not isinstance(cfg.get("installed_modules"), dict):
        cfg["installed_modules"] = {}
    cfg["installed_modules"]["core"] = {"version": ver, "installed_at": action_tag, "provider": target_prov}
    cfg["default_provider"] = target_prov
    _write_json_lf(cfg_path, cfg)

    verb = "repaired core" if has_cfg else "initialized"
    print(f"[yscb] Successfully {verb} (core@{ver}). Triggering initial reload...")
    _activate_runtime_env(yscb_abs, host_dir=base_dir)
    rc = dispatch_module("core", ["reload"])
    if not has_cfg and rc == 0:
        _print_init_next_steps(yscb_root)
    return rc


def _print_init_next_steps(yscb_root: str) -> None:
    """於全新工作區初始化完成後輸出結構化 Next Steps 引導卡片。"""
    print("\n" + "-" * 72)
    print("[Next Steps] YS-Codebase Workspace Onboarding Guide:")
    print("  1. Bind host project root : python yscb.py config set core project_root ./")
    print("  2. Verify URI health      : python yscb.py uri check")
    print("  3. Install core ecosystem : python yscb.py install agents-workflow")
    print("                              python yscb.py install knowledge-db")
    print("                              python yscb.py install server")
    print(f"  * Documentation           : {yscb_root}/.modules/core/README.md")
    print("-" * 72)


def _generate_internal_gitignore(yscb_dir: str) -> None:
    _activate_runtime_env(yscb_dir)
    try:
        from core.installer import generate_internal_gitignore
        generate_internal_gitignore(yscb_dir)
    except Exception:
        pass


def _print_missing_source_remediation(module_name: str, version: str, provider_arg: str) -> None:
    """當組態宣告之確定來源遺失或無法下載時，輸出明確錯誤訊息與建議修復措施。"""
    print(f"[yscb] 錯誤: '{module_name}' 模組 (v{version}) 來源 '{provider_arg}' 已遺失或無法存取，需手動修復。")
    print("       建議措施為:")
    if module_name == "core":
        print("         1. 修復核心模組並切換來源 : python yscb.py init --fix [--provider <valid_url_or_path>]")
    else:
        print(f"         1. 重新指定來源安裝該模組 : python yscb.py install {module_name} --force [--provider <valid_url_or_path>]")
    print("         2. 以指定來源全量還原環境 : python yscb.py restore --force --provider <valid_url_or_path>")
    print(f"         3. 檢查並修正 '{CONFIG_FILENAME}' 中 '{module_name}' 的 version / provider 設定")


def _extract_and_cache_mirror(src_path: str, dest_dir: str, mirror_dir: str, mirror_zip: str) -> bool:
    """提取套件至 dest_dir 並於來源為 zip 檔時同步快取至 mirror_zip。"""
    try:
        os.makedirs(dest_dir, exist_ok=True)
        os.makedirs(mirror_dir, exist_ok=True)
        _fetch_and_extract_zip(src_path, dest_dir)
        if os.path.isfile(src_path) and zipfile.is_zipfile(src_path) and os.path.abspath(src_path) != os.path.abspath(mirror_zip):
            try:
                shutil.copy2(src_path, mirror_zip)
            except Exception:
                pass
        return True
    except Exception:
        return False


def _bootstrap_package_from_provider(
    base_dir: str,
    yscb_root: str,
    module_name: str,
    version: str,
    provider_arg: str,
    dest_dir: str,
    mirror_dir: str,
) -> bool:
    """純標準庫零依賴（不依賴 core）嚴格依組態確定之 version 與 provider_arg 提取模組至 dest_dir 與 mirror_dir（禁止跨版本猜測 fallback）。"""
    if not version or not provider_arg:
        return False

    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    mirror_zip = os.path.join(mirror_dir, f"{version}.zip")

    # 1. 若為 .build 版本且本地 yscb_abs/.build/<mod>/<ver>.zip 存在，優先提取
    if version == "build" or version.endswith(".build"):
        dot_build_zip = os.path.join(yscb_abs, ".build", module_name, f"{version}.zip")
        if os.path.isfile(dot_build_zip) and _extract_and_cache_mirror(dot_build_zip, dest_dir, mirror_dir, mirror_zip):
            return True

    # 2. 本地鏡像庫 (.mirror/<mod>/<ver>.zip) 精確版本命中
    if os.path.isfile(mirror_zip) and _extract_and_cache_mirror(mirror_zip, dest_dir, mirror_dir, mirror_zip):
        return True

    # 3. 檢查組態指定之本地 Provider 路徑（僅接受精確版本 <mod>/<ver>.zip 或 <mod>/<ver>）
    p_arg = provider_arg.strip()
    p_abs = _normalize_local_path(p_arg, base_dir=base_dir)
    if p_abs and os.path.isdir(p_abs):
        candidates = (
            os.path.join(p_abs, module_name, f"{version}.zip"),
            os.path.join(p_abs, module_name, f"{version}"),
            os.path.join(p_abs, "release", module_name, f"{version}.zip"),
        )
        found = next((c for c in candidates if os.path.exists(c)), None)
        if found and _extract_and_cache_mirror(found, dest_dir, mirror_dir, mirror_zip):
            return True

    # 4. 檢查組態指定之遠端 Provider (HTTP/HTTPS) 精確版本 URL
    if p_arg.startswith(("http://", "https://")):
        remote_zip_url = f"{p_arg.rstrip('/')}/{module_name}/{version}.zip"
        if _extract_and_cache_mirror(remote_zip_url, dest_dir, mirror_dir, mirror_zip):
            return True

    return False


def _restore_module_package(base_dir: str, yscb_root: str, module_name: str, version: str, provider_arg: str, dest_dir: str, mirror_dir: str) -> bool:
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    core_dir = _activate_runtime_env(yscb_abs)
    if _is_core_healthy(core_dir)[0]:
        from core.installer import Installer
        return Installer()._restore_module_package(base_dir, yscb_root, module_name, version, provider_arg, dest_dir, mirror_dir)
    return _bootstrap_package_from_provider(base_dir, yscb_root, module_name, version, provider_arg, dest_dir, mirror_dir)


def _auto_bootstrap_and_restore_if_needed(host_dir: str, yscb_rel: str, cfg: Dict[str, Any], target_cmd: str) -> bool:
    """
    自適應環境重建：當 yscb.config.json 存在，但 .modules/core 尚未下載或 installed_modules 有缺失時，
    嚴格依據組態已知之 provider 與 version 下載 core 後觸發 restore 重建運行環境；
    若確定來源已遺失或無法下載，立即阻斷並提示手動修復措施（禁止跨版本猜測 fallback）。
    """
    yscb_abs = os.path.normpath(os.path.join(host_dir, yscb_rel))
    installed = cfg.get("installed_modules", {})
    if not isinstance(installed, dict):
        installed = {}

    core_module_dir = os.path.join(yscb_abs, ".modules", "core")
    core_healthy, _ = _is_core_healthy(core_module_dir)
    is_dirty, _ = _is_modules_dirty(host_dir, yscb_rel, installed)

    if core_healthy and not is_dirty:
        return True

    default_prov = cfg.get("default_provider", "")

    # Step 1: 若 core 尚未安裝或損毀，嚴格依組態宣告之 version 與 provider 下載 core
    if not core_healthy:
        core_info = installed.get("core")
        core_ver = core_info.get("version") if isinstance(core_info, dict) else None
        core_prov = (core_info.get("provider") if isinstance(core_info, dict) else None) or default_prov
        if not core_ver or not core_prov:
            _print_missing_source_remediation("core", str(core_ver or "unknown"), str(core_prov or "unknown"))
            return False

        print(f"[yscb] Core runtime missing at '{yscb_rel}/.modules/core'. Auto-bootstrapping core@{core_ver} from '{core_prov}'...")
        ok = _bootstrap_package_from_provider(
            host_dir, yscb_rel, "core", core_ver, core_prov,
            core_module_dir, os.path.join(yscb_abs, ".mirror", "core"),
        )
        if not ok or not _is_core_healthy(core_module_dir)[0]:
            _print_missing_source_remediation("core", core_ver, core_prov)
            return False

    _activate_runtime_env(yscb_abs, host_dir=host_dir)

    # Step 2: 若使用者原本執行的就是 restore，交由後續 dispatch 直接執行 restore，避免重複執行兩次
    if target_cmd == "restore":
        return True

    # Step 3: 若仍有缺漏模組或剛完成 core 自舉，自動觸發 restore 重建運行環境
    still_dirty, remaining_mods = _is_modules_dirty(host_dir, yscb_rel, installed)
    if not core_healthy or still_dirty:
        if remaining_mods:
            print(f"[yscb] Missing runtime modules detected ({', '.join(remaining_mods)}). Triggering auto-restore...")
        else:
            print("[yscb] Triggering auto-restore to reconcile runtime environment...")
        return dispatch_module("core", ["restore"]) == 0

    return True


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
    default_prov = cfg.get("default_provider", "")
    for mod, info in sorted(installed.items(), key=lambda x: (0 if x[0] == "core" else 1, x[0])):
        ver = info.get("version", "") if isinstance(info, dict) else str(info)
        prov = (info.get("provider") if isinstance(info, dict) else None) or default_prov
        dest = os.path.join(mods_dir, mod)
        if not force and os.path.isdir(dest) and os.path.isfile(os.path.join(dest, "manifest.json")):
            continue
        if not ver or not prov or not _restore_module_package(base_dir, yscb_root, mod, ver, prov, dest, os.path.join(mirror_dir, mod)):
            _print_missing_source_remediation(mod, str(ver or "unknown"), str(prov or "unknown"))
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
    data = _read_json_dict(manifest_path)
    return str(data["version"]) if (data and data.get("version")) else None


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
            if _read_module_manifest_version(mf_file) != i.get("version"):
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
    1. 執行 init / self-update 自舉
    2. 探測注入私有微環境 (.venv)、.modules/core 與工作區安全邊界 (Token)
    3. 自適應環境重建 (當 yscb.config.json 存在但 .modules 尚未物化時)
    4. 全量轉派至 core.commands.dispatch
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "init":
        return cmd_init(argv[1:])
    if argv and argv[0] == "self-update":
        return cmd_self_update(argv[1:])

    cfg_path, cfg = load_config()
    host_dir = os.path.dirname(cfg_path) if cfg_path else os.getcwd()
    yscb_rel = cfg.get("yscb_root", ".") if cfg else "."
    yscb_abs = os.path.normpath(os.path.join(host_dir, yscb_rel))

    # =========================================================================
    # 🚨 剛性架構約束 (Rigid Architectural Guardrail) - 嚴禁擅自改動！
    # 本專案嚴格遵循：虛擬機測試 (dev test) -> install @build -> 實機測試 流程。
    # 運行時 (Runtime) 僅允許載入 .modules/ 運行時空間，嚴禁直接運行開發環境 (source/) 程式碼。
    # 絕對禁止對此邏輯進行任何 fallback 至 source/ 或向 sys.path 插入 source/ 空間之刪改！
    # =========================================================================
    _activate_runtime_env(yscb_abs, host_dir=host_dir)
    os.environ["PYTHONUNBUFFERED"] = "1"

    if cfg is not None:
        primary_arg = argv[0] if argv else ""
        if not _auto_bootstrap_and_restore_if_needed(host_dir, yscb_rel, cfg, primary_arg):
            return 1
        _activate_runtime_env(yscb_abs, host_dir=host_dir)

    try:
        from core.commands import dispatch
        return dispatch(argv)
    except ImportError as e:
        print(f"[yscb] Error: Environment not initialized or core module missing ({e}). Run 'python yscb.py init' or 'python yscb.py init --fix' first.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
