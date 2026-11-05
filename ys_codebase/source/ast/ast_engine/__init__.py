"""
Internal core engine package (`ast_engine`) for `module:ast@1.0.0.0`.
Uses PEP 562 module-level `__getattr__` lazy loading so top-level package imports remain zero-overhead and free of third-party imports until symbols are accessed.
"""

import importlib
from typing import Any, Dict, List, Tuple

__version__ = "1.0.1.2"

_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    "SemanticBundler": (".bundler", "SemanticBundler"),
    "aggregate_partial_symbols": (".bundler", "aggregate_partial_symbols"),
    "ensure_unique_overload_ids": (".bundler", "ensure_unique_overload_ids"),
    "restore_unaggregated_partial_symbol": (".bundler", "restore_unaggregated_partial_symbol"),
    "DialectAdapter": (".dialects", "DialectAdapter"),
    "get_dialect": (".dialects", "get_dialect"),
    "register_dialect": (".dialects", "register_dialect"),
    "ASTEngine": (".engine", "ASTEngine"),
    "get_engine": (".engine", "get_engine"),
    "reset_default_engine": (".engine", "reset_default_engine"),
    "ASTCorruptedError": (".exceptions", "ASTCorruptedError"),
    "ASTError": (".exceptions", "ASTError"),
    "ASTIndexNotFoundError": (".exceptions", "ASTIndexNotFoundError"),
    "InvalidConfigError": (".exceptions", "InvalidConfigError"),
    "SchemaValidationError": (".exceptions", "SchemaValidationError"),
    "ASTResultFormatter": (".formatter", "ASTResultFormatter"),
    "TerminalStyler": (".formatter", "TerminalStyler"),
    "format_json": (".formatter", "format_json"),
    "CallGraphIndex": (".graph", "CallGraphIndex"),
    "atomic_save_gzip_pickle": (".io_utils", "atomic_save_gzip_pickle"),
    "compute_project_relpath": (".io_utils", "compute_project_relpath"),
    "is_dirty_file_match": (".io_utils", "is_dirty_file_match"),
    "load_gzip_pickle": (".io_utils", "load_gzip_pickle"),
    "normalize_dirty_paths": (".io_utils", "normalize_dirty_paths"),
    "resolve_project_root": (".io_utils", "resolve_project_root"),
    "TopologyLinker": (".linker", "TopologyLinker"),
    "expand_contract_symbol_ids": (".linker", "expand_contract_symbol_ids"),
    "BaseParser": (".parsers", "BaseParser"),
    "CssParser": (".parsers", "CssParser"),
    "HtmlParser": (".parsers", "HtmlParser"),
    "MarkdownParser": (".parsers", "MarkdownParser"),
    "ParserRegistry": (".parsers", "ParserRegistry"),
    "PythonASTParser": (".parsers", "PythonASTParser"),
    "SpiceParser": (".parsers", "SpiceParser"),
    "TreeSitterDriver": (".parsers", "TreeSitterDriver"),
    "GrammarProvisioner": (".provisioner", "GrammarProvisioner"),
    "CodeSnippet": (".resolver", "CodeSnippet"),
    "DeterministicSymbolResolver": (".resolver", "DeterministicSymbolResolver"),
    "ParsedSelector": (".resolver", "ParsedSelector"),
    "SnippetExtractor": (".resolver", "SnippetExtractor"),
    "SymbolResolutionResult": (".resolver", "SymbolResolutionResult"),
    "SymbolSelector": (".resolver", "SymbolSelector"),
    "query_callees": (".resolver", "query_callees"),
    "query_callers": (".resolver", "query_callers"),
    "query_impact": (".resolver", "query_impact"),
    "ASTSnapshot": (".schema", "ASTSnapshot"),
    "LanguageConfig": (".schema", "LanguageConfig"),
    "LanguageType": (".schema", "LanguageType"),
    "MemberInfo": (".schema", "MemberInfo"),
    "OutlineNode": (".schema", "OutlineNode"),
    "OutlineResult": (".schema", "OutlineResult"),
    "SemanticBundle": (".schema", "SemanticBundle"),
    "SymbolCallSite": (".schema", "SymbolCallSite"),
    "SymbolKind": (".schema", "SymbolKind"),
    "UnifiedSymbol": (".schema", "UnifiedSymbol"),
}

__all__ = [
    "ASTCorruptedError",
    "ASTEngine",
    "ASTError",
    "ASTIndexNotFoundError",
    "ASTResultFormatter",
    "ASTSnapshot",
    "BaseParser",
    "CallGraphIndex",
    "CodeSnippet",
    "CssParser",
    "DeterministicSymbolResolver",
    "DialectAdapter",
    "GrammarProvisioner",
    "HtmlParser",
    "InvalidConfigError",
    "LanguageConfig",
    "LanguageType",
    "MarkdownParser",
    "MemberInfo",
    "OutlineNode",
    "OutlineResult",
    "ParsedSelector",
    "ParserRegistry",
    "PythonASTParser",
    "SchemaValidationError",
    "SemanticBundle",
    "SemanticBundler",
    "SnippetExtractor",
    "SpiceParser",
    "SymbolCallSite",
    "SymbolKind",
    "SymbolResolutionResult",
    "SymbolSelector",
    "TerminalStyler",
    "TopologyLinker",
    "TreeSitterDriver",
    "UnifiedSymbol",
    "aggregate_partial_symbols",
    "atomic_save_gzip_pickle",
    "compute_project_relpath",
    "ensure_unique_overload_ids",
    "expand_contract_symbol_ids",
    "format_json",
    "get_dialect",
    "get_engine",
    "is_dirty_file_match",
    "load_gzip_pickle",
    "normalize_dirty_paths",
    "query_callees",
    "query_callers",
    "query_impact",
    "register_dialect",
    "reset_default_engine",
    "resolve_project_root",
    "restore_unaggregated_partial_symbol",
]


def __getattr__(name: str) -> Any:
    """PEP 562 module-level lazy attribute loader."""
    if name in _LAZY_EXPORTS:
        mod_rel, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(mod_rel, __name__)
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(list(globals().keys()) + list(__all__))
