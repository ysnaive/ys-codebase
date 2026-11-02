"""
Internal core engine package (`ast_engine`) for `module:ast@1.0.0.0`.
"""

from pathlib import Path
import sys


def _ensure_dependency_module_paths() -> None:
    """Ensure dependency module (`module:file-space`) package directory is mounted in `sys.path`."""
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

from .bundler import (
    SemanticBundler,
    aggregate_partial_symbols,
    ensure_unique_overload_ids,
    restore_unaggregated_partial_symbol,
)
from .dialects import DialectAdapter, get_dialect, register_dialect
from .engine import ASTEngine, get_engine, reset_default_engine
from .exceptions import (
    ASTCorruptedError,
    ASTError,
    ASTIndexNotFoundError,
    InvalidConfigError,
    SchemaValidationError,
)
from .formatter import (
    ASTResultFormatter,
    TerminalStyler,
    format_json,
)
from .graph import CallGraphIndex
from .io_utils import (
    atomic_save_gzip_pickle,
    compute_project_relpath,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
    resolve_project_root,
)
from .linker import TopologyLinker, expand_contract_symbol_ids
from .parsers import (
    BaseParser,
    CssParser,
    HtmlParser,
    MarkdownParser,
    ParserRegistry,
    PythonASTParser,
    SpiceParser,
    TreeSitterDriver,
)
from .provisioner import GrammarProvisioner
from .resolver import (
    CodeSnippet,
    DeterministicSymbolResolver,
    ParsedSelector,
    SnippetExtractor,
    SymbolResolutionResult,
    SymbolSelector,
    query_callees,
    query_callers,
    query_impact,
)
from .schema import (
    ASTSnapshot,
    LanguageConfig,
    LanguageType,
    MemberInfo,
    OutlineNode,
    OutlineResult,
    SemanticBundle,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
)

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
