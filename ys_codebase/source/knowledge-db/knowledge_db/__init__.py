"""
YS-Codebase Knowledge-DB Module
Provides semantic symbol extraction (Universal AST v2.0), BM25 + ONNX Hybrid RRF retrieval,
and Call Graph Topology analysis.
"""

from pathlib import Path
import sys


def _ensure_dependency_module_paths() -> None:
    """確保依賴模組 (module:file-space) 的套件目錄已掛載至 sys.path。"""
    try:
        from core import uri

        space_mod_dir = uri.resolve("module://file-space", interactive=False)
        if space_mod_dir:
            sp_path = Path(space_mod_dir).resolve()
            if (sp_path / "file_space" / "__init__.py").is_file() and str(sp_path) not in sys.path:
                sys.path.insert(0, str(sp_path))
    except Exception:
        pass
    pkg_parent = Path(__file__).resolve().parent.parent.parent
    for cand in (pkg_parent / "file-space", pkg_parent.parent / ".modules" / "file-space"):
        if (cand / "file_space" / "__init__.py").is_file():
            cand_str = str(cand.resolve())
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)
    existing_space = sys.modules.get("file_space")
    if existing_space is not None and getattr(existing_space, "__file__", None) is None:
        del sys.modules["file_space"]


_ensure_dependency_module_paths()

from .bundler import SemanticBundle, SemanticBundler
from .config import DEFAULT_EMBEDDING_MODEL, KnowledgeDBConfig
from .embedding import EmbeddingService, VectorIndex
from .engine import KnowledgeEngine
from .exceptions import (
    InvalidConfigError,
    KnowledgeDBError,
    SchemaValidationError,
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
from .schema import (
    AggregatedFileResult,
    AggregatedItem,
    KnowledgeDBContributes,
    LanguageConfig,
    LanguageType,
    MemberInfo,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
    validate_space_weights,
)
from .selector import ParsedSelector, SymbolSelector
from .service import KnowledgeDBServiceWorker, get_worker_busy_ms, is_worker_running
from .tokenizer import MultilingualTokenizer

__version__ = "1.3.0.0"

__all__ = [
    "KnowledgeEngine",
    "KnowledgeDBServiceWorker",
    "get_worker_busy_ms",
    "is_worker_running",
    "KnowledgeDBConfig",
    "DEFAULT_EMBEDDING_MODEL",
    "KnowledgeDBError",
    "InvalidConfigError",
    "SchemaValidationError",
    "SymbolKind",
    "LanguageType",
    "LanguageConfig",
    "KnowledgeDBContributes",
    "validate_space_weights",
    "MemberInfo",
    "UnifiedSymbol",
    "SymbolCallSite",
    "AggregatedItem",
    "AggregatedFileResult",
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
