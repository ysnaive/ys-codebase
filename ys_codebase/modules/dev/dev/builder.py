"""
Builder & Release Packager for YS-Codebase modules.
- dev build: 100% Complete Packaging (retains tests/, sets version to X.Y.Z.build).
- dev release: Hermetic Clean Packaging (excludes tests/ and .yscbignore, immutable).
"""
import os
import sys
import json
import fnmatch
import shutil
import functools
from typing import Tuple, Dict, List, Optional
from core import uri
from core import semver
from dev.checker import Checker

DEV_BUILD_IGNORES = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".git*",
    ".pytest_cache",
    ".DS_Store"
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
    "tests/*"
]

class Builder:
    def __init__(self):
        self.checker = Checker()

    def _load_module_ignores(self, src_uri: str, base_ignores: List[str]) -> List[str]:
        ignore_file_uri = f"{src_uri}/.yscbignore"
        ignores = list(base_ignores)
        if uri.exists(ignore_file_uri):
            try:
                content = uri.read_text(ignore_file_uri)
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignores.append(line)
            except Exception:
                pass
        return ignores

    def _should_ignore(self, rel_path: str, ignores: List[str]) -> bool:
        norm_rel = rel_path.replace("\\", "/").rstrip("/")
        name = os.path.basename(norm_rel)
        for pattern in ignores:
            pat = pattern.replace("\\", "/").rstrip("/")
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(norm_rel, pat) or fnmatch.fnmatch(norm_rel, pat + "/*") or norm_rel.startswith(pat.rstrip("*").rstrip("/") + "/"):
                return True
        return False

    def _update_build_index(self, name: str, description: str = "") -> None:
        """Updates build/{name}/index.json maintaining isomorphic provider structure."""
        mod_build_root = f"module.build.root://{name}"
        if not uri.exists(mod_build_root):
            return
            
        versions: List[str] = []
        for item in uri.listdir(mod_build_root):
            sub_uri = f"{mod_build_root}/{item}"
            if uri.is_dir(sub_uri) and uri.exists(f"{sub_uri}/manifest.json"):
                versions.append(item)
                
        versions.sort(key=functools.cmp_to_key(semver.compare_semver))
        index_data = {
            "name": name,
            "description": description or f"YS-Codebase module {name} (dev build)",
            "versions": versions
        }
        uri.write_json(f"{mod_build_root}/index.json", index_data, indent=2)

    def _update_release_index(self, name: str, description: str = "", new_version: Optional[str] = None) -> None:
        """
        Updates release/{name}/index.json with Single Active Revision per X.Y.Z rule.
        If new_version is provided, automatically eliminates older revisions under the same major.minor.patch.
        """
        mod_rel_root = f"release.root://{name}"
        if not uri.exists(mod_rel_root):
            return
        
        # 1. Clean up old revisions if new_version given
        if new_version:
            new_tuple = semver.parse_semver(new_version)
            for item in list(uri.listdir(mod_rel_root)):
                sub_uri = f"{mod_rel_root}/{item}"
                if uri.is_dir(sub_uri) and item != new_version:
                    try:
                        item_tuple = semver.parse_semver(item)
                        if item_tuple.triplet == new_tuple.triplet:
                            # Same X.Y.Z -> purge older revision directory
                            uri.rmtree(sub_uri)
                    except Exception:
                        pass

        # 2. Gather active release versions
        versions: List[str] = []
        for item in uri.listdir(mod_rel_root):
            sub_uri = f"{mod_rel_root}/{item}"
            if uri.is_dir(sub_uri) and uri.exists(f"{sub_uri}/manifest.json"):
                versions.append(item)
                
        versions.sort(key=functools.cmp_to_key(semver.compare_semver))
        index_data = {
            "name": name,
            "description": description or f"YS-Codebase module {name}",
            "versions": versions
        }
        uri.write_json(f"{mod_rel_root}/index.json", index_data, indent=2)

    def build_module(self, name: str, clean: bool = True) -> Tuple[bool, str]:
        """
        本地完整打包 (dev build):
        - 100% 保留 tests/ 與開發檔案。
        - 產物版本號強制標記為 X.Y.Z.build。
        - 清理舊 *.build 目錄保持單一最新產物。
        - 自動更新 build/{name}/index.json。
        """
        src_uri = f"module.source.root://{name}"
        if not uri.exists(src_uri):
            return False, f"Source module not found at {src_uri}."
        
        # 1. Run compliance check
        passed, errors = self.checker.check_module(name)
        if not passed:
            err_msg = "\n  - ".join(errors)
            return False, f"Check failed for module '{name}':\n  - {err_msg}"
        
        manifest_data = uri.read_json(f"{src_uri}/manifest.json")
        raw_version = manifest_data.get("version", "1.0.0.0")
        v_tuple = semver.parse_semver(raw_version)
        build_version = f"{v_tuple.major}.{v_tuple.minor}.{v_tuple.patch}.build"
        
        mod_build_root = f"module.build.root://{name}"
        target_build_uri = f"{mod_build_root}/{build_version}"
        
        # 2. Clean previous *.build directories in module.build.root://{name}
        if uri.exists(mod_build_root):
            for item in list(uri.listdir(mod_build_root)):
                sub = f"{mod_build_root}/{item}"
                if uri.is_dir(sub) and item.endswith(".build"):
                    uri.rmtree(sub)
        uri.makedirs(target_build_uri)
        
        ignores = DEV_BUILD_IGNORES
        src_real = uri.resolve(src_uri)
        build_real = uri.resolve(target_build_uri)
        
        copied_count = 0
        for root, dirs, files in os.walk(src_real):
            rel_dir = os.path.relpath(root, src_real).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            
            dirs[:] = [d for d in dirs if not self._should_ignore(f"{rel_dir}/{d}".lstrip("/"), ignores)]
            
            for f in files:
                rel_file = f"{rel_dir}/{f}".lstrip("/")
                if not self._should_ignore(rel_file, ignores):
                    src_file_path = os.path.join(root, f)
                    dst_file_path = os.path.join(build_real, os.path.normpath(rel_file))
                    os.makedirs(os.path.dirname(dst_file_path), exist_ok=True)
                    shutil.copy2(src_file_path, dst_file_path)
                    copied_count += 1
                    
        # 3. Override manifest version in build output to X.Y.Z.build
        out_manifest_path = os.path.join(build_real, "manifest.json")
        if os.path.isfile(out_manifest_path):
            with open(out_manifest_path, "r", encoding="utf-8") as f:
                out_mdata = json.load(f)
            out_mdata["version"] = build_version
            with open(out_manifest_path, "w", encoding="utf-8") as f:
                json.dump(out_mdata, f, indent=2, ensure_ascii=False)
                
        # 4. Automatically update build/index.json
        self._update_build_index(name, description=manifest_data.get("description", ""))
        
        return True, f"Successfully built dev package '{name}@{build_version}' ({copied_count} files) to {target_build_uri}."

    def package_release(self, name: str, target_version: str) -> Tuple[bool, str]:
        """
        純淨發布打包 (dev release packager):
        - 嚴格依 .yscbignore 與 RELEASE_IGNORES 排除 tests/ 與開發檔案。
        - 寫入 release/{name}/{target_version}/。
        - 更新 release/{name}/index.json 並執行同 X.Y.Z 淘汰清理。
        """
        src_uri = f"module.source.root://{name}"
        if not uri.exists(src_uri):
            return False, f"Source module not found at {src_uri}."
            
        manifest_data = uri.read_json(f"{src_uri}/manifest.json")
        target_rel_uri = f"release.root://{name}/{target_version}"
        
        if uri.exists(target_rel_uri):
            uri.rmtree(target_rel_uri)
        uri.makedirs(target_rel_uri)
        
        ignores = self._load_module_ignores(src_uri, RELEASE_IGNORES)
        src_real = uri.resolve(src_uri)
        rel_real = uri.resolve(target_rel_uri)
        
        copied_count = 0
        for root, dirs, files in os.walk(src_real):
            rel_dir = os.path.relpath(root, src_real).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            
            dirs[:] = [d for d in dirs if not self._should_ignore(f"{rel_dir}/{d}".lstrip("/"), ignores)]
            
            for f in files:
                rel_file = f"{rel_dir}/{f}".lstrip("/")
                if not self._should_ignore(rel_file, ignores):
                    src_file_path = os.path.join(root, f)
                    dst_file_path = os.path.join(rel_real, os.path.normpath(rel_file))
                    os.makedirs(os.path.dirname(dst_file_path), exist_ok=True)
                    shutil.copy2(src_file_path, dst_file_path)
                    copied_count += 1
                    
        # Override manifest version in release output
        out_manifest_path = os.path.join(rel_real, "manifest.json")
        if os.path.isfile(out_manifest_path):
            with open(out_manifest_path, "r", encoding="utf-8") as f:
                out_mdata = json.load(f)
            out_mdata["version"] = target_version
            with open(out_manifest_path, "w", encoding="utf-8") as f:
                json.dump(out_mdata, f, indent=2, ensure_ascii=False)
                
        # Update release/index.json with revision purging
        self._update_release_index(name, description=manifest_data.get("description", ""), new_version=target_version)
        
        return True, f"Successfully packaged release '{name}@{target_version}' ({copied_count} files)."

    def build_all(self, clean: bool = True) -> Dict[str, Tuple[bool, str]]:
        results = {}
        src_root_uri = "module.source.root://"
        if not uri.exists(src_root_uri):
            return results
        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source.root://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.build_module(item, clean=clean)
        return results
