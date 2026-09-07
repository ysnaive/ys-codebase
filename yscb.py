"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & Thin Router.
100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import Any, Dict, List, Optional, Tuple
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
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release"
INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="

CORE_COMMANDS: set = {
    "install", "update", "remove", "list", "status",
    "rollback", "reload", "restore", "bootstrap", "uri", "config", "event", "help"
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


def cmd_init(argv: List[str]) -> int:
    """唯一入口職責 ①：極簡自舉：初始化工作區並解壓 core 模組。"""
    provider = DEFAULT_PROVIDER_URL
    clean_argv = [a for a in argv if not a.startswith("--provider=")]
    for a in argv:
        if a.startswith("--provider="):
            provider = a.split("=", 1)[1].strip("\"'")
    yscb_root = clean_argv[0] if clean_argv else "."
    base_dir, cfg_path = os.path.abspath(os.getcwd()), os.path.join(os.path.abspath(os.getcwd()), CONFIG_FILENAME)
    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    if os.path.exists(cfg_path):
        print(f"[yscb] Error: Configuration already exists at '{cfg_path}'.")
        return 1
    os.makedirs(os.path.join(yscb_abs, ".mirror", "core"), exist_ok=True)
    candidates = [
        os.path.join(provider, "core", "1.0.0.0.zip"),
        os.path.join(provider, "release", "core", "1.0.0.0.zip"),
        os.path.join(provider, "core"),
    ]
    source = (
        next((c for c in candidates if os.path.exists(c)), None)
        if os.path.isdir(provider)
        else (provider.rstrip("/") + "/core/1.0.0.0.zip" if provider.startswith(("http://", "https://")) else None)
    )
    if not source:
        print(f"[yscb] Error: Cannot locate core package in provider '{provider}'.")
        return 1
    print(f"[yscb] Initializing environment at '{yscb_root}'...")
    _fetch_and_extract_zip(source, os.path.join(yscb_abs, ".modules", "core"))
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "yscb_root": yscb_root,
                "default_provider": provider,
                "installed_modules": {
                    "core": {
                        "version": "1.0.0.0",
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
    print("[yscb] Successfully initialized. Triggering initial reload...")
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
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    # 1. 唯一入口職責 ①：init 自舉
    if argv and argv[0] == "init":
        return cmd_init(argv[1:])

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
        print(f"[yscb] Error: Environment not initialized or core module missing ({e}). Run 'python yscb.py init <yscbRoot>' first.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
