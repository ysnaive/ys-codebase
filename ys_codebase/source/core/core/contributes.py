"""
Contributes Aggregator and Dependency Injection Engine.
Rigid Topology & Zero Speculation: strictly scans installed modules in module://.
Standard Directory: module://<donor>/contributes/<target>.json
Project Overrides: config://<target>/config.project.json
"""
from typing import Dict, Any, List, Optional, Tuple
import os
import copy
import time
import logging
from core import uri
from core import vfs

logger = logging.getLogger("core.contributes")


def _tag_provider(data: Any, donor_name: str) -> Any:
    """
    遞迴為 contributes 宣告中的 Dict 與 List[Dict] 項目注入 __provider__ 標記。
    若物件已顯式宣告 __provider__ 則予以保留不覆蓋。
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                result[k] = _tag_provider(v, donor_name)
            else:
                result[k] = v
        if "__provider__" not in result:
            result["__provider__"] = donor_name
        return result
    if isinstance(data, list):
        return [_tag_provider(item, donor_name) for item in data]
    return data


def _tag_payload_body(body: Dict[str, Any], donor_name: str) -> Dict[str, Any]:
    """對整個 contributes 單檔頂層字典的各擴充點內容遞迴注入 __provider__。"""
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


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    """深層合併 overlay 至 base（Dict 遞迴合併，List 依序去重擴展）。"""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        elif k in base and isinstance(base[k], list) and isinstance(v, list):
            base[k].extend(x for x in v if x not in base[k])
        else:
            base[k] = v


def _get_contributes_meta_uri() -> str:
    """返回 contributes 快照元資料存儲 URI。"""
    return "cache://core/contributes.meta.json"


def _record_file_stat(files_snapshot: Dict[str, Tuple[float, int]], file_path: str) -> None:
    """若實體檔案存在，記錄其 (mtime, size) 至快照字典。"""
    if os.path.isfile(file_path):
        st = os.stat(file_path)
        files_snapshot[file_path] = (st.st_mtime, st.st_size)


def _scan_donor_contributes_files(donor: str, files_snapshot: Dict[str, Tuple[float, int]]) -> None:
    """掃描單一模組之 contributes/*.json、語系檔與單一 contributes.json。"""
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
                        c_obj = vfs.read_json(f_uri)
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
        _record_file_stat(files_snapshot, uri.resolve("project://yscb.config.json", interactive=False))
    except Exception:
        pass

    if vfs.exists("module://"):
        try:
            for donor in vfs.listdir("module://"):
                _scan_donor_contributes_files(donor, files_snapshot)
        except Exception:
            pass

    if vfs.exists("config://"):
        try:
            for tgt in vfs.listdir("config://"):
                p_uri = f"config://{tgt}/contribute.json"
                if vfs.exists(p_uri):
                    try:
                        _record_file_stat(files_snapshot, uri.resolve(p_uri, interactive=False))
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


def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    標準 Contributes 查詢 SDK (支援 JIT 變更嗅探與熱自愈):
    查詢指定目標模組之已合併 Contributes 字典或特定鍵值。
    """
    cache_file = f"cache://{target_module}/contributes.merged.json"
    is_dirty, _ = _is_contributes_dirty(target_module)
    data = None
    if not is_dirty and vfs.exists(cache_file):
        try:
            data = vfs.read_json(cache_file)
        except Exception:
            data = None

    if data is None or not isinstance(data, dict):
        aggregator = ContributesAggregator()
        all_merged = aggregator.scan_and_inject()
        data = all_merged.get(target_module, {})

    if key is not None:
        return data.get(key, default)
    return data if data else default


def get_format(module: str) -> Optional[Dict[str, Any]]:
    """讀取並返回指定目標模組之 contributes/_format.json 字典，若不存在則返回 None。"""
    fmt_uri = f"module://{module}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        fmt_uri = f"module.source://{module}/contributes/_format.json"
    if vfs.exists(fmt_uri):
        try:
            data = vfs.read_json(fmt_uri)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"Failed to read format schema for '{module}' at '{fmt_uri}': {e}")
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
    installed = [module] if module else (vfs.listdir("module://") if vfs.exists("module://") else [])
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
                    aggregated.setdefault(target, {})
                    target_file_uri = f"{donor_contrib_dir}/{filename}"
                    try:
                        c_data = vfs.read_json(target_file_uri)
                        if isinstance(c_data, dict):
                            val_res = validate(target, c_data, donor_module=donor)
                            if not val_res.is_valid:
                                logger.warning(f"Contributes validation failed for donor '{donor}' -> target '{target}':")
                                for err in val_res.errors:
                                    logger.warning(f"  [{err.path}] {err.message} ({err.suggestion or ''})")
                            valid_body = val_res.payload if val_res.payload is not None else c_data
                            tagged_body = _tag_payload_body(valid_body, donor)

                            if target == "core" and "commands" in tagged_body:
                                core_modules_commands[donor] = copy.deepcopy(tagged_body["commands"])
                            if target == "core" and "locales" in tagged_body and isinstance(tagged_body["locales"], dict):
                                core_modules_locales[donor] = copy.deepcopy(tagged_body["locales"])

                            _deep_merge(aggregated[target], tagged_body)
                            if target == "core" and core_modules_commands:
                                aggregated[target].setdefault("commands", {})["__modules__"] = core_modules_commands
                            if target == "core" and core_modules_locales:
                                aggregated[target].setdefault("locales", {})["__modules__"] = core_modules_locales
                    except Exception as e:
                        logger.warning(f"Failed to read contributes file '{target_file_uri}': {e}")
            except Exception as e:
                logger.warning(f"Failed to scan donor contributes dir '{donor_contrib_dir}': {e}")

        donor_unified_file = f"module://{donor}/contributes.json"
        if vfs.exists(donor_unified_file):
            try:
                u_data = vfs.read_json(donor_unified_file)
                if isinstance(u_data, dict):
                    for target, c_body in u_data.items():
                        if isinstance(c_body, dict):
                            aggregated.setdefault(target, {})
                            _deep_merge(aggregated[target], _tag_payload_body(c_body, donor))
            except Exception:
                pass

    def _apply_project_overrides_and_persist(
        self,
        aggregated: Dict[str, Dict[str, Any]],
        core_modules_locales: Dict[str, Any],
    ) -> None:
        """疊加專案層級 config://<target>/contribute.json 並物化至 cache://。"""
        for target in list(aggregated.keys()):
            local_contrib_uri = f"config://{target}/contribute.local.json"
            if vfs.exists(local_contrib_uri):
                logger.warning(
                    f"Ignoring '{local_contrib_uri}': project contribute overrides must be tracked by Git (no local overrides allowed)."
                )

            proj_contrib_uri = f"config://{target}/contribute.json"
            if vfs.exists(proj_contrib_uri):
                try:
                    c_data = vfs.read_json(proj_contrib_uri)
                    if isinstance(c_data, dict):
                        target_overlay = c_data.get(target, c_data)
                        if isinstance(target_overlay, dict):
                            val_res = validate(target, target_overlay, donor_module="project_override")
                            if not val_res.is_valid:
                                logger.warning(f"Contributes validation failed for project override 'config://{target}/contribute.json':")
                                for err in val_res.errors:
                                    logger.warning(f"  [{err.path}] {err.message} ({err.suggestion or ''})")
                            valid_overlay = val_res.payload if val_res.payload is not None else target_overlay
                            if target == "core" and "locales" in valid_overlay and isinstance(valid_overlay["locales"], dict):
                                core_modules_locales["project"] = copy.deepcopy(valid_overlay["locales"])
                            _deep_merge(aggregated[target], valid_overlay)
                            if target == "core" and core_modules_locales:
                                aggregated[target].setdefault("locales", {})["__modules__"] = core_modules_locales
                except Exception as e:
                    logger.warning(f"Failed to read project contribute override '{proj_contrib_uri}': {e}")

            target_cache_uri = f"cache://{target}/contributes.merged.json"
            if aggregated[target]:
                vfs.makedirs(f"cache://{target}", exist_ok=True)
                vfs.write_json(target_cache_uri, aggregated[target])
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
            vfs.write_json(meta_uri, meta_payload)
        except Exception as e:
            logger.warning(f"Failed to update contributes.meta.json: {e}")

    def scan_and_inject(self, topological_order: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        掃描所有 installed_modules 之 contributes/<target>.json，
        依拓撲排序 (topological_order) 依序合併，自動注入 __provider__，
        最後疊加 config:// 專案特化宣告並寫入快取。
        """
        aggregated: Dict[str, Dict[str, Any]] = {}
        installed_modules = vfs.listdir("module://") if vfs.exists("module://") else []
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
        return aggregated

