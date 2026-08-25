"""
YS-Codebase Semantic URI Protocol & First-Class VFS SDK.
100% Python Standard Library, Zero Third-Party Dependency.
Dynamically resolves contributed URI schemes from contributes.merged.json with self-injection architecture
and provides JIT prompt & auto-reconciliation for !undefined configurations.
"""

import os
import sys
import json
import shutil
import importlib.util
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple, Generator, Set

# Import ExecutionContext from SSOT context.py
from core.context import ExecutionContext

CONFIG_FILENAME = "yscb.config.json"
_active_module_context: Optional[str] = None
_active_host_dir: Optional[str] = None
_reconciling_tokens: Set[str] = set()

# Bootstrap fallback schemes used strictly during initial bootstrap before contributes injection
_BOOTSTRAP_FALLBACK_SCHEMES: List[Dict[str, Any]] = [
    {"token": "yscb.host", "type": "const", "value": "{yscb_host}"},
    {"token": "module.mirror.root", "type": "const", "value": "yscb://.mirror/"},
    {"token": "module.mirror", "type": "const", "value": "yscb://.mirror/{module}/"},
    {"token": "temp", "type": "const", "value": "yscb://.temp/"},
    {"token": "snapshot", "type": "const", "value": "yscb://.snapshots/"},
    {"token": "module.root", "type": "const", "value": "yscb://modules/"},
    {"token": "module", "type": "const", "value": "yscb://modules/{module}/"},
    {"token": "config.root", "type": "const", "value": "yscb://config/"},
    {"token": "config", "type": "const", "value": "yscb://config/{module}/"},
    {"token": "cache.root", "type": "const", "value": "yscb://.cache/"},
    {"token": "cache", "type": "const", "value": "yscb://.cache/{module}/"},
    {"token": "storage.root", "type": "const", "value": "yscb://storage/"},
    {"token": "storage", "type": "const", "value": "yscb://storage/{module}/"},
    {"token": "module.source.root", "type": "const", "value": "yscb://source/"},
    {"token": "module.source", "type": "const", "value": "yscb://source/{module}/"},
    {"token": "module.build.root", "type": "const", "value": "yscb://build/"},
    {"token": "module.build", "type": "const", "value": "yscb://build/{module}/"},
    {"token": "module.release.root", "type": "const", "value": "yscb://release/"},
    {"token": "module.release", "type": "const", "value": "yscb://release/{module}/"},
]


class UndefinedURIError(ValueError):
    """當語意協議未設定 (!undefined) 且處於非互動環境或拒絕補齊時拋出之結構化異常。"""
    def __init__(self, scheme: str, provider: Optional[str] = None, binding: Optional[str] = None, message: Optional[str] = None):
        self.scheme = scheme
        self.provider = provider or "core"
        self.binding = binding or "unknown"
        default_msg = (
            f"Semantic URI '{scheme}://' is undefined (!undefined). "
            f"Provider: '{self.provider}', Config Binding: '{self.binding}'. "
            f"Please configure it in config://{self.provider}/config.project.json."
        )
        super().__init__(message or default_msg)


class CyclicURIDependencyError(ValueError):
    """當檢測到語意協議自引用或循環依賴時拋出。"""
    pass


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
    """
    curr = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))


def _get_host_config(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    獲取宿主目錄與工具庫根目錄 (Physical Topology Invariant Guarantee).
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
                if str(rel_proj).startswith("!undefined"):
                    return None
                if os.path.isabs(str(rel_proj)):
                    return os.path.normpath(str(rel_proj))
                return os.path.normpath(os.path.join(host_dir, str(rel_proj)))
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


def list_registered_schemes_summary() -> List[Dict[str, Any]]:
    """
    列出當前全系統已註冊之所有語意 URI 協議摘要清冊 (供 --help 展開與自省展示)。
    """
    yscb_dir = _get_yscb_root()
    all_schemes = _get_merged_uri_schemes(yscb_dir)
    token_map = {s.get("token"): dict(s) for s in all_schemes if isinstance(s, dict) and "token" in s}
    for fb in _BOOTSTRAP_FALLBACK_SCHEMES:
        if fb["token"] not in token_map:
            token_map[fb["token"]] = dict(fb)

    # 包含 project 協議
    token_map["project"] = {
        "token": "project",
        "type": "config",
        "value": "project_root",
        "description": "指向專案最頂層根目錄",
        "__provider__": "core"
    }

    results = []
    for token, scheme in token_map.items():
        try:
            res_p = resolve(f"{token}://", interactive=False)
        except Exception:
            res_p = "!undefined"
        results.append({
            "token": token,
            "type": scheme.get("type", "const"),
            "value": scheme.get("value", ""),
            "provider": scheme.get("__provider__", "core"),
            "resolved_path": res_p,
            "description": scheme.get("description", "")
        })
    return results


def reconcile_undefined_uri(
    scheme_token: str,
    raw_target: str,
    provider: Optional[str] = None,
    config_binding: Optional[str] = None,
    description: Optional[str] = None,
    interactive: bool = True
) -> str:
    """
    執行 !undefined 協議之 JIT 終端互動、輸入解析、寫回設定檔與熱重載。
    """
    global _reconciling_tokens
    if scheme_token in _reconciling_tokens:
        raise CyclicURIDependencyError(f"Cyclic or self-referencing URI dependency detected for '{scheme_token}://'")
    
    provider_name = provider or "core"
    binding_key = config_binding or ("project_root" if scheme_token == "project" else "unknown")
    desc = description or ("指向專案最頂層根目錄" if scheme_token == "project" else "")
    
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    if not interactive or not is_tty:
        raise UndefinedURIError(scheme=scheme_token, provider=provider_name, binding=binding_key)

    yscb_dir = _get_yscb_root()
    
    while True:
        print(f"\n[{provider_name}] 語意協議 '{scheme_token}://' 尚未設定 (當前為 !undefined)。")
        if desc:
            print(f"  • 說明: {desc}")
        print(f"  • 目標設定檔: config://{provider_name}/config.project.json ({binding_key})")
        print(f"  • 路徑基準: 相對路徑一律以 'yscb://' (工具庫根目錄) 為起始，支援 '../' 穿透或直接輸入語意協議格式 (例: project://plans)")
        print("\n是否進行及時熱更新補齊?")
        print("  -y <path> : 設定路徑、自動更新設定檔並繼續運行")
        print("  -n        : 終止當前操作")
        print("  --help    : 展開詳細協議資訊與全系統可用協議清單")
        
        try:
            ans = input("請輸入 [-y <path> / -n / --help]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n[{provider_name}] 操作已取消。")
            sys.exit(1)
            
        if ans == "-n":
            print(f"[{provider_name}] 協議 '{scheme_token}://' 未配置，已由使用者終止運行。")
            sys.exit(1)
        elif ans == "--help":
            print(f"\n==============================================================================================================")
            print(f"YS-Codebase 語意協議註冊清冊 (Registered URI Protocols Summary)")
            print(f"==============================================================================================================")
            print(f"{'TOKEN':<23} {'PROVIDER':<12} {'RAW TARGET / VALUE':<28} {'RESOLVED PATH / STATUS'}")
            print(f"--------------------------------------------------------------------------------------------------------------")
            for s in list_registered_schemes_summary():
                raw_v = s.get("value", "")
                print(f"{s['token'] + '://':<23} {s['provider']:<12} {raw_v:<28} {s['resolved_path']}")
            print(f"==============================================================================================================\n")
            continue
        elif ans.startswith("-y "):
            input_val = ans[3:].strip()
            if not input_val:
                print("錯誤: 請在 -y 後指定路徑 (例如: -y ./plans 或 -y project://plans)")
                continue
            
            # 解算輸入之路徑 (支援連鎖依賴)
            _reconciling_tokens.add(scheme_token)
            try:
                if "://" in input_val:
                    resolved_target = resolve(input_val, interactive=True)
                else:
                    if os.path.isabs(input_val) or (len(input_val) > 1 and input_val[1] == ":"):
                        resolved_target = os.path.normpath(input_val)
                    else:
                        resolved_target = os.path.normpath(os.path.join(yscb_dir, input_val))
            finally:
                _reconciling_tokens.discard(scheme_token)
            
            # 定位設定檔並寫入
            mod_proj_cfg = os.path.join(yscb_dir, "config", provider_name, "config.project.json")
            os.makedirs(os.path.dirname(mod_proj_cfg), exist_ok=True)
            cfg_data = {}
            if os.path.isfile(mod_proj_cfg):
                try:
                    with open(mod_proj_cfg, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                except Exception:
                    cfg_data = {}
            
            # 寫入鍵值 (支援巢狀 key 如 paths.plans_dir 或 project_root)
            keys = binding_key.split(".")
            curr = cfg_data
            for k in keys[:-1]:
                if k not in curr or not isinstance(curr[k], dict):
                    curr[k] = {}
                curr = curr[k]
            curr[keys[-1]] = input_val
            
            with open(mod_proj_cfg, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, indent=2, ensure_ascii=False)
            
            print(f"[{provider_name}] 已成功寫入設定檔: '{binding_key}' = '{input_val}'")
            
            # 若實體目錄不存在，自動建立
            if not os.path.exists(resolved_target):
                try:
                    os.makedirs(resolved_target, exist_ok=True)
                    print(f"[{provider_name}] 目錄不存在，已自動建立: {resolved_target}")
                except Exception:
                    pass
                    
            return resolved_target
        else:
            print("無效的輸入選項，請輸入 -y <path>、-n 或 --help。")


def resolve(
    uri: str, 
    current_module: Optional[str] = None, 
    context: Optional[ExecutionContext] = None,
    interactive: bool = True
) -> str:
    """
    解析語意 URI 為實體絕對路徑。
    
    :param uri: 語意 URI 字串 (例 "project://AGENTS.md", "config://config.project.json")
    :param current_module: 指定當前模組名稱
    :param context: 執行期上下文 (供動態佔位符解算)
    :param interactive: 當檢測到 !undefined 且為 TTY 時是否觸發 JIT 互動熱補齊 (預設 True)
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

    # Fast-path for host anchor protocol yscb.host:// (Force points to yscb.py/yscb.config.json directory)
    if uri.startswith("yscb.host://"):
        try:
            host_dir, _ = _get_host_config()
        except Exception:
            host_dir = get_host_dir() or os.path.normpath(os.path.dirname(yscb_dir))
        rel = uri[len("yscb.host://"):].lstrip("/\\")
        return os.path.normpath(os.path.join(host_dir, rel)) if rel else host_dir

    # 1. Check project:// with strict explicit configuration rule & JIT Hot-Reconciliation
    if uri.startswith("project://"):
        host_dir, _ = _get_host_config()
        proj_dir = _get_project_dir(host_dir, yscb_dir)
        if proj_dir is None:
            # 觸發 JIT 熱補齊
            proj_dir = reconcile_undefined_uri(
                scheme_token="project",
                raw_target="!undefined",
                provider="core",
                config_binding="project_root",
                description="指向專案最頂層根目錄",
                interactive=interactive
            )
        rel = uri[len("project://"):].lstrip("/\\")
        return os.path.normpath(os.path.join(proj_dir, rel)) if rel else proj_dir

    # 2. Dynamic contributed protocols lookup
    if "://" in uri:
        scheme_token, rel = uri.split("://", 1)
        rel = rel.lstrip("/\\")
        
        all_schemes = _get_merged_uri_schemes(yscb_dir)
        token_map = {s.get("token"): s for s in all_schemes if isinstance(s, dict) and "token" in s}
        for fb in _BOOTSTRAP_FALLBACK_SCHEMES:
            if fb["token"] not in token_map:
                token_map[fb["token"]] = fb
                
        if scheme_token in token_map:
            scheme = token_map[scheme_token]
            stype = scheme.get("type", "const")
            sval = scheme.get("value", "")
            provider_name = scheme.get("__provider__", mod)
            
            if stype == "const":
                try:
                    host_dir, _ = _get_host_config()
                except Exception:
                    host_dir = get_host_dir() or os.path.normpath(os.path.dirname(yscb_dir))
                val_expanded = sval.replace("{module}", mod).replace("{yscb_root}", yscb_dir).replace("{yscb_host}", host_dir or "")
                if "{module}" in sval and not mod:
                    raise ValueError(f"Cannot resolve placeholder {{module}} in '{uri}' without active module context.")
                target_base = resolve(val_expanded, current_module=mod, context=context, interactive=interactive)
                if rel:
                    rel_expanded = rel.replace("{module}", mod)
                    return os.path.normpath(os.path.join(target_base, rel_expanded))
                return os.path.normpath(target_base)
            elif stype == "config":
                host_dir, _ = _get_host_config()
                # 優先尋找 provider_name 的 config.project.json，其次 mod，最後 core
                cand_configs = [
                    os.path.join(yscb_dir, "config", provider_name, "config.project.json"),
                    os.path.join(yscb_dir, "config", mod, "config.project.json"),
                    os.path.join(yscb_dir, "config", "core", "config.project.json")
                ]
                curr_val = None
                found_cfg_file = None
                for mod_proj_cfg in cand_configs:
                    if os.path.isfile(mod_proj_cfg):
                        try:
                            with open(mod_proj_cfg, "r", encoding="utf-8") as pf:
                                pcfg = json.load(pf)
                            keys = sval.split(".")
                            c_temp = pcfg
                            for k in keys:
                                if isinstance(c_temp, dict):
                                    c_temp = c_temp.get(k)
                                else:
                                    c_temp = None
                                    break
                            if c_temp is not None:
                                curr_val = c_temp
                                found_cfg_file = mod_proj_cfg
                                break
                        except Exception:
                            pass
                
                # 檢查是否為 !undefined 或未找到
                if curr_val is None or str(curr_val).startswith("!undefined"):
                    # 觸發 JIT 熱補齊
                    target_base = reconcile_undefined_uri(
                        scheme_token=scheme_token,
                        raw_target=str(curr_val) if curr_val else "!undefined",
                        provider=provider_name,
                        config_binding=sval,
                        description=scheme.get("description", ""),
                        interactive=interactive
                    )
                    return os.path.normpath(os.path.join(target_base, rel)) if rel else target_base
                
                # 已有配置值
                val_str = str(curr_val)
                if "://" in val_str:
                    target_base = resolve(val_str, current_module=mod, context=context, interactive=interactive)
                elif os.path.isabs(val_str) or (len(val_str) > 1 and val_str[1] == ":"):
                    target_base = os.path.normpath(val_str)
                else:
                    # 相對路徑以 yscb_dir 為基準展開
                    target_base = os.path.normpath(os.path.join(yscb_dir, val_str))
                return os.path.normpath(os.path.join(target_base, rel)) if rel else target_base

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
                base_p = resolve(f"{token}://", current_module=mod, interactive=False)
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
        p = resolve(uri, interactive=False)
        return os.path.exists(p)
    except Exception:
        return False

def isfile(uri: str) -> bool:
    try:
        p = resolve(uri, interactive=False)
        return os.path.isfile(p)
    except Exception:
        return False

is_file = isfile

def isdir(uri: str) -> bool:
    try:
        p = resolve(uri, interactive=False)
        return os.path.isdir(p)
    except Exception:
        return False

is_dir = isdir

def remove(uri_str: str) -> None:
    try:
        p = resolve(uri_str, interactive=False)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def read_text(uri: str, encoding: str = "utf-8") -> str:
    p = resolve(uri, interactive=False)
    with open(p, "r", encoding=encoding) as f:
        return f.read()

def write_text(uri: str, content: str, encoding: str = "utf-8") -> None:
    p = resolve(uri, interactive=False)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=encoding) as f:
        f.write(content)

def read_json(uri: str, encoding: str = "utf-8") -> Any:
    p = resolve(uri, interactive=False)
    with open(p, "r", encoding=encoding) as f:
        return json.load(f)

def write_json(uri: str, data: Any, indent: int = 2, encoding: str = "utf-8") -> None:
    p = resolve(uri, interactive=False)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=encoding) as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def makedirs(uri: str, exist_ok: bool = True) -> None:
    p = resolve(uri, interactive=False)
    os.makedirs(p, exist_ok=exist_ok)

def listdir(uri: str) -> List[str]:
    p = resolve(uri, interactive=False)
    return os.listdir(p)

def copy(src_uri: str, dst_uri: str) -> None:
    src_p = resolve(src_uri, interactive=False)
    dst_p = resolve(dst_uri, interactive=False)
    if os.path.isdir(src_p):
        if os.path.exists(dst_p):
            shutil.rmtree(dst_p)
        shutil.copytree(src_p, dst_p)
    else:
        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
        shutil.copy2(src_p, dst_p)

def rmtree(uri: str) -> None:
    p = resolve(uri, interactive=False)
    if os.path.exists(p):
        shutil.rmtree(p)
