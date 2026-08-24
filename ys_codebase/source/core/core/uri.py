"""
YS-Codebase Semantic URI Protocol & First-Class VFS SDK.
100% Python Standard Library, Zero Third-Party Dependency.
Dynamically resolves contributed URI schemes from contributes.merged.json with self-injection architecture.
"""

import os
import sys
import json
import shutil
import importlib.util
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

CONFIG_FILENAME = "yscb.config.json"
_active_module_context: Optional[str] = None
_active_host_dir: Optional[str] = None

# Bootstrap fallback schemes used strictly during initial bootstrap before contributes injection
_BOOTSTRAP_FALLBACK_SCHEMES: List[Dict[str, Any]] = [
    {"token": "mirror", "type": "const", "value": "yscb://.mirror/"},
    {"token": "temp", "type": "const", "value": "yscb://.temp/"},
    {"token": "snapshot", "type": "const", "value": "yscb://.snapshots/"},
    {"token": "module.root", "type": "const", "value": "yscb://modules/"},
    {"token": "module", "type": "const", "value": "yscb://modules/{module}/"},
    {"token": "config.root", "type": "const", "value": "yscb://config/"},
    {"token": "config", "type": "const", "value": "yscb://config/{module}/"},
    {"token": "cache.root", "type": "const", "value": "yscb://.cache/"},
    {"token": "cache", "type": "const", "value": "yscb://.cache/{module}/"},
    {"token": "module.source.root", "type": "const", "value": "yscb://source/"},
    {"token": "module.source", "type": "const", "value": "yscb://source/{module}/"},
    {"token": "module.build.root", "type": "const", "value": "yscb://build/"},
    {"token": "module.build", "type": "const", "value": "yscb://build/{module}/"},
]

@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface)"""
    module_name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

def set_module_context(module_name: Optional[str]) -> None:
    global _active_module_context
    _active_module_context = module_name

def get_module_context() -> Optional[str]:
    return _active_module_context

def set_host_dir(host_dir: Optional[str]) -> None:
    """Explicitly inject host directory."""
    global _active_host_dir
    _active_host_dir = os.path.normpath(os.path.abspath(host_dir)) if host_dir else None

def get_host_dir() -> Optional[str]:
    """Get active host directory from memory context or YSCB_HOST_DIR environment variable."""
    if _active_host_dir:
        return _active_host_dir
    env_dir = os.environ.get("YSCB_HOST_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.normpath(os.path.abspath(env_dir))
    return None

def _get_yscb_root() -> str:
    """
    Constant self-locating: computes yscb_root from __file__ location (up 3 levels).
    Runtime: <yscb_root>/modules/core/core/uri.py -> <yscb_root>
    Source:  <yscb_root>/source/core/core/uri.py  -> <yscb_root>
    """
    curr = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))

def _find_host_config(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    Locates host directory and yscb_root deterministically.
    1. If start_dir is given, checks start_dir strictly.
    2. Uses get_host_dir() if injected.
    3. Falls back to parent of yscb_root or yscb_root if yscb.config.json exists.
    4. Raises FileNotFoundError if yscb.config.json does not exist. (Zero Speculation)
    """
    yscb_dir = _get_yscb_root()
    if start_dir:
        s_abs = os.path.normpath(os.path.abspath(start_dir))
        cfg_path = os.path.join(s_abs, CONFIG_FILENAME)
        if os.path.isfile(cfg_path):
            return s_abs, yscb_dir
        raise FileNotFoundError(f"'{CONFIG_FILENAME}' not found at specified start_dir '{s_abs}'.")
        
    injected_host = get_host_dir()
    candidate_hosts: List[str] = []
    if injected_host:
        candidate_hosts.append(injected_host)
    candidate_hosts.append(os.path.normpath(os.path.dirname(yscb_dir)))
    candidate_hosts.append(yscb_dir)
    
    for h_dir in candidate_hosts:
        cfg_path = os.path.join(h_dir, CONFIG_FILENAME)
        if os.path.isfile(cfg_path):
            return h_dir, yscb_dir
            
    # Zero Speculation: Raise explicit error
    raise FileNotFoundError(
        f"'{CONFIG_FILENAME}' not found in candidate host directories: {candidate_hosts}. "
        "Please initialize environment with 'python yscb.py init <yscbRoot>' first."
    )

def _get_project_dir(host_dir: str, yscb_dir: str) -> Optional[str]:
    """Reads project_root explicitly from config/core/config.project.json. No fallback allowed."""
    core_cfg_path = os.path.join(yscb_dir, "config", "core", "config.project.json")
    if os.path.isfile(core_cfg_path):
        try:
            with open(core_cfg_path, "r", encoding="utf-8") as f:
                cfg_data = json.load(f)
            p_root = cfg_data.get("project_root")
            if p_root is not None and isinstance(p_root, str):
                p_clean = p_root.strip()
                if p_clean and p_clean != "!undefined":
                    if os.path.isabs(p_clean):
                        return os.path.normpath(p_clean)
                    return os.path.normpath(os.path.join(host_dir, p_clean))
        except Exception:
            pass
    return None

def _get_merged_uri_schemes(yscb_dir: str) -> List[Dict[str, Any]]:
    """Loads all dynamically registered URI schemes from .cache/core/contributes.merged.json."""
    merged_cfg = os.path.join(yscb_dir, ".cache", "core", "contributes.merged.json")
    if os.path.isfile(merged_cfg):
        try:
            with open(merged_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            schemes = data.get("uri_schemes", [])
            if isinstance(schemes, list) and len(schemes) > 0:
                return schemes
        except Exception:
            pass
    return _BOOTSTRAP_FALLBACK_SCHEMES

def resolve(
    uri: str, 
    current_module: Optional[str] = None, 
    context: Optional[ExecutionContext] = None
) -> str:
    """
    解析語意 URI 為實體絕對路徑。
    
    :param uri: 語意 URI 字串 (例 "project://AGENTS.md", "config://config.project.json")
    :param current_module: 指定當前模組名稱
    :param context: 執行期上下文 (供動態佔位符解算)
    :return: 實體作業系統路徑
    """
    if not isinstance(uri, str):
        raise TypeError(f"URI must be a string, got {type(uri)}")
    
    # Pass-through absolute OS paths
    if os.path.isabs(uri) or (len(uri) > 1 and uri[1] == ":"):
        return os.path.normpath(uri)
    
    yscb_dir = _get_yscb_root()
    mod = current_module or _active_module_context or "core"
    
    # Fast-path for root anchor protocol yscb:// (No need to read host config)
    if uri.startswith("yscb://"):
        rel = uri[len("yscb://"):].lstrip("/\\")
        return os.path.normpath(os.path.join(yscb_dir, rel)) if rel else yscb_dir

    # 1. Check project:// with strict explicit configuration rule (Zero Speculation / No Fallback)
    if uri.startswith("project://"):
        host_dir, _ = _find_host_config()
        proj_dir = _get_project_dir(host_dir, yscb_dir)
        if proj_dir is None:
            raise ValueError("'project://' is undefined. Please configure 'project_root' in config://config.project.json (core)")
        rel = uri[len("project://"):].lstrip("/\\")
        return os.path.normpath(os.path.join(proj_dir, rel)) if rel else proj_dir

    # 2. Dynamic contributed protocols lookup
    if "://" in uri:
        scheme_token, rel = uri.split("://", 1)
        rel = rel.lstrip("/\\")
        
        all_schemes = _get_merged_uri_schemes(yscb_dir)
        # Also check bootstrap fallback if not in merged
        token_map = {s.get("token"): s for s in all_schemes if isinstance(s, dict) and "token" in s}
        for fb in _BOOTSTRAP_FALLBACK_SCHEMES:
            if fb["token"] not in token_map:
                token_map[fb["token"]] = fb
                
        if scheme_token in token_map:
            scheme = token_map[scheme_token]
            stype = scheme.get("type", "const")
            sval = scheme.get("value", "")
            
            if stype == "const":
                val_expanded = sval.replace("{module}", mod).replace("{yscb_root}", yscb_dir)
                if "{module}" in sval and not mod:
                    raise ValueError(f"Cannot resolve placeholder {{module}} in '{uri}' without active module context.")
                target_base = resolve(val_expanded, current_module=mod, context=context)
                if rel:
                    rel_expanded = rel.replace("{module}", mod)
                    return os.path.normpath(os.path.join(target_base, rel_expanded))
                return os.path.normpath(target_base)
            elif stype == "config":
                host_dir, _ = _find_host_config()
                mod_proj_cfg = os.path.join(yscb_dir, "config", mod, "config.project.json")
                if not os.path.isfile(mod_proj_cfg):
                    mod_proj_cfg = os.path.join(yscb_dir, "config", "core", "config.project.json")
                if os.path.isfile(mod_proj_cfg):
                    try:
                        with open(mod_proj_cfg, "r", encoding="utf-8") as pf:
                            pcfg = json.load(pf)
                        keys = sval.split(".")
                        curr_val = pcfg
                        for k in keys:
                            if isinstance(curr_val, dict):
                                curr_val = curr_val.get(k)
                            else:
                                curr_val = None
                                break
                        if curr_val:
                            proj_d = _get_project_dir(host_dir, yscb_dir)
                            base_p = proj_d or host_dir
                            target_base = os.path.normpath(os.path.join(base_p, str(curr_val)))
                            return os.path.normpath(os.path.join(target_base, rel)) if rel else target_base
                    except Exception:
                        pass
                raise ValueError(f"Cannot resolve config URI '{uri}': key '{sval}' not found in configuration.")

        raise ValueError(f"Unsupported URI scheme: {scheme_token}://")
        
    try:
        host_dir, _ = _find_host_config()
        proj_d = _get_project_dir(host_dir, yscb_dir)
        return os.path.normpath(os.path.join(proj_d or host_dir, uri))
    except Exception:
        return os.path.normpath(os.path.join(yscb_dir, uri))

def to_uri(abs_path: str, current_module: Optional[str] = None) -> str:
    norm = os.path.normpath(os.path.abspath(abs_path))
    yscb_dir = _get_yscb_root()
    mod = current_module or _active_module_context or "core"
    
    proj_dir = None
    try:
        host_dir, _ = _find_host_config()
        proj_dir = _get_project_dir(host_dir, yscb_dir)
    except Exception:
        pass
    
    # Dynamically build resolution list from contributed schemes
    all_schemes = _get_merged_uri_schemes(yscb_dir)
    token_map = {s.get("token"): s for s in all_schemes if isinstance(s, dict) and "token" in s}
    for fb in _BOOTSTRAP_FALLBACK_SCHEMES:
        if fb["token"] not in token_map:
            token_map[fb["token"]] = fb
            
    check_order: List[Tuple[str, str]] = []
    for token, scheme in token_map.items():
        if scheme.get("type") == "const":
            try:
                base_p = resolve(f"{token}://", current_module=mod)
                check_order.append((base_p, f"{token}://"))
            except Exception:
                pass
                
    check_order.append((yscb_dir, "yscb://"))
    if proj_dir:
        check_order.append((proj_dir, "project://"))
    
    # Sort by descending length of base path to match most specific URI prefix first
    check_order.sort(key=lambda x: len(os.path.normpath(x[0])), reverse=True)
    
    for base_p, prefix in check_order:
        base_norm = os.path.normpath(base_p)
        if norm == base_norm:
            return prefix
        if norm.startswith(base_norm + os.sep):
            sub = norm[len(base_norm) + 1:].replace("\\", "/")
            return prefix + sub
            
    return norm

# --- First-Class VFS SDK Operations ---

def read_text(path_or_uri: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> str:
    real_path = resolve(path_or_uri, current_module=current_module)
    with open(real_path, "r", encoding=encoding) as f:
        return f.read()

def write_text(path_or_uri: str, content: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> None:
    real_path = resolve(path_or_uri, current_module=current_module)
    os.makedirs(os.path.dirname(real_path), exist_ok=True)
    tmp_path = f"{real_path}.tmp_{os.getpid()}"
    with open(tmp_path, "w", encoding=encoding) as f:
        f.write(content)
    if os.path.exists(real_path):
        os.remove(real_path)
    os.rename(tmp_path, real_path)

def read_json(path_or_uri: str, encoding: str = "utf-8", current_module: Optional[str] = None) -> Any:
    real_path = resolve(path_or_uri, current_module=current_module)
    with open(real_path, "r", encoding=encoding) as f:
        return json.load(f)

def write_json(path_or_uri: str, data: Any, indent: int = 2, encoding: str = "utf-8", current_module: Optional[str] = None) -> None:
    content = json.dumps(data, indent=indent, ensure_ascii=False)
    write_text(path_or_uri, content, encoding=encoding, current_module=current_module)

def read_bytes(path_or_uri: str, current_module: Optional[str] = None) -> bytes:
    real_path = resolve(path_or_uri, current_module=current_module)
    with open(real_path, "rb") as f:
        return f.read()

def write_bytes(path_or_uri: str, data: bytes, current_module: Optional[str] = None) -> None:
    real_path = resolve(path_or_uri, current_module=current_module)
    os.makedirs(os.path.dirname(real_path), exist_ok=True)
    tmp_path = f"{real_path}.tmp_{os.getpid()}"
    with open(tmp_path, "wb") as f:
        f.write(data)
    if os.path.exists(real_path):
        os.remove(real_path)
    os.rename(tmp_path, real_path)

def exists(path_or_uri: str, current_module: Optional[str] = None) -> bool:
    try:
        real_path = resolve(path_or_uri, current_module=current_module)
        return os.path.exists(real_path)
    except Exception:
        return False

def is_file(path_or_uri: str, current_module: Optional[str] = None) -> bool:
    try:
        real_path = resolve(path_or_uri, current_module=current_module)
        return os.path.isfile(real_path)
    except Exception:
        return False

def is_dir(path_or_uri: str, current_module: Optional[str] = None) -> bool:
    try:
        real_path = resolve(path_or_uri, current_module=current_module)
        return os.path.isdir(real_path)
    except Exception:
        return False

def makedirs(path_or_uri: str, exist_ok: bool = True, current_module: Optional[str] = None) -> None:
    real_path = resolve(path_or_uri, current_module=current_module)
    os.makedirs(real_path, exist_ok=exist_ok)

def remove(path_or_uri: str, current_module: Optional[str] = None) -> None:
    real_path = resolve(path_or_uri, current_module=current_module)
    if os.path.isfile(real_path) or os.path.islink(real_path):
        os.remove(real_path)

def rmtree(path_or_uri: str, ignore_errors: bool = False, current_module: Optional[str] = None) -> None:
    real_path = resolve(path_or_uri, current_module=current_module)
    if os.path.exists(real_path):
        shutil.rmtree(real_path, ignore_errors=ignore_errors)

def listdir(path_or_uri: str, current_module: Optional[str] = None) -> List[str]:
    real_path = resolve(path_or_uri, current_module=current_module)
    if os.path.isdir(real_path):
        return os.listdir(real_path)
    return []

def copy(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    src_p = resolve(src_uri, current_module=current_module)
    dst_p = resolve(dst_uri, current_module=current_module)
    if os.path.isdir(src_p):
        shutil.copytree(src_p, dst_p, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
        shutil.copy2(src_p, dst_p)

def move(src_uri: str, dst_uri: str, current_module: Optional[str] = None) -> None:
    src_p = resolve(src_uri, current_module=current_module)
    dst_p = resolve(dst_uri, current_module=current_module)
    os.makedirs(os.path.dirname(dst_p), exist_ok=True)
    shutil.move(src_p, dst_p)
