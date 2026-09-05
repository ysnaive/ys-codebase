"""
knowledge-db 多語言混雜分詞器 (MultilingualTokenizer / CodeTokenizer)
支援中英混雜、CJK 字符、駝峰/蛇形標識符與程式碼標記分詞。
100% 採用純 Python 原生標準庫 (Zero External Dependency)。
"""

import functools
import re
from typing import List, Optional, Set, Tuple

# 預設中英文常用停用詞
DEFAULT_STOPWORDS: Set[str] = {
    # 英文停用詞
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "can", "will", "just", "should", "now",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "this", "that", "these", "those",
    # 中文停用詞
    "的", "了", "和", "是", "就", "都", "而", "及", "與", "著",
    "或", "一個", "沒有", "我們", "你們", "他們", "這", "那", "之",
    "在", "於", "把", "被", "讓", "由", "向", "往", "從", "到",
}

# 預編譯標識符拆解正則
_CAMEL_SUB1 = re.compile(r"([A-Z]+)([A-Z][a-z0-9])")
_CAMEL_SUB2 = re.compile(r"([a-z0-9])([A-Z])")
_SPLIT_PUNCT = re.compile(r"[_\-\s.]+")
_CLEAN_ALPHA = re.compile(r"[^a-z0-9]")


def _is_cjk_ord(code: int) -> bool:
    """
    依據 Unicode 整數值判斷是否為 CJK / 東亞常用字元 (純整數比對，零正則呼叫開銷)。
    """
    return (
        (0x4E00 <= code <= 0x9FFF) or   # CJK Unified Ideographs
        (0x3400 <= code <= 0x4DBF) or   # CJK Unified Ideographs Extension A
        (0x20000 <= code <= 0x2A6DF) or # CJK Extension B
        (0xF900 <= code <= 0xFAFF) or   # CJK Compatibility Ideographs
        (0x3040 <= code <= 0x309F) or   # Hiragana
        (0x30A0 <= code <= 0x30FF) or   # Katakana
        (0xAC00 <= code <= 0xD7AF)      # Hangul Syllables
    )


@functools.lru_cache(maxsize=8192)
def _split_identifier_cached(identifier: str) -> Tuple[str, ...]:
    """
    將程式碼標識符進行駝峰與底線拆解，結果以元組形式快取 (LRU Cache)。
    """
    if not identifier:
        return ()

    # 1. 駝峰拆解正則
    s1 = _CAMEL_SUB1.sub(r"\1_\2", identifier)
    s2 = _CAMEL_SUB2.sub(r"\1_\2", s1)

    # 2. 底線與標點切分
    parts = [p.lower() for p in _SPLIT_PUNCT.split(s2) if p]

    tokens: List[str] = []
    for p in parts:
        if p:
            tokens.append(p)

    # 對點號切分的各個片段加入單獨小寫標識符
    for seg in re.split(r"[.\s]+", identifier):
        clean_seg = _CLEAN_ALPHA.sub("", seg.lower())
        if clean_seg and clean_seg not in tokens and len(clean_seg) > 1:
            tokens.append(clean_seg)

    # 若拆解出多個子 token，保留整體小寫標識符
    clean_raw = identifier.lower().replace("-", "_")
    if clean_raw not in tokens and len(clean_raw) > 1:
        tokens.append(clean_raw)
    pure_alpha = _CLEAN_ALPHA.sub("", identifier.lower())
    if pure_alpha and pure_alpha not in tokens and len(pure_alpha) > 1:
        tokens.append(pure_alpha)

    return tuple(tokens)


class MultilingualTokenizer:
    """
    多語言混雜分詞器 (支援中英混雜、CJK 1/2-gram、駝峰蛇形標識符拆解)
    """

    def __init__(self, stopwords: Optional[Set[str]] = None):
        self.stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS

    @classmethod
    def is_cjk(cls, char: str) -> bool:
        """檢查單一字元是否為 CJK 東亞字元"""
        if not char:
            return False
        return _is_cjk_ord(ord(char[0]))

    @classmethod
    def split_identifier(cls, identifier: str) -> List[str]:
        """
        將程式碼標識符進行駝峰與底線拆解。
        例如：
          - 'PIDController' ➔ ['pid', 'controller', 'pidcontroller']
          - 'getHTTPResponse' ➔ ['get', 'http', 'response', 'gethttpresponse']
          - 'user_id_v5' ➔ ['user', 'id', 'v5', 'user_id_v5']
        """
        return list(_split_identifier_cached(identifier))

    def tokenize(self, text: str) -> List[str]:
        """
        對輸入字串進行混合分詞，輸出標準小寫 Token 清單。
        支援無縫處理中英混排邊界 (如 '解析InvertedIndex倒排索引')。
        """
        if not text or not isinstance(text, str):
            return []

        tokens: List[str] = []
        n = len(text)
        i = 0

        while i < n:
            ch = text[i]
            code = ord(ch)

            # 1. 處理 CJK 東亞文字連續區塊
            if _is_cjk_ord(code):
                cjk_start = i
                while i < n and _is_cjk_ord(ord(text[i])):
                    i += 1
                cjk_chunk = text[cjk_start:i]

                # 1-gram
                for c in cjk_chunk:
                    if c not in self.stopwords:
                        tokens.append(c)

                # 2-gram 滑動窗口
                if len(cjk_chunk) >= 2:
                    for j in range(len(cjk_chunk) - 1):
                        bi_gram = cjk_chunk[j:j + 2]
                        tokens.append(bi_gram)

                # 3~6 字元整詞
                if 2 < len(cjk_chunk) <= 6:
                    tokens.append(cjk_chunk)
                continue

            # 2. 處理 ASCII / 代碼識別碼連續區塊
            if ch.isascii() and (ch.isalnum() or ch == "_"):
                ident_start = i
                while i < n and text[i].isascii() and (text[i].isalnum() or text[i] == "_"):
                    i += 1
                ident_chunk = text[ident_start:i]

                sub_tokens = _split_identifier_cached(ident_chunk)
                for st in sub_tokens:
                    if st not in self.stopwords and len(st) > 0:
                        tokens.append(st)
                continue

            # 3. 其他非字母數字（標點、空白、特殊符號），前進一位
            i += 1

        return tokens


# 向後相容別名
CodeTokenizer = MultilingualTokenizer
