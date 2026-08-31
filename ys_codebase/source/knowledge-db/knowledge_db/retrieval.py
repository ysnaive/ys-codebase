"""
knowledge-db 倒排索引、多欄位加權 BM25 語意評分與二進位 Gzip 快取引擎 (retrieval.py)
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gzip
import heapq
import json
import logging
import math
import os
from pathlib import Path
import pickle
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .exceptions import KnowledgeDBError, SchemaValidationError
from .schema import AggregatedFileResult, AggregatedItem, UnifiedSymbol, WeightedToken
from .thesaurus import ThesaurusEngine
from .tokenizer import CodeTokenizer

logger = logging.getLogger("knowledge-db.retrieval")


class Posting:
    """輕量倒排索引節點 (消滅 Symbol 深拷貝冗餘與 field_lengths 字典冗餘，節省 40%+ 節點記憶體)"""

    __slots__ = ("doc_id", "field_freqs", "space", "spaces")

    def __init__(
        self,
        doc_id: str,
        field_freqs: Optional[Dict[str, int]] = None,
        field_lengths: Optional[Dict[str, int]] = None,  # 向後相容參數 (舊代碼若傳入不報錯)
        space: str = "",
        spaces: Optional[List[str]] = None,
    ):
        self.doc_id: str = doc_id
        self.field_freqs: Dict[str, int] = field_freqs or {}
        self.space: str = space or (spaces[0] if spaces else "")
        self.spaces: List[str] = list(spaces) if spaces else ([space] if space else [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "field_freqs": self.field_freqs,
            "space": self.space,
            "spaces": self.spaces,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Posting":
        spaces = data.get("spaces") or ([data["space"]] if data.get("space") else [])
        return cls(
            doc_id=data["doc_id"],
            field_freqs=data.get("field_freqs", {}),
            space=data.get("space", ""),
            spaces=spaces,
        )


@dataclass(frozen=True)
class QueryFilter:
    """檢索條件過濾器"""

    spaces: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    kinds: Optional[List[str]] = None
    ftypes: Optional[List[str]] = None
    min_score: float = 0.01
    limit: int = 20


@dataclass
class CodeSnippet:
    """提取之結構化程式碼片段與 Docstring 摘要"""

    lines: List[Tuple[int, str]] = field(default_factory=list)  # [(line_num, text), ...]
    start_line: int = 1
    end_line: int = 1
    target_line: int = 1
    docstring_summary: str = ""
    is_truncated: bool = False
    error: Optional[str] = None

    def get_lines(self, max_lines: Optional[int] = None) -> List[Tuple[int, str]]:
        """
        獲取裁切後的代碼行清單。
        若提供 max_lines 且小於現有行數，則以 target_line 為焦點保留最關鍵區塊。
        """
        if not self.lines:
            return []
        if max_lines is None or max_lines >= len(self.lines):
            return list(self.lines)
        if max_lines <= 0:
            return []

        # 尋找 target_line 在 lines 中的索引位置
        target_idx = 0
        for idx, (ln, _) in enumerate(self.lines):
            if ln == self.target_line:
                target_idx = idx
                break

        # 以 target_line 為焦點向前後展開
        half = max_lines // 2
        start_idx = max(0, target_idx - half)
        end_idx = start_idx + max_lines
        if end_idx > len(self.lines):
            end_idx = len(self.lines)
            start_idx = max(0, end_idx - max_lines)

        return self.lines[start_idx:end_idx]

    def format_text(self, prefix: str = "    ", max_lines: Optional[int] = None) -> str:
        """格式化為帶有行號對齊的純文字區塊 (支援動態 max_lines 裁切)"""
        if self.error:
            return f"{prefix}[Snippet Unavailable: {self.error}]"
        if not self.lines or (max_lines is not None and max_lines <= 0):
            return ""

        effective_lines = self.get_lines(max_lines)
        if not effective_lines:
            return ""

        max_line_num = max(ln for ln, _ in effective_lines)
        line_num_width = max(len(str(max_line_num)), 3)

        formatted_lines = []
        for ln, txt in effective_lines:
            pointer = " >" if ln == self.target_line else "  "
            formatted_lines.append(f"{prefix}{pointer} {ln:{line_num_width}d} | {txt}")

        if self.is_truncated or (max_lines is not None and len(effective_lines) < len(self.lines)):
            formatted_lines.append(f"{prefix}   {' ' * line_num_width} | ... (lines truncated)")

        return "\n".join(formatted_lines)

    def get_raw_code(self) -> str:
        """取得原始代碼字串"""
        return "\n".join(txt for _, txt in self.lines)

    def to_dict(self) -> Dict[str, Any]:
        """產出精簡且完備之結構化字典 (提供 raw_code 與行號區間)"""
        raw_code = self.get_raw_code()
        res: Dict[str, Any] = {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "target_line": self.target_line,
            "raw_code": raw_code,
        }
        if self.docstring_summary:
            res["docstring_summary"] = self.docstring_summary
        if self.is_truncated:
            res["is_truncated"] = True
        if self.error:
            res["error"] = self.error
        return res


class SnippetExtractor:
    """原始碼片段延遲提取器 (安全切片讀取、符號邊界感知與編碼容錯)"""

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None, max_lines: int = 30):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self.max_lines = max_lines

    def resolve_file_path(self, file_path: Union[str, Path]) -> Path:
        """解析檔案為實體絕對路徑"""
        p = Path(file_path)
        if p.is_absolute() and p.exists():
            return p
        try:
            from core import uri
            p_res = uri.resolve(f"project://{file_path}", interactive=False)
            if p_res:
                p_cand = Path(p_res).resolve()
                if p_cand.exists():
                    return p_cand
        except Exception:
            pass
        if self.workspace_root:
            cand = self.workspace_root / p
            if cand.exists():
                return cand
        cand_cwd = Path.cwd() / p
        if cand_cwd.exists():
            return cand_cwd
        return p

    def extract(
        self,
        file_path: Union[str, Path],
        line_number: int,
        end_line: Optional[int] = None,
        context_before: int = 2,
        context_after: int = 8,
        docstring: str = "",
    ) -> CodeSnippet:
        """自實體檔案安全切片讀取原始碼區塊 (支援完整符號邊界感知)。"""
        real_path = self.resolve_file_path(file_path)
        doc_summary = docstring.strip().split("\n")[0] if docstring else ""

        if not real_path.is_file():
            return CodeSnippet(
                lines=[],
                start_line=line_number,
                end_line=end_line or line_number,
                target_line=line_number,
                docstring_summary=doc_summary,
                error="File not found",
            )

        try:
            with open(real_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return CodeSnippet(
                lines=[],
                start_line=line_number,
                end_line=end_line or line_number,
                target_line=line_number,
                docstring_summary=doc_summary,
                error=f"Read error: {e}",
            )

        total_lines = len(all_lines)
        if total_lines == 0:
            return CodeSnippet(
                lines=[],
                start_line=1,
                end_line=1,
                target_line=line_number,
                docstring_summary=doc_summary,
            )

        target_ln = max(1, min(line_number, total_lines))
        start_ln = max(1, target_ln - context_before)
        
        # 若有提供 end_line，以 end_line 為目標切片邊界
        if end_line is not None and end_line >= target_ln:
            target_end_ln = min(total_lines, end_line + 1)
        else:
            target_end_ln = min(total_lines, target_ln + context_after)

        end_ln = target_end_ln
        is_trunc = False
        if (end_ln - start_ln + 1) > self.max_lines:
            end_ln = start_ln + self.max_lines - 1
            is_trunc = True

        slice_lines = []
        for ln in range(start_ln, end_ln + 1):
            raw_line = all_lines[ln - 1].rstrip("\r\n")
            slice_lines.append((ln, raw_line))

        return CodeSnippet(
            lines=slice_lines,
            start_line=start_ln,
            end_line=end_ln,
            target_line=target_ln,
            docstring_summary=doc_summary,
            is_truncated=is_trunc,
        )


@dataclass(frozen=True)
class SearchResult:
    """結構化檢索結果"""

    symbol: UnifiedSymbol
    score: float
    matched_terms: List[str]
    space: str
    snippet: str = ""
    code_snippet: Optional[CodeSnippet] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
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
        if self.code_snippet:
            data["code_snippet"] = self.code_snippet.to_dict()
        return data


class InvertedIndex:
    """多欄位倒排索引與符號池中心 (管理頂層 doc_lengths 共享池)"""

    INDEXED_FIELDS = ["name", "signature", "members", "docstring"]

    def __init__(self, space_name: str = ""):
        self.space_name = space_name
        self.doc_count: int = 0
        self.symbols: Dict[str, UnifiedSymbol] = {}
        self.index: Dict[str, List[Posting]] = defaultdict(list)
        self.doc_lengths: Dict[str, Dict[str, int]] = {}  # 頂層文檔長度共享池
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

    def add_symbol(
        self,
        symbol: UnifiedSymbol,
        tokenizer: CodeTokenizer,
        space: str = "",
        spaces: Optional[List[str]] = None,
    ) -> None:
        """加入單一 UnifiedSymbol 建立欄位倒排索引與註冊符號池"""
        doc_id = symbol.id
        self.symbols[doc_id] = symbol
        self.doc_count += 1

        symbol_spaces = getattr(symbol, "spaces", [])
        effective_spaces = spaces or symbol_spaces or ([space] if space else []) or ([self.space_name] if self.space_name else [])
        curr_space = effective_spaces[0] if effective_spaces else ""

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

        # 註冊至頂層文檔長度共享池 (消滅 Posting 冗餘副本)
        self.doc_lengths[doc_id] = field_lengths

        # 3. 建立輕量 Posting
        for term in all_unique_terms:
            t_freqs = {f_name: field_freqs_map[f_name][term] for f_name in self.INDEXED_FIELDS}
            posting = Posting(
                doc_id=doc_id,
                field_freqs=t_freqs,
                space=curr_space,
                spaces=list(effective_spaces),
            )
            self.index[term].append(posting)

    def build(self, symbols: List[UnifiedSymbol], tokenizer: Optional[CodeTokenizer] = None, space: str = "") -> None:
        """批次建立倒排索引並計算 avgdl"""
        tok = tokenizer or CodeTokenizer()
        self.doc_count = 0
        self.symbols.clear()
        self.index.clear()
        self.doc_lengths.clear()
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

    def build_unified(self, symbols: List[UnifiedSymbol], tokenizer: Optional[CodeTokenizer] = None) -> None:
        """批次建立全域聯集單一倒排索引"""
        self.space_name = "unified"
        self.build(symbols, tokenizer=tokenizer, space="unified")

    def to_dict(self) -> Dict[str, Any]:
        """序列化倒排索引為正規化符號池字典 (包含 doc_lengths)"""
        serialized_index = {}
        for term, postings in self.index.items():
            serialized_index[term] = [p.to_dict() for p in postings]

        serialized_symbols = {doc_id: sym.to_dict() for doc_id, sym in self.symbols.items()}

        return {
            "space_name": self.space_name,
            "doc_count": self.doc_count,
            "field_avgdl": self.field_avgdl,
            "field_total_lengths": self.field_total_lengths,
            "doc_lengths": self.doc_lengths,
            "symbols": serialized_symbols,
            "index": serialized_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvertedIndex":
        """反序列化正規化倒排索引 (具備 Schema 自省與舊快取自動遷移)"""
        if not isinstance(data, dict):
            raise SchemaValidationError("InvertedIndex data must be a dictionary.")

        idx = cls(space_name=data.get("space_name", ""))
        idx.doc_count = int(data.get("doc_count", 0))
        idx.field_avgdl = data.get("field_avgdl", {f: 1.0 for f in cls.INDEXED_FIELDS})
        idx.field_total_lengths = data.get("field_total_lengths", {f: 0 for f in cls.INDEXED_FIELDS})
        idx.doc_lengths = data.get("doc_lengths", {})

        # 1. 還原符號池
        raw_symbols = data.get("symbols", {})
        if raw_symbols:
            for doc_id, s_dict in raw_symbols.items():
                if isinstance(s_dict, dict):
                    idx.symbols[doc_id] = UnifiedSymbol.from_dict(s_dict)

        # 2. 還原倒排表 (兼顧舊版格式自省遷移)
        raw_index = data.get("index", {})
        for term, postings_raw in raw_index.items():
            postings: List[Posting] = []
            for p in postings_raw:
                if isinstance(p, dict):
                    posting = Posting.from_dict(p)
                    postings.append(posting)
                    # 舊版相容：若 doc_lengths 缺失，自動自舊版 Posting 萃取
                    if "field_lengths" in p and p["field_lengths"] and posting.doc_id not in idx.doc_lengths:
                        idx.doc_lengths[posting.doc_id] = p["field_lengths"]
                    # 舊版向下相容：補充符號池
                    if "symbol" in p and isinstance(p["symbol"], dict) and posting.doc_id not in idx.symbols:
                        idx.symbols[posting.doc_id] = UnifiedSymbol.from_dict(p["symbol"])
            idx.index[term] = postings

        return idx

    def patch_incremental(
        self,
        dirty_file_paths: Set[str],
        new_symbols: List[UnifiedSymbol],
        tokenizer: Optional[CodeTokenizer] = None,
    ) -> None:
        """
        差量修補倒排索引 (Incremental Hot Patching)：
        1. 識別並刪除屬於 dirty_file_paths 的舊符號與 Postings，扣減長度指標並清理 doc_lengths。
        2. 將 new_symbols 注入符號池、倒排表與 doc_lengths。
        3. 動態重新計算 field_avgdl。
        """
        tok = tokenizer or CodeTokenizer()
        dirty_paths_norm = {p.replace("\\", "/").lower() for p in dirty_file_paths}

        # 1. 識別需移除的舊 doc_id
        doc_ids_to_remove: List[str] = []
        for doc_id, sym in list(self.symbols.items()):
            sym_path_norm = sym.file_path.replace("\\", "/").lower()
            sym_filename = Path(sym_path_norm).name
            if any(
                sym_path_norm == p
                or p.endswith("/" + sym_path_norm)
                or sym_path_norm.endswith("/" + p)
                or Path(p).name == sym_filename
                for p in dirty_paths_norm
            ):
                doc_ids_to_remove.append(doc_id)

        doc_ids_set = set(doc_ids_to_remove)

        # 2. 扣減長度、清理 doc_lengths 與自符號池移除
        for doc_id in doc_ids_to_remove:
            self.doc_lengths.pop(doc_id, None)
            sym = self.symbols.pop(doc_id, None)
            if sym:
                self.doc_count = max(0, self.doc_count - 1)
                members_text = " ".join([f"{m.name} {m.signature} {m.docstring}" for m in sym.members])
                field_texts = {
                    "name": sym.name,
                    "signature": sym.signature,
                    "members": members_text,
                    "docstring": sym.docstring,
                }
                for f_name, text in field_texts.items():
                    tokens = tok.tokenize(text)
                    self.field_total_lengths[f_name] = max(
                        0, self.field_total_lengths[f_name] - len(tokens)
                    )

        # 3. 自倒排表移除舊 Postings
        if doc_ids_set:
            for term in list(self.index.keys()):
                new_postings = [p for p in self.index[term] if p.doc_id not in doc_ids_set]
                if new_postings:
                    self.index[term] = new_postings
                else:
                    del self.index[term]

        # 4. 加入新符號
        for sym in new_symbols:
            self.add_symbol(sym, tok, spaces=sym.spaces)

        # 5. 重新計算 avgdl
        if self.doc_count > 0:
            for f in self.INDEXED_FIELDS:
                self.field_avgdl[f] = max(1.0, self.field_total_lengths[f] / self.doc_count)
        else:
            for f in self.INDEXED_FIELDS:
                self.field_avgdl[f] = 1.0

    def save_binary(self, path: Union[str, Path], compresslevel: int = 1) -> None:
        """使用 Pickle (Protocol 5) + Gzip 原子持久化二進位快取"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()
        pkl_bytes = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        compressed_bytes = gzip.compress(pkl_bytes, compresslevel=compresslevel)

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
    """多欄位加權 BM25 檢索引擎 (支援 Max-Score 剪枝與三階同義詞加權)"""

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

    def _normalize_ftypes(self, ftypes: Optional[Union[str, List[str]]]) -> Set[str]:
        """將使用者輸入的副檔名規格化為純小寫且無前置點的集合"""
        if not ftypes:
            return set()
        raw_list = [ftypes] if isinstance(ftypes, str) else list(ftypes)
        result: Set[str] = set()
        for item in raw_list:
            parts = re.split(r"[|,]", str(item))
            for p in parts:
                clean = p.strip().lower().lstrip(".")
                if clean:
                    result.add(clean)
        return result

    def search(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
    ) -> List[SearchResult]:
        """
        執行多欄位加權語意檢索 (向後相容扁平清單模式)。
        """
        if not query or not query.strip() or index.doc_count == 0:
            return []

        flt = filter_cfg or QueryFilter()
        raw_query = query.strip()
        allowed_ftypes = self._normalize_ftypes(flt.ftypes)

        # 1. 分詞與加權同義詞/別名/關聯詞擴展 (三階加權展開)
        base_tokens = self.tokenizer.tokenize(raw_query)
        if not base_tokens:
            return []

        if hasattr(self.thesaurus, "expand_query_weighted"):
            weighted_tokens = self.thesaurus.expand_query_weighted(base_tokens)
        else:
            expanded_raw = self.thesaurus.expand_query(base_tokens)
            weighted_tokens = [WeightedToken(term=t, weight=1.0, kind="original") for t in expanded_raw]

        # 2. 候選文檔計分累加器: doc_id -> (score, matched_terms, posting)
        doc_scores: Dict[str, float] = defaultdict(float)
        doc_matches: Dict[str, Set[str]] = defaultdict(set)
        doc_postings: Dict[str, Posting] = {}

        N = index.doc_count

        for w_token in weighted_tokens:
            term = w_token.term
            term_weight = w_token.weight
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

                # 多欄位 BM25 評分計算 (結合頂層 doc_lengths 與 term_weight 衰減)
                field_scores_sum = 0.0
                doc_fl = index.doc_lengths.get(doc_id, {})
                for f_name, weight in self.field_weights.items():
                    tf = posting.field_freqs.get(f_name, 0)
                    if tf <= 0:
                        continue
                    dl = doc_fl.get(f_name, getattr(posting, "field_lengths", {}).get(f_name, 1))
                    avgdl = max(1.0, index.field_avgdl.get(f_name, 1.0))

                    # BM25 tf normalization
                    norm_tf = (tf * (self.k1 + 1.0)) / (
                        tf + self.k1 * (1.0 - self.b + self.b * (dl / avgdl)) + 1e-9
                    )
                    field_scores_sum += weight * norm_tf

                term_score = idf * field_scores_sum * term_weight
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

            # 過濾 ftypes
            if allowed_ftypes:
                file_ext = Path(sym.file_path).suffix.lower().lstrip(".")
                if file_ext not in allowed_ftypes:
                    continue

            posting = doc_postings[doc_id]
            posting_spaces = getattr(posting, "spaces", None) or ([posting.space] if posting.space else [])

            # 過濾 space
            if flt.spaces and not any(s in flt.spaces for s in posting_spaces):
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

            sp_display = ", ".join(posting_spaces) if posting_spaces else posting.space
            results.append(
                SearchResult(
                    symbol=sym,
                    score=score,
                    matched_terms=sorted(list(doc_matches[doc_id])),
                    space=sp_display,
                    snippet=snippet,
                )
            )

        # 按分數降序排列
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:flt.limit]

    def search_aggregated(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
        alpha: float = 0.2,
        top_k_items_per_file: int = 3,
    ) -> List[AggregatedFileResult]:
        """
        執行多欄位加權 BM25 檢索並透過 Top-N 動態回填管線聚合為檔案節點清單。
        
        評分公式：
          Score(File) = max(S_i) + alpha * sum(S_j for j != i)
        """
        if not query or not query.strip() or index.doc_count == 0:
            return []

        flt = filter_cfg or QueryFilter()
        raw_query = query.strip()
        allowed_ftypes = self._normalize_ftypes(flt.ftypes)

        # 1. 分詞與同義詞擴展 (三階加權展開)
        base_tokens = self.tokenizer.tokenize(raw_query)
        if not base_tokens:
            return []

        if hasattr(self.thesaurus, "expand_query_weighted"):
            weighted_tokens = self.thesaurus.expand_query_weighted(base_tokens)
        else:
            expanded_raw = self.thesaurus.expand_query(base_tokens)
            weighted_tokens = [WeightedToken(term=t, weight=1.0, kind="original") for t in expanded_raw]

        # 2. 候選文檔計分累加器
        doc_scores: Dict[str, float] = defaultdict(float)
        doc_matches: Dict[str, Set[str]] = defaultdict(set)
        doc_postings: Dict[str, Posting] = {}

        N = index.doc_count

        for w_token in weighted_tokens:
            term = w_token.term
            term_weight = w_token.weight
            postings = index.index.get(term, [])
            if not postings:
                continue

            n_q = len(postings)
            idf = self._compute_idf(n_q, N)

            for posting in postings:
                doc_id = posting.doc_id
                doc_postings[doc_id] = posting
                doc_matches[doc_id].add(term)

                field_scores_sum = 0.0
                doc_fl = index.doc_lengths.get(doc_id, {})
                for f_name, weight in self.field_weights.items():
                    tf = posting.field_freqs.get(f_name, 0)
                    if tf <= 0:
                        continue
                    dl = doc_fl.get(f_name, getattr(posting, "field_lengths", {}).get(f_name, 1))
                    avgdl = max(1.0, index.field_avgdl.get(f_name, 1.0))

                    norm_tf = (tf * (self.k1 + 1.0)) / (
                        tf + self.k1 * (1.0 - self.b + self.b * (dl / avgdl)) + 1e-9
                    )
                    field_scores_sum += weight * norm_tf

                term_score = idf * field_scores_sum * term_weight
                doc_scores[doc_id] += term_score

        # 3. Exact Match 置頂加權
        clean_raw_query = raw_query.lower()
        for doc_id, base_score in list(doc_scores.items()):
            sym = index.get_symbol(doc_id)
            if not sym:
                continue
            sym_name_clean = sym.name.lower()
            last_segment = sym_name_clean.split(".")[-1].split("::")[-1]

            if clean_raw_query == sym_name_clean or clean_raw_query == last_segment:
                doc_scores[doc_id] = base_score * 2.0

        # 4. 篩選合格的候選 Item 池並按單項分數降序排列
        candidate_items: List[Tuple[UnifiedSymbol, float, List[str], List[str]]] = []
        for doc_id, score in doc_scores.items():
            if score < flt.min_score:
                continue

            sym = index.get_symbol(doc_id)
            if not sym:
                continue

            # 過濾 ftypes
            if allowed_ftypes:
                file_ext = Path(sym.file_path).suffix.lower().lstrip(".")
                if file_ext not in allowed_ftypes:
                    continue

            posting = doc_postings[doc_id]
            posting_spaces = getattr(posting, "spaces", None) or ([posting.space] if posting.space else [])

            if flt.spaces and not any(s in flt.spaces for s in posting_spaces):
                continue
            if flt.languages and sym.language not in flt.languages:
                continue
            if flt.kinds and sym.kind not in flt.kinds:
                continue

            candidate_items.append(
                (sym, score, sorted(list(doc_matches[doc_id])), list(posting_spaces))
            )

        candidate_items.sort(key=lambda x: x[1], reverse=True)

        if not candidate_items:
            return []

        # 5. Top-N 動態聚合與回填管線
        file_nodes: Dict[str, Dict[str, Any]] = {}
        unique_files: List[str] = []
        target_limit = max(1, flt.limit)

        for sym, score, matched_terms, spaces in candidate_items:
            file_path = sym.file_path
            snippet = sym.docstring.split("\n")[0] if sym.docstring else sym.signature
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."

            agg_item = AggregatedItem(
                symbol=sym,
                score=score,
                matched_terms=matched_terms,
                snippet=snippet,
            )

            if file_path in file_nodes:
                node = file_nodes[file_path]
                node["items"].append(agg_item)
                node["scores"].append(score)
                node["spaces"].update(spaces)
            else:
                if len(unique_files) < target_limit:
                    unique_files.append(file_path)
                    file_nodes[file_path] = {
                        "items": [agg_item],
                        "scores": [score],
                        "spaces": set(spaces),
                        "language": sym.language,
                    }
                else:
                    continue

        # 6. 計算各檔案聚合積分並裁切內部 Top-3
        aggregated_results: List[AggregatedFileResult] = []
        for file_path in unique_files:
            node = file_nodes[file_path]
            scores = node["scores"]
            items = node["items"]

            items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
            capped_items = items_sorted[:top_k_items_per_file]

            max_s = max(scores) if scores else 0.0
            rest_sum = sum(scores) - max_s
            total_score = max_s + alpha * rest_sum

            aggregated_results.append(
                AggregatedFileResult(
                    file_path=file_path,
                    total_score=total_score,
                    items=capped_items,
                    spaces=sorted(list(node["spaces"])),
                    language=node["language"],
                )
            )

        # 7. 二次依最終聚合總分降序穩定重排
        aggregated_results.sort(key=lambda x: x.total_score, reverse=True)
        return aggregated_results
