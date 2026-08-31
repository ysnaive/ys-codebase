"""
knowledge-db 雙層三階同義詞與關聯詞擴展引擎 (ThesaurusEngine)
"""

from collections import defaultdict
import logging
from typing import Dict, List, Optional, Set, Tuple

from .schema import ThesaurusConfig, WeightedToken

logger = logging.getLogger("knowledge-db.thesaurus")


class ThesaurusEngine:
    """雙層三階同義詞與關聯詞擴展引擎 (純淨無狀態詞庫容器，具備 LRU Memoization 快取)"""

    def __init__(
        self,
        config: Optional[ThesaurusConfig] = None,
        custom_groups: Optional[List[List[str]]] = None,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
        custom_related: Optional[List[List[str]]] = None,
    ):
        self._synonym_map: Dict[str, Set[str]] = defaultdict(set)
        self._alias_map: Dict[str, Set[str]] = defaultdict(set)
        self._related_map: Dict[str, Set[str]] = defaultdict(set)
        self._expansion_cache: Dict[Tuple[Tuple[str, ...], int, bool], List[WeightedToken]] = {}
        self._cache_maxsize: int = 1024

        # 1. 載入傳入之 ThesaurusConfig
        if config:
            if config.groups:
                for group in config.groups:
                    self.add_group(group)
            if config.aliases:
                for src, tgts in config.aliases.items():
                    self.add_alias(src, tgts)
            if config.related:
                for r_group in config.related:
                    self.add_related_group(r_group)

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

    def _clear_cache(self) -> None:
        """清空同義詞展開快取池"""
        self._expansion_cache.clear()

    def add_group(self, group: List[str]) -> None:
        """
        動態加入一組雙向等價同義詞 (Tier 2, weight=0.6)。
        :param group: 同義詞字串清單
        """
        if not group or len(group) < 2:
            return

        self._clear_cache()
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
        self._clear_cache()
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

        self._clear_cache()
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
        對輸入的查詢 Token 清單進行三階加權展開與去重 (具備 LRU Memoization 快取)。
        - Tier 1: 原始詞 (kind="original", weight=1.0)
        - Tier 2: 雙向同義詞 (kind="synonym", weight=0.6) / 單向別名 (kind="alias", weight=0.6)
        - Tier 3: 領域關聯詞 (kind="related", weight=0.25)
        """
        if not tokens:
            return []

        # 查快取 (以標準化 tuple 為鍵)
        cache_key = (
            tuple(str(t).strip().lower() for t in tokens if t and str(t).strip()),
            max_expanded,
            include_related,
        )
        if cache_key in self._expansion_cache:
            # 返回淺拷貝清單，避免外部修改破壞快取內容
            return list(self._expansion_cache[cache_key])

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
                # 衝突時保留最高權重
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
        tier2_terms: List[str] = []
        for t in cleaned_inputs:
            # 2a. 同義詞
            for syn in self._synonym_map.get(t, set()):
                if _insert_or_update(syn, weight=0.6, kind="synonym"):
                    tier2_terms.append(syn)
                if len(token_order) >= max_expanded:
                    break
            if len(token_order) >= max_expanded:
                break
            # 2b. 單向別名
            for alias in self._alias_map.get(t, set()):
                if _insert_or_update(alias, weight=0.6, kind="alias"):
                    tier2_terms.append(alias)
                if len(token_order) >= max_expanded:
                    break
            if len(token_order) >= max_expanded:
                break

        # Tier 3: 領域關聯詞 (weight=0.25) - 多跳鏈式傳播
        if include_related and len(token_order) < max_expanded:
            hop2_sources = list(cleaned_inputs) + [t for t in tier2_terms if t not in cleaned_inputs]
            hop2_related_terms: List[str] = []
            for t in hop2_sources:
                for rel in self._related_map.get(t, set()):
                    if _insert_or_update(rel, weight=0.25, kind="related"):
                        hop2_related_terms.append(rel)
                    if len(token_order) >= max_expanded:
                        break
                if len(token_order) >= max_expanded:
                    break

            # Hop 3: 關聯詞之雙向同義展開
            if len(token_order) < max_expanded:
                for r_term in hop2_related_terms:
                    for r_syn in self._synonym_map.get(r_term, set()):
                        _insert_or_update(r_syn, weight=0.25, kind="related")
                        if len(token_order) >= max_expanded:
                            break
                    if len(token_order) >= max_expanded:
                        break

        result = [token_map[t] for t in token_order]

        # 寫入快取 (FIFO / 簡單容量上限保護)
        if len(self._expansion_cache) >= self._cache_maxsize:
            # 清除最舊一半快取
            keys = list(self._expansion_cache.keys())
            for k in keys[: len(keys) // 2]:
                self._expansion_cache.pop(k, None)

        self._expansion_cache[cache_key] = result
        return list(result)

    def expand_query(self, tokens: List[str], max_expanded: int = 50) -> List[str]:
        """
        向後相容介面：回傳包含原始詞、同義詞、別名與關聯詞之字串 Token 清單。
        """
        weighted = self.expand_query_weighted(tokens, max_expanded=max_expanded, include_related=True)
        return [w.term for w in weighted]
