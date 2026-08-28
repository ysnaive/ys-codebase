"""
knowledge-db 模組頂層統一門面 SDK (KnowledgeEngine)
100% 純 Python 原生標準庫實現 (Zero External Dependency)
"""

from collections import defaultdict
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Union

from .bundler import SemanticBundle, SemanticBundler
from .exceptions import KnowledgeDBError, SpaceNotFoundError
from .parsers.registry import ParserRegistry
from .retrieval import BM25Engine, InvertedIndex, QueryFilter, SearchResult
from .scanner import FingerprintScanner, ScanDiffResult
from .schema import SpaceConfig, UnifiedSymbol
from .space import SpaceManager
from .thesaurus import ThesaurusEngine
from .tokenizer import CodeTokenizer

logger = logging.getLogger("knowledge-db.engine")


class KnowledgeEngine:
    """knowledge-db 模組頂層統一門面 Facade"""

    def __init__(
        self,
        core_context: Optional[Any] = None,
        config_dir: Optional[Union[str, Path]] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
    ):
        self.space_manager = SpaceManager(
            core_context=core_context,
            config_dir=config_dir,
            storage_dir=storage_dir,
            contributes_data=contributes_data,
        )
        self.scanner = FingerprintScanner(self.space_manager)
        self.parser_registry = ParserRegistry(register_defaults=True)
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
            scanner=self.scanner,
        )
        self.tokenizer = CodeTokenizer()
        self.thesaurus = ThesaurusEngine(custom_groups=self.space_manager.load_thesaurus())
        self.bm25_engine = BM25Engine(tokenizer=self.tokenizer, thesaurus=self.thesaurus)

        self._index_cache: Dict[str, InvertedIndex] = {}

    @property
    def storage_dir(self) -> Path:
        return self.space_manager.storage_dir

    def status(self) -> Dict[str, Any]:
        """
        取得系統當前空間、指紋、同義詞與索引狀態摘要。
        """
        spaces = self.space_manager.load_spaces()
        thesaurus_groups = self.space_manager.load_thesaurus()

        space_details = {}
        for name, sp in spaces.items():
            fps = self.scanner.load_fingerprints(name)
            idx_file = self.storage_dir / "indices" / f"{name}.index.json"
            space_details[name] = {
                "origin": sp.origin,
                "description": sp.description,
                "include_count": len(sp.include),
                "file_patterns": sp.file_patterns,
                "cached_files": len(fps),
                "has_index": idx_file.exists(),
            }

        return {
            "total_spaces": len(spaces),
            "thesaurus_groups": len(thesaurus_groups),
            "storage_dir": str(self.storage_dir),
            "spaces": space_details,
        }

    def scan(self, space: Optional[str] = None, force: bool = False) -> Dict[str, ScanDiffResult]:
        """
        執行增量/全量指紋比對。
        :param space: 指定空間名稱 (若為 None 則掃描全空間聯集)
        :param force: 是否強制重新計算 SHA1
        """
        if space is not None:
            sp_cfg = self.space_manager.get_space(space)
            diff = self.scanner.scan_space(sp_cfg, force=force)
            return {space: diff}
        else:
            return self.scanner.scan_all_spaces(force=force)

    def bundle(
        self,
        space: Optional[str] = None,
        export_path: Optional[Union[str, Path]] = None,
    ) -> List[SemanticBundle]:
        """
        執行空間符號提取與 SemanticBundle 導出。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        bundles = []
        for sp in targets:
            b = self.bundler.bundle_space(sp)
            self.bundler.export_bundle(b, target_path=export_path)
            bundles.append(b)
        return bundles

    def _get_indices_dir(self) -> Path:
        p = self.storage_dir / "indices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, InvertedIndex]:
        """
        建置空間倒排索引並持久化快取至磁碟。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        indices_dir = self._get_indices_dir()
        result_indices = {}

        for sp in targets:
            sp_name = sp.name
            idx_file = indices_dir / f"{sp_name}.index.json"

            if not force and idx_file.exists():
                try:
                    with open(idx_file, "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    idx = InvertedIndex.from_dict(data)
                    self._index_cache[sp_name] = idx
                    result_indices[sp_name] = idx
                    continue
                except Exception as e:
                    logger.warning(f"Failed loading cached index for '{sp_name}', rebuilding: {e}")

            # 即時打包並構建倒排索引
            bundle = self.bundler.bundle_space(sp)
            idx = InvertedIndex(space_name=sp_name)
            idx.build(bundle.symbols, tokenizer=self.tokenizer, space=sp_name)

            # 原子寫入持久化
            temp_fd, temp_path = tempfile.mkstemp(
                dir=str(indices_dir), prefix="idx_tmp_", suffix=".json"
            )
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    json.dump(idx.to_dict(), f, indent=2, ensure_ascii=False)
                os.replace(temp_path, str(idx_file))
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                raise KnowledgeDBError(f"Failed saving index cache for '{sp_name}': {e}")

            self._index_cache[sp_name] = idx
            result_indices[sp_name] = idx

        return result_indices

    def search(
        self,
        query: str,
        space: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        min_score: float = 0.01,
        limit: int = 10,
    ) -> List[SearchResult]:
        """
        多空間多欄位加權語意檢索 (支援自動懶加載與即時索引建置)。
        """
        if not query or not query.strip():
            return []

        # 1. 確保目標空間已加載倒排索引 (Lazy Indexing, EC-01)
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        all_symbols: List[UnifiedSymbol] = []

        for sp in targets:
            sp_name = sp.name
            if sp_name not in self._index_cache:
                idx_file = self._get_indices_dir() / f"{sp_name}.index.json"
                if idx_file.exists():
                    try:
                        with open(idx_file, "r", encoding="utf-8", errors="replace") as f:
                            data = json.load(f)
                        self._index_cache[sp_name] = InvertedIndex.from_dict(data)
                    except Exception:
                        self.build_index(space=sp_name, force=True)
                else:
                    self.build_index(space=sp_name, force=True)

        # 2. 構建全域查詢倒排索引 (直接聚合各空間 Posting 清單，保留各空間標籤且極致迅速)
        merged_index = InvertedIndex(space_name="merged")
        for sp in targets:
            idx = self._index_cache.get(sp.name)
            if idx:
                for term, postings in idx.index.items():
                    merged_index.index[term].extend(postings)
                merged_index.doc_count += idx.doc_count
                for f in InvertedIndex.INDEXED_FIELDS:
                    merged_index.field_total_lengths[f] += idx.field_total_lengths.get(f, 0)
                merged_index.symbols_map.update(idx.symbols_map)

        if merged_index.doc_count > 0:
            for f in InvertedIndex.INDEXED_FIELDS:
                merged_index.field_avgdl[f] = max(
                    1.0, merged_index.field_total_lengths[f] / merged_index.doc_count
                )
        else:
            return []

        # 3. 執行檢索
        flt = QueryFilter(
            spaces=[space] if space else None,
            languages=languages,
            kinds=kinds,
            min_score=min_score,
            limit=limit,
        )

        return self.bm25_engine.search(query=query, index=merged_index, filter_cfg=flt)

    def clean(self, space: Optional[str] = None) -> None:
        """
        清理指定空間或全空間之指紋快取、Bundle 檔案與倒排索引快取 (EC-03)。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        for sp in targets:
            sp_name = sp.name
            # 1. 清理指紋
            fp_file = self.space_manager.get_space_storage_dir(sp_name) / "fingerprints.json"
            if fp_file.exists():
                try:
                    fp_file.unlink()
                except OSError:
                    pass

            # 2. 清理 Bundle
            bundle_file = self.storage_dir / "bundles" / f"{sp_name}.bundle.json"
            if bundle_file.exists():
                try:
                    bundle_file.unlink()
                except OSError:
                    pass

            # 3. 清理索引
            idx_file = self.storage_dir / "indices" / f"{sp_name}.index.json"
            if idx_file.exists():
                try:
                    idx_file.unlink()
                except OSError:
                    pass

            # 4. 清理記憶體快取
            self._index_cache.pop(sp_name, None)
