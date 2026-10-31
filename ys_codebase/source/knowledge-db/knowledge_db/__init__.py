"""
YS-Codebase Knowledge-DB Module
Provides semantic symbol extraction (Universal AST v2.0), incremental fingerprint scanning,
BM25 + ONNX Hybrid RRF retrieval, and Call Graph Topology analysis.
"""

from .bundler import SemanticBundle, SemanticBundler
from .config import DEFAULT_EMBEDDING_MODEL, KnowledgeDBConfig
from .embedding import EmbeddingService, VectorIndex
from .engine import KnowledgeEngine
from .exceptions import (
    FingerprintCorruptedError,
    InvalidSpaceConfigError,
    KnowledgeDBError,
    SchemaValidationError,
    SpaceNotFoundError,
)
from .graph import CallGraphIndex
from .hybrid import HybridSearchEngine
from .linker import TopologyLinker
from .parsers import (
    BaseParser,
    CssParser,
    HtmlParser,
    ParserRegistry,
    SpiceParser,
    TreeSitterDriver,
)
from .retrieval import (
    BM25Engine,
    CodeSnippet,
    InvertedIndex,
    Posting,
    QueryFilter,
    SearchResult,
    SnippetExtractor,
)
from .scanner import FileFingerprint, FingerprintScanner, ScanDiffResult
from .schema import (
    AggregatedFileResult,
    AggregatedItem,
    LanguageConfig,
    LanguageType,
    MemberInfo,
    SpaceConfig,
    SpaceOrigin,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
)
from .selector import ParsedSelector, SymbolSelector
from .space import SpaceManager
from .tokenizer import MultilingualTokenizer

__version__ = "1.1.2.0"

__all__ = [
    "KnowledgeEngine",
    "KnowledgeDBConfig",
    "DEFAULT_EMBEDDING_MODEL",
    "KnowledgeDBError",
    "SpaceNotFoundError",
    "InvalidSpaceConfigError",
    "SchemaValidationError",
    "FingerprintCorruptedError",
    "SymbolKind",
    "LanguageType",
    "LanguageConfig",
    "SpaceOrigin",
    "MemberInfo",
    "UnifiedSymbol",
    "SymbolCallSite",
    "SpaceConfig",
    "AggregatedItem",
    "AggregatedFileResult",
    "SpaceManager",
    "FileFingerprint",
    "ScanDiffResult",
    "FingerprintScanner",
    "BaseParser",
    "TreeSitterDriver",
    "SpiceParser",
    "HtmlParser",
    "CssParser",
    "ParserRegistry",
    "SemanticBundle",
    "SemanticBundler",
    "MultilingualTokenizer",
    "SymbolSelector",
    "ParsedSelector",
    "Posting",
    "InvertedIndex",
    "QueryFilter",
    "CodeSnippet",
    "SnippetExtractor",
    "SearchResult",
    "BM25Engine",
    "EmbeddingService",
    "VectorIndex",
    "HybridSearchEngine",
    "CallGraphIndex",
    "TopologyLinker",
]
