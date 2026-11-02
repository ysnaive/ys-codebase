"""
YS-Codebase Knowledge-DB Module
Provides BM25 + ONNX Hybrid RRF semantic retrieval consuming AST snapshots from module:ast.
"""

from pathlib import Path
import sys


def _ensure_dependency_module_paths() -> None:
    """確保依賴模組 (module:file-space 與 module:ast) 的套件目錄已掛載至 sys.path。"""
    try:
        from core import uri

        for mod_uri, pkg_name in (("module://file-space", "file_space"), ("module://ast", "ast_engine")):
            mod_dir = uri.resolve(mod_uri, interactive=False)
            if mod_dir:
                m_path = Path(mod_dir).resolve()
                if (m_path / pkg_name / "__init__.py").is_file() and str(m_path) not in sys.path:
                    sys.path.insert(0, str(m_path))
    except Exception:
        pass
    pkg_parent = Path(__file__).resolve().parent.parent.parent
    for mod_folder, pkg_name in (("file-space", "file_space"), ("ast", "ast_engine")):
        for cand in (pkg_parent / mod_folder, pkg_parent.parent / ".modules" / mod_folder):
            if (cand / pkg_name / "__init__.py").is_file():
                cand_str = str(cand.resolve())
                if cand_str not in sys.path:
                    sys.path.insert(0, cand_str)
        existing_mod = sys.modules.get(pkg_name)
        if existing_mod is not None and getattr(existing_mod, "__file__", None) is None:
            del sys.modules[pkg_name]


_ensure_dependency_module_paths()

from ast_engine import ASTEngine, ASTSnapshot, SemanticBundle, SemanticBundler
from .config import DEFAULT_EMBEDDING_MODEL, KnowledgeDBConfig
from .embedding import EmbeddingService, VectorIndex
from .engine import KnowledgeEngine
from .exceptions import (
    InvalidConfigError,
    KnowledgeDBError,
    SchemaValidationError,
)
from .hybrid import HybridSearchEngine
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
    "ASTEngine",
    "ASTSnapshot",
    "SymbolKind",
    "LanguageType",
    "KnowledgeDBContributes",
    "validate_space_weights",
    "MemberInfo",
    "UnifiedSymbol",
    "SymbolCallSite",
    "AggregatedItem",
    "AggregatedFileResult",
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
]
