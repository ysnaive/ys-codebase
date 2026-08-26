"""
Contributes Aggregator and Dependency Injection Engine.
Rigid Topology & Zero Speculation: strictly scans installed modules in module.root://.
"""
from typing import Dict, Any, List, Optional
import os
import copy
from core import uri

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
    Contributes 聚合引擎：
    負責掃描已安裝模組的 Contributes 宣告，執行拓撲合併，並物化寫入 cache://{module}/contributes.merged.json。
    """
    def __init__(self):
        pass

    def scan_and_inject(self, topological_order: Optional[List[str]] = None, clean: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        掃描所有 installed_modules，聚合 Manifest 與 contributes.<target>.json，
        依拓撲排序 (topological_order) 依序合併，並在搜集階段自動注入 __provider__。
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

        # 2. 初始化所有 targets 字典
        for mod in installed_modules:
            aggregated[mod] = {}

        # 3. 依拓撲順序搜集模組層級 contributes
        for donor in ordered_donors:
            # Source 1: Manifest
            manifest_uri = f"module://{donor}/manifest.json"
            if uri.exists(manifest_uri):
                try:
                    m_data = uri.read_json(manifest_uri)
                    m_contribs = m_data.get("contributes", {})
                    if isinstance(m_contribs, dict):
                        for target, c_body in m_contribs.items():
                            if target in aggregated and isinstance(c_body, dict):
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

            # Source 2: contributes.<target>.json in donor module
            for target in installed_modules:
                donor_file = f"module://{donor}/contributes.{target}.json"
                if uri.exists(donor_file):
                    try:
                        c_data = uri.read_json(donor_file)
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

        # 4. Project-level and local-level overrides
        for target in installed_modules:
            # Source 3: project-level config.project.json
            proj_cfg_uri = f"config://{target}/config.project.json"
            if uri.exists(proj_cfg_uri):
                try:
                    p_data = uri.read_json(proj_cfg_uri)
                    p_contribs = p_data.get("contributes", {}).get(target, {})
                    if isinstance(p_contribs, dict):
                        self._deep_merge(aggregated[target], p_contribs)
                except Exception:
                    pass

            # Remove legacy file in config/ if exists
            legacy_cfg_uri = f"config://{target}/contributes.merged.json"
            if uri.exists(legacy_cfg_uri):
                try:
                    uri.rmtree(legacy_cfg_uri) if uri.isdir(legacy_cfg_uri) else uri.write_text(legacy_cfg_uri, "")
                except Exception:
                    pass

            # Persist injected contributes to cache space
            target_cache_uri = f"cache://{target}/contributes.merged.json"
            if aggregated[target]:
                uri.makedirs(f"cache://{target}", exist_ok=True)
                uri.write_json(target_cache_uri, aggregated[target])
            else:
                if uri.exists(target_cache_uri):
                    target_p = uri.resolve(target_cache_uri, interactive=False)
                    if os.path.exists(target_p):
                        os.remove(target_p)

        return aggregated

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            elif k in base and isinstance(base[k], list) and isinstance(v, list):
                base[k].extend(x for x in v if x not in base[k])
            else:
                base[k] = v
