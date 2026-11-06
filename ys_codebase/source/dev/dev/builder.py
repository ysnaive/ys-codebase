"""
Builder & Release Packager for YS-Codebase modules.
Implements Full Zip Packaging Standard:
- dev build: Pure single-file build package (build/<mod>/<ver>.build.zip, retains tests/).
- dev release: Pure single-file release package (release/<mod>/<ver>.zip, excludes tests/ and .yscbignore).
- No scattered unpacked directories in build/ or release/.
"""
import os
import json
import uuid
import fnmatch
import hashlib
import shutil
import functools
import zipfile
from typing import Tuple, Dict, List, Optional, Any, Set
from core import uri, vfs, semver
from dev.checker import Checker, discover_source_modules


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hex digest of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def compare_semver_safe(a: str, b: str) -> int:
    """Safe SemVer comparator with lexicographical fallback (returns 0 on equality)."""
    try:
        return semver.compare_semver(a, b)
    except Exception:
        return 1 if a > b else (-1 if a < b else 0)


DEV_BUILD_IGNORES = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".git*",
    ".pytest_cache",
    ".DS_Store",
]

RELEASE_IGNORES = [*DEV_BUILD_IGNORES, ".yscbignore", "tests", "tests/*"]


def _should_ignore(rel_path: str, ignores: List[str]) -> bool:
    norm_rel = rel_path.replace("\\", "/").strip("/")
    if not norm_rel:
        return False
    name = os.path.basename(norm_rel)
    parts = norm_rel.split("/")
    for pattern in ignores:
        pat = pattern.replace("\\", "/").strip("/")
        if not pat:
            continue
        pat_prefix = pat.rstrip("*").rstrip("/")
        if (
            fnmatch.fnmatch(name, pat)
            or fnmatch.fnmatch(norm_rel, pat)
            or fnmatch.fnmatch(norm_rel, pat + "/*")
            or (pat_prefix and norm_rel.startswith(pat_prefix + "/"))
            or (pat_prefix and f"/{pat_prefix}/" in f"/{norm_rel}/")
            or ("/" not in pat and any(fnmatch.fnmatch(p, pat) for p in parts))
        ):
            return True
    return False


_TEXT_EXTENSIONS = (".py", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh")
_TEXT_BASENAMES = (".yscbignore", ".gitignore")
_DETERMINISTIC_ZIP_DATETIME = (2020, 1, 1, 0, 0, 0)
_DETERMINISTIC_ZIP_EXTERNAL_ATTR = (0o644 & 0xFFFF) << 16


def _is_text_archive_entry(rel_file: str) -> bool:
    base = os.path.basename(rel_file)
    return rel_file.endswith(_TEXT_EXTENSIONS) or base in _TEXT_BASENAMES


def _create_module_archive_atomic(
    source_dir: str,
    target_zip_path: str,
    ignores: List[str],
    manifest_data: Dict[str, Any],
    target_version: str,
) -> int:
    """
    Atomically package module files from source_dir into target_zip_path via a PID/random .tmp staging file
    using deterministic entry ordering, fixed timestamp/permissions, and LF text normalization.
    Guarantees .tmp cleanup on any failure.
    """
    tmp_zip_path = f"{target_zip_path}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    entries: List[Tuple[str, str]] = []
    for root, dirs, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""

        dirs[:] = sorted(d for d in dirs if not _should_ignore(f"{rel_dir}/{d}".lstrip("/"), ignores))

        for f in sorted(files):
            rel_file = f"{rel_dir}/{f}".lstrip("/")
            if not _should_ignore(rel_file, ignores):
                entries.append((rel_file, os.path.join(root, f)))

    entries.sort(key=lambda item: item[0])

    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_file, src_file_path in entries:
                zinfo = zipfile.ZipInfo(filename=rel_file, date_time=_DETERMINISTIC_ZIP_DATETIME)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zinfo.external_attr = _DETERMINISTIC_ZIP_EXTERNAL_ATTR
                if rel_file == "manifest.json":
                    m_copy = dict(manifest_data)
                    m_copy["version"] = target_version
                    payload = json.dumps(m_copy, indent=2, ensure_ascii=False).replace("\r\n", "\n").encode("utf-8")
                else:
                    with open(src_file_path, "rb") as rf:
                        raw_bytes = rf.read()
                    if _is_text_archive_entry(rel_file):
                        try:
                            payload = raw_bytes.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
                        except UnicodeDecodeError:
                            payload = raw_bytes
                    else:
                        payload = raw_bytes
                zf.writestr(zinfo, payload)

        os.replace(tmp_zip_path, target_zip_path)
        return len(entries)
    finally:
        if os.path.exists(tmp_zip_path):
            try:
                os.remove(tmp_zip_path)
            except OSError:
                pass


class Builder:
    def __init__(self) -> None:
        self.checker = Checker()

    def _load_module_ignores(self, src_uri: str, base_ignores: List[str]) -> List[str]:
        ignore_file_uri = f"{src_uri}/.yscbignore"
        ignores = list(base_ignores)
        if vfs.exists(ignore_file_uri):
            try:
                content = vfs.read_text(ignore_file_uri)
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignores.append(line)
            except OSError:
                pass
        return ignores

    def _update_build_index(self, name: str, description: str = "") -> None:
        """Updates build/{name}/index.json scanning *.zip files."""
        mod_build_root = f"module.build://{name}"
        if not vfs.exists(mod_build_root):
            return

        real_build_dir = uri.resolve(mod_build_root)
        versions: List[str] = []
        if os.path.isdir(real_build_dir):
            for item in os.listdir(real_build_dir):
                if item.endswith(".zip"):
                    versions.append(item[:-4])

        versions.sort(key=functools.cmp_to_key(compare_semver_safe))
        index_data = {
            "name": name,
            "description": description or f"YS-Codebase module {name} (dev build)",
            "versions": versions,
        }
        vfs.write_json(f"{mod_build_root}/index.json", index_data, indent=2, atomic=True)

    def _update_release_index(
        self,
        name: str,
        description: str = "",
        new_version: Optional[str] = None,
        manifest_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Updates release/{name}/index.json with 3-Revision Sliding Window & Legacy Triplet Convergence.
        - Rule 1 (Same Triplet): Retain at most 3 latest revisions (X.Y.Z.W, X.Y.Z.W-1, X.Y.Z.W-2), purge older.
        - Rule 2 (Cross Triplet): When bumped to X.Y.Z+1 or higher, legacy triplets retain only their highest revision (X.Y.Z.W_max).
        - Rule 3 (Dual-Track Index SSOT): Top-level 'versions' holds active downloadable versions within the sliding window;
          'releases' ledger permanently retains historical release metadata with status='active'|'pruned'.
        """
        mod_rel_root = f"module.release://{name}"
        if not vfs.exists(mod_rel_root):
            return

        real_rel_dir = uri.resolve(mod_rel_root)
        if not os.path.isdir(real_rel_dir):
            return

        index_uri = f"{mod_rel_root}/index.json"
        existing_index: Dict[str, Any] = {}
        if vfs.exists(index_uri):
            try:
                raw_idx = vfs.read_json(index_uri)
                if isinstance(raw_idx, dict):
                    existing_index = raw_idx
            except Exception:
                existing_index = {}

        existing_versions = existing_index.get("versions", []) if isinstance(existing_index.get("versions"), list) else []
        existing_releases = dict(existing_index.get("releases")) if isinstance(existing_index.get("releases"), dict) else {}

        zip_versions: Set[str] = {
            item[:-4] for item in os.listdir(real_rel_dir) if item.endswith(".zip")
        }
        candidate_active: Set[str] = set(existing_versions) | zip_versions
        if new_version:
            candidate_active.add(new_version)

        active_versions: List[str] = []
        pruned_versions: Set[str] = set()

        new_tuple: Optional[semver.VersionTuple] = None
        if new_version:
            try:
                new_tuple = semver.parse_semver(new_version)
            except ValueError:
                new_tuple = None

        if new_tuple is not None:
            triplet_map: Dict[Tuple[int, int, int], List[Tuple[semver.VersionTuple, str]]] = {}
            for item_ver in candidate_active:
                try:
                    item_tuple = semver.parse_semver(item_ver)
                    trip = item_tuple.triplet
                    if trip not in triplet_map:
                        triplet_map[trip] = []
                    triplet_map[trip].append((item_tuple, item_ver))
                except ValueError:
                    pass

            for trip, items in triplet_map.items():
                items.sort(key=functools.cmp_to_key(lambda a, b: semver.compare_semver(a[0], b[0])), reverse=True)
                retained = items[:3] if trip == new_tuple.triplet else items[:1]
                purge = items[3:] if trip == new_tuple.triplet else items[1:]
                for _, keep_ver in retained:
                    active_versions.append(keep_ver)
                for _, purge_ver in purge:
                    pruned_versions.add(purge_ver)
                    purge_path = os.path.join(real_rel_dir, f"{purge_ver}.zip")
                    if os.path.isfile(purge_path):
                        try:
                            os.remove(purge_path)
                        except OSError:
                            pass
        else:
            for item_ver in candidate_active:
                try:
                    semver.parse_semver(item_ver)
                    active_versions.append(item_ver)
                except ValueError:
                    pass

        active_versions.sort(key=functools.cmp_to_key(compare_semver_safe))
        active_set = set(active_versions)

        for v_key, v_meta in list(existing_releases.items()):
            meta_copy = dict(v_meta) if isinstance(v_meta, dict) else {}
            meta_copy["status"] = "active" if v_key in active_set else "pruned"
            existing_releases[v_key] = meta_copy

        for p_ver in pruned_versions:
            meta_copy = dict(existing_releases.get(p_ver, {})) if isinstance(existing_releases.get(p_ver), dict) else {}
            meta_copy["status"] = "pruned"
            if "dependencies" not in meta_copy:
                meta_copy["dependencies"] = {}
            existing_releases[p_ver] = meta_copy

        for a_ver in active_versions:
            meta_copy = dict(existing_releases.get(a_ver, {})) if isinstance(existing_releases.get(a_ver), dict) else {}
            meta_copy["status"] = "active"
            zip_cand = os.path.join(real_rel_dir, f"{a_ver}.zip")
            if "dependencies" not in meta_copy:
                if os.path.isfile(zip_cand):
                    try:
                        with zipfile.ZipFile(zip_cand, "r") as zf:
                            z_mf = json.loads(zf.read("manifest.json").decode("utf-8"))
                            if isinstance(z_mf.get("dependencies"), dict):
                                meta_copy["dependencies"] = dict(z_mf["dependencies"])
                    except Exception:
                        pass
                if "dependencies" not in meta_copy:
                    meta_copy["dependencies"] = {}
            if os.path.isfile(zip_cand) and (
                a_ver == new_version or "sha256" not in meta_copy or not meta_copy.get("sha256")
            ):
                meta_copy["sha256"] = compute_file_sha256(zip_cand)
            existing_releases[a_ver] = meta_copy

        if new_version and isinstance(manifest_data, dict):
            new_meta = dict(existing_releases.get(new_version, {})) if isinstance(existing_releases.get(new_version), dict) else {}
            new_meta["status"] = "active" if new_version in active_set else "pruned"
            raw_deps = manifest_data.get("dependencies", {})
            if isinstance(raw_deps, dict):
                new_meta["dependencies"] = dict(raw_deps)
            elif "dependencies" not in new_meta:
                new_meta["dependencies"] = {}
            rel_info = manifest_data.get("release")
            if isinstance(rel_info, dict):
                for k in ("type", "urgency", "summary"):
                    if isinstance(rel_info.get(k), str) and rel_info[k].strip():
                        new_meta[k] = rel_info[k].strip()
            if not new_meta.get("sha256"):
                new_zip_cand = os.path.join(real_rel_dir, f"{new_version}.zip")
                if os.path.isfile(new_zip_cand):
                    new_meta["sha256"] = compute_file_sha256(new_zip_cand)
            existing_releases[new_version] = new_meta

        sorted_rel_keys = sorted(existing_releases.keys(), key=functools.cmp_to_key(compare_semver_safe))
        ordered_releases = {k: existing_releases[k] for k in sorted_rel_keys}

        index_data = {
            "name": name,
            "description": description or existing_index.get("description") or f"YS-Codebase module {name}",
            "versions": active_versions,
            "releases": ordered_releases,
        }
        vfs.write_json(index_uri, index_data, indent=2, atomic=True)

    def build_module(self, name: str, clean: bool = True) -> Tuple[bool, str]:
        """
        本地完整打包 (dev build):
        - 打包前自動清空 build/<name>/ 目錄（當 clean=True）。
        - 輸出單一 build/<name>/<ver>.build.zip。
        - 100% 完整保留 tests/ 與開發檔案。
        - 產物版本號強制標記為 X.Y.Z.build。
        - 自動更新 build/{name}/index.json。
        """
        src_uri = f"module.source://{name}"
        if not vfs.exists(src_uri):
            return False, f"Source module not found at {src_uri}."

        report = self.checker.check_module(name)
        if not report.passed:
            err_msg = "\n  - ".join(report.errors)
            return False, f"Check failed for module '{name}':\n  - {err_msg}"

        manifest_data = vfs.read_json(f"{src_uri}/manifest.json")
        raw_version = manifest_data.get("version", "1.0.0.0")
        v_tuple = semver.parse_semver(raw_version)
        build_version = f"{v_tuple.major}.{v_tuple.minor}.{v_tuple.patch}.build"

        mod_build_root = f"module.build://{name}"
        vfs.makedirs(mod_build_root)
        real_build_dir = uri.resolve(mod_build_root)

        if clean and os.path.isdir(real_build_dir):
            for item in list(os.listdir(real_build_dir)):
                p = os.path.join(real_build_dir, item)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        target_zip_path = os.path.join(real_build_dir, f"{build_version}.zip")
        src_real = uri.resolve(src_uri)
        copied_count = _create_module_archive_atomic(
            src_real,
            target_zip_path,
            DEV_BUILD_IGNORES,
            manifest_data,
            build_version,
        )

        self._update_build_index(name, description=manifest_data.get("description", ""))
        return True, f"Successfully built dev package '{name}@{build_version}' ({copied_count} files) -> {target_zip_path}."

    def package_release(self, name: str, target_version: str) -> Tuple[bool, str]:
        """
        純淨發布打包 (dev release packager):
        - 輸出單一 release/<name>/<target_version>.zip。
        - 嚴格依 .yscbignore 與 RELEASE_IGNORES 排除 tests/ 與開發檔案。
        - 自動執行 3-Revision 滑動窗口保留與淘汰清理。
        - 更新 release/{name}/index.json。
        """
        src_uri = f"module.source://{name}"
        if not vfs.exists(src_uri):
            return False, f"Source module not found at {src_uri}."

        manifest_uri = f"{src_uri}/manifest.json"
        if not vfs.exists(manifest_uri):
            return False, f"manifest.json not found for module '{name}'."
        try:
            manifest_data = vfs.read_json(manifest_uri)
            if not isinstance(manifest_data, dict):
                return False, f"Invalid manifest.json format for module '{name}'."
        except Exception as e:
            return False, f"Invalid JSON in manifest.json for module '{name}': {e}"

        mod_rel_root = f"module.release://{name}"
        vfs.makedirs(mod_rel_root)

        real_rel_dir = uri.resolve(mod_rel_root)
        target_zip_path = os.path.join(real_rel_dir, f"{target_version}.zip")
        ignores = self._load_module_ignores(src_uri, RELEASE_IGNORES)
        src_real = uri.resolve(src_uri)

        copied_count = _create_module_archive_atomic(
            src_real,
            target_zip_path,
            ignores,
            manifest_data,
            target_version,
        )

        self._update_release_index(
            name,
            description=manifest_data.get("description", ""),
            new_version=target_version,
            manifest_data=manifest_data,
        )
        return True, f"Successfully packaged release '{name}@{target_version}' ({copied_count} files) -> {target_zip_path}."

    def build_all(self, clean: bool = True) -> Dict[str, Tuple[bool, str]]:
        return {mod: self.build_module(mod, clean=clean) for mod in discover_source_modules()}
