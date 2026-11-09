"""
YS-Codebase Knowledge-DB Module
Provides BM25 + ONNX Hybrid RRF semantic retrieval consuming AST snapshots from module:ast.
Uses PEP 562 module-level `__getattr__` lazy loading so top-level package imports remain lightweight and free of third-party imports until symbols are accessed.
"""

import importlib
from types import MappingProxyType
from typing import Any, Dict, List, Tuple

__version__ = "1.2.2.1"

_LAZY_EXPORTS: Any = MappingProxyType({
    "ASTEngine": ("ast_engine", "ASTEngine"),
    "ASTSnapshot": ("ast_engine", "ASTSnapshot"),
    "SemanticBundle": ("ast_engine", "SemanticBundle"),
    "SemanticBundler": ("ast_engine", "SemanticBundler"),
    "DEFAULT_EMBEDDING_MODEL": (".config", "DEFAULT_EMBEDDING_MODEL"),
    "KnowledgeDBConfig": (".config", "KnowledgeDBConfig"),
    "EmbeddingService": (".embedding", "EmbeddingService"),
    "VectorIndex": (".embedding", "VectorIndex"),
    "KnowledgeEngine": (".engine", "KnowledgeEngine"),
    "InvalidConfigError": (".exceptions", "InvalidConfigError"),
    "KnowledgeDBError": (".exceptions", "KnowledgeDBError"),
    "SchemaValidationError": (".exceptions", "SchemaValidationError"),
    "HybridSearchEngine": (".hybrid", "HybridSearchEngine"),
    "BM25Engine": (".retrieval", "BM25Engine"),
    "CodeSnippet": (".retrieval", "CodeSnippet"),
    "InvertedIndex": (".retrieval", "InvertedIndex"),
    "Posting": (".retrieval", "Posting"),
    "QueryFilter": (".retrieval", "QueryFilter"),
    "SearchResult": (".retrieval", "SearchResult"),
    "SnippetExtractor": (".retrieval", "SnippetExtractor"),
    "AggregatedFileResult": (".schema", "AggregatedFileResult"),
    "AggregatedItem": (".schema", "AggregatedItem"),
    "KnowledgeDBContributes": (".schema", "KnowledgeDBContributes"),
    "LanguageType": (".schema", "LanguageType"),
    "MemberInfo": (".schema", "MemberInfo"),
    "SymbolCallSite": (".schema", "SymbolCallSite"),
    "SymbolKind": (".schema", "SymbolKind"),
    "UnifiedSymbol": (".schema", "UnifiedSymbol"),
    "validate_space_weights": (".schema", "validate_space_weights"),
    "ParsedSelector": (".selector", "ParsedSelector"),
    "SymbolSelector": (".selector", "SymbolSelector"),
    "KnowledgeDBServiceWorker": (".service", "KnowledgeDBServiceWorker"),
    "get_worker_busy_ms": (".service", "get_worker_busy_ms"),
    "is_worker_running": (".service", "is_worker_running"),
    "MultilingualTokenizer": (".tokenizer", "MultilingualTokenizer"),
})

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


def __getattr__(name: str) -> Any:
    """PEP 562 module-level lazy attribute loader."""
    if name in _LAZY_EXPORTS:
        mod_rel, attr_name = _LAZY_EXPORTS[name]
        if mod_rel.startswith("."):
            module = importlib.import_module(mod_rel, __name__)
        else:
            module = importlib.import_module(mod_rel)
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals().keys()) | set(__all__))
