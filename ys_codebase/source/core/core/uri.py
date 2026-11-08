"""
YS-Codebase Semantic URI Protocol SDK.
100% Python Standard Library, Zero Third-Party Dependency.
Dynamically resolves contributed URI schemes from contributes.merged.json with self-injection architecture
and provides JIT prompt & auto-reconciliation for !undefined configurations.
"""

import os
import sys
import time
import types
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple, Generator, Set, Mapping

# Import ExecutionContext & RuntimeContext from SSOT context.py
from core.context import (
    ExecutionContext,
    get_current_scope,
    get_env,
    get_runtime_context,
    _ThreadLocalSet,
)

CONFIG_FILENAME = "yscb.config.json"


def _get_uri_tls() -> threading.local:
    return get_runtime_context().uri_tls


def _get_reconciling_tokens() -> _ThreadLocalSet:
    return get_runtime_context().uri_reconciling_tokens


def _get_token_map_cache() -> Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]]:
    return get_runtime_context().uri_token_map_cache


def _get_schemes_cache() -> Dict[str, Tuple[float, float, List[Dict[str, Any]]]]:
    return get_runtime_context().uri_schemes_cache


def _get_uri_reentrancy() -> threading.local:
    return get_runtime_context().uri_reentrancy


# Bootstrap fallback schemes (Option B: Canonical Rooted Schemes)
_BOOTSTRAP_FALLBACK_SCHEMES: Tuple[Mapping[str, Any], ...] = (
    types.MappingProxyType({"token": "yscb.host", "type": "const", "value": "{yscb_host}"}),
    types.MappingProxyType({"token": "module.mirror", "type": "const", "value": "yscb://.mirror/"}),
    types.MappingProxyType({"token": "snapshot", "type": "const", "value": "yscb://.snapshots/"}),
    types.MappingProxyType({"token": "module", "type": "const", "value": "yscb://.modules/"}),
    types.MappingProxyType({"token": "config", "type": "const", "value": "yscb://config/"}),
    types.MappingProxyType({"token": "config.local", "type": "const", "value": "yscb://.config.local/"}),
    types.MappingProxyType({"token": "cache", "type": "const", "value": "yscb://.cache/"}),
    types.MappingProxyType({"token": "storage", "type": "const", "value": "yscb://storage/"}),
    types.MappingProxyType({"token": "storage.local", "type": "const", "value": "yscb://.storage.local/"}),
    types.MappingProxyType({"token": "module.source", "type": "const", "value": "yscb://source/"}),
    types.MappingProxyType({"token": "module.build", "type": "const", "value": "yscb://.build/"}),
    types.MappingProxyType({"token": "module.release", "type": "const", "value": "yscb://release/"}),
    types.MappingProxyType({"token": "yscb.venv", "type": "const", "value": "yscb://.venv/"}),
)


class UndefinedModuleContextError(ValueError):
    """當 URI 中包含 '@/' 自省語法但缺乏當前模組上下文時拋出。"""
    def __init__(self, uri_str: str, message: Optional[str] = None):
        self.uri_str = uri_str
        default_msg = (
            f"Cannot resolve active module placeholder '@' in URI '{uri_str}'. "
            "No active module context is set. Please use 'with uri.module_scope(name):' "
            "or pass explicit module name like '{scheme}://{module}/path'."
        )
        super().__init__(message or default_msg)


def format_undefined_uri_hint(
    scheme: str,
    provider: Optional[str] = None,
    binding: Optional[str] = None,
) -> str:
    """
    針對未定義 (!undefined) 之語意 URI 協議生成可直接複製執行的 CLI 修復指令提示。

    Args:
        scheme: 協議名稱（不含 '://'，如 'project' 或 'workflow.plans'）。
        provider: 宣告該協議之模組名稱（預設 'core'）。
        binding: 綁定之組態鍵路徑（如 'project_root' 或 'paths.plans'）。

    Returns:
        str: 單行可執行之 CLI 修復建議字串。
    """
    prov = provider or "core"
    bind = binding or ("project_root" if scheme == "project" else "unknown")
    if scheme == "project" or (prov == "core" and bind == "project_root"):
        return "python yscb.py config set core project_root ./"
    return f"python yscb.py config set {prov} {bind} <path>"


class UndefinedURIError(ValueError):
    """當語意協議未設定 (!undefined) 且處於非互動環境或拒絕補齊時拋出之結構化異常。"""
    def __init__(self, scheme: str, provider: Optional[str] = None, binding: Optional[str] = None, message: Optional[str] = None):
        self.scheme = scheme
        self.provider = provider or "core"
        self.binding = binding or "unknown"
        quick_fix = format_undefined_uri_hint(self.scheme, self.provider, self.binding)
        default_msg = (
            f"Semantic URI '{scheme}://' is undefined (!undefined). "
            f"Provider: '{self.provider}', Config Binding: '{self.binding}'. "
            f"Please configure it in config://{self.provider}/config.project.json. "
            f"Quick fix: {quick_fix}"
        )
        super().__init__(message or default_msg)


class CyclicURIDependencyError(ValueError):
    """當檢測到語意協議自引用或循環依賴時拋出。"""
    pass


def set_module_context(module_name: Optional[str]) -> None:
    _get_uri_tls().active_module_context = module_name


def get_module_context() -> Optional[str]:
    scope = get_current_scope()
    if scope is not None and scope.active_module:
        return scope.active_module
    tls_mod = getattr(_get_uri_tls(), "active_module_context", None)
    if tls_mod:
        return tls_mod
    return None


@contextmanager
def module_scope(module_name: Optional[str]) -> Generator[None, None, None]:
    """
    模組上下文安全作用域 (Context Manager)：
    退出區塊時以 finally 100% 保證還原舊執行緒本地 active_module_context，防止測試與 Hook 污染。
    """
    tls = _get_uri_tls()
    old = getattr(tls, "active_module_context", None)
    set_module_context(module_name)
    try:
        yield
    finally:
        tls.active_module_context = old


def set_host_dir(host_dir: Optional[str]) -> None:
    """Explicitly inject host directory."""
    _get_uri_tls().active_host_dir = os.path.normpath(os.path.abspath(host_dir)) if host_dir else None


def get_host_dir() -> Optional[str]:
    """Get active host directory from RuntimeScope, thread-local memory context, or YSCB_HOST_DIR environment variable."""
    scope = get_current_scope()
    if scope is not None and scope.active_host_dir:
        return scope.active_host_dir
    active_host = getattr(_get_uri_tls(), "active_host_dir", None)
    if active_host:
        return active_host
    env_dir = get_env("YSCB_HOST_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.normpath(os.path.abspath(env_dir))
    return None


@contextmanager
def host_scope(host_dir: Optional[str], yscb_dir: Optional[str] = None) -> Generator[None, None, None]:
    """
    宿主目錄安全作用域 (Context Manager)：
    退出區塊時以 finally 100% 保證還原舊執行緒本地 active_host_dir（與可選之 active_yscb_dir）。
    """
    tls = _get_uri_tls()
    old_host = getattr(tls, "active_host_dir", None)
    old_yscb = getattr(tls, "active_yscb_dir", None)
    set_host_dir(host_dir)
    if yscb_dir is not None:
        if host_dir and not os.path.isabs(yscb_dir):
            set_yscb_root(os.path.join(os.path.abspath(host_dir), yscb_dir))
        else:
            set_yscb_root(yscb_dir)
    try:
        yield
    finally:
        tls.active_host_dir = old_host
        if yscb_dir is not None:
            tls.active_yscb_dir = old_yscb


def set_yscb_root(yscb_dir: Optional[str]) -> None:
    """Explicitly inject YSCB toolchain root directory."""
    _get_uri_tls().active_yscb_dir = os.path.normpath(os.path.abspath(yscb_dir)) if yscb_dir else None


def get_yscb_root() -> Optional[str]:
    """Get active YSCB toolchain root directory from RuntimeScope, thread-local memory context, or YSCB_ROOT_DIR environment variable."""
    scope = get_current_scope()
    if scope is not None and scope.active_yscb_dir:
        return scope.active_yscb_dir
    active_yscb = getattr(_get_uri_tls(), "active_yscb_dir", None)
    if active_yscb:
        return active_yscb
    env_dir = get_env("YSCB_ROOT_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.normpath(os.path.abspath(env_dir))
    return None


@contextmanager
def yscb_scope(yscb_dir: Optional[str]) -> Generator[None, None, None]:
    """
    工具庫核心目錄安全作用域 (Context Manager)：
    退出區塊時以 finally 100% 保證還原舊執行緒本地 active_yscb_dir。
    """
    tls = _get_uri_tls()
    old = getattr(tls, "active_yscb_dir", None)
    set_yscb_root(yscb_dir)
    try:
        yield
    finally:
        tls.active_yscb_dir = old


def resolve_yscb_root() -> str:
    """
    三階梯物理拓撲不變性自省：
    1. 優先返回顯式注入之 yscb_root (記憶體或環境變數)。
    2. 常數自省：以 __file__ 物理路徑向上推算 3 層。
    """
    injected = get_yscb_root()
    if injected and os.path.isdir(injected):
        return injected
    curr = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))


def _get_host_config(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    獲取宿主目錄與工具庫根目錄 (Physical Topology Invariant Guarantee).
    """
    yscb_dir = resolve_yscb_root()
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


def _get_project_dir(host_dir: str, yscb_dir: str) -> Optional[str]:
    """
    Resolves project root directory using core.config SDK (core module).
    """
    try:
        from core import config
        rel_proj = config.get("core", "project_root")
    except Exception:
        rel_proj = None

    if rel_proj:
        if str(rel_proj).startswith("!undefined"):
            return None
        if os.path.isabs(str(rel_proj)):
            return os.path.normpath(str(rel_proj))
        return os.path.normpath(os.path.join(host_dir, str(rel_proj)))
    return None


_TOKEN_MAP_TTL_SEC: float = 0.1


def invalidate_uri_cache() -> None:
    """Clears in-memory URI schemes, token map, and contributes scan/merged caches."""
    _get_schemes_cache().clear()
    _get_token_map_cache().clear()
    try:
        from . import contributes
        contributes.invalidate_cache()
    except Exception:
        pass


def _get_merged_uri_schemes(yscb_dir: str) -> List[Dict[str, Any]]:
    """
    Reads contributed URI schemes from merged cache with in-memory (merged_mtime, cfg_mtime, data) cache
    and thread-local reentrancy-guarded JIT dirty check.
    """
    reentrancy = _get_uri_reentrancy()
    if getattr(reentrancy, "active", False):
        return [dict(s) for s in _BOOTSTRAP_FALLBACK_SCHEMES]

    merged_cfg = os.path.join(yscb_dir, ".cache", "core", "contributes.merged.json")
    cfg_core_contrib = os.path.join(yscb_dir, "config", "core", "contribute.json")
    merged_mtime = os.path.getmtime(merged_cfg) if os.path.isfile(merged_cfg) else -1.0
    cfg_mtime = os.path.getmtime(cfg_core_contrib) if os.path.isfile(cfg_core_contrib) else -1.0

    schemes_cache = _get_schemes_cache()
    cached = schemes_cache.get(yscb_dir)
    if cached and cached[0] == merged_mtime and cached[1] == cfg_mtime and merged_mtime > 0:
        return cached[2]

    reentrancy.active = True
    try:
        try:
            from . import contributes
            is_dirty, _ = contributes._is_contributes_dirty("core")
            if is_dirty:
                contributes.get("core", "uri_schemes")
                merged_mtime = os.path.getmtime(merged_cfg) if os.path.isfile(merged_cfg) else -1.0
        except Exception:
            pass

        try:
            from core import vfs
            if vfs.is_file(merged_cfg):
                merged_mtime = os.path.getmtime(merged_cfg)
                data = vfs.read_json(merged_cfg)
                schemes = data.get("uri_schemes", [])
                if isinstance(schemes, list) and len(schemes) > 0:
                    schemes_cache[yscb_dir] = (merged_mtime, cfg_mtime, schemes)
                    return schemes
        except Exception:
            pass
    finally:
        reentrancy.active = False

    return [dict(s) for s in _BOOTSTRAP_FALLBACK_SCHEMES]


def _build_scheme_token_map(yscb_dir: str) -> Dict[str, Dict[str, Any]]:
    """Builds combined URI scheme lookup dictionary from merged cache and fallback schemes."""
    is_reentrant = getattr(_get_uri_reentrancy(), "active", False)
    token_map_cache = _get_token_map_cache()
    if not is_reentrant:
        now_mono = time.monotonic()
        cached_entry = token_map_cache.get(yscb_dir)
        if cached_entry is not None and (now_mono - cached_entry[0]) < _TOKEN_MAP_TTL_SEC:
            return {k: dict(v) for k, v in cached_entry[1].items()}

    all_schemes = _get_merged_uri_schemes(yscb_dir)
    token_map = {s.get("token"): dict(s) for s in all_schemes if isinstance(s, dict) and "token" in s}
    for fb in _BOOTSTRAP_FALLBACK_SCHEMES:
        if fb["token"] not in token_map:
            token_map[fb["token"]] = dict(fb)

    if not is_reentrant:
        token_map_cache[yscb_dir] = (time.monotonic(), {k: dict(v) for k, v in token_map.items()})
    return token_map


def list_registered_schemes_summary() -> List[Dict[str, Any]]:
    """
    列出當前全系統已註冊之所有語意 URI 協議摘要清冊 (供 --help 展開與自省展示)。
    """
    yscb_dir = resolve_yscb_root()
    token_map = _build_scheme_token_map(yscb_dir)

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


def _print_reconcile_prompt(provider_name: str, scheme_token: str, desc: str, binding_key: str) -> None:
    """Renders JIT prompt text for an undefined semantic URI protocol."""
    from core.log import log
    log(f"\n[{provider_name}] 語意協議 '{scheme_token}://' 尚未設定 (當前為 !undefined)。")
    if desc:
        log(f"  • 說明: {desc}")
    log(f"  • 目標設定檔: config://{provider_name}/config.project.json ({binding_key})")
    log("  • 路徑基準: 相對路徑一律以 'yscb://' (工具庫根目錄) 為起始，支援 '../' 穿透或直接輸入語意協議格式 (例: project://plans)")
    log("\n是否進行及時熱更新補齊?")
    log("  -y <path> : 設定路徑、自動更新設定檔並繼續運行")
    log("  -n        : 終止當前操作")
    log("  --help    : 展開詳細協議資訊與全系統可用協議清單")


def _print_schemes_summary_table() -> None:
    """Renders the registered URI protocols summary table to stdout."""
    from core.log import log
    log("\n==============================================================================================================")
    log("YS-Codebase 語意協議註冊清冊 (Registered URI Protocols Summary)")
    log("==============================================================================================================")
    log(f"{'TOKEN':<23} {'PROVIDER':<12} {'RAW TARGET / VALUE':<28} {'RESOLVED PATH / STATUS'}")
    log("--------------------------------------------------------------------------------------------------------------")
    for s in list_registered_schemes_summary():
        raw_v = s.get("value", "")
        log(f"{s['token'] + '://':<23} {s['provider']:<12} {raw_v:<28} {s['resolved_path']}")
    log("==============================================================================================================\n")


def _persist_reconciled_uri_config(yscb_dir: str, provider_name: str, binding_key: str, input_val: str, resolved_target: str) -> None:
    """Writes reconciled URI configuration back to config.project.json and ensures target directory exists."""
    from core import vfs
    from core.log import log_info
    mod_proj_cfg = os.path.join(yscb_dir, "config", provider_name, "config.project.json")
    cfg_data: Dict[str, Any] = {}
    if vfs.is_file(mod_proj_cfg):
        try:
            loaded = vfs.read_json(mod_proj_cfg)
            if isinstance(loaded, dict):
                cfg_data = loaded
        except Exception:
            cfg_data = {}

    keys = binding_key.split(".")
    curr = cfg_data
    for k in keys[:-1]:
        if k not in curr or not isinstance(curr[k], dict):
            curr[k] = {}
        curr = curr[k]
    curr[keys[-1]] = input_val

    vfs.write_json(mod_proj_cfg, cfg_data, indent=2, atomic=True)
    try:
        from core import config
        config.reload(provider_name)
    except Exception:
        pass

    log_info(f"[{provider_name}] 已成功寫入設定檔: '{binding_key}' = '{input_val}'")
    if not vfs.exists(resolved_target):
        try:
            vfs.makedirs(resolved_target, exist_ok=True)
            log_info(f"[{provider_name}] 目錄不存在，已自動建立: {resolved_target}")
        except Exception:
            pass


def reconcile_undefined_uri(
    scheme_token: str,
    raw_target: str,
    provider: Optional[str] = None,
    config_binding: Optional[str] = None,
    description: Optional[str] = None,
    interactive: bool = True
) -> str:
    """
    處理 !undefined 協議：
    檢查循環依賴後，統一拋出結構化 UndefinedURIError（附帶單行 CLI Quick Fix 指令提示），
    杜絕阻塞式 stdin 互動與非啟動器 sys.exit。
    """
    reconciling = _get_reconciling_tokens()
    if scheme_token in reconciling:
        raise CyclicURIDependencyError(f"Cyclic or self-referencing URI dependency detected for '{scheme_token}://'")

    provider_name = provider or "core"
    binding_key = config_binding or ("project_root" if scheme_token == "project" else "unknown")
    raise UndefinedURIError(scheme=scheme_token, provider=provider_name, binding=binding_key)


def _expand_module_placeholder_in_rel(rel: str, active_mod: Optional[str], raw_uri: str) -> str:
    """Expands '@/...' or '{module}' active module placeholders in relative URI path."""
    if rel.startswith("@/") or rel == "@":
        if not active_mod:
            raise UndefinedModuleContextError(raw_uri)
        return active_mod if rel == "@" else active_mod + rel[1:]
    if "{module}" in rel:
        if not active_mod:
            raise UndefinedModuleContextError(raw_uri)
        return rel.replace("{module}", active_mod)
    return rel


def _ensure_safe_subpath(target_base: str, rel: str, raw_uri: str) -> str:
    """
    Verifies that a non-empty relative URI subpath stays within target_base
    without '..' escape or Windows drive reset.
    """
    base_norm = os.path.normpath(os.path.abspath(target_base))
    if not rel:
        return base_norm
    if len(rel) > 1 and rel[1] == ":":
        raise PermissionError(
            f"Path traversal or drive reset detected in URI '{raw_uri}': escaped base '{base_norm}'."
        )
    joined_norm = os.path.normpath(os.path.join(base_norm, rel))
    try:
        common = os.path.commonpath([base_norm, joined_norm])
    except ValueError as err:
        raise PermissionError(
            f"Path traversal or drive reset detected in URI '{raw_uri}': escaped base '{base_norm}'."
        ) from err
    if common != base_norm:
        raise PermissionError(
            f"Path traversal detected in URI '{raw_uri}': subpath '{rel}' escaped base '{base_norm}'."
        )
    return joined_norm


def _resolve_const_scheme(
    raw_uri: str,
    sval: str,
    rel: str,
    yscb_dir: str,
    active_mod: Optional[str],
    context: Optional[ExecutionContext],
    interactive: bool,
) -> str:
    """Resolves a 'const' type contributed URI scheme with path traversal protection."""
    try:
        host_dir, _ = _get_host_config()
    except Exception:
        host_dir = get_host_dir() or os.path.normpath(os.path.dirname(yscb_dir))

    if "{module}" in sval:
        if not active_mod:
            raise UndefinedModuleContextError(raw_uri)
        val_expanded = sval.replace("{module}", active_mod)
    else:
        val_expanded = sval
    val_expanded = val_expanded.replace("{yscb_root}", yscb_dir).replace("{yscb_host}", host_dir or "")

    target_base = resolve(val_expanded, current_module=active_mod, context=context, interactive=interactive)
    return _ensure_safe_subpath(target_base, rel, raw_uri)


def _resolve_config_scheme(
    scheme_token: str,
    scheme: Dict[str, Any],
    sval: str,
    rel: str,
    yscb_dir: str,
    provider_name: str,
    active_mod: Optional[str],
    context: Optional[ExecutionContext],
    interactive: bool,
) -> str:
    """Resolves a 'config' type contributed URI scheme with JIT hot-reconciliation fallback."""
    _get_host_config()
    curr_val = None
    try:
        from core import config
        curr_val = config.get(provider_name, sval)
        if curr_val is None and active_mod and active_mod != provider_name:
            curr_val = config.get(active_mod, sval)
        if curr_val is None and provider_name != "core":
            curr_val = config.get("core", sval)
    except Exception:
        curr_val = None

    raw_uri = f"{scheme_token}://{rel}" if rel else f"{scheme_token}://"
    if curr_val is None or str(curr_val).startswith("!undefined"):
        target_base = reconcile_undefined_uri(
            scheme_token=scheme_token,
            raw_target=str(curr_val) if curr_val else "!undefined",
            provider=provider_name,
            config_binding=sval,
            description=scheme.get("description", ""),
            interactive=interactive,
        )
        return _ensure_safe_subpath(target_base, rel, raw_uri)

    val_str = str(curr_val)
    if "://" in val_str:
        target_base = resolve(val_str, current_module=active_mod, context=context, interactive=interactive)
    elif os.path.isabs(val_str) or (len(val_str) > 1 and val_str[1] == ":"):
        target_base = os.path.normpath(val_str)
    else:
        target_base = os.path.normpath(os.path.join(yscb_dir, val_str))
    return _ensure_safe_subpath(target_base, rel, raw_uri)


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

    yscb_dir = resolve_yscb_root()
    active_mod = current_module or get_module_context() or (
        context.module_name if context and hasattr(context, "module_name") else None
    )

    # Fast-path for root anchor protocol yscb:// (No need to read host config)
    if uri.startswith("yscb://"):
        rel = uri[len("yscb://"):].lstrip("/\\")
        return _ensure_safe_subpath(yscb_dir, rel, uri)

    # Fast-path for host anchor protocol yscb.host:// (Force points to yscb.py/yscb.config.json directory)
    if uri.startswith("yscb.host://"):
        try:
            host_dir, _ = _get_host_config()
        except Exception:
            host_dir = get_host_dir() or os.path.normpath(os.path.dirname(yscb_dir))
        rel = uri[len("yscb.host://"):].lstrip("/\\")
        return _ensure_safe_subpath(host_dir, rel, uri)

    # 1. Check project:// with strict explicit configuration rule & JIT Hot-Reconciliation
    if uri.startswith("project://"):
        host_dir, _ = _get_host_config()
        proj_dir = _get_project_dir(host_dir, yscb_dir)
        if proj_dir is None:
            proj_dir = reconcile_undefined_uri(
                scheme_token="project",
                raw_target="!undefined",
                provider="core",
                config_binding="project_root",
                description="指向專案最頂層根目錄",
                interactive=interactive
            )
        rel = uri[len("project://"):].lstrip("/\\")
        return _ensure_safe_subpath(proj_dir, rel, uri)

    # 2. Dynamic contributed protocols lookup
    if "://" in uri:
        scheme_token, rel = uri.split("://", 1)
        rel = _expand_module_placeholder_in_rel(rel.lstrip("/\\"), active_mod, uri)
        token_map = _build_scheme_token_map(yscb_dir)

        if scheme_token in token_map:
            scheme = token_map[scheme_token]
            stype = scheme.get("type", "const")
            sval = scheme.get("value", "")
            provider_name = scheme.get("__provider__", active_mod or "core")

            if stype == "const":
                return _resolve_const_scheme(uri, sval, rel, yscb_dir, active_mod, context, interactive)
            if stype == "config":
                return _resolve_config_scheme(
                    scheme_token, scheme, sval, rel, yscb_dir, provider_name, active_mod, context, interactive
                )

        raise ValueError(f"Unsupported URI scheme: {scheme_token}://")

    # Zero Speculation: Disallow ambiguous non-URI relative strings
    raise ValueError(
        f"Invalid semantic URI format: '{uri}'. "
        "Path must be a registered semantic URI ('scheme://...') or an absolute OS path."
    )


def to_uri(abs_path: str, current_module: Optional[str] = None) -> str:
    norm = os.path.normpath(os.path.abspath(abs_path))
    yscb_dir = resolve_yscb_root()
    mod = current_module or get_module_context() or "core"

    proj_dir = None
    try:
        host_dir, _ = _get_host_config()
        proj_dir = _get_project_dir(host_dir, yscb_dir)
    except Exception:
        pass

    token_map = _build_scheme_token_map(yscb_dir)

    check_order: List[Tuple[str, str]] = []
    for token, scheme in token_map.items():
        stype = scheme.get("type")
        if stype in ("const", "config"):
            try:
                base_p = resolve(f"{token}://", current_module=mod, interactive=False)
                if base_p:
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


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    ctx = get_runtime_context()
    if name == "_URI_TLS":
        return ctx.uri_tls
    if name == "_reconciling_tokens":
        return ctx.uri_reconciling_tokens
    if name == "_TOKEN_MAP_CACHE":
        return ctx.uri_token_map_cache
    if name == "_SCHEMES_CACHE":
        return ctx.uri_schemes_cache
    if name == "_URI_REENTRANCY":
        return ctx.uri_reentrancy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
