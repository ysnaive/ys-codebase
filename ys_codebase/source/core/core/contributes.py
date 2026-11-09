"""
Contributes Aggregator and Dependency Injection Engine.
Rigid Topology & Zero Speculation: strictly scans installed modules in module://.
Standard Directory: module://<donor>/contributes/<target>.json
Project Overrides: config://<target>/config.project.json
"""
from typing import Dict, Any, List, Optional, Set, Tuple
import os
import copy
import time
from core import uri
from core import vfs
from core.context import cell_span, get_runtime_context
from core.log import log_warn


def _tag_provider(data: Any, donor_name: str) -> Any:
    """
    遞迴為 contributes 宣告中的 Dict 與 List[Dict] 項目注入 __provider__ 與 __providers__ 標記。
    若物件已顯式宣告 __provider__ 則予以保留不覆蓋。
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)) and not (k.startswith("__") and k.endswith("__")):
                result[k] = _tag_provider(v, donor_name)
            else:
                result[k] = v
        provider_val = str(result.get("__provider__", donor_name))
        result["__provider__"] = provider_val
        existing_providers = result.get("__providers__")
        if isinstance(existing_providers, list):
            providers_list = [str(p) for p in existing_providers]
            if provider_val not in providers_list:
                providers_list.append(provider_val)
            result["__providers__"] = providers_list
        else:
            result["__providers__"] = [provider_val]
        return result
    if isinstance(data, list):
        return [_tag_provider(item, donor_name) for item in data]
    return data


def _tag_payload_body(body: Dict[str, Any], donor_name: str) -> Dict[str, Any]:
    """對整個 contributes 單檔頂層字典的各擴充點內容遞迴注入 __provider__ 與 __providers__。"""
    tagged: Dict[str, Any] = {}
    for c_key, c_val in body.items():
        if isinstance(c_val, list):
            tagged[c_key] = [
                _tag_provider(item, donor_name) if isinstance(item, dict) else item
                for item in c_val
            ]
        elif isinstance(c_val, dict):
            tagged[c_key] = _tag_provider(c_val, donor_name)
        else:
            tagged[c_key] = c_val
    return tagged


def _merge_providers_meta(base_dict: Dict[str, Any], overlay_dict: Dict[str, Any]) -> None:
    """合併兩個字典之 __providers__ 清單並更新最新 __provider__。"""
    base_providers: List[str] = []
    if isinstance(base_dict.get("__providers__"), list):
        base_providers.extend(str(p) for p in base_dict["__providers__"])
    elif "__provider__" in base_dict:
        base_providers.append(str(base_dict["__provider__"]))

    overlay_providers: List[str] = []
    if isinstance(overlay_dict.get("__providers__"), list):
        overlay_providers.extend(str(p) for p in overlay_dict["__providers__"])
    elif "__provider__" in overlay_dict:
        overlay_providers.append(str(overlay_dict["__provider__"]))

    combined: List[str] = []
    seen_p: Set[str] = set()
    for p in base_providers + overlay_providers:
        if p not in seen_p:
            seen_p.add(p)
            combined.append(p)

    if combined:
        base_dict["__providers__"] = combined
    if "__provider__" in overlay_dict:
        base_dict["__provider__"] = overlay_dict["__provider__"]


def _resolve_schema_for_key(
    schema: Any,
    key: str,
    types_map: Dict[str, Any],
) -> Tuple[Optional[str], Any]:
    """根據當前層級之 _format.json schema 解析指定 key 的 (merge_strategy, child_schema)。"""
    if schema is None:
        return None, None

    from core.validator import ContributesValidator

    cur_schema = schema
    if isinstance(cur_schema, str):
        rule = ContributesValidator.parse_type_signature(cur_schema)
        if rule["type"] == "ref" and rule["ref_name"] in types_map:
            cur_schema = types_map[rule["ref_name"]]
    elif isinstance(cur_schema, dict) and "$ref" in cur_schema:
        ref_name = str(cur_schema["$ref"]).lstrip("$")
        if ref_name in types_map:
            cur_schema = types_map[ref_name]

    if not isinstance(cur_schema, dict):
        return None, None

    raw_spec = cur_schema.get(key) if key in cur_schema else cur_schema.get("*")
    if raw_spec is None:
        return None, None

    if isinstance(raw_spec, dict) and "format" in raw_spec and "description" in raw_spec:
        point_strategy = raw_spec.get("merge") if isinstance(raw_spec.get("merge"), str) else None
        fmt_spec = raw_spec["format"]
        if isinstance(fmt_spec, str):
            rule = ContributesValidator.parse_type_signature(fmt_spec)
            strat = point_strategy or rule.get("merge_strategy")
            child = types_map.get(rule["ref_name"]) if rule["type"] == "ref" else fmt_spec
            return strat, child
        return point_strategy, fmt_spec

    if isinstance(raw_spec, str):
        rule = ContributesValidator.parse_type_signature(raw_spec)
        strat = rule.get("merge_strategy")
        child = types_map.get(rule["ref_name"]) if rule["type"] == "ref" else raw_spec
        return strat, child

    if isinstance(raw_spec, dict):
        strat = raw_spec.get("_merge") if isinstance(raw_spec.get("_merge"), str) else None
        return strat, raw_spec

    if isinstance(raw_spec, list):
        return None, (raw_spec[0] if raw_spec else None)

    return None, None


def _extend_list_dedup(target_list: List[Any], incoming_list: List[Any]) -> None:
    """Extends `target_list` with deduplicated elements from `incoming_list` using an $O(1)$ set for hashable scalars."""
    seen_hashable: Set[Any] = set()
    for existing_item in target_list:
        if not isinstance(existing_item, (dict, list)):
            try:
                seen_hashable.add((type(existing_item), existing_item))
            except TypeError:
                pass

    for x in incoming_list:
        if isinstance(x, (dict, list)):
            if x not in target_list:
                target_list.append(copy.deepcopy(x))
        else:
            try:
                h_key = (type(x), x)
                if h_key not in seen_hashable:
                    seen_hashable.add(h_key)
                    target_list.append(x)
            except TypeError:
                if x not in target_list:
                    target_list.append(x)


def _deep_merge(
    base: Dict[str, Any],
    overlay: Dict[str, Any],
    schema: Optional[Any] = None,
    types_map: Optional[Dict[str, Any]] = None,
    is_project_override: bool = False,
    raw_overlay: Optional[Dict[str, Any]] = None,
) -> None:
    """
    深層合併 overlay 至 base：
    支援依據目標模組 _format.json 宣告之 merge / extend / replace / unique 策略執行合併，
    並自動累積去重之 __providers__ 來源清單。
    """
    if types_map is None and isinstance(schema, dict) and "_types" in schema:
        raw_types = schema.get("_types")
        types_map = raw_types if isinstance(raw_types, dict) else {}

    _merge_providers_meta(base, overlay)

    for k, v in overlay.items():
        if k in ("__provider__", "__providers__"):
            continue

        strat, child_schema = _resolve_schema_for_key(schema, k, types_map or {})

        if k in base:
            if raw_overlay is not None and isinstance(raw_overlay, dict) and k not in raw_overlay:
                continue
            child_raw = raw_overlay.get(k) if isinstance(raw_overlay, dict) else None

            if strat == "unique" and not is_project_override:
                existing_donor = (
                    base[k].get("__provider__", "existing")
                    if isinstance(base[k], dict)
                    else "existing"
                )
                new_donor = (
                    v.get("__provider__", "overlay")
                    if isinstance(v, dict)
                    else "overlay"
                )
                log_warn(
                    f"Contributes unique key collision on '{k}': keeping '{existing_donor}', ignoring '{new_donor}'.",
                    stream="stderr",
                )
                continue

            if isinstance(base[k], dict) and isinstance(v, dict):
                eff_strat = strat or "merge"
                if eff_strat == "replace":
                    replaced = copy.deepcopy(v)
                    if isinstance(base[k].get("__providers__"), list) or "__provider__" in base[k]:
                        prev_meta: Dict[str, Any] = {}
                        if isinstance(base[k].get("__providers__"), list):
                            prev_meta["__providers__"] = list(base[k]["__providers__"])
                        elif "__provider__" in base[k]:
                            prev_meta["__provider__"] = base[k]["__provider__"]
                        _merge_providers_meta(prev_meta, replaced)
                        replaced["__providers__"] = prev_meta["__providers__"]
                        if "__provider__" in prev_meta:
                            replaced["__provider__"] = prev_meta["__provider__"]
                    base[k] = replaced
                else:
                    _deep_merge(
                        base[k],
                        v,
                        schema=child_schema,
                        types_map=types_map,
                        is_project_override=is_project_override,
                        raw_overlay=child_raw,
                    )
            elif isinstance(base[k], list) and isinstance(v, list):
                eff_strat = strat or "extend"
                if eff_strat == "replace":
                    base[k] = copy.deepcopy(v)
                else:
                    _extend_list_dedup(base[k], v)
            else:
                base[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
        else:
            base[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v


def _get_contributes_meta_uri() -> str:
    """返回 contributes 快照元資料存儲 URI。"""
    return "cache://core/contributes.meta.json"


# Short window (seconds) within which consecutive get() calls skip full directory walk
# provided contributes.meta.json and contributes.merged.json mtimes have not changed.
_CLEAN_SCAN_WINDOW_SEC: float = 0.25


def _get_merged_memory_cache() -> Dict[Tuple[str, str], Tuple[float, float, Dict[str, Any]]]:
    return get_runtime_context().contributes_merged_cache


def _get_json_file_cache() -> Dict[str, Tuple[int, int, Any]]:
    return get_runtime_context().contributes_json_file_cache


def _get_last_clean_scan_ts() -> Dict[str, Tuple[float, float]]:
    return get_runtime_context().contributes_last_clean_scan_ts


def _read_json_cached(path_or_uri: str) -> Any:
    """
    Reads and parses a JSON file with an in-memory ``(norm_path, st_mtime_ns, st_size)`` cache
    to eliminate repeated disk I/O across a single CLI lifecycle.
    """
    resolved = uri.resolve(path_or_uri, interactive=False) if "://" in str(path_or_uri) else str(path_or_uri)
    norm_path = os.path.normpath(os.path.abspath(resolved))
    json_cache = _get_json_file_cache()
    try:
        st = os.stat(norm_path)
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        size = st.st_size
    except OSError:
        json_cache.pop(norm_path, None)
        return vfs.read_json(path_or_uri)

    cached = json_cache.get(norm_path)
    if cached is not None and cached[0] == mtime_ns and cached[1] == size:
        return copy.deepcopy(cached[2])

    data = vfs.read_json(path_or_uri)
    json_cache[norm_path] = (mtime_ns, size, copy.deepcopy(data))
    return data


def invalidate_cache(target_module: Optional[str] = None) -> None:
    """
    手動清空 contributes 程序內記憶體快取與免掃時窗標記。
    若指定 target_module 則僅清除該目標模組之已合併字典快取，並重置免掃時窗。
    """
    _get_last_clean_scan_ts().clear()
    _get_json_file_cache().clear()
    merged_cache = _get_merged_memory_cache()
    ctx = get_runtime_context()
    ctx.uri_token_map_cache.clear()
    if target_module:
        stale_keys = [k for k in merged_cache if k[1] == target_module]
        for k in stale_keys:
            merged_cache.pop(k, None)
        if target_module == "core":
            ctx.uri_schemes_cache.clear()
    else:
        merged_cache.clear()
        ctx.uri_schemes_cache.clear()


def _safe_file_mtime(file_path: str) -> float:
    """安全取得實體檔案 mtime，不存在時回傳 0.0。"""
    try:
        return os.stat(file_path).st_mtime
    except OSError:
        return 0.0


def _record_file_stat(files_snapshot: Dict[str, Tuple[float, int]], file_path: str) -> None:
    """若實體檔案存在，記錄其 (mtime, size) 至快照字典。"""
    if os.path.isfile(file_path):
        st = os.stat(file_path)
        files_snapshot[file_path] = (st.st_mtime, st.st_size)


def _scan_donor_contributes_files(donor: str, files_snapshot: Dict[str, Tuple[float, int]]) -> None:
    """掃描單一模組之 contributes/*.json、語系檔、開發源碼 _format.json fallback 與單一 contributes.json。"""
    donor_contrib_dir = f"module://{donor}/contributes"
    if vfs.exists(donor_contrib_dir) and vfs.is_dir(donor_contrib_dir):
        try:
            for fname in vfs.listdir(donor_contrib_dir):
                if not fname.endswith(".json"):
                    continue
                f_uri = f"{donor_contrib_dir}/{fname}"
                try:
                    f_p = uri.resolve(f_uri, interactive=False)
                    _record_file_stat(files_snapshot, f_p)
                    if fname == "core.json" and os.path.isfile(f_p):
                        c_obj = _read_json_cached(f_uri)
                        locales_decl = c_obj.get("locales") if isinstance(c_obj, dict) else None
                        if isinstance(locales_decl, dict):
                            mod_root = uri.resolve(f"module://{donor}", interactive=False)
                            for l_key, rel_p in locales_decl.items():
                                if not l_key.startswith("_") and isinstance(rel_p, str):
                                    loc_f = os.path.normpath(os.path.join(mod_root, rel_p))
                                    _record_file_stat(files_snapshot, loc_f)
                except Exception:
                    pass
        except Exception:
            pass

    if not vfs.exists(f"module://{donor}/contributes/_format.json"):
        try:
            src_fmt_p = uri.resolve(f"module.source://{donor}/contributes/_format.json", interactive=False)
            _record_file_stat(files_snapshot, src_fmt_p)
        except Exception:
            pass

    donor_unified = f"module://{donor}/contributes.json"
    if vfs.exists(donor_unified):
        try:
            _record_file_stat(files_snapshot, uri.resolve(donor_unified, interactive=False))
        except Exception:
            pass


def _scan_contributes_inputs() -> Dict[str, Tuple[float, int]]:
    """
    掃描所有影響 contributes 聚合之輸入檔案，取得其實體絕對路徑與 (mtime, size) 快照。
    """
    files_snapshot: Dict[str, Tuple[float, int]] = {}

    try:
        _record_file_stat(files_snapshot, uri.resolve("yscb.host://yscb.config.json", interactive=False))
    except Exception:
        pass

    if vfs.exists("module://"):
        try:
            for donor in (d for d in vfs.listdir("module://") if not d.startswith(".")):
                _scan_donor_contributes_files(donor, files_snapshot)
        except Exception:
            pass

    if vfs.exists("config://"):
        try:
            for tgt in vfs.listdir("config://"):
                p_uri = f"config://{tgt}/contribute.json"
                if vfs.exists(p_uri):
                    try:
                        p_abs = uri.resolve(p_uri, interactive=False)
                        _record_file_stat(files_snapshot, p_abs)
                        if tgt == "core" and os.path.isfile(p_abs):
                            c_obj = _read_json_cached(p_uri)
                            if isinstance(c_obj, dict):
                                core_body = c_obj.get("core", c_obj)
                                locales_decl = core_body.get("locales") if isinstance(core_body, dict) else None
                                if isinstance(locales_decl, dict):
                                    cfg_core_root = uri.resolve("config://core", interactive=False)
                                    for l_key, rel_p in locales_decl.items():
                                        if not l_key.startswith("_") and isinstance(rel_p, str):
                                            loc_f = os.path.normpath(os.path.join(cfg_core_root, rel_p))
                                            _record_file_stat(files_snapshot, loc_f)
                    except Exception:
                        pass
        except Exception:
            pass

    return files_snapshot


def _is_contributes_dirty(target_module: Optional[str] = None) -> Tuple[bool, Dict[str, Tuple[float, int]]]:
    """
    嗅探 JIT 快照是否 dirty：
    1. 若指定 target_module，且其 cache://{target_module}/contributes.merged.json 缺失，直接視為 dirty。
    2. 檢查 cache://core/contributes.meta.json 是否存在。
    3. 比對即時掃描之檔案 (mtime, size) 與快取清單。
    返回 (is_dirty, current_snapshot)。
    """
    prev_reentrancy = getattr(uri._URI_REENTRANCY, "active", False)
    uri._URI_REENTRANCY.active = True
    try:
        if target_module:
            target_cache_uri = f"cache://{target_module}/contributes.merged.json"
            if not vfs.exists(target_cache_uri):
                return True, {}

        meta_uri = _get_contributes_meta_uri()
        if not vfs.exists(meta_uri):
            return True, {}

        try:
            meta_data = vfs.read_json(meta_uri)
            if not isinstance(meta_data, dict) or "files" not in meta_data:
                return True, {}
            cached_files = meta_data["files"]
        except Exception:
            return True, {}

        current_snapshot = _scan_contributes_inputs()
        if set(current_snapshot.keys()) != set(cached_files.keys()):
            return True, current_snapshot

        for p, (cur_mtime, cur_size) in current_snapshot.items():
            cached_val = cached_files.get(p)
            if not cached_val or len(cached_val) < 2:
                return True, current_snapshot
            if cur_mtime != cached_val[0] or cur_size != cached_val[1]:
                return True, current_snapshot

        return False, current_snapshot
    finally:
        uri._URI_REENTRANCY.active = prev_reentrancy


def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    標準 Contributes 查詢 SDK (支援程序內記憶體快取、JIT 變更嗅探與熱自愈):
    查詢指定目標模組之已合併 Contributes 字典或特定鍵值。
    """
    try:
        yscb_root = uri.resolve_yscb_root()
    except Exception:
        yscb_root = ""

    cache_file = f"cache://{target_module}/contributes.merged.json"
    meta_uri = _get_contributes_meta_uri()
    cache_key = (yscb_root, target_module)

    try:
        meta_abs = os.path.join(yscb_root, ".cache", "core", "contributes.meta.json") if yscb_root else uri.resolve(meta_uri, interactive=False)
        merged_abs = os.path.join(yscb_root, ".cache", target_module, "contributes.merged.json") if yscb_root else uri.resolve(cache_file, interactive=False)
    except Exception:
        meta_abs = ""
        merged_abs = ""

    meta_mtime = _safe_file_mtime(meta_abs) if meta_abs else 0.0
    merged_mtime = _safe_file_mtime(merged_abs) if merged_abs else 0.0

    now_mono = time.monotonic()
    merged_cache = _get_merged_memory_cache()
    last_clean_map = _get_last_clean_scan_ts()
    cached_entry = merged_cache.get(cache_key)
    last_clean = last_clean_map.get(yscb_root)

    if (
        cached_entry is not None
        and meta_mtime > 0.0
        and merged_mtime > 0.0
        and cached_entry[0] == meta_mtime
        and cached_entry[1] == merged_mtime
        and last_clean is not None
        and last_clean[0] == meta_mtime
        and (now_mono - last_clean[1]) < _CLEAN_SCAN_WINDOW_SEC
    ):
        data = cached_entry[2]
        res = data.get(key, default) if key is not None else (data if data else default)
        return copy.deepcopy(res) if isinstance(res, (dict, list)) else res

    is_dirty, _ = _is_contributes_dirty(target_module)
    data = None
    if not is_dirty:
        meta_mtime = _safe_file_mtime(meta_abs) if meta_abs else 0.0
        merged_mtime = _safe_file_mtime(merged_abs) if merged_abs else 0.0
        if meta_mtime > 0.0:
            last_clean_map[yscb_root] = (meta_mtime, time.monotonic())
        if (
            cached_entry is not None
            and meta_mtime > 0.0
            and merged_mtime > 0.0
            and cached_entry[0] == meta_mtime
            and cached_entry[1] == merged_mtime
        ):
            data = cached_entry[2]
        else:
            prev_re = getattr(uri._URI_REENTRANCY, "active", False)
            uri._URI_REENTRANCY.active = True
            try:
                if vfs.exists(cache_file):
                    loaded = vfs.read_json(cache_file)
                    if isinstance(loaded, dict):
                        data = loaded
                        if meta_mtime > 0.0 and merged_mtime > 0.0:
                            merged_cache[cache_key] = (meta_mtime, merged_mtime, data)
            except Exception:
                data = None
            finally:
                uri._URI_REENTRANCY.active = prev_re

    if data is None or not isinstance(data, dict):
        aggregator = ContributesAggregator()
        all_merged = aggregator.scan_and_inject()
        data = all_merged.get(target_module, {})
        meta_mtime = _safe_file_mtime(meta_abs) if meta_abs else 0.0
        merged_mtime = _safe_file_mtime(merged_abs) if merged_abs else 0.0
        if meta_mtime > 0.0:
            last_clean_map[yscb_root] = (meta_mtime, time.monotonic())
            if merged_mtime > 0.0 and isinstance(data, dict):
                merged_cache[cache_key] = (meta_mtime, merged_mtime, data)

    res = data.get(key, default) if key is not None else (data if data else default)
    return copy.deepcopy(res) if isinstance(res, (dict, list)) else res


def get_merged_contributes(target_module: str = "core") -> Dict[str, Any]:
    """Returns the full merged contributes dictionary for `target_module` via the canonical SSOT aggregator."""
    res = get(target_module, key=None, default={})
    return res if isinstance(res, dict) else {}


def get_format(module: str) -> Optional[Dict[str, Any]]:
    """讀取並返回指定目標模組之 contributes/_format.json 字典，若不存在則返回 None。"""
    fmt_uri = f"module://{module}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        fmt_uri = f"module.source://{module}/contributes/_format.json"
    if vfs.exists(fmt_uri):
        try:
            data = _read_json_cached(fmt_uri)
            if isinstance(data, dict):
                return data
        except Exception as e:
            log_warn(f"Failed to read format schema for '{module}' at '{fmt_uri}': {e}", stream="stderr")
    return None


def validate(target_module: str, payload: Dict[str, Any], donor_module: str = "") -> Any:
    """便捷 SDK: 自動定位 target_module 之 _format.json 並執行剛性校驗。"""
    from core.validator import ContributesValidator
    fmt = get_format(target_module)
    return ContributesValidator.validate(target_module, payload, donor_mod=donor_module, format_schema=fmt, strict_points=True)


def list_points(module: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    查詢生態系開放之擴充點清單。
    回傳 [{"module": str, "point": str, "description": str, "format_type": str}, ...]
    """
    installed = [module] if module else ([d for d in vfs.listdir("module://") if not d.startswith(".")] if vfs.exists("module://") else [])
    if not installed and vfs.exists("module.source://"):
        try:
            installed = vfs.listdir("module.source://")
        except Exception:
            installed = []
    results: List[Dict[str, Any]] = []
    for mod in installed:
        fmt = get_format(mod)
        if not fmt:
            continue
        for k, v in fmt.items():
            if k.startswith("_"):
                continue
            desc = v.get("description", "") if isinstance(v, dict) else ""
            f_spec = v.get("format") if isinstance(v, dict) else v
            f_type = "list" if isinstance(f_spec, list) else ("dict" if isinstance(f_spec, dict) else str(f_spec))
            results.append({
                "module": mod,
                "point": k,
                "description": desc,
                "format_type": f_type,
            })
    return results


class ContributesAggregator:
    """
    Contributes 雙階聚合引擎：
    負責掃描已安裝模組的 contributes/<target>.json 宣告與專案級組態，
    執行拓撲合併，並物化寫入 cache://{module}/contributes.merged.json。
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _resolve_donor_order(installed_modules: List[str], topological_order: Optional[List[str]]) -> List[str]:
        """計算模組 contributes 合併之拓撲遍歷順序。"""
        if topological_order:
            ordered = [m for m in topological_order if m in installed_modules]
            for m in installed_modules:
                if m not in ordered:
                    ordered.append(m)
            return ordered
        ordered = ["core"] if "core" in installed_modules else []
        for m in sorted(installed_modules):
            if m not in ordered:
                ordered.append(m)
        return ordered

    @staticmethod
    def _merge_validated_donor_target(
        donor: str,
        target: str,
        c_data: Dict[str, Any],
        aggregated: Dict[str, Dict[str, Any]],
        core_modules_commands: Dict[str, Any],
        core_modules_locales: Dict[str, Any],
    ) -> None:
        """驗證單一 donor 對 target 的 contributes 資料並合併至 aggregated[target]。"""
        aggregated.setdefault(target, {})
        val_res = validate(target, c_data, donor_module=donor)
        if not val_res.is_valid:
            log_warn(f"Contributes validation failed for donor '{donor}' -> target '{target}':", stream="stderr")
            for err in val_res.errors:
                log_warn(f"  [{err.path}] {err.message} ({err.suggestion or ''})", stream="stderr")
        valid_body = val_res.payload if val_res.payload is not None else c_data
        tagged_body = _tag_payload_body(valid_body, donor)

        if target == "core" and "commands" in tagged_body:
            if donor in core_modules_commands and isinstance(core_modules_commands[donor], dict) and isinstance(tagged_body["commands"], dict):
                _deep_merge(core_modules_commands[donor], copy.deepcopy(tagged_body["commands"]))
            else:
                core_modules_commands[donor] = copy.deepcopy(tagged_body["commands"])
        if target == "core" and "locales" in tagged_body and isinstance(tagged_body["locales"], dict):
            core_modules_locales[donor] = copy.deepcopy(tagged_body["locales"])

        fmt_schema = get_format(target)
        _deep_merge(
            aggregated[target],
            tagged_body,
            schema=fmt_schema,
            is_project_override=False,
            raw_overlay=c_data,
        )
        if target == "core" and core_modules_commands:
            aggregated[target].setdefault("commands", {})["__modules__"] = core_modules_commands
        if target == "core" and core_modules_locales:
            aggregated[target].setdefault("locales", {})["__modules__"] = core_modules_locales

    def _collect_donor_contributes(
        self,
        donor: str,
        aggregated: Dict[str, Dict[str, Any]],
        core_modules_commands: Dict[str, Any],
        core_modules_locales: Dict[str, Any],
    ) -> None:
        """收集單一模組之 contributes/<target>.json 與單一 contributes.json 並合併。"""
        donor_contrib_dir = f"module://{donor}/contributes"
        if vfs.exists(donor_contrib_dir) and vfs.is_dir(donor_contrib_dir):
            try:
                for filename in vfs.listdir(donor_contrib_dir):
                    if not filename.endswith(".json") or filename.startswith("_"):
                        continue
                    target = filename[:-5]
                    if target == "commands":
                        target = "core"
                    aggregated.setdefault(target, {})
                    target_file_uri = f"{donor_contrib_dir}/{filename}"
                    try:
                        c_data = _read_json_cached(target_file_uri)
                        if isinstance(c_data, dict):
                            self._merge_validated_donor_target(
                                donor, target, c_data, aggregated, core_modules_commands, core_modules_locales
                            )
                    except Exception as e:
                        log_warn(f"Failed to read contributes file '{target_file_uri}': {e}", stream="stderr")
            except Exception as e:
                log_warn(f"Failed to scan donor contributes dir '{donor_contrib_dir}': {e}", stream="stderr")

        donor_unified_file = f"module://{donor}/contributes.json"
        if vfs.exists(donor_unified_file):
            try:
                u_data = _read_json_cached(donor_unified_file)
                if isinstance(u_data, dict):
                    if "commands" in u_data and isinstance(u_data["commands"], dict) and not any(
                        isinstance(v, dict) and "commands" in v for v in u_data.values()
                    ):
                        self._merge_validated_donor_target(
                            donor, "core", u_data, aggregated, core_modules_commands, core_modules_locales
                        )
                    else:
                        for target, c_body in u_data.items():
                            if isinstance(c_body, dict):
                                eff_target = "core" if target == "commands" else target
                                self._merge_validated_donor_target(
                                    donor, eff_target, c_body, aggregated, core_modules_commands, core_modules_locales
                                )
            except Exception:
                pass

    def _apply_project_overrides_and_persist(
        self,
        aggregated: Dict[str, Dict[str, Any]],
        core_modules_locales: Dict[str, Any],
    ) -> None:
        """疊加專案層級 config://<target>/contribute.json 並物化至 cache://。"""
        if vfs.exists("config://"):
            try:
                for cfg_tgt in vfs.listdir("config://"):
                    if vfs.exists(f"config://{cfg_tgt}/contribute.json"):
                        aggregated.setdefault(cfg_tgt, {})
            except Exception:
                pass

        for target in list(aggregated.keys()):
            local_contrib_uri = f"config://{target}/contribute.local.json"
            if vfs.exists(local_contrib_uri):
                log_warn(
                    f"Ignoring '{local_contrib_uri}': project contribute overrides must be tracked by Git (no local overrides allowed).",
                    stream="stderr",
                )

            proj_contrib_uri = f"config://{target}/contribute.json"
            if vfs.exists(proj_contrib_uri):
                try:
                    c_data = _read_json_cached(proj_contrib_uri)
                    if isinstance(c_data, dict):
                        target_overlay = c_data.get(target, c_data)
                        if isinstance(target_overlay, dict):
                            val_res = validate(target, target_overlay, donor_module="project_override")
                            if not val_res.is_valid:
                                log_warn(
                                    f"Contributes validation failed for project override 'config://{target}/contribute.json':",
                                    stream="stderr",
                                )
                                for err in val_res.errors:
                                    log_warn(f"  [{err.path}] {err.message} ({err.suggestion or ''})", stream="stderr")
                            valid_overlay = val_res.payload if val_res.payload is not None else target_overlay
                            tagged_overlay = _tag_payload_body(valid_overlay, "project")
                            if target == "core" and "locales" in tagged_overlay and isinstance(tagged_overlay["locales"], dict):
                                core_modules_locales["project"] = copy.deepcopy(tagged_overlay["locales"])
                            fmt_schema = get_format(target)
                            _deep_merge(
                                aggregated[target],
                                tagged_overlay,
                                schema=fmt_schema,
                                is_project_override=True,
                                raw_overlay=target_overlay,
                            )
                            if target == "core" and core_modules_locales:
                                aggregated[target].setdefault("locales", {})["__modules__"] = core_modules_locales
                except Exception as e:
                    log_warn(f"Failed to read project contribute override '{proj_contrib_uri}': {e}", stream="stderr")

            target_cache_uri = f"cache://{target}/contributes.merged.json"
            if aggregated[target]:
                vfs.makedirs(f"cache://{target}", exist_ok=True)
                vfs.write_json(target_cache_uri, aggregated[target], atomic=True)
            elif vfs.exists(target_cache_uri):
                try:
                    vfs.remove(target_cache_uri, missing_ok=True)
                except Exception:
                    pass

        try:
            meta_uri = _get_contributes_meta_uri()
            current_snapshot = _scan_contributes_inputs()
            meta_payload = {
                "updated_at": time.time(),
                "files": {k: [v[0], v[1]] for k, v in current_snapshot.items()},
            }
            vfs.makedirs("cache://core", exist_ok=True)
            vfs.write_json(meta_uri, meta_payload, atomic=True)
        except Exception as e:
            log_warn(f"Failed to update contributes.meta.json: {e}", stream="stderr")

    def scan_and_inject(self, topological_order: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        掃描所有 installed_modules 之 contributes/<target>.json，
        依拓撲排序 (topological_order) 依序合併，自動注入 __provider__，
        最後疊加 config:// 專案特化宣告並寫入快取。
        """
        with cell_span("contributes.rebuild"):
            aggregated: Dict[str, Dict[str, Any]] = {}
            installed_modules = [d for d in vfs.listdir("module://") if not d.startswith(".")] if vfs.exists("module://") else []
            if not installed_modules:
                return aggregated

            ordered_donors = self._resolve_donor_order(installed_modules, topological_order)
            for mod in installed_modules:
                aggregated[mod] = {}
            core_modules_commands: Dict[str, Any] = {}
            core_modules_locales: Dict[str, Any] = {}

            for donor in ordered_donors:
                self._collect_donor_contributes(donor, aggregated, core_modules_commands, core_modules_locales)

            self._apply_project_overrides_and_persist(aggregated, core_modules_locales)
            invalidate_cache()
            return aggregated


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    ctx = get_runtime_context()
    if name == "_MERGED_MEMORY_CACHE":
        return ctx.contributes_merged_cache
    if name == "_JSON_FILE_CACHE":
        return ctx.contributes_json_file_cache
    if name == "_LAST_CLEAN_SCAN_TS":
        return ctx.contributes_last_clean_scan_ts
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
