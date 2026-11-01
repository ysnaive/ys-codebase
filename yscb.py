"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & Thin Router.
100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import Any, Dict, List, Optional, Tuple
import ast
import difflib
import fnmatch
import importlib.util
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile

__version__: str = "1.2.1.0"
CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases"
LEGACY_PROVIDER_URLS: Tuple[str, ...] = (
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/",
)
DEFAULT_SELF_UPDATE_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py"
INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="
_RELEASE_PACKAGE_IGNORES: Tuple[str, ...] = (
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".git*",
    ".pytest_cache",
    ".DS_Store",
    ".yscbignore",
    "tests",
    "tests/*",
)

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


def _normalize_provider_url(url: Optional[str]) -> str:
    """將指向舊官方 main 分支之 Provider URL 無感遷移至 releases 分支。"""
    s = (url or "").strip()
    if s in LEGACY_PROVIDER_URLS:
        return DEFAULT_PROVIDER_URL
    return s


def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """剛性組態載入：僅探測當前目錄同層之 yscb.config.json，並自動遷移舊版官方 Provider URL。"""
    cfg_path = os.path.join(os.path.abspath(start_dir or os.getcwd()), CONFIG_FILENAME)
    if os.path.isfile(cfg_path):
        data = _read_json_dict(cfg_path)
        if isinstance(data, dict):
            changed = False
            dp = data.get("default_provider")
            if isinstance(dp, str) and dp.strip() in LEGACY_PROVIDER_URLS:
                data["default_provider"] = DEFAULT_PROVIDER_URL
                changed = True
            inst = data.get("installed_modules")
            if isinstance(inst, dict):
                for m_info in inst.values():
                    if isinstance(m_info, dict):
                        mp = m_info.get("provider")
                        if isinstance(mp, str) and mp.strip() in LEGACY_PROVIDER_URLS:
                            m_info["provider"] = DEFAULT_PROVIDER_URL
                            changed = True
            if changed:
                try:
                    _write_json_lf(cfg_path, data)
                except Exception:
                    pass
        return cfg_path, data
    return None, None


def _should_ignore_rel_path(rel_path: str, ignores: List[str]) -> bool:
    norm_rel = rel_path.replace("\\", "/").rstrip("/")
    name = os.path.basename(norm_rel)
    for pattern in ignores:
        pat = pattern.replace("\\", "/").rstrip("/")
        if (
            fnmatch.fnmatch(name, pat)
            or fnmatch.fnmatch(norm_rel, pat)
            or fnmatch.fnmatch(norm_rel, pat + "/*")
            or norm_rel.startswith(pat.rstrip("*").rstrip("/") + "/")
        ):
            return True
    return False


def _package_source_to_zip_if_exact_version(
    source_dir: str,
    target_version: str,
    dest_zip_path: str,
    release_zip_path: Optional[str] = None,
) -> bool:
    """當本地 source/<mod>/manifest.json 存在且版本與 target_version 嚴格相等時，以純標準庫打包至 dest_zip_path。"""
    if not source_dir or not os.path.isdir(source_dir):
        return False
    mf_path = os.path.join(source_dir, "manifest.json")
    mf_data = _read_json_dict(mf_path)
    if not mf_data or str(mf_data.get("version", "")).strip() != str(target_version).strip():
        return False

    ignores = list(_RELEASE_PACKAGE_IGNORES)
    yscbignore_path = os.path.join(source_dir, ".yscbignore")
    if os.path.isfile(yscbignore_path):
        try:
            with open(yscbignore_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        ignores.append(s)
        except Exception:
            pass

    os.makedirs(os.path.dirname(os.path.abspath(dest_zip_path)), exist_ok=True)
    tmp_zip = dest_zip_path + f".tmp_{os.getpid()}"
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source_dir):
                rel_dir = os.path.relpath(root, source_dir).replace("\\", "/")
                if rel_dir == ".":
                    rel_dir = ""
                dirs[:] = [d for d in dirs if not _should_ignore_rel_path(f"{rel_dir}/{d}".lstrip("/"), ignores)]
                for fname in files:
                    rel_file = f"{rel_dir}/{fname}".lstrip("/")
                    if not _should_ignore_rel_path(rel_file, ignores):
                        src_f = os.path.join(root, fname)
                        if rel_file == "manifest.json":
                            m_copy = dict(mf_data)
                            m_copy["version"] = target_version
                            zf.writestr("manifest.json", json.dumps(m_copy, indent=2, ensure_ascii=False))
                        else:
                            zf.write(src_f, arcname=rel_file)
        if os.path.exists(dest_zip_path):
            os.remove(dest_zip_path)
        os.replace(tmp_zip, dest_zip_path)
        if release_zip_path and os.path.abspath(release_zip_path) != os.path.abspath(dest_zip_path):
            try:
                os.makedirs(os.path.dirname(os.path.abspath(release_zip_path)), exist_ok=True)
                shutil.copy2(dest_zip_path, release_zip_path)
            except Exception:
                pass
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(tmp_zip):
            try:
                os.remove(tmp_zip)
            except Exception:
                pass


def _find_matching_source_dir(module_name: str, candidate_roots: List[str]) -> Optional[str]:
    """於候選根目錄下探測 source/<module_name> 目錄。"""
    for r in candidate_roots:
        if not r:
            continue
        for cand in (
            os.path.join(r, "source", module_name),
            os.path.join(os.path.dirname(r), "source", module_name),
            os.path.join(r, "ys_codebase", "source", module_name),
        ):
            if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "manifest.json")):
                return cand
    return None


def _resolve_same_triplet_fallback_version(
    provider: str,
    module_name: str,
    requested_version: str,
    base_dir: Optional[str] = None,
) -> Optional[str]:
    """當請求版本已被滑動視窗淘汰 (pruned) 時，自 index.json 尋找同三元組 (X.Y.Z.*) 最高可用 active 版本。"""
    req_t = _parse_simple_semver(requested_version)
    if req_t[4]:
        return None
    req_triplet = (req_t[0], req_t[1], req_t[2])
    p = _normalize_provider_url(provider).rstrip("/")
    idx_data: Optional[Dict[str, Any]] = None

    if not p.startswith(("http://", "https://")):
        p_abs = _normalize_local_path(p, base_dir=base_dir)
        if p_abs and os.path.isdir(p_abs):
            for idx_cand in (
                os.path.join(p_abs, module_name, "index.json"),
                os.path.join(p_abs, "release", module_name, "index.json"),
                os.path.join(p_abs, "index.json") if os.path.basename(p_abs) == module_name else "",
            ):
                if idx_cand and os.path.isfile(idx_cand):
                    idx_data = _read_json_dict(idx_cand)
                    if idx_data:
                        break
    else:
        try:
            idx_url = f"{p}/{module_name}/index.json"
            req = urllib.request.Request(idx_url, headers={"User-Agent": "yscb-host/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                if isinstance(raw, dict):
                    idx_data = raw
        except Exception:
            idx_data = None

    if not isinstance(idx_data, dict):
        return None
    active_vers = idx_data.get("versions")
    if not isinstance(active_vers, list) or requested_version in active_vers:
        return None

    same_triplet_cands: List[Tuple[Tuple[int, int, int, int, bool], str]] = []
    for v in active_vers:
        if not isinstance(v, str):
            continue
        vt = _parse_simple_semver(v)
        if not vt[4] and (vt[0], vt[1], vt[2]) == req_triplet:
            same_triplet_cands.append((vt, v))

    if not same_triplet_cands:
        return None
    same_triplet_cands.sort(key=lambda x: x[0], reverse=True)
    return same_triplet_cands[0][1]


def _extract_safe_zip(zip_path: str, dest_dir: str) -> None:
    dest_abs = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for m in zf.infolist():
            tgt = os.path.abspath(os.path.join(dest_abs, m.filename))
            if not tgt.startswith(dest_abs + os.sep) and tgt != dest_abs:
                raise RuntimeError(f"Zip Slip vulnerability detected: '{m.filename}'")
        zf.extractall(dest_dir)


def _is_dir_handle_locked_for_rename(err: OSError, parent_dir: str, target_dir: str) -> bool:
    """三階段跨平台鑑別器：區分宿主機/virtiofs 目錄句柄暫態鎖定與真正的檔案系統權限/I/O 故障。"""
    import errno
    import time
    err_no = getattr(err, "errno", None)
    win_err = getattr(err, "winerror", None)
    if err_no not in (errno.EACCES, errno.EBUSY, errno.EPERM) and win_err not in (5, 32):
        return False
    if not os.path.isdir(parent_dir) or not os.path.isdir(target_dir):
        return False

    req_mode = os.W_OK if os.name == "nt" else (os.W_OK | os.X_OK)
    if not os.access(parent_dir, req_mode) or not os.access(target_dir, req_mode):
        return False

    probe_src = os.path.join(target_dir, f".yscb_probe_src_{os.getpid()}_{int(time.time() * 1000)}")
    probe_dst = os.path.join(target_dir, f".yscb_probe_dst_{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(probe_src, "wb") as f:
            f.write(b"1")
            f.flush()
        os.replace(probe_src, probe_dst)
        os.remove(probe_dst)
        return True
    except Exception:
        return False
    finally:
        for p in (probe_src, probe_dst):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _inplace_atomic_sync_dir(staging_dir: str, target_dir: str) -> None:
    """階段三：當目錄級 rename 因句柄鎖定被拒且通過寫入探針時，執行全有全無 (All-or-Nothing) 檔案級原子同步與異常回滾。"""
    import stat
    import time

    staging_abs = os.path.abspath(staging_dir)
    target_abs = os.path.abspath(target_dir)
    parent_dir = os.path.dirname(target_abs)
    base_name = os.path.basename(target_abs)
    backup_dir = os.path.join(parent_dir, f".old_backup_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")

    existing_rel_files = set()
    os.makedirs(backup_dir, exist_ok=True)
    try:
        for root, dirs, files in os.walk(target_abs):
            dirs[:] = [d for d in dirs if not d.startswith((".old_", ".staging_", ".yscb_probe_"))]
            rel_root = os.path.relpath(root, target_abs)
            if rel_root == ".":
                rel_root = ""
            for fname in files:
                if fname.startswith((".yscb_probe_", ".yscb_tmp_")):
                    continue
                rel_path = os.path.join(rel_root, fname) if rel_root else fname
                norm_rel = rel_path.replace("\\", "/")
                existing_rel_files.add(norm_rel)
                src_f = os.path.join(root, fname)
                bak_f = os.path.join(backup_dir, rel_path)
                os.makedirs(os.path.dirname(bak_f), exist_ok=True)
                shutil.copy2(src_f, bak_f)

        staged_rel_files = set()
        for root, dirs, files in os.walk(staging_abs):
            rel_root = os.path.relpath(root, staging_abs)
            if rel_root == ".":
                rel_root = ""
            target_sub = os.path.join(target_abs, rel_root) if rel_root else target_abs
            os.makedirs(target_sub, exist_ok=True)
            for fname in files:
                rel_path = os.path.join(rel_root, fname) if rel_root else fname
                norm_rel = rel_path.replace("\\", "/")
                staged_rel_files.add(norm_rel)
                src_f = os.path.join(root, fname)
                dst_f = os.path.join(target_abs, rel_path)
                tmp_dst = os.path.join(os.path.dirname(dst_f), f".yscb_tmp_{os.getpid()}_{fname}")
                try:
                    if os.path.exists(dst_f) and not os.access(dst_f, os.W_OK):
                        try:
                            os.chmod(dst_f, stat.S_IWRITE | stat.S_IREAD)
                        except Exception:
                            pass
                    shutil.copy2(src_f, tmp_dst)
                    os.replace(tmp_dst, dst_f)
                finally:
                    if os.path.exists(tmp_dst):
                        try:
                            os.remove(tmp_dst)
                        except Exception:
                            pass

        for norm_rel in existing_rel_files - staged_rel_files:
            obs_f = os.path.join(target_abs, norm_rel.replace("/", os.sep))
            if os.path.isfile(obs_f):
                try:
                    os.chmod(obs_f, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
                os.remove(obs_f)

        for root, dirs, _ in os.walk(target_abs, topdown=False):
            for d in dirs:
                d_abs = os.path.join(root, d)
                rel_d = os.path.relpath(d_abs, target_abs)
                staged_d = os.path.join(staging_abs, rel_d)
                if not os.path.exists(staged_d):
                    try:
                        if not os.listdir(d_abs):
                            os.rmdir(d_abs)
                    except OSError:
                        pass
    except Exception:
        try:
            for root, _, files in os.walk(target_abs):
                rel_root = os.path.relpath(root, target_abs)
                if rel_root == ".":
                    rel_root = ""
                for fname in files:
                    rel_path = os.path.join(rel_root, fname) if rel_root else fname
                    norm_rel = rel_path.replace("\\", "/")
                    if norm_rel not in existing_rel_files:
                        try:
                            os.remove(os.path.join(root, fname))
                        except Exception:
                            pass
            for norm_rel in existing_rel_files:
                rel_os = norm_rel.replace("/", os.sep)
                bak_f = os.path.join(backup_dir, rel_os)
                dst_f = os.path.join(target_abs, rel_os)
                if os.path.isfile(bak_f):
                    os.makedirs(os.path.dirname(dst_f), exist_ok=True)
                    tmp_restore = os.path.join(os.path.dirname(dst_f), f".yscb_restore_{os.getpid()}_{os.path.basename(dst_f)}")
                    shutil.copy2(bak_f, tmp_restore)
                    os.replace(tmp_restore, dst_f)
        except Exception:
            pass
        raise
    finally:
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)


def _fetch_and_extract_zip(source: str, dest_dir: str) -> None:
    """自舉提取壓縮包至同父目錄 .staging 臨時空間，完成後原子替換至 dest_dir，嚴防 Zip Slip 與非原子撕裂。"""
    dest_abs = os.path.abspath(dest_dir)
    parent_dir = os.path.dirname(dest_abs)
    base_name = os.path.basename(dest_abs)
    os.makedirs(parent_dir, exist_ok=True)
    staging_dir = os.path.join(parent_dir, f".staging_{base_name}_{os.getpid()}")
    old_dir = os.path.join(parent_dir, f".old_{base_name}_{os.getpid()}")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir, exist_ok=True)

    try:
        if source.startswith(("http://", "https://")):
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
                tmp_p = tmp_f.name
            try:
                req = urllib.request.Request(source, headers={"User-Agent": "yscb-host/2.0"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_p, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                _extract_safe_zip(tmp_p, staging_dir)
            finally:
                if os.path.exists(tmp_p):
                    try:
                        os.remove(tmp_p)
                    except Exception:
                        pass
        elif os.path.isdir(source):
            shutil.copytree(source, staging_dir, dirs_exist_ok=True)
        elif os.path.isfile(source) and zipfile.is_zipfile(source):
            _extract_safe_zip(source, staging_dir)
        else:
            raise FileNotFoundError(f"[yscb] Error: Package source '{source}' not found or is not a valid zip archive.")

        moved_old = False
        try:
            if os.path.exists(old_dir):
                shutil.rmtree(old_dir, ignore_errors=True)
            if os.path.exists(dest_abs):
                try:
                    os.replace(dest_abs, old_dir)
                    moved_old = True
                except OSError as rename_err:
                    if _is_dir_handle_locked_for_rename(rename_err, parent_dir, dest_abs):
                        _inplace_atomic_sync_dir(staging_dir, dest_abs)
                        return
                    raise
            os.replace(staging_dir, dest_abs)
        except Exception:
            if moved_old and not os.path.exists(dest_abs) and os.path.exists(old_dir):
                try:
                    os.replace(old_dir, dest_abs)
                except Exception:
                    pass
            raise
    finally:
        if os.path.exists(old_dir):
            shutil.rmtree(old_dir, ignore_errors=True)
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


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
    p = _normalize_provider_url(provider or DEFAULT_PROVIDER_URL).strip().rstrip("/")
    # 1. 本地目錄探測
    if not p.startswith(("http://", "https://")):
        p_abs = _normalize_local_path(p) or p
        cand_dirs = [os.path.join(p_abs, "core"), os.path.join(p_abs, "release", "core"), p_abs]
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
                    else:
                        src_dir = _find_matching_source_dir("core", [c_dir, os.path.dirname(c_dir), p_abs, os.getcwd()])
                        if src_dir and _package_source_to_zip_if_exact_version(src_dir, str(v), zip_cand):
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

        for c_dir in (os.path.join(p_abs, "core"), p_abs):
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
        target_prov = _normalize_provider_url(explicit_prov if explicit_prov else cfg.get("default_provider", DEFAULT_PROVIDER_URL))
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
        target_prov = _normalize_provider_url(explicit_prov or DEFAULT_PROVIDER_URL)
        yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
        core_module_dir = os.path.join(yscb_abs, ".modules", "core")
        cfg = {"yscb_root": yscb_root, "default_provider": target_prov, "installed_modules": {}}
        print(f"[yscb] Initializing environment at '{yscb_root}'...")
        action_tag = "init"

    ver, source = _discover_latest_core(target_prov)
    if not source or not ver:
        print(f"[yscb] Error: Cannot locate core package in provider '{target_prov}'.")
        return 1

    core_mirror_dir = os.path.join(yscb_abs, ".mirror", "core")
    os.makedirs(core_mirror_dir, exist_ok=True)
    _fetch_and_extract_zip(source, core_module_dir)
    if os.path.isfile(source) and zipfile.is_zipfile(source):
        mirror_zip = os.path.join(core_mirror_dir, f"{ver}.zip")
        if os.path.abspath(source) != os.path.abspath(mirror_zip):
            try:
                shutil.copy2(source, mirror_zip)
            except Exception:
                pass
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


def _update_config_module_version(base_dir: str, module_name: str, new_version: str) -> None:
    """當發生同三元組 (X.Y.Z.*) pruned 版本自動降級還原時，同步更新 yscb.config.json 中該模組之鎖定版本。"""
    cfg_path = os.path.join(base_dir, CONFIG_FILENAME)
    cfg = _read_json_dict(cfg_path)
    if not isinstance(cfg, dict):
        return
    inst = cfg.get("installed_modules")
    if isinstance(inst, dict) and module_name in inst:
        if isinstance(inst[module_name], dict):
            inst[module_name]["version"] = new_version
        else:
            inst[module_name] = {"version": new_version}
        try:
            _write_json_lf(cfg_path, cfg)
        except Exception:
            pass


def _bootstrap_package_from_provider(
    base_dir: str,
    yscb_root: str,
    module_name: str,
    version: str,
    provider_arg: str,
    dest_dir: str,
    mirror_dir: str,
    _allow_fallback: bool = True,
) -> bool:
    """純標準庫零依賴（不依賴 core）嚴格依組態確定之 version 與 provider_arg 提取模組至 dest_dir 與 mirror_dir。"""
    if not version or not provider_arg:
        return False

    yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
    mirror_zip = os.path.join(mirror_dir, f"{version}.zip")
    p_arg = _normalize_provider_url(provider_arg)

    # 1. 若為 .build 版本且本地 yscb_abs/.build/<mod>/<ver>.zip 存在，優先提取（若升版覆寫則匹配最新 .build.zip）
    if version == "build" or version.endswith(".build"):
        dot_build_zip = os.path.join(yscb_abs, ".build", module_name, f"{version}.zip")
        if not os.path.isfile(dot_build_zip):
            dot_build_mod_dir = os.path.join(yscb_abs, ".build", module_name)
            if os.path.isdir(dot_build_mod_dir):
                b_zips = sorted(
                    [
                        os.path.join(dot_build_mod_dir, f)
                        for f in os.listdir(dot_build_mod_dir)
                        if f.endswith(".build.zip") and os.path.isfile(os.path.join(dot_build_mod_dir, f))
                    ],
                    key=lambda p: os.path.getmtime(p),
                    reverse=True,
                )
                if b_zips:
                    dot_build_zip = b_zips[0]
                    new_b_ver = os.path.basename(dot_build_zip)[:-4]
                    mirror_zip = os.path.join(mirror_dir, f"{new_b_ver}.zip")
                    _update_config_module_version(base_dir, module_name, new_b_ver)
        if os.path.isfile(dot_build_zip) and _extract_and_cache_mirror(dot_build_zip, dest_dir, mirror_dir, mirror_zip):
            return True

    # 2. 本地鏡像庫 (.mirror/<mod>/<ver>.zip) 精確版本命中
    if os.path.isfile(mirror_zip) and _extract_and_cache_mirror(mirror_zip, dest_dir, mirror_dir, mirror_zip):
        return True

    # 3. 檢查組態指定之本地 Provider 路徑（精確版本 <mod>/<ver>.zip 或本地同版 source/<mod> 即時打包）
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

        src_dir = _find_matching_source_dir(module_name, [yscb_abs, p_abs, base_dir])
        rel_zip_target = os.path.join(yscb_abs, "release", module_name, f"{version}.zip")
        if src_dir and _package_source_to_zip_if_exact_version(src_dir, version, mirror_zip, release_zip_path=rel_zip_target):
            if _extract_and_cache_mirror(mirror_zip, dest_dir, mirror_dir, mirror_zip):
                return True

    # 3b. 即便為遠端 Provider，若當前工作區具備嚴格同版本之 source/<mod>，亦優先自給自足打包
    src_dir_local = _find_matching_source_dir(module_name, [yscb_abs, base_dir])
    if src_dir_local and _package_source_to_zip_if_exact_version(src_dir_local, version, mirror_zip):
        if _extract_and_cache_mirror(mirror_zip, dest_dir, mirror_dir, mirror_zip):
            return True

    # 4. 檢查組態指定之遠端 Provider (HTTP/HTTPS) 精確版本 URL
    if p_arg.startswith(("http://", "https://")):
        remote_zip_url = f"{p_arg.rstrip('/')}/{module_name}/{version}.zip"
        if _extract_and_cache_mirror(remote_zip_url, dest_dir, mirror_dir, mirror_zip):
            return True

    # 5. 若精確版本已被滑動視窗淘汰 (pruned)，自動退回同三元組 (X.Y.Z.*) 最高可用 active 版本
    if _allow_fallback:
        fallback_ver = _resolve_same_triplet_fallback_version(p_arg, module_name, version, base_dir=base_dir)
        if fallback_ver and fallback_ver != version:
            print(
                f"[yscb:restore] Exact revision '{module_name}@{version}' has been pruned upstream; "
                f"seamlessly restoring compatible same-triplet revision '{fallback_ver}'."
            )
            ok = _bootstrap_package_from_provider(
                base_dir, yscb_root, module_name, fallback_ver, p_arg, dest_dir, mirror_dir, _allow_fallback=False
            )
            if ok:
                _update_config_module_version(base_dir, module_name, fallback_ver)
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
        mf_file = os.path.join(dest, "manifest.json")
        if not force and os.path.isdir(dest) and os.path.isfile(mf_file):
            installed_ver = _read_module_manifest_version(mf_file)
            if ver == "build" or installed_ver == ver:
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
