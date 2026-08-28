"""
knowledge-db 倒排索引、多欄位加權 BM25 語意評分與二進位 Gzip 快取引擎 (retrieval.py)
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gzip
import json
import logging
import math
import os
from pathlib import Path
import pickle
import tempfile
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .exceptions import KnowledgeDBError, SchemaValidationError
from .schema import UnifiedSymbol
from .thesaurus import ThesaurusEngine
from .tokenizer import CodeTokenizer

logger = logging.getLogger("knowledge-db.retrieval")


@dataclass
class Posting:
    """輕量倒排索引節點 (消滅 Symbol 深拷貝冗餘)"""

    doc_id: str
    field_freqs: Dict[str, int] = field(default_factory=dict)
    field_lengths: Dict[str, int] = field(default_factory=dict)
    space: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "field_freqs": self.field_freqs,
            "field_lengths": self.field_lengths,
            "space": self.space,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Posting":
        return cls(
            doc_id=data["doc_id"],
            field_freqs=data.get("field_freqs", {}),
            field_lengths=data.get("field_lengths", {}),
            space=data.get("space", ""),
        )


@dataclass(frozen=True)
class QueryFilter:
    """檢索條件過濾器"""

    spaces: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    kinds: Optional[List[str]] = None
    min_score: float = 0.01
    limit: int = 20


@dataclass(frozen=True)
class SearchResult:
    """結構化檢索結果"""

    symbol: UnifiedSymbol
    score: float
    matched_terms: List[str]
    space: str
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.symbol.id,
            "name": self.symbol.name,
            "kind": self.symbol.kind,
            "file_path": self.symbol.file_path,
            "line_number": self.symbol.line_number,
            "language": self.symbol.language,
            "score": round(self.score, 4),
            "matched_terms": self.matched_terms,
            "space": self.space,
            "snippet": self.snippet,
        }


class InvertedIndex:
    """多欄位倒排索引與符號池中心"""

    INDEXED_FIELDS = ["name", "signature", "members", "docstring"]

    def __init__(self, space_name: str = ""):
        self.space_name = space_name
        self.doc_count: int = 0
        self.symbols: Dict[str, UnifiedSymbol] = {}
        self.index: Dict[str, List[Posting]] = defaultdict(list)
        self.field_avgdl: Dict[str, float] = {f: 1.0 for f in self.INDEXED_FIELDS}
        self.field_total_lengths: Dict[str, int] = {f: 0 for f in self.INDEXED_FIELDS}

    @property
    def symbols_map(self) -> Dict[str, UnifiedSymbol]:
        """向後相容別名"""
        return self.symbols

    @symbols_map.setter
    def symbols_map(self, value: Dict[str, UnifiedSymbol]) -> None:
        self.symbols = value

    def get_symbol(self, doc_id: str) -> Optional[UnifiedSymbol]:
        """自符號池中以 O(1) 獲取符號實例"""
        return self.symbols.get(doc_id)

    def add_symbol(self, symbol: UnifiedSymbol, tokenizer: CodeTokenizer, space: str = "") -> None:
        """加入單一 UnifiedSymbol 建立欄位倒排索引與註冊符號池"""
        doc_id = symbol.id
        self.symbols[doc_id] = symbol
        self.doc_count += 1
        curr_space = (
            space
            or symbol.metadata.get("space", "")
            or getattr(symbol, "space", "")
            or self.space_name
        )

        # 1. 提取各欄位文字
        members_text = " ".join([f"{m.name} {m.signature} {m.docstring}" for m in symbol.members])

        field_texts = {
            "name": symbol.name,
            "signature": symbol.signature,
            "members": members_text,
            "docstring": symbol.docstring,
        }

        # 2. 分詞與詞頻計算
        field_tokens: Dict[str, List[str]] = {}
        field_freqs_map: Dict[str, Counter] = {}
        field_lengths: Dict[str, int] = {}
        all_unique_terms: Set[str] = set()

        for f_name, text in field_texts.items():
            tokens = tokenizer.tokenize(text)
            field_tokens[f_name] = tokens
            field_lengths[f_name] = len(tokens)
            self.field_total_lengths[f_name] += len(tokens)
            counts = Counter(tokens)
            field_freqs_map[f_name] = counts
            all_unique_terms.update(counts.keys())

        # 3. 建立輕量 Posting (僅記錄 doc_id)
        for term in all_unique_terms:
            t_freqs = {f_name: field_freqs_map[f_name][term] for f_name in self.INDEXED_FIELDS}
            posting = Posting(
                doc_id=doc_id,
                field_freqs=t_freqs,
                field_lengths=field_lengths,
                space=curr_space,
            )
            self.index[term].append(posting)

    def build(self, symbols: List[UnifiedSymbol], tokenizer: Optional[CodeTokenizer] = None, space: str = "") -> None:
        """批次建立倒排索引並計算 avgdl"""
        tok = tokenizer or CodeTokenizer()
        self.doc_count = 0
        self.symbols.clear()
        self.index.clear()
        self.field_total_lengths = {f: 0 for f in self.INDEXED_FIELDS}

        for sym in symbols:
            self.add_symbol(sym, tok, space=space)

        # 計算 avgdl
        if self.doc_count > 0:
            for f in self.INDEXED_FIELDS:
                self.field_avgdl[f] = max(1.0, self.field_total_lengths[f] / self.doc_count)
        else:
            for f in self.INDEXED_FIELDS:
                self.field_avgdl[f] = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化倒排索引為正規化符號池字典"""
        serialized_index = {}
        for term, postings in self.index.items():
            serialized_index[term] = [p.to_dict() for p in postings]

        serialized_symbols = {doc_id: sym.to_dict() for doc_id, sym in self.symbols.items()}

        return {
            "space_name": self.space_name,
            "doc_count": self.doc_count,
            "field_avgdl": self.field_avgdl,
            "field_total_lengths": self.field_total_lengths,
            "symbols": serialized_symbols,
            "index": serialized_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvertedIndex":
        """反序列化正規化倒排索引"""
        if not isinstance(data, dict):
            raise SchemaValidationError("InvertedIndex data must be a dictionary.")

        idx = cls(space_name=data.get("space_name", ""))
        idx.doc_count = int(data.get("doc_count", 0))
        idx.field_avgdl = data.get("field_avgdl", {f: 1.0 for f in cls.INDEXED_FIELDS})
        idx.field_total_lengths = data.get("field_total_lengths", {f: 0 for f in cls.INDEXED_FIELDS})

        # 1. 還原符號池
        raw_symbols = data.get("symbols", {})
        if raw_symbols:
            for doc_id, s_dict in raw_symbols.items():
                if isinstance(s_dict, dict):
                    idx.symbols[doc_id] = UnifiedSymbol.from_dict(s_dict)

        # 2. 還原倒排表 (兼顧舊版內嵌 symbol 格式)
        raw_index = data.get("index", {})
        for term, postings_raw in raw_index.items():
            postings: List[Posting] = []
            for p in postings_raw:
                if isinstance(p, dict):
                    posting = Posting.from_dict(p)
                    postings.append(posting)
                    # 舊版向下相容：若舊版 JSON 內含 symbol 且未在符號池中，補充註冊
                    if "symbol" in p and isinstance(p["symbol"], dict) and posting.doc_id not in idx.symbols:
                        idx.symbols[posting.doc_id] = UnifiedSymbol.from_dict(p["symbol"])
            idx.index[term] = postings

        return idx

    def save_binary(self, path: Union[str, Path]) -> None:
        """使用 Pickle (Protocol 5) + Gzip (Level 6) 原子持久化二進位快取"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()
        pkl_bytes = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        compressed_bytes = gzip.compress(pkl_bytes, compresslevel=6)

        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(compressed_bytes)

        os.replace(str(tmp_path), str(out_path))
        logger.debug(f"Saved binary inverted index to: {out_path} ({len(compressed_bytes)} bytes)")

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "InvertedIndex":
        """自二進位 Gzip 快取反序列化 InvertedIndex"""
        in_path = Path(path)
        if not in_path.exists():
            raise FileNotFoundError(f"Binary inverted index cache not found: {in_path}")

        with open(in_path, "rb") as f:
            compressed_bytes = f.read()

        pkl_bytes = gzip.decompress(compressed_bytes)
        data = pickle.loads(pkl_bytes)
        return cls.from_dict(data)


class BM25Engine:
    """多欄位加權 BM25 檢索引擎"""

    DEFAULT_WEIGHTS = {
        "name": 3.5,
        "signature": 2.0,
        "members": 2.0,
        "docstring": 1.5,
    }

    def __init__(
        self,
        tokenizer: Optional[CodeTokenizer] = None,
        thesaurus: Optional[ThesaurusEngine] = None,
        field_weights: Optional[Dict[str, float]] = None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.tokenizer = tokenizer or CodeTokenizer()
        self.thesaurus = thesaurus or ThesaurusEngine()
        self.field_weights = field_weights or dict(self.DEFAULT_WEIGHTS)
        self.k1 = k1
        self.b = b

    def _compute_idf(self, doc_freq: int, total_docs: int) -> float:
        """平滑 IDF 計算公式：ln(1 + (N - n + 0.5) / (n + 0.5))"""
        numerator = total_docs - doc_freq + 0.5
        denominator = doc_freq + 0.5
        return math.log(1.0 + max(0.0, numerator / denominator))

    def search(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
    ) -> List[SearchResult]:
        """
        執行多欄位加權語意檢索。
        """
        if not query or not query.strip() or index.doc_count == 0:
            return []

        flt = filter_cfg or QueryFilter()
        raw_query = query.strip()

        # 1. 分詞與同義詞擴展
        base_tokens = self.tokenizer.tokenize(raw_query)
        if not base_tokens:
            return []

        expanded_tokens = self.thesaurus.expand_query(base_tokens)

        # 2. 候選文檔計分累加器: doc_id -> (score, matched_terms, posting)
        doc_scores: Dict[str, float] = defaultdict(float)
        doc_matches: Dict[str, Set[str]] = defaultdict(set)
        doc_postings: Dict[str, Posting] = {}

        N = index.doc_count

        for term in expanded_tokens:
            postings = index.index.get(term, [])
            if not postings:
                continue

            # IDF 權重
            n_q = len(postings)
            idf = self._compute_idf(n_q, N)

            for posting in postings:
                doc_id = posting.doc_id
                doc_postings[doc_id] = posting
                doc_matches[doc_id].add(term)

                # 多欄位 BM25 評分計算
                field_scores_sum = 0.0
                for f_name, weight in self.field_weights.items():
                    tf = posting.field_freqs.get(f_name, 0)
                    if tf <= 0:
                        continue
                    dl = posting.field_lengths.get(f_name, 1)
                    avgdl = max(1.0, index.field_avgdl.get(f_name, 1.0))

                    # BM25 tf normalization
                    norm_tf = (tf * (self.k1 + 1.0)) / (
                        tf + self.k1 * (1.0 - self.b + self.b * (dl / avgdl)) + 1e-9
                    )
                    field_scores_sum += weight * norm_tf

                term_score = idf * field_scores_sum
                doc_scores[doc_id] += term_score

        # 3. Exact Match 置頂加權 (2.0x Boost)
        clean_raw_query = raw_query.lower()
        for doc_id, base_score in list(doc_scores.items()):
            sym = index.get_symbol(doc_id)
            if not sym:
                continue
            sym_name_clean = sym.name.lower()
            last_segment = sym_name_clean.split(".")[-1].split("::")[-1]

            if clean_raw_query == sym_name_clean or clean_raw_query == last_segment:
                doc_scores[doc_id] = base_score * 2.0

        # 4. 條件過濾與結果封裝
        results: List[SearchResult] = []
        for doc_id, score in doc_scores.items():
            if score < flt.min_score:
                continue

            sym = index.get_symbol(doc_id)
            if not sym:
                continue

            posting = doc_postings[doc_id]
            sp = posting.space

            # 過濾 space
            if flt.spaces and sp not in flt.spaces:
                continue
            # 過濾 language
            if flt.languages and sym.language not in flt.languages:
                continue
            # 過濾 kind
            if flt.kinds and sym.kind not in flt.kinds:
                continue

            # 產生摘要片段 (Snippet)
            snippet = sym.docstring.split("\n")[0] if sym.docstring else sym.signature
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."

            results.append(
                SearchResult(
                    symbol=sym,
                    score=score,
                    matched_terms=sorted(list(doc_matches[doc_id])),
                    space=sp,
                    snippet=snippet,
                )
            )

        # 按分數降序排列
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:flt.limit]
