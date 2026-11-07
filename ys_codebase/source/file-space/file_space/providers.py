"""
Deprecated documentation token providers for the file-space module.
Delegates directly to core.space.providers.
"""
from typing import Any, Optional

from core.space.providers import (
    _resolve_knowledge_db_indexed_space_names,
    get_knowledge_db_spaces as _core_get_knowledge_db_spaces,
    get_registered_file_spaces_table as _core_get_registered_file_spaces_table,
)


def get_registered_file_spaces_table(context: Optional[Any] = None) -> str:
    """Delegate registered file spaces Markdown table generation to core.space.providers."""
    return _core_get_registered_file_spaces_table(context=context)


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """Delegate knowledge-db spaces Markdown table generation to core.space.providers."""
    return _core_get_knowledge_db_spaces(context=context, **kwargs)


__all__ = [
    "_resolve_knowledge_db_indexed_space_names",
    "get_knowledge_db_spaces",
    "get_registered_file_spaces_table",
]
