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
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple, Generator

# Import ExecutionContext from SSOT context.py
from core.context import ExecutionContext

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

def set_module_context(module_name: Optional[str]) -> None:
    global _active_module_context
    _active_module_context = module_name

def get_module_context() -> Optional[str]:
    return _active_module_context

@contextmanager
def module_scope(module_name: Optional[str]) -> Generator[None, None, None]:
    """
    模組上下文安全作用域 (Context Manager)：
    退出區塊時以 finally 100% 保證還原舊全域 _active_module_context，防止測試與 Hook 污染。
    """
    old = get_module_context()
    set_module_context(module_name)
    try:
        yield
    finally:
        set_module_context(old)

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

@contextmanager
def host_scope(host_dir: Optional[str]) -> Generator[None, None, None]:
    """
    宿主目錄安全作用域 (Context Manager)：
    退出區塊時以 finally 100% 保證還原舊全域 _active_host_dir。
    """
    old = get_host_dir()
    set_host_dir(host_dir)
    try:
        yield
    finally:
        set_host_dir(old)

def _get_yscb_root() -> str:
    """
    Constant self-locating: computes yscb_root from __file__ location (up 3 levels).
    Runtime: <yscb_root>/modules/core/core/uri.py -> <yscb_root>
    Source:  <yscb_root>/source/core/core/uri.py  -> <yscb_root>
    
    Under YSCB microkernel dispatch invariants, the code can only be invoked if yscb.py
    has located core. Therefore, __file__ up 3 levels strictly equals yscb_root (zero I/O fast-path).
    """
    curr = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))

def _get_host_config(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    獲取宿主目錄與工具庫根目錄 (Physical Topology Invariant Guarantee).
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
            
    raise FileNotFoundError(
        f"Cannot locate '{CONFIG_FILENAME}'. Checked candidate locations: {candidate_hosts}. "
        "YS-Codebase requires a valid yscb.config.json to operate."
    )

# Backward-compatibility alias
_find_host_config = _get_host_config

def _get_project_dir(host_dir: str, yscb_dir: str) -> Optional[str]:
    """
    Resolves project root directory from config://config.project.json (core module).
    """
    proj_cfg_path = os.path.join(yscb_dir, "config", "core", "config.project.json")
    if os.path.isfile(proj_cfg_path):
        try:
            with open(proj_cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rel_proj = data.get("project_root")
            if rel_proj:
                if rel_proj.startswith("!undefined"):
                    return None
                if os.path.isabs(rel_proj):
                    return os.path.normpath(rel_proj)
                return os.path.normpath(os.path.join(host_dir, rel_proj))
        except Exception:
            pass
    return None

def _get_merged_uri_schemes(yscb_dir: str) -> List[Dict[str, Any]]:
    """
    Reads contributed URI schemes from merged cache.
    """
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
        host_dir, _ = _get_host_config()
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
                host_dir, _ = _get_host_config()
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
        
    # Zero Speculation: Disallow ambiguous non-URI relative strings
    raise ValueError(
        f"Invalid semantic URI format: '{uri}'. "
        "Path must be a registered semantic URI ('scheme://...') or an absolute OS path."
    )

def to_uri(abs_path: str, current_module: Optional[str] = None) -> str:
    norm = os.path.normpath(os.path.abspath(abs_path))
    yscb_dir = _get_yscb_root()
    mod = current_module or _active_module_context or "core"
    
    proj_dir = None
    try:
        host_dir, _ = _get_host_config()
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

# --- First-Class VFS IO Helpers ---

def exists(uri: str) -> bool:
    try:
        p = resolve(uri)
        return os.path.exists(p)
    except Exception:
        return False

def isfile(uri: str) -> bool:
    try:
        p = resolve(uri)
        return os.path.isfile(p)
    except Exception:
        return False

is_file = isfile

def isdir(uri: str) -> bool:
    try:
        p = resolve(uri)
        return os.path.isdir(p)
    except Exception:
        return False

is_dir = isdir

def remove(uri_str: str) -> None:
    try:
        p = resolve(uri_str)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def read_text(uri: str, encoding: str = "utf-8") -> str:
    p = resolve(uri)
    with open(p, "r", encoding=encoding) as f:
        return f.read()

def write_text(uri: str, content: str, encoding: str = "utf-8") -> None:
    p = resolve(uri)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=encoding) as f:
        f.write(content)

def read_json(uri: str, encoding: str = "utf-8") -> Any:
    p = resolve(uri)
    with open(p, "r", encoding=encoding) as f:
        return json.load(f)

def write_json(uri: str, data: Any, indent: int = 2, encoding: str = "utf-8") -> None:
    p = resolve(uri)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=encoding) as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def makedirs(uri: str, exist_ok: bool = True) -> None:
    p = resolve(uri)
    os.makedirs(p, exist_ok=exist_ok)

def listdir(uri: str) -> List[str]:
    p = resolve(uri)
    return os.listdir(p)

def copy(src_uri: str, dst_uri: str) -> None:
    src_p = resolve(src_uri)
    dst_p = resolve(dst_uri)
    if os.path.isdir(src_p):
        if os.path.exists(dst_p):
            shutil.rmtree(dst_p)
        shutil.copytree(src_p, dst_p)
    else:
        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
        shutil.copy2(src_p, dst_p)

def rmtree(uri: str) -> None:
    p = resolve(uri)
    if os.path.exists(p):
        shutil.rmtree(p)
