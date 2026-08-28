"""
Contributes Aggregator and Dependency Injection Engine.
Rigid Topology & Zero Speculation: strictly scans installed modules in module://.
Standard Directory: module://<donor>/contributes/<target>.json
Project Overrides: config://<target>/config.project.json
"""
from typing import Dict, Any, List, Optional
import os
import copy
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


def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    標準 Contributes 查詢 SDK:
    查詢指定目標模組之已合併 Contributes 字典或特定鍵值。
    
    1. 優先從 cache://{target_module}/contributes.merged.json 讀取。
    2. 若快取不存在或損毀，自動調用 scan_and_inject() 即時自愈聚合。
    3. 若指定 key 則返回該特定欄位，否則返回全字典。
    """
    cache_file = f"cache://{target_module}/contributes.merged.json"
    data = None
    if uri.exists(cache_file):
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

        return aggregated

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            elif k in base and isinstance(base[k], list) and isinstance(v, list):
                base[k].extend(x for x in v if x not in base[k])
            else:
                base[k] = v
