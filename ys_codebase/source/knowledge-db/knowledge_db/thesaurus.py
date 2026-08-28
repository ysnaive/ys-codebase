"""
knowledge-db 雙層同義詞擴展引擎 (ThesaurusEngine)
"""

from collections import defaultdict
import logging
from typing import Dict, List, Optional, Set

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
    """雙層同義詞擴展引擎"""

    def __init__(self, custom_groups: Optional[List[List[str]]] = None):
        self._synonym_map: Dict[str, Set[str]] = defaultdict(set)

        # 1. 載入內建軟工詞庫
        for group in BUILTIN_THESAURUS:
            self.add_group(group)

        # 2. 合併自訂詞庫
        if custom_groups:
            for group in custom_groups:
                self.add_group(group)

    def add_group(self, group: List[str]) -> None:
        """
        動態加入一組同義詞。
        :param group: 同義詞字串清單
        """
        if not group or len(group) < 2:
            return

        cleaned_words = [w.strip().lower() for w in group if w and w.strip()]
        for w in cleaned_words:
            for other in cleaned_words:
                if w != other:
                    self._synonym_map[w].add(other)

    def get_synonyms(self, word: str) -> Set[str]:
        """查詢單一詞條的所有直接同義詞"""
        return set(self._synonym_map.get(word.strip().lower(), set()))

    def expand_query(self, tokens: List[str], max_expanded: int = 50) -> List[str]:
        """
        對輸入的查詢 Token 清單進行單步去重同義詞擴展 (EC-05: 集合防無窮迴圈)。
        :param tokens: 原始查詢 Token 清單
        :param max_expanded: 擴展詞最大總量上限 (預設 50)
        :return: 包含原始詞與同義詞之 Token 清單
        """
        if not tokens:
            return []

        expanded: List[str] = list(tokens)
        seen: Set[str] = set(t.lower() for t in tokens)

        for token in tokens:
            t_lower = token.lower()
            synonyms = self._synonym_map.get(t_lower, set())
            for syn in synonyms:
                if syn not in seen:
                    seen.add(syn)
                    expanded.append(syn)
                    if len(expanded) >= max_expanded:
                        break
            if len(expanded) >= max_expanded:
                break

        return expanded
