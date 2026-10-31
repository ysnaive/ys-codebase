"""
YS-Codebase Atomic Package Lifecycle Engine.
100% Python Standard Library, Zero Third-Party Dependency.
Implements:
- 3-Tier Resolution Chain (build:// -> mirror:// -> provider)
- 4-Segment SemVer Dependency Solving
- Dual-Layer Snapshots & Atomic Rollback (modules/, config/, storage/, yscb.config.json)
- Incremental Migration Ladder Subsystem
"""
import os
import sys
import json
import time
import copy
import shutil
import zipfile
import urllib.request
import importlib.util
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Set, Generator

from core import uri
from core import vfs
from core.context import ExecutionContext
from core import semver
from core.contributes import ContributesAggregator
from core import events
from core.platform import InterProcessLock


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
            _replace_with_retry(target_abs, old_abs)
            moved_old = True

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
        return f"config://{mod}/config.local.json", True, f"config://{mod}/config.project.json"
    if tmpl_file == "config.project.json":
        return f"config://{mod}/config.project.json", False, None
    if tmpl_file.startswith("config.") and tmpl_file.endswith(".local.json"):
        sub_name = tmpl_file[len("config."):-len(".local.json")]
        return (
            f"config://{mod}/config.{sub_name}.local.json",
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

    def _get_config(self) -> Tuple[str, Dict[str, Any]]:
        host_dir, _ = uri._get_host_config()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        if not vfs.is_file(cfg_path):
            raise FileNotFoundError(f"Configuration file not found: {cfg_path}")
        return cfg_path, vfs.read_json(cfg_path)

    def _save_config(self, cfg_path: str, data: Dict[str, Any]) -> None:
        vfs.write_json(cfg_path, data, indent=2, atomic=True)

    def act_fetch(self, provider_url: str, relative_path: str) -> Tuple[bool, Any]:
        """
        Fetches a manifest, index, or package archive from local filesystem or remote HTTP/HTTPS.
        """
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

    def act_lock(self, operation: str, timeout: float = 10.0) -> None:
        """
        Acquire inter-process lock on cache://.yscb.lock using core.platform.InterProcessLock.
        """
        lock_uri = "cache://.yscb.lock"
        lock_path = uri.resolve(lock_uri)
        vfs.makedirs("cache://", exist_ok=True)

        lock = InterProcessLock(lock_path)
        if not lock.acquire(blocking=True, timeout_sec=timeout):
            raise BlockingIOError(f"Another yscb process is currently holding the lock for operation '{operation}'.")
        self._active_locks[operation] = lock

    def act_unlock(self, operation: str) -> None:
        """Release inter-process lock on cache://.yscb.lock."""
        lock = self._active_locks.pop(operation, None)
        if lock is not None:
            lock.release()
        else:
            lock_uri = "cache://.yscb.lock"
            try:
                lock_p = uri.resolve(lock_uri)
                if os.path.exists(lock_p):
                    InterProcessLock(lock_p).release()
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

        p_abs = os.path.abspath(provider_url) if not provider_url.startswith(("http://", "https://", "file://")) else None
        if p_abs and os.path.isdir(p_abs):
            for b_path in (
                os.path.join(p_abs, "build", module_name, f"{version}.zip"),
                os.path.join(p_abs, "build", module_name, f"{version}.build.zip"),
            ):
                if os.path.isfile(b_path):
                    shutil.copy2(b_path, dest_zip_real)
                    return dest_zip_uri

        raise FileNotFoundError(
            f"Build package not found for '{module_name}'. Please run 'python yscb.py dev build {module_name}' first."
        )

    def _download_from_release_tier(self, module_name: str, version: str, provider_url: str, dest_zip_real: str, dest_zip_uri: str) -> Optional[str]:
        """Tier 2 download: resolves package from module.release:// or local provider directory."""
        rel_zip = f"module.release://{module_name}/{version}.zip"
        if vfs.exists(rel_zip):
            shutil.copy2(uri.resolve(rel_zip), dest_zip_real)
            return dest_zip_uri

        p_abs = os.path.abspath(provider_url) if not provider_url.startswith(("http://", "https://", "file://")) else None
        if p_abs and os.path.isdir(p_abs):
            for z_path in (
                os.path.join(p_abs, module_name, f"{version}.zip"),
                os.path.join(p_abs, "release", module_name, f"{version}.zip"),
            ):
                if os.path.isfile(z_path):
                    shutil.copy2(z_path, dest_zip_real)
                    return dest_zip_uri

            for d_path in (
                os.path.join(p_abs, module_name, version),
                os.path.join(p_abs, "release", module_name, version),
            ):
                if os.path.isdir(d_path) and os.path.isfile(os.path.join(d_path, "manifest.json")):
                    with zipfile.ZipFile(dest_zip_real, "w", zipfile.ZIP_DEFLATED) as zf:
                        for root, _, files in os.walk(d_path):
                            for f in files:
                                f_p = os.path.join(root, f)
                                arc = os.path.relpath(f_p, d_path).replace("\\", "/")
                                zf.write(f_p, arcname=arc)
                    return dest_zip_uri
        return None

    def _download_from_remote_tier(self, module_name: str, version: str, provider_url: str, dest_zip_real: str, dest_zip_uri: str) -> str:
        """Tier 3 download: fetches single-file <version>.zip from remote HTTP/HTTPS provider."""
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
            return dest_zip_uri
        except Exception as e:
            if vfs.exists(dest_zip_real):
                try:
                    vfs.remove(dest_zip_real)
                except Exception:
                    pass
            raise RuntimeError(f"Failed to download module '{module_name}@{version}' from '{remote_zip_url}': {e}")

    def act_download(self, module_name: str, version: str, provider_url: str) -> str:
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

        rel_hit = self._download_from_release_tier(module_name, version, provider_url, dest_zip_real, dest_zip_uri)
        if rel_hit is not None:
            return rel_hit

        return self._download_from_remote_tier(module_name, version, provider_url, dest_zip_real, dest_zip_uri)

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
                    vers = idx_data.get("versions", []) if isinstance(idx_data, dict) else []
                    best_v = semver.find_best_version(vers, version_constraint)
                    if best_v:
                        zip_p = os.path.join(os.path.dirname(idx_p), f"{best_v}.zip")
                        if vfs.is_file(zip_p):
                            with zipfile.ZipFile(zip_p, "r") as zf:
                                return json.loads(zf.read("manifest.json").decode("utf-8"))
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

        p_abs = os.path.abspath(provider_url) if not provider_url.startswith(("http://", "https://", "file://")) else None
        if p_abs and os.path.isdir(p_abs):
            loc_mf = self._find_manifest_in_local_provider(module_name, p_abs, version_constraint, is_build_req)
            if loc_mf is not None:
                return loc_mf

        ok, res = self.act_fetch(provider_url, f"{module_name}/index.json")
        if ok and isinstance(res, dict):
            if "versions" in res and isinstance(res["versions"], list):
                best_ver = semver.find_best_version(res["versions"], version_constraint)
                if best_ver:
                    return {"name": module_name, "version": best_ver, "dependencies": {}}
            elif "manifest" in res:
                return res["manifest"]

        raise ModuleNotFoundError(
            f"Cannot find module '{module_name}' (version constraint: '{version_constraint}') in provider '{provider_url}'."
        )

    def act_solve_deps(
        self,
        target_module: str,
        version_constraint: Optional[str],
        provider_url: str,
    ) -> List[Tuple[str, str]]:
        """
        Recursively resolves dependency topology with 4-segment SemVer constraint satisfaction.
        """
        ordered_list: List[Tuple[str, str]] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def _solve(mod_name: str, ver_req: Optional[str]) -> None:
            if mod_name in visiting:
                raise ValueError(f"Circular dependency detected: '{mod_name}' in call chain.")
            if mod_name in visited:
                return

            visiting.add(mod_name)
            manifest = self._get_module_manifest_from_provider_or_local(mod_name, provider_url, ver_req)
            resolved_ver = manifest.get("version", "1.0.0.0")

            if ver_req and not semver.match_constraint(resolved_ver, ver_req):
                raise RuntimeError(
                    f"Cannot resolve dependency for '{mod_name}': "
                    f"resolved version '{resolved_ver}' does not satisfy constraint '{ver_req}'."
                )

            parsed_deps = _parse_dependencies(manifest.get("dependencies", {}))
            for dep_name, dep_ver in parsed_deps.items():
                if dep_name != "core":
                    _solve(dep_name, dep_ver)

            visiting.remove(mod_name)
            visited.add(mod_name)
            ordered_list.append((mod_name, resolved_ver))

        _solve(target_module, version_constraint)
        return ordered_list

    def act_prepare(self, target_list: List[Tuple[str, str]], provider_url: str, force: bool = False) -> None:
        for mod, ver in target_list:
            mirror_zip = f"module.mirror://{mod}/{ver}.zip"
            if force or not vfs.exists(mirror_zip):
                self.act_download(mod, ver, provider_url)

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
                vfs.makedirs(f"config://{mod}", exist_ok=True)
                vfs.write_json(target_cfg_uri, merged_data, indent=2)

    def _deploy_and_strip_single_module_config(self, mod: str, mod_dir_real: str) -> None:
        """
        Extracts and infills configuration templates from <mod_dir_real>/configurable/
        and root <mod_dir_real>/config.*.json into config://<mod>/, seeds initial
        system locale for 'core' if config.local.json is absent, then physically
        deletes all template files and .yscbignore from <mod_dir_real>.
        """
        if "://" in mod_dir_real:
            mod_dir_real = uri.resolve(mod_dir_real)
        if not os.path.isdir(mod_dir_real):
            return

        cfg_tpl_dir = os.path.join(mod_dir_real, "configurable")
        if os.path.isdir(cfg_tpl_dir):
            try:
                raw_files = [f for f in os.listdir(cfg_tpl_dir) if f.endswith(".json")]
                tmpl_files = sorted(raw_files, key=lambda x: (1 if "local" in x else 0, x))
                for tmpl_file in tmpl_files:
                    tmpl_real = os.path.join(cfg_tpl_dir, tmpl_file)
                    target_cfg_uri, is_local, proj_pair_uri = _resolve_target_cfg_uris(mod, tmpl_file)
                    self._infill_single_template(mod, tmpl_real, target_cfg_uri, is_local, proj_pair_uri)
                    try:
                        os.remove(tmpl_real)
                    except OSError:
                        pass
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
        cfg_local_uri = f"config://{mod}/config.local.json"
        if mod == "core" and not vfs.exists(cfg_local_uri):
            try:
                from core import locale as core_locale
                detected_chain = core_locale.detect_system_locale_chain()
                vfs.makedirs(f"config://{mod}", exist_ok=True)
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
        Scans all modules in module://, infills/deploys configuration from configurable/ (or root config.*.json) to config://,
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
        - clean_mirror=True: 刪除 module.mirror://{module_name}/
        - purge=True: 強制物理刪除 storage://{module_name}/ 與 config://{module_name}/
        """
        _clean_module_cache(module_name)

        if clean_mirror:
            mirror_uri = f"module.mirror://{module_name}"
            if vfs.exists(mirror_uri):
                vfs.rmtree(mirror_uri, ignore_errors=True)

        if purge:
            for root_scheme in ("storage", "config"):
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
                self._deploy_and_strip_single_module_config(mod, staging_dir)
                _atomic_swap_dir(staging_dir, real_dst)
            finally:
                if os.path.exists(staging_dir):
                    shutil.rmtree(staging_dir, ignore_errors=True)

    def act_reload(self, clean_stage: bool = True, inject_stage: bool = True) -> None:
        """
        4-Stage Atomic Reload Pipeline:
        Stage 1 (自癒拉取) -> Stage 2 (解壓物化) -> Stage 3 (組態治理) -> Stage 4 (依賴注入與事件廣播)
        """
        _, cfg = self._get_config()
        installed = cfg.get("installed_modules", {})
        default_prov = cfg.get("default_provider", "")

        # Stage 1: 拉取/還原壓縮來源檔 (若 module.mirror:// 缺少單檔 zip，自癒補齊)
        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0")
            prov = meta.get("provider") or default_prov
            mirror_zip = f"module.mirror://{mod}/{ver}.zip"
            if not vfs.exists(mirror_zip):
                try:
                    self.act_download(mod, ver, prov)
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
                    vfs.rmtree(f"module://{mod}", ignore_errors=True)
                    _clean_module_cache(mod)

        for mod, meta in installed.items():
            ver = meta.get("version", "1.0.0.0")
            self._reload_materialize_single_module(mod, ver, modules_root_real)

        # Stage 3 fallback: 對任何未經由 mirror 更新但存在於 module:// 的模組（如自舉 core）確保組態模板已部署並剝離
        self.act_deploy_configs_from_modules()
        _cleanup_stale_swap_dirs(modules_root_real)

        # Stage 4: 依賴注入與事件廣播
        if inject_stage:
            self.contributes_aggregator.scan_and_inject()
            events.broadcast("on_reload", ExecutionContext("core", "reload", []), emit_module="core")

    def act_snapshot(self, tag: Optional[str] = None) -> str:
        """
        Creates a full atomic snapshot:
        1. Backs up yscb.config.json.
        2. Backs up config:// (config/).
        3. Backs up storage:// (storage/).
        4. Backs up module:// (modules/).
        """
        host_dir, _ = uri._get_host_config()
        host_cfg = os.path.join(host_dir, "yscb.config.json")
        snapshot_id = tag or f"snap_{int(time.time())}"
        snap_dir = f"snapshot://{snapshot_id}"
        vfs.makedirs(snap_dir)

        if os.path.isfile(host_cfg):
            vfs.copy(host_cfg, f"{snap_dir}/yscb.config.json")

        if vfs.exists("config://"):
            vfs.copy("config://", f"{snap_dir}/config/")

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
        2. Restores config/ and storage/.
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
        - Evaluates minor version differential: {major}.{minor}.x.py
        - Silently skips non-existent scripts.
        - Raises RuntimeError on script failure to trigger atomic snapshot rollback.
        """
        t_old = semver.parse_semver(old_version)
        t_new = semver.parse_semver(new_version)

        if t_new.major != t_old.major or t_new.minor <= t_old.minor:
            return True

        host_dir, yscb_dir = uri._get_host_config()
        storage_dir = (
            uri.resolve(f"storage://{module_name}")
            if vfs.exists(f"storage://{module_name}")
            else os.path.join(yscb_dir, "storage", module_name)
        )

        context = {
            "host_dir": host_dir,
            "storage_dir": storage_dir,
            "old_version": old_version,
            "target_version": new_version,
        }

        for m in range(t_old.minor + 1, t_new.minor + 1):
            script_rel = f"scripts/migrations/{t_old.major}.{m}.x.py"
            mod_script_uri = f"module://{module_name}/{script_rel}"

            if vfs.exists(mod_script_uri):
                script_real = uri.resolve(mod_script_uri)
                mod_key = f"_yscb_migrate_{module_name}_{t_old.major}_{m}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_key, script_real)
                    if spec and spec.loader:
                        migrate_mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_key] = migrate_mod
                        spec.loader.exec_module(migrate_mod)
                        if hasattr(migrate_mod, "migrate"):
                            res = migrate_mod.migrate(context)
                            if not res:
                                raise RuntimeError(f"Migration script '{script_rel}' returned False.")
                except Exception as e:
                    raise RuntimeError(f"Migration step '{script_rel}' failed for module '{module_name}': {e}")

        return True

