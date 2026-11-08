"""
knowledge-db 複合檢索與 RRF 倒數排名融合引擎 (HybridSearchEngine)
結合 BM25 關鍵字檢索與語意向量檢索，具備 100% 雙軌剛性降級保證。
"""

from typing import Any, Dict, List, Optional, Set, Union

from core.log import log_warn

from .embedding import EmbeddingService, VectorIndex
from .retrieval import QueryFilter, _extract_file_ext, normalize_ftypes, resolve_space_weight
from .schema import UnifiedSymbol

DEFAULT_RRF_K = 60
DEFAULT_WEIGHT_LEXICAL = 0.5
DEFAULT_WEIGHT_VECTOR = 0.5
DEFAULT_MIN_VECTOR_SIMILARITY = 0.70


class HybridSearchEngine:
    """
    BM25 + 向量 RRF (Reciprocal Rank Fusion) 複合檢索引擎
    """

    def __init__(
        self,
        inverted_index: Any = None,
        vector_index: Optional[VectorIndex] = None,
        embedding_service: Optional[EmbeddingService] = None,
        bm25_engine: Optional[Any] = None,
        rrf_k: int = DEFAULT_RRF_K,
        weight_lexical: float = DEFAULT_WEIGHT_LEXICAL,
        weight_vector: float = DEFAULT_WEIGHT_VECTOR,
        min_vector_similarity: float = DEFAULT_MIN_VECTOR_SIMILARITY,
        space_weights: Optional[Dict[str, float]] = None,
    ):
        self.inverted_index = inverted_index
        self.vector_index = vector_index if vector_index is not None else VectorIndex()
        self.embedding_service = embedding_service
        self.bm25_engine = bm25_engine
        self.rrf_k = rrf_k
        self.weight_lexical = weight_lexical
        self.weight_vector = weight_vector
        self.min_vector_similarity = min_vector_similarity
        self.space_weights: Dict[str, float] = dict(space_weights) if space_weights else {}

    def _resolve_symbol_space_weight(
        self,
        sym: Optional[UnifiedSymbol],
        spaces_filter: Optional[List[str]] = None,
        space_weights: Optional[Dict[str, float]] = None,
    ) -> float:
        weights_map = space_weights if space_weights is not None else self.space_weights
        if not weights_map or sym is None:
            return 1.0
        return resolve_space_weight(getattr(sym, "spaces", None), spaces_filter=spaces_filter, space_weights=weights_map)

    @staticmethod
    def _build_bm25_results(
        bm25_hits: List[Dict[str, Any]],
        symbols_map: Dict[str, UnifiedSymbol],
        limit: int,
        mode: str = "lexical_bm25",
    ) -> List[Dict[str, Any]]:
        return [
            {
                "symbol": symbols_map.get(hit["doc_id"]),
                "score": hit["score"],
                "matched_terms": hit.get("matched_terms", []),
                "mode": mode,
            }
            for hit in bm25_hits[:limit]
        ]

    @property
    def is_vector_available(self) -> bool:
        """檢查向量檢索子系統是否完全就緒"""
        return (
            self.embedding_service is not None
            and self.embedding_service.is_available
            and self.vector_index is not None
            and len(self.vector_index.doc_ids) > 0
        )

    def compute_rrf(
        self,
        lexical_ranks: Dict[str, int],
        vector_ranks: Dict[str, int],
    ) -> Dict[str, float]:
        """
        標準 RRF 倒數排名融合演算法：
        Score(d) = w_lex / (k + rank_lex) + w_vec / (k + rank_vec)
        """
        all_doc_ids: Set[str] = set(lexical_ranks.keys()) | set(vector_ranks.keys())
        rrf_scores: Dict[str, float] = {}

        for doc_id in all_doc_ids:
            score = 0.0
            if doc_id in lexical_ranks:
                score += self.weight_lexical / (self.rrf_k + lexical_ranks[doc_id])
            if doc_id in vector_ranks:
                score += self.weight_vector / (self.rrf_k + vector_ranks[doc_id])
            rrf_scores[doc_id] = score

        return rrf_scores

    def search(
        self,
        query: str,
        limit: int = 10,
        file_types: Optional[Union[str, List[str]]] = None,
        spaces: Optional[List[str]] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        lexical_only: bool = False,
        space_weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        執行複合檢索：
        1. 若 lexical_only 為 True 或向量服務未就緒，100% 平滑退化為純 BM25 檢索。
        2. 否則並行獲取 BM25 排名與向量語意排名，計算 RRF 融合分數並重排輸出。
        """
        if not query or not str(query).strip():
            return []

        effective_weights = space_weights if space_weights is not None else self.space_weights
        norm_ftypes = normalize_ftypes(file_types) or None

        # 1. 執行 BM25 倒排檢索 (擷取足夠候選集供融合)
        fetch_limit = max(limit * 3, 30)
        bm25_hits: List[Dict[str, Any]] = []
        symbols_map = getattr(self.inverted_index, "symbols", {}) if self.inverted_index else {}
        if self.bm25_engine is not None and self.inverted_index is not None:
            flt = QueryFilter(
                spaces=spaces,
                kinds=kinds,
                languages=languages,
                ftypes=list(norm_ftypes) if norm_ftypes else None,
                limit=fetch_limit,
                space_weights=effective_weights if effective_weights else None,
            )
            raw_res = self.bm25_engine.search(query=query, index=self.inverted_index, filter_cfg=flt)
            bm25_hits = [
                {
                    "doc_id": r.symbol.id,
                    "score": r.score,
                    "matched_terms": r.matched_terms,
                }
                for r in raw_res
            ]

        # 2. 若指定 lexical_only 或向量管線未就緒，執行 100% 剛性平滑降級
        if lexical_only or not self.is_vector_available:
            return self._build_bm25_results(bm25_hits, symbols_map, limit, mode="lexical_bm25")

        # 3. 執行語意向量檢索
        try:
            query_vec = self.embedding_service.embed_query(query)
            raw_vector_hits = self.vector_index.search(query_vec, top_k=fetch_limit)
        except Exception as e:
            log_warn(f"Vector search failed ({e}), falling back to pure BM25.", stream="stderr")
            return self._build_bm25_results(bm25_hits, symbols_map, limit, mode="fallback_bm25")

        # 依 file_types、spaces、kinds、languages 與純語意相似度門檻過濾向量候選集
        filtered_vector_hits = []
        lexical_doc_ids = {hit["doc_id"] for hit in bm25_hits}
        for doc_id, sim in raw_vector_hits:
            sym = symbols_map.get(doc_id)
            if sym is None:
                continue
            if norm_ftypes and _extract_file_ext(sym.file_path) not in norm_ftypes:
                continue
            if spaces and not any(
                s in spaces or s.split("/")[-1] in {f.split("/")[-1] for f in spaces}
                for s in getattr(sym, "spaces", [])
            ):
                continue
            if kinds and sym.kind not in kinds:
                continue
            if languages and sym.language not in languages:
                continue
            if doc_id not in lexical_doc_ids and sim < self.min_vector_similarity:
                continue
            filtered_vector_hits.append((doc_id, sim))

        # 4. 構建 1-indexed 排名字典
        lexical_ranks: Dict[str, int] = {
            hit["doc_id"]: rank for rank, hit in enumerate(bm25_hits, start=1)
        }
        vector_ranks: Dict[str, int] = {
            doc_id: rank for rank, (doc_id, _) in enumerate(filtered_vector_hits, start=1)
        }

        # 5. RRF 倒數排名融合與空間權重乘算
        rrf_scores = self.compute_rrf(lexical_ranks, vector_ranks)
        if effective_weights:
            for doc_id in list(rrf_scores.keys()):
                sym = symbols_map.get(doc_id)
                sp_w = self._resolve_symbol_space_weight(sym, spaces_filter=spaces, space_weights=effective_weights)
                rrf_scores[doc_id] = rrf_scores[doc_id] * sp_w

        sorted_doc_ids = sorted(
            rrf_scores.keys(),
            key=lambda d: rrf_scores[d],
            reverse=True,
        )

        bm25_terms_map = {hit["doc_id"]: hit.get("matched_terms", []) for hit in bm25_hits}

        final_results = []
        for doc_id in sorted_doc_ids[:limit]:
            sym = symbols_map.get(doc_id)
            if sym is None:
                continue
            final_results.append({
                "symbol": sym,
                "score": float(rrf_scores[doc_id]),
                "matched_terms": bm25_terms_map.get(doc_id, []),
                "lexical_rank": lexical_ranks.get(doc_id),
                "vector_rank": vector_ranks.get(doc_id),
                "mode": "hybrid_rrf",
            })

        return final_results
