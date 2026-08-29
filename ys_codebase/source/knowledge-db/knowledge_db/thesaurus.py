"""
knowledge-db 雙層三階同義詞與關聯詞擴展引擎 (ThesaurusEngine)
"""

from collections import defaultdict
import logging
from typing import Dict, List, Optional, Set

from .schema import WeightedToken

logger = logging.getLogger("knowledge-db.thesaurus")

# 內建軟體工程通用同義詞庫 (標準雙向映射)
BUILTIN_THESAURUS: List[List[str]] = [
    ["建立", "創建", "初始化", "建置", "create", "init", "initialize", "new", "build", "construct"],
    ["搜尋", "檢索", "查詢", "尋找", "search", "query", "find", "lookup", "retrieval"],
    ["狀態", "現狀", "status", "state"],
    ["更新", "修改", "變更", "update", "modify", "change"],
    ["刪除", "移除", "清除", "delete", "remove", "clear"],
    ["取得", "獲取", "讀取", "get", "fetch", "read", "load"],
    ["儲存", "保存", "寫入", "save", "store", "write", "persist"],
    ["控制", "控制器", "control", "controller"],
    ["引擎", "核心", "engine", "core"],
    ["解析", "解析器", "parse", "parser"],
    ["打包", "封裝", "bundle", "bundler", "package"],
    ["空間", "範圍", "space", "scope"],
    ["配置", "組態", "設定", "config", "configuration", "setting"],
    ["掃描", "比對", "scan", "scanner", "diff"],
    ["符號", "識別碼", "symbol", "identifier"],
    ["類別", "類", "class", "struct"],
    ["函式", "方法", "函數", "function", "method"],
    ["錯誤", "異常", "例外", "error", "exception", "bug"],
]


class ThesaurusEngine:
    """雙層三階同義詞與關聯詞擴展引擎"""

    def __init__(
        self,
        custom_groups: Optional[List[List[str]]] = None,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
        custom_related: Optional[List[List[str]]] = None,
    ):
        self._synonym_map: Dict[str, Set[str]] = defaultdict(set)
        self._alias_map: Dict[str, Set[str]] = defaultdict(set)
        self._related_map: Dict[str, Set[str]] = defaultdict(set)

        # 1. 載入內建軟工詞庫
        for group in BUILTIN_THESAURUS:
            self.add_group(group)

        # 2. 合併自訂同義詞庫 (Tier 2, 0.6)
        if custom_groups:
            for group in custom_groups:
                self.add_group(group)

        # 3. 合併自訂單向別名 (Tier 2, 0.6)
        if custom_aliases:
            for src, tgts in custom_aliases.items():
                self.add_alias(src, tgts)

        # 4. 合併自訂領域關聯詞 (Tier 3, 0.25)
        if custom_related:
            for group in custom_related:
                self.add_related_group(group)

    def add_group(self, group: List[str]) -> None:
        """
        動態加入一組雙向等價同義詞 (Tier 2, weight=0.6)。
        :param group: 同義詞字串清單
        """
        if not group or len(group) < 2:
            return

        cleaned_words = [w.strip().lower() for w in group if w and str(w).strip()]
        for w in cleaned_words:
            for other in cleaned_words:
                if w != other:
                    self._synonym_map[w].add(other)

    def add_alias(self, source: str, targets: List[str]) -> None:
        """
        動態加入單向別名映射 (source => targets, Tier 2, weight=0.6)。
        :param source: 來源詞
        :param targets: 單向展開目標詞清單
        """
        if not source or not str(source).strip() or not targets:
            return
        src_clean = str(source).strip().lower()
        for t in targets:
            if t and str(t).strip():
                t_clean = str(t).strip().lower()
                if t_clean != src_clean:
                    self._alias_map[src_clean].add(t_clean)

    def add_related_group(self, group: List[str]) -> None:
        """
        動態加入一組雙向領域關聯詞 (Tier 3, weight=0.25)。
        :param group: 關聯詞字串清單
        """
        if not group or len(group) < 2:
            return

        cleaned_words = [w.strip().lower() for w in group if w and str(w).strip()]
        for w in cleaned_words:
            for other in cleaned_words:
                if w != other:
                    self._related_map[w].add(other)

    def get_synonyms(self, word: str) -> Set[str]:
        """查詢單一詞條的所有直接雙向同義詞"""
        return set(self._synonym_map.get(str(word).strip().lower(), set()))

    def get_aliases(self, word: str) -> Set[str]:
        """查詢單一詞條的所有單向別名"""
        return set(self._alias_map.get(str(word).strip().lower(), set()))

    def get_related(self, word: str) -> Set[str]:
        """查詢單一詞條的所有領域關聯詞"""
        return set(self._related_map.get(str(word).strip().lower(), set()))

    def expand_query_weighted(
        self,
        tokens: List[str],
        max_expanded: int = 50,
        include_related: bool = True,
    ) -> List[WeightedToken]:
        """
        對輸入的查詢 Token 清單進行三階加權展開與去重 (Max-Weight Retention, EC-01, EC-02, EC-04)。
        - Tier 1: 原始詞 (kind="original", weight=1.0)
        - Tier 2: 雙向同義詞 (kind="synonym", weight=0.6) / 單向別名 (kind="alias", weight=0.6)
        - Tier 3: 領域關聯詞 (kind="related", weight=0.25)
        """
        if not tokens:
            return []

        # 1. 建立加權字典 (term -> WeightedToken) 與順序清單
        token_order: List[str] = []
        token_map: Dict[str, WeightedToken] = {}

        def _insert_or_update(term_str: str, weight: float, kind: str) -> bool:
            clean = term_str.strip().lower()
            if not clean:
                return False
            if clean not in token_map:
                if len(token_order) >= max_expanded:
                    return False
                wt = WeightedToken(term=clean, weight=weight, kind=kind)
                token_map[clean] = wt
                token_order.append(clean)
                return True
            else:
                # 衝突時保留最高權重 (EC-02)
                existing = token_map[clean]
                if weight > existing.weight:
                    existing.weight = weight
                    existing.kind = kind
                return True

        # Tier 1: 原始查詢詞
        cleaned_inputs: List[str] = []
        for t in tokens:
            if t and str(t).strip():
                clean_t = str(t).strip().lower()
                if clean_t not in cleaned_inputs:
                    cleaned_inputs.append(clean_t)
                _insert_or_update(clean_t, weight=1.0, kind="original")

        # Tier 2: 同義詞與單向別名 (weight=0.6)
        for t in cleaned_inputs:
            # 2a. 同義詞
            for syn in self._synonym_map.get(t, set()):
                _insert_or_update(syn, weight=0.6, kind="synonym")
                if len(token_order) >= max_expanded:
                    break
            if len(token_order) >= max_expanded:
                break
            # 2b. 單向別名
            for alias in self._alias_map.get(t, set()):
                _insert_or_update(alias, weight=0.6, kind="alias")
                if len(token_order) >= max_expanded:
                    break
            if len(token_order) >= max_expanded:
                break

        # Tier 3: 領域關聯詞 (weight=0.25)
        if include_related and len(token_order) < max_expanded:
            for t in cleaned_inputs:
                for rel in self._related_map.get(t, set()):
                    _insert_or_update(rel, weight=0.25, kind="related")
                    if len(token_order) >= max_expanded:
                        break
                if len(token_order) >= max_expanded:
                    break

        return [token_map[t] for t in token_order]

    def expand_query(self, tokens: List[str], max_expanded: int = 50) -> List[str]:
        """
        向後相容介面：回傳包含原始詞、同義詞、別名與關聯詞之字串 Token 清單。
        """
        weighted = self.expand_query_weighted(tokens, max_expanded=max_expanded, include_related=True)
        return [w.term for w in weighted]

