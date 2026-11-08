"""
YS-Codebase Symbol & Function Resolution Protocol (code.func://).
100% Python Standard Library, Zero Third-Party Dependency.
Provides uniform parsing, dynamic module discovery, and safe callable loading
across installed Zip modules and source development workspaces.
"""

import os
import sys
import importlib
from typing import Any, Callable, Optional, Tuple, Dict

from core import uri
from core import vfs
from core.context import get_env, get_runtime_context
from core.loader import _file_generation, get_cached_module, load_module_from_path


class SymbolError(Exception):
    """符號定位與加載基礎異常。"""
    pass


class InvalidSymbolURIError(SymbolError, ValueError):
    """當 code.func:// URI 格式無效時拋出。"""
    pass


class SymbolNotFoundError(SymbolError):
    """當目標模組、檔案或函式符號不存在或不可呼叫時拋出。"""
    pass


def _get_callable_cache() -> Dict[Any, Any]:
    return get_runtime_context().symbols_callable_cache


def _unpack_callable_entry(
    entry: Any,
) -> Tuple[Optional[Callable[..., Any]], Optional[Tuple[str, int, int]]]:
    """Unpacks a `callable_cache` value into `(callable_obj, (file_path, mtime_ns, size) | None)`."""
    if isinstance(entry, tuple) and len(entry) == 4 and callable(entry[0]):
        return entry[0], (str(entry[1]), int(entry[2]), int(entry[3]))
    if callable(entry):
        return entry, None
    return None, None


def parse_code_func_uri(uri_str: str) -> Tuple[str, str, str]:
    """
    解析 code.func://<module>/<subpath>:<function_name> 語法。

    Args:
        uri_str: code.func:// 協議字串
    Returns:
        (module_name, subpath, function_name) 三元組
    Raises:
        InvalidSymbolURIError: 若協議格式不正確或缺少 ':'
    """
    if not isinstance(uri_str, str):
        raise InvalidSymbolURIError(f"Symbol URI must be a string, got: {type(uri_str).__name__}")

    stripped = uri_str.strip()
    if not stripped.startswith("code.func://"):
        raise InvalidSymbolURIError(f"Symbol URI must start with 'code.func://', got: '{uri_str}'")

    raw_path = stripped[len("code.func://"):]
    if not raw_path:
        raise InvalidSymbolURIError(f"Empty body in symbol URI: '{uri_str}'")

    if ":" not in raw_path:
        raise InvalidSymbolURIError(
            f"Missing function separator ':' in symbol URI '{uri_str}'. "
            f"Expected format: code.func://<module>/<subpath>:<function_name>"
        )

    module_and_subpath, function_name = raw_path.rsplit(":", 1)
    function_name = function_name.strip()
    if not function_name:
        raise InvalidSymbolURIError(f"Empty function name in symbol URI '{uri_str}'.")

    # Clean leading/trailing slashes
    module_and_subpath = module_and_subpath.strip("/")
    parts = module_and_subpath.split("/", 1)
    module_name = parts[0].strip()
    subpath = parts[1].strip() if len(parts) > 1 else ""

    if not module_name:
        raise InvalidSymbolURIError(f"Empty module name in symbol URI '{uri_str}'.")
    if not subpath:
        # Default subpath to module_name if omitted (e.g. code.func://agents-workflow:get_map)
        subpath = module_name

    # Remove .py suffix if user provided it
    if subpath.endswith(".py"):
        subpath = subpath[:-3]

    return module_name, subpath, function_name


def resolve_callable(uri_str: str, context: Optional[Any] = None, use_cache: bool = True) -> Callable[..., Any]:
    """
    解析 code.func:// 協議並動態載入返回 Python 可呼叫物件 (Callable)。

    雙軌尋址策略：
      1. [軌道 1: Package Import] 優先透過 Python sys.modules 或標準 importlib 載入。
      2. [軌道 2: VFS Spec Import] 透過語意 URI (module.root://, module.source.root://) 尋找實體 .py 檔案載入。

    Args:
        uri_str: code.func:// 協議字串
        context: 可選之執行期/編譯期上下文
        use_cache: 是否使用載入快取
    Returns:
        Python Callable 物件
    Raises:
        InvalidSymbolURIError: 格式錯誤
        SymbolNotFoundError: 模組或函式符號不存在、非 Callable
    """
    try:
        yscb_root_key = os.path.normpath(uri.resolve_yscb_root())
    except Exception:
        yscb_root_key = ""
    cache_key = (yscb_root_key, uri_str)
    callable_cache = _get_callable_cache()
    if use_cache:
        for ck in (cache_key, uri_str):
            if ck in callable_cache:
                cached_fn, file_meta = _unpack_callable_entry(callable_cache[ck])
                if cached_fn is not None:
                    if file_meta is None:
                        return cached_fn
                    f_path, c_mtime, c_size = file_meta
                    cur_mtime, cur_size = _file_generation(f_path)
                    if cur_mtime != -1 and cur_mtime == c_mtime and cur_size == c_size:
                        return cached_fn
                callable_cache.pop(ck, None)

    module_name, subpath, function_name = parse_code_func_uri(uri_str)
    mod_pkg = module_name.replace("-", "_")

    from core.platform import ensure_installed_modules_path
    ensure_installed_modules_path(priority_module=module_name)

    loaded_mod = None
    resolved_file_meta: Optional[Tuple[str, int, int]] = None

    # --- 軌道 1: 嘗試標準 Package Import ---
    # 嘗試模組名與 subpath 的組合（例：agents_workflow.providers 或 agents_workflow）
    import_candidates = []
    subpath_dots = subpath.replace("/", ".")
    if subpath_dots.startswith(f"{mod_pkg}."):
        import_candidates.append(subpath_dots)
    else:
        import_candidates.append(f"{mod_pkg}.{subpath_dots}")
        import_candidates.append(subpath_dots)

    for imp_cand in import_candidates:
        try:
            cand_mod = importlib.import_module(imp_cand)
            if cand_mod is not None:
                # 若該模組係由 Track 2 VFS loader 先前載入，交由 Track 2 執行 (mtime_ns, size) 校驗與重載
                cand_name = getattr(cand_mod, "__name__", "")
                if cand_name.startswith("_yscb_") or get_cached_module(f"_yscb_mod_{mod_pkg}_{subpath.replace('/', '_').replace('.', '_')}") is cand_mod:
                    continue
                loaded_mod = cand_mod
                break
        except (ImportError, ModuleNotFoundError):
            continue

    # --- 軌道 2: 嘗試 VFS 實體檔案載入 ---
    if loaded_mod is None:
        file_candidates = [
            f"module://{module_name}/{subpath}.py",
            f"module://{module_name}/{mod_pkg}/{subpath}.py",
        ]
        if get_env("YSCB_TEST_SANDBOX") == "1":
            file_candidates.extend([
                f"module.source://{module_name}/{mod_pkg}/{subpath}.py",
                f"module.source://{module_name}/{subpath}.py",
            ])

        for f_uri in file_candidates:
            if vfs.exists(f_uri):
                real_file_path = uri.resolve(f_uri)
                if os.path.isfile(real_file_path):
                    norm_real_path = os.path.normpath(os.path.abspath(real_file_path))
                    cur_mtime, cur_size = _file_generation(norm_real_path)
                    resolved_file_meta = (norm_real_path, cur_mtime, cur_size)
                    script_stem = subpath.replace("/", "_").replace(".", "_")
                    mod_unique_key = f"_yscb_mod_{mod_pkg}_{script_stem}"
                    dot_name = subpath.replace("/", ".")
                    full_mod_name = dot_name if dot_name.startswith(f"{mod_pkg}.") else f"{mod_pkg}.{dot_name}"
                    try:
                        mod_dir = os.path.dirname(real_file_path)
                        mod_parent = os.path.dirname(mod_dir)
                        extra_dirs = [p_cand for p_cand in (mod_dir, mod_parent) if p_cand and os.path.isdir(p_cand)]
                        ensure_installed_modules_path(
                            priority_module=module_name,
                            extra_paths=extra_dirs,
                        )

                        if os.path.isfile(os.path.join(mod_dir, "__init__.py")):
                            pkg_name = os.path.basename(mod_dir)
                            sub_stem = os.path.splitext(os.path.basename(real_file_path))[0]
                            pkg_mod_name = pkg_name if sub_stem == "__init__" else f"{pkg_name}.{sub_stem}"
                            if get_cached_module(mod_unique_key) is None:
                                loaded_mod = importlib.import_module(pkg_mod_name)
                                break

                        loaded_mod = load_module_from_path(
                            mod_unique_key,
                            real_file_path,
                            alias_keys=(full_mod_name, subpath.replace("/", ".")),
                            reload_if_changed=True,
                        )
                        break
                    except Exception as e:
                        raise SymbolNotFoundError(
                            f"Failed to load module file '{real_file_path}' for symbol URI '{uri_str}': {e}"
                        ) from e

    if loaded_mod is None:
        raise SymbolNotFoundError(
            f"Could not locate module for symbol URI '{uri_str}'. "
            f"Module: '{module_name}', Subpath: '{subpath}'."
        )

    if not hasattr(loaded_mod, function_name):
        raise SymbolNotFoundError(
            f"Function '{function_name}' not found in module '{loaded_mod.__name__}' for symbol URI '{uri_str}'."
        )

    target_fn = getattr(loaded_mod, function_name)
    if not callable(target_fn):
        raise SymbolNotFoundError(
            f"Symbol '{function_name}' in module '{loaded_mod.__name__}' is not callable (got {type(target_fn).__name__})."
        )

    if use_cache:
        if resolved_file_meta is not None:
            callable_cache[cache_key] = (
                target_fn,
                resolved_file_meta[0],
                resolved_file_meta[1],
                resolved_file_meta[2],
            )
        else:
            callable_cache[cache_key] = target_fn

    return target_fn


def clear_callable_cache() -> None:
    """清理已載入的 Callable 快取。"""
    _get_callable_cache().clear()


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    if name == "_RESOLVED_CALLABLE_CACHE":
        return _get_callable_cache()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
