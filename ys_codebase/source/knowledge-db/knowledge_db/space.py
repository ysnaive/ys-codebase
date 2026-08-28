"""
knowledge-db 空間管理、雙軌聚合 (Contributes + Config) 與路徑解算服務
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .exceptions import InvalidSpaceConfigError, SpaceNotFoundError
from .schema import SpaceConfig, SpaceOrigin, ThesaurusConfig, ThesaurusGroup

logger = logging.getLogger("knowledge-db.space")


def _safe_resolve_uri(uri_str: str) -> Optional[Path]:
    """安全解算語意 URI，若無 core 環境或失敗則回傳 None"""
    try:
        from core.uri import resolve
        resolved = resolve(uri_str)
        return Path(resolved).resolve()
    except Exception:
        # 非 URI 格式或無法透過 core 解算時，若為實體路徑則直接返回
        p = Path(uri_str)
        if p.is_absolute() or p.exists():
            return p.resolve()
        return None


class SpaceManager:
    """
    多空間管理器：
    負責雙軌來源聚合 (模組聯動注入 + 2x2 組態檔案)、階層優先權合併、
    全空間聯集 (Union Scope) 以及語意路徑解算與 VFS 存儲目錄定位。
    """

    def __init__(
        self,
        core_context: Optional[Any] = None,
        config_dir: Optional[Union[str, Path]] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化 SpaceManager。
        :param core_context: Core 模組上下文 (可選)
        :param config_dir: 自訂組態目錄 (用於測試或覆蓋 config://knowledge-db/)
        :param storage_dir: 自訂存儲目錄 (用於測試或覆蓋 storage://knowledge-db/)
        :param contributes_data: 直接注入之 contributes 字典 (用於測試或自訂注入)
        """
        self.core_context = core_context
        self._custom_config_dir = Path(config_dir).resolve() if config_dir else None
        self._custom_storage_dir = Path(storage_dir).resolve() if storage_dir else None
        self._custom_contributes_data = contributes_data

    def _get_config_path(self, filename: str) -> Optional[Path]:
        """取得指定設定檔之實體路徑"""
        if self._custom_config_dir:
            p = self._custom_config_dir / filename
            return p if p.exists() else None

        # 透過 URI 解析
        resolved = _safe_resolve_uri(f"config://knowledge-db/{filename}")
        if resolved and resolved.exists():
            return resolved

        return None

    def _get_storage_root(self) -> Path:
        """取得資料庫本機快取根目錄 (cache://knowledge-db/)"""
        if self._custom_storage_dir:
            return self._custom_storage_dir

        resolved = _safe_resolve_uri("cache://knowledge-db/")
        if resolved:
            return resolved

        # 預設回退至本地 .cache/knowledge-db
        p = Path("./.cache/knowledge-db").resolve()
        return p

    @property
    def storage_dir(self) -> Path:
        """取得存儲空間根目錄"""
        return self._get_storage_root()

    def _load_contributes(self) -> Dict[str, Any]:
        """讀取模組聯動注入之 Contributes 資料 (100% 由 core.contributes SDK 與專案特化 contribute.json 驅動)"""
        result = {"spaces": {}, "thesaurus": []}

        # 1. 自訂注入 (測試或隔離環境)
        if self._custom_contributes_data is not None:
            if isinstance(self._custom_contributes_data, dict):
                result["spaces"].update(self._custom_contributes_data.get("spaces", {}))
                result["thesaurus"].extend(self._custom_contributes_data.get("thesaurus", []))

        # 2. 自訂 config_dir 之 contribute.json (若指定)
        if self._custom_config_dir:
            contrib_file = self._custom_config_dir / "contribute.json"
            if contrib_file.exists():
                try:
                    with open(contrib_file, "r", encoding="utf-8", errors="replace") as f:
                        c_data = json.load(f)
                    if isinstance(c_data, dict):
                        result["spaces"].update(c_data.get("spaces", {}))
                        result["thesaurus"].extend(c_data.get("thesaurus", []))
                except Exception as e:
                    logger.warning(f"Failed to read custom contribute.json: {e}")
            return result

        # 3. 核心 SDK 聚合結果
        try:
            from core import contributes
            data = contributes.get("knowledge-db")
            if isinstance(data, dict):
                result["spaces"].update(data.get("spaces", {}))
                result["thesaurus"].extend(data.get("thesaurus", []))
        except Exception as e:
            logger.warning(f"Failed to read contributes via core SDK: {e}")

        return result

    def load_spaces(self) -> Dict[str, SpaceConfig]:
        """
        載入並聚合所有來源 (Contributes 體系：模組 Contributes + 專案特化 contribute.json) 之空間清單。
        """
        spaces: Dict[str, SpaceConfig] = {}

        contrib_data = self._load_contributes()
        contrib_spaces = contrib_data.get("spaces", {})
        if isinstance(contrib_spaces, dict):
            for sp_name, sp_val in contrib_spaces.items():
                if isinstance(sp_val, dict):
                    donor = sp_val.get("__provider__")
                    origin = f"module:{donor}" if donor else sp_val.get("origin", SpaceOrigin.CONTRIBUTED.value)
                    try:
                        spaces[sp_name] = SpaceConfig.from_dict(sp_name, sp_val, origin=origin)
                    except InvalidSpaceConfigError as e:
                        logger.warning(f"Skipping invalid contributed space '{sp_name}': {e}")

        return spaces

    def load_thesaurus(self) -> List[ThesaurusGroup]:
        """
        載入並聚合所有來源之同義詞群組清單 (Contributes 體系)。
        """
        all_groups: List[ThesaurusGroup] = []
        seen_signatures = set()

        def _add_groups(raw_list: Any):
            if not isinstance(raw_list, list):
                return
            for item in raw_list:
                if isinstance(item, list):
                    normalized = sorted(list(set(str(w).strip() for w in item if str(w).strip())))
                    sig = tuple(normalized)
                    if sig and sig not in seen_signatures:
                        seen_signatures.add(sig)
                        all_groups.append(list(item))

        contrib_data = self._load_contributes()
        _add_groups(contrib_data.get("thesaurus", []))
        return all_groups



        return all_groups

    def get_space(self, name: str) -> SpaceConfig:
        """
        取得指定空間組態，若不存在拋出 SpaceNotFoundError。
        """
        spaces = self.load_spaces()
        if name not in spaces:
            raise SpaceNotFoundError(name, list(spaces.keys()))
        return spaces[name]

    def list_spaces(self) -> List[SpaceConfig]:
        """
        列出當前所有有效 SpaceConfig 清單。
        """
        return list(self.load_spaces().values())

    def get_union_spaces(self) -> List[SpaceConfig]:
        """
        取得所有空間之聯集清單 (全量處理清單)。
        """
        return self.list_spaces()

    def resolve_space_include(self, space_name: str) -> List[Path]:
        """
        將空間宣告之 include 語意 URI 清單解算為本機實體絕對路徑清單。
        過濾不存在的路徑並發出 Warning 日誌 (EC-02)。
        """
        space_config = self.get_space(space_name)
        resolved_paths: List[Path] = []
        seen = set()

        for uri_item in space_config.include:
            resolved = _safe_resolve_uri(uri_item)
            if resolved is None:
                # 嘗試相對路徑
                p = Path(uri_item)
                if p.exists():
                    resolved = p.resolve()

            if resolved and resolved.exists():
                abs_p = resolved.resolve()
                if abs_p not in seen:
                    seen.add(abs_p)
                    resolved_paths.append(abs_p)
            else:
                logger.warning(f"Space '{space_name}' include path does not exist or cannot be resolved: '{uri_item}'")

        return resolved_paths

    def get_space_storage_dir(self, space_name: str) -> Path:
        """
        定位該空間專屬之 VFS 存儲目錄 (storage://knowledge-db/spaces/<space_name>/)。
        若目錄不存在則自動建立。
        """
        storage_root = self._get_storage_root()
        space_dir = storage_root / "spaces" / space_name
        space_dir.mkdir(parents=True, exist_ok=True)
        return space_dir
