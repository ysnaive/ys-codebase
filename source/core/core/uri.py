"""
YS-Codebase Semantic URI Protocol & First-Class VFS SDK.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import sys
import json
import shutil
from typing import Optional, List, Dict, Any, Tuple

CONFIG_FILENAME = "yscb.config.json"
_active_module_context: Optional[str] = None

def set_module_context(module_name: Optional[str]) -> None:
    global _active_module_context
    _active_module_context = module_name

def get_module_context() -> Optional[str]:
    return _active_module_context

def _find_host_config(start_dir: Optional[str] = None) -> Tuple[str, str]:
    curr = os.path.abspath(start_dir or os.getcwd())
    while True:
        cfg_path = os.path.join(curr, CONFIG_FILENAME)
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                project_dir = curr
                yscb_rel = data.get("yscb_root", "./ys_codebase")
                yscb_dir = os.path.normpath(os.path.join(project_dir, yscb_rel))
                return project_dir, yscb_dir
            except Exception:
                pass
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    
    # Fallback to current working directory
    proj = os.path.abspath(os.getcwd())
    return proj, os.path.join(proj, "ys_codebase")

def resolve(uri: str, current_module: Optional[str] = None) -> str:
    if not isinstance(uri, str):
        raise TypeError(f"URI must be a string, got {type(uri)}")
    
    # Pass-through absolute OS paths
    if os.path.isabs(uri) or (len(uri) > 1 and uri[1] == ":"):
        return os.path.normpath(uri)
    
    project_dir, yscb_dir = _find_host_config()
    mod = current_module or _active_module_context or "core"
    
    # Protocols table
    protocols = [
        ("project://", project_dir),
        ("yscb://", yscb_dir),
        ("mirror://", os.path.join(yscb_dir, ".mirror")),
        ("temp://", os.path.join(yscb_dir, ".temp")),
        ("snapshot://", os.path.join(yscb_dir, ".snapshots")),
        ("module.root://", os.path.join(yscb_dir, "modules")),
        ("module://", os.path.join(yscb_dir, "modules", "{module}")),
        ("config.root://", os.path.join(yscb_dir, ".config")),
        ("config://", os.path.join(yscb_dir, ".config", "{module}")),
        ("cache.root://", os.path.join(yscb_dir, ".cache")),
        ("cache://", os.path.join(yscb_dir, ".cache", "{module}")),
        ("module.source.root://", os.path.join(yscb_dir, "source")),
        ("module.source://", os.path.join(yscb_dir, "source", "{module}")),
        ("module.build.root://", os.path.join(yscb_dir, "build")),
        ("module.build://", os.path.join(yscb_dir, "build", "{module}")),
    ]
    
    for prefix, base_path in protocols:
        if uri.startswith(prefix):
            rel = uri[len(prefix):].lstrip("/\\")
            target = base_path.replace("{module}", mod)
            if "{module}" in base_path and not mod:
                raise ValueError(f"Cannot resolve placeholder {{module}} in '{uri}' without active module context.")
            if rel:
                target = os.path.join(target, rel.replace("{module}", mod))
            return os.path.normpath(target)
            
    if "://" in uri:
        scheme = uri.split("://", 1)[0] + "://"
        raise ValueError(f"Unsupported URI scheme: {scheme}")
        
    return os.path.normpath(os.path.join(project_dir, uri))

def to_uri(abs_path: str, current_module: Optional[str] = None) -> str:
    norm = os.path.normpath(os.path.abspath(abs_path))
    project_dir, yscb_dir = _find_host_config()
    mod = current_module or _active_module_context or "core"
    
    check_order = [
        (os.path.join(yscb_dir, "modules", mod), "module://"),
        (os.path.join(yscb_dir, "modules"), "module.root://"),
        (os.path.join(yscb_dir, ".mirror"), "mirror://"),
        (os.path.join(yscb_dir, ".temp"), "temp://"),
        (os.path.join(yscb_dir, ".snapshots"), "snapshot://"),
        (os.path.join(yscb_dir, ".config", mod), "config://"),
        (os.path.join(yscb_dir, ".config"), "config.root://"),
        (os.path.join(yscb_dir, ".cache", mod), "cache://"),
        (os.path.join(yscb_dir, ".cache"), "cache.root://"),
        (os.path.join(yscb_dir, "source", mod), "module.source://"),
        (os.path.join(yscb_dir, "source"), "module.source.root://"),
        (os.path.join(yscb_dir, "build", mod), "module.build://"),
        (os.path.join(yscb_dir, "build"), "module.build.root://"),
        (yscb_dir, "yscb://"),
        (project_dir, "project://"),
    ]
    
    for base_p, prefix in check_order:
        base_norm = os.path.normpath(base_p)
        if norm == base_norm:
            return prefix
        if norm.startswith(base_norm + os.sep):
            sub = norm[len(base_norm) + 1:].replace("\\", "/")
            return prefix + sub
            
    return norm.replace("\\", "/")

# ── VFS Read/Write Operations ──────────────────────────────────

def read_text(uri: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> str:
    path = resolve(uri, current_module)
    with open(path, "r", encoding=encoding) as f:
        return f.read()

def write_text(uri: str, content: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> None:
    path = resolve(uri, current_module)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding=encoding) as f:
        f.write(content)
    os.replace(tmp_path, path)

def read_json(uri: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> Any:
    return json.loads(read_text(uri, encoding=encoding, current_module=current_module))

def write_json(uri: str, data: Any, indent: int = 2, encoding: str = "utf-8", current_module: Optional[str] = None) -> None:
    text = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    write_text(uri, text, encoding=encoding, current_module=current_module)

def read_bytes(uri: str, current_module: Optional[str] = None) -> bytes:
    path = resolve(uri, current_module)
    with open(path, "rb") as f:
        return f.read()

def write_bytes(uri: str, data: bytes, current_module: Optional[str] = None) -> None:
    path = resolve(uri, current_module)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, path)

def exists(uri: str, current_module: Optional[str] = None) -> bool:
    return os.path.exists(resolve(uri, current_module))

def is_file(uri: str, current_module: Optional[str] = None) -> bool:
    return os.path.isfile(resolve(uri, current_module))

def is_dir(uri: str, current_module: Optional[str] = None) -> bool:
    return os.path.isdir(resolve(uri, current_module))

def makedirs(uri: str, exist_ok: bool = True, current_module: Optional[str] = None) -> None:
    os.makedirs(resolve(uri, current_module), exist_ok=exist_ok)

def remove(uri: str, current_module: Optional[str] = None) -> None:
    path = resolve(uri, current_module)
    if os.path.isfile(path):
        os.remove(path)

def rmtree(uri: str, ignore_errors: bool = False, current_module: Optional[str] = None) -> None:
    path = resolve(uri, current_module)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=ignore_errors)

def listdir(uri: str, current_module: Optional[str] = None) -> List[str]:
    path = resolve(uri, current_module)
    if os.path.isdir(path):
        return os.listdir(path)
    return []

def copy(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    src_p = resolve(src_uri, current_module)
    dst_p = resolve(dst_uri, current_module)
    if os.path.isdir(src_p):
        if os.path.exists(dst_p):
            shutil.rmtree(dst_p)
        shutil.copytree(src_p, dst_p)
    elif os.path.isfile(src_p):
        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
        shutil.copy2(src_p, dst_p)

def move(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    src_p = resolve(src_uri, current_module)
    dst_p = resolve(dst_uri, current_module)
    os.makedirs(os.path.dirname(dst_p), exist_ok=True)
    shutil.move(src_p, dst_p)
