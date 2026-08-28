"""
knowledge-db 代碼標識符與 CJK 中文混合分詞器 (CodeTokenizer)
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

import re
from typing import List, Optional, Set

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

# CJK 中文字元 Unicode 正則區間
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
# 英文/數字/底線程式碼標識符正則
IDENTIFIER_CHUNK_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class CodeTokenizer:
    """程式碼標識符與 CJK 中文 1-gram / 2-gram 混合分詞器"""

    def __init__(self, stopwords: Optional[Set[str]] = None):
        self.stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS

    @classmethod
    def is_cjk(cls, char: str) -> bool:
        """檢查單一字元是否為 CJK 中文字元"""
        return bool(CJK_PATTERN.match(char))

    @classmethod
    def split_identifier(cls, identifier: str) -> List[str]:
        """
        將程式碼標識符進行駝峰與底線拆解。
        例如：
          - 'PIDController' ➔ ['pid', 'controller', 'pidcontroller']
          - 'getHTTPResponse' ➔ ['get', 'http', 'response', 'gethttpresponse']
          - 'user_id_v5' ➔ ['user', 'id', 'v5', 'user_id_v5']
        """
        if not identifier:
            return []

        # 1. 駝峰拆解正則
        s1 = re.sub(r"([A-Z]+)([A-Z][a-z0-9])", r"\1_\2", identifier)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)

        # 2. 底線與標點切分
        parts = [p.lower() for p in re.split(r"[_\-\s.]+", s2) if p]

        tokens: List[str] = []
        for p in parts:
            if p:
                tokens.append(p)

        # 若拆解出多個子 token，保留整體小寫標識符
        clean_raw = identifier.lower().replace("-", "_")
        if clean_raw not in tokens and len(clean_raw) > 1:
            tokens.append(clean_raw)
        pure_alpha = re.sub(r"[^a-z0-9]", "", identifier.lower())
        if pure_alpha and pure_alpha not in tokens and len(pure_alpha) > 1:
            tokens.append(pure_alpha)

        return tokens

    def tokenize(self, text: str) -> List[str]:
        """
        對輸入字串進行混合分詞，輸出標準小寫 Token 清單。
        """
        if not text or not isinstance(text, str):
            return []

        tokens: List[str] = []
        n = len(text)
        i = 0

        while i < n:
            ch = text[i]

            # 1. 處理 CJK 中文字元連續區塊
            if self.is_cjk(ch):
                cjk_start = i
                while i < n and self.is_cjk(text[i]):
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

                # 若區塊長度在 3~6 之間，亦加入整詞
                if 2 < len(cjk_chunk) <= 6:
                    tokens.append(cjk_chunk)
                continue

            # 2. 處理 ASCII / 代碼識別碼連續區塊
            if ch.isalnum() or ch == "_":
                ident_start = i
                while i < n and (text[i].isalnum() or text[i] == "_"):
                    i += 1
                ident_chunk = text[ident_start:i]

                sub_tokens = self.split_identifier(ident_chunk)
                for st in sub_tokens:
                    if st not in self.stopwords and len(st) > 0:
                        tokens.append(st)
                continue

            # 3. 其他非字母數字（標點符號、空白、特殊字元等），直接跳過
            i += 1

        return tokens
