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
        # 如果是業務宣告物件 (非頂層分類鍵值，如 export/insert/token 清單裡的項目)
        if "__provider__" not in result:
            result["__provider__"] = donor_name
        return result
    elif isinstance(data, list):
        return [_tag_provider(item, donor_name) for item in data]
    return data


def _get_contributes_meta_uri() -> str:
    """返回 contributes 快照元資料存儲 URI。"""
    return "cache://core/contributes.meta.json"


def _scan_contributes_inputs() -> Dict[str, Tuple[float, int]]:
    """
    掃描所有影響 contributes 聚合之輸入檔案，取得其實體絕對路徑與 (mtime, size) 快照。
    比對檔案包含：
    - yscb.config.json
    - module://*/contributes/*.json 與 module://*/contributes.json
    - config://*/contribute.json
    """
    files_snapshot: Dict[str, Tuple[float, int]] = {}

    # 1. 宿主設定 yscb.config.json
    try:
        cfg_p = uri.resolve("project://yscb.config.json", interactive=False)
        if os.path.isfile(cfg_p):
            st = os.stat(cfg_p)
            files_snapshot[cfg_p] = (st.st_mtime, st.st_size)
    except Exception:
        pass

    # 2. 模組層級 contributes
    if uri.exists("module://"):
        try:
            installed = uri.listdir("module://")
            for donor in installed:
                donor_contrib_dir = f"module://{donor}/contributes"
                if uri.exists(donor_contrib_dir) and uri.isdir(donor_contrib_dir):
                    try:
                        for fname in uri.listdir(donor_contrib_dir):
                            if fname.endswith(".json"):
                                f_uri = f"{donor_contrib_dir}/{fname}"
                                try:
                                    f_p = uri.resolve(f_uri, interactive=False)
                                    if os.path.isfile(f_p):
                                        st = os.stat(f_p)
                                        files_snapshot[f_p] = (st.st_mtime, st.st_size)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                donor_unified = f"module://{donor}/contributes.json"
                if uri.exists(donor_unified):
                    try:
                        f_p = uri.resolve(donor_unified, interactive=False)
                        if os.path.isfile(f_p):
                            st = os.stat(f_p)
                            files_snapshot[f_p] = (st.st_mtime, st.st_size)
                    except Exception:
                        pass
        except Exception:
            pass

    # 3. 專案特化 config://*/contribute.json
    if uri.exists("config://"):
        try:
            targets = uri.listdir("config://")
            for tgt in targets:
                p_uri = f"config://{tgt}/contribute.json"
                if uri.exists(p_uri):
                    try:
                        f_p = uri.resolve(p_uri, interactive=False)
                        if os.path.isfile(f_p):
                            st = os.stat(f_p)
                            files_snapshot[f_p] = (st.st_mtime, st.st_size)
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
        if not uri.exists(target_cache_uri):
            return True, {}

    meta_uri = _get_contributes_meta_uri()
    if not uri.exists(meta_uri):
        return True, {}

    try:
        meta_data = uri.read_json(meta_uri)
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
        cached_mtime, cached_size = cached_val[0], cached_val[1]
        if cur_mtime != cached_mtime or cur_size != cached_size:
            return True, current_snapshot

    return False, current_snapshot


def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    標準 Contributes 查詢 SDK (支援 JIT 變更嗅探與熱自愈):
    查詢指定目標模組之已合併 Contributes 字典或特定鍵值。
    
    1. 執行 JIT 嗅探 (_is_contributes_dirty)，檢查輸入檔案與快取狀態。
    2. 若未變更 (Clean)，優先從 cache://{target_module}/contributes.merged.json 讀取。
    3. 若 dirty 或快取損毀，自動調用 scan_and_inject() 即時自愈聚合並更新快照。
    4. 若指定 key 則返回該特定欄位，否則返回全字典。
    """
    cache_file = f"cache://{target_module}/contributes.merged.json"
    is_dirty, _ = _is_contributes_dirty(target_module)
    data = None
    if not is_dirty and uri.exists(cache_file):
        try:
            data = uri.read_json(cache_file)
        except Exception:
            data = None

    if data is None or not isinstance(data, dict):
        # 自愈聚合
        aggregator = ContributesAggregator()
        all_merged = aggregator.scan_and_inject()
        data = all_merged.get(target_module, {})

    if key is not None:
        return data.get(key, default)
    return data if data else default


def get_for_current_module(key: Optional[str] = None, default: Any = None) -> Any:
    """
    從當前活躍模組上下文獲取 Contributes 字典或特定鍵值。
    """
    curr_mod = uri.get_module_context() or "core"
    return get(curr_mod, key=key, default=default)


class ContributesAggregator:
    """
    Contributes 雙階聚合引擎：
    負責掃描已安裝模組的 contributes/<target>.json 宣告與專案級組態，
    執行拓撲合併，並物化寫入 cache://{module}/contributes.merged.json。
    """
    def __init__(self):
        pass

    def scan_and_inject(self, topological_order: Optional[List[str]] = None, clean: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        掃描所有 installed_modules 之 contributes/<target>.json，
        依拓撲排序 (topological_order) 依序合併，自動注入 __provider__，
        最後疊加 config:// 專案特化宣告並寫入快取。
        """
        aggregated: Dict[str, Dict[str, Any]] = {}
        installed_modules = uri.listdir("module://") if uri.exists("module://") else []
        
        if not installed_modules:
            return aggregated
        
        # 1. 決定有序遍歷清單 (Topological Order)
        if topological_order:
            ordered_donors = [m for m in topological_order if m in installed_modules]
            # 追加未在拓撲清單中之模組
            for m in installed_modules:
                if m not in ordered_donors:
                    ordered_donors.append(m)
        else:
            # 預設：core 最先，其他字母序
            ordered_donors = ["core"] if "core" in installed_modules else []
            for m in sorted(installed_modules):
                if m not in ordered_donors:
                    ordered_donors.append(m)

        # 2. 初始化所有已安裝模組 targets 字典
        for mod in installed_modules:
            aggregated[mod] = {}

        # 3. 階層 ①：依拓撲順序搜集模組層級 contributes/<target>.json
        for donor in ordered_donors:
            donor_contrib_dir = f"module://{donor}/contributes"
            if uri.exists(donor_contrib_dir) and uri.isdir(donor_contrib_dir):
                try:
                    for filename in uri.listdir(donor_contrib_dir):
                        if not filename.endswith(".json"):
                            continue
                        target = filename[:-5]
                        if target not in aggregated:
                            aggregated[target] = {}
                        
                        target_file_uri = f"{donor_contrib_dir}/{filename}"
                        try:
                            c_data = uri.read_json(target_file_uri)
                            if isinstance(c_data, dict):
                                tagged_body = {}
                                for c_key, c_val in c_data.items():
                                    if isinstance(c_val, list):
                                        tagged_body[c_key] = [
                                            _tag_provider(item, donor) if isinstance(item, dict) else item 
                                            for item in c_val
                                        ]
                                    elif isinstance(c_val, dict):
                                        tagged_body[c_key] = _tag_provider(c_val, donor)
                                    else:
                                        tagged_body[c_key] = c_val
                                self._deep_merge(aggregated[target], tagged_body)
                        except Exception:
                            pass
                except Exception:
                    pass

            # 單一 contributes.json 輔助支援
            donor_unified_file = f"module://{donor}/contributes.json"
            if uri.exists(donor_unified_file):
                try:
                    u_data = uri.read_json(donor_unified_file)
                    if isinstance(u_data, dict):
                        for target, c_body in u_data.items():
                            if isinstance(c_body, dict):
                                if target not in aggregated:
                                    aggregated[target] = {}
                                tagged_body = {}
                                for c_key, c_val in c_body.items():
                                    if isinstance(c_val, list):
                                        tagged_body[c_key] = [
                                            _tag_provider(item, donor) if isinstance(item, dict) else item 
                                            for item in c_val
                                        ]
                                    elif isinstance(c_val, dict):
                                        tagged_body[c_key] = _tag_provider(c_val, donor)
                                    else:
                                        tagged_body[c_key] = c_val
                                self._deep_merge(aggregated[target], tagged_body)
                except Exception:
                    pass

        # 4. 階層 ②：專案層級特化注入 (Project Contribute Overrides)
        # 🚨 剛性禁止 contribute.local.json，檢測到時輸出警告日誌並忽略。
        all_targets = list(aggregated.keys())
        for target in all_targets:
            local_contrib_uri = f"config://{target}/contribute.local.json"
            if uri.exists(local_contrib_uri):
                logger.warning(f"Ignoring '{local_contrib_uri}': project contribute overrides must be tracked by Git (no local overrides allowed).")

            proj_contrib_uri = f"config://{target}/contribute.json"
            if uri.exists(proj_contrib_uri):
                try:
                    c_data = uri.read_json(proj_contrib_uri)
                    if isinstance(c_data, dict):
                        # contribute.json 可直接為該目標之擴充內容，或嵌套於 target 鍵下
                        target_overlay = c_data.get(target, c_data)
                        if isinstance(target_overlay, dict):
                            self._deep_merge(aggregated[target], target_overlay)
                except Exception as e:
                    logger.warning(f"Failed to read project contribute override '{proj_contrib_uri}': {e}")


            # 5. 持久化物化至 cache 空間
            target_cache_uri = f"cache://{target}/contributes.merged.json"
            if aggregated[target]:
                uri.makedirs(f"cache://{target}", exist_ok=True)
                uri.write_json(target_cache_uri, aggregated[target])
            else:
                if uri.exists(target_cache_uri):
                    try:
                        target_p = uri.resolve(target_cache_uri, interactive=False)
                        if os.path.exists(target_p):
                            os.remove(target_p)
                    except Exception:
                        pass

        # 6. 持久化 contributes.meta.json 快照 (JIT Freshness Snapshot)
        try:
            meta_uri = _get_contributes_meta_uri()
            current_snapshot = _scan_contributes_inputs()
            meta_payload = {
                "updated_at": time.time(),
                "files": {k: [v[0], v[1]] for k, v in current_snapshot.items()}
            }
            uri.makedirs("cache://core", exist_ok=True)
            uri.write_json(meta_uri, meta_payload)
        except Exception as e:
            logger.warning(f"Failed to update contributes.meta.json: {e}")

        return aggregated

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            elif k in base and isinstance(base[k], list) and isinstance(v, list):
                base[k].extend(x for x in v if x not in base[k])
            else:
                base[k] = v
