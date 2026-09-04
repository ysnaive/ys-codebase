"""
YS-Codebase Microkernel Event Bus.
Decoupled, zero-dependency, ultra-lightweight lifecycle event dispatcher.
Scans module://{mod}/scripts/hook.{emit_module}.py or specified search roots.
"""
from typing import List, Dict, Any, Optional
import os
import sys
import importlib.util
from core import uri
from core.context import ExecutionContext


def broadcast(
    event_name: str,
    context: Optional[Any] = None,
    emit_module: str = "core",
    search_roots: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    向模組廣播生命週期事件，動態尋址 scripts/hook.{emit_module}.py。

    :param event_name: 事件名稱（如 "pre_cli_dispatch", "post_cli_dispatch", "on_reload"）
    :param context: 執行期上下文物件，預設自動建立 ExecutionContext
    :param emit_module: 事件發送者名稱，用於定位 hook.{emit_module}.py，預設為 "core"
    :param search_roots: 自訂掃描根目錄列表；若為 None 則預設掃描 module:// 運行端
    :return: 執行結果字典 { module_name: result_or_status }
    """
    results: Dict[str, Any] = {}
    ctx = context if context is not None else ExecutionContext(emit_module, event_name, [])

    targets: List[tuple[str, str]] = []  # [(mod_name, hook_real_path)]

    if search_roots is not None:
        executed_hooks = set()
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            for mod_name in sorted(os.listdir(root)):
                if mod_name in executed_hooks:
                    continue
                hook_file = os.path.join(root, mod_name, "scripts", f"hook.{emit_module}.py")
                if os.path.isfile(hook_file):
                    executed_hooks.add(mod_name)
                    targets.append((mod_name, os.path.abspath(hook_file)))
    else:
        if not uri.exists("module://"):
            return results
        try:
            for mod in sorted(uri.listdir("module://")):
                hook_uri = f"module://{mod}/scripts/hook.{emit_module}.py"
                if uri.exists(hook_uri):
                    hook_real_path = uri.resolve(hook_uri)
                    if os.path.isfile(hook_real_path):
                        targets.append((mod, hook_real_path))
        except Exception:
            return results

    # Candidate function names for flexible matching
    if event_name.startswith("on_"):
        candidate_funcs = [event_name, event_name[3:], "on_event"]
    else:
        candidate_funcs = [f"on_{event_name}", event_name, "on_event"]

    for mod_name, hook_real_path in targets:
        mod_key = f"_yscb_hook_{mod_name}_{emit_module}"
        try:
            spec = importlib.util.spec_from_file_location(mod_key, hook_real_path)
            if spec and spec.loader:
                hook_mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_key] = hook_mod
                spec.loader.exec_module(hook_mod)

                hook_func = None
                for fname in candidate_funcs:
                    fn = getattr(hook_mod, fname, None)
                    if callable(fn):
                        hook_func = fn
                        break

                if callable(hook_func):
                    h_res = hook_func(ctx)
                    results[mod_name] = h_res if h_res is not None else "success"
        except Exception as e:
            results[mod_name] = f"warning: {e}"
            print(f"[{emit_module}:events] Warning: Hook '{mod_name}:hook.{emit_module}.py' failed on '{event_name}': {e}", file=sys.stderr)

    return results


def get_contributed_events() -> Dict[str, List[Dict[str, str]]]:
    """
    聚合全系統各模組派送之事件清冊（中繼資料查表）。
    支援 list[{"<name>": "description"}]、list[{"name": "...", "description": "..."}] 與 dict 格式。

    :return: 字典格式 { module_name: [ {"name": event_name, "description": desc} ] }
    """
    from core import contributes
    result: Dict[str, List[Dict[str, str]]] = {}

    try:
        events_raw = contributes.get("core", "events", default=[])
    except Exception:
        events_raw = []

    if isinstance(events_raw, list):
        for item in events_raw:
            if not isinstance(item, dict):
                continue
            provider = item.get("__provider__", "core")
            if provider not in result:
                result[provider] = []

            if "name" in item and "description" in item:
                result[provider].append({
                    "name": str(item["name"]),
                    "description": str(item["description"])
                })
            else:
                for k, v in item.items():
                    if k == "__provider__":
                        continue
                    result[provider].append({
                        "name": str(k),
                        "description": str(v)
                    })
    elif isinstance(events_raw, dict):
        for k, v in events_raw.items():
            if k == "__provider__":
                continue
            provider = "core"
            if isinstance(v, dict):
                provider = v.get("__provider__", "core")
                desc = v.get("description", str(v))
            else:
                desc = str(v)
            if provider not in result:
                result[provider] = []
            result[provider].append({
                "name": str(k),
                "description": desc
            })

    return result
