"""
Builder & Release Packager for YS-Codebase modules.
Implements Full Zip Packaging Standard:
- dev build: Pure single-file build package (build/<mod>/<ver>.build.zip, retains tests/).
- dev release: Pure single-file release package (release/<mod>/<ver>.zip, excludes tests/ and .yscbignore).
- No scattered unpacked directories in build/ or release/.
"""
import os
import json
import fnmatch
import shutil
import functools
import zipfile
from typing import Tuple, Dict, List, Optional, Any
from core import uri, vfs, semver
from dev.checker import Checker, discover_source_modules

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

RELEASE_IGNORES = [
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
]


def _should_ignore(rel_path: str, ignores: List[str]) -> bool:
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


def _create_module_archive_atomic(
    source_dir: str,
    target_zip_path: str,
    ignores: List[str],
    manifest_data: Dict[str, Any],
    target_version: str,
) -> int:
    """
    Atomically package module files from source_dir into target_zip_path via a .tmp staging file.
    Guarantees .zip.tmp cleanup on any failure.
    """
    tmp_zip_path = target_zip_path + ".tmp"
    copied_count = 0
    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source_dir):
                rel_dir = os.path.relpath(root, source_dir).replace("\\", "/")
                if rel_dir == ".":
                    rel_dir = ""

                dirs[:] = [d for d in dirs if not _should_ignore(f"{rel_dir}/{d}".lstrip("/"), ignores)]

                for f in files:
                    rel_file = f"{rel_dir}/{f}".lstrip("/")
                    if not _should_ignore(rel_file, ignores):
                        src_file_path = os.path.join(root, f)
                        if rel_file == "manifest.json":
                            m_copy = dict(manifest_data)
                            m_copy["version"] = target_version
                            zf.writestr("manifest.json", json.dumps(m_copy, indent=2, ensure_ascii=False))
                        else:
                            zf.write(src_file_path, arcname=rel_file)
                        copied_count += 1

        if os.path.exists(target_zip_path):
            os.remove(target_zip_path)
        os.replace(tmp_zip_path, target_zip_path)
        return copied_count
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

        versions.sort(key=functools.cmp_to_key(semver.compare_semver))
        index_data = {
            "name": name,
            "description": description or f"YS-Codebase module {name} (dev build)",
            "versions": versions,
        }
        vfs.write_json(f"{mod_build_root}/index.json", index_data, indent=2)

    def _update_release_index(self, name: str, description: str = "", new_version: Optional[str] = None) -> None:
        """
        Updates release/{name}/index.json with 3-Revision Sliding Window & Legacy Triplet Convergence.
        - Rule 1 (Same Triplet): Retain at most 3 latest revisions (X.Y.Z.W, X.Y.Z.W-1, X.Y.Z.W-2), purge older.
        - Rule 2 (Cross Triplet): When bumped to X.Y.Z+1 or higher, legacy triplets retain only their highest revision (X.Y.Z.W_max).
        - Rule 3 (Index SSOT): Re-scan active physical zip files to generate index.json.
        """
        mod_rel_root = f"module.release://{name}"
        if not vfs.exists(mod_rel_root):
            return

        real_rel_dir = uri.resolve(mod_rel_root)
        if not os.path.isdir(real_rel_dir):
            return

        if new_version:
            try:
                new_tuple = semver.parse_semver(new_version)
            except ValueError:
                new_tuple = None

            if new_tuple is not None:
                triplet_map: Dict[Tuple[int, int, int], List[Tuple[semver.VersionTuple, str, str]]] = {}
                for item in list(os.listdir(real_rel_dir)):
                    item_path = os.path.join(real_rel_dir, item)
                    if item.endswith(".zip"):
                        item_ver = item[:-4]
                        try:
                            item_tuple = semver.parse_semver(item_ver)
                            trip = item_tuple.triplet
                            if trip not in triplet_map:
                                triplet_map[trip] = []
                            triplet_map[trip].append((item_tuple, item_ver, item_path))
                        except ValueError:
                            pass

                for trip, items in triplet_map.items():
                    items.sort(key=functools.cmp_to_key(lambda a, b: semver.compare_semver(a[0], b[0])), reverse=True)
                    purge = items[3:] if trip == new_tuple.triplet else items[1:]
                    for _, _, purge_path in purge:
                        try:
                            os.remove(purge_path)
                        except OSError:
                            pass

        versions: List[str] = [
            item[:-4] for item in os.listdir(real_rel_dir) if item.endswith(".zip")
        ]
        versions.sort(key=functools.cmp_to_key(semver.compare_semver))
        index_data = {
            "name": name,
            "description": description or f"YS-Codebase module {name}",
            "versions": versions,
        }
        vfs.write_json(f"{mod_rel_root}/index.json", index_data, indent=2)

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

        manifest_data = vfs.read_json(f"{src_uri}/manifest.json")
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

        self._update_release_index(name, description=manifest_data.get("description", ""), new_version=target_version)
        return True, f"Successfully packaged release '{name}@{target_version}' ({copied_count} files) -> {target_zip_path}."

    def build_all(self, clean: bool = True) -> Dict[str, Tuple[bool, str]]:
        return {mod: self.build_module(mod, clean=clean) for mod in discover_source_modules()}
