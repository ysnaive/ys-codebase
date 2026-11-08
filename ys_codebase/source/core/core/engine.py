"""
YS-Codebase Atomic Package Lifecycle Engine.
100% Python Standard Library, Zero Third-Party Dependency.
Implements:
- 3-Tier Resolution Chain (build:// -> mirror:// -> provider)
- 4-Segment SemVer Dependency Solving
- Dual-Layer Snapshots & Atomic Rollback (modules/, config/, .config.local/, storage/, yscb.config.json)
- Incremental Migration Ladder Subsystem
"""
import os
import sys
import json
import time
import copy
import hashlib
import shutil
import zipfile
import urllib.request
import importlib.util
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Set, Generator, Sequence, Union

from core import uri
from core import vfs
from core.context import ExecutionContext
from core import semver
from core.contributes import ContributesAggregator
from core import events
from core.platform import InterProcessLock

DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases"
LEGACY_PROVIDER_URLS: Tuple[str, ...] = (
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/",
    "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release",
    "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release/",
)
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


def normalize_legacy_provider_url(provider_url: Optional[str]) -> str:
    """Normalizes legacy main-branch official provider URLs to the dedicated releases branch."""
    s = (provider_url or "").strip()
    if s in LEGACY_PROVIDER_URLS:
        return DEFAULT_PROVIDER_URL
    return s


def resolve_local_provider_path(provider_url: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """
    Resolves a local filesystem path or ``file://`` URI provider string to a normalized
    local path. Returns ``None`` if ``provider_url`` is empty or an HTTP/HTTPS URL.
    """
    p_str = normalize_legacy_provider_url(provider_url)
    if not p_str or p_str.startswith(("http://", "https://")):
        return None
    if p_str.startswith("file://"):
        raw_p = urllib.request.url2pathname(p_str[7:])
        while raw_p.startswith("//"):
            raw_p = raw_p[1:]
        return os.path.normpath(raw_p)
    if os.path.isabs(p_str) or (len(p_str) > 1 and p_str[1] == ":"):
        return os.path.normpath(p_str)
    if base_dir:
        return os.path.normpath(os.path.join(base_dir, p_str))
    return os.path.normpath(os.path.abspath(p_str))


def _should_ignore_rel_path(rel_path: str, ignores: List[str]) -> bool:
    import fnmatch
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


def _parse_simple_semver(v_str: str) -> Tuple[int, int, int, int, bool, Tuple[int, str]]:
    """輕量 SemVer 解析器：返回 (major, minor, patch, revision, is_build, prerelease_weight)。"""
    raw = str(v_str).strip()
    is_build = raw == "build" or raw.endswith(".build")
    if raw.endswith(".build"):
        raw = raw[:-6]
    elif raw == "build":
        return (0, 0, 0, 0, True, (1, ""))

    main_part, _, pre_tag = raw.partition("-")
    parts: List[int] = []
    for token in main_part.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)

    while len(parts) < 4:
        parts.append(0)
    pre_weight: Tuple[int, str] = (0, pre_tag) if pre_tag else (1, "")
    return (parts[0], parts[1], parts[2], parts[3], is_build, pre_weight)


def _is_source_version_compatible_with_target(src_ver: str, target_ver: str) -> bool:
    """Checks if local source manifest version matches target_ver (including same-triplet .build requests)."""
    s = str(src_ver).strip()
    t = str(target_ver).strip()
    if not s or not t:
        return False
    if s == t or t == "build":
        return True
    if t.endswith(".build"):
        sv = _parse_simple_semver(s)
        tv = _parse_simple_semver(t)
        return (sv[0], sv[1], sv[2]) == (tv[0], tv[1], tv[2])
    return False


_TEXT_NORMALIZE_EXTS: Tuple[str, ...] = (
    ".py",
    ".json",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
)
_TEXT_NORMALIZE_NAMES: Tuple[str, ...] = (
    ".yscbignore",
    ".gitignore",
)
_DETERMINISTIC_ZIP_DATE: Tuple[int, int, int, int, int, int] = (2020, 1, 1, 0, 0, 0)


def compute_file_sha256(file_path: str) -> str:
    """Computes the lowercase SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _make_deterministic_zip_info(rel_file: str) -> zipfile.ZipInfo:
    """Creates a ZipInfo entry with fixed timestamp and file permissions for deterministic packaging."""
    zi = zipfile.ZipInfo(filename=rel_file, date_time=_DETERMINISTIC_ZIP_DATE)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = (0o644 & 0xFFFF) << 16
    return zi


def _read_normalized_package_file_bytes(src_path: str, rel_file: str) -> bytes:
    """Reads file bytes, normalizing CRLF to LF for UTF-8 text files."""
    base_name = os.path.basename(rel_file)
    _, ext = os.path.splitext(base_name)
    with open(src_path, "rb") as f:
        raw = f.read()
    if ext.lower() in _TEXT_NORMALIZE_EXTS or base_name in _TEXT_NORMALIZE_NAMES:
        try:
            text = raw.decode("utf-8")
            return text.replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            return raw
    return raw


def package_local_source_if_exact_match(
    source_dir: str,
    target_version: str,
    dest_zip_path: str,
    release_zip_path: Optional[str] = None,
) -> bool:
    """
    Packages source_dir into dest_zip_path (and optional release_zip_path) using stdlib zipfile
    when source_dir/manifest.json exists and its 'version' matches target_version (or same-triplet .build).
    """
    if not source_dir or not os.path.isdir(source_dir):
        return False
    mf_path = os.path.join(source_dir, "manifest.json")
    if not os.path.isfile(mf_path):
        return False
    try:
        mf_data = vfs.read_json(mf_path)
    except Exception:
        return False
    if not isinstance(mf_data, dict) or not _is_source_version_compatible_with_target(mf_data.get("version", ""), target_version):
        return False

    ignores = list(_RELEASE_PACKAGE_IGNORES)
    yscbignore_path = os.path.join(source_dir, ".yscbignore")
    if os.path.isfile(yscbignore_path):
        try:
            for line in vfs.read_text(yscbignore_path).splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    ignores.append(s)
        except Exception:
            pass

    entries: List[Tuple[str, str]] = []
    for root, dirs, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        dirs[:] = sorted(d for d in dirs if not _should_ignore_rel_path(f"{rel_dir}/{d}".lstrip("/"), ignores))
        for fname in sorted(files):
            rel_file = f"{rel_dir}/{fname}".lstrip("/")
            if not _should_ignore_rel_path(rel_file, ignores):
                entries.append((rel_file, os.path.join(root, fname)))
    entries.sort(key=lambda item: item[0])

    os.makedirs(os.path.dirname(os.path.abspath(dest_zip_path)), exist_ok=True)
    tmp_zip = dest_zip_path + f".tmp_{os.getpid()}"
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_file, src_f in entries:
                zi = _make_deterministic_zip_info(rel_file)
                if rel_file == "manifest.json":
                    m_copy = dict(mf_data)
                    m_copy["version"] = target_version
                    payload = json.dumps(m_copy, indent=2, ensure_ascii=False).replace("\r\n", "\n").encode("utf-8")
                    zf.writestr(zi, payload, compress_type=zipfile.ZIP_DEFLATED)
                else:
                    payload = _read_normalized_package_file_bytes(src_f, rel_file)
                    zf.writestr(zi, payload, compress_type=zipfile.ZIP_DEFLATED)
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


def find_matching_local_source_dir(module_name: str, candidate_roots: List[str]) -> Optional[str]:
    """Probes candidate_roots for a valid source/<module_name> directory containing manifest.json."""
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
    try:
        src_uri = f"module.source://{module_name}"
        if vfs.is_dir(src_uri) and vfs.is_file(f"{src_uri}/manifest.json"):
            return uri.resolve(src_uri)
    except Exception:
        pass
    return None


def _parse_dependencies(raw_deps: Any) -> Dict[str, str]:
    """Parse dependencies from dict or list format into {module_name: constraint}."""
    if isinstance(raw_deps, dict):
        return {k: str(v) for k, v in raw_deps.items()}
    if isinstance(raw_deps, list):
        result: Dict[str, str] = {}
        for item in raw_deps:
            if isinstance(item, str):
                item = item.strip()
                if "@" in item:
                    m, v = item.split("@", 1)
                    result[m.strip()] = v.strip()
                elif " " in item:
                    m, v = item.split(" ", 1)
                    result[m.strip()] = v.strip()
                else:
                    result[item] = "*"
        return result
    return {}


def _deep_infill_dict(
    base: Dict[str, Any],
    template: Dict[str, Any],
    project_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Recursively infill missing keys from template into base without overwriting existing keys."""
    changed = False
    result = dict(base)
    proj = project_data if isinstance(project_data, dict) else {}

    for k, v in template.items():
        if k not in result:
            if k in proj:
                if isinstance(v, dict) and isinstance(proj[k], dict):
                    sub_res, sub_changed = _deep_infill_dict({}, v, project_data=proj[k])
                    if sub_res:
                        result[k] = sub_res
                        changed = True
                else:
                    continue
            else:
                result[k] = copy.deepcopy(v)
                changed = True
        elif isinstance(result[k], dict) and isinstance(v, dict):
            sub_proj = proj.get(k) if isinstance(proj.get(k), dict) else None
            sub_res, sub_changed = _deep_infill_dict(result[k], v, project_data=sub_proj)
            result[k] = sub_res
            if sub_changed:
                changed = True

    return result, changed


def _force_rmtree_with_retry(
    path: str,
    retries: int = 5,
    retry_delay: float = 0.05,
) -> None:
    """
    Best-effort recursive removal with read-only chmod handler and short backoff retries
    to handle transient OS/virtiofs file handle release delays.
    """
    if not os.path.exists(path):
        return

    def _on_rm_error(func, failed_path, _exc_info):
        try:
            os.chmod(failed_path, 0o700)
            func(failed_path)
        except Exception:
            pass

    for attempt in range(max(1, retries)):
        if not os.path.exists(path):
            return
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
        except Exception:
            pass
        if not os.path.exists(path):
            return
        try:
            os.rmdir(path)
            return
        except Exception:
            if attempt + 1 < retries:
                time.sleep(retry_delay * (attempt + 1))


def _cleanup_stale_swap_dirs(parent_dir: str) -> None:
    """
    Sweeps and cleans up any residual .old_* or .staging_* directories inside parent_dir
    left behind by prior swaps or delayed handle releases.
    """
    if not os.path.isdir(parent_dir):
        return
    try:
        entries = os.listdir(parent_dir)
    except Exception:
        return
    for entry in entries:
        if entry.startswith((".old_", ".staging_")):
            stale_path = os.path.join(parent_dir, entry)
            if os.path.isdir(stale_path):
                _force_rmtree_with_retry(stale_path, retries=3, retry_delay=0.03)


def _is_dir_handle_locked_for_rename(err: OSError, parent_dir: str, target_dir: str) -> bool:
    """
    Three-stage cross-platform discriminator to distinguish transient directory handle locking
    (e.g., Windows/virtiofs/WSL2/9p open directory handles by IDE/watchers) from genuine
    filesystem permission or I/O failures.
    """
    import errno
    err_no = getattr(err, "errno", None)
    win_err = getattr(err, "winerror", None)
    if err_no not in (errno.EACCES, errno.EBUSY, errno.EPERM) and win_err not in (5, 32):
        return False

    if not os.path.isdir(parent_dir) or not os.path.isdir(target_dir):
        return False

    # Stage 1: Verify local OS access mode bits on both parent_dir and target_dir
    req_mode = os.W_OK if os.name == "nt" else (os.W_OK | os.X_OK)
    if not os.access(parent_dir, req_mode) or not os.access(target_dir, req_mode):
        return False

    # Stage 2: Execute a physical file-level write + atomic replace + unlink probe inside target_dir
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
    """
    Stage 3: All-or-nothing file-level atomic sync from staging_dir into target_dir when
    directory-level rename is blocked by host/virtiofs open directory handles.
    """
    import stat

    staging_abs = os.path.abspath(staging_dir)
    target_abs = os.path.abspath(target_dir)
    parent_dir = os.path.dirname(target_abs)
    base_name = os.path.basename(target_abs)
    backup_dir = os.path.join(parent_dir, f".old_backup_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")

    existing_rel_files: Set[str] = set()
    os.makedirs(backup_dir, exist_ok=True)

    try:
        # 1. Snapshot all existing files in target_abs into backup_dir for all-or-nothing rollback
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

        # 2. Atomically replace/create all files from staging_abs into target_abs
        staged_rel_files: Set[str] = set()
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

        # 3. Remove obsolete files that no longer exist in staging_abs
        obsolete_files = existing_rel_files - staged_rel_files
        for norm_rel in obsolete_files:
            obs_f = os.path.join(target_abs, norm_rel.replace("/", os.sep))
            if os.path.isfile(obs_f):
                try:
                    os.chmod(obs_f, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
                os.remove(obs_f)

        # 4. Best-effort cleanup of empty obsolete subdirectories (safe if locked since all files are removed)
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
        # Full rollback from backup_dir if any file write/replace/unlink failed
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
            _force_rmtree_with_retry(backup_dir)


def _atomic_swap_dir(
    staging_dir: str,
    target_dir: str,
    retries: int = 3,
    retry_delay: float = 0.05,
) -> None:
    """
    Atomically swaps a prepared staging_dir into target_dir within the same parent filesystem.
    Moves any existing target_dir to a hidden .old_<name>_<pid> sibling, replaces staging_dir
    into target_dir, rolls back from .old on failure, and removes .old and stale swap dirs upon success.
    When directory-level rename is blocked by host/virtiofs directory handles (verified via 3-stage
    probe), falls back to all-or-nothing file-level atomic sync.
    """
    target_abs = os.path.abspath(target_dir)
    staging_abs = os.path.abspath(staging_dir)
    parent_dir = os.path.dirname(target_abs)
    base_name = os.path.basename(target_abs)
    old_abs = os.path.join(parent_dir, f".old_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")

    def _replace_with_retry(src: str, dst: str) -> None:
        last_err: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            try:
                os.replace(src, dst)
                return
            except OSError as err:
                last_err = err
                if attempt + 1 < retries:
                    time.sleep(retry_delay)
        if last_err is not None:
            raise last_err

    moved_old = False
    try:
        if os.path.exists(old_abs):
            _force_rmtree_with_retry(old_abs)

        if os.path.exists(target_abs):
            try:
                _replace_with_retry(target_abs, old_abs)
                moved_old = True
            except OSError as rename_err:
                if _is_dir_handle_locked_for_rename(rename_err, parent_dir, target_abs):
                    _inplace_atomic_sync_dir(staging_abs, target_abs)
                    return
                raise

        _replace_with_retry(staging_abs, target_abs)
    except Exception:
        if moved_old and not os.path.exists(target_abs) and os.path.exists(old_abs):
            try:
                _replace_with_retry(old_abs, target_abs)
            except Exception:
                pass
        raise
    finally:
        if os.path.exists(old_abs):
            _force_rmtree_with_retry(old_abs)
        if os.path.exists(staging_abs):
            _force_rmtree_with_retry(staging_abs)
        _cleanup_stale_swap_dirs(parent_dir)


def _clean_module_cache(module_name: str) -> None:
    """物理清空指定模組之快取空間 (cache://{module_name}/)。"""
    cache_uri = f"cache://{module_name}"
    if vfs.exists(cache_uri):
        try:
            vfs.rmtree(cache_uri, ignore_errors=True)
        except Exception:
            pass


def _extract_zip_safely(zip_path: str, dest_dir: str, source_label: str = "") -> None:
    """
    Validates zip archive integrity and extracts all entries into dest_dir
    with strict Zip-Slip path traversal protection.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        if zf.testzip() is not None:
            raise RuntimeError(f"Corrupted zip archive from '{source_label or zip_path}'.")
        dest_abs = os.path.abspath(dest_dir)
        for member in zf.infolist():
            target_path = os.path.abspath(os.path.join(dest_abs, member.filename))
            if not target_path.startswith(dest_abs + os.sep) and target_path != dest_abs:
                raise RuntimeError(
                    f"Zip Slip vulnerability detected: '{member.filename}' in '{source_label or zip_path}' "
                    f"attempts to extract outside destination '{dest_abs}'."
                )
        zf.extractall(dest_dir)


def _is_build_version_request(version_or_constraint: Optional[str]) -> bool:
    """Determines whether a version string or constraint explicitly requests a 'build' revision."""
    if not version_or_constraint:
        return False
    if version_or_constraint == "build" or version_or_constraint.endswith(".build") or "build" in version_or_constraint:
        return True
    try:
        v_tuple = semver.parse_semver(version_or_constraint)
        return v_tuple.revision == "build"
    except Exception:
        return False


def _resolve_target_cfg_uris(mod: str, tmpl_file: str) -> Tuple[str, bool, Optional[str]]:
    """Maps a module configuration template filename to (target_cfg_uri, is_local, proj_pair_uri)."""
    if tmpl_file == "contribute.json":
        return f"config://{mod}/contribute.json", False, None
    if tmpl_file == "config.local.json":
        return f"config.local://{mod}/config.local.json", True, f"config://{mod}/config.project.json"
    if tmpl_file == "config.project.json":
        return f"config://{mod}/config.project.json", False, None
    if tmpl_file.startswith("config.") and tmpl_file.endswith(".local.json"):
        sub_name = tmpl_file[len("config."):-len(".local.json")]
        return (
            f"config.local://{mod}/config.{sub_name}.local.json",
            True,
            f"config://{mod}/config.{sub_name}.project.json",
        )
    if tmpl_file.startswith("config.") and tmpl_file.endswith(".project.json"):
        sub_name = tmpl_file[len("config."):-len(".project.json")]
        return f"config://{mod}/config.{sub_name}.project.json", False, None
    return f"config://{mod}/{tmpl_file}", False, None


class AtomicEngine:
    def __init__(self) -> None:
        self.contributes_aggregator = ContributesAggregator()
        self._active_locks: Dict[str, InterProcessLock] = {}
        self._lock_counts: Dict[str, int] = {}

    def _get_config(self) -> Tuple[str, Dict[str, Any]]:
        host_dir, _ = uri._get_host_config()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        if not vfs.is_file(cfg_path):
            raise FileNotFoundError(f"Configuration file not found: {cfg_path}")
        data = vfs.read_json(cfg_path)
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
                    self._save_config(cfg_path, data)
                except Exception:
                    pass
        return cfg_path, data

    def _save_config(self, cfg_path: str, data: Dict[str, Any]) -> None:
        vfs.write_json(cfg_path, data, indent=2, atomic=True)

    def act_fetch(self, provider_url: str, relative_path: str) -> Tuple[bool, Any]:
        """
        Fetches a manifest, index, or package archive from local filesystem or remote HTTP/HTTPS.
        """
        provider_url = normalize_legacy_provider_url(provider_url)
        local_provider = resolve_local_provider_path(provider_url)
        if local_provider is not None and provider_url.startswith("file://"):
            provider_url = local_provider
        local_target = os.path.join(provider_url, relative_path)
        if not os.path.exists(local_target):
            for sub in ("release", "build"):
                cand = os.path.join(provider_url, sub, relative_path)
                if os.path.exists(cand):
                    local_target = cand
                    break

        if os.path.exists(local_target):
            if relative_path.endswith(".json") and vfs.is_file(local_target):
                try:
                    return True, vfs.read_json(local_target)
                except Exception as e:
                    return False, str(e)
            return True, local_target

        if not provider_url.startswith(("http://", "https://")):
            return False, f"File not found in local provider: {local_target}"

        remote_url = f"{provider_url.rstrip('/')}/{relative_path.lstrip('/')}"
        try:
            req = urllib.request.Request(remote_url, headers={"User-Agent": "yscb-client/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
                if relative_path.endswith(".json"):
                    return True, json.loads(content)
                return True, content
        except Exception as e:
            return False, str(e)

    def act_lock(self, operation: str = "global", timeout: float = 10.0) -> None:
        """
        Acquire inter-process lock on cache://.yscb.lock using core.platform.InterProcessLock.
        Supports same-operation reentrancy and stale-lock auto-healing.
        """
        existing = self._active_locks.get(operation)
        if existing is not None and existing.is_locked:
            self._lock_counts[operation] = self._lock_counts.get(operation, 1) + 1
            return

        lock_uri = "cache://.yscb.lock"
        lock_path = uri.resolve(lock_uri)
        vfs.makedirs("cache://", exist_ok=True)

        if os.path.exists(lock_path):
            try:
                mtime = os.path.getmtime(lock_path)
                if (time.time() - mtime) > timeout:
                    for held_op, held_lock in list(self._active_locks.items()):
                        held_lock.release()
                        self._active_locks.pop(held_op, None)
                        self._lock_counts.pop(held_op, None)
                    probe = InterProcessLock(lock_path)
                    if probe.acquire(blocking=False):
                        probe.release()
                        vfs.remove(lock_uri)
                elif self._active_locks:
                    raise BlockingIOError(
                        f"Another yscb operation is currently holding the lock for operation '{operation}'."
                    )
            except BlockingIOError:
                raise
            except OSError:
                pass

        lock = InterProcessLock(lock_path)
        if not lock.acquire(blocking=True, timeout_sec=timeout):
            raise BlockingIOError(f"Another yscb process is currently holding the lock for operation '{operation}'.")
        try:
            os.utime(lock_path, None)
        except OSError:
            pass
        self._active_locks[operation] = lock
        self._lock_counts[operation] = 1

    def act_unlock(self, operation: str = "global") -> None:
        """Release inter-process lock on cache://.yscb.lock."""
        count = self._lock_counts.get(operation, 0)
        if count > 1:
            self._lock_counts[operation] = count - 1
            return

        self._lock_counts.pop(operation, None)
        lock = self._active_locks.pop(operation, None)
        lock_uri = "cache://.yscb.lock"
        if lock is not None:
            lock.release()
            if not self._active_locks and vfs.exists(lock_uri):
                try:
                    vfs.remove(lock_uri)
                except OSError:
                    pass
        else:
            try:
                lock_p = uri.resolve(lock_uri)
                if os.path.exists(lock_p):
                    InterProcessLock(lock_p).release()
                    if not self._active_locks:
                        vfs.remove(lock_uri)
            except Exception:
                pass

    @contextmanager
    def transaction_lock(self, operation: str, timeout: float = 10.0) -> Generator[None, None, None]:
        """Context manager wrapping act_lock and act_unlock with deterministic finally release."""
        self.act_lock(operation, timeout=timeout)
        try:
            yield
        finally:
            self.act_unlock(operation)

    def _download_from_build_tier(self, module_name: str, version: str, provider_url: str, dest_zip_real: str, dest_zip_uri: str) -> str:
        """Tier 1 download: resolves package from module.build:// or local provider build/ subfolder."""
        build_root = f"module.build://{module_name}"
        build_zip_candidates = [
            f"{build_root}/{version}.zip",
            f"{build_root}/{version}.build.zip",
        ]
        try:
            v_tuple = semver.parse_semver(version)
            build_ver_str = f"{v_tuple.major}.{v_tuple.minor}.{v_tuple.patch}.build"
            build_zip_candidates.extend([
                f"{build_root}/{build_ver_str}.zip",
                f"{build_root}/{build_ver_str}.build.zip",
            ])
        except Exception:
            pass

        if vfs.exists(build_root):
            try:
                for f in vfs.listdir(build_root):
                    if f.endswith((".build.zip", ".zip")):
                        build_zip_candidates.append(f"{build_root}/{f}")
            except Exception:
                pass

        for b_zip in build_zip_candidates:
            if vfs.exists(b_zip):
                shutil.copy2(uri.resolve(b_zip), dest_zip_real)
                return dest_zip_uri

        p_abs = resolve_local_provider_path(provider_url)
        if p_abs and os.path.isdir(p_abs):
            for b_path in (
                os.path.join(p_abs, "build", module_name, f"{version}.zip"),
                os.path.join(p_abs, "build", module_name, f"{version}.build.zip"),
            ):
                if os.path.isfile(b_path):
                    shutil.copy2(b_path, dest_zip_real)
                    return dest_zip_uri

        src_dir = find_matching_local_source_dir(module_name, [p_abs] if p_abs else [])
        if src_dir and package_local_source_if_exact_match(src_dir, version, dest_zip_real):
            return dest_zip_uri

        raise FileNotFoundError(
            f"Build package not found for '{module_name}'. Please run 'python yscb.py dev build {module_name}' first."
        )

    def _lookup_expected_sha256(self, module_name: str, version: str, provider_url: str) -> Optional[str]:
        """Looks up releases[version]['sha256'] from local provider, release/mirror index.json, or remote provider."""
        provider_url = normalize_legacy_provider_url(provider_url)
        candidate_dicts: List[Dict[str, Any]] = []

        p_abs = resolve_local_provider_path(provider_url)
        if p_abs:
            for idx_cand in (
                os.path.join(p_abs, module_name, "index.json"),
                os.path.join(p_abs, "release", module_name, "index.json"),
                os.path.join(p_abs, "index.json") if os.path.basename(p_abs) == module_name else "",
            ):
                if idx_cand and vfs.is_file(idx_cand):
                    try:
                        loaded = vfs.read_json(idx_cand)
                        if isinstance(loaded, dict):
                            candidate_dicts.append(loaded)
                    except Exception:
                        pass

        for idx_uri in (f"module.release://{module_name}/index.json", f"module.mirror://{module_name}/index.json"):
            if vfs.is_file(idx_uri):
                try:
                    loaded = vfs.read_json(idx_uri)
                    if isinstance(loaded, dict):
                        candidate_dicts.append(loaded)
                except Exception:
                    pass

        if provider_url:
            ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
            if ok and isinstance(res, dict):
                candidate_dicts.append(res)

        for idx_d in candidate_dicts:
            rels = idx_d.get("releases")
            if isinstance(rels, dict):
                rel_entry = rels.get(version)
                if isinstance(rel_entry, dict):
                    sha_val = rel_entry.get("sha256")
                    if isinstance(sha_val, str) and sha_val.strip():
                        return sha_val.strip()
        return None

    def _verify_zip_sha256(
        self,
        module_name: str,
        version: str,
        zip_real_path: str,
        provider_url: str,
        ignore_sha256: bool = False,
    ) -> None:
        """Verifies SHA-256 checksum of zip_real_path against index.json['releases'][version]['sha256']."""
        if _is_build_version_request(version):
            return
        if ignore_sha256:
            from core.log import log_warn
            log_warn(f"[core:security] [WARN] Skipping SHA-256 verification for '{module_name}@{version}' (--ignore-sha256).")
            return

        expected_sha256 = self._lookup_expected_sha256(module_name, version, provider_url)
        if not expected_sha256 or not isinstance(expected_sha256, str) or not expected_sha256.strip():
            if os.path.exists(zip_real_path):
                try:
                    os.remove(zip_real_path)
                except Exception:
                    pass
            raise RuntimeError(
                f"Missing SHA-256 checksum for '{module_name}@{version}' in index.json. "
                "Refusing unverified package (use --ignore-sha256 to bypass)."
            )

        actual_sha256 = compute_file_sha256(zip_real_path)
        if actual_sha256.lower() != expected_sha256.strip().lower():
            if os.path.exists(zip_real_path):
                try:
                    os.remove(zip_real_path)
                except Exception:
                    pass
            raise RuntimeError(
                f"SHA-256 checksum mismatch for '{module_name}@{version}': "
                f"expected {expected_sha256}, got {actual_sha256}."
            )

    def _download_from_release_tier(
        self,
        module_name: str,
        version: str,
        provider_url: str,
        dest_zip_real: str,
        dest_zip_uri: str,
        ignore_sha256: bool = False,
    ) -> Optional[str]:
        """Tier 2 download: resolves package from module.release://, local provider directory, or exact-version local source/."""
        rel_zip = f"module.release://{module_name}/{version}.zip"
        if vfs.exists(rel_zip):
            shutil.copy2(uri.resolve(rel_zip), dest_zip_real)
            self._verify_zip_sha256(module_name, version, dest_zip_real, provider_url, ignore_sha256=ignore_sha256)
            return dest_zip_uri

        provider_url = normalize_legacy_provider_url(provider_url)
        p_abs = resolve_local_provider_path(provider_url)
        if p_abs and os.path.isdir(p_abs):
            for z_path in (
                os.path.join(p_abs, module_name, f"{version}.zip"),
                os.path.join(p_abs, "release", module_name, f"{version}.zip"),
            ):
                if os.path.isfile(z_path):
                    shutil.copy2(z_path, dest_zip_real)
                    self._verify_zip_sha256(module_name, version, dest_zip_real, provider_url, ignore_sha256=ignore_sha256)
                    return dest_zip_uri

            for d_path in (
                os.path.join(p_abs, module_name, version),
                os.path.join(p_abs, "release", module_name, version),
            ):
                if os.path.isdir(d_path) and os.path.isfile(os.path.join(d_path, "manifest.json")):
                    os.makedirs(os.path.dirname(os.path.abspath(dest_zip_real)), exist_ok=True)
                    tmp_zip = f"{dest_zip_real}.tmp_{os.getpid()}"
                    try:
                        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                            for root, _, files in os.walk(d_path):
                                for f in files:
                                    f_p = os.path.join(root, f)
                                    arc = os.path.relpath(f_p, d_path).replace("\\", "/")
                                    zf.write(f_p, arcname=arc)
                        os.replace(tmp_zip, dest_zip_real)
                    finally:
                        if os.path.exists(tmp_zip):
                            try:
                                os.remove(tmp_zip)
                            except OSError:
                                pass
                    return dest_zip_uri

        # Local exact-version source/<mod> dynamic packaging fallback
        src_dir = find_matching_local_source_dir(module_name, [p_abs] if p_abs else [])
        if src_dir:
            rel_zip_real = None
            try:
                rel_zip_real = uri.resolve(rel_zip)
            except Exception:
                rel_zip_real = None
            if package_local_source_if_exact_match(src_dir, version, dest_zip_real, release_zip_path=rel_zip_real):
                return dest_zip_uri

        return None

    def _get_installed_core_version_for_compat(self, candidate_core_version: Optional[str] = None) -> Optional[str]:
        """Returns the normalized installed core version (resolving .build to source/module manifest version when available)."""
        raw_ver: Optional[str] = candidate_core_version
        if not raw_ver:
            try:
                _, cfg = self._get_config()
                inst = cfg.get("installed_modules", {})
                if isinstance(inst, dict) and "core" in inst:
                    c_meta = inst["core"]
                    raw_ver = c_meta.get("version") if isinstance(c_meta, dict) else str(c_meta)
            except Exception:
                pass
        if not raw_ver and vfs.is_file("module://core/manifest.json"):
            try:
                mf = vfs.read_json("module://core/manifest.json")
                if isinstance(mf, dict):
                    raw_ver = mf.get("version")
            except Exception:
                pass
        if not raw_ver:
            return None
        s = str(raw_ver).strip()
        if s.endswith(".build") or s == "build":
            for mf_uri in ("module.source://core/manifest.json", "module://core/manifest.json"):
                try:
                    if vfs.is_file(mf_uri):
                        mf = vfs.read_json(mf_uri)
                        mv = str(mf.get("version", "")).strip() if isinstance(mf, dict) else ""
                        if mv and not mv.endswith(".build") and mv != "build":
                            return mv
                except Exception:
                    pass
            return s[:-len(".build")] if s.endswith(".build") else s
        return s

    def _is_dependencies_compatible_with_env(self, deps: Any, candidate_core_version: Optional[str] = None) -> bool:
        """Checks whether a candidate version's dependencies are compatible with the currently installed core version."""
        parsed = _parse_dependencies(deps)
        core_req = parsed.get("core")
        if not core_req:
            return True
        installed_core = self._get_installed_core_version_for_compat(candidate_core_version=candidate_core_version)
        if not installed_core:
            return True
        return semver.match_constraint(installed_core, core_req)

    def _read_installed_module_dependencies(self, mod: str, ver: str, provider_url: str = "") -> Dict[str, str]:
        """
        Reads the effective `dependencies` dict of a module version from local mirror/module manifest
        with `index.json["releases"][<ver>]["dependencies"]` override priority (zero network when local exists).
        """
        override_deps: Optional[Dict[str, Any]] = None
        for idx_uri in (f"module.release://{mod}/index.json", f"module.mirror://{mod}/index.json"):
            if vfs.is_file(idx_uri):
                try:
                    loaded = vfs.read_json(idx_uri)
                    rel_entry = loaded.get("releases", {}).get(ver) if isinstance(loaded, dict) and isinstance(loaded.get("releases"), dict) else None
                    if isinstance(rel_entry, dict) and isinstance(rel_entry.get("dependencies"), dict):
                        override_deps = rel_entry["dependencies"]
                        break
                except Exception:
                    pass
        if override_deps is not None:
            return _parse_dependencies(override_deps)

        if vfs.is_file(f"module://{mod}/manifest.json"):
            try:
                mf = vfs.read_json(f"module://{mod}/manifest.json")
                if isinstance(mf, dict) and (str(mf.get("version", "")).strip() == str(ver).strip() or _is_build_version_request(ver)):
                    return _parse_dependencies(mf.get("dependencies", {}))
            except Exception:
                pass

        mirror_zip = f"module.mirror://{mod}/{ver}.zip"
        if vfs.is_file(mirror_zip):
            try:
                real_zip = uri.resolve(mirror_zip)
                with zipfile.ZipFile(real_zip, "r") as zf:
                    mf = json.loads(zf.read("manifest.json").decode("utf-8"))
                    if isinstance(mf, dict):
                        return _parse_dependencies(mf.get("dependencies", {}))
            except Exception:
                pass

        mirror_mf = f"module.mirror://{mod}/{ver}/manifest.json"
        if vfs.is_file(mirror_mf):
            try:
                mf = vfs.read_json(mirror_mf)
                if isinstance(mf, dict):
                    return _parse_dependencies(mf.get("dependencies", {}))
            except Exception:
                pass

        if provider_url:
            try:
                mf = self._get_module_manifest_from_provider_or_local(mod, provider_url, f"=={ver}")
                if isinstance(mf, dict):
                    return _parse_dependencies(mf.get("dependencies", {}))
            except Exception:
                pass
        return {}

    def _cache_release_index_to_mirror(self, module_name: str, index_data: Dict[str, Any]) -> None:
        """Persists a copy of the module's release index.json into module.mirror://<module_name>/index.json for offline reload/rollback."""
        if not isinstance(index_data, dict):
            return
        try:
            mirror_dir = f"module.mirror://{module_name}"
            vfs.makedirs(mirror_dir, exist_ok=True)
            vfs.write_json(f"{mirror_dir}/index.json", index_data, indent=2, atomic=True)
        except Exception:
            pass

    def _apply_release_index_override_to_staging(self, mod: str, ver: str, staging_dir: str) -> None:
        """Applies post-release dependency and metadata overrides from index.json into staging_dir/manifest.json."""
        mf_path = os.path.join(staging_dir, "manifest.json")
        if not os.path.isfile(mf_path):
            return
        idx_data: Optional[Dict[str, Any]] = None
        for idx_uri in (f"module.release://{mod}/index.json", f"module.mirror://{mod}/index.json"):
            if vfs.is_file(idx_uri):
                try:
                    loaded = vfs.read_json(idx_uri)
                    if isinstance(loaded, dict) and isinstance(loaded.get("releases"), dict):
                        idx_data = loaded
                        break
                except Exception:
                    pass
        if not idx_data:
            return
        rel_entry = idx_data.get("releases", {}).get(ver)
        if not isinstance(rel_entry, dict):
            return
        try:
            mf_data = vfs.read_json(mf_path)
            if not isinstance(mf_data, dict):
                return
            changed = False
            if isinstance(rel_entry.get("dependencies"), dict):
                if mf_data.get("dependencies") != rel_entry["dependencies"]:
                    mf_data["dependencies"] = dict(rel_entry["dependencies"])
                    changed = True
            rel_meta = {k: rel_entry[k] for k in ("type", "urgency", "summary") if isinstance(rel_entry.get(k), str) and rel_entry[k]}
            if rel_meta:
                cur_rel = mf_data.get("release") if isinstance(mf_data.get("release"), dict) else {}
                merged_rel = dict(cur_rel)
                merged_rel.update(rel_meta)
                if mf_data.get("release") != merged_rel:
                    mf_data["release"] = merged_rel
                    changed = True
            if changed:
                vfs.write_json(mf_path, mf_data, indent=2, atomic=True)
        except Exception:
            pass

    def _download_from_remote_tier(
        self,
        module_name: str,
        version: str,
        provider_url: str,
        dest_zip_real: str,
        dest_zip_uri: str,
        ignore_sha256: bool = False,
    ) -> str:
        """Tier 3 download: fetches single-file <version>.zip from remote HTTP/HTTPS provider."""
        provider_url = normalize_legacy_provider_url(provider_url)
        if not provider_url.startswith(("http://", "https://", "file://")):
            raise FileNotFoundError(
                f"Cannot find release package for module '{module_name}@{version}' in provider '{provider_url}'."
            )

        remote_zip_url = provider_url.rstrip("/") + f"/{module_name}/{version}.zip"
        try:
            req = urllib.request.Request(remote_zip_url, headers={"User-Agent": "yscb-core/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with vfs.atomic_write(dest_zip_real, mode="wb") as f:
                    shutil.copyfileobj(resp, f)

            if not zipfile.is_zipfile(dest_zip_real):
                raise RuntimeError(f"Downloaded file from '{remote_zip_url}' is not a valid zip archive.")

            with zipfile.ZipFile(dest_zip_real, "r") as zf:
                if zf.testzip() is not None:
                    raise RuntimeError(f"Corrupted zip archive downloaded from '{remote_zip_url}'.")

            self._verify_zip_sha256(module_name, version, dest_zip_real, provider_url, ignore_sha256=ignore_sha256)
            return dest_zip_uri
        except Exception as e:
            if vfs.exists(dest_zip_real):
                try:
                    vfs.remove(dest_zip_real)
                except Exception:
                    pass
            raise RuntimeError(f"Failed to download module '{module_name}@{version}' from '{remote_zip_url}': {e}")

    def _resolve_same_triplet_fallback_version(
        self,
        module_name: str,
        requested_version: str,
        provider_url: str,
        base_dir: Optional[str] = None,
    ) -> Optional[str]:
        """Resolves the highest available active version in the same triplet (X.Y.Z.*) when requested_version has been pruned."""
        try:
            req_t = semver.parse_semver(requested_version)
        except Exception:
            return None
        if req_t.is_build or str(requested_version).endswith(".build"):
            return None
        req_triplet = (req_t.major, req_t.minor, req_t.patch)
        p_arg = normalize_legacy_provider_url(provider_url)
        idx_data: Optional[Dict[str, Any]] = None

        p_abs = resolve_local_provider_path(p_arg, base_dir=base_dir)

        if p_abs and os.path.isdir(p_abs):
            for idx_cand in (
                os.path.join(p_abs, module_name, "index.json"),
                os.path.join(p_abs, "release", module_name, "index.json"),
                os.path.join(p_abs, "index.json") if os.path.basename(p_abs) == module_name else "",
            ):
                if idx_cand and vfs.is_file(idx_cand):
                    try:
                        idx_data = vfs.read_json(idx_cand)
                        if isinstance(idx_data, dict):
                            break
                    except Exception:
                        pass
        else:
            ok, res = self.act_fetch(p_arg, f"{module_name}/index.json")
            if ok and isinstance(res, dict):
                idx_data = res

        if not isinstance(idx_data, dict):
            return None
        active_vers = idx_data.get("versions")
        if not isinstance(active_vers, list) or requested_version in active_vers:
            return None

        cands: List[str] = []
        for v in active_vers:
            if not isinstance(v, str):
                continue
            try:
                vt = semver.parse_semver(v)
                if not vt.is_build and not v.endswith(".build") and (vt.major, vt.minor, vt.patch) == req_triplet:
                    cands.append(v)
            except Exception:
                pass
        if not cands:
            return None
        return semver.find_best_version(cands)

    def act_download(self, module_name: str, version: str, provider_url: str, ignore_sha256: bool = False) -> str:
        """
        Downloads/Materializes a specific module version into module.mirror://{module_name}/{version}.zip.
        Enforces 3-Tier Resolution Chain (module.build:// -> module.release:// -> provider_url).
        """
        dest_mirror_dir = f"module.mirror://{module_name}"
        vfs.makedirs(dest_mirror_dir)
        dest_zip_uri = f"{dest_mirror_dir}/{version}.zip"
        dest_zip_real = uri.resolve(dest_zip_uri)

        if _is_build_version_request(version):
            return self._download_from_build_tier(module_name, version, provider_url, dest_zip_real, dest_zip_uri)

        try:
            rel_idx_uri = f"module.release://{module_name}/index.json"
            if vfs.is_file(rel_idx_uri):
                idx_d = vfs.read_json(rel_idx_uri)
                if isinstance(idx_d, dict):
                    self._cache_release_index_to_mirror(module_name, idx_d)
            else:
                ok_idx, res_idx = self.act_fetch(provider_url, f"{module_name}/index.json")
                if ok_idx and isinstance(res_idx, dict):
                    self._cache_release_index_to_mirror(module_name, res_idx)
        except Exception:
            pass

        rel_hit = self._download_from_release_tier(
            module_name, version, provider_url, dest_zip_real, dest_zip_uri, ignore_sha256=ignore_sha256
        )
        if rel_hit is not None:
            return rel_hit

        return self._download_from_remote_tier(
            module_name, version, provider_url, dest_zip_real, dest_zip_uri, ignore_sha256=ignore_sha256
        )

    def act_register(self, module_name: str, version: str, provider_url: str) -> None:
        cfg_path, cfg = self._get_config()
        if "installed_modules" not in cfg:
            cfg["installed_modules"] = {}
        cfg["installed_modules"][module_name] = {
            "version": version,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider_url,
        }
        self._save_config(cfg_path, cfg)

    def act_unregister(self, module_name: str) -> None:
        cfg_path, cfg = self._get_config()
        if "installed_modules" in cfg and module_name in cfg["installed_modules"]:
            del cfg["installed_modules"][module_name]
            self._save_config(cfg_path, cfg)

    def _find_manifest_in_build_tier(self, module_name: str, version_constraint: Optional[str]) -> Optional[Dict[str, Any]]:
        """Reads manifest.json from module.build://<module_name> when build revision is requested."""
        build_root_uri = f"module.build://{module_name}"
        if vfs.exists(build_root_uri):
            try:
                for f in vfs.listdir(build_root_uri):
                    if f.endswith((".build.zip", ".zip")):
                        b_zip_uri = f"{build_root_uri}/{f}"
                        with zipfile.ZipFile(uri.resolve(b_zip_uri), "r") as zf:
                            m_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                            ver_in_m = m_data.get("version", "1.0.0.0")
                            if not ver_in_m.endswith(".build"):
                                v_p = semver.parse_semver(ver_in_m)
                                m_data["version"] = f"{v_p.major}.{v_p.minor}.{v_p.patch}.build"
                            return m_data
            except Exception:
                pass

        if vfs.exists(f"{build_root_uri}/index.json"):
            try:
                b_idx = vfs.read_json(f"{build_root_uri}/index.json")
                b_versions = b_idx.get("versions", [])
                best_bld = semver.find_best_version(b_versions, version_constraint)
                if best_bld:
                    b_zip_uri = f"{build_root_uri}/{best_bld}.zip"
                    if vfs.exists(b_zip_uri):
                        with zipfile.ZipFile(uri.resolve(b_zip_uri), "r") as zf:
                            return json.loads(zf.read("manifest.json").decode("utf-8"))
                    if vfs.exists(f"{build_root_uri}/{best_bld}/manifest.json"):
                        return vfs.read_json(f"{build_root_uri}/{best_bld}/manifest.json")
            except Exception:
                pass

        src_dir = find_matching_local_source_dir(module_name, [])
        if src_dir:
            try:
                m_data = vfs.read_json(os.path.join(src_dir, "manifest.json"))
                if isinstance(m_data, dict):
                    m_copy = dict(m_data)
                    v_p = semver.parse_semver(str(m_copy.get("version", "1.0.0.0")))
                    m_copy["version"] = f"{v_p.major}.{v_p.minor}.{v_p.patch}.build"
                    return m_copy
            except Exception:
                pass
        return None

    def _find_manifest_in_local_provider(
        self,
        module_name: str,
        p_abs: str,
        version_constraint: Optional[str],
        is_build_req: bool,
    ) -> Optional[Dict[str, Any]]:
        """Reads manifest.json from local provider index.json or release directories."""
        candidate_indexes = [
            os.path.join(p_abs, module_name, "index.json"),
            os.path.join(p_abs, "release", module_name, "index.json"),
        ]
        if is_build_req:
            candidate_indexes.append(os.path.join(p_abs, "build", module_name, "index.json"))

        for idx_p in candidate_indexes:
            if vfs.is_file(idx_p):
                try:
                    idx_data = vfs.read_json(idx_p)
                    if isinstance(idx_data, dict):
                        self._cache_release_index_to_mirror(module_name, idx_data)
                    vers = idx_data.get("versions", []) if isinstance(idx_data, dict) else []
                    releases_map = idx_data.get("releases") if isinstance(idx_data, dict) else None
                    compat_vers: List[str] = []
                    for v in vers:
                        if not isinstance(v, str):
                            continue
                        rel_v = releases_map.get(v) if isinstance(releases_map, dict) else None
                        if isinstance(rel_v, dict) and isinstance(rel_v.get("dependencies"), dict):
                            if not self._is_dependencies_compatible_with_env(rel_v["dependencies"]):
                                continue
                        compat_vers.append(v)
                    best_v = semver.find_best_version(compat_vers, version_constraint)
                    if not best_v:
                        best_v = semver.find_best_version(vers, version_constraint)
                    if best_v:
                        rel_entry = releases_map.get(best_v) if isinstance(releases_map, dict) else None
                        override_deps = rel_entry.get("dependencies") if isinstance(rel_entry, dict) else None
                        base_mf: Optional[Dict[str, Any]] = None
                        zip_p = os.path.join(os.path.dirname(idx_p), f"{best_v}.zip")
                        if vfs.is_file(zip_p):
                            with zipfile.ZipFile(zip_p, "r") as zf:
                                base_mf = json.loads(zf.read("manifest.json").decode("utf-8"))
                        if base_mf is None:
                            src_dir = find_matching_local_source_dir(module_name, [p_abs, os.path.dirname(os.path.dirname(idx_p))])
                            if src_dir:
                                src_mf = vfs.read_json(os.path.join(src_dir, "manifest.json"))
                                if isinstance(src_mf, dict) and str(src_mf.get("version", "")).strip() == str(best_v).strip():
                                    base_mf = dict(src_mf)
                        if base_mf is None and isinstance(rel_entry, dict):
                            base_mf = {
                                "name": module_name,
                                "version": best_v,
                                "dependencies": rel_entry.get("dependencies", {}),
                            }
                        if isinstance(base_mf, dict):
                            if isinstance(override_deps, dict):
                                base_mf["dependencies"] = dict(override_deps)
                            return base_mf
                except Exception:
                    pass

        candidate_dirs = [
            os.path.join(p_abs, "release", module_name),
            os.path.join(p_abs, module_name),
        ]
        if is_build_req:
            candidate_dirs.append(os.path.join(p_abs, "build", module_name))

        for c_dir in candidate_dirs:
            if vfs.is_dir(c_dir):
                versions = [v for v in vfs.listdir(c_dir) if vfs.is_dir(os.path.join(c_dir, v))]
                best_ver = semver.find_best_version(versions, version_constraint)
                if best_ver and vfs.is_file(os.path.join(c_dir, best_ver, "manifest.json")):
                    try:
                        return vfs.read_json(os.path.join(c_dir, best_ver, "manifest.json"))
                    except Exception:
                        pass
                direct_mf = os.path.join(c_dir, "manifest.json")
                if vfs.is_file(direct_mf):
                    try:
                        m_data = vfs.read_json(direct_mf)
                        if isinstance(m_data, dict) and semver.match_constraint(m_data.get("version", "1.0.0.0"), version_constraint):
                            return m_data
                    except Exception:
                        pass
        return None

    def _get_module_manifest_from_provider_or_local(
        self,
        module_name: str,
        provider_url: str,
        version_constraint: Optional[str] = None,
    ) -> Dict[str, Any]:
        is_build_req = _is_build_version_request(version_constraint)

        if is_build_req:
            bld_mf = self._find_manifest_in_build_tier(module_name, version_constraint)
            if bld_mf is not None:
                return bld_mf

        p_abs = resolve_local_provider_path(provider_url)
        if p_abs and os.path.isdir(p_abs):
            loc_mf = self._find_manifest_in_local_provider(module_name, p_abs, version_constraint, is_build_req)
            if loc_mf is not None:
                return loc_mf

        ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if ok and isinstance(res, dict):
            self._cache_release_index_to_mirror(module_name, res)
            if "versions" in res and isinstance(res["versions"], list):
                releases_map = res.get("releases") if isinstance(res.get("releases"), dict) else {}
                compat_vers: List[str] = []
                for v in res["versions"]:
                    if not isinstance(v, str):
                        continue
                    rel_v = releases_map.get(v) if isinstance(releases_map, dict) else None
                    if isinstance(rel_v, dict) and isinstance(rel_v.get("dependencies"), dict):
                        if not self._is_dependencies_compatible_with_env(rel_v["dependencies"]):
                            continue
                    compat_vers.append(v)
                best_ver = semver.find_best_version(compat_vers, version_constraint)
                if not best_ver:
                    best_ver = semver.find_best_version(res["versions"], version_constraint)
                if best_ver:
                    rel_entry = releases_map.get(best_ver) if isinstance(releases_map, dict) else None
                    deps = rel_entry.get("dependencies", {}) if isinstance(rel_entry, dict) else {}
                    return {
                        "name": module_name,
                        "version": best_ver,
                        "dependencies": dict(deps) if isinstance(deps, dict) else {},
                    }
            elif "manifest" in res:
                return res["manifest"]

        raise ModuleNotFoundError(
            f"Cannot find module '{module_name}' (version constraint: '{version_constraint}') in provider '{provider_url}'."
        )

    def act_solve_deps(
        self,
        target_module: Union[str, Sequence[Union[str, Tuple[str, Optional[str]]]]],
        version_constraint: Optional[str] = None,
        provider_url: str = "",
    ) -> List[Tuple[str, str]]:
        """
        Recursively resolves dependency topology with 4-segment SemVer constraint satisfaction.
        Supports both single module (str) and batch module specifications (Sequence[str | Tuple[str, Optional[str]]]),
        enforcing cross-root and cross-dependency version constraint compatibility.
        """
        root_requests: List[Tuple[str, Optional[str]]] = []
        if isinstance(target_module, str):
            root_requests.append((target_module, version_constraint))
        else:
            for item in target_module:
                if isinstance(item, tuple):
                    mod_n, mod_v = item[0], item[1] if len(item) > 1 else version_constraint
                    root_requests.append((str(mod_n), mod_v))
                else:
                    spec_str = str(item)
                    if "@" in spec_str:
                        mod_n, mod_v = spec_str.split("@", 1)
                        root_requests.append((mod_n, mod_v))
                    else:
                        root_requests.append((spec_str, version_constraint))

        explicit_constraints: Dict[str, Optional[str]] = {}
        for mod_n, mod_v in root_requests:
            if mod_n in explicit_constraints:
                prev_v = explicit_constraints[mod_n]
                if prev_v and mod_v and prev_v != mod_v:
                    prev_is_op = prev_v.startswith((">=", "<=", "!=", "==", "~=", "^=", "^", ">", "<", "="))
                    mod_is_op = mod_v.startswith((">=", "<=", "!=", "==", "~=", "^=", "^", ">", "<", "="))
                    if not prev_is_op and not mod_is_op:
                        compatible = semver.match_constraint(prev_v, mod_v) or semver.match_constraint(mod_v, prev_v)
                    elif not prev_is_op:
                        compatible = semver.match_constraint(prev_v, mod_v)
                    elif not mod_is_op:
                        compatible = semver.match_constraint(mod_v, prev_v)
                    else:
                        compatible = True
                    if not compatible:
                        raise RuntimeError(
                            f"Conflicting version constraints for module '{mod_n}' in batch request: "
                            f"'{prev_v}' vs '{mod_v}'."
                        )
                    explicit_constraints[mod_n] = f"{prev_v},{mod_v}" if (prev_is_op and mod_is_op) else (prev_v if not prev_is_op else mod_v)
                elif mod_v and not prev_v:
                    explicit_constraints[mod_n] = mod_v
            else:
                explicit_constraints[mod_n] = mod_v

        ordered_list: List[Tuple[str, str]] = []
        resolved_versions: Dict[str, str] = {}
        constraint_sources: Dict[str, List[Tuple[str, str]]] = {}
        for mod_n, mod_v in root_requests:
            if mod_v:
                constraint_sources.setdefault(mod_n, []).append(("explicit request", mod_v))
        visited: Set[str] = set()
        visiting: Set[str] = set()
        _, cur_cfg = self._get_config()
        installed_map = cur_cfg.get("installed_modules", {}) if isinstance(cur_cfg, dict) else {}

        def _combine_constraints(c1: Optional[str], c2: Optional[str]) -> Optional[str]:
            if not c1:
                return c2
            if not c2 or c1 == c2:
                return c1
            if _is_build_version_request(c1):
                return c1
            if _is_build_version_request(c2):
                return c2
            return f"{c1},{c2}"

        def _format_conflict_sources(mod_name: str) -> str:
            srcs = constraint_sources.get(mod_name, [])
            if not srcs:
                return ""
            return " | ".join(f"'{c}' (by {req})" for req, c in srcs)

        def _check_resolved_compatibility(mod_name: str, resolved_ver: str, req_constraint: Optional[str]) -> None:
            if not req_constraint:
                return
            if _is_build_version_request(resolved_ver):
                return
            if not semver.match_constraint(resolved_ver, req_constraint):
                detail = _format_conflict_sources(mod_name)
                suffix = f" [constraints: {detail}]" if detail else ""
                raise RuntimeError(
                    f"Cannot resolve dependency for '{mod_name}': "
                    f"resolved version '{resolved_ver}' does not satisfy constraint '{req_constraint}'.{suffix}"
                )

        def _solve(mod_name: str, ver_req: Optional[str], requester: str = "root") -> None:
            if ver_req:
                constraint_sources.setdefault(mod_name, []).append((requester, ver_req))
            if mod_name in visiting:
                raise ValueError(f"Circular dependency detected: '{mod_name}' in call chain.")
            if mod_name in visited:
                _check_resolved_compatibility(mod_name, resolved_versions[mod_name], ver_req)
                return

            visiting.add(mod_name)
            joint_req: Optional[str] = explicit_constraints.get(mod_name)
            for _, c_str in constraint_sources.get(mod_name, []):
                joint_req = _combine_constraints(joint_req, c_str)
            effective_req = _combine_constraints(joint_req, ver_req)
            manifest: Optional[Dict[str, Any]] = None
            if mod_name not in explicit_constraints and not _is_build_version_request(effective_req):
                inst_meta = installed_map.get(mod_name) if isinstance(installed_map, dict) else None
                inst_ver = str(inst_meta.get("version", "")) if isinstance(inst_meta, dict) else ""
                if _is_build_version_request(inst_ver):
                    manifest = self._find_manifest_in_build_tier(mod_name, "build")
            if manifest is None:
                try:
                    manifest = self._get_module_manifest_from_provider_or_local(mod_name, provider_url, effective_req)
                except ModuleNotFoundError as exc:
                    if len(constraint_sources.get(mod_name, [])) > 1:
                        detail = _format_conflict_sources(mod_name)
                        raise RuntimeError(
                            f"Dependency conflict for '{mod_name}': no overlapping version satisfies [{detail}]."
                        ) from exc
                    raise
            resolved_ver = manifest.get("version", "1.0.0.0")

            _check_resolved_compatibility(mod_name, resolved_ver, effective_req)
            if mod_name in explicit_constraints:
                _check_resolved_compatibility(mod_name, resolved_ver, explicit_constraints[mod_name])

            parsed_deps = _parse_dependencies(manifest.get("dependencies", {}))
            for dep_name, dep_ver in parsed_deps.items():
                if dep_name == "core":
                    candidate_core = resolved_versions.get("core") or explicit_constraints.get("core")
                    if candidate_core and candidate_core.startswith("=="):
                        candidate_core = candidate_core[2:].strip()
                    installed_core = self._get_installed_core_version_for_compat(candidate_core_version=candidate_core)
                    if installed_core and not semver.match_constraint(installed_core, dep_ver):
                        raise RuntimeError(
                            f"Cannot resolve dependency for '{mod_name}': "
                            f"required core version '{dep_ver}' is not satisfied by installed core@{installed_core}."
                        )
                else:
                    _solve(dep_name, dep_ver, requester=f"{mod_name}@{resolved_ver}")

            visiting.remove(mod_name)
            visited.add(mod_name)
            resolved_versions[mod_name] = resolved_ver
            ordered_list.append((mod_name, resolved_ver))

        for root_mod, root_ver in root_requests:
            _solve(root_mod, root_ver, requester="root")
        return ordered_list

    def reconcile_installed_dependencies(
        self,
        provider_url: Optional[str] = None,
        candidate_overrides: Optional[Dict[str, str]] = None,
        strict: bool = True,
        ignore_sha256: bool = False,
    ) -> List[Tuple[str, Optional[str], str]]:
        """
        Standard dependency self-check and intersection self-healing engine:
        - Fast local O(1) pass when all declared dependencies are already installed and satisfy joint constraints.
        - Missing dependency module (not installed): resolves constraint intersection and auto-downloads/registers it.
        - Installed dependency module failing new constraints: resolves intersection across all upstream requesters
          and auto-upgrades if an overlapping version exists; raises RuntimeError on disjoint version conflict.
        Returns a list of `(mod_name, old_version_or_None, new_version)` for any newly installed or upgraded modules.
        """
        _, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        if not isinstance(installed, dict) or not installed:
            return []

        default_prov = normalize_legacy_provider_url(
            provider_url
            or cfg.get("default_provider")
            or (installed.get("core", {}).get("provider") if isinstance(installed.get("core"), dict) else "")
            or ""
        )

        effective_versions: Dict[str, str] = {}
        mod_providers: Dict[str, str] = {}
        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0") if isinstance(meta, dict) else str(meta)
            prov = (meta.get("provider") if isinstance(meta, dict) else None) or default_prov
            effective_versions[mod] = str(ver)
            mod_providers[mod] = normalize_legacy_provider_url(prov) if prov else default_prov

        if candidate_overrides:
            for mod, new_ver in candidate_overrides.items():
                effective_versions[mod] = str(new_ver)
                if mod not in mod_providers:
                    mod_providers[mod] = default_prov

        healed_changes: List[Tuple[str, Optional[str], str]] = []
        max_rounds = 8
        for _ in range(max_rounds):
            req_map: Dict[str, List[Tuple[str, str]]] = {}
            for mod, ver in list(effective_versions.items()):
                prov = mod_providers.get(mod, default_prov)
                deps = self._read_installed_module_dependencies(mod, ver, provider_url=prov)
                for dep_name, dep_constraint in deps.items():
                    req_map.setdefault(dep_name, []).append((f"{mod}@{ver}", dep_constraint))

            if not req_map:
                break

            # Verify core compatibility first
            if "core" in req_map:
                raw_core_ver = effective_versions.get("core", "")
                if not _is_build_version_request(raw_core_ver):
                    cur_core = self._get_installed_core_version_for_compat(
                        candidate_core_version=raw_core_ver or None
                    )
                    if cur_core and not _is_build_version_request(cur_core):
                        for requester_label, core_c in req_map["core"]:
                            if not semver.match_constraint(cur_core, core_c):
                                raise RuntimeError(
                                    f"Cannot resolve dependency on 'core': required '{core_c}' by '{requester_label}', "
                                    f"but core@{cur_core} is active."
                                )

            round_changed = False
            for dep_mod, req_list in req_map.items():
                if dep_mod == "core":
                    continue
                joint_clauses: List[str] = []
                for _, c_str in req_list:
                    if c_str and c_str not in joint_clauses:
                        joint_clauses.append(c_str)
                joint_constraint = ",".join(joint_clauses) if joint_clauses else "*"
                detail_str = " | ".join(f"'{c}' (by {r})" for r, c in req_list)

                cur_dep_ver = effective_versions.get(dep_mod)
                if cur_dep_ver is not None:
                    if _is_build_version_request(cur_dep_ver):
                        continue
                    if semver.match_constraint(cur_dep_ver, joint_constraint):
                        continue

                # Needs self-heal: either dep_mod is missing or its current version violates joint_constraint
                prov_to_use = mod_providers.get(dep_mod)
                if not prov_to_use and req_list:
                    first_req_mod = req_list[0][0].partition("@")[0]
                    prov_to_use = mod_providers.get(first_req_mod, default_prov)
                if not prov_to_use:
                    prov_to_use = default_prov
                if not prov_to_use:
                    raise RuntimeError(
                        f"Cannot self-heal dependency '{dep_mod}' ({detail_str}): no provider configured."
                    )

                resolved_mf: Optional[Dict[str, Any]] = None
                if cur_dep_ver is not None and not _is_build_version_request(cur_dep_ver):
                    try:
                        cur_t = semver.parse_semver(cur_dep_ver)
                        major_lock = f"^{cur_t.major}.0.0"
                        locked_joint = f"{joint_constraint},{major_lock}" if joint_constraint != "*" else major_lock
                        resolved_mf = self._get_module_manifest_from_provider_or_local(dep_mod, prov_to_use, locked_joint)
                    except Exception:
                        resolved_mf = None

                if resolved_mf is None:
                    try:
                        resolved_mf = self._get_module_manifest_from_provider_or_local(dep_mod, prov_to_use, joint_constraint)
                    except Exception as exc:
                        if not strict and len(req_list) == 1 and cur_dep_ver is None:
                            continue
                        raise RuntimeError(
                            f"Dependency conflict for '{dep_mod}': no overlapping version satisfies [{detail_str}]."
                        ) from exc

                target_dep_ver = str(resolved_mf.get("version", "1.0.0.0"))
                if not semver.match_constraint(target_dep_ver, joint_constraint):
                    raise RuntimeError(
                        f"Dependency conflict for '{dep_mod}': candidate '{target_dep_ver}' does not satisfy "
                        f"joint constraints [{detail_str}]."
                    )

                # Verify that target_dep_ver's own core requirement is compatible
                target_deps = _parse_dependencies(resolved_mf.get("dependencies", {}))
                if "core" in target_deps:
                    cur_core = self._get_installed_core_version_for_compat(
                        candidate_core_version=effective_versions.get("core")
                    )
                    if cur_core and not semver.match_constraint(cur_core, target_deps["core"]):
                        raise RuntimeError(
                            f"Cannot resolve dependency '{dep_mod}@{target_dep_ver}': "
                            f"required core version '{target_deps['core']}' is not satisfied by core@{cur_core}."
                        )

                old_v = installed.get(dep_mod, {}).get("version") if isinstance(installed.get(dep_mod), dict) else None
                self.act_prepare([(dep_mod, target_dep_ver)], prov_to_use, force=False, ignore_sha256=ignore_sha256)
                self.act_register(dep_mod, target_dep_ver, prov_to_use)
                effective_versions[dep_mod] = target_dep_ver
                mod_providers[dep_mod] = prov_to_use
                healed_changes.append((dep_mod, old_v, target_dep_ver))
                round_changed = True

            if not round_changed:
                break

        return healed_changes

    def act_prepare(
        self,
        target_list: List[Tuple[str, str]],
        provider_url: str,
        force: bool = False,
        ignore_sha256: bool = False,
    ) -> None:
        for mod, ver in target_list:
            mirror_zip = f"module.mirror://{mod}/{ver}.zip"
            if force or not vfs.exists(mirror_zip):
                self.act_download(mod, ver, provider_url, ignore_sha256=ignore_sha256)

    def _infill_single_template(
        self,
        mod: str,
        tmpl_real_path: str,
        target_cfg_uri: str,
        is_local: bool,
        proj_pair_uri: Optional[str],
    ) -> None:
        """Infills a single JSON configuration template into target_cfg_uri."""
        try:
            tmpl_data = vfs.read_json(tmpl_real_path)
        except Exception:
            return
        if not isinstance(tmpl_data, dict):
            return

        target_data: Dict[str, Any] = {}
        if vfs.exists(target_cfg_uri):
            try:
                loaded = vfs.read_json(target_cfg_uri)
                if isinstance(loaded, dict):
                    target_data = loaded
            except Exception:
                target_data = {}

        proj_data = None
        if is_local and proj_pair_uri and vfs.exists(proj_pair_uri):
            try:
                proj_data = vfs.read_json(proj_pair_uri)
            except Exception:
                proj_data = None

        merged_data, changed = _deep_infill_dict(target_data, tmpl_data, project_data=proj_data)
        if changed or not vfs.exists(target_cfg_uri):
            if not is_local or merged_data:
                target_dir_uri = f"config.local://{mod}" if is_local else f"config://{mod}"
                vfs.makedirs(target_dir_uri, exist_ok=True)
                vfs.write_json(target_cfg_uri, merged_data, indent=2)

    def _deploy_and_strip_single_module_config(self, mod: str, mod_dir_real: str) -> None:
        """
        Extracts and infills configuration templates from <mod_dir_real>/configurable/
        and root <mod_dir_real>/config.*.json into config://<mod>/ and config.local://<mod>/,
        seeds initial system locale for 'core' if config.local.json is absent, then physically
        deletes all template files and .yscbignore from <mod_dir_real>.
        """
        if "://" in mod_dir_real:
            mod_dir_real = uri.resolve(mod_dir_real)
        if not os.path.isdir(mod_dir_real):
            return

        cfg_tpl_dir = os.path.join(mod_dir_real, "configurable")
        if os.path.isdir(cfg_tpl_dir):
            try:
                raw_files = [
                    f for f in os.listdir(cfg_tpl_dir)
                    if f.endswith(".json") and not f.startswith("_")
                ]
                tmpl_files = sorted(raw_files, key=lambda x: (1 if "local" in x else 0, x))
                for tmpl_file in tmpl_files:
                    tmpl_real = os.path.join(cfg_tpl_dir, tmpl_file)
                    target_cfg_uri, is_local, proj_pair_uri = _resolve_target_cfg_uris(mod, tmpl_file)
                    self._infill_single_template(mod, tmpl_real, target_cfg_uri, is_local, proj_pair_uri)
                    try:
                        os.remove(tmpl_real)
                    except OSError:
                        pass
                remaining = [f for f in os.listdir(cfg_tpl_dir) if f != "_format.json"]
                if not remaining and not os.path.isfile(os.path.join(cfg_tpl_dir, "_format.json")):
                    shutil.rmtree(cfg_tpl_dir, ignore_errors=True)
            except Exception:
                pass

        try:
            raw_root_files = [
                f for f in os.listdir(mod_dir_real)
                if f.startswith("config.") and f.endswith(".json") and os.path.isfile(os.path.join(mod_dir_real, f))
            ]
            root_files = sorted(raw_root_files, key=lambda x: (1 if "local" in x else 0, x))
            for tmpl_file in root_files:
                tmpl_real = os.path.join(mod_dir_real, tmpl_file)
                if tmpl_file in ("config.local.json", "config.project.json") or (
                    tmpl_file.startswith("config.") and (tmpl_file.endswith(".local.json") or tmpl_file.endswith(".project.json"))
                ):
                    target_cfg_uri, is_local, proj_pair_uri = _resolve_target_cfg_uris(mod, tmpl_file)
                else:
                    target_cfg_uri, is_local, proj_pair_uri = f"config://{mod}/config.project.json", False, None
                self._infill_single_template(mod, tmpl_real, target_cfg_uri, is_local, proj_pair_uri)
                try:
                    os.remove(tmpl_real)
                except OSError:
                    pass
        except Exception:
            pass

        # 初次建立 core 模組組態時，自動偵測使用者系統主語系播種至 config.local.json（最終 fallback 為開發團隊母語 'zh'）
        cfg_local_uri = f"config.local://{mod}/config.local.json"
        if mod == "core" and not vfs.exists(cfg_local_uri):
            try:
                from core import locale as core_locale
                detected_chain = core_locale.detect_system_locale_chain()
                vfs.makedirs(f"config.local://{mod}", exist_ok=True)
                vfs.write_json(cfg_local_uri, {"locale": detected_chain}, indent=2)
            except Exception:
                pass

        ignore_file = os.path.join(mod_dir_real, ".yscbignore")
        if os.path.isfile(ignore_file):
            try:
                os.remove(ignore_file)
            except OSError:
                pass

    def act_deploy_configs_from_modules(self) -> None:
        """
        Stage 3 (Atomic Config Deployment & Template Purge):
        Scans all modules in module://, infills/deploys configuration from configurable/ (or root config.*.json) to config:// and config.local://,
        and unconditionally physically deletes template files from modules/ to maintain pure code.
        """
        if not vfs.exists("module://"):
            return

        _, host_cfg = self._get_config()
        installed = host_cfg.get("installed_modules", {})

        for mod in vfs.listdir("module://"):
            if mod not in installed and mod != "core":
                continue

            mod_runtime_dir = f"module://{mod}"
            if not vfs.is_dir(mod_runtime_dir):
                continue

            self._deploy_and_strip_single_module_config(mod, uri.resolve(mod_runtime_dir))

    def act_delete(self, module_name: str, clean_mirror: bool = False, purge: bool = False) -> None:
        """
        刪除指定模組資產與相關狀態 (生命週期治理)。
        - 自動清空 cache://{module_name}/
        - 自動清除該模組於 core.gitignore 註冊之動態忽略規則
        - clean_mirror=True: 刪除 module.mirror://{module_name}/
        - purge=True: 強制物理刪除 storage://{module_name}/、storage.local://{module_name}/、config://{module_name}/ 與 config.local://{module_name}/
        """
        _clean_module_cache(module_name)
        try:
            from core import gitignore as gi_mod
            gi_mod.clear_dynamic(module_name, sync_now=False)
        except Exception:
            pass

        if clean_mirror:
            mirror_uri = f"module.mirror://{module_name}"
            if vfs.exists(mirror_uri):
                vfs.rmtree(mirror_uri, ignore_errors=True)

        if purge:
            for root_scheme in ("storage", "storage.local", "config", "config.local"):
                target_uri = f"{root_scheme}://{module_name}"
                if vfs.exists(target_uri):
                    try:
                        p = uri.resolve(target_uri)
                        root_p = uri.resolve(f"{root_scheme}://")
                        if os.path.abspath(p).startswith(os.path.abspath(root_p) + os.sep):
                            shutil.rmtree(p, ignore_errors=True)
                    except Exception:
                        pass

    def _reload_materialize_single_module(self, mod: str, ver: str, modules_root_real: str) -> None:
        """Extracts or copies a single module from mirror into staging, strips config templates, and atomically swaps into module://."""
        mirror_zip = f"module.mirror://{mod}/{ver}.zip"
        mirror_dir_uri = f"module.mirror://{mod}/{ver}/"
        real_dst = uri.resolve(f"module://{mod}/")
        staging_dir = os.path.join(modules_root_real, f".staging_{mod}_{os.getpid()}_{int(time.time() * 1000)}")

        if vfs.exists(mirror_zip):
            real_zip = uri.resolve(mirror_zip)
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
            os.makedirs(staging_dir, exist_ok=True)
            try:
                _extract_zip_safely(real_zip, staging_dir, source_label=mirror_zip)
                self._apply_release_index_override_to_staging(mod, ver, staging_dir)
                self._deploy_and_strip_single_module_config(mod, staging_dir)
                _atomic_swap_dir(staging_dir, real_dst)
            finally:
                if os.path.exists(staging_dir):
                    shutil.rmtree(staging_dir, ignore_errors=True)
        elif vfs.exists(mirror_dir_uri):
            real_mirror_src = uri.resolve(mirror_dir_uri)
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
            try:
                shutil.copytree(real_mirror_src, staging_dir, dirs_exist_ok=True)
                self._apply_release_index_override_to_staging(mod, ver, staging_dir)
                self._deploy_and_strip_single_module_config(mod, staging_dir)
                _atomic_swap_dir(staging_dir, real_dst)
            finally:
                if os.path.exists(staging_dir):
                    shutil.rmtree(staging_dir, ignore_errors=True)

    def act_reload(
        self,
        clean_stage: bool = True,
        inject_stage: bool = True,
        reconcile_deps: bool = True,
        ignore_sha256: bool = False,
    ) -> None:
        """
        4-Stage Atomic Reload Pipeline:
        Stage 1 (自癒拉取) -> Stage 1.5 (相依交集自檢與自動自癒) -> Stage 2 (解壓物化) -> Stage 3 (組態治理) -> Stage 4 (依賴注入與事件廣播)
        """
        _, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        default_prov = cfg.get("default_provider", "")

        # Stage 1: 拉取/還原壓縮來源檔 (若 module.mirror:// 缺少單檔 zip，自癒補齊；若版本已被淘汰則平滑遞補同三元組最高 active 版本)
        host_dir, _ = uri._get_host_config()
        for mod, meta in list(installed.items()):
            ver = meta.get("version", "1.0.0.0") if isinstance(meta, dict) else str(meta)
            prov = (meta.get("provider") if isinstance(meta, dict) else None) or default_prov
            mirror_zip = f"module.mirror://{mod}/{ver}.zip"
            if not vfs.exists(mirror_zip):
                try:
                    self.act_download(mod, ver, prov, ignore_sha256=ignore_sha256)
                except Exception:
                    fallback_ver = self._resolve_same_triplet_fallback_version(mod, ver, prov, base_dir=host_dir)
                    if fallback_ver and fallback_ver != ver:
                        try:
                            from core.log import log_info
                            log_info(
                                f"[core:reload] Exact revision '{mod}@{ver}' has been pruned upstream; "
                                f"seamlessly restoring compatible same-triplet revision '{fallback_ver}'."
                            )
                            self.act_download(mod, fallback_ver, prov, ignore_sha256=ignore_sha256)
                            self.act_register(mod, fallback_ver, prov)
                            if isinstance(meta, dict):
                                meta["version"] = fallback_ver
                            else:
                                installed[mod] = {"version": fallback_ver, "provider": prov}
                        except Exception:
                            pass

        # Stage 1.5: 相依交集自檢與自動自癒 (若 installed_modules 漏列底層相依模組或相依版號過舊且存在相容交集，自動補齊並重新讀取 installed)
        if reconcile_deps and default_prov:
            try:
                healed = self.reconcile_installed_dependencies(
                    provider_url=default_prov, strict=False, ignore_sha256=ignore_sha256
                )
                if healed:
                    from core.log import log_info
                    _, cfg = self._get_config()
                    installed = cfg.get("installed_modules", {})
                    for h_mod, h_old, h_new in healed:
                        if h_old is None:
                            log_info(f"[core:reload] Auto-healed missing dependency '{h_mod}@{h_new}'.")
                        else:
                            log_info(f"[core:reload] Auto-healed dependency '{h_mod}' ({h_old} -> {h_new}).")
            except RuntimeError:
                raise
            except Exception:
                pass

        # Stage 2 & 3: 於 .modules/.staging_<mod>_<pid>_<ts> 預組裝解壓與組態剝離，再執行目錄級原子替換
        modules_root_real = uri.resolve("module://")
        os.makedirs(modules_root_real, exist_ok=True)
        _cleanup_stale_swap_dirs(modules_root_real)

        if clean_stage and vfs.exists("module://"):
            for mod in vfs.listdir("module://"):
                if mod.startswith("."):
                    continue
                if mod != "core" and mod not in installed:
                    mod_real = uri.resolve(f"module://{mod}")
                    if os.path.isdir(mod_real):
                        old_del = os.path.join(modules_root_real, f".old_{mod}_{os.getpid()}_{int(time.time() * 1000)}")
                        try:
                            os.replace(mod_real, old_del)
                            _force_rmtree_with_retry(old_del, retries=3, retry_delay=0.03)
                        except OSError:
                            _force_rmtree_with_retry(mod_real, retries=3, retry_delay=0.03)
                    _clean_module_cache(mod)

        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0") if isinstance(meta, dict) else str(meta)
            self._reload_materialize_single_module(mod, ver, modules_root_real)

        # Stage 3 fallback: 對任何未經由 mirror 更新但存在於 module:// 的模組（如自舉 core）確保組態模板已部署並剝離
        self.act_deploy_configs_from_modules()
        _cleanup_stale_swap_dirs(modules_root_real)

        try:
            from core import config as cfg_mod, locale as loc_mod, symbols as sym_mod, contributes as contrib_mod
            from core.commands import dispatcher as disp_mod
            cfg_mod.reload()
            loc_mod.clear_cache()
            sym_mod.clear_callable_cache()
            contrib_mod.invalidate_cache()
            uri.invalidate_uri_cache()
            disp_mod.clear_cache()
        except Exception:
            pass

        # Stage 4: 依賴注入與事件廣播
        if inject_stage:
            self.contributes_aggregator.scan_and_inject()
            try:
                from core import gitignore as gi_mod
                gi_mod.sync(emit_event=False)
            except Exception:
                pass
            events.broadcast("on_reload", ExecutionContext("core", "reload", []), emit_module="core")

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        """
        Creates a full atomic snapshot:
        1. Backs up yscb.config.json.
        2. Backs up config:// (config/) and config.local:// (config.local/).
        3. Backs up storage:// (storage/).
        4. Backs up module:// (modules/).
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        if vfs.exists(snap_dir):
            vfs.rmtree(snap_dir, ignore_errors=True)
        vfs.makedirs(snap_dir)

        if os.path.isfile(host_cfg):
            vfs.copy(host_cfg, f"{snap_dir}/yscb.config.json")

        if vfs.exists("config://"):
            vfs.copy("config://", f"{snap_dir}/config/")

        if vfs.exists("config.local://"):
            vfs.copy("config.local://", f"{snap_dir}/config.local/")

        if vfs.exists("storage://"):
            vfs.copy("storage://", f"{snap_dir}/storage/")

        if vfs.exists("module://"):
            modules_root_real = uri.resolve("module://")
            _cleanup_stale_swap_dirs(modules_root_real)
            vfs.makedirs(f"{snap_dir}/modules/")
            for mod_entry in vfs.listdir("module://"):
                if mod_entry.startswith("."):
                    continue
                vfs.copy(f"module://{mod_entry}", f"{snap_dir}/modules/{mod_entry}")

        return snapshot_id

    def act_restore_snapshot(self, snapshot_id: str) -> None:
        """
        Restores a full atomic snapshot:
        1. Restores yscb.config.json.
        2. Restores config/, config.local/, and storage/.
        3. Restores modules/.
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snap_dir = f"snapshot://{snapshot_id}"
        snap_cfg = f"{snap_dir}/yscb.config.json"

        if not vfs.exists(snap_cfg):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' does not exist.")

        vfs.copy(snap_cfg, host_cfg)

        snap_config_dir = f"{snap_dir}/config"
        if vfs.exists(snap_config_dir):
            if vfs.exists("config://"):
                vfs.rmtree("config://", ignore_errors=True)
            vfs.copy(snap_config_dir, "config://")

        snap_config_local_dir = f"{snap_dir}/config.local"
        if vfs.exists(snap_config_local_dir):
            if vfs.exists("config.local://"):
                vfs.rmtree("config.local://", ignore_errors=True)
            vfs.copy(snap_config_local_dir, "config.local://")
        else:
            if vfs.exists("config.local://"):
                vfs.rmtree("config.local://", ignore_errors=True)
            vfs.makedirs("config.local://", exist_ok=True)

        snap_storage_dir = f"{snap_dir}/storage"
        if vfs.exists(snap_storage_dir):
            if vfs.exists("storage://"):
                vfs.rmtree("storage://", ignore_errors=True)
            vfs.copy(snap_storage_dir, "storage://")

        snap_mod_dir = f"{snap_dir}/modules"
        if vfs.exists(snap_mod_dir):
            modules_root_real = uri.resolve("module://")
            _cleanup_stale_swap_dirs(modules_root_real)
            snap_mods = set(vfs.listdir(snap_mod_dir))
            if vfs.exists("module://"):
                for existing_mod in vfs.listdir("module://"):
                    if existing_mod.startswith("."):
                        continue
                    if existing_mod not in snap_mods:
                        vfs.rmtree(f"module://{existing_mod}", ignore_errors=True)
            vfs.makedirs("module://")
            for mod_entry in snap_mods:
                if mod_entry.startswith("."):
                    continue
                vfs.copy(f"{snap_mod_dir}/{mod_entry}", f"module://{mod_entry}")

        self.act_reload(clean_stage=False, inject_stage=True)

    def act_migrate(self, module_name: str, old_version: str, new_version: str) -> bool:
        """
        Executes Incremental Migration Ladder:
        - Short-circuits when versions are bare 'build' or within the same version/major lock.
        - Evaluates minor/patch/revision version differential (including across @build triplets) across:
          * {major}.{minor}.x.py
          * {major}.{minor}.{patch}.x.py
          * {major}.{minor}.{patch}.{rev}.py
        - Silently skips non-existent scripts.
        - Raises RuntimeError on script failure to trigger atomic snapshot rollback.
        """
        if str(old_version).strip().lower() == "build" or str(new_version).strip().lower() == "build":
            return True

        try:
            t_old = semver.parse_semver(old_version)
            t_new = semver.parse_semver(new_version)
        except ValueError:
            return True

        if t_new.major != t_old.major or semver.compare_semver(new_version, old_version) <= 0:
            return True

        host_dir, yscb_dir = uri._get_host_config()

        def _resolve_space_dir(scheme: str, fallback_rel: str) -> str:
            try:
                return uri.resolve(f"{scheme}://{module_name}")
            except Exception:
                return os.path.join(yscb_dir, fallback_rel, module_name)

        context = {
            "host_dir": host_dir,
            "yscb_dir": yscb_dir,
            "config_dir": _resolve_space_dir("config", "config"),
            "config_local_dir": _resolve_space_dir("config.local", ".config.local"),
            "storage_dir": _resolve_space_dir("storage", "storage"),
            "storage_local_dir": _resolve_space_dir("storage.local", ".storage.local"),
            "old_version": old_version,
            "target_version": new_version,
        }

        mig_dir_uri = f"module://{module_name}/scripts/migrations"
        if not vfs.is_dir(mig_dir_uri):
            return True

        candidates: List[Tuple[Tuple[int, int, int, int, int, str], str]] = []
        for fname in vfs.listdir(mig_dir_uri):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            stem = fname[:-3]
            parts = stem.split(".")
            if len(parts) == 3 and parts[2] == "x":
                if not (parts[0].isdigit() and parts[1].isdigit()):
                    continue
                maj, min_v = int(parts[0]), int(parts[1])
                if maj == t_old.major and (t_old.major, t_old.minor) < (maj, min_v) <= (t_new.major, t_new.minor):
                    candidates.append(((maj, min_v, 0, 0, 0, fname), fname))
            elif len(parts) == 4 and parts[3] == "x":
                if not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
                    continue
                maj, min_v, pat_v = int(parts[0]), int(parts[1]), int(parts[2])
                if maj == t_old.major and t_old.triplet < (maj, min_v, pat_v) <= t_new.triplet:
                    candidates.append(((maj, min_v, pat_v, 0, 1, fname), fname))
            elif len(parts) == 4 and parts[3] != "x":
                if not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
                    continue
                try:
                    t_script = semver.parse_semver(stem)
                except Exception:
                    continue
                if (
                    t_script.major == t_old.major
                    and semver.compare_semver(old_version, stem) < 0
                    and semver.compare_semver(new_version, stem) >= 0
                ):
                    rev_num = int(t_script.revision) if str(t_script.revision).isdigit() else 999999
                    candidates.append(((t_script.major, t_script.minor, t_script.patch, rev_num, 2, fname), fname))

        candidates.sort(key=lambda item: item[0])

        for _, fname in candidates:
            script_rel = f"scripts/migrations/{fname}"
            mod_script_uri = f"module://{module_name}/{script_rel}"
            script_real = uri.resolve(mod_script_uri)
            safe_stem = fname[:-3].replace(".", "_")
            mod_key = f"_yscb_migrate_{module_name}_{safe_stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_key, script_real)
                if spec and spec.loader:
                    migrate_mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_key] = migrate_mod
                    try:
                        spec.loader.exec_module(migrate_mod)
                    except Exception:
                        sys.modules.pop(mod_key, None)
                        raise
                    if hasattr(migrate_mod, "migrate"):
                        res = migrate_mod.migrate(context)
                        if not res:
                            raise RuntimeError(f"Migration script '{script_rel}' returned False.")
            except Exception as e:
                raise RuntimeError(f"Migration step '{script_rel}' failed for module '{module_name}': {e}")

        return True

