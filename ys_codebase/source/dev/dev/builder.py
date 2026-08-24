"""
Clean Builder implementation for YS-Codebase modules.
"""
import os
import fnmatch
import shutil
from typing import Tuple, Dict, List
from core import uri
from dev.checker import Checker

GLOBAL_IGNORES = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".git*",
    ".pytest_cache",
    ".DS_Store",
    ".yscbignore"
]

class Builder:
    def __init__(self):
        self.checker = Checker()

    def _load_module_ignores(self, src_uri: str) -> List[str]:
        ignore_file_uri = f"{src_uri}/.yscbignore"
        ignores = list(GLOBAL_IGNORES)
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

    def build_module(self, name: str, clean: bool = False) -> Tuple[bool, str]:
        src_uri = f"module.source.root://{name}"
        
        if not uri.exists(src_uri):
            return False, f"Source module not found at {src_uri}."
        
        # 1. Run compliance check first
        passed, errors = self.checker.check_module(name)
        if not passed:
            err_msg = "\n  - ".join(errors)
            return False, f"Check failed for module '{name}':\n  - {err_msg}"
        
        manifest_data = uri.read_json(f"{src_uri}/manifest.json")
        version = manifest_data.get("version", "1.0.0")
        build_uri = f"module.build.root://{name}/{version}"
        
        # 2. Prepare build directory
        if clean and uri.exists(build_uri):
            uri.rmtree(build_uri)
        uri.makedirs(build_uri)
        
        ignores = self._load_module_ignores(src_uri)
        src_real = uri.resolve(src_uri)
        build_real = uri.resolve(build_uri)
        
        copied_count = 0
        for root, dirs, files in os.walk(src_real):
            rel_dir = os.path.relpath(root, src_real).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            
            # Filter subdirs in-place so os.walk doesn't descend into ignored dirs
            dirs[:] = [d for d in dirs if not self._should_ignore(f"{rel_dir}/{d}".lstrip("/"), ignores)]
            
            for f in files:
                rel_file = f"{rel_dir}/{f}".lstrip("/")
                if not self._should_ignore(rel_file, ignores):
                    src_file_path = os.path.join(root, f)
                    dst_file_path = os.path.join(build_real, os.path.normpath(rel_file))
                    os.makedirs(os.path.dirname(dst_file_path), exist_ok=True)
                    shutil.copy2(src_file_path, dst_file_path)
                    copied_count += 1
                    
        return True, f"Successfully built '{name}' ({copied_count} files) to {build_uri}."

    def build_all(self, clean: bool = False) -> Dict[str, Tuple[bool, str]]:
        results = {}
        src_root_uri = "module.source.root://"
        if not uri.exists(src_root_uri):
            return results
        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source.root://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.build_module(item, clean=clean)
        return results
