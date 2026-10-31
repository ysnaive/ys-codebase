"""
Multilingual Code & CJK Tokenizer for Knowledge-DB.

Provides:
1. Identifier splitting (CamelCase, PascalCase, snake_case, kebab-case, acronyms).
2. CJK (Chinese/Japanese/Korean) Unigram + Bigram sliding-window n-gram extraction.
3. Seamless handling of mixed English/CJK identifiers without spaces.
"""

import re
from typing import List, Set

_CAMEL_BOUNDARY_1 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")
_DELIM_SPLIT = re.compile(r"[^a-zA-Z0-9]+")

_CJK_OR_WORD_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\uffef]+|[a-zA-Z0-9_]+",
    re.UNICODE,
)
_CJK_CHECK_RE = re.compile(r"^[\u4e00-\u9fff\u3400-\u4dbf\uf900-\uffef]+$")


class MultilingualTokenizer:
    """
    Deterministic, zero-dependency tokenizer optimized for source code identifiers
    and CJK technical documentation.
    """

    DEFAULT_STOPWORDS: Set[str] = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
        "and", "or", "not", "this", "that", "it", "self", "cls", "def", "class",
        "return", "import", "true", "false", "none", "null", "void",
        "的", "了", "在", "是", "與", "及", "或", "將", "對", "於", "中", "為", "以",
    }

    def __init__(self, stopwords: Set[str] = None, keep_original_identifier: bool = True):
        self.stopwords = stopwords if stopwords is not None else self.DEFAULT_STOPWORDS
        self.keep_original_identifier = keep_original_identifier

    @staticmethod
    def _split_identifier(word: str) -> List[str]:
        """Split a code identifier (CamelCase / snake_case) into lowercase sub-tokens."""
        raw_parts = [p for p in _DELIM_SPLIT.split(word) if p]
        sub_tokens: List[str] = []

        for part in raw_parts:
            step1 = _CAMEL_BOUNDARY_1.sub(r"\1_\2", part)
            step2 = _CAMEL_BOUNDARY_2.sub(r"\1_\2", step1)
            for piece in step2.split("_"):
                low = piece.lower()
                if low:
                    sub_tokens.append(low)

        return sub_tokens

    @staticmethod
    def _tokenize_cjk(cjk_chunk: str, stopwords: Set[str]) -> List[str]:
        """Extract CJK Unigrams and Bigrams from a contiguous CJK string."""
        tokens: List[str] = []
        length = len(cjk_chunk)

        for ch in cjk_chunk:
            if ch not in stopwords:
                tokens.append(ch)

        if length >= 2:
            for i in range(length - 1):
                bigram = cjk_chunk[i : i + 2]
                tokens.append(bigram)

        return tokens

    def tokenize(self, text: str) -> List[str]:
        """Tokenize arbitrary text or code snippet into normalized indexable terms."""
        if not text or not text.strip():
            return []

        tokens: List[str] = []
        segments = _CJK_OR_WORD_RE.findall(text)

        for seg in segments:
            if _CJK_CHECK_RE.match(seg):
                tokens.extend(self._tokenize_cjk(seg, self.stopwords))
            else:
                cleaned_full = re.sub(r"[^a-zA-Z0-9]", "", seg).lower()
                sub_parts = self._split_identifier(seg)

                filtered_subs = [
                    p for p in sub_parts if p not in self.stopwords and len(p) >= 1
                ]
                tokens.extend(filtered_subs)

                if (
                    self.keep_original_identifier
                    and len(sub_parts) > 1
                    and cleaned_full
                    and cleaned_full not in self.stopwords
                ):
                    if cleaned_full not in filtered_subs:
                        tokens.append(cleaned_full)

        return tokens

    def tokenize_unique(self, text: str) -> List[str]:
        """Tokenize and deduplicate while preserving first-seen order."""
        seen: Set[str] = set()
        result: List[str] = []
        for tok in self.tokenize(text):
            if tok not in seen:
                seen.add(tok)
                result.append(tok)
        return result
